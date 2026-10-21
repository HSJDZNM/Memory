"""同步通知队列（v1）：列表实现，既有调用点继续用它。"""


class NotificationQueue:
    """同步通知队列：先进先出。"""

    def __init__(self) -> None:
        self._items: list[dict] = []

    def append(self, notification: dict) -> None:
        """入队一条通知；存副本，改入参不影响队列。"""
        self._items.append(dict(notification))

    def pop(self) -> dict:
        """出队最早的一条通知；空队列抛 IndexError。"""
        if not self._items:
            raise IndexError("通知队列为空")
        return self._items.pop(0)

    def __len__(self) -> int:
        """队列里当前的通知条数。"""
        return len(self._items)
