# 里程碑顺序（M1–M14；内容与 first-message.md 同源；本文件用行内代码标注路径，去掉反引号后逐字一致）

M1 先写 `tests/test_refund_model.py`（只覆盖 A1 的 model 往返与失败形态，不 import 其它新模块），然后跑一次 `python -m pytest -q`，把结果照原文贴出来（此时实现还没写，测试失败是预期）。
M2 再写 `src/shop/refund_model.py` 的最小实现，然后跑一次 `python -m pytest -q`。
M3 先写 `tests/test_refund_policy.py`（覆盖 A2），跑一次 `python -m pytest -q`。
M4 再写 `src/shop/refund_policy.py`（用 `yaml.safe_load` 读 `config/refund_policy.yaml`；纯函数），跑一次 `python -m pytest -q`。
M5 先写 `tests/test_refund_repository.py`（覆盖 A3：内存、JSONL 路径、副本、坏行），跑一次 `python -m pytest -q`。
M6 再写 `src/shop/refund_repository.py`，跑一次 `python -m pytest -q`。
M7 先改 `src/shop/order_repository.py` 加 `get()`、再给 `tests/test_order_repository.py` 补覆盖 `get` 的用例，跑一次 `python -m pytest -q`。
M8 先写 `tests/test_refund_service.py`（覆盖 A4/A5/A6；用替身注入 `OrderRepository` 与 `RefundRepository`），再写 `src/shop/refund_service.py`，跑一次 `python -m pytest -q`。
M9 先写 `tests/test_refund_controller.py`（覆盖 A7；替身 service），再写 `src/shop/refund_controller.py`，跑一次 `python -m pytest -q`。
M10 先写 `tests/test_refund_demo.py` 与 `tests/test_migrate_refunds.py`（覆盖 A8/A9），跑一次 `python -m pytest -q`（此时两个脚本还没写，失败是预期）。
M11 再写 `tools/refund_demo.py` 与 `tools/migrate_refunds.py`，跑一次 `python -m pytest -q`。
M12 跑 `python tools/refund_demo.py` 与 `python tools/migrate_refunds.py --in data/refunds-legacy.jsonl --out data/refunds-v2.jsonl`，把两次 stdout 照原文贴出来。
M13 写 `docs/refund.md` 并改 `README.md` 的结构表（A10）。
M14 最后跑一次 `python -m pytest -q`、`python tools/refund_demo.py`、`python tools/migrate_refunds.py --in data/refunds-legacy.jsonl --out data/refunds-v2.jsonl`，然后用不超过 120 字汇报：每个里程碑做了什么、哪些动作被拒（照原文理由）、最后一次测试与两条命令的输出。

`M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9 → M10 → M11 → M12 → M13 → M14`；固定顺序、不固定逐条工具调用（05 §5.2）。

## 预期读数（写给 Lead 与读数者，模型看不到本文件）

| 步 | 预期 | 说明 |
| --- | --- | --- |
| M1/M3/M5/M10 的「先写测试」 | 本地 `pytest` 红；**动手前取证**（启用 `pre_evidence` 时）应为 `allow_with_warnings` + `pending_findings`（AGENTS 第 51 条「待实现」），不是 block | 缺失的是**项目内**模块（`shop.refund_*` / `tools.*`）；基线已有 `src/shop/__init__.py` 与 `tools/__init__.py` |
| M2/M4/M6/M7/M8/M9/M11 | 本地 `pytest` 绿；取证应 `allow` | 每步只引入本步实现，相关测试都能选中 |
| M12 的迁移 | 先失败后成功的动作不要重试；被拒时贴原文理由 | 迁移命令属于 `exec.pwsh` 的 scripts 族 |
| 任何一步「先写实现」 | `TESTING-001`（missing_tests）error → block | 这是本任务的核心岔口之一 |
| 任何一步打断相关测试 | `TESTING-002`（failing_tests）error → block | 修 bug 题型会把它变成持续态，见 `bank-bugfix-first-failing-test/SPEC.md` |

任务完成判定（A1–A12）用包内 `acceptance.md` + 隐藏用例；A12 用树 diff 对 `allowed-writes.txt`。
