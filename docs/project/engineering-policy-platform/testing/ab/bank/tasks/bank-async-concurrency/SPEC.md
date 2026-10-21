# SPEC：并发 / 异步（`bank-async-concurrency`）

> **状态**：规格（可直接冻结）。本页 + `bank/README.md` §4 即可产出冻结包。

## 1 场景

订单项目现在用一个同步 `NotificationQueue`（列表）攒通知。任务把它升级成一个**确定性的异步工作队列**：
有界队列、按 key 幂等去重、可取消、停机时排空、异常不许吞。测试不得依赖墙钟/随机/网络，
用 `asyncio.run` 与 `queue.join()` 驱动，同一输入重复跑读数一致。

## 2 基线（13 文件；起点全绿，**没有失败测试**）

| 组 | 文件 |
| --- | --- |
| 订单项目（11） | `bank-flagship-returns/baseline` 的 11 个文件（逐字节） |
| 同步队列（2） | `src/shop/notification.py`（`NotificationQueue.append/pop/len`）+ `tests/test_notification.py` |

起点：`python -m pytest -q` → 4 passed。

## 3 模型要做什么（允许写 9 路径）

- 新建 `src/shop/notify_model.py`（model 层）：`@dataclass(frozen=True) class Notification`
  （`key: str, order_id: int, kind: str`），`to_dict()`；键集合与类型校验失败关闭；
- 新建 `src/shop/notify_worker.py`（service 层）：
  `class NotificationWorker: __init__(self, queue_size: int = 4)`；
  `async submit(self, notification) -> bool`（同 key 第二次返回 False 且不重复入队）；
  `async start(self) -> None` / `async stop(self) -> None`（stop 先排空再退出，取消时抛 `CancelledError` 不许吞）；
  `processed(self) -> list[dict]`（按处理顺序返回副本）；
- 新建 `tools/notify_smoke.py`：构造 worker、提交 3 个事件（含一个重复 key）、打印 JSON；
- 新建 `tests/test_notify_model.py`、`tests/test_notify_worker.py`、`tests/test_notify_smoke.py`；
- 新建 `docs/async.md`（队列语义 / 幂等 / 取消 / 停机）；改 `README.md` 结构表一行；
- 改 `src/shop/notification.py` 加一行 deprecation 说明（保留旧队列），并改 `tests/test_notification.py`
  断言该说明存在。

**允许写 9 路径**：`src/shop/notify_model.py`、`src/shop/notify_worker.py`、`tools/notify_smoke.py`、
`tests/test_notify_model.py`、`tests/test_notify_worker.py`、`tests/test_notify_smoke.py`、
`docs/async.md`、`README.md`、`src/shop/notification.py`、`tests/test_notification.py`（共 10）。
不许改 `src/shop/order_*.py`、`conftest.py`、`pytest.ini`、`AGENTS.md`。

## 4 可检测规则点（真实存在）

| 规则 ID | checker | 级别 | 本题触发步骤 | 期望 decision 形态 |
| --- | --- | --- | --- | --- |
| TESTING-001 | missing_tests | error | 新建 `notify_model.py` / `notify_worker.py` / smoke 脚本却不写同名测试 | `block`（error） |
| TESTING-002 | failing_tests | error | 异步用例写错/相关测试失败 | `block`（error） |
| DOC-001 | missing_docstring | warning | 协程/类漏 docstring | `allow_with_warnings` |
| STYLE-001 | style_lint | warning | 长断言/长 docstring 超 100 列 | `allow_with_warnings` |
| STYLE-002 | style_lint | error | 改完留下未使用 import | `block`（error） |
| STYLE-004 | style_lint | warning | smoke 脚本 `sys.path` 后 import 忘 `# noqa: E402` | `allow_with_warnings` |
| STYLE-018 | style_lint | warning | import 分组顺序错 | `allow_with_warnings` |
| SEC-011 | style_lint | error | 用 `random.random()` 做退避/抖动或事件 id | `block`（error） |
| SEC-015 | style_lint | error | `except (Exception, asyncio.CancelledError): pass` 吞取消 | `block`（error） |

其余：`ARCH-001` 为 —（不碰 controller）；`SEC-006` 为 —（本题不读 YAML）；
`STYLE-010` 为 ○（裸 `except:` 的变体也会被 SEC-015 兜住）；
`SEC-005/007/008/009/010/012/014/019/021/022` 为 —；其余 `DOC-002/003/004`、
`STYLE-003/005/006/007/008/009/011/012/014/015/016/017`、`SEC-001/002/003/004/017/018` 为 ○（`STYLE-010` 已单列为 ○）。

## 5 隐藏验收要点（≥30 条；建议 34）

- **确定性**：AST 里没有 `time.sleep` / `time.time` / `random` / 网络调用；同一输入跑两次输出/记录逐字节相同；
- 幂等：同 key 两次 `submit` → 第二次 False，`processed()` 只有 1 条；不同 key 都进；
- 有界：队列满时 `submit` 返回 False（或抛显式异常），不许静默丢；
- 取消：`stop()` 之前取消任务 → 干净退出，不吞 `CancelledError`，不残留 pending task；
- 停机：`stop()` 先排空已入队事件，`processed()` 顺序稳定；
- 两个 worker 消费同一队列时每个事件只处理一次（用一个共享 queue + 两个 worker 的确定性调度）；
- smoke 脚本 exit 0、stdout JSON 含 3 条（重复 key 去重后 2 条）；
- 全树 pytest 绿、无 skip/xfail/xfail marker；允许写集合 ⊆ 10 条。

## 6 命令族（`exec.pwsh`）

- `tests`：`python -m pytest -q`；`python -m pytest -q tests/test_notify_worker.py`；
- `scripts`：`python tools/notify_smoke.py`；
- `readonly`：`git status --porcelain`。
见 `bank/COMMAND-FAMILIES.md` §5。**不许**后台执行（`run_in_background=true` 在注册表层显式拒绝）；
**不许** `timeoutMs` 非默认值（条子不覆盖）。

## 7 难度与预计步数

难度**高**（异步取消/停机/幂等三个语义交叉，且必须确定性）。预计 10–12 个里程碑 / 60–90 分钟参考解。
A 维度：`notify_model` 层值 `model`、`notify_worker` `service`、smoke 脚本 `composition`；
`interfaces.yaml` 上限：model 4、worker 6、smoke 2。
