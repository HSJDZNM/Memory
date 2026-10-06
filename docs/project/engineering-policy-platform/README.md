# Engineering Policy Platform 文档集

本目录是这套平台的**现状文档 + 未来工作**，不再是按轮次编写的过程记录：

| 文件 | 是什么 |
| --- | --- |
| [00-vision-and-principles.md](00-vision-and-principles.md) | 愿景、边界与设计原则 |
| [01-architecture-and-contracts.md](01-architecture-and-contracts.md) | 总体架构与核心契约 |
| [02-repository-data-sources.md](02-repository-data-sources.md) | 仓库数据源与规范转化方法 |
| [03-technology-and-layout.md](03-technology-and-layout.md) | 技术选型与目标目录 |
| [04-open-work.md](04-open-work.md) | **未完成工作与复审清单**：还没做完 / 还没核实 / 到期要复看的事项、已知边界、复审日历 |
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
- **剩下的**：剩余缺口 8 条、各处未核实、已知边界与引用纪律，全部收在
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
