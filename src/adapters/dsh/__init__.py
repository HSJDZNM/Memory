"""dsh Adapter：dsh Hook 事件与核心策略协议之间的双向翻译。

- adapter：纯映射（dsh Event → PolicyEvent / PolicyContext），无副作用；
- hooks：pre-execute Hook（策略判定、受控执行、审计与失败关闭），
  以命令方式运行：python -m adapters.dsh.hooks --config <adapter 配置>。

这里刻意只导出 adapter 的符号：hooks 是进程入口，若在包初始化时被导入，
python -m adapters.dsh.hooks 会触发 runpy 的 "found in sys.modules" 警告，
而 dsh 会把 stderr 记进 hook/result——放行路径必须保持安静。

调查结论与接线方式见同目录 README.md。
"""

from __future__ import annotations

from .adapter import (
    DSH_AGENT_ID,
    HOOK_EVENT_PRE_TOOL_USE,
    SUPPORTED_HOOK_EVENTS,
    TOOL_TABLE,
    AdapterConfig,
    AdapterDecision,
    DshEventError,
    PolicyEvent,
    ToolKind,
    load_config,
    to_policy_context,
    to_policy_event,
)

__all__ = [
    "DSH_AGENT_ID",
    "HOOK_EVENT_PRE_TOOL_USE",
    "SUPPORTED_HOOK_EVENTS",
    "TOOL_TABLE",
    "AdapterConfig",
    "AdapterDecision",
    "DshEventError",
    "PolicyEvent",
    "ToolKind",
    "load_config",
    "to_policy_context",
    "to_policy_event",
]
