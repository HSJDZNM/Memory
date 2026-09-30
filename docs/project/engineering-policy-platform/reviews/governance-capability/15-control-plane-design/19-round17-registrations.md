# 19 · 第 17 轮：台阶 4 `reading_context` 的登记项、遗留与门禁读数

- **执行**：2026-09-30（本机）；控制面重构会话（**唯一写者**）。
- **树**：分支 `refactor/control-plane`；**before** = `2d9b353`（第 16 轮末），两个提交依次落地：
  `640fd98`（小修：义务门禁"账本不存在 = 不适用"）→ `0fa42d1`（只报告读数读得懂多行 JSON）；
  本文件是第三个提交。
- **更正（2026/09/30 18:06 +08:00，本文件的第四笔改动，只动文档）**：§3 第 2 行的端到端读数在**使用者裁定**下
  更正为「**真机 = pass；受限沙箱里 = skipped**」，原件 sha256 与四条旁证见 §3.1；
  `tools/` 与 `tests/` 一个字节都没改。
- **依据**：本轮指令的四步；AGENTS 第 45（仪器要能失败）/ 46（违规则清单）/ 50（口径诚实）/
  55（加键就是改协议）/ 56（义务账）条；18 号 §2（`tool.pytest` 第 55 条核查的既定语）。
- **本文件是什么**：这一轮的**前置读数、小修口径、登记项、门禁读数**，以及
  **没做 / 未核实 / 请评审裁定**。它不替代方案的任何一节。

---

## 0 一句话

第 1 步（合并 `origin/perf/ci-local`）在本树上**前置不成立**（§1：本仓库没有这个 ref、
对象也不在，没有对象传输就合并不了）；第 2 步小修落地（§2，R-d 差集 **0 条**）；
第 3 步登记两项 `reading_context` 待建项 + 一项遗留（§3 / §4，**只登记不动手**）；
第 4 步门禁 `--full` **退出码 0 / 合计 8m 09.4s / 33 步全绿**（§5）。

---

## 1 第 1 步：合并 `origin/perf/ci-local` 的前置不成立（读数逐条）

指令按"使用者已在本机 `fetch` origin"给的，但**本仓库里没有这个远端跟踪分支**。
五条读数互相印证：

| # | 读什么 | 命令 | 读数 |
| --- | --- | --- | --- |
| 1 | `origin/perf/ci-local` 存不存在 | `git rev-parse origin/perf/ci-local` | `fatal: ambiguous argument …: unknown revision`（退出 1） |
| 2 | 对象在不在本仓库 object store | `git cat-file -t dde53f1` | `fatal: Not a valid object name` |
| 3 | 有没有 `fetch` 过 | `Test-Path .git\FETCH_HEAD` | **不存在** |
| 4 | 远端跟踪 ref 有哪些 | `.git/logs/refs/remotes/origin/` | 只有 `HEAD` 与 `refactor/control-plane` 两条 reflog |
| 5 | origin 那一侧 | `git -C C:\Users\ZNM\Downloads\Memory for-each-ref` | 有 `refs/heads/perf/ci-local` = `dde53f1`「perf(ci): 本地门禁 993s→223s（xdist、去重步骤、confcutdir）」；父提交 `6fa800e` 正是本分支的祖先（`git merge-base HEAD 6fa800e` = `6fa800e`） |

**结论**：分支在 origin 上存在、在本仓库里不存在 —— 要合并必须先做一次**对象传输**（`git fetch`），
而本轮指令明令**不要 fetch / push**。因此四件指令动作**一件都没有做**：
没有合并、没有解决冲突、没有在合并后的树上按锁文件装 `pytest-xdist==3.8.0`、
也没有"合并后"的 `argv_length 12→14` 读数。
**不伪造一个"看起来合过了"的提交**（与 18 号 §1 同一条纪律）。

**第 1 步的实质预习（读的是 origin 侧那棵树，不是本树；仅供评审预判，不算读数）**：
`git -C … diff --stat 6fa800e dde53f1` 显示 **11 个文件**，指令点名要手工解决的三处冲突文件
（`AGENTS.md` / `tests/integration/test_validator_pipeline.py` / `tools/ci_local.py`）
都在里面，另有 `.github/workflows/phase-8.yml`（删两步重复）、
`requirements.in` / `requirements.lock` / `pyproject.toml`（`pytest-xdist`）、
`validation/validators.yaml` 与两个测试文件。

**`argv_length 12→14` 的来源就在这里**：`tool.pytest` 的 `argv` 增加
`--confcutdir {workspace}` 两个元素（12 → 14），目的是把收集范围钉在工作区内
（回归用例 `test_conftest_above_the_workspace_is_not_part_of_the_run`）。
按 18 号 §2 的既定语（**证据里能追溯到 `validation/validators.yaml` 的摘要就不升版**，依据
`policy.check --json` 的 `evidence.configs.registry`），初步判断仍是**不升**
`tool.pytest@1.0`；但 R1 / R2 / R3 三条读数必须**在合并后的树上重跑**才算数 ——
本树跑不出 12→14（本树没有那两个元素）。

---

## 2 第 2 步：义务门禁"账本文件不存在 = 不适用"（`640fd98`）

**口径**（写进 `tools/obligations_gate.py` 的 docstring、`tools/README.md` 与 AGENTS 第 56 条）：

- 账本**文件不存在** = 这次**没有账本可读** → 该账本报 `applicable=false` + 不适用：
  **不算命中**，也**不算一次真实读数**（L5 升格判据里的"0 命中"必须来自至少一次真实读数，
  没读到账本的那一次凑不了这个判据）；
- 账本**存在**（哪怕是个空文件）却拿不出「最近一次真实测试运行」= **没有依据** →
  **仍按命中处理**（AGENTS 第 56 条的既有口径，本轮**没有改**；口径边界见 §6 第 1 条）；
- 账本路径存在但不是文件 → 用法错误、退出 2（原先会抛出 `IsADirectoryError` 的裸栈）。

**载荷版本**：报告新增 `report_schema_version` / `applicable` /
`applicable_ledgers` / `not_applicable_ledgers`，按 AGENTS 第 55 条 **1.0 → 1.1**，
并把这条新轴登记进第 55 条的版本轴表（新增一组"本机门禁与仪器"）；
`tools/ci_local.py` 的只报告读数把"不适用"打出来。

**改了哪条既有测试**：`test_a_ledger_with_no_real_run_cannot_claim_zero` 名字说"空账本"、
传的却是一个**从来没被创建**的路径（用例名与事实不符）—— 拆成两条：
不存在 → 不适用（0 命中、退出 0）；存在但空 → 没有依据（仍然命中、退出 1）。

**R-d 字段级差集（判据：必须为 0）**：

| 产物 | 读数 |
| --- | --- |
| `.tmp/step5/decisions-after.json` | sha256 `cfad8c32c59a57a49290759d54db020c57f9cb6a07f0fbdf7d759d9f13ad4588`（23992 B） |
| 与 `.tmp/step4/decisions-before.json` 的关系 | **逐字节相同**（同一个 sha256） |
| `json_field_diff.py --before … --after …` | `count = 0`（`DIFF_EXIT=0`） |

10 个场景（四种 decision + pending 一族 + 审批门禁 + 失败关闭对照）的
`decision` / `violations` / `pending_findings` / `matched_rules` /
`skipped_rules` / `required_action` / 载荷键集合 / 模型字段集合**逐个相同** ——
判定路径一个字节没改。

**回归**：`tests/integration/test_obligations_gate.py` **9 passed**；
它与 `tests/unit/test_ci_local_report_only.py` 合计 **17 passed**；整树读数见 §5。

---

## 3 登记：台阶 4 `reading_context` 的两项（**只登记，机制未建**）

17 号 §2.3 第 2 条把 `reading_context` 判成"**建机制（薄）**"，
但"薄"到什么程度当时没有写下。本轮把两项登记进去（17 号 §8 是这条登记的回指）：

| # | 待建项 | 为什么属于 `reading_context` | 代价（按第 55 条算） |
| --- | --- | --- | --- |
| 1 | **Hook 侧 `tool.pytest` 的追溯缺口**：`pre_evidence` 的审计摘要里没有注册表摘要（字段是 `registry_resolution` / `validators_requested` / `validators[]` …，见 `src/adapters/dsh/pre_evidence.py` 的 `_summary`），同一条 `tool.pytest@1.0` 在账本里对应三种行为（H4 之前 / H4 之后 / 3b 之后） | `reading_context` 要回答"这份读数属于哪棵树、哪一套声明"；审计记录答不出它出自哪一版 `validation/validators.yaml` —— 这正是同一个问题在**审计侧**的形态。证据段（`policy.check --json` 的 `evidence.configs.registry`）**已经**能读到注册表摘要（18 号 §2 的 R2），缺口只在 Hook 侧 | 给 `pre_evidence` 摘要加注册表摘要键 = **审计记录的键集合变化** → 递增 `AUDIT_SCHEMA_VERSION`（**1.2 → 1.3**）；同批要改 5 处测试断言与 14 处文档读数引用（18 号 §2 已列出） |
| 2 | **JS 侧真实 dsh 端到端**：**真机 = pass；受限沙箱里 = skipped**（2026-09-30 更正，见 §3.1）—— 更正前那条读数（`python tools/dsh_sandbox_loop.py` 退出码 0、`result=skipped`、`environment_skipped=true`、`dsh_startup_denied_kind=profile_write_denied`、被拒路径 `C:\Users\ZNM\.dsh\profiles\headless\cordis.yml`、拒绝系统调用 `open`、根证据 `env:DSH_HOME`；两个场景 `passed=false`、`audit={}`（**Hook 从未被调用**）） | 台阶 4 的机制要能说"这份读数属于哪个环境"，而这条端到端读数**在真机上拿得到、在受限沙箱里拿不到**（同一个工具的结论差别**只来自环境**）：环境跳过不是通过（AGENTS 第 45 条），"本机拿不到"也不是。机制建起来之后，"绿"必须仍然能区分"真跑过"与"环境跳过" —— **它是机制的前置条件**，不是机制的替代品 | 跳过本身是**显式**的（退出码 0 + reason + 复现命令），不必改协议；要评审裁定的是：机制要不要为"端到端在受限宿主上不可得"单独留一档读数 —— 更正后这一档还必须写明**哪台宿主、哪一个环境**（否则同一个工具在两处的结论会被读成同一件事） |

### 3.1 更正（2026-09-30）：端到端 = 真机 pass / 受限沙箱内 skipped

**被更正的那条**：上面表格第 2 行原写「JS 侧真实 dsh 端到端 = skipped（本机）」，并据此把
"本机拿不到这条读数"当成 `reading_context` 的前置条件。**这个说法只对受限沙箱成立**：
使用者真机上跑通过一次 `result=pass`；`skipped` 是**在 DSH 沙箱里跑出来**的读数，不作为端到端读数。

**原件**（使用者指定；下表逐字取自它）：

| 项 | 读数 |
| --- | --- |
| 路径 | `.tmp/e2e/phase-2-sandbox-result.pass-20260930T010751Z.json` |
| 大小 / sha256 | **2653 B / `df2646db896cf726d03cbdff0372783d96f2cffb01b3873034a583167859ed30`** |
| 结论 | `result=pass`、`environment_skipped=false`、`agent=dsh`、`timestamp=2026-09-30T01:07:51.436314Z`（= 本机 09:07:51 +08:00） |
| block 场景 | `decision=block`、`reason_code=policy_block`、`exit_code=2`、`executed=false`、`matched_rules=[ARCH-001@1]`、文件 sha256 前后**同为** `53b53a25162599fc713132968f015263e3c914fb30f6bb532e4c9c712137ed66`（**未变**）、`passed=true`、session `session-e0c9cd74-2dd8-4f78-9b57-9ada35db6317`（01:07:40Z） |
| allow 场景 | `decision=allow`、`reason_code=allow`、`exit_code=0`、`executed=true`、文件 sha256 `53b53a25…ed66` → `2972725e717804ec67a4cf5b4bb5a7500de25d161b5e28a15a2e27f76088b558`（**改了一次**）、`passed=true`、session `session-77616ce0-a6ed-451c-81da-45b48ab7d247`（01:07:49Z） |

**成立条件**（使用者裁定）：`DSH_HOME`、`TEMP`、`TMP` 指到 `.tmp/phase-2-sandbox/dsh-home` 与
`.tmp/phase-2-sandbox/dsh-tmp` —— 两者都在受控项目 `demo-shop` **之外**。

**旁证（本机可复核的四条）**：

1. `dsh-home/sessions/--C-Users-ZNM-…-demo-shop--/` 下正好两个 `session.v3.jsonl.zstd`
   （09:07:43 / 09:07:51），目录名就是原件里那两个 session id；
2. `dsh-tmp/dsh-acl-locks/*.lock` 7 个（09:07:35–09:07:49）与 `dsh-tmp/dsh-spill-AVwp50`（09:07:44）：
   dsh 的 Windows ACL 沙箱与 spill-local **真的在这个临时根上工作过**；
3. `demo-shop/.policy/audit.enforcement-ledger.jsonl` 5 条（01:07:49.292Z–01:07:50.365Z）：
   `claim → grant → pre_decision → pre_state → execution`，`action_id` 是 allow 场景的 event_id；
   **block 场景一条台账都没有**（它停在策略判定，没进受控执行链）；
4. `dsh-home`（09:07:34）与 `dsh-tmp`（09:07:51）的 mtime 与原件时间戳同刻。

**12:15 那次 skipped 的出处与性质（不作为读数）**：`.tmp/step5/ci-local-full.log` 的
`=== Real dsh sandbox loop (skipped without dsh) ===`（该次门禁的第 10 个执行步骤；日志第 162–208 行）：
`result=skipped`、`environment_skipped=true`、`dsh_startup_denied_kind=profile_write_denied`、
被拒路径 `C:\Users\ZNM\.dsh\profiles\headless\cordis.yml`、`syscall=open`、根证据 `env:DSH_HOME`。
**它是在 DSH 沙箱里跑的**（门禁跑在受限宿主上，沙箱不允许写 `$DSH_HOME`），所以它既不是
"这台机器的端到端读数"，也不是"端到端跑不成"的证据。落到 12:15 的依据：该次门禁 12:09:59.6 起跑、
12:18:09 结束（合计 8m 09.4s），它前面 9 个执行步骤的耗时合计约 5m 23.5s。

**同一路径上的第二次跳过（登记，归属未核实）**：`.tmp/artifacts/phase-2-sandbox-result.json` 现在是
`timestamp=2026-09-30T08:43:06.919440Z` 的 **skipped**（同一个 `profile_write_denied`，但根证据只有
平台默认 `default:$HOME/.dsh`，**没有** `env:DSH_HOME`），与 16:42–16:46 的一批门禁产物同批。
**它是哪条命令、哪个会话触发的，本轮未核实** —— 登记在这里，免得被读成端到端读数。

**更正后依然成立的判据**：`reading_context` 仍要能区分"真跑过"与"环境跳过"，而且现在多了一条已知形态：
**pass 与 skip 的差别可以只来自环境**（真机 vs 受限沙箱）。读数必须写明"哪台宿主、哪一个环境"，
否则同一棵树上的两次运行会被读成同一件事。

**未核实（照实写）**：原件里 allow 场景的 `file_sha256_after`（`2972725e…b558`）**在当前磁盘上复核不了**：
`demo-shop` 已被后续运行按 `build_project()` 重置（当前 `src/shop/order_controller.py` 的 sha256 =
`53b53a25…ed66`，正好等于原件里两个场景的 before），`demo-shop/.policy/audit.jsonl` 与 `captures/`
也被那几次重建清掉了。因此上面 block / allow 两条结论**只有原件本身可证**；旁证 1–4 证明的是
"那两个 session 真跑过、真的走过受控执行链"，不等于"那两次改动的最终哈希"。

---

## 4 遗留（登记）：`check_arch_style` 的既有红

**读数**（本机实跑 `python tools/check_arch_style.py`）：

```
================== 文风自检（只看散文）
  x 使用说明.md §7. 多 Agent 适配（Phas 概括句过长（218 字）：`agent_version` 写着「**已实测**的产品版本」，所…
共 1 处
退出码 1
```

| 项 | 值 |
| --- | --- |
| 文件 / 小节 | `docs/project/architecture/使用说明.md` 的 `## 7. 多 Agent 适配（Phase 6）`（第 252 行） |
| 规则 | 该 H2 小节第一段散文的**首句 218 字** > 45 字（`tools/check_arch_style.py` 的 `check_docs()`） |
| 是不是本轮引入 | **不是**。用检查器自己的函数在 `843f6dd^` 上复算 §7，同样是 218 字；`git log -S` 指向 `b9d3b11`（2026-09-28，第 15 轮 Q6/Q7/Q8 修复） |
| 为什么一直没被拦住 | `check_arch_style.py` **不在** `.github/workflows/phase-8.yml`、也**不在** `tools/ci_local.py` 的步骤表里（两处 `git grep` 都无命中）→ 这条红**没有任何门禁会拦住**，只能靠人跑 |
| 处置建议（未做） | 二选一：① 按"文风口径"改写那一句（拆成概括句 + 精确句）；② 明确"文风自检不在门禁内"并把这条红登记为**已知红**。本文件只登记，`docs/project/architecture/` 一个字节没动 |

---

## 5 第 4 步：门禁读数（`--full`）

**命令**（树 = `0fa42d1`，工作树干净、无并发）：

```powershell
python tools/ci_local.py --full --python .venv/Scripts/python.exe
```

| 项 | 读数 |
| --- | --- |
| **显式退出码** | **0** —— `本机检查全部通过（33 步）；只报告 2 步（非零退出不计入失败）` |
| **耗时** | **8m 09.4s**（`=== 执行耗时（合计 8m 09.4s，35 步）===`） |
| 大头 | `Unit, contract, integration and security tests` **5m 05.3s**（62.4%）→ `Learning notebooks are in sync` 1m 11.7s → `Orchestration closed loop` 1m 01.7s |
| 选组 | `改动文件 800 个；执行 33 步（本机跳过 11 步，登记豁免 2 步，只报告 2 步）` |
| 与 **223s** 对照 | 223s 是 `origin/perf/ci-local`（xdist + 去重两步）在**它自己那棵树**上的读数；本树没有合并它、也没有 `pytest-xdist`。两个数**不是同一棵树上的读数**，不能相减；从构成看，pytest 一步占 62.4%，正是 xdist 要压的那一块 |
| 只报告步骤 1 | `Obligations gate (report only)` —— 0 命中（退出码 0）；读数 `hits=0 / 1 个账本（不适用 1：没有账本可读，不算一次真实读数）` |
| 只报告步骤 2 | `Exemption expiry report (report only)` —— 0 命中（退出码 0）；读数 **读不出命中数**（见 §6 第 2 条） |
| 同命令的第一次运行（树 = `640fd98`） | 退出码 **0**、**8m 11.2s**；该次只报告读数是"读不出命中数"（促成 `0fa42d1`）。日志：`.tmp/step5/ci-local-full-at-640fd98.log`；被 kill 的半程日志 `.tmp/step5/ci-local-full-aborted.log` |

---

## 6 没做 / 未核实 / 请评审裁定

1. **口径边界（请裁定）**：本轮把"账本**文件不存在**"判成不适用；**"账本存在但 0 条义务、又没有真实运行"仍然按命中处理**（AGENTS 第 56 条原话）。若评审要的是"账本存在但没有未结义务时也不算命中"，那是**改既有口径**，需要显式裁定 —— 本提交没有改它。
2. **登记未修（请裁定）**：`Exemption expiry report (report only)` 的读数读不出来。两个原因叠在一起：① 这一步的 `args` **没有** `--json`，而它的 `reads` 字段声称读 `--json` 的 `due` / `expired`；② `report_only_hits` 只认 `hits` 这一个键。处置很小（加 `--json` + 给一个"没有 `hits` 时打印标量摘要"的回退），但它属于第 16 轮那条豁免的读数口径，本轮**只登记不动**。
3. **本轮第 3 个提交（`0fa42d1`）是额外项**（不在指令的四步里）。理由：第 4 步第一次门禁运行暴露"只报告读数读不出命中数"，**第 2 步刚做的"不适用"因此在真实门禁运行里不可见**，L5 升格判据（"0 命中必须来自至少一次真实读数"）也就无从引用。它是**独立提交**：如评审认为越界，`git revert 0fa42d1` 即可，不影响 `640fd98`。
4. **未核实**：`%TEMP%` 那一次 dsh 起不来（`other_path_denied`，被拒的是系统 temp 的 `mkdtemp`）。本轮实跑只复现了 `~/.dsh` 那一次（`profile_write_denied` / `open`）；使用者的读数里两次都在，**本机只复现了一次**。
5. **未核实**：远端 `origin/perf/ci-local` 此刻的真实状态（本轮按禁令没有 fetch / push）。§1 的全部读数只对本机对象库与 origin 目录的当前状态成立。
6. **未做（按禁令与前置）**：没有合并 `origin/perf/ci-local`、没有解决那三处冲突、没有装 `pytest-xdist==3.8.0`、**没有做 `REPORT_ONLY_STEPS` 与 `FULL_ONLY_STEPS` 并存的那次合并**、没有跑"合并后"的 `argv_length 12→14` 读数。
7. **未做**：`git push`、`--no-verify`、强推、`git add -f`、`tools/cleanup.py` —— 一律没有；改动只用 `write` / `edit` 落树，提交按路径暂存。
8. **未核实**：§4 那条红"最早出现的版本"（只证到 `843f6dd^` 与 `b9d3b11` 之间，没有逐版二分）。

---

## 7 复现命令（按顺序，只读或只写 `.tmp`）

```powershell
# 0 第 1 步的前置读数（应为 unknown revision / 非法对象名 / False）
git rev-parse origin/perf/ci-local
git cat-file -t dde53f1
Test-Path .git\FETCH_HEAD
git -C C:\Users\ZNM\Downloads\Memory for-each-ref --format='%(refname) %(objectname:short)' | Select-String perf

# 1 第 2 步的 R-d 差集（应为 count=0、退出 0）
$env:PYTHONPATH='src'
.venv\Scripts\python.exe .tmp\step3b\probe_decisions.py --out .tmp\step5\decisions-after.json
.venv\Scripts\python.exe .tmp\step3b\json_field_diff.py --before .tmp\step4\decisions-before.json --after .tmp\step5\decisions-after.json

# 2 义务门禁的三种形态（不适用 / 没有依据 / 未结）
.venv\Scripts\python.exe tools\obligations_gate.py --ledger .tmp\obligations\missing.jsonl
.venv\Scripts\python.exe tools\obligations_gate.py --ledger .tmp\obligations\repo.jsonl --json

# 3 遗留那条红（应退出 1、共 1 处）
.venv\Scripts\python.exe tools\check_arch_style.py

# 4 dsh 端到端（**受限宿主上**应为 skipped、退出 0；真机读数与更正见 §3.1）
.venv\Scripts\python.exe tools\dsh_sandbox_loop.py

# 5 门禁（本轮读数：退出码 0 / 8m 09.4s）
python tools/ci_local.py --full --python .venv/Scripts/python.exe
```

---

## 8 本轮改动的文件（按提交）

| 提交 | 文件 | 处置 |
| --- | --- | --- |
| `640fd98` 小修 | `tools/obligations_gate.py` | 适用性：账本不存在 = `applicable=false` + 不适用；`REPORT_SCHEMA_VERSION` 1.0→1.1；目录 → 退出 2 |
| | `tests/integration/test_obligations_gate.py` | 拆开"不存在"与"存在但空"，共 9 条 |
| | `tools/ci_local.py` | 只报告读数带出"不适用"计数 |
| | `tools/README.md`、`AGENTS.md` | 口径同步（第 55 条版本轴表新增一组、第 56 条补"不适用"那一档） |
| | `tests/unit/test_ci_local_report_only.py` | 读数带"不适用"的回归 |
| `0fa42d1` 读数修复（额外项，见 §6 第 3 条） | `tools/ci_local.py` | `json_objects()`：多行 JSON 按花括号配平切出来整体解析 |
| | `tests/unit/test_ci_local_report_only.py` | 缩进载荷的回归 |
| 本文件 | `…/15-control-plane-design/19-round17-registrations.md` | 第 17 轮的读数、登记与遗留 |
| | `…/15-control-plane-design/17-step4-5-scope-assessment.md` | §8 补记：`reading_context` 两项登记的回指 |
| | `…/15-control-plane-design/README.md` | 索引新增本文件 |
| 更正（2026-09-30，本文件的第四笔；**只动文档**） | 本文件 | §3 第 2 行的端到端读数更正为「真机 pass / 受限沙箱内 skipped」，新增 §3.1（原件 sha256 + 四条旁证 + 12:15 的出处 + 未核实）；§7 复现命令的注释同步 |
| | `…/15-control-plane-design/17-step4-5-scope-assessment.md` | §8 第 2 行的回指同步更正 |
| | `…/15-control-plane-design/README.md` | 索引里 19 号的摘要同步更正 |
