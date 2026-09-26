# 治理覆盖缺口 · 根因分析与修复计划

> 输入：`docs/project/engineering-policy-platform/reviews/governance-coverage-gaps.md`（实测 13 项缺口）。
> 本文把 13 项**现象**归并成 5 个**机制性根因**，给出本轮修复范围、写域划分与验收口径。
> 所有根因都指向仓库里的具体文件与行号；没有一条结论只靠阅读源码推断而不给出坐标。

## 0. 一句话

13 项缺口不是 13 个互不相干的 bug，而是**同一件事在五个层次上没做**：

> 平台的能力是"阶段 0→8 加法"堆出来的，但"**治理覆盖面**"从来没有被当成一个需要被证明的输出。
> 每一层都把自己那一半做对了，而"两层之间有没有接上"没有任何机制负责。

因此修复的重点不是补 13 个补丁，而是**把"覆盖"变成会失败的检查**：
钩子成对、接线可枚举、跳过要标注、口径要单一、声明要漂移检测。

## 1. 根因（按机制归并）

### R1 · 转发层只注册了一个钩子：能力在两层之间没有成对契约

- **现象**：G2（26 次受治理动作，"动手后"记录 0 条）、G11（注入内容零留痕）。
- **证据**：
  - `src/adapters/dsh/policy-hook.plugin.mjs:37` 全文只注册了 `ctx.on('tools/pre-execute', …)`；
  - 而 Python 侧 **已经实现**了事后钩子：`src/adapters/dsh/hooks.py:798 post_execute_outcome()`、
    `:863 run_hook()` 按事件名分派、`src/adapters/dsh/enforcement.py:272 handle_post_execute()`、
    `src/enforcement/postcheck.py:235` 按注册表 `post_checks` 逐项验证。
- **根因**：**Python 侧是全的，缺的是那一行插件注册。** 两句代码分散在两个语言、两个进程里，
  没有任何测试断言"注册了 pre 就必须注册 post"。漏注册不让任何测试变红 —— 这正是它能活到实测阶段的原因。
- **判定**：**缺陷**，不是设计取舍（注册表已经为每个工具声明了 `post_checks`，声明了却从不执行）。

### R2 · 接线状态是"配置事实"，运行期不可自证

- **现象**：G1（Agent Teams 通道零治理零留痕）、G13（没人能发现哪个通道没接线）。
- **证据**：
  - `src/adapters/dsh/hooks.py:939-943`：`check_wiring()` 在 `hooks_config_path is None` 时**直接 `return ""`（= 通过）**；
  - 全仓库没有任何模块枚举"本机有哪些 Agent 运行时、各自接没接线、最近一次留痕是什么时候"。
- **根因**：治理把"我覆盖了什么"当成自己的**内部属性**，而不是一个**可观测、可失败的输出**。
  审计账本"永远完整漂亮"，恰恰是因为**没接线的通道根本不写记录** —— 账本上看不出缺了什么。
  这是典型的**幸存者偏差被写进了监控口径**：只统计"被观测到的请求"。
- **判定**：**缺陷**（"自检缺席即通过"违反仓库自己的失败关闭原则，见 AGENTS.md 第 10 条）。

### R3 · 预执行路径只有"文本事实"，没有证据提供者；而跳过与通过在账本上长得一样

- **现象**：G3（43 条规则只有 1 条真正在查）、G6（依赖规则只认字面写法）、G7（分层靠文件名）。
- **证据**：
  - `src/adapters/dsh/adapter.py:241 proposed_dependencies()` —— 行级正则提取
    （`:234 _FROM_IMPORT_RE` / `:237 _PLAIN_IMPORT_RE` / `:238 _IDENTIFIER_RE`），**不是 AST**；
  - `src/policy/checkers.py:30 CONTEXT_CHECKERS = frozenset({"forbidden_dependency"})` —— 只需要上下文就能判的 checker 只有 1 个；
  - 其余 42 条（`style_lint` 39 / `missing_docstring` 1 / `missing_tests` 1 / `failing_tests` 1）需要 Phase 5 证据。
- **根因**：Phase 2 的 Hook 路径（"只提供上下文"）与 Phase 5 的验证器流水线之间**没有桥**。
  这本身是**设计取舍**（Phase 2 文档写得清楚），但取舍的后果没有被写进审计：
  42 条进 `skipped_rules`，账本上却和"检查通过"一样是 `allow`。
  **"跳过"与"通过"不可区分 = 治理宣称的能力与实际拦截面不符。**
- **判定**：**设计取舍 + 缺陷各一半**。取舍（不在 pre 路径跑 Ruff/pytest）保留；
  缺陷（跳过不可见、文本扫描冒充依赖证据）必须修。

### R4 · "在范围内"这一个语义被写了四遍，边界上四处不一致

- **现象**：G5（工作目录 = 项目根被判越界）、G8（`**/*.md` 匹配不到根目录文件）。
- **证据**：
  - `src/policy/models.py:162-163`：`if not segments: raise PolicyContextError("路径必须指向仓库内的文件")` —— `.` 被拒；
  - `src/policy/context.py:86-89`：`if len(target_parts) <= len(anchor_parts)` —— 绝对路径**等于根**被拒；
  - `src/adapters/dsh/adapter.py:277-278`：`**` 直接翻成 `.*`（**要求至少一层目录**），
    而同一仓库的 `src/validators/globs.py:37` 明确实现成 `(?:.*/)?`（零层可匹配）；
  - `src/validators/globs.py:9-12` 的 docstring 把这份分歧写成"**刻意不同**，不是疏忽"。
- **根因**：同一个语义（"这个路径在受控范围内吗"）在四个地方各实现一遍，没有单一权威函数。
  分歧被**文档化成"有意为之"**之后，就没有人再去比较谁对 —— 文档在这里起到了**掩盖缺陷**的作用。
  后果是不对称的：G5 让正确的事做不了（可用性），G8 让配置看着对、实际漏一层（静默失效）。
- **判定**：**缺陷**（"等于工作区根记为 `.`"是本仓库已在别处采用的口径，这里没跟上）。

### R5 · 声明式数据与运行期现实之间没有漂移检测；声明本身也不完备

- **现象**：G10（工具表缺 Agent Teams 工具）、G9（`run_code` 没有第二道闸）、G4（审批绑死运行时编号）。
- **证据**：
  - `src/adapters/dsh/adapter.py:163 TOOL_TABLE` 是默认拒绝的白名单，**缺** `spawn_teammate` /
    `team_task_*` / `wait_agent`（全仓库检索只在缺口文档里命中，代码里零命中）；
  - `registry/tool-registry.yaml:235-245`：`exec.run_code` 是 `driver: none` + `post_checks: []` +
    无 `allowed_commands`，唯一门禁是审批；
  - `src/enforcement/approvals.py:106` 审批只绑 `action_hash`，而 `action_hash` 覆盖运行时生成的
    `action_id` / `tool_use_id`（`src/enforcement/action.py:284-318`）。
- **根因**：白名单与注册表是**人工同步的静态声明**，没有任何机制把"运行期真的出现了什么"
  回灌成待评审项。**默认拒绝是对的安全策略，但"默认拒绝 + 人工同步"会退化成"接线即瘫痪"**：
  一挂上检查站，新工具全部判未知而阻断。
  G4 是同一根因的另一面：静态声明只表达了"这一次调用"，表达不了"这一类调用"。
- **判定**：G10 / G9 是**缺陷**；G4 是**设计取舍缺少一个必要选项**（单次绑定保留为更严格档）。

### 1.1 为什么这五个根因能同时存在（结构性解释）

| 层 | 它做对了什么 | 它不负责什么 |
| --- | --- | --- |
| Phase 2 Hook | 单次调用的失败关闭、脱敏、超时不等式 | 钩子是否成对注册（R1）、本机通道是否接线（R2） |
| Phase 5 验证器 | 真解析、真工具、真证据 | 被 pre 路径调用（R3） |
| 路径/范围 | 越界一律拒绝 | "等于根"这种合法边界（R4） |
| 注册表/工具表 | 默认拒绝、哈希审核 | 漂移检测、模式级授权（R5） |
| 审计 | 脱敏、追加写摘要链 | 覆盖了**几分之几**的面（R2/R3） |

每一格单看都是对的。**缺口全部长在格子之间的接缝上** —— 所以修复方式必须是
"给接缝加会失败的检查"，而不是继续在格子里加功能。

## 2. 本轮修复范围与写域

工作目录：`C:\Users\ZNM\Downloads\Memory`。四个实现工作流 + 一个独立验收工作流，
**写域互斥**（同一路径只允许一个 owner 写）。

| 工作流 | 根因 | 缺口 | 主要写域 |
| --- | --- | --- | --- |
| T1 hook-chain | R1 | G2, G12, G3(可见性), G11 | `src/adapters/dsh/policy-hook.plugin.mjs`, `src/adapters/dsh/hooks.py`, `src/adapters/dsh/README.md` |
| T2 channel-inventory | R2 | G13, G1 | `src/adapters/wiring.py`(新), `src/adapters/cli.py` |
| T3 rule-fidelity | R3, R4(glob), R5(工具表) | G6, G7, G8, G10 | `src/adapters/dsh/adapter.py`, `src/policy/checkers.py`, `adapters/dsh/manifest.yaml`, `adapters/approved.json` |
| T4 enforcement-availability | R4(路径), R5(审批/注册表) | G5, G4, G9 | `src/enforcement/*.py`, `src/policy/context.py`, `src/policy/models.py`, `registry/*` |
| V1 verifier | — | 全部 13 项 | `tools/governance_gap_probe.py`(新), 验收报告 |

### 冻结的跨工作流接口（写死，双方不得各自发明）

1. **T3 → T1（分层命中）**：`AdapterConfig.layer_resolution(repo_path)` 返回
   `LayerResolution(layer: str | None, matched_pattern: str | None, defaulted: bool)`。
   `layer_for()` 保留原签名（向后兼容）。T1 在审计里写 `layer` / `layer_matched_pattern` /
   `layer_defaulted`，未命中任何分层规则时 `defaulted=True` 且 `matched_pattern=None`。
2. **T3 → T2（工具表）**：`src/adapters/dsh/adapter.py` 的 `TOOL_TABLE` 是唯一声明源；
   T2 只读导入，不得复制一份。
3. **T4 → T2（审批/注册表）**：审批与注册表的失败一律仍走 `ReasonCode` 枚举；
   新增枚举值必须同时更新 `errors.STATUS_BY_CODE` 之外的**全部**未知值拒绝路径。

### 明确不做（并说明为什么）

| 缺口 | 不做的部分 | 理由 |
| --- | --- | --- |
| G1 | 把策略插件"装进"本机 desktop profile | 那是仓库外的主机配置；装上要重启 GUI，无法在本会话内验收。本轮改为**把它变成可发现的显式状态**（T2）+ 仓库内可复现的接线模板 |
| G3 | 把 Phase 5 验证器流水线接进 pre 路径 | 这是架构变更（Hook 进程要拿到 evidence provider 与工作区快照）。半截接线比不接更危险（会出现"看起来在查"的假证据）。本轮只做**如实标注** |
| G11 | 对注入内容做策略校验 | 需要对注入链路的所有权；本轮只做**来源与哈希留痕** |
| G7 | 按类名/依赖等内容特征推断层 | 内容推断会引入猜主体（违反 AGENTS.md 第 6 条）。本轮只做目录维度补充声明 + 显式标注 |
| G4 | "会话开始前声明调用编号空间" | 编号空间是 Agent 运行时的内部实现，声明它等于把运行期细节写进协议 |

## 3. 验收口径

1. **每条修复必须配一个"会失败的检查"**：单元/契约测试，或确定性探针脚本的一行断言。
   "改了代码但说不出哪条检查会因此变红"= 没修。
2. **独立验收（V1）**：用与实现者**不同的入口**复现 13 项现象，逐项给出
   `FIXED / PARTIAL / NOT FIXED / DEFERRED` + 证据路径 + 复现命令。
   V1 不得复用实现者写的测试作为唯一证据。
3. **基线对照**：`.tmp/governance-baseline.zip`（= `git archive HEAD` 的代码快照，不含未跟踪文档）
   用于"修前 / 修后"对照，证明行为确实变了，而不是测试被放宽。
4. **全量门禁**：Lead 独占运行 `python tools/ci_local.py`（AGENTS.md：同一工作树同时只允许一个）。
5. **不得放宽既有断言**：`tests/fixtures/decisions/` 的协议快照、已审核哈希、
   `SCHEMA_VERSION` / `POLICY_VERSION` 一律只能**显式**更新，且必须说明原因。

## 4. 已知风险

| 风险 | 处置 |
| --- | --- |
| G8 修好 `**/` 零层匹配会**放大**既有 layer/language 映射的匹配范围 | T3 必须逐条核对 `adapters/dsh/adapter.yaml` 的 pattern，把被放大的命中写进测试；若放大不可接受，改数据而不是改语义 |
| G6 改成"无法解析即拒绝"可能**过度阻断** | 只在 `forbidden_dependency` 这一类 checker、且规则 scope 命中时生效；必须先跑通 `tests/integration/test_rule_corpus.py` 的正反例夹具 |
| G4 模式化审批可能削弱防重放 | 按 `action_id` 的重放拦截**保持不变**；模式审批只放宽"人工签条"这一环，并加次数上限与时效 |
| T3 改 `TOOL_TABLE` 必须同步 `adapters/dsh/manifest.yaml` 并重新审核 | 契约测试逐项比对（AGENTS.md 第 28 条）；`python -m adapters.cli approve --reviewer <name>` 重签 `adapters/approved.json` |
| 四个工作流并发写 | 写域互斥 + 共享任务板上登记；越界写一律由 Lead 打回 |

## 5. 集成阶段记录：本轮新发现的缺口与遗留（Lead）

以下是**执行期内实测出来的、原始缺口清单里没有写**的问题。它们不改本轮范围，但必须留档，
否则下一次"治理覆盖缺口"实测会重新发现一遍。

| 编号 | 发现 | 坐标 | 处置 | 为什么不在本轮修 |
| --- | --- | --- | --- | --- |
| N1 | 多 Agent 路径的依赖提取仍是旧口径（不识别相对导入、不识别动态导入），G6 在这条路径上仍可绕过 | `src/adapters/textfacts.py`（被 `json_adapter` / `event_adapter` / `dsh_adapter` 共用） | **已修（2026-09-26，单开一轮）**：提取引擎搬进共享层，Phase 6 的接线点收敛到 `base.Adapter.to_policy_context`（一个引擎 + 一个接线点）。计划见 [07-ruff-cleanup-and-n1.md](07-ruff-cleanup-and-n1.md)，独立验收见 [08-n1-independent-verification.md](08-n1-independent-verification.md)（修前的红 → 修后绿 → 反向对照 → 两组灵敏度变异，四条验收全部通过） | 修它的**理由**：原判断是"改动聚焦"，但用户在本轮明确要求修；且它与本轮 ruff 清理同属"上一轮登记未清"的尾巴 |
| N2 | Phase 2 的 `load_config` 与 Phase 6 的 `adapter.yaml` 字段口径未合并：前者拒绝后者声明的 `schema_version` / `ledger_alias` / `max_events_per_window` / `window_seconds` | `adapters/dsh/adapter.yaml` vs `src/adapters/dsh/adapter.py:load_config` | **登记为待办**：两份配置各服务一条路径，合并需要一次显式设计 | 合并会改变两条路径的配置契约与已审核哈希，属于独立变更 |
| N3 | 词级匹配的过度近似：`forbidden: repository` 会命中 `order_repository_helpers` 这类同词模块名；`repositories`（复数）不命中 | `src/policy/checkers.py` 的 `dependency_forbidden` | **保留并写进实施记录**：方向是失败关闭（多拦不漏拦） | 精确匹配需要模块索引，与 N4 同因 |
| N4 | 预执行路径没有模块索引，判不了"顶层包存在、模块不存在"（`unresolved`）这一形态 | `src/adapters/dsh/adapter.py` 的 `propose_dependencies` | **保留**：已由 `tests/integration/test_dependency_path_consistency.py` 把这条不等价写成断言（已知差异而非静默差异） | 预执行路径拿到的是**变更片段**，不构成完整模块，建立索引需要读磁盘——会破坏"只看这次改动"的既有语义 |
| N5 | `run_hook()` 库内默认 `allow_unverified_wiring=True`，只有 CLI（生产入口）默认拒绝 | `src/adapters/dsh/hooks.py` | **保留并标注**：生产接线走 CLI，库内调用方（测试、notebook 生成器）显式可选 | 收紧会连带 27 处调用点与**已生成的学习手册**（`ci_local` 的 "Learning notebooks are in sync" 会一起红），超出本轮范围 |
| N6 | 本机平台驱动不可用：`shutil.which("pwsh")` 为 `None`、`bash` 走 WSL 被 `E_ACCESSDENIED` 拒绝 | 环境事实 | **写进验收报告**：G4 只能证明"审批绑定不再因运行时编号失效"，**不能**证明"受治理会话可以跑测试了" | 环境限制，不是仓库缺陷 |
| N7 | `tools/dsh_sandbox_loop.py` 原本没有"dsh 自身起不来"的环境跳过路径，默认 DSH_HOME 下会报 fail（写 profile 被沙箱拒绝，EPERM） | `tools/dsh_sandbox_loop.py` | **已修（Lead）**：新增 `dsh_could_not_start()` 与独立状态 `dsh_startup_denied`，仍走 `environment_skipped`（默认退出 0 + reason + reproduce，`--require-dsh` 下退出 1） | 属于本轮，因为它是 CI 步骤 "Real dsh sandbox loop" 的假红来源 |
| N8 | `src/adapters/cli.py` 有 8 处 HEAD 就存在的 ruff 违规；`tests/integration/test_dsh_hook.py` / `src/adapters/dsh/hooks.py` 等亦有既有违规 | 见 `02-channel-inventory.md` §9.1 | **已清理（2026-09-26）**：范围见 [07-ruff-cleanup-and-n1.md](07-ruff-cleanup-and-n1.md) §2（用户裁决 = 本轮改动集的 `src/` + `tests/` + 手写 `tools/`，清到 0 且**新增 0 条 noqa**）；边界外的 notebook 生成链与 `docs/` 计数不变，由独立验收逐文件核对 | 登记时的理由是"改动聚焦"，本轮由用户明确要求清理，因此不再成立 |
| N9 | **全量门禁抓出的连带破坏**：把"接线自检缺席 = 失败关闭"落到 CLI 后，凡是**直接调 CLI 的调用方**都要补 `--hooks-config`。T1 改了插件与 CLI，只改了 `tests/integration/test_dsh_hook.py` 之外的一个调用方；实际还有 **两个文档生成器**（`tools/build_learning_notebook.py`、`docs/project/architecture/tech-detail/notebooks/nb_cells/nb02.py`）与它们生成的 20 份 notebook | `ci_local` 的 "Learning notebooks are in sync" / "Tech-detail notebooks are in sync" | **已修（Lead）**：补 `write_hooks_config()` 与 3 处调用；并按"生成器是唯一真相源"重新生成产物 | 属于本轮。教训写在这里：**改一处契约要 grep 全部调用方**，只跑相关单测抓不到生成器 |
| N10 | 生成器里的**文档断言**随行为变化失效：依赖清单（G6 点分路径）、pre_decision 审计载荷键名（G4 新增三键）、post 审计记录条数（G11 多一条留痕） | 见上两处生成器 | **已修（Lead）**：更新为新的正确值；其中"数记录条数 == 4"改成了**语义断言**（每次调用有没有 pre 与 post）。理由是：计数会随不相干的记录增减而变红，或者更糟——被放宽成 `>=` 之后再也测不到"少了一段" | 属于本轮 |
| N11 | `docs/.../designs/os/06-*.md`（会话开始前就存在的未跟踪文档）引用合成演示令牌 `local-dev-token`，触发凭据扫描 | `secret_scan.py` | **已修（Lead）**：按仓库既有约定在**命中行本身**加 `secret-scan: allow` 注释并写明理由（与 `api/README.md:50` 同值，仓库历史上处理过同类问题两次） | 属于本轮：不修则本机门禁永红 |
| N12 | `tools/dsh_sandbox_loop.py` 只有"没有 dsh / Hook 起不来"两条环境跳过；本机默认 `DSH_HOME` 下 dsh **自身**因写 profile 被拒而起不来，会被判 fail | 见 N7 | **已修（Lead）**：新增 `dsh_could_not_start()` 与 `dsh_startup_denied` 状态 | 属于本轮，因为它是 CI 步骤 "Real dsh sandbox loop" 的假红来源 |
| N13 | **缺口探针自己有缺口**：`tools/governance_gap_probe.py` 的 G06 只驱动 Phase 2 的 `python -m adapters.dsh.hooks`，**从不走 Phase 6**。实测（V1）：拿它对**修前快照**跑 `--phase after`，仍然 **13/13、exit 0** —— 也就是说这个探针**看不到 N1**，不能用它当 N1 的验收证据 | `tools/governance_gap_probe.py` 的 `check_g06`（全文 grep `JsonAdapter` / `to_policy_context` **零命中**；`Env` 只有 Phase 2 的 `hook()`） | **本轮已做**：在 `check_g06` 加**显式范围声明**（只覆盖 Phase 2 路径）+ 指向真正覆盖 Phase 6 的检查；Phase 6 的四条路径由 `tests/integration/test_dependency_path_consistency.py`、`tests/contract/test_dependency_extraction_parity.py` 与 V1 的 `.tmp/verifier-n1/probe_n1.py` 覆盖 | **登记为下一轮候选**：给 G06 增加一组走 generic-json 规范事件的用例。**不在本轮做的技术理由**：探针完全没有驱动 Phase 6 的机器，新增检查会把 gaps 从 13 变成 14、改掉 `--phase after` 的期望表，属于**新仪器**而不是补注释；而 [08-n1-independent-verification.md](08-n1-independent-verification.md) 是在"13 条检查、行为未变"的前提下出具的——在半验证状态下改仪器，就是又做一台假绿仪器。下一轮的验收口径应当是"**它对修前快照必须变红**" |

| N14 | **依赖规则的"跳过"仍可能不可见**：`language` 声明不出来（`None`）时依赖集是 `()`，依赖类 checker 于是 allow——而 allow 的**理由**（"语言不知道"）没有任何地方写下来。今天没有洞，靠的是**规则作者的纪律**（43 条规则里只有 ARCH-001 用 `forbidden_dependency`，而它 scope 里声明了 `language=python`），不是代码保证 | `src/adapters/base.py` 的 `language` 解析 + `src/policy/checkers.py` 的 `dependency_forbidden` scope 匹配 | **登记为下一轮候选**：在**规则加载期**拒绝"使用 `forbidden_dependency` 却没有声明 language 维度"的规则——把"规则作者的纪律"变成**会失败的检查**，而不是靠人记得。由 T2 在写跨路径测试时发现并如实上报（不是实现缺陷，是**覆盖缺口**） | 属于"规则作者纪律 vs 代码保证"的口径问题，要改 `policy.loader` 的加载期校验与既有 43 条规则的 scope，是独立变更 |

## 6. 最终状态（集成收口）

**本机门禁：`python tools/ci_local.py --full` → 本机检查全部通过（32 步）。**

独立验收（V1，`tools/governance_gap_probe.py`，13 项 × before/after 双预期，`--repeat 2`）：

| 轮次 | `git diff HEAD \| git hash-object` | 规模 | 探针 | G07 |
| --- | --- | --- | --- | --- |
| 修前基线 | `git archive HEAD` zip | — | 13/13 与 before 一致 | — |
| 第 1 轮 | `1bf25c17…` | 38 文件（3258+/204-） | 12/13 | PARTIAL（探针**故意**保持红） |
| 第 2 轮 | `e13673c3…` | 39 文件（3270+/205-） | 13/13 | FIXED（含反向对照） |
| 第 3 轮（最终） | `30053031…` | 44 文件（3417+/215-） | **13/13** | FIXED（未变） |

**判定：FIXED 9（G02 G04 G05 G06 G07 G08 G09 G10 G13）· PARTIAL 4（G01 G03 G11 G12）· NOT FIXED 0。**

第二重验收（V2，用**原缺口实验自带的 harness**复跑，独立于 V1 的仪器）：
28 条探针对差 **EXPECTED_FIX 5 / UNEXPECTED_REGRESSION 0 / ENVIRONMENT 0**，其余 23 行无变化；
复跑期间 412 个文件 sha256 未变（对差结论成立）。

四条必须与结论一起读的口径：
1. **G01 仍是 PARTIAL**：本机 desktop/headless/web 三条通道仍未接线（`wiring --check` 如实报 not_wired）。本轮做的是**让它可被发现**，不是把它接上——接上要重启 GUI。
2. **G03 仍是 PARTIAL**：43 条规则里**仍只有 1 条**在 pre 路径真正参与判定，其余 42 条只是"可见地被跳过"（`effective_rule_count=0 / skipped_rule_count=43` 已进审计）。本轮做的是可见性，不是接线。
3. **G12 仍是 PARTIAL**：CLI 路径全部失败关闭，但 `hooks.run_hook()` 的**库内默认**仍放行（N5）。
4. **G04 只声明"审批不再因运行时编号失效"**：本机 `pwsh` 不在 PATH、`bash` 被 WSL 拒绝，**不能**声明"受治理会话现在能跑测试"。
