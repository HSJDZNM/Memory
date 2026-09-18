"""Generic JSON Adapter：与具体 Agent 无关的协议示例与测试工具。

计划 §3 的要求是"实现一个 JSON Adapter，作为协议示例和测试工具"：它不对应任何具体
产品，但能证明**第三方只要生成标准事件就能接入**——不需要改核心层，也不需要装 SDK。

它消费的是 `AgentEvent` 的线上形态（`parse_canonical_event` 的输入），
因此它同时也是"规范事件长什么样"的可执行文档：

    {
      "schema_version": "1.0",
      "event_id": "req-1:call-1",
      "event_type": "tool.pre_execute",
      "request_id": "req-1",
      "agent_version": "third-party-0.9",
      "principal": {"subject": "local-user", "roles": ["developer"]},
      "tool": "write",
      "operation": "create",
      "payload": {"path": "src/shop/x.py", "params": {"content": "..."}}
    }

`agent_id` 由装配处钉死（manifest 里的 `agent_id`），载荷自称的一律被忽略：
否则请求方可以自称成另一个 Agent，跨 Agent 隔离就形同虚设。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from policy.models import Decision, RequiredAction, ValidationResult

from .base import Adapter
from .textfacts import proposed_dependencies
from .models import AgentEvent, AdapterEventError, parse_canonical_event

__all__ = ["JsonAdapter", "agent_response_from_decision"]


def agent_response_from_decision(decision: Any, *, event: Optional[AgentEvent] = None) -> dict[str, Any]:
    """把决策翻译成通用 JSON 响应（受控字段，不含内部信息）。"""

    if isinstance(decision, Mapping):
        payload = dict(decision)
    elif isinstance(decision, ValidationResult):
        payload = decision.to_decision_dict()
    else:
        raise AdapterEventError(
            f"agent_response_from_decision 只接受 ValidationResult 或映射，"
            f"得到 {type(decision).__name__}"
        )

    allowed = {
        "schema_version",
        "decision",
        "request_id",
        "trace_id",
        "matched_rules",
        "violations",
        "required_action",
        "policy_version",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise AdapterEventError(f"决策载荷出现未知字段 {unknown}：拒绝把未知协议翻译给 Agent")

    violations = payload.get("violations") or []
    if not isinstance(violations, (list, tuple)):
        raise AdapterEventError("决策载荷的 violations 必须是列表")

    required = payload.get("required_action")
    if required is not None:
        try:
            required = RequiredAction(required).value
        except ValueError:
            raise AdapterEventError(
                f"未知 required_action {required!r}：不接受未定义的审批动作"
            ) from None

    return {
        "schema_version": payload.get("schema_version"),
        "decision": payload.get("decision"),
        "request_id": payload.get("request_id"),
        "trace_id": payload.get("trace_id") or (None if event is None else event.trace_id),
        "matched_rules": list(payload.get("matched_rules") or []),
        "violations": [dict(item) for item in violations if isinstance(item, Mapping)],
        "required_action": required,
        "executable": payload.get("decision") in (Decision.ALLOW.value, Decision.ALLOW_WITH_WARNINGS.value),
    }


class JsonAdapter(Adapter):
    """规范事件的直接消费者：第三方 Adapter 的参考实现。"""

    def _build_event(self, raw_event: Mapping[str, Any]) -> AgentEvent:
        event = parse_canonical_event(raw_event, agent_id=self.agent_id)
        # 契约：payload.text 是"本次改动引入的文本"。依赖维度由平台统一提取，
        # 避免"同一语义的改动在不同 Adapter 里得到不同的 PolicyContext"。
        text = event.payload.get("text")
        if isinstance(text, str) and text and "dependencies" not in event.payload:
            payload = dict(event.payload)
            payload["dependencies"] = list(proposed_dependencies(text))
            object.__setattr__(event, "payload", payload)
        return event

    def validate_event(
        self, event: AgentEvent, *, workspace: Optional[Path] = None
    ) -> None:
        """工具名先按别名表归一，再走公共校验。"""

        if event.tool is not None:
            canonical = self.canonical_tool_name(event.tool)
            if canonical != event.tool:
                object.__setattr__(event, "tool", canonical)
        super().validate_event(event, workspace=workspace)

    def response_from_decision(
        self, decision: Any, *, event: Optional[AgentEvent] = None
    ) -> dict[str, Any]:
        return agent_response_from_decision(decision, event=event)
