# 异步工作队列接口契约（bank-async-concurrency）

> 本文件是**题目的一部分**：模型的首消息（first-message.md）会以更完整的形式复述同一组签名与语义。
> 两者不一致 = 任务包自相矛盾，冻结前必须先对齐；冻结后任何一个字节的变化都算换构造。

## 1 基线里已有的（只读；本任务只允许改 `notification.py` 的模块 docstring）

`src/shop/notification.py` 的 `NotificationQueue` 已有：

```python
class NotificationQueue:
    def __init__(self) -> None: ...
    def append(self, notification: dict) -> None: ...   # 入队一条通知（存副本）
    def pop(self) -> dict: ...                          # 出队最早一条；空队列抛 IndexError
    def __len__(self) -> int: ...                       # 队列长度
```

本任务只给模块 docstring 加一行弃用说明；`append` / `pop` / `__len__` 的行为一个字节不动
（旧调用点继续可用）。`src/shop/order_*.py`、`conftest.py`、`pytest.ini`、`AGENTS.md` 等其它基线文件**不许改**。

基线还含 `tools/__init__.py`（与 `bank-flagship-returns/baseline/tools/__init__.py` 逐字节相同）：
它是顶层包标记、本任务不改；正因为它已存在，`tools.*` 的测试先写时走的是「待实现」通道而不是收集失败。

## 2 新建 `src/shop/notify_model.py`（model 层）

```python
@dataclass(frozen=True)
class Notification:
    key: str
    order_id: int
    kind: str

    def __post_init__(self) -> None: ...    # 构造期校验；不合法抛 ValueError
    def to_dict(self) -> dict: ...          # 键集合恰为 {key, order_id, kind}，返回新 dict
```

- 构造期校验（可写在 `__post_init__`）：`key` / `kind` 是非空 `str`；`order_id` 是非 `bool` 的非负 `int`；
  不合法一律抛 `ValueError`，对象不得带着非法值存在；
- `to_dict()` 的键集合恰为 `{key, order_id, kind}`，值逐字段对应；返回**新** dict（改它不影响记录）；
- frozen：构造后给字段赋值抛 `dataclasses.FrozenInstanceError`；同值两次构造 `==`。

## 3 新建 `src/shop/notify_worker.py`（service 层）

```python
class NotificationWorker:
    def __init__(self, queue_size: int = 4, queue: asyncio.Queue | None = None) -> None: ...
    async def start(self) -> None: ...
    async def submit(self, notification: Notification) -> bool: ...
    async def stop(self) -> None: ...
    def processed(self) -> list[dict]: ...
```

- `queue_size`：必须是 `int >= 1`（`bool` 不算），否则 `ValueError`；`queue is None` 时自建
  `asyncio.Queue(maxsize=queue_size)`；
- `queue`：可选的共享队列（SPEC §5 要求「两个 worker 消费同一队列」）。给定时必须
  `isinstance(queue, asyncio.Queue)`，否则 `ValueError`；给定时队列容量由该队列自己的 `maxsize` 决定；
- `start()`：启动后台消费任务；运行中重复调用是幂等的；`stop()` 之后再调用抛 `RuntimeError`；
- `submit(notification)`：
  - 参数不是 `Notification` 实例 → `ValueError`；
  - 同 key 第二次及以后 → 返回 `False`，不重复入队（去重表在 worker 生命周期内保留，处理后仍生效）；
  - 队列满（`queue.full()`）→ 返回 `False`，不入队、不阻塞、不静默丢；
  - 首次入队成功 → 返回 `True`；`stop()` 之后调用 → `RuntimeError`；
  - 允许在 `start()` 之前调用：只入队，不消费（`start()` 之后照常处理）；
- `stop()`：
  - 先排空：`await queue.join()` 等所有已入队事件处理完，再停止本 worker 的消费任务；
  - 重复调用幂等；未 `start()` 时立即返回（没有消费者，不消费、不排空）；
  - 被取消时 `asyncio.CancelledError` 必须继续抛出（允许清理后再抛；**不许** `except ...: pass` 后正常返回）；
    该任务结束后不得残留 pending 消费任务；
- `processed()`：按处理顺序返回 `to_dict()` 的副本列表（新 list + 每条新 dict）；运行中与 `stop()` 后都可调用；
- 消费循环按 FIFO 处理；只用 `asyncio`，不 sleep、不用随机/时钟/网络，同一场景重复运行结果一致。

## 4 新建 `tools/notify_smoke.py`（composition 层）

```python
def main() -> list[dict]: ...    # 跑一次确定性队列，返回去重后的 processed()
# __main__：print(json.dumps(main(), ensure_ascii=False, sort_keys=True))
```

- 构造 `NotificationWorker()`，在 `asyncio.run(...)` 里 `start` → 提交 3 个事件（逐字）：
  `Notification("smoke-1", 1, "email")`、`Notification("smoke-2", 2, "sms")`、`Notification("smoke-1", 3, "email")`
  （第三个与第一个同 key，`submit` 返回 `False`）→ `stop`；返回 `worker.processed()`
  （去重后 2 条，顺序为 `smoke-1`、`smoke-2`）；
- 在项目根用 `python tools/notify_smoke.py` 跑（`sys.path[0]` 是 `tools/`）：像 `conftest.py` 那样把
  `<项目根>/src` 插进 `sys.path` 再 import `shop`；紧随其后的 import 行加 `# noqa: E402`；
- 退出码 0；stdout 只有这一行 JSON（合法 JSON 数组，恰 2 条记录）。

## 5 改既有文件

- `src/shop/notification.py`：模块 docstring 增加一行弃用说明，**同时含子串** `已弃用` 与 `NotificationWorker`
  （例：`已弃用：新代码请用 shop.notify_worker.NotificationWorker；NotificationQueue 仅为兼容保留。`）；
- `tests/test_notification.py`：保留原用例并新增一条断言——`shop.notification` 的模块 docstring 含 `已弃用`
  （说明旧队列仍保留但已弃用）；
- `README.md`：「结构」表新增一行，第一列（路径）为 `src/shop/notify_worker.py`；其它行不动。

## 6 新建 `docs/async.md`

必须含 4 个二级标题（逐字、按此顺序）：`## 队列语义`、`## 幂等`、`## 取消`、`## 停机`；
每个标题下至少一行非空正文。

## 7 新建 2 个测试文件 + 改写基线静态契约测试

- `tests/test_notify_model.py`：覆盖 A1/A2；
- `tests/test_notify_worker.py`：覆盖 A3–A8；异步用例用 `asyncio.run` 驱动（**不用** pytest-asyncio），
  共享队列用 `NotificationWorker(queue=shared)`；
- `tests/test_notify_smoke.py`（基线静态契约测试，M8 改写为行为测试）：文件顶部把项目根插进 `sys.path`，然后
  `from tools.notify_smoke import main  # noqa: E402`，调用 `main()` 并断言去重后 2 条记录；
- 每个新测试文件至少 1 个 `assert`；M8 改写后的测试不许 `skip` / `skipif` / `xfail` / 任何标记（基线静态测试在工具不存在时 skip 是允许的）。

## 8 错误语义（逐条可测）

| 场景 | 结果 |
| --- | --- |
| `Notification` 字段类型/内容不合法 | `ValueError` |
| 构造后给字段赋值 | `dataclasses.FrozenInstanceError` |
| `NotificationWorker(queue_size=0)` / `queue_size=True` / `queue` 不是 `asyncio.Queue` | `ValueError` |
| `submit` 的不是 `Notification` | `ValueError` |
| 同 key 重复提交 / 队列满 | `False`（不是异常、不阻塞） |
| `stop()` 之后再 `start()` / 再 `submit` | `RuntimeError` |
| 取消正在等待的 `stop()` | `asyncio.CancelledError` 继续抛出 |

## 9 确定性纪律

测试与实现都不得依赖墙钟、随机数、网络：用例用 `asyncio.run` 与 `queue.join()` 驱动；
同一输入重复跑，`processed()` 与 smoke 脚本 stdout 必须逐字节相同。
