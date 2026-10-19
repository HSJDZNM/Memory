"""夹具：测试层（layer=test）——用静态 import 覆盖每一条生产路径。"""

from __future__ import annotations

from shop.composition import build_controller
from shop.models import Order
from shop.order_controller import OrderController
from shop.order_repository import OrderRepository
from shop.order_service import OrderService


def test_composition_wires_the_whole_stack() -> None:
    """组合根装配出的 controller 能建单并返回字典。"""

    controller = build_controller()
    assert controller.create("o-1", 100) == {"order_id": "o-1", "amount": 100}


def test_explicit_injection_reaches_the_repository() -> None:
    """显式注入时，写入真的落到仓库里。"""

    repository = OrderRepository()
    service = OrderService(repository)
    controller = OrderController(service)

    assert controller.create("o-2", 7) == {"order_id": "o-2", "amount": 7}
    assert len(repository.rows) == 1


def test_model_returns_a_copy() -> None:
    """写返回的副本不影响对象本身。"""

    payload = Order("o-3", 1).to_dict()
    payload["amount"] = 99
    assert Order("o-3", 1).to_dict()["amount"] == 1
