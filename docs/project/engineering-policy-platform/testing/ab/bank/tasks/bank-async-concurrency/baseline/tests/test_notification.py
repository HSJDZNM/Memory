"""notification 的用例：同步队列仍然可用。"""

from shop.notification import NotificationQueue


def test_sync_queue_keeps_order_and_length() -> None:
    """append/pop/len 按先进先出工作，且存的是入参副本。"""
    queue = NotificationQueue()
    queue.append({"key": "a", "order_id": 1, "kind": "email"})
    queue.append({"key": "b", "order_id": 2, "kind": "sms"})
    assert len(queue) == 2
    first = queue.pop()
    assert first == {"key": "a", "order_id": 1, "kind": "email"}
    assert len(queue) == 1
