from shop.order_service import OrderService


class OrderFacade:
    """有 docstring 的类（模块本身没有 docstring）。"""

    def __init__(self, service: OrderService) -> None:
        """注入业务用例层。"""

        self._service = service
