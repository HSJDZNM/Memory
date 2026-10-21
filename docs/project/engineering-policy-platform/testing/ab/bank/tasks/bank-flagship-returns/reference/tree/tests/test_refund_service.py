"""refund_service 的用例：正常路径、拒绝路径与幂等。"""

from pathlib import Path
from typing import Any

import pytest

from shop.refund_policy import load_policy
from shop.refund_service import RefundService

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POLICY = load_policy(PROJECT_ROOT / "config" / "refund_policy.yaml")


class _Orders:
    """最小订单替身：只实现 get。"""

    def __init__(self, rows: dict[int, int]) -> None:
        self._rows = dict(rows)

    def get(self, order_id: int) -> dict | None:
        """按 id 返回订单副本。"""
        total = self._rows.get(order_id)
        return None if total is None else {"id": order_id, "total_cents": total}


class _Refunds:
    """最小退款仓储替身：add / all / by_order。"""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, record: Any) -> dict:
        """追加并返回副本。"""
        payload = record.to_dict()
        self.rows.append(dict(payload))
        return dict(payload)

    def all(self) -> list[dict]:
        """全部记录的副本。"""
        return [dict(row) for row in self.rows]

    def by_order(self, order_id: int) -> list[dict]:
        """该订单的记录副本。"""
        return [dict(row) for row in self.rows if row["order_id"] == order_id]


def _service(rows: dict[int, int]) -> RefundService:
    """用替身装配一个 service。"""
    return RefundService(_Orders(rows), _Refunds(), POLICY)


def test_create_refund_records_the_order_amount_and_fee() -> None:
    """正常路径：id 从 1 开始、fee 按 bps 算、状态 recorded。"""
    refund = _service({7: 1000}).create_refund(7, 1000, "damaged")
    assert refund["refund_id"] == 1
    assert refund["order_id"] == 7
    assert refund["amount_cents"] == 1000
    assert refund["fee_cents"] == 25
    assert refund["status"] == "recorded"
    assert refund["idempotency_key"] is None
    assert refund["schema_version"] == 2


def test_unknown_order_is_rejected_without_writing() -> None:
    """未知订单：ValueError，且没有任何记录。"""
    service = _service({})
    with pytest.raises(ValueError):
        service.create_refund(7, 1000, "damaged")
    assert service.refunds.all() == []


def test_bad_amounts_are_rejected_without_writing() -> None:
    """0、负数、超总额：3/3 ValueError，且没有任何记录。"""
    service = _service({7: 1000})
    for amount in (0, -1, 1001):
        with pytest.raises(ValueError):
            service.create_refund(7, amount, "damaged")
    assert service.refunds.all() == []


def test_same_idempotency_key_returns_the_first_record() -> None:
    """同一个 key 复用同一条；不同 key 拿到新 id。"""
    service = _service({7: 1000})
    first = service.create_refund(7, 500, "damaged", "k1")
    again = service.create_refund(7, 500, "damaged", "k1")
    other = service.create_refund(7, 400, "late", "k2")
    assert [first["refund_id"], again["refund_id"], other["refund_id"]] == [1, 1, 2]
    assert len(service.refunds.all()) == 2


def test_list_refunds_filters_by_order() -> None:
    """无参给全部，传 order_id 只给该订单。"""
    service = _service({1: 1000, 2: 1000})
    service.create_refund(1, 300, "a")
    service.create_refund(1, 200, "b")
    service.create_refund(2, 100, "c")
    assert len(service.list_refunds()) == 3
    assert [row["refund_id"] for row in service.list_refunds(1)] == [1, 2]
