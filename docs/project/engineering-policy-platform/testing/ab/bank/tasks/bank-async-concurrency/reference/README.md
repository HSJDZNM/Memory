# 参考解（bank-async-concurrency）

> **是什么**：本题的参考实现（从 `baseline/` 复制成 `tree/`，按 `SPEC.md` + `task-package/first-message.md`
> 完成整题）。**不进判据**：判分只看被评树（T = `hidden/runner.py`、C = `policy.check`、
> A = `tools/structure_metrics.py`）。它的用途是实测天花板：证明 38 条隐藏用例**可全过**、
> A 的 10 条谓词**可全 pass**、C 的 8 次 `policy.check` **可以一个 error 都没有**。
> 参考树是按「允许写 10 条」逐条搭的，可复核；与 baseline 的 diff 就是这 10 条。

## 1 决策点（为什么这么写）

| id | 决策 | 理由 / 影响 |
| --- | --- | --- |
| D1 | `NotificationWorker.__init__(queue_size=4, queue=None)` 多一个**可选**的 `queue` | SPEC §3 只写 `queue_size`，但 SPEC §5 要求「两个 worker 消费**同一队列**」；任务 README §8.3 已裁定接受这个可选注入。没有它 A7（共享队列）不可表达 |
| D2 | 去重表 `_seen` 在 worker 生命周期内保留（记录处理完之后仍生效） | 首消息 A3 的「处理后仍生效」是显式语义；去重按 **key**，不按整条记录 |
| D3 | `stop()` 先把 `_closed` 置位再排空；`_closed` 之后 `start` / `submit` 抛 `RuntimeError` | 关闭只有一个方向（fail-closed）；`stop` 自身幂等（再调直接返回），与 `start` / `submit` 的拒绝形态**不同**，各自被 T16 / T18 / T19 钉住 |
| D4 | `stop()` 只在 `await queue.join()` 外包一层 `except asyncio.CancelledError`：先 `_shutdown()`（取消并回收自己的消费任务）再 `raise` | 「不吞取消」的写法只有这一种是可测的：吞掉（`pass` 后正常返回）会让 T22 红；清理不彻底会让 T22 的「无残留任务」红 |
| D5 | 消费循环：`await queue.get()` → 追加副本 → `queue.task_done()`（**先记录，后标记完成**） | `queue.join()` 返回时未完成数已归零；顺序反了会让 `stop()` 返回后 `processed()` 少条目（T14 会红） |
| D6 | `submit` 的判定顺序：关闭 → 类型（`ValueError`）→ 去重（`False`）→ 满（`False`）→ `put_nowait` | 类型错是调用方 bug（异常），去重/满是有意义的返回值；`_seen` 只在**真的入队**之后才写，满队列被拒的 key 之后还能重试 |
| D7 | 冒烟脚本把 `<root>/src` 插进 `sys.path`，紧随的 import 行加 `# noqa: E402` | 与 `conftest.py` 同一写法；STYLE-004（E402）的**实测**可触发形态是「先有模块级赋值再 import」，本题就是这样（`ROOT = ...`） |
| D8 | 测试里的异步场景写成**私有**内嵌协程 `_scenario()`，用 `asyncio.run` 驱动 | 不用 pytest-asyncio（首消息明令）；私有前缀是 A7 的要求——A7 对**公开**定义查 docstring，内嵌公开函数会各算一处缺失（首版就是这么红的，见 §5） |
| D9 | 旧队列只改**模块 docstring**（含 `已弃用` 与 `NotificationWorker` 两个子串），`append` / `pop` / `__len__` 一个字节不动 | SPEC §3 与 A11 的原文；`tests/test_notification.py` 新增一条断言把说明钉住（I5 要求断言本身引用 `__doc__`） |
| D10 | 有界性用 `queue.full()` + `put_nowait()`，不 `await put()` | 「满 → 返回 `False`，不阻塞、不静默丢」；`await put()` 会在满时挂住（T12 用 20 秒预算判红，不挂死 runner） |

## 2 交付面（10 条允许写）

| 路径 | 动作 | 要点 |
| --- | --- | --- |
| `src/shop/notify_model.py` | 新建 | frozen dataclass + `__post_init__` 校验（含 `bool` 冒充 `int`）+ `to_dict()` 返回新 dict |
| `src/shop/notify_worker.py` | 新建 | 消费任务 / 幂等 / 有界 / 排空 / 取消 / 关闭语义 |
| `tools/notify_smoke.py` | 新建 | `main() -> list[dict]`；`__main__` 打印单行 JSON（`ensure_ascii=False, sort_keys=True`） |
| `tests/test_notify_model.py` | 新建 | 7 个用例（13 条 assert） |
| `tests/test_notify_worker.py` | 新建 | 9 个用例（21 条 assert），含 stuck-queue 取消用例 |
| `tests/test_notify_smoke.py` | 改写基线（静态契约测试 → 行为测试） | 静态 `from tools.notify_smoke import main` + 3 条 assert（A9 的那条静态边） |
| `docs/async.md` | 新建 | 4 个指定二级标题（队列语义 / 幂等 / 取消 / 停机） |
| `README.md` | 修改 | 「结构」表加 `src/shop/notify_worker.py` 一行，其它行不动 |
| `src/shop/notification.py` | 修改 | 模块 docstring 加弃用说明；实现不动 |
| `tests/test_notification.py` | 修改 | 新增 `test_sync_queue_module_is_deprecated`（断言 docstring 含两个子串） |

## 3 读数（本机实测；参考树 = 21 文件）

| 维度 | 命令 | 读数 |
| --- | --- | --- |
| T（参考树） | `BANK_TASK_TREE=<reference/tree> .venv/Scripts/python.exe hidden/runner.py` | **38/38**、exit 0、两次输出逐字节相同（sha256 `3d216ebcd82f0606c50f7b5aef6ac677c3588a39ab1593ec103651418b84e98a`，取自仓库根 cwd、树标签为仓库相对路径） |
| T（基线） | 同一命令，树 = `baseline/` 的副本 | **2/38**、exit 1、两次逐字节相同（sha256 `7941facf266ba8f9ae2a4488cef97254b06db1d96fd1961229a94e39b13542ee`）；只剩 EN7（基线 pytest 绿）与 I6（基线冻结文件当然没变） |
| pytest | `cd <reference/tree> && python -m pytest -q` | **22 passed**、exit 0（基线 4 passed, 1 skipped → 22） |
| 冒烟 | `cd <reference/tree> && python tools/notify_smoke.py` | exit 0，单行 JSON、恰 2 条（`smoke-1` → `smoke-2`） |
| A | `python tools/structure_metrics.py --workspace <reference/tree> --layers <task>/layers.yaml --interfaces <task>/interfaces.yaml --json` | **10/10 pass**、exit 0（A1–A10 全 pass；A9 覆盖 8/8 生产文件） |
| C | 8 次 `python -m policy.check <file> ... --operation edit --changed <10 条> ...`（见 §4） | **8/8 `allow`**、8 次 exit 0、**0 条 error、0 条 warning**；每次 `skipped_rules=[ARCH-001@1]`（scope 不匹配，不是通过）、`blocking_capable_skipped=1`、`complete=true` |
| C 计分 | 7 条适用规则 × 3 + 冻结文件 3 + 无旁路 3 | **27/27**（`effective_total=27`；ARCH-001 的 3 分 `not_applicable`） |

旁路三项（C 的 3 分）也逐条实测：控制面目录（`policies/`、`registry/`、`validation/`、`adapters/`、`api/`）
在参考树里**都不存在**；每个新测试文件都有 assert 且无 `skip` / `skipif` / `xfail`（13 / 21 / 3 条 assert）；
`--collect-only -q` 收集 **22** 条（≥7）；树 diff 恰为上述 10 条允许写。

## 4 复算命令

```powershell
# A
.venv/Scripts/python.exe tools/structure_metrics.py --workspace docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-async-concurrency/reference/tree --layers docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-async-concurrency/layers.yaml --interfaces docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-async-concurrency/interfaces.yaml --json

# T（同一棵树跑两次，比对 stdout 的 sha256）
$env:BANK_TASK_TREE = 'docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-async-concurrency/reference/tree'
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-async-concurrency/hidden/runner.py

# C（8 个文件逐个；--changed 是 append，10 条写 10 次；--request-id 固定）
$env:PYTHONPATH = 'src'
.venv/Scripts/python.exe -m policy.check src/shop/notify_worker.py --workspace <tree> --config-root . --layer service --operation edit --changed README.md --changed docs/async.md --changed src/shop/notification.py --changed src/shop/notify_model.py --changed src/shop/notify_worker.py --changed tests/test_notification.py --changed tests/test_notify_model.py --changed tests/test_notify_smoke.py --changed tests/test_notify_worker.py --changed tools/notify_smoke.py --request-id bank-async-reference-notify-worker --json
```

## 5 与 SPEC / 首消息的偏差与踩到的坑

1. **构造器多一个可选 `queue` 参数**（D1）：SPEC §3 只写 `queue_size`；这是任务 README §8.3 已经裁定的
   构造修复，不是本参考解自创。若 Lead 要求逐字照 SPEC，则 A7 的一条隐藏用例（T21）必须删掉，
   并同批改 `acceptance.md` / `interfaces.md` / 首消息。
2. **A7 对「公开的内嵌函数」也要求 docstring**（D8）：首版测试把异步场景写成内嵌 `def scenario()`，
   A7 报 9 处缺失（8 个 `scenario` + `StuckQueue.join`）。参考解改成私有 `_scenario` 并给 `join`
   补 docstring 之后 A 才 10/10。**后来的题要注意**：A7 的口径是「模块 + 全部公开定义」，内嵌函数也算。
3. **DOC-004（Ruff D401）会咬中文 docstring 的英文首词**（实测）：`"""action() 抛 ValueError 时……"""` 被判
   「非祈使语气」，`allow_with_warnings`；改成以中文动词开头（`"""判断 action() 是否……"""`）即通过。
   这不是 SPEC 的判据（DOC-004 不在 C 的 8 条里），但参考解取「8 次全 `allow`」的干净形态。
4. **隐藏作者与参考解作者是同一个子会话**（独立性降级）：`hidden/PLAN.md` 与 `hidden/runner.py` 在
   **参考解之前**落盘并先跑出基线红（2/38），PLAN 里没有参考实现的任何细节；但作者确实知道自己的实现意图。
   这与 `bank/README.md` §4.3 的「未参与设计/实施的子会话」不符，如实记在这里，不冒充独立出题。
5. **参考解不引入任何新依赖**：只用标准库 `asyncio` / `json` / `dataclasses`；没有 pytest-asyncio、
   没有网络/时钟/随机数。
6. **参考树里没有 `.policy/` 与缓存**：21 个文件 = 15 基线 + 6 新建；参考读数都在副本或
   `PYTHONDONTWRITEBYTECODE=1` 下跑，树本身一个字节没多。
