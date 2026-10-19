"""夹具：数据访问层（layer=repository）。"""

from __future__ import annotations

from shop.models import Order

__all__ = ["OrderRepository"]


class OrderRepository:
    """内存版订单仓库（只依赖 model）。"""

    def __init__(self) -> None:
        """从空表开始。"""

        self.rows: list[Order] = []

    def save(self, order: Order) -> None:
        """写入一张订单。"""

        self.rows.append(order)
