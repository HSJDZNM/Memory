# 16 · 台阶 3c：义务账（只记账、不判罚；按 L5 以 warn 跑一轮）

- **执行**：2026-09-29（本机）；控制面重构会话（**唯一写者**）。
- **树**：分支 `refactor/control-plane`；**before** = `57ee761`（小修提交），本文件与代码
  在同一个新提交里落地（提交号见 §9）。
- **依据**：方案 **§3.3**（义务账）、§4 台阶 3 的 **J1(c)(d)**、§4 台阶 5 的 **L5 上线闸**、
  AGENTS 第 51 条（「待实现」是显式状态）与第 55 条（加键就是改协议；本台阶新增了一条版本轴）。
- **本文件是什么**：设计口径、**R-d 字段级差集**、J1(c)/(d) 的读数、**L5 一轮的读数与命中数**、
  预算对账，以及**没做 / 未核实 / 请评审裁定**的清单。

---

## 1 这一步要解决什么（一句话）

Q7 把「先写测试」从阻断改成 `allow_with_warnings`（台阶 3b 又把它移进独立通道
`pending_findings`），但**「覆盖它的测试还没能运行」这件事只活在那一次判定里**：
下一次判定、下一个会话、本机门禁都读不到它。于是一个拼错的 import 可以永久待实现下去，
而每一次判定都长成"放行了、没违规"。义务账把这件事变成**跨会话持久化**的一行数据，
并且规定**只有一次真实的 pytest 运行**能把它划掉。

---

## 2 设计

### 2.1 三条口径（与方案 §3.3 逐条对应，写在 `src/policy/obligations.py` 的模块 docstring 里）

| # | 口径 | 落点 |
| --- | --- | --- |
| 1 | **会话内只记账，不判罚**：本机制不产出、不修改任何 decision；判定仍然只有 `policy.engine.evaluate` 一条路径 | Hook 记账失败只打一行 stderr；`decision` 与退出码一字不变 |
| 2 | **键 = `(rule_id, target, missing_target)`，不含 `session_id`** | 带上会话标识，新会话就把义务清零（评审 §2.1 否掉的旧设计） |
| 3 | **判罚集中在本机门禁**，且**跨会话持久化** | `tools/obligations_gate.py` 读同一份账本；账本是追加写 JSONL |

方案还要求：**门禁声称 `obligations_open == 0` 时必须同时给出「最近一次真实测试运行时间」**。
实现把它做成 `claim_supported`：0 条义务但账本里**没有任何一次真实运行**时，
`claim_supported=false`、`note` 写明「没有依据」，**门禁按命中处理**（§5 的 B 实例就是反例面）。

### 2.2 账本协议与版本轴

```
{"kind": "pending",   "schema_version": "1.0", "at": "...", "rule_id": "TESTING-002", "rule_version": 1,
 "target": "src/shop/order_service.py", "missing_target": "shop.order_service:cancel_order",
 "missing_targets": ["shop.order_service:cancel_order"], "test_module": "tests/test_order_service.py",
 "checker": "failing_tests"}
{"kind": "test_run",  "schema_version": "1.0", "at": "...", "target": "src/shop/order_service.py",
 "selected_tests": ["tests/test_order_service.py"], "python_tests_executed": true, "source": "policy.check"}
```

- **账本是追加写、不改写**：解除是**折叠时算出来的**（`load()` 按记录顺序走一遍），所以"什么时候记的、
  什么时候解除的"都能从同一份文件读出来；
- **版本轴**：`policy.obligations.LEDGER_SCHEMA_VERSION = "1.0"`（**新增的一条轴**，已登记进
  AGENTS 第 55 条的清单）。读账本时：未知 `kind` / 未知 `schema_version` /
  键集合多一个或少一个一律 `ObligationsError` —— 不静默跳过，也不往"读不懂"的账本里续写；
- **键集合是公开的**（`OBLIGATIONS_KEYS`）：测试与门禁按同一份事实断言，避免两处各写一份。

### 2.3 记账点：为什么 Hook 只记义务、解除只在 CLI

| 路径 | 记什么 | 为什么 |
| --- | --- | --- |
| dsh Hook（受治理会话） | **只记 `pending`** | 它手里有判定（`pending_findings` + 取证摘要里的 `missing_targets`），**没有**"这次到底选中并执行了哪些测试"的结构化字段 |
| `policy.check --obligations`（本机门禁这一侧） | 记 `pending` **和** `test_run` | 它手里同时有判定与真流水线报告（`selection.nodeids` + `served_checkers` + `tool.pytest` 状态） |

**为什么不让 Hook 猜解除**：预取证摘要只有 `served_checkers`，没有选中的测试清单。
按 `served_checkers` 猜会把"选了一堆用例却一个都没跑起来"读成跑过了 ——
而那个错误的方向是**把义务悄悄清掉**（读数变小、门禁变绿），比"义务挂着不解除"危险得多。
这条边界由 `tests/unit/test_dsh_obligations.py::test_the_hook_records_no_discharge` 钉住。

### 2.4 解除判据（三条结构化事实 + 一条"或"规则，**请评审**）

**"真实 pytest 运行"** = 三条同时成立（`obligations.real_pytest_run`）：

1. `tool.pytest` 的记录状态 ∈ `{ok, findings}`（`pending_implementation` /
   `crashed` / `unavailable` 都不算跑成）；
2. `failing_tests` 在 `served_checkers` 里（退出码 5 = 选中了用例、一个都没收集到，
   那时验证器只服务 `missing_tests`，台阶 1 / R-f）；
3. 选中的测试非空（`selection.nodeids` 非空：没有选中任何测试的早退分支没有执行证据）。

**一条 `test_run`（`python_tests_executed=true`）解除哪些义务**：`target` 相同，**或**
"那次跑不起来的测试模块这次真的被选中"（`test_module ∈ selected_tests`）。

- 为什么需要"或"：Q7 的真实次序是「先写测试（target = 测试文件）→ 再写实现（target = 实现文件）」，
  只按 `target` 匹配会让义务永远挂着；而"覆盖它的测试这次真的跑了"才是这条义务要等的那个事实。
- **这是本次的一个设计决定，不是方案原文**（§3.3 只给了键与"只由真实运行解除"）：请评审确认或改口径。
- 实测（§5）：A1 的 `target` 是 `src/shop/order_service.py`、`test_module` 是
  `tests/test_order_service.py`；A2 的 `target` 与它相同，两条通道**同时**成立。

### 2.5 `check_volume` 的键与"不加版本号"的理由

J1(c) 要求 `obligations_open > 0` 时 `check_volume.complete = false`。实现：

- 调用方**显式**给了义务账摘要时，`check_volume` 才多两个键 `obligations_open` /
  `obligations_note`，并把 `complete` 与 `obligations_open == 0` 取合取；
- **没给账本时两个键都不出现** —— 缺键的意思是"这次没有账本可读"，不是"0 条未结义务"
  （AGENTS 第 46/50 条：两种读法必须能分开）；
- 文本渲染里，义务**单独一行** `OPEN OBLIGATIONS:`，不与"缺维度"的 `INCOMPLETE:` 混成一句
  （`complete` 有两个成因，理由必须说得出来，AGENTS 第 52 条）；
- **没有引入 `CHECK_VOLUME_SCHEMA_VERSION`**：`check_volume` 是 CLI 包装字段
  （`policy/check.py` 的模块 docstring 写明"`--json` 的顶层是 CLI 包装……
  其中 `result` 就是完整的决策协议载荷"），它不是跨进程协议载荷；既有的
  `layer_source@@ / `check_volume` 也是按"只增不改"的包装约定加进来的。
  **决策载荷 `result` 一个字节都没动**（§3 的差集读数）。这条口径请评审确认。

---

## 3 R-d 字段级差集（**先交差集，再改**）

**口径**：台阶 3b 的同一台仪器 `.tmp/step3b/probe_decisions.py`（**未改一个字节**），
10 个场景（四种 decision + pending 一族 + 混合批 + 审批门禁 + 失败关闭对照）+ 决策真值表；
**before 读数在动手之前采集**（`57ee761` 树）。

| 产物 | sha256 | 说明 |
| --- | --- | --- |
| `.tmp/step3c/decisions-before.json` | `CFAD8C32C59A57A49290759D54DB020C57F9CB6A07F0FBDF7D759D9F13AD4588` | 动手前（23992 B） |
| `.tmp/step3c/decisions-after.json` | `CFAD8C32C59A57A49290759D54DB020C57F9CB6A07F0FBDF7D759D9F13AD4588` | 动手后（**同一 sha256**） |
| `.tmp/step3c/field-diff.json` | `8799B73603EF5D14096027BC66B80FA9CE9870A2F77829F3E943602F037BA22C` | **count = 0** |

- **预注册的形状**：本台阶**预期不改判定**（账本只是记账；`check_volume` 的两个键不在
  `result` 里）。读数与预期一致：**10 个场景的 `decision` /
  `violations`（含内容）/ `pending_findings` / `matched_rules` /
  `skipped_rules` / `required_action` / 载荷键集合 / 模型字段集合逐个相同，差集 0 条**；
- 仪器自检：同一进程内重算两遍逐字节相同（`same_tree_rerun_identical = true`）；
- **这条差集只覆盖 `policy.engine.evaluate` 的载荷**：Hook 的退出码 / 审计记录 / API 响应不在它的口径里。
  **未核实**：`check_volume` 新增两个键之后，仓库外是否有消费方按"键集合恰好等于旧集合"来读
  `--json`（仓库内没有这样的断言，`tests/integration/test_cli.py` 用的是键存在性断言）。

---

## 4 J1(c) 与 J1(d) 的读数

判据（方案 §4 台阶 3）：(c) `obligations_open > 0` 时 `check_volume.complete = false`；
(d) 解除只由一次真实 pytest 运行判定。

驱动方式：**真流水线**（真 pytest 子进程、真选择、真证据协议），
`tests/integration/test_obligations_round.py`（3 条用例）：

| 步骤 | 读数 |
| --- | --- |
| 先写测试（测试文件 import 还不存在的 `shop.order_service:cancel_order`）+ 生产文件上的一次改动 | `decision=allow_with_warnings`、`violations=[]`、`pending_findings` 非空、退出码 **1**（与台阶 3b 相同：待实现不阻断） |
| **(c)** | `check_volume.obligations_open = 1`、`check_volume.complete = false`、`missing_dimensions = []`（**理由是义务，不是缺维度**） |
| 账本内容 | `["pending", "test_run"]`；那条 `test_run` 的 `python_tests_executed = false`（pytest 被选起来了、一个用例都没跑成 —— "没跑成"不许被读成"跑过了"） |
| 再写实现（同一个工作区补上 `cancel_order`） | `decision=allow`、退出码 **0**；账本变成 `["pending", "test_run", "test_run"]`，最后一条 `python_tests_executed = true` 且 `selected_tests` 含 `tests/test_order_service.py` |
| **(d)** | `obligations_open = 0`、`complete = true`、`closed = 1`、`last_real_test_run` 非空 |

**"解除"这一步的独立性**：`test_only_a_real_pytest_run_closes_the_obligation` 断言
`state.closed == 1` 且账本里确实多了一条**真运行**记录 —— 不是"新会话把义务清零"。

---

## 5 L5 试用期：一轮读数与命中数

**"一轮"的定义（本文件的口径，请评审确认）**：一次完整的「先写测试 → 再写实现」推进，
**两个实例**各跑一遍真流水线，随后各跑一次门禁：
**实例 A = .tmp 受控项目**（Hook 路径 + CLI 路径），**实例 B = 仓库自身**（CLI 路径）。

| 步骤 | 读数 | 命中 |
| --- | --- | --- |
| **A1** 先写测试（Hook 路径，`python -m adapters.dsh.hooks`，真 pre_evidence 流水线，43 条规则全开） | `exit 0`、`decision=allow_with_warnings`、`pending_findings=1`、stderr 有 `[policy] obligations recorded=1 ledger=instance-a.jsonl` | 记账 **1** 条 |
| **A1 之后**：门禁 | `HITS: 1 / 1`、`exit 1`；`OPEN OBLIGATIONS: 1 条未结义务 —— TESTING-002 src/shop/order_service.py ← shop.order_service:cancel_order（×1，自 2026-09-29T14:29:06Z）` | **1** |
| **A2** 再写实现（CLI 路径，真 pytest） | `exit 0`、`decision=allow`、`obligations_open=0`、`complete=true`；账本 `closed=1` | 解除 **1** 条 |
| **A2 之后**：门禁 | `HITS: 0 / 1`、`exit 0`；`OPEN OBLIGATIONS: 0（最近一次真实 pytest 运行 2026-09-29T14:29:08Z）` | **0** |
| **B** 仓库自身（CLI 路径，真 pytest） | `decision=block`（43 条规则对仓库真实文件判定，与义务无关）、`obligations_open=0`；账本里有一次真运行（`selected_tests=["tests/unit/test_obligations.py"]`） | **0** |
| **B 之后**：门禁 | `HITS: 0 / 1`、`exit 0` | **0** |

**一轮合计**：**2 个账本、3 次门禁运行、命中 1 次**（A1 那次）；记账 1 条、解除 1 条；
两次 0 命中**都**来自真实读数（A2 有真运行、B 有真运行）—— 这正是 L5 升格判据要的那件事：
"0 命中必须来自至少一次真实读数"。

- **树摘要**：`sha256:2f53d6d39d4de744b41f81051dc114ebeb8de2879b916604b6ee0304206a62ed`（两个实例同树）；
- **读数原文**：`.tmp/step3c/round/readings.json`（sha256 `DF3E70196D9AC974CC7A4F0F23D5E5A6084316AD1B3B6683CDD6A672B68A1188`）、
  仪器 `.tmp/step3c/round.py`（sha256 `9D7937E3619843A4782456B583674E8711EA55B3AAED7DAD9F5734AF23FBA6DD`）；
- **它不是门禁的阻断步**：`tools/ci_local.py` 的步骤表里**没有** `obligations_gate.py`；
  非零退出只是读数（"会红"这一次是 A1）。升格（接进门禁）需要评审先认定"跑过 N≥1 次且 0 命中"。

**这次读数暴露的两件事（都写下来）**：

1. **只改测试文件不会触发「待实现」**：测试选择器在"变更集里没有生产文件"时直接说
   `变更集里没有生产文件，测试选择不适用`，于是 `tool.pytest` 记 `ok`、
   `failing_tests` 照样进 `served_checkers`（R-f 允许的"没有对象"那一支）。
   所以"先写测试"这一步**必须**同时有一次生产文件改动，`pending` 才会出现 ——
   这不是缺陷，但**它决定了义务账在真实会话里的触发面**：只写测试文件的那些动作不记账。
2. **`served_checkers` 里的 `failing_tests` 不等于"跑了用例"**（上面那一支）——
   这正是 `real_pytest_run` 必须有第 3 条（选中的测试非空）的原因；按 `served@@ 猜会误解除。

---

## 6 预算对账（方案 §7.1 的上调后上限）

口径 `len(text.splitlines())`（与方案 §7 同）：

| 桶 | 实测 | 原估 | 1.5× 停下复核线 | 结论 |
| --- | --- | --- | --- | --- |
| src（`obligations.py` 540 新增 + `check.py` / `hooks.py` / `adapter.py` 合计 +174 修改） | **714 行** | 0.25k–0.8k | 1.2k | 在区间内上限附近（0.89× 原上限） |
| tests（4 个文件：315 + 248 + 162 + 147） | **872 行** | 0.3k–0.9k | 1.35k | 在区间内（0.97× 原上限） |
| 工具（`tools/obligations_gate.py`） | **137 行** | 原估里**没有这一项** | —— | 与台阶 0 的 `tools/provenance_loop.py`（302 行）同类，登记 |
| 文档（AGENTS 第 56 条 / README / dsh README / 本文件） | 见 §9 | 原估里没有 | —— | —— |

**未触发 1.5 倍的停下复核线**；**墙钟**不在 §7 的分桶里，按纪律如实记在 §9。

---

## 7 未做 / 未核实 / 请评审裁定

1. **请评审裁定（口径 1）**：`test_run` 的解除规则里那条"**或** `test_module ∈ selected_tests`"
   是本次的设计决定（§2.4），方案 §3.3 只给了键与"只由真实运行解除"。
2. **请评审裁定（口径 2）**：`check_volume` 加了两个键而**没有**递增任何版本号
   （§2.5 的理由是"它是 CLI 包装、不是协议载荷"）。若评审认为 CLI 包装也算协议载荷，处置是：
   给 `check_volume` 引入自己的版本轴并显式递增，同时改 `--json` 的消费方断言。
3. **未核实**：Hook 侧 `obligations_ledger` 是**新增的可选配置键** —— 旧配置照常加载
   （缺省 = 不记账），但**没有**验证过"仓库外已有的 dsh-adapter.yaml 带未知键"这一侧
   （本仓库的加载器按设计拒绝未知键，见 AGENTS 第 3 条）。
4. **未接**：`obligations_gate.py` 不在 `ci_local.py` 的步骤表里（L5 试用期，§5）；
   也**没有**接进 `.github/workflows/phase-8.yml`。升格是下一轮的事。
5. **未核实**：真实 dsh 会话里"退出码被归一化"（本机把 2 压成 1）对记账的影响 ——
   本次 A1 用的是 Hook CLI 子进程，读的是 Hook 自己的退出码。
6. **未做**：`policy.check` 的 `--obligations` 目前**只**由调用方显式给出；
   README 的命令是手写路径，没有任何"默认账本位置"（避免把义务写进一个没人读的地方）。
7. **本轮没有跑 `tools/cleanup.py`**；`.tmp/step3c/` 的产物全部保留供评审复核。
8. **本轮没有 push**、没有 `--no-verify`、没有强推、没有 `git add -f`；
   改动**只用 `write` / `edit` 落树**，提交按路径暂存。

---

## 8 复现命令（按顺序）

```powershell
# R-d：before 侧（动手前采集；现在重跑会得到 after 侧的读数）
.venv\Scripts\python.exe .tmp\step3b\probe_decisions.py --out .tmp\step3c\decisions-before.json

# R-d：after 侧与差集（自检必须 count=0 且 exit 0）
.venv\Scripts\python.exe .tmp\step3b\probe_decisions.py --out .tmp\step3c\decisions-after.json
.venv\Scripts\python.exe .tmp\step3b\json_field_diff.py --before .tmp\step3c\decisions-before.json --after .tmp\step3c\decisions-after.json --out .tmp\step3c\field-diff.json

# J1(c)/(d)：真流水线的一轮（先写测试 → 再写实现）
.venv\Scripts\python.exe -m pytest tests\integration\test_obligations_round.py -q
.venv\Scripts\python.exe -m pytest tests\unit\test_obligations.py tests\unit\test_dsh_obligations.py tests\integration\test_obligations_gate.py -q

# L5：一轮读数（两个实例 + 三次门禁运行）
.venv\Scripts\python.exe .tmp\step3c\round.py
.venv\Scripts\python.exe tools\obligations_gate.py --ledger .tmp\step3c\round\instance-a-a1-state.jsonl
.venv\Scripts\python.exe tools\obligations_gate.py --ledger .tmp\step3c\round\instance-a.jsonl
.venv\Scripts\python.exe tools\obligations_gate.py --ledger .tmp\step3c\round\instance-b.jsonl
```

---

## 9 本次改动的文件

| 文件 | 处置 |
| --- | --- |
| `src/policy/obligations.py`（新增，540 行） | 账本代数：键 / 记录 / 折叠 / 解除 / 摘要 / 描述；三条口径写在 docstring |
| `src/policy/check.py`（+117） | `--obligations`；`obligation_summary` / `selected_nodeids`；`build_check_volume(..., obligations=)`；文本与 JSON 输出 |
| `src/adapters/dsh/hooks.py`（+44） | `book_obligations`（只记 pending；写不了只打一行，不改判定） |
| `src/adapters/dsh/adapter.py`（+13） | `AdapterConfig.obligations_ledger` + 配置字段白名单 + 解析 |
| `tools/obligations_gate.py`（新增，137 行） | L5 warn 门禁：读数 + 树摘要 + 非零退出（不阻断） |
| `tests/unit/test_obligations.py`（315 行） | 账本代数、解除规则、失败关闭、整数读数 |
| `tests/integration/test_obligations_round.py`（248 行） | J1(c)/(d)：真流水线的一轮 |
| `tests/unit/test_dsh_obligations.py`（162 行） | Hook 侧：只记义务、不改判定、写不了要出声、不记解除 |
| `tests/integration/test_obligations_gate.py`（147 行） | 门禁：会红 / 会绿 / 没有依据 / 读不懂 / 多实例并列 |
| `AGENTS.md`（+16） | 新增第 56 条（三条口径 + J1(c)(d) + L5 状态 + 版本轴） |
| `README.md`（+28） | 「义务账（台阶 3c · L5 试用期）」一节；顺带修正一处过时读数（决策协议 1.0 → 1.1） |
| `src/adapters/dsh/README.md`（+15） | `obligations_ledger` 配置项与三条边界 |
| `tools/README.md`（+1） | 登记 `obligations_gate.py` |
| 本文件 | 新归档 |

**执行纪律**：只用 `write` / `edit` 落树；按路径暂存；没有 `--no-verify`、
没有 `git add -f`、没有强推、没有跑 `tools/cleanup.py`。
**墙钟**：本台阶从 R-d before 读数到提交约 1.5 小时（含两次测试套件回归与一轮 L5 读数）；
门禁（`ci_local.py --full`）的读数在提交后单独记录。
