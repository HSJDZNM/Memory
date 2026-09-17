"""Phase 0 反例：Controller 直接依赖 Repository，应当被 ARCH-001 阻断。

依赖以注释声明，便于 CLI 用 --dependencies 重放本示例：

    python -m policy.check examples/bad_controller.py --dependencies repository
"""

from __future__ import annotations

from examples.bad_repository import OrderRepository


class OrderController:
    """反例：绕过 Service 直接读写数据层。"""

    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository

    def create_order(self, payload: dict) -> dict:
        return self._repository.save(payload)


# 该模块的直接依赖（供 CLI --dependencies 使用）：repository
