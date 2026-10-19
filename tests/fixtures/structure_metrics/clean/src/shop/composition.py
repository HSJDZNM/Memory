"""夹具：组合根（layer=composition）——唯一装配具象协作者的地方。"""

from __future__ import annotations

from shop.order_controller import OrderController
from shop.order_repository import OrderRepository
from shop.order_service import OrderService

__all__ = ["build_controller"]


def build_controller() -> OrderController:
    """把 repository → service → controller 装配起来。"""

    repository = OrderRepository()
    service = OrderService(repository)
    return OrderController(service)
