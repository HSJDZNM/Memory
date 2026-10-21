"""order_service 的用例。"""

from shop.order_service import OrderService


def test_create_goes_through_repository() -> None:
    """create 把订单交给 repository。"""
    service = OrderService()
    assert service.create({"id": 1}) == {"id": 1}
    assert service.listing() == [{"id": 1}]
