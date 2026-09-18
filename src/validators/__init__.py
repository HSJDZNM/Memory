"""Phase 5 代码验证器：把代码与工具输出变成确定性证据。

分层：

- policy.evidence 定义证据协议（核心端口），policy.checkers 决定"证据怎么变成违规"；
- 本包是端口的实现：内置验证器（源码 / AST / 依赖图 / docstring）、外部工具适配器
  （Ruff / 类型检查器 / pytest）、测试选择，以及把它们聚合成一次运行的流水线；
- 本包只依赖标准库、pydantic 与核心层，不导入任何 Agent SDK 或 Web 框架。

用法：

    python -m validators.cli check <file>      # 只产出证据（不判定）
    python -m validators.cli pipeline <file>   # 证据 + Policy Engine 判定
    python -m validators.cli registry          # 验证器注册表事实
"""

from __future__ import annotations

__all__ = ["EVIDENCE_SCHEMA_VERSION", "PIPELINE_SCHEMA_VERSION"]

# 证据协议的版本由核心层定义，这里只是转发，避免两处口径漂移。
from policy.evidence import EVIDENCE_SCHEMA_VERSION  # noqa: E402

# 一次流水线运行的报告版本（validators.cli --json 的顶层载荷）。
PIPELINE_SCHEMA_VERSION = "1.0"
