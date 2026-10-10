# round2-C（设计审查·终审）：裁决 + 交付物规格

> 审查者：design-reviewer。写域：本文件。输入：`round2-A.md`（正方 v1）、`round2-B.md`（反方复核）、
> `datapack.md`（Lead D1–D11）、`round1-C.md`（我自己那轮）。
> **本文件所有"复算了"都是我 2026-10-11 07:10–07:35（本地）自己跑出来的**；方法写在每处；
> 没跑过的写「未复算」。我只写了本文件（探针脚本落在 `.tmp/ab-plan/r2-verify*.py`，可复跑）。
> **账本仍在长**：我这轮快照 5,584 → 5,686 条（约 25 分钟 +102 条）。下面所有计数都带"我读的那一刻"。

---

## 0 六处裁决一览

| # | 分歧 | 裁决 | 我复算了吗 |
| --- | --- | --- | --- |
| 1 | `executed` 的语义与可用性 | **两边都对一半**：B 的分布对，A 的"不能当判据"对；**真正的判据是"哪条支路"**，见 §1 | **复算了**（账本 5,686 条）+ 读了 `hooks.py:1787–1802 / 1994–2012 / 1602–1627` 的代码路径 |
| 2 | `pwsh` 形状是否可知 | **A 对**（不可知，且不是"随会话变"而是"每个会话都至少 2 种"）；D8 的 143 **是单位混用** | **复算了**（9 个会话逐个解压计数）+ 全机 13 种格 |
| 3 | `session_id` 是否可靠 | **B 对**（两种文本形状确实存在、且**不是前缀问题**）；D1 的"15"口径来自 86 条无 session_id 记录 | **复算了**（5,686 条：14 个值，8 带前缀 + 6 裸 uuid，action_id 前缀 100% 相等） |
| 4 | D8 是否双计 | **D8 不是双计，是单位混用**；B 的"修数"方向对，但他给的 72 也不是我数到的 74 | **复算了**（9 个会话 dispatch-start vs dispatch 差 ≤1） |
| 5 | wiring 判据 | **A 对**（不能用 wiring=wired），**B 的补强也对**（留痕 ≠ 在范围内，这是两件事） | **复算了**（重跑 `wiring --json`，落盘 `.tmp/ab-plan/wiring.json`） |
| 6 | R4b 是否拆级 | **A 对（拆）**，但必须**带上 B 的"归因不可分"限定**；两级回答的是两个不同问题 | **复算了**（两个账本里 `repair_required`/`post_check_failed`/`inconsistent` 全 0 命中） |

六处里，**三处（1、2、4）的读数都在说明同一件事**：这份材料里反复出现的争议，多数不是"谁记错了"，
而是**同一个逻辑动作在平台里有 2–6 条记录、在会话里有 2 条部件**，而每一方都在用自己那个单位说话。
**单位必须在预注册里逐源写死**——这是 v1 最重要的一条修正，比任何单点裁决都重要。

---

## 1 裁决一：`executed` 的语义与可用性（复算）

**复算方法与结果**（脚本 `r2-verify8.py`；账本 5,686 条，按 `reason_code` 统计字段存在性）：

| reason_code | n | executed=true | 有 decision | 有 grant_id | 有 pre_evidence | 有 violations |
| --- | --- | --- | --- | --- | --- | --- |
| `enforcement_allow` | 56 | **0** | 7 | **56** | 7 | 7 |
| `allow` | 3 | **3** | 3 | 0 | 3 | 3 |
| `allow_with_warnings` | 4 | **4** | 4 | 0 | 4 | 4 |
| `policy_block` | 7 | 0 | 7 | 0 | 7 | 7 |
| `not_governed` | 68 | 0 | 0 | 0 | 0 | 0 |
| `allow_delegated` | 49 | 0 | 0 | 0 | 0 | 0 |
| `post_validated` / `post_error` | 7 / 7 | 0 / 0 | 0 | 0 | 0 | 0 |
| PostToolUse 全部 | 2,750 | **0** | 0 | 0 | 0 | 0 |

**关键新读数（A 与 B 都没写）**：同一个 `action_id` 在一次被允许的 `edit` 上**有 2 条 PreToolUse 判定记录**，
一条是**发凭据的**（`enforcement_allow`，`executed=false`，**带 `grant_id`**），一条是**钩子自己执行的**
（`allow`/`allow_with_warnings`，`executed=true`，带 `execution` 子对象）。
我逐条列出这条路：`PreToolUse enforcement_allow executed=false` + `PreToolUse allow executed=true` + `PostToolUse post_validated executed=false`。

**代码路径（我读了，这是"语义"而不是"分布"的证据）**：`src/adapters/dsh/hooks.py`
- 1602–1627：不在规则引擎准入面的工具，先看是不是执行类（`ToolKind.EXECUTE`）或写类 → 走 `_decide_via_enforcement`；
- 1994–2012：该路径放行时写一条**带 `grant_id`** 的记录，`reason_code="enforcement_allow"`，**不设 `executed`**（`HookOutcome` 默认，落盘为 `false`）；
- 1787–1802：只有**走规则引擎**的写类动作才会 `execution = self.executor.execute(event)` → `executed = status in {executed, delegated}`。

⇒ **`executed=true` 的含义是"平台的进程内驱动真的执行了这个动作"，不是"这个工具跑了"。**
委派族（`exec.pwsh` / `exec.run_code`：`risk=privileged_execution`，由 Agent 运行时执行）**结构上永远拿不到 true**。

**裁决**：B 的分布对（7 条 true 全在 `allow`/`allow_with_warnings`）；**A 的结论对且更彻底**——
不是"pwsh 走哪条路未知"，而是**两条路的代码分叉是确定的**：`exec.pwsh` 是 `privileged_execution`、
注册表 `driver: shell_command`（受治注册表实测），它**必然**落在 1602–1617 那条委派支路。
⇒ **L2 写 `executed=true` 预注册是结构性不可能**，不是"说不定"。
**正确判据**：该动作要么有 "`grant_id` 且 `executed=false`"（发凭据），要么有 "`executed=true`"（进程内执行）
——**两者都是"平台放行了它"的正面证据**；两者都没有才是没放行。

---

## 2 裁决二：`pwsh` 形状是否可知（复算）

**复算方法**（`r2-verify3.py` / `r2-verify4.py`）：解 9 个含 pwsh 的会话记录，按
`type=tool/ptc-dispatch-start ∧ data.name=="pwsh"` 每个调用数一次，形状 = `data.arguments` 的键集合排序。

| 会话 | pwsh 调用数（dispatch-start 单位） | 形状分布 |
| --- | --- | --- |
| `4bb24e4e`（Memory，D8 的那个） | **74** | 四格 61 / 三格(`workdir`) 12 / 四格+`run_in_background` 1 |
| `5831341c`（Memory） | 26 | 四格 18 / 三格 8 |
| `27988844`（Memory） | 30 | 三格 23 / 两格 7 |
| `b51c64fc`（Memory） | 3 | 两格 2 / `command+description+timeoutMs` 1 |
| `3f255054`（受治 AB 会话） | **0** | —— |
| `545133ba`（自由 AB 会话） | **0** | —— |

**全机口径（51 个会话、30433 个 dispatch 部件、13 种格）**：四格 8430 / `cmd+desc+timeoutMs` 7620 /
**两格 6854** / 三格(`workdir`) 6511 / `+run_in_background` 若干 / 另有 `justification+sandbox_permissions` 一族。

**裁决**：
1. **A 对**：单一签名不可能覆盖。而且比 A 说的更强——不是"模态随会话变"，
   是**每个会话都至少出现 2 种格**（上表 4/4 会话如此），所以"取本会话最常见的格"这个折中也不成立。
2. **B 的 72 与我的 74 不一致**，差 2 条。我按 `dispatch-start` 数是 74；B 写的 72 我**无法复现**
   （他的口径未写全，可能多过滤了一层）。**这条以我的 74 为准，但它是次要的**——它不影响任何结论。
3. **D8 的 143 = 74 个调用 × 2 个部件**（`dispatch-start` 与 `dispatch` 在 9 个会话里差 ≤1，我逐会话核过）。
   所以不是"双计错误"，是**单位没写死**：143 是"部件数"，74 是"调用数"。D8 的**结论**（形状会变）成立，
   **数字**要除以 2。
4. **一个后果**：L1 试灯取到的形状**不能预报 L2 的形状**（4/4 会话内部就在变）。
   ⇒ 我支持 B 的处置：**L1 只产生一张"形状—签名对照表"，L2 仍然允许在级内再拒一次**；
   v1 现在写的"照抄重签后同一条命令变成放行族"在同一级内**可能重复发生**，必须写清**最多允许几次**（建议 ≤3）。

---

## 3 裁决三：`session_id` 是否可靠（复算）

**复算方法与结果**（`r2-verify1.py`，账本 5,686 条）：
- 有 `session_id` 的记录 **5,498** 条（其余 86 条是摘要链条目，见裁决四）；
- **distinct = 14**：**8 个带 `session-` 前缀** + **6 个裸 uuid**；
- **`action_id` 前缀与 `session_id` 字段逐条相等：5,498 / 5,498**（不需要补前缀、不需要归一化）。

**裁决**：**B 对**——两种文本形状确实存在。但 B 的解释需要一个限定：
这**不是"读取器要处理两种形状"**，而是**"读取器不得对 `session_id` 做字符串构造"**。
我实测 `action_id.startswith(session_id)` 在两种形状下**都是精确的**；会出问题的是
"自己拼 `'session-' + sid`"或"取 `sid.strip('session-')`"这类写法。
⇒ 正确写法一句话：**`session_id` 取字段原值、只做前缀比较、不做任何拼接或裁剪**。

**D1 的"15"与 B 的"14"**：口径差就是那 86 条没有 `session_id` 的记录——D1 若把它当成一个取值就会数出 15。
**两个都对，必须写明分母**（"14 个非空取值 + 86 条无值记录"）。

**对 v1 的直接影响**：我自己的会话（正在写这个账本的）**就是裸 uuid 形状**。
⇒ **读取器必须在 R0 就对两种形状各跑一次并报计数**，否则新会话的记录会被静默丢掉。

---

## 4 裁决四：86 条无 `session_id` 是否双计（复算）

**复算方法与结果**（`r2-verify5.py`）：
- 86 条 = `pre_decision` 65 + `post_evidence` 14 + `final_decision` 7；`tool_id` = `exec.run_code` 58 / `fs.edit` 27 / `fs.write` 1；
- 它们对应 **72 个不同 `action_id`**，**其中 14 个同时也是 hook 侧带 decision 的 `action_id`**；
- 同一动作的链侧记录数 = 3（`pre_decision` + `post_evidence` + `final_decision`）。

**裁决**：**不是"同一条记录出现两次"，是"同一个动作在两个源里各有一套记录"**。
- 按**记录**数：不双计（86 vs 5,498 是不同记录）；
- 按**动作**数：**会双计**——若对账表"一个动作一行"，链侧的 3 条必须折叠成 1 行，否则 7 个动作用 86 条记录报出。
⇒ v1 的"对账单位 = `callId:ptc:N`"是对的，但必须**再加一句**：
**链侧（无 `session_id`）先按 `action_id` 折叠成每动作一行，再与 hook 侧那一行对齐**；两组都报计数。

---

## 5 裁决五：wiring 判据（复算）

**复算方法与结果**（重跑 `python -m adapters.cli wiring --json`，落盘 `.tmp/ab-plan/wiring.json`，exit 0）：

| channel | wiring_status | status | wired | freshness | audit_records |
| --- | --- | --- | --- | --- | --- |
| `dsh:desktop` | wired | `audit_never_written` | **false** | never_written | **0** |
| `dsh:governed` | wired | `stale` | false | stale | 168 |
| `dsh:governed-grade` | wired | `stale` | false | stale | 11 |
| `dsh:governed-grade-approval` | wired | `stale` | false | stale | 49 |
| `dsh:governed-wmsvc` | wired | `stale` | false | stale | 128 |
| `dsh:headless` / `dsh:web` | not_wired | `not_wired` | false | unevaluated | 0 |

**裁决**：**A 对**（`wiring = wired` 不能当 R0 完成判据）。补两条只在我这里出现的限定：
1. 报告里**每一个 channel 的 `audit_path` 都是 `<external>/audit.jsonl`**（脱敏后的同一个串）。
   所以"它解析出的目标与真实受治账本不是同一个文件"这句话，**在报告文本上不可复核**
   （只能从 `audit_records=0` 与"该文件不存在"推出）。**引用时必须写成"报告说它读的那个文件不存在/为空"**，
   不要写成"它指向了另一个文件"（那是未核实的机制推断）。
2. **B 的补强成立且必须进 v1**：留痕 ≠ 在范围内。我的实测支持它——
   我自己这个会话（cwd 在 Memory）**每一分钟都在往受治账本写记录**，但全是 `session_out_of_scope`。
   ⇒ R0 的判据必须是**两条**：①该 `session_id` 在 `Governance/.policy/audit.jsonl` 里有新增记录；
   ②这些记录的 `reason_code` **不属于** out-of-scope 族（即 `governed` 为真或 `not_governed`）。
   **wiring 报告降级为观测值，不进判据。**

---

## 6 裁决六：R4b 是否拆级（复算）

**复算方法与结果**：两个账本里 `repair_required` / `post_check_failed` / `inconsistent` **全 0 命中**；
`command_composition_blocked` / `command_not_allowlisted` / `tool_not_registered` / `approval_required` **全 0 命中**；
`code_parse_failed` 3 条、`param_unknown` 1 条、`approval_invalid` 6 条（后者全在 `run_code` 上）。

**裁决**：**A 对（拆）**，但要**把 B 的限定原样附上**，两点缺一不可：
- R4b-1（写坏）：这一级**只能**得出"**阻断成立，失败关闭与规则违规不可分**"（账本上两种理由同形，
  `violations` 里会同时出现 `TESTING-001` 与解析失败）——**B10 的限定照抄进判据**；
- R4b-2（写回对的）：**只有它能回答 5.68 的死锁问题**（拦了之后还能不能改对）。
  **这一级今天没有先例、也没有任何账本读数**（`repair_required` 0 命中）⇒ 它的判据只能写"预期观测"，
  不许写"期望值**必须**是 allow"——那正是 v1 在 L2 犯过的错。

---

## 7 v1 终审：可执行吗？可复核吗？逐级结论

**总评**：v1 的**结构与纪律是可用**的（三态判决、三键切分、每级必填工具名+条数、不覆盖段、
把"摩擦"与"治理结论"分开）——这比 v0 强一个量级。**但它有一类系统性缺陷**：
**把"没有先例的读数"写成了"期望值"**（L2 的 `executed=true`、L1 的"照抄重签即放行"、
L4 的两个命令类 reason_code）。这类预注册**跑一次就会红，而红的是预注册自己**。

**逐级"第三方拿到账本 + 两侧树能不能重算出同一个结论"**：

| 级 | 能不能重算 | 卡在哪 |
| --- | --- | --- |
| R0 | **能** | 树摘要、审批文件逐格、读取器变异证明都可复算。前提是 `approval.json` 以**文件**为准（preview 只是想要的形状） |
| L0 | **能** | 范围（`reason_code` 族）+ 控制级（`decision=block`、`violations[].rule_id`）+ 树哈希；三条都在账本/树上 |
| L1 | **部分** | "pwsh 记录存在"能；"照抄重签后放行"要**重签后的审批文件**才能复核 ⇒ 必须把重签前/后的 `approval.json` 两份都留档 |
| L2 | **不能** | ① 判据 `executed=true` **结构性不成立**（§1）；② "两侧 pytest 输出归一化后相等"——自由侧输出**只在会话里**，账本与树上都没有 ⇒ 必须把两侧原文各留一份哈希与归一化后的文本 |
| L3 | **能** | `decision` + `pre_evidence.served_checkers` + 文件哈希，账本里全有（实测 `served_checkers` 确实出现在 `pre_evidence` 子对象里） |
| L4a | **能**（限"阻断成立"） | 归因不可分，只能写到 §6 那一句 |
| L4b / L4c | **不能（今天）** | 两个 `reason_code` 本机 **0 先例**；跑完才可知，且必须**逐字记下实际拿到的码**而不是比对预注册的码 |
| D（对账表） | **能**，条件是 §4 的折叠规则 + §3 的读取器写法 | —— |

### 必须修的最后六条（每条一句）

1. **判据一律写"哪条支路、哪条记录"**：凡 `executed`，必须写清是"发凭据那条（`grant_id` 且 `executed=false`）"
   还是"进程内执行那条（`executed=true`）"——`exec.pwsh` **只能**是前者（§1，代码路径已证）。
2. **凡本机 0 先例的键，只能写"预期观测"，不能写"判据"**：`executed=true`（对 pwsh）、
   `kind=execution ∧ tool_id=exec.pwsh`、`command_composition_blocked`、`command_not_allowlisted`、
   `repair_required`、`tool_not_registered`——读到就记，读不到写 `unavailable`（不写 0、不写 false）。
3. **每个计数写死"单位 + 来源 + 时刻"**：pwsh 调用数用 `dispatch-start`（D8 的 143 是部件数，调用数是 74）；
   audit 一次放行动作是**两条** PreToolUse（发凭据 + 执行）；链侧一动作是**三条**记录（折叠成一行）。
4. **L1 从"级"降为"前置摩擦项"，且允许级内拒 ≤3 次**：它产出的是**形状—签名对照表**，
   进合集的是**那张表**，不是"一次放行"这个结论；L1 的失败**不得**计入治理发现。
5. **`session_id` 读取器规则写死**：取字段原值、只做前缀比较、**不做任何拼接/裁剪**；
   R0 对"带前缀/裸 uuid"两种形状各跑一次并报计数（我自己的会话就是裸 uuid，见 §3）。
6. **R0 的接线判据改成两条**（留痕新增 **且** `reason_code` 不在 out-of-scope 族），wiring 报告只作观测（§5）。

---

## 8 交付物规格

### 8.1 放哪、谁读

| 产物 | 落点 | 谁读 | 为什么是这里 |
| --- | --- | --- | --- |
| **方法（长期）** | `docs/project/engineering-policy-platform/testing/ab/gui-ladder.md`（**进仓库**，与 30 臂线同目录、同体裁） | 三个月后要重跑合集的人 / 下次改平台的维护者 | 与 `ab-protocol.md` 同源，能被 `04-open-work.md` 的复审日历引用 |
| **读数（一次性）** | `C:/Users/ZNM/Downloads/Comparison-test/comparison-runs/<ISO 日期>-<run_id>/` | 同上 + 复算者 | **不进 `.policy/`**（那是平台自己的账）、**不进两侧树**（读数自己会被治理、且破坏树相等）、**不进 `.tmp/`**（`tools/cleanup.py` 会删，是 5.32 已登记的错） |
| **临时脚本** | `.tmp/ab-plan/` | 只有本研讨 | 会被清，不进任何结论 |

### 8.2 包含哪几张表（四张，缺一张就不算交付）

1. **预注册表**（每级一行，跑之前写死）：`级 / 发什么（原文）/ [AB-Rx] 标记 / 必须出现的工具名 / 记录条数 /
   期望 decision / 期望 reason_code / 期望 violation 规则 ID / 期望树变化 / 读数的三源归属 / Memory HEAD / 账本起始偏移`。
2. **判据表**：`期望 → 来源 ∈ {audit, ledger, session, tree} → 具体键路径 → 取哪一条记录（支路）`。
   **没有这一列就不许写成判据**——v1 的 L2 缺陷正是缺这一列。
3. **三态判决表**：`符合预注册 / 新问题（带复现）/ 跑不成（带复现 + 触发条件编号）`。
   **"跑不成"不占绿红**；`实际` 允许取 `unavailable`（不是 0、不是空）。
4. **不覆盖表**：统计效力（n=1、非随机、无盲法）/ 反事实精确率 / 门禁 vs 反馈分解 / 只读工具与
   `run_code` 内的旁路 / MCP 一族 / 后台命令 / 编排层 / 多 Agent / **本机 exit 编码与契约不一致**。

**另加一张（不算交付物，但合集必须有）**：**参数形状对照表**（从账本实测：本次会话 pwsh 用了几种格），
它是"下次重跑合集时先比对形状是否变了"的输入。

### 8.3 怎么防过期（三把锁）

- **锁 1 · Memory HEAD**：`rules` 与 `pre_evidence.registry_root` 指向本仓库（`dsh-adapter.yaml` 实测），
  所以**判定行为随本仓库变**。每次读数记 `git rev-parse HEAD` + 账本 `rule_set_hash`。
  HEAD 变了 ⇒ **整套重跑**。
- **锁 2 · 账本偏移**：记"`audit.jsonl` 起始条数 + 结束条数 + 读的时刻"。账本 append-only 且**跨会话共享**
  （我自己 25 分钟就写了 102 条），所以**只允许按 `session_id` 切片**，时间窗只作粗过滤；
  偏移变了但 session 切片不变时，结论**仍然有效**（这正是"切片而不是对齐"的意义）。
- **锁 3 · schema 版本**：`audit_schema_version`（实测 **1.3**）、`ledger_schema_version`（**1.0**）、
  `approval.json.schema_version`（现 **1.1**，重签后应 **1.2**）、`policy.models` 的决策协议世代。
  任一升版 ⇒ 判据表要**重新审一遍键路径**（不是重跑就行——键可能改名，AGENTS 第 55 条）。
- **到期日**：合集头部写"审批 24h/7d 有效 + `.tmp/` 会被清 + 本计划只给存在性读数"，
  并给一个**复核日期**（建议挂 `04-open-work.md` 的 2026-12-31 复审日历，或更早）。

---

## 9 「合集」的验收条件（可判定门槛）

**说"这一套可以重复跑"必须同时满足 A1–A5**：

- **A1 前置自检四项全过**：① R0 两条接线判据（留痕新增 + 非 out-of-scope）；② `approval.json` 在有效期内
  且逐格覆盖（以**文件**为准）；③ `tree_digest(G) == tree_digest(F)` 且**两侧都不含** `src/shop/order_audit.py`；
  ④ `Memory HEAD` + `rule_set_hash` + 账本起始偏移**已记**。
  任一不过 ⇒ 整份合集输出 **`跑不成`**，**显式拒绝给"通过"**。
- **A2 每一条预注册条目都落到三态之一**，且 `跑不成` **必带**：触发条件编号（①会话全 out-of-scope /
  ②要求的工具一次都没出现 / ③判据要求的键在账本里缺失）+ 复现命令。
- **A3 对账表里 `符合` 的条目覆盖至少 4 类判据**：树变化 / `decision` / `reason_code` / 文件哈希。
  只有一类算"绿"的合集不算通过（那是把一次巧合当复现能力）。
- **A4 没有 `新问题` 未处置**：出现即写"`改平台` / `改计划` / `只登记`"三选一 + 结论落点。
- **A5 数字可复算**：另一个会话只拿"账本 + 两侧树 + 本文件"，按 §8.2 的判据表能重算出**同样的三态取值**。

**"跑不成"怎么算（这是最容易含糊的一条）**：
- `跑不成` **不占绿、也不占红**，但**必须有配额**：合集里 `跑不成` 的条目数 **> 总条目数的 1/3 ⇒ 整套判`跑不成`**
  （理由：那时你验的是平台缺口，不是治理效果）。
- 逐条判定：**环境/构造问题**（桥没装、审批过期、树不等、zstd 解不开、模型没调那个工具）⇒ `跑不成`；
  **平台在预期之外拒绝**（例如命令类动作没走到白名单就 `approval_invalid`）⇒ **也记 `跑不成`**，
  但要在旁边单列"**摩擦**"，**不计入治理发现**（brief §8 已把它列为已知失败模式）。
- 一条硬规则：**`跑不成` 的条目不得用来支持任何结论**（既不能说"治理有效"，也不能说"治理失效"）。

**"可重复跑"与"跑得过"是两件事**：A1–A5 全过只说明**这套仪器能重复**；
治理效果的任何判断都超出本计划（见 §8.2 不覆盖表第 1 条）。

---

## 10 如果现在就开始执行，最可能翻车的五处

1. **条子先过期**：现网 `approval.json` 是 **1.1 单记录**、`expires_at = 2026-10-11T03:26:37Z`
   （本地 **11:26**）——**今天上午就到**。不先重签，L0 的第一个动作就是 `approval_invalid`，
   而整级会被读成"无读数"。
2. **L2 的预注册会自己红**：只要判据还写 `executed=true`，而 `exec.pwsh` 走的是**发凭据支路**
   （`grant_id` + `executed=false`，§1 代码路径已证），**一次成功的 L2 会被判成"不符合预注册"**。
3. **L1 的形状接力会空转**：4/4 会话内部就有 2–3 种格（§2）。L1 取到的形状**预报不了** L2 的；
   若 L2 只允许重签一次，就会把"审批摩擦"记成"跑不成"甚至"新问题"。
4. **读取器丢掉新会话**：新会话是**裸 uuid** 形状（我自己就是，§3）。任何"拼 `session-` 前缀"
   或"取 `session-` 开头"的写法会**静默**把本次记录全部丢掉，然后你看到的是"一条记录都没有"。
5. **把链侧记录算成两倍**：86 条摘要链条目与 hook 侧 21 条判定记录覆盖**同一批 14 个动作**（§4）。
   不先按 `action_id` 折叠，"这次有 86 条判定"会直接进结论。
