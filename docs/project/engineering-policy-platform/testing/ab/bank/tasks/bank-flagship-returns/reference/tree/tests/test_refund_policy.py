"""refund_policy 的用例：读入、夹逼与资格边界。"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from shop.refund_policy import fee_cents, is_eligible, load_policy

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = PROJECT_ROOT / "config" / "refund_policy.yaml"

EXPECTED = {
    "version": 1,
    "currency": "CNY",
    "fee_bps": 250,
    "min_fee_cents": 0,
    "max_fee_cents": 500,
    "max_refund_ratio": 1.0,
}


def test_load_policy_reads_the_commented_yaml() -> None:
    """基线策略（带注释）能读成 6 个键。"""
    assert load_policy(POLICY_PATH) == EXPECTED


def _scratch(name: str) -> Path:
    """一个干净的临时目录（不依赖 pytest 的 tmp_path）。"""
    path = Path(tempfile.gettempdir()) / "demo-shop-tests" / name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path


def test_load_policy_rejects_malformed_mappings() -> None:
    """多键、少键、类型错、越界一律 ValueError。"""
    cases = [
        {**EXPECTED, "fee_bps_max": 1},
        {key: value for key, value in EXPECTED.items() if key != "currency"},
        {**EXPECTED, "fee_bps": "250"},
        {**EXPECTED, "max_refund_ratio": 0},
        {**EXPECTED, "min_fee_cents": 600, "max_fee_cents": 500},
    ]
    directory = _scratch("policy")
    for index, payload in enumerate(cases):
        path = directory / ("bad-%d.yaml" % index)
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError):
            load_policy(path)


def test_fee_cents_clamps_without_floats() -> None:
    """整数夹逼：floor 后再夹到 [min, max]。"""
    assert fee_cents(10000, EXPECTED) == 250
    assert fee_cents(500, EXPECTED) == 12
    assert fee_cents(1, EXPECTED) == 0
    assert fee_cents(100000, EXPECTED) == 500
    assert fee_cents(100, {**EXPECTED, "min_fee_cents": 100}) == 100


def test_is_eligible_boundaries() -> None:
    """恰好等于总额可退、超 1 分不可退、0 元与缺失订单不可退。"""
    order = {"id": 1, "total_cents": 1000}
    assert is_eligible(order, 1000, EXPECTED) is True
    assert is_eligible(order, 1001, EXPECTED) is False
    assert is_eligible(order, 0, EXPECTED) is False
    assert is_eligible(None, 1000, EXPECTED) is False
    assert is_eligible({}, 1000, EXPECTED) is False
    half = {**EXPECTED, "max_refund_ratio": 0.5}
    assert is_eligible(order, 500, half) is True
    assert is_eligible(order, 501, half) is False
