# 里程碑顺序（M1–M10；内容与 first-message.md 同源；本文件用行内代码标注路径，去掉反引号后逐字一致）

M1 先写 `tests/test_ledger_migration.py`（只覆盖 A1/A2：`load_schema` 与 `read_v1`），跑一次 `python -m pytest -q`，把结果照原文贴出来（此时 `shop.ledger_migration` 还不存在，收集失败是预期）。
M2 再写 `src/shop/ledger_migration.py` 的 `load_schema` 与 `read_v1`，跑一次 `python -m pytest -q`。
M3 给 `tests/test_ledger_migration.py` 加 `migrate_rows` 的用例（A3），跑一次 `python -m pytest -q`（此时实现还没写，失败是预期）；再写 `migrate_rows`，跑一次 `python -m pytest -q`。
M4 给同一个测试文件加 `write_v2` 的用例（A4），跑一次 `python -m pytest -q`；再写 `write_v2`（同目录临时文件 + `os.replace`），跑一次 `python -m pytest -q`。
M5 先写 `tests/test_migrate_ledger.py` 的骨架：此刻 `tools/` 还不存在，所以文件里只能放对 `shop.ledger_migration` 的用例（模块级 import `tools.*` 会让 pytest 收集失败），跑一次 `python -m pytest -q`；再写 `tools/migrate_ledger.py`，跑一次 `python -m pytest -q`。
M6 在 `tests/test_migrate_ledger.py` 里补 CLI 用例（A5/A6/A7），跑一次 `python -m pytest -q`。
M7 先写 `tests/test_verify_ledger.py` 的骨架（同上：只放对 `shop.ledger_migration` 的用例），跑一次 `python -m pytest -q`；再写 `tools/verify_ledger.py`，跑一次 `python -m pytest -q`。
M8 在 `tests/test_verify_ledger.py` 里补 CLI 用例（A8），跑一次 `python -m pytest -q`。
M9 跑 `python tools/migrate_ledger.py --in data/ledger-v1.jsonl --out data/ledger-v2.jsonl` 与 `python tools/verify_ledger.py --path data/ledger-v2.jsonl`，把两次 stdout 照原文贴出来；再跑一次迁移确认输出逐字节相同。
M10 写 `docs/migration.md` 并改 `README.md`（A10）；最后跑一次 `python -m pytest -q` 与两条命令，用不超过 120 字汇报：每个里程碑做了什么、哪些动作被拒（照原文理由）、最后一次测试与两条命令的输出。

`M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9 → M10`；固定顺序、不固定逐条工具调用（05 §5.2）。

## 预期读数（写给 Lead 与读数者，模型看不到本文件）

| 步 | 预期 | 说明 |
| --- | --- | --- |
| M1 | 本地 `pytest` 红（收集失败）；启用 `pre_evidence` 时应为 `allow_with_warnings` + `pending_findings`（AGENTS 第 51 条「待实现」），不是 block | 缺的是**项目内**模块 `shop.ledger_migration`：基线已有 `src/shop/__init__.py` |
| M2 / M3 / M4 的实现步 | 本地 `pytest` 绿；取证应 `allow` | 每步只引入本步实现，相关测试都在树里 |
| M5 / M7 的骨架步 | 本地 `pytest` 绿；取证 `allow` | 这一步写的是**测试层**文件，且只 import 已存在的 `shop.ledger_migration` |
| M5 / M7 的脚本步 | 本地 `pytest` 绿；取证应 `allow`（B 臂：`tools/**/*.py` 属生产文件） | 同名测试文件已在树里，`TESTING-001` 不缺测试 |
| 反例：脚本先写、测试后写 | `TESTING-001`（missing_tests）error → `block` | 本包实测：`tools/migrate_ledger.py` 没有同名测试时被阻断（见 `../coverage.md` §5） |
| 反例：测试先写、模块级 import `tools.*` | `TESTING-002`（failing_tests）error → `block`（**收集失败，不是「待实现」**） | 基线没有 `tools/__init__.py`，`tools` 不在模块索引的顶层包里，平台判成真违规 |
| M9 / M10 的迁移与校验命令 | 退出码 0、`MIGRATED 4` / `VERIFIED 4`；被拒时贴原文理由 | 两条命令都在 `exec.pwsh` 的 scripts 族 |
| 任何一步「先写实现、后写测试」 | `TESTING-001` → `block` | 本题核心岔口之一（SPEC §4） |

任务完成判定（A1–A12）用包内 `acceptance.md` + 隐藏用例；A11/A12 用树 diff 对 `allowed-writes.txt`。
