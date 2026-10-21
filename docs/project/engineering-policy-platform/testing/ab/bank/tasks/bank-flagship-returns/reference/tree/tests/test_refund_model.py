"""refund_model 的用例：v2 记录的形状、往返与失败形态。"""

import dataclasses

import pytest

from shop.refund_model import REFUND_SCHEMA_VERSION, RefundRecord


def _payload() -> dict:
    """一条合法的 v2 记录。"""
    return {
        "schema_version": 2,
        "refund_id": 1,
        "order_id": 2,
        "amount_cents": 1000,
        "fee_cents": 25,
        "reason": "damaged",
        "status": "recorded",
        "idempotency_key": None,
    }


def test_to_dict_has_exactly_the_eight_keys() -> None:
    """to_dict 的 8 个键与值逐字段对应。"""
    record = RefundRecord(1, 2, 1000, 25, "damaged", "recorded", None)
    assert record.to_dict() == _payload()
    assert REFUND_SCHEMA_VERSION == 2


def test_to_dict_returns_a_fresh_dict() -> None:
    """改 to_dict 的返回值不影响记录本身。"""
    record = RefundRecord(1, 2, 1000, 25, "damaged", "recorded")
    payload = record.to_dict()
    payload["amount_cents"] = 1
    assert record.to_dict() == _payload()
    assert record.to_dict() is not record.to_dict()


def test_record_is_frozen() -> None:
    """记录不可变。"""
    record = RefundRecord(1, 2, 1000, 25, "damaged", "recorded")
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.amount_cents = 1


def test_from_dict_round_trips() -> None:
    """往返一次数据无损。"""
    record = RefundRecord.from_dict(_payload())
    assert record == RefundRecord(1, 2, 1000, 25, "damaged", "recorded", None)
    assert record.to_dict() == _payload()


def test_from_dict_rejects_malformed_payloads() -> None:
    """多键、少键、错 schema、类型错（含 bool 冒充 int）一律 ValueError。"""
    good = _payload()
    cases = [
        {key: value for key, value in good.items() if key != "reason"},
        {**good, "extra": 1},
        {**good, "schema_version": 1},
        {**good, "refund_id": True},
        {**good, "amount_cents": -1},
        {**good, "status": ""},
        {**good, "idempotency_key": 1},
    ]
    for payload in cases:
        with pytest.raises(ValueError):
            RefundRecord.from_dict(payload)
