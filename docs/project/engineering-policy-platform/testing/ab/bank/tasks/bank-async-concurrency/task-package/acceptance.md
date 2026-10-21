# 验收表（bank-async-concurrency）

> 判定方式三档：**隐藏用例**（另一子会话按隐藏验收计划实现，最终树只读）、
> **树执行**（在最终树的副本里跑命令，只看退出码/输出）、**树 diff**（最终树 vs 14 文件基线）。
> 本表与 first-message.md 的「验收表」逐字对应；改一处必须改另一处。

| id | 检查 | 判定方式 |
| --- | --- | --- |
| A1 | `Notification` 构造校验与不可变：三字段类型/内容不符一律 `ValueError`（含 `bool` 冒充 `int`、空 `str`、负 `order_id`）；frozen（赋值抛 `FrozenInstanceError`）；同值两次构造相等 | 隐藏用例 |
| A2 | `to_dict()` 键集合恰为 `{key, order_id, kind}`；两次调用返回不同 dict；改返回值不影响对象 | 隐藏用例 |
| A3 | `submit` 幂等：同 key 第二次返回 `False` 且不重复入队（处理后 `processed()` 只 1 条）；不同 key 都返回 `True`；返回值是 `bool` | 隐藏用例 |
| A4 | 有界：`queue_size=2` 时连续 3 次 `submit`（中间不推进事件循环）第 3 次返回 `False` 且未入队；不静默丢、不阻塞 | 隐藏用例 |
| A5 | 停机排空与副本：`start` 后提交 3 条，`stop()` 返回后 `processed()` 恰 3 条且顺序稳定；`processed()` 返回新 list + 每条新 dict；`stop()` 可重复调用 | 隐藏用例 |
| A6 | 取消：取消正在等待 `stop()` 的任务 → `asyncio.CancelledError` 继续抛出（不吞）；该任务结束后无残留 pending 消费任务；源码里没有 `except asyncio.CancelledError: pass` 这类吞取消写法 | 隐藏用例 + AST |
| A7 | 共享队列：两个 worker 共享同一个 `asyncio.Queue`、都 `start`，3 个事件（含 1 个重复 key）→ 聚合 `processed()` 恰 2 条，每个 key 最多出现一次 | 隐藏用例 |
| A8 | 确定性：AST 里没有 `time.sleep` / `time.time` / `random` / 网络调用；同一场景两次运行 `processed()` 逐字节相同 | 隐藏用例 + AST |
| A9 | 项目根 `python tools/notify_smoke.py` 退出码 0；stdout 是合法 JSON 数组、恰 2 条记录（3 次提交去重后）；两次运行逐字节相同；`tests/test_notify_smoke.py` 调用 `main()` 并断言这 2 条 | 树执行 + 隐藏用例 |
| A10 | `docs/async.md` 含 4 个指定二级标题且每个标题下有非空正文；`README.md` 的「结构」表含 `src/shop/notify_worker.py` 一行 | 隐藏用例 |
| A11 | 旧队列保留并标注弃用：`src/shop/notification.py` 模块 docstring 含 `已弃用` 与 `NotificationWorker`；`tests/test_notification.py` 断言该说明存在；`append` / `pop` / `__len__` 行为不变 | 隐藏用例 |
| A12 | 全树：`python -m pytest -q` 全绿、无 `skip` / `xfail`；收集数 ≥ 7；改动集合 ⊆ `allowed-writes.txt` 的 10 条；14 个基线文件里不属于允许写的 11 个逐字节不变 | 树执行 + 树 diff |
