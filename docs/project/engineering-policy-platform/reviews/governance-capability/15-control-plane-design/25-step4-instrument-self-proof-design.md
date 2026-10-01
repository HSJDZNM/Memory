# 25 · 台阶 4 · 仪器自证（R-h）设计稿（**只报告**，只写文档）

- **执行**：2026-10-01（本机）；控制面重构会话（**唯一写者**）。
- **树**：分支 `refactor/control-plane`；写这份稿子时的 HEAD = `f568a99`（`git status --porcelain -uall` 为空）。
- **依据**：17 号 §2.3 第 7 条（仪器自证判「**建机制**」，服务对象 = 门禁步骤 + G01–G13 + 5 个封条场景）
  与 §2.2 清单乙 B3；方案 §4 台阶 4 的「红→绿」（三态皆红）、§5.1 **J5**（新检查自证）、
  §5.3 的封条三段式与退出码表；AGENTS 第 45（自己的仪器也要能失败）/ 48（读数属于哪棵树）/
  50（口径诚实）/ 55（加键就是改协议）/ 56（账本不存在 = 不适用）条。
- **本文件是什么**：R-h 的**设计稿**——对象清单（带实数）、三态皆红的判据、只报告期的表达、
  要加的键与**版本轴**、消费方、R-d 预注册形状、**需要 CI 线配合的部分（交接清单）**、
  预算与「越过复核线多少 / 可以缩小到什么范围」。
- **本文件不是什么**：不是开工单，也不是排期。**本文没有改任何代码、任何载荷、任何数据文件**；
  R-h 的机制、`validation/control-plane.yaml`、门禁接封条**一个都没建**。

---

## 0 一句话

把「**每条仪器检查都要能证明自己会红**」做成**可读的红**，并且在解冻之前**一条退出码都不接**：
三种坏形态（没有 `check_id` / 既没有 `mutation_id` 又没有 `gap_note` / 变异打不上补丁）
在只报告期用「**显式的红 + 显式的未接线**」表达（`enforced: false` + `would_exit_code: 1` + 机器行），
它就是将来那条阻断条件的**预注册形态**，而不是一条被悄悄推迟的检查。

---

## 1 对象（四族，带实数）

| # | 族 | 实数（读数，2026-10-01） | 出处 / 复现 |
| --- | --- | --- | --- |
| 1 | 门禁步骤 | workflow 里有 `run` 块的步骤 **44** 条：`--full` 本机执行 **31**、`--hook` 执行 **30**（差的那条是推迟到 `--full` 的 `Learning notebooks are in sync`）、bash-only **11**、登记豁免 **2** | `python tools/ci_local.py --list`；`tools/ci_local.py` 的 `_plan_steps(False/True)` |
| 2 | 治理能力缺口探针 | **G01–G13 = 13** 条（`tools/governance_gap_probe.py` 的 `CHECKS`） | `python tools/governance_gap_probe.py --json-out …` |
| 3 | 判据级封条闭环 | **5** 个场景（`tools/provenance_loop.py` 的 `SCENARIOS`：`pass-sealed-check` / `external-write` / `unprovable` / `no-declaration` / `self-check`） | `python tools/provenance_loop.py` |
| 4 | 义务门禁 | **1** 条本机**只报告**步骤（`tools/obligations_gate.py`，L5 试用期） | `tools/ci_local.py` 的 `REPORT_ONLY_STEPS` |

**合计 63 条**（44 + 13 + 5 + 1）。**两个数不是一回事，写清楚**：17 号 §2.3 记的「33 条门禁步骤」
是**当时** `--full` 的执行数；workflow 之后删过两步（`dsh adapter contract and hook behaviour`、
`Performance baseline`，理由写在 `tools/ci_local.py` 的注释里），因此今天是 **31**。
引用「多少条在管」时必须带**是哪一族、哪个口径**（AGENTS 第 43 条的同一条纪律）。

**为什么这四族都在范围内**（17 号 §2.3 第 7 条的结论）：它们是**平台自己的仪器**，
没有一条是「已声明不治理」的对象；且 J5 的后半句（「既无 `mutation_id` 又无 `gap_note` → 红」
这条要求本身要被门禁守住）需要一个**不只覆盖产品、也覆盖仪器**的载体。

---

## 2 判据（三态皆红，可证伪）

**三态**（方案 §4 台阶 4 的原文）：一条检查只要落在下面任意一态，就**红**。

| 态 | 判据式（结构化，不解析文本） | 读数键 | 谁判 |
| --- | --- | --- | --- |
| ① 没有身份 | 对象在差集里出现、但 `checks` 表里没有它的 `check_id` | `red_conditions.no_check_id.items[]` | 自证执行器（加载期读到对象清单之后） |
| ② 没有自证也没有缺口说明 | `mutation_id` 缺失 **且** `gap_note` 缺失（含**空白串**：与 `wiring_scope` 的「空理由」同口径，判缺失而不是判通过） | `red_conditions.no_mutation_and_no_gap_note.items[]` | 同上 |
| ③ 变异打不上 | 按 `mutation_id` 取的补丁在**影子树**上 `git apply --check` 失败 | `red_conditions.patch_not_applicable.items[]`（带 `mutation_id` 与失败原因） | 同上 |

**两条反退化**（不写下来，这三条态就会被读成「跑过了、没红」）：

1. **「未评」不是「不红」**：表读不到 / 影子树建不出来 / 检查命令超时，写 `status: unavailable` + `reason`
   （与 AGENTS 第 56 条「账本不存在 = 不适用」同一条口径）。**三态里任何一态都不许用 `0` 冒充**；
2. **对象清单本身要有第二来源**：`checks` 表说自己有多少条不算证据；对象清单必须与
   实际可枚举的三处（workflow 步骤表 / `CHECKS` 常量 / `SCENARIOS` 常量）**双向比对**，
   差集非空即红（否则「表里只写 1 条、其余 62 条谁也不提」会静默通过）。

**J5 的后半句怎么被守住**：态 ② 这条规则自己必须有自证用例——
在**影子表**（复制一份 `checks` 表、删掉某条的 `mutation_id` 与 `gap_note`）上跑一次，
断言 `red_conditions.no_mutation_and_no_gap_note` **从 0 变 1**；撤回后变回 0。
**「跑了、是绿的」不算覆盖**（AGENTS 第 45 条）。

---

## 3 只报告期怎么表达（一条退出码都不接）

| 层 | 形态 | 为什么 |
| --- | --- | --- |
| 载荷键 | `checks[]`（每个对象一行**读数**：`check_id` / `object_kind` / `mutation_id` / `gap_note_present` / `state`）、`red_conditions`（三态各一格，与 `wiring` 的 `red_conditions.in_scope_not_wired` 同形状） | 复用既有形状，不新造一套「红」的表达 |
| 每格 | `status` / `count` / `items[]` / `red_when` / `enforced: false` / `would_exit_code: 1` / `promote_when` | 「这是一条红条件」由**块本身的存在**表达；「此刻真的红着」由 `count > 0` 表达（23 号 §14.2③ 的裁定，同一口径） |
| 文本 | 一行机器行 `INSTRUMENT_SELF_PROOF: <三态计数> / objects=<n>` + 一句话 headline | 与 `wiring` 的 `headline.machine_line`、`exemption_expiry` 的 `HITS:` 行同一形态：机器行是**跨文件契约**，人读的句子不进判据 |
| 退出码 | **恒 0**（只报告）；非零退出只在「读不到」时（用法错误 2），与判据无关 | 本轮总原则：不新增阻断步骤 |

**升格路径**（预注册，不是承诺）：与 L5 同型——「跑过 N≥1 次且三态合计 0 命中，且 0 命中来自
至少一次真实读数」→ 才允许把某一态接进退出码；届时**必须**先有一轮 `warn + 非零退出`。

---

## 4 要加的键与版本轴（AGENTS 第 55 条）

| 载体 | 加什么 | 版本轴 | 同批必须改的引用点 |
| --- | --- | --- | --- |
| 自证报告（新载荷） | 顶层 `schema_version` / `reading_context` / `objects` / `checks[]` / `red_conditions` / `headline` | **`INSTRUMENT_SELF_PROOF_SCHEMA_VERSION = "1.0"`**（新载荷**第一次就要带轴**；AGENTS 第 55 条的「还没有版本轴的载荷」那一档现在是空的，新增一条必须登记回那张表） | 报告打印、`--json`、契约用例、`AGENTS.md` 第 55 条的表 |
| 检查登记表（新数据） | 每条 8 字段：`check_id` / `owner` / `command` / `covers` / `evidence_level` / `mutation_id` / `gap_note` / `severity`（方案 §3.2 的 checks 段，**只放指针**） | 数据文件自己的 `schema_version`（新文件从 `"1"` 起） | 加载器、`unregistered_steps()` 那类「悬空即红」的双向比对 |
| 现有载荷 | **一个键都不加** | —— | —— |

**刻意不并进既有载荷**：`adapters.cli wiring` 是「发现 × 声明」的账，`policy.check --json` 是判定包装，
把仪器自证塞进它们任何一个都是**量纲混用**（第 50 条），也会逼着那些载荷跟着升版。

**消费方总表**：

| 消费方 | 读什么 | 不读什么 |
| --- | --- | --- |
| 评审（人） | `red_conditions` 三态 + `headline.machine_line` | 不读原始命令输出 |
| 门禁（**升格之后**） | 只读 `red_conditions` 的 `count` | 不解析文本（AGENTS 第 49 条的口径） |
| `tools/phase_evidence.py`（CI 线） | 只读**指针**（报告路径 + sha256） | 不读逐条明细 |
| Hook / Policy Engine / API | **什么都不读** | 仪器自证**不是**判定输入；它不许改变任何 allow / block |

---

## 5 R-d 预注册形状（落地后逐条核对）

| # | 尺子 | 预期 |
| --- | --- | --- |
| R1 | 决策载荷（10 个场景，`.tmp/step3b/probe_decisions.py`） | **逐字节相同** |
| R2' | `VERDICT` 判定行（144 行 + 插件字面量，`.tmp/step9/probe_verdict_lines.py`） | **逐字节相同**；`VERDICT_SCHEMA_VERSION` 仍 `1.0` |
| R5 | `adapters.cli wiring --json` 三个入口 | 顶层**新增键为 0**（本稿不碰覆盖账）；`result` / `failures` / `counts` / `fact_counts` / `channels[].status` **逐字段相同** |
| R6 | `provenance.cli wiring-scope --check --json` | **逐字节相同** |
| R7 | 门禁各步骤退出码（含第 24 步 `adapters.cli wiring` 默认形态） | **一个都不变** |
| R8 | **新载荷**的自证 | 同一棵树上两次运行**逐字节相同**（`run.id` / `run.started_at` 这一类归属读数按 §15.1.1 的规则剥掉后相比；剥离项要写出来） |
| 硬约束 | 三态皆红的自证 | 在**影子表**上删 `mutation_id` + `gap_note` → 态② 的 `count` 从 0 变 1；撤回 → 变回 0 |

---

## 6 需要 CI 线配合的部分（交接清单）

> **文件归属**（2026-10-01 会话边界）：`tools/ci_local.py`、`tests/unit/test_ci_local*.py`、
> `tools/phase_evidence.py` 属 **CI 线**，控制面重构会话**一个字都不许动**。
> 因此下面每一项都只写「**要 CI 线做什么**」，不代写。

| # | 文件（CI 线） | 要加什么 | 期望读数 | 为什么必须 CI 线做 |
| --- | --- | --- | --- | --- |
| 1 | `tools/ci_local.py` 的 `REPORT_ONLY_STEPS` | 一条只报告步骤 `Instrument self-proof (report only)`（`args=("tools/instrument_self_proof.py", "--json")`，必填 `reason` / `expires_at` / `adopted` / `reads`） | `HITS: 0` 类的机器行由本工具自己给；非零退出**不计入门禁失败** | 只报告步骤表是 CI 线的数据；改它要同步 `tools/exemption_expiry.py` 的读数（`declared` 会 **9 → 10**） |
| 2 | `tools/ci_local.py` 的步骤分组 | 新步骤的 `name` 必须登记进某个分组，否则 `unregistered_steps()` 直接失败关闭 | `--list` 里出现该步骤、`unregistered_steps() == []` | 同上；漏登记会让这一步「既不执行、也不报告跳过」（本仓库真的这样漏跑过） |
| 3 | **门禁接封条**（方案 §4 台阶 0 的 R-e 缺口：31 步没有任何一步交出判据级封条） | 在 `_run_line` 前后各取一次 `referenced_inputs_digest`，`pre != post` → **退出码 3**（§5.3 的封条失效） | `external_write` / `unprovable` 两种状态可从读数里读出来 | **这是新的阻断语义**，按 L5 必须先 warn 跑满一个轮次；且它改的是门禁自己的执行路径 |
| 4 | `.github/workflows/phase-8.yml` | 若新步骤要在 CI 上也跑，加一个同名 `run` 块；**CI 上没有宿主**（dsh / profiles），该步必须能自我声明 `not_applicable` 或 `unprovable` | CI 与本机读数分开记（AGENTS 第 48 条） | workflow 是 CI 线的文件 |
| 5 | `tests/unit/test_ci_local*.py` | 新步骤的登记/选择/只报告读数各一条用例 | 用例名与期望写在这条交接里 | 那几个用例文件是 CI 线的 |
| 6 | `tools/phase_evidence.py` | 若要进阶段证据，只加**指针**（报告路径 + sha256），不加逐条明细 | 证据载荷键集合**不变**（第 55 条：加键就要升版） | phase_evidence 属 CI 线 |

**交接的验收办法**（写给下一位写者）：改完之后跑
`python tools/ci_local.py --full --python .venv/Scripts/python.exe`，
把 `--timings` 与只报告步骤的机器行一起贴进 23 号的新一节；**不要**只贴退出码。

---

## 7 预算（口径 = 新增行，`git show --numstat`）

**先对本轮（第 25 轮）的对账**——两个口径都要给，因为它们对「复核线」的含义不同：

| 桶 | 台阶 4 累计（截至 `f4a46a6`，§14.5） | 本轮属于台阶 4 的 | 本轮全部（含第 0.5 条小修） | 台阶 4 累计（含本轮） | 复核线 | 余量 |
| --- | --- | --- | --- | --- | --- | --- |
| src | 1426 | **+41**（`wiring.py` 9 / `wiring_scope.py` 32） | +85（另含 `client.py` 44） | **1467** | 1950 | 483 |
| tests | 1933 | **+82**（`test_wiring_inventory.py` 4 / `test_provenance_wiring_scope.py` 78） | +287（另含两个新用例文件 205） | **2015** | 2100 | **85** |
| tools | 893 | 0 | +21（`orchestration_loop.py`） | 893 | —— | —— |
| 数据 / 文档 | 1849 | +34（声明文件）/ +92（文档） | 同 | 1975 | —— | —— |

**第二个口径要单列**：若「台阶 4 累计」按**本轮全部新增**读（把第 0.5 条稳定性小修的
src 44 / tools 21 / tests 205 也算进来），则是 **src 1511 / tests 2220** ——
**tests 已经越过复核线 120 行**（这笔账属于「非台阶 4 的稳定性小修」，不是台阶 4 的机制）。
**请评审定夺复核线按哪个口径读**（§8 第 2 条）。两个口径下 R-h 的结论相同：**tests 必然越过，src 不越过**。

**R-h 自己的估计**（本稿只估、不落码；依据是同类机制的已花行数：`tools/governance_gap_probe.py` 的
检查骨架、`tools/provenance_loop.py` 的 5 场景闭环、`src/provenance/wiring_scope.py` 的加载器）：

| 件 | src | tests | 依据 |
| --- | --- | --- | --- |
| 检查登记表的加载与双向比对 | 80–140 | 60–100 | 与 `wiring_scope.py`（175 行含报告）同量级 |
| 影子树 + 变异应用 + 两态断言（`patch_not_applicable` 是第三态） | 120–200 | 80–140 | `tools/provenance_loop.py` 302 行的同量级 |
| 只报告载荷（含 `reading_context` 与机器行） | 60–100 | 40–60 | 与 `exemption_expiry` 的载荷同量级 |
| **合计** | **260–440** | **180–300** | —— |

**结论**：

- **src**：1467 + 260~440 = **1727–1907**，**不越过** 1950（余量 43–223）；离硬上限 3250 很远；
- **tests**：2015 + 180~300 = **2195–2315**，**越过复核线 95–215 行**；离硬上限 3500 还有 1185–1305；
- 因此按方案 §4 的纪律（「实测超过 1.5 倍就停下复核」），R-h **不能整包开工**，
  必须先按下面的某一条**缩小范围**（缩到多少要请评审拍板）。

**可以缩小到什么范围**（三条，按代价从小到大）：

| 方案 | 做什么 | 不做什么 | tests 估计 | tests 累计 | 是否在复核线内 |
| --- | --- | --- | --- | --- | --- |
| **A（推荐）** | 表的加载 + 三态判据 + 只报告载荷 + 机读自证用例；**存量 62 条先写 `gap_note`**（「存量检查，未做变异自证」） | 不做任何变异（`mutation_id` 全空） | ~60 | ~2075 | **线内**（余量 25） |
| B | A + 给 **3 条**已有现成变异体的检查（G05 / G06 / G12）建 `mutation_id` 并真跑两态 | 其余 59 条写 `gap_note` | ~120 | ~2135 | 越线 35 |
| C | 拆两次：R-h1 = A；R-h2 = 变异执行器（单独一次复核） | R-h2 不在本轮 | R-h1 ~60 / R-h2 120–240 | 分别 2075 / 2195–2315 | R-h1 线内；R-h2 越线 95–215 |

**为什么 A 在判据上是站得住的**（不是偷工）：方案 §5.1 的 J5 原文是「每条**新**检查必须能证明
自己会红」——存量检查的正确形态**就是**一条可评审的 `gap_note`（AGENTS 第 45 条：做不到就写下
「这条检查覆盖不到」）。而且 A 保留了三态里最容易悄悄溜走的那一条：**态② 这条要求本身**有自证用例。
A 的代价也写清楚：**`validation/instrument-checks.yaml` 里 62 行的 `mutation_id` 会是空的**，
读的人必须看得见「这批对象还没有变异自证」——这正是 `red_conditions` 要数的东西。

---

## 8 未核实 / 请评审裁定

**未核实（逐条）**：

1. R-h 的三态判据**没有实跑过**：本稿只有判据式与对象实数，没有任何一条检查真的被变异过；
2. 「门禁 31 步 + G01–G13 + 5 场景 + 义务门禁 = 63 条」这个整数**只数了对象**，
   没有核对每一条是否**可枚举**（bash-only 的 11 步本机跑不了，见下面第 7 条）；
3. 影子树的载体没有选型实测（`git archive HEAD` 副本 vs `src/provenance/worktree.py` 的既有实现）——
   两者对「未跟踪文件」与「.tmp 落点」的行为不同；
4. `git apply --check` 在 Windows 换行（`core.autocrlf`）下对补丁的判定**没有实测**；
5. 预算区间是估计，不是 `numstat` 读数（本稿只写文档）。

**请评审裁定（七条）**：

1. **检查登记表的载体**：R-h 自带一份（`validation/instrument-checks.yaml`），还是等台阶 5 的
   `validation/control-plane.yaml`（方案 §3.2 的 facts + checks 合表）——后者会让 R-h 依赖一个尚未解冻的台阶；
2. **复核线的分子口径**：按「台阶 4 桶」（1467 / 2015）还是「本轮全部」（1511 / 2220）读？
   这决定了「越线 95–215 行」的基准；
3. **缩小方案**：取 A / B / C 哪一条（推荐 A）；若取 B，是否放行那 35 行越线；
4. **变异体放在哪**：仓库内 `validation/mutations/*.yaml`（可评审、可追溯）还是在 `.tmp`（不进树）？
   进树就要为它定「只放指针不放正文」的边界；
5. **升格判据**：三态各自的「N≥1 次且 0 命中」由谁记轮次（本机门禁的只报告读数，还是人工登记）？
6. **与 R-e 封条的关系**：门禁接封条（方案 §4 台阶 0 的缺口）与 R-h 是两件事还是同一件？
   本稿把它们分开（第 6 节第 3 条只列交接，不合并），请确认；
7. **bash-only 的 11 步怎么算**：本机跑不了、CI 上跑——R-h 对它们写 `unprovable`（带 reason）、
   `not_applicable`，还是只登记 `gap_note`？三条都不许写成「通过」。

---

## 9 复现命令（只读）

```powershell
# 对象实数：门禁步骤（44 / 31 / 30 / 11 / 2）
.venv\Scripts\python.exe tools\ci_local.py --list

# 对象实数：G01–G13 与 5 个封条场景
.venv\Scripts\python.exe -c "import importlib.util,sys; s=importlib.util.spec_from_file_location('gp','tools/governance_gap_probe.py'); m=importlib.util.module_from_spec(s); sys.modules['gp']=m; s.loader.exec_module(m); print([f.__name__ for f in m.CHECKS])"
.venv\Scripts\python.exe tools\provenance_loop.py

# 对象实数：义务门禁（只报告步骤）
.venv\Scripts\python.exe tools\obligations_gate.py --ledger .tmp/obligations/repo.jsonl --json

# 预算对账（口径 = 新增行）
.venv\Scripts\python.exe -c "import subprocess,collections; out=subprocess.run(['git','diff','--numstat','f4a46a6..HEAD'],capture_output=True,text=True).stdout; b=collections.Counter(); [b.update({('src' if p.startswith('src/') else 'tests' if p.startswith('tests/') else 'tools' if p.startswith('tools/') else 'data' if p.startswith(('adapters/','validation/','registry/')) else 'docs' if p.startswith('docs/') else 'other'): int(a)}) for a,d,p in (l.split(chr(9)) for l in out.strip().splitlines())]; print(dict(b))"
```

---

**本文件是本轮的第 6 个提交**（前五个：23 号 §15 的裁定登记、第 0.5 条稳定性小修、
裁定④ 的默认值改正、covers 数据、声明读数用例）；索引见同目录 `README.md`。
