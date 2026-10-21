"""订单存储层。"""


class OrderRepository:
    """内存订单表。"""

    def __init__(self) -> None:
        self._rows: list[dict] = []

    def insert(self, payload: dict) -> dict:
        """写入一条订单，返回副本。"""
        row = dict(payload)
        self._rows.append(row)
        return dict(row)

    def listing(self) -> list[dict]:
        """返回全部订单的副本。"""
        return [dict(row) for row in self._rows]

    def get(self, order_id: int) -> dict | None:
        """按 id 找一条订单，返回副本；找不到返回 None。"""
        for row in self._rows:
            if row.get("id") == order_id:
                return dict(row)
        return None
