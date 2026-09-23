# Phase 6：多 Agent Adapter

> 状态：仓库内协议、运行时、门禁与测试已完成。当前只有 dsh 是实际产品接入；
> `generic-json` 与 `legacy-post-only` 是合成协议消费者。第二真实 Agent 的产品验证尚未完成。

## 目标

证明多个 Agent Runtime 可以通过同一套事件和决策协议接受一致治理，同时不修改 Policy Engine。dsh Adapter 是参考实现，其他 Adapter 只能做协议转换。

## 统一接口

```text
Agent Runtime
  → AgentAdapter.to_policy_event(raw_event)
  → Policy Platform
  → AgentAdapter.to_agent_response(decision)
```

Adapter 能力声明至少包含：支持的事件、工具、pre/post hook、阻断能力、审批能力和协议版本。平台不得假设所有 Agent 都支持同样的 Hook。

## 开发步骤

### 1. 固化 Canonical Event Schema

标准事件包含 `schema_version`、`event_id`、`event_type`、`request_id`、`trace_id`、`agent`、`principal`、`timestamp` 和 `payload`。事件类型使用 [核心契约](../01-architecture-and-contracts.md#标准事件) 中的受控枚举。

### 2. 提取 dsh Conformance Fixture

把 Phase 2 的 dsh 用例改造成与实现无关的输入/期望对，作为所有 Adapter 的一致性套件。

### 3. 实现 Generic Adapter

先实现一个 JSON Adapter，作为协议示例和测试工具。它不对应具体 Agent，但能验证第三方只要生成标准事件即可接入。

### 4. 按能力增加具体 Adapter

建议顺序：dsh → Generic JSON → Codex/Claude Code。每次只新增一个 Adapter，并先记录当前产品版本实际提供的 Hook、MCP 或 SDK 边界。

### 5. 隔离 Agent 身份与状态

不同 Agent、会话、主体和项目分别命名空间化。一个 Agent 的检索结果、审批、缓存、工具能力或 trace 不能被另一个 Agent 隐式继承。

### 6. 兼容能力差异

如果某 Agent 只有 post-hook 而没有可靠 pre-hook，Adapter 必须声明无法强制阻断，平台不得把它标记为完整 enforcement。能力不足应在接入时显式失败或降级为只读模式。

## 测试步骤

### 一致性套件

每个 Adapter 对同一组语义事件必须满足：

- 等价 edit 事件产生等价 PolicyContext；
- 路径、operation、主体和 trace 保留；
- block 不触发原生工具；
- allow 只触发一次；
- 未知事件和版本被拒绝；
- 错误响应能被 Agent 理解但不泄露内部信息；
- 重复 event ID 幂等。

### 差异测试

记录各 Agent 对取消、超时、重试、并发和工具错误的不同语义。差异只能留在 Adapter 内，核心测试期望不随 Agent 分支。

### 多 Agent 安全测试

- Agent A 的审批不能用于 Agent B；
- Agent A 的缓存或检索片段不能泄漏给 Agent B；
- Agent A 发送的消息不能提升 Agent B 工具权限；
- trace 传播可验证来源，伪造父 trace 被拒绝；
- Agent 间消息中的“系统指令”只作为不可信数据；
- circuit breaker 能终止互相触发的无限循环。

### 兼容性测试

保存各 Adapter 的最小真实事件 fixture 和产品版本。升级 Agent Runtime 时，先重跑 fixture 与沙箱集成测试，再更新支持矩阵。

## 观察点

当前可比较 dsh 与两个合成协议消费者的事件差异；待具备第二个真实 Agent 环境后，还要用其真实 fixture
重跑同一套比较。新增 Adapter 不应迫使 Rule 或 Engine 增加 Agent 专用分支。

## 退出条件

- 至少两个不同 Agent/协议消费者通过一致性套件；
- 支持矩阵明确区分完整 enforcement、只读与不支持；
- 跨 Agent 隔离和循环限制测试通过；
- 核心层没有新增 Agent SDK 依赖；
- Adapter 升级流程和版本 fixture 已文档化。

以上是仓库内实现的退出条件；产品验收还要求**第二个真实 Agent**以真实版本和事件 fixture
通过一致性套件。当前不能用两个合成消费者冒充这条外部证据。

## 实施记录

本记录对应 Phase 6 的七个开发步骤、三组测试与五个退出条件。**实际命令以根 `README.md` 为准**，
这里只记录实现事实、踩到的坑与需要知道的偏差。

### 实际做了什么

| 计划步骤 | 落地物 |
| --- | --- |
| 1 固化 Canonical Event Schema | `src/adapters/models.py`：`AgentEvent`（`schema_version` / `event_id` / `event_type` / `request_id` / `trace_id` / `parent_trace_id` / `agent_id`+版本 / `occurred_at` / `principal` / `tool` / `operation` / `payload` / `payload_digest` / `input_fields`），`EventType` 受控枚举（含 Phase 6 新增的 `agent.message`），`parse_canonical_event` 只认受控字段 |
| 2 提取 dsh Conformance Fixture | 一致性套件本身即"与实现无关的输入/期望对"（`src/adapters/conformance.py`，12 个场景、87 项检查）；报告按 Adapter 给出 checks/inapplicable 覆盖，不能只列名字却不运行；dsh 的最小真实事件样本沿用 Phase 2 fixture |
| 3 实现 Generic Adapter | `src/adapters/json_adapter.py`（`canonical-json` 协议）：第三方只要产出规范事件即可接入，不需要装任何 SDK |
| 4 按能力增加具体 Adapter | `adapters/dsh/`（`canonical-tool-table`，复用 Phase 2 的代码工具表）、`adapters/generic-json/`、`adapters/legacy-post-only/`（只有 PostToolUse 的协议消费者） |
| 5 隔离 Agent 身份与状态 | `src/adapters/runtime.py`：台账键 `<adapter.namespace>:<event_id>`（默认 agent id，`ledger_alias` 可覆盖）、主体只认声明、trace 登记表按 `owner_agent` 校验、窗口熔断 |
| 6 兼容能力差异 | `ceiling_from_capabilities`（`base.py`）：由声明推出上限，`post_only`/无 pre-hook → `read_only`；受治理动作得到 `capability_unavailable` |
| 7（额外）一致性与支持矩阵可执行 | `src/adapters/cli.py`（`matrix` / `approve` / `check` / `inspect` / `events`）、`adapters/approved.json` 已审核哈希、`tools/agent_loop.py` 闭环 |

### 实际新增与变化

| 位置 | 内容 |
| --- | --- |
| `src/adapters/models.py` | 新增：规范事件 Schema、能力声明模型（`AdapterManifest` / `ParticipantCapability` / `HookNames` / `AgentTool` / `Capability`）、`AgentResponse`、`normalize_event_path`（受控字段 + 路径归一化） |
| `src/adapters/base.py` | 新增：`Adapter`（事件校验 / 上下文构造 / 响应翻译）、`AdapterRegistry`（原子加载 + 已审核哈希比对）、`SupportCeiling`、`AdapterDescriptor`/`AdapterList`（支持矩阵） |
| `src/adapters/runtime.py` | 新增：`AgentRuntime`（原子 claim、Phase 5 evidence gate、Policy 判定、Phase 4 pre/post、callback 至多一次、幂等台账、窗口熔断）、`TraceRegistry`（严格读取的 trace 来源表）、`sanitize_message`、受控原因码 `REASON_CODES` |
| `src/adapters/textfacts.py` | 新增：与协议无关的"变更文本 → 直接依赖"提取（Phase 2 的实现搬到这里，两个 Adapter 共用一份） |
| `src/adapters/json_adapter.py`、`event_adapter.py`、`dsh_adapter.py` | 新增：三个协议实现；`event_adapter` 是钩子类 Agent 的公共实现（事件名与字段名来自 manifest） |
| `src/adapters/conformance.py` | 新增：12 个语义场景 + 场景渲染器 + 逐项检查；当前覆盖 dsh 40 项、generic-json 35 项、legacy-post-only 12 项显式不适用，共 87 项。**Phase 7 变化**：`conformance_enforcer` 的判据从"它是不是 dsh"改成"它有没有声明工具注册表与已审核哈希"——任何接入 Phase 4 的 Adapter 都走同一条链路，第二个接线的 Agent 不必复制一份桥接层 |
| `src/adapters/loader.py`、`cli.py`、`__main__.py` | 新增：装配（协议 → 实现类）、五条子命令 |
| `adapters/` | 新增：`dsh` / `generic-json` / `legacy-post-only` 三份 manifest + adapter 配置 + 事件样本 + `approved.json` 已审核清单；fixture 路径一律是**仓库相对路径**（"样本在哪"写在声明里，不允许读取方按 Agent id 去猜） |
| `tests/fixtures/agent_events/workspace/` | 新增：一致性套件的**探针工作区**（layer 映射与"越界"的真实边界都靠它） |
| `src/adapters/__init__.py` | 变化：从空包变为显式导出（协议、注册表、运行时、套件） |
| `tests/contract/test_agent_adapters.py` | 新增：40 个用例（manifest 校验、能力上限、规范事件白名单、路径、注册表漂移、工具表一致性、场景渲染） |
| `tests/integration/test_multi_agent_runtime.py` | 新增：36 个用例（一致性套件、能力降级、Phase 4/5 门禁、原子幂等、pre/post 生命周期、trace、熔断、CLI） |
| `tests/security/test_multi_agent_adversarial.py` | 新增：17 个用例（身份伪造、内部字段注入、协议降级、超大与二进制载荷、响应不泄露） |
| `tests/conftest.py` | 变化：新增 `module_tmp_root` / `tmp_root_factory`（都不依赖 `mkdtemp`） |
| `tools/agent_loop.py` | 新增：多 Agent 闭环（7 个场景 + 一致性套件结论，写给阶段证据） |
| `tools/phase_evidence.py` | 变化：`CURRENT_PHASE=6`，新增 `agent_adapters` 段（支持矩阵 / 协议版本 / 能力上限 / fixture / 闭环结论） |
| `tools/ci_local.py` | 变化：登记 Phase 6 的四个步骤与 `adapters/` 前缀 |
| `.github/workflows/phase-6.yml` | 替换 `phase-5.yml`：追加一致性套件、支持矩阵审核、fixture 存在性、多 Agent 闭环四步 |

### 决策链的形状（一次多 Agent 判定的九个位置）

    (1) 装配：manifest（能力声明）+ adapter 配置 + 已审核哈希
        → 未审核 / 哈希漂移 / 能力不足 / 工作区不存在 → 拒绝接入
    (2) 协议转换：AgentAdapter.to_policy_event(raw)
        → 未知事件、未知工具、缺路径、路径越界、".." 逃逸 → 拒绝（context_error / unknown_*）
    (3) trace 与身份：trace 登记表（owner_agent）+ 主体（只认 Adapter 声明）
        → 伪造父 trace → trace_forged；载荷自称主体 → context_error
    (4) 能力门禁：写类动作要求"具备执行前阻断能力"
        → post_only / 无 pre-hook / 主动收紧的上限 → capability_unavailable
    (5) 幂等与熔断：先原子 claim；台账键 <adapter.namespace>:<event_id>；窗口内事件数上限
        → 重放 → event_replay；同标识换参数 → event_id_reuse；循环 → request_busy
    (6) Phase 5 证据：写类动作必须取得 EvidenceBundle
        → 未接入 / 崩溃 / 类型错误 → evidence_unavailable
    (7) Policy 判定：evaluate(..., evidence=...)
        → block / timeout / evaluator 异常 → policy_block / policy_timeout / engine_error
    (8) Phase 4 受控执行：Tool Registry → 参数 allowlist → pre-check；PostToolUse 只跑 post-check
        → 未接线 / 未登记工具 → enforcement_unavailable；授权失败 → enforcement_block
    (9) callback 与响应：claim + Policy allow + pre-check allow 后才调用 callback
        → callback 恰好一次；异常 → execution_failed；post 事件绝不再次调用 callback

### 与原始计划的偏差（都需要知道）

1. **"审批不能跨 Agent 复用"用命名空间实现，而不是在审批文件里加 Agent 字段。**
   Phase 4 的授权与 `action_hash` 绑定，而 `action_hash` 已经覆盖 Agent、主体、参数与
   上下文摘要；因此 A 的授权在 B 那里本来就对不上。Phase 6 补的是**读取侧**的隔离：
   幂等与审计键以 `<adapter.namespace>:` 为前缀，A 的 allow 记录不会被 B 当成"已经批准过"。
   比"再加一个字段"更强的地方在于：它不依赖任何一方写对字段。
2. **第二个"Agent"是明确标注的第三方协议消费者，不是某个真实产品的克隆。**
   `legacy-post-only` 与 `generic-json` 都写在 `adapters/*/manifest.yaml` 的 `notes` 里，
   说明它们代表"只有 PostToolUse 的 Agent"与"产出规范事件的 in-house 消费者"。
   仓库内退出条件要求至少两个协议消费者；产品验收仍要求第二真实 Agent。真实的 Codex / Claude Code
   接入需要先核实产品版本与钩子契约，这件事留在有该环境的机器上做（流程见下）。
3. **Generic Adapter 主动声明 `read_only`。** 它的协议完整、也确实具备执行前阻断能力，
   但接入方要求"只治理只读动作"，于是平台尊重更严的上限。这条同时证明：
   上限不只看能力，也看接入方的选择。
4. **熔断按"窗口内事件数"而不是"单个 request_id 的事件数"。** 计划写的是 loop breaker，
   实现里最初按 `request_id` 计数，被一致性套件的循环场景当场打脸：
   真实循环里每次触发的 `request_id` 都可能是新的，按请求计数永远数不到上限。
   现在按 `(agent, 时间窗口)` 计数（`max_events_per_window` / `window_seconds`），
   并且刻意在配置里写明这条理由，避免以后被"优化"回去。
5. **`EventType` 增加了 `agent.message`。** 计划的安全测试要求"Agent 间消息中的系统指令
   只作为不可信数据"，因此需要一个受控事件类型来承载它；它只登记不判定，
   消息内容不参与任何策略判断（有对抗用例钉住这一点）。
6. **一致性套件的场景是语义而非报文。** 每个 Adapter 用**自己的**事件名与工具名渲染同一个场景
   （`render_event`），因此"新增一个 Agent"只增加渲染分支；核心测试期望里没有
   `if agent_id == ...`。Adapter 声明不支持某事件时渲染器显式抛错，不静默跳过。
7. **`policy_version` 不变。** 规范事件有自己的 `schema_version = "1.0"`（`AgentEvent` 的兼容轴），
   决策载荷仍然是 Phase 1 的 `schema_version = "1.0"` / `policy_version = "phase-1"`：
   Phase 6 没有改决策协议，因而快照未动（`tests/fixtures/decisions/` 原样）。

### 失败关闭是怎么实现的

1. **未审核或哈希漂移的 manifest** → 整次注册表加载失败 / 装配拒绝（`AdapterRegistry.check_approved`、`load_adapter`）；
2. **能力不足** → 上限被算成 `read_only`，写类动作 `capability_unavailable`（不是"跳过治理"）；
3. **协议不认识的东西** → 未知版本、未知字段、未知事件类型、未知操作、未知工具一律拒绝，
   原因码区分 `unknown_version` / `unknown_event` / `unknown_tool` / `context_error`；
4. **路径证明不了** → 绝对路径越界、含 `..` 的相对路径、空路径一律拒绝（含只读动作）；
5. **身份证明不了** → 载荷自称 `agent_id` 无效（装配处钉死）；载荷自称主体与声明不一致即拒绝；
6. **来源证明不了** → 伪造或未发放的父 trace 一律 `trace_forged`；
7. **循环** → 窗口内事件数到上限即 `request_busy`；重复 `event_id` 一律不执行第二次；
8. **判定超时 / 引擎异常** → `policy_timeout` / `engine_error`，都阻断；
9. **运行时 / trace 台账不可验证** → 损坏、未知版本、不可读写统一得到 `ledger_unavailable` 阻断；
10. **验证器证据不可用** → 写类动作 `evidence_unavailable`，不能把 skipped 当作 allow；
11. **受控执行不可用或拒绝** → `enforcement_unavailable` / `enforcement_block`，Policy allow 不能替代授权；
12. **callback / post-check 失败** → `execution_failed` / `postcheck_*`；post 事件不会再次执行 callback；
13. **Phase 4 台账与审计不可写** → 受治理动作不执行；两种 JSONL 协议分文件保存，避免混写后无法严格验证。

### 一处环境观察（与本阶段实现无关，但影响测试写法）

Windows 的受限沙箱里 `tempfile.mkdtemp` / `chmod` 会被拒绝，pytest 的 `tmp_path` 因此
在部分用例上直接 PermissionError。仓库已有的约定是"只用 `mkdir` + 唯一名字"，
Phase 6 把它扩成两个夹具（函数级 `tmp_root`、模块级 `module_tmp_root`）——
一致性套件这类"跑一次、多个用例共用结论"的夹具需要模块级作用域。
**不要改用 `tmp_path`**：那会让测试在受限环境里因为与被测行为无关的权限错误失败。

### 二次复核发现并已修复的问题

| # | 问题 | 修复 | 回归用例 |
| --- | --- | --- | --- |
| P1 | dsh Adapter 在构造事件时就按 `adapter 配置里的默认工作区` 归一化路径，逃逸（`../outside.py`）被 `normpath` 成一次静默的"相对路径"，越界检查再也看不到它 | 范围校验统一绑定**本次判定的工作区**（`to_policy_event(..., workspace=...)` → `_build_event` → `_resolve`），并对含 `..` 的相对路径无条件拒绝 | `path-escape` / `absolute-path-outside` 两个场景 + `test_normalize_event_path_rejects_relative_escape` |
| P2 | 能力门禁与主体核对顺序颠倒：写错主体的请求被"能力不足"掩盖，Agent 得到的是"换个 Agent 吧"而不是"你的主体写错了" | 先构上下文（核对主体）再判能力上限 | `test_subject_cannot_be_self_asserted` / `test_principal_is_declared_not_self_asserted` |
| P3 | 只读上限的 Adapter 只拦"pre_execute 事件"，PostToolUse 形态的写类动作照样放行 | 门禁按"**动作**是否需要执行前阻断"判断，而不是按事件类型 | `test_post_only_adapter_refuses_mutating_actions` |
| P4 | 熔断按 `request_id` 计数，循环场景里永远数不到上限（一致性套件当场失败） | 改成按 `(agent, 时间窗口)` 计数，配置键改名并写明理由 | `test_breaker_terminates_a_cross_agent_loop` / `breaker-terminates-loop` 场景 |
| P5 | 一致性套件复用同一份台账，"上一次运行的 event_id"把本次拦成重放/熔断，失败原因与被测行为无关 | 每次运行一份目录、每个场景一份台账（`ledger_dir`），并把它写进结论 | `test_conformance_report_is_deterministic` |
| P6 | `--json` 只在子命令**之前**生效：argparse 的子解析器会用默认值覆盖父级，于是 `check --json` 静默地输出人类可读文本 | 父级与子级都声明 `--json` 且用 `default=argparse.SUPPRESS`（"没给"不写属性），两种位置都成立 | `test_cli_matrix_and_check`（显式用 `--json check`） |
| P7 | 清理未登记的重复 fixture 时，manifest 里的裸文件名（`pre-tool-use-edit.json`）让读取方按 Agent id 猜目录，结果"样本存在但检查不到" | fixture 路径统一成仓库相对路径，`_fixture_path` 不再有猜测分支；`adapters.cli events` 会如实报 missing 并退出 1 | `test_declared_fixture_paths_resolve` + `python -m adapters.cli events` |
| P8 | 事件可自报 `read` 覆盖 manifest 的 `edit`，把写动作伪装成只读 | canonical operation 以已审核 manifest 为准，冲突直接拒绝 | `test_adapter_rejects_operation_that_conflicts_with_manifest` |
| P9 | 外部 canonical payload 可注入 `dependencies` / `result_present` / `request` / `digest` 等内部事实 | 外部 payload 只允许 `path` / `params` / `text` / `cwd`；message 顶层输入后作为不可信数据注入，digest 始终由平台计算 | `test_canonical_event_rejects_internal_payload_fields` 等契约/对抗用例 |
| P10 | 并发相同 event id 可能在 callback 后才写台账，造成副作用执行两次 | callback 前跨线程/进程原子 claim，final 写失败也保留 claim | `test_concurrent_replay_executes_callback_at_most_once` |
| P11 | callback 或 evaluator 的异常可能逃逸或仍返回 allow | 安全边界统一收敛为 `execution_failed` / `engine_error` | `test_callback_exception_fails_closed`、`test_unexpected_evaluator_exception_is_an_engine_error` |
| P12 | 损坏 runtime / enforcement ledger 被当空记录继续 | JSON、对象类型和 schema 全部严格读取，未知记录失败关闭 | `test_corrupt_runtime_ledger_fails_closed`、`test_ledger_records_reject_malformed_or_foreign_lines` |
| P13 | `ledger_alias` 只存在于声明，幂等键仍固定 agent id | 所有 claim/lookup 使用 `adapter.namespace` | `test_ledger_alias_is_the_idempotency_namespace` |
| P14 | `full` 被误解为自动具备 Phase 4/5 运行时链路 | 写动作强制 evidence provider + enforcer + Tool Registry + pre-check，缺一即 block | `test_full_mutating_adapter_without_phase4_enforcer_fails_closed`、`test_full_mutating_adapter_without_validator_evidence_fails_closed` 与参数 allowlist 回归 |
| P15 | 所有 outbound 工具都被当成写动作，只读工具误报 `capability_unavailable` | mutating 以 manifest operation 为准，`read` 不进入写链 | 多 Agent allow/隔离场景 |
| P16 | PreToolUse 与 PostToolUse 共用 event id 时，post 被当重放且可能再次 callback | claim 按 event type 区分；post 只跑 `enforcer.post` | `test_post_event_runs_postcheck_without_executing_callback_again` |
| P17 | 闭环场景共享 breaker 状态，trace 场景实际 `request_busy` 仍因只查字段而假通过 | 普通/熔断场景隔离 runtime，trace 场景同时断言 allow | `test_agent_loop_trace_scenario_reaches_an_allow_decision` |
| P18 | trace 登记表跳过损坏 JSON / IO 错误，伪造来源可能被当成未知但无害 | trace JSONL 严格校验 schema/字段，并用进程锁保护读写 | `test_corrupt_trace_registry_fails_closed` |
| P19 | `execute_on_allow=False` 仍认领 runtime event 并签发/消耗 Phase 4 状态 | 只判定模式跳过 runtime claim，Phase 4 使用 `dry_run=True`，之后同 event id 仍可真实执行一次 | `test_decision_only_does_not_consume_runtime_or_enforcement_claim` |
| P20 | 严格 EnforcementLedger 与 dsh 的“审计/台账混写同一 JSONL”冲突，PostToolUse 全部误报损坏 | Phase 2/4 审计链仍共用审计文件，Phase 4 幂等/授权台账拆到独立 `*.enforcement-ledger.jsonl` | `test_post_tool_use_*` + `test_bridge_state_records_do_not_store_file_content` |
| P21 | 一致性报告列出 3 个 Adapter，但实现只遍历 `full` 集合，40 项其实全是 dsh；两个只读消费者零检查 | 遍历所有 Adapter；read_only 写场景必须显式 `capability_unavailable`，不支持的事件记为 `declared_inapplicable`，summary 输出逐 Adapter coverage | `test_conformance_suite_passes_for_every_adapter` + `python -m adapters.cli check --json` |
| P22 | 同一 `trace_id` 可被后写入的 Agent 重新登记，读取时“最后一条赢”导致所有权劫持 | 在同一进程/文件锁内校验现有绑定；完全相同的登记幂等，不同 owner / parent / request 一律拒绝 | `test_trace_owner_cannot_be_reassigned` |

### Adapter 升级流程（升级 Agent Runtime 时照着做）

    1) 先核实产品版本与实际钩子契约，把它写进 adapters/<agent_id>/manifest.yaml 的
       agent_version / protocol_version / hooks / event_types；
    2) 更新工具表（规范名 + Agent 侧别名 + 操作 + 路径字段），若是 dsh 还要同步
       src/adapters/dsh/adapter.py 的 TOOL_TABLE（契约测试会逐项比对）；
    3) 重新采集最小真实事件样本，放进该 Agent 的 fixtures/（或 Phase 2 的共享目录），
       并在 manifest 的 fixtures 里登记；
    4) 重跑 python -m adapters.cli events（样本存在）、
       python -m adapters.cli check（一致性套件）、
       python tools/agent_loop.py（闭环）；
    5) 重新审核能力声明并更新支持矩阵：
       python -m adapters.cli approve --reviewer <name>，
       然后把新的 agent_version / enforcement 写进阶段证据；
    6) 若升级改变了阻断或审批能力，先改支持的写法（read_only ↔ full），再改矩阵——
       顺序反了就会出现"矩阵说能拦、实际拦不住"。

### 落地命令

    python -m adapters.cli matrix                            # 支持矩阵（full / read_only / unsupported）
    python -m adapters.cli approve --reviewer <name>          # 审核能力声明（改 manifest 后必须重跑）
    python -m adapters.cli check [--json]                     # 一致性套件（12 场景、87 项；含逐 Adapter coverage；--json 前后都行）
    python -m adapters.cli events                             # 每个 Agent 的兼容性 fixture 是否存在
    python -m adapters.cli inspect --agent dsh --event e.json  # 一条事件被翻译成了什么
    python tools/agent_loop.py                                # 多 Agent 闭环（结论进阶段证据）
    python -m pytest tests/contract -q                        # 152 用例
    python -m pytest tests/integration -q                     # 225 用例
    python -m pytest tests/security -q                        # 51 用例
    python -m pytest -q                                       # 922 passed, 1 skipped
    python tools/phase_evidence.py                            # .tmp/artifacts/phase-6-evidence.json

### 验收证据

`python tools/phase_evidence.py` 生成的 `.tmp/artifacts/phase-6-evidence.json` 记录：
实现版本、规则集哈希、决策协议版本、Phase 2 的 dsh Adapter 契约事实、检索与受控执行事实、
验证器事实、**多 Agent 适配事实**（支持矩阵：agent id / 产品版本 / 协议与协议版本 / 能力上限 /
工具数量 / fixture / 已审核状态与 manifest 摘要、审议人与时间、三种状态的计数）、
**多 Agent 闭环结论**（7 个场景 + 一致性套件的检查数与失败数）、
每个套件的命令 / 用例数 / 失败数、性能基线、JUnit 报告路径与时间戳。

### 一处环境观察（读阶段证据时要知道）

本机的阶段证据里 `sandbox_loop.result` 是 `fail`：那一步跑的是 **Phase 2 的真实 dsh 沙箱闭环**
（`tools/dsh_sandbox_loop.py`），需要本机装着 dsh。这个环境的嵌套进程启动被外层拦住，
审计为空，所以脚本如实报 fail 并给出 diagnosis——这是 Phase 2 遗留的环境限制，
不是 Phase 6 的回归；CI 上仍然照跑，没有 dsh 的环境会显式跳过（退出码 0，不假装通过）。
Phase 6 自己的四步门禁（一致性套件 / 支持矩阵 / fixture 存在性 / 多 Agent 闭环）全部 pass。

### 退出条件核对

| 退出条件 | 结论 | 证据 |
| --- | --- | --- |
| 至少两个不同 Agent/协议消费者通过一致性套件 | 仓库条件满足：dsh 40 项、generic-json 35 项；legacy-post-only 因只有 post hook，12 个 pre 场景均显式记为 inapplicable；总计 87 项全绿。第二真实产品验证待完成 | `python -m adapters.cli check --json`；`tests/integration/test_multi_agent_runtime.py` |
| 支持矩阵明确区分 full、read_only 与 unsupported | 协议可区分；当前活动清单实际为 full=1、read_only=2、unsupported=0，不能声称三种都有实例 | `python -m adapters.cli matrix`；`test_support_matrix_reports_current_full_and_read_only_states` |
| 跨 Agent 隔离和循环限制测试通过 | 满足：命名空间、主体、trace、熔断各有专项用例（含对抗） | `tests/security/test_multi_agent_adversarial.py`、`tests/integration/test_multi_agent_runtime.py` |
| 核心层没有新增 Agent SDK 依赖 | 满足：`src/policy/` 未改动；适配层只依赖标准库 + pydantic + PyYAML | `tests/contract/test_validator_protocol.py` 的核心层导入用例；`git diff` 里没有 `src/policy/` 的适配相关改动 |
| Adapter 升级流程和版本 fixture 已文档化 | 满足：本文件"Adapter 升级流程"小节 + manifest 的 `fixtures` 登记 + `adapters/cli.py events` | `python -m adapters.cli events`；`test_declared_fixture_paths_resolve` |

仓库内实现通过；在进入 [Phase 7](phase-7-policy-api.md) 的产品验收前，仍需补第二真实 Agent 的
版本化 fixture 与一致性套件证据。
