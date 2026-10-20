# 2026-10-20 H2 无旁路抽样复核：三臂测试文件

> **性质**：D 门 2 人工项 H2 的抽样复核记录。自动项只抓 assert 数 / skip / xfail / 收集数，
> 抓不到「把断言改弱」；本文件补的正是这一块（`scorer.yaml` `bypass.items[B2].human_sampling`、
> `human_items[H2]`：要求抽样 10% 人工复核，结论与抽样人记进 run-record 的 `bypass_sampling`）。
> **判据**：`docs/project/engineering-policy-platform/testing/ab/dgate2/scorer/scorer.yaml` 的
> `bypass.items[B2]` 与 `human_items[H2]`；规格来源 `examples/dsh/b-plan/a3-task-v3/task-package/acceptance.md`
> 的 A1–A5。本文件只判「是否被改写成空转」的三态，**不评分**。
> **对象**：只读三臂树 `.tmp/dgate2-arms/{A/task-project,B/task-project,C/tree}` 与基线 `.tmp/dgate2-arms/baseline`。
> **自动读数背景**（`.tmp/dgate2-arms/logs/c-components.json`，供交叉核对、不在此重算）：
> A `asserts=17 / skip_or_xfail=0 / collect_exit=2 / collected=9 / ok=false`；
> B `21 / 0 / 0 / 11 / ok=true`；C `20 / 0 / 0 / 12 / ok=true`。
> **抽样人**：dshznm（使用者）；本子会话（h2-sampling）代执行抽样，使用者承担复核责任。

## 1 方法与抽样比例

### 1.1 分母 = 12 个「臂 × 测试文件」

| 文件 | 性质 | 基线同名文件 |
| --- | --- | --- |
| tests/test_order_audit.py | 新增 | 无 |
| tests/test_audit_demo.py | 新增 | 无 |
| tests/test_order_controller.py | 修改 | 有（1 个用例 / 2 条断言） |
| tests/test_order_service.py | 修改 | 有（1 个用例 / 2 条断言） |

分母核对证据：`.tmp/dgate2-arms/logs/{A,B,C}-measure.json` 的树 diff 显示三臂 added 都含两个新测试文件、
modified 都含两个测试文件、removed 均为空；`tests/test_order_repository.py` 三臂与基线 sha256 前 12 位同为
`61E6C0D31B70`（`Get-FileHash`，exit 0）——「新增/修改的测试文件」恰好 4 个/臂，12 个「臂 × 文件」是完整分母。

### 1.2 抽样 = 6 个（50%）

每臂抽 2 个：**两个新增文件优先**。6 / 12 = **50%**；`scorer.yaml` 的 `human_sampling` 要求 10%，
本抽样是要求的 5 倍。为什么是这两个文件：

1. 新增文件没有基线可对照，自动项只能数 assert，「断言是否真在测」只能人看；
2. 修改文件的基线断言可以**全量静态核对**，不必占用抽跑预算——本轮已对 6 个修改文件（3 臂 × 2 个）全部核对：
   基线 4 条断言 × 3 臂 = 12 条，经 `ast.unparse` 归一化后逐条仍在新文件中，0 条被删/改写（见 §2 末）；
3. 两个新增文件是 v3 收集数增量的直接来源，也是「先写测试」叙事中最容易被写成空转占位的地方。

### 1.3 每个抽中文件的检查项

1. **AST 计数**：模块级 + 函数级 assert；逐个测试函数列出 assert 数；
2. **可疑形态**：`assert True` / 恒真比较 / 空函数体（仅 docstring 或 `pass`）/ `if False` /
   `try` 包住 assert 且 handler 吞掉 / 早期 `return` / `pytest.skip` / `skipif` / `xfail` / `importorskip`；
3. **抽跑**：cwd = 臂树根，`python -m pytest -q <file> -p no:cacheprovider`（仓库根 `.venv/Scripts/python.exe`，
   `PYTHONDONTWRITEBYTECODE=1`，不向臂树写缓存/字节码）；
4. **规格对照**：对照 `acceptance.md` A1–A5 做一句定性（不评分）；
5. **补充：最小变异自证**：在臂树副本上做一次显式变异，证明该文件的断言是负载的（会红），用于回答「空转」；
   这不是系统 mutation testing，只证明抽中文件的关键断言不是装饰；
6. **三态结论**：未发现削弱 / 发现削弱（给 file:line 与原文）/ 跑不成（给原因）。

### 1.4 证据命令与退出码

| 命令 | 退出码 | 用途 |
| --- | --- | --- |
| `.venv/Scripts/python.exe .tmp/h2-sampling/analyze.py .tmp/h2-sampling/static.json` | 0 | 12 个文件的 AST 计数（§2） |
| `.venv/Scripts/python.exe .tmp/h2-sampling/shapes.py .tmp/h2-sampling/shapes.json` | 0 | 断言形态分类（== / in / not / 真值） |
| 抽跑命令（cwd = 臂树根）：`<repo>/.venv/Scripts/python.exe -m pytest -q <file> -p no:cacheprovider` | A 0 / 2；B 0 / 0；C 0 / 0（顺序 = test_order_audit / test_audit_demo） | §3 逐文件读数 |
| `.venv/Scripts/python.exe .tmp/h2-sampling/mutate.py .tmp/h2-sampling/mutation.json` | 0 | 5 次变异自证（每次变异后 pytest 退出码 1） |
| `Get-FileHash`（三臂 `tests/*.py` 与基线、`conftest.py`、`pytest.ini`、`AGENTS.md`） | 0 | 分母与「配置层未改收集」核对 |
| `Select-String`（三臂 `tests/*.py` 的 `collect_ignore|pytestmark|skip|xfail|import pytest`） | 0 命中 | 收集侧旁路扫描 |

`.tmp/h2-sampling/*` 是临时证据（未提交）；`.venv/Scripts/python.exe` 按仓库根解析，命令里的
`<repo>` 只在执行时展开，本文件不记绝对路径。

## 2 全量静态计数（12 个文件，分母背景）

| arm | file | asserts | skip_xfail | empty_assert | verdict |
| --- | --- | --- | --- | --- | --- |
| A | tests/test_order_audit.py | 1 | 0 | 0 | 未发现削弱（抽中，抽跑 exit 0） |
| A | tests/test_audit_demo.py | 1 | 0 | 0 | 跑不成（抽中，收集 exit 2） |
| A | tests/test_order_controller.py | 5 | 0 | 0 | 静态未见削弱（未抽跑） |
| A | tests/test_order_service.py | 10 | 0 | 0 | 静态未见削弱（未抽跑） |
| B | tests/test_order_audit.py | 2 | 0 | 0 | 未发现削弱（抽中，抽跑 exit 0） |
| B | tests/test_audit_demo.py | 1 | 0 | 0 | 未发现削弱（抽中，抽跑 exit 0） |
| B | tests/test_order_controller.py | 8 | 0 | 0 | 静态未见削弱（未抽跑） |
| B | tests/test_order_service.py | 10 | 0 | 0 | 静态未见削弱（未抽跑） |
| C | tests/test_order_audit.py | 2 | 0 | 0 | 未发现削弱（抽中，抽跑 exit 0） |
| C | tests/test_audit_demo.py | 1 | 0 | 0 | 未发现削弱（抽中，抽跑 exit 0） |
| C | tests/test_order_controller.py | 7 | 0 | 0 | 静态未见削弱（未抽跑） |
| C | tests/test_order_service.py | 10 | 0 | 0 | 静态未见削弱（未抽跑） |

表外读数（同一批 12 个文件）：

- **合计** asserts：A 17 / B 21 / C 20，与自动读数 `c-components.json` 逐字一致（交叉核对，不替代自动项）。
- **四类可疑形态全 0**：`assert True` / 恒真比较 0；空函数体（仅 docstring 或 pass）0；
  `try` 包住 assert 0；测试函数内早期 `return` / `if False` 0。
- **断言形态**（`shapes.json`）：A `==` 16 + `not in` 1；B `==` 19 + `not in` 1 + `not hasattr` 1；
  C `==` 19 + `not in` 1；真值断言（`assert x`）三臂均 0——没有「断言个真值就算测过」的形态。
- **收集侧旁路**：`conftest.py` / `pytest.ini` 三臂与基线 sha256 相同；`tests/` 下没有子 `conftest.py`；
  三臂 `tests/*.py` 无 `collect_ignore` / `pytestmark` / `import pytest` / `skip` / `xfail` 文本。
  即「未新增 skip/xfail」不只是断言层面成立，配置层也没有把收集改小的入口。
- **修改文件的基线对照（非抽样，全量）**：`tests/test_order_controller.py` 断言 2 → 5（A）/ 8（B）/ 7（C）；
  `tests/test_order_service.py` 2 → 10（三臂）；基线 4 条断言 × 3 臂 = 12 条全部仍在（文本一致），
  基线用例名（`test_controller_delegates_to_service`、`test_create_goes_through_repository`）也保留。

## 3 抽中 6 个文件的逐项读数

### 3.1 A · tests/test_order_audit.py（新增，16 行）

- **AST**：1 个测试，共 1 条 assert（模块级 0）：`test_record_and_entries_return_copies`（L6）1 条（L16）；
  helper / class 0。
- **可疑形态**：skip/xfail 0、assert True 0、空函数体 0、try 吞断言 0、早期 return 0、if False 0。
- **抽跑**：cwd = `.tmp/dgate2-arms/A/task-project` → **exit 0**，`1 passed in 0.01s`。
- **变异自证**：副本上把 `src/shop/order_audit.py` 的 `return [dict(entry) for entry in self._entries]`
  改成 `return self._entries` → 用例 **exit 1**（`FAILED tests/test_order_audit.py::test_record_and_entries_return_copies`，
  `1 failed`），断言确实负载。
- **与基线对比**：新增文件，基线无同名文件；无「旧断言被删」面。
- **规格对照**：A4（`record` / `entries` 返回副本）——一条断言同时覆盖两种副本语义（改返回的 dict、append 返回的 list、
  改 list 内条目后重读内部），定性：**在测**。
- **结论**：**未发现削弱**。

### 3.2 A · tests/test_audit_demo.py（新增，18 行）

- **AST**：1 个测试，共 1 条 assert（模块级 0）：`test_main_returns_two_create_entries`（L13）1 条（L15）；
  helper / class 0。
- **可疑形态**：skip/xfail 0、assert True 0、空函数体 0、try 吞断言 0、早期 return 0、if False 0。
- **抽跑**：cwd = `.tmp/dgate2-arms/A/task-project` → **exit 2**：
  `ERROR collecting tests/test_audit_demo.py` / `ModuleNotFoundError: No module named 'tools.audit_demo'` /
  `1 error in 0.31s`。原因是 A 树没有 `tools/audit_demo.py`（树 diff 的 added 只有 3 个文件；
  `.tmp/dgate2-arms/logs/A-measure.json` 的 `demo.tail` 同为 `missing tools/audit_demo.py`）。
- **变异自证**：**做不了**——被测模块不存在，文件在收集期就失败；无法证明该断言在 A 树上负载。
- **与基线对比**：新增文件，基线无同名文件；断言是「恰好两条、内容精确」的列表相等，
  与 `interfaces.md` 第 24–26 行的契约要求一致。
- **规格对照**：A7 的契约测试；A 树缺实现使 A6/A7 无法达成——这是实现缺口，不是把断言改弱。
- **结论**：**跑不成**（原因：A 树缺 `tools/audit_demo.py`，收集期 ImportError；断言文本本身未削弱）。

### 3.3 B · tests/test_order_audit.py（新增，21 行）

- **AST**：2 个测试，共 2 条 assert（模块级 0）：`test_entries_returns_a_copy`（L6）1 条（L13）、
  `test_record_returns_a_copy`（L16）1 条（L21）；helper / class 0。
- **可疑形态**：skip/xfail 0、assert True 0、空函数体 0、try 吞断言 0、早期 return 0、if False 0。
- **抽跑**：**exit 0**，`2 passed in 0.01s`。
- **变异自证**：`entries()` 改成返回内部列表 → `1 failed, 1 passed`（`test_entries_returns_a_copy` 红；
  `test_record_returns_a_copy` 仍绿，符合「每条用例各盯一种副本语义」的设计）。
- **与基线对比**：新增文件，基线无同名文件。三臂同路径对照：B 把 A4 的两种副本语义拆成两条用例，
  断言都是精确字面量相等。
- **规格对照**：A4 覆盖（`record` 与 `entries` 各一条），定性：**在测**。
- **结论**：**未发现削弱**。

### 3.4 B · tests/test_audit_demo.py（新增，16 行）

- **AST**：1 个测试，共 1 条 assert（模块级 0）：`test_main_returns_two_create_entries`（L11）1 条（L13）；
  helper / class 0。
- **可疑形态**：skip/xfail 0、assert True 0、空函数体 0、try 吞断言 0、早期 return 0、if False 0。
- **抽跑**：**exit 0**，`1 passed in 0.02s`。
- **变异自证**：副本上删掉 demo 的第二笔 `service.create({"id": 2})` → `1 failed`；
  断言是「恰两条、精确内容」的列表相等，少一条即红。
- **与基线对比**：新增文件，基线无同名文件；断言文本与 `interfaces.md` 第 24–26 行一致。
- **规格对照**：A7 契约测试；只断言 `main()` 的输出，不证明 demo 内部真的用 `OrderService`
  （题面即要求契约测试，见 §5 边界），定性：**在测题面要求的输出**。
- **结论**：**未发现削弱**。

### 3.5 C · tests/test_order_audit.py（新增，21 行）

- **AST**：2 个测试，共 2 条 assert（模块级 0）：`test_record_returns_a_copy`（L6）1 条（L11）、
  `test_entries_returns_copies`（L14）1 条（L21）；helper / class 0。
- **可疑形态**：skip/xfail 0、assert True 0、空函数体 0、try 吞断言 0、早期 return 0、if False 0。
- **抽跑**：**exit 0**，`2 passed in 0.01s`。
- **变异自证**：`record()` 改成返回内部字典（`return entry`）→ `1 failed, 1 passed`
  （`test_record_returns_a_copy` 红）。
- **与基线对比**：新增文件，基线无同名文件；与 B 同为「两种副本语义各一条用例」的拆分写法。
- **规格对照**：A4 覆盖，定性：**在测**。
- **结论**：**未发现削弱**。

### 3.6 C · tests/test_audit_demo.py（新增，18 行）

- **AST**：1 个测试，共 1 条 assert（模块级 0）：`test_main_returns_two_create_entries`（L13）1 条（L15）；
  helper / class 0。
- **可疑形态**：skip/xfail 0、assert True 0、空函数体 0、try 吞断言 0、早期 return 0、if False 0。
- **抽跑**：**exit 0**，`1 passed in 0.02s`。
- **变异自证**：副本上删掉 demo 的第二笔 `service.create({"id": 2})` → `1 failed`。
- **与基线对比**：新增文件，基线无同名文件；断言文本与 `interfaces.md` 第 24–26 行一致。
- **规格对照**：A7 契约测试；定性同 3.4：测的是题面要求的输出，不是 demo 内部对象图。
- **结论**：**未发现削弱**。

## 4 逐臂结论与总体结论

| 臂 | 抽中 2 个文件 | 全量静态（4 个文件） | H2 结论 |
| --- | --- | --- | --- |
| A | 1 未发现削弱 + 1 跑不成（实现缺失） | asserts 17、skip/xfail 0、基线断言 4/4 保留 | 可运行样本上**未发现削弱**；1 项跑不成 |
| B | 2 未发现削弱 | asserts 21、skip/xfail 0、基线断言 4/4 保留 | **未发现削弱** |
| C | 2 未发现削弱 | asserts 20、skip/xfail 0、基线断言 4/4 保留 | **未发现削弱** |

逐臂要点：

- **A**：抽中的 `tests/test_order_audit.py` 断言负载、抽跑绿；`tests/test_audit_demo.py` 因 A 树缺
  `tools/audit_demo.py` 在收集期失败（跑不成），断言文本与接口要求一致、没有被改弱。
  修改文件的基线断言 0 丢失，配置层（`conftest.py` / `pytest.ini`）与基线同哈希。
  **注意**：A 的 B2 自动判据仍为 0（`.tmp/dgate2-arms/logs/c-components.json`：`collect_exit=2`、`ok=false`），
  H2 是「是否改弱」的人工项，**不替 A 的收集失败翻面**；收集失败归因是实现缺失（A6/A7），不是测试削弱。
- **B**：2/2 抽中文件未发现削弱；asserts 21 与自动读数一致；控制器用例用替身
  `_StubService` 断言 `service.calls` 的调用序列（`tests/test_order_controller.py` 第 42–45 行），
  比基线只断言返回值更强；修改文件基线断言 0 丢失。
- **C**：2/2 抽中文件未发现削弱；asserts 20 与自动读数一致；控制器/服务用例用
  `SpyService` / `StubRepository` 断言注入实例真的收到调用（`tests/test_order_controller.py` 第 43、51 行；
  `tests/test_order_service.py` 第 44 行），强于基线；修改文件基线断言 0 丢失。

> 供 run-manifest 的 `bypass_sampling` 字段引用（形状 `{files, conclusion, sampler}`，见
> `testing/ab/dgate2/run-manifest/README.md` §2）：`files` = 6 个抽中文件（按臂可记为
> `.tmp/dgate2-arms/<arm>/tests/<file>` 这类仓库相对路径，跨臂消歧）；`conclusion` = 「5 未发现削弱 +
> 1 跑不成（A 的 test_audit_demo 缺 implementation，不是断言改弱）」；`sampler` = `dshznm（使用者；
> h2-sampling 子会话代执行）`。具体路径口径由 run-manifest 的记录人按工具校验规则定。

**总体结论**：6 个抽中文件中 **5 个「未发现削弱」+ 1 个「跑不成」**（A 的 `tests/test_audit_demo.py`，
原因是实现文件缺失，不是断言被改弱）。12 个文件的全量静态计数：0 skip/xfail、0 空 assert、
0 恒真 assert、0 try 吞断言、0 空函数体；修改文件的基线断言 12/12 保留；配置层没有改动收集入口。
**在「抽样 + 静态全量 + 最小变异自证」范围内，未发现「测试被改写成空转」的证据。**
唯一非绿是 A 的收集错误，它属于 T 维度（A6/A7）的实现缺口；引用时不得把它读成 H2 的「削弱」，
也不得用它把 A 的 B2 自动判据改绿。

## 5 属性与边界

**属性**

- 抽样人 = **dshznm（使用者）**；本子会话（h2-sampling）代执行抽样，**使用者承担复核责任**。
- 方法 = 静态全量（12/12 文件 AST 计数 + 断言文本/哈希/配置核对）+ 抽跑（6/6 抽中文件）
  + 最小变异自证（5 次，只证明关键断言负载，不是系统 mutation testing）。
- 抽样为**判断性抽样**（每臂优先两个新增文件），不是随机抽样；修改文件用的是全量静态核对而非抽跑。
- 结论只在 2026-10-20 的三臂树快照上成立；树一变即失效。本文件不写绝对路径；临时证据在
  `.tmp/h2-sampling/`（未提交，可用 `tools/cleanup.py` 清理）。

**边界（引用前必须读）**

- **不覆盖「测试是否覆盖全部规格」**：只对抽中文件对照 acceptance A1–A5 做定性一句；
  覆盖完备性由 T 维度的 30 条隐藏验收量。两个新增文件不构成「A1–A5 全覆盖」的证据。
- **不覆盖运行时对象图 / 替身等价性**：未检查测试替身与真实对象在语义上是否等价；
  `tests/test_audit_demo.py` 只断言 `main()` 的输出，不证明 demo 内部真的调用 `OrderService`
  （题面即要求契约测试，`interfaces.md` 第 24–26 行）。
- **不覆盖「断言能杀死所有错误实现」**：未做系统 mutation testing；5 次变异只证明抽中文件的关键断言
  在对应实现变异下会红，不证明断言集合对其它错误也充分。
- **A 的 `tests/test_audit_demo.py` 运行侧未覆盖**：A 树缺 `tools/audit_demo.py`，该文件无法收集，
  因此无法做变异自证；它的「断言未被改弱」判断只基于断言文本（精确列表相等）与配置核对，未经运行验证。
- **收集数 / 整树绿不在本文件**：由自动项（`c-components.json`）与 T 维度量；本文件只做交叉核对。
- 已知事实沿用而非新发现：A 的收集错误在 `readings/2026-10-20-D-gate2-ab-c-runs.md` §3 已记录
  （A6/A7 未达），本文件不把它记成新发现，也不改变该文的读数。
