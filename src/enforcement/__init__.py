"""Phase 4 受控执行层（Tool Enforcement）。

职责：把"给 Agent 规范建议"升级成"所有受控工具都经过执行前授权与执行后验证"。

    Tool Registry（数据）
        ↓ 解析工具身份、风险级别、参数表、权限、post-check、预算
    Action Request（不可变、带 action_hash）
        ↓
    Pre-execute Policy（注册表 / 主体 / 权限 / 参数 / 白名单 / 审批 / 规则 / 限流 / 审计）
        ↓ allow + 短时效 grant
    Controlled Executor（校验绑定、单次消费、幂等、驱动执行一次）
        ↓
    Post-execute Validation（文件哈希与 diff、退出码、确定性验证器、必要时回滚）
        ↓
    Audit Chain（request → retrieval → proposal → action → pre → exec → post → final）

核心层约束：本包只依赖标准库、pydantic、PyYAML 与 policy 核心模型，
不导入任何 Agent SDK、Web 框架或向量库。
"""

from __future__ import annotations

from .models import ENFORCEMENT_SCHEMA_VERSION, REGISTRY_SCHEMA_VERSION

__all__ = ["ENFORCEMENT_SCHEMA_VERSION", "REGISTRY_SCHEMA_VERSION"]
