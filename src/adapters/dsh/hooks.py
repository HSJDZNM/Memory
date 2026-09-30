"""dsh pre-execute / post-execute Hook：策略判定、受控执行与审计。

数据流（Phase 2 文档第 4 步）：

    PreToolUse   dsh tool request → Adapter → Policy Engine → allow: 执行一次
                                                            → block: 结构化违规，不执行
    PostToolUse  工具已执行 → 基线/证据比对 → validate → validated / repair_required

dsh 侧的真实契约（0.1.5-rc.1，证据见 src/adapters/dsh/README.md）：

- Hook 是一个**外部命令**：dsh 把事件 JSON 写到它的 stdin，命令按 PowerShell 语法执行；
- **exit 2 表示阻断**，stderr 作为理由显示给模型；其他非 0 退出、启动失败、
  被超时杀掉，对 dsh 都只是"非阻断失败"——**工具照样执行**；
- 因此失败关闭不可能靠 dsh 给：必须由本模块自己保证。这里做三件事：
  1) 内部预算（timeout_ms）严格小于 hooks.json 里的 timeout，超预算自己判 block；
  2) 捕获所有异常并转成 exit 2，绝不让解释器以退出码 1 结束；
  3) hooks.json 读不到等于零 hook 注册，所以运行期用 --self-check 显式验证接线，
     且**自检缺席本身就按失败关闭处理**（没有接线证据 = 证明不了治理生效）。

治理覆盖面的四条可见性约定（G3 / G11 / G12 与 P1 修复）：

- 审计记录里 effective_rule_count / skipped_rule_count / skipped_reason 把
  "查了并通过"与"被跳过"分开（跳过绝不等于通过）；
- 判定记录里的 violations 列出**真的报了违规**的规则（canonical rule_id + severity +
  message + evidence），与"参与过判定"的 matched_rules 分开；没有做出判定的记录
  （context_error / evidence_unavailable / event_replay 等）没有这个键；

- 会进入 AI 上下文的项目约定文档（AGENTS.md / CLAUDE.md）的来源路径与内容哈希
  在会话起点附近记一次，供事后核对"模型看到的约定"是不是评审过的那一份；
- 每个受治理动作在审计里带 hook_event（PreToolUse / PostToolUse）与 action_id，
  成对契约可以在这份产物上直接判定"缺了哪一段"。

本模块不导入 dsh、不读源码文件、不调用 LLM：策略判定完全由核心 policy 包完成。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Protocol, Sequence

from enforcement.audit import FileAuditSink, redact_text
from enforcement.ledger import EnforcementLedger
from policy.checkers import CONTEXT_CHECKERS
from policy.engine import EngineError, evaluate
from policy.evidence import EvidenceBundle
from policy.loader import LoaderError, load_rule_set
from policy.models import (
    BLOCKING_SEVERITIES,
    SCHEMA_VERSION,
    Decision,
    PolicyContextError,
    RequiredAction,
    RuleSet,
    ValidationResult,
)
from policy.obligations import book_pending_findings
from provenance import reading_context as reading
from provenance.origin import Origin
from provenance.origin_runtime import ORIGIN_BY_REASON_CODE, origin_from_failure

from .adapter import (
    HOOK_EVENT_POST_TOOL_USE,
    TOOL_TABLE,
    AdapterConfig,
    DshEventError,
    PolicyEvent,
    ToolKind,
    load_config,
    to_policy_context,
    to_policy_event,
)
from .enforcement import EnforcementBridge, EnforcementUnavailable, bridge_from_config
from .pre_evidence import PreEvidenceError, PreEvidenceResult, build_pre_evidence

__all__ = [
    "EXIT_ALLOW",
    "EXIT_BLOCK",
    "AUDIT_SCHEMA_VERSION",
    "ORIGIN_PREFIX",
    "PRE_EVIDENCE_STATUSES",
    "VERDICT_PREFIX",
    "VERDICT_SCHEMA_VERSION",
    "AuditLedger",
    "ControlledExecutor",
    "DshPreExecuteHook",
    "EvidenceProvider",
    "ExecutionOutcome",
    "HookOutcome",
    "NullExecutor",
    "PolicyTimeout",
    "build_parser",
    "enforcement_feedback",
    "feedback_text",
    "main",
    "EFFECTIVE_PATHS_PREFIX",
    "effective_paths",
    "effective_paths_line",
    "origin_line",
    "run_hook",
    "sanitize",
    "verdict_line",
]

# dsh 协议：0 = 放行；2 = 阻断（stderr 即阻断理由）。没有第三种"警告"出口。
EXIT_ALLOW = 0
EXIT_BLOCK = 2

# 1.1（台阶 3a / H1）：判定记录新增**受控** `decision_reason`（"这次 block 属于哪一类"）。
# 判定记录是审计协议的一部分，改键集合就按它自己的规则递增版本号——**3a 当时**决策协议
# （1.0）不动：这个值是**从已有字段派生**的，不是第二份判定（见 `decision_reason`）。
# （台阶 3b 之后决策协议是 1.1，那是**另一套**协议，与本行的理由无关。）
#
# 1.2（台阶 3b / D-1(b)）：判定记录新增 `pending_findings` 通道。为什么必须加这个键：
# 决策协议的 pending 移出 `violations` 之后，"判定了、有一条待实现"与"判定了、没违规"
# 在账本上会重新变得一样（两者的 violations 都是空），而这正是 P1 修掉的那类同名两义。
# 按统一规则（任何协议载荷加键或改语义都递增该协议自己的版本号）递增到 1.2——
# 决策协议那一侧的 1.0→1.1 是**另一套**协议，两个版本各自演进。
#
# 1.3（台阶 4 / 21 号 §2.2）：判定记录新增两处——顶层的 `reading_context`（这条记录属于
# 哪棵树 / 哪一套声明 / 哪台宿主）与 `pre_evidence.registry`（本次取证读的是哪一版
# validation/validators.yaml；18 号 §2 的 R4：没有它，同一条 tool.pytest@1.0 在账本里
# 对应三种行为）。两条都是"加键"，所以按本协议自己的规则递增（第 55 条）；
# 决策协议、证据协议、VERDICT 行都不动——它们是**另外几套**协议。
AUDIT_SCHEMA_VERSION = "1.3"

# 反馈文本长度上限：阻断理由会进入模型上下文，必须足够短且不含敏感内容。
FEEDBACK_MAX_CHARS = 4000

# N18：阻断判定行的机读协议。
#
# 为什么需要它：dsh 在本机把 Hook 的非 0 退出码压成 1（机制与最小复现见 README §2.3），
# 于是"exit 2 = 策略阻断"这条契约在真实会话里读不到，插件的理由分类退化成"未知状态"。
# 退出码是**传输事实**，判定是**策略事实**：把判定单独写成一行，理由分类就不再依赖
# 退出码保真。这一行只影响"为什么被拒"的措辞，**不影响是否拒绝**：任何非 0 退出仍然
# 一律阻断，解析失败也一样（没有判定行 = 未知状态 = 失败关闭）。
VERDICT_SCHEMA_VERSION = "1.0"
VERDICT_PREFIX = "[policy] VERDICT "

# 台阶 2（方案 §3.4 / R-g）：归因闭集的**机读**出口。
#
# 为什么不塞进 VERDICT 行：VERDICT 是 N18 的既有协议，消费方（JS 插件）按精确版本号读，
# 改它的键集合就必须同步改两侧并让"版本不认识 → 未知状态"这条失败关闭重新走一遍。
# 归因是**诊断**，不是判定：另起一行，读不到就只是读不到，任何一侧的不认识都不会改
# allow/block。这一行的载荷形状由 provenance.origin 冻结（跨语言契约）。
ORIGIN_PREFIX = "[policy] ORIGIN "

# N21：带 --audit 时台账路径由审计路径派生，adapter 配置里的 enforcement_ledger 被覆盖。
# 派生本身是对的（Phase 2 的记录与 Phase 4 的链要落在同一份证据里，两种 JSONL 协议不能
# 混写），但它让"按配置名去数台账"的人得到 0 条，于是误判"事后核对从来没跑过"。
# 处置：把生效路径变成一等输出（自检行 + 审计记录），不一致时显式警告。
EFFECTIVE_PATHS_PREFIX = "[policy] effective-paths "

# G3/M2：动手前取证的状态值域（封闭枚举）。读账本的人必须能一眼分清五件事——
# 缺任何一个值，"跳过"都会重新长成"通过"：
#   not_declared   配置里没有 pre_evidence（Phase 2 契约：证据类 checker 进 skipped_rules）
#   disabled       声明了但 enabled=false（显式关闭，不是"取不到"）
#   collected      本次真的取到了证据并交给了引擎
#   unavailable    声明并启用，但取证失败（已按失败关闭阻断，exit 2）
#   not_applicable 该动作没有文件维度（执行类），取证不适用
PRE_EVIDENCE_STATUSES = (
    "not_declared",
    "disabled",
    "collected",
    "unavailable",
    "not_applicable",
)

# dsh 的默认 hook 超时：hooks.json 没写 timeout 时用桥的 defaultTimeoutMs（README §2.5）。
# pre_evidence 的预算不等式必须把它写成显式事实——"没写 timeout"不等于"没有上限"。
DEFAULT_HOOK_TIMEOUT_MS = 600_000

LEDGER_OVERRIDE_NOTE = (
    "--audit 派生优先：Phase 2 的审计记录与 Phase 4 的台账是两份不同的 JSONL 协议，"
    "不能混写；按配置声明的 enforcement_ledger 去数台账会得到 0 条"
)

# P1：判定记录里的违规可见性。
#
# 为什么口径必须写死在账本里：matched_rules 的语义是"参与过判定"。06 轮参与面只有 1 条时，
# "参与"与"报违规"在账本上长得一样；07 轮治理全开之后参与面变成 43 条，block 与
# allow_with_warnings 的记录里于是**一条真正报违规的规则都读不出来**——那份清单只活在
# 给模型看的 stderr 里。三个词必须能分开读：真的报了违规 / 参与过判定 / 没有做出判定。
VIOLATIONS_NOTE = (
    "violations 是本次**真的报了违规**的规则；matched_rules 是本次**参与过判定**的规则；"
    "两者不是一回事，warning 命中只产出 allow_with_warnings。"
    "pending_findings 是第三个、也是唯一一个**不是违规**的通道：「待实现」——选中的测试因"
    "项目内目标还不存在而没能收集，覆盖它的测试尚未运行。它不阻断，也不进 violations，"
    "所以一条 allow_with_warnings 记录可能 violations 为空而 pending_findings 非空："
    "那种记录说的是「这次放行了、但有东西没能查成」，不是「什么都没发生」。"
    "没有 violations 键的记录（context_error / evidence_unavailable / event_replay 等）"
    "表示本次没有做出判定——「没判定」与「判定了、没违规」必须能分开读"
)

# 绝对路径的识别必须带**边界**：没有边界的 "/" 会把普通仓库相对路径
# （src/shop/order_service.py）也当成绝对路径，账本里于是只剩 "src<abs>"，
# 而"这次查的是哪个文件"正是审计要回答的问题。边界 = 串首，或空白 / 引号 /
# 括号 / 等号 / 冒号 / 逗号之后。
# 全角标点同样算边界：归因的 observation.result 是「（路径）」这种中英混排形态，
# 只认 ASCII 括号会让整个绝对路径原样漏过（台阶 3a 实测，见 10-h4-field-diff / 11 号 §7.5）。
_ABS_PATH_BOUNDARY = r"(?:(?<=[\s'\"(\[=:,\uff08\uff09\u3001\uff0c\u3002\uff1b\uff1a])|^)"
_ABS_PATH_RE = re.compile(_ABS_PATH_BOUNDARY + r"(?:[A-Za-z]:[\\/]|\\\\|/)[^\s'\"]+")
# 含空格的绝对路径：上一条在空白处截断，`C:\Program Files\nodejs\node.exe` 只会被抹掉
# `C:\Program`，尾巴留在账本里（实测；这正是 11-step2-origin-closure.md §7.5 点名的真机串）。
# 第二条整段匹配「盘符/UNC 起、到行尾或成对包边标点为止」，因此只在**成对包边或行尾**这一侧收敛，
# 不会跨过句读吃掉后面的话；同一段被上一条先抹掉时它无副作用（幂等）。
# 结构写成「卷标 + 一段段路径」，段内允许空格——但这**必然**多吞掉同一行里路径之后的
# 尾随词（`...node.exe ENOENT` → `<abs>`）："哪些空格属于路径"在没有引号的语言里不可判。
# 取舍按「失败关闭」写：**宁可多抹，也不留半截路径**（半截路径正是要修的那个缺陷），
# 代价是同一行的诊断词可能一起消失——这个代价写在文档里，不假装没有。
_ABS_PATH_COMPONENT = r"[^\\/\r\n'\"\[\]()\uff08\uff09\u3001\uff0c\u3002\uff1b\uff1a]+"
_ABS_PATH_RELAXED = re.compile(
    _ABS_PATH_BOUNDARY
    + r"(?:[A-Za-z]:[\\/]|\\\\|/)"
    + _ABS_PATH_COMPONENT
    + r"(?:[\\/]" + _ABS_PATH_COMPONENT + r")*"
    + r"(?:[ \t]+" + _ABS_PATH_COMPONENT + r")*"
)
_SECRET_RE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_\-]{8,}|api[_-]?key\s*[=:]\s*\S+|authorization:\s*\S+|bearer\s+\S+)"
)


# G11：会进入 AI 上下文的项目约定文档。**只按显式声明的文件名在项目根查找**：
# 多一个文件就等于多一份进入模型上下文的内容，必须由人显式加进这张表；
# 这里不做目录扫描，也不从文件内容推断"它算不算项目约定"。
CONTEXT_DOCUMENTS: tuple[str, ...] = ("AGENTS.md", "CLAUDE.md")


def call_action_id(raw_payload: Any) -> Optional[str]:
    """dsh 调用标识 → Phase 4 口径的 action_id（与 enforcement.py 的口径一致）。

    PreToolUse 与 PostToolUse 只有靠这个标识才能接回同一个动作。载荷缺字段时返回 None：
    调用方据此把该事件判成失败关闭，而不是编一个标识出来（编出来的标识会让"事后核对"
    接错动作，比没有标识更危险）。
    """

    if not isinstance(raw_payload, Mapping):
        return None
    session_id = str(raw_payload.get("session_id") or "")
    tool_use_id = str(raw_payload.get("tool_use_id") or "")
    if session_id and tool_use_id:
        return f"{session_id}:{tool_use_id}"
    if tool_use_id or session_id:
        return tool_use_id or session_id
    return None


class PolicyTimeout(Exception):
    """策略判定超出内部预算：按失败策略阻断，不执行工具。"""


def sanitize(
    text: str, *, project_root: Optional[Path] = None, limit: int = FEEDBACK_MAX_CHARS
) -> str:
    """脱敏：去掉绝对路径与密钥样式，截断到固定长度。

    返回给模型的内容绝不包含内部堆栈、绝对路径、完整规则库或敏感上下文。
    """

    if not isinstance(text, str):
        text = str(text)
    if project_root is not None:
        variants = {str(project_root), str(project_root).replace("\\", "/")}
        for variant in variants:
            if variant:
                text = text.replace(variant, "<repo>")
    # 顺序要紧：先跑"整段"那条（它认得含空格的路径），再跑"到空白为止"那条兜住其余形态。
    # 反过来写会把 `C:\Program Files\...` 先切成 `<abs> Files\...`，尾巴再也抹不掉（实测）。
    text = _ABS_PATH_RELAXED.sub("<abs>", text)
    text = _ABS_PATH_RE.sub("<abs>", text)
    text = _SECRET_RE.sub("<redacted>", text)
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


def _sanitized(value: Any, *, project_root: Optional[Path]) -> Any:
    """递归脱敏：审计里的字符串一律走 sanitize。

    一条违规的 message / evidence 都可能带路径与工具原文，而"绝对路径与凭据不得进审计"
    （AGENTS 第 16 条）不因为字段嵌套一层就放松。递归只处理容器与字符串，其余原样返回。
    """

    if isinstance(value, str):
        return sanitize(value, project_root=project_root)
    if isinstance(value, Mapping):
        return {
            key: _sanitized(item, project_root=project_root) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitized(item, project_root=project_root) for item in value]
    return value


# H1：一次 block 属于哪一类。**受控闭集**，由判定载荷里已有的字段派生，绝不猜：
#   approval_required    授权是前置条件（required_action=approval），没有可修的对象；
#   policy_violation     至少一条 violation 是规则报的违规（可修）；
#   evidence_unavailable 全部 violation 都是"平台没能查"（uncovered / blocker），改文件改不掉；
#   None                 说不出来（例如 block + 空 violations 却没有审批要求）——
#                        消费方必须按失败关闭处理，**不许把 None 读成某一种**。
DECISION_REASON_APPROVAL_REQUIRED = "approval_required"
DECISION_REASON_POLICY_VIOLATION = "policy_violation"
DECISION_REASON_EVIDENCE_UNAVAILABLE = "evidence_unavailable"
UNREPAIRABLE_VIOLATION_DETAILS = frozenset({"uncovered_checker", "blocker"})


def decision_reason(decision: ValidationResult) -> Optional[str]:
    """给一次判定算受控 `decision_reason`；allow / allow_with_warnings 返回 None。

    为什么必须有它：`block` + `violations=[]` 是**合法**形态（审批门禁），而账本只写
    "block + 空清单"时，读的人（和下游节点）只能把它读成"没有依据"。归类的规则是**结构**的
    （required_action 与 evidence.kind），不解析任何中文。
    """

    if decision.decision is not Decision.BLOCK:
        return None
    if decision.required_action is RequiredAction.APPROVAL:
        return DECISION_REASON_APPROVAL_REQUIRED
    if not decision.violations:
        return None
    if all(
        violation.evidence.kind == "validator"
        and (violation.evidence.detail or "") in UNREPAIRABLE_VIOLATION_DETAILS
        for violation in decision.violations
    ):
        return DECISION_REASON_EVIDENCE_UNAVAILABLE
    return DECISION_REASON_POLICY_VIOLATION


def _counts_by_severity(names: Iterable[str]) -> dict[str, int]:
    """按严重级别计数（键排序）：M3 的 *_by_severity 与 P1 的 violations_by_severity 共用。

    只有这一份实现，两个字段的"同一口径"才不是靠人工比对维持的：分级名归调用方给
    （规则集里没有的 rule_id 归 "unknown"，违规自带 severity），这里只负责数。
    """

    bucket: dict[str, int] = {}
    for name in names:
        bucket[name] = bucket.get(name, 0) + 1
    return {key: bucket[key] for key in sorted(bucket)}


def context_documents(project_root: Path | str) -> list[dict[str, Any]]:
    """G11：项目根下会进入 AI 上下文的约定文档 → 来源路径 + 内容哈希。

    这是**留痕**，不是对注入内容的策略校验：Hook 载荷里没有"注入了什么"的事实，
    所以这里记录的是"项目根下有哪些约定文档、内容是什么版本"，供事后核对
    "模型看到的约定"与"评审过的约定"是不是同一份。读得到的带上 sha256 与字节数；
    读不到的显式记 present=False —— "没有这个文件"本身也是一条要写下来的结论，
    不能被静默省略成"没有约定文档"。
    """

    documents: list[dict[str, Any]] = []
    root = Path(project_root)
    for name in CONTEXT_DOCUMENTS:
        try:
            data = (root / name).read_bytes()
        except OSError:
            documents.append({"path": name, "present": False})
            continue
        documents.append(
            {
                "path": name,
                "present": True,
                "sha256": "sha256:" + sha256(data).hexdigest(),
                "bytes": len(data),
            }
        )
    return documents


@dataclass(frozen=True)
class ExecutionOutcome:
    """执行器的一次调用结果。

    status 只有三种，刻意保持封闭：executed（确实执行了一次）、
    delegated（本次判定的下游由 Agent 执行，Phase 2 的默认语义）、failed。
    """

    status: str
    detail: str = ""


class ControlledExecutor(Protocol):
    """受控执行器端口：只在 allow 之后被调用，且至多一次。"""

    def execute(self, event: PolicyEvent) -> ExecutionOutcome:
        ...


class EvidenceProvider(Protocol):
    """动手前取证的端口：默认实现是 pre_evidence.build_pre_evidence（Phase 5 真流水线）。

    端口契约（Hook 依赖的全部）：在 pre_evidence.timeout_ms 之内返回一个
    PreEvidenceResult；取不到证据就抛 PreEvidenceError，**不许**返回一份空证据。
    Hook 另外会套一层更大的预算（pre_evidence.timeout_ms + config.timeout_ms），
    并在任何一层超时 / 异常 / 形状不对时按 evidence_unavailable 失败关闭。
    """

    def __call__(
        self,
        raw_payload: Any,
        *,
        event: PolicyEvent,
        config: AdapterConfig,
        rules: RuleSet,
        context: Any,
    ) -> PreEvidenceResult:
        ...


class NullExecutor:
    """生产环境的执行器：Phase 2 里工具由 dsh 自己在 pre-execute 之后调用。

    Hook 放行（exit 0）就是"允许 dsh 执行一次"；这个类只负责把这个事实记录清楚，
    测试则换成记录调用次数与参数的 fake。
    """

    def execute(self, event: PolicyEvent) -> ExecutionOutcome:
        return ExecutionOutcome(
            status="delegated", detail=f"交由 dsh 执行 {event.tool}（pre-execute 之后）"
        )


@dataclass(frozen=True)
class HookOutcome:
    """一次 Hook 处理的完整结果，可直接序列化进审计。"""

    exit_code: int
    reason_code: str
    stderr: str = ""
    stdout: str = ""
    decision: Optional[ValidationResult] = None
    event: Optional[PolicyEvent] = None
    executed: bool = False
    elapsed_ms: int = 0
    # 台阶 2（§3.4）：失败时的结构化归因。默认 None = 这次没有归因（或不需要）。
    # 它**不是**判定的一部分：allow/block 只看 exit_code 与 reason_code。
    origin: Optional[Origin] = None

    @property
    def blocked(self) -> bool:
        return self.exit_code == EXIT_BLOCK


class AuditLedger:
    """追加写的 JSONL 审计与幂等台账。

    每个 hook 调用都是一个新进程，因此"同一 event_id 不重复执行"必须落在文件上：
    审计记录同时充当幂等台账，键是 event_id，值是上一次判定的载荷摘要与结论。
    只写摘要与结论，不写工具参数原文、不写源码内容。
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _entries(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        entries: list[dict[str, Any]] = []
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # 只有最后一行可能因为进程被杀而截断；其余情况视为审计不可信。
                continue
            if isinstance(record, dict):
                entries.append(record)
        return entries

    def lookup(self, event_id: str) -> Optional[dict[str, Any]]:
        """返回该 event_id 上一次已完成的判定（最后一条），没有就返回 None。"""

        found: Optional[dict[str, Any]] = None
        for record in self._entries():
            if record.get("event_id") == event_id and "exit_code" in record:
                found = record
        return found

    def has_record(self, *, reason_code: str, session_id: Optional[str] = None) -> bool:
        """审计里是否已有某个原因码的记录（用于"每个会话只记一次"的幂等判断）。

        session_id 为 None 时按全局判断；否则只认同会话的记录——不同会话各自记录一次，
        否则第二个会话的起点留痕会被当成"已经记过"而丢掉。
        """

        for record in self._entries():
            if record.get("reason_code") != reason_code:
                continue
            if session_id is None or record.get("session_id") == session_id:
                return True
        return False

    def append(self, record: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(dict(record), ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")


def _within_budget(
    run: Callable[[], Any],
    *,
    budget_ms: int,
    on_timeout: Callable[[], BaseException],
    name: str,
) -> Any:
    """在预算内跑一段可能阻塞的调用；超预算就抛 on_timeout() 造的异常。

    用 daemon 线程 + join(timeout) 实现：超时后线程不会阻止解释器退出。
    策略判定与动手前取证共用这一个形状——两处的预算语义必须一致，否则
    "哪一个会先超时"就变成要靠读两个实现来猜的事。预算之和必须严格小于
    hooks.json 的 timeout（check_wiring 会把这条不等式当成接线错误报出来），
    因为 dsh 杀进程在协议里等于放行。
    """

    box: dict[str, Any] = {}

    def run_it() -> None:
        try:
            box["result"] = run()
        except BaseException as error:  # noqa: BLE001 - 任何异常都必须回到调用方
            box["error"] = error

    worker = threading.Thread(target=run_it, name=name, daemon=True)
    worker.start()
    worker.join(budget_ms / 1000)
    if worker.is_alive():
        raise on_timeout()

    error = box.get("error")
    if error is not None:
        raise error
    return box["result"]


def _evaluate_with_budget(
    evaluator: Callable[..., ValidationResult],
    rules: RuleSet,
    context: Any,
    budget_ms: int,
    *,
    evidence: Optional[EvidenceBundle] = None,
) -> ValidationResult:
    """在预算内完成策略判定（Phase 2 契约 + G3 的证据入口）。

    evidence 为 None 时**逐字节保持**既有调用形状：`evaluator(rules, context)` 两个位置参数。
    既有测试与既有消费方注入的是 2 参数替身，改成恒传关键字会让它们全部变成内部错误——
    而"没有声明取证"正是 Phase 2 的默认路径，它必须一点都不变。
    """

    def run() -> ValidationResult:
        if evidence is None:
            return evaluator(rules, context)
        return evaluator(rules, context, evidence=evidence)

    return _within_budget(
        run,
        budget_ms=budget_ms,
        on_timeout=lambda: PolicyTimeout(f"策略判定超过内部预算 {budget_ms} ms"),
        name="policy-evaluate",
    )


def feedback_text(
    *,
    reason_code: str,
    event: Optional[PolicyEvent],
    decision: Optional[ValidationResult],
    detail: str = "",
) -> str:
    """面向模型的阻断理由：规则 ID、严重级别、原因、证据与期望修复方向。"""

    lines: list[str] = []
    header = "[policy] BLOCKED" + (f" {event.tool}" if event else "")
    if event is not None:
        header += f" {event.file}"
    lines.append(f"{header} ({reason_code})")
    if detail:
        lines.append(f"detail: {detail}")
    if decision is not None:
        for violation in decision.violations:
            lines.append(
                f"rule {violation.canonical_id} severity={violation.severity.value}: "
                f"{violation.message}"
            )
            evidence = violation.evidence
            evidence_line = f"evidence: {evidence.kind}={evidence.value}"
            if evidence.detail:
                evidence_line += f" ({evidence.detail})"
            lines.append(evidence_line)
        if decision.required_action is not None:
            lines.append(f"required_action: {decision.required_action.value}")
        lines.append(
            "expected: controller -> service -> repository（不要在该层直接依赖 repository）"
        )
        if event is not None:
            lines.append(f"request: {event.request_id}")
    lines.append(f"schema: {SCHEMA_VERSION} agent: dsh")
    return "\n".join(lines)


def enforcement_feedback(
    *,
    tool: str,
    file: Optional[str],
    reason_code: str,
    checks: Sequence[Any] = (),
    detail: str = "",
) -> str:
    """把 Phase 4 的检查结论渲染成模型可读的阻断理由（只含结构化字段）。"""

    header = f"[policy] BLOCKED {tool}" + (f" {file}" if file else "")
    lines = [f"{header} ({reason_code})"]
    if detail:
        lines.append(f"detail: {detail}")
    for check in checks:
        if getattr(check, "status", None) is not None and check.status.value == "failed":
            lines.append(f"check {check.check}: {check.reason_code.value} {check.detail}")
    lines.append(f"schema: {SCHEMA_VERSION} agent: dsh enforcement: phase-4")
    return chr(10).join(lines)


@dataclass
class DshPreExecuteHook:
    """pre-execute Hook 的实现：Adapter → Engine → （Phase 4）受控执行门禁 → 执行或阻断。"""

    config: AdapterConfig
    rules: RuleSet
    executor: ControlledExecutor = field(default_factory=NullExecutor)
    evaluator: Callable[[RuleSet, Any], ValidationResult] = evaluate
    clock: Callable[[], float] = time.monotonic
    ledger: Optional[AuditLedger] = None
    capture_dir: Optional[Path] = None
    sequence: int = 0
    bridge: Optional[EnforcementBridge] = None
    # G3/M2：动手前取证的提供者。None = 按配置决定（声明并启用时用 Phase 5 真实现）。
    evidence_provider: Optional[EvidenceProvider] = None
    # 台阶 2（§3.4 核验前置）：本次判定真正读的那份 adapter 配置，以及它是从哪来的。
    # 有了它，"配置读不到"这条理由才有对象可核验；没有它就只能落 unknown_origin。
    config_path: Optional[Path | str] = None
    config_source: str = "未声明（调用方没有给出配置路径）"

    def __post_init__(self) -> None:
        """没有显式注入桥接层时，按配置自己装配一次。

        这样"忘了接线"不会静默降级成"没有治理"：装配失败时 self.bridge 仍是 None，
        受控工具会在门禁处被阻断（enforcement_unavailable）。
        """

        if self.bridge is None:
            try:
                self.bridge = bridge_from_config(self.config)
            except EnforcementUnavailable:
                self.bridge = None

    def _audit(
        self,
        record: Mapping[str, Any],
        *,
        outcome: HookOutcome,
    ) -> None:
        if self.ledger is None:
            return
        payload: dict[str, Any] = {
            "audit_schema_version": AUDIT_SCHEMA_VERSION,
            "timestamp": _utc_now(),
            "agent": "dsh",
            "agent_version": self.config.agent_version,
            "reason_code": outcome.reason_code,
            "exit_code": outcome.exit_code,
            "executed": outcome.executed,
            "elapsed_ms": outcome.elapsed_ms,
            "rule_set_hash": self.rules.identity,
        }
        payload.update({key: value for key, value in record.items() if value is not None})
        # 台阶 4 / 21 号 §2.2：这条记录属于**哪棵树 / 哪一套声明 / 哪台宿主**。
        # 它是旁注——不进 policy.engine.evaluate 的任何输入，也不改任何 allow / block；
        # 放在既有键之后写，既有键的取值一个字符都不动。
        payload["reading_context"] = self.reading_context_for_record(payload)
        self.ledger.append(payload)

    def reading_context_for_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        r"""台阶 4：这条审计记录属于哪棵树 / 哪一套声明 / 哪台宿主（形状只有一份实现）。

        三条约束写死在这里（21 号 §2.2 + 本台阶的三条硬约束）：

        1. **不另算树摘要**（延迟）：\`tree\` **直接引用**本记录 \`pre_evidence.tree\` 的
           同一组值（\`scope\` / \`tree_digest\`）——既不遍历工作区，也不重复算指纹。
           拿不到取证树时写 \`unavailable\`（取证失败）或 \`not_applicable\`（这条路径上没有
           取证），**绝不**退回去自己算一棵树：那正是"每次调用多出一次全树遍历"的来源；
        2. **只放已有的声明摘要**：\`registry\` 用 \`pre_evidence.registry\` 里**同一个**
           digest（由 validators.pipeline 算好的那一份），这里一个字节都不重算；
           \`adapter_config\` 是这一个配置文件的 sha256（单文件，不遍历目录）；
        3. **不进判定**：判定路径不读它，只有 \`_audit()\` 调用本方法。

        形状与其余五处读数**同名同义**（\`provenance.reading_context\` 的唯一实现）：
        \`source\` / \`tree\` / \`declarations\` / \`host\` / \`run\`。两份**偏离**如实写下来，
        不等读者自己发现：

        - \`tree\` 只有 \`status\` / \`scope\` / \`digest\`，**没有 \`revision\`**：修订号要一次
          \`git rev-parse\` 子进程，而受控项目常常不是 git 工作树（取不到会是常态）；
          本台阶的硬约束是"每次调用不新增计算"，所以这里只放已有的取证树摘要；
        - \`host.sandbox\` 恒为 \`unknown\`：Hook 不探测沙箱（探测要有副作用），
          这一条与 21 号 §9.2 裁定④对 \`check\` 路径的口径相同——不猜。

        \`declarations.test_layout\` 写 \`not_applicable\`：这条记录本身不依赖那份声明；
        取证流水线读过的那一份不在 21 号 §2.2 预注册的搬运范围内。
        """

        pre = record.get("pre_evidence")
        pre_block: Mapping[str, Any] = pre if isinstance(pre, Mapping) else {}
        status = record.get("pre_evidence_status")
        raw_tree = pre_block.get("tree")

        if isinstance(raw_tree, Mapping) and raw_tree.get("tree_digest"):
            tree: dict[str, Any] = {
                "status": reading.STATUS_AVAILABLE,
                "scope": str(raw_tree.get("scope") or "unknown"),
                "digest": str(raw_tree["tree_digest"]),
            }
        elif status == "unavailable":
            tree = reading.unavailable("本次取证失败：没有可引用的取证树（pre_evidence 未收集）")
        else:
            tree = reading.not_applicable()

        declarations: dict[str, Any] = {}
        raw_registry = pre_block.get("registry")
        if isinstance(raw_registry, Mapping) and raw_registry.get("digest"):
            declarations[reading.DECLARATION_REGISTRY] = {
                "status": reading.STATUS_AVAILABLE,
                "path": raw_registry.get("path"),
                "digest": raw_registry.get("digest"),
            }
        elif status == "unavailable":
            declarations[reading.DECLARATION_REGISTRY] = reading.unavailable(
                "本次取证失败：注册表摘要没有取到"
            )
        else:
            declarations[reading.DECLARATION_REGISTRY] = reading.not_applicable()
        declarations[reading.DECLARATION_ADAPTER_CONFIG] = (
            reading.unavailable("调用点没有给出 adapter 配置路径")
            if self.config_path is None
            else reading.declaration_block(self.config_path, root=self.config.project_root)
        )
        declarations[reading.DECLARATION_TEST_LAYOUT] = reading.not_applicable()

        return reading.build(
            source=reading.SOURCE_HOOK,
            tree=tree,
            declarations=declarations,
            # 宿主只报事实：平台与解释器取得到，沙箱**不探测**（见上）。
            host=reading.host_block(),
        )

    def _capture(self, raw_payload: Mapping[str, Any], tool_name: str) -> None:
        """把收到的原始事件原样落盘，用于采集脱敏 fixture。

        文件按工具名 + 调用标识命名：每次 Hook 都是新进程，序号会重复，
        用调用标识才能保证"一次调用一个文件"（采集失败会让 fixture 不可信）。
        """

        if self.capture_dir is None:
            return
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.sequence += 1
        safe_tool = re.sub(r"[^A-Za-z0-9_.-]", "_", tool_name) or "unknown"
        call_id = str(raw_payload.get("tool_use_id") or f"{self.sequence:03d}")
        safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", call_id) or f"{self.sequence:03d}"
        target = self.capture_dir / f"{safe_tool}-{safe_id}.json"
        target.write_text(
            json.dumps(dict(raw_payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def _pre_evidence(
        self, raw_payload: Any, *, event: PolicyEvent, context: Any
    ) -> PreEvidenceResult:
        """按声明取证。提供者默认是 pre_evidence.build_pre_evidence（Phase 5 真流水线）。

        外层预算 = pre_evidence.timeout_ms + config.timeout_ms：取证与判定是**串行**的，
        而 dsh 的 hooks.json timeout 必须大于它们之和（check_wiring 会把这条不等式
        当成接线错误报出来）。dsh 杀掉 Hook 等于放行，所以这道外层预算不是优化，
        而是"失败关闭真的会触发"的前提。
        """

        pre = self.config.pre_evidence
        assert pre is not None  # 调用点在 pre is not None and pre.enabled 的分支里
        provider = self.evidence_provider or build_pre_evidence
        budget_ms = pre.timeout_ms + self.config.timeout_ms
        return _within_budget(
            lambda: provider(
                raw_payload,
                event=event,
                config=self.config,
                rules=self.rules,
                context=context,
            ),
            budget_ms=budget_ms,
            on_timeout=lambda: PreEvidenceError(
                f"动手前取证超过外层预算 {budget_ms} ms（pre_evidence.timeout_ms="
                f"{pre.timeout_ms} + timeout_ms={self.config.timeout_ms}）"
            ),
            name="pre-evidence-budget",
        )

    def _checker_scope_note(self, evidence_collected: bool) -> str:
        """能力边界的说明文字。

        没有取证时（默认）与改动前**逐字节相同**——既有键既不能少、也不能换意思。
        取到证据时追加的那句话是必要的：否则"本路径没有证据提供者"会在取证成功的
        记录里变成一句假话，而账本里最危险的就是"读起来没问题的假话"。
        """

        head = (
            "pre-execute 路径只做文本类 checker（"
            + ", ".join(sorted(CONTEXT_CHECKERS))
            + "）：仅凭上下文即可判定；"
        )
        if evidence_collected:
            return (
                head
                + "其余 checker 的证据由本次 pre_evidence 流水线提供"
                "（见 pre_evidence 摘要的 served_checkers / validators / target_sha256），"
                "因此它们真的参与了判定；没出现在 served_checkers 里的 checker 仍然进 "
                "skipped_rule_count —— 跳过不等于通过"
            )
        return (
            head + "其余 checker 需要 Phase 5 的验证器证据，"
            "本路径没有证据提供者，因此进 skipped_rule_count —— 跳过不等于通过"
        )

    def _severity_visibility(
        self, *, evaluated: Sequence[str], skipped: Sequence[str]
    ) -> dict[str, Any]:
        """M3：按严重级别的分布（只**新增**键，既有键一个都不动）。

        为什么必须按级别报（AGENTS 第 43 条）：实测 43 条规则里 24 条 error、19 条 warning，
        而 warning 命中只产出 allow_with_warnings——它拦不下任何东西。只报总数会让
        "43 条规则在管着"与"43 条会拦人的规则"在账本上一模一样。

        两条口径写死在这里：
        - evaluated_by_severity 数的是**真的参与过判定**的规则（matched_rules）；
        - skipped_by_severity 数的是**没有被查**的规则——它们不是"查过没问题"。
        规则集里没有的 rule_id 归 "unknown"：替它猜一个级别等于伪造分布。
        """

        severity_of = {rule.canonical_id: rule.severity.value for rule in self.rules.rules}
        blocking = {item.value for item in BLOCKING_SEVERITIES}

        def counts(ids: Sequence[str]) -> dict[str, int]:
            return _counts_by_severity(severity_of.get(item, "unknown") for item in ids)

        rule_set = counts(sorted(severity_of))
        evaluated_counts = counts(evaluated)
        skipped_counts = counts(skipped)
        blocking_count = sum(count for name, count in rule_set.items() if name in blocking)
        advisory_count = rule_set.get("warning", 0)
        return {
            "rules_by_severity": rule_set,
            "evaluated_by_severity": evaluated_counts,
            "skipped_by_severity": skipped_counts,
            "blocking_capable_rule_count": blocking_count,
            "advisory_rule_count": advisory_count,
            "severity_note": (
                "严重级别分布：只有 error / critical 拦得住（规则集里 "
                + str(blocking_count)
                + " 条），warning 命中只产出 allow_with_warnings、拦不下任何东西（"
                + str(advisory_count)
                + " 条）；evaluated_by_severity 是本次**真的参与过判定**的规则，"
                "skipped_by_severity 是本次**没有被查**的规则（跳过不等于通过）"
            ),
        }

    def rule_visibility(
        self, decision: ValidationResult, *, evidence_collected: bool = False
    ) -> dict[str, Any]:
        """G3：把"查了并通过"与"被跳过"写成审计里可区分的两个数（只标注，不改判定）。

        - effective_rule_count：本次**真的参与了判定**的规则数（= 总规则数 - 跳过数）；
        - skipped_rule_count / skipped_reason：跳过的规则数与按 checker 的归类；
        - checker_scope(_note)：写明 pre-execute 路径只做文本类 checker；
        - 按严重级别的分布（M3，见 _severity_visibility）："有多少条规则"与
          "有多少条会拦人的规则"是两件事，引用时必须带级别。

        "跳过"既不判违规，也**不是通过**：把它写进审计，是为了让读者一眼看出
        "这次到底查了几条规则"，而不是从 allow 反推"全都查过且没问题"。

        evidence_collected=True（声明并取到证据）时，note 会追加一句"本次证据类 checker
        真的参与了判定"——否则那句"本路径没有证据提供者"会在取证成功的记录里变成假话。
        默认 False 时输出与改动前逐字节相同（Phase 2 契约）。
        """

        checker_of = {
            rule.canonical_id: (rule.enforcement.checker or "unknown")
            for rule in self.rules.rules
        }
        skipped_by_checker: dict[str, int] = {}
        unknown_rules: list[str] = []
        for item in decision.skipped_rules:
            checker = checker_of.get(item.rule_id)
            if checker is None:
                unknown_rules.append(item.rule_id)
                checker = "not_in_rule_set"
            skipped_by_checker[checker] = skipped_by_checker.get(checker, 0) + 1
        skipped = len(decision.skipped_rules)
        return {
            "rule_count": len(self.rules.rules),
            "effective_rule_count": len(self.rules.rules) - skipped,
            "skipped_rule_count": skipped,
            "skipped_reason": {
                key: skipped_by_checker[key] for key in sorted(skipped_by_checker)
            },
            "checker_scope": sorted(CONTEXT_CHECKERS),
            "checker_scope_note": self._checker_scope_note(evidence_collected),
            "skipped_rule_ids_unknown": sorted(unknown_rules),
            # M3：按严重级别的分布（只新增键）。matched_rules 才是"真的参与过判定"的规则。
            **self._severity_visibility(
                evaluated=decision.matched_rules,
                skipped=[item.rule_id for item in decision.skipped_rules],
            ),
        }

    def violation_visibility(self, decision: ValidationResult) -> dict[str, Any]:
        """P1：账本必须答得出"哪几条规则真的报了违规"（只标注，不改判定）。

        为什么需要它：matched_rules 的语义是"参与过判定"，而 07 轮治理全开之后参与面是
        43 条——block 与 allow_with_warnings 的记录里因此读不出任何一条**真正报违规**的规则，
        那份清单只活在给模型看的 stderr 里。这里把同一份清单搬进审计。

        三条口径（同一条也写在 violations_note 里）：

        - violations 是本次真的报了违规的规则，逐条带 canonical rule_id（ARCH-001@1）、
          severity、message、evidence（与决策载荷同一形状）与决策级 required_action（若有）；
        - matched_rules 是本次参与过判定的规则；两者不是一回事——warning 命中只产出
          allow_with_warnings，而判定为 allow 的记录会带一个**空的** violations；
        - 排序用 Violation.sort_key（规则身份 → 证据值 → 证据主体），字符串一律走 sanitize：
          相同输入必须得到逐字节相同的记录，绝对路径与凭据不得进审计（AGENTS 第 16 条）。

        调用点只在"已经算出 decision"之后：没有判定的记录（context_error /
        evidence_unavailable / event_replay 等）不许出现这些键——"没判定"与"判定了、
        没违规"必须能分开读。
        """

        violations = [
            {
                "rule_id": violation.canonical_id,
                "severity": violation.severity.value,
                "message": violation.message,
                # 复用 Evidence 自己的字段集合：与决策载荷里的 evidence 子对象逐字段相同
                "evidence": violation.evidence.model_dump(exclude_none=True),
            }
            for violation in sorted(decision.violations, key=lambda item: item.sort_key)
        ]
        if decision.required_action is not None:
            # required_action 是**决策级**字段（审批门禁）：逐条附上是为了让单独一行违规
            # 也能读到它；它不表示"这条规则本身要求审批"。
            for item in violations:
                item["required_action"] = decision.required_action.value
        # 第三通道（台阶 3b / B2）：条目形状与 violations **逐字段相同**（同一个 Evidence
        # 的字段集合、同一把排序键），只是通道不同——读者不需要为 pending 另学一套形状。
        pending = [
            {
                "rule_id": finding.canonical_id,
                "severity": finding.severity.value,
                "message": finding.message,
                "evidence": finding.evidence.model_dump(exclude_none=True),
            }
            for finding in sorted(decision.pending_findings, key=lambda item: item.sort_key)
        ]
        if decision.required_action is not None:
            for item in pending:
                item["required_action"] = decision.required_action.value
        return {
            "violations": _sanitized(violations, project_root=self.config.project_root),
            "violations_by_severity": _counts_by_severity(
                violation.severity.value for violation in decision.violations
            ),
            "violations_note": VIOLATIONS_NOTE,
            # 这个键永远存在（可能是空列表）：与 violations 同一条口径——「判定了、这条通道
            # 里没有东西」是一个明确的结论，不是一个缺失的键。
            "pending_findings": _sanitized(pending, project_root=self.config.project_root),
        }

    def decision_reason_for_audit(self, decision: ValidationResult) -> Optional[str]:
        """账本口径的受控 `decision_reason`（薄封装：归类规则只有一份实现）。"""

        return decision_reason(decision)

    def book_obligations(
        self, decision: ValidationResult, *, event: PolicyEvent, record: Mapping[str, Any]
    ) -> None:
        """台阶 3c：把这次判定的「待实现」记进义务账（方案 §3.3）。

        **只记账、不判罚**：这一段既不产出也不修改 decision，异常也不改变任何 allow/block
        （L5 warn 期）。但失败必须**显式**写出来 —— 静默失败会让「这次没记上」与「这次没有义务」
        长得一模一样，而那正是本台阶要消灭的读法。退出码语义因此一字不变：非 0 退出的唯一来源
        仍是判定本身。

        为什么解除不在这条路径上记：解除只认「一次**真实** pytest 运行」，而这份证据（这次到底
        选中并执行了哪些测试）在预取证摘要里没有结构化字段。按 served_checkers 猜会把「选了一堆
        用例却一个都没跑起来」读成跑过了 —— 那是往"义务被悄悄清掉"的方向错。所以 Hook 只记义务，
        解除由 `python -m policy.check --obligations`（它手里有真流水线报告）记。
        """

        ledger = self.config.obligations_ledger
        if ledger is None or not decision.pending_findings or not event.file:
            return
        snapshot = (record.get("pre_evidence") or {}).get("pending_implementation") or ()
        try:
            written = book_pending_findings(
                ledger,
                findings=decision.pending_findings,
                target=event.file,
                pending_snapshot=snapshot,
            )
        except Exception as error:  # noqa: BLE001 - 只记账：不改判定，但必须说出来
            print(
                "[policy] OBLIGATIONS LEDGER UNAVAILABLE "
                + sanitize(str(error), project_root=self.config.project_root),
                file=sys.stderr,
            )
            return
        if written:
            print(
                "[policy] obligations recorded=" + str(written) + " ledger=" + ledger.name,
                file=sys.stderr,
            )

    def rule_visibility_not_applicable(self) -> dict[str, Any]:
        """没有文件维度的动作（Phase 4 执行类）：Phase 1 规则引擎完全不适用。

        这里同样只标注：全部规则算"跳过"、effective_rule_count=0。不写的话，
        读者会以为这些动作也过了一遍规则。
        """

        total = len(self.rules.rules)
        return {
            "rule_count": total,
            "effective_rule_count": 0,
            "skipped_rule_count": total,
            "skipped_reason": {"phase1_not_applicable": total} if total else {},
            "checker_scope": sorted(CONTEXT_CHECKERS),
            "checker_scope_note": (
                "该动作没有文件维度：Phase 1 规则引擎不适用（全部规则算跳过、不算通过）；"
                "授权由 Tool Registry（权限 / 参数白名单 / 命令白名单 / 审批）决定"
            ),
            "skipped_rule_ids_unknown": [],
            # M3：没有文件维度时全部规则都没跑，因此 skipped 的分布就等于规则集分布。
            **self._severity_visibility(
                evaluated=(), skipped=[rule.canonical_id for rule in self.rules.rules]
            ),
        }

    def _record_context_injection(
        self, *, base_record: Mapping[str, Any], started: float
    ) -> None:
        """G11：会话内记一次"会进入 AI 上下文的约定文档"的来源与哈希。

        为什么不做策略校验：载荷里没有"注入了什么"的事实，猜一份内容再判它，等于把推断
        当证据（AGENTS.md 第 6 条）。本轮只做来源与哈希留痕。

        为什么是近似：dsh 的 SessionStart 没有接到本 Hook（进程内插件只转发 pre/post-execute），
        所以这里是"本会话第一次工具调用"这个时刻，记录里用 approximate=True 明说，不假装
        它是真实注入时刻。
        """

        if self.ledger is None:
            return
        session_id = base_record.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return
        try:
            already = self.ledger.has_record(
                reason_code="context_injection", session_id=session_id
            )
        except Exception:  # noqa: BLE001 - 读不到审计就不能当作"已经记过"
            already = False
        if already:
            return
        outcome = HookOutcome(
            exit_code=EXIT_ALLOW,
            reason_code="context_injection",
            elapsed_ms=int((self.clock() - started) * 1000),
        )
        self._audit(
            {
                **base_record,
                "context_injection": {
                    "approximate": True,
                    "documents": context_documents(self.config.project_root),
                    "note": (
                        "记录的是项目根下声明过的约定文档与内容哈希；它是本会话第一次 Hook 调用"
                        "时的近似（不是真实注入时刻），也不代表对注入内容做过策略校验"
                    ),
                },
            },
            outcome=outcome,
        )

    def handle(self, raw_payload: Any) -> HookOutcome:
        """处理一条事件：任何异常路径都返回阻断，绝不抛给解释器。"""

        started = self.clock()
        base_record: dict[str, Any] = {}
        if isinstance(raw_payload, Mapping):
            tool_name = str(raw_payload.get("tool_name", "unknown"))
            self._capture(raw_payload, tool_name)
            base_record = {
                "session_id": raw_payload.get("session_id"),
                "tool": tool_name,
                "cwd_scope": "<repo>" if raw_payload.get("cwd") else None,
                # 成对契约（G2）靠这两项把 pre / post 接回同一个动作。
                "hook_event": raw_payload.get("hook_event_name"),
                "tool_use_id": raw_payload.get("tool_use_id"),
                "action_id": call_action_id(raw_payload),
            }

        outcome = self._handle_guarded(raw_payload, started=started, base_record=base_record)
        # G11：放在判定记录**之后**写。既有消费方（测试与工具）按"首行 = 本次判定"读审计，
        # 把留痕插到前面会改变这条既有约定（只增不改的意思是不动已有记录，不是随便插队）。
        self._record_context_injection(base_record=base_record, started=started)
        return outcome

    def _handle_guarded(
        self, raw_payload: Any, *, started: float, base_record: dict[str, Any]
    ) -> HookOutcome:
        """判定入口：任何异常路径都转成阻断，绝不抛给解释器。"""

        try:
            return self._decide(raw_payload, started=started, base_record=base_record)
        except DshEventError as error:
            return self._fail(
                "context_error", sanitize(str(error), project_root=self.config.project_root),
                started=started, base_record=base_record,
            )
        except PolicyContextError as error:
            return self._fail(
                "context_error", sanitize(str(error), project_root=self.config.project_root),
                started=started, base_record=base_record,
            )
        except PolicyTimeout as error:
            return self._fail(
                "policy_timeout", str(error), started=started, base_record=base_record
            )
        except EngineError as error:
            return self._fail(
                "engine_error", sanitize(str(error), project_root=self.config.project_root),
                started=started, base_record=base_record,
            )
        except (LoaderError, OSError) as error:
            detail = sanitize(str(error), project_root=self.config.project_root)
            return self._fail(
                "config_error", detail,
                started=started, base_record=base_record,
                # 台阶 2（R-g）：先把这条指控的证伪判据跑掉，再把它写进理由。
                origin=self._origin_for("config_error", detail),
            )
        except Exception as error:  # noqa: BLE001 - 未知异常也必须失败关闭
            return self._fail(
                "internal_error",
                f"{type(error).__name__}: "
                + sanitize(str(error), project_root=self.config.project_root),
                started=started,
                base_record=base_record,
            )

    def _decide(
        self, raw_payload: Any, *, started: float, base_record: dict[str, Any]
    ) -> HookOutcome:
        admission = to_policy_event(raw_payload, config=self.config)
        spec = None if self.bridge is None else self.bridge.spec_for(
            str(raw_payload.get("tool_name", "")) if isinstance(raw_payload, Mapping) else ""
        )

        if not admission.governed:
            tool_name = (
                str(raw_payload.get("tool_name", "")) if isinstance(raw_payload, Mapping) else ""
            )
            table_spec = TOOL_TABLE.get(tool_name)
            # Phase 4：执行类工具（以及注册表里声明的写类工具）一律走受控链路。
            # 注意"不在注册表里"也必须走这条路：交给门禁去拒绝（tool_not_registered），
            # 而不是因为"注册表不认识它"就退化成放行。
            if table_spec is not None and table_spec.kind is ToolKind.EXECUTE:
                return self._decide_via_enforcement(
                    raw_payload, spec=spec, started=started, base_record=base_record
                )
            if spec is not None and spec.risk.value in ("reversible_write", "destructive_write"):
                return self._decide_via_enforcement(
                    raw_payload, spec=spec, started=started, base_record=base_record
                )
            # 只读或不吃文件的工具：显式降级并记录，不假装检查过（Phase 4 的"允许显式降级"）。
            note = admission.reason
            outcome = HookOutcome(
                exit_code=EXIT_ALLOW,
                reason_code="not_governed",
                event=None,
                elapsed_ms=int((self.clock() - started) * 1000),
            )
            self._audit({**base_record, "governed": False, "scope_note": note}, outcome=outcome)
            return outcome

        event = admission.event
        assert event is not None
        # G7 的审计侧面：只写 layer 看不出来"这个层是**判出来的**还是**兜底来的**"——
        # 于是"未命中任何分层规则"在账本上和"命中某个层"长得一模一样，改个文件名即静默失效。
        # 这里把分层解析的完整结果一起落账（跨工作流冻结接口见 adapter.LayerResolution）。
        # event.file 与 Adapter 里做分层解析用的是同一个仓库相对路径，因此这里重算必然一致。
        resolution = (
            self.config.layer_resolution(event.file) if isinstance(event.file, str) else None
        )
        record: dict[str, Any] = {
            **base_record,
            "governed": True,
            "event_id": event.event_id,
            "request_id": event.request_id,
            "trace_id": event.trace_id,
            "tool": event.tool,
            "operation": event.operation.value,
            "file": event.file,
            "layer": event.layer,
            # None 表示"这次动作没有文件路径，分层不适用"；defaulted=True 才表示"没有规则给出答案"。
            "layer_defaulted": None if resolution is None else resolution.defaulted,
            "layer_matched_pattern": None if resolution is None else resolution.matched_pattern,
            "language": event.language,
            "dependencies": list(event.dependencies),
            "payload_digest": event.payload_digest,
            "payload_fields": list(event.payload_fields),
        }

        if self.ledger is not None:
            previous = self.ledger.lookup(event.event_id)
            if previous is not None:
                same_payload = previous.get("payload_digest") == event.payload_digest
                detail = (
                    "该 event_id 已经判定过：为避免重复执行工具，重放一律阻断"
                    if same_payload
                    else "该 event_id 被复用到了不同参数：事件标识不再可信，拒绝执行"
                )
                return self._fail(
                    "event_replay" if same_payload else "event_id_reuse",
                    detail,
                    started=started,
                    base_record=record,
                )

        context = to_policy_context(event, config=self.config)
        # G3/M2：动手前取证。声明的形状决定这一段是否存在——没有声明时连提供者都不问，
        # Phase 2 的判定路径因此逐字节不变。
        pre = self.config.pre_evidence
        evidence: Optional[EvidenceBundle] = None
        if pre is None:
            record["pre_evidence_status"] = "not_declared"
        elif not pre.enabled:
            record["pre_evidence_status"] = "disabled"
        else:
            try:
                result = self._pre_evidence(raw_payload, event=event, context=context)
            except PreEvidenceError as error:
                detail = sanitize(str(error), project_root=self.config.project_root)
                record["pre_evidence_status"] = "unavailable"
                record["pre_evidence"] = {"status": "unavailable", "detail": detail}
                return self._fail(
                    "evidence_unavailable",
                    detail
                    + "；本次声明了 pre_evidence，就必须拿出验证器证据："
                    "拒绝在证明不了的情况下放行（绝不把「跳过」当成「通过」）",
                    started=started,
                    base_record=record,
                    origin=self._origin_for("evidence_unavailable", detail),
                )
            bundle = getattr(result, "bundle", None)
            if not isinstance(bundle, EvidenceBundle):
                detail = (
                    "取证提供者没有返回 EvidenceBundle：无法证明证据来自 Phase 5 流水线，"
                    "拒绝在证明不了的情况下放行"
                )
                record["pre_evidence_status"] = "unavailable"
                record["pre_evidence"] = {"status": "unavailable", "detail": detail}
                return self._fail(
                    "evidence_unavailable", detail, started=started, base_record=record
                )
            evidence = bundle
            record["pre_evidence_status"] = "collected"
            record["pre_evidence"] = dict(getattr(result, "summary", None) or {})

        decision = _evaluate_with_budget(
            self.evaluator,
            self.rules,
            context,
            self.config.timeout_ms,
            evidence=evidence,
        )

        if decision.decision not in (Decision.ALLOW, Decision.ALLOW_WITH_WARNINGS, Decision.BLOCK):
            return self._fail(
                "unknown_decision",
                f"Engine 返回未知 decision {decision.decision!r}；不认识的决策值不得放行",
                started=started,
                base_record=record,
            )

        record["matched_rules"] = list(decision.matched_rules)
        record["skipped_rules"] = [item.rule_id for item in decision.skipped_rules]
        record["decision"] = decision.decision.value
        # H1：判定记录必须答得出"这次 block 属于哪一类"，否则 block + 空 violations 会被
        # 读成"没有依据"。None 时不写这个键（与 violations 同一条纪律：说不出来就不编）。
        reason = decision_reason(decision)
        if reason is not None:
            record["decision_reason"] = reason
        record["required_action"] = (
            None if decision.required_action is None else decision.required_action.value
        )
        # G3：把"查了并通过"与"被跳过"分开写进审计（新增字段，既有字段不动）。
        record.update(
            self.rule_visibility(decision, evidence_collected=evidence is not None)
        )
        # P1：判定记录还要答得出"哪几条规则真的报了违规"（新增字段，既有字段不动）。
        record.update(self.violation_visibility(decision))
        # 台阶 3c：义务账。放在审计内容已经成型之后、任何 gate 之前 —— 义务说的是
        # "这次判定看见了什么"，与后续授权链路是否放行无关（它不改变判定，见方法注释）。
        self.book_obligations(decision, event=event, record=record)

        if decision.decision is Decision.BLOCK:
            outcome = HookOutcome(
                exit_code=EXIT_BLOCK,
                reason_code="policy_block",
                stderr=feedback_text(
                    reason_code="policy_block", event=event, decision=decision
                ),
                decision=decision,
                event=event,
                elapsed_ms=int((self.clock() - started) * 1000),
            )
            self._audit(record, outcome=outcome)
            return outcome

        # Phase 4：把"引擎允许"升级成"绑定到具体动作的授权"。
        gate = self._enforcement_gate(
            raw_payload,
            spec=self.bridge.spec_for(event.tool) if self.bridge is not None else None,
            tool=event.tool,
            file=event.file,
            started=started,
            base_record=record,
            policy_decision=decision,
        )
        if gate is not None:
            return gate

        # allow / allow_with_warnings：执行器恰好被调用一次，参数由 Adapter 提供、不再改写。
        execution = self.executor.execute(event)
        executed = execution.status in {"executed", "delegated"}
        warnings = [
            violation.canonical_id
            for violation in decision.violations
        ]
        # B1：pending 不进 violations，但它同样必须让模型看得见——只读 violations 的话，
        # "先写测试"的批次在模型眼里会变成 `ALLOWED WITH WARNINGS <tool> <file>:` 后面
        # **空无一物**（"被警告了，但不知道警告什么"）。带「待实现」后缀是为了让这两种
        # 条目在同一行里仍然分得开，不与真违规混成一个清单。
        warnings.extend(
            f"{finding.canonical_id}（待实现）" for finding in decision.pending_findings
        )
        stderr = ""
        if decision.decision is Decision.ALLOW_WITH_WARNINGS:
            stderr = (
                "[policy] ALLOWED WITH WARNINGS "
                + (f"{event.tool} {event.file}: " if event else "")
                + ", ".join(warnings)
            )
        outcome = HookOutcome(
            exit_code=EXIT_ALLOW,
            reason_code=(
                "allow_with_warnings"
                if decision.decision is Decision.ALLOW_WITH_WARNINGS
                else "allow"
            ),
            stderr=stderr,
            decision=decision,
            event=event,
            executed=executed,
            elapsed_ms=int((self.clock() - started) * 1000),
        )
        record["execution"] = execution.status
        self._audit(record, outcome=outcome)
        return outcome

    # ------------------------------------------------------------------ Phase 4 门禁
    def _enforcement_block(
        self,
        *,
        reason_code: str,
        checks: Sequence[Any],
        detail: str,
        started: float,
        base_record: Mapping[str, Any],
        tool: Optional[str] = None,
        file: Optional[str] = None,
    ) -> HookOutcome:
        """按 Phase 4 的检查结论阻断，并把失败项写进给模型的理由与审计记录。

        审计里那一份（`enforcement_detail`）与给模型的那一份（stderr）**脱敏口径必须一致**：
        `path_out_of_scope` 的文案里带受控范围的**绝对路径**（"路径不在仓库 <anchor> 之内"），
        不脱敏就等于把本机布局写进审计（AGENTS 第 16 条）。这里用**审计链自己的**
        `enforcement.audit.redact_text`（工作区路径 → <workspace>、绝对路径 → <abs>、
        密钥 → <redacted-secret>、控制字符转义、2000 字符上限），而不是面向模型的 `sanitize`：
        后者带 FEEDBACK_MAX_CHARS=4000 的**面向模型**截断，拿它洗审计明细会把明细截成另一种失真。
        两份产物各自用自己的口径，但都不许出现本机绝对路径——不会出现"摘要链干净、Hook 记录流脏"
        这种一半干净。
        """

        stderr = sanitize(
            enforcement_feedback(
                tool=tool or "<unknown>",
                file=file,
                reason_code=reason_code,
                checks=checks,
                detail=sanitize(detail, project_root=self.config.project_root),
            ),
            project_root=self.config.project_root,
        )
        outcome = HookOutcome(
            exit_code=EXIT_BLOCK,
            reason_code=reason_code,
            stderr=stderr,
            elapsed_ms=int((self.clock() - started) * 1000),
        )
        self._audit(
            {
                **base_record,
                "enforcement_reason": reason_code,
                "enforcement_detail": redact_text(
                    detail, workspace=self.config.project_root
                ),
            },
            outcome=outcome,
        )
        return outcome

    def _enforcement_gate(
        self,
        raw_payload: Any,
        *,
        spec: Optional[Any],
        tool: str,
        file: Optional[str],
        started: float,
        base_record: Mapping[str, Any],
        policy_decision: Optional[ValidationResult] = None,
        policy_skipped: str = "",
    ) -> Optional[HookOutcome]:
        """Phase 4 的执行前授权。返回 None 表示放行；返回 HookOutcome 表示已阻断。"""

        if self.bridge is None:
            return self._enforcement_block(
                reason_code="enforcement_unavailable",
                checks=(),
                detail=(
                    "adapter 配置没有接入 Phase 4 工具注册表（registry / registry_approved）："
                    "受控工具不得在无授权链路下执行"
                ),
                started=started,
                base_record=base_record,
                tool=tool,
                file=file,
            )
        if spec is None:
            return self._enforcement_block(
                reason_code="tool_not_registered",
                checks=(),
                detail=(
                    f"工具 {tool!r} 不在 Tool Registry 里：未登记的工具没有执行语义，默认阻断；"
                    "升级 Agent 后必须先登记工具并重新审核注册表"
                ),
                started=started,
                base_record=base_record,
                tool=tool,
                file=file,
            )

        tool_input = raw_payload.get("tool_input") if isinstance(raw_payload, Mapping) else {}
        if not isinstance(tool_input, Mapping):
            tool_input = {}
        # 与 Phase 2 的 event_id 同口径：PostToolUse 只能靠这个标识把事后证据接回同一个动作。
        action_id = call_action_id(raw_payload) or "unknown"
        try:
            request = self.bridge.build_request(
                spec=spec,
                action_id=action_id,
                request_id=action_id,
                trace_id=self.config.trace_id,
                subject=None if self.config.principal is None else self.config.principal.subject,
                roles=() if self.config.principal is None else tuple(self.config.principal.roles),
                params=dict(tool_input),
            )
        except Exception as error:  # noqa: BLE001 - 参数不合法一律阻断
            # 错误码必须如实：G5 实测过一条误导——workdir 等于工作区根被判越界时，
            # 反馈里写的是"参数错误"，人和模型都会以为参数写错了，而真实原因是范围。
            # Phase 4 的 ActionRequestError 带**结构化** reason_code（path_out_of_scope /
            # param_invalid / ...），这里透传；只有拿不到结构化原因时才退回笼统值。
            return self._enforcement_block(
                reason_code=getattr(error, "reason_code", None) or "enforcement_param_error",
                checks=(),
                detail=str(error),
                started=started,
                base_record=base_record,
                tool=tool,
                file=file,
            )

        try:
            outcome = self.bridge.pre(
                request,
                policy_decision=policy_decision,
                policy_skipped_reason=policy_skipped,
            )
        except Exception as error:  # noqa: BLE001 - 受控链路不可用一律阻断
            return self._enforcement_block(
                reason_code="enforcement_error",
                checks=(),
                detail=f"{type(error).__name__}: {error}",
                started=started,
                base_record=base_record,
                tool=tool,
                file=file,
            )

        if outcome.decision.decision is Decision.BLOCK:
            return self._enforcement_block(
                reason_code=outcome.decision.reason_code.value,
                checks=outcome.decision.checks,
                detail="Phase 4 pre-check 未通过：动作没有执行",
                started=started,
                base_record={
                    **base_record,
                    "action_hash": request.action_hash,
                    "action_id": request.action_id,
                    "tool_id": request.tool_id,
                    "risk": request.risk.value,
                },
                tool=tool,
                file=file,
            )
        # 允许：把授权凭据记进审计（工具本身由 dsh 在 pre-execute 之后执行）。
        if outcome.decision.grant is not None and self.ledger is not None:
            self._audit(
                {
                    **base_record,
                    "action_hash": request.action_hash,
                    "action_id": request.action_id,
                    "tool_id": request.tool_id,
                    "risk": request.risk.value,
                    "grant_id": outcome.decision.grant.grant_id,
                    "grant_expires_at": outcome.decision.grant.expires_at.isoformat(),
                },
                outcome=HookOutcome(
                    exit_code=EXIT_ALLOW,
                    reason_code="enforcement_allow",
                    elapsed_ms=int((self.clock() - started) * 1000),
                ),
            )
        return None

    def _decide_via_enforcement(
        self, raw_payload: Any, *, spec: Optional[Any], started: float, base_record: dict[str, Any]
    ) -> HookOutcome:
        """Phase 4 的高权限执行路径：授权通过后由 Agent 运行时执行。"""

        tool = (
            str(raw_payload.get("tool_name", "unknown")) if isinstance(raw_payload, Mapping)
            else "unknown"
        )
        gate = self._enforcement_gate(
            raw_payload,
            spec=spec,
            tool=tool,
            file=None,
            started=started,
            base_record=base_record,
            policy_skipped=(
                "该动作没有文件维度：Phase 1 规则引擎不适用；"
                "授权由 Tool Registry（权限 / 参数白名单 / 命令白名单 / 审批）决定"
            ),
        )
        if gate is not None:
            return gate

        outcome = HookOutcome(
            exit_code=EXIT_ALLOW,
            reason_code="allow_delegated",
            event=None,
            executed=False,
            elapsed_ms=int((self.clock() - started) * 1000),
        )
        self._audit(
            {
                **base_record,
                "governed": True,
                "scope_note": "Phase 4 受控执行：高权限动作放行，由 Agent 运行时执行",
                # G3：这类动作没有文件维度，Phase 1 一条规则都没跑 —— 显式写明，
                # 免得读者把"没有 matched_rules"读成"规则都查过且通过"。
                **self.rule_visibility_not_applicable(),
                # M2/G3：执行类动作没有文件内容可取证，证据类 checker 在这里同样不参与判定。
                # 写封闭值域里的取值，而不是留空让人猜"是没声明还是没取到"。
                "pre_evidence_status": "not_applicable",
            },
            outcome=outcome,
        )
        return outcome

    def _fail(
        self,
        reason_code: str,
        detail: str,
        *,
        started: float,
        base_record: Mapping[str, Any],
        origin: Optional[Origin] = None,
    ) -> HookOutcome:
        """失败关闭：任何无法安全判定的情况都阻断，并给出可诊断但不含敏感信息的原因。

        台阶 2（§3.4）：带上 `origin` 时，一条**结构化归因**同时进审计与机读诊断行。
        它是**诊断**不是判定——核验记录无权威，消费者不得据它 allow/block（所以它既不进
        `decision` 也不进 `violations`）。归属由调用方给出（`_origin_for`），本函数不猜。
        """

        event = None
        outcome = HookOutcome(
            exit_code=EXIT_BLOCK,
            reason_code=reason_code,
            stderr=feedback_text(
                reason_code=reason_code, event=event, decision=None, detail=detail
            ),
            elapsed_ms=int((self.clock() - started) * 1000),
            origin=origin,
        )
        record: dict[str, Any] = {**base_record, "detail": detail}
        if origin is not None:
            # 审计里的归因同样要脱敏（AGENTS 第 16 条；2026-09-29 裁定不开例外）：
            # detail 早就走 sanitize，origin 却整份直写——同一个字段族里两套口径。
            record["origin"] = _sanitized(
                origin.to_payload(), project_root=self.config.project_root
            )
        self._audit(record, outcome=outcome)
        return outcome

    def _origin_for(self, reason_code: str, detail: str) -> Optional[Origin]:
        """失败码 + 失败原文 → 结构化归因（**核验前置已执行**）。

        本台阶只覆盖配置族：其余原因码由 `origin_from_failure` 显式落 `unknown_origin`
        （"这条理由目前没有可执行的证伪判据"）——那本身就是一个要能被读出来的结论。
        归因**绝不影响** allow/block：调用点拿到的仍然是同一个 reason_code 与 exit 2。
        """

        if reason_code not in ORIGIN_BY_REASON_CODE:
            return None
        return origin_from_failure(
            reason_code=reason_code,
            detail=detail,
            config_path=self.config_path,
            config_source=self.config_source,
        )


def _utc_now() -> str:
    import datetime as clock

    return clock.datetime.now(clock.timezone.utc).isoformat().replace("+00:00", "Z")


def post_execute_outcome(
    raw_payload: Mapping[str, Any],
    *,
    bridge: Optional[EnforcementBridge],
    config: AdapterConfig,
    hook: "DshPreExecuteHook",
    started: float,
) -> HookOutcome:
    """PostToolUse：事后验证。失败时用 exit 2 表示"这次执行的结果不可信"。

    PostToolUse 阶段副作用已经发生，dsh 只能把工具结果标成错误——所以这里的语义是
    "结果需要修复"，绝不是"回滚成功"。

    与 PreToolUse 共用同一份审计：这里额外写一条 hook_event="PostToolUse" 的记录，
    于是"任一放行的受治理动作必须有 pre 与 post 两段"这条契约可以在这份产物上直接判定
    （G2 的核心证据是"审计/台账里到底有没有 post 阶段记录"，不是代码里注册了几个回调）。
    """

    record: dict[str, Any] = {
        "session_id": raw_payload.get("session_id"),
        "tool": str(raw_payload.get("tool_name") or "unknown"),
        "hook_event": HOOK_EVENT_POST_TOOL_USE,
        "tool_use_id": raw_payload.get("tool_use_id"),
        "action_id": call_action_id(raw_payload),
    }
    outcome = _post_decision_outcome(
        raw_payload, bridge=bridge, config=config, hook=hook, started=started
    )
    hook._audit(record, outcome=outcome)  # noqa: SLF001 - 与 pre 走同一条审计写入路径
    return outcome


def _post_decision_outcome(
    raw_payload: Mapping[str, Any],
    *,
    bridge: Optional[EnforcementBridge],
    config: AdapterConfig,
    hook: "DshPreExecuteHook",
    started: float,
) -> HookOutcome:
    """事后判定的实现（审计写入由 post_execute_outcome 统一负责，避免漏记）。"""

    if bridge is None:
        return HookOutcome(
            exit_code=EXIT_ALLOW,
            reason_code="post_not_governed",
            elapsed_ms=int((hook.clock() - started) * 1000),
        )
    try:
        decision = bridge.post(raw_payload)
    except Exception as error:  # noqa: BLE001 - 事后验证失败不得谎报通过
        return HookOutcome(
            exit_code=EXIT_BLOCK,
            reason_code="post_error",
            stderr=sanitize(
                f"[policy] POST-CHECK FAILED detail: {type(error).__name__}: {error}",
                project_root=config.project_root,
            ),
            elapsed_ms=int((hook.clock() - started) * 1000),
        )

    if decision is None:
        return HookOutcome(
            exit_code=EXIT_ALLOW,
            reason_code="post_not_required",
            elapsed_ms=int((hook.clock() - started) * 1000),
        )
    if decision.status.value == "validated":
        return HookOutcome(
            exit_code=EXIT_ALLOW,
            reason_code="post_validated",
            elapsed_ms=int((hook.clock() - started) * 1000),
        )
    detail = "; ".join(
        f"{item.check}: {item.detail}" for item in decision.checks if item.status.value == "failed"
    )
    return HookOutcome(
        exit_code=EXIT_BLOCK,
        reason_code=f"post_{decision.status.value}",
        stderr=sanitize(
            chr(10).join(
                [
                    f"[policy] POST-CHECK {decision.status.value} ({decision.reason_code.value})",
                    *( [f"detail: {detail}"] if detail else [] ),
                    "该动作已经执行，副作用无法撤销：按 repair_required 处理，"
                    "需要人工或后续修复流程介入",
                ]
            ),
            project_root=config.project_root,
        ),
        elapsed_ms=int((hook.clock() - started) * 1000),
    )


def run_hook(
    raw_payload: Any,
    *,
    config_path: Path | str,
    executor: Optional[ControlledExecutor] = None,
    evaluator: Optional[Callable[[RuleSet, Any], ValidationResult]] = None,
    audit_path: Optional[Path | str] = None,
    capture_dir: Optional[Path | str] = None,
    hooks_config_path: Optional[Path | str] = None,
    allow_unverified_wiring: bool = True,
    bridge: Optional[EnforcementBridge] = None,
    evidence_provider: Optional[EvidenceProvider] = None,
) -> HookOutcome:
    """装配并执行一次 Hook 调用（测试与 CLI 共用的入口）。

    PreToolUse 走执行前授权；PostToolUse 走事后验证；两者共用同一份台账与审计链，
    因此一次工具调用在审计里是一条完整的 trace。

    关于 allow_unverified_wiring（G12）：**生产入口是 CLI，默认 False** —— 缺
    --hooks-config 时直接判 wiring_error（exit 2），因为"证明不了 dsh 会注册本 Hook"
    正是最危险的静默失效路径。库内调用（集成测试、学习手册、探针）默认 True：它们不是
    "由 Agent 运行时启动的 Hook 进程"，接线与否由调用方自己负责；把默认改成 False 会让
    几十个与被测行为无关的调用点一起变成 wiring_error，而真正需要严格的地方（CLI）
    已经在 main() 里显式传 False。
    """

    # 台阶 2 的纪律（R-d 的一条推论）：**不改判定的形状**。配置加载失败在库里仍然原样
    # 抛出（生产入口 main() 把它翻成 reason_code=startup_error 的那条既有路径），归因由
    # main() 用同一个 origin_from_failure 算——那里才拿得到 args.config。曾经在这里加过
    # 一层 try/except 把它改写成 config_error：那是**改变判定载荷**，不属于本台阶的授权
    # 范围，已撤回（字段级差集的口径见 10 号 §2）。
    config = load_config(config_path)
    rules = load_rule_set(config.rule_dirs, repo_root=config.rule_anchor)

    ledger_path = audit_path if audit_path is not None else config.audit_log
    ledger = None if ledger_path is None else AuditLedger(ledger_path)

    if bridge is None:
        try:
            bridge = bridge_from_config(config)
        except EnforcementUnavailable:
            bridge = None

    effective_ledger: Optional[Path] = None
    audit_file_path: Optional[Path] = None
    if bridge is not None and audit_path is not None:
        # --audit 是"本次会话的审计文件"：Phase 2 的记录与 Phase 4 的链落在同一份证据里。
        # 幂等/授权状态使用独立台账；两种 JSONL 协议不能混写，否则严格读取无法区分
        # "合法的外来审计行"与"丢失 schema 的损坏台账行"。
        audit_file = Path(audit_path)
        state_file = derived_ledger_path(audit_file)
        bridge.sink = FileAuditSink(audit_file, workspace=config.project_root)
        bridge.ledger = EnforcementLedger(state_file)
        # N21：这条派生改写了一个被声明出来的配置字段，事实必须能被读到（见函数实现）。
        effective_ledger = state_file
        audit_file_path = audit_file

    kwargs: dict[str, Any] = {
        "config": config,
        "rules": rules,
        "ledger": ledger,
        "capture_dir": None if capture_dir is None else Path(capture_dir),
        "bridge": bridge,
        # 台阶 2：核验前置要的是"这次真的读的是哪份配置、从哪来"，不是重新拼一个路径。
        "config_path": config_path,
        "config_source": "--config（本次调用显式给出的 adapter 配置）",
    }
    if executor is not None:
        kwargs["executor"] = executor
    if evaluator is not None:
        kwargs["evaluator"] = evaluator
    if evidence_provider is not None:
        kwargs["evidence_provider"] = evidence_provider

    hook = DshPreExecuteHook(**kwargs)
    report = check_wiring(
        config,
        hooks_config_path=hooks_config_path,
        allow_unverified_wiring=allow_unverified_wiring,
    )
    if report:
        outcome = hook._fail(  # noqa: SLF001 - 接线错误必须走同一条失败关闭路径
            "wiring_error",
            report,
            started=hook.clock(),
            base_record={},
            # 接线族的对象是 hooks.json（不是 adapter 配置）：把**那一个**路径交进去，
            # 归因才会指着读者真正该改的东西。
            origin=origin_from_failure(
                reason_code="wiring_error",
                detail=report,
                config_path=hooks_config_path,
                config_source="--hooks-config（本次调用显式给出的接线配置）",
            ),
        )
    elif (
        isinstance(raw_payload, Mapping)
        and raw_payload.get("hook_event_name") == HOOK_EVENT_POST_TOOL_USE
    ):
        outcome = post_execute_outcome(
            raw_payload, bridge=bridge, config=config, hook=hook, started=hook.clock()
        )
    else:
        outcome = hook.handle(raw_payload)

    # N21：写在本次判定**之后**——既有消费方按"首行 = 本次判定"读审计，元信息不许插队。
    if effective_ledger is not None and audit_file_path is not None:
        record_ledger_derivation(
            hook,
            audit_path=audit_file_path,
            declared=config.enforcement_ledger,
            effective=effective_ledger,
            raw_payload=raw_payload,
        )
    return outcome


def display_path(path: Path | str, *, project_root: Path | str) -> str:
    """把路径渲染成可以写进证据的形式。

    受控项目内记仓库相对路径（POSIX 分隔符）；项目外一律先把目录脱敏，只保留文件名——
    文件名正是 N21 那个读数陷阱的关键（"按配置名去数是 0 条"），而绝对路径不得进证据。
    """

    candidate = Path(path)
    try:
        relative = candidate.resolve().relative_to(Path(project_root).resolve())
    except (OSError, ValueError):
        return sanitize(str(candidate.parent)) + "/" + candidate.name
    return relative.as_posix()


def derived_ledger_path(audit_path: Path | str) -> Path:
    """由审计路径派生台账路径（N21 的派生规则，只有这一处实现）。

    .policy/audit.jsonl  ->  .policy/audit.enforcement-ledger.jsonl
    """

    audit_file = Path(audit_path)
    return audit_file.with_name(
        f"{audit_file.stem}.enforcement-ledger{audit_file.suffix}"
    )


def effective_paths(
    config: AdapterConfig, *, audit_path: Optional[Path | str] = None
) -> dict[str, Any]:
    """本次运行真正会写的审计 / 台账路径：启动自检的一等输出（N21）。

    三种来源必须能被区分，否则读者只能靠猜：

    - derived_from_audit：带了 --audit，台账按派生规则改写（配置声明被覆盖）；
    - configured：没有 --audit，用配置声明的 enforcement_ledger；
    - default：两者都没有，落到 <project_root>/.policy/enforcement-ledger.jsonl。
    """

    declared = config.enforcement_ledger
    if audit_path is not None:
        ledger = derived_ledger_path(audit_path)
        source = "derived_from_audit"
    elif declared is not None:
        ledger = Path(declared)
        source = "configured"
    else:
        ledger = config.project_root / ".policy" / "enforcement-ledger.jsonl"
        source = "default"

    audit = Path(audit_path) if audit_path is not None else config.audit_log
    overridden = (
        source == "derived_from_audit" and declared is not None and Path(declared) != ledger
    )
    return {
        "audit": None if audit is None else display_path(audit, project_root=config.project_root),
        "ledger": display_path(ledger, project_root=config.project_root),
        "ledger_source": source,
        "ledger_declared": (
            None if declared is None else display_path(declared, project_root=config.project_root)
        ),
        "ledger_overridden": overridden,
        "ledger_override_note": LEDGER_OVERRIDE_NOTE if overridden else None,
    }


def effective_paths_line(
    config: AdapterConfig, *, audit_path: Optional[Path | str] = None
) -> str:
    """自检用的机读生效路径行（N21）：一行 JSON，不猜、不省略。"""

    return EFFECTIVE_PATHS_PREFIX + json.dumps(
        effective_paths(config, audit_path=audit_path), ensure_ascii=False, sort_keys=True
    )


def record_ledger_derivation(
    hook: "DshPreExecuteHook",
    *,
    audit_path: Path,
    declared: Optional[Path],
    effective: Path,
    raw_payload: Any,
) -> bool:
    """把"台账路径被 --audit 派生改写"写进审计（每会话一次），返回是否写了。

    为什么要有这条记录：配置里的 enforcement_ledger 被静默覆盖，按它去数台账会得到 0 条，
    然后被读成"事后核对从来没跑过"。记录里写明配置声明的路径与真正生效的路径，
    谁读审计谁就能找到台账。

    为什么可以不记：没有声明 enforcement_ledger（没有"被改写"这回事）、两者本来就一致、
    或者已经记过一次。记录**不带 hook_event / action_id**：它是元信息，不得参与
    "pre / post 成对"这类按动作聚合的判定。
    """

    if declared is None or Path(declared) == Path(effective) or hook.ledger is None:
        return False
    session_id = raw_payload.get("session_id") if isinstance(raw_payload, Mapping) else None
    try:
        already = hook.ledger.has_record(
            reason_code="ledger_path_overridden",
            session_id=session_id if isinstance(session_id, str) and session_id else None,
        )
    except Exception:  # noqa: BLE001 - 读不到审计就不能当作"已经记过"
        already = False
    if already:
        return False

    report = effective_paths(hook.config, audit_path=audit_path)
    hook._audit(  # noqa: SLF001 - 与判定记录走同一条审计写入路径
        {
            "session_id": session_id,
            "ledger_path": {
                "declared": report["ledger_declared"],
                "effective": report["ledger"],
                "source": report["ledger_source"],
                "note": LEDGER_OVERRIDE_NOTE,
            },
        },
        outcome=HookOutcome(
            exit_code=EXIT_ALLOW, reason_code="ledger_path_overridden", elapsed_ms=0
        ),
    )
    return True


def check_wiring(
    config: AdapterConfig,
    *,
    hooks_config_path: Optional[Path | str] = None,
    allow_unverified_wiring: bool = False,
) -> str:
    """接线自检：把"配置没接上 = 静默放行"这一类失效变成显式错误。

    dsh 在 hooks.json 读不到时不注册任何 hook，也不会报错；因此运行期必须自己确认
    hooks.json 存在、指向的 adapter 配置就是本次使用的那份，且内部预算小于 dsh 超时。

    **自检缺席 = 失败关闭**（G12）：没有提供 hooks_config_path 时，上面三条一条都证明不了，
    而"证明不了就当通过"正是这个缺口本身。所以这里返回错误而不是空串；只有显式命名的
    开关（CLI 的 --allow-unverified-wiring / 本函数的 allow_unverified_wiring=True）
    才能跳过，默认一律拒绝。
    """

    if hooks_config_path is None:
        if allow_unverified_wiring:
            return ""
        return (
            "接线自检缺席：没有提供 hooks.json 路径，无法证明 dsh 会注册本 Hook"
            "（dsh 在 hooks 配置读不到时不注册任何 hook，也不报错，等于没有治理）。"
            "确需在没有接线证据的情况下运行，必须显式声明 --allow-unverified-wiring"
        )
    path = Path(hooks_config_path)
    if not path.is_file():
        return f"hooks.json 不存在：{path.name}；dsh 会因此不注册任何 hook（等于没有治理）"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return f"hooks.json 不可解析（{type(error).__name__}）；dsh 会因此不注册任何 hook"

    commands: list[str] = []
    hooks_section = document.get("hooks") if isinstance(document, Mapping) else None
    if isinstance(hooks_section, Mapping):
        for groups in hooks_section.values():
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, Mapping):
                    continue
                for entry in group.get("hooks", []):
                    if isinstance(entry, Mapping) and isinstance(entry.get("command"), str):
                        commands.append(entry["command"])
    if not any("adapters.dsh.hooks" in command for command in commands):
        return "hooks.json 里没有指向 adapters.dsh.hooks 的命令；当前组合没有接入策略 Hook"

    timeout_sec = None
    for groups in (hooks_section or {}).values() if isinstance(hooks_section, Mapping) else []:
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, Mapping):
                continue
            for entry in group.get("hooks", []):
                if isinstance(entry, Mapping) and isinstance(entry.get("command"), str):
                    if "adapters.dsh.hooks" in entry["command"] and isinstance(
                        entry.get("timeout"), (int, float)
                    ):
                        timeout_sec = float(entry["timeout"])
    if timeout_sec is not None and timeout_sec * 1000 <= config.timeout_ms:
        return (
            f"hooks.json 的 timeout={timeout_sec:g}s 不大于内部预算 {config.timeout_ms}ms："
            "dsh 会先杀掉 Hook，而被杀在 dsh 协议里等同于放行，必须让内部预算先触发"
        )

    # G3/M2：声明了 pre_evidence 之后，Hook 一次调用里**串行**跑两段带预算的工作
    # （取证 → 判定），因此要证明的是"两段之和"小于 dsh 的超时。只证明其中一段，
    # 等价于把"被杀 = 放行"这条路径留在接线里。
    pre = config.pre_evidence
    if pre is not None and pre.enabled:
        budget_ms = pre.timeout_ms + config.timeout_ms
        # hooks.json 没写 timeout 时 dsh 用桥的 defaultTimeoutMs（README §2.5）：
        # "没写"不等于"没有上限"，所以这里用显式常量而不是跳过检查。
        limit_ms = DEFAULT_HOOK_TIMEOUT_MS if timeout_sec is None else int(timeout_sec * 1000)
        if budget_ms >= limit_ms:
            return (
                f"pre_evidence 的预算之和 {budget_ms}ms"
                f"（pre_evidence.timeout_ms={pre.timeout_ms} + timeout_ms={config.timeout_ms}）"
                f"不小于 dsh 侧的 {limit_ms}ms"
                + ("（hooks.json 没写 timeout，按 dsh 默认 600000ms 计）" if timeout_sec is None else "")
                + "：dsh 会先杀掉 Hook，而被杀在 dsh 协议里等同于放行；"
                "必须让取证与判定两段预算都在 dsh 超时之前触发"
            )
    return ""


def origin_line(origin: Origin, *, project_root: Optional[Path] = None) -> str:
    """归因的机读行（台阶 2）。

    与 `verdict_line` 分开：判定行是**契约**（消费方按精确版本号读，读不到按未知状态
    失败关闭），归因行是**诊断**（读不到只是读不到，不改任何 allow/block）。

    绝对路径不开例外（AGENTS 第 16 条，2026-09-29 裁定）：observation.result / object.value /
    object.source 里的真机原文可能带绝对路径（实测：`--config <绝对路径>` 会整串出现在
    object.source 与 observation.result 里）。**脱敏在 json.dumps 之前**做，载荷的键集合因此
    一字不变（跨语言`payload_is_well_formed` 只校验形状与取值闭集）。
    脱敏只处理字符串，不引入新的失败模式：它不改变 reason_code / exit_code。
    """

    payload = _sanitized(origin.to_payload(), project_root=project_root)
    return ORIGIN_PREFIX + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def verdict_line(
    *, reason_code: str, exit_code: int = EXIT_BLOCK, hook_event: Optional[str] = None
) -> str:
    """阻断时写给上层（进程内插件 / 命令桥）的机读判定行（N18）。

    形状固定，消费方按 schema_version + reason_code 读：

        [policy] VERDICT {"exit_code": 2, "reason_code": "policy_block", "schema_version": "1.0"}

    它只描述"Hook 判了什么"，不是第二份判定：没有这一行时上层必须按未知状态失败关闭，
    有这一行也不会把任何非 0 退出变成放行。
    """

    payload: dict[str, Any] = {
        "schema_version": VERDICT_SCHEMA_VERSION,
        "reason_code": reason_code,
        "exit_code": exit_code,
    }
    if hook_event:
        payload["hook_event"] = hook_event
    return VERDICT_PREFIX + json.dumps(payload, ensure_ascii=False, sort_keys=True)


def hook_event_of(payload: Any) -> Optional[str]:
    """从 Hook 载荷里取事件名；取不到就返回 None（判定行里不写这一项，不猜）。"""

    if isinstance(payload, Mapping):
        name = payload.get("hook_event_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m adapters.dsh.hooks",
        description="dsh pre-execute Hook：读 stdin 的事件 JSON，放行（exit 0）或阻断（exit 2）。",
    )
    parser.add_argument("--config", required=True, help="adapter 配置（YAML）路径")
    parser.add_argument("--audit", default=None, help="审计 JSONL 路径（覆盖配置里的 audit_log）")
    parser.add_argument(
        "--hooks-config",
        default=None,
        help=(
            "hooks.json 路径：提供时做接线自检（存在性、命令、超时预算）；"
            "不提供时按失败关闭处理（除非显式 --allow-unverified-wiring）"
        ),
    )
    parser.add_argument(
        "--allow-unverified-wiring",
        action="store_true",
        help=(
            "显式跳过接线自检（默认拒绝）：没有 --hooks-config 时本 Hook 证明不了 dsh 会注册它。"
            "只应在受控排障时使用，且应当在证据里写明"
        ),
    )
    parser.add_argument(
        "--capture",
        default=None,
        help="把收到的原始事件写到该目录（用于采集脱敏 fixture；不影响判定）",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="只做配置与接线自检，不读 stdin；成功退出码 0，失败 2",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """执行 Hook 的进程入口。

    契约：stdout 在放行时保持为空（dsh 只在 exit 0 且 stdout 以 { 开头时才解析 JSON，
    提前写入文本会被误当成结构化输出）；所有诊断写 stderr。

    退出码契约（README §2.3）：放行 = 0，阻断 = 2。本机实测 dsh 会把非 0 退出码压成 1，
    因此阻断时**额外**写一行机读判定（verdict_line，N18），供插件把"策略阻断 + 原因码"
    与"未知状态"分开；退出码本身仍然是唯一的放行/拒绝信号。
    """

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):  # 已经被重定向且不可重配置
                pass

    args = build_parser().parse_args(argv)
    # N18：判定行里带事件名，便于读者区分 pre / post；读不到就不写这一项。
    hook_event: Optional[str] = None

    try:
        if args.self_check:
            config = load_config(args.config)
            load_rule_set(config.rule_dirs, repo_root=config.rule_anchor)
            report = check_wiring(
                config,
                hooks_config_path=args.hooks_config,
                allow_unverified_wiring=args.allow_unverified_wiring,
            )
            if report:
                print(f"[policy] wiring error: {report}", file=sys.stderr)
                print(verdict_line(reason_code="wiring_error"), file=sys.stderr)
                return EXIT_BLOCK
            # N21：把本次运行真正会写的审计 / 台账路径写成一行一等输出。
            # 少了它，读者只能按配置名去数台账，而那个名字在带 --audit 时已被派生覆盖。
            print(effective_paths_line(config, audit_path=args.audit), file=sys.stderr)
            print("[policy] self-check ok", file=sys.stderr)
            return EXIT_ALLOW

        payload = json.loads(sys.stdin.read() or "null")
        hook_event = hook_event_of(payload)
    except (DshEventError, LoaderError, OSError, ValueError) as error:
        print(f"[policy] BLOCKED (startup_error) detail: {error}", file=sys.stderr)
        print(verdict_line(reason_code="startup_error"), file=sys.stderr)
        # 台阶 2（R-g）：这里正是配置族最常被误归因的地方——"起不来"很容易被读成
        # "运行时没装"。核验前置先看一眼被点名的配置到底怎么了（路径不存在 / 是个目录 /
        # 不是 UTF-8 / 其实好好的），再决定这条理由指着谁；核验证伪了自己人就落
        # unknown_origin，**绝不**换一个对象继续指控。归因只进这一行诊断，不进判定。
        print(
            origin_line(
                origin_from_failure(
                    reason_code="startup_error",
                    detail=str(error),
                    config_path=args.config,
                    config_source="--config（本次 Hook 进程显式给出的 adapter 配置）",
                )
            ),
            file=sys.stderr,
        )
        return EXIT_BLOCK

    try:
        outcome = run_hook(
            payload,
            config_path=args.config,
            audit_path=args.audit,
            capture_dir=args.capture,
            hooks_config_path=args.hooks_config,
            # CLI 是生产入口：**默认要求接线证据**，缺 --hooks-config 即失败关闭（G12）。
            allow_unverified_wiring=args.allow_unverified_wiring,
        )
    except Exception as error:  # noqa: BLE001 - 最后一道失败关闭：绝不能以退出码 1 结束
        print(
            f"[policy] BLOCKED (startup_error) detail: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        print(verdict_line(reason_code="startup_error", hook_event=hook_event), file=sys.stderr)
        # 归因**总要**给出一条：给不出对象时它就是 unknown_origin（写明"没有对象可核验"），
        # 而不是缺席——缺席会让读者把"这次没归因"读成"这次归因没问题"。
        # 函数内 import：config_path_in 只在异常路径上用得上，别给正常路径加依赖。
        from provenance.origin import config_path_in

        named = config_path_in(str(error))
        print(
            origin_line(
                origin_from_failure(
                    reason_code="startup_error",
                    detail=str(error),
                    config_path=named,
                    config_source=(
                        "从失败原文里取回（配置：--config " + str(args.config) + "）"
                        if named is not None
                        else "失败原文与 --config 都没有指名可核验的对象"
                    ),
                )
            ),
            file=sys.stderr,
        )
        return EXIT_BLOCK

    if outcome.stderr:
        print(outcome.stderr, file=sys.stderr)
    if outcome.exit_code == EXIT_ALLOW:
        return EXIT_ALLOW
    if not outcome.stderr:
        print(f"[policy] BLOCKED ({outcome.reason_code})", file=sys.stderr)
    print(
        verdict_line(reason_code=outcome.reason_code, hook_event=hook_event), file=sys.stderr
    )
    return EXIT_BLOCK


if __name__ == "__main__":
    raise SystemExit(main())
