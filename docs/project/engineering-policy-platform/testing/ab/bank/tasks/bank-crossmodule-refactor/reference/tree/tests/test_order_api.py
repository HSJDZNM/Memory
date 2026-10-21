"""order_api 的用例：兼容门面的转发、副本语义与弃用说明。"""

from shop.order_api import OrderApi
from shop.order_repository import OrderRepository


class RecordingRepository:
    """只实现 add / list_all 的替身：记录收到的对象，返回预先给定的对象。"""

    def __init__(self) -> None:
        self.add_calls: list[dict] = []
        self.list_all_calls = 0
        self.returned_row: dict = {"id": 99}
        self.returned_rows: list[dict] = [{"id": 99}]

    def add(self, payload: dict) -> dict:
        """记录参数并返回预先给定的行对象。"""
        self.add_calls.append(payload)
        return self.returned_row

    def list_all(self) -> list[dict]:
        """记录调用次数并返回预先给定的列表对象。"""
        self.list_all_calls += 1
        return self.returned_rows


def test_insert_forwards_to_add() -> None:
    """insert 原样转发到 add：参数与返回都是同一个对象。"""
    repository = RecordingRepository()
    api = OrderApi(repository)
    payload = {"id": 1}
    result = api.insert(payload)
    assert repository.add_calls == [payload]
    assert repository.add_calls[0] is payload
    assert result is repository.returned_row


def test_listing_forwards_to_list_all() -> None:
    """listing 原样转发到 list_all：返回同一个对象。"""
    repository = RecordingRepository()
    api = OrderApi(repository)
    assert api.listing() is repository.returned_rows
    assert repository.list_all_calls == 1


def test_insert_returns_a_copy_through_the_facade() -> None:
    """经门面写入仍然返回副本：改返回值不影响内部。"""
    api = OrderApi(OrderRepository())
    row = api.insert({"id": 1})
    row["id"] = 2
    assert api.listing() == [{"id": 1}]


def test_docstrings_mark_the_api_deprecated() -> None:
    """两个旧方法的说明里写明弃用与对应的新名。"""
    insert_doc = OrderApi.insert.__doc__ or ""
    listing_doc = OrderApi.listing.__doc__ or ""
    assert "弃用" in insert_doc
    assert "add" in insert_doc
    assert "弃用" in listing_doc
    assert "list_all" in listing_doc
