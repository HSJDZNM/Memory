"""dsh Adapter：把 dsh 的 Hook 事件映射成核心协议。

职责严格限定为（Phase 2 文档第 2 步）：

    dsh Event → 验证 → 字段规范化 → PolicyEvent / PolicyContext

它不加载规则、不决定 severity、不调用工具、不拼接 Prompt、不读文件系统、不访问网络，
也不导入 dsh 的 TypeScript 实现：本模块只依赖 dsh 的线协议（stdin 上的 JSON 载荷），
因此可以在没有安装 dsh 的环境里跑契约测试。

调查结论（dsh 0.1.5-rc.1，证据见 src/adapters/dsh/README.md）决定了这里的形状：

- Hook 事件名是 PreToolUse / PostToolUse / UserPromptSubmit / SessionStart / Stop；
  Phase 2 只治理工具执行前的 PreToolUse，其他事件一律拒绝，不猜测语义；
- 载荷由事件基座加事件字段构成：session_id、transcript_path（dsh 恒为空串）、
  cwd、hook_event_name，加 tool_name、tool_input、tool_use_id；
- 工具名是扁平 snake_case 字符串，参数同样是 snake_case（file_path / content /
  old_string / new_string）；pre-execute 阶段拿到的是未解析的原始路径，
  解析基准是载荷里的 cwd（dsh 传的是 agent.session.header.cwd）；
- 载荷里没有 layer、language、principal、依赖列表：这些字段由适配器配置显式声明，
  绝不从文件名、目录或用户消息推断；声明不出来就失败关闭。

按治理缺口复核（R3 / R4-glob / R5-工具表）追加的四条约束：

- 依赖证据不许只抓"顶层名字"：变更文本里的 import 提取**完整点分路径**
  （相对导入保留前导点），动态导入取字符串字面量目标；"证明不了"的部分
  （目标不是字面量、变更片段解析不了）留下显式标记，由依赖类 checker 失败关闭。
  判定语义与验证器（AST / 依赖图）路径对齐，两边共用 policy.checkers 的同一个比较函数；
- 分层命中必须可解释：layer_resolution() 同时给出命中的 pattern 与"是否走了默认值"，
  "未命中任何分层规则"必须能与"命中某个层"区分开；
- 通配符语义与 src/validators/globs.py 一致（"**/" = 零个或多个目录）。同一个
  "在范围内"的语义不许有两份实现给出不同答案；
- 工具表是默认拒绝的白名单：缺漂移检测就会退化成"接线即瘫痪"，
  因此 tool_table_drift() 把"运行期观察到的工具"与表做差集，新增项列为**待评审**。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Tuple

import yaml

from policy.checkers import UNPROVEN_CHANGED_TEXT, UNPROVEN_DYNAMIC_IMPORT
from policy.context import repo_relative_path
from policy.models import (
    Operation,
    PolicyContext,
    PolicyContextError,
    Principal,
    canonical_identifier,
    normalize_repo_path,
)

# 依赖提取的**唯一实现**在共享层（Agent 无关）：这里保留同名再导出，
# Phase 2 的对外接口与行为逐字节不变，Phase 6 的接线点也调同一份实现。
from ..textfacts import (
    DependencyProposal,
    governed_dependencies,
    propose_dependencies,
    proposed_dependencies,
)

__all__ = [
    "DSH_AGENT_ID",
    "HOOK_EVENT_POST_TOOL_USE",
    "HOOK_EVENT_PRE_TOOL_USE",
    "REQUIRED_PAYLOAD_FIELDS",
    "SUPPORTED_HOOK_EVENTS",
    "TOOL_TABLE",
    "UNPROVEN_CHANGED_TEXT",
    "UNPROVEN_DYNAMIC_IMPORT",
    "AdapterConfig",
    "AdapterDecision",
    "DependencyProposal",
    "DshEventError",
    "LanguageRule",
    "LayerResolution",
    "LayerRule",
    "PolicyEvent",
    "ToolKind",
    "ToolSpec",
    "ToolTableDrift",
    "config_from_mapping",
    "glob_match",
    "load_config",
    "observed_tools_from_payloads",
    "propose_dependencies",
    "proposed_dependencies",
    "read_payload",
    "to_policy_context",
    "to_policy_event",
    "tool_table_drift",
]

# Agent 固定标识：审计必须能区分"决定来自哪个 Agent"；版本单独记录，不混进标识。
DSH_AGENT_ID = "dsh"

HOOK_EVENT_PRE_TOOL_USE = "PreToolUse"
HOOK_EVENT_POST_TOOL_USE = "PostToolUse"
# Phase 2 只承认工具执行前事件；Phase 4 追加执行后事件（PostToolUse）用于事后验证。
# 其他事件在 Adapter 层被拒绝（未知事件不得静默忽略）。
SUPPORTED_HOOK_EVENTS: Tuple[str, ...] = (HOOK_EVENT_PRE_TOOL_USE, HOOK_EVENT_POST_TOOL_USE)

# dsh PreToolUse 载荷的必需字段（dsh-hooks-claude-code/lib/index.js:347-374）。
# 缺任何一项都无法安全判定；额外字段一律不进入核心模型。
REQUIRED_PAYLOAD_FIELDS: Tuple[str, ...] = (
    "session_id",
    "hook_event_name",
    "tool_name",
    "tool_input",
    "tool_use_id",
)

_CONFIG_FIELDS: Tuple[str, ...] = (
    "agent_version",
    "registry",
    "registry_approved",
    "enforcement_ledger",
    "approval_file",
    "project",
    "project_root",
    "rules",
    "rules_root",
    "timeout_ms",
    "layers",
    "default_layer",
    "languages",
    "default_language",
    "principal",
    "trace_id",
    "audit_log",
)


class DshEventError(ValueError):
    """dsh 事件不符合已核实的线协议，或适配器配置不足以安全判定。

    未知事件、未知工具、缺字段、载荷类型错误、缺少 layer 映射——一律失败关闭：
    Adapter 拒绝映射，Hook 据此阻断并给出可诊断信息。
    """


class ToolKind(str, Enum):
    """工具类别：决定"是否构建上下文并评估策略"，不决定严重级别。"""

    WRITE = "write"
    READ_ONLY = "read_only"
    EXECUTE = "execute"
    NO_FILE = "no_file"


@dataclass(frozen=True)
class ToolSpec:
    """一个 dsh 工具的映射规格。"""

    name: str
    kind: ToolKind
    operation: Optional[Operation]
    path_field: Optional[str] = None
    proposed_fields: Tuple[str, ...] = ()
    note: str = ""


def _spec(
    name: str,
    kind: ToolKind,
    operation: Optional[Operation],
    *,
    path_field: Optional[str] = None,
    proposed_fields: Tuple[str, ...] = (),
    note: str = "",
) -> ToolSpec:
    return ToolSpec(
        name=name,
        kind=kind,
        operation=operation,
        path_field=path_field,
        proposed_fields=proposed_fields,
        note=note,
    )


# 已知工具表。未知工具一律拒绝：dsh 会随版本新增工具（还有任意命名的 MCP 工具），
# 而"没见过就放行"等于把新增的写工具变成策略绕过通道；升级 dsh 时必须先更新这张表并补契约测试。
#
# 表中的名字来自 dsh 0.1.5-rc.1 的真实装配（standard preset）与真实会话观测；
# 名称可由部署方通过 dsh 的 toolName 配置改写，改写后的名字属于"未知工具"，同样失败关闭。
TOOL_TABLE: Mapping[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        # —— 受治理：按"写"的语义修改仓库内容 ——
        _spec(
            "edit",
            ToolKind.WRITE,
            Operation.EDIT,
            path_field="file_path",
            proposed_fields=("new_string",),
            note="字面量替换；只检查本次引入的文本",
        ),
        _spec(
            "write",
            ToolKind.WRITE,
            Operation.CREATE,
            path_field="file_path",
            proposed_fields=("content",),
            note="整文件写入（dsh 文档称 create-or-overwrite），本表映射为 create；"
            "需要同时覆盖两种语义的规则应把 operation 写成 [create, edit]（同维度多值 = OR）",
        ),
        _spec(
            "str_replace_editor",
            ToolKind.WRITE,
            Operation.EDIT,
            path_field="path",
            proposed_fields=("file_text", "new_str"),
            note="dsh-tool-str-replace-editor；与 dsh-tool-fs 是替代关系，标准装配里不启用",
        ),
        # —— 只读 ——
        _spec("read", ToolKind.READ_ONLY, Operation.READ, path_field="file_path"),
        _spec("read_image", ToolKind.READ_ONLY, Operation.READ, path_field="file_path"),
        _spec("glob", ToolKind.READ_ONLY, Operation.READ, path_field="path"),
        _spec("grep", ToolKind.READ_ONLY, Operation.READ, path_field="path"),
        # —— 执行类：Phase 4 的治理范围，本阶段逐条显式记录为 not_governed ——
        _spec("pwsh", ToolKind.EXECUTE, Operation.EXECUTE, note="shell：Phase 4 治理"),
        _spec("bash", ToolKind.EXECUTE, Operation.EXECUTE, note="shell：Phase 4 治理"),
        _spec(
            "run_code",
            ToolKind.EXECUTE,
            Operation.EXECUTE,
            note="代码运行时：可以写文件，Phase 4 治理",
        ),
        _spec("workflow", ToolKind.EXECUTE, Operation.EXECUTE, note="子工作流：Phase 4 治理"),
        # —— 不触碰文件系统 ——
        _spec("todo_write", ToolKind.NO_FILE, None),
        _spec("create_goal", ToolKind.NO_FILE, None),
        _spec("get_goal", ToolKind.NO_FILE, None),
        _spec("update_goal", ToolKind.NO_FILE, None),
        _spec("exit_plan_mode", ToolKind.NO_FILE, None),
        _spec("job_list", ToolKind.NO_FILE, None),
        _spec("job_output", ToolKind.NO_FILE, None),
        _spec("job_kill", ToolKind.NO_FILE, None),
        _spec("list_agents", ToolKind.NO_FILE, None),
        _spec("list_subagent_models", ToolKind.NO_FILE, None),
        _spec("send_message", ToolKind.NO_FILE, None),
        _spec("interrupt_agent", ToolKind.NO_FILE, None),
        _spec("subagent", ToolKind.NO_FILE, None),
        _spec("subagent_fork", ToolKind.NO_FILE, None),
        _spec("ralph", ToolKind.NO_FILE, None),
        _spec("skill", ToolKind.NO_FILE, None),
        _spec("ask_user_question", ToolKind.NO_FILE, None),
        _spec("present", ToolKind.NO_FILE, None),
        _spec("web_search", ToolKind.NO_FILE, None),
        _spec("web_fetch", ToolKind.NO_FILE, None),
        # —— Agent Teams 的编排类工具（G10）：白名单缺了它们，一接线就变成
        # "新工具全部判未知而阻断"，而不是"新工具被评审过"。——
        # 分类口径只有一条：**这个工具自己写不写仓库里的文件**。
        # 不写 → NO_FILE（记录但不治理）；绝不因为"它可能间接导致写"就声称它已被治理。
        _spec(
            "spawn_teammate",
            ToolKind.NO_FILE,
            None,
            note="拉起一个独立会话（teammate）：它自己不写仓库文件，但被拉起的会话是否"
            "有检查站，本检查站**看不到**（子会话的写类动作不会经过父会话的 PreToolUse）。"
            "因此这里只记录、不声称已治理；通道是否接线由 adapters 的接线自检负责"
            "（AGENTS.md 第 24 条：拦不住写类动作的通道不得被标成完整 enforcement）",
        ),
        _spec(
            "team_task_create",
            ToolKind.NO_FILE,
            None,
            note="共享任务板：写的是协作状态（谁做什么），不是仓库文件；"
            "任务板自身的审计由任务板负责，这里只记录该调用发生过",
        ),
        _spec(
            "team_task_get",
            ToolKind.NO_FILE,
            None,
            note="共享任务板：只读一次任务详情，不触碰文件系统",
        ),
        _spec(
            "team_task_list",
            ToolKind.NO_FILE,
            None,
            note="共享任务板：只读任务列表，不触碰文件系统",
        ),
        _spec(
            "team_task_update",
            ToolKind.NO_FILE,
            None,
            note="共享任务板：认领 / 完成等状态转移。它改写协作记录而不是仓库文件，"
            "因此按「记录但不治理」处理——绝不记成「检查通过」",
        ),
        _spec(
            "wait_agent",
            ToolKind.NO_FILE,
            None,
            note="阻塞等待队友状态变化：不触碰文件系统；占用一次工具调用的时间预算",
        ),
        _spec(
            "load_workspace_dependencies",
            ToolKind.NO_FILE,
            None,
            note="返回本机解释器与依赖目录/版本；不读写仓库文件（调用方据此拼命令，"
            "命令本身由执行类工具的受控链路治理）",
        ),
    )
}

# 默认拒绝的白名单 + 没有漂移检测 = "接线即瘫痪"：Agent 一升级，新工具全部判未知而阻断，
# 而"哪些新工具出现过"没有任何地方记录。下面这个纯函数把观察与声明做差集，
# 新增项列为**待评审**；它不改变任何判定，只把"表落后了"变成一条可失败的检查。


@dataclass(frozen=True)
class ToolTableDrift:
    """一次"运行期观察到的工具 vs TOOL_TABLE"的差集。

    - unreviewed：观察到了、工具表里没有 → **待评审**（不是自动放行，也不是忽略）；
    - absent：工具表里有、本批观察里没有 → 只是信息（白名单可以比一次观察更宽）；
    - source：观察数据来自哪里（审计日志 / 事件 fixture / 会话工具清单快照）。

    clean 为真只代表"这张表没有落后于这批观察"，不代表工具已被治理。
    """

    source: str
    observed: Tuple[str, ...]
    unreviewed: Tuple[str, ...]
    absent: Tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.unreviewed

    def to_payload(self) -> Mapping[str, Any]:
        return {
            "source": self.source,
            "observed": list(self.observed),
            "unreviewed": list(self.unreviewed),
            "absent": list(self.absent),
            "clean": self.clean,
        }


def observed_tools_from_payloads(payloads: Iterable[Any]) -> Tuple[str, ...]:
    """从 dsh 钩子载荷里取工具名（观察数据的一种来源）。

    载荷形状不是本模块说了算的：缺 tool_name、类型不对一律报错，不跳过、不补默认值 ——
    观察数据本身不可信时，漂移检测的结论也不可信。
    """

    seen: set[str] = set()
    for index, payload in enumerate(payloads):
        if not isinstance(payload, Mapping):
            raise DshEventError(f"观察载荷[{index}] 必须是映射，得到 {type(payload).__name__}")
        name = payload.get("tool_name")
        if not isinstance(name, str) or not name.strip():
            raise DshEventError(
                f"观察载荷[{index}] 缺少 tool_name：无法据此判断工具表是否漂移"
            )
        seen.add(name.strip())
    return tuple(sorted(seen))


def tool_table_drift(
    observed: Iterable[str],
    *,
    source: str,
    table: Optional[Mapping[str, ToolSpec]] = None,
) -> ToolTableDrift:
    """把观察到的工具名与 TOOL_TABLE 做差集（纯函数、离线、确定性）。

    观察数据从哪里来（三种都要显式传 source，结论才能追到来源）：

    - dsh 钩子审计 JSONL（adapter 配置 audit_log 指向的那份，字段 tool）：运行期真实调用；
    - tests/fixtures/agent_events/dsh/*.json：committed 的真实采集样本，可离线复现；
    - 会话工具清单快照：Agent 侧声明的工具全集，没有事件可采时的下限。

    拿不到观察数据时调用方必须**报错**，不能传空集：空集会被读成"没有漂移"，
    那正是缺口 G10 的形态。这里的做法是显式拒绝空观察集。
    """

    if not isinstance(source, str) or not source.strip():
        raise DshEventError("漂移检测必须写明观察数据来源（source）：来源不明的差集不可复核")

    cleaned: set[str] = set()
    for name in observed:
        if not isinstance(name, str) or not name.strip():
            raise DshEventError(f"观察到的工具名必须是非空字符串，得到 {name!r}")
        cleaned.add(name.strip())
    if not cleaned:
        raise DshEventError(
            "观察集为空：拒绝把「没观察到」当成「没有漂移」（拿不到观察数据时请显式报错）"
        )

    known = TOOL_TABLE if table is None else table
    if not known:
        raise DshEventError("工具表为空：默认拒绝的白名单不该是空的，差集没有意义")

    return ToolTableDrift(
        source=source.strip(),
        observed=tuple(sorted(cleaned)),
        unreviewed=tuple(sorted(cleaned - set(known))),
        absent=tuple(sorted(set(known) - cleaned)),
    )


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """把仓库相对路径 glob 编译成正则。

    语义与 src/validators/globs.py 完全一致：

    - "**/" 匹配**零个或多个**目录，即 "(?:.*/)?"（曾经实现成"至少一层目录"，
      于是 adapter 配置里写 "**/*.md" 匹配不到根目录的 README.md：
      配置看着对、实际漏一层，属于静默失效）；
    - 结尾的 "**" 匹配任意剩余路径；
    - "*" 不跨目录，"?" 匹配单个字符。

    两份实现的等价性由 tests/contract/test_dsh_adapter.py 的跨模块对照测试钉住：
    同一个"这个路径在不在范围内"的语义，不许有两份实现给出不同答案。
    """

    parts: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if pattern[index : index + 2] == "**":
                if pattern[index + 2 : index + 3] == "/":
                    parts.append("(?:.*/)?")
                    index += 3
                    continue
                parts.append(".*")
                index += 2
                continue
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(char))
        index += 1
    return re.compile("^" + "".join(parts) + "$")


_GLOB_CACHE: dict[str, re.Pattern[str]] = {}


def glob_match(pattern: str, path: str) -> bool:
    """仓库相对路径匹配；pattern 与 path 都用斜杠分隔。"""

    compiled = _GLOB_CACHE.get(pattern)
    if compiled is None:
        compiled = _glob_to_regex(pattern)
        _GLOB_CACHE[pattern] = compiled
    return bool(compiled.match(path))


@dataclass(frozen=True)
class LayerRule:
    """显式声明的 path → layer 映射：可评审，而不是代码里硬编码推断。"""

    pattern: str
    layer: str


@dataclass(frozen=True)
class LanguageRule:
    """显式声明的 path → language 映射。"""

    pattern: str
    language: str


@dataclass(frozen=True)
class LayerResolution:
    """一次分层解析的完整结果（跨工作流冻结接口，审计侧按这三个字段落记录）。

    - 命中某条 layers 规则：layer = 声明的层，matched_pattern = 命中的 pattern，
      defaulted = False；
    - 未命中任何分层规则：layer = default_layer（可能为 None），matched_pattern = None，
      defaulted = True。

    因此"未命中任何分层规则"（defaulted=True 且 matched_pattern=None）与
    "命中某个层"（defaulted=False 且有 pattern）在审计里区分得开：
    默认值不是一条分层规则，它只是"没有规则给出答案"时的显式兜底。
    """

    layer: Optional[str]
    matched_pattern: Optional[str]
    defaulted: bool


@dataclass(frozen=True)
class AdapterConfig:
    """dsh Adapter 的显式上下文来源。

    核心协议需要、而 dsh 载荷不提供的字段都在这里声明：layer、language、project、
    principal、trace_id。没有声明项时失败关闭，而不是猜一个值出来。
    """

    project_root: Path
    rule_dirs: Tuple[Path, ...]
    agent_version: str = "unknown"
    project: Optional[str] = None
    timeout_ms: int = 5000
    layers: Tuple[LayerRule, ...] = ()
    default_layer: Optional[str] = None
    languages: Tuple[LanguageRule, ...] = ()
    default_language: Optional[str] = None
    principal: Optional[Principal] = None
    trace_id: Optional[str] = None
    audit_log: Optional[Path] = None
    rules_root: Optional[Path] = None
    config_path: Optional[Path] = None
    # Phase 4：受控执行所需的工具注册表与幂等台账
    registry_path: Optional[Path] = None
    registry_approved_path: Optional[Path] = None
    enforcement_ledger: Optional[Path] = None
    approval_file: Optional[Path] = None

    @property
    def rule_anchor(self) -> Path:
        """规则目录的锚点。

        被治理项目与规则库常常不在同一个仓库：规则可以放在中心规则库里，
        因此规则来源的仓库相对路径必须相对自己的锚点计算，而不是相对被治理项目。
        """

        return self.rules_root if self.rules_root is not None else self.project_root

    def layer_resolution(self, repo_path: str) -> LayerResolution:
        """解析一次分层：按声明顺序取第一个命中的规则，否则退回显式默认值。

        返回值把"命中了哪条 pattern"与"是不是走了默认值"一起交出来，
        审计因此能回答"这个 layer 是判出来的还是兜底来的"——否则
        "未命中任何分层规则"会和"命中默认层"长得一模一样。
        """

        for rule in self.layers:
            if glob_match(rule.pattern, repo_path):
                return LayerResolution(
                    layer=rule.layer, matched_pattern=rule.pattern, defaulted=False
                )
        return LayerResolution(
            layer=self.default_layer, matched_pattern=None, defaulted=True
        )

    def layer_for(self, repo_path: str) -> Optional[str]:
        """按声明顺序取第一个命中的 layer；没有命中就用显式声明的默认值（可能为空）。

        保留原签名与行为（向后兼容）：完整结果见 layer_resolution()。
        """

        return self.layer_resolution(repo_path).layer

    def language_for(self, repo_path: str) -> Optional[str]:
        for rule in self.languages:
            if glob_match(rule.pattern, repo_path):
                return rule.language
        return self.default_language


class _StrictLoader(yaml.SafeLoader):
    """拒绝重复键的 YAML 加载器。

    PyYAML 默认让重复键"后者覆盖前者"，在策略配置里等同于静默改变执行范围，必须报错。
    """


def _construct_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> Any:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"发现重复键 {key!r}：策略配置不得有歧义",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _require(mapping: Mapping[str, Any], key: str, *, where: str) -> Any:
    if key not in mapping:
        raise DshEventError(f"{where} 缺少必需字段 {key!r}")
    return mapping[key]


def _as_str(value: Any, *, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DshEventError(f"{where} 必须是非空字符串，得到 {value!r}")
    return value.strip()


def _as_path(value: Any, *, base_dir: Path, where: str) -> Path:
    raw = _as_str(value, where=where)
    candidate = Path(raw.replace("\\", "/"))
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate.resolve()


def _rule_rows(
    document: Mapping[str, Any], *, key: str, fields: Tuple[str, ...]
) -> list[dict[str, str]]:
    raw = document.get(key, [])
    if not isinstance(raw, (list, tuple)):
        raise DshEventError(f"{key} 必须是列表，元素形如 {{{', '.join(fields)}}}")
    parsed: list[dict[str, str]] = []
    for index, item in enumerate(raw):
        where = f"{key}[{index}]"
        if not isinstance(item, Mapping):
            raise DshEventError(f"{where} 必须是映射")
        unknown = sorted(set(item) - set(fields))
        if unknown:
            raise DshEventError(f"{where} 出现未知字段 {unknown}")
        parsed.append(
            {
                field: _as_str(_require(item, field, where=where), where=f"{where}.{field}")
                for field in fields
            }
        )
    return parsed


def config_from_mapping(document: Mapping[str, Any], *, base_dir: Path) -> AdapterConfig:
    """从显式映射构造 Adapter 配置；未知键、类型错误、缺必需项一律报错。"""

    if not isinstance(document, Mapping):
        raise DshEventError(f"adapter 配置必须是映射，得到 {type(document).__name__}")

    unknown = sorted(set(document) - set(_CONFIG_FIELDS))
    if unknown:
        raise DshEventError(
            f"adapter 配置出现未知字段 {unknown}；允许的字段为 {sorted(_CONFIG_FIELDS)}"
        )

    project_root = _as_path(
        _require(document, "project_root", where="adapter 配置"),
        base_dir=base_dir,
        where="project_root",
    )

    raw_rules = _require(document, "rules", where="adapter 配置")
    if not isinstance(raw_rules, (list, tuple)) or not raw_rules:
        raise DshEventError("rules 必须是非空列表：至少声明一个规则目录")
    rule_dirs = tuple(
        _as_path(item, base_dir=base_dir, where=f"rules[{index}]")
        for index, item in enumerate(raw_rules)
    )

    layers = tuple(
        LayerRule(pattern=item["pattern"], layer=canonical_identifier(item["layer"]))
        for item in _rule_rows(document, key="layers", fields=("pattern", "layer"))
    )
    languages = tuple(
        LanguageRule(pattern=item["pattern"], language=canonical_identifier(item["language"]))
        for item in _rule_rows(document, key="languages", fields=("pattern", "language"))
    )

    principal: Optional[Principal] = None
    raw_principal = document.get("principal")
    if raw_principal is not None:
        if not isinstance(raw_principal, Mapping):
            raise DshEventError("principal 必须是 {subject, roles} 结构")
        unknown_principal = sorted(set(raw_principal) - {"subject", "roles"})
        if unknown_principal:
            raise DshEventError(f"principal 出现未知字段 {unknown_principal}")
        try:
            principal = Principal.model_validate(dict(raw_principal))
        except Exception as error:  # pydantic ValidationError
            raise DshEventError(f"principal 不合法：{error}") from error

    timeout_ms = document.get("timeout_ms", 5000)
    if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0:
        raise DshEventError(f"timeout_ms 必须是正整数毫秒，得到 {timeout_ms!r}")

    def optional_identifier(key: str) -> Optional[str]:
        value = document.get(key)
        if value is None:
            return None
        return canonical_identifier(_as_str(value, where=key))

    audit_log = document.get("audit_log")
    rules_root = document.get("rules_root")
    registry = document.get("registry")
    registry_approved = document.get("registry_approved")
    enforcement_ledger = document.get("enforcement_ledger")
    approval_file = document.get("approval_file")

    return AdapterConfig(
        project_root=project_root,
        rule_dirs=rule_dirs,
        agent_version=canonical_identifier(
            _as_str(document.get("agent_version", "unknown"), where="agent_version")
        ),
        project=optional_identifier("project"),
        timeout_ms=timeout_ms,
        layers=layers,
        default_layer=optional_identifier("default_layer"),
        languages=languages,
        default_language=optional_identifier("default_language"),
        principal=principal,
        trace_id=(
            None
            if document.get("trace_id") is None
            else _as_str(document["trace_id"], where="trace_id")
        ),
        audit_log=(
            None if audit_log is None else _as_path(audit_log, base_dir=base_dir, where="audit_log")
        ),
        rules_root=(
            None
            if rules_root is None
            else _as_path(rules_root, base_dir=base_dir, where="rules_root")
        ),
        config_path=None,
        registry_path=(
            None if registry is None else _as_path(registry, base_dir=base_dir, where="registry")
        ),
        registry_approved_path=(
            None
            if registry_approved is None
            else _as_path(registry_approved, base_dir=base_dir, where="registry_approved")
        ),
        enforcement_ledger=(
            None
            if enforcement_ledger is None
            else _as_path(enforcement_ledger, base_dir=base_dir, where="enforcement_ledger")
        ),
        approval_file=(
            None
            if approval_file is None
            else _as_path(approval_file, base_dir=base_dir, where="approval_file")
        ),
    )


def load_config(path: Path | str) -> AdapterConfig:
    """读取并校验 Adapter 配置（YAML；拒绝重复键与未知字段）。"""

    config_path = Path(path)
    if not config_path.is_file():
        raise DshEventError(f"adapter 配置不存在: {config_path.name}")
    try:
        text = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise DshEventError(f"adapter 配置不可读: {config_path.name} ({error})") from error

    try:
        # _StrictLoader 是 yaml.SafeLoader 的子类（额外拒绝未知字段），不是任意对象
        # 实例化：bandit 的 B506 只看 yaml.load 的调用形态，属于仓库已知误报。
        document = yaml.load(text, Loader=_StrictLoader)  # noqa: S506 - SafeLoader 子类
    except yaml.YAMLError as error:
        raise DshEventError(f"adapter 配置解析失败: {config_path.name} ({error})") from error
    if document is None:
        raise DshEventError(f"adapter 配置为空: {config_path.name}")

    return replace(
        config_from_mapping(document, base_dir=config_path.parent), config_path=config_path
    )


@dataclass(frozen=True)
class PolicyEvent:
    """规范化后的标准事件（架构文档里的 tool.pre_execute）。

    只保留核心协议需要的字段：dsh 载荷里的其他内容不进入模型；载荷本身用摘要指代，
    既能做审计关联，又不会把源码内容或用户数据留进证据文件。
    """

    event_id: str
    request_id: str
    kind: str
    agent: str
    agent_version: str
    tool: str
    operation: Operation
    file: str
    layer: str
    language: Optional[str]
    dependencies: Tuple[str, ...]
    payload_digest: str
    payload_fields: Tuple[str, ...]
    session_id: str
    cwd: Optional[str]
    trace_id: Optional[str] = None


@dataclass(frozen=True)
class AdapterDecision:
    """一次映射的结果：是否受治理 + 原因 +（受治理时的）标准事件。"""

    governed: bool
    reason: str
    event: Optional[PolicyEvent] = None


def read_payload(raw: Any) -> Mapping[str, Any]:
    """校验 dsh 载荷的形状：必须是映射，必需字段齐全且类型正确。"""

    if not isinstance(raw, Mapping):
        raise DshEventError(f"dsh 事件载荷必须是映射，得到 {type(raw).__name__}")

    missing = [name for name in REQUIRED_PAYLOAD_FIELDS if name not in raw]
    if missing:
        raise DshEventError(f"dsh 事件载荷缺少必需字段 {missing}")

    event_name = raw["hook_event_name"]
    if event_name not in SUPPORTED_HOOK_EVENTS:
        raise DshEventError(
            f"未支持的 hook 事件 {event_name!r}；Phase 2 只治理 {list(SUPPORTED_HOOK_EVENTS)}，"
            "未识别事件不得静默放行"
        )

    for name in ("session_id", "tool_name", "tool_use_id", "hook_event_name"):
        value = raw[name]
        if not isinstance(value, str) or not value.strip():
            raise DshEventError(f"dsh 事件字段 {name} 必须是非空字符串，得到 {value!r}")

    tool_input = raw["tool_input"]
    if not isinstance(tool_input, Mapping):
        raise DshEventError(
            f"dsh 事件字段 tool_input 必须是映射（工具参数），得到 {type(tool_input).__name__}"
        )

    cwd = raw.get("cwd")
    if cwd is not None and (not isinstance(cwd, str) or not cwd.strip()):
        raise DshEventError(f"dsh 事件字段 cwd 必须是非空字符串或缺失，得到 {cwd!r}")

    if event_name == HOOK_EVENT_POST_TOOL_USE and "tool_response" not in raw:
        # 事后验证必须拿得到"运行时到底返回了什么"；缺失时不得猜成成功。
        raise DshEventError("PostToolUse 载荷缺少 tool_response：无法验证执行结果")

    return raw


def _payload_digest(tool_input: Mapping[str, Any]) -> str:
    """工具参数摘要：稳定序列化后取 sha256，避免把原文写进审计。"""

    canonical = json.dumps(
        {str(key): tool_input[key] for key in sorted(tool_input, key=str)},
        ensure_ascii=False,
        sort_keys=True,
    )
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def _resolve_file(raw_path: Any, *, cwd: Optional[str], config: AdapterConfig) -> str:
    """把工具参数里的路径解析成仓库相对路径。

    dsh 在 pre-execute 阶段给出的是未解析的原始字符串，解析基准是会话工作目录
    （载荷里的 cwd，即 agent.session.header.cwd）。逃出仓库的路径一律拒绝。
    """

    if not isinstance(raw_path, str) or not raw_path.strip():
        raise DshEventError("工具参数缺少目标文件路径；路径是安全关键字段，不得猜测")

    candidate = Path(raw_path.strip())
    if not candidate.is_absolute() and cwd:
        candidate = Path(cwd) / candidate

    return repo_relative_path(str(candidate), repo_root=config.project_root)


def _resolve_read_scope(
    raw_path: Any, *, cwd: Optional[str], config: AdapterConfig, tool: str
) -> str:
    """只读工具的目标范围：允许仓库根目录本身，但必须在受控项目内。

    注册表给只读工具声明了 `path_scope: workspace`；Adapter 不做授权判定，
    但"这次读的是哪个范围"必须能被证明。读不到显式路径时退回会话 cwd，
    证明不了就失败关闭——只读同样是越界即拒，而不是"反正不写所以不管"。

    与 `_resolve_file` 的唯一区别是允许等于仓库根目录（glob 常以项目根为范围）。
    """

    candidate: Optional[Path] = None
    if isinstance(raw_path, str) and raw_path.strip():
        candidate = Path(raw_path.strip())
        if not candidate.is_absolute() and cwd:
            candidate = Path(cwd) / candidate
    elif cwd:
        candidate = Path(cwd)

    if candidate is None:
        raise DshEventError(
            f"{tool} 既没有路径参数也没有会话 cwd：无法证明读取范围在受控项目内，拒绝放行"
        )

    anchor = Path(config.project_root).resolve()
    target = candidate.resolve()
    if target == anchor:
        return "."
    head = target.parts[: len(anchor.parts)]
    if len(target.parts) <= len(anchor.parts) or [item.lower() for item in head] != [
        item.lower() for item in anchor.parts
    ]:
        raise DshEventError(
            f"{tool} 的目标 {raw_path if raw_path else cwd!r} 不在受控项目 {anchor.name} 内："
            "只读动作同样受 path_scope=workspace 约束，越界一律拒绝"
        )
    return normalize_repo_path("/".join(target.parts[len(anchor.parts) :]))


def to_policy_event(raw: Any, *, config: AdapterConfig) -> AdapterDecision:
    """把一条 dsh 事件映射成标准事件，或显式判定它不受 Phase 2 治理。"""

    if not isinstance(config, AdapterConfig):
        raise DshEventError(f"config 必须是 AdapterConfig，得到 {type(config).__name__}")

    payload = read_payload(raw)
    tool_name = payload["tool_name"].strip()
    spec = TOOL_TABLE.get(tool_name)
    if spec is None:
        hint = (
            "（看起来像 MCP 工具：Phase 6 会引入声明式工具表）"
            if tool_name.startswith("mcp__")
            else ""
        )
        raise DshEventError(
            f"未知工具 {tool_name!r}{hint}：Adapter 工具表里没有它，拒绝在未知执行语义下放行。"
            "升级 dsh 后必须先更新 src/adapters/dsh/adapter.py 的 TOOL_TABLE 并补契约测试"
        )

    session_id = payload["session_id"].strip()
    tool_use_id = payload["tool_use_id"].strip()
    raw_cwd = payload.get("cwd")
    cwd = raw_cwd.strip() if isinstance(raw_cwd, str) and raw_cwd.strip() else None
    tool_input = payload["tool_input"]

    if spec.kind is not ToolKind.WRITE:
        # Adapter 只做协议转换，不在这里做判定：它只说明"这个工具为什么没有进入写类链路"。
        if spec.kind is ToolKind.READ_ONLY:
            # 降级的是"授权链路"，不是"范围校验"：读了什么必须能被证明并记进审计。
            scope = _resolve_read_scope(
                tool_input.get(spec.path_field) if spec.path_field else None,
                cwd=cwd,
                config=config,
                tool=tool_name,
            )
            note = f"只读动作：显式降级（仍记录），不做前置授权；范围 {scope}"
        elif spec.kind is ToolKind.EXECUTE:
            note = "执行类工具：交给 Phase 4 受控链路（权限 / 参数与命令白名单 / 审批 / 事后验证）"
        else:
            # 工具自己声明的 note 优先：NO_FILE 不等于"没有值得记的事"，
            # 例如 spawn_teammate 能拉起一个本检查站看不见的会话，这句话必须进审计。
            note = spec.note or "不触碰文件系统：不治理"
        return AdapterDecision(
            governed=False,
            reason=f"tool={tool_name} kind={spec.kind.value}：{note}",
        )

    if spec.operation is None or spec.path_field is None:
        raise DshEventError(f"工具表内部不一致：{tool_name} 缺少 operation 或 path_field")

    repo_path = _resolve_file(tool_input.get(spec.path_field), cwd=cwd, config=config)

    layer = config.layer_for(repo_path)
    if layer is None:
        raise DshEventError(
            f"路径 {repo_path} 没有声明 layer 映射：layer 是安全关键字段，Adapter 不得猜测。"
            "请在 adapter 配置的 layers 里补充 pattern 到 layer 的映射，或显式声明 default_layer"
        )

    language = config.language_for(repo_path)
    if language is None and config.languages and config.default_language is None:
        # 声明过 languages 却没有命中，说明映射不完整：这是配置缺陷，不当作语言未知处理。
        raise DshEventError(
            f"路径 {repo_path} 没有命中 languages 映射；请补充规则或显式声明 default_language"
        )

    text = "\n".join(
        tool_input[field]
        for field in spec.proposed_fields
        if isinstance(tool_input.get(field), str)
    )
    event = PolicyEvent(
        event_id=f"{session_id}:{tool_use_id}",
        request_id=f"{session_id}:{tool_use_id}",
        kind="tool.pre_execute",
        agent=DSH_AGENT_ID,
        agent_version=config.agent_version,
        tool=tool_name,
        operation=spec.operation,
        file=repo_path,
        layer=layer,
        language=language,
        dependencies=(
            governed_dependencies(text, language=language) if spec.proposed_fields else ()
        ),
        payload_digest=_payload_digest(tool_input),
        payload_fields=tuple(sorted(str(key) for key in tool_input)),
        session_id=session_id,
        cwd=cwd,
        trace_id=config.trace_id,
    )
    return AdapterDecision(governed=True, reason=f"tool={tool_name} kind=write", event=event)


def to_policy_context(event: PolicyEvent, *, config: AdapterConfig) -> PolicyContext:
    """把标准事件转成核心 PolicyContext。

    只搬运显式声明过的字段：principal 与 trace_id 来自配置，绝不从文件名、目录或
    用户消息推断；缺失就留空，并让规则在 skipped_rules 里说明未参与判断的原因。
    """

    if not isinstance(event, PolicyEvent):
        raise DshEventError(f"to_policy_context 只接受 PolicyEvent，得到 {type(event).__name__}")

    try:
        return PolicyContext(
            request_id=event.request_id,
            project=config.project,
            agent=event.agent,
            operation=event.operation,
            file=event.file,
            language=event.language,
            module=None,  # 刻意不推断：猜错模块会让规则在错误范围生效
            layer=event.layer,
            task=None,
            dependencies=event.dependencies,
            git_diff=None,
            principal=config.principal,
            trace_id=event.trace_id,
        )
    except PolicyContextError:
        raise
    except Exception as error:  # pydantic ValidationError
        raise DshEventError(f"PolicyContext 构造失败：{error}") from error
