"""Phase 0 反例的依赖目标：Repository 本身没有违规，违规发生在 Controller。"""

from __future__ import annotations


class OrderRepository:
    """数据访问层。"""

    def save(self, payload: dict) -> dict:
        return {"id": "order-1", **payload}


# 该模块的直接依赖（供 CLI --dependencies 使用）：
