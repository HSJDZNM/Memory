"""反例：Controller 直接依赖 Repository，ARCH-001 必须由 AST 证据命中。"""

from shop.order_repository import OrderRepository


class OrderController:
    """接口层：这里刻意绕过 Service。"""

    def __init__(self, repository: OrderRepository) -> None:
        """注入数据访问层（反例）。"""

        self._repository = repository

    def create(self, payload: dict) -> dict:
        """处理创建请求。"""

        return self._repository.save(payload)
