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

## 文件清单（01–08 是本轮原归档；09 / 10 是重构台阶的补记）

| 文件 | 来源（sha256[:16]） | 支撑什么 |
| --- | --- | --- |
| 本文件 README.md | —— | 索引、来源树、复核入口、口径 |
| [01-hook-matrix-summary.md](01-hook-matrix-summary.md) | hook-matrix.md `57E4F2B2F57F43FE`、verify-matrix.md `E87FCFCF289B1CB5`、两个 JSON | 方案 §1「30 臂 / 248 检查 / 0 偏差」与「第二方重算」 |
| [02-independent-verification-deviations.md](02-independent-verification-deviations.md) | 独立验收报告 `4D96D164E6C7F393` | 方案的 12 条内部验收偏差与处置 |
| [03-test-paths-disagreement.md](03-test-paths-disagreement.md) | test-layout.yaml `337D638B510D550D`、examples/dsh/dsh-adapter.yaml `985A6EE75EFF2825` | 方案 A-2「两份声明、101 个文件不一致」 |
| [04-deliberation-record.md](04-deliberation-record.md) | design/ 下 19 份过程文档（各自带 sha256） | 方案「三轮研讨」的过程、认输与未消解分歧 |
| [05-checkpoint-precheck.md](05-checkpoint-precheck.md) | SCAN.md `A69CAB68994B2C82`、EXCLUDE.md `DCE371C0E8C6ACCF`、stage-list.nul `369F047BCF74BDA5` | 检查点提交 e235626c 的预检结论与两条登记项 |
| [06-round-15-closeout.md](06-round-15-closeout.md) | 本轮提交链 `8b0be68→b2c1255→c75886e→b9d3b11→80acbe9`、标签 `checkpoint/round-15` | 按轮次拆分的提交图与来源树、门禁两次运行读数、回滚手册、遗留与未验证；含推送被凭据阻塞的事实（已补记：本机推送完成） |
| [08-refactor-kickoff.md](08-refactor-kickoff.md) | 只读核对 `f6b9b79` 与 `.tmp/push-run.log` | 重构开工状态：基线、前置清单 P1–P4、待定决策 D-1/D-2、首个改码台阶 |
| [09-baseline-recheck.md](09-baseline-recheck.md) | `probe_matrix.py` `2b447c7b1007009b`、`scaffold_full.py` `54beeb162b7ef0f5`、`decision_invariance.py` `2F8A962A31891974`、`compare_decisions.py` `10A11BA62799DF37`；两棵树的摘要与来源块写在该文件里 | **台阶 −1②**：矩阵（248 检查 0 偏差）与 11 个 fixture（逐字段全等）在**有修订号的树**上重采；两棵树摘要 + 12 个文件的差集；正面控制（变异 B 红 61 条 / 变异 A 仪器崩溃无证据）；三条新发现 |
| [10-h4-field-diff.md](10-h4-field-diff.md) | 影子树 `cb73617`（+新检查 / +修复）、`h4-*.json`、两份全量 junit；逐项 sha256 写在该文件 §7 | **台阶 1（H4）**：R-d 字段级差集（allow→block、violations 0→1、served 2→1）、受影响清单（1875 条用例只翻转新增的那 1 条）、R-f 红→绿、修复形状与未证明项 |

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
