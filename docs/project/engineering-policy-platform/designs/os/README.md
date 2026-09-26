# 平台操作系统（Platform OS）· 总体设计

> 这份文档集回答三个问题：这个仓库该拆成几块板子（[01](01-板块拆分.md)）、每块板子上的操作怎么走（[02](02-操作流程.md)）、人看到的界面长什么样（[03](03-页面布局.md)）。
> 它不是新系统，而是**把已有的 8 块板子的边界写清楚，再补第 9 块（操作台）**。
> 全部结论来自 2026-09-22 的三轮多成员讨论（R0 事实基线 → R1 五份提案 → R2 交叉与对抗评审 → R3 定稿与复核）。
> **与既有 [文档 → 规则 操作平台](../文档转规则操作平台-可行性评估.md) 的关系**：那是「台阶 1–7」这一段路线的提案与静态原型；本文把它放进更大的操作系统骨架里当作**其中一个板块（S9）的一条流程（C）**，不重复、不替代。

## 一句话

**内核是判定，系统调用是 6 条契约路由 + 1 条运行时 OpenAPI 端点与 7 个 CLI，驱动是受控执行与验证器，文件系统是数据契约，进程与调度是编排，包与安装是已审核哈希，日志是摘要链；缺的是唯一一块没有结论、却最容易长出结论的那层——操作台。**

## 阅读顺序

| 顺序 | 文件 | 读它为了 |
| --- | --- | --- |
| 0 | [04-会议纪要与裁决](04-会议纪要与裁决.md) | **先读这个**：事实勘误 + Lead 裁决 D1–D15 + 立场变化记录 |
| 1 | [01-板块拆分](01-板块拆分.md) | 9 个板块、隐喻映射与隐喻不成立、允许/禁止关系、每块接口面 |
| 2 | [02-操作流程](02-操作流程.md) | A–H 八条端到端流程：命令、退出码、失败状态、谁判定 |
| 3 | [03-页面布局](03-页面布局.md) | 信息架构、逐页线框、首屏、失败语义、验收条目 |
| 4 | [05-待决问题与路线](05-待决问题与路线.md) | 9 个未收敛问题、五期路线、风险登记册、一页速查 |
| 5 | [meeting/](meeting/) | 会议原始记录：`r0` 事实基线、`r1` 五份提案、`r2` 五份评审、`r3` 终稿复核、`r4` 修复复核 |
| 6 | [06-操作台可用性评审与新一轮建议](06-操作台可用性评审与新一轮建议.md) | **第 5 轮（2026-09-25）**：用户视角的操作台评审——功能重要度与信息传达 / 布局与层级 / 新手与专家双适配；含必须先修的 5 项、V28–V36 与 O10–O13 |
| 7 | [07-项目对标、价值完成度与 GUI 就绪度评估](07-项目对标、价值完成度与 GUI 就绪度评估.md) | **第 6 轮（2026-09-25）**：三问三答——GitHub 对标与诚实定位、转化率五口径与"能否 100% 遵守执行"（≈30% / ≈12%，估）、GUI 就绪度（conditional-go，N=8/M=3 与 G-1…G-5） |

## 相关设计资产

| 资产 | 入口 | 关系 |
| --- | --- | --- |
| 设计提案总索引 | [../README.md](../README.md) | 本目录与文档转规则、后端契约、前端交互和评审意见的总导航 |
| 静态操作台原型 | [../console/README.md](../console/README.md) | S9 的 6 页只读原型；不是生产服务，也不产生 Decision |
| 文档转规则提案 | [../文档转规则操作平台-可行性评估.md](../文档转规则操作平台-可行性评估.md) | 本设计的流程 C，覆盖台阶 1–7 |
| 当前实现架构 | [../../../architecture/README.md](../../../architecture/README.md) | 只描述代码已经做到的能力，不把本提案当成已实现功能 |

## 一页速览

**9 个板块**（切分线：**谁能产生结论**——只有 S1 能）

| S1 判定内核 | S2 接入与适配 | S3 受控执行 | S4 验证器 | S5 检索与语料 | S6 传输边界 | S7 编排（消费者） | S8 证据与门禁 | S9 操作台【提案】 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

**8 条流程**：A 首次装配引导 · B 日常判定 · C 规则文档→可执行规则 · D Agent 接入 · E 高风险写入 · F 编排运行与恢复 · G 故障与降级 · H 运维锚定与证据。

**8 个页面**（P0 只读面）：总览 · 判定工作台 · 能力层 · 数据与契约 · 证据与门禁 · 边界与路由 · 消费方与编排 · 治理写入【写入仍须受控路由与人工审批】。

## 三条不能破的规矩

1. **判定只有一条路径**（`policy.engine.evaluate`）：界面、脚本、编排一律不得产出 allow / block，也不得把 `severity` 换算成结论。
2. **没有结论不许写成通过**：超时、503、504、429、空壳重放、`skipped`、`未核对` —— 全部是「没有结论」。
3. **数字与哈希必须带取数时刻与取数命令**：这个仓库的工作树是活的（会议期间规则集身份就变了不止一次），任何烘死的常量当天就会过期。

## 评审阻塞项：已修复

| # | 现状 | 为什么它阻塞一切 |
| --- | --- | --- |
| **B1** | 已修复：新建规则选择 `orc.policy.write`；普通编排写入拒绝 `policies/`、`registry/`、`adapters/`、`api/`、`validation/` | 专用工具 `approval: required`，并由 pre-check 与驱动双重校验 |
| **B2** | 已修复：HTTP `index.hash_drift` 来自 `LoadedCorpus.verification.drift` | 漂移条目以稳定的 `dataset:source_path` 返回 |
| **B3** | 已修复：幂等响应超过 8192 字节时不写残缺条目 | 返回 503 `idempotency_unavailable`，重试不会伪装成成功重放 |

详见 [04](04-会议纪要与裁决.md) 的 D3 / D4 / D5 与 [05](05-待决问题与路线.md) 的 P-1 期。

## 会议记录（谁说服了谁）

| 文件 | 作者 | 内容 |
| --- | --- | --- |
| [meeting/r0-facts.md](meeting/r0-facts.md) | Lead | 事实基线 F1–F39 / N1–N6（含 verifier 勘误：F13 规则数、F35/F37 编号） |
| [meeting/r1-modules.md](meeting/r1-modules.md) | kernel-analyst | 9 板块提案、隐喻映射、被否决的 5 种拆分 |
| [meeting/r1-flows.md](meeting/r1-flows.md) | flow-analyst | A–H 八条流程 + 「今天走不通」清单 |
| [meeting/r1-layouts.md](meeting/r1-layouts.md) | ui-architect | 信息架构、逐页线框、失败语义表 |
| [meeting/r1-constraints.md](meeting/r1-constraints.md) | red-team | OS 宪法 C1–C15、攻击 A1–A14、验收 V1–V22 |
| [meeting/r2-review-flows.md](meeting/r2-review-flows.md)、[r2-review-kernel.md](meeting/r2-review-kernel.md)、[r2-review-redteam.md](meeting/r2-review-redteam.md)、[r2-review-ui.md](meeting/r2-review-ui.md)、[r2-verify-proposals.md](meeting/r2-verify-proposals.md) | 全体 | 交叉评审、对抗评审与提案事实核验 |
| [meeting/r3-fact-check.md](meeting/r3-fact-check.md)、[meeting/r3-adversarial.md](meeting/r3-adversarial.md) | verifier · red-team | 对三份终稿的逐条核验与最后攻击 |
| [meeting/r4-remediation-verification.md](meeting/r4-remediation-verification.md) | Lead | B1/B2/B3 与前端第二判定的修复复核 |

## 维护方式

```powershell
# 文本规范门禁（UTF-8 / LF / 行尾空白 / 结尾换行）
python tools/check_text_conventions.py

# 仓库一致性门禁
python tools/check_repo_consistency.py

# 取数时刻：本文引用的运行期事实请当场取，不要抄文档里的数字
$env:PYTHONPATH = "src"
python -m policy.check --check-rules        # 规则集身份
git ls-files policies                       # 受跟踪基线（与上面不同是正常的）
```

## 边界（这份文档不做什么）

- **不写代码**：本文只做板块、流程与页面的设计，不新增路由、不改判定内核、不动注册表；
- **不给数字结论**：凡是会随工作树变化的计数与哈希，本文只给命令与口径；
- **不承诺「操作台已上线」**：S9 仍没有服务端挂载；P-1 修复状态与复核证据见 `meeting/r4-remediation-verification.md`；
- **第 5 轮（`06`）只做评审与建议**：它给修订清单与验收条目，不替代 `03` 的页面定稿，也不改 `05` 的路线；其中 F1–F3（生成器不失败关闭）被判定为 P0 的前置条件；
- **不替仓库所有者裁决**：O1–O9 见 [05](05-待决问题与路线.md) §1。
