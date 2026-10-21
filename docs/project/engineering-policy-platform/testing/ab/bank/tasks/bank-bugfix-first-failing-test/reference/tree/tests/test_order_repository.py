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


def test_mutating_the_payload_does_not_touch_the_store() -> None:
    """写入之后再改入参：已存的行不变（存的是副本）。"""
    repository = OrderRepository()
    payload = {"id": 1, "note": "first"}
    repository.insert(payload)
    payload["note"] = "changed"
    assert repository.listing() == [{"id": 1, "note": "first"}]


def test_mutating_the_result_does_not_touch_the_store() -> None:
    """改 insert 的返回值：已存的行不变（返回的是另一个副本）。"""
    repository = OrderRepository()
    row = repository.insert({"id": 1})
    row["id"] = 2
    row["note"] = "added"
    assert repository.listing() == [{"id": 1}]


def test_two_listings_are_equal_but_not_the_same_list() -> None:
    """两次 listing 结果相等，但不是同一个列表、也不是同一批 dict。"""
    repository = OrderRepository()
    repository.insert({"id": 1})
    first = repository.listing()
    second = repository.listing()
    assert first == second
    assert first is not second
    assert first[0] is not second[0]
