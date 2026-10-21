# 参考解（bank-data-migration）

> **它是什么**：按 `SPEC.md` 在 `baseline/` 上做完整题的参考实现，落在 `reference/tree/`（21 文件 = 13 基线 ∪
> 8 新建）。**实现不参与判分**；它只用来实测 T 的可达性、C/A 的天花板与「读数的样子」。
> 本轮实测全部通过；下面每个数字都是本机跑出来的，不是推断。

## 1 读数摘要（本次实测；命令见 `4）

| 维度 | 命令 | 读数 |
| --- | --- | --- |
| **T** | `BANK_TASK_TREE=<tree> .venv/Scripts/python.exe <task>/hidden/runner.py` | **passed 40 / total 40**，exit 0；两次运行 stdout 逐字节相同（sha256 `23bb6880c25bc46a41e3ab6165d3fcef1cb4e84f84258ca27ab7278059b22581`）；weighted = round(40 × 40 / 40) = **40** |
| **T（基线红）** | 同上，树 = `.tmp/…/baseline`（13 文件副本） | **passed 2 / total 40**，exit 1；两次运行逐字节相同（sha256 `2b813af526881c878995ff03e12c0214779b632cee04bd279184e1e755c9f67f`）。通过的 2 条是 T29（未改动 ⇒ 树 diff 干净）与 EN1（基线 3 条用例本来就绿） |
| **pytest** | `python -m pytest -q`（树根） | **19 passed**，exit 0 |
| **A** | `python tools/structure_metrics.py --workspace <tree> --layers <task>/layers.yaml --interfaces <task>/interfaces.yaml --json` | exit 0，**A1–A10 全 pass（10/10）**，`workspace_scope.declared_unmatched = []`，21 条层声明、14 个 .py 全部命中 |
| **C** | 6 个 file_set 文件各跑一次 `policy.check`（9 个 `--changed` 全给、`--layer` 显式、`--operation edit`、`--request-id` 固定） | 6/6 `allow`、**0 violation**；每次只跳过 `ARCH-001@1`（`layer model/test/composition != controller`）；`served_checkers` = failing_tests / missing_docstring / missing_tests / style_lint，`check_volume.complete = true`、`blocking_capable_skipped = 1` |
| **C 计分** | 规则段 7 条 × 3 = 21（ARCH-001 的 3 分 `not_applicable`）+ 冻结 3 + 旁路 3 | **27 / 27（= effective_total）** |
| 冻结文件 | 12 个（基线 − `README.md`）逐字节 | **12/12 不变** |
| 树 diff | 最终树 vs 13 文件基线 | **9 条改动全部 ⊆ allowed-writes**（8 新建 + `README.md`） |
| 产物 | `data/ledger-v2.jsonl` | 4 行、按 `entry_id` 升序、键序 = `key_order`、LF、末尾恰一个换行 |
| 参考树摘要 | 21 文件组合摘要（`<sha256>  <relpath>` 清单再 sha256） | `d162fcc632c9fffd03f023f9dbbaddfb97bc02a46e34bf2fd1f690fe7f3173ca` |

C 的逐文件读数（判定都是 `allow`、violations 都是 `[]`）：

| 文件 | `--layer` | skipped_rules | served_checkers |
| --- | --- | --- | --- |
| `src/shop/ledger_migration.py` | model | `ARCH-001@1` | 4 个 |
| `tests/test_ledger_migration.py` | test | `ARCH-001@1` | 4 个 |
| `tests/test_migrate_ledger.py` | test | `ARCH-001@1` | 4 个 |
| `tests/test_verify_ledger.py` | test | `ARCH-001@1` | 4 个 |
| `tools/migrate_ledger.py` | composition | `ARCH-001@1` | 4 个 |
| `tools/verify_ledger.py` | composition | `ARCH-001@1` | 4 个 |

## 2 决策点（为什么这么写；每条都对应一个可测后果）

1. **原子替换 = 同目录临时文件 + `os.replace`**：`tempfile.mkstemp(dir=parent)` → `os.fdopen(…, "wb")` →
   `flush` → `fsync` → `os.replace`；失败路径在 `finally` 里删临时文件，**从不**先删目标。
   后果：T17（字节形态）、T18（幂等/替换/无残留）、T19（序列化失败目标不变且无残留）同时成立。
2. **先序列化、再建临时文件**：`json.dumps` 在 `mkstemp` 之前完成，非法记录（例如 `set` 值）不会留下
   任何临时文件；序列化异常被转成 `ValueError`（不是让 `TypeError` 冒出去）。
3. **父目录缺失先判**：`parent.is_dir()` 为假直接 `ValueError`，**不**替调用方 `mkdir`
   （T20 的「目录没有被创建」就是这一条）。
4. **失败关闭统一成 `ValueError`**：schema 读不到/YAML 语法错/形状不符、v1 坏行、映射坏行、写盘失败
   全部 `ValueError`；两个 CLI 只捕获 `ValueError` 并写**一行** `MIGRATE FAILED:` / `VERIFY FAILED:` 后
   返回 1——证据是 T22/T23/T26 的「exit 1 + 一行 stderr + 哨兵字节不变」。
5. **不跳过坏行、不做部分迁移**：`read_v1` 逐行校验（空行也算坏行、空文件也算坏文件）；
   `migrate_rows` 先全量校验再排序，抛错前不返回半份结果（T09/T10/T11/T14/T15/T16）。
6. **键序走字面插入序**：`_to_v2` 按 `key_order` 手写 6 个键，序列化用
   `json.dumps(record, ensure_ascii=False)`，**不用** `sort_keys`——字母序会让 T12/I3 红。
7. **bool 不算 int**：所有整数判定走 `_is_int()`（`isinstance(value, int) and not isinstance(value, bool)`）；
   这是 T11 的 `id: true` 与 I3 的类型断言共同的实现点。
8. **schema 严格性**：顶层键集合、`schema_id`、`version`（int 2）、`key_order`（互不相同、与 `fields` 集合相等、
   且恰等于 v2 的 6 个键名）、`sort_by ∈ key_order`、`sort_direction ∈ {asc, desc}`、字段约束键闭集、
   `min`/`min_length` 为 int、`enum` 非空；校验通过后**原样**返回读到的 dict。
9. **CLI 的 schema 定位不靠 cwd**：`ROOT = Path(__file__).resolve().parents[1]`，import 前把 `ROOT/src` 插进
   `sys.path`，随后的 `from shop… import …` 加 `# noqa: E402`（只此一处豁免，对应 STYLE-004）；
   证据是 T24 的「cwd = 副本父目录 + 绝对路径仍能迁移」。
10. **A 维度的形状**：公开面 = 4 个纯函数 + 2 个 `main`（`interfaces.yaml` 的上限是 6/2/2，实测远低于上限）；
    `load_schema` / `_check_field` / `verify._check_value` 的圈复杂度首轮实测为 12/12/13（A5 fail），
    按「顶层校验拆 `_check_layout`、字段约束改写为 `spec.get(默认值)` 单层判定、值校验拆 `_check_type` /
    `_check_bounds`」拆到 ≤ 10；`ledger_migration.py` 恰好 200 行（A6 的阈值是「> 200 才 fail」）。
11. **测试强度**：19 条用例，覆盖 4 个纯函数的正常路径 + 6 个 `ValueError` 反例 + 原子/幂等 +
    两个 CLI 的成功/坏输入/顺序篡改；没有 `skip`/`xfail`，每个文件都有 `assert`（T31、EN4）。

## 3 与 SPEC / 任务包的偏差（显式记下）

1. **`load_schema` 比 SPEC 更严一档**：SPEC 只要求 `key_order` 互不相同且集合等于 `fields` 的键集合；
   参考解额外要求它恰等于 v2 的 6 个键名（`schema_version/entry_id/order_id/amount_cents/reason/status`）。
   理由：`migrate_rows` 的映射是固定的，schema 声明的键名必须能对上；这是**收紧**，不是放宽。
2. **产物由 CLI 生成**：`data/ledger-v2.jsonl` 是「在参考树上跑一次 `python tools/migrate_ledger.py`」的产物
   （与 SPEC「由脚本产出，算允许写」一致），不是手写文件。
3. **不加 `tools/__init__.py`**：`tools/` 目录由两个脚本带出来；测试按任务包给的形态先把项目根插进
   `sys.path` 再 `from tools.<name> import main`。
4. **测试用 pytest 的 `tmp_path`**：本轮在 `danger-full-access` 下实测 19 passed；宿主若把 0700 临时目录
   整体拒掉（受限沙箱时期出现过），pytest 会先红——那是宿主限制，不是判据放宽。
5. **没有改任何判据输入**：`layers.yaml` / `interfaces.yaml` / `policies/**` / `validation/**` 一个字节没动
   （A 的 `interfaces.digest` 与 `frozen_inputs` 的声明摘要一致，C 的 `rule_set.identity` 与冻结时同一份规则集）。

## 4 命令（可逐条复跑；<task> = 本题目录，<tree> = <task>/reference/tree）

```powershell
# T（参考树）
$env:BANK_TASK_TREE = '<tree>'; .venv/Scripts/python.exe <task>/hidden/runner.py

# T（基线红：先把 baseline/ 复制到树副本）
$env:BANK_TASK_TREE = '<副本>'; .venv/Scripts/python.exe <task>/hidden/runner.py

# pytest（树根；临时目录要指到树外，否则 pytest 的 tmp_path 会在树里留下 pytest-of-*）
$env:TMP='<树外的可写目录>'; $env:TEMP=$env:TMP; cd <tree>; <repo>/.venv/Scripts/python.exe -m pytest -q

# A
.venv/Scripts/python.exe tools/structure_metrics.py --workspace <tree> --layers <task>/layers.yaml --interfaces <task>/interfaces.yaml --json

# C（每个 file_set 文件一次；下面是 ledger_migration 的那次）
$env:PYTHONPATH='src'; .venv/Scripts/python.exe -m policy.check src/shop/ledger_migration.py `
  --workspace <tree> --config-root . --layer model --operation edit `
  --changed README.md --changed data/ledger-v2.jsonl --changed docs/migration.md `
  --changed src/shop/ledger_migration.py --changed tests/test_ledger_migration.py `
  --changed tests/test_migrate_ledger.py --changed tests/test_verify_ledger.py `
  --changed tools/migrate_ledger.py --changed tools/verify_ledger.py `
  --request-id bank-data-migration-author-ledger-migration --json
```

## 5 文件清单（reference/tree/ 的 8 个新建文件）

| 路径 | 行数 | 角色 |
| --- | --- | --- |
| `src/shop/ledger_migration.py` | 200 | model 层纯函数：`load_schema` / `read_v1` / `migrate_rows` / `write_v2` |
| `tools/migrate_ledger.py` | 40 | composition：`--in/--out`，成功 `MIGRATED <n>`，坏数据 exit 1 |
| `tools/verify_ledger.py` | 131 | composition：`--path`，字节层 + 键序 + 约束 + 严格升序，成功 `VERIFIED <n>` |
| `tests/test_ledger_migration.py` | 109 | 4 个纯函数 + 6 个 `ValueError` 反例 + 原子/幂等 |
| `tests/test_migrate_ledger.py` | 52 | CLI：成功 / 坏行（哨兵不变）/ 幂等 / 用法错误 exit 2 |
| `tests/test_verify_ledger.py` | 52 | CLI：合法产物 / 缺键 / 乱序 |
| `docs/migration.md` | 47 | 5 个二级标题 + 字段映射表 + 幂等/原子/回滚 |
| `data/ledger-v2.jsonl` | 4 | 迁移产物（由 CLI 生成） |
| `README.md`（改） | 41 | 结构表 3 行 + 迁移命令 + 文档链接 |
