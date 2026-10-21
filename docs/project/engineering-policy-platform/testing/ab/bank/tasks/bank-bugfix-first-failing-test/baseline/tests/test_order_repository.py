"""order_repository 的用例。"""

from shop.order_repository import OrderRepository


def test_insert_returns_a_copy() -> None:
    """写入返回副本：改它不影响已存的行。"""
    repository = OrderRepository()
    row = repository.insert({"id": 1})
    row["id"] = 2
    assert repository.listing() == [{"id": 1}]


def test_listing_returns_copies() -> None:
    """listing 返回副本：改入参、改返回的列表都不影响已存的行。"""
    repository = OrderRepository()
    payload = {"id": 1}
    repository.insert(payload)
    payload["id"] = 2
    first = repository.listing()
    first[0]["id"] = 3
    second = repository.listing()
    assert second == [{"id": 1}]
    assert second is not first
