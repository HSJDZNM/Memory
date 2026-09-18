"""Agent Adapter 命名空间：把各家 Agent Runtime 的事件翻译成核心协议（Phase 6）。

适配器可以依赖具体 Agent 的**线协议**，但只能输出核心协议；
核心层（src/policy）不得反过来导入这里的任何模块。

这一层的边界非常清楚：

- **只做协议转换**：把各 Agent 的原始事件翻译成规范事件 `AgentEvent`，
  再把判定结果翻译回该 Agent 能理解的响应；判定本身仍然只发生在 `policy.engine`；
- **差异留在数据里**：事件名、工具名、钩子形态、阻断能力、审批能力都写在
  `adapters/<agent_id>/manifest.yaml`，并受 `adapters/approved.json` 的哈希审核约束；
- **能力不足显式失败**：拦不住动作的 Agent 不会被标记成完整 enforcement，
  而是在接入时就得到 `read_only` 上限，受治理动作一律拒绝。

这里刻意不导入任何 Agent SDK：Adapter 只依赖线协议（stdin / JSON / 退出码），
因此可以在没有安装任何 Agent 的环境里跑完整的一致性套件。
"""

from __future__ import annotations

from .base import (
    APPROVED_SCHEMA_VERSION,
    DEFAULT_ADAPTERS_ROOT,
    DEFAULT_APPROVED_PATH,
    Adapter,
    AdapterConfig,
    AdapterDescriptor,
    AdapterList,
    AdapterRegistry,
    AdapterSpec,
    RegistryError,
    SupportCeiling,
    approved_digest,
    ceiling_from_capabilities,
    manifest_digest,
)
from .event_adapter import EventAdapter
from .json_adapter import JsonAdapter
from .models import (
    ADAPTER_MANIFEST_SCHEMA_VERSION,
    CANONICAL_EVENT_SCHEMA_VERSION,
    EVENT_TYPES,
    SUPPORTED_CANONICAL_VERSIONS,
    AdapterEventError,
    AdapterManifest,
    AgentEvent,
    AgentResponse,
    AgentTool,
    ApprovalCapability,
    BlockingCapability,
    Capability,
    Direction,
    EnforcementLevel,
    EventType,
    HookNames,
    ManifestError,
    ParticipantCapability,
    ParticipantKind,
    ResponseKind,
    event_payload_digest,
    normalize_event_path,
    parse_canonical_event,
)
from .runtime import (
    AGENT_RUNTIME_SCHEMA_VERSION,
    DEFAULT_BREAKER_LIMIT,
    REASON_CODES,
    AgentRuntime,
    RuntimeOutcome,
    TraceRegistry,
    sanitize_message,
)

__all__ = [
    "ADAPTER_MANIFEST_SCHEMA_VERSION",
    "AGENT_RUNTIME_SCHEMA_VERSION",
    "APPROVED_SCHEMA_VERSION",
    "CANONICAL_EVENT_SCHEMA_VERSION",
    "DEFAULT_ADAPTERS_ROOT",
    "DEFAULT_APPROVED_PATH",
    "DEFAULT_BREAKER_LIMIT",
    "EVENT_TYPES",
    "REASON_CODES",
    "SUPPORTED_CANONICAL_VERSIONS",
    "Adapter",
    "AdapterConfig",
    "AdapterDescriptor",
    "AdapterEventError",
    "AdapterList",
    "AdapterManifest",
    "AdapterRegistry",
    "AdapterSpec",
    "AgentEvent",
    "AgentResponse",
    "AgentRuntime",
    "AgentTool",
    "ApprovalCapability",
    "BlockingCapability",
    "Capability",
    "Direction",
    "EnforcementLevel",
    "EventAdapter",
    "EventType",
    "HookNames",
    "JsonAdapter",
    "ManifestError",
    "ParticipantCapability",
    "ParticipantKind",
    "RegistryError",
    "ResponseKind",
    "RuntimeOutcome",
    "SupportCeiling",
    "TraceRegistry",
    "approved_digest",
    "ceiling_from_capabilities",
    "event_payload_digest",
    "manifest_digest",
    "normalize_event_path",
    "parse_canonical_event",
    "sanitize_message",
]
