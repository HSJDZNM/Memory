# 总体架构与核心契约

## 组件边界

```text
Agent Runtime
    ↓ 原始事件
Agent Adapter
    ↓ 标准 PolicyEvent / PolicyContext
Policy Platform
    ├── Context Engine
    ├── Policy Engine
    ├── Knowledge Retrieval
    ├── Validator Pipeline
    └── Audit Evidence
    ↓ PolicyDecision
Controlled Executor
    ├── allow → 执行
    └── block → 返回修复信息
```

核心层只能依赖自己的协议和端口，不能导入 dsh、Codex、Claude Code 或 LangGraph 类型。Adapter 可以依赖具体 Agent SDK，但只能输出核心协议。

## 核心模型

### Rule

```yaml
id: ARCH-001
version: 1
name: controller-service-boundary
description: Controller 不得直接访问 Repository。
scope:
  language: python
  layer: controller
severity: error
enforcement:
  type: deterministic
rule:
  forbidden_dependency:
    - repository
message: Controller 必须通过 Service 访问 Repository。
source:
  kind: project-policy
  path: policies/architecture/ARCH-001.yaml
```

规则标识与版本共同决定审计身份。修改规则语义必须递增版本；仅修改排版不应改变语义版本。

### PolicyContext

至少包含：

```yaml
request_id: req-123
project: ecommerce
agent: dsh
operation: edit
file: src/order/controller.py
language: python
module: order
layer: controller
task: add order creation API
dependencies: [service]
git_diff: null
principal:
  subject: local-user
  roles: [developer]
```

路径在进入 Engine 前统一为仓库相对路径和 `/` 分隔符。缺失的安全关键字段不得由 Adapter 猜测。

### PolicyDecision

```json
{
  "decision": "block",
  "request_id": "req-123",
  "matched_rules": ["ARCH-001@1"],
  "violations": [
    {
      "rule_id": "ARCH-001",
      "rule_version": 1,
      "severity": "error",
      "message": "Controller 必须通过 Service 访问 Repository。",
      "evidence": {
        "kind": "dependency",
        "subject": "src/order/controller.py",
        "value": "repository"
      }
    }
  ],
  "trace_id": "trace-456"
}
```

决策枚举固定为 `allow`、`allow_with_warnings`、`block`。任何未识别值都按协议错误处理，不能默认允许。

### 决策载荷的两个版本字段

| 字段 | 含义 | 什么时候变 |
| --- | --- | --- |
| `schema_version` | 协议形状：消费方能不能解析这份载荷 | 字段增删或语义变化时递增；消费方看不懂必须拒绝 |
| `policy_version` | 协议世代名：给人读的"这是第几代协议" | **只与 `schema_version` 同进同退**，不跟随平台阶段 |

平台走到哪个阶段**不写在载荷里**：看阶段验收证据的 `phase` 与 `implementation_version`
（`python tools/phase_evidence.py`），以及审计记录里的规则集哈希。
让 `policy_version` 跟着阶段走会引入第二条兼容轴，并把"显式更新快照"变成每阶段的例行公事——
那样它既提示不了兼容性，也提示不了语义变化，只剩下一次性的噪声。

`policy_version` 的取值来自 `src/policy/models.py` 里的 `POLICY_VERSION` 常量：载荷、快照与
阶段证据都从这一处取值，`tests/contract/test_decision_protocol.py` 有守卫用例。

## 标准事件

```text
agent.start
agent.request
agent.message
tool.pre_execute
tool.post_execute
agent.turn_end
```

每个事件携带 `event_id`、`request_id`、`trace_id`、时间戳、Agent 标识、主体信息和事件载荷。事件必须支持幂等处理；重复的 `event_id` 不得导致工具执行两次。

## 端口

- `RuleRepository`：加载并版本化规则；
- `PolicyEvaluator`：匹配范围并产生决定；
- `KnowledgeRetriever`：返回带来源与分数的知识片段；
- `Validator`：把代码或执行结果转成结构化证据；
- `AuditSink`：记录决策链，写入失败不应泄露敏感数据；
- `ControlledExecutor`：只执行已绑定到当前参数和版本的允许决定。

## 信任边界

以下内容一律视为不可信输入：用户消息、网页和文档内容、RAG 片段、模型输出、工具返回值、其他 Agent 消息。它们可以作为数据进入上下文，但不能改变系统策略、扩权或授权执行。

高风险动作的授权必须由 Policy Engine 和执行器独立校验。检索成功、模型自信或另一个 Agent 已允许，都不能替代当前动作的授权。

## 失败策略

| 失败点 | 默认行为 |
| --- | --- |
| 规则解析失败 | 阻止加载该规则集并报告具体文件 |
| 安全关键上下文缺失 | `block` |
| Policy Engine 超时 | 高风险写操作 `block` |
| 检索不可用 | 不回退到“模型记忆中的规范” |
| Validator 不可用 | 需要该验证器的门禁 `block` |
| 审批与实际参数不一致 | `block` |
| 未知事件或决策版本 | 拒绝并记录协议错误 |

只读、低风险操作是否允许降级必须由显式规则声明，不能在异常处理里偷偷放行。

## 九阶段依赖顺序

```text
0 最小规则系统 → 1 Policy Engine → 2 dsh Adapter
→ 3 Retrieval → 4 Tool Enforcement → 5 Validators
→ 6 Multi-Agent Adapters → 7 Policy API → 8 LangGraph
```

后续阶段只能通过稳定契约使用前序能力，不得反向让核心层依赖上层框架。
