"""与服务同名的测试：related 层级应当命中它。"""

from shop.order_service import OrderService


class FakeRepository:
    """最小替身。"""

    def save(self, payload: dict) -> dict:
        """返回写好的订单。"""

        return {"id": "order-1", **payload}


def test_create_delegates_to_repository() -> None:
    service = OrderService(FakeRepository())

    assert service.create({"sku": "x"})["id"] == "order-1"
