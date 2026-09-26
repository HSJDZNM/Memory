"""事件型 Adapter：把"钩子线协议"的原始事件翻译成规范事件。

绝大多数 Agent 的扩展点是**外部命令钩子**：运行时不 Import 我们的代码，
而是把事件 JSON 写到子进程的 stdin，再按退出码决定放行还是阻断
（dsh 是 `exit 0` 放行 / `exit 2` 阻断）。Phase 2 的 dsh Adapter 与 Phase 6 的
第二个协议消费者都属于这一类，因此公共部分写在这里，各 Agent 只提供数据：

- 事件名与载荷字段名 → manifest 的 `hooks`（`HookNames`）；
- 事件名 → 规范事件类型 → 子类的 `AGENT_WIRE`；
- 工具名 → 受控操作与路径字段 → manifest 的 `tools`（`AgentTool`，含 Agent 侧别名）。

这一层**不做任何判定**：它只回答"这条原始事件对应哪个规范事件、涉及哪个工具、
目标路径是什么"。判定全部在 `policy.engine`，授权全部在 `enforcement`。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from policy.models import ValidationResult

from .base import Adapter
from .models import (
    AdapterEventError,
    AgentEvent,
    AgentResponse,
    EventType,
    event_payload_digest,
)

__all__ = ["EXIT_ALLOW", "EXIT_BLOCK", "EventAdapter", "hook_command_result"]

# 钩子协议：0 = 放行；2 = 阻断（stderr 即阻断理由）。没有第三种"警告"出口。
EXIT_ALLOW = 0
EXIT_BLOCK = 2


def hook_command_result(
    response: Any, *, allow_exit: int = EXIT_ALLOW, block_exit: int = EXIT_BLOCK
) -> Mapping[str, Any]:
    """把判定翻译成"钩子命令结果"：退出码 + 给 Agent 的文本。

    这是**外部命令钩子类 Agent 唯一需要的响应形态**，因此它属于公共层：
    "阻断 = 退出码 2"这条语义如果每个 Adapter 各写一遍，就一定会有一次写错。
    """

    from policy.models import Decision

    if isinstance(response, AgentResponse):
        payload = response
    elif isinstance(response, ValidationResult):
        payload = AgentResponse(
            agent_id="unknown",
            request_id=response.request_id,
            event_id="",
            decision=response.decision,
            reason_code=response.decision.value,
            message="",
            violations=tuple(item.canonical_id for item in response.violations),
            matched_rules=tuple(response.matched_rules),
            trace_id=response.trace_id,
        )
    else:
        raise AdapterEventError(
            f"hook_command_result 只接受 AgentResponse 或 ValidationResult，"
            f"得到 {type(response).__name__}"
        )

    allowed = payload.decision in (Decision.ALLOW, Decision.ALLOW_WITH_WARNINGS)
    verdict = "ALLOWED" if allowed else "BLOCKED"
    lines = [f"[policy] {verdict} {payload.event_id} ({payload.reason_code})"]
    if payload.message:
        lines.append(f"detail: {payload.message}")
    for item in payload.violations:
        lines.append(f"rule: {item}")
    for item in payload.remediation:
        lines.append(f"expected: {item}")
    lines.append(f"schema: {payload.schema_version}")
    return {
        "exit_code": allow_exit if allowed else block_exit,
        "stdout": "",
        # 放行时保持 stderr 干净：dsh 只在 exit 0 且 stdout 以 "{" 开头时才解析 JSON，
        # 提前写文本会被误当成结构化输出。
        "stderr": "" if allowed else chr(10).join(lines),
        "response": payload,
    }


class EventAdapter(Adapter):
    """钩子线协议 Adapter 的公共实现。

    `AGENT_WIRE` 把 Agent 侧的事件名映射到规范事件类型。它是类属性而不是配置项，
    因为"这个 Agent 的事件名是什么意思"是**协议知识**，
    必须和这份协议一起被审核（manifest 里的 `hooks` 只描述字段名）。
    """

    AGENT_WIRE: Mapping[str, EventType] = {
        "PreToolUse": EventType.TOOL_PRE_EXECUTE,
        "PostToolUse": EventType.TOOL_POST_EXECUTE,
    }

    def raw_path_base(self, event: AgentEvent) -> Optional[str]:
        """钩子类的路径基准是**会话 cwd**（与 dsh 的 agent.session.header.cwd 同口径）。

        没有 cwd 时返回 None，由公共层用本次判定的工作区解析。
        """

        value = event.payload.get("cwd")
        return value if isinstance(value, str) and value.strip() else None

    def _build_event(self, raw_event: Mapping[str, Any]) -> AgentEvent:
        hooks = self.manifest.hooks
        event_name = _require_text(
            raw_event.get("hook_event_name"), where="hook_event_name"
        )
        event_type = self.AGENT_WIRE.get(event_name)
        if event_type is None:
            known = sorted(self.AGENT_WIRE)
            raise AdapterEventError(
                f"未支持的 hook 事件 {event_name!r}：{self.agent_id} 只治理 {known}，"
                "未识别事件不得静默放行"
            )

        session_id = _require_text(raw_event.get(hooks.session_field), where=hooks.session_field)
        call_id = _require_text(raw_event.get(hooks.call_id_field), where=hooks.call_id_field)
        tool_input = raw_event.get(hooks.input_field)
        if tool_input is None:
            tool_input = {}
        if not isinstance(tool_input, Mapping):
            raise AdapterEventError(
                f"载荷字段 {hooks.input_field} 必须是映射（工具参数），"
                f"得到 {type(tool_input).__name__}"
            )

        cwd = _optional_text(raw_event.get(hooks.cwd_field))

        tool: Optional[str] = None
        payload: dict[str, Any] = {}
        if event_type in (EventType.TOOL_PRE_EXECUTE, EventType.TOOL_POST_EXECUTE):
            vendor_tool = _require_text(raw_event.get(hooks.tool_field), where=hooks.tool_field)
            tool = self.canonical_tool_name(vendor_tool)
            spec = self.spec_for(tool)
            payload = self._tool_payload(spec, tool_input)
        else:
            payload["request"] = {
                str(key): _summarize(tool_input[key]) for key in sorted(tool_input, key=str)
            }

        if cwd is not None:
            # cwd 只用于解析路径（hook-command 的线协议语义），
            # 它不是授权输入：范围仍然由受控工作区决定。
            payload["cwd"] = cwd
        if event_type is EventType.TOOL_POST_EXECUTE:
            payload["result_present"] = raw_event.get("tool_response") is not None

        return AgentEvent(
            schema_version=_require_text(
                raw_event.get("schema_version") or "1.0", where="schema_version"
            ),
            event_id=f"{session_id}:{call_id}",
            event_type=event_type,
            request_id=f"{session_id}:{call_id}",
            agent_id=self.agent_id,
            agent_version=self.agent_version,
            payload_digest=event_payload_digest(
                {str(key): tool_input[key] for key in sorted(tool_input, key=str)}
            ),
            occurred_at=str(raw_event.get("occurred_at") or ""),
            input_fields=tuple(sorted(str(key) for key in tool_input)),
            trace_id=_optional_text(raw_event.get("trace_id")),
            parent_trace_id=_optional_text(raw_event.get("parent_trace_id")),
            principal_subject=_optional_text(raw_event.get("subject")),
            tool=tool,
            payload=payload,
        )

    def _tool_payload(self, spec: Any, tool_input: Mapping[str, Any]) -> dict[str, Any]:
        """只搬运受控字段：路径与参数。其余原始字段留在摘要里，不进模型。"""

        payload: dict[str, Any] = {}
        if spec.path_field is not None:
            raw_path = tool_input.get(spec.path_field)
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise AdapterEventError(
                    f"工具参数缺少 {spec.path_field!r}：路径是安全关键字段，"
                    "不得猜测（缺失即拒绝执行）"
                )
            payload["path"] = raw_path.strip()
        payload["params"] = {str(key): tool_input[key] for key in sorted(tool_input, key=str)}
        proposed = tuple(
            tool_input[field]
            for field in spec.proposed_fields
            if isinstance(tool_input.get(field), str)
        )
        if proposed:
            # payload 只带 text：依赖是核心上下文的维度，由公共层在 language 解析出来
            # 之后统一提取（base.Adapter.to_policy_context），跨 Adapter 的等价事件
            # 才会得到等价的 PolicyContext。
            payload["text"] = chr(10).join(proposed)
        return payload

    # ------------------------------------------------------------------ 响应
    def response_from_decision(
        self, decision: Any, *, event: Optional[AgentEvent] = None
    ) -> Mapping[str, Any]:
        return hook_command_result(decision)

    def to_command_result(self, response: Any) -> Mapping[str, Any]:
        return hook_command_result(response)


def _require_text(value: Any, *, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdapterEventError(f"事件字段 {where} 必须是非空字符串，得到 {value!r}")
    return value.strip()


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AdapterEventError(f"事件字段必须是字符串或缺失，得到 {type(value).__name__}")
    normalized = value.strip()
    return normalized or None


def _summarize(value: Any) -> Any:
    """非工具事件的载荷只留"有没有值、是什么类型"，不留内容。"""

    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if isinstance(value, str):
        return f"<{len(value)} chars>"
    if isinstance(value, Mapping):
        return {str(key): _summarize(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [f"<{len(value)} items>"]
    return f"<{type(value).__name__}>"
