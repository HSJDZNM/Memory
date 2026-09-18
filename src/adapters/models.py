"""Canonical Agent Event Schema：多 Agent 适配层的唯一交换协议。

本模块是 Phase 6 的协议固化点（计划第 1 步）。它与 Phase 2 的 `PolicyEvent` 是两件事：

- `adapters.dsh.adapter.PolicyEvent` 是 **dsh 专用**的扁平映射结果（工具表 + 路径 + layer）；
- `AgentEvent` 是**与实现无关**的规范事件：任何 Agent Runtime 只要产出它就能接入，
  平台不认识 dsh、Codex、Claude Code 的任何字段名。

设计约束（与核心层同一套失败策略）：

1. 受控枚举：未知 `event_type`、未知 `response_kind`、未知 `capability` 一律报错，
   不得静默忽略——"没见过的 event_type 当成无操作"等于给新事件开后门；
2. `schema_version` 是兼容轴：消费方看不懂必须拒绝，不能降级成默认放行；
3. 外部载荷只允许受控字段（`payload.path` / `payload.params` / `payload.text` /
   `payload.cwd`），Agent 消息从顶层进入后只作为内部不可信数据；其余原始字段留在
   `input_fields` 与 `payload_digest` 里——规范事件是协议，不是原始载荷的容器；
4. 路径只做**归一化**（反斜杠、`./`、尾部 `/`、工作区根记 `.`），
   逃逸与绝对路径一律拒绝：安全关键字段缺失时失败关闭。

能力声明同样在这里固化：平台不得假设所有 Agent 都支持同样的 Hook，
因此"每个 Agent 能做什么、不能做什么"必须是**数据**（adapter manifest），
而不是散落在适配器代码里的 `if agent_id == ...`。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from policy.models import (
    Decision,
    Operation,
    PolicyContextError,
    RequiredAction,
    canonical_identifier,
    normalize_repo_path,
)

__all__ = [
    "ADAPTER_MANIFEST_SCHEMA_VERSION",
    "AGENT_ID_PATTERN",
    "CANONICAL_EVENT_SCHEMA_VERSION",
    "EVENT_TYPES",
    "SUPPORTED_CANONICAL_VERSIONS",
    "SUPPORTED_MANIFEST_VERSIONS",
    "AdapterEventError",
    "AdapterManifest",
    "AgentEvent",
    "AgentResponse",
    "AgentTool",
    "ApprovalCapability",
    "BlockingCapability",
    "Capability",
    "Direction",
    "EnforcementLevel",
    "EventType",
    "HookNames",
    "ManifestError",
    "ParticipantCapability",
    "ParticipantKind",
    "ResponseKind",
    "event_payload_digest",
    "normalize_event_path",
    "parse_canonical_event",
]

# 规范事件的协议版本。任何字段增删或语义变化都必须显式改这里；
# 消费者（Runtime / 一致性套件 / 第三方 Adapter）只接受 SUPPORTED_CANONICAL_VERSIONS。
CANONICAL_EVENT_SCHEMA_VERSION = "1.0"
SUPPORTED_CANONICAL_VERSIONS: frozenset[str] = frozenset({CANONICAL_EVENT_SCHEMA_VERSION})

# Adapter manifest 的版本。manifest 是数据，改字段同样要走版本。
ADAPTER_MANIFEST_SCHEMA_VERSION = "1.0"
SUPPORTED_MANIFEST_VERSIONS: frozenset[str] = frozenset({ADAPTER_MANIFEST_SCHEMA_VERSION})

# Agent 标识：小写字母开头，只允许小写字母、数字、点、下划线、短横线。
# 它同时是命名空间前缀，因此不允许 ":"（否则 event_id 的命名空间无法反解）。
AGENT_ID_PATTERN = r"^[a-z][a-z0-9._-]*$"
# event_id 是命名空间 <adapter.namespace>:<event_id> 的组成：空白或反斜杠会让
# "这条记录属于谁"变得有歧义，因此一律拒绝。用集合判断而不是正则——
# 字符集里混进反斜杠既难读，也容易被改写坏（曾经真的被改坏过）。
_EVENT_ID_UNSAFE_CHARS = frozenset(chr(code) for code in range(33)) | frozenset(chr(92))


class AdapterEventError(ValueError):
    """规范事件或适配器声明不合法。一律失败关闭：不猜、不降级、不放行。"""


class ManifestError(AdapterEventError):
    """Adapter manifest（能力声明）不合法：接入阶段就必须显式失败。"""


class EventType(str, Enum):
    """标准事件类型（架构文档 §标准事件 的受控枚举）。

    未知事件不得静默忽略：平台必须拒绝并记录协议错误。
    """

    AGENT_START = "agent.start"
    AGENT_REQUEST = "agent.request"
    TOOL_PRE_EXECUTE = "tool.pre_execute"
    TOOL_POST_EXECUTE = "tool.post_execute"
    AGENT_TURN_END = "agent.turn_end"
    # Phase 6 新增：Agent 间消息。它是**不可信数据**，只能进上下文，不能改变策略。
    AGENT_MESSAGE = "agent.message"


EVENT_TYPES: Tuple[str, ...] = tuple(item.value for item in EventType)


class Direction(str, Enum):
    """工具动作的方向。方向决定"是否需要完整 enforcement"，而不是由工具名去猜。"""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class ParticipantKind(str, Enum):
    """决策类事件在 Agent 运行时的对应形态。"""

    PRE_HOOK = "pre_hook"
    POST_HOOK = "post_hook"
    SDK_MIDDLEWARE = "sdk_middleware"
    REQUEST_GATE = "request_gate"


class ResponseKind(str, Enum):
    """Adapter 能产出的响应形态（能力声明的一部分）。"""

    EXIT_CODE = "exit_code"
    JSON = "json"
    SDK_CALL = "sdk_call"


class BlockingCapability(str, Enum):
    """阻断能力：能阻断到什么程度。

    - `none`：不能阻断，只能记录。**不得**标记为完整 enforcement；
    - `post_only`：只能在动作发生后把结果标成失败（副作用已经产生）；
      对写类动作不是"阻断"，因此同样按只读处理；
    - `pre_execute`：能在工具执行前拒绝，这是完整 enforcement 的必要条件。
    """

    NONE = "none"
    POST_ONLY = "post_only"
    PRE_EXECUTE = "pre_execute"


class ApprovalCapability(str, Enum):
    """审批能力：模式只在 Adapter 内翻译，核心层只认 `required_action=approval`。"""

    NONE = "none"
    INTERACTIVE = "interactive"
    FILE = "file"


class EnforcementLevel(str, Enum):
    """支持矩阵的结论：每个 Agent 到底受什么程度的治理。

    - `full`：可阻断 + 可审批 + 有执行前事件 → 写类动作可被完整治理；
    - `read_only`：可映射、可判定、可记录，但拦不住 → 只允许只读动作；
    - `unsupported`：声明的协议版本或能力当前实现不了 → 接入即拒绝。
    """

    FULL = "full"
    READ_ONLY = "read_only"
    UNSUPPORTED = "unsupported"


class ParticipantCapability(BaseModel):
    """规范事件 → Agent 运行时形态的映射。

    `declared` 为 False 表示"该 Agent 没有这个阶段的钩子"——这本身是合法声明
    （平台不得假设所有 Agent 都支持同样的 Hook），但会限制可达到的 enforcement。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    declared: bool
    kind: ParticipantKind
    response_kind: ResponseKind

    @model_validator(mode="after")
    def _response_kind_consistent(self) -> "ParticipantCapability":
        if not self.declared and self.kind is ParticipantKind.POST_HOOK:
            raise ValueError(
                "未声明的钩子不得标记为 post_hook：声明与事实必须一致，"
                "能力不足要在接入时显式失败，而不是写一个看起来能用的种类"
            )
        return self


class Capability(BaseModel):
    """Adapter 的单项能力声明。

    能力是**声明**，不是承诺：Runtime 只把它当作"这个 Agent 是否可能在执行前被拦住"，
    真正的执行结果仍然由判定与执行记录决定。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability: str = Field(min_length=1)
    declared: bool
    detail: str = ""

    @field_validator("capability")
    @classmethod
    def _check_capability(cls, value: str) -> str:
        normalized = canonical_identifier(value)
        if not re.match(r"^[a-z][a-z0-9._-]*$", normalized):
            raise ValueError(f"能力名必须是稳定标识符（小写字母/数字/._-），得到 {value!r}")
        return normalized


class HookNames(BaseModel):
    """Agent 侧的事件名与载荷字段名（协议事实，不是平台的判断）。

    dsh 用 PreToolUse / PostToolUse / session_id / tool_name / tool_input / tool_use_id；
    另一个 Agent 可能只有其中一部分，或全不一样。差异必须留在数据里，
    否则"新增一个 Adapter"就会变成"在核心层再加一个 if agent_id == ..."。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    pre_execute: str = Field(default="PreToolUse", min_length=1)
    post_execute: str = Field(default="PostToolUse", min_length=1)
    session_field: str = Field(default="session_id", min_length=1)
    tool_field: str = Field(default="tool_name", min_length=1)
    input_field: str = Field(default="tool_input", min_length=1)
    call_id_field: str = Field(default="tool_use_id", min_length=1)
    cwd_field: str = Field(default="cwd", min_length=1)

    @field_validator("pre_execute", "post_execute")
    @classmethod
    def _check_event_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("事件名不能为空")
        return normalized

    @field_validator(
        "session_field", "tool_field", "input_field", "call_id_field", "cwd_field"
    )
    @classmethod
    def _check_field_name(cls, value: str) -> str:
        normalized = value.strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", normalized):
            raise ValueError(f"载荷字段名必须是标识符，得到 {value!r}")
        return normalized


class AgentTool(BaseModel):
    """Adapter 的工具表条目：工具 → 受控操作 + 路径字段。

    这是 Phase 6 的"声明式工具表"：dsh 的硬编码 TOOL_TABLE 仍然存在，
    但它与 manifest 的声明必须一致（契约测试守这条不变量），
    因此"升级 Agent 必须先更新工具表并补契约测试"这条约束对两种形态同样成立。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, description='平台侧规范工具名')
    aliases: Tuple[str, ...] = Field(
        default=(),
        description='Agent 侧的工具名（协议事实）；平台侧统一用规范名，差异留在数据里',
    )
    operation: Optional[Operation] = None
    direction: Direction = Direction.OUTBOUND
    path_field: Optional[str] = None
    path_scope: Optional[str] = Field(
        default=None,
        description="路径参数的解析基准：workspace 表示必须落在受控项目内",
    )
    proposed_fields: Tuple[str, ...] = ()
    note: str = ""

    @field_validator("path_scope")
    @classmethod
    def _check_scope(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = canonical_identifier(value)
        if normalized != "workspace":
            raise ValueError(
                f"path_scope 只支持 'workspace'（越界即拒绝）：得到 {value!r}；"
                "需要别的范围时先改协议并写进阶段文档"
            )
        return normalized

    @model_validator(mode="after")
    def _path_field_requires_scope(self) -> "AgentTool":
        if (self.path_field is None) != (self.path_scope is None):
            raise ValueError(
                f"工具 {self.name!r} 的 path_field 与 path_scope 必须同时声明或同时省略："
                "只写一个会让路径要么不被校验、要么无从解析"
            )
        return self


class AdapterManifest(BaseModel):
    """Adapter 的能力声明（`adapters/<agent_id>.yaml` 的文档模型）。

    必需项刻意包含 `agent_version`：没有版本就没法把"支持矩阵"钉在具体产品版本上，
    而升级 Agent 后重跑 fixture 正是 Phase 6 的验收要求之一。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default=ADAPTER_MANIFEST_SCHEMA_VERSION)
    agent_id: str = Field(min_length=1)
    agent_version: str = Field(min_length=1, description="已实测的 Agent 产品版本")
    display_name: str = Field(min_length=1)
    protocol: str = Field(min_length=1, description="线协议名，例如 dsh-hooks-claude-code")
    protocol_version: str = Field(min_length=1)
    pre_hook: ParticipantCapability
    post_hook: ParticipantCapability
    approval: ApprovalCapability
    blocking: BlockingCapability
    response_kind: ResponseKind
    hooks: HookNames = Field(default_factory=lambda: HookNames())
    ledger_alias: Optional[str] = None
    event_types: Tuple[EventType, ...] = Field(min_length=1)
    requested_enforcement: Optional[EnforcementLevel] = None
    # 兼容性 fixture：这个 Agent 的最小真实事件样本（tests/fixtures/agent_events/<agent>/）。
    # 升级 Agent Runtime 时先重跑这些 fixture 与沙箱集成测试，再更新支持矩阵。
    fixtures: Tuple[str, ...] = ()
    tools: Tuple[AgentTool, ...] = ()
    capabilities: Tuple[Capability, ...] = ()
    notes: str = ""

    @field_validator("schema_version")
    @classmethod
    def _check_manifest_version(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in SUPPORTED_MANIFEST_VERSIONS:
            raise ValueError(
                f"未知 adapter manifest 版本 {value!r}；本实现只接受 "
                f"{sorted(SUPPORTED_MANIFEST_VERSIONS)}，拒绝按旧语义解释新字段"
            )
        return normalized

    @field_validator("agent_id")
    @classmethod
    def _check_agent_id(cls, value: str) -> str:
        normalized = canonical_identifier(value)
        if not re.match(AGENT_ID_PATTERN, normalized):
            raise ValueError(
                f"agent_id 必须是稳定标识符（小写字母开头，允许 0-9 . _ -），得到 {value!r}"
            )
        return normalized

    @field_validator("agent_version", "display_name", "protocol", "protocol_version")
    @classmethod
    def _check_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("manifest 的文本字段不能是空字符串")
        return normalized

    @field_validator("event_types", mode="before")
    @classmethod
    def _check_event_types(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = (value,)
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("event_types 必须是列表")
        normalized: list[EventType] = []
        for raw in value:
            token = str(raw).strip()
            try:
                item = EventType(token)
            except ValueError:
                raise ValueError(
                    f"event_types 只接受受控枚举 {list(EVENT_TYPES)}，得到 {raw!r}；"
                    "未知事件类型不得出现在能力声明里"
                ) from None
            if item not in normalized:
                normalized.append(item)
        if not normalized:
            raise ValueError("event_types 不能为空")
        return tuple(sorted(normalized, key=lambda item: item.value))

    @field_validator("ledger_alias")
    @classmethod
    def _check_alias(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = canonical_identifier(value)
        if not re.match(AGENT_ID_PATTERN, normalized):
            raise ValueError(
                f"ledger_alias 必须是稳定标识符（小写字母开头），得到 {value!r}："
                "它决定审计命名空间，不允许有歧义"
            )
        return normalized

    @field_validator("tools")
    @classmethod
    def _check_tool_names(cls, value: Tuple[AgentTool, ...]) -> Tuple[AgentTool, ...]:
        """工具名与别名在整张表里必须唯一。

        Agent 侧的名字（别名）唯一，才能保证"按 Agent 发出的名字查表"没有歧义；
        规范名重复更是直接的语义冲突。工具自己的 name 写进 aliases 是允许的
        （同一个名字的两个视角而已），不算冲突。
        """

        seen: dict[str, str] = {}
        for item in value:
            for token in dict.fromkeys((item.name, *item.aliases)):
                owner = seen.get(token)
                if owner is not None:
                    raise ValueError(
                        f"工具表里 {token!r} 同时属于 {owner!r} 与 {item.name!r}："
                        "工具名与别名必须唯一，否则查表结果取决于顺序"
                    )
                seen[token] = item.name
        return value

    @model_validator(mode="after")
    def _capabilities_are_coherent(self) -> "AdapterManifest":
        """能力声明必须自洽：这是"能力不足时显式失败"的实现点。

        允许的唯一降级是 `blocking=post_only`——它表示"这个 Agent 只能在事后把结果标错"，
        对写类动作不算阻断，平台据此把它限制为只读，而不是假装能拦。
        """

        has_decision_event = (
            EventType.TOOL_PRE_EXECUTE in self.event_types
            or EventType.TOOL_POST_EXECUTE in self.event_types
        )
        if self.blocking is not BlockingCapability.NONE and not has_decision_event:
            raise ValueError(
                "声明了阻断能力却没有声明任何 tool.* 事件：能力声明与事实不一致"
            )
        if self.blocking is BlockingCapability.PRE_EXECUTE and (
            not self.pre_hook.declared
            or EventType.TOOL_PRE_EXECUTE not in self.event_types
        ):
            raise ValueError(
                "blocking=pre_execute 必须有已声明的 pre_hook 与 tool.pre_execute 事件："
                "没有执行前钩子的 Agent 无法在执行前拒绝动作"
            )
        if self.approval is not ApprovalCapability.NONE and (
            self.blocking is BlockingCapability.NONE
        ):
            raise ValueError(
                "声明审批能力但完全没有阻断能力：审批结论无处表达（核心层只认 block）"
            )
        if self.pre_hook.declared and EventType.TOOL_PRE_EXECUTE not in self.event_types:
            raise ValueError(
                "声明了 pre_hook 却没有声明 tool.pre_execute 事件：接入时显式失败，"
                "不得让 pre_hook 变成一句没有落点的声明"
            )
        if self.post_hook.declared and EventType.TOOL_POST_EXECUTE not in self.event_types:
            raise ValueError("声明了 post_hook 却没有声明 tool.post_execute 事件")
        if self.requested_enforcement is EnforcementLevel.FULL:
            if self.blocking is not BlockingCapability.PRE_EXECUTE:
                raise ValueError(
                    "requested_enforcement=full 但阻断能力不是 pre_execute："
                    "平台不得把无法强制阻断的 Agent 标成完整 enforcement。"
                    "请声明 read_only，或先在 Agent 侧接入执行前钩子"
                )
        for item in self.fixtures:
            token = item.strip()
            if (
                not token.endswith(".json")
                or token.startswith("/")
                or ".." in token.split("/")
            ):
                raise ValueError(
                    "fixtures 条目必须是仓库相对的 .json 路径（例如 "
                    "adapters/<agent>/fixtures/<name>.json），得到 " + repr(item)
                )
        if self.requested_enforcement is EnforcementLevel.UNSUPPORTED and self.tools:
            raise ValueError(
                "requested_enforcement=unsupported 的 Adapter 不得声明工具表："
                "未接入的协议没有可执行语义，写一张表只会让人以为它能用"
            )
        return self


@dataclass(frozen=True)
class AgentEvent:
    """规范事件：Agent 运行时与平台之间唯一允许的事件形状。

    `payload` 对外只接受 `path` / `params` / `text` / `cwd`；解析器可再注入顶层
    `message` 作为内部不可信数据。其余原始输入用 `payload_digest` 与 `input_fields` 指代——
    既能做幂等与审计关联，
    又不会把源码内容、提示词或用户数据留进证据文件。
    """

    schema_version: str
    event_id: str
    event_type: EventType
    request_id: str
    agent_id: str
    agent_version: str
    payload_digest: str
    occurred_at: str
    input_fields: Tuple[str, ...] = ()
    trace_id: Optional[str] = None
    parent_trace_id: Optional[str] = None
    principal_subject: Optional[str] = None
    principal_roles: Tuple[str, ...] = ()
    tool: Optional[str] = None
    operation: Optional[Operation] = None
    payload: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_CANONICAL_VERSIONS:
            raise AdapterEventError(
                f"未知规范事件版本 {self.schema_version!r}；本实现只接受 "
                f"{sorted(SUPPORTED_CANONICAL_VERSIONS)}，拒绝消费"
            )
        if not isinstance(self.event_type, EventType):
            raise AdapterEventError(
                f"event_type 必须是受控枚举 EventType，得到 {self.event_type!r}"
            )
        if self.payload is None:
            object.__setattr__(self, "payload", {})
        if not isinstance(self.payload, Mapping):
            raise AdapterEventError(
                f"payload 必须是映射，得到 {type(self.payload).__name__}"
            )
        if not self.event_id or not self.request_id:
            raise AdapterEventError("event_id 与 request_id 都必须非空")

    @property
    def decision_requested(self) -> bool:
        """该事件是否要求平台给出决定（其余事件只记录）。"""

        return self.event_type in (EventType.TOOL_PRE_EXECUTE, EventType.TOOL_POST_EXECUTE)

    @property
    def path(self) -> Optional[str]:
        """规范事件里的目标路径（已归一化，工作区根记 `.`）。"""

        value = self.payload.get("path")
        return value if isinstance(value, str) else None

    @property
    def params(self) -> Mapping[str, Any]:
        value = self.payload.get("params")
        return value if isinstance(value, Mapping) else {}

    @property
    def message(self) -> Optional[Mapping[str, Any]]:
        """Agent 间消息：**不可信数据**，永远不能改变策略或扩权。"""

        value = self.payload.get("message")
        return value if isinstance(value, Mapping) else None


class AgentResponse(BaseModel):
    """Adapter 回给 Agent 的响应（`to_agent_response` 的产物）。

    形状固定为受控字段：Agent 能读懂"该不该执行、为什么、怎么修"，
    但拿不到内部堆栈、绝对路径或完整规则库。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CANONICAL_EVENT_SCHEMA_VERSION
    agent_id: str
    request_id: str
    event_id: str
    decision: Decision
    reason_code: str
    message: str = ""
    remediation: Tuple[str, ...] = ()
    required_action: Optional[RequiredAction] = None
    violations: Tuple[str, ...] = ()
    matched_rules: Tuple[str, ...] = ()
    trace_id: Optional[str] = None
    executed: bool = False
    response_kind: ResponseKind = ResponseKind.JSON
    # Adapter 侧的原生表达（例如 dsh 的退出码 0/2）；核心层不解释它。
    native: Optional[str] = None


@dataclass(frozen=True)
class AdapterLoad:
    """一次加载的结果：manifest、配置、路径与可安全审计的注册表身份。"""

    manifest: AdapterManifest
    config_path: str
    manifest_digest: str
    config: Any


def normalize_event_path(value: str, *, workspace: Path, path_base: Optional[Path] = None) -> str:
    """把事件里的路径归一化为**仓库相对路径**。

    两种输入必须分开处理，否则"看起来是相对路径"的逃逸会直接漏过：

    - `path_base` 给定时（钩子类 Agent：路径是相对会话工作目录的原始字符串），
      先解析成绝对路径**再做包含性检查**——`../outside.py` 因此会被拒绝；
    - `path_base` 省略时（规范事件：路径已经是仓库相对路径），
      只做规范化并拒绝 `..` 逃逸。

    允许路径等于工作区根，规范化为 `.`（只读工具常以项目根为范围）。
    绝对路径落在工作区之外、`..` 逃逸、空路径一律拒绝：安全关键字段不得猜测。
    """

    if not isinstance(value, str):
        raise AdapterEventError(f"路径必须是字符串，得到 {type(value).__name__}")
    raw = value.strip()
    if not raw:
        raise AdapterEventError("路径不能为空；路径是安全关键字段，不得猜测")

    anchor = Path(workspace).resolve()
    looks_absolute = PurePosixPath(raw.replace(chr(92), "/")).is_absolute() or bool(
        re.match(r"^[A-Za-z]:", raw)
    )

    if path_base is not None and not looks_absolute:
        candidate = (Path(path_base).resolve() / raw.replace(chr(92), "/")).resolve()
        if not _within(candidate, anchor):
            raise AdapterEventError(
                f"路径不在受控工作区 {anchor.name} 内：越界一律拒绝（含只读动作）"
            )
        return _relative_to(candidate, anchor)

    if looks_absolute:
        candidate = Path(raw).resolve()
        if not _within(candidate, anchor):
            raise AdapterEventError(
                f"路径不在受控工作区 {anchor.name} 内：越界一律拒绝（含只读动作）"
            )
        return _relative_to(candidate, anchor)

    if raw.replace(chr(92), "/").strip("./") == "":
        # "." 与 "./" 表示工作区根：只读工具常以项目根为范围。
        return "."
    if ".." in raw.replace(chr(92), "/").split("/"):
        # 相对路径里的 ".." 一律拒绝，**不**依赖调用方先做 normpath。
        # 反例（真实踩过）：把 "../outside.py" 先 normpath 成 "outside.py"，
        # 再交给这里，逃逸就变成了一次静默的"规范化"。
        raise AdapterEventError(
            f"相对路径不允许包含 '..'：{raw!r} 试图逃出工作区，越界一律拒绝"
        )
    try:
        return normalize_repo_path(raw)
    except PolicyContextError as error:
        raise AdapterEventError(str(error)) from error


def _within(candidate: Path, anchor: Path) -> bool:
    head = [item.lower() for item in candidate.parts[: len(anchor.parts)]]
    return head == [item.lower() for item in anchor.parts]


def _relative_to(candidate: Path, anchor: Path) -> str:
    remainder = candidate.parts[len(anchor.parts) :]
    if not remainder:
        return "."
    try:
        return normalize_repo_path("/".join(remainder))
    except PolicyContextError as error:
        raise AdapterEventError(str(error)) from error


def event_payload_digest(value: Any) -> str:
    """载荷摘要：稳定序列化后取 sha256。

    非 JSON 可序列化的值只留类型名，绝不把原始对象 `repr` 进摘要输入——
    `repr` 可能带出绝对路径或凭据，而这里的结果会进审计。
    """

    try:
        canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        canonical = json.dumps(str(type(value).__name__), ensure_ascii=False)
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def parse_canonical_event(document: Mapping[str, Any], *, agent_id: Optional[str] = None) -> AgentEvent:
    """消费一份规范事件载荷（第三方 Adapter 的直接入口）。

    未知版本、未知字段、未知事件类型、载荷缺字段一律拒绝。
    `agent_id` 由调用方（Adapter 装配处）钉死，不从载荷里读：
    否则请求方可以自称成另一个 Agent，跨 Agent 隔离就形同虚设。
    """

    if not isinstance(document, Mapping):
        raise AdapterEventError(
            f"规范事件必须是映射，得到 {type(document).__name__}"
        )

    version = document.get("schema_version")
    if version is None:
        raise AdapterEventError("规范事件缺少 schema_version，拒绝消费")
    if version not in SUPPORTED_CANONICAL_VERSIONS:
        raise AdapterEventError(
            f"未知规范事件版本 {version!r}；本实现只接受 "
            f"{sorted(SUPPORTED_CANONICAL_VERSIONS)}，拒绝消费"
        )

    known = {
        "schema_version",
        "event_id",
        "event_type",
        "request_id",
        "trace_id",
        "parent_trace_id",
        "agent_version",
        "occurred_at",
        "principal",
        "tool",
        "operation",
        "payload",
        "message",
    }
    unknown = sorted(set(document) - known)
    if unknown:
        raise AdapterEventError(
            f"规范事件出现未知字段 {unknown}；允许的字段为 {sorted(known)}"
        )

    raw_type = document.get("event_type")
    try:
        event_type = EventType(str(raw_type))
    except ValueError:
        raise AdapterEventError(
            f"未知事件类型 {raw_type!r}；受控枚举为 {list(EVENT_TYPES)}，拒绝并记录协议错误"
        ) from None

    principal = document.get("principal") or {}
    if not isinstance(principal, Mapping):
        raise AdapterEventError("principal 必须是 {subject, roles} 结构")
    unknown_principal = sorted(set(principal) - {"subject", "roles"})
    if unknown_principal:
        raise AdapterEventError(f"principal 出现未知字段 {unknown_principal}")

    payload = document.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise AdapterEventError("payload 必须是映射")
    payload = dict(payload)
    allowed_payload = {"path", "params", "text", "cwd"}
    unknown_payload = sorted(set(payload) - allowed_payload)
    if unknown_payload:
        raise AdapterEventError(
            f"payload 出现未知或内部字段 {unknown_payload}；"
            f"外部规范事件只允许 {sorted(allowed_payload)}"
        )
    message = document.get("message")
    if message is not None:
        if not isinstance(message, Mapping):
            raise AdapterEventError("message 必须是映射（Agent 间消息是不可信数据）")
        payload["message"] = dict(message)

    raw_path = payload.get("path")
    if raw_path is not None:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise AdapterEventError("payload.path 必须是非空字符串或缺失")
        payload["path"] = raw_path.strip()

    params = payload.get("params")
    if params is not None and not isinstance(params, Mapping):
        raise AdapterEventError("payload.params 必须是映射")
    if isinstance(params, Mapping):
        payload["params"] = {str(key): params[key] for key in params}

    for field in ("text", "cwd"):
        value = payload.get(field)
        if value is not None and not isinstance(value, str):
            raise AdapterEventError(f"payload.{field} 必须是字符串或缺失")

    operation = document.get("operation")
    if operation is not None:
        try:
            operation = Operation(canonical_identifier(str(operation)))
        except ValueError:
            raise AdapterEventError(
                f"未知操作 {document.get('operation')!r}；受控枚举为 "
                f"{sorted(item.value for item in Operation)}"
            ) from None

    def identifier(key: str) -> str:
        value = document.get(key)
        if not isinstance(value, str) or not value.strip():
            raise AdapterEventError(f"规范事件字段 {key} 必须是非空字符串")
        return value.strip()

    resolved_agent = canonical_identifier(agent_id) if agent_id else "unknown"
    if not re.match(AGENT_ID_PATTERN, resolved_agent):
        raise AdapterEventError(f"agent_id {resolved_agent!r} 不是合法标识符")

    raw_event_id = identifier("event_id")
    if set(raw_event_id) & _EVENT_ID_UNSAFE_CHARS or any(
        item.isspace() for item in raw_event_id
    ):
        raise AdapterEventError(
            f"event_id {raw_event_id!r} 含空白或分隔符：它是命名空间的组成，不允许歧义"
        )

    return AgentEvent(
        schema_version=str(version),
        event_id=raw_event_id,
        event_type=event_type,
        request_id=identifier("request_id"),
        agent_id=resolved_agent,
        agent_version=str(document.get("agent_version") or "unknown").strip() or "unknown",
        payload_digest=event_payload_digest(payload),
        occurred_at=str(document.get("occurred_at") or "").strip(),
        input_fields=tuple(sorted(str(key) for key in payload)),
        trace_id=_optional_text(document.get("trace_id")),
        parent_trace_id=_optional_text(document.get("parent_trace_id")),
        principal_subject=_optional_text(principal.get("subject")),
        principal_roles=_roles(principal.get("roles")),
        tool=_optional_text(document.get("tool")),
        operation=operation,
        payload=payload,
    )


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AdapterEventError(f"标识字段必须是字符串或 null，得到 {type(value).__name__}")
    normalized = value.strip()
    return normalized or None


def _roles(value: Any) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (canonical_identifier(value),) if value.strip() else ()
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(sorted({canonical_identifier(str(item)) for item in value if str(item).strip()}))
    raise AdapterEventError("principal.roles 必须是字符串列表")
