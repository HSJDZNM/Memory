# Phase 6：多 Agent Adapter

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

比较 dsh、Generic 和第二个真实 Agent 的原始事件差异，确认它们最终产生相同核心语义。新增 Adapter 不应迫使 Rule 或 Engine 增加 Agent 专用分支。

## 退出条件

- 至少两个不同 Agent/协议消费者通过一致性套件；
- 支持矩阵明确区分完整 enforcement、只读与不支持；
- 跨 Agent 隔离和循环限制测试通过；
- 核心层没有新增 Agent SDK 依赖；
- Adapter 升级流程和版本 fixture 已文档化。

通过后进入 [Phase 7](phase-7-policy-api.md)。
