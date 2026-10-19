"""夹具：接口层（layer=controller）。"""

from __future__ import annotations

from shop.order_service import OrderService

__all__ = ["OrderController"]


class OrderController:
    """只做转发：不碰仓库，也不碰数据库。"""

    def __init__(self, service: OrderService) -> None:
        """只持有 service。"""

        self._service = service

    def create(self, order_id: str, amount: int = 0) -> dict:
        """转发给 service，返回字典。"""

        return self._service.create(order_id, amount).to_dict()
