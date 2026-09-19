# Phase 8 学习手册 · 任务与对象关系

## 这一阶段要完成的三件事

1. **把"工作流怎么走"从平台里分出来**。前七个阶段回答的是"某个动作允不允许"，
   Phase 8 回答的是"下一步做什么"：需求分析 → 检索 → 规划 → 实施 → 验证 ⇄ 修复 →
   测试 → 收尾。两件事必须由两套系统负责，否则"图跑到哪了"会被误当成"用户批准了"。
2. **用 LangGraph 做有状态、可循环、可恢复的编排**，而且让它只当消费者：
   平台照常独立运行，删掉编排层不影响规则、检索、验证器、受控执行与 API。
3. **把循环、恢复、审批与平台故障做成可测的语义**，不是文档里的承诺：
   循环有硬上限、checkpoint 带版本与兼容性凭据、审批与参数绑定且有限期、
   平台不可用时停下来而不是"照旧往下跑"。

## 对象清单

| 对象 | 位置 | 它负责什么 | 它不负责什么 |
| --- | --- | --- | --- |
| `GraphState` | `orchestration/models.py` | 最小图状态：任务、阶段、artifact/trace 引用、验证摘要、计数器、上限、审批引用 | 存正文 / 存凭据 / 存绝对路径 |
| `NodeId` / `NODES` | `orchestration/models.py` / `nodes.py` | 八个节点的名字与实现，每个单一职责 | 决定下一步去哪（那是路由的事） |
| `GraphSpec` / `ROUTERS` | `orchestration/graph.py` | 节点、静态边与条件分支（数据 + 纯函数） | 判定"允不允许" |
| `StepExecutor` | `orchestration/engines.py` | 与框架无关的单步：记账 → 跑节点 → 路由 → 落盘 → 失败映射 | 选择用哪个框架 |
| `ReferenceEngine` | `orchestration/engines.py` | 用一个循环驱动 `StepExecutor`（无第三方依赖） | 假装自己是 LangGraph |
| `LangGraphEngine` | `orchestration/langgraph_engine.py` | 把同一份 spec 交给 LangGraph 的 `StateGraph` | 定义图结构 / 存领域信息 |
| `PolicyClient` | `orchestration/client.py` | 唯一的"问平台"入口：evaluate / retrieve / validate / readiness | 执行工具 / 自带证据 |
| `ScriptedPolicyClient` | `orchestration/client.py` | 固定 allow/block/error 的假客户端（脚本用尽即失败关闭） | 猜测"没脚本时应该放行" |
| `PlatformToolRunner` | `orchestration/tools.py` | 把动作交给 Phase 4 的受控执行链（注册表 / action_hash / pre-check / 授权 / 事后验证） | 自己判断风险或权限 |
| `ApprovalGate` | `orchestration/approvals.py` | 校验审批：与 action_hash 绑定、限期、单次使用、主体一致 | 解析自然语言批准 |
| `JsonCheckpointStore` | `orchestration/checkpoint.py` | 原子替换的 checkpoint + 摘要校验 + 版本拒绝 | 决定"能不能接着跑"（那是 `plan_resume`） |
| `plan_resume` | `orchestration/checkpoint.py` | 兼容性判定：`resume` / `revalidate` / `reapprove` / `refuse` | 沿用旧 allow |
| `RunLimits` / `charge` | `orchestration/models.py` / `limits.py` | repair 轮次、工具调用、节点执行、token、费用、时间的硬上限 | 静默截断 |
| `STATUS_BY_CODE` | `orchestration/errors.py` | 失败码 → 终态（blocked / needs_human / failed） | 让节点自己发明状态 |

## 对象关系

```text
TaskSpec + ChangeAuthor + PolicyClient + ToolRunner + ApprovalGate + CheckpointStore
        │                                   （全部显式注入：节点不构造依赖）
        ▼
   build_assembly()  ── 选择引擎（auto → langgraph 或 reference）
        │
        ▼
   GraphEngine.run(task_id, state)
        │
        ├─ StepExecutor.prepare()  ── 读 checkpoint → plan_resume → 决定从哪继续
        │
        └─ 循环（参考引擎的 for / LangGraph 的 StateGraph）
              │
              ├─ StepExecutor.step()
              │     ├─ charge_node_run()      上限击穿 → LimitExceeded → needs_human
              │     ├─ 节点函数                平台调用 / 受治理写入 / 纯规划
              │     ├─ self.route()           标签 → 目标（未登记标签即契约错误）
              │     └─ self.save()            带着"下一步"落盘
              │
              ▼
        RunReport（步骤、traces、artifacts、计数、失败码；**不含正文**）
```

数据只往一个方向流：**节点提出、平台判定、执行器动手、checkpoint 记引用**。
反过来（用图的状态去证明"已经批准"）在这一层没有任何入口。

## 三条必须记住的判断

1. **"图到达了某个节点"不是用户批准**。审批是一条与 `action_hash` 绑定的结构化记录，
   有主体、有期限、有使用次数；恢复时必须重新校验，参数一变旧审批自动作废。
2. **"checkpoint 有旧 allow"不是可以沿用**。恢复前先比对规则集、索引与工具 schema：
   变了就 `revalidate`（清掉旧 trace 与旧验证结果，回到检索节点重评），
   协议世代变了直接拒绝恢复。
3. **"平台没回答"不是"没有限制"**。不可达、超时、证据缺失、trace 断裂一律进入
   `blocked`；`needs_human` 只用于"必须由人决定"的情况（上限、审批、副作用状态未知）。

## 这一层刻意不做什么

- 不实现规则、权限、证据与判定：这些仍然只有平台一处定义；
- 不存正文：需求原文、文件内容、工具输出与凭据都不进状态，checkpoint 里只有引用与摘要；
- 不假装可撤销：写入类工具的回滚能力由 Phase 4 的注册表声明，编排层不额外承诺；
- 不把 LangGraph 的 checkpointer 当成领域恢复机制：跨进程恢复靠本包的 checkpoint
  （它携带规则集/索引/工具 schema 的兼容性）。
