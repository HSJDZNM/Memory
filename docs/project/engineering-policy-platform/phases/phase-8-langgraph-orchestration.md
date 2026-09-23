# Phase 8：LangGraph 编排

## 目标

在 Policy Platform 已能独立服务多个 Agent 后，用 LangGraph 构建有状态、可循环、可恢复的上层工作流。LangGraph 是平台消费者，不拥有规则、权限或 Validator 语义。

## 工作流边界

```text
START
  → Requirement Analysis
  → Policy Retrieval
  → Architecture Planning
  → Implementation
  → Validation
      ├── FAIL → Repair → Validation
      └── PASS → Testing → Review → END
```

任何节点要调用工具，仍必须走 Policy Platform。Graph Edge 不能替代授权检查。

## 开发步骤

### 1. 定义最小 Graph State

只保存推进工作流需要的引用：task ID、当前阶段、artifact IDs、Policy trace IDs、验证摘要、重试计数和审批引用。敏感正文、密钥和完整工具输出不进入长期 checkpoint。

### 2. 先用 fake Policy Client

用固定 allow/block/error 响应测试状态机，再连接 Phase 7 API。这样可以区分编排缺陷与平台缺陷。

### 3. 实现明确节点

每个节点单一职责，输入输出有 schema。Policy Retrieval 只取得上下文；Validation 只提交证据；Repair 只基于结构化 violation 规划修复。

### 4. 限制循环

为 repair 次数、tool chain 深度、token、时间和费用设置硬上限。超过上限进入 `needs_human` 或失败状态，不能无限自调用。

### 5. Checkpoint 与恢复

Checkpoint 保存状态版本和已完成节点的幂等键。恢复时先确认规则集、索引和工具 schema 版本是否仍兼容；不兼容时重新评估，不沿用旧 allow。

### 6. Human-in-the-loop

高影响动作使用参数绑定、有效期有限的审批引用。恢复或参数改变后重新审批，不能把“图已到达该节点”视为用户批准。

## 测试步骤

### 状态机单元测试

- allow 路径按预期到 END；
- validation FAIL 进入 Repair 并再次验证；
- 达到最大 repair 次数后停止；
- 未知节点输出或缺失字段进入错误状态；
- 节点重试不重复执行已有副作用；
- PASS/FAIL 分支只由结构化 Decision 决定。

### Checkpoint 与恢复

- 每个节点后中断并恢复，结果与不中断执行一致；
- checkpoint 损坏、版本未知或状态缺失时安全失败；
- 旧规则集下的 allow 在恢复后重新评估；
- 已执行工具的 idempotency key 防止重复副作用；
- 敏感字段不进入持久化状态。

### 平台故障

- Policy API 不可用时停止高风险路径；
- Retrieval 不可用时不让模型凭记忆继续规范相关步骤；
- Validator 超时进入可诊断失败而不是 PASS；
- trace 传播中断时阻止执行并报告；
- circuit breaker 在反复失败时打开并停止调用。

### 人工审批

- 未审批、过期审批、错误主体和参数变化全部拒绝；
- 审批只能使用一次或按显式策略重用；
- resume 不绕过审批节点；
- 审批内容不被 Agent 消息伪造。

### 端到端学习场景

选择一个小型受控功能：需求分析 → 检索本仓库规范 → 规划 → 修改 fixture → AST/Lint/Test → 故意失败 → 修复 → 通过。保留每个节点的 trace ID 和 Decision，而不是只看最终代码。

## 观察点

观察“工作流如何前进”和“某个动作是否合规”由两套系统分别负责。替换 LangGraph 后，Policy API、规则、索引、Validator 和 Adapter 应继续工作。

## 退出条件

- Graph 使用公开 API/SDK，不导入 Policy Engine 内部实现；
- 循环、恢复、审批和平台故障全部有自动化测试；
- checkpoint 不存储敏感正文或可重放凭据；
- 受控端到端场景完整通过并可审计；
- 删除 LangGraph 应用不会影响 Policy Platform 独立运行。

至此形成：

```text
LangGraph 负责如何组织 Agent
Policy Platform 负责 Agent 应遵守什么
Agent / Tool 负责在授权后如何执行
```

## 实施记录

> 本节记录**实现事实**、踩到的坑与需要知道的偏差。安装、运行、测试命令以根 `README.md` 为准。

### 实际做了什么

| 计划步骤 | 落地物 |
| --- | --- |
| 1 定义最小 Graph State | `src/orchestration/models.py`：`GraphState`（任务、阶段、artifact/trace 引用、验证摘要、计数器、上限、审批引用）、`NODE_STATE_SCHEMA_VERSION = "1.0"`；**正文不入状态**：需求全文、文件内容、工具输出与凭据都只以摘要/引用存在，状态里没有墙钟字段（相同输入 → 逐字节相同的状态） |
| 2 先用 fake Policy Client | `src/orchestration/client.py`：`PolicyClient` 端口 + `ScriptedPolicyClient`（固定 allow/block/error，脚本用尽即 `PlatformUnavailableError`）+ `ApiPolicyClient`（标准库 HTTP，只走 Phase 7 的公开路由）+ `ResilientPolicyClient`（连续失败熔断） |
| 3 实现明确节点 | `src/orchestration/nodes.py`：八个单一职责节点（需求 / 检索 / 规划 / 实施 / 验证 / 修复 / 测试 / 收尾）；检索只取上下文、验证只提交证据、修复只读结构化 violation、写入先问平台再交 Phase 4 受控执行链 |
| 4 限制循环 | `src/orchestration/limits.py` + `RunLimits`：repair 轮次 / 工具调用 / 节点执行 / token / 费用 / 墙钟六个硬上限，击穿即 `LimitExceeded` → 失败码决定终态（`needs_human`），没有"截断后继续" |
| 5 Checkpoint 与恢复 | `src/orchestration/checkpoint.py`：原子替换的单文件 checkpoint（版本 + 摘要 + 兼容性凭据），`plan_resume` 给出 `resume` / `revalidate` / `reapprove` / `refuse` 四种结论；规则集或索引变化即清掉旧 trace 与旧验证结果并回到检索节点重评 |
| 6 Human-in-the-loop | `src/orchestration/approvals.py`：审批记录就是 Phase 4 的 `ApprovalRecord`，判定仍由 `enforcement.approvals.verify_approval` 做；编排层只把结论翻译成失败码（`approval_missing` / `approval_expired` / `approval_subject_mismatch` / `approval_param_mismatch` / `approval_consumed`） |
| （额外）| `src/orchestration/engines.py`（`StepExecutor` + 参考引擎）、`langgraph_engine.py`（LangGraph 引擎）、`graph.py`（图定义与条件分支）、`runtime.py`（显式装配）、`cli.py`（self-check / graph / status / run）、`src/orchestration/README.md` |

### 实际新增与变化

| 位置 | 内容 |
| --- | --- |
| `src/orchestration/models.py` | 新增：编排状态协议 `STATE_SCHEMA_VERSION = "1.0"`（**与平台阶段无关**，也不是决策协议）、`NodeId` / `StageStatus` / `RunStatus` / `FailureCode`、`RunLimits` 与 `Counters`、`ApprovalUse`、`NodeRun`、`PlatformSnapshot`；`policy_version` 与决策 schema 版本只从 `policy.models` 取值 |
| `src/orchestration/errors.py` | 新增：`FailureCode → RunStatus` 的 `STATUS_BY_CODE`。**终态由失败码决定**，节点与引擎都不许自己发明状态（`tests/unit/test_orchestration_state.py` 断言每个失败码都有映射） |
| `src/orchestration/engines.py` | 新增：`StepExecutor`——与框架无关的单步（上限记账 → 节点 → 路由 → 落盘 → 失败映射）。**落盘在路由之后**：checkpoint 里存的是"下一步做什么"，因此"checkpoint 之后崩溃"不会让恢复重跑刚完成的节点 |
| `src/orchestration/langgraph_engine.py` | 新增：唯一的框架导入点（构造引擎时延迟导入 + 主版本校验）。图结构不在这里：节点、静态边与条件分支都来自 `graph.DEFAULT_SPEC`；静态边也做成条件边，保证"失败即终止" |
| `src/orchestration/nodes.py` | 新增：写前记账（`_intent` 先刷盘再动手）+ 结算（`_settle`）；恢复时若发现"开工未结算"进入 `needs_human`（`side_effect_unknown`），既不重放也不假装成功 |
| `registry/tool-registry.yaml` | 变化：新增 **`orchestrator` 段**（`orc.fs.edit` / `orc.fs.write` / `orc.policy.edit`，最后一个是 `approval: required` 且路径必须匹配 `^policies/...`），并重新审核了 `registry/tool-registry.approved.json` |
| `tests/contract/test_enforcement_protocol.py` | 变化：注册表从 Phase 8 起**按 Agent 分段**，原先"注册表里的每个工具都属于 dsh"的断言改成只比对 `agent == "dsh"` 那一段；新增 `test_orchestrator_tools_match_the_orchestration_layer`（代码里的工具 ID、审核状态、路径范围与审批门禁逐项对齐） |
| `pyproject.toml` / `requirements.in` / `requirements.lock` | 变化：新增 `langgraph>=1.2,<2`（本机验证版本 1.2.11）。与 Phase 7 的 fastapi/uvicorn 同一条纪律：只有编排层需要它，核心层从不导入 |
| `tools/orchestration_loop.py` | 新增：Phase 8 闭环（真端口 uvicorn、真受控执行、真 checkpoint 与恢复） |
| `tools/phase_evidence.py` | 变化：`CURRENT_PHASE = 8`，新增 `orchestration()` 段（状态协议、引擎可用性、图节点、闭环结论） |
| `.github/workflows/phase-8.yml` | 由 `phase-7.yml` 重命名而来：追加编排自检与编排闭环两步，收尾步骤改名为 "Phase 8 acceptance evidence"，并补上缺失的 phase-7 手册校验 |

### 与原始计划的偏差（都需要知道）

1. **跨进程恢复用自己的 checkpoint，不用 LangGraph 的 checkpointer。**
   计划要求 checkpoint 里带"规则集 / 索引 / 工具 schema 版本是否仍兼容"——那是领域信息，
   通用 checkpointer 不提供，也不负责"不兼容时重新评估"。实现因此把
   **语义**（状态版本、幂等键、兼容性判定）放在 `checkpoint.py`，把**图执行**
   （递归、分支、状态通道）留给 LangGraph。`LangGraphEngine` 仍然接受外部注入的
   checkpointer 参数，但默认不依赖它。
2. **"不兼容"的判定基准是当前平台的凭据，不是新状态的空快照。**
   第一版实现拿"新建状态的快照"当基准，于是每次恢复都会因为"旧快照有规则集哈希、新快照是
   `None`"而被判成 `revalidate`。现在装配时先问 `/v1/health/ready`
   取当前 `rule_set_hash` / `index_version`；**拿不到就按"变了"处理**（重新评估），
   绝不按"没变"处理。
3. **恢复从"下一步"开始，而不是从头再跑一遍。**
   `StepExecutor.step` 先执行、再路由、再把"带着下一步的状态"落盘。这个顺序是
   "恢复不重复副作用"的真正依据；写前记账（intent）只是兜住"在副作用中间崩溃"的情况。
4. **LangGraph 的条件边返回的是标签，不是节点名。**
   第一版让路径函数直接返回目标节点，LangGraph 又把结果当成标签去查 `path_map`，
   于是得到 `KeyError: 'repair'`。现在路径函数只返回标签（并且先在 spec 里校验过），
   "标签 → 节点"交给 `path_map`。
5. **静态边也被改造成条件边。** 否则某个节点失败（写了 `failure`）之后，
   LangGraph 还会沿着静态边继续跑下一个节点——那就成了"失败之后继续动手"。
   两个引擎现在的终止语义完全一致（都由 `state.failure` 决定）。
6. **编排层的写入用 Phase 4 的受控执行链，但**不**经过 API。**
   Phase 7 明确没有 enforce 路由（"API 只回答允不允许"），因此"动手"这一步
   由 Agent 侧完成：编排层把动作交给 `PlatformToolRunner`（注册表 → action_hash →
   pre-check → 短时效授权 → 执行一次 → 事后验证 → 审计链）。判定入口仍然只有一处，
   编排层没有复制任何授权逻辑。
7. **写类动作的"证据"来自写后的验证节点，而不是写前。**
   写入前平台给出的判定是**无证据**的策略判定（`skipped_rules` 里记着需要证据的规则），
   工具链仍然完整（注册表 / 权限 / 路径范围 / 审批 / 限流 / 审计）。
   写入之后必须跑验证节点，`review` 节点拒绝在没有通过验证的情况下收尾——
   "图跑完了"不等于"通过"。
8. **引擎选择是显式可观测的。** `engine="auto"` 在 LangGraph 不可用时回落到参考引擎，
   但 `RunReport.engine` 会如实写明用的是哪一个；`engine="langgraph"` 不可用即
   `EngineUnavailableError`，不静默回落。
9. **编排协议有自己的版本名。** `STATE_SCHEMA_VERSION = "1.0"` 只描述**图状态**的形状，
   与 `API_SCHEMA_VERSION`、决策协议 `SCHEMA_VERSION`、
   `policy_version`（世代名 `phase-1`）互不影响——"改编排状态"不等于"改规则语义"。
10. **审批语义不另起一套。** 编排层的 `ApprovalGate` 只是 Phase 4 `verify_approval` 的调用方：
    判定权在平台，编排层只负责把"为什么拒绝"翻译成编排层的失败码（依据结构化字段，不解析错误文本）。
11. **审批绑的是平台的 `action_hash`，不是编排层的幂等键。**
    第一版把编排层自己的 `action_id` 当成审批绑定的哈希，于是出现一种很典型的假通过：
    编排层放行，Phase 4 的 pre-check 判"参数或主体已变化"（`approval_invalid`）而拒绝执行。
    现在 `ToolRunner` 端口多了 `binding(request)`：由平台口径算出 `action_hash`
    （覆盖工具 schema 哈希、规范化参数、主体、权限、上下文摘要**与 trace**），
    人工审批必须绑它；找到的审批**文件**原样交给 pre-check，判定权仍在平台。
12. **审批收件箱按 `action_id` 挑选，而不是按 `action_hash`。**
    若按哈希挑，主体不符 / 参数漂移 / 过期只会得到一句笼统的"没有审批"。
    按 `action_id`（任务 + 轮次 + 改动摘要）挑出**那条**记录，再由平台判定，
    失败码才能具体到 `approval_subject_mismatch` / `approval_param_mismatch` / `approval_expired`。
13. **恢复会清掉上一轮的终止标记。**
    第一版把 `failure` / `status` 原样带进恢复后的状态，于是"续跑"在第一个节点之后
    又因为"还有 failure"而停下——恢复等于没恢复。现在 `plan_resume` 对
    RESUME / REVALIDATE / REAPPROVE 三种结论统一把状态复位成 RUNNING + 无失败码：
    失败是"上一轮为什么停"，不是工作流的进度。
14. **写前记账必须自己刷盘。** 节点把"意图"写进状态并不会自动进 checkpoint
    （引擎是在节点返回之后才落盘）。因此 `NodeContext` 暴露了一个显式的
    `commit` 端口（由引擎注入），意图写完立刻刷盘；否则"在副作用中间崩溃"
    在恢复时完全看不见，保护也就名存实亡。

### 已知边界（不假装做到）

- **真实作者（模型）没有接入**：候选改动来自 `ChangeAuthor` 端口，仓库里只有确定性的
  `ScriptedAuthor`；接入模型不改变任何节点契约，但本阶段没有验证过真实模型的行为。
- **熔断是进程内的**：连续失败计数 + 显式复位，没有分布式协调，也没有自动恢复。
- **恢复不解释"人工已经处理过"**：`side_effect_unknown` 之后即使人工确认了结果，
  编排层也不会自己继续——需要重新发起一次运行（新的幂等键）。
- **编排层不执行命令类工具**：注册表里只声明了写入类与"改规则"工具；
  需要 shell 的场景仍然由 Agent 侧的受控执行链负责。
- **没有分布式一致性**：同一 task 的两个进程同时恢复同一个 checkpoint 不受保护
  （单机文件原子替换只保证"不会读到半份"）。
- **LangGraph 版本区间只验证了一个版本**：1.2.11；主版本变化一律拒绝，未做向后兼容矩阵。
- **审批记录是未签名的结构化文件**（沿用 Phase 4 的口径）：它的可信度来自"由谁放进收件箱"
  与审批人角色声明；单次使用由 Phase 4 的台账保证，作用域是**那一次部署的台账**——
  换一份台账（新的一次运行）等于换了一套账，同一份审批会被视为未使用。
  真正的签名/审批服务属于部署环境，本阶段不假装有；编排层只读取审批，代码里没有任何写审批记录的路径。
- **token 与费用上限的口径依赖作者端口如实上报**：`Change` 携带 `tokens` / `cost_units`，
  由作者（真实系统里是模型客户端）声明，编排层只负责记账与拦截。本阶段没有真实模型，
  因此这两条上限被验证的是**机制**（击穿即 `needs_human`），而不是被真实用量校准过——
  把未上报的用量当成 0 是这套机制的已知弱点。

### 独立交叉验证（Phase 8 交付后做的，结论写在这里）

交付后由**另一个会话**做了一次对抗性验证：验证者只读仓库、自己写探针（`.tmp/verify-phase8/probe*.py`），
逐条试图**证伪** 8 组不变量（授权判定、依赖方向、状态与 checkpoint 的保密性、审批语义、
循环上限、恢复语义、平台故障失败关闭、闭环场景自身的断言强度）。结论与处置：

| 发现 | 现象 | 处置 |
| --- | --- | --- |
| 状态可以夹带正文/凭据 | 把需求原文（含 `sk-` 形态假凭据）放进 `TaskSpec.acceptance`，它会逐字进入 `state.requirements` 并落进 checkpoint | **已修**：`models._safe_text` 把"短结论"变成**硬约束**——超过 200 字符或含凭据形态取值（`sk-`/`Bearer x`/私钥块）直接拒绝构造成状态；验收条目本来就该是短结论，不是正文 |
| 墙钟上限是死参数 | `LimitKind.ELAPSED_MS` 全仓没有一处 `charge`，`max_elapsed_ms=1` 时实跑 57ms 仍 `completed`，`counters.elapsed_ms=0` | **已修**：上限在**引擎**这一层检查（每次推进前比对本次运行已用时间），击穿即 `needs_human`/`limit_wall_clock`；刻意**不写回状态**——状态里一旦有墙钟数字，"相同输入得到逐字节相同的状态"就不成立了 |
| `engine="auto"` 的回落承诺不成立 | LangGraph 缺席时 `auto` 仍然选中 LangGraph 引擎，运行期才失败（`engine="langgraph"/failed/engine_unavailable`） | **已修**：`LangGraphEngine.__init__` **构造即校验**（版本区间不认识就 `EngineUnavailableError`），`auto` 的回落这才真的可达 |
| checkpoint 的兼容性块没有被摘要覆盖 | 只改 `compatibility` 的 `rule_set_hash`/`index_version`/`tool_schema_hash`，就能把 `revalidate` 变成 `resume`、旧 trace 原样保留（"不沿用旧 allow"被绕过） | **已修**：新增 `record_digest`，覆盖**除自身外的整条记录**；篡改 state 或 compatibility 都会被 `CheckpointError` 抓住（它仍然是摘要而不是签名） |
| 判定针对的是任务模板，不是真正要改的文件 | 改 `policies/…` 的动作拿着"控制器文件"的上下文去问平台（`file=task.target`），"平台允许"与"你写了什么"是两件事 | **已修**：`_apply_change` 用 `change.path` 构造判定上下文；越界仍由注册表的 `path_scope` 与审批门禁兜住 |
| 幂等键不覆盖请求体 | 判定上下文一变、键不变，平台（**文件台账，跨进程**）返回 `409 idempotency_key_conflict`，动作直接 `blocked` | **已修**（修上一条时暴露）：evaluate 的幂等键 = `状态幂等键 + 请求摘要`；同一个请求重放才幂等，请求变了键就变 |
| 审批未签名、单次使用按台账计 | `ApprovalRecord` 没有签名，`granted_by`/`granted_by_roles` 是自述；同一份审批换一份台账（新的一次运行）会被视为未使用 | **不改，写进已知边界**：这是 Phase 4 的既有口径——审批的可信度来自"由谁放进收件箱"，真正的签名/审批服务属于部署环境（与 Phase 7 的静态令牌同一条边界）。编排层的代码里**没有任何写入审批记录的地方**，闭环里的签发走的是 `enforcement.cli approve`（人工门禁） |
| 闭环自身有三处断言偏弱 | 场景 6 的"判定真的走到门禁"只写进 facts 未进 `passed`；场景 4 的"checkpoint 无正文"用 4 个手写字面量；facts 里出现过绝对路径 | **已修**：`routed_to_gate` 进 `passed`；敏感标记改为从**本次任务与本次改动**派生；facts 全部改成仓库相对路径 |

验证者同时确认了 4 组不变量**成立**：编排层不做授权判定（唯一的文件写入点是 checkpoint 与 CLI 建目录，
没有平台判定就不执行工具）；只有 `langgraph_engine.py` 导入工作流框架，核心层不导入 `orchestration`
（用 `sys.meta_path` 阻断器实测：`policy.check` / `policy_api.cli self-check` / `enforcement.cli` /
`retrieval.cli verify` 全部照常退出 0）；平台不可达 / 503 / 504 / 缺决策 / trace 断裂全部失败关闭且零执行；
工具调用中被杀会留下"开工未结算"并停止交给人（工具只被调用 1 次），未知协议世代拒绝恢复、
工具 schema 变化会让旧审批作废。

**环境事实（供后来者）**：本机 `.venv` 里没有 pip，也没有 fastapi/uvicorn/langgraph；
`ci_local.py` 会优先用 `.venv`，因此本机跑门禁要用
`python tools/ci_local.py --full --python C:\Users\ZNM\miniconda3\python.exe`（AGENTS.md 已记这条）。
`langgraph-checkpoint-sqlite` 在本机装不上（pip 无法写入自己的 mkdtemp 目录），
这也是"跨进程恢复用自己的 checkpoint"的一个现实理由——但即使它可装，领域兼容性仍然要自己判断。

### 验收证据

```powershell
$env:PYTHONPATH = "src"

# 装配自检：图定义 / 引擎可用性 / 注册表审核 / checkpoint 往返 / 状态协议
python -m orchestration.cli self-check

# 编排闭环：8 个场景（真端口 uvicorn + 真受控执行 + 真 checkpoint 与恢复）
python tools/orchestration_loop.py

# 四层测试：本机实跑 1098 passed、1 skipped（Windows 不允许普通用户创建符号链接）
python -m pytest tests/unit tests/contract tests/integration tests/security -q

# 阶段证据（含 orchestration 段：协议版本、引擎、图结构、闭环结论）
python tools/phase_evidence.py
```

新增测试：`tests/orchestration_support.py`（脚本化客户端、受控工作区、装配与运行助手）+
`tests/{unit/test_orchestration_state,contract/test_orchestration_engine,
integration/test_orchestration_runtime,security/test_orchestration_adversarial}.py`。
测试**不联网、不起端口**（HTTP 形状用假 opener 与未使用端口验证失败关闭），
真端口链路由 `tools/orchestration_loop.py` 覆盖。

### 退出条件对照

| 退出条件 | 证据 |
| --- | --- |
| Graph 使用公开 API/SDK，不导入 Policy Engine 内部实现 | `tests/contract/test_orchestration_engine.py`：只有 `langgraph_engine.py` 导入 `langgraph`；`src/orchestration` 不出现 `policy.engine` / `policy.loader` / `policy.check` 的导入；平台判定只经 `/v1/policy/evaluate`、`/v1/knowledge/retrieve`、`/v1/validation/evaluate` |
| 循环、恢复、审批和平台故障全部有自动化测试 | 四层共 95 个编排用例 + 闭环 8 个场景（端到端 / 引擎可替换 / 循环上限 / checkpoint 与恢复 / 规则集变化 / 人工审批 / 平台故障与熔断 / 幂等） |
| checkpoint 不存储敏感正文或可重放凭据 | `tests/security/test_orchestration_adversarial.py::test_secrets_never_land_in_checkpoints_or_reports`（需求正文、文件正文、`sk-` 形态凭据都不出现在 checkpoint 与报告里）+ 闭环场景"checkpoint 与恢复"对 checkpoint 原文的敏感标记断言 |
| 受控端到端场景完整通过并可审计 | 闭环场景 1：需求 → 检索 → 规划 → 受治理写入（Phase 4 链路）→ 验证失败（ARCH-001 / TESTING-002）→ 修复 → 通过 → 测试 → 收尾；审计链与台账落在 `.tmp/phase-8-orchestration/runs/<tag>/`，每个节点都有 Policy trace |
| 删除 LangGraph 应用不会影响 Policy Platform 独立运行 | 依赖方向由契约测试双向钉住（核心层从不导入 `orchestration`）；`engine="auto"` 在框架缺席时回落参考引擎并如实自报；平台自身的四层测试与全部闭环不经过编排层 |
