"""订单仓储（探针）：controller 不得直接依赖它（ARCH-001）。"""


class OrderRepository:
    """订单持久化。"""

    def save(self, payload: dict) -> dict:
        """保存订单。"""

        return dict(payload)
