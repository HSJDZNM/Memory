# 23 · 第 20 轮 · `reading_context` 落地（端到端 / 只报告两处 / `policy.check`）与评审点

- **执行**：2026-09-30（本机）；控制面重构会话（**唯一写者**）。
- **树**：分支 `refactor/control-plane`；本轮起点 HEAD = `cd40f74`（`git status --porcelain` 空）。
- **依据**：21 号设计稿（§3 统一形状 / §4 版本轴 / §5 R-d 预注册 / §7 落地顺序 / §8 预算 / §9 四条）
  与 2026-09-30 的四条裁定（**写进 21 号 §9.1**）。
- **本文是什么**：第 20 轮的记录——裁定执行、端到端真机读数登记、逐项 R-d 差集、门禁读数、
  未核实与评审点，以及本轮的复现命令。**本文只写读得到的东西**；读不到的写"未核实"。
- **本文不是什么**：不是评审结论，也不是"机制建好了"的宣告。它停在**评审点**上
  （覆盖账与审计**本轮不做**，见 §1 第 ④ 条）。

---

## 0 一句话

四条裁定落地了三件：端到端结论载荷、两条只报告读数的机器载荷、`policy.check --json` 的外层包装
各加一份 `reading_context`（**同一个形状、同一份实现**），三处各自的版本轴按 AGENTS 第 55 条同批递增；
**没有一条 allow / block 因此改变**（R-d 见 §3）。

---

## 1 裁定执行（四条，逐条给出落地证据或归属）

| # | 裁定（21 号 §9.1） | 本轮落地 | 证据 |
| --- | --- | --- | --- |
| ① | 受限宿主**不单独设状态轴**，只加 `host.sandbox` 枚举 | 端到端载荷里只有 `reading_context.host.sandbox`（`restricted` / `unrestricted` / `unknown`），**没有**第二个状态轴 | §3.4 R4 的差集；§4 `host.sandbox` 取值的逐条读数 |
| ② | `REPORT-ONLY:` 控制台行**不加** `reading_context` | `tools/ci_local.py` 本轮**一个字都没动**（含那条控制台行） | §7 改动文件表里没有它 |
| ③ | 阶段证据透传**交给 CI 线**，本线不做 | `tools/phase_evidence.py` 本轮**一个字都没动** | §7 改动文件表里没有它 |
| ④ | 落地顺序：端到端 → 只报告 → `policy.check`；**覆盖账与审计留到下一轮** | 本轮三个提交就是前三步；`AUDIT_SCHEMA_VERSION` 仍是 `1.2`、`WIRING_SCHEMA_VERSION` 仍是 `1.1` | §3 的三个小节；§5 未做清单 |

---

## 2 登记：使用者本机真机端到端读数（2026-09-30T11:35:32Z，树 = `cd40f74`）

**这是本轮要保住的那条读数**：同一个端到端闭环，**真机上 `result=pass`、受限沙箱里 `result=skipped`**
（19 号 §3.1 的更正；差别只来自环境）。

| 项 | 读数 |
| --- | --- |
| 时刻 / 约束 | `timestamp = 2026-09-30T11:35:32.027532Z`；两个场景的审计记录分别是 11:35:19.186925Z（block）与 11:35:29.633298Z（allow） |
| 开关 | `--isolated-home`（`DSH_HOME`/`TEMP`/`TMP` 只改 dsh 子进程的 env） |
| 结论 | `result = pass`、`environment_skipped = false`、`schema_version = "1.1"`（= `641b4ec` 建的那条轴） |
| block 场景 | `passed = true`；`file_sha256_before == file_sha256_after == 53b53a25162599fc…`（**文件未变**）；`decision=block`、`exit_code=2`、`executed=false`、`reason_code=policy_block`、`matched_rules=[ARCH-001@1]` |
| allow 场景 | `passed = true`；`53b53a25162599fc… → 2972725e717804ec…`（**文件改了一次**）；`decision=allow`、`exit_code=0`、`executed=true`、`matched_rules=[ARCH-001@1]` |
| 规则集 | 两个场景的 `rule_set_hash` 都是 `sha256:50202675b6ca4013…`；`agent_version = 0.1.5-rc.1` |
| 转录件 | `.tmp/e2e/phase-2-sandbox-result.pass-20260930T113532Z.json`（2780 B，sha256 `DBCF31765BBCEDEBCF6B73A8FF5EB29CBEC525F42800212E3CCABE91247A8946`，落盘时刻 2026-09-30 20:18:12 +08:00） |

**口径（第 50 条：先说不算什么）**：

1. 转录件是**从终端输出转录**的，**不是原文件字节**——它由使用者手抄进 `.tmp/e2e/`；
   原件（`.tmp/artifacts/phase-2-sandbox-result.json`）**已经被覆盖**（见下一条），不可复原。
   因此本文件登记的是"**有人读到过这份终端输出**"，不是"原件在这里可复核"。
2. **已知现象（本轮的设计约束就来自它）**：每次本机推送，pre-push 钩子都会跑一次沙箱闭环，
   并在受限上下文里以 `result=skipped` **覆盖**该产物。本次的覆盖发生在实测时刻
   `11:37:19.971926Z`（真机 pass 之后约 2 分钟）：现产物 2213 B、sha256
   `C2DAE5CBB3FAC3C0062DA5FD5FA7BA64163E49C522E5E84286A3BBB4DE99610F`、
   `result=skipped`、`environment_skipped=true`、`dsh_startup_denied_kind=profile_write_denied`、
   被拒路径 `C:\\Users\\ZNM\\.dsh\\profiles\\headless\\cordis.yml`、`syscall=open`。
   **所以：光看 `.tmp/artifacts/` 下这个文件，看不出它是不是这棵树上的真机读数**——
   加 `reading_context` 之后必须能看出来（本轮落地判据见 §3.4）。
3. **逐条核对的是转录件里能自己核对的部分**（前后哈希、`decision`、`exit_code`、`executed`、
   `matched_rules`、`rule_set_hash`、两个场景的 `passed`）。**"allow 场景真的写进了 `def ping`"
   这一条转录件里读不出来**（它只体现在 `passed=true` 上）→ 见 §6 未核实第 1 条。
4. 更早一次真机 pass 的转录件仍在：`.tmp/e2e/phase-2-sandbox-result.pass-20260930T010751Z.json`
   （2653 B，sha256 `DF2646DB896CF726D03CBDFF0372783D96F2CFFB01B3873034A583167859ED30`），
   与 19 号 §3.1 记的 `df2646db…ed30` 逐字符相同——**两份转录件是两次不同的运行**，不相减。

---
