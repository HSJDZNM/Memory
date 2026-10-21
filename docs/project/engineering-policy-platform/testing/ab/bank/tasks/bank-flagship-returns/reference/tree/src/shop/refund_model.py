"""退货记录的 v2 数据形状。"""

from dataclasses import dataclass

REFUND_SCHEMA_VERSION = 2

_FIELD_NAMES = (
    "refund_id",
    "order_id",
    "amount_cents",
    "fee_cents",
    "reason",
    "status",
    "idempotency_key",
)

_INT_FIELDS = ("refund_id", "order_id", "amount_cents", "fee_cents")
_TEXT_FIELDS = ("reason", "status")


def _require_int(name: str, value: object) -> int:
    """字段必须是非负 int；True/False 不算 int。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(name + " must be an int")
    if value < 0:
        raise ValueError(name + " must not be negative")
    return value


def _require_text(name: str, value: object) -> str:
    """字段必须是非空 str。"""
    if not isinstance(value, str) or not value:
        raise ValueError(name + " must be a non-empty string")
    return value


@dataclass(frozen=True)
class RefundRecord:
    """一条 v2 退货记录（不可变）。"""

    refund_id: int
    order_id: int
    amount_cents: int
    fee_cents: int
    reason: str
    status: str
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        """构造期就失败关闭：类型与取值范围不对一律 ValueError。"""
        for name in _INT_FIELDS:
            _require_int(name, getattr(self, name))
        for name in _TEXT_FIELDS:
            _require_text(name, getattr(self, name))
        key = self.idempotency_key
        if key is not None and (not isinstance(key, str) or not key):
            raise ValueError("idempotency_key must be a non-empty string or None")

    def to_dict(self) -> dict:
        """返回含 schema_version 的新 dict（改它不影响记录）。"""
        payload = {"schema_version": REFUND_SCHEMA_VERSION}
        for name in _FIELD_NAMES:
            payload[name] = getattr(self, name)
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "RefundRecord":
        """从恰好 8 个键的 dict 还原记录；形状不对一律 ValueError。"""
        if not isinstance(data, dict):
            raise ValueError("data must be a dict")
        if len(data) != len(_FIELD_NAMES) + 1:
            raise ValueError("data must have exactly 8 keys")
        if set(data) != set(_FIELD_NAMES) | {"schema_version"}:
            raise ValueError("data keys are not the v2 record keys")
        version = data["schema_version"]
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("schema_version must be an int")
        if version != REFUND_SCHEMA_VERSION:
            raise ValueError("schema_version must be " + str(REFUND_SCHEMA_VERSION))
        return cls(
            refund_id=data["refund_id"],
            order_id=data["order_id"],
            amount_cents=data["amount_cents"],
            fee_cents=data["fee_cents"],
            reason=data["reason"],
            status=data["status"],
            idempotency_key=data["idempotency_key"],
        )
