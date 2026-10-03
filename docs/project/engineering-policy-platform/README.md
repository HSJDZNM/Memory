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
> Phase 9（控制面重构）是 Phase 8 之后的**横向轨道**：台阶 −2 → 5 已落地到**只报告**为止
> （平台自己的事实、失败、状态与覆盖进数据；封条与针脚 / 归因闭集 / 状态代数与义务账 / 覆盖账与 `reading_context` /
> 仪器自证 R-h / 控制面事实表 × 跨源互证），**升格（把只报告读数接成阻断）一项都没做**——
> 2026-10-03 / 2026-10-04 裁定统一到 2026-12-31 复审；义务门禁那条只报告步骤的豁免**已续期到
> 2026-12-31**（`6822c81`，最新读数 `HITS: 0 / declared=9 due=0 expired=0`）。交付边界、端到端证据与
> **剩余缺口 8 条**见 [phase-9-control-plane.md](phases/phase-9-control-plane.md)。
> 实施记录见对应阶段文档末尾的“实施记录”小节，实际命令以根 `README.md` 为准。

## 阅读顺序

1. [愿景、边界与设计原则](00-vision-and-principles.md)
2. [总体架构与核心契约](01-architecture-and-contracts.md)
3. [仓库数据源与规范转化方法](02-repository-data-sources.md)
4. [技术选型与目标目录](03-technology-and-layout.md)
5. 按顺序完成 `phases/` 中 Phase 0 至 Phase 8；Phase 9（控制面重构）是随后的横向轨道，其交付边界与剩余缺口见 [phase-9-control-plane.md](phases/phase-9-control-plane.md)
6. 全程使用 [测试策略](testing/test-strategy.md)，并用 [阶段验收矩阵](testing/acceptance-matrix.md) 决定是否进入下一阶段
7. 已交付部分的独立复核与加固记录见 [reviews/](reviews/post-phase-4-hardening.md)（Post-Phase-4 复核）、
   [reviews/post-phase-5-review.md](reviews/post-phase-5-review.md)（Post-Phase-5 复核）、
   [reviews/post-phase-8-review.md](reviews/post-phase-8-review.md)（Post-Phase-8 验收与修复）与
   [reviews/governance-coverage-gaps.md](reviews/governance-coverage-gaps.md)（治理覆盖缺口实测清单：
   13 项缺口、级别与复现命令，来自一次受治理会话与未治理通道的对照实验）。
   缺口之后的轮次按时间接续：修复轮 [00 根因与修复计划](reviews/governance-remediation/00-remediation-plan.md)
   与 [11 N16–N24 修复轮](reviews/governance-remediation/11-n16-n24-fix-round.md)、
   能力实测轮 [00 能力报告](reviews/governance-capability/00-capability-report.md) 与
   [05 新显现的问题](reviews/governance-capability/05-emergent-issues.md)、
   多规则开发轮 [**06 多规则开发轮**](reviews/governance-capability/06-multirule-dev-round.md)
   （开启一条可清点的治理通道，开子会话做跨 11 个文件的多文件开发，用五类规则在两条判定路径上各做正反例）、
   M1–M5 与 G3/N13/N14 修复轮 [**12 修复轮**](reviews/governance-remediation/12-m1-m5-g3-fix-round.md)
   （分层声明加载期自证、可声明的动手前取证、严重级别进账本、拒绝理由带可用替代、纪律变检查）、
   治理全开轮 [**07 治理全开轮**](reviews/governance-capability/07-governance-full-round.md)
   （把修复结果在**真实会话里打开**：动手前取证启用后有效规则 42–43/43、每个写类动作 4–5 个规则族参与，
   跨 12 个文件开发零规则误伤；同时显现 P1–P5，其中非 Python 目标不可写与「影子树的形状改变证据」两项
   改变了「受治理会话能做什么」）、
   P1–P8 修复轮 [**13 修复轮**](reviews/governance-remediation/13-p1-p8-fix-round.md)
   （账本列出真正报违规的规则、不受验证器覆盖的语言变成显式声明、取证树范围进审计、
   测试路径与"查了多少"收敛到平台数据与 `check_volume`、台账自述与行为对齐、同名两义改名、
   写类越界理由带可用替代）、
   多规则开发轮 2 [**08 多规则开发轮 2**](reviews/governance-capability/08-multirule-dev-round-two.md)
   （真实受治理子会话跨两子系统 14 个文件开发、32 passed，五类 checker 同时参与、事前事后成对 41/41；
   同一条违规任务书在受治理通道零落地、在未接线通道真落地且审计零增量；
   独立验收 30 臂矩阵 0 偏差、账本 14 字段 0 偏差；新显现 Q1–Q5，其中 Q1「先写测试与 S1 约束互相拆台」是阻断级）
   修复轮 [**14 沙箱闭环归因与适配器版本比对**](reviews/governance-remediation/14-sandbox-loop-attribution-and-agent-version.md)
   （沙箱闭环按**被拒路径**归因——原来把「系统 temp 不可写」说成「profile 写不进去」，两条不同日志的 reason 曾逐字节相同；
   新增 `adapters.cli host-version --check` 把「声明版本 vs 宿主版本」的静默漂移变成会红的检查，并接进 CI 与本地门禁；
   同轮第一次量到「插件把失败原因报错」的活体证据 Q6，并第三次复现「先写测试与 S1 约束互相拆台」Q7）
8. **尚未实现**的提案与评估见 [设计提案索引](designs/README.md)：
   "文档 → 规则"能否做成用户可操作的控制台、前后端连接实测（无 CORS、只能同源）、
   前端操作逻辑与失败语义、以及评审给出的两条**必须先修**的阻塞项
   （新建规则文件绕过审批、HTTP 面漂移静默）。提案与阶段记录分开放：阶段记录在 `phases/`，
   提案在 `designs/`，两者不得互相冒充。
   **前端原型已撤销**：原先的静态操作台原型（`designs/console/`）与「平台操作系统」总体设计
   （`designs/os/`）已于 2026-09-26 一并从仓库移除，这两条线上没有任何代码或界面留在仓库里。

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
| [Phase 9](phases/phase-9-control-plane.md) | 控制面重构 | **已实现（部分）**：台阶 −2 → 5 的**只报告**部分（封条与针脚 = 部分绿 / 归因闭集 / 状态代数与义务账 / 覆盖账与 `reading_context` / 仪器自证 R-h / 控制面事实表 × 跨源互证）；**升格一项未做**（2026-10-03 / 2026-10-04 裁定：一律不升格，统一到 2026-12-31 复审；义务门禁的豁免已由 `6822c81` 续期到 2026-12-31，最近到期日不再是 2026-10-31），剩余缺口 8 条 |

原文把路线称为“八个阶段”，但实际编号为 Phase 0 至 Phase 8。本次统一为**九个阶段**（Phase 0–8），不再混用口径；
表中另加一行 **Phase 9（控制面重构）**——它沿用编号续接，但**不是**第九个产品阶段：它自己的编号体系是方案的「台阶 −2 → 5」，两者不得互相代入。

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
