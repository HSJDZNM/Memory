# v1 -> v2 台账迁移

`data/ledger-v1.jsonl` 是 v1 台账（4 条），`data/ledger-v2.jsonl` 是迁移产物；
两个文件的形状声明都在 `config/ledger_schema.yaml`（只读输入）。

## 字段映射

| v1 字段 | v2 字段 | 说明 |
| --- | --- | --- |
| `id` | `entry_id` | 原样搬运，并作为记录之间的排序键 |
| `order` | `order_id` | 原样搬运 |
| `cents` | `amount_cents` | 原样搬运；0 也保留，不丢弃 |
| `why` | `reason` | 原样搬运；必须非空 |
| — | `schema_version` | 固定写入 2 |
| — | `status` | 固定写入 "migrated" |

记录按 `entry_id` 升序，每行的键序与 `key_order` 一致（不是字母序：不要用 `sort_keys=True`）。

## 幂等

同一份 v1 输入连跑两次，产物逐字节相同：文件是 UTF-8 + LF、每行一条、末尾恰一个换行、没有 CR。
产物已存在时整体替换，不追加、不在末尾叠记录——所以「重跑」不改变任何字节。

## 原子替换

`write_v2` 先在**目标同目录**写临时文件，`flush` 之后用 `os.replace` 覆盖目标：
替换是原子的，读的人不会看到半份文件。序列化或写盘失败时删掉临时文件、**不替换**目标，
坏数据因此不会留下半成品。

## 回滚

`data/ledger-v1.jsonl` 一个字节都没改，所以回滚 = 删掉 `data/ledger-v2.jsonl`、
再用 v1 重跑一次迁移：

```powershell
python tools/migrate_ledger.py --in data/ledger-v1.jsonl --out data/ledger-v2.jsonl
```

## 命令

```powershell
python tools/migrate_ledger.py --in data/ledger-v1.jsonl --out data/ledger-v2.jsonl
python tools/verify_ledger.py --path data/ledger-v2.jsonl
```

迁移成功打印 `MIGRATED 4`、校验成功打印 `VERIFIED 4`；坏数据两条命令都以 exit 1 失败关闭
（`MIGRATE FAILED:` / `VERIFY FAILED:`），且不替换产物。
