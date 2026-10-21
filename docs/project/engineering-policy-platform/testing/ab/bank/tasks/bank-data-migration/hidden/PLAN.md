# 隐藏验收计划（bank-data-migration）

> **状态**：条目清单与判据（PLAN）落盘；`hidden/runner.py` 按本文件实现，**先 PLAN 后代码**。
> 本文件是 **40 条**：隐藏行为 **T01–T32**（32）+ 入口 **EN1–EN4**（4）+ 接口 **I1–I4**（4）。
> 每条都写成**可执行的测法**：断言要点 + 反向构造（怎么让这条真的变红）。
> 作者独立性：本文件与 runner 由未参与任务设计与实施的子会话写成，只读了 `task-package/`、`baseline/`、
> `layers.yaml`、`interfaces.yaml`、`SPEC.md`、`README.md`、`coverage.md`、`scoring.yaml` 与
> `bank/README.md` `4/`5、旗舰题 `hidden/README.md` 的 runner 契约；**没有读**任何参考解或实施 diff
> （本题没有参考解），也没有读其它题的隐藏用例。

## 0 runner 契约（实现与判读的唯一口径）

- 入口 `hidden/runner.py`，单文件自包含；被评树只从环境变量 `BANK_TASK_TREE` 取（相对路径按 cwd 解析）。
- **只读被评树**：所有需要执行/写入的动作（pytest、两条命令、构造坏输入、写 v2）都在**树的副本**里跑；
  进程内 `sys.dont_write_bytecode = True`，子进程 `PYTHONDONTWRITEBYTECODE=1` 且不带 `PYTHONPATH`/`PYTEST_ADDOPTS`；
  副本放在**被评树之外**（`<cwd>/.tmp`、树旁 `.tmp`、系统 temp，逐候选真写一次才算可用），退出时删。
- 子进程超时 **60 秒**；解释器 = 运行 runner 的 `sys.executable`。
- stdout 唯一载荷（UTF-8，`sort_keys` 固定）：

```json
{"schema_version": "1.0", "tree": "<相对 cwd 的标签>",
 "cases": [{"id": "T01", "pass": true, "detail": "ok"}, ...],
 "summary": {"passed": 40, "total": 40}}
```

  `cases` 顺序固定：T01..T32、EN1..EN4、I1..I4（= 本文件顺序）。
- 载荷不含时戳 / run id / 绝对路径；**同一 cwd + 同一棵树两次运行逐字节相同**。
- 退出码：**0** 全过 / **1** 有失败 / **2** 跑不成（缺 `BANK_TASK_TREE`、树不存在、用例集合与 id 清单不相等、
  树复制不出来）。**2 只表示「T 判不了」，不是 0 分**；原因写 stderr 一行。
- 每条用例独立 try/except：一条异常只让该条 fail；`detail` = 异常类型 + 脱敏短消息（无绝对路径）。

## 1 隐藏行为 32 条（T01–T32）

被测面 = `src/shop/ledger_migration.py` 的 4 个纯函数、两个工具脚本、3 个同名测试、`docs/migration.md`、
`README.md` 与最终树的形状。除特别注明外，「树内文件」指**被评树**里的那份只读字节。

### 1.1 schema 严格性（T01–T07）

| id | 断言要点 | 反向构造（让这条变红） |
| --- | --- | --- |
| T01 | `load_schema(<树>/config/ledger_schema.yaml)` 返回 dict；顶层键集合恰 6；`schema_id=="ledger-schema/2"`、`version==2`（int）、`key_order` 是 6 个键的**有序**列表、`sort_by=="entry_id"`、`sort_direction=="asc"`、`fields` 键集合 == `key_order` 集合、`fields` 逐键约束与基线相等；读完后该文件 sha256 不变 | 返回写死的常量（换一份 schema 仍返回旧值）；用 `json` 读（带注释的 YAML 直接失败）；把 `key_order` 读成 `fields` 的顺序 |
| T02 | 反例：schema **多一个**顶层键（`extra: 1`）→ `ValueError` | 只校验必需键存在、忽略多余键 → 该条红 |
| T03 | 反例：schema **少一个**顶层键（删 `sort_direction`）→ `ValueError` | 用 `.get(..., 默认)` 容错 → 该条红 |
| T04 | 反例：`key_order` 与 `fields` 键集合不一致（删掉 `reason` 一项；另一个子例：`key_order` 里重复 `status`）→ 均 `ValueError` | 只查 `len(key_order) == 6` → 两个子例都红 |
| T05 | 反例：`sort_by` 改成不在 `key_order` 里的 `amount`；`sort_direction` 改成 `up` → 均 `ValueError` | 不校验枚举 / 不校验 `sort_by` 成员关系 → 红 |
| T06 | 反例：YAML 语法错误；路径不存在；路径是目录 → 均 `ValueError`，且异常消息**不含绝对路径**（不含临时目录串、不含盘符冒号）；坏文件字节不变 | 让 `yaml.YAMLError`/`FileNotFoundError` 直接冒出来（不是 `ValueError`）；消息里拼 `path.resolve()` → 红 |
| T07 | 反例：`fields` 某项出现非法约束键（`max: 5`）；`type: float`；某 field 的值不是 dict（`reason: str`）；`schema_id` 改 `ledger-schema/3`；`version` 改成字符串 `"2"` → 均 `ValueError` | 只校验顶层键集合、不深入 `fields` → 全部子例红 |

### 1.2 v1 读取（T08–T11）

| id | 断言要点 | 反向构造（让这条变红） |
| --- | --- | --- |
| T08 | `read_v1(<树>/data/ledger-v1.jsonl)` → 4 条 dict，**按文件顺序**（`id` = 3、1、4、2）；每条键集合恰 `{id, order, cents, why}` 且逐键值与基线相等；返回的行是新对象（改返回值后重新读仍是原值）；输入文件 sha256 不变 | 按 `id` 排序后返回（顺序红）；返回的 dict 与内部缓存共享（改后重读变了 → 红） |
| T09 | 反例：非对象行 `[1, 2]`；非法 JSON（少一个 `}`）；文件中间夹空行；空文件 → 均 `ValueError`（空文件也算失败，失败关闭） | 坏行 `continue` 跳过 / 空文件返回 `[]` → 红 |
| T10 | 反例：缺 `why`；多一个 `extra` 键 → 均 `ValueError` | `row.get("why", "")` 兜底、或只查必需键 → 对应子例红 |
| T11 | 反例：`id: true`（bool 冒充 int）；`cents: -1`；`cents: "12"`（str）；`why: ""`；`why: 5` → 均 `ValueError` | 只写 `isinstance(x, int)`（bool 是 int 子类）→ bool 子例红；不查下界/非空 → 红 |

### 1.3 映射 / 排序 / 无损（T12–T16）

| id | 断言要点 | 反向构造（让这条变红） |
| --- | --- | --- |
| T12 | `migrate_rows(read_v1(<树 v1>))` → 4 条记录；每条 `list(keys()) == key_order`（逐字）；值逐键精确（`schema_version=2`、`status="migrated"`、`entry_id=id`、`order_id=order`、`amount_cents=cents`、`reason=why`）；按 `entry_id` **升序** 1/2/3/4；`cents=0` 的那条（`entry_id=3`）**保留** | 丢掉金额为 0 的行；`sort_keys=True`（键序按字母序）→ 红 |
| T13 | 返回**新的** list 与**新的** dict：`out is not rows`、无输出 dict 是入参 dict 本身；改 `out[0]["amount_cents"]` 后入参不变；入参 list 顺序未被原地重排（仍是 3/1/4/2）；连调两次结果相等 | `return sorted(rows)`（原地重排入参）或直接复用入参 dict → 红 |
| T14 | 反例：两条 `id=1`（重复）→ `ValueError`，且**不返回半份结果** | 用 `{row["id"]: row}` 去重（后者覆盖）→ 红 |
| T15 | 反例（逐条）：`cents=-1`；缺 `why`；`why=""`；元素是字符串 `"x"`；`order=-1` → 均 `ValueError` | 只校验 `id`/只校验行是 dict → 红 |
| T16 | 反例：`migrate_rows([])` → `ValueError`（空输入不是「成功的 0 条」） | 返回 `[]` 并声称成功 → 红 |

### 1.4 原子写与幂等（T17–T20）

| id | 断言要点 | 反向构造（让这条变红） |
| --- | --- | --- |
| T17 | `write_v2(<case>/out.jsonl, 4 条)` → 原始字节 == 4 行 `json.dumps(record, ensure_ascii=False)`（键序 = `key_order`）+ 每行一个 `\n`；无 `\r`；末尾**恰一个**换行；4 行 | 用 `indent`/`sort_keys`；末尾多写一个换行；用 `\r\n` → 红 |
| T18 | 幂等与替换：同一 rows 连写两次 → 字节相同；目标已有哨兵内容时被**替换**成新内容；成功路径结束后目标目录里**只剩**目标文件（不留临时文件） | 追加写（`"a"`）→ 替换子例红；成功后留着 `*.tmp` → 残留子例红 |
| T19 | 反例：rows 里含不可 JSON 序列化的值（`{"entry_id": {1, 2}, ...}`）→ `ValueError`；目标哨兵字节不变；目录里没有新增文件（临时文件被删） | 让 `TypeError` 冒出来（不是 `ValueError`）；先删目标再失败 → 哨兵红；临时文件不删 → 残留红 |
| T20 | 反例：父目录不存在 → `ValueError`，且该目录**没有被创建** | `mkdir(parents=True)` 后成功写 → 红 |

### 1.5 迁移 CLI（T21–T24）

| id | 断言要点 | 反向构造（让这条变红） |
| --- | --- | --- |
| T21 | 树副本根跑 `python tools/migrate_ledger.py --in data/ledger-v1.jsonl --out data/ledger-v2.jsonl` → exit 0；stdout **恰一行** `MIGRATED 4`；out 是 4 条精确 v2 记录；输入 sha256 不变 | stdout 多打一行；out 少一条 → 红 |
| T22 | 坏行 4 种（重复 id / 负 cents / 缺 why / 非对象行）：各 exit 1；stdout **不含** `MIGRATED`；stderr **恰一行**且以 `MIGRATE FAILED:` 开头、不含绝对路径；out 哨兵字节不变；`data/` 里没有新增残留文件 | `except Exception: pass` 后 exit 0；失败前先 truncate out；留下 `.tmp` → 红 |
| T23 | 坏 schema（副本删 `status` field；副本 `key_order` 少一项）与缺输入（`--in` 指向不存在的文件）：各 exit 1 + `MIGRATE FAILED:` 一行 + out 哨兵不变 | schema 读失败时退化成「不用 schema」继续迁移 → exit 0 红 |
| T24 | **cwd 无关**：cwd = 副本父目录、脚本与 `--in/--out` 全用绝对路径 → exit 0 且 `MIGRATED 4`（证明 schema 按 `__file__` 定位）；随后在副本根连跑两次 → 输出字节相同；删掉 out 再跑 → 与第一次字节相同 | schema 按 cwd 定位 → 第一条 exit 1 红；输出里掺时间/随机 → 两次字节不同红 |

### 1.6 校验 CLI（T25–T26）

| id | 断言要点 | 反向构造（让这条变红） |
| --- | --- | --- |
| T25 | 先迁移出合法 out，再跑 `python tools/verify_ledger.py --path data/ledger-v2.jsonl` → exit 0；stdout **恰一行** `VERIFIED 4`；被校验文件 sha256 不变（只读） | 合法文件判失败 → exit 红；边校验边回写（例如排序后写回）→ sha 红 |
| T26 | 篡改矩阵 10 种：缺 `reason`；前两个键换序；两行互换（顺序乱）；`schema_version=3`；`amount_cents=-1`；CRLF 行尾；末尾多一个空行；空文件；单行非法 JSON；单行不是对象 → 各 exit 1；stderr **恰一行**以 `VERIFY FAILED:` 开头；文件 sha256 不变 | 只校验「JSON 可解析」→ 多数子例红；把 CRLF / 末尾多空行当合法 → 红 |

### 1.7 文档与 README（T27–T28）

| id | 断言要点 | 反向构造（让这条变红） |
| --- | --- | --- |
| T27 | `docs/migration.md` 存在；5 个二级标题逐字出现（`## 字段映射`、`## 幂等`、`## 原子替换`、`## 回滚`、`## 命令`），每个标题后都有非空正文；`## 字段映射` 段内有 Markdown 表格且 v1 的 4 个键、v2 的 6 个键都出现在表格行里；`## 回滚` 段同时写到「v1 未改」+「删 v2」+「重跑」三件事 | 少一个标题；映射表漏 `why`；回滚段只写「从备份恢复」→ 红 |
| T28 | `README.md` 含 3 个新结构行（`src/shop/ledger_migration.py`、`tools/migrate_ledger.py`、`tools/verify_ledger.py` 字面）；含迁移命令行逐字 `python tools/migrate_ledger.py --in data/ledger-v1.jsonl --out data/ledger-v2.jsonl`；含指向 `docs/migration.md` 的链接；基线原 4 条结构行（3 个 `src/shop/order_*.py` + `tests/`）仍在 | 只加命令不加结构行；命令参数写错（例如 `--input`）；把原结构行整段替换掉 → 红 |

### 1.8 树形状与测试强度（T29–T32）

| id | 断言要点 | 反向构造（让这条变红） |
| --- | --- | --- |
| T29 | 改动集合 ⊆ 9 条允许写；13 个基线文件仍全部存在；**12 个冻结文件**（基线 − `README.md`）逐字节与基线 sha256 相等 | 改 `data/ledger-v1.jsonl` 一个字节；新建 `docs/extra.md`；删 `AGENTS.md` → 红 |
| T30 | 树内文件集（忽略 `.policy/**`、`__pycache__`、`.pytest_cache`、`.ruff_cache`、`*.pyc`）⊆ 21 条（13 基线 ∪ 8 新建）；`data/ledger-v2.jsonl` 存在、非空、是 4 条精确记录 | 多一个 `tools/__init__.py`；产物只有 3 条 → 红 |
| T31 | 3 个新测试文件存在；AST 里没有 `skip`/`skipif`/`xfail`/`importorskip`；每个文件 ≥ 1 个 `assert` | 加 `@pytest.mark.skip`；把文件写成 0 断言 → 红。**已知边界**：断言写弱（`assert True`）本条抓不到，交 `scoring.yaml` 的 H2 抽样 |
| T32 | 8 个新建文件存在；其中 7 个文本文件（6 个 `.py` + `docs/migration.md`）与 `data/ledger-v2.jsonl` 都是合法 UTF-8、无 BOM、无 `\r`、以**恰一个** `\n` 结尾 | 用 CRLF 落盘；末尾两个换行；写出 BOM → 红 |

## 2 入口 4 条（EN1–EN4）

| id | 断言要点 | 反向构造 |
| --- | --- | --- |
| EN1 | 项目根（树副本）`python -m pytest -q` → exit 0 | 新测试里有失败断言；迁移破坏既有订单测试 → 红 |
| EN2 | 树副本根跑迁移命令族（逐字形态）→ exit 0 且 `data/ledger-v2.jsonl` 存在非空 | 脚本不存在 / `--in` 拼错 → 红 |
| EN3 | 树副本根跑校验命令族 → exit 0 且 stdout 含 `VERIFIED 4` | 校验脚本不存在 → 红 |
| EN4 | 树副本 `python -m pytest --collect-only -q -p no:cacheprovider` → exit 0；收集到的用例数 **≥ 6**（基线 3 + 3 个新测试文件各 ≥ 1）；3 个新测试文件都出现在收集清单里 | 新测试文件没写 / 收集失败（例如模块级 import 不存在的 `tools.*`）→ 红 |

## 3 接口 4 条（I1–I4）

| id | 断言要点 | 反向构造 |
| --- | --- | --- |
| I1 | `shop.ledger_migration` 里 `load_schema` / `read_v1` / `migrate_rows` / `write_v2` 都是模块级 function；参数名与形态逐字：`load_schema(path)`、`read_v1(path)`、`migrate_rows(rows)`、`write_v2(path, rows)`；每个参数都是 `POSITIONAL_OR_KEYWORD` 且**没有默认值**；`migrate_rows(4 条)` 返回 `list` | 参数改名为 `p`/`data`；把 `rows` 设默认值；返回 tuple → 红 |
| I2 | 两个脚本的 `main` 都是模块级 function；签名恰 1 个参数 `argv`、默认 `None`、返回注解是 `int`；`main([])` 抛 `SystemExit` 且 `code == 2`（argparse 用法错误码，不是 0/1） | `main(argv=None)` 写成 `main()`；缺参时 `return 2` 而不是 argparse 退出 → 红 |
| I3 | 记录形状语义：`migrate_rows` 输出的每条 `list(keys()) == key_order`、恰 6 键；`status == "migrated"`；`schema_version` 是 `int`（且不是 `bool`）；`amount_cents` 是 `int` 不是 `bool` | 用 `dataclass` + `asdict`（键序可能变）；`status` 映射成 `"MIGRATED"` → 红 |
| I4 | 错误语义：4 个纯函数的坏输入一律 `ValueError`（不是 `OSError`/`RuntimeError`/`KeyError`/`TypeError`/`SystemExit`）；两个 `main` 对坏输入**返回** `int 1`（不抛异常、不 `SystemExit`），且不创建 out | 抛自定义异常；`main` 里 `raise SystemExit(1)`；坏输入时返回 0 → 红 |

## 4 反向用例索引（「期望失败/拒绝」不是「跑成=通过」）

**T02、T03、T04、T05、T06、T07**（坏 schema → `ValueError`）；**T09、T10、T11**（坏 v1 行 → `ValueError`）；
**T14、T15、T16**（坏 rows / 空输入 → `ValueError`）；**T19、T20**（写不成功时抛错且不破坏目标）；
**T22、T23**（坏输入/坏 schema → exit 1 且哨兵不变）；**T24**（cwd 无关的反向：按 cwd 定位 schema 会红）；
**T26**（10 种篡改 → exit 1）；**T29**（越界改动）；**T30**（多余文件）；**T31**（skip/xfail）；**T32**（CRLF/BOM）。

每条反向断言都必须落在**异常类型 / 退出码 / 字节不变 / 文件集合**上——不用「输出里含某个词」代替行为判定。

## 5 只读与确定性（实现纪律）

- 被评树一个字节都不写：pytest、两条命令、坏输入构造、v2 产物都在副本里；树内文件只读（`load_schema` / `read_v1` 直接读被评树，读完比对 sha256）。
- 副本目录名含 pid 只影响**路径**，进入载荷前一律 `_scrub` 成 `<tmp>` / `<tree>`；空跑两次逐字节相同是交付条件。
- 单条用例失败不终止整轮；但 `BANK_TASK_TREE` 缺失/树不存在/用例 id 集合与清单不等/副本建不出来 → **exit 2**。

## 6 与 SPEC 的口径差异（显式记下，避免「同名两义」）

1. **T27 的映射表**：SPEC 写「v1 4 键、v2 6 键各出现一次」；本 runner 判「都出现在 `## 字段映射` 段的
   Markdown 表格行里」（不断言恰一次）——同一份文档把键名在正文里再提一次不该判红，这是**放宽**，不是新判据。
2. **T32** 只查 8 个新建文本文件的编码/换行/BOM，不查行尾空白（基线 `AGENTS.md` 没有声明这条约定，
   拿它判分等于拿没写在树里的规则判分）。
3. **T31** 明确写清抓不到「断言改弱」，该面归 `scoring.yaml` 的 H2 人工抽样；不把它算成本条通过。
4. `data/ledger-v2.jsonl` 由 T30 校验内容；`write_v2` 的字节形态由 T17/T18 校验；两者不重复计分。
