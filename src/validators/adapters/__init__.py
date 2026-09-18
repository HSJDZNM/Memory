"""外部工具适配器：Ruff / 类型检查器 / pytest。

共同契约（Phase 5 计划书第 3 步）：工具版本与配置文件固定、参数来自 allowlist、工作目录与
超时显式、stdout/stderr 有上限、原始输出映射成统一证据，并且严格区分"工具缺失 / 崩溃 /
配置错误 / 输出非法"——任何一种都不是"没有发现问题"。
"""

from __future__ import annotations

from .base import AdapterResult, ToolError, probe_tool, run_tool, sanitize_text
from .mypy import run_mypy
from .pytest_runner import run_pytest
from .ruff import run_ruff

__all__ = [
    "AdapterResult",
    "ToolError",
    "probe_tool",
    "run_mypy",
    "run_pytest",
    "run_ruff",
    "run_tool",
    "sanitize_text",
]
