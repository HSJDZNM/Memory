"""order_repository 的用例。"""

from shop.order_repository import OrderRepository


def test_insert_returns_a_copy() -> None:
    """写入返回副本：改它不影响已存的行。"""
    repository = OrderRepository()
    row = repository.insert({"id": 1})
    row["id"] = 2
    assert repository.listing() == [{"id": 1}]
