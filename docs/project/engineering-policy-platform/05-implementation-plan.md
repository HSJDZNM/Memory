# 05 · 实施计划：从「动作判定」到「产物判定」

> **状态**：2026-10-17 编制，依据 HEAD f023b8e（工作树干净）。
> **定位**：把「在 dsh GUI 里做开发任务时，所有产出代码被自动审验、最终代码规范」这个目标，拆成可执行、可回退、可证伪的阶段。
> **强度声明**：本文件是计划，不是读数。凡引用数字都注明出处；凡未验证的推断都标「待验证」。
> **记录落点**：执行过程中的每条记录写进 06-plan-progress.md（格式见该文件），不在本文件追加读数。

---

## 0 这份文件回答什么

1. 目标在今天的系统里卡在哪（事实基线）。
2. 上一轮标为「未知」的六件事，现在查清了什么（第 3 节）。
3. 按「冻结内 → 窄口径解冻 → 协议扩展 → 实验」四段，先做什么、后做什么、每阶段的门是什么。
4. 对比实验怎么设计，以及它**不能**证明什么。

**不回答**：具体代码怎么写（那属于各任务的提交）；实验结论（还没跑）。

---

## 1 目标与成功判据

**目标**：在 dsh 桌面 GUI 的代码开发任务中，**所有产出的代码都被审验**，且**最终代码符合规则集**。

拆成三条可判定的成功判据：

| 编号 | 判据 | 判定方式 |
| --- | --- | --- |
| G1 | 覆盖：任务产生的每个文件变化，都能找到一次判定记录或一次显式「未覆盖」声明 | 从账本与树对账，不看模型自述 |
| G2 | 正确：最终树上规则集的 error 级违规为 0；warning 有清单 | 用**只读参照树**的判定器在最终树上量，不读被评臂自己的账本 |
| G3 | 可解释：每个被拦的动作都能读到「哪条规则 / 哪个原因码 / 哪棵树」 | 抽样复核判定记录 |

**反目标**（明确不做）：不追求「每一次中间编辑都完美」；不追求「命令类动作全部可自动执行」；不追求「统计显著」。

---

## 2 事实基线（2026-10-17）

### 2.1 规模与结构

| 项 | 读数 | 出处 |
| --- | --- | --- |
| 规则集 | 43 条 / 1,458 行；5 个 checker；**39 条共用 style_lint（Ruff）**；可阻断 24 条（21 条 Ruff 码 + 3 条语义） | 本次实测（解析 policies/**.yaml） |
| 判定路径 | 核心判定 4,943 + 取证 5,982 + 执行治理 9,356 + dsh 适配器 6,453 ≈ **26,700 行**（规则集的 18 倍） | 本次实测（按包统计 LOC） |
| 判定点 | 一次 edit 穿 13 道编号闸、约 46 个判定点；ReasonCode 37 值；hooks 侧 24 个 reason_code 里 15 个不在枚举内 | 本次实测 + 04-open-work |
| 声明面 | src 30 根版本轴（含 tools 共 50 根）；22 对重复声明（7–8 对无守门） | 本次实测 |
| 包级依赖 | policy 与 validators 有环，但只经 CLI 包装层（policy/check.py 顶层 import，带 noqa）；核心模块层干净；**没有 import-linter** | 本次实测（AST 依赖图） |
| 存量账本 | Governance 工作区 audit 12,868 行 / 18.66 MB；ledger 552 行 | 本次实测 |

### 2.2 已登记的缺口（与本计划直接相关）

| 编号 | 一句话 | 本计划落点 |
| --- | --- | --- |
| 5.46 | 批次/意图无法表达 | 阶段 C1 |
| 5.68 | 证据只有「服务过/失败关闭」两态 | 阶段 C2 |
| 5.69 | 审批按参数形状两向严格，GUI 里无法稳定预放行 | 阶段 B1 |
| 5.70 | 只读命令族不受 path_scope 约束 | 阶段 B3 |

### 2.3 仓库存量冻结令

摘自 04-open-work.md 第 1.4 节：**不改判定路径**（policy.engine.evaluate 判定逐字节不变）、**不新增加载期 FATAL**、**不新增阻断步骤**、**不改任何退出码**（升格前）。

⇒ 任何改变 allow/block 的改动，必须**先解冻**并交 **R-d 字段级差集**（见 3.5）。本计划按此把任务分成三段（第 4 节）。

---

## 3 未知项补齐（本轮新增）

> 上一轮交付里标为「不确定」的六件事，逐条查证如下。**查证方式**：读仓库源码、读宿主实现的 asar 归档、读存量配置；除特别说明外**未跑任何闭环**。

### 3.1 宿主 Stop 语义：可「反对」但不能「block」

**查到的事实**（来源：dsh 安装目录 app.asar 内 @deepseek-ai/dsh-agent-loop/lib/index.js 与 dsh-tool-cordis/lib/types/api-catalog.js）：

- 宿主确实在回合收尾前派发串行事件 agent/turn-stopping，参数是 { agent, turn, signal }。
- 该事件的约定**不是**返回 decision: block。API 目录原文：监听方「a listener that objects steers (agent.steer(...)) and the machine re-reads its inbox: fresh steering runs another step, none closes the turn.」
- 也就是说：**想阻止回合结束，要在监听器里调用 agent.steer(...) 注入一条新指令**，宿主会重读收件箱并再跑一步；没有拦截返回值。
- 平台侧现状：仓库的进程内插件只注册了 tools/pre-execute 与 tools/post-execute（policy-hook.plugin.mjs:669 / :678），**没有订阅 agent/turn-stopping**。

**对计划的影响**：

1. 「回合末门禁」在宿主能力上**存在可行路径**（订阅 + steer），但需要插件新增一种能力。**2026-10-21 真机验证（C4 探针）**：在已安装宿主（app.asar 内 bundled dsh **0.2.1-rc.2**）上，`agent/turn-stopping` 到达监听器、`agent.steer` 是函数，注入后宿主重读收件箱并在同一回合多跑一步；两例门（有/无未结清）在 headless 真机成立，**宿主自身没有注入次数上限**（C 例 step 1→2→3）。**desktop profile 未验证**（探针只跑 headless + 隔离 `DSH_HOME`）；读数见 `readings/2026-10-21-C4-steer-probe.md`。
2. 因此它不进阶段 A/B，放在阶段 C，「待验证 + 待裁定」。
3. 在它落地之前，「未结清清单」只能**只报告**（写进审计与 UI），不能阻断收工。

### 3.2 审批「两向严格」的确切位置与参数域改法

- 判定位置：src/enforcement/approvals.py 的 verify_approval，第 556–579 行：
  - 声明的参数不在请求里 → 拒（:558-561）；
  - 取值不匹配 → 拒（:563-567）；
  - 请求里出现未声明的参数 → 拒（:572-579）。
- 选择位置：select_approval 的 shape_matches（:412-431）用 set(params) != set(record.param_patterns) 只做「出示哪张条子」的排序，不是拒绝理由。
- **参数域改法**（阶段 B1）：
  1. 对「注册表声明为可选、且有默认值」的参数（如 workdir / timeoutMs），允许条子**不逐格声明**，按默认值补齐后参与匹配；
  2. 请求里出现未声明且**没有默认值**的参数，仍然拒；
  3. run_in_background=true、白名单外命令、未知参数三条负例**必须仍然拒**；
  4. 审批协议 1.2 → 1.3（新增「参数域」语义），旧记录照常读。
  5. **默认值只给驱动真的按「缺席等价」读的三个参数**（`exec.pwsh` / `exec.bash` 的 `timeoutMs=60000` / `workdir="."` / `run_in_background=false`）；`sandbox_permissions` / `justification` **故意不给默认值**——平台从不把「缺席」当作 workspace-write 或空理由，给默认值会在审批域里说一句不真实的话。
- **代价**：这是**放宽**，必须交 R-d 差集，且负例要有用例钉住。

### 3.3 批次状态的可行性

- 进程模型：Hook 每次工具调用是一个**新进程**（run_hook 一次装配一次退出），因此批次状态**必须落盘**，不能放内存。
- 建议落点：<受治项目>/.policy/pre-evidence-batches/<session_id>.jsonl，追加写、按 session 分文件；判定记录里带 batch_ref 摘要。
- 预算：现有 hooks.json 的 timeout = 30s；pre_evidence.timeout_ms = 20000；dsh-adapter.yaml 的 timeout_ms = 5000 ⇒ 20000 + 5000 < 30000 成立。批次判定若要额外跑测试，必须重新给不等式。
- 风险：并发会话共用同一 .policy/ 时，批次文件会互相污染 ⇒ 必须按 session 分文件 + TTL + 显式 settled / abandoned 状态。

### 3.4 覆盖表的数据格式（对齐现有两张表）

- 现有两张「只报告」表的格式：
  - validation/control-plane-facts.yaml：schema_version + facts 行（key / authority / canonical_ref / consumers / predicate / severity / remedy / on_unprovable / expires），**不放值、不判罚**。
  - adapters/wiring-scope.yaml：schema_version: "2" + 通道条目（decision / kind / owner / covers / reason / consequence / expires_at / renewals / governs_tree / tree_ref）。
- 新表 validation/channel-coverage.yaml 采用同族写法：
  - 自带 schema_version: "1"（新文件第一次出现就建轴）；
  - 每行 = channel × tool × mode × check_id × coverage，coverage ∈ {enforced, declared_uncovered, not_applicable}；
  - 必须带 owner / reason / expires_at（防「永久空白支票」）；
  - 只放指针，不放读数；与 control-plane-facts.yaml 用 covers_facts/反向引用连接键咬住。
- 红条件（只报告工具里算）：row_without_mode / mode_without_check / tool_with_hits_without_row / registry_digest_drift。

### 3.5 R-d 字段级差集的操作方法

- 定义（designs/控制面重构方案.md:212）：**任何改变 decision 的步骤必须交出字段级差集，含 violations 内容，不只 decision 值。**
- 可用的固定输入：
  - 决策快照：tests/fixtures/decisions/{allow,warning,block,approval}.json（4 份）；
  - 组合语料：tests/fixtures/rules/_combinations/cases/{conftest-alone,conftest-with-implementation,tests-only}.yaml；
  - 正反例夹具：tests/fixtures/rules/<ID>/{good,bad}.py。
- **操作要求**：差集工具必须**入库**（或至少是可复现脚本），不能像台阶 3b 那样只留在 .tmp（.tmp 会被 cleanup 删，见 5.32/5.33）。
- 差集输出三列：added / modified / removed，每条带 fixture → 字段 → 前值 → 后值。

### 3.6 存量锁与到期（开跑前必须处理）

- 实验必须用**独立 .policy** 或记录起止偏移，不能共用存量审计（§2.1 的账本行数只是当时读数，会继续增长）。
- 审批条子到期必须显式重签并记哈希（不许静默续期）；签发只能由使用者执行，代理不得自签（AGENTS 第 14 条）。
- 桥必须指向当前臂，并做一次正向对照（真实 PreToolUse 命中且 `governed=true`）。
- 取证/批次预算按 §3.3 的不等式核对：`pre_evidence.timeout_ms + timeout_ms < hooks.json 的 timeout`。

---

## 4 分阶段计划

> 统一字段：编号 / 内容 / 改动面 / 人日 / 门 / 回退 / R-d / 状态。
> 人日为单人工时估算，来自本轮子会话的分解；**不是承诺**。

### 阶段 A · 冻结内（只报告，不改任何 allow/block）

| 编号 | 内容 | 改动面 | 人日 | 门 | 回退 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | 覆盖表：把「哪个通道 × 哪个工具 × 哪种治理 × 哪条检查」变成可查询的行；桌面通道从 out_of_scope 改判 | 新增 validation/channel-coverage.yaml；tools/control_plane_facts.py 消费 + 四格红条件；adapters/wiring-scope.yaml 一条改判；validation/control-plane-facts.yaml、validation/instrument-checks.yaml 连接键；新增契约用例 | 5.5 | 表可加载；**删掉某工具的最后一行 / 全部行的变异必红（工具级红键）**；每个有审计命中的工具都有行；引用完整性 0 红格 | wiring-scope.yaml 改回一行；表读数 not_applicable | 已落地（2026-10-18，9806031；门禁绿） |
| A2 | 5.71 探针：delegated 支路在「干净树/脏树 × 空/非空输出」四种形态下的 post 证据 | 只跑探针，不改代码 | 0.5 | 能定性为「能力边界 / 假阳性 / 真阳性」之一；三种结论都要带读数 | 无（只读） | 已落地（2026-10-18；定性真阳性） |
| A3 | 干跑四数：受治臂跑一遍任务，只量 ① 写动作治理覆盖率 ② 命令族成功率 ③ 任务触碰路径族是否都已声明 layer ④ 是否上下文触顶 | 只读；需要一份任务包 | 0.5 | 4/4 通过 ⇒ 阶段 D 成立；任一不过 ⇒ 先修构造，不跑两臂 | 无 | 已执行（2026-10-18）：v2 4/4 + 任务完成；D 校准门通过；A/B/C 已于 2026-10-20 各跑一次（readings/2026-10-18-A3-dryrun-v2.md、readings/2026-10-20-D-gate2-ab-c-runs.md；前置见 04 5.78） |

**阶段 A 的退出条件**：A1 的变异证明通过、A2 有定性结论、A3 四数齐备。三者缺一，阶段 D 不开跑。

### 阶段 B · 窄口径解冻（每项必须交 R-d 字段级差集）

| 编号 | 内容 | 改动面 | 人日 | 门 | 回退 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| B1 | 审批签「参数域」：注册表声明的可选参数按默认值覆盖；族从注册表生成 | src/enforcement/approvals.py（1.2→1.3）、precheck.py（默认值补齐）、cli.py（approve --family）、registry/tool-registry.yaml（command_families）、tools/approval_allowlist_audit.py（--check）、契约用例 | 4 | 9/9 命令通过；三条负例（未知参数 / run_in_background=true / 白名单外命令）仍拒；approval_allowlist_audit --check 0 命中 | 审批文件换回逐格三条；1.3 分支无记录触发 | 已落地（2026-10-20，fe292b9）：读数 `readings/2026-10-20-B1-param-domain.md`；夹具矩阵 9/9，真实受治会话 9/9 待使用者签 1.3 条子；残留见 04 5.83 |
| B2 | 测试支撑声明：test_support_patterns + selection 消费 | validation/test-layout.yaml（v1→v2）、src/validators/selection.py（PIPELINE_SCHEMA_VERSION 1.3→1.4）、conftest-alone.yaml 显式翻面、用例 | 3.5 | conftest-alone 翻绿且 failing_tests 进 served_checkers；真实 Hook edit conftest.py exit 0；5 类反例仍 block | 删除 test_support_patterns、版本回 v1 | 已落地（2026-10-18，47fa325） |
| B3 | 只读命令族读面闸门 | registry/tool-registry.yaml（read_guard 数据）、src/enforcement/precheck.py（新检查）、models.py（新 reason code）、用例 | 3 | 3 条越界形态被拦；合法命令 0 误伤（400 份真实会话回放） | 删 read_guard 数据 | 已落地（2026-10-20，9a88112）：读数 `readings/2026-10-20-B3-read-guard.md`；7 条新拦 / 8 条合法 0 误伤；400 份真实会话回放**未取得**；残留见 04 5.86 |

**阶段 B 的纪律**：三项各自单独提交、单独差集；**不许合并成一次「方案包」提交**（否则 B2 的归因会被 B1 掩盖）。

### 阶段 C · 协议扩展（单独立项，每项先裁定后动手）

| 编号 | 内容 | 前置 | 人日 | 门 | 状态 |
| --- | --- | --- | --- | --- | --- |
| C1 | 批次台账：未结清集合进判定输入 | B2 落地；协议升版 | 5 | 三步（实现→测试→conftest）逐步 decision 与合并判定相等；批次能被显式 settle/abandon | **C1-a 已落地**（2026-10-21，05a05d5，只报告：批次落盘 + 审计 `batch_ref`，批次不进 evaluate；审计 1.3→1.4）；**C1-b（批次进判定）待裁定**，残项见 04 5.88 |
| C2 | 证据第三态（不适用） | 书面裁定 + EVIDENCE/PIPELINE 升版 + 到期日 | 3 | 「同一输入从 block 变 allow」的用例；反例一条不放宽 | 待裁定 |
| C3 | 最终树门禁 + 规则集哈希钉住 + 危险动作前置阻断 | 无（可独立） | 5 | 门禁能对整棵树跑 43 条 + 真实验证器；规则集被改能被发现；删除/执行/控制面写被前置阻断 | **v1 已落地**（2026-10-20 aca9491：整树判定 + 规则集哈希钉住）＋ **第三件 v1 已落地**（2026-10-21 8e6a3cb：控制面 `.policy` 写面阻断 + 三路径验证套件）＋ **执行面 v2 已落地**（2026-10-21 45d6168：`.git` 与 `.github/workflows` 纳入受保护前缀；27 条矩阵 7 条翻面、20 条相等）；读数 `readings/2026-10-20-C3-final-tree-gate.md`、`readings/2026-10-21-C3-control-plane-write-guard.md`、`readings/2026-10-21-C3-git-surface-guard.md`；其余治理面（dgate2/evaluation/语料/文档）按「规则 + 审批」不封（04 5.87） |
| C4 | 回合末 steer 门禁（可选） | **先验证** agent.steer 在桌面 profile 的插件 API 里可用；再裁定 | 3 | 真机：存在未结清文件时能多跑一步；不存在时不多跑 | 待验证 |

**C3 说明**：这是把「判定对象从动作换成产物」的唯一落地件。它不依赖 C1/C2，可先做；但它**只保证「结束/提交时干净」**，不保证「中间态不落盘」——这条要写进接受边界。

### 阶段 D · 对比实验

见第 5 节。D 拆两门：D 校准门（P+/P−，无模型）不依赖 A3 四数，也不依赖 B1；A/B/C 构造门依赖 A3 v2 4/4 + 任务完成，以及 treatment 已定义（B1 或经裁定的替代）+ 用户签 1.3 条子（2026-10-18 裁定 A-5/A-6，见 readings/2026-10-18-A3-fix-adjudication.md）。treatment 选项事实、评分器冻结与待拍板项见 `readings/2026-10-19-D-gate2-treatment.md`：B1 在 A3 v2 冻结包上不激活，推荐 04 5.75② + 任务包 v3，treatment 与 canary 二选一。**2026-10-19 落地**：treatment `e341c08`、任务包 v3 `6f88e59`、隐藏验收 30 条 + runner `6f22cee`（参考树 40/40）、A 维度工具 `2a2cb21`（参考树 10/10）、评分器冻结 `be63670`（`scorer/manifest.sha256` 组合摘要 `e3ef9e91…`，`--check --strict` PASS）、C 臂装配与冒烟见 `testing/ab/dgate2/c-arm/`。**A/B/C 未开跑**：开跑前必须 `make_manifest.py --check --strict` 通过并把组合摘要与 17 个 run-manifest 字段写全。**2026-10-19 开跑前置已工具化**：`dgate2/run-manifest/`（17 字段三态生成/校验）+ `dgate2/run-record/`（T/C/A 三维读数采集）+ 两份读数（冻结包复核、run-record 样例；参考树 A 10/10、C 24/24、T 40/40 与 §10 一致）；`make_manifest.py --check --strict` 复核 PASS。**仍差使用者确认**（04 5.78 的状态列）。**2026-10-20 已跑 A/B/C 各一次（n=1）**：A 未完成（M5b 被拦）、B/C 完成；案例读数见 `readings/2026-10-20-D-gate2-ab-c-runs.md`，run-manifest 在 `testing/ab/dgate2/runs/2026-10-20/`；**H2/H3 已由使用者授权的子会话代执行复核并记录**（H2 抽样文件、H3 组合根语义），三份 run-manifest `--strict` PASS。要写「值得扩试」仍需每臂 k≥3 次同题 run。

---

## 5 对比实验方案

### 5.1 四臂

| 臂 | 形态 | 回答什么 |
| --- | --- | --- |
| A 现方案 | 模型 + 当前规则数据 | 现状基线 |
| B 改后方案 | 同一模型 + 改后规则/配置 | 改动是否改变产出 |
| C 无治理 | 工作区在 project_root 外 | 不治理时模型自己能到几分 |
| D 机械补丁 | **无模型**，固定 P+ / P− 补丁直接喂 Hook | 仪器校准：拦不拦、误不误伤 |

**D 臂是唯一的干净因果读数**；D 通过 = P+ 被拦**且** P− 放行；D 不过 = P+ 被放行**或** P− 被拦，A/B 不开跑（2026-10-18 裁定 A-9）。D 校准门不依赖 A3 四数；A/B/C 构造门另需 A3 v2 4/4 + 任务完成（裁定 A-6/A-12）。

### 5.2 任务与压空间

- 任务选型：≥3 层、≥6 文件、≥2 个既有文件被改；既有测试与新增测试都要动；有一个「合规写法与省事写法都通」的岔口；无网络/随机/时钟；参考解 ≤90 分钟。
- 压空间：首条消息逐字节相同；固定接口签名、固定验收表、固定允许写的路径集合；**固定里程碑顺序而非逐条工具调用**；同模型同参数；禁提问（只允许一句预注册回复）。

### 5.3 判分（100）

| 维度 | 分值 | 判定 |
| --- | --- | --- |
| T 任务完成 | 40 | 隐藏验收 × 30 + 入口 5 + 接口 5 |
| C 规则遵守 | 30 | 冻结的 8 条规则 × 3 + 冻结文件未改 3 + 无旁路 3 |
| A 架构合理 | 30 | 10 条结构谓词 × 3（分层方向、无环、公开符号数、组合根唯一、复杂度阈值等） |

**三者都只读最终树**；平台账本只做过程读数，不进 100 分。

### 5.4 作废条件（任一成立，该 run 不进对比）

起点 sha256 不同；提示词不同；桥没生效（0 条 PreToolUse 或全是 out_of_scope）；条子过期/形状不覆盖；三把锁变了；规则集/配置在 run 中漂移；参照树或评分脚本哈希不符；宿主或模型跨臂不同；泄漏；预算截断；外部改动；同一输入两次读数不同。**作废 run 超过总数 1/3 ⇒ 整套判「跑不成」。**

### 5.5 强度声明与句式纪律

- **能写**：过程事实（这次被拒了几次、原因码分布）、案例描述（这次最终树诊断 x 条/千行）。
- **不能写**：平均、提升 X%、显著、有效、证明。
- **n=1 时**：只写案例；要写「值得扩试」，每臂 k≥3 且过预注册决策规则。
- **不能证明**：规则/反馈/审计各自的贡献；换任务/模型/宿主的外推；长期维护成本；「架构合理」的一般性。

### 5.6 干跑四数（阶段 A3，开跑前）

| 数 | 定义 | 通过线 |
| --- | --- | --- |
| 写动作治理覆盖率 | 有判定记录的任务路径写动作 / 实际文件变化 | 100%（缺的记 unmeasured） |
| 命令族成功率 | 任务需要的命令首次尝试通过率：`decision∈{allow,allow_with_warnings}` + grant/allow_delegated + **真的进入执行**（`post_evidence.process.exit_code` 可读或会话 tool/result 非错误）；命令自身退出码与 `post_outcomes` 只作单列读数 | ≥ 90%，且失败原因不全是 approval_invalid；**分母 = 预注册族数，<2 族记「不可判定」不记通过** |
| 路径族声明 | 任务触碰的每个路径族都有 layer 映射 | 100% |
| 上下文触顶 | 是否触发压缩/触顶 | 未触发（触发则记删失） |

> **2026-10-18 裁定 A-7/A-12（判据冻结，跑前写死）**：② 的「首次尝试通过」按上表固定口径，四数定义在 A3 v2 前冻结进 run-manifest（判据原文 sha256），读数表必须附任务完成度、attempted vs landed、受治/非受治比与 block 的 rule_id 分布；**D 开场另加**「A3 v2 任务完成（A1–A7：最终 `python -m pytest -q` exit 0、`python tools/audit_demo.py` exit 0、允许写集合内）」前置。裁定见 `readings/2026-10-18-A3-fix-adjudication.md`。

---

## 6 风险与反证条件

| 风险 | 反证/缓解 |
| --- | --- |
| 「温和改造只改账本写法，不改 allow/block」 | 判据：拿掉这条机制，是否仍有一条真实事件会逃？是 → 转 C3。 |
| 覆盖表退化成散文 | 加载期引用完整性 + 删一行必红。 |
| 批次状态跨进程不可靠 | 按 session 分文件 + TTL + 显式 settle；规模 1/3/10 压测。 |
| 解冻后判定漂移 | 每项单独 R-d 差集；差集工具入库。 |
| 实验被构造问题污染 | 阶段 A3 四数不过就不跑；D 臂先校准。 |
| run_code 的洞被误读成已覆盖 | 覆盖表必须有一行显式 declared_uncovered；最终树门禁 C3 才是真覆盖。 |

**整体反证条件**：若阶段 A 完成后，A3 的四数有任意一项无法达成，且 C3 无法在可接受成本内补齐，则本计划判「目标在当前宿主能力下不可达」，转入「只保证提交面」的降级形态。

---

## 7 与现有文档的对应

| 本计划项 | 04-open-work 编号 | AGENTS 条款 |
| --- | --- | --- |
| B1 | 5.69 | 第 14 条（审批绑定）、第 55 条（协议升版） |
| B2 | 5.66 | 第 49 条（平台级测试路径）、第 55 条 |
| B3 | 5.70 | 第 17 条（白名单不是沙箱） |
| C1 | 5.46 | 第 55 条 |
| C2 | 5.68 | 第 46/50/51 条 |
| A1 | — | 第 45 条（仪器要能失败）、第 56 条（义务账口径） |
| A2 | 5.71 | 第 15 条（事后证据） |
| 阶段 D | — | testing/ab/gui-ladder.md 的强度纪律 |

---

## 8 变更控制

1. 本文件的**阶段与门**改动，必须在本文件里显式记录（改哪一行、为什么、谁裁定）。
2. 每次执行（一次任务、一次探针、一次 run）的记录写进 06-plan-progress.md，格式由该文件规定。
3. 阶段 B 及之后的每一项，提交时必须同时给出：R-d 差集、负例、回退方式、对应的 04-open-work 编号更新。
4. 新增数据文件（覆盖表、批次台账）一律自带 schema_version，按第 55 条登记。
5. **2026-10-18 阶段 A 门措辞（现行措辞见 §4 A1/A2 行）**：A2 门取三态（能力边界 / 假阳性 / 真阳性），三种结论都要带读数；A1 门的「删一行变异必红」按**工具级**红键执行——可证明的是「删掉某工具的最后一行 / 全部行变异必红」，删单个阶段行不改变红格，(channel, tool, mode) 粒度留作后续候选。
6. **2026-10-18 A3 修复裁定（F-2..F-7）与 D 前置（裁定 A-5/A-6/A-7/A-12；现行判据见 §4 D 行、§5.1、§5.6）**：F-2 保留 F2 族与 demo 交付物（v2 基线预置 `tools/audit_demo.py`，A7 改为运行已有脚本）；F-3 先修构造、不改熔断口径（`breaker_seconds`=300s）；F-4 修 `.tmp` 装配器谓词并用其复算 run-01（② 仍 1/2）；F-5 启动受治 dsh 用一次性 `danger-full-access` 授权 + 跑后哈希复核；F-6/F-7 记录卫生。B1 是**条件前置**：D 校准门不依赖 B1，A/B/C 构造门依赖 B1（或经裁定的替代 treatment）+ 用户签 1.3 条子；触发：任一次 pwsh 因「注册表声明为可选、带默认值的参数」得 `approval_invalid` 且挡住必需命令 ⇒ B1 升为前置、当轮读数作废。D 拆两门（校准门 / 构造门）；② 判据冻结。裁定见 `readings/2026-10-18-A3-fix-adjudication.md`。
7. **2026-10-19 D 门 2 五项裁定（自行研讨；使用者授权自行决策）**：treatment = 04 5.75②（`production_patterns` 增 `tools/**/*.py`）+ 任务包 v3（要求新建 `tools/audit_demo.py`）；canary 退役（改判两层显式期望：同一动作 A 臂 block / B 臂 allow + 5 类反例两臂仍 block）；B1 不进 D（保留为 04 5.69 的独立 construct fix，若做则默认值语义只对 1.3 记录生效）；评分器按 `readings/2026-10-19-D-gate2-treatment.md` §4 冻结（先建 `tools/structure_metrics.py` 并做变异自证）；隐藏验收由独立子会话编写。执行次序、未核实项与回退见该文件 §8。
8. **2026-10-20 A/B/C 各一次 run（n=1）与人工项代执行**：三臂同一首消息、同一 12 文件基线，run-manifest 落 `testing/ab/dgate2/runs/2026-10-20/`；H2/H3 由使用者授权的两个子会话代执行复核，抽样人/复核人记使用者，代执行事实写在两份复核记录里；三份 manifest `--strict` PASS。**主张边界**：n=1 只写案例读数，写「值得扩试」需每臂 k≥3（05 §5.5）；A 首跑因注册表装配错误作废（D-20261020-01），不进计分。
9. **2026-10-20 使用者授权解冻与两项落地**：使用者在本会话明确授权解冻 05 §2.3 的四项不做（限 B1/B3/C3）；B1 审批「参数域」（协议 1.2→1.3、注册表 1.0→1.1、族数据）与 C3 最终树门禁 v1（整树判定 + `RuleSet.identity` 钉住）落地，读数见 `readings/2026-10-20-B1-param-domain.md`、`readings/2026-10-20-C3-final-tree-gate.md`；C3 的「危险动作前置阻断」未做（04 5.84）。**新增纪律**（同次事故换来的）：改 Hook 导入链上的模块后每次写入立刻跑 import 自检（04 5.85）。

---

## 附录 A · 本计划的依据来源

- 规则/判定链/声明面读数：本次实测（解析 policies/**、统计包级 LOC、AST 依赖图）。
- 缺口与冻结令：docs/project/engineering-policy-platform/04-open-work.md 第 1.4 节与第 5 节（5.46/5.66/5.68/5.69/5.70/5.71）。
- 宿主 Stop 语义：dsh 安装目录 asar 内 @deepseek-ai/dsh-agent-loop/lib/index.js 与 dsh-tool-cordis/lib/types/api-catalog.js。
- 审批两向严格：src/enforcement/approvals.py 第 412–431、540–579 行。
- 覆盖表格式：validation/control-plane-facts.yaml、adapters/wiring-scope.yaml。
- R-d：docs/project/engineering-policy-platform/designs/控制面重构方案.md 第 5.2 节。
- 对比测试方法：docs/project/engineering-policy-platform/testing/ab/gui-ladder.md、round2-*.md。

## 附录 B · 术语

| 术语 | 含义 |
| --- | --- |
| R-d | 改判定必须交的字段级差集（含 violations 内容） |
| 冻结令 | 04-open-work 第 1.4 节的四项不做 |
| 覆盖表 | 记录「哪个通道 × 哪个工具 × 哪种治理 × 哪条检查」的数据表，只报告 |
| 未结清清单 | 本次任务里已改但尚未通过判定的文件集合 |
| D 臂 | 无模型的机械补丁臂，用于校准仪器 |
| 干跑 | 不计分的单臂试跑，只量四个构造数 |
