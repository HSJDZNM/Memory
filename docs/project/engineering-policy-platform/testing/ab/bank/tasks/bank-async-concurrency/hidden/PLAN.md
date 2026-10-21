# 隐藏验收计划（bank-async-concurrency）

> **状态**：**已冻结**。本文件与 `hidden/runner.py` 同批落盘；`scoring.yaml` 的
> `dimension_t.total = 38`、`case_ids` = 本文件的 38 条 id（顺序相同）、两个 hidden 摘要同批回填。
> **口径**：本文件是隐藏用例的唯一来源，runner 逐条实现、**不增不减**；id 顺序 = runner 的
> `cases` 顺序；id 集合与 `case_ids` 不相等按「跑不成」（exit 2）处理，不把「少测了」记成「测过了」。
> **判据来源**：`SPEC.md` §5（≥30 条要点，建议 34）、`task-package/first-message.md` 的【接口】
> 与【验收表】A1–A12、`task-package/interfaces.md` §2–§9、`coverage.md` §5。

## 0 契约

- 被评树只从环境变量 `BANK_TASK_TREE` 取入；**一个字节都不写**：所有执行（pytest / 冒烟脚本 /
  模块导入）都在树的副本里跑，副本退出即删；进程内 `sys.dont_write_bytecode = True`。
- stdout 是**唯一**载荷（UTF-8，`sort_keys`）：`{schema_version, tree, cases[], summary{passed,total}}`；
  `cases` 每条 `{id, pass, detail}`；无时戳 / run id / 绝对路径 / 耗时。
- 退出码：**0 = 全过 / 1 = 有失败 / 2 = 跑不成**（缺 `BANK_TASK_TREE`、树不存在、
  用例集合不完整、树复制不出来）。2 表示判不了，**不是 0 分**。
- 子进程超时 60 秒；每条用例独立 try/except，一条异常只让该条 fail。
- 同一 cwd + 同一棵树两次运行**逐字节相同**（树标签相对调用 cwd；detail 已脱敏）。

## 1 分组（38 条）

| 组 | 条数 | 覆盖 |
| --- | --- | --- |
| T | 23（T01–T23） | 核心行为：`Notification` 的形状/校验/不可变、`NotificationWorker` 的幂等/有界/排空/取消/共享队列/确定性 |
| EN | 8（EN1–EN8） | 入口：冒烟脚本退出码与 stdout 形状、两次逐字节相同、smoke 测试静态 import、文档与 README、全树 pytest、收集数 |
| I | 7（I1–I7） | 接口与树形状：类形状/签名、AST 确定性、旧队列弃用、测试断言、冻结文件、改动集合 |

**反向用例**（断言的是「期望失败 / 期望拒绝」，不是「跑成 = 通过」）：
**T04 / T05 / T06 / T13 / T18 / T19 / T20 / T22**（8 条）。

## 2 T 组（核心行为）

### T01 `Notification` 构造与字段
- **断言要点**：`Notification("k1", 7, "email")` 的三个属性逐字段相等；关键字构造
  `Notification(key="k2", order_id=0, kind="sms")` 成立（`order_id=0` 合法）；`order_id` 是
  `int` 且**不是** `bool`（`type(x) is int`）。
- **反向构造**：实现缺失 → ImportError 该条 fail；字段名写错（`k`/`id`/`channel`）或把
  `order_id` 收成 `str` 都让本条红。正向用例，不设「期望失败」。

### T02 frozen 不可变
- **断言要点**：构造后给任一字段赋值抛 `dataclasses.FrozenInstanceError`；三次赋值分别试
  `key` / `order_id` / `kind`；`dataclasses.is_dataclass(cls)` 为真且
  `cls.__dataclass_params__.frozen` 为真。
- **反向构造**：普通类（不是 dataclass）、或 `dataclass` 漏 `frozen=True`、或自己写
  `__setattr__` 抛别的异常类型 → 红。

### T03 同值两次构造相等
- **断言要点**：同字段值的两个实例 `==` 成立；字段改一个字符后 `!=`。
- **反向构造**：`eq=False`、或忘了 dataclass 语义（自定义 `__eq__` 比 identity）→ 红。

### T04 非法 `key` 拒绝（**反向**）
- **断言要点**：`""`、`1`、`None`、`b"k"`、`["k"]` 一律抛 `ValueError`（纯空白串**不判**，
  见 §5 边界）。
- **反向构造**：抛别的异常（TypeError / AssertionError）、或干脆接受 `""` → 红。
  「期望失败」：本条的通过条件是**捕获到 ValueError**，不是「没抛」。

### T05 非法 `kind` 拒绝（**反向**）
- **断言要点**：`""`、`1`、`None`、`b"x"`、`{"kind": "email"}` 一律抛 `ValueError`。
- **反向构造**：同 T04（异常类型不对或接受 `""` → 红）。

### T06 非法 `order_id` 拒绝（**反向**）
- **断言要点**：`-1`、`True`、`False`、`1.0`、`"1"`、`None` 一律抛 `ValueError`。
- **反向构造**：把 bool 当 int 放行（`isinstance(True, int)` 为真）→ 红；用 `assert` /
  `TypeError` 代替 `ValueError` → 红。这是本题最容易漏的岔口（`bool` 冒充 `int`）。

### T07 `to_dict()` 形状与新 dict
- **断言要点**：`set(payload) == {"key", "order_id", "kind"}`；值逐字段相等；两次调用
  `is not`（每次新 dict）。
- **反向构造**：多键（例如塞 `schema_version`）、少键、返回 `self.__dict__` 的引用 → 红。

### T08 `to_dict()` 副本隔离
- **断言要点**：改返回值的键值后，对象自身与新一次 `to_dict()` 都不变。
- **反向构造**：把内部 dict 缓存后原样返回（改返回值污染后续读数）→ 红。

### T09 `submit` 幂等（同 key 第二次 `False`）
- **断言要点**：`start()` 后先提交 `("k", 1, ...)` 得 `True`，再提交 `("k", 2, ...)` 得 `False`；
  `stop()` 后 `processed()` 恰 1 条且是**第一条**（`order_id == 1`）。
- **反向构造**：去重表在消费后清空（处理后第二次仍 `True` → 红，这是本题「去重在 worker 生命周期
  内保留」的实测岔口）；按整条记录而不是 key 去重 → 红（`processed()` 会有 2 条）。

### T10 `submit` 的返回值是 `bool`
- **断言要点**：`first is True`、`dup is False`（identity 比较；`1` / `0` / 真值对象不算）；
  `type(first) is bool`。
- **反向构造**：返回 `1`/`0`、`None`、`self`、`queue.put` 的协程对象 → 红。

### T11 不同 key 全进且 FIFO 顺序
- **断言要点**：`queue_size=4`（默认）+ `start()` 后提交 3 个不同 key，三次都 `True`；
  `stop()` 后 `processed()` 的 key 顺序 = 提交顺序。
- **反向构造**：LIFO（从尾部取）、或乱序并发消费 → 红；把 `submit` 写成只入队不返回 bool → 红。

### T12 有界：队列满时 `False` 且不入队
- **断言要点**：`queue_size=2`、**不 start**，连续提交 3 个不同 key（同一次事件循环推进内）→
  `[True, True, False]`；随后 `start()+stop()` → `processed()` 恰 2 条（第 3 条既没入队也没丢）。
- **反向构造**：`await queue.put()` 不判 `full()`（第 3 次会一直阻塞 → `asyncio.wait_for` 超时 →
  红）；静默 `return True` 但不入队（`processed()` 只有 2 条且第 3 次是 True → 红）。

### T13 `submit` 非 `Notification` 拒绝（**反向**）
- **断言要点**：`{"key": "k", ...}`（dict）、`None`、`"k"`、`object()` 一律 `ValueError`；
  且**不入队**（此后 `stop()`，`processed()` 为空）。
- **反向构造**：`AttributeError`（直接取 `.key`）→ 红；静默返回 `False` 而不是 `ValueError` → 红。
  「期望失败」：通过条件 = 捕获 ValueError。

### T14 `stop()` 排空后顺序稳定
- **断言要点**：`start()` 后提交 3 条，`stop()` **返回后** `processed()` 恰 3 条且顺序 = 提交顺序；
  `stop()` 返回时注入队列无残留未完成项（`queue.empty()` 为真）。
- **反向构造**：`stop()` 直接 cancel 消费任务而不 `await queue.join()`（少 1–3 条、非确定性 → 红）；
  `stop()` 先取消消费任务再 join → 红。

### T15 `processed()` 返回副本
- **断言要点**：两次 `processed()` 是不同 list；同下标的 dict `is not`；改返回的 list / dict 后
  再取一次仍等于原值。
- **反向构造**：返回内部 list 本身或缓存的 dict 引用 → 红。

### T16 `stop()` 幂等
- **断言要点**：`start()` + 1 条 + `stop()` 后再 `stop()` 不抛异常；`processed()` 仍 1 条。
- **反向构造**：第二次 `stop()` 抛 `RuntimeError`（把它写成「已停止」的显式拒绝）→ 红。
  注意与 T18/T19 的差别：`stop` 之后 `start`/`submit` 必须抛 `RuntimeError`，但 `stop` 本身幂等。

### T17 未 `start()` 的 `stop()` 立即返回、不排空
- **断言要点**：注入共享队列 `shared`，`submit` 1 条后直接 `await stop()` → 立刻返回；
  `shared.qsize() == 1`（没被消费、没被丢弃）、`processed() == []`；再用**另一个** worker 接管同一
  队列 `start()+stop()` → 恰 1 条（证明队列内容原样保留）。
- **反向构造**：`stop()` 无条件 `await queue.join()`（没有消费者 → 永久阻塞 → 超时 → 红）；
  或 `stop()` 把队列清空（`qsize()==0` → 红）。

### T18 `stop()` 之后 `submit` 抛 `RuntimeError`（**反向**）
- **断言要点**：`start()+stop()` 后 `await submit(Notification(...))` 抛 `RuntimeError`（不是
  `ValueError`、不是静默 `False`、不是成功入队）。
- **反向构造**：把「已停止」写成 `False` 返回值（更常见的错法）→ 红；抛 `ValueError` → 红。
  「期望失败」：通过条件 = 捕获 RuntimeError。

### T19 `stop()` 之后 `start()` 抛 `RuntimeError`（**反向**）
- **断言要点**：同 T18 的先后顺序，`await start()` 抛 `RuntimeError`；且不产生新的消费任务
  （场景内 `asyncio.all_tasks()` 除当前任务外为空）。
- **反向构造**：静默重启（把 `_closed` 复位）→ 红；抛 `ValueError`/`AssertionError` → 红。

### T20 构造器参数校验（**反向**）
- **断言要点**：`queue_size` 为 `0` / `-1` / `True` / `"2"` / `2.0` 一律 `ValueError`；
  `queue` 为 `{}` / `[]` / `"q"` 一律 `ValueError`；`queue_size=1` 与
  `NotificationWorker(queue=asyncio.Queue())` 构造成功；`queue_size=True` **不许**被当成 1。
- **反向构造**：用 `assert` / `TypeError` / 只在 `start()` 时报错 → 红；把 `True` 放行 → 红。

### T21 两个 worker 共享同一 `asyncio.Queue`
- **断言要点**：`shared = asyncio.Queue()`，两个 `NotificationWorker(queue=shared)` 都 `start()`；
  worker A 提交 `("s1", 1)`、`("s2", 2)` 得 `True`，再提交 `("s1", 3)` 得 `False`；
  两边 `stop()` 后聚合 `processed()` 恰 2 条、每个 key 最多出现一次；`shared.empty()` 为真。
- **反向构造**：把注入的 `queue` 忽略（各自新建队列）→ 注入队列的 `qsize()` 一直是 0 且
  `shared.join()` 在 `stop()` 里等不到完成 → 红；跨 worker 去重**不要求**（去重表是每 worker
  一份，见 §5 边界）。

### T22 取消 `stop()` 时 `CancelledError` 不吞（**反向**）
- **断言要点**：注入一个 `asyncio.Queue` 子类，其 `join()` 永不返回（`await asyncio.Event().wait()`），
  `start()` 后创建 `stop()` 任务并让出事件循环若干次 → 断言该任务**确实还 pending**（否则本用例
  自证无效，判 fail）；`task.cancel()` 后 `await task` 必须抛 `asyncio.CancelledError`；
  该任务结束后 `asyncio.all_tasks()` 除当前任务外**为空**（不残留 pending 消费任务）。
- **反向构造**：`except asyncio.CancelledError: pass`（或 `except BaseException` 后正常 `return`）
  → `await task` 正常返回 → 红；清理时不取消自己的消费任务 → 残留 pending 任务 → 红。
  「期望失败」：通过条件 = 捕获到 CancelledError **且** 无残留任务。

### T23 同一场景两次运行逐字节一致
- **断言要点**：同一函数内跑两遍（两次 `asyncio.run`）：默认 worker、提交 4 次（key 依次
  `d1, d2, d1, d3`，order_id 0–3）、`stop()`；两遍 `json.dumps(processed, sort_keys=True)`
  逐字符相同；长度 3（去重生效）且 key 顺序 `d1, d2, d3`。
- **反向构造**：用 `time` / `random` 生成顺序或 id（两遍不同 → 红）；消费顺序不稳定 → 红。

## 3 EN 组（入口）

### EN1 冒烟脚本退出码 0
- **断言要点**：在树副本里 `<sys.executable> tools/notify_smoke.py`，退出码 0、stderr 不含
  `Traceback`。
- **反向构造**：脚本 import 路径写错（`ModuleNotFoundError`）、退出码非 0 → 红。

### EN2 冒烟脚本 stdout 形状
- **断言要点**：stdout 去掉空行后**恰 1 行**；该行是合法 JSON 数组、恰 2 条；
  逐条键集合 = `{key, order_id, kind}`；顺序为 `smoke-1`（`order_id=1`, `kind=email`）、
  `smoke-2`（`order_id=2`, `kind=sms`）。
- **反向构造**：打印 3 条（没去重）、多打印一行调试信息、返回 dict 而非 list → 红。

### EN3 冒烟脚本两次运行逐字节相同
- **断言要点**：同一副本内跑两次，两次 stdout 的 UTF-8 字节**完全相同**；两次退出码都为 0。
- **反向构造**：输出里带时戳 / 随机 id / 内存地址（`id()`）/ dict 顺序不稳 → 红。

### EN4 `tests/test_notify_smoke.py` 静态 import `main` 并调用
- **断言要点**：AST 里存在 `from tools.notify_smoke import main`（或 `import tools.notify_smoke`
  后用 `tools.notify_smoke.main`）；存在对 `main` 的 `Call`；至少 1 个 `assert`；无 `skip`/
  `skipif`/`xfail`。
- **反向构造**：只用 `subprocess` 跑脚本、不静态 import（A9 的静态边断掉 → 这条红，且 A 维度的
  A9 也会红）；只 import 不调用 → 红。

### EN5 `docs/async.md` 的四个二级标题
- **断言要点**：文件含 `## 队列语义`、`## 幂等`、`## 取消`、`## 停机` 四个**逐字**二级标题，
  顺序与上列相同；每个标题到下一个二级标题之间至少一行非空正文（不是标题本身、不是空行）。
- **反向构造**：缺一个标题、顺序错、标题写成三级 / 带前缀、标题下没有正文 → 红。

### EN6 `README.md` 的「结构」表新增一行
- **断言要点**：存在一张 markdown 表行，其**第一列**（去反引号、去空白）恰为
  `src/shop/notify_worker.py`；基线 4 行（`src/shop/order_controller.py`、`order_service.py`、
  `order_repository.py`、`tests/`）仍在。
- **反向构造**：写在正文而不是表行、写在第二列、路径写成 `shop/notify_worker.py` → 红；
  删掉基线行 → 红。

### EN7 全树 `pytest` 绿
- **断言要点**：树副本里 `<sys.executable> -m pytest -q -p no:cacheprovider` 退出码 0；
  输出里含 `passed`；不含 `failed` / `error` 计数行。
- **反向构造**：任一用例失败、收集错误、conftest 报错 → 红。

### EN8 收集数 ≥ 7 且 3 个新测试文件都被收集
- **断言要点**：`-m pytest --collect-only -q -p no:cacheprovider` 的收集项数 ≥ 7（基线 4 + 3 个
  新文件各至少 1 条）；输出里出现 `tests/test_notify_model.py::`、`tests/test_notify_worker.py::`、
  `tests/test_notify_smoke.py::` 三个前缀。
- **反向构造**：新测试文件为空、被 `__init__.py` 遮蔽、或写成非 `test_` 前缀 → 红。

## 4 I 组（接口与树形状）

### I1 模块形状与协程方法
- **断言要点**：`shop.notify_model.Notification` 是 dataclass，`fields` 名顺序恰为
  `("key", "order_id", "kind")`；`shop.notify_worker.NotificationWorker` 是类；
  `start` / `submit` / `stop` 是 `inspect.iscoroutinefunction` 为真的方法；`processed` 是普通方法。
- **反向构造**：把 `submit` 写成同步方法、把 `processed` 写成协程、字段顺序换位 → 红。

### I2 构造器签名
- **断言要点**：`inspect.signature(NotificationWorker.__init__)` 的参数名顺序为
  `["self", "queue_size", "queue"]`；默认值 `queue_size == 4`、`queue is None`；
  `NotificationWorker()` 与 `NotificationWorker(2)` 都能构造（位置参数形态可用）。
- **反向构造**：参数改名（`size` / `maxsize`）、默认值不是 4、把 `queue` 写成必填 → 红。

### I3 AST 确定性：无时钟 / 随机 / 网络
- **断言要点**：对 6 个新 .py（`src/shop/notify_model.py`、`src/shop/notify_worker.py`、
  `tools/notify_smoke.py`、3 个新测试文件）做 AST 扫描：调用的点分名不得命中
  `time.sleep` / `time.time` / `time.monotonic` / `time.perf_counter` / `random.*` /
  `socket.*` / `requests.*` / `urllib.request.*` / `httpx.*` / `http.client.*`。
- **反向构造**：`random.random()` 生成 key、`time.sleep(0.01)` 等事件循环、`urllib` 打桩 → 红。
  `asyncio.sleep(0)`（让出事件循环）**不判违规**（见 §5 边界）。

### I4 旧队列保留 + 弃用标注 + 行为不变
- **断言要点**：`shop.notification.__doc__` 同时含子串 `已弃用` 与 `NotificationWorker`；
  `NotificationQueue` 仍存在；`append` 存副本（改入参不影响队列）、`pop` 先进先出、
  `len` 计数、空队列 `pop` 抛 `IndexError`。
- **反向构造**：删掉旧队列 / 改成异步 / docstring 只写 `deprecated` 而不含两个指定子串 → 红。

### I5 `tests/test_notification.py` 断言弃用说明且保留原用例
- **断言要点**：AST 里有一个 `assert`，其源码（`ast.unparse`）同时引用 `__doc__`（或 `doc`）
  与子串 `已弃用`；原用例 `test_sync_queue_keeps_order_and_length` 仍在；该文件无
  `skip`/`skipif`/`xfail`。
- **反向构造**：只改生产文件不改测试（没有断言 → 红）、删掉原用例 → 红。这条同时钉住
  acceptance A11 的「测试断言该说明存在」。

### I6 11 个冻结基线文件逐字节不变
- **断言要点**：`AGENTS.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、
  `src/shop/order_controller.py`、`src/shop/order_repository.py`、`src/shop/order_service.py`、
  `tests/test_order_controller.py`、`tests/test_order_repository.py`、
  `tests/test_order_service.py`、`tools/__init__.py` 的 sha256 与 runner 内写死的基线值相等。
- **反向构造**：顺手重构 `order_*.py`、给 `conftest.py` 加路径、改 `pytest.ini` → 红。
  这是 C 的 `frozen_untouched`（3 分）在 T 侧的同一份事实，但**两处各自独立读数**。

### I7 文件集 = 21 且改动 ⊆ 10 条允许写
- **断言要点**：忽略 `.policy` / `__pycache__` / `.pytest_cache` / `.ruff_cache` / `*.pyc` 后，
  树内文件集**恰等于** 14 个基线文件 ∪ 7 个新建文件（21 个，无多余文件）；
  与基线逐文件 sha256 比较得到的「改动集合」⊆ 10 条允许写。
- **反向构造**：多写一个 `docs/notes.md` / `tools/__init__.py.bak` → 文件集不等 → 红；
  改了 `src/shop/order_service.py` → 改动集合越界 → 红。

## 5 边界（写下来，免得后来者以为是漏测）

- **纯空白的 `key`／`kind` 不判**：`"   "` 是否算「非空 str」在 SPEC 里没有定论，本计划只钉
  `""` 与非 `str`；把它写成 `strip()` 之后的空串**不**让本计划红（这是**可能漏**的方向）。
- **跨 worker 去重不要求**：T21 只要求「同一 worker 的重复 key 返回 False」，两个 worker 各有
  自己的去重表（SPEC 未要求跨实例共享）；用例里的重复 key 打给同一个 worker。
- **`asyncio.sleep(0)` 不判违规**：I3 只禁 `time.sleep` / `time.*` / `random` / 网络；
  让出事件循环用 `asyncio.sleep(0)` 是确定性写法。隐藏 runner 自己用 `asyncio.sleep(0)` 与
  `asyncio.wait_for` 驱动，不属于被评代码。
- **T22 的注入队列是 `asyncio.Queue` 子类**：接口契约写的是 `isinstance(queue, asyncio.Queue)`，
  子类合法；用「`join()` 永不返回」把 `stop()` **确定性地**卡在 pending 上，否则取消无处发生
  （未卡住时本用例自证无效、直接判 fail，不退化成空过）。
- **T12 的「不 start」形态**：三个 `submit` 都在同一次事件循环推进内完成（`put_nowait`），
  没有消费机会，队列满的判定因此确定；若实现用 `await queue.put()`，用例以 20 秒
  `asyncio.wait_for` 超时判红（不挂死 runner）。
- **A9 与 I7 的分工**：I7 只回答「文件集与改动集合」；「每个生产文件被测试静态 import」由
  `tools/structure_metrics.py` 的 A9 回答（A 维度），T 不重复计分，但 EN4 从 T 侧钉住
  `tools.notify_smoke` 的那条边（否则 A9 的 `tools/notify_smoke.py: no_test_import` 会失败）。
- **不判 `processed()` 的 dict 键顺序**：JSON 值相等即相等（`sort_keys` 比较），不做字节比较；
  与「逐字节相同」只在 EN3 的 stdout 与 T23 的 `json.dumps(sort_keys=True)` 上要求。

## 6 树形状常数（runner 内写死，运行时不读 baseline）

14 个基线文件的 sha256 由包内 `baseline/` 实算（组合摘要
`d12576d82488d3665ea38bacdb6b1a32e23b08caa979f316ca6ba07aadb581e8`，与 `scoring.yaml` 的
`frozen_inputs.baseline_combined_digest` 同值）；7 个新建路径与 10 条允许写取
`task-package/allowed-writes.txt` 与 `SPEC.md` §3。冻结的 11 个 = 14 − 允许写 ∩ 基线（3）。

## 7 作者独立性（本批的诚实边界）

`bank/README.md` §4.3 与 `SPEC.md` 要求隐藏用例由**未参与任务设计/实施**的子会话写。本批是
**同一个子会话**先写 PLAN + runner（本文件与 `runner.py` 在**参考解之前**落盘并先跑基线红），
**之后**才写 `reference/tree`；写 PLAN/runner 时没有读过任何参考实现（本题 `reference/` 当时
不存在，也没有读旗舰的 `reference/`）。这仍然是**降级**的独立性：作者知道自己的实现意图。
降级事实记在 `reference/README.md` 的偏差段与 Lead 报告里，不冒充独立出题。
