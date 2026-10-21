"""refund_controller 的用例：只转发，不碰数据层。"""

from shop.refund_controller import RefundController


class _Service:
    """记录参数的 service 替身。"""

    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.created: dict = {"refund_id": 1}
        self.listing: list[dict] = [{"refund_id": 1}]

    def create_refund(
        self,
        order_id: int,
        amount_cents: int,
        reason: str,
        idempotency_key: str | None = None,
    ) -> dict:
        """记录参数并返回哨兵对象。"""
        self.calls.append((order_id, amount_cents, reason, idempotency_key))
        return self.created

    def list_refunds(self, order_id: int | None = None) -> list[dict]:
        """记录参数并返回哨兵列表。"""
        self.calls.append((order_id,))
        return self.listing


def test_create_refund_forwards_arguments_and_result() -> None:
    """参数逐字传给 service，返回值原样透传。"""
    service = _Service()
    controller = RefundController(service)
    assert controller.create_refund(1, 2, "x", "k") is service.created
    assert service.calls == [(1, 2, "x", "k")]


def test_list_refunds_forwards_order_id_and_result() -> None:
    """order_id 原样传给 service，列表原样透传。"""
    service = _Service()
    controller = RefundController(service)
    assert controller.list_refunds(7) is service.listing
    assert service.calls == [(7,)]
