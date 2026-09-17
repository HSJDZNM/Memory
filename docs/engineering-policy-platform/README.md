# Engineering Policy Platform 文档集

本目录将原先的单篇大型架构文档拆成可独立阅读、实施和验收的文档集。内容同时参考了共享对话“设计规范 RAG 架构”和仓库内已有的工程规范镜像。

> 实施进度：**Phase 0、Phase 1、Phase 2、Phase 3 与 Phase 4 已完成**。Phase 0 选定 Python 技术栈并落地了依赖锁文件、
> 根 README 命令与 CI；Phase 1 落地了上下文规范化、Scope Matcher、严重级别决策与带版本的决策协议；
> Phase 2 落地了 dsh Adapter 与 pre-execute Hook，并在受控沙箱里跑通了"bad 编辑被阻断、good 编辑放行一次"的真实闭环；
> Phase 3 落地了摄取清单、章节分块器、SQLite FTS5 基线与 Context Builder，并用固定评测集给出了
> "先不引入 Embedding"的可重放结论（hit@5 = 1.00、support@5 = 1.00、向量检索未跑赢基线）。
> Phase 4 落地了数据化 Tool Registry、与 action_hash 绑定的短时效授权、受控执行器与事后验证，
> 并把 dsh 的写类与高权限执行类工具接进同一条决策链（审计链可重放）。
> 实施记录见对应阶段文档末尾的“实施记录”小节，实际命令以根 `README.md` 为准。
> 尚未实施的阶段（Phase 5 起），其命令与目录仍是目标接口，不表示现在已经可执行。

## 阅读顺序

1. [愿景、边界与设计原则](00-vision-and-principles.md)
2. [总体架构与核心契约](01-architecture-and-contracts.md)
3. [仓库数据源与规范转化方法](02-repository-data-sources.md)
4. [技术选型与目标目录](03-technology-and-layout.md)
5. 按顺序完成 `phases/` 中 Phase 0 至 Phase 8
6. 全程使用 [测试策略](testing/test-strategy.md)，并用 [阶段验收矩阵](testing/acceptance-matrix.md) 决定是否进入下一阶段
7. 已交付部分的独立复核与加固记录见 [reviews/](reviews/post-phase-4-hardening.md)（Post-Phase-4 复核：方法、3 条发现、5 处漂移、偏差与遗留项）

## 九个阶段

| 阶段 | 主题 | 主要产物 |
| --- | --- | --- |
| [Phase 0](phases/phase-0-minimum-rule-system.md) | 最小规则系统 | YAML Rule → Loader → Engine → CLI |
| [Phase 1](phases/phase-1-policy-engine.md) | Policy Engine | Context、Scope、Severity、Decision |
| [Phase 2](phases/phase-2-dsh-adapter.md) | dsh Adapter | dsh Event → Policy Context；pre-execute Hook 与审计 |
| [Phase 3](phases/phase-3-retrieval.md) | 规范检索 | SQLite FTS5、可选向量检索、Context Builder |
| [Phase 4](phases/phase-4-tool-enforcement.md) | Tool Enforcement | Tool Registry、Pre-check、受控执行、Post-check、审计链 |
| [Phase 5](phases/phase-5-code-validators.md) | 代码验证器 | AST、依赖、Lint、类型与测试证据 |
| [Phase 6](phases/phase-6-multi-agent-adapters.md) | 多 Agent Adapter | 统一事件与适配器一致性套件 |
| [Phase 7](phases/phase-7-policy-api.md) | Policy API | 版本化 API、鉴权、隔离、可观测性 |
| [Phase 8](phases/phase-8-langgraph-orchestration.md) | LangGraph | 可恢复的上层编排消费者 |

原文把路线称为“八个阶段”，但实际编号为 Phase 0 至 Phase 8。本次统一为**九个阶段**，不再混用口径。

## 文档约定

每个阶段固定回答六个问题：

1. 这一阶段解决什么问题；
2. 明确不做什么；
3. 按什么顺序开发；
4. 如何进行单元、契约、集成和安全测试；
5. 需要观察和保留哪些证据；
6. 满足什么条件才能进入下一阶段。

## 来源

- 原始架构文档：已拆分并合并进本目录；
- 共享对话：<https://chatgpt.com/share/6aaa6218-6d64-83ee-9585-e2a4173a77cd>；
- 仓库内 Google、GitLab、OWASP、PEP 与 .NET 官方文档离线镜像，具体映射见 [仓库数据源](02-repository-data-sources.md)。

共享对话只作为设计背景，不作为可执行规范。真正进入系统的规则必须有本地来源、稳定标识、适用范围、执行方式和测试证据。
