"""Phase 7：Policy API —— 把已经稳定的核心能力服务化。

设计边界（对应 docs/project/engineering-policy-platform/phases/phase-7-policy-api.md）：

1. **API 是传输边界，不是第二份业务逻辑**：判定仍由 `policy.engine.evaluate` 做，
   检索仍由 `retrieval` 做，证据仍由 `validators.pipeline` 产出。本包只做
   "协议 → 领域模型 → 协议" 的转换，以及部署边界上的认证、隔离、预算与观测。
2. **DTO 与领域模型分开**：`policy_api.models` 里的每个模型都带 `schema_version`，
   与 `policy.models.SCHEMA_VERSION`（决策协议）和 `API_SCHEMA_VERSION`（传输协议）
   是两个独立的东西——传输层改字段不改变规则语义，反之亦然。
3. **失败关闭**：未知 API 版本、未认证、跨租户、证据/验证器不可用、下游超时
   一律返回结构化错误或 `policy_unavailable`，**没有任何路径默认 allow**。
4. **核心库不依赖本包**：`src/policy/` 仍然只用标准库 + pydantic + PyYAML，
   不启动 API 也能独立运行（tests/contract 里有守住这条边界的用例）。
"""

from __future__ import annotations

from .models import API_SCHEMA_VERSION, SUPPORTED_API_SCHEMA_VERSIONS

__all__ = ["API_SCHEMA_VERSION", "SUPPORTED_API_SCHEMA_VERSIONS", "__version__"]

__version__ = "0.1.0"
