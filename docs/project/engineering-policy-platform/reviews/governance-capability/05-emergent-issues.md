# 实测显现的新问题（N16–N24）

> 来源：**治理能力实测轮**（2026-09-26）。这一轮把治理真正接上线，开子会话在治理下做了一个跨 6 文件的
> 开发任务，并用五种写法的违规探针 + 反向对照 + 独立验收去压它。
>
> 编制口径：本篇只记**实测出来的、上一轮 N1–N15 里没有的**问题。
> N1–N15 的登记表在 [00-remediation-plan.md §5](../governance-remediation/00-remediation-plan.md)，
> 本篇续号 N16 起；那张表的每一行都已补上指向本篇的指针。
>
> 每条按同一套四段式写：**会遇到什么场景 → 细节（坐标与机制）→ 证据与复现 → 处置建议与为什么不在本轮修**。
> 凡是只能靠读源码推断、没有实测支撑的，单独标 **UNPROVEN**，不写成事实。
>
> 配套：[00 能力报告](00-capability-report.md) · [01 规则覆盖矩阵](01-rule-coverage-matrix.md) ·
> [02 真实受治理会话](02-governed-runs.md) · [03 验证器路径与执行链](03-validator-and-execution-paths.md) ·
> [04 独立验收](04-independent-verification.md)
>
> **后续轮次（同日修复轮）：本文登记的 9 项全部处置完毕——6 项缺陷已修、1 项换形态、2 项按原建议写清，
> 见 [§6](#6-修复轮处置2026-09-26)。**
> 本文其余内容是对**当时那份实测**的忠实记录，除三处**事实性更正**（见 §2.2 与 01/03 的更正块）外不改写。

## 0. 一句话

这轮新显现的问题分四类：**一个阻断级产品缺陷**（N16：受治理会话里命令输出回不到模型）、
**一个验证器层的判定真伪缺口**（N17：语法错误文件上 39 条规则是空判定）、
**两个会让人得出错误结论的口径缺口**（N18：`exit 2` 契约在本机走不到；N20：`wired` 是联合属性）、
以及**一组读数与实验方法上的陷阱**（N19 / N21 / N22 / N23 / N24）。
其中 N16、N17 需要动产品代码，**都不在本轮修**——本轮全部改动对"当前树"的验收要成立，
半验证状态下改产品代码就是再造一台假绿仪器。

## 1. 总览

| 编号 | 一句话 | 类别 | 会不会改变已有结论 | 严重度 | 建议 |
| --- | --- | --- | --- | --- | --- |
| **N16** | 委派执行路径上 `exit_code_zero` **不可能通过** → 命令真的跑了，输出回不到模型 | **产品缺陷** | **会**：G4 的"审批修好了"不等于"能跑测试" | **阻断** | 单开一轮修 + 配会失败的检查 |
| **N17** | 语法错误文件上 39 条 `style_lint` 是**空判定** | **产品缺陷（口径）** | 会：G3"跳过≠通过"的下沉形态 | 重要 | 单开一轮修 |
| **N18** | `exit 2` 分支在本机**从未命中**，实际生效的是"其余非 0 → 失败关闭"兜底 | 契约与实现不一致 | 不会（两条分支都是拒绝） | 重要 | 先定位，再决定改契约还是改实现 |
| **N19** | 「拦住」与「没人尝试」在哈希上**长得一样** | **方法学缺口** | 会：影响所有"治理拦住了"的结论 | 重要 | 已在本轮落成判据（见 §2.4） |
| **N20** | `wired` 是"接线 + 审计新鲜度"的**联合**属性 | 口径缺口 | 会：不能拿一次 WIRED 当长期证据 | 重要 | 拆成两个字段 |
| **N21** | 台账文件名在运行期被**改写**，按配置名去数会得 0 条 | 读数陷阱 | 会：误判"事后核对没跑" | 次要 | 写进文档或让配置生效 |
| **N22** | 只读工具的范围阻断**打断探索** | 设计取舍的代价 | 不会（方向正确） | 次要 | 可选改善拒绝理由 |
| **N23** | 受治理会话里 `bash` / `run_code` **根本发不出来** | 装配事实 | 会：那两条结论只覆盖 Hook 层 | 次要 | 写清适用范围 |
| **N24** | `binding=action` 在会话里**永远过不去**；一个 `approval.json` 只放一条记录 | 设计取舍的边界 | 不会（方向正确） | 次要 | 写清边界 |

## 2. 逐条

### 2.1 N16 · 委派执行路径上 `exit_code_zero` 不可能通过（阻断级）

**会遇到什么场景。** 受治理会话里，模型想跑 `python -m pytest -q` 验证自己刚写的代码。
审批过了、命令也真的执行了——但**模型拿不到 stdout**：它收到的是被替换掉的策略错误。
于是它只能反复重试或放弃。会话外复跑同一批测试是 **9 passed**，会话内却"看不见"。

**细节（机制链，四步）。**

1. 注册表给执行类工具声明了事后核对：`registry/tool-registry.yaml` 的 `exec.pwsh` / `exec.bash`
   都是 `post_checks: [exit_code_zero]`，`driver: shell_command`，`approval: required`。
2. 事后核对要求拿到退出码：`src/enforcement/postcheck.py:420-430` ——
   `process` 为空判 False（"没有进程证据"），`process.exit_code is None` 判 False
   （"**命令没有退出码：结果不可判定**"），只有 `== 0` 才 True。
3. 但这条路径上执行是**委派**给 Agent 运行时的，平台不自己跑命令：
   `src/adapters/dsh/enforcement.py:309-325` 从 PostToolUse 事件重建 `ExecutionRecord` 时
   **只填了 `status=DELEGATED`、`reason_code=ALLOW`、`structured_digest` 与两处 `detail`**，
   **没有传 `exit_code`**。而模型里这个字段是存在的、默认 `None`
   （`src/enforcement/models.py:1150`）——所以它不会报错，只会静默地为空。
4. 于是：`exit_code_zero` 必然判 False → `repair_required` → Hook 失败关闭 →
   dsh 用策略错误替换工具输出（`src/enforcement/postcheck.py:306` 把
   `file_syntax / exit_code_zero / target_exists` 三类失败归入同一处置）。

**影响面。** 注册表里**所有**声明 `post_checks: [exit_code_zero]` 的工具，在"由 Agent 运行时执行"
这条委派路径上**永远到不了 `validated`**。这不是某一台机器的环境问题，是路径本身的性质。

**证据与复现。**

| 证据 | 位置 |
| --- | --- |
| 三处独立实测（真 ruff/真 pytest 的验证器流水线）+ `__pycache__` 字节码 mtime 反证"pytest 真的跑了" | [03 §2.5 / §2.6](03-validator-and-execution-paths.md) |
| 代码级复核（只做代码级，未独立复现 PostToolUse 行为） | [04 附录 B](04-independent-verification.md) |
| 真实会话里的旁证：d1 的 `pwsh` 被 `approval_required` / `command_composition_blocked` 拦；d2 同 | [02 §4.1 / §4.2](02-governed-runs.md) |

    # 脱离会话单独复现（T3）：pre 阶段 exit=0、post 阶段 exit=2，输出被替换
    python .tmp/governance-capability/grading/run_post_check_probe.py
    # 完整清单见 03 号文档 §4「复现命令清单」

    # Hook 自己退出码确为 2（T2 的独立复现）
    Get-ChildItem -Recurse .tmp/governance-capability/runs/t2-exitprobe

**处置建议（不在本轮修）。** 把 PostToolUse 载荷里已知的退出码接进 `ExecutionRecord.exit_code`，
并补一条**会失败的检查**：任一声明 `exit_code_zero` 的执行类工具，其事后证据必须能在真实桥接下取到退出码
（而不是在单测里手工构造一个带退出码的 record —— 那正是这个缺陷能活下来的原因）。
**为什么不在本轮修**：它要动 `src/`，而本轮所有"对当前树"的验收（11 次会话、独立验收的两轮）都建立在这棵树上；
在半验证状态下改产品代码，等于让那些证据失去所指。**单开一轮**，按本仓库既有口径配失败的检查。

### 2.2 N17 · 语法错误文件上，39 条 `style_lint` 是空判定

**会遇到什么场景。** 一个含语法错误的 `.py` 文件进了验证器流水线。账本上，39 条 `style_lint`
被记成"已判定 / 未发现"——看起来"查过了，没问题"。实际上 ruff 只报了一条**无归属**的诊断。

**细节。** 本机 ruff 0.14.13 对语法错误报的是 `{"code": "invalid-syntax"}`，
它**不对应任何声明的规则码**（更早的 ruff 版本写作 `E999`），
于是只能进 `unmapped_findings=1`。而按 checker 归属统计时，那 39 条 `style_lint` 仍然被算作"跑过了"。

> **2026-09-26 更正（修复轮）**：本条初版写过"`validation/ruff.toml` 的注释仍按旧口径写 `E999`"——
> **那句话是错的**。修复轮对 `validation/` 整个目录逐字检索：不含 `E999`，连 `999` 字样都没有。
> 全仓 `E999` 只出现在 `docs/` 里（本文、01、03 三处），也就是三份文档互相引用了同一个未核实的说法。
**整份文件确实仍然 `block`**——但拦住它的是 `py.ast` 的失败关闭（"解析失败不等于没有依赖"），
**不是** ruff。

**为什么它重要。** 这是 G3 那条"跳过 ≠ 通过"的**同构形态、下沉一层**：
G3 说的是"没查的被记成跳过"，这里说的是"**没查成的被记成查过了**"。
两者都让账本上的"判定过"与"真的查过"不可区分。

**证据。** [03 §1.6](03-validator-and-execution-paths.md)；ruff 版本与码归属的双向一致性由
[01 §5](01-rule-coverage-matrix.md) 的交叉复核钉住。

**处置建议（不在本轮修）。** 把"因无归属诊断而空转的 checker"变成**显式状态**
（例如在证据里写 `checker_scope_note` 或 `evidence_insufficient`），而不是让它长得像"已判定"。
~~同时把 `validation/ruff.toml` 注释里的 `E999` 按当前 ruff 版本更新。~~
**（2026-09-26 更正：`validation/` 里没有 `E999`，这一条建议本来就无从执行。见上文更正块。）**

### 2.3 N18 · `exit 2` 契约在 dsh 侧走不到（机制 UNPROVEN）

**会遇到什么场景。** 插件 `src/adapters/dsh/policy-hook.plugin.mjs` 的第一个分支是
`if (exitCode === 2) { return { allowed: false, reason: stderr } }`。
按 `src/adapters/dsh/README.md` §2.3 的退出码语义表，`2` 就是"阻断"。

**细节与证据（三步，两个入口）。**

1. **Hook 自己确实退出 2**：离线直调 Hook，违规 edit 得到退出码 2（Lead 的确定性矩阵里也有 5 例
   `exit_code=2`；T2 的 `runs/t2-exitprobe` 独立复现）。
2. **但 dsh 侧读到的是 1**：把插件指向一个"必然 exit 2"的命令，模型收到的拒绝原文是
   "**Hook 退出码 1，未知状态按失败关闭拒绝**"（[04 §5.4](04-independent-verification.md)）。
3. **Lead 用不同入口独立复核**：`python -c "import sys; sys.exit(2)"`、`sys.exit(3)`、`cmd /c exit 2`
   经 dsh 侧三次都报 `exitCode = 1`。

**结论与边界。** 安全性**不变**（两条分支都是拒绝，真正生效的是插件自己的
"其余非 0 → 失败关闭"兜底——这恰好印证了 G12 的判断：失败关闭的兜底只存在于自建插件里）。
但两件事要写下来：(a) 面向模型的原因码是"未知状态"而不是"策略阻断"，可诊断性打折；
(b) README §2.3 那张表里 `2` 这一行**在本机缺少实测支持**。
**机制未定位**（是 dsh shell 层归一化，还是插件读错了字段），标 **UNPROVEN，不猜**。

**处置建议。** 先定位归一化发生在哪一层；定位不到就在 README 的退出码表下加一句实测注记
（本轮已在 [src/adapters/dsh/README.md §2.3](../../../../../src/adapters/dsh/README.md) 加了这一句），
并在契约测试里把"非 0 非 2 也拒绝"钉死——那是本机真正在生效的那条路径。

### 2.4 N19 · 「拦住」与「没人尝试」在哈希上长得一样（方法学缺口）

**会遇到什么场景。** 第一次跑 v1 违规探针：模型读了自动注入的 `AGENTS.md` / `README.md`
（审计里那条 `context_injection` 就是它），**自己判定**"入口层不得直接依赖仓储层"，
于是**拒绝执行 edit**。结果：文件哈希没变、审计里**没有任何 `policy_block`**。
如果不区分这两件事，就会把"没人尝试"误报成"拦住了"。

**细节。** 只有哈希这一个观察量时，两种情形**完全同形**：

| 情形 | 目标文件哈希 | 审计里的写类判定记录 |
| --- | --- | --- |
| 真被治理拦住 | 未变 | 有：`decision=block` / `reason_code=policy_block` |
| 模型自审拒绝 | 未变 | **没有**（最多一条 `context_injection`） |

它与本仓库一直在治的"跳过 ≠ 通过"同构：**"没拦到" ≠ "拦住了"**。

**已落地的判据（本轮）。**

1. 受治理臂：审计里必须有该 action 的 `governed=true` 且带 `decision` 的记录；
2. 未治理臂：必须看到**目标文件真的变了**（否则"零留痕"没有对照物）；
3. 只写"文件哈希没变"**不构成结论**。

T2 据此给每个 label 加了 `verdict` / `attempted_write` 字段；V1 把每臂的"真的尝试过"分成三级
（A = 审计里有带判定字段的事前记录；B = 目标文件真的变了；C = 只有模型自述），
并把两条弱证据臂（坏 Hook、退出码保真——它们审计必然是 0 条）如实标成 C。

**证据。** 反面样本按原样保留：`.tmp/governance-capability/logs/v1-selfrefuse.log`；
[02 §4.5](02-governed-runs.md)；[04 §3.5](04-independent-verification.md)。

### 2.5 N20 · `wired` 是"接线 + 审计新鲜度"的联合属性

**会遇到什么场景。** 你看到 `python -m adapters.cli wiring --check` 报 `dsh:governed [WIRED]`，
于是认为"治理已开启"。

**细节。** 实测反例：**同一份逐字节相同的 patch**（sha256 `7dc33106…` 前后一致、全程未改动），
20:15:23 报 `audit_never_written`（总判定 fail、退出码 1），20:18:03 报 **WIRED**——
中间唯一的差别是一次真实会话把 `.policy/audit.jsonl` 从"不存在"变成"有记录"。
判据在代码里也是这么写的：只有"审计文件存在 + 记录数 > 0 + 最后一条足够新鲜"才返回 `WIRED`。

**后果。** `.tmp/` 清理或 `scaffold.py --reset-audit` 会把同一条接线打回 fail。
**拿一次 `wired` 输出当"治理已开启"的长期证据不成立。**

**附带一条同类观测。** `verify-bc`（插件挂着但 Hook 命令起不来）被判成 `audit_never_written`
而不是 `not_wired`——**"挂上了"与"拦得住"在清点器里是两个问题**，别用前者替代后者。

**处置建议。** 把清点输出里的"接线事实"与"留痕新鲜度"拆成两个字段，
让 `wired` 不再同时承担两个含义；或者在字段名/文档里把"它是联合属性"写死（本轮先在
[00 §1.2](00-capability-report.md) 与 [04 §6.2](04-independent-verification.md) 写清了）。

### 2.6 N21 · 台账文件名在运行期被改写（读数陷阱）

**会遇到什么场景。** adapter 配置里写着 `enforcement_ledger: enforcement-ledger.jsonl`，
于是你按这个名字去数，得到 **0 条**，然后误判"事后核对从来没跑过"。

**细节。** 只要 Hook 命令带了 `--audit`，台账路径就**由审计路径派生**，
配置字段被静默覆盖（`src/adapters/dsh/hooks.py:1155-1164`）：

    state_file = audit_file.with_name(f"{audit_file.stem}.enforcement-ledger{audit_file.suffix}")
    # --audit .policy/audit.jsonl  =>  .policy/audit.enforcement-ledger.jsonl

这个覆盖是**有理由的设计**（注释写明了：Phase 2 的记录与 Phase 4 的链落在同一份证据里，
而幂等/授权状态要用独立台账，两种 JSONL 协议不能混写）。问题在于：
(a) 一个被声明出来的配置字段被静默忽略；(b) 按配置名去数的人会得到 0。

**还有一条同日发现的区分。** 两份文件各司其职，不能互相顶替：

| 文件 | 内容 | 有没有 digest 链 |
| --- | --- | --- |
| `.policy/audit.jsonl` | Phase 2 的钩子记录 **+ Phase 4 的摘要链记录**（`stage` / `sequence` / `prev_digest`） | **有** |
| `.policy/audit.enforcement-ledger.jsonl` | 台账：`kind` = claim / grant / pre_decision / pre_state / execution | **没有** |

**证据。** V1 自己先踩了这个坑并公开改正（[04 §6.2](04-independent-verification.md)）；
T2 用 11 次会话的存证复核：链 43 条、`sequence` 1..43 连续、42/42 条 `prev_digest` 自洽；
台账 50 条、五种 `kind`、无 digest（[02 §6](02-governed-runs.md)）。

**处置建议。** 要么让 `enforcement_ledger` 配置在带 `--audit` 时仍然生效（并写清冲突时的优先级），
要么把这条派生规则写进 `src/adapters/dsh/README.md`，别让它只活在代码注释里。

### 2.7 N22 · 只读工具的范围阻断会打断探索（设计取舍的代价）

**会遇到什么场景。** d1 里模型想 `glob` 仓库根来了解项目结构——仓库根在受控项目之外，
于是被 `context_error` 拦住（exit 2），探索被打断一次。

**判定：方向正确，代价要写明。** `path_scope=workspace` **不因只读而降级**，
这是本仓库既定的安全口径（只读工具降级的只是授权链路，不是范围校验）。
代价是：模型拿到的是一个它不容易自我纠正的错误，会白走一次工具调用。

**处置建议（可选）。** 拒绝理由里直接给出可用的替代（例如"目标不在受控项目内，
当前工作区根是 `.`"），让它一次就能改对——这属于**可用性改善**，不改安全语义。

### 2.8 N23 · 受治理会话里 `bash` / `run_code` 根本发不出来（装配事实）

**会遇到什么场景。** 有人拿"受治理会话里 `bash` 的 reason_code 是 X"来推断会话行为。

**细节。** 实测（V1 的行为探针 + T3 的工具清单核对）：这条 profile 装配出来的会话
**只把 `pwsh` 暴露给模型**，没有 `bash`、也没有 `run_code`。
所以 T3 关于 `bash` / `run_code` 的结论**只覆盖 Hook 层**（把载荷直接喂给 Hook 得到的），
不代表会话里会发生什么。

**与 N6 的关系（两条一起才解释"跑不了测试"）。**

| 编号 | 说的是哪一层 | 内容 |
| --- | --- | --- |
| N6 | 平台侧驱动 | `shutil.which("pwsh")` 为 `None` → `enforcement.cli execute` 执行时 `process_error`（WinError 2） |
| N23 | 会话侧工具清单 | 会话里只有 `pwsh`，发不出 `bash` / `run_code` |
| N16 | 事后核对 | 即使跑起来，输出也回不到模型 |

**处置建议。** 写清适用范围即可；换 profile 装配就可能不同，所以这条是**装配事实**而非仓库缺陷。

### 2.9 N24 · `binding=action` 在会话里永远过不去；一个 `approval.json` 只放一条记录

**会遇到什么场景。** 管理员想按"这一次调用"签一张更严格的条子。

**细节（两条边界，都是实测）。**

1. **单次绑定在会话里不可用**：`action_hash` 覆盖运行时生成的 `action_id` / `tool_use_id`，
   而模型每次重试都会换一个新的调用编号 → 签好的条子立刻失配。
   这不是缺陷（防重放、防一签多用是方向），但它的**实际后果**是"会话里只有模式化审批可用"——
   这正好解释了 G4 为什么必须补 `binding=pattern` 这一档。
2. **一个 `approval.json` 只解析一个 JSON 对象**，因此**一次只能授权一个执行工具**；
   要同时授权 `pwsh` 与另一个工具，需要另一份文件（本轮 T3 就为两种场景各用了一份）。

**证据。** [03 §2.2 / §2.3](03-validator-and-execution-paths.md)：`binding=action` 实测在会话中
永远匹配不上；`binding=pattern` 签出的条子让同一条 `python -m pytest -q` 从
`approval_required`(exit 2) 变成 `allow_delegated`(exit 0)。

**处置建议。** 属于 G4 修复的已知边界，写清即可；若将来要放宽，仍应保留 `binding=action` 作为更严格档。

## 3. 本轮**关闭**或**确认**的旧条目（与上面的新问题成对读）

只列状态有变化的；完整判定见 [04 结论表](04-independent-verification.md) 与
[00 §4](00-capability-report.md)。

| 旧条目 | 本轮之前 | 本轮实测 |
| --- | --- | --- |
| **G2** 事后核对从未执行 | PARTIAL：台账里 `post_*` 记录 0 条 | **FIXED**：真实会话里 d1 `PostToolUse` 33 条、33 个 action_id 全部成对（pre_only=0、post_only=0），7 个写动作全部 `post_validated` |
| **G6** 依赖规则只认字面写法 | FIXED（探针级） | **真实会话确认**：五种写法（字面量 / 相对导入 / 动态字面量 / 别名 / 不可证动态）全部 `policy_block`，目标 sha256 未变 |
| **G10** 工具白名单跟不上升级 | FIXED（契约级） | **端到端确认**：`spawn_teammate` 类协作工具在受治理通道上是 `not_governed`（记录但不拦），不会一接线就把团队功能封死 |
| **G4** 命令类工具结构性不可用 | PARTIAL | **审批那一半 FIXED**（模式化审批实测可用）；**另一半被 N16 挡住**——审批过了，输出仍然回不去 |
| **G1** 通道没装检查站 | PARTIAL（本机零 wired 通道） | **部分关闭**：新增 `dsh:governed` 通道并实测 WIRED；桌面通道的开关已验证但**未安装**（装它要重启界面） |

## 4. 三条读数纪律（本轮三次返工的沉淀）

本轮出现了三次"结论没错、数字错了"的返工，共性是**把不同口径的东西数到了一起**。
这三条已写进 [01 §7.8](01-rule-coverage-matrix.md)，此处再强调一次：

1. **码 ≠ 规则，证据条数 ≠ 规则数**：39 条 `style_lint` 背后是 60 个 Ruff 码；
   反过来 `SEC-007@2` 一条规则能产出 3 条证据。
2. **规则命中 ≠ 任何阻断**：d1 的 `policy_block` 是 0，但同一份审计里有 3 条 `exit_code=2`
   （`approval_required` / `command_composition_blocked` / 只读 `glob` 越界的 `context_error`）。
   三类数字必须分开引用。
3. **审计侧 ≠ 台账侧 ≠ 两流合计**：d1 的判定数有 7 / 14、7 / 7、14 / 21 三个都对的口径，
   其中**两个不同的 14 来源不同**（审计侧的 `decision` 计数 vs 两流合并的 `reason_code=allow`）。
   引用时必须写明分母与来源文件。

一句话判据：**每个数字都要带分母与来源文件，且能被第三方在同一份原始产物上重算出来。**

## 5. 复现

    # 0) 造受控项目 + 治理三件套 + 装持久接线的 profile
    python .tmp/governance-capability/harness/scaffold.py --install-profile --reset-audit

    # 1) N19 的反面样本（模型自审拒绝 → 哈希没变但审计无写类判定）
    Get-Content .tmp/governance-capability/logs/v1-selfrefuse.log

    # 2) N18：Hook 直调退出码确为 2，而 dsh 侧读到 1
    python .tmp/governance-capability/harness/probe_hook.py          # 矩阵里 exit_code=2
    .tmp/governance-capability/verify/vexits2.py                     # 退出码保真探针

    # 3) N20：同一份 patch，审计被 reset 后同一条命令翻回 fail
    python .tmp/governance-capability/harness/scaffold.py --reset-audit
    python -m adapters.cli wiring --check                            # audit_never_written
    # 跑任一次真实会话后再跑同一条命令 → WIRED（patch 未变）

    # 4) N21：两份 JSONL 各司其职
    python .tmp/governance-capability/lead-probe/run_table.py

    # 5) N16 / N17 / N24：见 03 号文档 §4 的复现清单

## 6. 修复轮处置（2026-09-26）

同日又跑了一轮**修复轮**，输入就是这一篇：把这 9 项登记的问题修掉，每处配一条**修复前会红**的检查。
完整机制、修复前后对照、验证矩阵、边界与复现命令见
**[11-n16-n24-fix-round.md](../governance-remediation/11-n16-n24-fix-round.md)**；
独立验收见 [10-n16-n17-n20-verification.md](../governance-remediation/10-n16-n17-n20-verification.md)。

| 编号 | 处置 | 一句话 |
| --- | --- | --- |
| **N16** | **已修** | 退出事实从 dsh 规范化结果 `result.value` 转发 → 严格解析 → `ExecutionRecord.exit_code` → 审计落盘。修复前 exit 0 也判 `repair_required`；修复后 `post_validated`，且**拿不到退出码时仍不变量为 `repair_required`** |
| **N17** | **已修** | `invalid-syntax` 由 `validation/validators.yaml` 显式声明 → 命中即失败关闭；那 39 条 `style_lint` 不再被记成"已判定"；报告新增显式 `judgements`（`empty` / `unanalyzed`） |
| **N18** | **已修** | 根因**已定位**：本机无 `pwsh` → 回退 **Windows PowerShell 5.1**，其 `-Command` 把原生命令的非 0 退出码**压成 1**。理由分类改由 Hook 自写的机读判定行给出；**任何非 0 仍然一律拒绝** |
| **N19** | **换形态** | 判据变成 `src/enforcement/verdict.py` + `python -m enforcement.cli verdict`：带 A/B/C 证据等级的显式结论，**`blocked` 当且仅当存在拒绝记录** |
| **N20** | **已修** | `wired` 拆成 `wiring_status` / `freshness_status`；`status`/`ok` 是两者的合取；schema `1.0` → `1.1`（有版本钉） |
| **N21** | **已修** | 派生台账路径变成一等输出（`--self-check` 打 `effective-paths`）+ 每会话一条 `ledger_path_overridden` 审计记录 |
| **N22** | **已修** | 越界理由给出可用替代（项目根记为 `.`），**范围校验一个字没放松** |
| **N23** | **已写清** | README §11：只装配 `pwsh`，相关结论只覆盖 Hook 层 |
| **N24** | **已写清** | README §11：`binding=action` 必然失配；一个 `approval.json` 只放一条记录 |

**同一轮新显现 4 项**（编号续 N25）：

| 编号 | 一句话 | 类别 |
| --- | --- | --- |
| **N25** | **受限** DSH 会话里连 Hook 都起不来：插件用管道 stdio 起 Hook，沙箱禁止开命名管道 → `spawn EPERM` → 失败关闭拒绝。方向正确，但策略链路**根本没被触及**（没有审计、没有判定），容易把"跑不了"读成"跑成了、没拦住" | 宿主装配事实 |
| **N26** | 宿主 ACL 沙箱把 `os.mkdir(d, 0o700)` 的目录锁成不可读、不可删：pytest 的 `tmp_path` 会 ERROR、session 结束清理会 WinError 5，留下的目录连 `takeown` 都修不回来；`kill` 受限 pytest 会留下永久锁死目录 | 宿主环境事实 |
| **N27** | `exit_code_zero` 把"证据充分"与"命令成功"合成一条判定：N16 修好之后，"通过时看得到输出、**失败时看不到**"变成确定可达的行为。本轮只在**插件内**缓解（把同一份已截断输出作为不可信数据附回），注册表一个字没动 | 设计取舍的边界 |
| **N28** | 门禁对"工作树之外的动作"不免疫：同一棵树第一遍全绿、第二遍 `Tech-detail notebooks` 翻红——一份 tech-detail notebook 带上了 Jupyter 运行痕迹（`execution_count` / `outputs`），与改动无关。上一轮撞过同一件事（`04-受控执行.ipynb`） | 门禁性质 / 仪器陷阱 |

**三处事实性更正。** 本文 §2.2 与 01 / 03 两篇都写过"`validation/ruff.toml` 的注释仍按旧口径写 `E999`"——
修复轮对 `validation/` 整个目录逐字检索：**不含 `E999`**。三份文档互相引用了同一个未核实的说法；
三处已就地更正并留更正块。

**实验结束后建议清理**（本轮在 `$DSH_HOME/profiles/` 下留了 8 个 profile，
`governed` 是交付物，其余是实验产物）：

    Remove-Item -Recurse "$env:DSH_HOME\profiles\governed-grade",
        "$env:DSH_HOME\profiles\governed-grade-approval",
        "$env:DSH_HOME\profiles\verify-bc", "$env:DSH_HOME\profiles\verify-dead",
        "$env:DSH_HOME\profiles\verify-exit2", "$env:DSH_HOME\profiles\verify-gov",
        "$env:DSH_HOME\profiles\verify-manual"
    python tools/cleanup.py     # 删 .tmp/（仪器与原始证据随之下线，方法已在本目录逐条留档）
