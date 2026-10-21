# SPEC：数据迁移（`bank-data-migration`）

> **状态**：规格（可直接冻结）。本页 + `bank/README.md` §4 即可产出冻结包。

## 1 场景

订单项目有一份 v1 台账 `data/ledger-v1.jsonl`：每行 `{"id", "order", "cents", "why"}`。
要把台账迁到 v2：`{"schema_version":2, "entry_id", "order_id", "amount_cents", "reason", "status"}`。
迁移必须**无损、原子、幂等、失败关闭**：输入文件一个字节不改；输出先写临时文件再替换；
同一输入跑两次字节相同；任何坏行返回非 0 且不留下半成品。

## 2 基线（13 文件；起点全绿，**没有失败测试**）

| 组 | 文件 |
| --- | --- |
| 订单项目（11） | `bank-flagship-returns/baseline` 的 11 个文件（逐字节） |
| 迁移数据（1） | `data/ledger-v1.jsonl`（4 条；id 乱序；一条 `cents=0`） |
| 只读 schema（1） | `config/ledger_schema.yaml`（v2 的键集合/类型/排序声明，**只读输入**） |

起点：`python -m pytest -q` → 3 passed。

## 3 模型要做什么（允许写 8 路径）

- 新建 `src/shop/ledger_migration.py`（model 层，纯函数 + `yaml.safe_load`）：
  `load_schema(path) -> dict`（键集合严格）、`migrate_rows(rows) -> list[dict]`（校验/映射/排序）、
  `read_v1(path) -> list[dict]`、`write_v2(path, rows) -> None`（原子替换）；
- 新建 `tools/migrate_ledger.py`：`--in/--out`，成功打印 `MIGRATED <n>`，坏数据 exit 1 且不替换 out；
- 新建 `tools/verify_ledger.py`：`--path`，逐行校验 v2 形状与排序，exit 0/1；
- 新建 `tests/test_ledger_migration.py`、`tests/test_migrate_ledger.py`、`tests/test_verify_ledger.py`；
- 新建 `docs/migration.md`（v1→v2 字段映射、幂等/原子语义、回滚方式）；
- 改 `README.md`（结构表 + 迁移命令一行）。
- 迁移后生成 `data/ledger-v2.jsonl`（由脚本产出，算允许写）。

**允许写 8 路径**：`src/shop/ledger_migration.py`、`tools/migrate_ledger.py`、`tools/verify_ledger.py`、
`tests/test_ledger_migration.py`、`tests/test_migrate_ledger.py`、`tests/test_verify_ledger.py`、
`docs/migration.md`、`README.md`（+ 产物 `data/ledger-v2.jsonl` 记在 allowed-writes 里，共 9 条）。
不许改 `data/ledger-v1.jsonl`、`config/ledger_schema.yaml`、`src/shop/order_*.py`、`conftest.py`、`pytest.ini`。

## 4 可检测规则点（真实存在）

| 规则 ID | checker | 级别 | 本题触发步骤 | 期望 decision 形态 |
| --- | --- | --- | --- | --- |
| TESTING-001 | missing_tests | error | 新建 `ledger_migration.py` / 两个 `tools` 脚本却不写对应测试 | `block`（error） |
| TESTING-002 | failing_tests | error | 映射写错导致相关测试失败；或迁移破坏既有订单测试 | `block`（error） |
| DOC-001 | missing_docstring | warning | 纯函数模块/类漏 docstring | `allow_with_warnings` |
| STYLE-001 | style_lint | warning | 迁移行的 JSON 键串/日志串超 100 列 | `allow_with_warnings` |
| STYLE-002 | style_lint | error | 复制 import 后留下未使用项 | `block`（error） |
| STYLE-004 | style_lint | warning | 工具脚本 `sys.path.insert` 后的 import 忘加 `# noqa: E402` | `allow_with_warnings` |
| STYLE-010 | style_lint | error | 读文件失败时用裸 `except:` | `block`（error） |
| STYLE-018 | style_lint | warning | 本地区块 import 顺序错 | `allow_with_warnings` |
| SEC-006 | style_lint | error | `load_schema` 用 `yaml.load(handle, Loader=yaml.Loader)` | `block`（error） |
| SEC-015 | style_lint | error | 坏行用 `except Exception: pass` 跳过（与「失败关闭」直接冲突） | `block`（error） |

其余：`SEC-008`（SQL 拼接）为 —（数据层是 JSONL，不是 DB）；`SEC-011` 为 ○（变异）；
`ARCH-001` 为 —（不碰 controller）；`SEC-005/007/009/010/012/014/019/021/022` 为 —；
`DOC-002/003/004`、`STYLE-003/005/006/007/008/009/011/012/014/015/016/017`、`SEC-001/002/003/004/017/018` 为 ○。

## 5 隐藏验收要点（≥30 条；建议 36）

- 输出 4 条 v2 记录，按 `entry_id` 升序，字段/类型/status 精确；`cents=0` 的记录保留（不是丢弃）；
- 输入 `ledger-v1.jsonl` 逐字节不变（sha256 前后比对）；
- 原子性：坏行（重复 id / 负 cents / 缺 why / 非对象行）→ exit 1，且 `out` 的哨兵文件字节不变；
- 幂等：同一输入连跑两次输出字节相同；再以输出为输入（若 SPEC 要求）行为显式；
- `verify_ledger.py`：对合法输出 exit 0；对篡改行（缺键/乱序/错 schema）exit 1；
- schema 用 `yaml.safe_load`（行为面：坏 YAML 抛 `ValueError`）；`docs/migration.md` 含映射表与回滚；
- 全树 pytest 绿；允许写集合 = 9 条；新增测试无 skip/xfail。

## 6 命令族（`exec.pwsh`）

- `tests`：`python -m pytest -q`；
- `scripts`：`python tools/migrate_ledger.py --in data/ledger-v1.jsonl --out data/ledger-v2.jsonl`；
  `python tools/verify_ledger.py --path data/ledger-v2.jsonl`；
- `readonly`：`git status --porcelain`、`git diff --stat`。
见 `bank/COMMAND-FAMILIES.md` §4。**不用** `python -m json.tool`（不在白名单）。

## 7 难度与预计步数

难度**中**（纯函数好写，难在原子/幂等/失败关闭三件事同时成立）。预计 8–10 个里程碑 / 45–60 分钟参考解。
A 维度：`ledger_migration.py` 层值 `model`（纯数据变换），两个 tools 脚本 `composition`；
`interfaces.yaml` 上限：migration 6、migrate_ledger 2、verify_ledger 2。
