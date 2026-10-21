"""notify_model 的用例：字段顺序、构造期校验、不可变与副本。"""

import dataclasses

from shop.notify_model import Notification


def _raises_value_error(action) -> bool:
    """判断 action() 是否抛 ValueError。"""
    try:
        action()
    except ValueError:
        return True
    return False


def test_notification_keeps_fields_in_order() -> None:
    """三个字段按声明顺序保存。"""
    record = Notification("k1", 7, "email")
    assert (record.key, record.order_id, record.kind) == ("k1", 7, "email")
    assert [field.name for field in dataclasses.fields(record)] == [
        "key",
        "order_id",
        "kind",
    ]


def test_notification_is_frozen() -> None:
    """构造后给字段赋值抛 FrozenInstanceError，值保持不变。"""
    record = Notification("k", 1, "email")
    raised = False
    try:
        record.key = "x"
    except dataclasses.FrozenInstanceError:
        raised = True
    assert raised
    assert record.key == "k"


def test_notification_equality() -> None:
    """同值两次构造相等，kind 不同就不等。"""
    assert Notification("k", 1, "email") == Notification("k", 1, "email")
    assert Notification("k", 1, "email") != Notification("k", 1, "sms")


def test_notification_rejects_bad_key() -> None:
    """key 不是非空 str 时抛 ValueError。"""
    for bad in ("", 1, None):
        assert _raises_value_error(lambda bad=bad: Notification(bad, 1, "email"))


def test_notification_rejects_bad_kind() -> None:
    """kind 不是非空 str 时抛 ValueError。"""
    for bad in ("", 1, None):
        assert _raises_value_error(lambda bad=bad: Notification("k", 1, bad))


def test_notification_rejects_bad_order_id() -> None:
    """order_id 不是非负 int（含 bool、float、字符串、负数）时抛 ValueError。"""
    for bad in (-1, True, 1.0, "1", None):
        assert _raises_value_error(lambda bad=bad: Notification("k", bad, "email"))


def test_to_dict_returns_fresh_copies() -> None:
    """to_dict 的键集合恰为三键，每次返回新 dict，改它不影响记录。"""
    record = Notification("k1", 7, "email")
    first = record.to_dict()
    second = record.to_dict()
    assert set(first) == {"key", "order_id", "kind"}
    assert first == {"key": "k1", "order_id": 7, "kind": "email"}
    assert first is not second
    first["key"] = "mutated"
    assert record.to_dict()["key"] == "k1"
