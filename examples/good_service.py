"""Phase 0 示例：Service 层可以依赖 Repository，ARCH-001 不会命中。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4


@dataclass
class Order:
    id: str
    payload: dict


class OrderRepository(Protocol):
    """数据访问层的**接口**：Service 只依赖这个方法，不依赖具体实现。

    示例用 Protocol 而不是 Any：写 Any 会把这一层的契约整个抹掉——返回值换了、save 的签名变了，
    类型检查与评审都看不见，而"Service 通过接口访问数据"正是这个示例要演示的东西。
    """

    def save(self, order: Order) -> Order: ...


class OrderService:
    """业务用例层：Controller 只能通过这里访问数据。"""

    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository

    def create(self, payload: dict) -> Order:
        return self._repository.save(Order(id=uuid4().hex, payload=payload))


# 该模块的直接依赖（供 CLI --dependencies 使用）：repository
