# Engineering Policy Platform 文档集

本目录将原先的单篇大型架构文档拆成可独立阅读、实施和验收的文档集。内容同时参考了共享对话“设计规范 RAG 架构”和仓库内已有的工程规范镜像。

> 实施进度：**Phase 0 至 Phase 5 已完成；Phase 6 与 Phase 7 的仓库实现已完成，
> 其中 Phase 6 的产品验收（第二真实 Agent）仍待外部环境**。
> Phase 0 选定 Python 技术栈并落地了依赖锁文件、
> 根 README 命令与 CI；Phase 1 落地了上下文规范化、Scope Matcher、严重级别决策与带版本的决策协议；
> Phase 2 落地了 dsh Adapter 与 pre-execute Hook，并在受控沙箱里跑通了"bad 编辑被阻断、good 编辑放行一次"的真实闭环；
> Phase 3 落地了摄取清单、章节分块器、SQLite FTS5 基线与 Context Builder，并用固定评测集给出了
> "先不引入 Embedding"的可重放结论（hit@5 = 1.00、support@5 = 1.00、向量检索未跑赢基线）。
> Phase 4 落地了数据化 Tool Registry、与 action_hash 绑定的短时效授权、受控执行器与事后验证，
> 并把 dsh 的写类与高权限执行类工具接进同一条决策链（审计链可重放）。
> Phase 5 落地了 AST / 依赖图证据、外部工具适配器（Ruff / mypy / pytest，探针发现 + 失败关闭）、
> 测试验证器与流水线聚合：ARCH-001 不再需要调用方声明依赖，"解析失败"也不等于"没有依赖"。
> Phase 6 已落地规范事件、能力声明、运行时隔离、Phase 4/5 写链门禁与一致性套件；当前真实产品
> 只有 dsh，另外两个消费者是合成协议夹具，第二真实 Agent 接入仍待有相应环境时验证。
> Phase 7 已把核心能力服务化：版本化 DTO 与 OpenAPI 快照、Bearer 认证与租户/项目隔离、
> 墙钟预算与幂等台账、请求级观测与**可对外锚定的摘要链**；API 只增加部署与信任边界，
> 判定仍然只有 `policy.engine.evaluate` 一条路径（本地与经 API 的决定整份相等，由闭环证明）。
> Phase 8 已落地上层编排：`src/orchestration/` 用 LangGraph 驱动"需求 → 检索 → 规划 → 实施 →
> 验证 ⇄ 修复 → 测试 → 收尾"的可恢复工作流，**只当消费者**——判定仍只有平台一条路径，
> 每个受治理的写入仍然走 Phase 4 的受控执行链；循环、checkpoint 兼容性、人工审批与平台故障
> 全部有自动化测试与闭环证据。该层是仓库里**唯一**导入工作流框架的地方，删掉它不影响平台独立运行。
> 实施记录见对应阶段文档末尾的“实施记录”小节，实际命令以根 `README.md` 为准。

## 阅读顺序

1. [愿景、边界与设计原则](00-vision-and-principles.md)
2. [总体架构与核心契约](01-architecture-and-contracts.md)
3. [仓库数据源与规范转化方法](02-repository-data-sources.md)
4. [技术选型与目标目录](03-technology-and-layout.md)
5. 按顺序完成 `phases/` 中 Phase 0 至 Phase 8
6. 全程使用 [测试策略](testing/test-strategy.md)，并用 [阶段验收矩阵](testing/acceptance-matrix.md) 决定是否进入下一阶段
7. 已交付部分的独立复核与加固记录见 [reviews/](reviews/post-phase-4-hardening.md)（Post-Phase-4 复核）、
   [reviews/post-phase-5-review.md](reviews/post-phase-5-review.md)（Post-Phase-5 复核）与
   [reviews/post-phase-8-review.md](reviews/post-phase-8-review.md)（Post-Phase-8 验收与修复）
8. **尚未实现**的提案与评估见 [designs/](designs/文档转规则操作平台-可行性评估.md)：
   "文档 → 规则"能否做成用户可操作的控制台、前后端连接实测（无 CORS、只能同源）、
   前端操作逻辑与失败语义、以及评审给出的两条**必须先修**的阻塞项
   （新建规则文件绕过审批、HTTP 面漂移静默）。提案与阶段记录分开放：阶段记录在 `phases/`，
   提案在 `designs/`，两者不得互相冒充。提案有一个**可点开的静态原型**：
   [designs/console/](designs/console/index.html)（6 个页面，按台阶分层合并；原生 JS 零构建，数据取自仓库真实数据）
9. **平台操作系统的总体设计**见 [designs/os/](designs/os/README.md)：把仓库拆成 9 个板块、8 条端到端操作流程与 8 个页面，
   并记录三轮多成员讨论（提案 / 交叉与对抗评审 / 定稿复核）、Lead 裁决 D1–D15 与五期落地路线。
   它把第 8 条那份「文档 → 规则」控制台收作**其中一个板块（S9）的一条流程（C）**，不重复、不替代；
   三份终稿里所有会随工作树变化的数字都只给「值 + 取数时刻 + 取数命令」三元组。

## 九个阶段

| 阶段 | 主题 | 主要产物 |
| --- | --- | --- |
| [Phase 0](phases/phase-0-minimum-rule-system.md) | 最小规则系统 | YAML Rule → Loader → Engine → CLI |
| [Phase 1](phases/phase-1-policy-engine.md) | Policy Engine | Context、Scope、Severity、Decision |
| [Phase 2](phases/phase-2-dsh-adapter.md) | dsh Adapter | dsh Event → Policy Context；pre-execute Hook 与审计 |
| [Phase 3](phases/phase-3-retrieval.md) | 规范检索 | SQLite FTS5、可选向量检索、Context Builder |
| [Phase 4](phases/phase-4-tool-enforcement.md) | Tool Enforcement | Tool Registry、Pre-check、受控执行、Post-check、审计链 |
| [Phase 5](phases/phase-5-code-validators.md) | 代码验证器 | AST、依赖、Lint、类型与测试证据（**已完成**：证据协议 + 流水线 + 失败关闭） |
| [Phase 6](phases/phase-6-multi-agent-adapters.md) | 多 Agent Adapter | 仓库实现完成：规范事件、能力声明、写链门禁与一致性套件；第二真实 Agent 产品验证待完成 |
| [Phase 7](phases/phase-7-policy-api.md) | Policy API | **已完成**：版本化 DTO 与 OpenAPI 快照、Bearer 认证、租户/项目隔离、预算与幂等、观测与锚定；核心库仍可独立运行 |
| [Phase 8](phases/phase-8-langgraph-orchestration.md) | LangGraph | **已完成**：可恢复的上层编排消费者（最小状态、循环上限、checkpoint 与恢复、人工审批、平台故障失败关闭）；框架可替换且平台仍独立运行 |

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
