"""Phase 0 示例：Service 层可以依赖 Repository，ARCH-001 不会命中。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Order:
    id: str
    payload: dict


class OrderService:
    """业务用例层：Controller 只能通过这里访问数据。"""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def create(self, payload: dict) -> Order:
        return self._repository.save(Order(id="order-1", payload=payload))


# 该模块的直接依赖（供 CLI --dependencies 使用）：repository
