"""notification 的用例：同步队列仍然可用，并标注已弃用。"""

import shop.notification as notification_module
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


def test_sync_queue_module_is_deprecated() -> None:
    """模块 docstring 标注旧队列已弃用、新代码改用 NotificationWorker。"""
    assert "已弃用" in (notification_module.__doc__ or "")
    assert "NotificationWorker" in (notification_module.__doc__ or "")
