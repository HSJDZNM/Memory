# 第 15 轮收口记录：按轮次拆分、门禁与基线

> **状态**：定稿（原草稿由 stage-scan 写于 task-22，写域 `.tmp/round-15/closeout/`；本文件由 Lead 补齐运行二结果与最终状态后落入已跟踪目录）。
> **每个 sha 与数字都标了来源**；标「未核实」的即没有证据。全程只读 git，未修改平台源码。
> **最终状态**（2026-09-28 22:1x +08:00）：分支 `feat/rules-and-os-platform` = `80acbe9`，工作区为空；
> `split/round-15` 与 `wip/round-15-baseline` 已删除；检查点由注释标签 `checkpoint/round-15` 固定；
> **推送未完成**——被凭据阻塞（见 §5.3）。

## 1 提交图

链：`8b0be68 -> b2c1255 -> c75886e -> b9d3b11 -> 80acbe9`（`git log --oneline 8b0be68..feat/rules-and-os-platform`，恰好 4 个新提交）。

| 提交 | 轮次 | 文件数（M/A） | 内容来源树 | 提交信息承诺了什么 |
| --- | --- | --- | --- | --- |
| `8b0be68` | 基线（不属本次拆分） | 8（7/1，相对父 `10d2fbd`） | —— | 拆分前的 `feat` 顶端 |
| `b2c1255` | 第 12+13 轮 | 73（51/22） | `.tmp/round-10/c/trees/pre`（07:19:47 创建、929 文件） | M1–M5/G3/N13/N14 + P1–P9；**声明**两轮合并及理由 |
| `c75886e` | 第 14 轮 | 11（8/3） | `.tmp/round-10/c/trees/post`（07:27:07 创建、932 文件） | 按被拒路径归因；`host_version.py` 与观测记录；CI 与门禁接线 |
| `b9d3b11` | 第 15 轮（另一会话实施） | 39（35/4） | 检查点相对 R14-post 的增量；**另有第三方快照锚点**：`.tmp/round-15/verify/trees/post`（08:47:18）与它 911/913 逐字节相同 | Q6/Q7/Q8 与诊断；**写明诚实边界**：本轮不背书，点名三处仍红（H4 / H1 / 义务无一次性） |
| `80acbe9` | 第 15 轮设计线 | 9（1/8） | 检查点中的设计文档 + 末尾换行修复 | 方案 v2 + 评审批次 1 + 索引 + 6 份证据归档；并**更正**了提交信息里「基线 = 父提交」的错误（真实父是 `b9d3b11`） |

树哈希依次为 `317c6d23 / bfe20402 / f84e2679 / c9d9060c / 202a4179`（`git rev-parse <rev>^{tree}`）。
四提交文件集**并集恰为 102 条**（= `git diff --name-only 8b0be68 80acbe9`）；其中 28 条出现在多个提交里——那是**真跨轮文件被按树切成两段**，不是重复计数。

## 2 拆分方法：真实树快照，而不是 hunk 推断

**为什么。** hunk/标记推断产出的是**分类学**（task-20 得到 R12=18 / R13=30、44 条跨轮混合、8 条「必须 hunk 拆」），依据是文档写域表、diff 标记计数、docstring——全是判据，没有一条是那一刻的字节。
树快照产出的是**历史状态**：`pre -> post` 的逐路径差集**就是**第 14 轮的改动集。只有后者能满足「提交内容 = 真实历史状态」。

**四棵副本**（实测）：`.tmp/round-10/c/trees/pre`（929 文件，无 R14/R15 标记）、`post`（932，有 R14 无 R15）、
`.tmp/round-15/verify/trees/pre`（916，有 R14 无 R15）、`post`（918，有 R14 + 6 个 R15 代码标记、无 AGENTS 第 51 条）。

**核验方法（三条，不转述提交信息）：**
1. **逐路径 blob 比对**：`git ls-tree -r -z` 取树内 blob 哈希，磁盘侧自算 `sha1(b'blob <len>' + NUL + content)`——同一个函数，因此是逐字节比较。
   结果：`b2c1255` vs R10-pre = **906/906 相同**；`c75886e` vs R10-post = **909/909 相同**；`b9d3b11` vs R15-post = **911/913 相同**（差异 1 条 `AGENTS.md`：快照只到第 50 条；缺失 1 条：第 15 轮报告写于快照之后）。
2. **多余产物核对**：两棵 R10 快照里各有 23 条不在提交树内（17 个 `__pycache__/*.pyc` + 6 个 `*.egg-info/*`），`git check-ignore` 全部命中——git 结构上不可能提交，等式必须先减掉它们。
3. **独立标记矩阵**（10 个标记逐文件读字节）：四个快照呈**单调阶梯**（无/无 → 有R14/无R15 → 有R14/无R15 → 有R14+6项R15/无第51条）。
   *自我纠错留档*：最初把 `PENDING_IMPLEMENTATION` 的标记文件写成 `src/validators/models.py`（错，实在 `evidence.py` / `pytest_runner.py` / `pipeline.py`），改正后重跑才得到上表。

## 3 为什么第 12 与第 13 轮合并成一个提交

1. **两轮之间没有树快照**：`trees/` 只有 `pre`(07:19) 与 `post`(07:27)，都在第 14 轮；`mut-final`(07:27:41) 是变异测试树，不是第 13 轮的中途快照；`.tmp/round-15/verify/trees/pre`(08:19) 已在第 14 轮之后。
2. **文件级分法只能靠推断**：R12=18 / R13=30，其中 **10 条跨轮混合**（`00-remediation-plan.md`、`dsh/hooks.py`、`policy/models.py`、`validators/models.py`、`test_cli.py`、`test_dsh_pre_evidence.py`、`test_hook_violation_visibility.py`、`test_validator_registry.py`、`validation/test-layout.yaml`、`validation/validators.yaml`）。
3. **取舍**：为保住「提交内容 = 真实历史状态」，宁可不拆——按文件拆会让两个提交都说谎。
4. **代价（点名）**：`b2c1255` 一个提交承载两轮，`git log` 读不出 M1–M5 与 P1–P9 的分界；轮次粒度损失一次。

## 4 独立验证的结论

**两轮验证**：task-21 的被测对象是 `661fd56`（已被 `80acbe9` 取代）；task-23 针对最终顶端 `80acbe9` 重跑（结论见 `.tmp/round-15/verify-final/REPORT.md`，临时产物）。

**task-21 的六项**：树同一性 通过（两分支树哈希同为 `0b0e8f69`）；提交数与顺序 通过；文件集 通过（并集 == 102）；
第 14/15 轮边界 —— 第 14 轮**完全真实**、第 15 轮等式不成立（点名）；抽样逐字节 通过；无丢失 通过（两边同为 102 files / +17962 / −250）。

**三条偏差（全部落在「说明文字/预期」侧，内容侧 0 偏差）：**
- **V1**：`c3 改动集(39) == post 到检查点的差异集(54)` 为假；差 15 条 = 9 条 c4 的设计/归档 + 6 条被 `.gitignore` 忽略的 `*.egg-info/*`。修正等式：`c3 == (post→c3) − egg-info == 39`。
- **V2**：简报把「检查点 `e235626c` = 96 文件」与「共 102 条路径」并排写给同一个提交。实测 `8b0be68..e235626c` = **96**；**102** 属于随后的 tip。
- **V3**：抽样建议说 `tools/dsh_sandbox_loop.py` 在 base/pre/post/cur 上是四个不同内容；实测是**三个**（base 与 pre 逐字节相同——该文件只属第 14、15 轮）。

**为什么这不影响拆分**：V1 的差额被两部分穷尽解释（`c3` 里不属于 `post→cur` 的路径数 = 0）；V2 的 96 与 102 各自都正确、只是分属两个提交；V3 是抽样预期写错，而该文件的真实归属由两条独立事实钉住。

## 5 门禁

### 5.1 运行一（唯一一次红）

来源 `.tmp/ci-local-timings.json`（`generated_at 21:51:38`；已复制为 `_evidence/ci-local-timings.run1.json`）：33 步、`total_seconds 938.982`、`changed_files 754`。
**唯一红项**：第 22 步 `Text conventions (UTF-8 / LF / trailing whitespace)` rc=1（0.679s）。其余 32 步 rc=0（含 581s 全量测试）。
**红因（核到字节）**：`designs/README.md` 在 `5fcdc27` / `661fd56` 里是 3294 B 且**不以换行结尾**（第 15 轮更新该索引时吃掉了末尾换行）。
**修法**：补回末尾换行；单独重跑该步 → 「检查 608 个文本文件，问题 0 处」rc=0。

### 5.2 运行二（全绿）

在修好之后的顶端树上重跑 `python tools/ci_local.py --full --timings`：**本机检查全部通过（33 步）**。
因此 `feat` 上这 4 个提交的内容**通过过本机全量门禁**。

### 5.3 推送（未完成）

`git push origin feat/rules-and-os-platform` **失败在凭据环节**，不是门禁：

```text
error: failed to execute prompt script (exit code 66)
fatal: could not read Username for 'https://github.com': No such file or directory
```

`credential.helper = manager`（Git Credential Manager）在本环境无法弹窗；`gh` 已安装但**未登录**（`gh auth status`）。
由于 git 必须先连远端才能取 refs，**pre-push 钩子根本没跑到**——所以这次失败没有产生任何门禁读数。
**待办**：由使用者在具凭据的本机推送（`git push origin feat/rules-and-os-platform`），届时钩子会在这棵树上再跑一次全量门禁。

## 6 回滚手册（已按删除分支后的现状更新）

| 想退到哪 | 命令 | 丢什么 | 不丢什么 |
| --- | --- | --- | --- |
| 退掉设计提交 | `git reset --hard b9d3b11` | `designs/*` 两份文档、索引登记行与**末尾换行修复** | 前三个提交；注意末尾换行一退，第 22 步会**重新变红** |
| 退掉第 15 轮 | `git reset --hard c75886e` | 第 15 轮全部 39 条改动 | 第 12+13、14 轮的提交 |
| 整体退回拆分前的冻结态 | `git switch --detach checkpoint/round-15` | 四个提交（它们不在检查点链上） | 检查点的 96 条冻结内容；注意它**含**末尾换行缺陷 |
| 把 feat 移回基线 | `git reset --hard 8b0be68` | 本地四个提交（此后只靠 reflog；标签不受影响） | 标签 `checkpoint/round-15` 与其指向的检查点 |
| 找回被删的 `wip/round-15-baseline` | `git branch wip/round-15-baseline 5fcdc27` | 无（若该提交已被 gc 回收则不可恢复） | 若仍在：其树 = 检查点内容 + 设计文档 |
| 回到拆分前的原始提交 | `git switch --detach e235626c` | designs 的 9 条文档 | 检查点的 96 条冻结内容 |

**重建原料仍在磁盘**：`c1 == R10-pre 去掉忽略产物`、`c2 == R10-post 去掉忽略产物`、`c3 == R15-post + AGENTS 第 51–54 条 + 第 15 轮报告`、`c4 == 检查点里的 9 条文档 + 末尾换行`。
但 `.tmp/` 会被 `tools/cleanup.py` 整体清理——**清理之后重建不再可能**，只能依赖 `feat` 上的提交本身。

## 7 遗留与未验证

1. **R12/R13 未按文件级细分**（备选分法在 `.tmp/round-15/split/ATTRIBUTION.md`，未执行；两轮之间没有快照，事后也无法补做）。
2. **`661fd56` 已被 `80acbe9` 取代**且不再有任何 ref 引用；它只出现在 task-21 的验证记录里。要复现那份记录需在 gc 前打 tag（本轮**未做**）。
3. **验证的边界（我也受此限）**：只能证明「提交 == 那些快照树」，**不能**证明「快照树 == 当时的工作树」。若快照本身被构造过，两次核验会被一起骗过。
4. **`.tmp` 一旦清理**：本轮的全部分析产物（归属表、验证报告、收口草稿、四棵快照）都会消失；能留下来的只有本文与 `01`–`05` 的归档。
5. **未验证**：四个提交各自能否独立通过 CI（门禁只对最终树跑过）；`*.egg-info` 在快照形成时是否真的存在于工作树；git 对象库完整性（未做 fsck）。
