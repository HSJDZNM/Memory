"""正例：Controller 只依赖 Service，ARCH-001 不应命中。"""

from shop.order_service import OrderService


class OrderController:
    """接口层：把请求转成服务调用。"""

    def __init__(self, service: OrderService) -> None:
        """注入业务用例层。"""

        self._service = service

    def create(self, payload: dict) -> dict:
        """处理创建请求。"""

        return self._service.create(payload)
