"""业务用例层：依赖图里应解析成 service 组件。"""

from shop.order_repository import OrderRepository


class OrderService:
    """业务用例：Controller 只能通过它访问数据。"""

    def __init__(self, repository: OrderRepository) -> None:
        """注入数据访问层。"""

        self._repository = repository

    def create(self, payload: dict) -> dict:
        """创建订单。"""

        return self._repository.save(payload)
