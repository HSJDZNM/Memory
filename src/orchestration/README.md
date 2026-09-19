# `src/orchestration`：LangGraph 编排层

这一层是 **Policy Platform 的消费者**，不是它的一部分。它回答的问题是
"工作流怎么往前走"，而"某个动作允不允许"始终由平台回答：

```text
LangGraph 负责如何组织 Agent
Policy Platform 负责 Agent 应遵守什么
Agent / Tool 负责在授权后如何执行
```

## 硬边界（改代码前先读）

1. **判定只有一条路径**：编排层不实现任何规则、权限或证据语义，它只调用
   `/v1/policy/evaluate`、`/v1/knowledge/retrieve`、`/v1/validation/evaluate`，
   以及在需要动手时把动作交给 Phase 4 的受控执行链。
2. **只有 `langgraph_engine.py` 导入 `langgraph`**，而且是构造引擎时延迟导入：
   版本不认识就 `EngineUnavailableError`，绝不"尽力兼容"。
3. **核心层从不导入本包**：删掉 `src/orchestration/`，平台照常独立运行
   （`tests/contract/test_orchestration_engine.py` 会检查这条）。
4. **状态里不放正文**：需求原文、文件内容、工具输出、凭据都不进 `GraphState`，
   只留摘要、路径与引用；相同输入必须得到逐字节相同的状态（没有墙钟字段）。
5. **分支只由结构化 Decision 决定**：PASS/FAIL 读的是决策协议里的 `decision`，
   不是文本、不是异常、也不是"图跑到哪了"。
6. **失败关闭**：平台不可用 / trace 断裂 / 证据缺失 / 审批不合法 / 上限击穿
   一律进入显式终态（`blocked` / `needs_human` / `failed`），没有"默认放行"分支。

## 模块地图

| 文件 | 职责 |
| --- | --- |
| `models.py` | 最小图状态、节点契约、失败码、上限与审批引用（框架中立、可序列化） |
| `errors.py` | 失败码 → 终态的映射（`STATUS_BY_CODE`）：状态由失败码决定，节点不许自己发明 |
| `limits.py` | repair / 工具调用 / 节点执行 / token / 时间 / 费用的硬上限 |
| `checkpoint.py` | 原子替换的 JSON checkpoint、版本与摘要校验、恢复兼容性判定 |
| `approvals.py` | 参数绑定、限期、单次使用的人工审批（语义来自 Phase 4，不另起一套） |
| `client.py` | Policy API 客户端端口：HTTP 实现 / 脚本化假实现 / 熔断包装 |
| `tools.py` | 受治理的工具执行端口：默认接 Phase 4 受控执行链 |
| `nodes.py` | 八个节点：需求 / 检索 / 规划 / 实施 / 验证 / 修复 / 测试 / 收尾 |
| `graph.py` | 图定义与条件分支（数据 + 纯函数），两个引擎共用 |
| `engines.py` | `StepExecutor`（与框架无关的单步）+ 参考引擎 |
| `langgraph_engine.py` | LangGraph 引擎：同一份 spec 交给 `StateGraph` |
| `runtime.py` | 显式装配：客户端、工具端口、checkpoint、引擎选择 |
| `cli.py` | `python -m orchestration.cli {self-check,graph,status,run}` |

## 怎么跑

```powershell
$env:PYTHONPATH = "src"

# 装配自检：图 / 引擎 / 注册表 / checkpoint / 状态协议（加 --api-url 连平台一起查）
python -m orchestration.cli self-check

# 图定义：节点、静态边与条件分支
python -m orchestration.cli graph

# 跑一个任务（任务文件是数据：目标、验收条目与候选改动都在里面）
python -m orchestration.cli run --task .tmp/phase-8/cli/task.json --engine auto

# 读 checkpoint 摘要（阶段、revision、判定与失败码）
python -m orchestration.cli status --task-id demo-1
```

完整闭环（真端口 uvicorn、真受控执行、真 checkpoint 与恢复）见
`python tools/orchestration_loop.py`。

## 恢复语义（最容易被误解的一段）

- `StepExecutor` 在**路由之后**才落盘：checkpoint 里保存的是"下一步该做什么"，
  所以"checkpoint 之后崩溃"不会让恢复重跑刚刚完成的节点；
- 每个 checkpoint 带一份兼容性凭据（`rule_set_hash` / `index_version` /
  `tool_schema_hash` / 协议世代）。恢复时与**当前平台**的凭据比对：
  规则集或索引变了 → `revalidate`（清掉旧 trace 与旧验证结果，回到检索节点重评，
  **不沿用旧 allow**）；工具 schema 变了 → `reapprove`（旧审批作废）；
  协议世代变了 → 拒绝恢复；
- 拿不到当前凭据时按"变了"处理：宁可多评估一次，也不沿用旧结论；
- 副作用开工前先写一笔**意图**并立刻刷盘：恢复时若发现"开工未结算"，
  进入 `needs_human`（`side_effect_unknown`），既不重放也不假装成功。

## 已知边界（不假装做到）

- 真实作者（模型）不在本层：候选改动来自 `ChangeAuthor` 端口，仓库里只有确定性的
  `ScriptedAuthor`；接入模型不改变任何节点契约，但本阶段没有验证过真实模型；
- 跨进程恢复用的是本包的 checkpoint 存储，不是 LangGraph 的 checkpointer
  （通用 checkpointer 不携带规则集/索引/工具 schema 的兼容性信息）；
- 熔断是进程内的连续失败计数，没有分布式协调，也没有自动复位
  （`CircuitBreaker.reset(authorised=True)` 需要显式动作）；
- 编排层不执行命令类工具：它只声明了写入类工具与"改规则"工具，
  需要 shell 的场景仍然由 Agent 侧的受控执行链负责。
