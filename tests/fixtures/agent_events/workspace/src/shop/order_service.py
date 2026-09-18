"""订单 Service（探针）：允许修改的层。

allow 场景在这里做一次不引入禁止依赖的改动；layer 映射把它判成 service。
"""

from shop.order_repository import OrderRepository


class OrderService:
    """订单应用服务。"""

    def __init__(self, repository: OrderRepository) -> None:
        self.repository = repository

    def create(self, payload: dict) -> dict:
        """创建订单。"""

        return self.repository.save(payload)
