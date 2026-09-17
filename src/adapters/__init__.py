"""Agent Adapter 命名空间：把各家 Agent Runtime 的事件翻译成核心协议。

适配器可以依赖具体 Agent 的**线协议**，但只能输出核心协议；
核心层（src/policy）不得反过来导入这里的任何模块。
"""

from __future__ import annotations

__all__: list[str] = []
