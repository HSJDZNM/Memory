# 2026-10-22 题库 k≥3 研讨收敛：10 条主决定 + 6 条附带决定

> **性质**：8 份一次性研讨备忘的收敛读数——只落结论与证据指针，不改判据、不改任何冻结件、不新增协议键。
> **起点**：HEAD `861aad9`、工作树干净、`origin/main` 领先 94、未 push（8 份备忘的共同起点；本轮不 push）。
> **为什么以此文件为准**：原始备忘在一次性现场，cleanup 之后不可读；本文件是它们在受跟踪文件里的唯一权威收敛。
> **引用前**：本文件所有路径与行号都用 read/grep 在本仓库复核过；哈希只在备忘/读数里出现过时引用，并标「历史/当前」。

## 0 性质与边界

一句话：本文件把 8 份一次性研讨备忘（signoff / k3 / freeze / c-axis / digest / fairness / snapshot / index）收敛成一份受跟踪读数，只记录已拍板结论、一句话理由与证据指针。

- **不做什么**：不改判据、不改任务包/隐藏/评分器/注册表、不新增协议键、不跑新实验；本文件是唯一写入。
- **边界**：本文件不替代 `04-open-work.md` / `06-plan-progress.md` 的状态表，也不替代 `testing/ab/bank/README.md`；它回答「决定了什么、为什么、证据在哪」。
- **一次性现场**：审批条子、臂配置、冻结集、探针输出都在 `.tmp` 下（cleanup 会删）；本文件只落结论值与复核方法，不落它们的路径。
- **起点事实**：HEAD `861aad9`、工作树干净、`origin/main` 领先 94、未 push；本轮不 push。
- **同批可见改动**：本文件写作时工作树里已有附带决定 b/c/d 与 errata 的落地（`04/05/06`、`bank/README.md`、`COMMAND-FAMILIES.md`、async/bugfix README、smoke errata、新建 `testing/ab/README.md`）；本文件只记录决策与证据，不重复实现细节。

## 1 已拍板事项

### 1.1 10 条主决定

| 编号 | 事项 | 决定 | 一句话理由 | 证据指针 |
| --- | --- | --- | --- | --- |
| D1 | k≥3 主目标 | k≥3 主目标 = 激活 + 测量有效性门；k≥3 是「仪器/激活轮」，不是「效应估计轮」；没有激活不跑 27 run。 | 5 题都不满足 C1-b 的激活形态，T3 后批次会把模型自写的测试带进 changed 集，A 臂也可能从 `level=none` 变 `level=target`；不先做离线探针就分不清「treatment 无机会」与「未观察到效应」。 | `readings/2026-10-21-c1b-treatment-adjudication.md:192-199`（保住 activation 的已知形态）；`src/validators/selection.py:172-236`（target 支路）；`readings/2026-10-21-bank-five-tasks-hidden-and-ceilings.md:76-81`（k≥3 未跑、需新建实验集） |
| D2 | 3 题选型 | 3 题 = async + docs-config + crossmodule；data-migration 仅作预注册替补；bugfix、旗舰出局。 | docs-config 与 async 覆盖文档/配置与并发两类操作，crossmodule 是唯一 C=30 且构造上无 tools 写面的负对照；data-migration 的 T32 超契约、T31 抓不到断言改弱，只作替补。 | `testing/ab/bank/README.md:11-18`（6 题与类型）；`testing/ab/bank/tasks/bank-docs-config/README.md:178-189`（5 处变异校准 hidden）；`testing/ab/bank/tasks/bank-data-migration/hidden/PLAN.md:106-107`（T31/T32 边界）；`testing/ab/bank/tasks/bank-data-migration/task-package/first-message.md:16`（只有 v2 输出文件写了字节形态） |
| D3 | H1 作者独立性 | H1 = 接受降级 + 第三方逐条可追溯性复核；不重出 hidden；结论限定为「固定 hidden 件下的臂间对比」。 | 6 题（含旗舰）的 hidden 与 reference 由同一子会话按序产出，重出要 2-4 天；复核可审计、成本低，但只能换措辞、换不了独立性。 | `readings/2026-10-21-bank-five-tasks-hidden-and-ceilings.md:50-54`；`06-plan-progress.md:331`（旗舰同作者）；`testing/ab/bank/README.md:111`（§4.3 字面要求）；`testing/ab/dgate2/run-manifest/README.md:33`（H1 只有两个键） |
| D4 | TTL 与签核 | TTL/签核 = 使用者签；TTL 7 天，覆盖窗口+1 天余量；签在受跟踪读数；每臂 2 条 union；frozen_by 由 Lead 签，不等于「可开跑」。 | 批内重签会改 `approval.sha256`，而它是 `platform_generation` 的字段：前后 run 不同代际、不可合并；`frozen_by` 只冻结 T 判据，不能冒充发车许可。 | `testing/ab/bank/README.md` §1 与 §8（TTL 文案；本批已改成物证值 ≤2026-10-22 20:09 +08）；`testing/ab/dgate2/run-manifest/README.md:123`（approval 进 platform_generation）；`readings/2026-10-21-bank-five-tasks-hidden-and-ceilings.md:78` 与 `04-open-work.md:320`（使用者签「可开跑」）；`testing/ab/bank/harness/README.md:162-165`（占位条子拒发车） |
| D5 | acceptance/coverage | acceptance/coverage = C′：立「快照 vs 权威」条款 + 受跟踪读数；不改 task-package 字节。 | 3 题 6 处注记是构造期快照；改一个字节要重生成 manifest/frozen_inputs 与冻结链；立条款 + 读数零字节改动就能消除误导。 | `testing/ab/bank/tasks/bank-crossmodule-refactor/task-package/acceptance.md:6`；`testing/ab/bank/tasks/bank-bugfix-first-failing-test/task-package/acceptance.md:22`；`testing/ab/bank/tasks/bank-data-migration/task-package/acceptance.md:3`、`:6-7`、`:33`；`readings/2026-10-21-bank-five-tasks-hidden-and-ceilings.md:55-58`；`testing/ab/bank/README.md` §4.1（本批新增 C′ 条款） |
| D6 | C 口径与 digest 判据 | C/digest = 只做报告约定，不改 scoring/代码；修 2 处 task README 文本；历史读数只加 errata 注记。 | C 的 27 是有效分母（N/A 不计分不计分母），折算到 30 会改条目权重；整份载荷逐字节比对会因平台树写入与默认 request-id 误判非确定性。 | 6 份 `scoring.yaml` 的 `dimension_c`（`tasks/bank-flagship-returns/scoring.yaml:215-218`、`bank-crossmodule-refactor/scoring.yaml:193-196`、`bank-bugfix-first-failing-test/scoring.yaml:188-196`、`bank-data-migration/scoring.yaml:220-228`、`bank-async-concurrency/scoring.yaml:199-208`、`bank-docs-config/scoring.yaml:198-206`）；`src/policy/check.py:514-516`、`:873`、`:31-39`；`readings/2026-10-21-bank-five-tasks-hidden-and-ceilings.md:35-38` |
| D7 | 冻结面 | 冻结面 = 借 scorer_inputs：`dgate2/configs/{before,after}` + `policies/` + `validation/` + 受跟踪评分器；暂不升 AB_FREEZE_SET 1.1。 | `configs/{before,after}` 是 treatment 的交付路径却不在任何冻结根里（最大冻结洞）；升 `AB_FREEZE_SET_SCHEMA_VERSION 1.1` 要改 freeze_manifest/README/测试/轴表，借 `scorer_inputs` 零代码。 | `testing/ab/dgate2/configs/before/sha256.txt`（`validation/test-layout.yaml` = `69e9d4bb…`）；`testing/ab/dgate2/configs/after/sha256.txt`（`af70bee1…`）；`validation/test-layout.yaml:23-25`；`testing/ab/bank/README.md` §4（冻结规范） |
| D8 | 入口 | 入口 = headless，并写限定；不声称桌面 GUI。 | harness 起的是 `dsh --profile headless`，C4 探针只验证过 headless；05 §1 的目标是桌面 GUI，读数只能写限定。 | `testing/ab/bank/harness/run_session.py:14`、`:980`；`05-implementation-plan.md:23`（桌面 GUI 目标）；`testing/ab/bank/harness/README.md:191-195`；`readings/2026-10-21-C4-steer-probe.md:16`（桌面 profile 未验证） |
| D9 | 记录缺口 | 记录缺口 = 先实现最小 bank run-record（platform_generation + 模型身份 + 起点 HEAD + 三态 sandbox + T/C/A 采集）再跑；不书面放宽。 | `BANK_RUN_MANIFEST_SCHEMA_VERSION 1.1` 未实现、`run.json` 九键不记模型/起点/三态 sandbox；按 bank §4.8「缺任一字段 = 该 run 作废」，书面放宽会把缺口变成惯例。 | `testing/ab/bank/README.md` §4.8（run-manifest 字段）、§7 轴表（1.1 是规划值）；`testing/ab/bank/harness/README.md:109-128`（run.json 九键）；`readings/2026-10-21-experiment-freeze-adjudication.md:203-213`（字段表） |
| D10 | push | push = 不 push。 | 本轮只做读数，不改变远端状态；94 ahead 是起点事实。 | `04-open-work.md:320`（本地提交、未 push）；`git status -sb` 实测 `ahead 94` |

### 1.2 6 条附带决定

| 编号 | 事项 | 决定 | 一句话理由 | 证据指针 |
| --- | --- | --- | --- | --- |
| a | 收敛顺序 | 先把 8 份备忘收敛成这份读数，再动 .tmp。 | 备忘是一次性现场，结论不落受跟踪文件就等于没决定；收敛后再 cleanup 不会丢结论。 | 本文件 §2；`tools/cleanup.py`（cleanup 白名单，只删 .tmp 等） |
| b | 题库索引 | 建 `testing/ab/README.md` 薄索引：链接 + 两轴状态（可开跑：未签｜k≥3：未跑）；不合并成一档。 | 可开跑是人的签核门、k≥3 是实验门，失败原因不同；索引只做导航，不复制计数。 | `testing/ab/` 决策时无根 README（实测）；本批已新建 `testing/ab/README.md`（两轴状态表）；`testing/ab/bank/README.md` §6 决策点 7（索引留给 Lead）；`readings/2026-10-21-bank-seven-adjudications.md:24`、`:36`（留给 Lead、未做） |
| c | 硬文档修正 | 修硬文档：`04:320` 标题/三冻结值/「50 条」、`06` 提交记录、`05 §8` 第 11 条、bank README 的 TTL 文案改成物证 20:09。 | 04:320 同一格并列 37/39 两个摘要还写「未做」，06 漏记 6 个提交，05 §8 第 10 条不含题库；文档与事实不符会被下一次引用放大。 | `04-open-work.md` §5.92（:320，本批已重写）；`06-plan-progress.md` P-MNT-011 / P-MNT-012（:335、:337，本批已补）；`05-implementation-plan.md` §8 第 10 条（:275）与第 11 条（:276，本批新增）；`testing/ab/bank/README.md` §1、§8（TTL，本批已改）；`testing/ab/bank/harness/README.md:13`（55 例） |
| d | 配方与出题纪律 | `COMMAND-FAMILIES.md:101-118` 的三步 `--family` 配方改成手写 union；bugfix `hidden/PLAN.md:10-11` 的优先级改成「首消息/验收表是上限，SPEC 只解释意图」（下一批出题时改，不改已冻结件）。 | CLI 对同一工具是「取代」不是「叠加」，三步 `--family` 只会留下最后一条；SPEC 优先于首消息会造出模型看不到的要求。 | `testing/ab/bank/COMMAND-FAMILIES.md` §7（本批已改成手写 union，旧三步写法保留为反例）；`src/enforcement/cli.py:802-808`（同工具取代）；`testing/ab/bank/tasks/bank-bugfix-first-failing-test/hidden/PLAN.md:10-11` |
| e | 臂配置 | 臂配置 token 化并移出 .tmp；A 臂 `dsh-adapter.yaml` 的机器绝对路径换占位；复用现有 4 份配置，不重跑 `registry --approve`。 | 绝对路径进冻结输入后换机/换目录即失效；4 份配置已审核过，重审会改 approved.json、使既有摘要链全变。 | 一次性现场实测 A 臂 `dsh-adapter.yaml` 的 `policies`/`rules_root`/`registry_root` 是机器绝对路径；`testing/ab/dgate2/run-manifest/README.md:121-122`（摘要进事实）；`readings/2026-10-21-experiment-freeze-adjudication.md:156`（仓库 registry 一个字节不动） |
| f | H2 盲抽 | H2 盲抽预注册：3 题各抽 2 个改动/新增测试文件；data-migration 若入选另加 T31 专项；由不知道臂分配的复核者做，写 run-record.bypass_sampling。 | T31 只数 assert、抓不到「断言改弱」，这是唯一可能带 treatment 偏的漏测；盲抽是把它变成可审计结论的低成本装置。 | `testing/ab/bank/tasks/bank-data-migration/hidden/PLAN.md:106`；`testing/ab/bank/tasks/bank-data-migration/scoring.yaml:256-262`（B2 human_sampling）；`testing/ab/dgate2/run-manifest/README.md:34`（bypass_sampling 形状）；`testing/ab/bank/README.md` §4.8（人工项沿用 H1-H4 记法） |

### 1.3 与备忘建议的冲突（以上表为准）

- 备忘建议未采纳：`k3.md` §2.3 推荐 migration + async + crossmodule；本轮以 docs-config 替 migration——migration 的 T32 超出首消息契约、T31 抓不到断言改弱，3 题放在缺陷更小的题上，migration 只作预注册替补。
- 备忘建议未采纳：`k3.md` §3.5 允许「无激活时仍跑 A/B/C 作治理成本案例」；本轮改为无激活不跑 27 run——k≥3 已被定义为仪器/激活轮，没激活的读数回答不了主目标。
- 备忘建议未采纳：`k3.md` §6.2 的最小路径含「对 bank §4.8 九字段显式放宽并取书面同意」；本轮改为先实现最小 run-record、不书面放宽。
- 备忘建议未采纳：`snapshot.md` §7 推荐 B + C′ + D（改 3 题 6 处注记、重生成 4 处摘要、加自检门禁）；本轮只取 C′——改 task-package 字节会进 manifest/frozen_inputs 与冻结链。
- 备忘建议未采纳：`freeze.md` §1.3 的选项 C（升 `AB_FREEZE_SET_SCHEMA_VERSION 1.1`、加 `judging_inputs` 角色）本轮不做，理由见 D7。

## 2 逐份备忘收敛

### 2.1 k3.md（3 题选型、27 run 预注册、激活缺口）

- **核心结论**：3 题要同时满足「treatment 有机会」与「操作类型覆盖」；27 run = 3 题 × 3 臂 × 3 block，块内臂序平衡（ABC/BCA/CAB）；主判据 T，C/A 只作回归守卫；n=3 只报原值；预注册与停跑规则见 §3。
- **被采纳**：Gate 0 离线激活探针（三选一）；crossmodule 作为负对照；停跑结构（预飞 P1-P5、单 run R1-R6、块间 B1-B2、全轮 W1-W3）；「作废 >1/3 ⇒ 跑不成」；「值得扩试」是结论上限。
- **被搁置/未采纳**：把 migration 放进主组合（改 docs-config，见 D2）；「无激活仍跑作治理成本案例」；对 bank §4.8 的书面放宽；C 臂只跑 k=1 的压缩方案（本轮不预设）。
- **证据指针**：`readings/2026-10-21-c1b-treatment-adjudication.md:192-199`；`src/validators/selection.py:172-236`；`readings/2026-10-21-bank-five-tasks-hidden-and-ceilings.md:76-81`；`05-implementation-plan.md:211`、`:217`；`testing/ab/bank/harness/README.md:186`（单次 run 无重试、无自动重复）。

### 2.2 freeze.md（冻结范围、顺序、TTL）

- **核心结论**：现在不能开跑的不是签名，而是五类机械事实——批内条子会过期、冻结面缺 treatment 快照与 C 的 config root、评分器与 T/C/A 采集器未落盘、harness 1.1 自动化路径未复跑、可开跑签核没有落点。
- **被采纳**：3 份 per-task 实验集（`first_message` 是单文件，1 份装不下 3 题）；冻结顺序（定题 → 使用者签条子 → 建臂配置 → 写 set → freeze --write/--check → scaffold → P1-P6 → dry-run → re-smoke → 可开跑签字）；借 `scorer_inputs`；TTL 7 天；每 run 独立父目录。
- **被搁置/未采纳**：升 `AB_FREEZE_SET_SCHEMA_VERSION 1.1`；把评分器继续留在一次性现场（改为「受跟踪评分器」）；按「换树 = 重签」字面签 6 份（pattern 条子不绑树，按每臂 2 条算）。
- **证据指针**：`testing/ab/dgate2/configs/before/sha256.txt`、`configs/after/sha256.txt`；`testing/ab/bank/README.md` §8（TTL 文案）；`readings/2026-10-21-experiment-freeze-adjudication.md:163`（条子只由使用者签）、`:188`（摘要进 platform_generation）；`src/enforcement/cli.py:802-808`。

### 2.3 signoff.md（可开跑两层、H1 实际作者链）

- **核心结论**：可开跑必须拆两层（题包级 vs 实验级），否则会把「题包可复核」误读成「实验可发车」；H1 的真实范围是 6 题不是 5 题；`hidden_author` 只有 `{author, saw_impl_diff}` 两键会「字面真、整体误导」。
- **被采纳**：使用者签可开跑、Lead 只签 `frozen_by`；签核读数要含摘要集合与 TTL；H1 接受降级 + 第三方逐条可追溯性复核；flag 阈值（>2 或涉核心语义则停/重出该题）；结论写「固定 hidden 件下的臂间对比」。
- **被搁置/未采纳**：对 3 题全部重出 hidden（B）；在 bank run-manifest 里新增 `run_ready` 协议块（本轮先落受跟踪读数，协议与最小 run-record 同批）；对 5 题全签（只签最终 3 题）。
- **证据指针**：`readings/2026-10-21-bank-five-tasks-hidden-and-ceilings.md:50-54`；`06-plan-progress.md:331`；`testing/ab/dgate2/run-manifest/README.md:33`；`testing/ab/bank/README.md` §4.3、§4.8；`04-open-work.md:320`。

### 2.4 c-axis.md（C 口径 passed/effective_total，不折算）

- **核心结论**：C = `passed/effective_total`，并强制同句披露 `nominal_total=30` 与 `not_applicable`；4 题 27/27、旗舰与 crossmodule 30/30；27/27 与 30/30 不能作为数比，只能并排陈述「各自达到声明上限」。
- **被采纳**：不归一化到 30；N/A 四元组（rule/points/basis/observed + denominator）；run-record C 段（score_mode、nominal/effective/passed、not_applicable、rules、files、segments、drift、determinism）；不升 `bank-scoring/3`，只改报告约定。
- **被搁置/未采纳**：`display_only` 的 30 折算；把 `effective_total` 纳入 `frozen_inputs`（会改 scoring 形状）；把 N/A 记 0 或记 3。
- **两处 task README 修正（2026-10-22 已按拍板直接修正）**：`tasks/bank-async-concurrency/README.md:292` 原写「得 30」→ 已改为「C 按 passed/effective_total 读（27/27）；不折算成 30」；`tasks/bank-bugfix-first-failing-test/README.md:11` 的 C 口径 → 已改为「C 27/27（effective_total=27；ARCH-001 N/A 3 分不计分不计分母）」。
- **历史读数 errata（2026-10-22 已加注记）**：`readings/2026-10-21-bank-flagship-abc-smoke.md` §7——30 分分解应为 8 规则×3 + 冻结 3 + 旁路 3 = 30。
- **不计为 errata**：`tasks/bank-bugfix-first-failing-test/README.md:204` 的「C 27」是**加权分列**、不是折算。
- **口径**：历史读数只加 errata 注记；题 README 的两处文字按拍板直接修正。
- **证据指针**：6 份 `scoring.yaml` 的 `dimension_c`（D6 行内列了行号）；`src/policy/check.py:514-516`；`readings/2026-10-21-bank-five-tasks-hidden-and-ceilings.md:35-38`；errata 与两处 README 修正的原文位置见本节第 4-6 条；`testing/ab/dgate2/scorer/scorer.yaml:522-535`（区分力只在 T）。

### 2.5 digest.md（整份载荷逐字节不是判据）

- **核心结论**：`reading_context.tree.digest` 是被遍历树的确定性函数（逐文件 sha256 排序后再 sha256），遍历顺序不是输入；「同输入两次不同」最可能是两次读数之间树被写了，不是摘要函数非确定。
- **被采纳**：先配对 provenance（同 argv 含固定 `--request-id`、rule_set、declarations、tree.digest+revision 全相等），再比决策面（result + check_volume + exit_code + evidence）；tree.digest 不同 = 输入树不同，不算 nondeterminism；run-record 只记 provenance 四元组。
- **被搁置/未采纳**：改 scoring 的 `invalidation.nondeterminism` 文本（等下一次 `bank-scoring/3` 与 C 口径合并）；把 tree 锚到 `--workspace`（会升 `OUTPUT_SCHEMA_VERSION` 并使历史读数不可比）；改 `DEFAULT_EXCLUDES`。
- **证据指针**：`src/policy/check.py:31-39`（默认 request-id 每次不同）、`:873`（tree 取 anchor）；`src/provenance/reading_context.py:325-376`；`testing/ab/bank/README.md:150-154`（作废条件）；`readings/2026-10-21-bank-five-tasks-hidden-and-ceilings.md:59-61`（未复现报告）。

### 2.6 fairness.md（5 题 SPEC 偏差与对 T 解释力的影响）

- **核心结论**：逐条裁决 12 项——1 项超契约（data-migration T32 对 7 个新建文本文件的编码/BOM/换行检查）、7 项契约内可推导、3 项 hidden 比契约窄、1 项非判据（参考解更严）；全部「接受并披露」，仅 T32 附条件。
- **被采纳**：不改 task-package/SPEC；T32 若该题入选则只改 hidden 收窄（本轮 migration 是替补，条件写进 Gate 0）；bugfix `hidden/PLAN.md` 的判据优先级下一批改成「首消息/验收表是上限」；data-migration T31 归 H2 盲抽。
- **被搁置/未采纳**：删 T21（async 的唯一跨 worker 行为面）、加严 T05（会让 crossmodule 不可解）、给 T08 加嵌套隔离判据、重写 5 题 SPEC。
- **对 k≥3 的影响**：三臂共享同一 hidden 与同一首消息，偏差是共模、不产生臂间偏；但 T 是唯一有区分力的维度，报告必须按「每题一条轴 + 已知边界」写——T 满分不等于契约全满足（T08 漏测嵌套隔离、T27 只要求「出现即过」、T31 只数 assert），不许把 T 满分写成「完全满足契约」。
- **证据指针**：`testing/ab/bank/tasks/bank-data-migration/hidden/PLAN.md:106-107`；`testing/ab/bank/tasks/bank-docs-config/README.md:178-189`；`testing/ab/bank/tasks/bank-bugfix-first-failing-test/hidden/PLAN.md:10-11`；`testing/ab/bank/tasks/bank-crossmodule-refactor/task-package/acceptance.md:6`；`readings/2026-10-21-bank-five-tasks-hidden-and-ceilings.md:63-74`。

### 2.7 snapshot.md（acceptance/coverage 是构造期快照）

- **核心结论**：3 题 6 处「隐藏尚未落盘/未冻结」是构造期快照，被 `manifest.sha256` 钉住；现在是最便宜的窗口（5 题不在任何冻结集、无 run 可作废）；哈希链只有一个硬门禁（run 前的 `freeze_manifest --check --strict`）。
- **被采纳**：立「快照 vs 权威」条款——状态只认 `scoring.yaml` 的 `dimension_t` 与题 README 的「天花板读数」节；`coverage.md` 保留状态块但收窄措辞（只作废「状态类」措辞，不碰「证据等级类」）；受跟踪读数记录该条款；不改 task-package。
- **被搁置/未采纳**：改 6 处注记并同批重生成 manifest/README/scoring 摘要；只读自检门禁（D）——等 3 题进冻结集时与重冻同批做，避免今天必红。
- **证据指针**：`testing/ab/bank/tasks/bank-crossmodule-refactor/task-package/acceptance.md:6`；`tasks/bank-bugfix-first-failing-test/task-package/acceptance.md:22`；`tasks/bank-data-migration/task-package/acceptance.md:3`、`:6-7`、`:33`；`readings/2026-10-21-bank-five-tasks-hidden-and-ceilings.md:55-58`；`testing/ab/bank/README.md` §4.1。

### 2.8 index.md（文档硬状态清单、两轴索引）

- **核心结论**：决策时 `testing/ab/README.md` 不存在（`bank/README.md` §6 决策点 7 指向它）；04/06/05 至少 10 条状态与事实不符；可开跑没有机器可读落点；「待使用者签」不能压成一个状态字。
- **被采纳**：薄索引（链接 + 两轴状态 + 权威指针，本批已建 `testing/ab/README.md`）；`04:320` 重写（标题/当前冻结值/55 例/3 题未选）；`06` 补提交记录；`05 §8` 新增第 11 条；bank README **部分采纳**：TTL 物证值 + §4.1 快照条款已落；六行状态统一留到 k≥3 前的一次性状态收口。
- **被搁置/未采纳**：新建 `BANK_TASK_STATUS` 独立状态轴；把「可开跑」塞进 `scoring.yaml`（会动 `bank-scoring/2` 轴）；k≥3 前 push（R8 的备选，本轮不采纳）。
- **证据指针**：`04-open-work.md` §5.92（:320）；`06-plan-progress.md` P-MNT-011 / P-MNT-012（:335、:337）；`05-implementation-plan.md` §8 第 10/11 条；`testing/ab/bank/README.md` §1、§6 决策点 7、§8；`testing/ab/README.md`（本批新建，两轴状态表）。

## 3 k≥3 门与预注册

### 3.1 Gate 0（离线激活探针）

- **方法**：照 `readings/2026-10-21-c1b-treatment-adjudication.md:81-94` 的离线复现法——用 `python -m policy.check`（不是真机 Hook），在每题基线树副本上按 `milestones.md` 的写序列模拟 changed 集；A 臂读 `dgate2/configs/before`（`test-layout.yaml` sha `69e9d4bb…`），B 臂读 `configs/after`（`af70bee1…`）；逐序列比对 `decision` / `violations` / `served_checkers` / `selection.level` / `check_failed`。
- **三选一**：激活（至少一条真实写序列 A 与 B 的 decision 或 served/level 不同且方向可解释）/ 方向反转（差异存在但与设计意图相反，预注册方向改成双侧并写明「与预期相反」）/ 无激活。
- **通过条件**：≥2 个被选题显示激活机会（因为 crossmodule 不应有激活，等价于 async 与 docs-config 都显示机会）；crossmodule 负对照无激活——它的允许写里没有 `tools/`（`testing/ab/bank/tasks/bank-crossmodule-refactor/task-package/allowed-writes.txt`），按构造不应有 treatment 差异；async 无激活即停；docs-config 无激活且 data-migration 有激活才允许替换。
- **替换条件**：替换前必须收窄 T32（hidden-only：只对 `data/ledger-v2.jsonl` 判 UTF-8/LF/无 CR/恰一个换行，其余 7 个文本文件只要求存在且 UTF-8 可解码）、重算 hidden 摘要、重冻结。
- **未过的处置**：不跑 27 run；写「无激活/跑不成」+ 原因 + 复现指针；不得把无激活读成「treatment 无效」。

### 3.2 H1（降级 + 逐条复核）

- **降级事实**：6 题 hidden 与 reference 同作者（先 PLAN/runner、跑基线红、后 reference；旗舰亦同）；docs-config 还有「看参考树变异失败后把 T17 从 4 类扩到 7 类」的文本证据。
- **复核方式**：另一个未参与子会话（使用者授权、Lead 复核）逐条审 hidden：每条判据能否指到 first-message 的句子或 acceptance 的 A#；用「只满足首消息字面」的替代实现/变异做探针；出 keep/fix/exclude。
- **flag 阈值**：单题 flag 用例 >2 或涉及该题核心语义 → 停/重出该题 hidden；≤2 且可定点修 → 修 hidden + 重算摘要 + 重冻；3 题若混搭，结论必须写「混合独立性」。
- **措辞上限**：只写「固定 hidden 件（hash 见签核读数）下的臂间对比」；不写「独立出题」，不写「T 绝对值证明 SPEC 完备或独立可解」。

### 3.3 TTL（7 天 + 物证值）

- **7 天**：从重签日（2026-10-22）起算，覆盖整个 k≥3 窗口 + 1 天余量；`max_uses` 保持 1000（台账每棵树重置）。
- **物证值**：4 条记录 `expires_at = 2026-10-22T12:09Z`（+08 20:09）、`granted_at = 2026-10-21T12:09Z`、TTL 86400s；每臂 2 条——`approval-run-code` + 三族并成一条的 `approval-pwsh-all`（union）。2026-10-22 08:49 +08 复核时**尚未到期**，但 TTL 只到今晚，覆盖不了 k≥3 窗口（7 天），因此必须重签。
- **文档 19:55 是旧值**：决策时 `testing/ab/bank/README.md` §1/§8 写 19:55 +08；本批已改成物证值「≤2026-10-22 20:09 +08（`approval.json` 的 `expires_at=2026-10-22T12:09Z`；文档旧值 19:55 作废）」。
- **批内重签 = 换代际**：`approval.sha256` 是 `platform_generation.declarations.approval` 的字段，前后 run 不可合并；所以 TTL 必须一次签到底。
- **签核落点**：受跟踪读数（本目录）写 `signed_by`、`signed_at`、`expires_at`、`scope`（3 个 task id + 3 份 freeze 摘要 + 臂配置/审批/test-layout 摘要）；`frozen_by` 只由 Lead 填，表示 T 判据冻结。

### 3.4 冻结面（借 scorer_inputs）

- **3 份 per-task 实验集**：每份 = 该题任务目录 + 共享 A/B 臂配置 + 该题首消息 + `scorer_inputs`；3 份各自 `--check --strict` PASS 并记 3 个 combined_digest。
- **`scorer_inputs` 内容**：`testing/ab/dgate2/configs/before`、`configs/after`（treatment 交付路径）、`policies/`（43 条规则）、`validation/`（9 个文件）、受跟踪的 T/C/A 采集器（评分器）。
- **不升 `AB_FREEZE_SET_SCHEMA_VERSION 1.1`**：升版要改 freeze_manifest/README/测试/轴表（AGENTS 55）；本轮借 `scorer_inputs`（0 代码改动），角色含义写在读数里。
- **参考解不进冻结根**：它是天花板读数对象、不是 run 输入；其哈希由读数/run-record 记，不能靠 freeze 守。
- **顺序**：定题 → 使用者签 4 条 → 建臂配置（token 化）→ 写 3 份 set → `--write`/`--check --strict` → scaffold 9 树 → P1-P6 → dry-run → re-smoke → 可开跑签字 → 27 run。

### 3.5 记录缺口（先实现再跑）

- **现状**：`BANK_RUN_MANIFEST_SCHEMA_VERSION 1.1` 是未实现的规划值；bank `run.json` 九键不记模型、起点 HEAD、三态 sandbox、T/C/A；按 bank §4.8「缺任一字段 = 该 run 作废」。
- **最小 run-record 字段**（新轴首版 1.0）：`platform_generation`（`host.entry`/`dsh_runtime`/`dsh_source`/`profile`/`file_policy`/`session_sandbox`/`sandbox` 三态；`declarations.{adapter_config,registry,approval,test_layout}` 摘要；`batch_ledger`；`audit_schema_version`；`pre_evidence`/`timeouts`；`model.id`+params；`start.head`/`worktree_clean`；`run.serial`）。
- **T/C/A**：T 记 passed/total/case_ids/exit/两次输出同字节；C 记 score_mode、nominal/effective_total、passed、`not_applicable[]`（含观测）、`rules[]`、`files[]`（含 check_volume / skipped_rule_ids / skipped_by_reason）、`segments`（rules+frozen+bypass）、`drift`、`determinism`；A 记 10 谓词逐条。
- **过程读数**：batch 10 键 + settlement、`selection.level`、`served_checkers`、post 按 pre decision 分列、invalid/degraded、B1-B3。
- **模型身份**：只从 profile 的 `agent-default-model`（provider/model）与 session header 取；读不到写「未记录」，不得写「同一模型」。

### 3.6 入口（headless 限定）

- harness 的 argv 是 `dsh --profile headless`（`run_session.py:14`、`:980`），C4 探针只在 headless 成立、桌面 profile 未验证（`readings/2026-10-21-C4-steer-probe.md:16`、`:184`）；05 §1 的目标是桌面 GUI。
- 所有读数固定写「headless 入口，不回答桌面 GUI」；`host.entry` 写实，不得把 headless 写成 desktop。

### 3.7 结论上限（n=3）

- **能写**：每题每臂 3 个原值；block 级 δ 的正/零/负计数；机制描述（阻断规则集合、`selection.level`、`served_checkers`、batch 形态）。
- **不能写**：均值/中位数/百分比/区间/显著性/p 值、「有效」「证明」、因果归因、换任务/模型/宿主的外推、跨题总分。
- **treatment 效应**：只有每臂 3 个有效 run 且过预注册才可写，上限是「值得扩试」，不得升级为「有效」。
- **合法结论**：「跑不成」「天花板受限」「无激活/无机会」都必须写原因与复现指针。

## 4 剩余开放项

| # | 项 | 为什么还没做 / 卡在谁 |
| --- | --- | --- |
| 1 | 使用者重签 4 条审批 | 只有使用者能签（AGENTS 14；`readings/2026-10-21-experiment-freeze-adjudication.md:163`）；4 条记录 `expires_at=2026-10-22T12:09Z`（+08 20:09），2026-10-22 08:49 +08 复核时尚未到期，但 TTL 只到今晚，覆盖不了 k≥3 窗口（7 天），因此必须重签；且重签会改 `approval.sha256`，必须与重冻、重脚手架同批做。 |
| 2 | 可开跑签核 | 需要 3 份 freeze 摘要 + 臂配置/审批 sha + Gate 0 + H1 复核结果；落点是本目录的受跟踪读数（D4）；先由 Lead 填 3 题 `frozen_by`，再由使用者签。 |
| 3 | Gate 0 | 3 题与 milestones 已定，但离线探针要按写序列逐条跑；卡在 Lead（只读执行，不需要真机）。 |
| 4 | H1 复核 | 需要另一个未参与子会话、使用者授权、Lead 复核；卡在 Lead 排期与使用者授权。 |
| 5 | 3 份 exp-set | 依赖 token 化后的臂配置与签好的条子字节；卡在重签（第 1 项）。 |
| 6 | 臂配置 token 化 | 一次性现场的 A 臂配置含机器绝对路径（`policies`/`rules_root`/`registry_root`），改字节 = 重冻结；卡在 Lead 与「移出 .tmp 的落点」决定。 |
| 7 | 最小 bank run-record + T/C/A 采集器 | 新工具 + 新轴（`BANK_RUN_RECORD_SCHEMA_VERSION` 1.0），要先定字段与版本轴；卡在 Lead 排期。 |
| 8 | freeze×3 | 依赖第 5、6、7 项；三次 `--check --strict` 必须全过并记摘要。 |
| 9 | scaffold 9 树 | 依赖 freeze；每 run 独立父目录（`reset-manifest` 一父目录一份）。 |
| 10 | P1-P6 探针 | 依赖臂树；P1（条子过期）现在必红，必须等重签。 |
| 11 | dry-run | 依赖 scaffold + 探针；dry-run 绿不证明条子可用（只看占位与结构）。 |
| 12 | 1 臂 re-smoke | 依赖 dry-run + 使用者注入凭据；harness 1.1 的自动化路径在新代码上未复跑（`testing/ab/bank/harness/README.md:191-195`）。 |
| 13 | 27 run | 依赖第 1-12 项全绿且 Gate 0 有激活。 |
| 14 | H2 抽样 | 跑完后按预注册抽样；抽样者不得知道臂分配；写 `run-record.bypass_sampling`。 |
| 15 | data-migration T31 专项（若替换） | 只有 Gate 0 判定 docs-config 无激活、data-migration 有激活并替换时才做；替换前收窄 T32、重算 hidden 摘要、重冻。 |

## 5 纪律

- **允许句示例**：「在 3 个冻结任务、每臂 3 次 run、app 自带 dsh 0.2.1-rc.2、headless 入口、同一模型身份（记录见 …）下，A/B 的 T 原值逐次为 …；按预注册判定为值得扩试 / 未观察到一致方向」；「跑不成：原因 + 复现指针」。
- **禁止句**：「平均提升 X%」「显著」「有效」「证明」「A 比 B 好」；「T 满分 = 契约全满足」；「C 满分 = 30/30」；「隐藏独立出题」；跨题总分。
- **不写**：绝对路径、凭据值、时戳/耗时（耗时只进 run 日志）；日期只写证据性期限（如 `expires_at`）。
- **不改**：任何已冻结件（`testing/ab/dgate2/**`、题包、`baseline/`、`hidden/`、`scoring.yaml`、`testing/ab/dgate2/configs/**`）；要改先重冻并写明旧 run 作废。
- **不跑**：`ci_local`、真机 dsh、新实验；本轮只读 + 只写本文件。
- **哈希标注**：`2028dd5c…` 是旗舰实验集收口时的历史值（39 条），新建 3 份 set 后会换值；`3d54a9f8…` 是冒烟现场的历史值；`69e9d4bb…`/`af70bee1…` 是 A/B 两臂 `test-layout.yaml` 的当前配置值（随 `configs/{before,after}` 冻结）。
