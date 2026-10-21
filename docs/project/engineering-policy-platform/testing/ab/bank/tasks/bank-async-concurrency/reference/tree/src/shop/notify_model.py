"""通知记录模型（model 层）：不可变、构造期校验、导出副本。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Notification:
    """一条待发通知：key 是幂等去重键，order_id 是订单号，kind 是渠道。"""

    key: str
    order_id: int
    kind: str

    def __post_init__(self) -> None:
        """构造期校验：字段不合法一律抛 ValueError，对象不带着非法值存在。"""
        if not isinstance(self.key, str) or not self.key:
            raise ValueError("key 必须是非空 str")
        if isinstance(self.order_id, bool) or not isinstance(self.order_id, int):
            raise ValueError("order_id 必须是 int（bool 不算）")
        if self.order_id < 0:
            raise ValueError("order_id 必须是非负整数")
        if not isinstance(self.kind, str) or not self.kind:
            raise ValueError("kind 必须是非空 str")

    def to_dict(self) -> dict:
        """导出新 dict：键集合恰为 key / order_id / kind，改它不影响记录。"""
        return {"key": self.key, "order_id": self.order_id, "kind": self.kind}
