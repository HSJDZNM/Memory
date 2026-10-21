# 数据迁移任务接口契约（bank-data-migration）

> 本文件是**题目的一部分**：首消息（first-message.md）以更完整的形式复述同一组签名与语义。
> 两者不一致 = 任务包自相矛盾，冻结前必须先对齐；冻结后任何一个字节的变化都算换构造。

## 1 基线里已有的（只读，一个字节都不许改）

- 订单示例包 `src/shop/`：`__init__.py`、`order_repository.py`（内存订单表：`insert` / `listing`）、
  `order_service.py`、`order_controller.py`；
- `tests/` 三个同名测试；`conftest.py` 把 `src` 插进 `sys.path`；`pytest.ini` 的 `testpaths = tests`、
  `pythonpath = src`；
- `data/ledger-v1.jsonl`（迁移**输入**，只读）与 `config/ledger_schema.yaml`（v2 形状**声明**，只读）。

本任务**不**新增 `tools/__init__.py`，也不新增别的基线文件：`tools/` 目录由 M5/M7 的新建文件带出来。

## 2 v1 输入（`data/ledger-v1.jsonl`，只读）

每行一个 JSON 对象，键集合恰为 4 个：

```text
{"id": <int>, "order": <int>, "cents": <int>, "why": <str>}
```

- 文件 4 行；`id` 在文件里**不是**升序（实际是 3、1、4、2）；其中一条 `cents` 为 **0**（必须保留，不是丢弃）；
- `id` / `order` / `cents` 是 `int`（用 `True`/`False` 冒充 int 一律拒收）；`order >= 0`、`cents >= 0`、`id >= 0`；
- `why` 是非空 `str`；`id` 在文件内**唯一**。

## 3 v2 输出（`data/ledger-v2.jsonl`，任务产物）

每行一个 JSON 对象，键集合恰为 6 个、**顺序**逐字如下（= `config/ledger_schema.yaml` 的 `key_order`）：

```text
{"schema_version": 2, "entry_id": <int>, "order_id": <int>, "amount_cents": <int>, "reason": <str>, "status": "migrated"}
```

字段映射：`entry_id = id`、`order_id = order`、`amount_cents = cents`、`reason = why`、`status = "migrated"`、
`schema_version = 2`。记录按 `entry_id` **升序**；文件是 UTF-8 + LF、每行一条、末尾**一个**换行，不得出现 CR。
序列化用 `json.dumps(record, ensure_ascii=False)`；**不要**用它自己的 `sort_keys=True`——那会按字母序，
与 `key_order` 不符。

## 4 只读 schema（`config/ledger_schema.yaml`）

顶层键集合恰为 6 个：`schema_id` / `version` / `key_order` / `sort_by` / `sort_direction` / `fields`。
`schema_id == "ledger-schema/2"`、`version == 2`；`key_order` 是 6 个互不相同的字符串、其集合**等于**
`fields` 的键集合、顺序就是输出行里键的顺序；`sort_by` ∈ `key_order`；`sort_direction` ∈ {`asc`, `desc`}；
`fields` 的值是 dict，允许的约束键恰为 `type` / `const` / `min` / `min_length` / `enum`，`type` ∈ {`int`, `str`}。

## 5 新建 `src/shop/ledger_migration.py`（model 层，纯函数）

```python
def load_schema(path: Path) -> dict: ...
def read_v1(path: Path) -> list[dict]: ...
def migrate_rows(rows: list[dict]) -> list[dict]: ...
def write_v2(path: Path, rows: list[dict]) -> None: ...
```

- **`load_schema`**：用 `yaml.safe_load` 读 YAML（这份 schema 带注释，`json` 读不了）；按 §4 严格校验后**原样**
  返回读到的 dict。文件读不到 / 不是 UTF-8 / YAML 语法错误 / 形状不符 → `ValueError`（消息里不许出现绝对路径）。
- **`read_v1`**：UTF-8 逐行读（`splitlines()`）；每行 `json.loads` 必须是对象、键集合恰为 §2 的 4 个；
  空行、非法 JSON、非对象行、缺键、多键、类型错 → `ValueError`（**不许跳过坏行**）；返回**按文件顺序**的 list，
  每行一个新 dict。不写任何文件。
- **`migrate_rows`**：逐行校验（§2 的全部约束，含 `id` 唯一），映射成 §3 的 6 键记录（**按 `key_order` 的顺序插入**），
  按 `entry_id` 升序返回**新的** list；返回的 dict 与入参不共享。`rows` 为空、或任一行坏 → `ValueError`，
  **不做部分迁移**（不返回半份结果）。
- **`write_v2`**：**原子替换**——先在**同目录**写临时文件，`flush` 后 `os.replace`；每行
  `json.dumps(record, ensure_ascii=False)` + `\n`；父目录不存在 → `ValueError`。序列化或写盘失败时删掉临时文件、
  **不替换** `path`，并对调用方抛 `ValueError`（消息里不许出现绝对路径）。

## 6 新建 `tools/migrate_ledger.py`（composition 层）

```python
def main(argv: list[str] | None = None) -> int: ...
# 例：main(["--in", "data/ledger-v1.jsonl", "--out", "data/ledger-v2.jsonl"])
```

- argparse 选项 `--in` 与 `--out`（都必填；缺一个就是用法错误，argparse 自己退出 2）；
- schema 路径 = `<项目根>/config/ledger_schema.yaml`，按 `__file__` 定位（**不靠 cwd**）；先 `load_schema`；
  schema 读不出来或形状不符 = 与「坏输入」同一条失败关闭路径；
- 流程：`load_schema` → `read_v1` → `migrate_rows` → `write_v2`；成功时 stdout **恰好一行** `MIGRATED <n>`，返回 0；
- 任何 `ValueError`：stdout 不打印 `MIGRATED`，stderr **一行** `MIGRATE FAILED: <原因>`（脱敏、不含绝对路径），
  返回 1；**不创建/不替换** `--out`（不许留 `.tmp` 半成品）；`--in` 文件逐字节不变。

## 7 新建 `tools/verify_ledger.py`（composition 层）

```python
def main(argv: list[str] | None = None) -> int: ...
# 例：main(["--path", "data/ledger-v2.jsonl"])
```

- argparse 选项 `--path`（必填）；schema 同上按 `__file__` 定位；
- 逐行校验：字节层（UTF-8、无 CR、LF、末尾**恰一个**换行、空文件算失败）→ 每行是合法 JSON 对象 →
  键集合 == `fields` 且**键序** == `key_order` → 每个键按 `fields` 的 `type` / `const` / `min` / `min_length` /
  `enum` 校验 → `sort_by` 指定的键**严格升序**（`sort_direction == "asc"` 时）；
- 全过：stdout **恰好一行** `VERIFIED <n>`，返回 0；任一不符：stderr **一行** `VERIFY FAILED: <原因>`，返回 1；
- 只读：**不改**被校验文件，也不写别的文件。

## 8 两个工具脚本的三个固定细节（逐字照做）

1. `python tools/<name>.py` 的 `sys.path[0]` 是 `tools/`：在 import `shop` 之前，把 `<项目根>/src` 插进
   `sys.path`（像 `conftest.py` 那样）；
2. 紧随其后的 `from shop... import ...` 行加 `# noqa: E402`（只此一处豁免，对应 STYLE-004）；
3. 文件末尾：`if __name__ == "__main__": raise SystemExit(main())`。

## 9 测试文件（3 个，与生产文件同名）

- `tests/test_ledger_migration.py`：覆盖 `load_schema` / `read_v1` / `migrate_rows` / `write_v2`（正常路径 +
  至少 3 个 `ValueError` 反例 + 原子替换/幂等）；`from shop.ledger_migration import ...`（`conftest.py` 已把 `src`
  插进 `sys.path`）；
- `tests/test_migrate_ledger.py`：覆盖 CLI（成功 stdout `MIGRATED 4`、坏输入 exit 1 且 out 的哨兵字节不变、
  连跑两次字节相同）；
- `tests/test_verify_ledger.py`：覆盖 CLI（合法输出 exit 0 + `VERIFIED 4`；篡改行 exit 1）；
- 三个文件都**不许** `skip` / `skipif` / `xfail`；每个文件至少 1 个 `assert`；不许把断言改弱
  （「跑得通就算过」不算测试）。

第 2、3 个文件导入工具模块的方式（`tools/` 在基线里不存在，所以**必须**先把项目根插进 `sys.path`）：

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.migrate_ledger import main  # noqa: E402
```

## 10 文档与 README

`docs/migration.md` 必须含 5 个二级标题（逐字）：`## 字段映射`、`## 幂等`、`## 原子替换`、`## 回滚`、`## 命令`；
`## 字段映射` 下必须是一张表——v1 的 4 个键（`id` / `order` / `cents` / `why`）各出现一次、v2 的 6 个键
（`schema_version` / `entry_id` / `order_id` / `amount_cents` / `reason` / `status`）各出现一次；
`## 回滚` 必须写到「v1 一个字节都没改，回滚 = 删掉 v2、用 v1 重跑」。

`README.md`：在「结构」表新增 3 行（`src/shop/ledger_migration.py` / `tools/migrate_ledger.py` /
`tools/verify_ledger.py`）、在「跑测试」之外新增一行迁移命令
`python tools/migrate_ledger.py --in data/ledger-v1.jsonl --out data/ledger-v2.jsonl`，并在文末链接 `docs/migration.md`。
