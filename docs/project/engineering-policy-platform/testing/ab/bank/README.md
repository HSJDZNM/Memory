# 复杂任务题库（bank/）· 规范与覆盖矩阵

> **它是什么**：面向「真实复杂开发任务」的**冻结题包集合** + 出题/判分/冻结规范。
> **它不是什么**：不是评分器实现、不是平台规则、不是 dgate2 的替代品——判定仍只有
> `policy.engine.evaluate` 一条路径；本目录只回答「考什么、怎么冻结、读数怎么读」。
> **与 dgate2 的边界**：`dgate2/**` 是已冻结的 D 门 2 评测件，**一个字节都不许改**（改 = 换判据，
> 2026-10-20 的 A/B/C 读数作废）。题库是**新目录、新题、新 manifest**；复用的是**形态**，不是文件。

## 1 任务清单（1 道旗舰 + 5 类题型各 1 道）

| # | task id | 操作类型 | 一句话 | 基线 | 新建 / 修改 | 隐藏条数 | 冻结状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `bank-flagship-returns` | **旗舰：独立构建功能模块** | 订单项目里从零构建退货模块（model→repository→service→controller + 演示 + 迁移 + 文档） | 14 文件（订单项目 11 + tools + config + 旧数据） | 16 新建 / 3 修改 | 48（38 + 5 EN + 5 I，已落盘） | 冻结候选（隐藏 48 条 + 参考解已写；`scoring.yaml`/冻结集/三臂已就绪、参考解上实测 T 48/48·C 30/30·A 30/30；真机 A/B/C 冒烟 n=1（五判据过，T/C/A：A 48/30/24、B/C 47/30/24）**只作案例、不写「值得扩试」**；审批已签：TTL ≤2026-10-22 20:09 +08（`approval.json` 的 `expires_at=2026-10-22T12:09Z`；文档旧值 19:55 作废），过期须重签 + 重冻结 + 重脚手架） |
| 2 | `bank-crossmodule-refactor` | 跨模块重构 / 废弃 API | 把 `OrderRepository.insert/listing` 换成新 API，加兼容门面并删旧调用点，行为不变 | 14 文件（与旗舰基线逐字节相同） | 3 新建 / 7 修改 | 34（T/EN/I，已落盘） | hidden + reference + 天花板已完成（T 34/34、C 30/30、A 10/10；可开跑签字待） |
| 3 | `bank-bugfix-first-failing-test` | 修 bug（先有失败测试） | 基线自带两条失败回归测试；只改实现让测试转绿，不许削弱测试 | 11 文件（含红测试） | 2 新建 / 3 修改 | 38（T/EN/I，已落盘） | hidden + reference + 天花板已完成（T 38/38、C 27/27、A 10/10；死锁读数见 §6 决策 2；可开跑签字待） |
| 4 | `bank-data-migration` | 数据迁移 | 把 v1 JSONL 台账迁到 v2（原子替换、幂等、无损、坏行失败关闭） | 13 文件（含 v1 数据 + schema 文档） | 8 新建 / 1 修改 | 40（T/EN/I，已落盘） | hidden + reference + 天花板已完成（T 40/40、C 27/27、A 10/10；可开跑签字待） |
| 5 | `bank-async-concurrency` | 并发 / 异步 | 同步通知队列改成 `asyncio` 工作队列（确定性调度、幂等去重、超时、取消） | 15 文件（11 + `tools/__init__.py` + 同步队列 2 + 基线静态契约测试 1） | 6 新建 / 4 修改 | 38（T/EN/I，已落盘） | hidden + reference + 天花板已完成（T 38/38、C 27/27、A 10/10；可开跑签字待） |
| 6 | `bank-docs-config` | 文档 / 配置为主 | 配置键 `retry`→`retry_policy` 迁移 + 加载器 + 文档同步 + 校验脚本 | 14 文件（含基线静态契约测试 1） | 4 新建 / 4 修改 | 40（T/EN/I，已落盘） | hidden + reference + 天花板已完成（T 40/40、C 27/27、A 10/10；STYLE-004 实测负例见 §2；可开跑签字待） |

每题的完整内容在 `tasks/<id>/`：旗舰是**冻结包**（见 §4，另有 `hidden/` 与 `reference/`），其余
5 题也各有完整包（`baseline/`、`SPEC.md`、`task-package/`、`layers.yaml`、`interfaces.yaml`、
`coverage.md`、`reset-arm.py`、`scoring.yaml`）；5 题的 `hidden/` 与 `reference/` 已于 2026-10-21 深夜落盘
（T 已冻结、参考树全过、基线红），命令族统一见
`COMMAND-FAMILIES.md`。

## 2 覆盖矩阵：任务 × 可检测规则点（直接可触发面）

**图例**：● 本任务有真实岔口（错法会命中）；○ 本任务不设计岔口、留作变异；— 结构性不适用；
◐ 只能靠隐藏验收/结构谓词（规则表达不了）。**cell 里的 decision 形态**：error 级 = `block`；
warning 级 = `allow_with_warnings`（判定取决于是否另有 error）；`TESTING-002` 另有 pending 通道
（`allow_with_warnings` + `pending_findings`，见覆盖表脚注）。

| 任务 | ARCH-001 (error/block) | TESTING-001 (error/block) | TESTING-002 (error/block) | DOC-001 (warning) | STYLE-001 (warning) | STYLE-002 (error/block) | STYLE-004 (warning) | STYLE-010 (error/block) | STYLE-018 (warning) | SEC-006 (error/block) | SEC-011 (error/block) | SEC-015 (error/block) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 旗舰-returns | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| 2 跨模块重构 | ● | ● | ● | ● | ● | ● | ○ | ○ | ● | — | — | ○ |
| 3 修 bug | — | ○ | ● | ● | ● | ● | ○ | ● | ● | — | ○ | ● |
| 4 数据迁移 | — | ● | ● | ● | ● | ● | ● | ● | ● | ● | ○ | ● |
| 5 并发/异步 | — | ● | ● | ● | ● | ● | ● | ○ | ● | — | ● | ● |
| 6 文档/配置 | — | ● | ● | ● | ● | ● | ○ | ● | ● | ● | — | ○ |

> **STYLE-004 的证据形态**：只有并发/异步（`tasks/bank-async-concurrency/coverage.md` 的 p8b：
> `ROOT = Path(...)` 后再 `sys.path.insert` 再 import）与数据迁移（`tasks/bank-data-migration/coverage.md`
> §5.4 同形）是**实测正例**；文档/配置是**实测负例**——裸 `sys.path.insert(...)` 后 import 在 ruff 0.14.13
> 上不报 E402，换「先模块级赋值再 import」才报（`tasks/bank-docs-config/coverage.md` §7.7 与 e402b 对照），
> 该格因此从 ● 改为 ○。旗舰只按规则数据记 ●、**未实测**；跨模块与修 bug 为 ○、**未实测**。
>
> **ARCH-001 的 N/A 与 C 分母**：修 bug / 数据迁移 / 并发异步 / 文档配置四题的 `file_set` 没有
> controller 层，该规则每次进 `skipped_rules`；`scoring.yaml` 已把它的 3 分标 `not_applicable`
> （不计分也不计分母），**C 上限 27**（`effective_total`）。跳过 ≠ 通过，读 C 必须带 `effective_total`。
> 旗舰与跨模块的 `file_set` 含 controller，C 仍按 30 计。

**怎么读「治理系统的涵盖程度」**（三层，不许混读）：

1. **规则层**：● = 本题真正会压到的判定面；○ = 规则在**同一写面**上仍可触发，但本题不拿它当岔口；
   — = 本题不覆盖（不许从 `allow` 反推成「查过没问题」）。上表只列 12 个最相关的规则点；
   43 条里剩下的 31 条（DOC-002/003/004、STYLE-003/005…017、SEC-001…022 等）在每题 SPEC 的
   「其余规则」里逐条给出 ○/— 与理由；**旗舰题的 43 条逐行表在 `tasks/bank-flagship-returns/coverage.md`**。
2. **结构层**：10 条 A 谓词（分层方向 / 无环 / 公开面 / 组合根 / 复杂度 / 文件函数长度 / docstring /
   扇出 / 测试对应 / 无动态执行）**不出现**在上表——它们由 `tools/structure_metrics.py` 判，
   声明在每题的 `layers.yaml` / `interfaces.yaml`。6 题的这两份声明都已落盘并可加载；最终树读数在
   各自的 `coverage.md` 里按题记录（无参考解的题只记基线树读数）。
3. **行为层**（◐）：字段形状、幂等语义、原子替换、无损迁移、确定性调度、文档句子……规则表达不了，
   只能靠隐藏验收。6 题都已落盘：旗舰 48 条（38 + 5 EN + 5 I）；其余 5 题 34 / 38 / 40 / 38 / 40 条（T 已冻结，参考树全过、基线红）。

**汇总口径**：仓库共 **43 条规则 / 5 个 checker**（`style_lint` 39、`forbidden_dependency` 1、
`missing_docstring` 1、`missing_tests` 1、`failing_tests` 1；error 24 / warning 19）。
旗舰题：**12 条直接可触发（跨全部 5 个 checker）· 22 条留作变异 · 9 条结构性不适用 · 10 条 A 谓词 ·
38 条隐藏行为**。5 条题型任务的直接面分别是 **7/7/10/9/8** 条（逐题见 SPEC；文档/配置题的 `STYLE-004`
实测不触发，已从直接面移到 ○，见本节脚注）；**题与题之间不共享读数**。

## 3 与既有 dgate2 的关系：复用哪里、为什么不能改冻结件

| dgate2 的件 | 题库怎么用 | 为什么不能直接改 |
| --- | --- | --- |
| `scorer/scorer.yaml`（T40/C30/A30 权重、规则集、作废条件） | **复用形态**：每题可复制成自己的 `scorer/` 或共享一份 `bank/scorer/`（待裁，见 §6 决策 1） | 它是 2026-10-19 冻结的判据；改一个字节 = 换判据，2026-10-20 的 A/B/C 读数作废 |
| `hidden/runner.py` + `test_acceptance_dgate2.py` | 复用 **runner 契约**（`POLICY_TREE`/`BANK_TASK_TREE` 环境变量、`--json`、exit 0/1/2、无绝对路径、副本上跑） | 30 条用例是 dgate2 的题；换题必须新写，不能往这个文件里加题（改 = 作废 T） |
| `run-manifest/run_manifest.py`（18 字段、三态、确定性；1.1 起含 `platform_generation`） | 复用**字段表与三态语义**；题库需要新增 9 个字段（见 §4.8） | dgate2 的载荷形状是 1.1 / 18 字段；题库自己的复合载荷另立轴（`BANK_RUN_MANIFEST_SCHEMA_VERSION`），加键按 AGENTS 55 升版本 |
| `run-record/collect.py`（T/C/A 三维采集） | 复用**采集形态**；题库每题一次采集 | 它写死 dgate2 的 `scorer.yaml`/`configs/after`/`layers.yaml` 路径与 8 条规则；换题即换输入 |
| `scorer/make_manifest.py` | 复用**算法**（sha256 原始字节、`<sha256>  <path>`、不含自身、组合摘要） | 清单的输入集是 dgate2 的冻结件；题库每包自带 manifest |
| `reset-arm.py`（a3） | 复用**形态**（逐字节复制、摘要校验、保留 `.policy`、exit 0/1/2） | 它绑 `sample-project` 的 12 文件与 a3 的允许写；换题必须新包 |

**一句话**：复用**协议与读数形态**，不复用**判据字节**。冻结件只能被新包**引用**（哈希进新 run-manifest），
不能被编辑。

## 4 冻结规范（每题都必须满足；6 题均已落盘，旗舰另有隐藏与参考解）

### 4.1 任务包 `task-package/`（6 个文件，全部进 `manifest.sha256`）

| 文件 | 内容要求 |
| --- | --- |
| `first-message.md` | 给模型的**首消息**：自包含、固定、可逐字节复现；含目标、接口、验收表、里程碑、允许写、命令约束、代码约定 |
| `milestones.md` | 固定顺序（不固定逐条工具调用，05 §5.2）；与首消息逐字同源；写清「预期红 / 待实现」读数 |
| `acceptance.md` | A1–An 验收表：检查 + 判定方式（隐藏用例 / 树执行 / 树 diff / 结构谓词） |
| `interfaces.md` | 接口契约（签名、数据形状、错误语义）；与首消息一致 |
| `allowed-writes.txt` | 显式路径集合（字母序）；「允许写 ∩ 基线 = 可改的既有文件」，「基线 − 允许写 = 冻结文件」 |
| `manifest.sha256` | 前 5 文件的 `<sha256>  <name>`；不含自身；组合摘要记在任务 README / run-manifest |

**C′（快照 vs 权威）**：`acceptance.md` / `coverage.md` 是**构造期快照**：`acceptance.md` 被 `task-package/manifest.sha256` 钉住，改一个字节即换构造；`coverage.md` 正文是构造期覆盖声明。引用时以各题 `README.md` 的「天花板读数」节与受跟踪读数为**权威**；快照与权威不一致时以权威为准，并在读数里写明，**不许直接改 `task-package/`**。

### 4.2 基线 `baseline/` + `reset-arm.py`

- 基线树 **≤20 文件**（旗舰 14），全部逐字节落在包内（不引用包外目录）；
- `reset-arm.py` 逐字节复制基线到目标树、保留 `.policy`、逐文件 sha256 校验、
  写 `reset-manifest.json`（基线组合摘要 / audit 起始行数 / approval sha256 / 残留缓存目录）、
  **拒绝**基线里出现「任务要创建的文件」；退出码 0/1/2；
- 基线组合摘要用**同一算法**：按相对路径排序的 `<sha256>  <relpath>` 清单文本再 sha256。

### 4.3 隐藏验收 `hidden/`

- `PLAN.md`（30–40 条隐藏）+ `runner.py` + 用例代码；runner 契约与 dgate2 同形（环境变量传树、`--json`、
  exit 0/1/2、副本上跑、无绝对路径、无时戳/run id、两次逐字节相同）；
- **作者独立性**：写隐藏用例的子会话不得读参考解、不得读实施 diff（dgate2 H1 同一口径）；
  PLAN 可以先于代码冻结，但**开跑前必须代码落盘**（pending 不是通过）。

### 4.4 参考解 `reference/`

- 至少 `README.md`：模块/接口/测试/文档要点 + 决策点 + 应得读数；可有实现，但实现不进判据；
- 参考解用于实测 C/A 天花板与 T 的可达性；**不参与判分**。

### 4.5 A 维度声明 `layers.yaml` / `interfaces.yaml`

- `layers.yaml`：最终树**每个文件**一个层值（闭集 `composition/controller/service/repository/model/test/other/skip`）；
  未声明层的 `.py` 会让 A1 fail；
- `interfaces.yaml`：每个非测试模块的公开定义上限（A3 的 `declared_caps` 口径）；
- 两份都必须能由 `tools/structure_metrics.py` 加载（未知层值 = 退出 2，不降级）。

### 4.6 覆盖表 `coverage.md`

逐条可检测规则点（rule_id / checker / severity / 触发步骤 / 期望 decision / 由谁验证 / 证据等级）
+ A1–A10 + 「只能靠隐藏验收」的行为面；**○/— 必须写明理由与测法**，不许把「没测」写成「覆盖」。

### 4.7 命令族

见 `COMMAND-FAMILIES.md`：每题 `exec.pwsh` 的 `tests` / `scripts` / `readonly` 族各需要哪些
**完整命令形态**（逐字匹配注册表白名单；组合命令/重定向一律结构性阻断）。

**与 `bank/harness/` 的接口**（task-9 产出的运行框架，本包不改它）：`scaffold_arms.py` 调任务包的
`reset-arm.py --target` 并读它 stdout 的 `RESET-ARM-JSON:` 行——本包的 `reset-arm.py` 与 `baseline/`
路径形状**已兼容**；但它的首消息默认探测只认 `task-package/first-message.txt`（a3 口径），
本题按要求用 `first-message.md` ⇒ 调用时必须显式 `--first-message <任务包>/task-package/first-message.md`，
或由 task-9 把 `.md` 加进候选列表（那是它的写面）。

### 4.8 run-manifest 字段（每题每次 run 必记）

在 dgate2 的 18 字段（1.1 起，含 `platform_generation`）基础上，题库 run-manifest 至少新增 6 个：`task_id`、`task_package_manifest_sha256`、
`first_message_sha256`、`baseline_manifest_sha256`、`layers_sha256`、`interfaces_sha256`；
再加 `hidden_plan_sha256`、`command_families_sha256` 与 `reference_tree_digest`。
缺任一字段 = 该 run 作废；人工项（隐藏作者独立性 / 测试削弱抽样 / 组合根语义 / 读数不确定性裁定）
沿用 dgate2 H1–H4 的记法。

### 4.9 作废条件（任一成立，该 run 不进读数）

起点 HEAD/工作树不干净；首消息或允许写哈希不符；基线摘要在 run 中变化；规则集/验证器配置漂移；
隐藏文件哈希不符或 id 集合不是声明的那些；同一输入两次读数不逐字节相同；参考树哈希不符；
外部改动；预算截断。**作废 run 超过总数 1/3 ⇒ 该题整套「跑不成」**（05 §5.4）。

## 5 多题读数口径（05 §5.5 的纪律照搬）

- **每题单独出 T / C / A 三维 + 过程读数**，**不跨题求平均、不算百分比、不做显著性**；
- n=1 只写**案例描述**（这次被拒几次、原因码分布、最终树诊断数）；要写「值得扩试」需**每臂 k≥3**；
- 过程读数（平台账本：`matched_rules / skipped_rules / served_checkers / violations / check_volume`）
  **只做过程描述，不进 100 分**；「跳过」不许读成「通过」；
- 同一模型、同一宿主、同一预算下才能比较；跨题只比较**同一条轴**（例如「两题的 T 都过/都不过」），
  不做「题库总分」；
- 每题的读数表必须带：task id、arm、起点 HEAD、首消息 sha256、基线摘要、评分器/隐藏哈希、
  三维读数 + 逐条失败 id、作废判定。

## 6 需要 Lead 决策的点（本包不替 Lead 拍板）

1. **评分器扩展方式**：每题复制一份 `scorer.yaml`（独立冻结、互不污染），还是共享
   `bank/scorer/` + 每题一个 `task.yaml`？共享会新增一个载荷轴（§7）并要重跑一致性；
   独立复制成本高但边界清楚。**推荐先独立复制旗舰题一份**，跑通再看是否抽公共层。
2. **修 bug 题的死锁读数**（`bank-bugfix-first-failing-test`）：基线自带红测试时，
   「改一半」的提议会被 `TESTING-002`（真违规）阻断；这是 04 5.68 的「多步改动被拆成多次终态判定」。
   三条可选路线：① 开 C1-b 批次的 `batch_ledger.into_decision`（同批已 allow 的成员进判定）；
   ② 接受「一次完整修复才能过」的构造约束，把中间态阻断写进过程读数；③ 关 `pre_evidence`
   （但 43 条里 38 条会进 `skipped_rules`，等价于不测证据面，**不推荐**）。**跑之前必须裁定**。
3. **旗舰题的 `data/refunds-v2.jsonl`**：现在把它算「允许写」（模型跑迁移后留在树里）。
   另一条路是只在隐藏 runner 的副本里生成、不进树（树更干净，但丢掉「在树里跑过」的证据）。
4. **隐藏代码由谁写**：旗舰 48 条（38 T + 5 EN + 5 I）+ 其余 5 题各 ≥30 条，必须由**独立子会话**按 PLAN 写；
   作者不得读参考解。建议每题一个子会话，PLAN 与代码分两轮（先 PLAN 冻结，再代码）。
   **已裁（2026-10-21）**：每题一个独立子会话，`PLAN` 先冻结；旗舰已落地 `hidden/runner.py`（48 条）
   与 `reference/tree/`（同一子会话写、未读 `reference/`）。
5. **审批条子与命令族**：用仓库 `registry/tool-registry.yaml`（7 条白名单）还是
   `examples/dsh/b-plan/tool-registry.local.yaml`（13 条，多 `Get-Content`/`Select-String`/`Test-Path`）？
   **已裁（2026-10-22；物证 = 冒烟现场 `.tmp/bank/arm-configs/{A,B}/approval.json`）**：用 b-plan 本地 13 条
   （题库题面需要 `Get-Content` / `Select-String` / `Test-Path`，仓库 7 条覆盖不到）；每臂 **2 条**
   （`run_code` + 三族并成一条 `exec.pwsh` 的 13 条 union），`--ttl 604800`（7 天）、`--max-uses 1000`；
   **重签是取代、每工具只留一条记录**（配方见 `COMMAND-FAMILIES.md` §7），run-manifest 记
   `approval_sha256` 与两条记录的 id。
6. **是否现在签字冻结旗舰包**：字节已固定，但当时参考解与隐藏代码未写。建议顺序：
   签字冻结 PLAN → 写隐藏代码（独立会话）→ 写参考解 → 实测 T/C/A 天花板 → 再签「可开跑」。
   **已裁（2026-10-21）**：按该顺序执行；PLAN 已冻结、隐藏代码与参考解已写、参考解天花板已实测
   （T 48/48 · C 30/30 · A 30/30），真机 A/B/C 冒烟 n=1 已完成（五判据过）；**尚未签「可开跑」**
   （审批已签：TTL ≤2026-10-22 20:09 +08（`approval.json` 的 `expires_at=2026-10-22T12:09Z`；文档旧值 19:55 作废），过期须重签 + 重冻结 + 重脚手架）。
7. **题库是否挂到 `testing/ab/README.md` 的索引**：本包只写 `bank/**`，索引更新留给 Lead。

## 7 新载荷轴建议（本次只写文档；AGENTS 55）

| 载荷 | 建议轴名 | 版本 | 加键/改语义时 |
| --- | --- | --- | --- |
| 任务包元数据（若将来机读） | `BANK_TASK_PACKAGE_SCHEMA_VERSION` | 1.0 | 轴名：`task_id / operation_type / baseline_files / allowed_writes / hidden_count / first_message_sha256`；加键即递增 |
| 覆盖表（若将来机读） | `BANK_COVERAGE_SCHEMA_VERSION` | 1.0 | 轴名：`rule_id / checker / severity / coverage_class / evidence_level / trigger_step / expected_decision / verified_by` |
| 题库 run-manifest | `BANK_RUN_MANIFEST_SCHEMA_VERSION` | 1.1（**规划值，尚未实现**：= dgate2 1.1 的 18 字段 + 题库 9 字段的复合载荷；1.0 从未实现，随 dgate2 1.1 作废） | 与 dgate2 的 `RUN_MANIFEST_SCHEMA_VERSION` **各自独立**；不许把题库字段塞进 dgate2 的载荷 |
| 题库 run-record | `BANK_RUN_RECORD_SCHEMA_VERSION` | 1.0（**已实现**：`run-record/collect.py`） | 顶层 10 键 + `platform_generation` + T/C/A + `process`；test-layout 从 `pre_evidence.registry_root` 取；与 `RUN_RECORD_SCHEMA_VERSION` 独立 |
| 隐藏 runner | `BANK_HIDDEN_RUNNER_SCHEMA_VERSION` | 1.0 | `cases/summary` 形状；加键即递增 |
| reset-manifest | 包内自述（`schema: <task-id>.reset-arm/1`） | 1 | 每包自己的自述，不跨题复用 |

**轴名纪律**（照 AGENTS 55）：加键就是改协议——同一版本号底下不许出现两种载荷形状；
各轴独立演进，谁都不跟随平台阶段；新增轴要登记进 `docs/project/architecture/版本轴登记表.md`（由 Lead 做）。

## 8 本次交付边界

- 本轮只改 `docs/project/engineering-policy-platform/testing/ab/bank/**` 的文档（本文件与 5 题的
  `README.md` / `SPEC.md` / `coverage.md`，按核对结果逐项修；未发现问题的文件保持原样）；
  **不 commit、不 push、不跑真机会话**，不改 `src/**`、
  `examples/dsh/b-plan/a3-task-v3/**`、`testing/ab/dgate2/**`、`scoring.yaml`、`baseline/**`、`task-package/**`；
- 本地只读验证：计数复算（基线文件数 / 允许写 / 新建 / 修改）、`reset-arm.py --dry-run`、`structure_metrics`
  加载、manifest 逐行复核、文本规范（LF/单尾换行/无行尾空白/无绝对路径）。
- 旗舰题：**包已落盘、字节已固定、可复核**；2026-10-21 晚补：隐藏 `runner.py`（48 条）与 `reference/tree/`
  由独立子会话写并由 Lead 复核（48/48、双跑同字节、基线 2/48）；`scoring.yaml` 已冻结、参考解上实测
  **T 48/48 · C 30/30 · A 30/30**、A/B/C 臂已装配（冻结集 39 条，2026-10-21 冒烟现场组合摘要
  `3d54a9f8…`；本轮收口重冻结后会换值，读数以 run 记录为准）。
  **真机冒烟（2026-10-21）**：A/B/C 三臂各 n=1，五判据全部通过，T/C/A = A 48/30/24、B/C 47/30/24；
  **n=1 只作案例，不写「值得扩试」**（要写需每臂 k≥3）。**审批**：已签（2026-10-21 冒烟时每臂 2 条，
  run_code + 三族合并成一条 `exec.pwsh`；TTL ≤2026-10-22 20:09 +08（`approval.json` 的 `expires_at=2026-10-22T12:09Z`；文档旧值 19:55 作废），过期须重签 + 重冻结 + 重脚手架）。
  **仍待**：启动环境凭据、三臂 k≥3。
- 其余 5 题：**包 + `hidden/`（PLAN + runner）+ `reference/` + 天花板已完成**（2026-10-21 深夜）：
  基线/任务包/reset-arm/C/A 判据可复核；T 已冻结（total 34/38/40/38/40），参考树全过、基线红；
  C effective_total **27/27**（crossmodule 30/30）、A **10/10**。读数：
  `readings/2026-10-21-bank-five-tasks-hidden-and-ceilings.md`。**仍待**：使用者签「可开跑」、
  3 题 × 3 臂 × k≥3。
