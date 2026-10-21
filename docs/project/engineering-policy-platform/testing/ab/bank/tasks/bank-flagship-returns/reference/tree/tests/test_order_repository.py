"""order_repository 的用例。"""

from shop.order_repository import OrderRepository


def test_insert_returns_a_copy() -> None:
    """写入返回副本：改它不影响已存的行。"""
    repository = OrderRepository()
    row = repository.insert({"id": 1})
    row["id"] = 2
    assert repository.listing() == [{"id": 1}]


def test_get_returns_a_copy_or_none() -> None:
    """get 按 id 找一条；命中返回副本，找不到返回 None。"""
    repository = OrderRepository()
    repository.insert({"id": 1, "total_cents": 1000})
    repository.insert({"id": 2, "total_cents": 500})
    row = repository.get(1)
    assert row == {"id": 1, "total_cents": 1000}
    row["total_cents"] = 1
    assert repository.get(1) == {"id": 1, "total_cents": 1000}
    assert repository.get(9) is None
