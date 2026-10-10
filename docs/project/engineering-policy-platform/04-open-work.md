# 04 · 未完成工作与复审清单

> **这份文件是什么**：仍然会影响未来开发的未完成事项、已知边界与复审时间的**唯一去处**。
> Phase 0–9 的按阶段实施记录、按轮次的复核与修复轮记录已于 2026-10-06 一并下线；
> 这里只保留"还没做完、还没核实、到期要复看"的东西，不追溯过程。
>
> **每行五列**：事项 / 现状 / 证据（可执行命令、CI 步骤名或行为描述）/ 下一步 / 复审或到期。
> **读法**（三条都会改变结论）：
>
> 1. 只报告 ≠ 已接线：四条只报告步骤的非零退出**不计入**本机门禁失败；
> 2. 不适用 ≠ 0 命中：账本文件不存在时既不是"没有义务"，**也不算一次真实读数**；
> 3. `unavailable` ≠ 0：读数读不出来是显式状态，不许当成"没问题"。
>
> **权威来源**：所有数字都由工具现场产出（命令写在"证据"列），本文只登记入口、判据与到期日。
> 版本轴各自独立演进、**不跟随平台阶段**（AGENTS.md 第 55 条）。
> 设计提案的状态表在 [designs/README.md](designs/README.md)；架构口径见 `docs/project/architecture/`。

## 0 复审日历（先看这张）

| 时间 | 事项 | 动作 |
| --- | --- | --- |
| **2026-12-31** | 四条只报告步骤（义务门禁 / 豁免到期 / 仪器自证 / 控制面事实表）+ 覆盖账红条件 + 端到端 `host.sandbox` 读数的**统一升格复审** | 决定：升格 / 继续只报告 / 改形态；结论必须落进已跟踪文档 |
| **2026-12-31** | 义务门禁的**结构问题**：仓库门禁里永远没有账本 → L5 试用期升格判据（"跑过 N≥1 次且 0 命中，且 0 命中来自至少一次真实读数"）在现有配置下**跑不满** | 决定：找真实实例（让门禁真读到一次账本与一次真实 pytest 运行）**还是撤销**这一步 |
| 到期前 14 天（自动） | `tools/exemption_expiry.py` 报 `DUE`；过期报 `RED`；**退出码恒 0** | 读数本身不阻断；到 `DUE` 就要安排复审 |
| 未指定 | Phase 6 第二真实 Agent 产品验证、Phase 8 真实 `ChangeAuthor` 模型实现 | 需要仓库外的产品/模型环境，见 §9 |

**豁免到期**读数（2026-10-06 本机直跑 `tools/exemption_expiry.py`）：`HITS: 0 / declared=9 due=0 expired=0 unprovable=0`——
这是四条只报告步骤里**第一条**的读数（四条各自的读数见 §1.1，互不相加）；
九条豁免的到期日**全部**是 `2026-12-31`（还有 86 天）。

## 1 Phase 9 控制面：只报告已落地，**升格一项未做**

### 1.1 已交付的部分（只报告）

| 台阶 | 已落地（只报告） | 门禁落点 | 复现命令 |
| --- | --- | --- | --- |
| −2 会话隔离 | 每会话一棵工作树 + 仓库内排他锁（`.tmp/ci-local.lock`）；抢不到锁**直接退 1** 并报出持锁者 pid，不等待、无绕过开关；`tools/cleanup.py` 认同一把锁并跳过锁文件 | 门禁自身的**前置**（不是一步；`--list` 不取锁） | `python tools/ci_local.py --list` |
| −1 基线冻结 | 30 臂矩阵 248 检查 0 偏差、11 fixture 逐字段全等，在有修订号的树上重采 | **未接**（只读仪器在 `.tmp/`，未入库） | 见 §8「仪器与环境的读法」 |
| 0 封条与针脚 | 四个名字一份实现（`evidence_tree_digest` / `referenced_inputs_digest` / `workspace_tree_digest` / `platform_revision`）、严格模式（读不到 = `unprovable`）；`provenance_loop.py` 5 个场景闭环 | **未接**：本机 `--full` 计划的 29 步里没有任何一步被要求交出判据级封条 | `.venv\Scripts\python.exe tools\provenance_loop.py` |
| 1 H4/H5 | pytest 退出码 **5**（没有收集到用例）不再记成"测试跑过了" | `Unit, contract, integration and security tests` | `python -m pytest tests\integration\test_validator_pipeline.py -q` |
| 2 归因闭集 | `origin` 五族闭集 + 核验前置；Python 与 JS 两端；真插件产出 → 真分类器的跨语言契约用例 | `dsh hook wiring self-check` + pytest 契约用例 | `python -m pytest tests\contract\test_policy_hook_chain.py -q` |
| 3a 受控 reason 与脱敏 | 受控 `decision_reason` + 归因路径脱敏（两语言同一口径） | `dsh hook wiring self-check` | `python -m adapters.dsh.hooks --self-check` |
| 3b pending 独立通道 | 「待实现」移出 `violations`，改 `pending_findings`（构造期强制 warning）；四种 decision 与改动前逐个相等 | 上述两个步骤 | `python -m pytest tests\unit -q -k pending` |
| 3c 义务账 | 只记账不判罚；键 `(rule_id, target, missing_target)` 不含 `session_id`；解除只由一次真实 pytest 运行判定 | **只报告步骤 1** `Obligations gate (report only)` | `.venv\Scripts\python.exe tools\obligations_gate.py --ledger .tmp/obligations/repo.jsonl` |
| 4 覆盖账 + `reading_context` | 三数分离（discovered/declared/measured，**整数、禁比例**）、六格差集、红条件；六类读数统一"属于哪棵树 / 哪个环境"的形状；豁免到期读数 | 本机门禁计划第 22 步 `Agent channel wiring inventory`（报告模式、恒退 0）+ **只报告步骤 2** | `.venv\Scripts\python.exe tools\exemption_expiry.py` |
| 4 仪器自证（R-h） | 对象表四族（门禁步骤 / 探针检查 / 封条场景 / 只报告步骤）+ 三态判据 + 反退化检查；**方案 A**：存量写 `gap_note`、不做变异 | **只报告步骤 3** `Instrument self-proof (report only)` | `.venv\Scripts\python.exe tools\instrument_self_proof.py` |
| 5 控制面事实表 × 跨源互证 | facts 表 13 行 + 连接键双向必查 + C1/C2/C3 三组读数 + 四格红条件 | **只报告步骤 4** `Control plane facts (report only)`；**workflow 里仍未接** | `.venv\Scripts\python.exe tools\control_plane_facts.py` |

本机实测（2026-10-06）：`CONTROL_PLANE_FACTS: fact_without_check=0 check_covers_unknown_fact=0
test_path_declaration=101 budget_inequality=0 / facts=13 checks=64` → `HITS: 101`，
**唯一非 0 的那一格是 C1**（见 §1.2 缺口 3）。

### 1.2 剩余缺口 8 条（**未实现**，不许读成已交付）

| # | 缺口 | 现状（可复核读数） | 处置 |
| --- | --- | --- | --- |
| 1 | **门禁接封条（R-e 完整版）** | 门禁执行路径里**没有任何一步**被要求交出判据级封条（`referenced_inputs_digest` 的 pre/post 比对 + 退出码 3）；机制只在 `tools/provenance_loop.py` 的 5 个场景里 → 台阶 0 只是**部分绿** | **不排期**；若做，形态约束：只能先以只报告形式、由 CI 线加、第一版不接退出码 3、先用声明输入 |
| 2 | **R-h 变异自证覆盖为 0** | `validation/instrument-checks.yaml` 的 `mutation_id` **全为 `null`**（方案 A 的存量写法：写 `gap_note`、不做变异）；三态里的"补丁打不上"因此没有真实对象 | 升格 R-h 之前必须先补（方案 B/C），另走一轮 |
| 3 | **C1：两份测试路径声明对 101 个文件判定不一致** | `tools/control_plane_facts.py` 读数：扫描 **204** 个文件、判定不一致 **101**（platform=False/adapter=True 101、反向 0）、层级不一致 **100**；两份声明仍是各写各的（平台 `validation/test-layout.yaml` 的 `test_patterns` vs `examples/dsh/dsh-adapter.yaml` 的 `test_paths`） | 合并谓词会**改变判定**（layer 是判据输入）→ 属 R-d 范畴，**单列为后续项目**、须另开一轮并交出字段级差集；**不许用写声明的方式把这 101 条消掉** |
| 4 | **orchestrator 的 `tool_name` 为 `unavailable`** | C2 关系读数：registry 的 4 条 orchestrator `tool_name` 在 `src` / `registry` / `adapters` / `tools` 下**没有任何读取点**（代码侧引用的是四个 `orc.*` id）→ 报告写 `unavailable`，不猜 | 保持 `unavailable`；要变 `available` 得先有一条可评审的判据 |
| 5 | **DSH 会话里 xdist 起不来** | 本会话 `workspace-write` 下 `pytest -n auto` 必然 `INTERNALERROR`；门禁读数靠 `PYTEST_XDIST_AUTO_NUM_WORKERS=0` **串行**跑（pytest 步 6–7 分钟，并行约 2 分钟）；**根因未核实** | 每次用它跑出的门禁读数**必须逐次声明**；根因另查 |
| 6 | **`~/.dsh` 与 `%TEMP%` 在 dsh 进程里不可写的原因未核实** | 门禁第 9 步：`result=skipped`、`host.sandbox=restricted`、`dsh_startup_denied_kind=profile_write_denied`、被拒路径 `C:\Users\ZNM\.dsh\profiles\headless\cordis.yml`；而 `--isolated-home` 的真机形态 `result=pass` | 只登记现象与归因路径，**没有根因**；不写成"沙箱就是这样" |
| 7 | **只报告读数的 2026-12-31 复审** | 四条只报告步骤 + 覆盖账红条件 + `host.sandbox`；四条步骤的 `expires_at` 现均为 2026-12-31（义务门禁那条原为 2026-10-31，已续期） | 统一到 **2026-12-31** 复审；到期前 14 天 `exemption_expiry` 报 `DUE`、过期报 `RED` |
| 8 | **义务门禁在仓库门禁里读不到账本（结构问题）** | 它读 `.tmp/obligations/repo.jsonl`，而仓库门禁里**永远没有账本**（`applicable: false` = 不适用，既不是 0 命中、也不算一次真实读数）→ 已归档的 20 次 `--full` 里**没有一次真实读数**；L5 升格判据在现有配置下**跑不满** | 2026-12-31 复审时决定：**找真实实例**还是**撤销**这一条步骤 |

**同批登记、不排期的两条**：① 覆盖账的 `declared_not_discovered = 1`（本机没有绑定到任何通道）与
`in_scope_not_wired = 3`（三条通道留痕 stale）都**不是**本阶段能判的，改动要走显式提交；
② R-e 的三个状态（`landed_unverified` / `landed_peer_verified` / `round_verified`）**没有任何一方签发过**。

### 1.3 未核实（照实登记，别读成"已核实"）

| # | 未核实的事 | 读法 / 下一步 |
| --- | --- | --- |
| 1 | **并发对照没有重跑**：排他锁"抢不到即退 1"只在代码与纪律里，本轮**没有造一次并发运行**来复现 | 需要时造一次双实例运行并把两行输出留档 |
| 2 | **门禁运行的完整次数**：登记在案的是已归档的运行；`--hook` 形态与未归档的运行无法从归档里数全 | 引用"跑过几次"时必须写清口径 |
| 3 | **GitHub Actions 上的读数**：C1/C3 依赖宿主与仓库内容（本机 C1 = 101）；**不要照抄本机数字** | 在 CI 上重跑并另记一份 |
| 4 | **远端状态**：本会话不 `fetch`；本机跟踪引用与远端此刻是否一致未核实 | 需要时先 `git fetch` 再引用 |
| 5 | **`--full` 门禁本轮没有跑**：只报告步骤 4 在门禁里的实际输出行**没有实测读数**，目前只有用例支撑 | 跑一次 `--full` 并贴 `REPORT-ONLY:` 行 |
| 6 | **`.tmp/e2e/` 的原件不是长期证据**：登记的是"存在过且被复核过"，`cleanup` 之后只能靠登记里的 sha256 复核 | 需要长期复核的读数先落已跟踪目录 |
| 7 | **本机沙箱的强制点实现**（minifilter / 令牌 / 其它）未定位：已定位的只是"解释器映像必须在会话工作区之外"这一环境约束 | 换树 / 换解释器时重新确认，不要当成 ACL 问题 |

### 1.4 边界（本阶段明确不做，改动前先读）

- **不改判定路径**：`policy.engine.evaluate` 的判定逐字节不变（R-d 差集 0 条是每轮验收项）。
- **不新增加载期 FATAL、不新增阻断步骤、不改任何退出码**（升格前）。
- **不合并谓词**：C1 的两份声明只读出 101 条不一致，不合成第三份（合并会改变判定）。
- **不把"没跑成"记成"通过"**：环境跳过（沙箱受限 / dsh 缺失 / 账本不存在）是显式状态，不是 0 命中。
- **在此之前**：本阶段的一切读数**只报告**，不得作为任何 allow / block 的输入。

## 2 义务账门禁（L5 试用期）

| 事项 | 现状 | 证据 | 下一步 | 复审/到期 |
| --- | --- | --- | --- | --- |
| 义务门禁只报告、未升格 | 2026-09-30 起作为 `ci_local.py` 的**只报告步骤 1**执行；非零退出只打印命中数、**不计入门禁失败**（L5 试用期：warn + 非零退出） | `.venv\Scripts\python.exe tools\obligations_gate.py --ledger .tmp/obligations/repo.jsonl` | 跑满升格判据后升格 | **2026-12-31**（豁免 `expires_at`） |
| 升格判据 | 「跑过 **N≥1** 次且 **0 命中**」，且 0 命中必须来自**至少一次真实读数**；升格那一轮必须先是 warn + 非零退出 | 见上；与 R-h / 控制面事实表**同型** | 每次门禁运行留读数 | 2026-12-31 |
| 结构问题（缺口 8） | 仓库门禁里**永远没有账本** → `applicable: false` = 不适用；**不适用凑不了"0 命中"** | 上面那条命令的实际输出："不适用：账本文件不存在：这次没有账本可读" | 复议：找真实实例 or 撤销 | 2026-12-31 |
| 门禁侧的三种形态必须读得出区别 | 账本**文件不存在** = 不适用（不算命中、不算真实读数）；账本**存在**却拿不出最近一次真实运行 = **按命中处理** | `tools/obligations_gate.py` 与 AGENTS.md 第 56 条 | 引用读数时写明是哪一种 | — |
| 义务的解除只认一次真实 pytest 运行 | "真实"是结构化三条事实：`tool.pytest` 状态 ∈ `{ok, findings}`、`failing_tests` 在 `served_checkers` 里、选中的测试非空；不解析 reasons 文本、不许由账本推断 | `src/policy/obligations.py`、`tools/obligations_gate.py` | 任何"义务已解除"的结论都要带这三条 | — |

## 3 怎么把新的只报告工具接进门禁（交接手册，AGENTS.md 第 55 条指向本节）

**适用场景**：你在 CI 线（`tools/ci_local.py` / `tests/unit/test_ci_local*.py` / `tools/phase_evidence.py` /
`.github/workflows/*`）要给某条"只报告、退出码恒 0"的读数加一步。**现有实例**：
`tools/instrument_self_proof.py`（R-h）与 `tools/control_plane_facts.py`（台阶 5）都是按这套做法接进
`REPORT_ONLY_STEPS` 的。

### 3.1 要做的事（三件，前两件必须**同一个提交**）

1. `tools/ci_local.py` 的 `REPORT_ONLY_STEPS` 末尾加一条，**六个字段都必填**（缺 `reason` 读不出
   "为什么允许它不阻断"，缺 `expires_at` 就是一张永不过期的空白支票）：

        ReportOnlyStep(
            name="<工具名> (report only)",
            args=("tools/<工具>.py",),          # 注意：**不带 --json**
            reason="<这条读数是什么、为什么只报告>",
            expires_at="<YYYY-MM-DD>",
            adopted="<YYYY-MM-DD>",
            reads="默认输出里的 HITS: 行（不带 --json；退出码恒为 0，命中数只能从这一行读）",
        )

2. **同一个提交里**给 `validation/instrument-checks.yaml` 加一行
   `check_id: "report-only:<第 1 件里那个 name>"`（`owner` / `command` / `covers` /
   `evidence_level: report` / `mutation_id: null` / `gap_note` / `severity: advisory`）。
   **两个方向都会红，而且都只报告**：

   - 加了步骤不加登记行 → R-h（仪器自证）报 `no_check_id = 1`；
   - 加了登记行不加步骤 → 报 `check_id_without_object = 1`。

   同批做掉，两个都不会出现。这一行也会让 R-h 的对象清单变大（对象表第 4 族 = `REPORT_ONLY_STEPS`）。

3. 用例（`tests/unit/test_ci_local*.py`）：一条"登记 + 读数"就够——断言这一步在 `REPORT_ONLY_STEPS` 里、
   `args` **不含** `--json`、`reason` / `expires_at` / `adopted` / `reads` 都非空，
   且 `report_only_reading()` 从**该工具的真实默认输出**里读出整数命中数（不是猜出来的 0）。
   跨侧读数契约由工具自己的用例用**真的 `ci_local` 读取器**钉住，CI 线不必重复造。

### 3.2 两条容易踩的硬约束

- **为什么必须不带 `--json`**：`ci_local.report_only_reading()` 在带 `--json` 时**只认载荷里的 `hits` 键**，
  而这类工具的载荷**没有 `hits`**（它不是账本）；不带 `--json` 时它读默认输出里的文本 `HITS:` 行
  （`HITS: <合计> / <逐项> / <对象计数>`，与 `exemption_expiry` **同族**）——读取器**一个字都不用改**。
  **读不出整数时**（表读不到 / 影子树建不出来）那一行写 `unavailable`：读取器照原文给出读数、不猜命中数
  （`count` 是 `None`，**不是 0**）。
- **改 `name` 就是改跨文件身份**：`tools/instrument_self_proof.py` 按 AST 读 `REPORT_ONLY_STEPS` 里的
  `name=` 字面量，并与登记表的 `report-only:<name>` 双向比对。改名要**同一个提交**同步登记表。

### 3.3 不需要做的事（写下来免得去找）

- **不需要**登记进 workflow 分组：只报告步骤不在 `.github/workflows/*.yml` 里，`unregistered_steps()` 看不到它。
- **不需要**给它接退出码：升格前 `enforced: false` / `would_exit_code: 1` 只是**预注册**。
- **不需要**动 `tools/phase_evidence.py`：阶段证据加指针（报告路径 + sha256）是**升格之后**的事；
  现在加会改证据载荷的键集合（第 55 条要升版）而消费方还不存在。
- **不需要**改 `tools/exemption_expiry.py`：它读 `REPORT_ONLY_STEPS`，加完这一步 `declared` 自动 +1。
- **不需要**碰门禁第 9 步（`Real dsh sandbox loop`）与任何封条语义——那是缺口 1，与本节**是两件事**。
- 若你加的是**新的 workflow 步骤**（不是只报告步骤），对象清单第 1 族会变多，**同样要同步登记表**，
  否则仪器自证报 `no_check_id`（只报告、不阻断）。

### 3.4 升格判据与验收办法

- **升格前提**（与 L5 同型）：跑过 **N≥1** 次且**四格合计 0 命中**，且 0 命中来自**至少一次真实读数**；
  升格那一轮必须先是 **warn + 非零退出**，最后由一次**显式提交**改判据 / 版本轴 / 门禁步骤表。
- **验收**：跑 `python tools/ci_local.py --full --python .venv/Scripts/python.exe`，退出码 0；把 `--timings`
  （或末尾耗时汇总）与属于这一步的 `REPORT-ONLY:` 行一起留档——**不要只贴退出码**。
- **联动读数**：加一条只报告步骤会让 `exemption_expiry` 的 `declared` +1、让 R-h 的对象清单与第 4 族 +1。
- **Windows 上若 pytest 步报 `INTERNALERROR`**：那是本机环境条件（缺口 5），绕法是加
  `PYTEST_XDIST_AUTO_NUM_WORKERS=0`（判据与步骤一个都不改，只是慢）；
  **用了它就必须在读数处逐次声明**。

### 3.5 交接清单上仍未关的口子

| 事项 | 现状 | 下一步 | 复审/到期 |
| --- | --- | --- | --- |
| R-h / 事实表要不要在 **GitHub Actions** 上也跑 | 当前**不要求**（只在本机门禁里）；工具不需要宿主，理论上 CI 上会读出同一份清单与同一张表，但**那是推断不是实测** | 要接就按 §3.1 的三件套做，并**同一提交**同步登记行 | 未指定 |
| 升格判据的**轮次登记方式** | 目前每次门禁运行不落"这是第几次"的结构化记录 | 评审后定一种登记方式，否则"N≥1 次"只能靠人记 | 未指定 |
| R-h 的**复核线分子/分母口径**、**变异体放哪** | 三态判据没有实跑过；`git apply --check` 在 Windows 换行下未实测；变异体是否落 `validation/mutations/` 未裁定 | 做缺口 2 时一并裁定并补实测 | 未指定 |
| `--hook`（pre-push）形态下这几步也跑 | 它们不是 `FULL_ONLY_STEPS`，`--hook` 与 `--full` 下都会执行；**没有实测跑过 `--hook` 形态** | 跑一次 `--hook` 并留读数 | 未指定 |
| 只报告工具在门禁里连跑会不会与别的步骤抢 `.tmp` | 事实表工具只读、不写台账；R-h 会建**自己的**影子索引 | 门禁首次真跑时观察 | 未指定 |
| **四条**只报告步骤在任何 CI workflow 里都不存在 | `REPORT_ONLY_STEPS` 只在本机门禁执行；`.github/workflows/*.yml` 里没有它们的 run 块（实测四条名字全部无命中） | 若要在 CI 上覆盖，按 §3.1 加并同步登记行 | 未指定 |

## 4 治理覆盖缺口 13 项（级别 + 复现命令）

来源：一次受治理会话与未治理通道的对照实验 + 28 条确定性探针 + 4 个审批用例。
**判据**（写死，不许事后放宽）：`FIXED` = 本轮声明范围内的行为断言全部成立；
`PARTIAL` = 只做了一半（判词里写清剩下的是什么）；`DEFERRED` = 计划内不做或需要仓库外条件，
**不得算进 FIXED**；`NOT FIXED` = 承诺要做却没做到（0 项）。

统一复现命令（`--only Gxx` 换成对应编号；`--phase before` 看修前预期）：

    python tools/governance_gap_probe.py --root . --phase after --only G01
    python tools/governance_gap_probe.py --root . --phase after --repeat 2 --json-out .tmp/probe.json

| 编号 | 缺口 | 级别 | 判定 | 现状 / 证据 | 复现命令 |
| --- | --- | --- | --- | --- | --- |
| G1 | Agent Teams 子会话与主会话通道没有装检查站 | **阻断** | **PARTIAL**（清点已建成；通道仍未接线，安装 DEFERRED） | `wiring` 报 `dsh:desktop / dsh:headless / dsh:web` 全部 `status=not_wired`、`wired=false`；缺口原话"同一条违规写入成功且零审计记录"**仍然成立**：仓库外的主机配置不在仓库范围 | `--only G01`；`$env:PYTHONPATH='src'; python -m adapters.cli wiring --check`（退出 1） |
| G2 | 只装了"动手前"，"动手后核对"从未执行 | **阻断** | **FIXED**（残余假设 DEFERRED） | 插件注册了 `tools/post-execute`、回调三参；真载荷喂给 Hook 后审计出现 `post_evidence`；Python 侧真改文件后判 `validated`。**残余**：真实 dsh 会话端到端未验证（需重启 GUI） | `--only G02` |
| G3 | 43 条规则里只有 1 条真正在查 | 重要 | **PARTIAL**（计划内不做） | 审计有 `effective_rule_count / skipped_rule_count`；controller 层 `effective=1 skipped=42`，module 层 `effective=0 skipped=43`。**拦截面没有变化，只有可见性变化**（把 Phase 5 流水线接进 pre 路径是架构变更，半截接线更危险） | `--only G03` |
| G4 | 命令类工具在 AI 会话里结构性不可用 | **阻断** | **FIXED**（仅限"审批不再因运行时编号失效"） | 模式化审批可用；同一命令换 `action_id` → `allow`（修前 `approval_invalid`）；换命令 / 主体 / 过期 / 次数上限全部被拒；**换新审批 + 同一 `action_id` → `action_replay`**。**不声明**"受治理会话现在能跑测试"：本机 `shutil.which("pwsh")` 为 `None`、`bash` 被 WSL 拒绝 | `--only G04` |
| G5 | 工作目录等于项目根被判"越界" | 重要 | **FIXED** | `workdir` = 绝对根 / `.` / `./` / 子目录 → 不再报参数错误（落到下一道闸 `permission_denied`）；越界与 `..` → `path_out_of_scope`；拿不到结构化 `reason_code` 时仍退回 `enforcement_param_error`（反向断言） | `--only G05` |
| G6 | 依赖规则只认字面写法，换写法就绕过 | 重要 | **FIXED** | 9 种写法（含 `importlib.import_module` / `__import__` / 相对导入 / 大小写变体）全部 `policy_block`；两条"不得误伤"对照仍 `allow` | `--only G06` |
| G7 | 规则生不生效取决于文件名 | 重要 | **FIXED** | 审计出现 `layer_defaulted` / `layer_matched_pattern`；命中通配符与走默认层在账本上第一次可读；反向对照（回退那份文件 → 探针变红）在第 2、3 轮各验一次 | `--only G07` |
| G8 | `**/` 通配符匹配不到根目录文件 | 次要 | **FIXED** | `glob_match("**/*.md","README.md")=true`、`("**/*.py","cli.py")=true`；误伤对照 `a.pyc` / `a.md.bak` / `other/src/a.py` 仍 false | `--only G08` |
| G9 | "跑代码"工具没有第二道闸 | 重要 | **FIXED** | 注册表 `exec.run_code` 新增 `code_check` 声明；带合法审批的危险代码 → `block / code_blocked`（修前 `allow`） | `--only G09` |
| G10 | 工具白名单跟不上工具升级 | 重要 | **FIXED** | `TOOL_TABLE` 与 `adapters/dsh/manifest.yaml` 逐项一致（两个差集都为空）；本会话工具清单差集为空；`python -m adapters.cli events` 退出 0（已审核哈希不漂移） | `--only G10` |
| G11 | 只管结构化事实，管不了进到 AI 眼睛里的内容 | 次要 | **PARTIAL**（留痕已做；注入内容的策略校验 DEFERRED） | 审计出现 `context_injection`（来源 + 哈希）、`injection_trace_present=true`；但"进到 AI 眼睛里的内容"**仍然不做策略校验**（需要对注入链路的所有权） | `--only G11` |
| G12 | "故障即拦住"的兜底只在自建插件里 | 次要 | **PARTIAL**（CLI 失败关闭；**库内默认仍放行**，已知遗留 N5） | CLI：`--self-check` 不带 `--hooks-config` → `exit=2`（修前 0）；hooks.json 损坏 / 配置缺失 / stdin 损坏 → 全部 2。但 `hooks.run_hook(hooks_config_path=None)` 不传 `allow_unverified_wiring` 时实测放行 | `--only G12` |
| G13 | 没人能自动发现"哪个通道没接线" | **阻断** | **FIXED** | `wiring --check` 指名道姓报出 3 条 `not_wired` 通道并退出 1；`--dsh-home` 指向空目录 / 损坏 / 不存在三种情况全部 `result=fail`、`exit=1`；`skipped` 必须带 `skip_reason`、绝不等于 `ok` | `--only G13` |

**缺口本身的判定**：FIXED 9（G2/G4/G5/G6/G7/G8/G9/G10/G13）· PARTIAL 4（G1/G3/G11/G12）· NOT FIXED 0。
**三处 DEFERRED**（需仓库外条件）：G2 的真实会话端到端、G1 的"真正装上去"、G11 的注入内容校验。

仍需处理的三条（其余已关闭，不必再查）：

| 事项 | 现状 | 下一步 | 复审/到期 |
| --- | --- | --- | --- |
| **G1 把策略桥挂到本机 desktop / headless / web profile** | 三条通道实测 `not_wired`；装上需**重启界面**；`spawn_teammate` 拉起的子会话其写类动作**不经过父会话的 PreToolUse** | 由使用者决定是否安装；装完在通道清点里复核 `dsh:desktop` | 未指定（仓库外主机配置） |
| **G3 把 Phase 5 流水线接进 pre 路径** | 42 条规则只是"可见地被跳过"；半截接线更危险 | 属架构变更，须另开阶段并交出字段级差集 | 未指定 |
| **G12 库内默认值 N5** | `allow_unverified_wiring=True` 让"库调用 + 不传 wiring 校验"仍放行；改默认值会波及几十个与被测行为无关的调用点 | **产品决策**：是否改成"必须显式传 `True` 才放行" | 未指定 |

## 5 仍未修 / 未核实 / 待裁定的工程项

按"会不会挡住未来开发"排序。**证据列是可复核的入口**，不是原文摘录。

| # | 事项 | 现状 | 证据 | 下一步 | 复审/到期 |
| --- | --- | --- | --- | --- | --- |
| 5.1 | **`tools/governance_gap_probe.py` 硬编码本机绝对路径** | `DSH_IMPL_ASAR` 写死 `C:/Users/ZNM/.../app.asar`；换机器即失效（有显式降级：文件不存在时返回空事实并记 `dsh_impl_asar_exists=false`，但**该事实只落在 facts 里、报告里容易被读成检查通过**） | `Select-String -Path tools/governance_gap_probe.py -Pattern 'C:/Users'` → 769 行 | 改成环境变量或从 `shutil.which("dsh")` 反推；把"实现包不存在"提升为**报告可见**状态 | 未指定 |
| 5.2 | **R-g（`origin` 归因）没有接进 `ci_local.py` 任何一步** | 台阶 2 明确声明"R-g 目前只由用例守住"；本机 `--full` 计划的 29 步里没有"origin 里不许有绝对路径"这类检查 | `Select-String -Path tools/ci_local.py -Pattern 'origin'` → 只有 git 的 `origin/main` | 接成门禁步骤（只报告起步），否则同类缺陷只在测试被改坏时暴露 | 未指定 |
| 5.3 | **空选择分支把 `failing_tests` 记成"服务过"** | pytest 选择结果为空时提前返回、不写 `served=`（默认空元组）→ 流水线回退到 `spec.checkers`，于是**没有任何测试执行**也把 `failing_tests` 记进 `served_checkers`（违反"没查成的不能记成查过了"） | `src/validators/adapters/pytest_runner.py:177-183`、`src/validators/pipeline.py:536`（`checkers = output.served or spec.checkers`） | 收窄为显式状态（`not_evaluated` / `no_subject`），或显式写 `served=()` 并加用例 | 未指定 |
| 5.4 | **`probe_matrix.py` 的 `exit 1` 二义 + 一处崩溃未修** | 正常路径 1 = "有检查不一致"，**未捕获异常也让 Python 退 1**，且证据 JSON 只在全部臂跑完之后才写（变异 A：exit 1、零证据）；`Decision.ALLOW` 那次崩溃的根因已定位（`worst` 为 `None` 时仍在拼文案）但**没有修** | `probe_matrix.py:1646`（`.tmp/` 下，未入库） | 区分"仪器崩了"与"偏差非 0"，并让证据在崩溃时也落盘；修 `None` 处理 | 未指定 |
| 5.5 | **矩阵里一条检查的观察值永不稳定** | `block-composite-command` 的 stderr 里带 `approval-<12hex>`（`uuid4()`）；`op=contains` 让它照样绿，但"248 条逐字节全等"这类更强说法**不成立** | `src/enforcement/cli.py:637` | 引用时只写"除 run-scoped 文本外逐条一致"，或把该字段从观察值里剔除 | 未指定 |
| 5.6 | **"读数属于哪棵树"没有机制化** | 矩阵的 `environment` 只记解释器 / 路径，**没有源码修订哈希**；矩阵与 11 条 fixture 的旧读数属于一棵无修订号的树 | `tools\provenance_loop.py`（封条机制只覆盖 5 个场景）、缺口 1 | 把"读数必须钉 pre_tree → post_tree 摘要"做成机制（门禁接封条） | 未指定 |
| 5.7 | **B4：API 侧缺"pending 计数"键**（登记待裁） | 给 API 载荷加键要递增 `API_SCHEMA_VERSION` 1.0→1.1、给请求日志加键要动 `REQUEST_LOG_SCHEMA_VERSION`；**连带清单**（`tools/api_loop.py` 的版本字面量、契约快照、生成物）不在既有授权范围 | `src/policy_api/models.py`、`src/policy_api/observability.py` 的版本常量 | 请评审裁定：授权这两处升版，或把第 55 条明确为"只覆盖写侧载荷、读侧附加键不算" | 未指定 |
| 5.8 | **经 API 的 pending 正例无覆盖** | `/v1/policy/evaluate` 结构上不可能产生 pending；`/v1/validation/evaluate` 能，但需要一份"选中的测试 import 项目内不存在的模块"的 API 夹具；请求级 JSONL 也没有 `allow_with_warnings` 且 `violations=0` 的日志行用例 | `tests/api_support.py` 的项目是固定形状的 | 建一份能产生 pending 的 API 夹具并补正例 | 未指定 |
| 5.9 | **符号链接安全用例在 Windows 本机长期 skip** | 本机 `1109 passed, 1 skipped`（另一处计数 1098/1）；跳过项正是"符号链接逃逸"这条安全用例——**本机绿不代表它被覆盖**，只有 Linux CI 真跑该分支 | `python -m pytest tests/security -q` | 以 Linux CI 的实际执行结果记一次"已验证"，否则保持"未核实" | 未指定 |
| 5.10 | **`src/policy/__init__.py` 缺（唯一的隐式命名空间包）** | 复核时"只记名未改"；`src/adapters`、`src/retrieval`、`src/enforcement` 都有 | `glob src/policy/__init__.py` → 空 | 补文件，或**明确写下**"永久保留隐式命名空间包"的决定与理由 | 未指定 |
| 5.11 | **`registry/tool-registry.yaml` 里驱动层从不读取的参数** | `exec.pwsh` 声明了 `workdir` / `timeoutMs` / `run_in_background`，而驱动只读 `spec.timeout_ms`——**声明了却不执行** | `registry/tool-registry.yaml:160/165/169`；`Select-String -Path src/enforcement/drivers.py -Pattern 'workdir|timeoutMs|run_in_background'` | 二选一：让驱动真的读并按声明校验，或从注册表删掉；**改注册表必须重新审核**（`python -m enforcement.cli registry --approve --reviewer <name>`） | 未指定 |
| 5.12 | **只读工具的 `path_scope` 仍是"只声明、不执行"** | 只读工具现在会归一化并校验路径落在受控项目内（越界失败关闭），但校验写在 **Adapter** 里；注册表的 `path_scope: workspace` 对只读工具没有执行点——两处表达同一规则、改一处不会自动改另一处 | `src/adapters/dsh/adapter.py:1148`、`src/enforcement/models.py:613` | 决定是否让 Hook 读注册表驱动这条校验（改前写清代价），或**固化为显式设计决定** | 未指定 |
| 5.13 | **`tests/e2e/` 与 `tests/fixtures/adversarial/` 一直不存在** | 测试策略文档早已列出（DORA 因果链第 6 项），仓库里没有 | `glob tests/e2e/*` → 空；`glob tests/fixtures/adversarial/*` → 空 | 先定义运行入口（命令、退出码、是否进门禁），再建目录与最小用例 | 未指定 |
| 5.14 | **`type_check` / mypy 未启用；`F811`/`F841` 无规则归属** | `policies/` 里 `type_check` 0 命中（是"没启用"，不是"通过了"）；一旦有规则声明它，critical 会失败关闭。`F811`/`F841` 在 `validation/ruff.toml` 的 `select` 里但没有规则，只进 `unmapped_findings` 计数 | `python -m validators.cli probe --json` → `tool.mypy ... unavailable`；`python -m pytest tests/contract/test_validator_protocol.py -q` | 装好 mypy（锁定版本区间）后先 `probe` 确认可用再启用；两个 Ruff 码要么归一条规则、要么写明是"只计数"的已知空档 | 未指定 |
| 5.15 | **`pre_evidence`（动手前取证）可声明、默认未启用** | 声明并启用后证据类 checker 才真正参与判定；仓库示例里那一段仍是注释 | `examples/dsh/dsh-adapter.yaml` 的 `pre_evidence` 段（注释）；`validation/control-plane-facts.yaml` 记为"没有声明" | 要么在示例里真正打开（须满足 `pre_evidence.timeout_ms + timeout_ms < hooks.json 的 timeout`）并补跨侧用例，要么把"默认未启用"写成显式状态 | 未指定 |
| 5.16 | **`hook_could_not_spawn()` 仍解析 Agent 自然语言日志** | 措辞一变判据就漂；可靠判据应是"Hook 启动见证文件"。第 53 条已把"归因合取必须在同一条记录内"定成纪律，但**结构化见证尚未落地** | `tools/dsh_sandbox_loop.py` 的分类器 + `tests/contract/test_policy_hook_chain.py` 跨侧用例 | 改为读结构化见证文件；改措辞必须同步两侧 | 未指定 |
| 5.17 | **`--require-dsh` 没有负向用例；`wiring --check` 的退出码取决于本机有几条通道** | 没有"要求 dsh 但 dsh 不在时必须非 0 退出且不写成暂通过"的用例；`wiring --check` 只要有一条通道未接线就退出 1（"对照臂故意未接线"与"该接线却没接"在退出码上分不开） | `python tools/dsh_sandbox_loop.py --require-dsh`；`$env:PYTHONPATH='src'; python -m adapters.cli wiring --check` | 补负向用例；给 `wiring --check` 加"期望接线通道"的显式入参 | 未指定 |
| 5.18 | **阶段证据顶层 `result` 可以是 `pass`，而真实闭环 `skipped`；`block_passed` / `allow_passed` 不是三态** | 顶层 pass 不覆盖外部产品闭环；`false` 既表示"跑了没通过"也表示"根本没跑起来" | `python tools/phase_evidence.py` → `.tmp/artifacts/phase-8-evidence.json` | 要么把 skipped 提升为顶层三态之一，要么显式标注"顶层 pass 不覆盖外部闭环"；改形状要动 `SANDBOX_RESULT_SCHEMA_VERSION` | 未指定 |
| 5.19 | **`adapter.yaml` 阈值不在已审核哈希范围内；不支持 per-adapter 阈值** | 改熔断阈值不会被动到 `adapters/approved.json` 的审核拦下（只有 manifest 在范围内）；一个 `AgentRuntime` 只有一组全局阈值 | `python -m adapters.cli approve --reviewer <name>`；`src/adapters/runtime.py::_resolve_thresholds` | 把 adapter 配置纳入审核哈希，或写明"阈值属运行时配置、不进审核"；per-adapter 阈值等有需求再引入（要动 `AGENT_RUNTIME_SCHEMA_VERSION`） | 未指定 |
| 5.20 | **`bash` 的事后链未实测；`bash` / `run_code` 未装配进受治理会话** | pwsh 的 `post_repair_required` 有实测；bash 按代码推断同病但没有跑通 pre；会话的工具清单里没有 bash / run_code（`run_code` 跑 pytest 与它自己的 `code_check` 禁止面结构性冲突） | `python -m enforcement.cli registry --show exec.bash`；会话侧工具清单来自 profile 装配 | 补 bash 实测；要真能用需改 profile 装配 + 审批协议（见 5.21） | 未指定 |
| 5.21 | **一个 `approval.json` 只授权一个执行类工具；`binding=action` 在会话里"永远过不去"** | 给 `exec.pwsh` 签的条子对 `exec.bash` / `exec.run_code` 一律 `approval_invalid`；`action` 档绑运行时生成的编号，模型每次重试都换号 → 会话里实际只有 `binding=pattern` 可用 | `python -m enforcement.cli approve --binding pattern --param-pattern "command=^python -m pytest( .*)?$" --param-pattern "description=.*" --max-uses N`（1.1 起**模式必须覆盖本次请求的全部参数**：只声明 `command` 的条子对带 `workdir` / `timeoutMs` / `run_in_background` 的调用一律 `approval_invalid`——见 `src/enforcement/approvals.py` 的 `_check_shape` 与 `APPROVAL_SCHEMA_VERSION`） | 属 Phase 4 审批协议改动（多记录支持 / 按工具分文件）；在此之前引用 `action` 档必须写明它在会话里等于永远过不去 | 未指定 |
| 5.22 | **事后验证没有负例** | `post_validated` 有多次、链上有 `post_evidence`，但**没有一次"事后发现不一致"的负例**，无法证明它对坏改动会报 `repair_required`；非 0 退出 → `repair_required` 这条分支在真实会话里一次都没出现 | 受治理会话的审计 JSONL（`.tmp/` 下的运行产物） | 补一条"写坏了"的真实会话或探针，观察 `post_check_failed` / `repair_required` | 未指定 |
| 5.23 | **`pre_evidence` 的 45 秒预算只测到"没超"；`pre_evidence` 超时/超预算注入没有用例** | 最慢一次 1853 ms（用掉 4%）；超预算时的失败关闭只有声明与单元测试，真实会话没有触发 | 受治理会话的耗时读数与用例 | 在真实会话或探针里触发一次超预算，确认失败关闭形态 | 未指定 |
| 5.24 | **Q4：`check_volume` 在 Hook 路径根本没有这个键** | 读出来是 `None`，与"值为 null"长得一样——"这次查得全不全"在 Hook 路径上**没有答案** | 扫受治理解判记录可见 0 命中 | 要么在 Hook 路径补上（`rule.scope` 与 context 直接可算），要么写明它只属于 CLI | 未指定 |
| 5.25 | **Q2：被 blocker 划掉的 checker 与"没参与"的 checker 分不开** | 一次判定的 `served_checkers` 里没有 `failing_tests` / `missing_tests`，而违规正来自它们——按 `SUCCESS_STATUSES` 重算是正确行为，但读的人会误判 | 审计的 `served_checkers` 与 `violations` 分居两个字段 | 把"被划掉的 checker"单列（如 `blocked_checkers`），或改名 | 未指定 |
| 5.26 | **Q5：`wiring --check` 的退出码取决于本机通道数** | 只要有一条通道未接线就退出 1；做对照臂时故意留的未接线 profile 会让门禁必然红 | `python -m adapters.cli wiring --dsh-home <dir> --check` | 把"未接线通道是否属于本次承诺范围"变成显式入参（如 `--expect-wired`） | 未指定 |
| 5.27 | **`e:` 语料扩充把权威来源挤出前排，排序加权未做** | 掉名次已作为可查证据记进基线与 CLI 输出（如 `reference@12`）；当时明确"不偷偷调参" | `python tools/retrieval_eval.py --method both` | 做一次显式的排序 / 加权实验（如按 tier / 来源分层加权），用同一份评测集复评并 `--record` 重记基线、递增评测集版本 | 未指定 |
| 5.28 | **向量检索未采纳，`vector_min_similarity` 是实测分布常数** | 同一评测集上向量 support@5 0.857 < 1.00、precision 0.657 < 0.829；默认下限 0.25 来自本机实测（无意义查询上限 ≈0.21、真实查询从 0.29 起） | `python tools/retrieval_eval.py --method both` | 换 embedding 时用同一份评测集复评，并**重测该下限**；采纳前必须同时过安全用例与来源完整性 | 未指定 |
| 5.29 | **`workflow` / `str_replace_editor` 两个工具的线协议参数未核实、未登记** | 两者没有写进注册表；被调用即 `tool_not_registered`（失败关闭）。这是"未核实"，不是"已判定为不需要" | `python -m enforcement.cli registry --show <tool>` | 升级 dsh 后先核对参数表，再登记并 `--approve` 重新审核 | 未指定 |
| 5.30 | **`check_arch_style` 的既有红无人处置，也没有门禁拦它** | 登记为既有红（应退出 1、共 1 处） | `.venv\Scripts\python.exe tools\check_arch_style.py` | **已修（选「修掉」）**：`使用说明.md` §7 的概括句拆短，实测退出 0；这条检查**仍未接进 ci_local**（是否接进门禁单开一次，注意它只看散文、判据是阈值） | 未指定 |
| 5.31 | **`$DSH_HOME/profiles` 下留有 8 个实验 profile** | `governed` 是交付物，`governed-grade` / `verify-*` 等是实验产物；它们会出现在通道清点里并造成 FAIL 行 | 清点命令：`python -m adapters.cli wiring --check`；目录：`$DSH_HOME\profiles` | 清理实验 profile、只留 `governed`；清理后重跑清点 | 未指定 |
| 5.32 | **`.tmp` 里的原件不是长期证据** | 多条结论的原始产物（矩阵重跑材料、探针输出、端到端读数）只在 `.tmp/` 下；`tools/cleanup.py` 之后不可复核（`.tmp` 在 `.gitignore` 里） | `python tools/cleanup.py --dry-run` | 需要长期复核的读数在清理前重采并落已跟踪目录；否则接受"不可复核"并写明 | 未指定 |
| 5.33 | **一次性仪器的载体随本轮清理消失** | 30 臂矩阵、封条探针等仪器带硬编码路径、按既定口径**不进 `tools/`**；它们的判定摘要此前只写在被删掉的记录里 | 见 §5.4 / §5.5 / §5.6 | 复现命令与判据摘要已收进本节；**未入库的方法**要重跑就得重写仪器（接受或重建） | 未指定 |
| 5.34 | **N2：Phase 2 的 `load_config` 与 Phase 6 的 `adapter.yaml` 字段口径没有合并** | 两份配置各服务一条路径；Phase 2 的加载器仍按未知字段拒绝 Phase 6 声明的 `schema_version` / `ledger_alias` / `max_events_per_window` / `window_seconds`——仓库自己的 Phase 6 配置因此没法带测试层声明 | `adapters/dsh/adapter.yaml` 与 Phase 2 加载器的字段白名单 | 单开一轮做显式设计（统一字段集合，或明确两套配置各自的 schema）；**合并会改契约与已审核哈希**，改完必须 `python -m adapters.cli approve --reviewer <name>` | 未指定 |
| 5.35 | **`exit_code_zero` 把"证据充分"与"命令成功"合成一条判定（N27 残留）** | 两种后果：①"非 0 退出但证据完整"无法表达成独立状态；②**受治理会话里后台命令（`run_in_background`）必然 `repair_required`**——后台句柄没有退出码，"拿不到证据就失败关闭"是对的，但后台命令实际不可用 | `registry/tool-registry.yaml` 给 `exec.pwsh` / `exec.bash` 声明的 `post_checks: [exit_code_zero]`；后台用例读数 | 单开一轮改注册表词汇表（例如新增"只要求证据"的事后核对），并重新审核；同时给后台任务一条显式的"未结算"通道，或在注册表里声明它不被 `exit_code_zero` 覆盖 | 未指定 |
| 5.36 | **`ruff check` 不在 CI 的任何步骤里；`tools/` 与 `docs/` 的既有违规不受门禁约束** | `ruff check --config validation/ruff.toml tools` 有大量命中（一条历史读数：tools 483 条、其中手写脚本 57 条未清；`docs/**/*.py` 另有整桶）；ruff 只作为 `tool.ruff` 验证器作用于被声明的目标文件 | `ruff check --config validation/ruff.toml tools`；`python tools/ci_local.py --list` | 要么显式接受"可见但不受门禁约束"，要么单开一轮接进门禁并清零（注意：ruff 配置文件哈希会进验证器证据） | 未指定 |
| 5.37 | **覆盖率工具缺失** | `coverage` / `pytest-cov` 都没安装，没有分支覆盖率读数；当时的替代是"变异能否被测试杀死"（更强，但没有覆盖率数字） | `python -c "import coverage"`（ModuleNotFoundError） | 需要覆盖率读数就把 coverage / pytest-cov 加进 dev 依赖；不需要就写明"以变异替代覆盖率" | 未指定 |
| 5.38 | **审核动作不是独立复核（单人仓库的结构性限制）** | `adapters/approved.json` / `registry/tool-registry.approved.json` 的 `reviewed_by` 是写手本人；哈希确实重算过，但"重新审核"这一步没有第三方；`host-version --record` 的记录也**不能自证**是在哪台机器上写的 | `python -m adapters.cli approve --reviewer <name>`；`python -m enforcement.cli registry --approve --reviewer <name>`；`adapters/host-versions.observed.json` | 记在案、不假装解决：有第二个人时重跑审核命令；记录 diff 必须送评审 | 未指定 |
| 5.39 | **台账与证据的口径缺口（P6 的后续）** | ①台账存参数原文与绝对 `workspace` 是**刻意行为**，但**没有做过威胁建模**；②`violations` 条数没有上限；③证据子对象没有 `column` | `.tmp/` 下真实台账的复算读数；`src/policy/evidence.py` | 威胁建模单开一次（不要在别的改动里顺手做）；条数上限是新增口径；补 `column` 属核心模型 + 决策协议快照变更（要显式升版并更新快照） | 未指定 |
| 5.40 | **「待实现」的判据写在代码里、`missing_targets` 未结构化、只覆盖 pytest** | 判据没有数据化（对比 `analysis_failure_codes` 是数据）；`missing_targets` 是字符串 `模块名` / `模块名:名字`，结构化要再升 `EVIDENCE_SCHEMA_VERSION` / `PIPELINE_SCHEMA_VERSION` 1.2→1.3；Ruff / mypy 的同类形态（"工具跑成了、报告的是树还在构建中"）没有定义 | `python -m pytest tests/unit -q -k pending`；`src/validators/pipeline.py` | 有真实消费者时再做结构化并显式升版；逐工具定义同类形态并补用例 | 未指定 |
| 5.41 | **并发不是只有"同一条门禁流程"这一种** | `ci-local.lock` 只对同一条 CI 流程串行；**另一个会话改同一棵树**会让门禁的文本规范步骤变红（实测：另一个会话改 `designs/README.md` 后复跑仍红，补行尾换行才绿）。多 worktree 并发同样不在锁的保护范围内 | `python tools/ci_local.py --full --timings`（红在文本规范步骤） | 需要多人 / 多会话并发时设计门禁仲裁；在此之前，改动期不要与另一个会话共用同一棵树 | 未指定 |
| 5.42 | **`zstandard` 不在 `requirements.lock`** | 本机系统解释器有；CI 上没有 → 通道清点里的"工具漂移"观察在 CI 上退化为**显式不可用**（不阻断，因为漂移只报告） | `python -m adapters.cli wiring --json` 的 tools 段；`requirements.lock` | 要让 CI 也观察漂移，就把 `zstandard` 加进依赖或换一个观察源 | 未指定 |
| 5.43 | **三处协议口径待评审裁定** | ①判定行是否要为 warnings 新增键并升 `VERDICT_SCHEMA_VERSION` 1.0→1.1（本轮判"不升"，附三组 0 差集读数；若要升，Python 与 JS 必须同批改并重跑"版本不认识"用例）；②`check_volume` 新增 `obligations_open` / `obligations_note` 两键**没有递增任何版本号**（理由：CLI 包装不是协议载荷）；③`policy.check --obligations` **没有默认账本位置**，只由调用方显式给出 | `tests/contract/test_policy_hook_chain.py`（判定行 4 键断言）；`tests/integration/test_cli.py`（键存在性断言）；`src/policy/check.py` | 按 AGENTS.md 第 55 条逐条裁定：要么建轴升版并同批改断言，要么把"读侧附加键不算协议变更"写成明确规则 | 未指定 |
| 5.44 | **`tools/ast_unchanged.py` 不存在（登记为候选、裁决不做）** | "这次重构只换行没改语义"每次都要现写脚本；全仓 `ast.dump` 零命中。若立项，默认 baseline 只能是 git 或显式 `--before`，**不得指向会被 `cleanup.py` 删掉的快照** | `glob tools/ast_unchanged.py` → 空 | 真要用时按当时接口现写（约 80 行）；不要为它单独排期 | 未指定 |
| 5.45 | **两处"理由自证"的边角未收** | ①插件侧相对路径 `projectDir` 的解析基准仍可能与 shell 不一致（下一次插件侧改动时统一）；②payload 的 `JSON.stringify` 在 `try` 之外（循环引用 / BigInt → 插件抛错而非 deny；当前 dsh 更早就会拒绝这类参数，属理论路径） | `src/adapters/dsh/policy-hook.plugin.mjs` | 下一次插件侧改动顺手收，并补用例；不要把这两条当成会放行的漏洞 | 未指定 |
| 5.46 | **P3 的批次语义没做**（"同一批次里已经提议过的文件"进不进取证树） | Hook 每次调用只见一个文件，批次状态要跨进程持久化；现在只写清"这棵树是什么"（`tree.scope` / `tree_digest` / `tree_gaps`），后果是"先写测试"会被自己的取证打成 warning | `src/adapters/dsh/pre_evidence.py`；`examples/dsh/dsh-adapter.yaml` 的 `pre_evidence` | 单开一次显式设计（批次在 Hook 路径上的表示）；不在既有承诺里 | 未指定 |
| 5.47 | **没声明 `test_paths` 的配置仍会静默误判测试文件** | 分层自证只在**声明了** `test_paths` / `test_layer` 的配置上生效；不声明的项目里测试文件仍可能被生产层规则罩住（M1 的原始形态） | `python -m pytest tests/unit/test_dsh_layer_guard.py tests/contract/test_dsh_layer_declaration.py -q` | 若要强制，需把"哪些路径算测试"变成平台级强制声明（与"不猜不推断"冲突，须显式裁决） | 未指定 |
| 5.48 | **动手前取证没有端到端压过 `tool.pytest`** | `pre_evidence` 那条路只压过内置验证器与 `tool.ruff`；"在影子副本上真跑 pytest（missing_tests / failing_tests）"的端到端证据缺 | `src/adapters/dsh/pre_evidence.py`；`tests/integration/test_validator_pipeline.py` | 补一条在影子副本上跑 `tool.pytest` 的动手前取证端到端用例 | 未指定 |
| 5.49 | **N19 判定仪器对"允许"的情形报 `unproven`，待裁定** | 它按 `hook_event == PreToolUse` 取候选，而 Phase 4 放行时不带 `decision` 字段（`reason_code=enforcement_allow` / `allow_delegated`）；方向保守，但"这次动作被允许了吗"这根轴答错 | `python -m enforcement.cli verdict --audit <audit.jsonl> --tool pwsh --json` | 若要让这根轴也回答"允许"，需把 Phase 4 的允许语义纳入判据；同时写明它的**问题域不含事后阻断** | 未指定 |
| 5.50 | **已知且被钉住的路径不等价：预执行路径判不了"顶层包存在但模块不存在"** | 预执行只看变更片段、不读磁盘，没有模块索引；该形态只有 AST 路径能判。已写成 `KNOWN_DIVERGENCES` 断言（已知差异而非静默差异），且写后 Phase 5 仍失败关闭 | `python -m pytest tests/integration/test_dependency_path_consistency.py -q` | 保持断言：**这条差异变红 = 差距形态变了**，要重新评审；不要在改之前把预执行路径当成与 AST 等价 | 未指定 |


| 5.52 | **`tools/check_notebook.py` 不在 `HANDBOOK_PREFIXES`** | 它是 tech-detail 门禁步骤复用的结构校验器，但改它只命中 `CODE_PREFIXES`，而 `CODE_STEPS` 不含 `Tech-detail notebooks are in sync` → 改坏校验器时那一步不会跑 | `Select-String -Path tools/ci_local.py -Pattern 'HANDBOOK_PREFIXES' -Context 0,5` | 把 `tools/check_notebook.py` 加进 `HANDBOOK_PREFIXES`（一行），或写明"复用者改动不影响产物同步"的理由 | 未指定 |
| 5.53 | **`/v1/validation/evaluate` 的超时路径没有专门用例** | 该路由的超时只由**默认预算**兼职覆盖；2026-10-06 把测试部署的 `validate_ms` 提到 30s 之后，"验证太慢"这个信号在测试里更不会被触发 | `git grep validate_timeout -- tests` → 空；`tests/api_support.py` 的 `budgets.validate_ms` | 补一条用**极小预算**驱动的用例（断言 504 + 错误码 `validate_timeout`），别让默认预算兼职被测对象 | 未指定 |
| 5.54 | **仓库自身源码没有 lint 门禁**（与 §5.36 是同一条缺口；本条给出更完整的读数与入口清单） | `validation/ruff.toml` 目前只服务夹具 / 探针 / 验证器路径；**CI 不对仓库自身源码跑 ruff**（workflow 里与 ruff 有关的只有 `Install external linter (ruff)` 这一步，`tools/ci_local.py` 的步骤映射里也只有它的安装名）。`src/retrieval/models.py` 的既有 E501 就是这样被"顺手取证"发现的（另有两处是本期新提交引入、已单独修掉）。读数（ruff 0.14.13 + 仓库自己的配置，2026-10-08 本机复跑）：`ruff check --config validation/ruff.toml src/ tools/` → **Found 842 errors**；分布：E501 **737**（87.5%）、F401 24、I001 20、N806 18、S110 9、S105 6、D205 5、S310 5、E401 4、N802 3、S314 3、E741 2，以及 E402 / F841 / S106 / S112 / S311 / S608 各 1；**可自动修复 49 条**（F401 24 + I001 20 + E401 4 + F841 1）。这些码**全部**来自该文件 `select` 里已归属规则的集合（E501→STYLE-001、F401→STYLE-002、I001→STYLE-018…），不是"未映射诊断"。（同一条命令在本轮两处既有 E501 修掉**之前**的读数是 844（E501 739），差值 2 正是这两处——`3ac92b5` / `45e6710` 拆掉 `src/retrieval/models.py` 的两行长行。） | `ruff check --config validation/ruff.toml src/ tools/`（加 `--statistics` 出分布）；`python tools/ci_local.py --list` | **维持现状（已登记未接，不排期）**。为什么暂不接：842 条里近九成是长行口径而非缺陷面；一次性 `--fix` 49 条会跨约 40 个文件，属于独立的机械性工作。将来若要接，三个入口（按推荐顺序）：(a) **只报告步骤**（恒退 0，与 `instrument_self_proof` / `control_plane_facts` 同族，需先定义**结构化红条件**，否则只是噪声）；(b) **窄口径门禁**——只 `select` 可自动修复的四类，先 `--fix` 清掉 49 条，之后新增即红；(c) 只留这条登记。接之前要先说清它归"外部工具探针"还是"项目档案"哪一套口径、红了谁负责修；`tools/` 与 CI 配置惯例上归 tools 侧维护者。 | 未指定 |
| 5.55 | **CI 里的 ruff 是浮动区间，而规则与文档按"实测 0.14.13"措辞** | `.github/workflows/phase-8.yml` 的 `Install external linter (ruff)` 装的是**区间**（现为 `ruff>=0.10,<1`），而 `policies/**` 与若干文档写的是"本机实测 ruff 0.14.13"（如 SEC-005 的覆盖边界 note）；区间内任一版本都可能被装进来，装进来的版本一变，这些"实测"措辞就不再成立，而门禁读不出这个漂移 | `Select-String -Path .github/workflows/phase-8.yml -Pattern "uv pip install"`；`python -m validators.cli probe --json`（`tool.ruff` 的可用性与版本） | 要么把 CI 的 ruff **钉到具体版本**（与 `validation/validators.yaml` 的 `tool.ruff.version_requirement` 同一处口径），要么加一条"实测版本 vs 安装版本"的一致性检查；在此之前引用"实测 0.14.13"必须写明只对该版本成立 | 未指定 |
| 5.56 | **workflow 里的 ruff 版本区间是第二份副本** | 同一个区间在 `.github/workflows/phase-8.yml` 与 `validation/validators.yaml` 的 `tool.ruff.version_requirement` 各写一份；两处目前是同步的（下界 0.6 → 0.10 是逐码读 `ruff rule <CODE> --output-format json` 的 `since` 之后一起改的），但没有任何机制保证下次仍同步 | `Select-String -Path .github/workflows/phase-8.yml -Pattern "ruff>="`；`Select-String -Path validation/validators.yaml -Pattern "version_requirement"` | 让 CI 那一步从 `validation/validators.yaml` 读区间（需要一段内联 python，属 CI shell 语义、本机验不了），或加一条一致性检查；无论哪条，改动前先给改前/改后推演 | 未指定 |
| 5.57 | **eval-datasets 的 `role` 里藏着资格规则，缺机器可读的排除字段** | `docs/project/engineering-policy-platform/testing/eval-datasets.yaml` 把 `role` 定义为"这条语料服务哪些工作包与指标（W*/GV-*）"，但 `pylint-functional` 一条写成 `[差分对照（人工映射，不计入 GV-01）]`——一条**资格规则**藏在自由文本里（2026-10-08 已把该处收窄为 `[差分对照]`、口径移进 `cannot_prove`，但没有把它变成可解析字段） | `Select-String -Path docs/project/engineering-policy-platform/testing/eval-datasets.yaml -Pattern "role:"`；该文件的字段表（`note` 一节） | 由登记表维护者决定是否加 `not_counted_toward: [GV-01]` / `gate_eligible` 一类字段（该文件带 `schema_id` / `version`，加键即一次显式 schema 变更）；在此之前资格规则一律按 `cannot_prove` 读 | 未指定 |
| 5.58 | **开启 `pre_evidence` 后「改动集里只有测试文件」的编辑一律被拦** | 真 Hook 实测（2026-10-10）：把只改了模块 docstring 的 `edit tests/test_order_service.py` 喂给配置了 `pre_evidence` 的 Hook → exit 2 `policy_block`，唯一 violation 是 `TESTING-002@1`（severity=critical、`detail=uncovered_checker`、`value=failing_tests`）；同一次运行里 `tool.pytest` 的 reason 是「变更集里没有生产文件，测试选择不适用」。根因链：`select_tests` 在该情形返回 `level="none"`（`src/validators/selection.py:159`），`pytest_runner` 于是只把 `missing_tests` 记进 `served`（`src/validators/adapters/pytest_runner.py:177-190`——它本身是 5.3「空选择被记成服务过」的正确修复），引擎再按 AGENTS 第 20 条对需要 `failing_tests` 的规则失败关闭。后果：开启取证的工作区**无法新增或修改任何测试文件**，于是也补不上 `TESTING-001` 要求的测试——两条测试规则合起来是一条死路（与第 51 条「先写测试不该被自己的平台拦死」的意图相反） | `python -m adapters.dsh.hooks --config <启用 pre_evidence 的配置> --hooks-config <hooks.json>` 喂一条 `edit tests/...` 的 PreToolUse 载荷；复现脚本与读数在 `.tmp/ab-verify/{drive,final_check,scope_check}.py` | 二选一，都要走完整条协议纪律：① 让 `select_tests` 把「目标本身是测试文件」当成一次合法选择（新增 `level` 取值 = 载荷语义变更，按第 55 条递增 `PIPELINE_SCHEMA_VERSION` 并同步 tech-detail 生成物）；② 把 `TESTING-002` 的 scope 收窄到生产层（规则语义变更，须重跑规则覆盖与契约断言）。**本次不顺手做**：2026-10-10 的 A/B 对比测试以「两边都不动 `tests/`」绕开，缺口单独登记。顺带：本次实测正是在影子副本上真跑了 `tool.pytest`、`failing_tests` 进了 `served_checkers` 并报出 `FAILED tests/test_order_controller.py::test_controller_delegates_to_service`，这正是 5.48 想要的那条端到端读数（仍差把它固化成仓库用例） | 未指定 |
| 5.59 | **GUI 的 PTC 传输工具与「单审批槽位」冲突：受治会话要么全冻结、要么跑不了命令** | 真机读数（2026-10-10，dsh 桌面端 + desktop profile）：本机每个模型侧动作都包在 `run_code`（PTC 传输）里，子工具调用（`write` / `edit` / `pwsh`）由运行时**逐个派发**并**逐个判定**（审计里是 `<callId>:ptc:N`）。而 5.21 规定一个 `approval.json` 只授权一个执行类工具、`approval_file` 是单值 → 名额给了 `run_code`，`tools.pwsh` 一律 `approval_invalid`（实测：`python -m pytest -q` 被拦）；名额给了 `pwsh`，`run_code` 被拦 → **整个会话冻结**（实测：连读一个文件都进不去）。另有两个实测坑：① `.*` **不匹配换行**，run_code 的 `code` 天然多行 → 用 `code=.*` 签的条子对任何真实代码都是 `approval_invalid`，必须写 `code=(?s).*`；② `risk=privileged_execution` 的工具写成 `approval: none` 会在**注册表加载期**被拒（第 14 条的加载期形态），所以「拿掉审批」这条路走不通 | 三份读数：`.tmp/ab-verify/{run_code_check,final_cfg_check,resign_check}.py`；受治会话记录 `.dsh/sessions/--C-Users-ZNM-Downloads-Comparison-test-Governance--/session-ac482d66.../session.v4.jsonl.zstd` | 与 5.21 同一处修：审批协议支持**按工具分文件 / 多记录**（`precheck` 已按 `tool_id` 选记录，改动主要在 dsh 适配器的加载与选择）；在它落地前，PTC 宿主的受治会话只能二选一——这也是本次对比测试把「跑命令」排除在外的原因 | 未指定 |
| 5.60 | **被拦下的动作，模型看到的第一段理由是 post-check 的「找不到 pre-check 记录」** | 实测（受治会话 3f255054...9498f74f，2026-10-10 真实 GUI 对比测试）：7 次 pre-check 拦下（policy_block）**每次都跟一条 PostToolUse 的 `post_error`**，原文 `PostToolUse 找不到对应的 pre-check 记录：既证明不了这次执行被授权过，也证明不了它被拒绝过——证据不足，不得按放行处理`。语义上保守且正确（动作没执行、证据不足就不按放行），但**顺序**上它排在真理由前面：模型与读者第一眼读到的是「post-check 失败」，而「ARCH-001 Controller 必须通过 Service 访问 Repository」在第 4 行之后——会话里的模型自己得先剥掉这段「共同外壳」才敢引用真理由（它的汇报原文如此）。同会话 reason_code 分布：`policy_block 7 / post_error 7 / post_validated 7` | 审计 `Comparison-test/Governance/.policy/audit.jsonl`；读数脚本 `.tmp/ab-verify/post_check.py` | 让 post-check 能识别「同一 action_id 已在 pre-check 被拦」这一事实，给出独立状态（例如 `post_skipped_blocked`）并**不重复报错**；最低限度也要把顺序调成「先给真因、再给事后核对」。属 `hooks.py` 的判定行与审计记录变更，要动 `VERDICT_SCHEMA_VERSION` / `AUDIT_SCHEMA_VERSION` | 未指定 |
| 5.61 | **`host_version` 只探 CLI 那条版本线，桌面端是另一条；而跑治理的恰恰是桌面端** | `adapters/dsh/manifest.yaml` 的 `agent_version` 口径是"**已实测**的 Agent 产品版本"，唯一的读法是 `dsh --version`。本机实测（2026-10-10）两条线不同号：CLI 的 `dsh --version` = `0.2.1-alpha.2`，桌面端 `DeepSeek Harness.exe` 的 FileVersion = `0.2.0-rc.2`（ProductVersion 0.2.0.0；安装目录 `resources/version` 里的 44.0.0 是 Electron 的，不是产品版本）。于是"声明与宿主一致"这句话**只对 CLI 成立**：桌面端那条线漂移了也不会红，而桌面端才是桥实际挂载的宿主（`desktop` profile，见 `tools/dsh_bridge.py`） | `dsh --version`；`(Get-Item '<桌面安装目录>\DeepSeek Harness.exe').VersionInfo.FileVersion`；对比 `adapters/dsh/manifest.yaml` 与 `adapters/host-versions.observed.json` | 二选一：① 给桌面端加**第二条**读法——manifest 的 `host_version` 目前是单值，加它就要动 `ADAPTER_MANIFEST_SCHEMA_VERSION` 与 `HOST_VERSION_RECORD_SCHEMA_VERSION`，并按 AGENTS 第 54 条重跑 `approve` + `host-version --record`（记录里的两条线都必须能核对）；② 显式写明"这条声明只承诺 CLI 那条线"，把桌面端版本记在别处。**在此之前**引用 `agent_version` 必须带"这是 CLI 版本"这个限定 | 未指定 |
| 5.62 | **工具表与运行期观察的漂移此前读不出来：`wiring` 的「被调用过」这一列恒为空** | 2026-10-10 读数（`--observe-sessions 400`，400 份真实会话记录）：工具表 **38** 条 vs 运行期**声明**过 **86** 个不同工具——**表外 54 个**（`mcp__github__*` 50 + MCP 资源类 3 + `working_directory` 1）；**真的被调用过、且表外**的有 **5** 个（`list_mcp_resources` / `list_mcp_resource_templates` / `mcp__github__actions_list` / `mcp__github__get_job_logs` / `run_command`）。其中 `run_command` **任何会话的 header 里都没声明过**，所以仪器修好之前它完全不可见。根因：`observe_runtime_tools` 只认 `tool_use` 部件（0.1.x / 外部方言的形状），而 0.2.x 的 v4 记录写 `tool-call`——**同一批记录里 `tool_use` 部件 0 个、`tool-call` 覆盖 16 个工具**，"被调用过"这一列结构性恒为空（仪器也要能失败）。**已修**：两种部件名都认（`TOOL_CALL_PART_TYPES`），回归用例 `tests/unit/test_wiring.py::test_v4_session_records_use_tool_call_parts` 喂真实形状，修复前红 | `python -m adapters.cli wiring --json --observe-sessions 400` 的 `tools` 段；`tests/unit/test_wiring.py` 的工具观察四条 + 新增一条 | 处置：**工具表保持不变**（白名单 + 失败关闭是设计：受治会话调用表外工具即 `tool_not_registered`，`tests/integration/test_dsh_enforcement.py` 钉住这个 reason_code）。不顺手补表——MCP 家族里有写类（`create_or_update_file` / `push_files` / `delete_file` / `merge_pull_request`），要放行必须逐个核实语义并补契约测试（同 5.28 的口径）；`working_directory` 的语义已从真实会话头读出（读当前目录 / 用 `cd` 改它），但它**改变会话工作目录**，而作用域判定的基准是插件载荷里的 `session_cwd`——"`cd` 之后基准还准不准"没有读数，所以在解决它之前不许登记（登记了就等于宣称它被治理了） | 未指定 |

## 6 已知边界（设计取舍，不是缺陷；但产品化 / 部署前必须处理）

这些是仓库存量文档里的显式边界，AGENTS.md 的核心约束**没有**覆盖它们
（第 16 条覆盖"审计链不是防篡改日志"、第 17 条覆盖"白名单不是沙箱"，这里不重复）。

| 事项 | 边界内容 | 需要时做什么 |
| --- | --- | --- |
| 令牌与身份 | **静态凭据**：配置里声明 `token_sha256` + `expires_at`，没有 OIDC、没有签名、没有轮换，也没有 `audience` 可判 | 生产部署前接 OIDC / 短期凭据；在此之前"身份已解决"的表述都不成立 |
| 传输与部署 | **没有 TLS、没有反向代理、没有连接池调优**；uvicorn 直接监听 `127.0.0.1` | 生产部署前补齐，并把这一条从"平台能力"里划出去 |
| 超时语义 | 超时是"**调用方不再等待**"，不是"工作已经停止"（Python 无可移植线程取消）；结果被丢弃、观测记 `outcome=timeout` | 要真正中止需改成分进程执行 + 终止进程树 |
| 指标 | **只在进程内**、无持久化、重启归零；`/v1/ops/metrics` 是当前进程的自述 | 要历史报表需外部后端；不要当容量规划依据 |
| 并发 | `BoundedSemaphore` 只保证"不会无限排队"，不保证有容量（0.5s 拿不到 → 503 `policy_busy`） | 更强保证需排队上限 / 拒绝策略的显式设计 |
| 多进程 / 多 worker | 文件锁、限流、幂等台账、metrics 竞态**只做了单进程验证**；编排的熔断是**进程内**的、checkpoint 单文件原子替换**不保证互斥**（同 task 两进程同时恢复不受保护） | 多 worker / 多机部署前先压测并检查跨进程正确性（必要时动 `IDEMPOTENCY_SCHEMA_VERSION`）；恢复加锁或租约 |
| 规则集热替换 | "整份替换 + 指纹检测"，**没有跨请求事务**；两个请求可以合理使用不同世代的规则集 | 需要原子切换要在服务层加版本门（属于新契约，先升 `API_SCHEMA_VERSION`） |
| 索引 | **离线构建、服务只读**；服务不在请求里建索引；索引缺失 → 503 `knowledge_unavailable`（不回退空结果） | 部署流程必须写"先建索引再启动服务" |
| 审批可信度 | 审批是**未签名的结构化文件**，靠"由谁放进收件箱" + 角色声明；伪造 `granted_by_roles=[reviewer]` 即可自批；作用域限于那一次部署的台账；**没有 API 入口**（签发走 `enforcement.cli approve`） | 引入签名 / 审批服务 / 独立名册前，任何"审批已被验证"的表述都要带上下文；要真正的人机闭环需新增审批服务（并同步版本轴与契约快照） |
| `Content-Type` | **没有该头的 JSON 请求会被接受**（有意的宽松） | 收紧会改变调用方行为，属契约变更（要动 `API_SCHEMA_VERSION`） |
| 编排的作者与用量 | 真实模型作者**未接入**（只有 `ScriptedAuthor`）；token / 费用上限只验证了机制、**没有被真实用量校准**，且"未上报的用量被当成 0"；`side_effect_unknown` 之后**不解释"人工已处理"**，要用新幂等键重新发起 | 接入真实模型后核对用量上报，并把"未上报 = 拒绝"作为显式决定；若要人工确认后续跑，需要新契约 |
| 版本兼容矩阵 | LangGraph 只验证了 1.2.11 一个版本（主版本变化一律拒绝，小版本没有矩阵）；`checkpoint.record_digest` **是摘要不是签名** | 升级依赖 / 接新 Agent 时重跑对应闭环与一致性套件，并把新验证版本记进文档 |
| 命令白名单 | 语义是"**单条语句**"：组合命令与受限选项结构性阻断；**它不是沙箱**——会读仓库内配置的命令仍可能被改写成执行外部命令 | 遇到新的危险形态：改注册表数据 + `--approve` 重审，**不要放宽结构性阻断**；真正的隔离属于运行时沙箱 |
| `run_code` | 平台侧 `driver: none`，执行器显式拒绝——**只有 Agent 运行时能执行它** | 要在平台侧执行代码必须新增驱动并重新审核注册表，不能靠现有驱动假装执行 |
| 依赖事实 | **调用链不产生依赖事实**（`self._repository.save()` 需要类型推断，本阶段不做）；判定只依据 import 事实 | 要类型感知的依赖事实需引入类型推断 / 类型检查器证据；引入前先写清会不会改变现有判定 |
| `--dependencies` 旁路 | 调用方显式声明依赖可**替换 AST 证据**、给出与默认路径不同的结论（证据记成 `cli.explicit@1.0`） | 若要收窄，先把依赖它的示例 / 手册单元改造成 AST 证据路径，再决定是否废弃 |
| 会话身份与留痕 | 未治理通道（含桌面 GUI）**不写审计**："账本干净"不等于"没有被改"；`attempted_write=false` 在未治理通道里是"没有审计可看"，**不是"没有尝试"**；未声明 `pre_evidence` 的部署只有 1/43 条规则参与判定，**文档类目标是 0/43（声明过的 0）** | 读未治理臂时以**文件哈希**为准；引用"43 条规则 / 42–43 覆盖"时必须带分母与语言范围；接通道路径见 §4 的 G1 |
| 坏配置的代价 | 配置坏了 = **整条通道完全不可用（含只读）**：可用性换安全性的取舍（正确的失败关闭，不是 bug）。受限沙箱里 Hook 用管道 stdio 启动会被拒（`spawn EPERM`）→ **策略链路根本没被触及** | 受治理会话必须在不受限 shell 里起；受限环境下要写明"策略链路未被触及"，不要把"跑不了"读成"跑成了、没拦住" |

## 7 引用纪律（把读数读对的最小集合）

| 事项 | 纪律 |
| --- | --- |
| 只报告读数 | 引用时同时给出：哪棵树（`reading_context.tree.revision`）、哪一次运行（`run.id`）、是否 enforceable（`enforced: false` = 声明出来的"还没接线"） |
| 环境跳过 | 环境跳过（沙箱受限 / dsh 缺失 / 账本不存在）**不是命中、也不是通过**；读数必须写明 reason / reproduce |
| 会话结论 | 必须同时给"参与判定 / 跳过"的分母（如 controller 层 1 条参与、42 条跳过）；`skipped` 不等于通过 |
| 规则命中 | 必须同时给严重级别（仓库当前 24 条 error / 19 条 warning）；**"规则命中"与"动作被拦住"是两件事** |
| 账本条数 | 三种切法（按内容定位的会话增量 / 按时间窗 / 按 `session_id`）**互不相等**；引用"会话内有多少条记录"必须写明切法 |
| 仪器覆盖 | 每条检查都要能说出"驱动的是哪条路径、仍不覆盖什么"：矩阵只压 3 个 Ruff 码（不是全码表）、不含真超时、不含 POSIX、`type_check` 未启用；是 **6 臂重放 + 2 变异**，不是 30 臂全重放 |
| 样本量 | 受治领会话样本量小（如 4 次 / 1 次有效）；"会不会换一种写法绕过"这类问题**没有统计结论**；引用时写明样本量 |
| 不可复核的历史陈述 | "修复前 PostToolUse 是 0 条"这类表述没有修复前证据文件，**只写现在**、不回述修复前状态 |
| 提交历史 | 门禁绿 ≠ 提交历史合规：历史上存在一个提交承载两轮、或一个提交混两件事的情况 |
| 性能读数 | 性能基线不是硬门槛（受负载影响可达 2 倍，测试只断数量级上限） |

## 8 仪器与环境的读法（弄错会把环境失败读成回归）

| 事项 | 读法 |
| --- | --- |
| **仪器在哪** | 已跟踪：`tools/governance_gap_probe.py`（13 项缺口 + before/after 双预期）、`tools/dsh_sandbox_loop.py`、`tools/provenance_loop.py`、`tools/obligations_gate.py`、`tools/exemption_expiry.py`、`tools/instrument_self_proof.py`、`tools/control_plane_facts.py`。**未入库**：30 臂矩阵 / 封条探针（一次性仪器、带硬编码路径，见 5.33） |
| **本机门禁要显式指定解释器** | `.venv` 存在但缺 pip / fastapi / uvicorn / langgraph；本机跑门禁用 `python tools/ci_local.py --full --python <已验证解释器>`（pre-push 钩子认 `CI_LOCAL_PYTHON`） |
| **`Real dsh sandbox loop`（门禁第 9 步）** | 现行口径：dsh 缺失**或**沙箱禁止管道 stdio（Hook spawn EPERM）时**按环境跳过**（退出码 0 + 写明 reason/reproduce，见根 README 第 7.1 节），**绝不把"跑不了"记成 pass**。旧记录里的 `result=fail` / 退出 1 是历史行为，不要照抄。**审计为空 = 没有判定**，不是被规则阻断 |
| **xdist 在本会话起不来** | `pytest -n auto` 必 `INTERNALERROR`；用 `PYTEST_XDIST_AUTO_NUM_WORKERS=0` 串行，并**在读数处逐次声明**（缺口 5） |
| **pytest 缓存与残留目录** | `.tmp/.pytest_cache` 的 ACL 会产生 `PytestCacheWarning`（不影响结果，但写不进也清不掉）；受限沙箱里还会在仓库根留下 `pytest-cache-files-*/` 空目录（普通开发机上不会，`pytest.ini` 已把缓存指到 `.tmp/`） |
| **受限会话里 `tmp_path` 与 `0o700` 目录会被锁死** | 受限沙箱下 `os.mkdir(d, 0o700)` 出来的目录**读不到也删不掉**，pytest 的 `tmp_path` fixture 会 `ERROR at setup`；**kill 正在跑的受限 pytest 会留下永久锁死的目录**（ACL 恢复步骤一起被杀）。对策：受限会话里写测试不要用 `tmp_path`，自建 `.tmp/tests/<名字>/` 且只删文件不删目录；给每次跑一个全新的 `--basetemp`；不要 kill 受限的 pytest 进程 |
| **受限会话里 `tmp_path` 的现存用量** | 2026-10-10 读数：`tests/` 里 **22 个用例函数（9 个文件）**把 `tmp_path` 列进参数（`tests/unit/test_check_repo_consistency.py` 9 条最多）；受限会话里它们必然 `ERROR at setup`。本机门禁实测：第 3 步 `rc=3`（xdist `INTERNALERROR`）、第 26 步 `failures=23`，**其余 24 步全绿**——读到「门禁红」先看这条，别当成改动引入的回归。复现：`python tools/ci_local.py`，`.tmp/ci-local-logs/03-*.log` 里的 `PermissionError: ...\.tmp\tmp\pytest-of-*`。不受限 shell 里同一批用例正常（`reviews/fix-ledger-2026-10-08.md` §5.1：同一路径在完整权限下可读，ACL 诊断脚本判定 `NOT_THIS_CLASS`、未改任何权限）。两条出路：在不受限 shell 里跑门禁，或把这 22 条迁到 `tmp_root` 夹具（仓库自己的对策，见 `tests/unit/test_phase4_reason_redaction.py` 的用例注释） |
| **`tools/cleanup.py` 在受限沙箱下可能退出 1** | 删除失败即**如实报错退出 1**，不假装成功——不是脚本坏了 |
| **真实受治理会话的三个前置条件** | ① 凭据只注入子进程环境（`DEEPSEEK_API_KEY` 之类）；② 会话必须在**不受限 shell** 里起（受限沙箱里 spawn EPERM）；③ 同一时刻**只跑一个** dsh 会话（审计是同一个文件）。缺任一条，会话结论就退化成环境结论 |
| **门禁的通道清点默认读真实 `~/.dsh`** | 装在会话沙箱内 `DSH_HOME` 的通道不在门禁视野里；要清点它就显式给 `python -m adapters.cli wiring --dsh-home <dir>` |
| **多 worktree 并发不在锁的保护范围内** | `ci_local.py` 的排他锁只保证**同一棵树**上的单实例；同时只允许一个 `ci_local.py`（含 pre-push 那一次）真正执行 |

## 9 外部环境项（本仓库无法完成）

| 事项 | 现状 | 下一步 |
| --- | --- | --- |
| **Phase 6 第二真实 Agent 产品验证** | 当前只有 dsh 是真实产品接入；`generic-json` / `legacy-post-only` 是合成协议消费者。仓库内退出条件已满足（dsh 40 项 / generic-json 35 项 / legacy-post-only 12 项显式不适用），**产品验收那条外部证据仍缺** | 在具备第二真实产品的机器上跑一致性套件，留下版本化 fixture 与运行报告；不能宣称"三种支持状态都有实例"（当前 `full=1 / read_only=2 / unsupported=0`） |
| **Phase 8 真实 `ChangeAuthor` 模型实现** | 只有确定性的 `ScriptedAuthor`；接入模型不改变节点契约，但没有验证过真实模型行为 | 接入后重跑 `python tools/orchestration_loop.py` 并记录报告（引擎、终态、用量口径） |
| **真实 dsh 会话端到端（G2 残余）** | 事件名与三参签名已用实现包字符串事实核对，但**没有真会话触发过 PostToolUse**（需要重启 GUI） | 在能装 dsh 的环境跑真实闭环并把结构化结论留档 |
| **dsh Hook 桥"拦截不生效"的原因未定论** | 外部命令 Hook 被调用、审计有记录、退出码 2，但工具仍然执行；改用进程内 shim 插件后才阻断成功；怀疑版本错配（未证实） | 在能装 dsh 的环境做版本对齐实验：要么修桥，要么把 shim 转正当作唯一接线方式并写进架构文档 |
| **真实 Codex / Claude Code 接入** | 建议顺序里的第三、四个 Adapter 尚未接入，需要先核实产品版本与钩子契约 | 按升级流程 6 步执行（`adapters.cli events` → `check` → `agent_loop.py` → `approve`）；顺序反了会出现"矩阵说能拦、实际拦不住" |

## 10 设计提案的阻塞项核实（designs/）

`designs/` 保留的是**尚未实现**的提案与评估，状态表见 [designs/README.md](designs/README.md)。
"文档 → 规则 操作平台"的独立评审曾指出两条**必须先修**的阻塞项。**本轮核对代码后两条都已在代码侧收口**
（不是遗留缺陷，登记在这里是为了避免后来者按旧评审重复排查）：

| 曾阻塞项 | 现状（已收口） | 核实证据 |
| --- | --- | --- |
| **新建规则文件绕过审批**（"整文件写入"模式下工具落到了 `approval: none` 的 `orc.fs.write`） | **已修**：`policies/` 前缀在**工具选择**层被硬约束，新建规则走 `orc.policy.write`（`approval: required` + `pattern: ^policies/...`）；`orc.fs.write` / `orc.fs.edit` 的 `blocked_prefixes` 含 `policies` | `src/orchestration/nodes.py:69-101`、`registry/tool-registry.yaml:333/342/367`、`tests/unit/test_orchestration_state.py:749`、`tests/contract/test_enforcement_protocol.py:376-385` |
| **HTTP 面漂移静默**（`index.hash_drift` 恒为 `[]`，检索的漂移在 HTTP 面被抹平） | **已修**：`retrieve` 响应的 `index.hash_drift` 现在由语料校验结果逐条产出（与 `verify` 退出 1 同源） | `src/policy_api/runtime.py:689-692`（`sorted(... for issue in loaded.verification.drift)`）；对照 `python -m retrieval.cli verify` |

**仍有效的实施约束**（提案落地时按这些做）：

- **镜像内容是不可信数据**：`hits[].text` 原样返回含 `<script>` 与控制字符的第三方正文，而全仓
  `src/` + `tools/` **没有任何 HTML 转义**（`html.escape` / `markupsafe` 0 命中）。界面一律
  `textContent` / 输出转义、禁用 `innerHTML`，并把"镜像内容永不作为 HTML 解析"写成验收断言。
- **草稿存储不存在**：`action_hash` 只能由 Phase 4 / 编排层的 `binding()` 产出，**前端不得自算**；
  "已生效 / 未生效 / 生效失败"三态要分开。
- **前端不得复制枚举**：checker / scope / severity 的可选项必须来自后端只读接口，不得硬编码；
  一切"通过 / OK"文案只由后端响应字段驱动；跨条一致性（唯一性、原子性）不得在前端实现。
- **未知路由的 404/405 语义**：若采用同源静态挂载，挂载会改变未知路径的 404/405（统一错误信封不再成立），
  必须补回归测试；**推荐反向代理同源**（`policy_api` 零改动、零契约影响）。
- **失败码映射要覆盖编排侧**：`side_effect_unknown` / `approval_param_mismatch` / `evidence_unavailable`
  等来自编排层，不在 `policy_api` 的 33 个码里，界面必须补一张映射表。

---

**维护纪律**：本文件只登记"还没做完 / 还没核实 / 到期要复看"的东西。做完一条就在同一次提交里把它删掉
（或改写为结论）；**不要**把已完成的过程记录搬回来。新增一条时写全五列，证据列给**可执行命令**
（或 CI 步骤名、行为描述），不要写"见某轮记录"——那些记录已经不在仓库里了。

---

## 11 数字口径：本次已落地 / 仍未校准（2026-10-06）

**已落地**（学习手册下线 + 图全部下线之后一次成型回写）。判据从「图 / 文 / 口径表三处同改」
收窄为**「文 / 口径表两处同改」**：`tools/check_arch_canon.py` 随图删除，
`tools/check_arch_style.py` 仍守文风（它读的是散文，与图无关）。

| 项 | 现在写什么 | 实测命令 |
| --- | --- | --- |
| CI 具名步骤 | **43**（带 `run` 块、可被调度的是 **42**；本机 `--full` 计划实际执行 **29**；无名的 `actions/checkout@v7` 不计） | `(Select-String -Path .github/workflows/phase-8.yml -Pattern '^      - name:').Count`；`python -c "import sys;sys.path.insert(0,'tools');import ci_local;print(len(ci_local._steps()))"` |
| 全量测试 | **收集 2136 = 2135 passed / 0 failed / 1 skipped**（2026-10-06 门禁实跑，305s） | `python -m pytest -q -n auto --dist loadfile` |
| `tools/` 计数 | 顶层 `.py` **28** / 顶层文件 **29** / `git ls-files tools` **37** | `(Get-ChildItem tools/*.py).Count`、`(Get-ChildItem tools -File).Count`、`(git ls-files tools).Count` |
| 闭环脚本 | **7** | `(Get-ChildItem tools/*_loop.py).Count` |
| `AGENTS.md` 约束条数 | **56** | 见 `功能清单.md` §7 的实测命令 |

**仍未校准**（另开一次口径校准，别顺手改）：语料 / 索引类数字两处互相冲突
（`功能清单.md` 的「27 篇 / 535 chunk」与 `术语与口径.md` §5 的文档 / chunk / 章节计数）；
受控工具数（`功能清单.md` 写 9、`术语与口径.md` §5 写 10）；
`术语与口径.md` 头部的 `SCHEMA_VERSION="1.0"` / `POLICY_VERSION="phase-1"`（AGENTS.md 现为 `1.1` / `decision-1.1`）；
阶段证据脚本那一行的根因描述（取数早于最新一次运行）。

---

## 附录：历史编号对照

> **用途**：仓库里仍有大量**短式编号引用**（"21 号 §2.5""07 号报告""24 号 §8.3""R2/G13"）指向
> 2026-10-06 下线的轮次记录与阶段实施记录。本表**只保证编号可查**——正文已删除，
> **结论一律以现状文档为准**（本文件、00–03、`docs/project/architecture/`、[designs/README.md](designs/README.md)）。
> 表里只写**文件名与主题**，不写指向已删文件的链接：它是一张对照表，不是死链集合。
> 编号里的组名：`15-control-plane-design` = 控制面重构线（其下的两位编号就是历史引用里的"21 号""13 号"）；
> `governance-capability` / `governance-remediation` = 治理能力实测线与修复线；`reviews` = 顶层复核；
> `phases` = 阶段实施记录。
> 主题取各文件的一级标题原文（phases 为阶段名）。

| 编号（原出处） | 主题（原文标题） | 现在的落点 |
| --- | --- | --- |
| `governance-capability/00` | 治理能力实测报告：把一个真实的多文件开发任务压到治理上 | [04-open-work.md](04-open-work.md) §5 / §6 / §7 |
| `governance-capability/01` | 01 · 规则覆盖矩阵：43 条规则各自"能被哪条路径判出来"（T1） | [04-open-work.md](04-open-work.md) §5 / §6 / §7 |
| `governance-capability/02` | T2 · 真实受治理多文件开发会话与证据采集 | [04-open-work.md](04-open-work.md) §5 / §6 / §7 |
| `governance-capability/03` | 03 · 验证器路径与执行链能力取证（T3） | [04-open-work.md](04-open-work.md) §5 / §6 / §7 |
| `governance-capability/04` | V1 · 独立验收：换个入口复核"治理能力"结论 | [04-open-work.md](04-open-work.md) §5 / §6 / §7 |
| `governance-capability/05` | 实测显现的新问题（N16–N24） | [04-open-work.md](04-open-work.md) §5 / §6 / §7 |
| `governance-capability/06` | 多规则开发轮：开启治理、开子会话做多文件开发、用五类规则压它（2026-09-27） | [04-open-work.md](04-open-work.md) §5 / §6 / §7 |
| `governance-capability/07` | 治理全开轮：动手前取证在真实会话里打开、跨 12 个文件开发、五类规则同时参与判定（2026-09-27） | [04-open-work.md](04-open-work.md) §5 / §6 / §7 |
| `governance-capability/08` | 多规则开发轮 2：真实受治理子会话做跨两子系统开发、五类 checker 同时参与判定、账本可独立重算（2026-09-27） | [04-open-work.md](04-open-work.md) §5 / §6 / §7 |
| `15-control-plane-design/01` | 01 · 30 臂确定性 Hook 矩阵摘要 | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/02` | 02 · 内部独立验收：12 条偏差与处置 | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/03` | 03 · 「哪些路径算测试」两份声明的不一致（101 个文件） | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/04` | 04 · 三轮研讨的过程记录 | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/05` | 05 · 检查点提交的预检摘要（task-17） | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/06` | 第 15 轮收口记录：按轮次拆分、门禁与基线 | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/07` | 第 15 轮 · 最终状态独立验证报告（被测 sha = 928df2a） | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/08` | 控制面重构 · 开工状态与前置清单 | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/09` | 09 · 台阶 −1② 基线读数重采（30 臂矩阵 + 11 fixture + 树摘要） | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/10` | 10 · 台阶 1（H4）字段级差集、受影响清单与红→绿读数 | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/11` | 11 · 台阶 2：归因闭集与核验前置（R-g）的读数与字段级差集 | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/12` | 台阶 3a · H1/H10 受控 reason 与归因路径脱敏（实施记录） | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/13` | 台阶 3b（D-1）· 字段级差集与受影响 fixture 清单（分析稿，**未落码**） | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/14` | 台阶 3b（D-1(b)）· 落码与读数（实施记录） | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/15` | 15 · 台阶 3c 之前的小修：VERDICT 行核查、AGENTS 第 55 条版本轴、B4 正例 | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/16` | 16 · 台阶 3c：义务账（只记账、不判罚；按 L5 以 warn 跑一轮） | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/17` | 17 · §3.6 前置评估：台阶 4–5 的两份整数清单与逐条结论 | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/18` | 18 · 第 16 轮：2026-09-30 裁定的执行（包装层版本轴、义务门禁接门禁、台阶 4 写声明） | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/19` | 19 · 第 17 轮：台阶 4 `reading_context` 的登记项、遗留与门禁读数 | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/20` | 20 · 第 18 轮：端到端读数更正、`--isolated-home` 与豁免读数的机器行 | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/21` | 21 · 台阶 4 · `reading_context` 设计稿（**只写文档，不写代码**） | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/22` | 22 · 第 19 轮：合并 CI 线、沙箱载荷建轴、`reading_context` 设计稿与门禁读数 | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/23` | 23 · 第 20 轮 · `reading_context` 落地（端到端 / 只报告两处 / `policy.check`）与评审点 | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/24` | 24 · 台阶 4 · `governs` 轴与声明差集设计稿（**只报告**，只写文档） | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/25` | 25 · 台阶 4 · 仪器自证（R-h）设计稿（**只报告**，只写文档） | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/26` | 26 · CI 线交接清单：把「仪器自证」（R-h）接成只报告步骤 | [04-open-work.md](04-open-work.md) §3（只报告步骤接入手册） |
| `15-control-plane-design/27` | 27 · 台阶 5 · 控制面事实表与跨源互证设计稿（**只报告部分**，只写文档） | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `15-control-plane-design/28` | 28 · CI 线交接清单：把「控制面事实表 × 跨源互证」（台阶 5）接成只报告步骤 | [04-open-work.md](04-open-work.md) §3（只报告步骤接入手册） |
| `15-control-plane-design/README` | 第 15 轮 · 控制面重构方案 · 证据归档 | [04-open-work.md](04-open-work.md) §1 / §3 / §5 |
| `reviews/governance-coverage-gaps` | 治理覆盖缺口清单（实测 13 项） | [04-open-work.md](04-open-work.md) §4（13 项缺口） |
| `governance-remediation/00` | 治理覆盖缺口 · 根因分析与修复计划 | [04-open-work.md](04-open-work.md) §4 / §5 |
| `governance-remediation/01` | T1 · hook-chain 实施记录（G2 / G12 / G3 可见性 / G11） | [04-open-work.md](04-open-work.md) §4 / §5 |
| `governance-remediation/02` | T2 · Agent 通道清点（channel inventory）实施记录 | [04-open-work.md](04-open-work.md) §4 / §5 |
| `governance-remediation/03` | T3 rule-fidelity 实施记录（G6 / G7 / G8 / G10） | [04-open-work.md](04-open-work.md) §4 / §5 |
| `governance-remediation/04` | T4 · enforcement-availability 实施记录（G5 / G4 / G9） | [04-open-work.md](04-open-work.md) §4 / §5 |
| `governance-remediation/05` | 治理覆盖缺口 · 独立验收报告（V1） | [04-open-work.md](04-open-work.md) §4 / §5 |
| `governance-remediation/06` | 06 · 独立复跑与对差（第二重验收） | [04-open-work.md](04-open-work.md) §4 / §5 |
| `governance-remediation/07` | 07 · ruff 清理与 N1（多 Agent 依赖口径统一） | [04-open-work.md](04-open-work.md) §4 / §5 |
| `governance-remediation/08` | 08 · N1 独立验收（V1） | [04-open-work.md](04-open-work.md) §4 / §5 |
| `governance-remediation/09` | 09 · V1 十件仪器移入 `tools/` 的收益与风险评估（A1 / task-6） | [04-open-work.md](04-open-work.md) §5、§8 |
| `governance-remediation/10` | N16 / N17 / N20 修复 · 独立验收（V1） | [04-open-work.md](04-open-work.md) §4 / §5 |
| `governance-remediation/11` | 修复轮：N16–N24 的处置与证据（2026-09-26） | [04-open-work.md](04-open-work.md) §4 / §5 |
| `governance-remediation/12` | 修复轮：M1–M5 与 G3/N13/N14 的处置（2026-09-27） | [04-open-work.md](04-open-work.md) §4 / §5 |
| `governance-remediation/13` | 修复轮：07 治理全开轮的 P1–P9（2026-09-27） | [04-open-work.md](04-open-work.md) §4 / §5 |
| `governance-remediation/14` | 修复轮 14：沙箱闭环的归因分类 + 适配器声明版本与宿主的比对（2026-09-27） | [04-open-work.md](04-open-work.md) §4 / §5 |
| `governance-remediation/15` | 修复轮 15：Q6 的归因、Q7 的「待实现」状态、Q8 的尾巴与 D4 的诊断字段（2026-09-28） | [04-open-work.md](04-open-work.md) §4 / §5 |
| `reviews/post-phase-4-hardening` | Post-Phase-4 复核与加固记录 | [04-open-work.md](04-open-work.md) §5 / §6、`docs/project/architecture/术语与口径.md` |
| `reviews/post-phase-5-review` | Post-Phase-5 独立复核记录 | [04-open-work.md](04-open-work.md) §5 / §6、`docs/project/architecture/术语与口径.md` |
| `reviews/post-phase-8-review` | Post-Phase-8 独立验收与修复记录 | [04-open-work.md](04-open-work.md) §5 / §6、`docs/project/architecture/术语与口径.md` |
| `phases/phase-0` | Phase 0：最小规则系统 | [README.md](README.md) 的阶段现状表、`docs/project/architecture/功能清单.md` |
| `phases/phase-1` | Phase 1：Policy Engine | [README.md](README.md) 的阶段现状表、`docs/project/architecture/功能清单.md` |
| `phases/phase-2` | Phase 2：dsh Adapter | [README.md](README.md) 的阶段现状表、`docs/project/architecture/功能清单.md` |
| `phases/phase-3` | Phase 3：规范检索 | [README.md](README.md) 的阶段现状表、`docs/project/architecture/功能清单.md` |
| `phases/phase-4` | Phase 4：Tool Enforcement | [README.md](README.md) 的阶段现状表、`docs/project/architecture/功能清单.md` |
| `phases/phase-5` | Phase 5：代码验证器 | [README.md](README.md) 的阶段现状表、`docs/project/architecture/功能清单.md` |
| `phases/phase-6` | Phase 6：多 Agent Adapter | [README.md](README.md) 的阶段现状表、`docs/project/architecture/功能清单.md` |
| `phases/phase-7` | Phase 7：Policy API | [README.md](README.md) 的阶段现状表、`docs/project/architecture/功能清单.md` |
| `phases/phase-8` | Phase 8：LangGraph 编排 | [README.md](README.md) 的阶段现状表、`docs/project/architecture/功能清单.md` |
| `phases/phase-9` | Phase 9：控制面重构（台阶 −2 → 5，**只报告部分**） | [04-open-work.md](04-open-work.md) §1（未完成项）、[README.md](README.md)（阶段现状） |

**文档内部的问题编号**（它们不是文件名，历史引用里同样会出现）：

| 编号 | 含义 | 现在的落点 |
| --- | --- | --- |
| G01–G13 | 治理覆盖缺口 13 项（级别 + 判定 + 复现命令） | [04-open-work.md](04-open-work.md) §4 |
| R1–R5 | 13 项缺口归并出的五个机制性根因 | [04-open-work.md](04-open-work.md) §4（结论） |
| N16–N28 / M1–M5 / P1–P9 / Q1–Q8 | 历轮实测新显现的问题 | [04-open-work.md](04-open-work.md) §5（仍未修的残留） |
| D1–D12 | 控制面方案的 12 条内部验收偏差 | [designs/控制面重构方案.md](designs/控制面重构方案.md) 附录 B |
| H1 / H4 / H5 / H10 | 状态缺陷：空 `violations`、零测试却记 served、选择期证据被丢、blocker 撤证据 | [designs/控制面重构方案.md](designs/控制面重构方案.md) §11、[04-open-work.md](04-open-work.md) §1.1 |
| L1–L13 / J1–J5 / R-a–R-h | 方案自己的裁决、验收判据与红线 | [designs/控制面重构方案.md](designs/控制面重构方案.md) §5、§10 |
| 台阶 −2 → 5 | 控制面重构的阶段编号（**不是**平台阶段编号） | [04-open-work.md](04-open-work.md) §1.1 |
| T1–T4 / V1 / W1–W7 | 轮次内的分工角色、独立验收与现场事件 | [04-open-work.md](04-open-work.md) §7（引用纪律） |
