"""order_repository 的用例。"""

from shop.order_repository import OrderRepository


def test_repository_insert_returns_copy() -> None:
    """插入返回副本，改它不影响表里的行。"""
    repository = OrderRepository()
    row = repository.insert({"id": 3})
    row["id"] = 99
    assert repository.listing() == [{"id": 3}]
