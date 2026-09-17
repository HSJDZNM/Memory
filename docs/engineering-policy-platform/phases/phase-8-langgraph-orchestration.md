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
