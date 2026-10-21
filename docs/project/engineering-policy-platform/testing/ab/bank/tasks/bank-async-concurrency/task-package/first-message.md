这是一个无人值守的开发任务，工作目录就是本项目根目录（订单示例项目 + 一个同步通知队列的基线）。不要向我提问；被拒的动作不要重试、不要绕过、不要改主意——把系统给出的原文理由贴出来，然后继续下一个里程碑。命令逐条执行，不要用管道或重定向组合命令。

调用 pwsh 时只传 command 与 description 两个参数；不要传 timeoutMs、workdir、run_in_background、sandbox_permissions、justification。

【命令约束】只使用这些命令形态：`python -m pytest -q`、`python -m pytest -q tests/test_notify_worker.py`、`python tools/notify_smoke.py`、`git status --porcelain`。不要用 `python -c`、`python -m <自定义模块>`、后台执行（`run_in_background`）、非默认 `timeoutMs` 或 `workdir`；不要用管道、重定向或分号拼接命令。

【本次只允许写这些路径】README.md、docs/async.md（新建）、src/shop/notification.py、src/shop/notify_model.py（新建）、src/shop/notify_worker.py（新建）、tests/test_notification.py、tests/test_notify_model.py（新建）、tests/test_notify_smoke.py（新建）、tests/test_notify_worker.py（新建）、tools/notify_smoke.py（新建）。其它文件一律不改（尤其不要改 AGENTS.md、conftest.py、pytest.ini、src/shop/__init__.py、src/shop/order_controller.py、src/shop/order_repository.py、src/shop/order_service.py、tests/test_order_controller.py、tests/test_order_repository.py、tests/test_order_service.py、tools/__init__.py）。不要 git commit / git push。不要新增第三方依赖（asyncio 是标准库）；不要用网络、随机数或时钟。

【基线】14 个文件，起点干净（`python -m pytest -q` → 4 passed）：
- 订单示例项目 11 文件：`AGENTS.md`、`README.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_controller.py`、`src/shop/order_repository.py`、`src/shop/order_service.py`、`tests/test_order_controller.py`、`tests/test_order_repository.py`、`tests/test_order_service.py`；
- 脚本包 1 文件：`tools/__init__.py`（与旗舰题同名文件逐字节相同；`tools` 已经是基线里的顶层包，先写 `tests/test_notify_smoke.py` 会走「待实现」而不会被收集失败阻断）；
- 同步通知队列 2 文件：`src/shop/notification.py`（`NotificationQueue.append/pop/len`，本任务只允许改它的模块 docstring）、`tests/test_notification.py`。

【目标】把现有的同步 `NotificationQueue` 升级成一个**确定性的 asyncio 工作队列**：有界队列、按 key 幂等去重、可取消、停机时排空、异常不许吞。新增 model（`Notification`）与 service（`NotificationWorker`）两层、一个可运行的冒烟脚本、3 个同名测试文件、1 篇文档；旧队列保留并标注弃用。测试不得依赖墙钟 / 随机 / 网络，用 `asyncio.run` 与 `queue.join()` 驱动，同一输入重复跑读数一致。

【数据形状（逐键精确）】`Notification` → `to_dict()` 的键集合恰为 `{key, order_id, kind}`：`key` 是非空 str（幂等去重键），`order_id` 是非负 int，`kind` 是非空 str。

【接口（逐字实现；签名与语义都不许改）】
1) 新建 `src/shop/notify_model.py`（model 层）：
   - `@dataclass(frozen=True) class Notification`，字段依次为 `key: str`、`order_id: int`、`kind: str`；
   - 构造期校验（可写在 `__post_init__`）：`key` / `kind` 是非空 str，`order_id` 是非 bool 的非负 int；不合法一律抛 `ValueError`，对象不得带着非法值存在；
   - `to_dict() -> dict`：键集合恰为 `{key, order_id, kind}`，值逐字段对应；返回**新** dict（改它不影响记录）；
   - frozen：构造后给字段赋值抛 `dataclasses.FrozenInstanceError`；同值两次构造 `==`。
2) 新建 `src/shop/notify_worker.py`（service 层）：
   - `class NotificationWorker: __init__(self, queue_size: int = 4, queue: asyncio.Queue | None = None)`；
   - `queue_size` 必须是 `int >= 1`（bool 不算），否则 `ValueError`；`queue is None` 时自建 `asyncio.Queue(maxsize=queue_size)`；
   - `queue` 是可选的共享队列（两个 worker 消费同一队列）：给定时必须 `isinstance(queue, asyncio.Queue)`，否则 `ValueError`；给定时队列容量由该队列自己的 `maxsize` 决定；
   - `async start(self) -> None`：启动后台消费任务；运行中重复调用是幂等的；`stop()` 之后再调用抛 `RuntimeError`；
   - `async submit(self, notification: Notification) -> bool`：参数不是 `Notification` 实例 → `ValueError`；同 key 第二次及以后 → 返回 `False` 且不重复入队（去重表在 worker 生命周期内保留，处理后仍生效）；队列满（`queue.full()`）→ 返回 `False`，不入队、不阻塞、不静默丢；首次入队成功 → 返回 `True`；`stop()` 之后调用 → `RuntimeError`；允许在 `start()` 之前调用（只入队，不消费；`start()` 之后照常处理）；
   - `async stop(self) -> None`：先排空（`await queue.join()` 等所有已入队事件处理完），再停止本 worker 的消费任务；重复调用幂等；未 `start()` 时立即返回（没有消费者，不消费、不排空）；被取消时 `asyncio.CancelledError` 必须继续抛出（允许清理后再抛，**不许** `except ...: pass` 后正常返回），该任务结束后不得残留 pending 消费任务；
   - `processed(self) -> list[dict]`：按处理顺序返回 `to_dict()` 的副本列表（新 list + 每条新 dict）；运行中与 `stop()` 后都可调用；
   - 消费循环按 FIFO 处理；只用 asyncio，不 sleep、不用随机 / 时钟 / 网络，同一场景重复运行结果一致。
3) 新建 `tools/notify_smoke.py`（composition 层）：
   - `main() -> list[dict]`：构造 `NotificationWorker()`，在 `asyncio.run(...)` 里 `start` → 提交 3 个事件（逐字）：`Notification("smoke-1", 1, "email")`、`Notification("smoke-2", 2, "sms")`、`Notification("smoke-1", 3, "email")`（第三个与第一个同 key，`submit` 返回 `False`）→ `stop`；返回 `worker.processed()`（去重后 2 条，顺序为 `smoke-1`、`smoke-2`）；
   - `if __name__ == "__main__":`：`print(json.dumps(main(), ensure_ascii=False, sort_keys=True))`；退出码 0；stdout 只有这一行 JSON（合法 JSON 数组，恰 2 条记录）；
   - 在项目根用 `python tools/notify_smoke.py` 跑（`sys.path[0]` 是 `tools/`）：像 `conftest.py` 那样把 `<项目根>/src` 插进 `sys.path` 再 import `shop`；紧随其后的 import 行加 `# noqa: E402`。
4) 改既有 `src/shop/notification.py`：模块 docstring 增加一行弃用说明，**同时含子串** `已弃用` 与 `NotificationWorker`（例：`已弃用：新代码请用 shop.notify_worker.NotificationWorker；NotificationQueue 仅为兼容保留。`）；`append` / `pop` / `__len__` 的行为一个字节不动。
5) 改既有 `tests/test_notification.py`：保留原用例并新增一条断言——`shop.notification` 的模块 docstring 含 `已弃用`。
6) 新建 `docs/async.md`：必须含 4 个二级标题（逐字、按此顺序）：`## 队列语义`、`## 幂等`、`## 取消`、`## 停机`；每个标题下至少一行非空正文。
7) 改 `README.md`：「结构」表新增一行，第一列（路径）为 `src/shop/notify_worker.py`；其它行不动。
8) 新建 3 个测试文件（与生产文件同名）：`tests/test_notify_model.py`（A1/A2）、`tests/test_notify_worker.py`（A3–A8；异步用例用 `asyncio.run` 驱动，不用 pytest-asyncio；共享队列用 `NotificationWorker(queue=shared)`）、`tests/test_notify_smoke.py`（文件顶部把项目根插进 `sys.path`，然后 `from tools.notify_smoke import main  # noqa: E402`，调用 `main()` 并断言去重后 2 条）。每个新测试文件至少 1 个 `assert`；不许 `skip` / `skipif` / `xfail` / 任何标记。
9) 错误语义（逐条可测）：字段/参数不合法 → `ValueError`；构造后赋值 → `FrozenInstanceError`；`queue_size=0` / `queue_size=True` / `queue` 不是 `asyncio.Queue` → `ValueError`；同 key 重复提交或队列满 → `False`（不是异常、不阻塞）；`stop()` 之后再 `start()` 或再 `submit` → `RuntimeError`；取消正在等待的 `stop()` → `asyncio.CancelledError` 继续抛出。
10) 确定性纪律：测试与实现都不得依赖墙钟、随机数、网络；用例用 `asyncio.run` 与 `queue.join()` 驱动；同一输入重复跑，`processed()` 与 smoke 脚本 stdout 必须逐字节相同。

【验收表】
A1 `Notification` 构造校验与不可变：三字段类型/内容不符一律 `ValueError`（含 `bool` 冒充 `int`、空 `str`、负 `order_id`）；frozen（赋值抛 `FrozenInstanceError`）；同值两次构造相等 → 隐藏用例
A2 `to_dict()` 键集合恰为 `{key, order_id, kind}`；两次调用返回不同 dict；改返回值不影响对象 → 隐藏用例
A3 `submit` 幂等：同 key 第二次返回 `False` 且不重复入队（处理后 `processed()` 只 1 条）；不同 key 都返回 `True`；返回值是 `bool` → 隐藏用例
A4 有界：`queue_size=2` 时连续 3 次 `submit`（中间不推进事件循环）第 3 次返回 `False` 且未入队；不静默丢、不阻塞 → 隐藏用例
A5 停机排空与副本：`start` 后提交 3 条，`stop()` 返回后 `processed()` 恰 3 条且顺序稳定；`processed()` 返回新 list + 每条新 dict；`stop()` 可重复调用 → 隐藏用例
A6 取消：取消正在等待 `stop()` 的任务 → `asyncio.CancelledError` 继续抛出（不吞）；该任务结束后无残留 pending 消费任务；源码里没有 `except asyncio.CancelledError: pass` 这类吞取消写法 → 隐藏用例 + AST
A7 共享队列：两个 worker 共享同一个 `asyncio.Queue`、都 `start`，3 个事件（含 1 个重复 key）→ 聚合 `processed()` 恰 2 条，每个 key 最多出现一次 → 隐藏用例
A8 确定性：AST 里没有 `time.sleep` / `time.time` / `random` / 网络调用；同一场景两次运行 `processed()` 逐字节相同 → 隐藏用例 + AST
A9 项目根 `python tools/notify_smoke.py` 退出码 0；stdout 是合法 JSON 数组、恰 2 条记录（3 次提交去重后）；两次运行逐字节相同；`tests/test_notify_smoke.py` 调用 `main()` 并断言这 2 条 → 树执行 + 隐藏用例
A10 `docs/async.md` 含 4 个指定二级标题且每个标题下有非空正文；`README.md` 的「结构」表含 `src/shop/notify_worker.py` 一行 → 隐藏用例
A11 旧队列保留并标注弃用：`src/shop/notification.py` 模块 docstring 含 `已弃用` 与 `NotificationWorker`；`tests/test_notification.py` 断言该说明存在；`append` / `pop` / `__len__` 行为不变 → 隐藏用例
A12 全树：`python -m pytest -q` 全绿、无 `skip` / `xfail`；收集数 ≥ 7；改动集合 ⊆ `allowed-writes.txt` 的 10 条；14 个基线文件里不属于允许写的 11 个逐字节不变 → 树执行 + 树 diff

【里程碑，按这个顺序做，不要跳步】
M1 先写 tests/test_notify_model.py（覆盖 A1/A2；不 import 其它新模块），然后跑一次 python -m pytest -q，把结果照原文贴出来（实现还没写，测试失败是预期）。
M2 再写 src/shop/notify_model.py 的最小实现（dataclass + 构造校验 + to_dict），然后跑一次 python -m pytest -q。
M3 先写 tests/test_notify_worker.py（覆盖 A3–A8；异步用例用 asyncio.run 驱动；共享队列用 NotificationWorker(queue=shared)），然后跑一次 python -m pytest -q（shop.notify_worker 还没写，失败是预期）。
M4 再写 src/shop/notify_worker.py（消费任务 + 幂等 + 有界 + 排空 + 取消不吞），然后跑一次 python -m pytest -q。
M5 改 src/shop/notification.py 的模块 docstring（含 已弃用 与 NotificationWorker），再改 tests/test_notification.py 补断言（A11），然后跑一次 python -m pytest -q。
M6 写 docs/async.md（4 个指定二级标题）并改 README.md 的「结构」表加 src/shop/notify_worker.py 一行（A10），然后跑一次 python -m pytest -q。
M7 写 tests/test_notify_smoke.py（from tools.notify_smoke import main，调用 main() 并断言去重后 2 条），然后跑一次 python -m pytest -q（tools/notify_smoke 还没写，失败是预期）。
M8 写 tools/notify_smoke.py（main() + __main__ 打印 JSON；sys.path 后的 import 行加 # noqa: E402），然后跑一次 python -m pytest -q 与 python tools/notify_smoke.py，把两段输出照原文贴出来。
M9 再跑一次 python -m pytest -q tests/test_notify_worker.py、一次 python -m pytest -q 与一次 python tools/notify_smoke.py，把结果照原文贴出来（确定性用例要连续两次一致）。
M10 最后跑 python -m pytest -q 与 python tools/notify_smoke.py，用不超过 120 字汇报：每个里程碑做了什么、哪些动作被拒（照原文理由）、最后一次测试与脚本输出。

【代码约定】模块/类/公开函数都要有 docstring；单行不超过 100 列；不留未使用的 import；import 分组顺序正确（标准库 / 第三方 / 本地）；不用裸 except（用具体异常）；不用 random / 时间 / 网络；同一场景的输出必须可复现；测试里不许 skip / xfail，每个新测试文件至少一条 assert。
