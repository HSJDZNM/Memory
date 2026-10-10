"""订单业务层。"""

from shop.order_repository import OrderRepository


class OrderService:
    """订单用例。"""

    def __init__(self, repository: OrderRepository | None = None) -> None:
        self.repository = repository or OrderRepository()

    def create(self, payload: dict) -> dict:
        """创建一条订单。"""
        return self.repository.insert(payload)

    def listing(self) -> list[dict]:
        """列出全部订单。"""
        return self.repository.listing()
