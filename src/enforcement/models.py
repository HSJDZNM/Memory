"""Phase 4 受控执行的核心模型：Tool Registry、Action Request、授权、执行与验证证据。

本模块只定义类型、枚举、结构校验与哈希口径，不读文件、不执行工具、不调用 LLM。
与 Phase 1 的核心模型同源：所有模型 extra="forbid"、frozen=True，未知字段与未知枚举报错。

三条不可动摇的约定：

1. **一切绑定都用哈希表达**：action_hash 绑住工具身份、schema 版本与哈希、规范化参数、
   主体、权限、上下文摘要与 request/action 标识。参数变一个字符，哈希就变，
   之前发出的授权（grant）随之失效——"允许结果不可被复用于不同参数"靠的是数学，不是自觉。
2. **决策枚举封闭**：allow / allow_with_warnings / block 之外的值一律拒绝；
   PostDecision / FinalDecision 同样是封闭枚举，未知值按协议错误处理。
3. **协议带版本**：任何字段增删或语义变化都必须改 ENFORCEMENT_SCHEMA_VERSION，
   消费方看不懂就拒绝，绝不降级成 allow。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from hashlib import sha256
from typing import Annotated, Any, Mapping, Optional, Tuple, Union

from pydantic import AfterValidator, Field, field_validator, model_validator

from policy.models import (
    Decision,
    RequiredAction,
    RuleValidationError,
    StrictModel,
    ValidationResult,
    Violation,
)

__all__ = [
    "ENFORCEMENT_SCHEMA_VERSION",
    "SUPPORTED_POST_CHECKS",
    "HIGH_RISK_LEVELS",
    "REGISTRY_SCHEMA_VERSION",
    "SUPPORTED_ENFORCEMENT_SCHEMA_VERSIONS",
    "SUPPORTED_REGISTRY_SCHEMA_VERSIONS",
    "ActionRequest",
    "ActionRequestError",
    "ApprovalMode",
    "CodeCheckSpec",
    "CommandFamily",
    "PathKind",
    "READ_FORBIDDEN_FORMS",
    "READ_PATH_FORMS",
    "ReadGuardSpec",
    "SUPPORTED_CODE_CHECKS",
    "UngovernedSpec",
    "AuditError",
    "AuditFailurePolicy",
    "AuditRecord",
    "AuditStage",
    "AuthorizationGrant",
    "CheckResult",
    "CheckStatus",
    "DriverError",
    "DriverKind",
    "EffectKind",
    "EnforcementError",
    "ExecutionRecord",
    "ExecutionStatus",
    "FinalDecision",
    "FinalOutcome",
    "GrantError",
    "LedgerError",
    "ParamSpec",
    "ParamType",
    "ParamValue",
    "ParamValueValue",
    "PolicySummary",
    "PostDecision",
    "PostEvidence",
    "PostStatus",
    "PreDecision",
    "ProcessEffect",
    "FileBaseline",
    "FileEffect",
    "RateLimit",
    "ReasonCode",
    "RegistryError",
    "RiskLevel",
    "RollbackMode",
    "RollbackOutcome",
    "ToolSpec",
    "canonical_json",
    "digest_of",
    "parse_audit_record",
    "parse_pre_decision",
    "parse_timestamp",
    "to_timestamp",
    "utc_now",
    "ValidatorOutcome",
]

# 1.0（首次建轴）→ **1.1（B3，2026-10-20）**：`ReasonCode` 多出取值 `read_guard_blocked`。
# 键集合一个字没变，变的是**枚举取值集合**——按 AGENTS 第 55 条，取值集合变了同样是协议变化
# （先例：`validators.pipeline` 的 `selection.level` 多出 "support" ⇒ 1.3 → 1.4）。
# 旧消费方看到 `read_guard_blocked` 必须拒绝消费，而不是把它当成一个不认识的"放行"。
# **1.0 仍然接受**：已经落盘的审计 / 台账 / 决策记录是 1.0 载荷，它们与 1.1 的键集合逐字相同，
# 拒收只会让历史证据读不出来；这与 `REGISTRY_SCHEMA_VERSION` 的 1.0/1.1/1.2 同型。
ENFORCEMENT_SCHEMA_VERSION = "1.1"
SUPPORTED_ENFORCEMENT_SCHEMA_VERSIONS = frozenset({"1.0", ENFORCEMENT_SCHEMA_VERSION})


def _check_protocol_version(value: str) -> str:
    """第 3 条"协议带版本"：看不懂的版本一律拒收，不做兼容猜测。"""

    if value not in SUPPORTED_ENFORCEMENT_SCHEMA_VERSIONS:
        raise ValueError(
            f"未知受控执行协议版本 {value!r}；只接受 "
            f"{sorted(SUPPORTED_ENFORCEMENT_SCHEMA_VERSIONS)}，拒绝消费"
        )
    return value


#: **每一个**信封模型共用的版本字段类型。旧实现只在校验 ActionRequest 与 PreDecision：
#: 嵌套在里面的凭据（AuthorizationGrant）可以带任意 schema_version 被消费
#: （grant.verify 不看版本），执行 / 证据 / 终态 / 审计记录同样照单全收——外部或持久化
#: 载荷于是能从"协议带版本"这条不变式下面溜过去。类型只有一份，就不会再漏。
EnforcementVersion = Annotated[str, AfterValidator(_check_protocol_version)]

# 工具注册表数据文件自己的协议轴（与受控执行协议各走各的）。
#
# 1.1（B1，2026-10-20）：逐工具新增**可选**字段 `command_families`（命令族数据），
# 逐参数新增**可选**字段 `default`（审批「参数域」的默认值来源）。加键就是改协议
# （AGENTS 第 55 条），所以显式升版；两者都是可选的，**旧注册表（1.0、不带这两个
# 字段）照常加载**，与 `validators.models.TEST_LAYOUT_SCHEMA_VERSIONS` 的
# 「加可选字段不制造兼容窗口」同型。两个字段都进 `schema_hash`：它们是授权面数据，
# 改了就与已审核哈希对不上（必须重新 `registry --approve`）。
#
# 1.2（B3，2026-10-20）：逐工具新增**可选**字段 `read_guard`（只读命令族的读面闸门数据，
# 见 `ReadGuardSpec`）。同样按第 55 条显式升版；同样可选，因此 `SUPPORTED` 保留 1.0 / 1.1，
# 两份旧注册表照常加载。它进 `schema_hash`（授权面数据）：读面的边界改一个字都必须重新审核。
REGISTRY_SCHEMA_VERSION = "1.2"
SUPPORTED_REGISTRY_SCHEMA_VERSIONS = frozenset({"1.0", "1.1", REGISTRY_SCHEMA_VERSION})

# 命令文本里出现这些片段就说明它不是一条单语句：分隔、管道、命令替换、重定向、
# 换行都意味着「白名单匹配的那条命令之外还有别的东西」。这些一律结构性阻断——
# 只靠 allowlist 正则是不够的：一个 ( .*)? 的尾巴就能吞掉「 ; 任意命令」。
FORBIDDEN_COMMAND_FRAGMENTS = (
    ";",
    "|",
    "&",
    "`",
    "$(",
    "${",
    ">",
    "<",
    "\n",
    "\r",
    "\x00",
)

# Phase 4 内置的事后验证器。注册表里出现别的名字一律拒绝加载：
# "声明了但没人执行"的验证器等于没有门禁，Phase 5 的 Validator Pipeline 会在这张表上扩展。
SUPPORTED_POST_CHECKS = (
    "content_matches",
    "file_changed",
    "file_syntax",
    "diff_recorded",
    "exit_code_zero",
    "target_exists",
)

# 已实现的代码静态检查。与 SUPPORTED_POST_CHECKS 同一套做法：**封闭枚举**，
# 注册表里出现别的名字一律在加载期报错。"声明了但没人执行"的检查等于没有门禁，
# 而"声明了但什么都没查"更糟——它把缺口藏进了一份看起来更完整的声明里。
SUPPORTED_CODE_CHECKS = ("python_forbidden_surface",)

# 读面闸门（read_guard）的两张**闭集**。分开是因为它们回答两个不同的问题，而且都只能由
# 代码来兑现——注册表能声明"用哪几种"，但不能发明一种没人实现的形态（与 SUPPORTED_CODE_CHECKS
# 同一口径：声明了却没人执行的检查等于没有门禁）：
#
# READ_PATH_FORMS       命令文本里**哪些写法算路径操作数**。认不出来的写法等于没有检查，
#                       所以这张表必须显式、有限、可评审。
#   positional          不以 "-" 开头的独立 token（git log -p -- .policy/audit.jsonl）
#   revision_path       <rev>:<path> 里冒号右侧的 path（git show HEAD:.policy/approval.json）
# READ_FORBIDDEN_FORMS  **什么样算读面越界**，每条对应 pre-check 里一条结构性谓词。
#   parent_escape       归一化后越出受控项目（.. / a/../../x）
#   absolute_path       绝对路径（/x、C:/x、UNC）；revision_path 形态按 git 语义视为树内相对，
#                       因此 "HEAD:/README.md" 不算绝对路径——误伤合法读法比漏拦更常见。
READ_PATH_FORMS = ("positional", "revision_path")
READ_FORBIDDEN_FORMS = ("parent_escape", "absolute_path")

# 检查项名字的字符集：与参数名同一口径（稳定标识符），避免出现无法比较的写法。
_CODE_CHECK_ENTRY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


# --------------------------------------------------------------------------- 错误类型


class EnforcementError(Exception):
    """受控执行层的基类错误。"""


class RegistryError(EnforcementError):
    """工具注册表不可用、不合规，或与已审核哈希不一致（配置错误 → 退出码 2）。"""


class ActionRequestError(EnforcementError):
    """Action Request 无法构造或不合法（参数越界、类型错误、未知参数）。

    reason_code 是**结构化的**拒绝原因（ReasonCode 的值）：调用方（Hook / CLI / 编排层）
    必须能按它分流，而不是把所有构造失败都记成一句笼统的"参数错误"——
    "路径越界"与"这个参数不是文件"是两件事，混在一起会让正确参数被误当成写错了。
    """

    def __init__(self, message: str, *, reason_code: Optional[str] = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class GrantError(EnforcementError):
    """授权不可用：哈希不符、过期、已被使用、主体不符或缺少绑定信息。

    一律按失败关闭处理：不执行、不降级、不"再问一次模型"。

    `reason_code` 是**结构化**的拒绝原因（ReasonCode 的值）：执行器据此写审计的
    reason_code，不去解析消息文本——措辞、标点或本地化一改，读文本分流就会把
    "过期 / 已被使用"悄悄降级成笼统的 GRANT_INVALID，而审计信号正是这条链路要保证的东西。
    读不出来时调用方按最保守的 GRANT_INVALID 处理（仍然是拒绝，不会放行）。
    """

    def __init__(self, message: str, *, reason_code: Optional[str] = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class LedgerError(EnforcementError):
    """幂等 / 授权 / 限流台账不可读写。"""


class AuditError(EnforcementError):
    """审计链不可写或已损坏。"""


class DriverError(EnforcementError):
    """执行驱动不可用或拒绝执行（能力缺失时不得假装执行过）。"""


# --------------------------------------------------------------------------- 枚举


class RiskLevel(str, Enum):
    """动作分类（Phase 4 文档第 1 节）。分类由 Tool Registry 定义，模型不得自行声明。"""

    READ_ONLY = "read_only"
    REVERSIBLE_WRITE = "reversible_write"
    DESTRUCTIVE_WRITE = "destructive_write"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    PRIVILEGED_EXECUTION = "privileged_execution"


# 高风险：缺少明确授权时必须 block，审计不可用时不得降级。
HIGH_RISK_LEVELS = frozenset(
    {
        RiskLevel.DESTRUCTIVE_WRITE,
        RiskLevel.EXTERNAL_SIDE_EFFECT,
        RiskLevel.PRIVILEGED_EXECUTION,
    }
)


class EffectKind(str, Enum):
    """动作在文件系统 / 进程上留下的可观测效果，决定事后验证收集什么证据。"""

    FILE_WRITE = "file_write"
    PROCESS = "process"
    NONE = "none"


class DriverKind(str, Enum):
    """平台侧执行驱动。delegated/none 表示平台不执行，交给 Agent 运行时。"""

    FILE_EDIT = "file_edit"
    FILE_WRITE = "file_write"
    PROCESS_ARGV = "process_argv"
    SHELL_COMMAND = "shell_command"
    NONE = "none"


class RollbackMode(str, Enum):
    """回滚能力。能力不足必须显式说"不支持"，不能假装所有副作用都可撤销。"""

    NONE = "none"
    FILE_SNAPSHOT = "file_snapshot"


class ParamType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    PATH = "path"
    STRING_LIST = "string_list"


class PathKind(str, Enum):
    """path 参数指向的是什么：文件 / 目录 / 两者皆可。

    存在的理由是一个真实缺陷："等于工作区根"这一个边界被写成了"路径必须指向文件"，
    于是"工作目录 = 项目根"这种合法参数被判越界，而报错还说是参数错误。
    **文件与目录的区别是数据，不是代码里的特判**：默认 file（大多数路径参数是编辑目标），
    目录类参数（workdir / cwd）必须在注册表里显式声明 directory 才会接受根。
    """

    FILE = "file"
    DIRECTORY = "directory"
    ANY = "any"


class ApprovalMode(str, Enum):
    NONE = "none"
    REQUIRED = "required"


class AuditFailurePolicy(str, Enum):
    """审计不可写时的行为。block = 失败关闭（默认）。"""

    BLOCK = "block"
    DEGRADE = "degrade"


class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExecutionStatus(str, Enum):
    EXECUTED = "executed"       # 平台驱动确实执行了一次
    DELEGATED = "delegated"     # 允许 Agent 运行时执行（pre-execute 之后的既有语义）
    FAILED = "failed"           # 执行了但失败（非零退出、超时、部分写入）
    REFUSED = "refused"         # 未执行：绑定不一致、重复 action、权限不足


class PostStatus(str, Enum):
    VALIDATED = "validated"
    REPAIR_REQUIRED = "repair_required"
    INCONSISTENT = "inconsistent"
    NOT_REQUIRED = "not_required"


class FinalOutcome(str, Enum):
    DELIVERED = "delivered"
    BLOCKED = "blocked"
    REPAIR_REQUIRED = "repair_required"
    ROLLED_BACK = "rolled_back"
    INCONSISTENT = "inconsistent"


class AuditStage(str, Enum):
    """审计链的固定阶段（Phase 4 文档第 6 步）。顺序即链路顺序。"""

    REQUEST = "request"
    RETRIEVAL = "retrieval"
    PROPOSAL = "proposal"
    ACTION_REQUEST = "action_request"
    PRE_DECISION = "pre_decision"
    EXECUTION = "execution"
    POST_EVIDENCE = "post_evidence"
    FINAL_DECISION = "final_decision"


class ReasonCode(str, Enum):
    """显式原因码。审计与模型反馈都只认这些值，自由文本只作为 detail。"""

    ALLOW = "allow"
    ALLOW_WITH_WARNINGS = "allow_with_warnings"
    TOOL_NOT_REGISTERED = "tool_not_registered"
    SCHEMA_NOT_APPROVED = "schema_not_approved"
    PARAM_UNKNOWN = "param_unknown"
    PARAM_INVALID = "param_invalid"
    PARAM_REQUIRED_MISSING = "param_required_missing"
    PATH_OUT_OF_SCOPE = "path_out_of_scope"
    PRINCIPAL_REQUIRED = "principal_required"
    PERMISSION_DENIED = "permission_denied"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_INVALID = "approval_invalid"
    POLICY_BLOCK = "policy_block"
    POLICY_TIMEOUT = "policy_timeout"
    RATE_LIMITED = "rate_limited"
    CIRCUIT_OPEN = "circuit_open"
    AUDIT_UNAVAILABLE = "audit_unavailable"
    LEDGER_UNAVAILABLE = "ledger_unavailable"
    ACTION_EXPIRED = "action_expired"
    GRANT_INVALID = "grant_invalid"
    GRANT_EXPIRED = "grant_expired"
    GRANT_REUSED = "grant_reused"
    ACTION_REPLAY = "action_replay"
    ACTION_ID_REUSE = "action_id_reuse"
    DRIVER_UNAVAILABLE = "driver_unavailable"
    CODE_BLOCKED = "code_blocked"
    CODE_PARSE_FAILED = "code_parse_failed"
    UNGOVERNED_DECLARED = "ungoverned_declared"
    COMMAND_NOT_ALLOWLISTED = "command_not_allowlisted"
    COMMAND_COMPOSITION_BLOCKED = "command_composition_blocked"
    COMMAND_FRAGMENT_BLOCKED = "command_fragment_blocked"
    # B3：只读命令族的**读面**越界（受保护前缀 / 越出受控项目）。与 command_fragment_blocked
    # 是两件事，按 reason_code 聚合的人必须能分开读：片段清单问的是「命令文本里有没有会改变
    # 行为的片段」（--output / --ext-diff / ../），本码问的是「这次读取的目标落在读面之外吗」。
    READ_GUARD_BLOCKED = "read_guard_blocked"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_TIMEOUT = "execution_timeout"
    POST_CHECK_FAILED = "post_check_failed"
    POST_EVIDENCE_INCONSISTENT = "post_evidence_inconsistent"
    POST_ROLLED_BACK = "post_rolled_back"
    PROCESS_ERROR = "process_error"


# --------------------------------------------------------------------------- 时间与哈希


def utc_now() -> datetime:
    """当前 UTC 时间（timezone-aware）。所有时间比较都必须带时区。"""

    return datetime.now(timezone.utc)


def to_timestamp(moment: datetime) -> str:
    """RFC3339（UTC，Z 结尾）：审计与协议里唯一的时间表示。"""

    if moment.tzinfo is None:
        raise EnforcementError("时间必须带时区；拒绝把本地时间写进审计")
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    """解析 RFC3339 时间；不带时区的输入直接拒绝（否则时效判断会随机器漂移）。"""

    if not isinstance(value, str) or not value.strip():
        raise EnforcementError(f"时间必须是非空字符串，得到 {value!r}")
    text = value.strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as error:
        raise EnforcementError(f"无法解析时间 {value!r}: {error}") from error
    if moment.tzinfo is None:
        raise EnforcementError(f"时间 {value!r} 没有时区，拒绝按时效使用")
    return moment.astimezone(timezone.utc)


def canonical_json(value: Any) -> str:
    """稳定序列化：排序键、无多余空白、非 ASCII 原样保留。哈希口径只此一种。"""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def digest_of(value: Any) -> str:
    """对任意可序列化值取 sha256（带前缀），用于参数、证据与载荷关联。"""

    return "sha256:" + sha256(canonical_json(value).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- Tool Registry


class RateLimit(StrictModel):
    """限流与熔断。窗口与阈值是数据，写在注册表里，不写在代码里。"""

    max_calls: int = Field(ge=1, description="窗口内最多允许的调用次数")
    window_seconds: int = Field(ge=1)
    max_failures: int = Field(default=0, ge=0, description="0 表示不启用熔断")
    breaker_seconds: int = Field(default=0, ge=0, description="熔断保持时间")


class CodeCheckSpec(StrictModel):
    """一段"代码类参数"的结构化静态检查声明（数据，不是代码里的判断）。

    为什么需要它：`exec.run_code` 这类工具由 Agent 运行时执行（driver=none），平台既不能
    执行它、也没有事后证据，唯一的门禁曾是人工审批——审批一过就是任意代码。这里把
    "代码里不许出现的表面"写成数据，让 pre-check 能在放行之前做一次**结构性**检查。

    **它不是沙箱**：静态检查看的是语法结构，绕过的写法客观存在（拼接字符串构造名字、
    通过下标取函数、动态属性……）。known_gaps 就是把这些已知不可覆盖的形态**如实写出来**，
    并让 pre-check 把它带进审计警告，而不是让调用方以为"查过了就等于安全"。
    真正的隔离属于运行时的文件系统与进程沙箱，不在本阶段。
    """

    kind: str = Field(description="已实现的检查名，取值必须在 SUPPORTED_CODE_CHECKS 内")
    param: str = Field(min_length=1, description="承载代码文本的参数名（必须是 string 参数）")
    language: str = Field(default="python", description="代码语言；未知语言拒绝加载")
    forbidden_imports: Tuple[str, ...] = Field(
        default=(), description="禁止 import 的模块根名或完整点分名"
    )
    forbidden_calls: Tuple[str, ...] = Field(
        default=(), description="禁止以该名字直接调用（例如 open / exec / eval）"
    )
    forbidden_attributes: Tuple[str, ...] = Field(
        default=(),
        description="禁止出现的属性链前缀（例如 os 覆盖 os.system / os.popen）",
    )
    known_gaps: Tuple[str, ...] = Field(
        default=(),
        description="已知不可覆盖的绕过形态（写进审计警告，防止把结构性检查当成沙箱）",
    )

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in SUPPORTED_CODE_CHECKS:
            raise ValueError(
                f"未知代码检查 kind {value!r}；已实现的检查为 {list(SUPPORTED_CODE_CHECKS)}。"
                "声明一个没人实现的检查名等于给缺口换了一张更好看的封面，必须拒绝"
            )
        return normalized

    @field_validator("language")
    @classmethod
    def _check_language(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != "python":
            raise ValueError(
                f"未知代码语言 {value!r}：已实现的检查只解析 python（用标准库 ast），"
                "换语言必须同时换实现"
            )
        return normalized

    @field_validator("forbidden_imports", "forbidden_calls", "forbidden_attributes")
    @classmethod
    def _check_entries(cls, value: Tuple[str, ...], info: Any) -> Tuple[str, ...]:
        normalized: list[str] = []
        for item in value:
            token = str(item).strip()
            if not token:
                raise ValueError(f"{info.field_name} 不能包含空值")
            if _CODE_CHECK_ENTRY_RE.fullmatch(token) is None:
                raise ValueError(
                    f"{info.field_name} 的条目必须是模块 / 属性名"
                    f"（字母数字下划线点），得到 {item!r}"
                )
            if token in normalized:
                continue
            normalized.append(token)
        return tuple(sorted(normalized))

    @field_validator("known_gaps")
    @classmethod
    def _check_gaps(cls, value: Tuple[str, ...]) -> Tuple[str, ...]:
        """已知绕过形态是给人读的说明文字，只要求非空、去重、顺序稳定。"""

        normalized: list[str] = []
        for item in value:
            token = str(item).strip()
            if not token:
                raise ValueError("known_gaps 不能包含空条目：空条目等于没写")
            if token in normalized:
                continue
            normalized.append(token)
        return tuple(normalized)

    @property
    def has_rules(self) -> bool:
        """是否真的声明了检查项：三个禁止面全空 = 什么都没查。"""

        return bool(self.forbidden_imports or self.forbidden_calls or self.forbidden_attributes)

    @model_validator(mode="after")
    def _check_shape(self) -> "CodeCheckSpec":
        if not self.has_rules:
            raise ValueError(
                "代码检查至少要声明 forbidden_imports / forbidden_calls / "
                "forbidden_attributes 之一："
                "三个都空的检查只会解析语法，却会被当成'查过了'"
            )
        return self


class UngovernedSpec(StrictModel):
    """显式的"这条委派工具在平台上不可结构化治理"声明（降级，不是默认值，也不静默）。

    driver=none 且 effect=process 的工具（平台执行不了、只能是 Agent 运行时执行）必须
    在"结构化检查"与"这条显式降级声明"之间选一个。**没有默认值**：不写就是加载期错误，
    因为"没声明"与"声明了不可治理"必须可区分——否则 G9 会以另一种形式复现。

    声明之后并非静默通过：pre-check 会输出 governance_coverage 检查项（reason_code =
    ungoverned_declared）、写入审计，并让决策至少是 allow_with_warnings。
    """

    reason: str = Field(min_length=1, description="为什么这条工具在平台上无法被结构化检查")
    declared_by: str = Field(min_length=1, description="做出这个判断的人 / 角色")

    @field_validator("reason", "declared_by")
    @classmethod
    def _check_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("不可治理声明必须写明 reason 与 declared_by")
        return normalized


def _check_param_default(spec: "ParamSpec") -> None:
    """校验 `default`：类型必须与参数声明一致，且**已经满足**声明的约束。

    默认值会作为审批「参数域」参与匹配（1.3），所以它必须是**可以拿来比对的规范形态**：
    类型不符、越界（max_chars / pattern / enum）、路径不是工作区相对路径，一律在加载期拒绝。
    宁可让注册表加载失败，也不让一个"看起来能用"的默认值悄悄变成匹配依据。
    """

    name = spec.name
    value = spec.default
    if spec.required:
        raise ValueError(
            f"{name}: required=True 与 default 自相矛盾——"
            "有默认值就意味着它可以不出现；要给它默认值请去掉 required"
        )
    if spec.type is ParamType.STRING_LIST:
        raise ValueError(
            f"{name}: string_list 参数不得声明 default——"
            "审批模式只支持字符串 / 整数 / 布尔，列表类默认值无法参与整串匹配"
        )
    if spec.type is ParamType.STRING:
        if not isinstance(value, str):
            raise ValueError(
                f"{name}: default 必须是字符串，得到 {type(value).__name__}"
            )
    elif spec.type is ParamType.PATH:
        if not isinstance(value, str):
            raise ValueError(f"{name}: default 必须是路径字符串，得到 {type(value).__name__}")
        candidate = value.strip()
        if not candidate:
            raise ValueError(f"{name}: default 不得为空字符串")
        if candidate != value:
            raise ValueError(f"{name}: default 不得带首尾空白（它要参与逐字匹配）")
        if "\\" in value or "/./" in value or value.startswith("./"):
            raise ValueError(
                f"{name}: default 必须是规范形态：用 '/' 分隔、不带 './' 前缀，得到 {value!r}"
            )
        if re.match(r"^[A-Za-z]:", value) or value.startswith(("/", "\\")):
            raise ValueError(f"{name}: default 必须是工作区相对路径，得到绝对路径 {value!r}")
        if any(part == ".." for part in value.split("/")):
            raise ValueError(f"{name}: default 不得包含 '..'：默认值不能越出工作区，得到 {value!r}")
    elif spec.type is ParamType.INTEGER:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name}: default 必须是整数，得到 {value!r}")
    elif spec.type is ParamType.BOOLEAN:
        if not isinstance(value, bool):
            raise ValueError(f"{name}: default 必须是布尔值，得到 {value!r}")
    if isinstance(value, str):
        if spec.max_chars is not None and len(value) > spec.max_chars:
            raise ValueError(
                f"{name}: default 长度 {len(value)} 超过声明的 max_chars={spec.max_chars}"
            )
        if spec.pattern is not None and re.fullmatch(spec.pattern, value) is None:
            raise ValueError(
                f"{name}: default 不匹配声明的 pattern {spec.pattern!r}（整串匹配）"
            )
        if spec.enum and value not in spec.enum:
            raise ValueError(f"{name}: default 取值 {value!r} 不在声明的 enum {list(spec.enum)} 内")


class ParamSpec(StrictModel):
    """一个参数的允许形态。未声明的参数一律拒绝（allowlist，不是 denylist）。"""

    name: str = Field(min_length=1)
    type: ParamType
    required: bool = False
    description: str = ""
    max_chars: Optional[int] = Field(default=None, ge=1)
    max_items: Optional[int] = Field(default=None, ge=1)
    max_item_chars: Optional[int] = Field(default=None, ge=1)
    pattern: Optional[str] = Field(default=None, description="整串匹配的正则（re.fullmatch）")
    enum: Tuple[str, ...] = ()
    path_scope: Optional[str] = Field(
        default=None, description="path 类型的作用域：workspace 表示必须落在工作区内"
    )
    path_kind: PathKind = Field(
        default=PathKind.FILE,
        description="path 类型指向什么：file（默认）拒绝等于工作区根的路径，"
        "directory 把根归一化为 .，any 两者都接受",
    )
    blocked_prefixes: Tuple[str, ...] = Field(
        default=(),
        description="path 类型禁止触达的工作区相对路径前缀；pre-check 与驱动都会校验",
    )
    escalating_values: Tuple[str, ...] = Field(
        default=(), description="这些取值会额外要求 requires_permission（参数绑定授权）"
    )
    requires_permission: Optional[str] = Field(
        default=None, description="出现 escalating_values 时必须具备的额外权限"
    )
    secret: bool = Field(default=False, description="值不进审计，只留摘要")
    default: Any = Field(
        default=None,
        description=(
            "可选参数的默认值（审批协议 1.3 的「参数域」按它补齐后再匹配）。"
            "null = 没有默认值：此时审批条子必须逐格声明这个参数。"
            "**只参与审批匹配，不改变执行**：驱动层读取参数的缺省行为一字未动"
            "（open-work 5.11「声明了却不执行」仍是未修项，默认值不是它的修复）"
        ),
    )

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        normalized = value.strip()
        if not _SAFE_ID_RE.match(normalized):
            raise ValueError(f"参数名必须是稳定标识符（字母/数字/._:-），得到 {value!r}")
        return normalized

    @field_validator("pattern")
    @classmethod
    def _check_pattern(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        try:
            re.compile(value)
        except re.error as error:
            raise ValueError(f"参数 {value!r} 的正则不合法: {error}") from error
        return value

    @field_validator("enum", "escalating_values")
    @classmethod
    def _check_unique(cls, value: Tuple[str, ...]) -> Tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("枚举值不得重复")
        return value

    @field_validator("blocked_prefixes")
    @classmethod
    def _check_blocked_prefixes(cls, value: Tuple[str, ...]) -> Tuple[str, ...]:
        # 与读面闸门（read_guard.forbidden_path_prefixes）共用同一条规范化口径与同一段实现：
        # 「受控项目内相对路径」这条规则只能有一个版本，否则两处会各自漂出一个可接受形态。
        return _normalize_relative_prefixes(value, what="禁止路径前缀")

    @model_validator(mode="after")
    def _check_shape(self) -> "ParamSpec":
        if self.default is not None:
            _check_param_default(self)
        if self.type is ParamType.STRING_LIST:
            if self.max_items is None:
                raise ValueError(f"{self.name}: string_list 必须声明 max_items（否则等于不设上限）")
        elif self.max_items is not None or self.max_item_chars is not None:
            raise ValueError(f"{self.name}: max_items/max_item_chars 只适用于 string_list")
        if self.type is ParamType.PATH and self.path_scope not in (None, "workspace"):
            raise ValueError(f"{self.name}: path_scope 只支持 workspace 或省略")
        if self.type is not ParamType.PATH and self.path_kind is not PathKind.FILE:
            raise ValueError(
                f"{self.name}: path_kind 只适用于 path 参数；"
                "在别的类型上声明目录语义会被静默忽略，因此直接拒绝"
            )
        if self.blocked_prefixes and self.type is not ParamType.PATH:
            raise ValueError(f"{self.name}: blocked_prefixes 只适用于 path 参数")
        if self.type not in (ParamType.STRING, ParamType.PATH) and (
            self.pattern is not None or self.max_chars is not None or self.enum
        ):
            # action._check_constraints 只对字符串取值生效：声明在 integer / boolean /
            # string_list 上的 pattern / max_chars / enum 会被**静默跳过**。
            # 与上面几条同一口径：会被忽略的声明直接拒绝，而不是"接受了但不执行"。
            # （string_list 的长度约束走 max_items / max_item_chars，它们有自己的校验。）
            raise ValueError(
                f"{self.name}: pattern / max_chars / enum 只适用于 string 与 path 参数，"
                f"当前类型是 {self.type.value}；在它上面声明这些约束会被静默跳过"
            )
        if self.escalating_values and not self.requires_permission:
            raise ValueError(
                f"{self.name}: 声明了 escalating_values 就必须声明 requires_permission，"
                "否则“提权”这件事无法被校验"
            )
        if self.requires_permission and not self.escalating_values:
            raise ValueError(f"{self.name}: requires_permission 只在 escalating_values 出现时生效")
        return self


class CommandFamily(StrictModel):
    """注册表声明的一个「命令族」：一组**同一种用途**的允许命令形态。

    族是**数据**，不是代码里的分类：`approve --family` 只按这里声明的模式签发条子，
    `tools/approval_allowlist_audit.py --check` 把族与 `allowed_commands` 做双向比对。

    这里**不**强制"族的模式必须落在 allowed_commands 里"：一致性由那台仪器判，
    在加载期强制只会让它永远绿（AGENTS 第 45 条）。加载期只保证族的形状可读：
    id 稳定且不重复、至少一条模式、每条模式都是可编译的正则。
    """

    id: str = Field(min_length=1)
    title: str = ""
    patterns: Tuple[str, ...] = Field(min_length=1, description="这一族覆盖的 allowed_commands 模式")

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        normalized = value.strip()
        if not _SAFE_ID_RE.match(normalized):
            raise ValueError(f"命令族 ID 必须是稳定标识符（字母/数字/._:-），得到 {value!r}")
        return normalized

    @field_validator("patterns")
    @classmethod
    def _check_patterns(cls, value: Tuple[str, ...]) -> Tuple[str, ...]:
        cleaned: list[str] = []
        for pattern in value:
            text = str(pattern).strip()
            if not text:
                raise ValueError("命令族的模式不能为空")
            try:
                re.compile(text)
            except re.error as error:
                raise ValueError(f"命令族的正则不合法 {text!r}: {error}") from error
            if text in cleaned:
                raise ValueError(f"命令族出现重复模式 {text!r}")
            cleaned.append(text)
        return tuple(cleaned)


# 受保护前缀的规范形态只认这一种口径：用 "/" 分隔、不带 "./" 或首尾斜杠、不含 ".." 或空段、
# 字符集受控。写路径（blocked_prefixes）与读面（read_guard）共用它——两处表达的是同一条
# 「受控项目内相对路径」的规则，各写一份就会漂。
_PREFIX_CHARS_RE = re.compile(r"[A-Za-z0-9._/-]+")


def _normalize_relative_prefixes(value: Tuple[str, ...], *, what: str) -> Tuple[str, ...]:
    """把一组「受控项目内相对路径前缀」规范化并校验；不合法一律加载期报错。"""

    normalized: list[str] = []
    for item in value:
        text = str(item).replace("\\", "/")
        if text.startswith("/"):
            # 前导斜杠有两种读法（"绝对路径" / "写顺手了"），代码不该替作者选一种：
            # 静默 strip 会让 "/etc" 变成受控项目里的 "etc"——声明说的与执行的不是一件事。
            raise ValueError(
                f"{what}必须是受控项目内的相对路径（不要以 / 开头），得到 {item!r}"
            )
        prefix = text.strip("/")
        parts = prefix.split("/")
        if not prefix or any(part in ("", ".", "..") for part in parts):
            raise ValueError(f"{what}必须是规范的工作区相对路径，得到 {item!r}")
        if _PREFIX_CHARS_RE.fullmatch(prefix) is None:
            raise ValueError(f"{what}含不受控字符，得到 {item!r}")
        normalized.append(prefix)
    if len({item.casefold() for item in normalized}) != len(normalized):
        raise ValueError(f"{what}不得重复（忽略大小写）")
    return tuple(normalized)


class ReadGuardSpec(StrictModel):
    """只读命令族的**读面**闸门声明（注册表 1.2 起，逐工具可选）。

    存在的理由（04 号 5.70）：写类参数走 `policy.context.repo_relative_path` 的范围校验，
    **命令文本里的路径操作数不走那一层**——`git show HEAD:.policy/approval.json`、
    `git log -p -- .policy/audit.jsonl` 完整匹配命令白名单，于是能读到信任根（审批条子与
    审计账本）。这一个字段把「读面的边界」写成数据：哪些命令族算读面、认哪些操作数形态、
    哪些前缀受保护、哪些形态算越界。

    **它是结构性检查，不是沙箱**：只认下面声明的操作数形态，选项取值、路径里带空格且被
    引号包裹、Windows 短名等写法不在承诺范围内；真正的隔离仍属于运行时的文件系统沙箱
    （AGENTS 第 17 条末句）。

    四个字段都**必填且不得为空集合**：只声明一半的闸门（例如只有前缀、没有越界形态）看起来
    像门，实际放走的正是另一半——"声明了但什么都没查"比不声明更糟（第 45 条）。
    """

    families: Tuple[str, ...] = Field(
        min_length=1,
        description="这条闸门适用的命令族 ID：必须在本工具的 command_families 里已声明。"
        "点名一个不存在的族，等于给一份没人读的声明发了一张通行证",
    )
    path_forms: Tuple[str, ...] = Field(
        min_length=1,
        description=f"命令文本里认哪些路径操作数形态；取值必须在 {list(READ_PATH_FORMS)} 内",
    )
    forbidden_path_prefixes: Tuple[str, ...] = Field(
        min_length=1,
        description="受保护的受控项目相对路径前缀（信任根，例如 .policy）：归一化后落在其下即阻断",
    )
    forbidden_forms: Tuple[str, ...] = Field(
        min_length=1,
        description=f"读面越界形态；取值必须在 {list(READ_FORBIDDEN_FORMS)} 内",
    )

    @field_validator("families")
    @classmethod
    def _check_families(cls, value: Tuple[str, ...]) -> Tuple[str, ...]:
        cleaned: list[str] = []
        for item in value:
            normalized = str(item).strip()
            if _SAFE_ID_RE.match(normalized) is None:
                raise ValueError(f"read_guard.families 必须是命令族 ID（稳定标识符），得到 {item!r}")
            if normalized in cleaned:
                raise ValueError(f"read_guard.families 出现重复族 {normalized!r}")
            cleaned.append(normalized)
        return tuple(cleaned)

    @field_validator("path_forms", "forbidden_forms")
    @classmethod
    def _check_forms(cls, value: Tuple[str, ...], info) -> Tuple[str, ...]:
        allowed = READ_PATH_FORMS if info.field_name == "path_forms" else READ_FORBIDDEN_FORMS
        cleaned: list[str] = []
        for item in value:
            normalized = str(item).strip()
            if normalized not in allowed:
                raise ValueError(
                    f"read_guard.{info.field_name} 出现未知形态 {item!r}；"
                    f"已实现的形态为 {list(allowed)}。换一种形态是代码工作，不是数据改动"
                )
            if normalized in cleaned:
                raise ValueError(f"read_guard.{info.field_name} 出现重复形态 {normalized!r}")
            cleaned.append(normalized)
        return tuple(cleaned)

    @field_validator("forbidden_path_prefixes")
    @classmethod
    def _check_prefixes(cls, value: Tuple[str, ...]) -> Tuple[str, ...]:
        return _normalize_relative_prefixes(value, what="read_guard.forbidden_path_prefixes")

class ToolSpec(StrictModel):
    """一个工具的被审核描述。schema_hash 覆盖全部字段，任何改动都会让哈希变化。"""

    id: str = Field(min_length=1, description="稳定 ID，例如 fs.edit")
    title: str = Field(min_length=1)
    agent: str = Field(min_length=1, description="工具所属 Agent，例如 dsh")
    tool_name: str = Field(min_length=1, description="Agent 侧工具名，例如 edit")
    schema_version: str = Field(min_length=1)
    risk: RiskLevel
    effect: EffectKind
    driver: DriverKind
    parameters: Tuple[ParamSpec, ...] = ()
    required_permissions: Tuple[str, ...] = ()
    approval: ApprovalMode = ApprovalMode.NONE
    post_checks: Tuple[str, ...] = ()
    code_check: Optional[CodeCheckSpec] = Field(
        default=None,
        description="代码类参数的结构化静态检查；driver=none 的进程类工具必须声明它，"
        "或显式声明 ungoverned（二者必居其一，没有默认值）",
    )
    ungoverned: Optional[UngovernedSpec] = Field(
        default=None,
        description="显式降级声明：这条委派工具在平台上不可结构化治理（进审计，不静默）",
    )
    timeout_ms: int = Field(default=5000, ge=1)
    rollback: RollbackMode = RollbackMode.NONE
    rate_limit: Optional[RateLimit] = None
    allowed_commands: Tuple[str, ...] = ()
    forbidden_command_fragments: Tuple[str, ...] = Field(
        default=(),
        description="命令文本里出现这些片段就结构性阻断：白名单正则描述的是「命令长什么样」，"
        "描述不了「这个选项会干什么」（例如 git diff --output 会写任意路径）",
    )
    command_param: Optional[str] = Field(
        default=None,
        description="shell_command 驱动里承载命令文本的参数名；allowlist 检查认这个参数",
    )
    shell: Tuple[str, ...] = Field(
        default=(),
        description="shell_command 驱动解析命令时使用的前缀（argv 形式，永不经过 shell 解析）",
    )
    command_families: Tuple[CommandFamily, ...] = Field(
        default=(),
        description="命令族数据（注册表 1.1 起）：按用途分组的 allowed_commands 模式。"
        "它是**授权面数据**（进 schema_hash）：「approve --family」只从这里取模式，"
        "「approval_allowlist_audit --check」把它与 allowed_commands 双向比对。"
        "省略 = 该工具没有族数据（旧注册表照常加载）。",
    )
    read_guard: Optional[ReadGuardSpec] = Field(
        default=None,
        description="读面闸门（注册表 1.2 起）：只读命令族的路径操作数边界。"
        "省略 = 该工具不做读面检查（旧注册表 1.0 / 1.1 照常加载），"
        "**但一旦声明就必须完整**（四个字段都必填、都不得为空集合）。"
        "它进 schema_hash：读面边界是被审核数据，改一个字都要重新 approve。",
    )
    audit_failure: AuditFailurePolicy = AuditFailurePolicy.BLOCK
    notes: str = ""

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        normalized = value.strip()
        if not _SAFE_ID_RE.match(normalized):
            raise ValueError(f"工具 ID 必须是稳定标识符（字母/数字/._:-），得到 {value!r}")
        return normalized

    @field_validator("tool_name", "agent")
    @classmethod
    def _check_token(cls, value: str) -> str:
        normalized = value.strip()
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", normalized):
            raise ValueError(f"必须是稳定标识符，得到 {value!r}")
        return normalized

    @field_validator("allowed_commands")
    @classmethod
    def _check_commands(cls, value: Tuple[str, ...]) -> Tuple[str, ...]:
        for pattern in value:
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f"allowed_commands 里的正则不合法 {pattern!r}: {error}") from error
        return value

    @field_validator("parameters")
    @classmethod
    def _check_unique_params(cls, value: Tuple[ParamSpec, ...]) -> Tuple[ParamSpec, ...]:
        names = [item.name for item in value]
        if len(set(names)) != len(names):
            duplicates = sorted({name for name in names if names.count(name) > 1})
            raise ValueError(f"参数名重复：{duplicates}")
        return tuple(sorted(value, key=lambda item: item.name))

    @model_validator(mode="after")
    def _check_invariants(self) -> "ToolSpec":
        high_risk = self.risk in HIGH_RISK_LEVELS
        if high_risk and self.approval is not ApprovalMode.REQUIRED:
            raise ValueError(
                f"{self.id}: risk={self.risk.value} 属于高风险动作，必须 approval=required"
                "（缺少明确授权时不得执行）"
            )
        if self.driver is DriverKind.SHELL_COMMAND and not self.allowed_commands:
            raise ValueError(
                f"{self.id}: shell_command 驱动必须声明 allowed_commands；"
                "没有命令白名单的 shell 等于没有治理"
            )
        if self.allowed_commands and self.driver is not DriverKind.SHELL_COMMAND:
            raise ValueError(f"{self.id}: allowed_commands 只适用于 shell_command 驱动")
        if self.forbidden_command_fragments and self.driver is not DriverKind.SHELL_COMMAND:
            raise ValueError(
                f"{self.id}: forbidden_command_fragments 只适用于 shell_command 驱动"
            )
        if self.driver is DriverKind.SHELL_COMMAND and not self.shell:
            raise ValueError(
                f"{self.id}: shell_command 驱动必须声明 shell 前缀（argv 形式），"
                "否则命令由谁解释就不确定了"
            )
        if self.driver is not DriverKind.SHELL_COMMAND and self.shell:
            raise ValueError(f"{self.id}: shell 前缀只适用于 shell_command 驱动")
        if self.driver is DriverKind.SHELL_COMMAND and not self.command_param:
            raise ValueError(
                f"{self.id}: shell_command 驱动必须声明 command_param（命令文本所在参数），"
                "否则白名单检查不知道要看哪个值"
            )
        if self.command_param is not None:
            if self.driver is not DriverKind.SHELL_COMMAND:
                raise ValueError(f"{self.id}: command_param 只适用于 shell_command 驱动")
            carrier = self.parameter(self.command_param)
            if carrier is None:
                raise ValueError(
                    f"{self.id}: command_param={self.command_param!r} 不是已声明的参数"
                )
            if carrier.type is not ParamType.STRING:
                # 与 code_check.param 同一口径：命令文本是字符串。指向 string_list / integer
                # 时，pre-check 拿到的不是 str，于是把它当成空串，组合与被禁片段检查直接报
                # PASSED——注册表里打错一个字，结构性阻断整条失效（失败打开）。
                raise ValueError(
                    f"{self.id}: command_param={carrier.name!r} 必须是 string 参数，"
                    f"得到 {carrier.type.value}：命令文本是字符串，"
                    "指向别的类型会让组合/被禁片段检查读到非字符串并被静默当成空串"
                )
        unknown_checks = [item for item in self.post_checks if item not in SUPPORTED_POST_CHECKS]
        if unknown_checks:
            raise ValueError(
                f"{self.id}: 未知 post_check {unknown_checks}；"
                f"内置验证器为 {list(SUPPORTED_POST_CHECKS)}"
            )
        if self.rollback is RollbackMode.FILE_SNAPSHOT and self.effect is not EffectKind.FILE_WRITE:
            raise ValueError(f"{self.id}: file_snapshot 回滚只适用于 effect=file_write")
        if self.risk is RiskLevel.READ_ONLY and self.effect is not EffectKind.NONE:
            raise ValueError(f"{self.id}: read_only 的动作不得声明写效果")
        if (
            self.audit_failure is AuditFailurePolicy.DEGRADE
            and self.risk is not RiskLevel.READ_ONLY
        ):
            raise ValueError(
                f"{self.id}: audit_failure=degrade 只允许只读工具使用；"
                "任何会产生副作用的动作都必须在审计不可写时失败关闭"
            )
        if self.code_check is not None and self.ungoverned is not None:
            raise ValueError(
                f"{self.id}: code_check 与 ungoverned 不得同时声明——"
                "要么给它加检查，要么如实说它不可治理，两者都写等于自相矛盾"
            )
        if self.code_check is not None:
            carrier = self.parameter(self.code_check.param)
            if carrier is None:
                raise ValueError(
                    f"{self.id}: code_check.param={self.code_check.param!r} 不是已声明的参数；"
                    "检查一个不存在的参数等于什么都没查"
                )
            if carrier.type is not ParamType.STRING:
                raise ValueError(
                    f"{self.id}: code_check.param={carrier.name!r} 必须是 string 参数，"
                    f"得到 {carrier.type.value}：静态检查只解析文本"
                )
        if self.ungoverned is not None and not self.is_delegated_process:
            raise ValueError(
                f"{self.id}: ungoverned 只适用于 driver=none 且 effect=process 的委派工具；"
                "平台真正执行的工具必须走驱动与 post_checks，不得用一句声明换掉门禁"
            )
        if self.command_families:
            if self.driver is not DriverKind.SHELL_COMMAND:
                raise ValueError(
                    f"{self.id}: command_families 只适用于 shell_command 驱动："
                    "别的工具没有命令白名单，族数据会变成一份没人读的声明"
                )
            if not self.allowed_commands:
                raise ValueError(
                    f"{self.id}: 声明了 command_families 却没有 allowed_commands——"
                    "族只能给白名单分组，不能凭空造出允许的命令"
                )
            ids = [item.id for item in self.command_families]
            duplicates = sorted({item for item in ids if ids.count(item) > 1})
            if duplicates:
                raise ValueError(f"{self.id}: 命令族 ID 重复：{duplicates}")
        if self.is_delegated_process and self.code_check is None and self.ungoverned is None:
            raise ValueError(
                f"{self.id}: driver=none 且 effect=process 的委派工具必须**显式**声明"
                "「结构化检查」(code_check) 或「不可治理」(ungoverned) 之一——"
                "没有默认值：平台执行不了它、也没有事后证据，缺了这条声明就只剩审批一道门，"
                "而审批一过就是任意代码（G9）。声明不可治理也不是静默通过：pre-check 会输出 "
                "governance_coverage=ungoverned_declared 并写进审计"
            )
        if self.read_guard is not None:
            # 与 command_families 同一套门槛：读面闸门只对「有命令白名单的 shell 命令」有意义。
            # 声明在没有命令文本的工具上，等于把一条永远不会执行的规则写进授权表。
            if self.driver is not DriverKind.SHELL_COMMAND:
                raise ValueError(
                    f"{self.id}: read_guard 只适用于 shell_command 驱动：别的工具没有命令文本，"
                    "声明了也永远不会被执行，只会把缺口藏进更完整的声明里"
                )
            declared_families = {family.id for family in self.command_families}
            if not declared_families:
                raise ValueError(
                    f"{self.id}: 声明了 read_guard 却没有 command_families——"
                    "读面闸门按**命令族**生效，没有族就没有可生效的范围"
                )
            unknown_families = sorted(set(self.read_guard.families) - declared_families)
            if unknown_families:
                raise ValueError(
                    f"{self.id}: read_guard.families 点名了未声明的命令族 {unknown_families}；"
                    f"已声明的族为 {sorted(declared_families)}——"
                    "点名一个不存在的族，等于这道闸门永远不会触发"
                )
        return self

    def parameter(self, name: str) -> Optional[ParamSpec]:
        for spec in self.parameters:
            if spec.name == name:
                return spec
        return None

    def param_defaults(self) -> dict[str, Any]:
        """可选参数的默认值（参数名 → 值）：审批协议 1.3「参数域」的**唯一**来源。

        只收 `default is not None` 的参数：没有默认值的参数不进这里，
        于是"请求里出现未声明且无默认值的参数"仍然拒（参数域放宽的边界）。
        这个方法只是把数据取出来，不改变任何执行行为。
        """

        return {item.name: item.default for item in self.parameters if item.default is not None}

    def command_family(self, family_id: str) -> Optional[CommandFamily]:
        """按 ID 取一个命令族；没有就是 None（调用方据此报"这个工具没有这一族"）。"""

        for family in self.command_families:
            if family.id == family_id:
                return family
        return None

    @property
    def schema_hash(self) -> str:
        """被审核的工具描述哈希：覆盖身份、schema 版本、参数表、权限与执行语义。"""

        return digest_of(self.approved_payload())

    def approved_payload(self) -> dict[str, Any]:
        """参与审核哈希的规范化载荷（不含 notes 之外的运行时无关内容）。"""

        payload = json.loads(self.model_dump_json(exclude={"notes"}))
        return payload

    @property
    def is_high_risk(self) -> bool:
        return self.risk in HIGH_RISK_LEVELS

    @property
    def is_delegated_process(self) -> bool:
        """平台不执行、但会在进程上留下效果的工具（例如 run_code / bash 类委派工具）。

        它们的共同缺口是"平台既执行不了、也拿不到事后证据"，因此必须有第二道闸。
        """

        return self.driver is DriverKind.NONE and self.effect is EffectKind.PROCESS


# --------------------------------------------------------------------------- Action Request


ParamValueValue = Union[str, int, bool, Tuple[str, ...]]


class ParamValue(StrictModel):
    """规范化后的单个参数值。原文可能含敏感内容，因此审计只留摘要。"""

    name: str = Field(min_length=1)
    type: ParamType
    value: ParamValueValue
    chars: int = Field(ge=0)
    digest: str
    secret: bool = False

    def canonical(self) -> Any:
        return list(self.value) if isinstance(self.value, tuple) else self.value

    def display(self) -> str:
        """可进审计 / 反馈的表示：secret 参数只留摘要，其余保留原文。"""

        if self.secret:
            return f"<secret {self.digest[:22]}...>"
        if isinstance(self.value, tuple):
            return ", ".join(self.value)
        if isinstance(self.value, bool):
            return "true" if self.value else "false"
        return str(self.value)


_ACTION_HASH_FIELDS = (
    "schema_version",
    "action_id",
    "request_id",
    "trace_id",
    "agent",
    "agent_version",
    "tool_id",
    "tool_name",
    "tool_schema_version",
    "tool_schema_hash",
    "risk",
    "effect",
    "driver",
    "subject",
    "roles",
    "permissions",
    "context_digest",
    "workspace",
)


class ActionRequest(StrictModel):
    """不可变动作请求：工具身份 + schema 哈希 + 规范化参数 + 主体 + 上下文摘要。

    action_hash 覆盖上述全部内容；任何一处变化都会让旧授权失效。
    """

    schema_version: EnforcementVersion = ENFORCEMENT_SCHEMA_VERSION
    action_id: str = Field(min_length=1, description="幂等键：同一 action 重试必须复用")
    request_id: str = Field(min_length=1)
    trace_id: Optional[str] = None
    agent: str = Field(min_length=1)
    agent_version: Optional[str] = None
    tool_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    tool_schema_version: str = Field(min_length=1)
    tool_schema_hash: str = Field(min_length=1)
    risk: RiskLevel
    effect: EffectKind
    driver: DriverKind
    params: Tuple[ParamValue, ...] = ()
    param_digest: str
    subject: Optional[str] = None
    roles: Tuple[str, ...] = ()
    permissions: Tuple[str, ...] = ()
    context_digest: str
    workspace: Optional[str] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    action_hash: str = ""

    @field_validator("params")
    @classmethod
    def _check_param_order(cls, value: Tuple[ParamValue, ...]) -> Tuple[ParamValue, ...]:
        names = [item.name for item in value]
        if len(set(names)) != len(names):
            raise ValueError(
                "参数名不得重复：param() / value_of() 取首个匹配，而 action_hash 的载荷"
                "由字典推导得出（last-wins），同一个请求会在「授权时哈希」与「执行时取值」"
                "上指向两个不同的值——参数绑定授权会因此静默失效"
            )
        if names != sorted(names):
            return tuple(sorted(value, key=lambda item: item.name))
        return value

    @model_validator(mode="after")
    def _check_hash(self) -> "ActionRequest":
        # param_digest 不在 action_hash 的 material 里（并进去会让在途授权与已存哈希全部
        # 失效，是协议级变更），但它必须**与规范化参数一致**：它是审计里"这次到底传了什么"
        # 的摘要，失配说明这份载荷被改过或字段是编的——构造期就拒绝，不让它作为"没人核的
        # 装饰"被记进审计。同一个请求文档因此不可能带着一个描述别的参数的摘要通过校验。
        expected_param_digest = digest_of(
            {item.name: item.canonical() for item in self.params}
        )
        if self.param_digest != expected_param_digest:
            raise ValueError(
                "param_digest 与规范化参数不一致：摘要必须能由 params 复算出来"
                f"（期望 {expected_param_digest}，得到 {self.param_digest!r}）"
            )
        expected = self.compute_action_hash()
        if not self.action_hash:
            object.__setattr__(self, "action_hash", expected)
        elif self.action_hash != expected:
            raise ValueError(
                "action_hash 与请求内容不一致：请求被改动过，或哈希口径变了。"
                "拒绝在无法解释的动作上授权"
            )
        return self

    def hash_payload(self) -> dict[str, Any]:
        """参与 action_hash 的规范化载荷。"""

        payload = {name: getattr(self, name) for name in _ACTION_HASH_FIELDS}
        payload["roles"] = sorted(self.roles)
        payload["permissions"] = sorted(self.permissions)
        payload["params"] = {item.name: item.canonical() for item in self.params}
        return json.loads(json.dumps(payload, default=str))

    def compute_action_hash(self) -> str:
        return digest_of(self.hash_payload())

    def param(self, name: str) -> Optional[ParamValue]:
        for item in self.params:
            if item.name == name:
                return item
        return None

    def value_of(self, name: str, default: Any = None) -> Any:
        item = self.param(name)
        if item is None:
            return default
        if isinstance(item.value, tuple):
            return list(item.value)
        return item.value

    @property
    def idempotency_key(self) -> str:
        return f"{self.agent}:{self.tool_id}:{self.action_id}"


class PolicySummary(StrictModel):
    """Phase 1 决策载荷在受控执行链里的只读摘要（含完整协议载荷以便重放）。"""

    decision: Decision
    request_id: str
    matched_rules: Tuple[str, ...] = ()
    violations: Tuple[Violation, ...] = ()
    payload: Optional[Mapping[str, Any]] = None

    @classmethod
    def from_validation_result(cls, result: ValidationResult) -> "PolicySummary":
        return cls(
            decision=result.decision,
            request_id=result.request_id,
            matched_rules=result.matched_rules,
            violations=result.violations,
            payload=result.to_decision_dict(),
        )


class CheckResult(StrictModel):
    """Pre-execute 的一项检查结论。checks 必须齐全，缺项按协议错误处理。"""

    check: str = Field(min_length=1)
    status: CheckStatus
    reason_code: ReasonCode
    detail: str = ""


class AuthorizationGrant(StrictModel):
    """短时效、单次使用、与 action_hash 绑定的允许凭据。

    执行器只认这一张凭据：它不解析自然语言批准，也不接受"模型说可以"。
    """

    schema_version: EnforcementVersion = ENFORCEMENT_SCHEMA_VERSION
    grant_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    action_hash: str = Field(min_length=1)
    tool_id: str = Field(min_length=1)
    tool_schema_hash: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    permissions: Tuple[str, ...] = ()
    risk: RiskLevel
    issued_at: datetime
    expires_at: datetime
    single_use: bool = True
    nonce: str = Field(min_length=1, description="每次授权唯一，用于单次使用台账")

    @model_validator(mode="after")
    def _check_window(self) -> "AuthorizationGrant":
        if self.expires_at <= self.issued_at:
            raise ValueError("授权有效期必须为正；过期时间不得早于签发时间")
        return self

    def verify(
        self,
        request: ActionRequest,
        *,
        now: datetime,
        used: bool = False,
        max_ttl_seconds: Optional[int] = None,
    ) -> None:
        """校验凭据与当前动作完全一致；任何不符都抛 GrantError（失败关闭）。"""

        if self.action_hash != request.action_hash:
            raise GrantError(
                "授权绑定的 action_hash 与当前动作不一致："
                "参数、主体、schema 或上下文已经变化，旧决定不得复用",
                reason_code=ReasonCode.GRANT_INVALID.value,
            )
        if self.action_id != request.action_id:
            raise GrantError(
                "授权绑定的 action_id 与当前动作不一致",
                reason_code=ReasonCode.GRANT_INVALID.value,
            )
        if self.tool_id != request.tool_id:
            raise GrantError(
                "授权绑定的工具与当前动作不一致", reason_code=ReasonCode.GRANT_INVALID.value
            )
        if self.tool_schema_hash != request.tool_schema_hash:
            raise GrantError(
                "工具 schema 已变化（可能升级过 Agent），授权立即失效",
                reason_code=ReasonCode.GRANT_INVALID.value,
            )
        if request.subject is None or self.subject != request.subject:
            raise GrantError(
                "授权主体与当前请求主体不一致：授权不可跨主体复用",
                reason_code=ReasonCode.GRANT_INVALID.value,
            )
        if now >= self.expires_at:
            raise GrantError(
                f"授权已过期（{to_timestamp(self.expires_at)}）：必须重新走 pre-check",
                reason_code=ReasonCode.GRANT_EXPIRED.value,
            )
        if now < self.issued_at - timedelta(seconds=5):
            raise GrantError(
                "授权签发时间在未来：时钟或凭据不可信，拒绝执行",
                reason_code=ReasonCode.GRANT_INVALID.value,
            )
        if max_ttl_seconds is not None:
            ttl = (self.expires_at - self.issued_at).total_seconds()
            if ttl > max_ttl_seconds:
                raise GrantError(
                    f"授权有效期 {ttl:g}s 超过上限 {max_ttl_seconds}s：允许结果必须是短时效的",
                    reason_code=ReasonCode.GRANT_INVALID.value,
                )
        if used and self.single_use:
            raise GrantError(
                "授权已被使用：单次授权不得重复消费",
                reason_code=ReasonCode.GRANT_REUSED.value,
            )


class PreDecision(StrictModel):
    """执行前决策：决定 + 全部检查项 + （允许时的）授权凭据。"""

    schema_version: EnforcementVersion = ENFORCEMENT_SCHEMA_VERSION
    decision: Decision
    reason_code: ReasonCode
    action_id: str
    request_id: str
    trace_id: Optional[str] = None
    action_hash: str
    tool_id: str
    tool_name: str
    risk: RiskLevel
    checks: Tuple[CheckResult, ...] = ()
    grant: Optional[AuthorizationGrant] = None
    required_action: Optional[RequiredAction] = None
    policy: Optional[PolicySummary] = None
    evaluated_at: datetime
    expires_at: Optional[datetime] = None
    dry_run: bool = Field(
        default=False,
        description="只做决策、不占用 action_id 也不签发可用授权（CLI precheck 的语义）",
    )

    @model_validator(mode="after")
    def _grant_matches_decision(self) -> "PreDecision":
        if self.dry_run:
            # dry-run 的 allow 只是"如果现在执行会被允许"，不是授权：不得携带凭据。
            if self.grant is not None:
                raise ValueError("dry-run 决策不得携带授权凭据（它不是一次授权）")
            return self
        if self.decision is Decision.BLOCK:
            if self.grant is not None:
                raise ValueError("block 决策不得携带授权凭据")
        else:
            if self.grant is None:
                raise ValueError("allow / allow_with_warnings 必须携带与动作绑定的授权凭据")
            if self.grant.action_hash != self.action_hash:
                raise ValueError("授权的 action_hash 与决策不一致")
        return self

    @property
    def allowed(self) -> bool:
        return self.decision is not Decision.BLOCK

    def check(self, name: str) -> Optional[CheckResult]:
        for item in self.checks:
            if item.check == name:
                return item
        return None

    def to_decision_dict(self) -> dict[str, Any]:
        return json.loads(self.model_dump_json())

    @classmethod
    def from_decision_dict(cls, payload: Mapping[str, Any]) -> "PreDecision":
        return parse_pre_decision(payload)


# --------------------------------------------------------------------------- 执行与验证


class ExecutionRecord(StrictModel):
    """一次执行的完整记录：执行器驱动、退出码、超时、输出摘要。"""

    schema_version: EnforcementVersion = ENFORCEMENT_SCHEMA_VERSION
    action_id: str
    request_id: str
    trace_id: Optional[str] = None
    action_hash: str
    grant_id: Optional[str] = None
    tool_id: str
    risk: RiskLevel
    status: ExecutionStatus
    reason_code: ReasonCode
    driver: DriverKind
    exit_code: Optional[int] = None
    timed_out: bool = False
    duration_ms: int = Field(ge=0)
    stdout_digest: Optional[str] = None
    stderr_digest: Optional[str] = None
    output_excerpt: str = ""
    structured_digest: Optional[str] = None
    detail: str = ""
    started_at: datetime
    finished_at: datetime

    @model_validator(mode="after")
    def _status_consistency(self) -> "ExecutionRecord":
        if self.status in (ExecutionStatus.EXECUTED, ExecutionStatus.DELEGATED):
            if self.reason_code not in (ReasonCode.ALLOW, ReasonCode.ALLOW_WITH_WARNINGS):
                raise ValueError(
                    "executed/delegated 的结果必须来自 allow 路径；"
                    "否则就是“没执行却记成执行了”"
                )
        if self.status is ExecutionStatus.REFUSED and self.exit_code is not None:
            raise ValueError("refused 表示没有执行，不得带退出码")
        return self

    @property
    def produced_effect(self) -> bool:
        return self.status in (ExecutionStatus.EXECUTED, ExecutionStatus.DELEGATED)


class FileEffect(StrictModel):
    """单个文件的执行前后证据。changed=False 时哈希必须相同。"""

    path: str
    existed_before: bool
    exists_after: bool
    baseline_recorded: bool = Field(
        default=True,
        description="是否存在执行前基线；False 表示'未知'，不能当成'没有变化'或'原来不存在'",
    )
    sha256_before: Optional[str] = None
    sha256_after: Optional[str] = None
    bytes_before: int = Field(default=0, ge=0)
    bytes_after: int = Field(default=0, ge=0)
    changed: bool = False
    diff_digest: Optional[str] = None
    diff_excerpt: str = ""
    truncated: bool = False

    @model_validator(mode="after")
    def _hash_consistency(self) -> "FileEffect":
        if not self.baseline_recorded:
            # 没有基线时"变了没有"未知：允许哈希一空一实，但不得声称发生了变化。
            if self.changed:
                raise ValueError(f"{self.path}: 没有执行前基线时不得声称发生了变化")
            return self
        if not self.changed and self.sha256_before != self.sha256_after:
            raise ValueError(
                f"{self.path}: changed=False 但前后哈希不同——证据自相矛盾，拒绝记录"
            )
        if self.changed and self.sha256_before == self.sha256_after:
            # 不附加 existed_before 条件：existed_before=False + 两侧都没有哈希 + changed=True
            # 是"声称变了、却没有任何变化可证明"的空证据（baseline_recorded=True 还声称有基线）。
            # 合法的"新建"是 before=None / after=<hash>，两侧本来就不相等，用不着放宽。
            raise ValueError(
                f"{self.path}: changed=True 但前后哈希相同（含两侧都没有哈希）——"
                "证据自相矛盾：声称发生了变化却没有变化可证明"
            )
        return self


class FileBaseline(StrictModel):
    """执行前捕获的文件基线：delegated 工具（由 Agent 运行时执行）事后靠它对比哈希。"""

    path: str
    existed: bool
    sha256: Optional[str] = None
    bytes: int = Field(default=0, ge=0)
    captured_at: datetime


class ProcessEffect(StrictModel):
    """进程类动作的执行证据：退出码、超时与输出摘要（原文只留脱敏片段）。"""

    exit_code: Optional[int] = None
    timed_out: bool = False
    stdout_digest: Optional[str] = None
    stderr_digest: Optional[str] = None
    output_excerpt: str = ""
    output_truncated: bool = False


class ValidatorOutcome(StrictModel):
    """事后验证器的一条结论（Phase 4 内置 file_changed / python_syntax / exit_code_zero）。"""

    validator: str
    status: CheckStatus
    detail: str = ""
    evidence_digest: Optional[str] = None


class PostEvidence(StrictModel):
    """执行后收集到的全部证据。工具返回值里的文本只作为不可信数据保存。"""

    schema_version: EnforcementVersion = ENFORCEMENT_SCHEMA_VERSION
    action_id: str
    request_id: str
    trace_id: Optional[str] = None
    action_hash: str
    tool_id: str
    execution_status: ExecutionStatus
    files: Tuple[FileEffect, ...] = ()
    process: Optional[ProcessEffect] = None
    validators: Tuple[ValidatorOutcome, ...] = ()
    untrusted_result_digest: Optional[str] = None
    collected_at: datetime

    def file(self, path: str) -> Optional[FileEffect]:
        for item in self.files:
            if item.path == path:
                return item
        return None


class RollbackOutcome(StrictModel):
    """回滚结论。不支持回滚时必须显式写 unsupported，不能假装可撤销。"""

    mode: RollbackMode
    status: str = Field(description="applied / skipped / unsupported / failed")
    detail: str = ""
    restored: Tuple[str, ...] = ()


class PostDecision(StrictModel):
    """事后验证决策：validated / repair_required / inconsistent / not_required。"""

    schema_version: EnforcementVersion = ENFORCEMENT_SCHEMA_VERSION
    status: PostStatus
    reason_code: ReasonCode
    action_id: str
    request_id: str
    trace_id: Optional[str] = None
    action_hash: str
    tool_id: str
    checks: Tuple[CheckResult, ...] = ()
    rollback: Optional[RollbackOutcome] = None
    detail: str = ""
    evaluated_at: datetime


class FinalDecision(StrictModel):
    """链路终态：把 pre、执行与 post 三段合成一个可重放的结论。"""

    schema_version: EnforcementVersion = ENFORCEMENT_SCHEMA_VERSION
    outcome: FinalOutcome
    reason_code: ReasonCode
    action_id: str
    request_id: str
    trace_id: Optional[str] = None
    action_hash: str
    tool_id: str
    risk: RiskLevel
    pre_decision: Decision
    execution_status: Optional[ExecutionStatus] = None
    post_status: Optional[PostStatus] = None
    detail: str = ""
    decided_at: datetime

    @model_validator(mode="after")
    def _outcome_consistency(self) -> "FinalDecision":
        if self.pre_decision is Decision.BLOCK and self.outcome is not FinalOutcome.BLOCKED:
            raise ValueError("pre 决策为 block 时终态只能是 blocked")
        if (
            self.pre_decision is not Decision.BLOCK
            and self.outcome is FinalOutcome.BLOCKED
            and self.execution_status is not ExecutionStatus.REFUSED
        ):
            raise ValueError(
                "pre 决策已允许且确实执行过时不得判 blocked；"
                "只有「允许但执行器拒绝执行」（refused）才是合法终态，"
                "其余情况请用 repair_required 或 inconsistent"
            )
        return self


# --------------------------------------------------------------------------- 审计记录


class AuditRecord(StrictModel):
    """审计链上的一条记录。payload 已经过脱敏与体积限制，且只作为不可信数据保存。"""

    schema_version: EnforcementVersion = ENFORCEMENT_SCHEMA_VERSION
    sequence: int = Field(ge=1)
    stage: AuditStage
    trace_id: Optional[str] = None
    action_id: Optional[str] = None
    request_id: Optional[str] = None
    tool_id: Optional[str] = None
    recorded_at: datetime
    payload: Mapping[str, Any] = Field(default_factory=dict)
    prev_digest: str = ""
    digest: str = ""

    def compute_digest(self) -> str:
        payload = json.loads(self.model_dump_json(exclude={"digest"}))
        return digest_of(payload)

    @model_validator(mode="after")
    def _check_digest(self) -> "AuditRecord":
        expected = self.compute_digest()
        if not self.digest:
            object.__setattr__(self, "digest", expected)
        elif self.digest != expected:
            raise ValueError("审计记录摘要与内容不一致：链已被改动，拒绝信任这条记录")
        return self


# --------------------------------------------------------------------------- 消费侧


def _protocol_error(error: Exception, *, model_name: str) -> EnforcementError:
    from pydantic import ValidationError

    if isinstance(error, ValidationError):
        return EnforcementError(
            str(RuleValidationError.from_pydantic(error, model_name=model_name))
        )
    return EnforcementError(f"{model_name} 不可消费：{error}")


def parse_pre_decision(payload: Mapping[str, Any]) -> PreDecision:
    """按协议解析执行前决策；未知版本或字段不合法一律拒绝。"""

    from pydantic import ValidationError

    if not isinstance(payload, Mapping):
        raise EnforcementError(f"决策载荷必须是映射，得到 {type(payload).__name__}")
    version = payload.get("schema_version")
    if version not in SUPPORTED_ENFORCEMENT_SCHEMA_VERSIONS:
        raise EnforcementError(
            f"未知受控执行协议版本 {version!r}；只接受 "
            f"{sorted(SUPPORTED_ENFORCEMENT_SCHEMA_VERSIONS)}，拒绝消费"
        )
    try:
        return PreDecision.model_validate(dict(payload))
    except ValidationError as error:
        raise _protocol_error(error, model_name="PreDecision") from error


def parse_audit_record(payload: Mapping[str, Any]) -> AuditRecord:
    from pydantic import ValidationError

    if not isinstance(payload, Mapping):
        raise AuditError(f"审计记录必须是映射，得到 {type(payload).__name__}")
    if payload.get("schema_version") not in SUPPORTED_ENFORCEMENT_SCHEMA_VERSIONS:
        raise AuditError(f"未知审计协议版本 {payload.get('schema_version')!r}，拒绝消费")
    try:
        return AuditRecord.model_validate(dict(payload))
    except ValidationError as error:
        raise AuditError(str(_protocol_error(error, model_name="AuditRecord"))) from error
