# Engineering Policy Platform 文档集

本目录是这套平台的**现状文档 + 未来工作**，不再是按轮次编写的过程记录：

| 文件 | 是什么 |
| --- | --- |
| [00-vision-and-principles.md](00-vision-and-principles.md) | 愿景、边界与设计原则 |
| [01-architecture-and-contracts.md](01-architecture-and-contracts.md) | 总体架构与核心契约 |
| [02-repository-data-sources.md](02-repository-data-sources.md) | 仓库数据源与规范转化方法 |
| [03-technology-and-layout.md](03-technology-and-layout.md) | 技术选型与目标目录 |
| [04-open-work.md](04-open-work.md) | **未完成工作与复审清单**：还没做完 / 还没核实 / 到期要复看的事项、已知边界、复审日历 |
| [05-implementation-plan.md](05-implementation-plan.md) | **实施计划**：从「动作判定」到「产物判定」的四阶段路线、每阶段的门与判据、对比实验方案 |
| [06-plan-progress.md](06-plan-progress.md) | **计划进度**：记录格式 + 执行记录（只收录技术读数与关键决策记录；纯文档 / 措辞 / 行政性变更不记录） |
| [07-status-brief.md](07-status-brief.md) | **进度简报（给非技术读者）**：在做什么、做到哪了、接下来做什么、你需要做什么；不含命令与内部编号 |
| [2026-10-21-new-session-prompt.md](2026-10-21-new-session-prompt.md) | **新会话交接提示词**：给下一个 agent 会话的完整任务书（现状、剩余任务、验收、纪律） |
| [testing/test-strategy.md](testing/test-strategy.md) | 测试策略 |
| [testing/acceptance-matrix.md](testing/acceptance-matrix.md) | 阶段验收矩阵 |
| [designs/README.md](designs/README.md) | 设计提案状态表（提案 / 状态 / 影响面 / 下一步） |

技术架构说明、术语与口径、规则转化两篇在 `docs/project/architecture/`；
仓库级文档分类与维护命令见 `docs/README.md`。

## 现在做到哪

平台已经跑完 Phase 0–8，并在 Phase 8 之后做了一条横向轨道（Phase 9 控制面重构）：

- **Phase 0–8 已交付并可用**：规则集与判定引擎（43 条规则）、dsh Hook 适配器、检索层、受控执行层、
  代码验证器、多 Agent 适配层、Policy API、LangGraph 编排消费者。安装、测试、CLI、闭环与评测命令
  以根 `README.md` 为准，且都是实际可执行、实际验证过的命令。
- **仍在外部环境上的两件**：Phase 6 的**第二真实 Agent 产品验证**与 Phase 8 的**真实 `ChangeAuthor`
  模型实现**——本仓库的合成协议消费者与 `ScriptedAuthor` 不能宣称完成它们。
- **Phase 9（控制面重构）**：台阶 −2 → 5 的**只报告部分**已落地（针脚与封条、归因闭集、义务账、
  覆盖账与 `reading_context`、仪器自证 R-h、控制面事实表 × 跨源互证）；**升格（把任何一条只报告读数
  接成阻断）一项都没做**——2026-10-03 / 2026-10-04 裁定一律不升格，统一到 **2026-12-31 复审**。
  四条只报告步骤的豁免到期日都是 2026-12-31；义务门禁另有一条**结构问题**（仓库门禁里读不到账本）
  同样留给 12-31。
- **Phase 9 之后的新计划（2026-10-17 起）**：把「动作判定」推进到「产物判定」的四阶段计划已开跑
  （[05-implementation-plan.md](05-implementation-plan.md)）：**阶段 A** 覆盖表、5.71 探针、5.72 接线修复已落地；
  A3 干跑两轮：v1 **3/4** 暴露构造/口径问题，经三派评审 + Lead 裁定（[裁定](readings/2026-10-18-A3-fix-adjudication.md)）
  后 v2 **4/4 + 任务完成**（[读数](readings/2026-10-18-A3-dryrun-v2.md)）；**阶段 B** 的 B2（测试支撑声明）与 B1（审批 1.3「参数域」，`fe292b9`）、B3（只读族读面闸门，`9a88112`）均已落地；
  B1 的真实受治会话仍需使用者签 1.3 条子。**阶段 C**：C3 三段（整树门禁 `aca9491`、控制面 `.policy` 写面 `8e6a3cb`、执行面 `.git`/CI `45d6168`）与 C1-a（批次台账只报告，`05a05d5`）已落地；
  C1-b/C2/C4 的裁定草案见 [2026-10-21 草案](readings/2026-10-21-C1C2C4-adjudication-draft.md)；新会话交接提示词见 [2026-10-21-new-session-prompt.md](2026-10-21-new-session-prompt.md)。**阶段 D** 的**校准门**通过（P+/P−/canary）；2026-10-19 交付并**冻结**了
  门 2 前置包：treatment（`tools/**` 纳入生产文件，[读数](readings/2026-10-19-treatment-tools-pattern.md)）、任务包 v3
  （`examples/dsh/b-plan/a3-task-v3/`）、隐藏验收 30 条 + runner（`testing/ab/dgate2/hidden/`）、评分器
  （`testing/ab/dgate2/scorer/`，`freeze.status=frozen`，清单组合摘要 `e3ef9e91…`）、C 臂（不治理）装配与 n=1 冒烟
  （`testing/ab/dgate2/c-arm/`；目录索引与边界见 `testing/ab/dgate2/README.md`）。**A/B/C 主实验已于 2026-10-20 各跑一次（n=1）**：三份 run-manifest 已写全
  （16 recorded / 1 not_applicable，`--strict` PASS），H2/H3 人工项已复核。**2026-10-19 已把清单与读数工具化**：
  `testing/ab/dgate2/run-manifest/`（17 字段生成/校验，`RUN_MANIFEST_SCHEMA_VERSION` 1.0）与
  `testing/ab/dgate2/run-record/`（T/C/A 三维读数，`RUN_RECORD_SCHEMA_VERSION` 1.0），读数见
  [冻结包复核](readings/2026-10-19-D-gate2-run-ready-verify.md) 与 [run-record 样例](readings/2026-10-19-D-gate2-run-record.md)；**A/B/C 已于 2026-10-20 各跑一次（n=1）**：现状治理臂未完成、treatment 臂与不治理臂完成；案例读数见
  [10-20 run 读数](readings/2026-10-20-D-gate2-ab-c-runs.md)，run-manifest 在
  `testing/ab/dgate2/runs/2026-10-20/`；H2/H3 已复核（[H2](readings/2026-10-20-H2-bypass-sampling.md) / [H3](readings/2026-10-20-H3-a4-review.md)）。
  执行记录在 [06-plan-progress.md](06-plan-progress.md)，
  非技术读者先看 [07-status-brief.md](07-status-brief.md)。
- **剩下的**：受治侧同步（注册表 1.4 + read_guard + `.policy`/`.git` 前缀）并重审、C4 验证探针、C1-b 裁定、间接执行面（`tools/**` 经 CI、`.gitattributes`）、D 实验每臂 k≥3、评分器已知边界、**AGENTS 指令预算**（已到 65.6 KB，建议拆出第 55 条轴表）、各处未核实与引用纪律，全部收在
  [04-open-work.md](04-open-work.md)——它是"还没做完"的唯一去处。

## 文档约定

每个阶段文档固定回答六个问题（现状文档沿用同一套口径）：

1. 这一阶段解决什么问题；2. 明确不做什么；3. 按什么顺序开发；
4. 如何进行单元、契约、集成和安全测试；5. 需要观察和保留哪些证据；6. 满足什么条件才能进入下一阶段。

**过程记录不再保留**：按阶段与按轮次的实施记录、复核与修复轮记录已于 2026-10-06 下线；
它们的编号对照表在 [04-open-work.md](04-open-work.md) 的附录里（只保证编号可查，结论以现状文档为准）。
仍在影响未来开发的内容已经提炼进 [04-open-work.md](04-open-work.md)，不要再去历史提交里找结论。

## 来源

- 原始架构文档：已拆分并合并进本目录；
- 共享对话：<https://chatgpt.com/share/6aaa6218-6d64-83ee-9585-e2a4173a77cd>；
- 仓库内 Google、GitLab、OWASP、PEP 与 .NET 官方文档离线镜像，具体映射见
  [仓库数据源](02-repository-data-sources.md)。

共享对话只作为设计背景，不作为可执行规范。真正进入系统的规则必须有本地来源、稳定标识、适用范围、执行方式和测试证据。
