# 第 15 轮 · 控制面重构方案 · 证据归档

- **归档对象**：`docs/project/engineering-policy-platform/designs/控制面重构方案.md`（sha256[:16] = `DF00F981EEAB3F27`，28011 B）
- **归档人 / 摘录日期**：plan-verifier（task-19）/ **2026-09-28**（读数时刻 20:53–21:0x +08:00）
- **来源树（本归档的封条）**：分支 `wip/round-15-baseline`，检查点提交 **`e235626c6b66340bb6a099df3be1adfa0932886e`**（2026-09-28 20:53:05 +08:00，提交内容 **96 个文件**）；
  摘录开始时（20:53:41）`git status --porcelain` 为空（工作树干净）。更早的基线提交是 `8b0be68`（预检时的 HEAD）。
- **摘录期间的并发写（必须知道）**：摘录过程中 Lead 又改了两个文件——`designs/控制面重构方案.md`（20:55:00，28011→33147 B，
  sha256[:16] `DF00F981EEAB3F27` → `6E13C48F76FDD011`）与 `designs/README.md`（20:55:06，`59C31EB2903372ED`）。
  因此：**本归档对方案的行号引用一律绑定 20:53 版 `DF00F981EEAB3F27`**；引用方案前先确认版本，行号可能已漂移。
  这不是谁的错，而是 W1/W2 的同一机制在摘录期间又发生了一次——**读任何读数前先问「哪棵树、哪一版」**。
- **来源 sha256[:16] / 摘录日期**：逐份写在每个文件开头的「来源」块里；本文末尾汇总。
- **补记（台阶 −1②，2026-09-28 23:20–23:35 +08:00）**：下表新增 [09-baseline-recheck.md](09-baseline-recheck.md)。矩阵与 fixture 已在**有修订号的树**（`refactor/control-plane` @ `f6b9b79`，worktree `../Memory-refactor`）上重采，因此下面「证据产出树 = 未记录修订」那条缺口被补上；09 的读数与本归档前六份的读数**分开引用**，不要混算。

## 为什么有这份归档

方案引用的证据全部在 `.tmp/round-15/`（矩阵在 `.tmp/round-09/`），而 `.tmp/` 被忽略
（`git check-ignore -v` → `.gitignore:109:.tmp/`），且 `git ls-files .tmp` = **0**。
一次 `python tools/cleanup.py` 之后原件即消失——那样这份长期文档的「现在是这样」就无法复核。
本归档把**最小证据**（结论、计数、可重算的入口）落进已跟踪目录；**不复制原件全文**。

## 文件清单（01–08 是本轮原归档；09–11 是台阶 −1/1/2 的补记；12–17 是台阶 3a/3b/小修/3c 与 §3.6 评估的补记；18 是 2026-09-30 裁定的执行；19 是第 17 轮的登记、遗留与门禁读数；20 是第 18 轮的端到端更正、`--isolated-home` 与豁免读数；21 是台阶 4 `reading_context` 的设计稿（**只写文档、不落码**）；22 是第 19 轮的合并读数、载荷建轴、设计稿与门禁读数；23 是第 20 轮的 `reading_context` 落地（前三步）与评审点，**其 §8–§9 另补记第 21 轮**：2026-09-30 第二轮裁定、覆盖账 1.1→1.2 与门禁读数；**§10–§11 是第 22 轮、§12 是第 23 轮、§13 是第 24 轮的背景登记与裁定登记**）；24 是台阶 4 `governs` 轴与声明差集的设计稿（**只报告、只写文档**）**，其 §8.3 = 2026-10-01 的五条裁定 + 第 0.5 条三条通道改判**

| 文件 | 来源（sha256[:16]） | 支撑什么 |
| --- | --- | --- |
| 本文件 README.md | —— | 索引、来源树、复核入口、口径 |
| [01-hook-matrix-summary.md](01-hook-matrix-summary.md) | hook-matrix.md `57E4F2B2F57F43FE`、verify-matrix.md `E87FCFCF289B1CB5`、两个 JSON | 方案 §1「30 臂 / 248 检查 / 0 偏差」与「第二方重算」 |
| [02-independent-verification-deviations.md](02-independent-verification-deviations.md) | 独立验收报告 `4D96D164E6C7F393` | 方案的 12 条内部验收偏差与处置 |
| [03-test-paths-disagreement.md](03-test-paths-disagreement.md) | test-layout.yaml `337D638B510D550D`、examples/dsh/dsh-adapter.yaml `985A6EE75EFF2825` | 方案 A-2「两份声明、101 个文件不一致」 |
| [04-deliberation-record.md](04-deliberation-record.md) | design/ 下 19 份过程文档（各自带 sha256） | 方案「三轮研讨」的过程、认输与未消解分歧 |
| [05-checkpoint-precheck.md](05-checkpoint-precheck.md) | SCAN.md `A69CAB68994B2C82`、EXCLUDE.md `DCE371C0E8C6ACCF`、stage-list.nul `369F047BCF74BDA5` | 检查点提交 e235626c 的预检结论与两条登记项 |
| [06-round-15-closeout.md](06-round-15-closeout.md) | 本轮提交链 `8b0be68→b2c1255→c75886e→b9d3b11→80acbe9`、标签 `checkpoint/round-15` | 按轮次拆分的提交图与来源树、门禁两次运行读数、回滚手册、遗留与未验证；含推送被凭据阻塞的事实（已补记：本机推送完成） |
| [07-final-verification-report.md](07-final-verification-report.md) | task-22 脚本（`final_check.py` / `boundary_final.py` / `reach_final.py` / `history_final.py`）与 `raw-*.txt`（原件 `.tmp/round-15/verify-final/`）；被测 sha `928df2a`、树 `f7300fcf…` | **拆分后最终状态的独立验证**：七项检查（历史 / 树同一性 / 提交信息 / 可达性 / 边界 / 抽样 / 远端）、V1–V5 偏差（5 条全部落在「复核说明 / 预期」侧，拆分内容侧 0 条） |
| [08-refactor-kickoff.md](08-refactor-kickoff.md) | 只读核对 `f6b9b79` 与 `.tmp/push-run.log` | 重构开工状态：基线、前置清单 P1–P4、待定决策 D-1/D-2、首个改码台阶 |
| [09-baseline-recheck.md](09-baseline-recheck.md) | `probe_matrix.py` `2b447c7b1007009b`、`scaffold_full.py` `54beeb162b7ef0f5`、`decision_invariance.py` `2F8A962A31891974`、`compare_decisions.py` `10A11BA62799DF37`；两棵树的摘要与来源块写在该文件里 | **台阶 −1②**：矩阵（248 检查 0 偏差）与 11 个 fixture（逐字段全等）在**有修订号的树**上重采；两棵树摘要 + 12 个文件的差集；正面控制（变异 B 红 61 条 / 变异 A 仪器崩溃无证据）；三条新发现 |
| [10-h4-field-diff.md](10-h4-field-diff.md) | 影子树 `cb73617`（+新检查 / +修复）、`h4-*.json`、两份全量 junit；逐项 sha256 写在该文件 §7 | **台阶 1（H4）**：R-d 字段级差集（allow→block、violations 0→1、served 2→1）、受影响清单（1875 条用例只翻转新增的那 1 条）、R-f 红→绿、修复形状与未证明项；8.6 原文命令（.venv）的本树门禁读数、9「先建空测试文件、再写实现」行为探针、**9.1 Q7 对照探针**（真的写了测试、导入一个还不存在的目标 → `allow_with_warnings` + `pending_implementation`） |
| [12-step3a-reason-and-redaction.md](12-step3a-reason-and-redaction.md) | `hooks.py` / 审计记录读数（该文件 §7 逐项 sha256） | **台阶 3a（H1/H10）**：受控 `decision_reason` 与归因路径脱敏的字段级差集、跨语言（Python ↔ JS）脱敏口径、审计 1.0→1.1 |
| [13-step3b-d1-field-diff.md](13-step3b-d1-field-diff.md) | 分析会话采集的两棵树的决策载荷（该文件 §5.4 预注册形状） | **台阶 3b（D-1）分析稿**：pending 移出 `violations` 的字段级差集预注册、B1–B7 的"绿但静默流失"清点、B4 的两个半边 |
| [14-step3b-landing.md](14-step3b-landing.md) | `.tmp/step3b/` 的 6 个产物（逐个 sha256）+ junit 报告 | **台阶 3b 落地**：决策 `SCHEMA_VERSION` 1.0→1.1、`POLICY_VERSION` 改 `decision-1.1`、审计 1.1→1.2、R-d 差集（0 条判定变化）、B 类 7 处、旧 checkpoint REFUSE 的证明、L5 未做项 |
| [15-small-fixes.md](15-small-fixes.md) | `.tmp/verdict-check/` 的 4 个产物（逐个 sha256） | **小修**：VERDICT 行在 `6fa800e → 466a75b` 的字段级差集 **0 条**（14 个用例 + 调用点/取值域读数 → **不升** `VERDICT_SCHEMA_VERSION`）；`warnings` 为何不触发这条轴；AGENTS 第 55 条版本轴清单；B4 正例（经 API 的 pending + 请求级 JSONL 行） |
| [16-step3c-obligation-ledger.md](16-step3c-obligation-ledger.md) | `.tmp/step3c/` 的 R-d 读数与 `readings.json`（逐个 sha256） | **台阶 3c 义务账**：三条口径与账本协议（新版本轴 `LEDGER_SCHEMA_VERSION`）、R-d 差集 **0 条**、J1(c)/(d) 读数、**L5 一轮：2 个账本 / 3 次门禁 / 命中 1 次**、预算对账（src 714 / tests 872 / 工具 137） |
| [18-round16-rulings-execution.md](18-round16-rulings-execution.md) | `.tmp/step4/` 的 R-d 读数与两条只报告步骤的实跑读数（该文件 §3 逐个 sha256） | **2026-09-30 裁定的执行（第 16 轮）**：合并 feat 的读数（**Already up to date**，feat 已是祖先）、`tool.pytest` 第 55 条核查（**不升**，证据段能读到 `validators.yaml` 摘要；Hook 审计摘要的缺口登记）、`output_schema_version = "1.1"`（1.0 追认）、义务门禁接进 `ci_local` 的**只报告**路径、台阶 4 的**五条写声明** + 只报告到期检查、R-d 差集 **0 条**、预算对账与未核实清单 |
| [19-round17-registrations.md](19-round17-registrations.md) | `.tmp/step5/` 的 R-d 读数与两次 `--full` 门禁日志（该文件 §2/§5 给出处） | **第 17 轮**：合并 `origin/perf/ci-local` 的**前置不成立**（本仓库没有这个 ref，五条读数）、义务门禁"账本不存在 = 不适用"（`REPORT_SCHEMA_VERSION` 1.0→1.1）与 R-d 差集 **0 条**、台阶 4 `reading_context` **两项登记**（Hook 侧 `tool.pytest` 追溯缺口 → `AUDIT_SCHEMA_VERSION` 1.2→1.3；JS 侧真实 dsh 端到端 = **真机 pass / 受限沙箱内 skipped**，2026-09-30 更正见 §3.1）、`check_arch_style` 既有红进**遗留**、`--full` 门禁 **退出码 0 / 8m 09.4s / 33 步** |
| [20-round18-e2e-solidification.md](20-round18-e2e-solidification.md) | `.tmp/step6/` 的门禁日志（sha256 `bb270eb8…1e64`）、R-d 读数与 `.tmp/e2e/before-gate/` 的对比清单（逐个写在该文件 §3.3 / §4） | **第 18 轮**：端到端读数更正（真机 pass / 受限沙箱 skipped，原件 sha256 `df2646db…ed30`）、`--isolated-home` 与「ACL 临时根落在工作区内」这条有名字的配置失败（`09322b0`）、豁免到期检查的 `HITS:` 机器行（`35a4ddd`，R-d 差集 **0 条**）、`--full` 门禁 **退出码 0 / 13m 29.4s / 33 步**、**交给 CI 会话的 4 项清单** |
| [21-step4-reading-context-design.md](21-step4-reading-context-design.md) | 本机只读读数（`render_json` / `_audit` / `_summary` 的键集合、`wiring.py` 与各处版本常量、`git show --numstat` 的已花行数）+ 本轮的两台探针（`.tmp/step1/probe_report_only.py`、`.tmp/step2/probe_phase_evidence_keys.py`） | **台阶 4 · `reading_context` 设计稿（只写文档）**：六类要带它的读数（`policy.check --json` / Hook 审计 / 只报告两处 / 端到端结果 / 覆盖账 / 阶段证据）逐项给出**要加的键 · 版本轴 · 消费方**，统一形状与三态纪律，`AUDIT_SCHEMA_VERSION` 1.2→1.3（`tool.pytest` 追溯缺口）归到这里；R-d 的**预注册形状**（四把尺子 × 预期差集 × 硬约束）与预算估计（台阶 4 硬上限 src 3.25k / tests 3.5k，已花 0 / 598） |
| [22-round19-merge-schema-design.md](22-round19-merge-schema-design.md) | 本机实跑读数（合并 `3627e27`、`--full` 门禁日志 `.tmp/step4/ci-local-full-r19.log` sha256 `cb7ffc59…207f`、跑前快照 `.tmp/e2e/before-gate-r19/20260930T190205/`、探针 `.tmp/step1` 与 `.tmp/step2`） | **第 19 轮**：合并 `origin/feat/rules-and-os-platform`（**零冲突**、+644/−83）并按锁文件装 `pytest-xdist==3.8.0`（附三条环境读数）、沙箱闭环载荷建轴 `SANDBOX_RESULT_SCHEMA_VERSION`（1.0 追认 / 1.1 现形状）与 `phase_evidence` 不依赖键集合的证明、`--full` 门禁 **退出码 0 / 4m 32.6s / 31 步**、跑前快照 → 跑后 **27/27 文件逐字节相同**（产物首次带 `schema_version="1.1"`）、**交给 CI 线的 5 项清单**；**§13 是第 24 轮**：使用者本机端到端第二、第三条真机读数（`92a6dd1` / `1e9df8c`，`.tmp/e2e/` 原字节与重算 sha256）、1.3 的 `declarations.test_layout` 已知偏差登记与"版本进了 feat 即视为已发布、此后改语义必须升版"规则（不追溯）、`evidence_unavailable` 那 3 条改 `unavailable` 的裁定（**接受**）；**§14 是第 24 轮的落地读数**：
`governs` 轴与声明差集（`WIRING_SCHEMA_VERSION` 1.2 → 1.3、声明 schema "1" → "2"）的 R-d
（R1 **0 条**、R2' **0 条**、R5 每份 **18 条** = 17 预注册 + 1 例外、残差尺子 **22 条**、R6 **4 条**、
R7 退出码 **0/0**）、硬约束逐字段核对、8 个 `<external>` 通道的**待写声明清单**（裁定③）、
预算（本轮 src 701 / tests 321，台阶 4 累计 1426 / 1933）与五处待评审偏离；**门禁 `--full` 跑了两次**：
`1bc5b8f` 上 **退出码 1 / 4m 56.9s**（第 20 步文本规范抓到 §14 末尾多一个空行 → `8baff4e` 修），
`8baff4e` 上 **退出码 0 / 4m 57.7s / 33 步**（第 24 步 `ok 0.8s`；跑前快照 → 跑后 81 个受控文件
**79 个逐字节相同**、2 个日志被重写） |
| [23-round20-reading-context-landing.md](23-round20-reading-context-landing.md) | 本机实跑读数：四把 R-d 尺子 + 只报告三条出口的 before/after（`.tmp/step7/`，仪器逐个 sha256）、`--full` 门禁日志与跑前/跑后快照、`.tmp/e2e/` 的两份真机 pass 转录件（逐份 sha256 写在 §2 与 §4） | **第 20 轮**：四条裁定（写进 21 号 §9.1）的执行——端到端结论载荷（`SANDBOX_RESULT_SCHEMA_VERSION` 1.1→1.2）、两条只报告读数（义务门禁 1.1→1.2；豁免到期**首建** `EXEMPTION_REPORT_SCHEMA_VERSION = "1.1"`）、`policy.check --json` 外层包装（`OUTPUT_SCHEMA_VERSION` 1.1→1.2 + 学习手册重生成）；**`reading_context` 的实现只有一份**（`src/provenance/reading_context.py`）；R-d 逐条核对 21 号 §5 的四把尺子；门禁读数（**退出码 0 / 5m 02.9s / 33 步**，`--full`）与"跑前快照 → 跑后 43 个文件里 41 个逐字节相同"的比对；登记使用者真机 `result=pass` 转录件（**从终端输出转录，不是原文件字节**）与 pre-push 覆盖现象；**跑前**写下的沙箱放宽理由（§4.1）与**跑后**的实际过程记录（§4.2：申请的那次放宽挂起未获批、真正生效的是使用者把会话策略改成 `danger-full-access`），以及 R4 在真产物上多出的 2 条**环境归因漂移**（§4.5，附归因实验）；**§8–§9 是第 21 轮的补记**——2026-09-30 第二轮四项裁定（写进 21 号 §9.2）的落地、覆盖账 `WIRING_SCHEMA_VERSION` 1.1 → 1.2（载荷级 R-d **4 条**）与门禁读数（**退出码 0 / 5m 35.6s / 33 步**；跑前快照 → 跑后 43 个受控文件**内容**逐字节相同，两个日志文件被重写成了同样的内容）；**§10 是第 22 轮的背景登记**（使用者本机真机 `--isolated-home` 端到端的**原字节**原件 `.tmp/e2e/pass-20260930T214825.json`：`result=pass` / `host.sandbox=unrestricted` / `tree.revision=7864dd2…`，关闭"真机 unrestricted 未采到"；以及 `7864dd2` 上那次 pre-push 门禁的旁证与它**没落盘**的汇总行）；**§11 是第 22 轮 · 审计 `reading_context` 的落地读数**（`AUDIT_SCHEMA_VERSION` 1.2 → 1.3：R1 决策载荷 **0 条**、VERDICT 行**逐字节相同**、51 条审计记录**只多出预注册的键与版本号**（107 条差集 = 51×2 + 5）、三条硬约束读数（延迟 0.53 ms/次、A/B 中位数 −1.8/+1.6 ms、11 个 fixture 无一超 50 ms；最大记录 6574→7518 B、余量 54.11%；1.2 不回写 + 混排链 `verify()==()`）、`--full` 门禁 **退出码 0 / 5m 00.1s / 33 步**、跑前快照 → 跑后 55 个受控文件 53 个逐字节相同，以及跑前删掉 ACL 残留的那次**程序级放宽**（只删一个 pytest 落点目录））；**§12 是第 23 轮的补记**——2026-09-30 **第三轮三项裁定**（`tree` 不带 `revision` 与 `host.sandbox=unknown` 接受；`declarations.test_layout = not_applicable` **不接受**，1.3 内改正、不升版）与提交 `096cb0d` 的落地读数：决策载荷 **0 条** / VERDICT 逐字节相同 / 51 条审计记录**21 条全部预注册**（残差 0、六个判定字段 0 命中）、三条硬约束重测（0/24 超 50 ms；最大记录 7519 → 7823 B、余量 52.25%；1.2 不回写 + 混排链 `verify()==()`）、`--full` 门禁 **退出码 0 / 4m 58.6s / 33 步**、跑前快照 → 跑后 69 个受控文件 67 个逐字节相同；**§17 是第 27 轮 · 2026-10-03 裁定①②③④⑤ 的落地（WIRING 1.3 的定稿）**——声明随宿主同批收尾（`declared` 8→6、`declared_not_discovered` 4→2 并如实报出「不止 `ci-agent-runtime`」）、`reason` 措辞按真实成因分开写、第六格 `expected_absent_present`（1.3 内加、不升版）、真实 now 与钉死 now 的 7 天窗口对照、三条**先于本轮**的墙钟到期红、预算 src 1559 / tests 2096、门禁 `--full` **退出码 1 / 4m 17.1s / 33 步**（两处失败同源于那 3 条墙钟到期用例）、跑前快照 → 跑后 93 个受控文件 **91 个逐字节相同** |
| [24-step4-governs-axis-design.md](24-step4-governs-axis-design.md) | 本机实跑读数（`adapters.cli wiring --json --now 2026-10-01T00:00:00+08:00` 的 24131 B 载荷、`provenance.cli wiring-scope --check` 的 `declared: 7`、`tools/exemption_expiry.py` 的 `HITS: 0`）+ 代码阅读（`wiring.py` 的 `WIRING_SCHEMA_VERSION = "1.2"` 与轴字段、`.github/workflows/phase-8.yml:277-278` 的报告模式步骤） | **台阶 4 · `governs` 轴与声明差集设计稿（只报告）**：按 `kind` 分档 + `covers` + 「有意治理另一棵树」的声明位；`account` 三数（discovered / declared / measured）与五个差集的定义；**`in_scope_not_wired` 在只报告期的四层表达**（看得见 / `red_conditions.enforced=false` / 退出码一个都不动 / 升格路径）；版本轴 `WIRING_SCHEMA_VERSION` 1.2→1.3 与 `wiring-scope.yaml` `"1"`→`"2"`；消费方总表；R-d 预注册（R1/R2'/R5/R6/R7）；预算（台阶 4 累计 src 681 / tests 1527，复核线 1.95k / 2.1k）；未核实 7 条与请评审 6 条；**§8.3 = 2026-10-01 的五条裁定**（声明文件 schema "2" 兼容 "1" 且**不许新增加载期 FATAL**；既有 13 个顶层键不删不改名、本台阶**只新增四个**；8 个 `<external>` 通道按证据判定、拿不出证据写 `unknown`；CI `skipped` 三数写 `unavailable` 不许写 0；`measured` 只取两根轴都评过的口径）与第 0.5 条（三条通道改判，`26bf07b`）；**§8.4 = 2026-10-01 的 `covers` 数据与 `governs_tree` 默认值裁定**；**§8.5 = 2026-10-03 的二次更正**（`verify-*` 是治理能力验证轮的实验 profile：撤回 `covers`、删 `dsh-verify-profiles` / `dsh-verify-dead-channel`、`reason` 措辞、第六格 `expected_absent_present`、「树声明与证据不一致」仍不进任何一格、R-h 挪到第二十三轮） |
| [25-step4-instrument-self-proof-design.md](25-step4-instrument-self-proof-design.md) | 本机实跑读数（`ci_local.py --list` 的 44 / 31 / 30 / 11 / 2、`governance_gap_probe.CHECKS` 的 13 条、`provenance_loop.SCENARIOS` 的 5 条、只报告步骤 1 条）+ `git diff --numstat` 的分桶 | **台阶 4 · 仪器自证（R-h）设计稿（只报告）**：三态皆红（无 `check_id` / 无 `mutation_id` 且无 `gap_note` / 变异 `patch_not_applicable`）的判据式与两条反退化（「未评」不是「不红」、对象清单要有第二来源）；只报告期的四层表达（`enforced: false` + `would_exit_code: 1` + 机器行 + 退出码恒 0）与 L5 同型的升格路径；新载荷首建轴 `INSTRUMENT_SELF_PROOF_SCHEMA_VERSION = "1.0"` 与检查登记表 8 字段（只放指针）；消费方总表；R-d 预注册（R1/R2'/R5/R6/R7 + 新载荷自证 + 影子表自证）；**需要 CI 线配合的 6 项交接清单**（`ci_local.py` / `phase-8.yml` / `test_ci_local*.py` / `phase_evidence.py`——控制面会话一个字都不动）；预算（台阶 4 累计 src 1467 / tests 2015；R-h 估计 src 260–440 / tests 180–300 → **tests 必越复核线 95–215 行**，三个缩小方案 A/B/C 与推荐 A）；未核实 5 条与请评审 7 条。**同一轮**：23 号 §15（§14.2 六条裁定 + 502 背景登记）与 **§16（第 0.5 条稳定性小修与自证、裁定④ 的 R-d、covers 数据的真实读数与两处待评审、豁免 `declared=9`、预算、门禁 `--full` 退出码 0 / 5m 07.7s 与跑前跑后比对）**、24 号 §8.4（covers 数据与默认值的裁定） |
| [17-step4-5-scope-assessment.md](17-step4-5-scope-assessment.md) | 本次实跑 `adapters.cli wiring --json`、`ci_local.py --list`、两份测试路径声明与各数据文件（逐条来源写在表里） | **§3.6 前置评估**：台阶 4–5 的两份**整数清单**（已声明不治理 **2** 条；在范围内 **4 组 + 5 组**）与逐条"建机制 / 写声明 / 只报告"结论（台阶 4：5/5/0；台阶 5：4/2/1）；D-2 冻结下**只交清单**；**§8.2 = 2026-10-01 的三条未声明通道改判**（判决不变、理由与到期日改；`26bf07b`） |
| [11-step2-origin-closure.md](11-step2-origin-closure.md) | `provenance/origin.py` `43d301bd547f1428`、`origin_runtime.py` `4bd867cf875cbb81`、`hooks.py` `75a0f52e7ac2bf83`、插件 `26ABA823F6DD9949`、契约用例 `1AC992EFDBE11336`；R-d 读数在 `.tmp/rd-diff/` | **台阶 2（归因闭集与核验前置，判据 R-g）**：五族闭集 + 每族必备字段 + 「写不出 fix 的 origin 不许存在」；核验前置与「证伪自己人落 unknown_origin」；配置族（Python）与 spawn 输入族（JS）的读数；R-d 字段级差集（11 个 fixture：0 条判定变化、3 条新增 `origin`、4 条墙钟漂移） |

## 复核入口（全部只读）

1. **看检查点里有什么**：`git show --stat e235626c`；取单文件历史用 `git show e235626c:<path>`。
2. **重算测试路径不一致**（本归档里唯一「不依赖 .tmp 也能重算」的读数）：两份声明都在 tracked 树里，见 03 文件 §复核。
3. **原件还在时**（.tmp 未被清理）：按 01/04/05 各自的「复核」小节给出的路径与命令读原件。
4. **口径核对**：本归档每份文件都写明来源 sha256[:16] 与摘录日期；读数与原件不一致时**以原件为准**并重采。

## 只在 .tmp 还在时可复核的部分

- **30 臂矩阵的重跑**：仪器 `.tmp/round-09/harness/probe_matrix.py`（sha256 `2b447c7b1007009b52aa3a8239a5f24ba306cc77e40c10c003109f61485845b3`）与臂脚手架、每条臂的项目副本都在 .tmp 下。
- **研讨的三轮过程产物**：立场文件 / 交叉质询 / 收敛稿（.tmp/round-15/design/）——本归档只摘结论。
- **原始证据文件**：C 的 `evidence-q7-cases.{out,r1}.txt`、`evidence-asymmetry.*`；独立验收者的 25 条事实复核原始输出 `.tmp/round-15/verify/plan/*-raw.txt`。
- **预检的支撑记录**：`.tmp/round-15/stage/_support/`（scan.json、status-z-*.json、entropy-table.md、machine-table.md 等）。
- 结论：**上列四项在 cleanup 之后不可复核**；本归档给出的是它们的结论与出处，不是它们的副本。

## 「证据属于哪棵树」的口径

**同一份载荷在两棵树上得到两个结论不是缺陷；没写清是哪棵树才是**（AGENTS 第 48 条，原文在 `AGENTS.md` 第 48 条）。
本归档涉及的树一共三棵，引用任何读数前先问「哪一棵」：

| 树 | 标识 | 覆盖什么 |
| --- | --- | --- |
| 检查点树 | `e235626c`（tracked，可复现） | 本归档自身的来源；test-paths 重算在这棵树上做过 |
| 工作树 | 预检时的未提交状态（当时 HEAD `8b0be68`） | 预检与「冻结前」的读数属于它；这些变更现已全部进入 `e235626c` |
| 证据产出树 | **未记录修订** | 30 臂矩阵（`2026-09-27T15:31:00Z` 起跑）与 11-fixture 读数属于它；见 01 文件「不证明什么」 |
| 重采树（台阶 −1②） | `refactor/control-plane` @ `f6b9b79`（worktree `../Memory-refactor`） | [09](09-baseline-recheck.md) 的矩阵 / fixture 读数属于它；pre 侧对照树是 round-10 `c/trees/post`（**不是 git 仓库根，无自有修订号**） |

## 边界（本归档不主张什么）

- 我**没有**重跑矩阵、门禁、受治理会话；01/04/05 的数字来自原件（逐份标注 sha256）或我自己的只读重算（03）。
- 我没有复制原件全文，因此**原件里的逐条明细**（248 条检查、30 条臂的 expected/actual、93 条路径清单）不在这里。
- 凡我没有亲自读到原文的数字，都在相应文件里标「**未核实**」。
