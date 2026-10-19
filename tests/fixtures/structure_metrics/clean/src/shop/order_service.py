"""夹具：业务用例层（layer=service）。"""

from __future__ import annotations

from shop.models import Order
from shop.order_repository import OrderRepository

__all__ = ["OrderService"]


class OrderService:
    """订单用例：只持有注入进来的仓库，不自己装配。"""

    def __init__(self, repository: OrderRepository) -> None:
        """注入仓库。"""

        self._repository = repository

    def create(self, order_id: str, amount: int = 0) -> Order:
        """建单并落库，返回建好的模型。"""

        order = Order(order_id=order_id, amount=amount)
        self._repository.save(order)
        return order
