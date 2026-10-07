"""Phase 0 反例的依赖目标：Repository 本身没有违规，违规发生在 Controller。"""

from __future__ import annotations

from uuid import uuid4


class OrderRepository:
    """数据访问层。"""

    def save(self, payload: dict) -> dict:
        # id 由本方法分配，必须写在 **payload **之后**：反过来写，调用方传来的同名键会静默
        # 覆盖它（bad_controller 把请求体原样透传进来），"标识由本方法分配"就不成立了。
        return {**payload, "id": uuid4().hex}


# 该模块的直接依赖（供 CLI --dependencies 使用）：
