# 隐藏验收计划（bank-bugfix-first-failing-test）

> **状态**：已落盘（**38 条**：`T01–T19` + `EN1–EN6` + `I1–I13`）。本文件**先于** `hidden/runner.py` 冻结；
> 代码按本清单逐条实现，id、顺序、断言要点与反向构造都以本文件为准。
> **作者独立性**：本文件与 `runner.py` 由未参与任务设计、也未看过任何参考解的子会话写成；
> 只读了 `SPEC.md`、本题 `README.md`、`coverage.md`、`layers.yaml`、`interfaces.yaml`、`scoring.yaml`、
> `task-package/`、`baseline/`、`bank/README.md` §4/§5 与旗舰题的 `hidden/README.md` + `runner.py` 的**管线部分**。
> 参考解 `reference/tree/` 在本轮之后写，写本文件时**尚不存在**。
>
> **判据来源的优先级**：`SPEC.md` §3/§5 > `task-package/first-message.md`（首消息，模型实际看到的契约）>
> `task-package/interfaces.md` > `task-package/acceptance.md`（A1–A10）> `coverage.md` §6 的候选清单。
> 候选清单与本文件的差异见 §5，逐条写明选哪边、为什么。

## 0 契约（与旗舰题 `hidden/runner.py` 同形）

| 项 | 取值 |
| --- | --- |
| 入口 | `hidden/runner.py`（单文件自包含，本目录不放别的用例文件） |
| 被评树 | 只从环境变量 `BANK_TASK_TREE` 读入（相对路径按 cwd 解析）；**只读**，一个字节都不写 |
| 执行 | 一切需要执行的动作（pytest / 导入 / 变异副本）都在**树副本**里跑；临时目录在树外，退出时删 |
| stdout | 唯一载荷（UTF-8）：`{schema_version, tree, cases[], summary{passed,total}}`；`cases` 顺序固定为 §4 的 38 条 |
| 确定性 | 无时戳 / 无 run id / 无绝对路径 / 无随机；同一 cwd + 同一棵树两次运行**逐字节相同** |
| 退出码 | 0 = 全过；1 = 有失败；2 = 跑不成（缺 `BANK_TASK_TREE`、树不存在、用例注册表不完整、树复制不出来） |
| 单条隔离 | 每条 `try/except`：一条异常只让该条 fail，`detail` 只留异常类型 + 脱敏短消息 |
| 子进程 | `sys.executable`，超时 **60 秒**，`PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider` |

**runner 内写死的常数**（运行时不读本包的 `baseline/`，也不读 `layers.yaml` / `scoring.yaml`）：

- `BASELINE_SHA256`：11 个基线文件的逐字节摘要（8 个冻结 + 3 个可改写）；
- `MODIFIABLE_BASELINE` = `README.md`、`src/shop/order_repository.py`、`tests/test_order_repository.py`；
- `ALLOWED_WRITES` = 5 条（上面 3 条 + `docs/fix-notes.md` + `tests/test_order_service_copy.py`）；
- `EXPECTED_PATHS` = 11 基线 ∪ 2 新建 = **13** 个路径（最终树的文件集上限）；
- `FROZEN` = 11 − 3 可改写 = **8** 个冻结文件（I5 逐字节校验这 8 个）；
- 忽略段：`.policy`、`__pycache__`、`.pytest_cache`、`.ruff_cache`、`*.pyc`（装配数据与缓存不算任务文件）。

**基线构造证明（`EN5`/`EN6` 的实现口径）**：runner 内**逐字内嵌 9 个基线文件**的源码
（`conftest.py`、`pytest.ini`、`src/shop/{__init__,order_repository,order_service,order_controller}.py`、
`tests/test_order_{repository,service,controller}.py`），在临时目录里重建这棵树再执行；
另逐字内嵌 `README.md` 供 `T19` 比对基线章节（`AGENTS.md` 与执行无关，不嵌——它的存在性由 `I5` 的逐字节摘要判）。**这两条与被评树无关**：它们证明的是「本题的起点确实是红的」这一**构造**，
不是「解法对不对」——后者由 `T` / `EN1–EN4` 判。

**反向构造的两类形态**（本文件的「反向构造」列）：

- **可执行反向用例**（`I8–I11`、`I12–I13` 中的一部分）：在**树副本**上把实现/测试改成歪法，
  断言**同款探针必须报 fail**——证明隐藏用例有牙，不当「跑完即通过」；
- **设计期反向构造**（其余各条）：写明「树被做成什么样时这条必须红」，供变异测试与人工 H2 抽样使用。

## 1 T 组：最终树上的行为（19 条）

被测对象 = 被评树的**副本**上导入的 `shop.order_repository` / `shop.order_service` / `shop.order_controller`；
AST 类用例只解析被评树里的文本，不执行它。

| id | 断言要点 | 反向构造（树做成什么样时这条必须红） |
| --- | --- | --- |
| T01 | `insert({"id": 1})` 的返回值与入参**值相等**、**身份不同**（`row is not payload`）；返回值是 `dict` | 返回入参本身（`return payload`）或返回 `None`/`OrderRow(...)` |
| T02 | 改 `insert` 返回的 row（`row["id"] = 2`）之后 `listing()` 仍是 `[{"id": 1}]` | `return self._rows[-1]`（返回内部行本身） |
| T03 | `insert(payload)` 之后改入参 `payload["id"] = 2`，`listing()` 仍是 `[{"id": 1}]` | `self._rows.append(payload)`（存调用方的 dict） |
| T04 | `insert` 的返回值**不是**内部存储行：`row is not repo._rows[-1]`，且 `repo._rows[-1] == payload`（存的是内容） | 存好后返回 `self._rows[-1]`；或内部列表不叫 `_rows`（契约声明过 `self._rows`，取不到 = 取证不了 = fail closed） |
| T05 | 两次 `listing()`：列表 `==` 但 `is not`；对应元素 dict 也 `is not` | `return self._rows`（内部列表直接外泄） |
| T06 | 改 `listing()` 返回的**列表元素**之后，再来一次 `listing()` 内容不变 | `return self._rows` 或 `return [row for row in self._rows]`（只复制外层） |
| T07 | 两条同内容记录：`_rows` 长度 2、`_rows[0] is not _rows[1]`、两者值相等；之后改入参两份内容都不受影响 | 两条记录共享同一个 dict（`self._rows.extend([payload, payload])`） |
| T08 | 三条不同记录：`_rows[i] == expected[i]`、两两 `is not`；`listing()` 按插入顺序等于期望；三个返回 row 与 `_rows[i]` 都 `is not` | 只对第一条成立（例如缓存第一行后重复 append）、或倒序/去重 |
| T09 | payload 的键集与值原样保留：`row == payload`、`set(row) == set(payload)`、`_rows[-1] == payload`（**不新增键、不改键名**） | 复制时加 `"copy": True` 之类的新键、或丢掉非 `id` 键 |
| T10 | 空仓储：`listing() == []`，两次空 `listing()` 不是同一个列表对象，`_rows` 初始为空 list | 初始 `_rows` 非空；`listing()` 返回模块级共享常量列表 |
| T11 | service 层：`OrderService().create({"id": 1})` 返回 `dict`、值相等；改它之后 `service.listing()` 仍是 `[{"id": 1}]` | 修好 repository 但 service 另存一份入参（本题不许改 service，因此只可能靠 repository 漏复制） |
| T12 | service 层：两次 `service.listing()` 相等但非同一列表，元素 dict 也非同一对象 | `OrderService.listing` 直接返回内部列表（需要改 service；本条同时是「service 未被改坏」的行为证据） |
| T13 | controller 层：`OrderController().create({"id": 7})` 值相等；改返回值后 `controller.listing()` 仍是 `[{"id": 7}]`；两次 listing 相等但非同一列表 | 入口层缓存了返回对象 / 修 bug 时顺手改了 controller 的转发语义 |
| T14 | AST：`test_insert_returns_a_copy` 的基线语句序列（`ast.dump` 归一化后逐条）是**新函数体的有序前缀**——原断言逐字仍在，可以往后追加 | 删掉或改写那条 assert、把 `row["id"] = 2` 删掉、把断言换成 `is not None` |
| T15 | AST：`test_listing_returns_copies` 的基线语句序列（含 2 条 assert）同样是新函数体的有序前缀 | 删掉 `assert second is not first`、把 `first[0]["id"] = 3` 删掉 |
| T16 | AST：`tests/test_order_repository.py` 的 assert 总数 ≥ 6（原 3 + 新 ≥ 3），test 函数数 ≥ 3，且至少有 1 个函数名不在基线里 | 只保留原两条用例（assert = 3）；三类新语义一条断言都没加 |
| T17 | AST：`tests/test_order_service_copy.py` 存在、≥ 2 个 test 函数、**每个**函数 ≥ 1 条 assert、无 `skip`/`skipif`/`xfail` | 新建文件只有空壳函数/只有 1 条用例/靠 `@pytest.mark.skip` 让它「绿」 |
| T18 | `docs/fix-notes.md` 含三个二级标题逐字（`## 根因`、`## 修法`、`## 验证`），且**每节非空**（标题外至少一行非空内容） | 只有标题没有正文；标题写成 `## 根因分析` 之类 |
| T19 | `README.md`：`## 跑测试` 一节**存在且正文与基线该节不同**，且含「红/失败」之一与「绿/通过/passed」之一；基线其余二级节（含 `## 结构`）正文**逐字不变** | 一个字都不改 README；或把整份 README 重写、顺手改掉「结构」表 |

## 2 EN 组：树执行（6 条）

命令一律在**树副本**里跑（`cwd` = 副本根），解释器 = 运行 runner 的 `sys.executable`；
输出只做**结构化解析**（退出码 / summary 行 / 收集数），不把裸文本当判据。

| id | 断言要点 | 反向构造 |
| --- | --- | --- |
| EN1 | 副本根 `python -m pytest -q` 退出码 **0** | 修一半（只改一侧）、测试写失败、import 顺序把模块打崩 |
| EN2 | 目标两条用例**逐条点名**跑过：`python -m pytest -q tests/test_order_repository.py::test_insert_returns_a_copy tests/test_order_repository.py::test_listing_returns_copies` 退出码 0 且 summary 含 `2 passed` | 把两条用例改名/删掉（点名跑会报 not found → 红）；断言仍红 |
| EN3 | `python -m pytest -q --collect-only` 的收集数 ≥ **8**（基线 4 + repo 新 ≥3 + 新文件 ≥1） | 只加 1 条新用例（收集 5）；新文件没被 pytest 收集 |
| EN4 | 全树 `pytest -q` 的 summary 解析出 `failed = 0`、`error = 0`、`passed ≥ 8`（**不只看退出码**：0 退出但 0 收集也算红） | 用 `pytest.ini` 的 `testpaths` 把新测试排除在外（收集数不涨）；用 `-k` 类开关掩盖 |
| EN5 | 基线构造证明（pytest）：重建的 9 文件基线树退出码 **1**，summary 是 **`2 failed, 2 passed`**，且两条目标 id 出现在 `FAILED` 行里 | 基线被谁改成绿的（= 题被撤掉）；测试文件被弱化 |
| EN6 | 基线构造证明（别名 bug 可观测，子进程）：`row is payload` 为真；改 `payload` 后 `listing()` 变化；改 `row` 后 `listing()` 变化 | 基线的 `insert` 已经是复制语义（= 「先有失败测试」不成立） |

## 3 I 组：接口 / 树形状 / 反向构造（13 条）

| id | 断言要点 | 反向构造 |
| --- | --- | --- |
| I1 | AST 签名：类名 `OrderRepository`；`__init__(self) -> None` 存在；`insert(self, payload: dict) -> dict`；`listing(self) -> list[dict]`（注解按 `ast.unparse` 归一化比较） | 改签名（`insert(self, order)`）、删注解、换成 `**kwargs` |
| I2 | AST docstring：模块、类、`insert`、`listing` 四处都有非空 docstring | 删类 docstring（C 侧 DOC-001 也会响，但那是 warning，不能当判据） |
| I3 | AST：`insert` 与 `listing` 体内无 `Try`/`Raise`/`ExceptHandler`（不新增异常分支） | 用 `try: ... except Exception: pass` 包住复制；加 `if not isinstance(...): raise TypeError` |
| I4 | `order_repository.py` 的顶层 import 全部来自标准库（`sys.stdlib_module_names`）；不 import 项目内模块、不 import 第三方 | 用 `copy.deepcopy` 之外的第三方库造副本；`from shop.order_service import ...`（分层反向边） |
| I5 | 树形状：**8 个冻结文件**逐字节等于基线 sha256 | 改 `AGENTS.md`/`order_service.py`/`conftest.py` 等「顺手改」；换行归一化（CRLF） |
| I6 | 树形状：文件集 ⊆ 13 个声明路径（忽略 `.policy`/缓存/`*.pyc`）；改动集合 ⊆ 5 条允许写 | 新建 `docs/notes.md`、`tests/test_copy.py`、`src/shop/copy_util.py` 等第 14 个文件 |
| I7 | 树形状：11 个基线文件全部存在 + 2 个任务新建文件存在（最终树 = 13） | 删掉 `docs/fix-notes.md`；把新建测试写成别的文件名 |
| I8 | **反向**「原 bug 复活」：副本里把 `insert` 改成 `self._rows.append(payload); return payload`，**副本语义探针**（T01–T03 同款断言）必须报 fail | 探针失去牙（永远 PASS）——那正是本条要抓的 |
| I9 | **反向**「只复制返回值」：`self._rows.append(payload); return dict(payload)` → 「改入参不影响内部」探针必须报 fail | 探针只查返回值、不查入参 |
| I10 | **反向**「清空列表」：`self._rows.clear()` 后写入 → 「多记录」探针必须报 fail | 多记录探针只看最后一条 |
| I11 | **反向**「listing 直接返回内部列表」：`return self._rows` → 「listing 副本」探针必须报 fail | 只比较两次 `listing()` 是否 `==`、不比较 `is not` |
| I12 | **反向**「断言被改弱」：对内存里的削弱版源码（删掉 `test_insert_returns_a_copy` 的唯一 assert）跑 **T14 同款**有序前缀判定 → 必须判 fail | 逐字比对写成「用例名存在即可」——那抓不到削弱 |
| I13 | **反向**「skip 掩盖」：对内存里加了 `@pytest.mark.skip` 的版本跑 **T17 同款**标记检测 → 必须报出 marker | 标记检测只认 `pytest.skip(` 调用、不认装饰器 |

## 4 计数、顺序与 id 集合

```
T01 T02 T03 T04 T05 T06 T07 T08 T09 T10 T11 T12 T13 T14 T15 T16 T17 T18 T19
EN1 EN2 EN3 EN4 EN5 EN6
I1 I2 I3 I4 I5 I6 I7 I8 I9 I10 I11 I12 I13
```

- **总数 38**（≥ SPEC §5 的「≥30」、≥ `scoring.yaml` 的 `planned_min_total: 30`）；
- `cases` 的顺序**就是上面三行**；`case_ids` 必须与 runner 实际输出的 id 列表**逐个相等**（顺序也相等），
  否则按「跑不成」（exit 2 / T 判不了）处理，不把「少测了」记成「测过了」；
- 反向用例（断言「必须失败/必须拒绝」）= **I8, I9, I10, I11, I12, I13**（6 条）；
  `EN5`/`EN6` 是「构造证明」——它们断言的是**基线**的红，不是解法的红。

## 5 与 `coverage.md` §6 候选清单的差异（逐条写明选哪边）

| # | 候选清单 | 本计划 | 理由 |
| --- | --- | --- | --- |
| 1 | 分组 `BASE / T / N`（4 + 26 + 6） | 分组 **`T / EN / I`**（19 + 6 + 13） | 派单要求 T/EN/I 三组并与旗舰同形；`BASE` 的 4 条落成 `EN5`/`EN6`（它们是**执行**出来的构造证明），`N` 的 6 条落成 `I8–I13`（可执行反向用例） |
| 2 | B01 要求「基线树 `pytest` → 2 failed, **2 passed**」 | 保留：`EN5` 在**内嵌重建**的 9 文件基线树上跑，断言 `2 failed, 2 passed` | 内嵌是唯一能「运行时不读包内 baseline/」又精确复现起始读数的做法；不嵌 `AGENTS.md`/`README.md`（与执行无关） |
| 3 | T12 写「assert 总数 ≥ 5（原 3 + 新 ≥3）」 | 取 **≥ 6**（3 + 3） | 原文自相矛盾：3 + 3 = 6。首消息与 `acceptance.md` A4 都写「至少 3 条新断言」，≥6 才是这句的合取，≥5 会放过「只加 2 条」 |
| 4 | T13「新增用例覆盖三类语义」 | 落成 `T16`（≥3 个测试函数、≥6 条断言）+ `T02/T03/T05` 的行为证据 | 「三类语义」用 AST 判要靠匹配断言文本，脆；改用「行为上确实成立 + 测试文件确实加厚」两条可执行事实 |
| 5 | T19「三节每节非空」 | 严格按「标题外至少一行非空内容」判 | 「非空」必须可执行；只认标题会被「三个标题连排」骗过 |
| 6 | T20「README 的『跑测试』一节有更新」 | `T19`：该节**必须变**，基线其余二级节**必须不变** | 首消息 §9 与 `interfaces.md` §6 都写「只改这一节，其它章节不动」，候选清单只说了「有更新」——取更严的那一侧，因为它是模型看到的契约 |
| 7 | T24「树里没有额外文件」 | `I6` 同时要求「文件数 ≤ 13」与「改动 ⊆ 5 条允许写」 | 两句话是同一件事的两个方向；分开写会漏掉「删了基线文件但不加文件」 |
| 8 | N01–N06 的期望写法「T02/T03/T04 fail」 | `I8–I11` 断言**同款探针在主进程内对该变异源码报 fail** | 反向用例若依赖「另一条用例的结果」，会让 id 之间互相指涉；本条自证（既证明歪法有牙、也证明探针会在歪法上红） |

**不写进本计划的**（明确不测，不当成覆盖）：C 维度规则读数（`policy.check`）、A 维度 10 条结构谓词、
过程账本（`matched_rules`/`check_volume`）、人工抽样 H2。它们由 `scoring.yaml` 的 `dimension_c` /
`dimension_a` / `human_items` 各自承接；T 只读最终树与两条基线构造证明。
