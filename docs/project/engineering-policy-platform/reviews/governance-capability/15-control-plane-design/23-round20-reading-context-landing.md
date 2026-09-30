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


## 3 逐项 R-d（按 21 号 §5 的预注册形状逐条核对）

### 3.0 仪器与它的自证（AGENTS 第 45 条：自己的仪器也要能失败）

仪器都在 `.tmp/step7/`（不提交），**before 侧在动手之前采集**：

| 仪器 | 作用 | sha256[:16] |
| --- | --- | --- |
| `.tmp/step3b/probe_decisions.py`（沿用 3b 那台） | R1：只调 `policy.engine.evaluate`，读**决策载荷本身** | ——（沿用） |
| `.tmp/step3b/json_field_diff.py`（沿用 3b 那台） | 逐字段递归差集（dict 按 key 并集、list 按标识键对齐） | ——（沿用） |
| `.tmp/step7/probe_check_wrapper.py`（**本轮新建**） | R2：跑**真 CLI 入口**（子进程 `python -m policy.check … --json`）的三个入口，采整份 JSON | `7203ffc866b819ae` |
| `.tmp/step7/probe_e2e_payload.py`（**本轮新建**） | R4：驱动 `tools/dsh_sandbox_loop.py` 的 `main()`，四条写盘路径（pass / profile_write_denied / `--isolated-home` / dsh 缺失） | `e42337d527669c42` |
| `.tmp/step7/probe_report_tools.py`（**本轮新建**） | 两条只报告读数的三条出口（`--json` ×2 + 默认文本） | `bb79d51af62d622b` |
| `.tmp/step7/volatile.py`（**本轮新建**） | 归一化：先剥掉**已声明**的随运行变化字段，再交给 3b 的差集 | `8fbe005abb48edbc` |
| `.tmp/step7/check_forbidden.py`（**本轮新建**） | 硬约束扫描：差集里不许出现六个判定字段 | `1ba4853ba26020a6` |

**仪器的自证（"自己对自己"必须 0 条，否则这把尺子没在量东西）**：

| 对照 | 读数 |
| --- | --- |
| R1 仪器自检 | `same_tree_rerun_identical True`（两次逐字节相同，23992 B） |
| R2 三个入口 first vs second（**before 树**） | 0 / 0 / 0（`selfcontrol-before-{allow,block,rules}.json`） |
| R2 三个入口 first vs second（**after 树**，剥掉 run 身份后） | 0 / 0 / 0（`selfcontrol-after-R2-*.json`） |
| R4 四条路径 第一次 vs 第二次（before 树） | 0 / 0 / 0 / 0 |
| R4 四条路径 第一次 vs 第二次（after 树，剥掉 run 身份后） | 0 / 0 / 0 / 0 |
| **硬约束扫描** | 11 份差集里 `decision` / `violations` / `pending_findings` / `matched_rules` / `skipped_rules` / `required_action` 命中 **0** |

**归一化声明（第 50 条：剥了什么必须说出来）**：`volatile.py` 只剥两类——(a) 任何名为
`timestamp` 的叶子；(b) 以 `reading_context.run.id` / `reading_context.run.started_at`
**结尾**的路径。其余一律不剥：下表里出现的每一条都被逐条读过。

**这台仪器第一次跑的时候是错的（记下来）**：第一版按"从根开始正好等于声明的路径"匹配，
而调用方取的是子树（`cases.<名字>.payload.*`），于是 after 侧自检报了 2 条
（`reading_context.run.id` / `run.started_at` 没被剥掉）。改成**后缀匹配**后自检回到 0。
这条留在记录里，是因为"差集 2 条"当时看起来**很像**真实差异——仪器错了，读数就会骗人。

### 3.1 R1 · 判定载荷（10 个场景）：**0 条**

| 项 | 读数 |
| --- | --- |
| before / after | `.tmp/step7/decisions-before.json` / `decisions-after.json`（都 23992 B） |
| sha256 | 两份**都是** `cfad8c32c59a57a49290759d54db020c57f9cb6a07f0fbdf7d759d9f13ad4588`（与 22 号记的第 19 轮那个值相同） |
| 差集 | `.tmp/step7/R1-field-diff.json`：**count = 0** |
| 结论 | `reading_context` **不进决策载荷**；六个判定字段一个都没动（硬约束满足） |

### 3.2 R2 · `policy.check --json` 包装层（三个入口）：**各 2 条**

| 入口 | 输入 | 差集（`R2-diff-<入口>.json`） |
| --- | --- | --- |
| `allow` | `examples/good_controller.py --layer controller` | 2 条：`payload.reading_context: 新增` + `payload.output_schema_version: "1.1" → "1.2"` |
| `block`（带证据） | `examples/bad_controller.py --layer controller --dependencies repository` | 同上 2 条 |
| `rules` | `--check-rules`（`result = null`） | 同上 2 条 |

**"没有第三把钥匙"**：三个入口的 `result` / `exit_code` / `check_volume` / `evidence` 全都不在差集里。
before 侧 `.tmp/step7/wrapper-before.json`（58325 B，`0d5c0f5351257151…`）→ after 侧
`.tmp/step7/wrapper-after-D.json`（65939 B，`c62cbe912fd8f629…`）。

### 3.3 只报告两处（21 号 §2.3 的三条出口）：**2 / 2 / 0 条**

| 出口 | 差集 | 说明 |
| --- | --- | --- |
| `tools/obligations_gate.py --ledger .tmp/obligations/repo.jsonl --json` | **2 条**：`reading_context: 新增` + `report_schema_version: "1.1" → "1.2"` | `hits` / `applicable_ledgers` / `exit_code` 一个都没动 |
| `tools/exemption_expiry.py --json` | **2 条**：`reading_context: 新增` + `report_schema_version: 新增 = "1.1"`（**首次建轴**） | 除这两条外没有第三个键 |
| `tools/exemption_expiry.py`（**默认输出**） | **0 条**——逐字节相同 | `HITS: 0 / declared=8 due=0 expired=0 unprovable=0` 一个字符都没改（跨文件契约） |

**消费方没被带坏**：走 `ci_local` 真正那条只报告路径（`.tmp/step1/probe_report_only.py`）——
义务门禁读数仍是 `hits=0 / 1 个账本（不适用 1：没有账本可读，不算一次真实读数）`，
豁免到期仍是 `HITS: 0 / declared=8 due=0 expired=0 unprovable=0`，两行 `REPORT-ONLY:` 一字不变。

### 3.4 R4 · 端到端结论载荷（四条写盘路径）：**各 2 条**

| 路径 | 载荷里的 `result` / `host.sandbox` | 差集（`R4-diff-<路径>.json`） |
| --- | --- | --- |
| `pass`（两个场景都过） | `pass` / `unrestricted` | 2 条：`payload.reading_context: 新增` + `payload.schema_version: "1.1" → "1.2"` |
| `skipped_profile_write_denied`（19 号 §3.1 那条读数的形态） | `skipped` / `restricted` | 同上 2 条 |
| `isolated_home_denied`（`--isolated-home`） | `skipped` / `restricted` | 同上 2 条；`host.dsh_home = .tmp/phase-2-sandbox/dsh-home`、`temp_roots = [.tmp/phase-2-sandbox/dsh-tmp]` |
| `dsh_absent`（最小跳过载荷） | `skipped` / `unknown` | 同上 2 条；`declarations.adapter_config = {status: not_applicable}` |

**R4 的硬约束**：`result` / `environment_skipped` / 两个 scenario 的 `passed` /
`dsh_startup_denied_*` / `hook_spawn_denied_*` / `dsh_config_failure_*` **一条都没进差集**。

**用户问的那件事（"skipped 要能从结果本身读出来不是这棵树上的真机读数"）**：本轮给的答案是
	extbf{三个事实同现}——`result = "skipped"`、`environment_skipped = true`、
`host.sandbox = "restricted"`；而真机那次是 `result = "pass"` + `environment_skipped = false` +
`host.sandbox = "unrestricted"`。**没有第二个状态轴**（裁定①），差别就在 `host.sandbox` 与既有两个字段上。
受限判定读的是**真实日志**（`dsh_startup_denial()` 与 `hook_spawn_failure()`），不是"这台机器像不像受限"。

### 3.5 一条偏离（**未预注册、必须评审**）

22 号 §4.1（第 19 轮）与本轮都撞到同一个问题：`render_json` 加了 `reading_context.run` 之后，
**`--json` 的输出不再是输入的纯函数**（两次运行的 `run.id` / `run.started_at` 必然不同）。
21 号 §2.1 的键表**确实把 `run` 列进去了**（"本次进程生成；只在读数层；不进证据"），所以本轮按它落地；
代价是仓库里两条"两次运行逐字节相同"的用例必须改口径：

- `test_cli_is_reproducible` 讲的是**文本输出**（没有这两个字段）——断言一字不改，仍然逐字节相同；
- 新增 `test_json_output_is_reproducible_modulo_the_run_identity`：剥掉那两个字段后**逐字节相同**，
  并且**单独断言**这两个字段存在、形状对、且每次都不同（归一化不是放宽，是"多写一步、多断一条"）；
- `test_python_module_entry_points_agree` 同法处理。

**请评审裁定**：`run` 要不要留在 `policy.check --json` 这一份里。留：形状与 21 号 §2.1 一致、
"这份读数什么时候算的"可读，代价是上面那两条性质要按新口径表述；不留（写 `not_applicable`）：
`--json` 保持纯函数，但 21 号 §2.1 的键表要改一笔。

---

## 4 第 4 步：门禁（`--full`）

### 4.1 先把"这次要放宽沙箱"的理由写在**跑之前**

**事实（第 0 步环境自检 + 第 19 轮 22 号 §4.1 的同一条读数）**：

| # | 读数 |
| --- | --- |
| 1 | 本会话的文件策略是 **workspace-write**；在这个上下文里 **`.tmp/tmp/pytest-of-ZNM` 连 `os.scandir` 都读不了**（`PermissionError: [WinError 5] 拒绝访问`）——本轮实测：`Get-ChildItem .tmp/tmp/pytest-of-ZNM -Force` → "访问被拒绝" |
| 2 | 那是**上一次不受限运行留下的 ACL 残留**（19 号 §4.1 记过同一现象：`mkdtemp` / `mode=0o700` 建出来的目录，同进程内再写就 EACCES，事后连 ACL 都读不了，DSH 自带的诊断脚本判 `UNREADABLE` 并 `stop`，**不推断修复**） |
| 3 | 门禁的 pytest 步骤用 `-n auto --dist loadfile`（xdist）。xdist 每个 worker 都要 `getbasetemp()`，而它先 `os.scandir` 那个残留目录 → 本轮实测**整批 INTERNALERROR**（`make_numbered_dir_with_cleanup` → `PermissionError [WinError 5]`），不是任何一条用例失败 |
| 4 | 本轮**不**用 pytest 全量跑代替门禁的理由也在这里：在 workspace-write 下它跑不起来；而"跑得起来"的那个上下文正是这次要申请的一次放宽 |

**这次放宽要做两件事，都写在同一次执行里**：
① 删掉 `.tmp/tmp/pytest-of-*` 这个**沙箱 ACL 残留**（只动 pytest 的落点目录，删之前先数一遍
能读到的东西，删之后报 `removed / kept`）；② 跑一次
`python tools/ci_local.py --full --python .venv/Scripts/python.exe`，记录**显式退出码**与**耗时**。

**理由一句话**：这不是"让门禁变绿"——门禁在 workspace-write 下**根本起不来**（第 3 条是 xdist 的
收集期崩溃，不是断言失败），而"起不来"既不是通过也不是失败；把它报成"门禁红了"是错的，
拿它当"已验证"更错。放宽的是**执行它的环境**，不是任何一条检查的口径。

**事后必记**：实际用了什么模式、删了什么（数量）、退出码、耗时、快照比对结果（见 §4.2 / §4.3）。
