# 异步通知队列（NotificationWorker）

本文说明把同步 `NotificationQueue` 升级成确定性 asyncio 工作队列之后的语义边界。
实现是 `src/shop/notify_worker.py`，记录模型是 `src/shop/notify_model.py`。

## 队列语义

队列有界（`queue_size`，默认 4），按先进先出消费；`submit` 成功返回 `True`，
队列已满返回 `False` 且不入队——不阻塞、也不静默丢弃。`submit` 允许在 `start()` 之前调用，
只入队不消费。

## 幂等

去重键是 `Notification.key`，去重表在 worker 的整个生命周期内保留（记录处理完之后仍生效）：
同一个 key 第二次提交返回 `False`，不会重复入队。两个 worker 各自维护自己的去重表；
要保证跨 worker 只处理一次，由调用方把同一个 key 提交给同一个 worker。

## 取消

`stop()` 被取消时（任务被 `cancel()`），`asyncio.CancelledError` 必须继续向上抛出：
实现只做「取消并回收自己的消费任务」这一件事，然后原样 re-raise，不吞异常。
取消之后不残留 pending 的消费任务。

## 停机

`stop()` 先 `await queue.join()` 把已入队的事件处理完，再停止消费任务；重复调用幂等；
从未 `start()` 过的 worker 上调用会立即返回（没有消费者，不消费也不排空）。
`stop()` 之后再 `submit` 或 `start` 抛 `RuntimeError`。

旧队列 `NotificationQueue` 保留但已弃用：新代码用 `NotificationWorker`。
`python tools/notify_smoke.py` 是一次确定性的冒烟运行（3 次提交、去重后 2 条）。
