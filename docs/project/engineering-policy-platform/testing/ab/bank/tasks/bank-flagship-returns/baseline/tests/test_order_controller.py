"""order_controller 的用例。"""

from shop.order_controller import OrderController


def test_controller_delegates_to_service() -> None:
    """入口层只做转发。"""
    controller = OrderController()
    assert controller.create({"id": 7}) == {"id": 7}
    assert controller.listing() == [{"id": 7}]
