"""notify_worker 的用例：幂等、有界、排空、关闭语义、共享队列、取消与确定性。"""

import asyncio
import json

from shop.notify_model import Notification
from shop.notify_worker import NotificationWorker


def _raises(action, kind: type) -> bool:
    """判断 action() 是否抛 kind。"""
    try:
        action()
    except kind:
        return True
    return False


def test_submit_is_idempotent_per_key() -> None:
    """同 key 第二次 submit 返回 False，processed 只有 1 条。"""

    async def _scenario():
        worker = NotificationWorker()
        await worker.start()
        first = await worker.submit(Notification("k", 1, "email"))
        second = await worker.submit(Notification("k", 2, "sms"))
        await worker.stop()
        return first, second, worker.processed()

    first, second, records = asyncio.run(_scenario())
    assert first is True
    assert second is False
    assert [record["order_id"] for record in records] == [1]


def test_bounded_queue_returns_false_when_full() -> None:
    """queue_size=2 时第三次 submit 返回 False 且不入队。"""

    async def _scenario():
        worker = NotificationWorker(queue_size=2)
        results = []
        for index, key in enumerate(["a", "b", "c"]):
            results.append(await worker.submit(Notification(key, index, "email")))
        await worker.start()
        await worker.stop()
        return results, worker.processed()

    results, records = asyncio.run(_scenario())
    assert results == [True, True, False]
    assert [record["key"] for record in records] == ["a", "b"]


def test_stop_drains_queue_in_order() -> None:
    """stop 返回后 3 条都处理完且顺序稳定，队列无残留。"""

    async def _scenario():
        shared = asyncio.Queue()
        worker = NotificationWorker(queue=shared)
        await worker.start()
        for index, key in enumerate(["a", "b", "c"]):
            await worker.submit(Notification(key, index, "email"))
        await worker.stop()
        return worker.processed(), shared.empty()

    records, empty = asyncio.run(_scenario())
    assert [record["key"] for record in records] == ["a", "b", "c"]
    assert empty is True


def test_processed_returns_copies() -> None:
    """processed 返回新 list 与每条新 dict，改它不影响内部记录。"""

    async def _scenario():
        worker = NotificationWorker()
        await worker.start()
        await worker.submit(Notification("k", 1, "email"))
        await worker.stop()
        return worker

    worker = asyncio.run(_scenario())
    first = worker.processed()
    second = worker.processed()
    first.append({"key": "extra", "order_id": 9, "kind": "sms"})
    first[0]["key"] = "mutated"
    assert len(second) == 1
    assert second[0]["key"] == "k"
    assert worker.processed()[0]["key"] == "k"


def test_shared_queue_delivers_each_event_once() -> None:
    """两个 worker 共享同一队列时，聚合记录恰 2 条且每个 key 只出现一次。"""

    async def _scenario():
        shared = asyncio.Queue()
        left = NotificationWorker(queue=shared)
        right = NotificationWorker(queue=shared)
        await left.start()
        await right.start()
        await left.submit(Notification("s1", 1, "email"))
        await left.submit(Notification("s2", 2, "sms"))
        duplicate = await left.submit(Notification("s1", 3, "email"))
        await left.stop()
        await right.stop()
        aggregate = left.processed() + right.processed()
        return duplicate, sorted(record["key"] for record in aggregate)

    duplicate, keys = asyncio.run(_scenario())
    assert duplicate is False
    assert keys == ["s1", "s2"]


def test_stop_is_idempotent_and_closes_worker() -> None:
    """stop 可重复调用；stop 之后 submit 与 start 都抛 RuntimeError。"""

    async def _scenario():
        worker = NotificationWorker()
        await worker.start()
        await worker.submit(Notification("k", 1, "email"))
        await worker.stop()
        await worker.stop()
        submit_raised = False
        start_raised = False
        try:
            await worker.submit(Notification("k2", 2, "sms"))
        except RuntimeError:
            submit_raised = True
        try:
            await worker.start()
        except RuntimeError:
            start_raised = True
        return submit_raised, start_raised, len(worker.processed())

    submit_raised, start_raised, count = asyncio.run(_scenario())
    assert submit_raised is True
    assert start_raised is True
    assert count == 1


def test_cancel_during_stop_propagates_cancelled_error() -> None:
    """取消阻塞中的 stop 时 CancelledError 继续抛出，且不残留消费任务。"""

    class StuckQueue(asyncio.Queue):
        """join() 永不返回的队列：把 stop 卡在 pending 上。"""

        async def join(self) -> None:
            """永不完成的 join：只挂住等待者，直到外部取消。"""
            await asyncio.Event().wait()

    async def _scenario():
        worker = NotificationWorker(queue=StuckQueue())
        await worker.start()
        task = asyncio.get_running_loop().create_task(worker.stop())
        for _ in range(5):
            await asyncio.sleep(0)
        task.cancel()
        raised = False
        try:
            await task
        except asyncio.CancelledError:
            raised = True
        current = asyncio.current_task()
        leftover = [item for item in asyncio.all_tasks() if item is not current]
        for item in leftover:
            item.cancel()
        if leftover:
            await asyncio.gather(*leftover, return_exceptions=True)
        return raised, len(leftover)

    raised, leftover = asyncio.run(_scenario())
    assert raised is True
    assert leftover == 0


def test_constructor_rejects_bad_arguments() -> None:
    """queue_size 与 queue 不合法时在构造期抛 ValueError。"""
    for bad in (0, -1, True, "2", 2.0):
        assert _raises(lambda bad=bad: NotificationWorker(queue_size=bad), ValueError)
    for bad_queue in ({}, [], "q"):
        assert _raises(
            lambda bad_queue=bad_queue: NotificationWorker(queue=bad_queue), ValueError
        )


def test_scene_is_deterministic() -> None:
    """同一场景跑两次，processed 的 JSON 逐字节相同。"""

    async def _scenario():
        worker = NotificationWorker()
        await worker.start()
        for index, key in enumerate(["d1", "d2", "d1", "d3"]):
            await worker.submit(Notification(key, index, "email"))
        await worker.stop()
        return worker.processed()

    first = json.dumps(asyncio.run(_scenario()), sort_keys=True, ensure_ascii=False)
    second = json.dumps(asyncio.run(_scenario()), sort_keys=True, ensure_ascii=False)
    assert first == second
    assert [record["key"] for record in json.loads(first)] == ["d1", "d2", "d3"]
