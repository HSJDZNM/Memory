"""订单入口层。"""

from shop.order_service import OrderService


class OrderController:
    """订单入口。"""

    def __init__(self, service: OrderService | None = None) -> None:
        self.service = service or OrderService()

    def create(self, payload: dict) -> dict:
        """创建订单。"""
        return self.service.create(payload)

    def listing(self) -> list[dict]:
        """列出订单。"""
        return self.service.listing()
