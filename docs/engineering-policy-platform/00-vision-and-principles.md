# 愿景、边界与设计原则

## 项目目标

构建一个独立于具体 Coding Agent 的软件工程治理层，使 Agent 在执行过程中能够：

1. 根据任务和文件上下文获得相关规范；
2. 在调用工具前接受权限与策略检查；
3. 在代码变更后接受确定性验证；
4. 收到结构化违规反馈并完成修复；
5. 留下可重放、可审计的决策证据。

目标闭环如下：

```text
规范知识 → 上下文识别 → 相关规范检索 → Agent 执行
    ↑                                      ↓
再次验证 ← Agent 修复 ← 违规反馈 ← 代码与行为验证
```

## 非目标

- 不用一个超长 System Prompt 承载全部规范；
- 不让 RAG 决定工具是否可以执行；
- 不用 LLM 代替 AST、依赖图、Linter、类型检查或测试；
- 不把 dsh、Codex、Claude Code 或 LangGraph 的内部对象泄漏到核心模型；
- 不在需求尚未出现时提前引入 Qdrant、Neo4j、Kafka 等基础设施；
- 不把外部文档原文直接等同于本项目的强制规则。

## 四项设计原则

### 1. 按上下文提供最小必要规范

规范通过 `PolicyContext` 选择和检索。Prompt 只接收当前任务需要的规范、来源和原因，避免上下文污染与规则冲突。

### 2. 检索、决策、执行相互分离

```text
Retriever   回答：当前应知道什么？
Policy      回答：当前允许做什么？
Validator   回答：实际结果是否合规？
Executor    负责：在获得允许后执行动作。
```

检索结果和模型输出均是不可信输入，不能直接触发工具。

### 3. 能确定性验证的规则不用模型裁决

例如“Controller 不得直接依赖 Repository”应由 AST 或依赖图产生证据，再由 Policy Engine 汇总成决策。LLM 可以解释结果，但不能覆盖确定性失败。

### 4. Agent Framework 与 Policy Platform 解耦

Agent 通过 Adapter、SDK、API 或 MCP 使用平台。LangGraph 只在 Phase 8 作为消费者负责工作流编排，不是规范系统的核心依赖。

## 成功标准

完成全部阶段后，平台应具备以下性质：

- **可执行**：规则能产生明确的 allow、warn 或 block；
- **可解释**：每个决定都能追溯到规则、证据和来源；
- **可测试**：每类规则都有正例、反例、边界和失效测试；
- **可移植**：新增 Agent 不修改 Policy Engine；
- **可追踪**：一次任务可关联检索、决策、工具调用、验证和修复；
- **可恢复**：失败不会静默降级为无策略执行；
- **最小权限**：Agent、工具、数据源和租户边界分别授权。

## 推荐学习顺序

```text
YAML / Pydantic → Policy Engine → dsh Hook → SQLite / FTS5
→ Retrieval → AST / Validator → FastAPI → MCP / Adapter → LangGraph
```

每完成一个阶段都必须运行该阶段的测试、保存证据并通过阶段门禁。不要并行引入尚未需要的框架。
