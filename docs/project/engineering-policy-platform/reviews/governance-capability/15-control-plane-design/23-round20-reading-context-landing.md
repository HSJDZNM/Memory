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


### 4.2 这次放宽**实际是怎么发生的**（事后记录，照 4.1 的承诺）

4.1 写下的计划是"申请一次显式放宽"。**实际过程与计划不同，照实记**：

| # | 动作 | 结果 |
| --- | --- | --- |
| 1 | 带 `danger-full-access` 的放宽请求（后台启动门禁，deadline 120s） | **挂到 deadline**：请求没有被应答，命令**没有启动**。副作用清点：无日志、无作业、`.tmp/tmp/pytest-of-ZNM` 原样、`git status` 空 |
| 2 | 同一条命令重试（deadline 600s） | 同上：**挂到 deadline，什么都没发生**（残留目录仍在、无 `.tmp/step7/ci-local-full-r20.log`、`job_list` 里没有新作业） |
| 3 | 探针（`Write-Output`，deadline 60s） | 挂到 deadline——**放宽通道在这一刻不可达** |
| 4 | **程序级**放宽 + 短 deadline | 返回了，且沙箱报告是 `mode=danger-full-access`：**这一刻放宽生效**。用它做了两件事之一——删掉 `.tmp/tmp/pytest-of-ZNM`（`still there? False`，`removed=1 / kept=0`） |
| 5 | 使用者把会话文件策略改成 **danger-full-access**（审批提示关闭） | 门禁在这个上下文里跑；**此后我没有再申请任何放宽** |

**放宽用在了哪两件事上**：① 删除 pytest 的 ACL 残留 `.tmp/tmp/pytest-of-ZNM`（它是第 3 步
`getbasetemp()` 崩溃的直接原因，**只动 pytest 的落点目录**）；② 跑**一次**全量门禁。
**没有**用在任何仓库文件的写入上：本轮所有代码 / 文档 / 测试改动**只用 `write` / `edit` 落树**，
按路径暂存，没有 `--no-verify`、没有强推、没有 `cleanup.py`、没有直接跑 `tools/dsh_sandbox_loop.py`。

**为什么不是"为了让门禁变绿才放宽"**：4.1 第 1–3 条是**独立测出来**的——
`os.mkdir(path, 0o700)` 建出来的目录**同进程内**就写不进去、连 `os.scandir` 都被拒
（`.tmp/step7/mode_probe.py`，同一目录下 `mkdir` 默认 mode 全绿而 `0o700` 全红）；
`pytest -n auto` 因此**在收集期**`INTERNALERROR`（`PermissionError [WinError 5]` 指向那个残留目录），
不是任何一条用例失败。**"跑不起来"既不是通过也不是失败**，把它读成"门禁红了"是错的。

### 4.3 门禁读数（`--full`）

**命令**（逐字）：`python tools/ci_local.py --full --python .venv/Scripts/python.exe`
**树**：HEAD = `45b9962`（工作树干净、无并发：跑前 `git status --porcelain -uall` 为空、`job_list` 里没有别的门禁作业）。

| 项 | 读数 |
| --- | --- |
| **显式退出码** | **0** —— `本机检查全部通过（31 步）；只报告 2 步（非零退出不计入失败）` |
| **耗时** | 门禁自己的汇总行 **5m 02.9s**（`=== 执行耗时（合计 5m 02.9s，33 步，最慢 5 步）===`）；外层秒表 **303.7 s** |
| 选组 | `改动文件 811 个；执行 31 步（本机跳过 11 步，登记豁免 2 步，只报告 2 步）` |
| 大头 | pytest **1m 52.0s**（37.0%）→ notebooks **1m 18.5s**（25.9%）→ 编排闭环 **1m 08.9s**（22.8%）→ 阶段验收证据 8.1s → 验证器闭环 7.5s |
| 与第 19 轮对照 | 同一条命令在 `d2b906f` 上是 **4m 32.6s / 31 步**；本轮 **5m 02.9s / 31 步**（**不相减**：改动面、机器负载都不同）。**能对照的是同一步**：pytest 1m45.7s → 1m52.0s（+6.3s）、notebooks 1m05.9s → 1m18.5s（+12.6s）——两处都含 `reading_context` 新引入的树摘要开销（每次 `--json` 走一次轮次级封条，实测 961 文件 / 1.84s），**远小于事前担心的量级**，因为 pytest 是按文件并行、这笔开销落在多个 worker 上 |
| 只报告步骤 1 | 义务门禁：0 命中（退出码 0），读数 `hits=0 / 1 个账本（不适用 1：没有账本可读，不算一次真实读数）` |
| 只报告步骤 2 | 豁免到期：0 命中（退出码 0），读数 `HITS: 0 / declared=8 due=0 expired=0 unprovable=0` |
| 日志 | `.tmp/step7/ci-local-full-r20.log`（4956 B，sha256 `cbae49f88f7ae8d51f0f7982d0d5b7667d741fa2c380f49e6b4fcad15a61d3be`）+ `.tmp/ci-local-logs/` 下 **33 个**分步日志 |
| 第 9 步（沙箱闭环） | `ok 1.7s`；产物 `result=skipped`、`environment_skipped=true`、`dsh_startup_denied_kind=profile_write_denied` —— **受限上下文里的读数，不是真机读数**（见 §4.5） |

### 4.4 跑前快照 → 跑后逐个文件比对（第 9 步必然跑 `tools/dsh_sandbox_loop.py`）

**禁令照样遵守**：**没有**直接跑 `tools/dsh_sandbox_loop.py`；它只作为门禁第 9 步被执行。
跑前快照 `.tmp/e2e/before-gate-r20/20260930T204619/manifest.json`（受控目录 43 个文件的
路径 / 字节 / mtime / sha256 + 产物副本 + HEAD + `git status`），跑后逐文件比对：

| 项 | 读数 |
| --- | --- |
| 受控目录 | before/after 都是 **43 个文件**；**逐字节相同 41、内容变了 2、新增 0、消失 0** |
| 变了的两个 | `.tmp/phase-2-sandbox/logs/{allow-run,block-run}.txt`：`2ab540972f1d1a75… → 2dc1a97ba8eea1c8…`（**两份内容相同**：都是这次 dsh 子进程的原样输出）。第 9 步这次真的起了 dsh（`profile_write_denied` 要在 dsh 启动后才能在日志里读出来），所以日志被重写；第 19 轮那次 `dsh_argv()` 直接返回 None，没起 dsh，所以这两个文件没动 |
| 仓库侧 | HEAD 仍 `45b9962`；`git status --porcelain -uall` **空** |
| 这一步证明什么 | 门禁**没有动仓库**、**没有动受控项目的源码与配置**；它**不**证明端到端闭环跑通了（那是环境跳过） |

### 4.5 R4 在**真产物**上的对照：4 条 = 2 条预注册 + **2 条环境归因漂移**

合成探针（同一环境、两边都固定）给出的是预注册的 **2 条**。这里再补一次**真产物**对照——
before 是门禁前那份（`.tmp/e2e/before-gate-r20/…/phase-2-sandbox-result.before.json`），
after 是门禁第 9 步刚写出的那份：

| # | 差集 | 判定 |
| --- | --- | --- |
| 1 | `reading_context: 新增` | **预注册** |
| 2 | `schema_version: "1.1" → "1.2"` | **预注册** |
| 3 | `dsh_startup_denied_home_root_evidence[0].source: "default:$HOME/.dsh" → "env:DSH_HOME"` | **预期外**——环境归因漂移 |
| 4 | `…[0].evidence: "$HOME/.dsh（平台默认）" → "环境变量 DSH_HOME"` | 同上 |

**第 3、4 条不是这次改动带来的**，证明是一台两分钟的归因实验
（`.tmp/step7/probe_home_root_attribution.py`，读数 `.tmp/step7/home-root-attribution.json`）：
**同一段日志、同一份代码**，只改 `DSH_HOME` 在不在——

| 条件 | `source` | `evidence` | 被拒路径 / 类别 |
| --- | --- | --- | --- |
| `DSH_HOME` 在 | `env:DSH_HOME` | 环境变量 DSH_HOME | `C:\\Users\\ZNM\\.dsh` / `profile_write_denied` |
| `DSH_HOME` 不在 | `default:$HOME/.dsh` | `$HOME/.dsh（平台默认）` | **同上（不一样）** |

before 那份产物的来源是使用者本机 pre-push 钩子那次运行（当时 env 里没有 `DSH_HOME`），
after 是本次门禁第 9 步（本会话的 env 里有 `DSH_HOME=C:\\Users\\ZNM\\.dsh`）。

**这条要评审裁定**：21 号 §5 的 R4 预注册写的是"每份 2 条"，而它没有声明"两份产物必须在**同一个环境**里采"。
真产物对照做不到这一点（before 是别的上下文写的），于是"环境变了"会以**诊断键**的形式出现在差集里——
**这恰好是 `reading_context` 存在的理由，却也让"差集条数"这个判据在真产物上不可用**。
两个可选处置（都不由本线单方面决定）：① 预注册补一句"真产物对照必须同环境，否则按合成探针为准"；
② R4 在真产物上只做**弱对照**（只查硬约束那几个字段在不在差集里）。


---

## 5 未核实 / 没做 / 请评审裁定

### 5.1 未核实（逐条）

1. **真机 pass 的原件字节**：原件已被 pre-push 那次 skipped 运行覆盖，不可复原；登记的是
   **转录件**（§2）。因此"pass 侧的 `reading_context`"**没有真机产物**——它只有合成探针（R4 的
   `pass` 路径）与源码两处证据；**"真机上跑一遍会写出 `host.sandbox=unrestricted`"这件事本轮没有实测**。
2. **`host.sandbox` 在 POSIX 上的判据**：21 号 §9 第 4 条把这条列在未核实里，本轮**仍然是未核实**——
   只在 Windows ACL 沙箱上采到读数（`profile_write_denied` / `sandbox_pipe_stdio_denied`）。
3. **受限判据比 21 号 §3 宽了一档**：§3 写的是"本次是否发生过**写工作区之外被拒**"，
   本轮把 `sandbox_pipe_stdio_denied`（禁止命名管道，spawn EPERM）**也算 restricted**。
   理由写在 `sandbox_state()` 的 docstring 里：把它记成 `unrestricted` 是一句没有依据的话；
   但这是**我加宽的**，请评审确认或改回。
4. **本轮的门禁读数只属于这台机器这个上下文**：CI 上没有 `.tmp/tmp/pytest-of-*` 的 ACL 残留，
   §4.1 那三条前置读数**没有在 CI 上复核过**。
5. **`tools/phase_evidence.py` 的键集合探针没有重跑**：它按固定键复制子载荷这件事是第 19 轮的读数
   （`.tmp/step2/probe_phase_evidence_keys.py`），本轮没有重跑，也没有动它（裁定③）。
6. **没有在`--hook`形态下跑过**：门禁只跑了 `--full`；pre-push 钩子的行为本轮没有实测。

### 5.2 没做（裁定④与本轮禁令的落点）

| 项 | 状态 | 依据 |
| --- | --- | --- |
| 覆盖账（`adapters.wiring.WIRING_SCHEMA_VERSION`） | **一个字没动**（仍是 1.1） | 裁定④：留到下一轮 |
| Hook 审计记录（`AUDIT_SCHEMA_VERSION` 1.2 → 1.3） | **一个字没动**（仍是 1.2） | 裁定④：放最后，本轮不做 |
| 阶段证据透传（`tools/phase_evidence.py`） | **一个字没动** | 裁定③：归 CI 线 |
| `REPORT-ONLY:` 控制台行（`tools/ci_local.py`） | **一个字没动** | 裁定② + 文件归属（CI 线） |
| `tools/ci_local.py` / `tests/unit/test_ci_local*.py` | **一个字没动** | 文件归属（CI 线） |
| `git push` / `git fetch` | **没有** | 指令：不要尝试 push/fetch |
| `git add -f` / `--no-verify` / 强推 / `tools/cleanup.py` | **没有** | 纪律 |

### 5.3 请评审裁定

1. **`reading_context.run` 要不要留在 `policy.check --json` 这一份里**（§3.5）：留＝与 21 号 §2.1
   的键表一致、代价是 `--json` 不再是输入的纯函数；不留（写 `not_applicable`）＝保住纯函数、
   但 21 号 §2.1 的键表要改一笔。
2. **R4 的预注册要不要补"真产物对照必须同环境"**（§4.5）：补＝真产物对照的"条数"判据才成立；
   不补＝真产物上只能做弱对照（只查硬约束字段在不在差集里），条数交给合成探针。
3. **`host.sandbox` 的受限判据要不要收回到"只有写被拒才算"**（§5.1 第 3 条）。
4. **`check` 路径的 `host.sandbox` 恒为 `unknown`**：CLI 不探测沙箱（探测要有副作用），
   所以那里永远是 `unknown`。若评审要求它可读，需要一条**显式声明**（环境变量或配置），
   本线不擅自猜。

### 5.4 预算对账（`git show --numstat`，口径 = 新增行）

| 桶 | 21 号 §8 的已花 | 本轮（A–E1 五个提交） | 台阶 4 累计 | 复核线（1.5×） | 硬上限（×2.5） |
| --- | --- | --- | --- | --- | --- |
| src | 0 | **463** | **463** | 1 950 | 3 250 |
| tests | 598 | **543** | **1 141** | 2 100 | 3 500 |
| tools | 641 | **221** | **862** | ——（方案 §7 的表里没有这一桶，照旧单列） | —— |
| 数据 / 文档 | 128 | 274 | 402 | —— | —— |

**逐提交**：`3848e36` docs 93；`d742775` src 380 / tests 364 / tools 120 / docs 10；
`f6b5a4b` tests 92 / tools 92 / docs 8；`3683761` src 83 / tests 87 / tools 9 / docs 32；
`45b9962` docs 131。**都在复核线之内**，没有触发"超过 1.5 倍就停下复核"。

---

## 6 复现命令（只读或只写 `.tmp`）

```powershell
# 0 环境自检 + 合并读数（应为 0：feat 上没有新提交）
git rev-list --count HEAD..origin/feat/rules-and-os-platform

# 1 仪器的自证（三个"自己对自己"，都应 0 条）
.venv\Scripts\python.exe .tmp/step7/volatile.py --before .tmp/step7/wrapper-before.json --after .tmp/step7/wrapper-before.json --before-path entries.allow.first --after-path entries.allow.second
.venv\Scripts\python.exe .tmp/step7/volatile.py --before .tmp/step7/e2e-before.json --after .tmp/step7/e2e-before-run2.json --before-path cases.pass --after-path cases.pass

# 2 R1（决策载荷 0 条）与硬约束
.venv\Scripts\python.exe .tmp/step3b/probe_decisions.py --out .tmp/step7/decisions-after.json
.venv\Scripts\python.exe .tmp/step3b/json_field_diff.py --before .tmp/step7/decisions-before.json --after .tmp/step7/decisions-after.json
.venv\Scripts\python.exe .tmp/step7/check_forbidden.py

# 3 R2（check 包装层；三个入口各 2 条）与 R4（端到端四条路径各 2 条）
.venv\Scripts\python.exe .tmp/step7/probe_check_wrapper.py --out .tmp/step7/wrapper-after-D.json
.venv\Scripts\python.exe .tmp/step7/probe_e2e_payload.py --out .tmp/step7/e2e-after-B.json
.venv\Scripts\python.exe .tmp/step7/volatile.py --before .tmp/step7/e2e-before.json --after .tmp/step7/e2e-after-B.json --before-path cases.pass --after-path cases.pass

# 4 只报告三条出口 + 归因实验
.venv\Scripts\python.exe .tmp/step7/probe_report_tools.py --out .tmp/step7/report-after-C.json
.venv\Scripts\python.exe .tmp/step7/probe_home_root_attribution.py

# 5 门禁（本轮读数：退出码 0 / 5m 02.9s / 33 步）
python tools/ci_local.py --full --python .venv/Scripts/python.exe

# 6 跑前快照 / 跑后比对
.venv\Scripts\python.exe .tmp/step7/snapshot_before_gate.py
.venv\Scripts\python.exe .tmp/step7/compare_after_gate.py
```

---

## 7 本轮改动的文件（按提交）

| 提交 | 文件 | 说明 |
| --- | --- | --- |
| `3848e36` | 21 号设计稿（§9.1 + 抬头补记）、23 号（新建）、设计目录 `README.md` | 四条裁定落进 21 号 §9.1；真机读数登记 |
| `d742775` | **`src/provenance/reading_context.py`（新）**、`tools/dsh_sandbox_loop.py`、`tests/unit/test_reading_context.py`（新）、`tests/contract/test_reading_context_digest_parity.py`（新）、`tests/integration/test_dsh_sandbox_loop.py`、`AGENTS.md`、`tools/README.md` | 统一形状**只有一份实现**；端到端两条写盘路径 |
| `f6b5a4b` | `tools/obligations_gate.py`、`tools/exemption_expiry.py`、`tests/integration/test_obligations_gate.py`、`tests/unit/test_exemption_expiry.py`、`AGENTS.md`、`tools/README.md` | 只报告两处；豁免到期**首建版本轴** |
| `3683761` | `src/policy/check.py`、`tests/integration/test_cli.py`、`README.md`、`docs/project/architecture/使用说明.md`、`tools/build_learning_notebook.py`、`docs/project/learning/phase-0/walkthrough.{py,ipynb}`、`AGENTS.md` | `--json` 外层包装 + 生成物重跑（`--check` 通过） |
| `45b9962` | 23 号、设计目录 `README.md` | R-d 读数与门禁前置说明（**跑门禁之前**提交） |
| 本提交 | 23 号（§4.2–§4.5、§5–§7）、设计目录 `README.md` | 门禁读数、放宽的事后记录、未核实与评审点 |

**没有碰过的文件**（列出来是为了说明"一个字都没动"）：`tools/ci_local.py`、
`tests/unit/test_ci_local*.py`、`tools/phase_evidence.py`、`src/adapters/wiring.py`、
`src/adapters/dsh/hooks.py`、`AGENTS.md` 的其余条目、`.github/workflows/*`、
`requirements*`、`validation/validators.yaml`。

---

**本文件的两半是两次提交**：§1–§4.1 在 `45b9962`（门禁之前），§4.2–§7 在本提交（门禁之后）。
切开写是刻意的：§4.1 是**事先**写下的放宽理由，事后补写就变成了"先射箭再画靶"。
