"""夹具：领域模型（layer=model）。"""

from __future__ import annotations

__all__ = ["Order"]


class Order:
    """一张订单（值对象，构造后不再改字段）。"""

    def __init__(self, order_id: str, amount: int = 0) -> None:
        """记下订单号与金额。"""

        self.order_id = order_id
        self.amount = amount

    def to_dict(self) -> dict:
        """以字典形式返回一份副本（调用方改它不影响对象）。"""

        return {"order_id": self.order_id, "amount": self.amount}
