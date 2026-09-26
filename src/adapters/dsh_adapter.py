"""dsh Adapter：把 Phase 2 的 dsh 钩子映射接进 Phase 6 的统一接口。

它**复用** Phase 2 已经验证过的映射事实，而不是重写一遍：

- 工具表仍是 `adapters.dsh.adapter.TOOL_TABLE`（升级 dsh 必须先更新它并补契约测试）；
- 路径解析仍是同一条规则（相对 `cwd` 解析，逃出工作区即拒绝）；
- 只读工具的**范围校验**不会被降级掉（降级的只是授权链路）。

差异只在接口形态：Phase 2 直接产出 `PolicyEvent`；Phase 6 要求所有 Adapter 先产出
**规范事件 `AgentEvent`**，再由公共层构造 `PolicyContext`。因此这里做的是"翻译"，
不是"再实现一次"。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from .base import Adapter
from .event_adapter import hook_command_result
from .models import (
    AdapterEventError,
    AgentEvent,
    EventType,
    event_payload_digest,
    normalize_event_path,
)

__all__ = ["DshAdapter", "DSH_WIRE"]


# dsh 的线协议（0.1.5-rc.1，证据见 src/adapters/dsh/README.md）。
DSH_WIRE: Mapping[str, EventType] = {
    "PreToolUse": EventType.TOOL_PRE_EXECUTE,
    "PostToolUse": EventType.TOOL_POST_EXECUTE,
}


class DshAdapter(Adapter):
    """dsh 的钩子载荷 → 规范事件。"""

    def _build_event(
        self, raw_event: Mapping[str, Any], *, workspace: Optional[Path] = None
    ) -> AgentEvent:
        from .dsh.adapter import TOOL_TABLE, ToolKind

        event_name = _require_text(raw_event.get("hook_event_name"), where="hook_event_name")
        event_type = DSH_WIRE.get(event_name)
        if event_type is None:
            raise AdapterEventError(
                f"未支持的 dsh hook 事件 {event_name!r}：本 Adapter 只治理 "
                f"{sorted(DSH_WIRE)}，未识别事件不得静默放行"
            )

        session_id = _require_text(raw_event.get("session_id"), where="session_id")
        call_id = _require_text(raw_event.get("tool_use_id"), where="tool_use_id")
        tool = _require_text(raw_event.get("tool_name"), where="tool_name")
        tool_input = raw_event.get("tool_input")
        if not isinstance(tool_input, Mapping):
            raise AdapterEventError(
                f"dsh 事件字段 tool_input 必须是映射（工具参数），"
                f"得到 {type(tool_input).__name__}"
            )

        spec = TOOL_TABLE.get(tool)
        if spec is None:
            hint = (
                "（看起来像 MCP 工具：Phase 6 的声明式工具表会覆盖它）"
                if tool.startswith("mcp__")
                else ""
            )
            raise AdapterEventError(
                f"未知工具 {tool!r}{hint}：Adapter 工具表里没有它，"
                "拒绝在未知执行语义下放行。升级 dsh 后必须先更新"
                " src/adapters/dsh/adapter.py 的 TOOL_TABLE 并补契约测试"
            )

        cwd = _optional_text(raw_event.get("cwd"))
        payload: dict[str, Any] = {
            "params": {str(key): tool_input[key] for key in sorted(tool_input, key=str)}
        }
        if cwd is not None:
            # cwd 只用于把 pre-execute 阶段的**未解析路径**转成仓库相对路径。
            # 它不是授权输入：范围仍然由受控工作区决定，解析后照样做包含性检查。
            payload["cwd"] = cwd
        if spec.kind is ToolKind.WRITE:
            if spec.path_field is None:
                raise AdapterEventError(f"工具表内部不一致：{tool} 缺少 path_field")
            payload["path"] = _resolve(
                raw_event,
                spec.path_field,
                cwd=cwd,
                workspace=self.workspace if workspace is None else Path(workspace),
            )
            text = chr(10).join(
                tool_input[field]
                for field in spec.proposed_fields
                if isinstance(tool_input.get(field), str)
            )
            if text:
                # payload 只带 text：依赖由公共层在 language 解析出来之后统一提取
                # （base.Adapter.to_policy_context），三个 Adapter 不再各写一份。
                payload["text"] = text
        elif spec.kind is ToolKind.READ_ONLY:
            # 只读动作降级的只是授权链路，不是范围校验：读了什么必须能被证明。
            payload["path"] = _resolve(
                raw_event,
                spec.path_field,
                cwd=cwd,
                workspace=self.workspace if workspace is None else Path(workspace),
                allow_root=True,
            )
        # EXECUTE / NO_FILE 的动作没有文件维度：授权由 Phase 4 的受控链路负责。

        if event_type is EventType.TOOL_POST_EXECUTE:
            payload["result_present"] = raw_event.get("tool_response") is not None

        return AgentEvent(
            schema_version="1.0",
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
            operation=spec.operation,
            payload=payload,
        )

    def raw_path_base(self, event: AgentEvent) -> Optional[str]:
        """dsh 的 pre-execute 路径相对**会话 cwd** 解析（载荷里的 cwd）。

        没有 cwd 时返回 None，由公共层用本次判定的工作区解析：dsh 给的是
        原始字符串，"相对哪里"必须有唯一答案，而配置默认值不是那个答案。
        """

        value = event.payload.get("cwd")
        return value if isinstance(value, str) and value.strip() else None

    def response_from_decision(
        self, decision: Any, *, event: Optional[AgentEvent] = None
    ) -> Mapping[str, Any]:
        return hook_command_result(decision)


def _resolve(
    raw_event: Mapping[str, Any],
    field: Optional[str],
    *,
    cwd: Optional[str],
    workspace: Path,
    allow_root: bool = False,
) -> str:
    """把 dsh 的原始路径解析成仓库相对路径（越界即拒绝）。

    dsh 在 pre-execute 阶段给出的是未解析的原始字符串，解析基准是会话工作目录
    （载荷里的 cwd）。这里与 Phase 2 的 `_resolve_file` / `_resolve_read_scope`
    同口径，只是范围锚点由调用方显式给出。
    """

    if field is None:
        raise AdapterEventError("工具表内部不一致：缺少路径字段名")
    tool_input = raw_event.get("tool_input") or {}
    raw_path = tool_input.get(field) if isinstance(tool_input, Mapping) else None

    candidate: Optional[str] = None
    if isinstance(raw_path, str) and raw_path.strip():
        candidate = raw_path.strip()
    elif allow_root and cwd:
        candidate = cwd
    if candidate is None:
        raise AdapterEventError(
            "工具参数缺少目标路径：路径是安全关键字段，不得猜测（缺失即拒绝执行）"
        )

    # 基准是**会话 cwd**（载荷里就有），不是 adapter 配置里的默认工作区：
    # dsh 在 pre-execute 阶段给的是未解析的原始字符串，"相对哪里"必须用会话
    # 自己的事实回答。拒绝它的理由由 normalize_event_path 给出（绝对路径越界、
    # ".." 逃逸、空路径），这里不做任何"先规范化再看"的处理。
    base = Path(cwd) if cwd else workspace
    return normalize_event_path(candidate, workspace=workspace, path_base=base)


def _require_text(value: Any, *, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdapterEventError(f"dsh 事件字段 {where} 必须是非空字符串，得到 {value!r}")
    return value.strip()


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AdapterEventError(f"dsh 事件字段必须是字符串或缺失，得到 {type(value).__name__}")
    normalized = value.strip()
    return normalized or None
