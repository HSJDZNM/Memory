# 隐藏验收计划（bank-crossmodule-refactor）

> **它是什么**：本题隐藏验收的冻结计划——`hidden/runner.py` 的 34 条用例（T01–T26 + EN1–EN4 + I1–I4）
> 逐条给出 id、断言要点与**反向构造**（怎么做会红）。runner 与 id 集合必须与本文一致。
> **它不读什么**：不读 `reference/`、不读任何实施 diff、不读其它题的 `hidden/`。
> 判据只来自 `SPEC.md`、`task-package/`、`baseline/`、`layers.yaml`、`interfaces.yaml`、`coverage.md`
> 与 `bank/README.md` §4。
> **它不是读数**：本文件是判据；实测读数（基线红 / 参考树全绿）记在 `README.md` 与 `scoring.yaml`。

## 0 runner 契约（与 `bank-flagship-returns` 同形）

- 被评树**只从环境变量 `BANK_TASK_TREE` 读入**（相对路径按 cwd 解析），**一个字节都不写**：
  需要执行的动作用树副本（临时目录，退出即删），进程内 `sys.dont_write_bytecode = True`，
  子进程 `PYTHONDONTWRITEBYTECODE=1` + `-p no:cacheprovider`，**子进程超时 60 秒**，解释器 = 运行 runner 的 `sys.executable`；
- stdout **唯一载荷**（UTF-8）：

  ```json
  {"schema_version": "1.0", "tree": "<相对调用 cwd 的标签>",
   "cases": [{"id": "T01", "pass": true, "detail": "ok"}],
   "summary": {"passed": 34, "total": 34}}
  ```

  载荷无时戳 / run id / 绝对路径 / 耗时；键 `sort_keys`、`cases` 顺序固定为 T01..T26, EN1..EN4, I1..I4；
  同一 cwd + 同一棵树两次运行**逐字节相同**；
- 退出码：**0 = 全过 / 1 = 有失败 / 2 = 跑不成**（缺 `BANK_TASK_TREE`、树不是目录、用例集合与 `CASE_IDS` 不等、
  树副本建不出来）。2 = 「判不了」，**不是 0 分**；原因写 stderr 一行，stdout 不出载荷；
- 每条用例独立 try/except：一条异常只让该条 fail（detail = 异常类型 + 脱敏短消息），不终止整轮。

## 1 树形状常数（runner 内写死，运行时不读 `baseline/`）

- 基线 14 文件（逐文件 sha256 常量；组合摘要 `b6d6d2f7…`，与 `baseline/` 实算一致）；
- 允许写 10 路径 = 可改写的 7 个基线文件（`README.md`、`src/shop/order_{repository,service,controller}.py`、
  `tests/test_order_{repository,service,controller}.py`）+ 3 个新建（`docs/api.md`、`src/shop/order_api.py`、
  `tests/test_order_api.py`）；
- **冻结 7 文件** = 基线 − 允许写：`AGENTS.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、
  `tools/__init__.py`、`config/refund_policy.yaml`、`data/refunds-legacy.jsonl`；
- 期望树 = 14 基线 ∪ 3 新建 = **17 路径**；遍历时忽略 `.policy`、`__pycache__`、`.pytest_cache`、
  `.ruff_cache`、`*.pyc` 与以 `.` 开头的目录。

「旧名」= `insert` / `listing`（标识符级匹配，`[A-Za-z0-9_]` 之外为边界）。**两种读法都要**：
AST（函数名 / 类名 / Name / Attribute / 参数名 / 关键字 / import 别名）与**文本**（docstring、注释、
字符串里的独立单词也算命中——`interfaces.md` §2.1 要求「方法名、调用、docstring 都不行」）。

## 2 T 组：行为、调用链、文档与树（26 条）

| id | 断言要点 | 反向构造（怎么做会红） |
| --- | --- | --- |
| T01 | `src/shop/order_repository.py` 里旧名 **0 处**（AST + 文本两种读法） | 只把方法名改回 `insert`；或在 docstring 里写一句「等价于旧的 insert」 |
| T02 | `src/shop/order_service.py` 旧名 0 处（AST + 文本）；AST：`OrderService.create` 的函数体含 `self.repository.add(...)` 调用，`list_all` 存在且函数体含 `self.repository.list_all()` | 只改方法名、函数体仍调 `self.repository.insert(...)`；或 `create` 直接读 `self.repository._rows` |
| T03 | `src/shop/order_controller.py` 旧名 0 处（AST + 文本）；AST：`create` 调 `self.service.create(...)`、`list_all` 调 `self.service.list_all()` | 只改方法名、函数体仍调 `self.service.listing()`；或入口层直接调 repository |
| T04 | 三个既有测试文件（repository / service / controller）旧名 0 处（AST + 文本），且每个文件 ≥1 个 `test_*` 函数、≥1 个 `assert` | 测试里留着 `repository.insert(...)`；或删光断言只留调用 |
| T05 | **非冻结** `.py` 的旧名命中集合**恰为** `{src/shop/order_api.py, tests/test_order_api.py}`，且两文件各 ≥1 处（冻结的基线文件由 T24 逐字节钉住、不参与扫描：`conftest.py` 的 `sys.path.insert(...)` 是标准库调用，不是被废弃的 API） | 在 `src/shop/order_repository.py`（或任何可改写文件）里提一句 insert；或门面把旧名改成 `insert_v2`（集合里少一个文件） |
| T06 | `add(payload)`：返回值 `== payload`、`is not payload`、也不是内部那一行的同一个对象；改返回值的**顶层键**后内部不变 | `return payload`（与入参同一对象）；`return row`（直接返回内部行，改返回值污染内部） |
| T07 | 入参隔离 + 顺序：`add(p)` 之后改 `p`（改值、加键）不影响已存行；连续 add 三行后 `list_all()` 顺序为 1,2,3 | `self._rows.append(payload)`（存原对象）；用 dict 去重/排序导致顺序变 |
| T08 | `list_all`：两次调用是**不同 list**、同一位置的 dict 是**不同对象**；改返回 list（append / clear / 改行）不影响内部 | `return self._rows`；`return [row for row in self._rows]`（新 list、旧行） |
| T09 | 非映射入参 `None` / `42` / `{1,2}` 三次都抛 `TypeError`（与基线 `dict(payload)` 同形），且失败**不落行**（`list_all()` 仍为空） | `except Exception: return {}` 吞掉；或先 `append` 再 `dict()`（半写） |
| T10 | controller 层固定序列（3 次 create、中途改返回值顶层键、两次 list_all、非映射入参）的返回值 JSON（`sort_keys`）**逐字节等于基线实算常量**；非映射入参抛 `TypeError` | 返回值改成内部行（listing 因此变化）；用深拷贝「优化」导致与基线不等的语义；吞掉非映射入参的异常 |
| T11 | 门面 `insert`：替身 repository 收到**同一个对象**、返回值 `is` 替身返回的对象、payload 未被改写、`list_all` 未被调用 | `return dict(self.repository.add(payload))`（返回值被复制） |
| T12 | 门面 `listing`：返回 `is` 替身返回的同一个 list、`list_all` 恰 1 次、`add` 0 次 | `return list(self.repository.list_all())` |
| T13 | 门面不复制：`id(insert(p))/id(listing())` 与替身返回对象一致，收到入参的 `is` 成立 | 任何 `copy.copy` / `dict(...)` / 列表推导都让 `id` 变 |
| T14 | `OrderApi.__init__` 去掉 self 后**恰 1 个**参数、名 `repository`、`POSITIONAL_OR_KEYWORD`、**无默认值**；`api.repository is fake`；`OrderApi()` 抛 `TypeError` | `def __init__(self, repository=None)`；或构造器里 `or OrderRepository()`（`is fake` 失败） |
| T15 | AST：`order_api.py` 的 import 模块集合 ⊆ `{shop.order_repository}`（不带 `*`），无 `shop.order_service` / `shop.order_controller`；0 处 `OrderRepository(...)` 调用 | `from shop.order_service import OrderService`；`self.repository = repository or OrderRepository()` |
| T16 | 模块 / 类 / `insert` / `listing` 四个 docstring 存在且非空；两个方法 docstring 各含（「弃用」或 `deprecated`）**且**含对应新名（`add` / `list_all`） | 方法 docstring 只写「转发到 add」（缺弃用字样）；`listing` 的 doc 写成「转发到 listing」 |
| T17 | 门面不吞、不包装异常：替身抛出的 `ValueError` / `KeyError` **同一个实例**原样穿出 | `except ValueError as exc: raise RuntimeError(...)`；`except Exception: return {}` |
| T18 | `service.create` 只经 `repository.add`：替身 `add` 记录到**同一个 payload 对象**、返回值 `is` 替身返回值、`insert` 一次都没被调（替身的 `insert` 一调就抛 `AssertionError`） | create 里仍调 `insert`；调两次 `add`（记录 2 次） |
| T19 | `service.list_all` 转发 `repository.list_all`：返回 `is` 替身返回的 list、恰 1 次调用、替身的 `listing` 未被调用 | `return list(self.repository.list_all())`（复制）；或仍调 `listing` |
| T20 | controller 只经 service：AST 的 import 集合 ⊆ `{shop.order_service}`、0 处 `OrderRepository` 的 Name/Attribute/Call；行为上 `list_all()` `is` 替身 service 返回值、恰 1 次、`listing` 未被调用 | controller import repository 并 `OrderRepository()`（同时会命中 ARCH-001，但本用例独立判） |
| T21 | 树副本里 `pytest -q tests/test_order_api.py` 单独退出 0（门面契约测试不依赖别的测试文件的 fixture / 顺序） | 测试依赖 `tests/test_order_repository.py` 里的常量；或文件没写 |
| T22 | `tests/test_order_api.py`：AST ≥3 个 `test_*`；出现 `insert`/`listing` 调用；引用 `OrderRepository`（真仓库做副本语义）；有弃用断言（`__doc__` 属性或含 `deprecated`/「弃用」的字符串） | 只写 1 条转发用例；删掉副本语义那条（不再引用 `OrderRepository`）；弃用说明只在文档里断言 |
| T23 | 4 个测试文件 AST 里 0 处 `skip`/`skipif`/`xfail`/`importorskip` 与 0 个 `pytest.skip(...)`/`pytest.xfail(...)`；每个文件 ≥1 个 `assert` | 加 `@pytest.mark.skip`；把断言改成 `print` |
| T24 | **冻结 7 文件**逐字节等于基线 sha256 常量（缺文件 = fail） | 往 `conftest.py` 加一行 print；改 `config/refund_policy.yaml` 的 `fee_bps`；改 `src/shop/__init__.py` |
| T25 | 树内文件集（忽略缓存 / `.policy`）**恰为** 17 个期望路径：无多余、无缺失 | 多写 `docs/notes.md` 或 `tests/__init__.py`；少写 `docs/api.md` |
| T26 | `docs/api.md`：三个二级标题 `## 对照表`/`## 废弃期限`/`## 迁移示例` 且各自正文非空；全文含 `insert`、`listing`、`add`、`list_all`、`v2.0`；`## 迁移示例` 一节有三个反引号的围栏代码块且含 `OrderApi` / `add(` / `list_all(`；`README.md` 有一行表格行含 `src/shop/order_api.py`（≥2 个 `|` 分隔）且有指向 `docs/api.md` 的 markdown 链接 | 删掉 `## 废弃期限` 一节；对照表只写新名；README 只在正文提一句、不进结构表也不链接 |

**T24 与 T25 合起来就是「树 diff ⊆ 允许写 10 条」**：未列入允许写的基线文件必须逐字节不变（T24），
其余额外路径由 T25 的集合相等挡。它们不重复判同一条事实：一个查字节，一个查文件集合。

## 3 EN 组：树副本里真跑命令（4 条）

| id | 断言要点 | 反向构造 |
| --- | --- | --- |
| EN1 | 树副本（cwd = 副本根）`python -m pytest -q` 退出 0 | 调用点改一半 → 相关用例红；`test_order_api.py` 断言写错 |
| EN2 | 同副本 `--collect-only -q` 退出 0 且收集到的 nodeid 数 ≥ **4**（基线 3 + 门面测试 ≥1） | 删既有测试；门面测试被 skip（skip 的用例不产生 nodeid，计数掉下去） |
| EN3 | 同副本 `pytest -q tests/test_order_repository.py tests/test_order_service.py tests/test_order_controller.py` 退出 0 | 只改新名一半、三个既有测试里还留着旧调用 |
| EN4 | 同副本里 `pytest -q` 连跑两次，把耗时（`\d+\.\d+s`）与路径脱敏后**两份输出逐字节相同** | 测试里用随机 / 时间 / 集合遍历顺序；或写文件后不清理导致第二轮输出变化 |

## 4 I 组：签名与公开面（4 条）

| id | 断言要点 | 反向构造 |
| --- | --- | --- |
| I1 | `OrderRepository.add(self, payload)` / `list_all(self)`：参数名恰为 `self, payload` / `self`，无默认值，**返回注解存在**（add 含 `dict`、list_all 含 `list`）；运行时 `add` 返回 `dict`、`list_all` 返回 `list` | 去掉返回注解；把参数改成 `data`；`add(*args)` |
| I2 | `OrderApi.__init__(self, repository)`：恰一个必填位置参数（无默认、`POSITIONAL_OR_KEYWORD`）；`OrderApi()` 抛 `TypeError` | 加默认值 `None`；改成关键字专用（`*,`） |
| I3 | `OrderApi.insert(self, payload)` / `listing(self)`：参数名恰为 `self, payload` / `self`，无默认值，返回注解存在（含 `dict` / 含 `list`） | 把 `insert` 改成 `insert(self, *args)`；去掉注解 |
| I4 | `OrderService` / `OrderController`：都有 `create` + `list_all`，都**没有** `insert`/`listing` 属性；`create(self, payload)` 必填；构造器保持基线形态（`OrderService(repository=None)` / `OrderController(service=None)`） | 保留一个旧名薄转发（`listing` 还在）；把 `create` 的参数改成可选 |

## 5 反向用例清单（断言「期望失败 / 期望拒绝 / 期望不存在」）

`T01`、`T02`、`T03`、`T04`、`T05`、`T09`、`T15`、`T17`、`T23`、`T24`、`T25` —— 共 **11 条**。
它们不是「跑成 = 通过」：T09/T17 要求指定异常类型（或同一个实例）出现，T01–T05/T15/T23–T25 要求
某些名字 / 文件 / 字节**不存在**。

## 6 与 `coverage.md` §6 计划骨架的三处收口（本 PLAN 是最终口径）

1. **T05 只扫「可改写」的 `.py`**：基线自带的 `conftest.py`（冻结文件）里有 `sys.path.insert(0, str(SRC))`。
   「旧名在全树 0 处、只允许出现在门面与它的契约测试里」按字面执行会让本题**无解**——而 `conftest.py`
   改一个字节就红（T24）。所以 T05 的扫描范围排除冻结文件；任何**可改写**文件里的旧名仍然会被抓到。
   这是 `hidden/runner.py` 在参考树上第一次运行就红出来的构造缺陷（实测发现，不是判据放宽）。
2. **T08 的「改嵌套 dict 不影响内部」不成立**：基线 `insert` 是 `dict(payload)` 的**浅拷贝**
   （实测 `{"a": {"b": 1}}` 的内层对象被共享），T10 又要求与基线逐字节等价；把嵌套隔离写成判据
   等于要求「与基线不等价」。所以 T08 只判**顶层键**与 list/行对象身份，嵌套对象**不进判据**
   （写了会在 PLAN 这里被读成过度约束）。
3. **T21 与 EN1 去重**：原骨架两者都写「树副本 pytest exit 0」。本 PLAN 把 T21 收成
   **`tests/test_order_api.py` 单独跑**（门面契约测试不依赖其它测试文件的顺序与夹具），EN1 仍是全树。

## 7 覆盖边界（写下来，免得读成「全测了」）

- **不判**「里程碑顺序 / 被拒动作有没有重试 / 平台账本读数」——那是过程维度（`bank/README.md` §5）；
- **不判**「测试断言被改弱」：T22/T23 只数用例数、断言数、skip 标记；「把 assert 改成 `assert True`」
  自动抓不到，按 `scoring.yaml` 的 H2 人工抽样；
- **不判**代码风格 / docstring 风格 / 类型注解完整性 —— 那是 C 维度（8 条规则）与 A 维度（10 条谓词）的事；
- **不判** `docs/api.md` 的措辞质量（只判标题、词、版本号、代码块与示例 token）；
- **不判** `.policy/**`（装配数据不在树形状里），也不判 `README.md` 其余段落；
- 树副本里的执行只代表「这棵树能跑」，**不证明**模型的会话过程、也不证明它在受治环境里没被拒过。

## 8 实测读数（另见 `README.md` 与 `scoring.yaml`）

| 被测树 | passed/total | 说明 |
| --- | --- | --- |
| 14 文件基线 | 见 `README.md` §「T 维度读数」 | 起点红：旧名、门面、文档、树形状全缺 |
| 参考解 `reference/tree` | 见 `README.md` §「T 维度读数」 | 必须 34/34；两次运行逐字节相同 |
