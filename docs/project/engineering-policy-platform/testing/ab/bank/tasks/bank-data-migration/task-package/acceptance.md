# 验收表（bank-data-migration）

> 判定方式三档：**隐藏用例**（下一批任务按隐藏计划实现，最终树只读）、**树执行**（在最终树的副本里跑命令，
> 只看退出码/输出）、**树 diff**（最终树 vs 13 文件基线）。
> 本表与 first-message.md 的「验收表」逐字对应（去掉反引号后逐字相同）；改一处必须改另一处。
> **隐藏用例此刻还没有落盘**：本表冻结的是**检查项与判定方式**，不是「已经测过」；
> 隐藏代码与 PLAN 属于下一批任务，A5–A8 的树执行部分可在冻结后立刻实测，A1–A4/A10 的隐藏用例待写。

| id | 检查 | 判定方式 |
| --- | --- | --- |
| A1 | `load_schema` 读带注释的 YAML；顶层键集合/`schema_id`/`version`/`key_order` 与 `fields` 一致/`sort_by` 与 `sort_direction` 一律严格校验；坏 YAML、缺键、多键、`key_order` 与 `fields` 不一致、`sort_by` 不在 `key_order` 里都抛 `ValueError`（消息不含绝对路径） | 隐藏用例 |
| A2 | `read_v1` 把 4 行按文件顺序读入、每行键集合恰为 4 个；非对象行/缺键/多键/类型错（含 `bool` 冒充 `int`）/空行/非法 JSON 一律 `ValueError`，不许跳过；输入文件字节不变 | 隐藏用例 |
| A3 | `migrate_rows` 映射 6 键且键序 = `key_order`、`status="migrated"`、按 `entry_id` 升序；`cents=0` 的记录保留；重复 `id` / 负 `cents` / 缺 `why` / 非对象元素 → `ValueError`；返回的记录与入参不共享 | 隐藏用例 |
| A4 | `write_v2` 原子替换（同目录临时文件 + `os.replace`）；LF、末尾恰一个换行、键序 = `key_order`；同一 `rows` 两次写出的字节相同；目标已存在时被替换；序列化失败不替换目标且不留临时文件 | 隐藏用例 |
| A5 | 项目根跑 `python tools/migrate_ledger.py --in data/ledger-v1.jsonl --out data/ledger-v2.jsonl` → exit 0、stdout 恰一行 `MIGRATED 4`、out 是 4 条正确 v2 记录、输入 sha256 不变 | 树执行 |
| A6 | 坏输入（重复 `id` / 负 `cents` / 缺 `why` / 非对象行）与坏 schema（副本里删一个 field）→ exit 1、stderr 一行 `MIGRATE FAILED:`、out 的哨兵字节不变、不留 `.tmp` 残留 | 树执行 + 隐藏用例 |
| A7 | 幂等：删掉 out 后再跑一次 → 输出与第一次逐字节相同；out 已存在时连跑两次同样逐字节相同 | 树执行 |
| A8 | `python tools/verify_ledger.py --path data/ledger-v2.jsonl` → exit 0、stdout 一行 `VERIFIED 4`；篡改（缺键/键序错/记录乱序/错 `schema_version`/负值/CRLF/末尾多空行）→ exit 1；不改被校验文件 | 树执行 + 隐藏用例 |
| A9 | 项目根 `python -m pytest -q` exit 0；`--collect-only -q` 收集数 ≥ 基线 3 + 3 = 6；3 个新测试文件都没有 `skip`/`skipif`/`xfail` 且各至少 1 个 `assert` | 树执行 |
| A10 | `docs/migration.md` 含 5 个指定二级标题 + 映射表（v1 4 键、v2 6 键各出现一次）+ 回滚段；`README.md` 结构表新增 3 行、迁移命令 1 行、链接 `docs/migration.md` | 隐藏用例 |
| A11 | 最终树相对 13 文件基线的改动集合 ⊆ `allowed-writes.txt` 的 9 条；12 个冻结文件（基线 − `README.md`）逐字节不变 | 树 diff |
| A12 | 树内文件集 ⊆ 13 基线 ∪ 8 新建（= 21；忽略 `.policy/**`、`__pycache__`、`.pytest_cache`、`.ruff_cache`）；`data/ledger-v2.jsonl` 存在且非空 | 树 diff |

## 判定口径

- **A5–A9 的树执行**在**树的副本**上跑（不许改受评树）：子进程 cwd = 副本根，解释器 = 运行验收的那个解释器；
  迁移命令的 `--out` 落在副本里。
- **A11/A12 的树 diff** 忽略 `.policy/**`（装配数据，由 run-manifest 单独钉哈希）与三个缓存目录；
  「12 个冻结文件」= 13 文件基线减去允许写集合里的 `README.md`。
- **A6 的哨兵**：先往 out 写一个已知字节的哨兵文件，坏输入跑完后必须逐字节不变——「没写成功」与
  「把旧的删了再失败」必须能分开读。
- **A9 的收集数下限 6** 由基线 3 条用例 + 3 个新测试文件各至少 1 条推出；收集数更高不扣分。
- 隐藏用例的编号与条数在隐藏计划冻结时再定（`scoring.yaml` 的 `dimension_t.status = pending_hidden`）。
