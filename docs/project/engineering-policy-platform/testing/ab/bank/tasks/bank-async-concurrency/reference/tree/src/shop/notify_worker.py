"""确定性 asyncio 工作队列（service 层）：有界、按 key 幂等、可取消、停机排空。"""

from __future__ import annotations

import asyncio

from shop.notify_model import Notification


class NotificationWorker:
    """有界通知工作队列：FIFO 消费、按 key 去重、停机先排空。"""

    def __init__(self, queue_size: int = 4, queue: asyncio.Queue | None = None) -> None:
        """构造 worker：自建有界队列，或注入共享队列（容量由该队列自己决定）。"""
        if isinstance(queue_size, bool) or not isinstance(queue_size, int):
            raise ValueError("queue_size 必须是 int（bool 不算）")
        if queue_size < 1:
            raise ValueError("queue_size 必须 >= 1")
        if queue is None:
            self._queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        elif isinstance(queue, asyncio.Queue):
            self._queue = queue
        else:
            raise ValueError("queue 必须是 asyncio.Queue")
        self._seen: set[str] = set()
        self._processed: list[dict] = []
        self._task: asyncio.Task | None = None
        self._closed = False

    async def start(self) -> None:
        """启动后台消费任务；重复调用幂等，stop 之后调用抛 RuntimeError。"""
        if self._closed:
            raise RuntimeError("worker 已停止")
        if self._task is not None:
            return
        self._task = asyncio.get_running_loop().create_task(self._consume())

    async def submit(self, notification: Notification) -> bool:
        """入队一条通知：同 key 重复或队列已满返回 False，成功入队返回 True。"""
        if self._closed:
            raise RuntimeError("worker 已停止")
        if not isinstance(notification, Notification):
            raise ValueError("notification 必须是 Notification")
        if notification.key in self._seen:
            return False
        if self._queue.full():
            return False
        self._seen.add(notification.key)
        self._queue.put_nowait(notification)
        return True

    async def stop(self) -> None:
        """先排空已入队事件再停止消费；重复调用幂等，被取消时继续抛出 CancelledError。"""
        if self._closed:
            return
        self._closed = True
        if self._task is None:
            return
        try:
            await self._queue.join()
        except asyncio.CancelledError:
            await self._shutdown()
            raise
        await self._shutdown()

    def processed(self) -> list[dict]:
        """按处理顺序返回已处理记录的新副本（新 list + 每条新 dict）。"""
        return [dict(record) for record in self._processed]

    async def _consume(self) -> None:
        """消费循环：按 FIFO 取事件、记录副本、标记完成；取消直接向上传播。"""
        while True:
            notification = await self._queue.get()
            self._processed.append(notification.to_dict())
            self._queue.task_done()

    async def _shutdown(self) -> None:
        """取消并回收本 worker 的消费任务（幂等）。"""
        task = self._task
        self._task = None
        if task is None or task.done():
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
