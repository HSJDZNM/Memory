"""订单 Controller（探针）：当前只依赖 Service 层。

一致性套件里的 block 场景在**编辑文本**里引入对 repository 的直接依赖，
因此这个文件本身保持干净：判定的输入是"这次改动"，不是文件现状。
"""

from shop.order_service import OrderService


class OrderController:
    """订单接口层。"""

    def __init__(self, service: OrderService) -> None:
        self.service = service

    def create(self, payload: dict) -> dict:
        """创建订单（转发给 Service）。"""

        return self.service.create(payload)
