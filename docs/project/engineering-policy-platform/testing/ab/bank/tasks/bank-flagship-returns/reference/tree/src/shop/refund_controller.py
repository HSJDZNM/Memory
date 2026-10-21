"""退货入口层：只转发，不直接访问数据层。"""

from shop.refund_service import RefundService


class RefundController:
    """退货入口。"""

    def __init__(self, service: RefundService) -> None:
        self.service = service

    def create_refund(
        self,
        order_id: int,
        amount_cents: int,
        reason: str,
        idempotency_key: str | None = None,
    ) -> dict:
        """创建一笔退货：参数原样转给 service。"""
        return self.service.create_refund(order_id, amount_cents, reason, idempotency_key)

    def list_refunds(self, order_id: int | None = None) -> list[dict]:
        """列出退货：参数原样转给 service。"""
        return self.service.list_refunds(order_id)
