"""Adapter 协议、能力矩阵与数据化的 Adapter 注册表。

Phase 6 的统一接口（计划 §统一接口）：

    Agent Runtime
      → AgentAdapter.to_policy_event(raw_event)
      → Policy Platform
      → AgentAdapter.to_agent_response(decision)

本模块负责三件事：

1. `Adapter`：所有 Adapter 的公共部分——**只做协议转换**，不判定 severity、
   不加载规则、不执行工具、不读源码内容；缺字段就失败关闭；
2. `AdapterRegistry`：从 `adapters/approved.json` 读取**已审核的能力声明哈希**，
   与磁盘上的 manifest 逐份比对。与 Phase 4 的工具注册表同一条思路：
   声明是数据，改声明必须重新审核——"升级 Agent 后忘了更新能力声明"
   不能变成一次静默的扩权；
3. `SupportCeiling`：由**声明的能力**推出该 Agent 真实的上限
   （full / read_only / unsupported），平台据此拒绝它做不到的治理。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, Sequence, Tuple

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from policy.models import (
    Operation,
    PolicyContext,
    PolicyContextError,
    Principal,
    RuleValidationError,
    canonical_identifier,
    normalize_repo_path,
)

from .models import (
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    AdapterEventError,
    AdapterManifest,
    AgentEvent,
    ApprovalCapability,
    BlockingCapability,
    EnforcementLevel,
    EventType,
    ManifestError,
    ParticipantCapability,
    Direction,
    normalize_event_path,
)

__all__ = [
    "APPROVED_SCHEMA_VERSION",
    "DEFAULT_ADAPTERS_ROOT",
    "DEFAULT_APPROVED_PATH",
    "ADAPTER_CONFIG_SCHEMA_VERSION",
    "Adapter",
    "AdapterConfig",
    "AdapterDescriptor",
    "AdapterList",
    "AdapterRegistry",
    "AdapterSpec",
    "EventAdapter",
    "PathRule",
    "RegistryError",
    "SupportCeiling",
    "approved_digest",
    "manifest_digest",
]

APPROVED_SCHEMA_VERSION = "1.0"
ADAPTER_CONFIG_SCHEMA_VERSION = "1.0"
DEFAULT_ADAPTERS_ROOT = "adapters"
DEFAULT_APPROVED_PATH = "adapters/approved.json"

# 能力上限：声明能做什么，就只能做什么。数值越大越强。
_CEILING_RANK = {
    EnforcementLevel.UNSUPPORTED: 0,
    EnforcementLevel.READ_ONLY: 1,
    EnforcementLevel.FULL: 2,
}


class RegistryError(Exception):
    """Adapter 注册表或清单不可用（失败策略：配置错误 → 拒绝接入）。"""


class AdapterSpec(BaseModel):
    """`adapters/<agent_id>/manifest.yaml` 的磁盘文档模型。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = ADAPTER_MANIFEST_SCHEMA_VERSION
    agent_id: str
    agent_version: str
    display_name: str
    protocol: str
    protocol_version: str
    pre_hook: Mapping[str, Any]
    post_hook: Mapping[str, Any]
    approval: str
    blocking: str
    response_kind: str
    event_types: Tuple[str, ...]
    hooks: Mapping[str, Any] = Field(default_factory=dict)
    ledger_alias: Optional[str] = None
    requested_enforcement: Optional[str] = None
    fixtures: Tuple[str, ...] = ()
    tools: Tuple[Mapping[str, Any], ...] = ()
    capabilities: Tuple[Mapping[str, Any], ...] = ()
    notes: str = ""

    def to_manifest(self, *, path: Path) -> AdapterManifest:
        try:
            return AdapterManifest.model_validate(self.model_dump(mode="json"))
        except ValidationError as error:
            failure = RuleValidationError.from_pydantic(
                error, model_name=f"adapter manifest {path.name}"
            )
            raise ManifestError(str(failure)) from error


class AdapterConfig(BaseModel):
    """Adapter 的运行期配置（`adapters/<agent_id>/adapter.yaml`）。

    `project_root` 与 `rules` 支持相对路径，基准是**该配置文件所在的目录**；
    与 Phase 2 的 dsh 配置保持同一口径，避免"配置放哪、路径算哪"的歧义。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = ADAPTER_CONFIG_SCHEMA_VERSION
    project_root: str = Field(min_length=1)
    rules: Tuple[str, ...] = Field(min_length=1)
    project: Optional[str] = None
    layers: Tuple[Mapping[str, str], ...] = ()
    default_layer: Optional[str] = None
    languages: Tuple[Mapping[str, str], ...] = ()
    default_language: Optional[str] = None
    principal: Optional[Mapping[str, Any]] = None
    audit_log: Optional[str] = None
    registry: Optional[str] = None
    registry_approved: Optional[str] = None
    timeout_ms: int = Field(default=5000, gt=0)
    trace_id: Optional[str] = None
    rules_root: Optional[str] = None
    # 台账命名空间：默认取 agent_id；同一个 Agent 跑多份部署时必须显式区分，
    # 否则 Agent A 的 event_id 会命中 Agent B 的幂等记录（跨实例隔离）。
    ledger_alias: Optional[str] = None
    # 熔断：同一个 Agent 在一个时间窗口内的受治理事件数上限。
    # 用窗口内的量而不是某个 request_id 的量：Agent 互相触发的循环里
    # request_id 每次都可能不同，按请求计数永远数不到上限。
    max_events_per_window: int = Field(default=50, gt=0)
    window_seconds: int = Field(default=60, gt=0)

    @model_validator(mode="after")
    def _check_rows(self) -> "AdapterConfig":
        for name, rows in (("layers", self.layers), ("languages", self.languages)):
            for index, row in enumerate(rows):
                unknown = sorted(set(row) - {"pattern", "layer", "language"})
                if unknown:
                    raise ValueError(f"{name}[{index}] 出现未知字段 {unknown}")
                if name == "layers" and set(row) != {"pattern", "layer"}:
                    raise ValueError(f"{name}[{index}] 必须是 {{pattern, layer}}")
                if name == "languages" and set(row) != {"pattern", "language"}:
                    raise ValueError(f"{name}[{index}] 必须是 {{pattern, language}}")
        return self


@dataclass(frozen=True)
class PathRule:
    """显式声明的 path → 维度映射（绝不由 Adapter 猜）。"""

    pattern: str
    value: str


@dataclass(frozen=True)
class SupportCeiling:
    """由能力声明推出的上限，以及它与申请值之间的差异说明。"""

    level: EnforcementLevel
    requested: Optional[EnforcementLevel]
    reasons: Tuple[str, ...] = ()

    @property
    def downgraded(self) -> bool:
        return self.requested is not None and _CEILING_RANK[self.level] < _CEILING_RANK[self.requested]


def _compile_glob(pattern: str) -> "re.Pattern[str]":
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if pattern[index : index + 2] == "**":
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


def ceiling_from_capabilities(manifest: AdapterManifest) -> SupportCeiling:
    """能力上限：平台**不得**把拦不住动作的 Agent 标成完整 enforcement。

    规则只有三条，全部来自声明：

    1. 没有执行前事件，或阻断能力不是 `pre_execute`（`none` / `post_only`），
       对写类动作就不是阻断 → 上限 `read_only`；
    2. 没有工具表（`agent.request` 这类"请求门禁"型消费者）→ 上限 `read_only`：
       它能被治理，但没有工具语义，不能算完整 enforcement；
    3. 申请值本身更低时以申请值为准（Adapter 主动要求收紧是合法的）。
    """

    reasons: list[str] = []
    level = EnforcementLevel.FULL

    if not manifest.pre_hook.declared:
        reasons.append("没有声明执行前钩子：无法在工具执行前拒绝")
        level = EnforcementLevel.READ_ONLY
    elif manifest.blocking is not BlockingCapability.PRE_EXECUTE:
        reasons.append(
            f"阻断能力是 {manifest.blocking.value}：动作已经发生才能标错，不算阻断"
        )
        level = EnforcementLevel.READ_ONLY
    elif EventType.TOOL_PRE_EXECUTE not in manifest.event_types:
        reasons.append("没有声明 tool.pre_execute 事件：没有执行前判定点")
        level = EnforcementLevel.READ_ONLY

    if level is EnforcementLevel.FULL and not manifest.tools:
        reasons.append("没有声明工具表：没有工具语义，只能治理请求级事件")
        level = EnforcementLevel.READ_ONLY

    requested = manifest.requested_enforcement
    if requested is not None and _CEILING_RANK[requested] < _CEILING_RANK[level]:
        reasons.append(f"Adapter 主动把上限收紧到 {requested.value}")
        level = requested

    return SupportCeiling(level=level, requested=requested, reasons=tuple(reasons))


class EventAdapter(Protocol):
    """每个具体 Adapter 必须实现的端口。

    只做协议转换：把 Agent Runtime 的原始事件映射成规范事件，
    再把决策翻译回该 Runtime 能理解的响应形态。
    """

    manifest: AdapterManifest

    @property
    def agent_id(self) -> str:
        ...

    def to_policy_event(
        self, raw_event: Any, *, workspace: Optional[Path] = None
    ) -> AgentEvent:
        ...

    def to_policy_context(
        self, event: AgentEvent, *, workspace: Optional[Path] = None
    ) -> PolicyContext:
        ...


class Adapter:
    """所有 Adapter 的公共实现：事件校验、路径归一化、上下文构造、响应翻译。

    子类只需实现 `_build_event`（原始载荷 → 规范事件）。公共部分刻意写死在这里，
    因为"路径越界即拒绝""未知事件即拒绝""缺 layer 即拒绝"对每个 Agent 都一样——
    把这三件事留给各 Adapter 自己实现，等于给每个新 Agent 一次重新犯错的机会。
    """

    manifest: AdapterManifest

    def __init__(
        self,
        *,
        manifest: AdapterManifest,
        config: AdapterConfig,
        config_path: Path | str = "<memory>",
        base_dir: Optional[Path] = None,
    ) -> None:
        self.manifest = manifest
        self.config = config
        self.config_path = Path(config_path).name if config_path else "<memory>"
        anchor = Path(base_dir) if base_dir is not None else Path.cwd()

        self.workspace = self._resolve(config.project_root, anchor)
        if not self.workspace.is_dir():
            raise AdapterEventError(
                f"受控工作区不存在：{self.workspace.name}；"
                "Adapter 不接受一个证明不了范围的配置"
            )
        self.rule_dirs = tuple(self._resolve(item, anchor) for item in config.rules)
        self.rules_root = (
            self._resolve(config.rules_root, anchor)
            if config.rules_root is not None
            else self.workspace
        )
        self.audit_path = (
            self._resolve(config.audit_log, anchor) if config.audit_log is not None else None
        )
        self.registry_path = (
            self._resolve(config.registry, anchor) if config.registry is not None else None
        )
        self.registry_approved_path = (
            self._resolve(config.registry_approved, anchor)
            if config.registry_approved is not None
            else None
        )
        self._layers = tuple(
            PathRule(row["pattern"], canonical_identifier(row["layer"])) for row in config.layers
        )
        self._languages = tuple(
            PathRule(row["pattern"], canonical_identifier(row["language"]))
            for row in config.languages
        )
        self._compiled: dict[str, "re.Pattern[str]"] = {}
        self._principal: Optional[Principal] = (
            None
            if config.principal is None
            else Principal.model_validate(dict(config.principal))
        )
        self.ceiling = ceiling_from_capabilities(manifest)
        self.tools = {item.name: item for item in manifest.tools}
        # Agent 侧的工具名（别名）也能查到同一条声明：差异留在数据里，
        # 调用方（例如规范事件里写的是 Agent 侧名字）不必自己翻译。
        self._by_vendor: dict[str, str] = {}
        for item in manifest.tools:
            self._by_vendor[item.name] = item.name
            for alias in item.aliases:
                self._by_vendor[alias] = item.name
        namespace = config.ledger_alias or manifest.ledger_alias or manifest.agent_id
        self.namespace = canonical_identifier(namespace)

    # ------------------------------------------------------------------ 装配
    @staticmethod
    def _resolve(value: str, anchor: Path) -> Path:
        candidate = Path(str(value).replace(chr(92), "/"))
        if not candidate.is_absolute():
            candidate = anchor / candidate
        return candidate.resolve()

    @property
    def agent_id(self) -> str:
        return self.manifest.agent_id

    @property
    def agent_version(self) -> str:
        return self.manifest.agent_version

    @property
    def principal(self) -> Optional[Principal]:
        """显式声明的主体；没有声明就没有——绝不从路径、文件名或消息里推断。"""

        return self._principal

    # ------------------------------------------------------------------ 维度映射
    def _match(self, rules: Sequence[PathRule], path: str) -> Optional[str]:
        for rule in rules:
            compiled = self._compiled.get(rule.pattern)
            if compiled is None:
                compiled = _compile_glob(rule.pattern)
                self._compiled[rule.pattern] = compiled
            if compiled.match(path):
                return rule.value
        return None

    def layer_for(self, path: str) -> Optional[str]:
        return self._match(self._layers, path) or (
            None if self.config.default_layer is None else canonical_identifier(self.config.default_layer)
        )

    def language_for(self, path: str) -> Optional[str]:
        return self._match(self._languages, path) or (
            None
            if self.config.default_language is None
            else canonical_identifier(self.config.default_language)
        )

    # ------------------------------------------------------------------ 工具表
    def spec_for(self, tool: str) -> Any:
        """查工具表；未知工具一律拒绝（白名单，不是黑名单）。"""

        spec = self.tools.get(self.canonical_tool_name(tool))
        if spec is None:
            known = sorted(self.tools)
            raise AdapterEventError(
                f"未知工具 {tool!r}：adapter {self.agent_id} 的工具表里没有它，"
                f"拒绝在未知执行语义下放行（已登记：{known}）；"
                "升级 Agent 后必须先更新 manifest 的工具表并重新审核"
            )
        return spec

    def canonical_tool_name(self, tool: str) -> str:
        """把 Agent 侧的工具名解析成平台侧的规范名（未登记的名字原样返回）。

        未登记的名字不在这里报错：spec_for 才是白名单的判定点，
        这样"未知工具"的报错信息里出现的仍然是 Agent 实际发出的名字。
        """

        token = str(tool).strip()
        return self._by_vendor.get(token, token)

    def tool_names(self) -> Tuple[str, ...]:
        return tuple(sorted(self.tools))

    def outbound_tools(self) -> Tuple[str, ...]:
        return tuple(
            sorted(
                name
                for name, spec in self.tools.items()
                if spec.direction is Direction.OUTBOUND
            )
        )

    # ------------------------------------------------------------------ 统一接口
    def to_policy_event(
        self, raw_event: Any, *, workspace: Optional[Path] = None
    ) -> AgentEvent:
        """原始事件 → 规范事件。子类实现 `_build_event`，公共校验在这里。"""

        if not isinstance(raw_event, Mapping):
            raise AdapterEventError(
                f"{self.agent_id} 的原始事件必须是映射，得到 {type(raw_event).__name__}"
            )
        # 子类可以选择接收 workspace：钩子类 Agent 的原始路径需要在构造事件时
        # 就按"本次判定的工作区"解析（否则一条路径会先按配置默认值被规范化，
        # 逃逸就变成了静默的"相对路径"）。不支持该参数的子类保持原签名。
        try:
            event = self._build_event(raw_event, workspace=workspace)  # type: ignore[call-arg]
        except TypeError as error:
            if "workspace" not in str(error):
                raise
            event = self._build_event(raw_event)
        if not isinstance(event, AgentEvent):
            raise AdapterEventError(
                f"{self.agent_id}._build_event 必须返回 AgentEvent，得到 {type(event).__name__}"
            )
        if event.agent_id != self.agent_id:
            raise AdapterEventError(
                f"事件自称的 agent_id {event.agent_id!r} 与 Adapter {self.agent_id!r} 不一致："
                "Agent 身份由装配处钉死，不得由载荷自称"
            )
        if event.event_type not in self.manifest.event_types:
            raise AdapterEventError(
                f"{self.agent_id} 不支持事件 {event.event_type.value!r}；"
                f"能力声明里的事件为 {[item.value for item in self.manifest.event_types]}"
            )
        self.validate_event(event, workspace=workspace)
        return event

    def validate_event(
        self, event: AgentEvent, *, workspace: Optional[Path] = None
    ) -> None:
        """事件级校验：工具、操作与路径范围。失败关闭。"""

        if event.event_type in (
            EventType.TOOL_PRE_EXECUTE,
            EventType.TOOL_POST_EXECUTE,
        ):
            if not event.tool:
                raise AdapterEventError(
                    f"{event.event_type.value} 事件缺少工具名：工具是安全关键字段，不得猜测"
                )
            spec = self.spec_for(event.tool)
            if (
                event.operation is not None
                and spec.operation is not None
                and event.operation is not spec.operation
            ):
                raise AdapterEventError(
                    f"工具 {event.tool!r} 的 operation 必须是 manifest 已审核的 "
                    f"{spec.operation.value!r}，事件自报 {event.operation.value!r} 不可信"
                )
            operation = spec.operation or event.operation
            if operation is None:
                raise AdapterEventError(
                    f"工具 {event.tool!r} 没有受控操作：方向为 {spec.direction.value} 的工具"
                    "必须由 manifest 或事件显式给出 operation"
                )
            if spec.path_field is not None and event.path is None:
                field = spec.path_field
                raise AdapterEventError(
                    f"工具 {event.tool!r} 需要参数 {field!r}（路径是安全关键字段）："
                    "缺失时不得猜测路径，按失败策略拒绝"
                )
            if event.path is not None:
                # 路径归一化必须在这里就做一次：越界、绝对路径或 ".." 逃逸
                # 都要在"事件合法"这一步被拒绝，而不是留到构上下文时才发现。
                self.canonical_path(event, workspace=workspace)

    def raw_path_base(self, event: AgentEvent) -> Optional[str]:
        """事件里声明的"路径相对哪个目录解析"（钩子类 Agent 的会话 cwd）。

        默认 None：路径本身就是仓库相对路径（规范事件）。钩子类 Adapter 覆盖它，
        返回会话工作目录。返回 None 时以**本次判定的工作区**为基准解析，
        因此"相对哪里"永远唯一，且永远不会因为配置默认值而放宽范围。
        """

        return None

    def canonical_path(
        self, event: AgentEvent, *, workspace: Optional[Path] = None
    ) -> Optional[str]:
        """归一化后的目标路径（`.` 表示工作区根）。

        纯函数且幂等：返回值本身已是规范化路径，再次传入结果不变。
        """

        if event.path is None:
            return None
        anchor = self.workspace if workspace is None else Path(workspace).resolve()
        base = self.raw_path_base(event)
        return normalize_event_path(
            event.path, workspace=anchor, path_base=Path(base) if base else anchor
        )

    def canonical_operation(self, event: AgentEvent) -> Optional[Operation]:
        if event.tool is None:
            return event.operation
        specification = self.spec_for(event.tool)
        if specification.operation is not None:
            return specification.operation
        return event.operation

    def to_policy_context(
        self, event: AgentEvent, *, workspace: Optional[Path] = None
    ) -> PolicyContext:
        """规范事件 → 核心 PolicyContext。

        只搬运显式字段：layer 必须有声明结果，language 未知就写 null（让规则在
        `skipped_rules` 里说明原因），principal 只来自配置，绝不从事件内容推断。
        """

        file = self.canonical_path(event, workspace=workspace)
        if file is None:
            # 没有文件维度的动作（执行类工具）：以工作区根为范围，规则按 layer 匹配。
            file = "."
            layer = self.layer_for(file) or (
                None
                if self.config.default_layer is None
                else canonical_identifier(self.config.default_layer)
            )
        else:
            layer = self.layer_for(file)
        if layer is None:
            raise AdapterEventError(
                f"路径 {file} 没有声明 layer 映射：layer 是安全关键字段，Adapter 不得猜测。"
                "请在 adapter 配置的 layers 里补充 pattern → layer，或显式声明 default_layer"
            )

        language = self.language_for(file)
        if language is None and self._languages and self.config.default_language is None:
            raise AdapterEventError(
                f"路径 {file} 没有命中 languages 映射；请补充规则或显式声明 default_language"
            )

        dependencies = event.payload.get("dependencies") or ()
        if isinstance(dependencies, str):
            raise AdapterEventError("payload.dependencies 必须是序列，不能是字符串")
        if not isinstance(dependencies, (list, tuple, set, frozenset)):
            raise AdapterEventError("payload.dependencies 必须是序列")

        try:
            return PolicyContext(
                request_id=event.request_id,
                project=self.config.project,
                agent=event.agent_id,
                operation=self.canonical_operation(event),
                file=file,
                language=language,
                module=None,  # 刻意不推断：猜错模块会让规则在错误范围生效
                layer=layer,
                task=None,
                dependencies=tuple(str(item) for item in dependencies),
                git_diff=None,
                principal=self.principal_for(event),
                trace_id=event.trace_id,
            )
        except PolicyContextError:
            raise
        except Exception as error:  # pydantic ValidationError
            raise AdapterEventError(f"PolicyContext 构造失败：{error}") from error

    def principal_for(self, event: AgentEvent) -> Optional[Principal]:
        """主体只来自 Adapter 的显式声明。

        事件里的 `principal` 只用于**核对**：声明过主体时，事件自称的主体不一致就拒绝
        （否则 Agent 可以用消息里的"我是管理员"把自己的身份改掉）。
        """

        declared = self._principal
        if declared is None:
            if event.principal_subject is not None:
                raise AdapterEventError(
                    f"事件自称主体 {event.principal_subject!r}，但 adapter {self.agent_id} "
                    "没有声明 principal：主体不得由载荷自称，拒绝"
                )
            return None
        if event.principal_subject is not None and (
            canonical_identifier(event.principal_subject) != canonical_identifier(declared.subject)
        ):
            raise AdapterEventError(
                "事件自称的主体与 Adapter 声明的主体不一致：主体是授权输入，不接受载荷改写"
            )
        return declared

    def to_agent_response(self, decision: Any, *, event: Optional[AgentEvent] = None) -> Any:
        """工厂方法：具体响应由子类 `response_from_decision` 决定形态。"""

        return self.response_from_decision(decision, event=event)

    def response_from_decision(self, decision: Any, *, event: Optional[AgentEvent] = None) -> Any:
        raise NotImplementedError

    # ------------------------------------------------------------------ 子类接口
    def _build_event(self, raw_event: Mapping[str, Any]) -> AgentEvent:
        raise NotImplementedError(
            f"{type(self).__name__} 必须实现 _build_event：Adapter 只做协议转换，"
            "没有默认实现就不会有'看起来能用但什么都没做'的 Adapter"
        )


class AdapterDescriptor(BaseModel):
    """支持矩阵的一行：这个 Agent 到底受什么程度的治理。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_id: str
    agent_version: str
    display_name: str
    protocol: str
    protocol_version: str
    fixtures: Tuple[str, ...] = ()
    enforcement: EnforcementLevel
    requested_enforcement: Optional[EnforcementLevel] = None
    downgraded: bool = False
    ceiling_reasons: Tuple[str, ...] = ()
    approved: bool = False
    manifest_digest: str
    blocking: BlockingCapability
    approval: ApprovalCapability
    pre_hook: ParticipantCapability
    post_hook: ParticipantCapability
    event_types: Tuple[str, ...]
    tools: Tuple[str, ...] = ()
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.model_dump_json())


class AdapterList(BaseModel):
    """注册表加载结果：adapter → 描述符，附注册表级元数据。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    descriptors: Tuple[AdapterDescriptor, ...] = ()
    approved_path: Optional[str] = None
    approved_schema_version: Optional[str] = None
    reviewed_by: Optional[str] = None
    approved_at: Optional[str] = None

    def get(self, agent_id: str) -> AdapterDescriptor:
        for item in self.descriptors:
            if item.agent_id == agent_id:
                return item
        raise RegistryError(f"支持矩阵里没有 Agent {agent_id!r}")

    @property
    def ids(self) -> Tuple[str, ...]:
        return tuple(item.agent_id for item in self.descriptors)

    def governed(self) -> Tuple[AdapterDescriptor, ...]:
        """真正受治理的 Agent（完整 enforcement）。"""

        return tuple(
            item for item in self.descriptors if item.enforcement is EnforcementLevel.FULL
        )

    def read_only(self) -> Tuple[AdapterDescriptor, ...]:
        return tuple(
            item
            for item in self.descriptors
            if item.enforcement is EnforcementLevel.READ_ONLY
        )

    def unsupported(self) -> Tuple[AdapterDescriptor, ...]:
        return tuple(
            item
            for item in self.descriptors
            if item.enforcement is EnforcementLevel.UNSUPPORTED
        )

    def refused_tools(self, agent_id: str) -> Tuple[str, ...]:
        """该 Agent 在只读上限下不得执行的工具（写类 / 执行类）。"""

        descriptor = self.get(agent_id)
        if descriptor.enforcement is EnforcementLevel.FULL:
            return ()
        return descriptor.tools


def manifest_digest(manifest: AdapterManifest) -> str:
    """能力声明的身份：稳定序列化后取 sha256（与加载顺序、文件排版无关）。"""

    payload = manifest.model_dump_json(exclude_none=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def approved_digest(spec: AdapterSpec) -> str:
    return manifest_digest(spec.to_manifest(path=Path("manifest.yaml")))


class AdapterRegistry:
    """`adapters/` 目录的加载器：manifest + approved 哈希 + 支持矩阵。

    加载是**原子**的：任何一份 manifest 不合法、或与已审核哈希不一致，
    都让整次加载失败——不允许"一部分 Adapter 先接进来"。
    """

    def __init__(
        self,
        manifests: Sequence[AdapterManifest],
        *,
        approved: Mapping[str, Any] | None = None,
        approved_path: Optional[Path] = None,
        sources: Mapping[str, Path] | None = None,
    ) -> None:
        self.manifests = {item.agent_id: item for item in manifests}
        self._sources = dict(sources or {})
        self.approved = dict(approved or {})
        self.approved_path = approved_path

    # ------------------------------------------------------------------ 加载
    @classmethod
    def load(
        cls,
        root: Path | str,
        *,
        approved_path: Optional[Path | str] = None,
        require_approval: bool = True,
    ) -> "AdapterRegistry":
        directory = Path(root)
        if not directory.is_dir():
            raise RegistryError(f"adapter 目录不存在：{directory}")

        manifests: list[AdapterManifest] = []
        sources: dict[str, Path] = {}
        for path in sorted(directory.glob("*/manifest.yaml")):
            spec = _load_spec(path)
            manifest = spec.to_manifest(path=path)
            if manifest.agent_id in {item.agent_id for item in manifests}:
                raise RegistryError(f"{path}: agent_id {manifest.agent_id!r} 重复声明")
            manifests.append(manifest)
            sources[manifest.agent_id] = path

        if not manifests:
            raise RegistryError(f"{directory} 下没有任何 */manifest.yaml：没有可用的 Adapter")

        approved: Mapping[str, Any] = {}
        snapshot: Optional[Path] = None
        if approved_path is not None:
            snapshot = Path(approved_path)
            try:
                approved = _load_approved(snapshot)
            except RegistryError:
                if require_approval:
                    raise
                # 未审核模式（审核前的本地检查 / matrix）：没有清单不算意外，
                # 但每一行都会被标成未审核，绝不会被误当成"已审核"。
                approved = {}

        registry = cls(
            manifests,
            approved=approved,
            approved_path=snapshot,
            sources=sources,
        )
        if require_approval:
            registry.check_approved()
        return registry

    # ------------------------------------------------------------------ 支持矩阵
    def descriptors(self) -> Tuple[AdapterDescriptor, ...]:
        rows: list[AdapterDescriptor] = []
        for agent_id in sorted(self.manifests):
            manifest = self.manifests[agent_id]
            ceiling = ceiling_from_capabilities(manifest)
            digest = manifest_digest(manifest)
            approved = self.approved.get("adapters", {}).get(agent_id) or {}
            is_approved = approved.get("manifest_digest") == digest
            level = ceiling.level
            reasons = list(ceiling.reasons)
            if not is_approved:
                # 未审核 = 不可使用，但**不改变能力上限**：
                # "能力不足"（unsupported）与"没审核过"是两条不同的轴，
                # 混在一起会让支持矩阵说不清某个 Agent 到底差在哪。
                # 未审核的后果由装配处承担：load_adapter 拒绝接入、
                # check_approved() 让整次加载失败（失败关闭）。
                reasons.append(
                    "manifest 与已审核哈希不一致或尚未审核：改能力声明必须重新审核"
                    "（python -m adapters.cli approve --reviewer <name>）"
                )
            rows.append(
                AdapterDescriptor(
                    agent_id=agent_id,
                    agent_version=manifest.agent_version,
                    display_name=manifest.display_name,
                    protocol=manifest.protocol,
                    protocol_version=manifest.protocol_version,
                    fixtures=manifest.fixtures,
                    enforcement=level,
                    requested_enforcement=manifest.requested_enforcement,
                    downgraded=ceiling.downgraded,
                    ceiling_reasons=tuple(reasons),
                    approved=is_approved,
                    manifest_digest=digest,
                    blocking=manifest.blocking,
                    approval=manifest.approval,
                    pre_hook=manifest.pre_hook,
                    post_hook=manifest.post_hook,
                    event_types=tuple(item.value for item in manifest.event_types),
                    tools=tuple(sorted(item.name for item in manifest.tools)),
                    notes=manifest.notes,
                )
            )
        return tuple(rows)

    def as_list(self) -> AdapterList:
        return AdapterList(
            descriptors=self.descriptors(),
            approved_path=None if self.approved_path is None else self.approved_path.as_posix(),
            approved_schema_version=self.approved.get("schema_version"),
            reviewed_by=self.approved.get("reviewed_by"),
            approved_at=self.approved.get("approved_at"),
        )

    def check_approved(self) -> None:
        """任何一份 manifest 与已审核哈希不一致就整体失败（失败关闭）。"""

        drift = [
            row.agent_id
            for row in self.descriptors()
            if not row.approved
        ]
        if drift:
            raise RegistryError(
                "adapter 能力声明与已审核哈希不一致："
                + ", ".join(sorted(drift))
                + "；先重新审核并更新 "
                + (str(self.approved_path) if self.approved_path is not None else "approved.json")
            )

    def lookup(self, name: str) -> Optional[str]:
        """按 agent_id 或台账别名（ledger_alias）找规范 agent_id。

        一个部署可以同时跑多份同型号 Agent（例如两个 dsh 实例）。它们共用一份
        manifest，但命名空间必须不同；调用方用别名来寻址，规范名仍然是 agent_id。
        """

        token = str(name).strip()
        if token in self.manifests:
            return token
        normalized = token.lower()
        for agent_id, manifest in self.manifests.items():
            if manifest.ledger_alias == normalized:
                return agent_id
        return None

    def namespaces(self) -> Tuple[str, ...]:
        """全部可寻址的命名空间：agent_id 与别名各占一个。"""

        names: list[str] = []
        for agent_id in sorted(self.manifests):
            names.append(agent_id)
            alias = self.manifests[agent_id].ledger_alias
            if alias and alias != agent_id:
                names.append(alias)
        return tuple(sorted(names))

    def manifest(self, agent_id: str) -> AdapterManifest:
        manifest = self.manifests.get(agent_id)
        if manifest is None:
            raise RegistryError(f"未知 Agent {agent_id!r}：注册表里没有它")
        return manifest

    def manifest_path(self, agent_id: str) -> Path:
        return self._sources.get(agent_id, Path("<unknown>"))

    def supports(self, agent_id: str, event_type: EventType) -> bool:
        return event_type in self.manifest(agent_id).event_types


def _load_spec(path: Path) -> AdapterSpec:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise RegistryError(f"{path}: 无法读取 ({error})") from error
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise RegistryError(f"{path}: YAML 解析失败：{error}") from error
    if not isinstance(document, Mapping):
        raise RegistryError(f"{path}: 顶层必须是映射，得到 {type(document).__name__}")
    try:
        return AdapterSpec.model_validate(dict(document))
    except ValidationError as error:
        failure = RuleValidationError.from_pydantic(error, model_name=f"adapter manifest {path}")
        raise RegistryError(str(failure)) from error


def _load_approved(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        raise RegistryError(
            f"已审核的 adapter 清单不存在：{path.name}；能力声明没有审核记录就不能接入"
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RegistryError(f"{path}: 已审核清单不可读 ({error})") from error
    if not isinstance(document, Mapping):
        raise RegistryError(f"{path}: 顶层必须是映射")
    version = document.get("schema_version")
    if version != APPROVED_SCHEMA_VERSION:
        raise RegistryError(
            f"{path}: 未知已审核清单版本 {version!r}；本实现只接受 {APPROVED_SCHEMA_VERSION}"
        )
    adapters = document.get("adapters")
    if not isinstance(adapters, Mapping) or not adapters:
        raise RegistryError(f"{path}: adapters 必须是非空映射")
    return document
