# Phase 6 学习手册 · 任务与对象关系

## 这一阶段要完成的三件事

1. **固化协议**：把"Agent 运行时发给平台的原始事件"统一成一份与实现无关的
   **规范事件**（Canonical Event Schema），并明确"看不懂就拒绝"；
2. **把差异变成数据**：事件名、字段名、工具名、阻断能力、审批能力全部写进
   `adapters/<agent_id>/manifest.yaml`，受 `adapters/approved.json` 的已审核哈希约束；
3. **证明一致性**：让多个协议消费者（真实 dsh、合成 JSON 消费者、合成 PostToolUse 消费者）
   对同一组语义事件给出同一套结论，并且互不干扰。

## 对象清单

| 对象 | 位置 | 职责 |
| --- | --- | --- |
| `AgentEvent` | `src/adapters/models.py` | 规范事件：与实现无关的交换协议 |
| `EventType` / `Operation` | `src/adapters/models.py`、`src/policy/models.py` | 受控枚举：未知值一律拒绝 |
| `AdapterManifest`、`AgentTool`、`HookNames` | `src/adapters/models.py` | 能力声明的数据模型（含工具表别名） |
| `ceiling_from_capabilities` | `src/adapters/base.py` | 由声明推出上限：full / read_only / unsupported |
| `AdapterRegistry`、`AdapterList` | `src/adapters/base.py` | 原子加载 + 已审核哈希比对 + 支持矩阵 |
| `Adapter`（基类） | `src/adapters/base.py` | 事件校验、路径归一化、上下文构造、响应翻译 |
| `JsonAdapter` / `EventAdapter` / `DshAdapter` | `src/adapters/*.py` | 三种协议的实现（前者通用，后两者是钩子类） |
| `AgentRuntime` | `src/adapters/runtime.py` | 所有 Agent 共用的判定入口：隔离、原子幂等、Phase 5 证据、Policy、Phase 4 pre/post、callback |
| `TraceRegistry` | `src/adapters/runtime.py` | trace 来源登记（`owner_agent`） |
| `run_conformance` / `SCENARIOS` | `src/adapters/conformance.py` | 一致性套件：语义场景 → 各家线协议 |
| `adapters/*/manifest.yaml`、`adapter.yaml` | `adapters/` | 能力声明与运行期配置（数据） |
| 探针工作区 | `tests/fixtures/agent_events/workspace/` | 一致性套件的受控工作区与"越界"边界 |
| `tools/agent_loop.py` | `tools/` | 多 Agent 闭环（7 个场景 + 套件结论） |

## 对象关系

```text
Agent Runtime（dsh / 第三方 / 旧 Agent）
      │  原始事件（各家报文）
      ▼
Adapter.to_policy_event(raw, workspace)
      │  规范事件 AgentEvent（受控字段 + 摘要）
      ▼
AgentRuntime.handle(agent_id, raw)
      ├─ trace 来源校验（TraceRegistry，按 owner_agent）
      ├─ 上下文构造（PolicyContext：主体只认 Adapter 声明）
      ├─ 能力门禁（read_only 上限 → capability_unavailable）
      ├─ 熔断（窗口内事件数）与幂等（台账键 <adapter.namespace>:<event_id>）
      ├─ 写类动作：Phase 5 evidence → Policy → Phase 4 pre-check
      ▼
Policy Engine（完全没有改动）
      │  PolicyDecision
      ▼
Adapter.to_agent_response / response_from_decision
      │  exit code（钩子类）或 JSON（通用）
      ▼
Agent Runtime
```

## 三条必须记住的判断

1. **能力不足 ≠ 跳过治理。** 只有 PostToolUse 的 Agent 仍然是"受治理"的，
   只是它的上限被算成只读；写类动作会被显式拒绝，而不是"没人查就放过去"；
2. **隔离靠机制。** 命名空间、主体、trace、熔断都是运行时的硬规则，不依赖任何一方的自觉；
3. **新增 Agent 不改核心。** 加一个协议消费者 = 一份 manifest + 一个渲染分支 + 一份事件样本。

`full` 只是 manifest 能力上限：运行时未注入 evidence provider 或 enforcer 时，写动作会失败关闭。
当前只有 dsh 是实际产品接入，另外两个消费者用于协议与降级语义测试。
