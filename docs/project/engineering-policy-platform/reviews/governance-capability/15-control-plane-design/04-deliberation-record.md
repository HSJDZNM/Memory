# 04 · 三轮研讨的过程记录

- **来源**：`.tmp/round-15/design/` 下 19 份过程文档（逐份 sha256[:16] 见 §3）＋ Lead 的四份母体文档（同目录）
- **摘录日期**：2026-09-28；**来源树**：检查点 `e235626c` 的工作树状态（过程文档在 .tmp，不随提交入库）
- **本文件是什么**：过程摘要（参与者、每轮产出、认输与证伪、裁决摘要、未消解分歧）。**原件不在本目录**。

## 1 参与者与写域（互斥）

| 角色 | 主题 | 写域 | 产出 |
| --- | --- | --- | --- |
| A（aspect-config） | 配置与控制面的单一真源 | `.tmp/round-15/design/A/` | 立场 / 交叉质询 / 收敛 |
| B（aspect-attribution） | 失败归因与依赖边界（平台/dsh/OS/项目） | `…/design/B/` | 同上 |
| C（aspect-state） | 状态语义（跳过/待实现/失败/未覆盖） | `…/design/C/` | 同上 |
| D（aspect-coverage） | 覆盖账与接线治理 | `…/design/D/` | 同上 |
| E（contrarian，反方） | 承诺面 vs 控制面的替代框架 | `…/design/E/` | 立场 / 收敛 |
| Lead | 母体判定、裁决、综合草案 | `…/design/`（顶层） | 00/10/20/30 + PLAN-draft |
| plan-verifier | 独立验收（不参与设计） | `.tmp/round-15/verify/` | 25 条事实复核 + 12 条偏差（见归档 02） |

## 2 三轮

| 轮 | 产出 | 份数 | 说明 |
| --- | --- | --- | --- |
| 第 1 轮 · 立场 | `A/A-position.md` 等 | 5 | 各方面给目标形态、坐标、四问与红→绿判据 |
| 第 2 轮 · 交叉质询 | `A/A-cross-review.md`、`B/X-cross-review.md`、`C/X-cross-review.md`、`D/D-cross-review.md` | 4 | 互指对方判据「会绿而问题存在」、口径混用、代价漏算 |
| 第 3 轮 · 收敛 | `A/Z-convergence.md` … `E/Z-convergence.md` | 5 | 逐条对 L1–L7 表态；E 先写四处认输 |
| Lead 母体 | 00 问题陈述 / 10 母体判定 / 20 修订针脚 / 30 裁决 L1–L7 | 4 | 10 先行，可被四方面推翻 |
| 综合 | `PLAN-draft.md` | 1 | 五件东西 + 六个台阶 + 红线 R-a..R-h |

## 3 产物清单（sha256[:16] / 字节 / mtime）

| 文件 | sha256[:16] | 字节 | mtime |
| --- | --- | ---: | --- |
| 00-problem-statement.md | 4F417548E5CC0FE7 | 5459 | 08:20:47 |
| 10-lead-thesis-and-outcome-criteria.md | 7D11320FB333EB8C | 10032 | 08:22:29 |
| 20-revision-pin.md | 535FA470BD589D9A | 11945 | 08:49:18 |
| 30-lead-rulings.md | 507E7A6B734D41A9 | 5216 | 08:38:28 |
| PLAN-draft.md | F06BFF1C2F680751 | 21498 | 08:40:54 |
| A/A-position.md | F62CC7489F3A7B85 | 40745 | 08:32:47 |
| B/B-position.md | EBC64CB3B32337F1 | 45997 | 08:31:04 |
| C/C-position.md | 80FA4FC093B89A6F | 39045 | 08:33:16 |
| D/D-position.md | 3E1660AD2F332D9E | 40947 | 08:37:29 |
| E/E-contrarian.md | 98E61D7B3187016C | 25188 | 08:31:01 |
| A/A-cross-review.md | B156E785E1A432A3 | 20178 | 08:36:35 |
| B/X-cross-review.md | 743B6411C6009E1F | 22272 | 08:36:48 |
| C/X-cross-review.md | CCC8F05CC3305CDC | 20428 | 08:36:55 |
| D/D-cross-review.md | EB27D93B63EF76D3 | 18731 | 08:37:13 |
| A/Z-convergence.md | 73F17B404300957D | 10946 | 08:39:15 |
| B/Z-convergence.md | 46214322416272FF | 11038 | 08:39:44 |
| C/Z-convergence.md | 64824845E0159782 | 8506 | 08:39:45 |
| D/Z-convergence.md | C3689A9B82FC96D9 | 10997 | 08:40:05 |
| E/Z-convergence.md | B48AAF22EDE4F43E | 8191 | 08:39:52 |

## 4 被证伪与认输的清单（含 Lead 自己的错）

**E（反方）四处认输**（`E/Z-convergence.md:7-28`）：
1. 0.1 分母 vs 发现集——D 对，措辞错（改为「发现集不是一个数；分母＝声明集，可由一次提交冻结」）；
2. 0.2 自己的判据自相矛盾（要求 cleanup 前后三数相同，又说 cleanup 会让 8 条通道失效）——改判据为 measured 归零并解释；
3. 0.3 §3.1-D 基于**不存在的机制**（`wiring.py:1659-1671` 候选根只有四类，`.tmp/**` 永不在候选里）；
4. 0.4 计数轴选错（漏掉 2 条 failed 通道），但按 D 的轴重算后结论方向不变。

**其他人的自我修正**：
- **B**：「我把『弱化检查→变绿』当成了『会红证明』」——认错，改为三类变异（`B/Z-convergence.md:34`）。
- **C**：一次性义务的键设计错误（用 `tree_digest` 作键，每次写盘都换树）——已改为会话内记账（`C/Z-convergence.md:9`）。
- **A**：原「不递增任何版本」修正为「只递增 AUDIT，不递增 EVIDENCE/PIPELINE/决策」（`A/Z-convergence.md:10`）；
  另撤回「封条只要一层」、承认 A-4…A-8 只有构造红（`PLAN-draft.md:300` 转记）。
- **D**：原「J3 不能绿」不成立，自行修正（`D/Z-convergence.md:22`）。

**Lead 自己的错（被指正后改判）**：
- L7 原三条**不够** → L7′ 四条（缺「声明数据文件」则 J4 不可能绿，缺「最小自证载体」则 J5 与 L5 上线闸失去载体）（`PLAN-draft.md:189-192`）。
- `30-lead-rulings.md:51-53` 自陈：本裁决本身也可能错（L4 的合表可能违反「表不放值」；L1 的「不递增」可能让未被识别的消费方误读）。
- 树外写者把 Q6/Q7/Q8 写进 AGENTS 第 51–54 条后，Lead 认「本方案不能静默推翻第 51 条」，落地需显式修订（`20-revision-pin.md:144-148`）。
- 独立验收的 12 条偏差（含 5 条事实不实：无独立验收 / 时间窗 / 针脚表漂移 / 常量名 / CI 行号）→ 方案附录 A/B 逐条处置（见归档 02）。
- 外部评审 §1.1「前提读数针对旧内核」→ 方案新增台阶 −1（重采矩阵与 fixture 并钉摘要）。

**被测对象自身被证伪**（不是人的错，但属于同一类）：矩阵首轮 9 条不一致里，2 条是**被测对象口径变了**（P1 修复后 `violations` 字段出现），
期望本身作废——「红过才成立」的闸门因此被加在检查上（`hook-matrix.md:143`）。

## 5 Lead 裁决 L1–L7（一句话各一条；原文 `30-lead-rulings.md` `507E7A6B734D41A9`）

1. **L1** 协议递增由「键的集合/含义变了」触发，不由「语义变了」触发：审计 1.0→1.1，决策保持 1.0（要改必须给差集+重记快照+审计记依据版本）。
2. **L2** 针脚拆成四个名字、**一套实现**（落 `src/policy/worktree.py`）：判据级 + 轮次级两层封条都要；pre/post 不一致 → `invalidated`。
3. **L3** J2 口径改为「**除显式例外，逐字段全等**」，并新增红线 **R-d**：任何会改 decision 的步骤先出差集。
4. **L4** 新增声明文件**上限两张**：`validation/control-plane.yaml`（facts 与 checks 合表，字段不重叠）＋ `adapters/wiring-scope.yaml`。
5. **L5** 新的加载期 FATAL 必须有**上线闸**：先 warn + 非零退出跑满一个轮次，再升格；这条闸自身要有一条会失败的检查。
6. **L6** D 的六处必须修：governs 分档 + 退出码表补格 + 禁比例（顶层键白名单）+ `--environment` 只选声明段 + 渲染基准含 `--project-root` + 豁免续期可发现。
7. **L7** 最小可行子集三件事（① 轮次封条 + 修订针脚 ② Q1/Q7 pending 与 H4/H5 的「没跑≠served」 ③ 边界裁定 + 三数分离，不新增层）；后被 L7′（四条）取代。

## 6 未消解的分歧（`PLAN-draft.md:171-181`，6 条）

1. pending 的表达：warning violation ↔ `not_evaluated`（C ↔ 树外写者）→ 按 C；**因 AGENTS 第 51 条已写反，落地需显式修订契约**。
2. 清点算不算义务的判罚点（C ↔ D）→ 按 C（清点只报计数与年龄，判罚在本机门禁）。
3. `tree_moved_under_verification` 归属（B ↔ D）→ 按 D（仅当树在判定期间移动且仍签发 allow/block 才升格为 origin 码）。
4. `platform_revision` 的范围（C ↔ D）→ 按 D（由声明给出，不写死目录；反例就是本轮 W1 改的文件不在写死范围里）。
5. 路径表示函数的归属（A ↔ B）→ 按 B（共用一个函数、两个 profile：display / audit）。
6. 义务是否进最小集（C ↔ Lead L7）→ 已由收敛轮解决：义务留在台阶 3，**不在最小集**，C 的反对记在案。

## 7 怎么复核

- 原件在 `.tmp/round-15/design/`（**只在 .tmp 里**）：按 §3 的 sha256[:16] 与 mtime 定位；表里的引文都带 file:line。
- 与最终方案的对应：`designs/控制面重构方案.md`（`DF00F981EEAB3F27`）附录 A/B/C 复述了本文件 §4–§6 的内容。
- 本文件**未核实**的项：无（所有引文都是我在 2026-09-28 亲自读到；mtime/sha256 为我现场计算）。
