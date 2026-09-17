"""Phase 0 正例：Controller 只依赖 Service。

依赖以注释声明，便于 CLI 用 --dependencies 重放本示例：

    python -m policy.check examples/good_controller.py --dependencies service
"""

from __future__ import annotations

from examples.good_service import OrderService


class OrderController:
    """把 HTTP 请求转成服务调用，不承载业务规则。"""

    def __init__(self, service: OrderService) -> None:
        self._service = service

    def create_order(self, payload: dict) -> dict:
        order = self._service.create(payload)
        return {"id": order.id, "status": "created"}


# 该模块的直接依赖（供 CLI --dependencies 使用）：service
