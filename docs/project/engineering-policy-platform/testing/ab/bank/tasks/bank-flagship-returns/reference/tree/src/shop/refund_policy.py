"""退货金额策略：读 YAML 与三个纯函数。"""

from pathlib import Path

import yaml

_POLICY_KEYS = frozenset(
    {
        "version",
        "currency",
        "fee_bps",
        "min_fee_cents",
        "max_fee_cents",
        "max_refund_ratio",
    }
)


def _fail(message: str) -> None:
    """统一的失败形态：一律 ValueError，消息里不带路径。"""
    raise ValueError(message)


def _require_int(name: str, value: object) -> int:
    """非负 int 字段；True/False 不算 int。"""
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(name + " must be an int")
    if value < 0:
        _fail(name + " must not be negative")
    return int(value)


def _validate(data: dict) -> dict:
    """校验 6 个键的类型与合法域，返回原 dict。"""
    if set(data) != _POLICY_KEYS:
        _fail("policy keys must be exactly the 6 documented keys")
    if _require_int("version", data["version"]) != 1:
        _fail("version must be 1")
    currency = data["currency"]
    if not isinstance(currency, str) or not currency:
        _fail("currency must be a non-empty string")
    _require_int("fee_bps", data["fee_bps"])
    low = _require_int("min_fee_cents", data["min_fee_cents"])
    high = _require_int("max_fee_cents", data["max_fee_cents"])
    if low > high:
        _fail("min_fee_cents must not exceed max_fee_cents")
    ratio = data["max_refund_ratio"]
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)):
        _fail("max_refund_ratio must be a number")
    if not 0 < ratio <= 1:
        _fail("max_refund_ratio must be in (0, 1]")
    return data


def load_policy(path: Path) -> dict:
    """读一份策略 YAML；语法错误与越界一律 ValueError。"""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError("policy file is not readable") from exc
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError("policy YAML is not parseable") from exc
    if not isinstance(data, dict):
        _fail("policy must be a mapping")
    return _validate(data)


def fee_cents(amount_cents: int, policy: dict) -> int:
    """按 bps 算手续费，再夹到 [min_fee_cents, max_fee_cents]（整数运算）。"""
    raw = amount_cents * policy["fee_bps"] // 10000
    low = policy["min_fee_cents"]
    high = policy["max_fee_cents"]
    return max(low, min(high, raw))


def is_eligible(order: dict | None, amount_cents: int, policy: dict) -> bool:
    """订单、金额与上限都合格才 True；任何缺失都 False（不抛异常）。"""
    if not isinstance(order, dict):
        return False
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int):
        return False
    if amount_cents <= 0:
        return False
    total = order.get("total_cents")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        return False
    ratio = policy.get("max_refund_ratio")
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)):
        return False
    return amount_cents <= int(total * ratio)
