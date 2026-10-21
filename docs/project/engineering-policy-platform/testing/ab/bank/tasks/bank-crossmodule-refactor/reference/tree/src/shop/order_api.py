"""旧订单 API 的兼容门面（已弃用）。"""

from shop.order_repository import OrderRepository


class OrderApi:
    """旧订单 API 的兼容门面：只转发到 OrderRepository 的新名。"""

    def __init__(self, repository: OrderRepository) -> None:
        """保存调用方给的 repository，不自己创建。"""
        self.repository = repository

    def insert(self, payload: dict) -> dict:
        """已弃用的旧名：原样转发到 OrderRepository.add(payload)。"""
        return self.repository.add(payload)

    def listing(self) -> list[dict]:
        """已弃用的旧名：原样转发到 OrderRepository.list_all()。"""
        return self.repository.list_all()
