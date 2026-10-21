"""service 层副本语义的用例。"""

from shop.order_service import OrderService


def test_create_returns_a_mutable_copy() -> None:
    """create 返回副本：改它之后 service.listing() 仍是插入时的内容。"""
    service = OrderService()
    created = service.create({"id": 1})
    created["id"] = 2
    assert service.listing() == [{"id": 1}]


def test_two_listings_are_equal_but_not_the_same_list() -> None:
    """两次 service.listing() 结果相等，但不是同一个列表、也不是同一批 dict。"""
    service = OrderService()
    service.create({"id": 1})
    first = service.listing()
    second = service.listing()
    assert first == second
    assert first is not second
    assert first[0] is not second[0]
