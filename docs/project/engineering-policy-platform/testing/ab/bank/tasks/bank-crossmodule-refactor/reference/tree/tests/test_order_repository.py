"""order_repository 的用例。"""

from shop.order_repository import OrderRepository


def test_add_returns_a_copy() -> None:
    """写入返回副本：改它不影响已存的行。"""
    repository = OrderRepository()
    row = repository.add({"id": 1})
    row["id"] = 2
    assert repository.list_all() == [{"id": 1}]


def test_list_all_returns_copies() -> None:
    """列出返回副本：改它不影响已存的行。"""
    repository = OrderRepository()
    repository.add({"id": 1})
    rows = repository.list_all()
    rows[0]["id"] = 9
    rows.append({"id": 2})
    assert repository.list_all() == [{"id": 1}]
