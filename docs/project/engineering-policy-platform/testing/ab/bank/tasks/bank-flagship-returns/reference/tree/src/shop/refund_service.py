"""退货业务层：校验、幂等与 refund_id 递增。"""

from shop.order_repository import OrderRepository
from shop.refund_model import RefundRecord
from shop.refund_policy import fee_cents, is_eligible
from shop.refund_repository import RefundRepository


class RefundService:
    """退货用例；协作者全部注入，不自己 new。"""

    def __init__(
        self,
        orders: OrderRepository,
        refunds: RefundRepository,
        policy: dict,
    ) -> None:
        self.orders = orders
        self.refunds = refunds
        self.policy = policy

    def create_refund(
        self,
        order_id: int,
        amount_cents: int,
        reason: str,
        idempotency_key: str | None = None,
    ) -> dict:
        """先校验再写入：任何一步不通过都不落盘。"""
        order = self.orders.get(order_id)
        if order is None:
            raise ValueError("order does not exist")
        if (
            isinstance(amount_cents, bool)
            or not isinstance(amount_cents, int)
            or amount_cents <= 0
        ):
            raise ValueError("amount_cents must be a positive integer")
        if not is_eligible(order, amount_cents, self.policy):
            raise ValueError("refund amount is not eligible for this order")
        existing = self.refunds.all()
        if idempotency_key is not None:
            for row in existing:
                if row.get("idempotency_key") == idempotency_key:
                    return dict(row)
        next_id = max((int(row.get("refund_id", 0)) for row in existing), default=0) + 1
        record = RefundRecord(
            refund_id=next_id,
            order_id=order_id,
            amount_cents=amount_cents,
            fee_cents=fee_cents(amount_cents, self.policy),
            reason=reason,
            status="recorded",
            idempotency_key=idempotency_key,
        )
        self.refunds.add(record)
        return record.to_dict()

    def list_refunds(self, order_id: int | None = None) -> list[dict]:
        """按订单过滤或返回全部。"""
        if order_id is None:
            return self.refunds.all()
        return self.refunds.by_order(order_id)
