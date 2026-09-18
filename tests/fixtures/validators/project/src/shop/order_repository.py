"""数据访问层：依赖图里应解析成 repository 组件。"""


class OrderRepository:
    """订单存储。"""

    def save(self, payload: dict) -> dict:
        """写入一条订单。"""

        return {"id": "order-1", **payload}
