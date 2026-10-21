"""refund_repository 的用例：内存、JSONL、副本与坏行。"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from shop.refund_model import RefundRecord
from shop.refund_repository import RefundRepository


def _scratch(name: str) -> Path:
    """一个干净的临时目录（不依赖 pytest 的 tmp_path）。"""
    path = Path(tempfile.gettempdir()) / "demo-shop-tests" / name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path


def _record(refund_id: int, order_id: int, amount_cents: int = 100) -> RefundRecord:
    """造一条退货记录。"""
    return RefundRecord(
        refund_id, order_id, amount_cents, 5, "damaged", "recorded", None
    )


def test_memory_repository_hands_out_copies() -> None:
    """add / all 交出副本，改它们不影响内部。"""
    repository = RefundRepository()
    payload = repository.add(_record(1, 1))
    payload["amount_cents"] = 999
    rows = repository.all()
    rows[0]["amount_cents"] = 7
    rows.append({"refund_id": 99})
    assert repository.all() == [_record(1, 1).to_dict()]


def test_by_order_filters_in_order() -> None:
    """by_order 只留该订单，顺序与写入一致。"""
    repository = RefundRepository()
    repository.add(_record(1, 1))
    repository.add(_record(2, 2))
    repository.add(_record(3, 1))
    assert [row["refund_id"] for row in repository.by_order(1)] == [1, 3]
    assert repository.by_order(9) == []


def test_file_repository_appends_and_reloads() -> None:
    """给了路径就按行追加，重新打开能读回。"""
    path = _scratch("repository") / "refunds.jsonl"
    repository = RefundRepository(path)
    repository.add(_record(1, 1))
    repository.add(_record(2, 2))
    reopened = RefundRepository(path)
    assert [row["refund_id"] for row in reopened.all()] == [1, 2]
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["order_id"] == 1


def test_file_repository_rejects_corrupt_lines() -> None:
    """非法 JSON 行与非对象行都必须 ValueError。"""
    directory = _scratch("repository-corrupt")
    for name, payload in (("bad-json", b"{oops\n"), ("not-object", b"[1]\n")):
        path = directory / (name + ".jsonl")
        path.write_bytes(payload)
        with pytest.raises(ValueError):
            RefundRepository(path)
