# 里程碑顺序（M1–M10；内容与 first-message.md 同源；本文件用行内代码标注路径，去掉反引号后逐字一致）

M1 写 `tools/notify_smoke.py`（`main()` + `__main__` 打印 JSON；`sys.path` 后的 import 行加 `# noqa: E402`；本步不运行脚本），然后跑一次 `python -m pytest -q`（基线的 `tests/test_notify_smoke.py` 是静态契约测试，会检查工具公开面，应通过）。
M2 先写 `tests/test_notify_model.py`（覆盖 A1/A2；不 import 其它新模块），然后跑一次 `python -m pytest -q`（实现还没写，测试失败是预期）。
M3 再写 `src/shop/notify_model.py` 的最小实现（dataclass + 构造校验 + `to_dict`），然后跑一次 `python -m pytest -q`。
M4 先写 `tests/test_notify_worker.py`（覆盖 A3–A8；异步用例用 `asyncio.run` 驱动；共享队列用 `NotificationWorker(queue=shared)`），然后跑一次 `python -m pytest -q`（`shop.notify_worker` 还没写，失败是预期）。
M5 再写 `src/shop/notify_worker.py`（消费任务 + 幂等 + 有界 + 排空 + 取消不吞），然后跑一次 `python -m pytest -q`。
M6 改 `src/shop/notification.py` 的模块 docstring（含 `已弃用` 与 `NotificationWorker`），再改 `tests/test_notification.py` 补断言（A11），然后跑一次 `python -m pytest -q`。
M7 写 `docs/async.md`（4 个指定二级标题）并改 `README.md` 的「结构」表加 `src/shop/notify_worker.py` 一行（A10），然后跑一次 `python -m pytest -q`。
M8 把基线的 `tests/test_notify_smoke.py`（静态契约测试）改写为行为测试：`from tools.notify_smoke import main`，调用 `main()` 并断言去重后 2 条（A9）；然后跑一次 `python -m pytest -q`。
M9 再跑一次 `python -m pytest -q tests/test_notify_worker.py`、一次 `python -m pytest -q` 与一次 `python tools/notify_smoke.py`，把结果照原文贴出来（确定性用例要连续两次一致）。
M10 最后跑 `python -m pytest -q` 与 `python tools/notify_smoke.py`，用不超过 120 字汇报：每个里程碑做了什么、哪些动作被拒（照原文理由）、最后一次测试与脚本输出。

`M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9 → M10`；固定顺序、不固定逐条工具调用（05 §5.2）。

## 预期读数（写给 Lead 与读数者，模型看不到本文件）

| 步 | 预期 | 说明 |
| --- | --- | --- |
| **M1 的「先写实现」** | 本地 `pytest` 绿（5 passed：4 个基线用例 + 基线静态契约测试；本步工具已在树里，静态测试不 skip）；`policy.check` **两臂分叉**：A（`tools` 非生产）**`block`**（`TESTING-002`，`selection.level=none`，`failing_tests` 未被服务）、B（`tools` 是生产文件）**`allow`**（`selection.level=related`，nodeids 含 `tests/test_notify_smoke.py`） | **设计方向步**（C1-b §7.3 形态）：M1 的批为空，模型自己写的测试进不了 `--changed`；A 因为 `tools` 不是生产文件选不到测试，B 选得到基线静态契约测试并跑通。离线实测见 `coverage.md` §2 的 `probe-async-m1-design`；构造变更理由见 `readings/2026-10-22-bank-k3-gate0-activation.md` §5 |
| M2 / M4 的「先写测试」 | 本地 `pytest` 红；`policy.check` 应为 `allow_with_warnings` + `pending_findings`（AGENTS 第 51 条「待实现」） | 缺失的是**项目内**模块（`shop.notify_model` / `shop.notify_worker`）；基线已有 `src/shop/__init__.py`，所以走 pending 而不是真违规（同形探针 `probe-async-p3-pending`） |
| M3 / M5 / M6 / M7 / M8 | 本地 `pytest` 绿；`policy.check` 应 `allow` | M6 改 `notification.py` 时同名测试已存在（基线 `tests/test_notification.py`）；M8 的树与参考树一致（实现已在 M1 落地，本步只改写测试文件），读数同 `README.md` §9.4 的 `tests/test_notify_smoke.py` 行（`allow`） |
| 任何一步「先写实现、后写测试」（`src/` 新文件） | `TESTING-001`（missing_tests）error → `block` | 新建 `src/shop/notify_model.py` 而没有 `tests/test_notify_model.py` 的探针已实测为 `block`（`probe-async-p2-missing-tests`）；`tools/notify_smoke.py` **不属于**这一形态（基线已有同名静态契约测试） |
| 任何一步打断相关测试 | `TESTING-002`（failing_tests）error → `block` | 每次 `policy.check` 都会跑选中测试；失败即 error |

任务完成判定（A1–A12）用包内 `acceptance.md` + 隐藏用例；A12 用树 diff 对 `allowed-writes.txt`。
