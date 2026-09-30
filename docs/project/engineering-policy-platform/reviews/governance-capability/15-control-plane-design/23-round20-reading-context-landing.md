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

## 8 评审裁定（2026-09-30 · 第二轮）与落地

§5.3 的四条"请评审裁定"已由使用者裁定，并同时写进 21 号 **§9.2**（原问题留在 21 号与本节，
便于复核"裁定的是不是当初问的那件事"）。本节只记**裁定 + 落地**；落地读数（R-d 与门禁）见 §9。

| # | §5.3 的问题 | 裁定 | 落地 |
| --- | --- | --- | --- |
| 1 | `reading_context.run` 要不要留在 `policy.check --json` 里 | **去掉**：违反 AGENTS 第 19 条的同一条纪律（包装层要保持"输入的纯函数"），且没有消费方；1.2 **尚未发布** → **在 1.2 内修、不升版**；端到端与只报告两处**保留** `run` | `src/provenance/reading_context.py` 的 `build(include_run=False)`（六处载荷里**唯一**的一份）；`tests/integration/test_cli.py` 的逐字节用例 |
| 2 | R4 预注册要不要补"真产物对照必须同环境" | **补**：§4.5 的 2 条归因漂移就是证据——跨环境采来的两份真产物会把环境差异算成改动 | 21 号 §5 的 R4 行加补记；做不到同环境时**条数以合成探针为准** |
| 3 | `host.sandbox` 的受限判据要不要收回到"只有写被拒才算" | **不收回**：`sandbox_pipe_stdio_denied`（禁止管道 stdio 的 spawn 拒绝）也算 `restricted` | 21 号 §3 的判据句同步改 |
| 4 | `check` 路径的 `host.sandbox` 恒为 `unknown` | **接受**：CLI 不探测沙箱（探测要有副作用）；要让它可读必须另给一条**显式声明**，本线不擅自猜 | 不变 |
| 另 | `tree.digest` 与实现对齐 | 用 `workspace_tree_digest`（轮次级封条、带声明的排除项） | 21 号 §2.1 同步改 |

**这五项都不改任何 allow / block、不新增阻断步骤、不改任何退出码。**

**合并（第 0 步）**：本轮起点是 `refactor/control-plane` @ `3ac54bd`（工作树干净）。按指令
`git merge origin/feat/rules-and-os-platform`（**不 rebase**）：上游那一条是
`13bb718 fix(ci_local): 只报告结论的命中数取自读数，不由退出码推断`，只动
`tools/ci_local.py` 与 `tests/unit/test_ci_local_report_only.py`（**CI 线的两个文件**），
与本线改动不相交，**无冲突**（合并提交 `6fc0595`，两个文件 +133 / −14）。
本线**没有**碰 `tools/ci_local.py` / `tests/unit/test_ci_local*.py` / `tools/phase_evidence.py`
一个字符。

**裁定④ 的其余两件**：第 20 轮把覆盖账与 Hook 审计留到"下一轮"。本轮（第 21 轮）**落了覆盖账**
（`WIRING_SCHEMA_VERSION` 1.1 → 1.2，见 §9.3）；**Hook 审计（`AUDIT_SCHEMA_VERSION` 1.2 → 1.3）
仍未动**——按指令，它等 `reading_context` 这一批在 `feat/rules-and-os-platform` 上跑满一轮再做。
D-2 冻结的部分（`account` / `differences` / `governs` 轴）照旧不动。

---

## 9 第 21 轮 · 落地读数（R-d）与门禁

- **树**：HEAD = `e71b5e0`（跑门禁前 `git status --porcelain -uall` 空；无并发门禁）。
- **仪器落点**：`.tmp/step8/`（不提交）。除沿用 3b 那台（`.tmp/step3b/probe_decisions.py` +
  `.tmp/step3b/json_field_diff.py`），本轮新增：`probe_byte_identity.py`（裁定①的直接判据）、
  `probe_wiring_payload.py`（覆盖账载荷的 before/after）、`probe_step1_readings.py` /
  `probe_step2_readings.py`（自证 + 硬约束扫描）、`measure_wiring_cost.py`（旁注开销）。

### 9.1 裁定①：`check --json` 去掉 run（提交 `6255057`）

| 尺子 | 读数 |
| --- | --- |
| 决策载荷（R1，10 个场景） | **0 条差异**：before / after 两份都是 23992 B、sha256 都是 `cfad8c32c59a57a4…`（与 22 号记的第 19 轮那个值相同） |
| 包装层（65939 B → 65015 B） | **6 条**，全部是同一字段 `reading_context.run: 删除`（3 个入口 allow / block / `--check-rules` × 2 份读数）；**没有第二个键变化** |
| 逐字节可重现（裁定①的判据） | 三个入口各跑两次，stdout **逐字节相同**（10593 / 10770 / 4298 B），且 `reading_context` 只有 4 个键（`source` / `tree` / `declarations` / `host`），**没有 run** |
| 仪器的自证（AGENTS 第 45 条） | before 侧同一份读数的 first vs second **6 条**（正是 `run.id` / `run.started_at`）——尺子对随运行变化的字段不瞎；after 侧 **0 条** |
| 硬约束扫描 | 差集里 `decision` / `violations` / `pending_findings` / `matched_rules` / `skipped_rules` / `required_action` 命中 **0** |

**口径**：那 6 条是"每份读数各一条"，不是"6 个字段"——被删的只有一个键（`.tmp/step8/R2b-diff-step1.json`）。

### 9.2 裁定②③④与 `tree.digest`：只动文档与判据（同一提交 `6255057`）

21 号 §2.1（run 不在这份里；`tree.digest` 改 `workspace_tree_digest`）、§3（run 是有条件的；
受限判据含 `sandbox_pipe_stdio_denied`）、§5（R4 真产物对照必须同环境）、新增 §9.2（四项裁定），
外加 AGENTS 第 55 条、README、使用说明同步。**没有第二处代码改动**：这三条的落点是文档与判据措辞。

### 9.3 覆盖账 `wiring --json`（提交 `e71b5e0`，21 号 §2.5）

| 尺子 | 读数 |
| --- | --- |
| 载荷级差集 | **4 条** = 2 条（`reading_context: 新增`、`wiring_schema_version: "1.1" → "1.2"`）× 2 份读数（first / second）；没有第三条 |
| 探针**文件级**那份 | 6 条 = 上面 4 条 + 2 条**仪器自己的** `stdout_bytes` 计数（24068 → 24831）——不是载荷变化 |
| after 侧 first vs second | **2 条**：`reading_context.run.id` / `run.started_at`——这一份**保留 run**（裁定①只对 check 生效），同时是"尺子能报出 run"的自证 |
| before 侧 first vs second | **0 条**（`--now` 钉死之后这份报告逐字节稳定；不钉死时 `age_seconds` 会随墙钟变，两次运行的字节不同） |
| 决策载荷 | **0 条差异**（sha256 仍是 `cfad8c32…`） |
| 旁注开销 | `wiring` 文本 **0.80 s** → `wiring --json` **1.81 s**（中位数，各 3 次）：**+1.01 s**，就是树摘要那一步；它只发生在 `--json` 这条出口 |
| 硬约束扫描 | 0 命中（同上六个字段） |

### 9.4 门禁（`--full`）

**命令（逐字）**：`python tools/ci_local.py --full --python .venv/Scripts/python.exe`
**树**：HEAD = `e71b5e0`（跑前工作树空；`.tmp/ci-local.lock` 没有被持有，本会话没有别的门禁作业）。

| 项 | 读数 |
| --- | --- |
| **显式退出码** | **0** —— `本机检查全部通过（31 步）；只报告 2 步（非零退出不计入失败）` |
| **耗时** | 门禁自己的汇总行 **5m 35.6s**（`=== 执行耗时（合计 5m 35.6s，33 步，最慢 5 步）===`）；外层秒表 **336.4 s** |
| 选组 | `改动文件 811 个；执行 31 步（本机跳过 11 步，登记豁免 2 步，只报告 2 步）` |
| 大头 | pytest **2m 06.6s**（37.7%）→ notebooks **1m 33.0s**（27.7%）→ 编排闭环 **1m 12.6s**（21.6%）→ 阶段验收证据 10.6s → 验证器闭环 6.7s |
| 与第 20 轮对照 | 同一条命令在 `45b9962` 上是 **5m 02.9s**（汇总行同为 33 步；"执行 31 步"是选组口径，两个数不是一回事），本轮 **5m 35.6s**（同样 33 / 31）（**不相减**：改动面与机器负载都不同）。能对照的是同一步：pytest 1m52.0s → 2m06.6s（+14.6s）、notebooks 1m18.5s → 1m33.0s（+14.5s）。**已归因的一处**：覆盖账契约用例每次 `wiring --json` 多走一次树摘要（实测 +1.01 s/次，见 §9.3）；**其余差异（notebooks 那一步、机器负载）未归因**，不写"就是它" |
| 只报告步骤 1 | 义务门禁：0 命中（退出码 0），读数 `hits=0 / 1 个账本（不适用 1：没有账本可读，不算一次真实读数）` |
| 只报告步骤 2 | 豁免到期：0 命中（退出码 0），读数 `HITS: 0 / declared=8 due=0 expired=0 unprovable=0` |
| 日志 | `.tmp/step8/ci-local-full-r21.log`（4958 B，sha256 `107c0c03b7531132…`）+ `.tmp/ci-local-logs/` 下 **33 个**分步日志 |
| 第 9 步（沙箱闭环） | `ok 1.5s`；产物 `result=skipped`、`environment_skipped=true`、`dsh_startup_denied_kind=profile_write_denied`（被拒路径 `C:\Users\ZNM\.dsh\profiles\headless\cordis.yml`，`syscall=open`）、`host.sandbox=restricted`、`tree.revision=e71b5e0…` —— **受限上下文里的读数，不是真机读数**（第 45 条：环境跳过不是通过） |

### 9.5 跑前快照 → 跑后逐个文件比对（第 9 步必然跑 `tools/dsh_sandbox_loop.py`）

**禁令照样遵守**：**没有**直接跑 `tools/dsh_sandbox_loop.py`；它只作为门禁第 9 步被执行。
跑前快照 `.tmp/e2e/before-gate-r21/20260930T213715/manifest.json`（受控目录 43 个文件的
路径 / 字节 / mtime / sha256 + 产物副本 + HEAD + `git status`），跑后逐文件比对：

| 项 | 读数 |
| --- | --- |
| 受控目录 | before/after 都是 **43 个文件**；内容**逐字节相同 43**、变了 0、新增 0、消失 0 |
| 但"内容相同"不等于"没有被重写" | `.tmp/phase-2-sandbox/logs/{allow-run,block-run}.txt` 的 **mtime 变了**（21:08:33 → 21:39:48，正是第 9 步的时刻），sha256 两次都是 `2dc1a97b…`——**这两个文件被重写成了同样的内容**。两件事分开报，免得把"没变"读成"没跑" |
| 产物 | `.tmp/artifacts/phase-2-sandbox-result.json`：3121 B；`db2fa89c…` → `31e419f7…`（**这一份每次都重写**：`timestamp` 与 `reading_context.run` 必然不同）；`result=skipped` / `environment_skipped=true` 两边一致 |
| 与第 20 轮的不同 | 第 20 轮那两个日志文件**内容**也变了（before 来自 env 里没有 `DSH_HOME` 的 pre-push 运行）；本轮 before 与 after 同环境，所以内容相同。这正是裁定②要的那句话：**真产物对照必须同环境**，否则环境差异会混进差集 |
| 仓库侧 | HEAD 仍 `e71b5e0`；`git status --porcelain -uall` **空** |
| 这一步证明什么 | 门禁**没有动仓库**、**没有动受控项目的源码与配置**；它**不**证明端到端闭环跑通了（那是环境跳过） |

### 9.6 未核实 / 待评审

1. **真机端到端仍然没有真机读数**：本轮第 9 步与第 20 轮一样是 `profile_write_denied` 的环境跳过；
   `host.sandbox=unrestricted` 这一档**只在合成探针里出现过**（第 20 轮 R4 的 `pass` 路径），真机上没采到。
2. **pytest 增量的归因只做了一半**：已测的是覆盖账每次 `--json` 的 +1.01 s；"pytest 一共慢了多少、
   其中多少是这次改动"**没有逐用例计时**，写在这里的 14.6 s 是**两次门禁的差**，不是归因。
3. **`wiring --json` 的 before 侧是在改动前采的**：两次采集用同一条命令、同一个 `--now`、
   同一台机器（相隔约 10 分钟）；期间的机器状态变化**没有单独取证**。
4. **本轮没有跑 `--hook` 形态**：只跑了 `--full`；pre-push 的行为没有实测。
5. **`tools/ci_local.py` / `tests/unit/test_ci_local*.py` / `tools/phase_evidence.py` 一个字都没动**
   （文件归属），`git push` / `git fetch` 没有做。

---

## 10 背景登记：真机 `unrestricted` 端到端与 `7864dd2` 的 pre-push 门禁（第 22 轮补记）

这一节登记两件**由使用者在本机产生**的读数，用来关闭 §9.6 的两条未核实。口径分开写：
「我复核了什么」与「使用者提供了什么、原件我没看到」不混在一起。

### 10.1 真机 `--isolated-home` 端到端：`result=pass`、`host.sandbox=unrestricted`

| 项 | 读数 |
| --- | --- |
| 时刻 | `timestamp = 2026-09-30T13:48:23.294459Z`（本机 21:48:23 +08:00） |
| 树 | `reading_context.tree.revision = 7864dd247cb8c98dedf2c26b55ebcd02a0092671` —— 与第 22 轮起点 HEAD（`7864dd2`）**逐字符相同** |
| 结论 | `result = pass`、`environment_skipped = false`、`schema_version = "1.2"`、`host.sandbox = "unrestricted"`、`host.isolated_home = true`、`host.dsh_home = .tmp/phase-2-sandbox/dsh-home` |
| 两个场景 | `block_scenario.passed = true`（`file_sha256_before == after == 53b53a25162599fc…`，**文件未变**）；`allow_scenario.passed = true`（`53b53a25162599fc… → 2972725e717804ec…`，**改了一次**）；两者 `rule_set_hash = sha256:50202675b6ca4013…` |
| 原件 | `.tmp/e2e/pass-20260930T214825.json`（**3603 B**，sha256 `da1279af9f86e0c082d3fb782aa3b2e0…`，mtime `2026-09-30T13:48:25.282163Z`）：使用者用 `Copy-Item` 从 `.tmp/artifacts/phase-2-sandbox-result.json` 复制的**原字节**——与前两份**转录件**（§2 的手抄件）不同，这份可逐字节复核 |
| 被覆盖的证据 | 现 `.tmp/artifacts/phase-2-sandbox-result.json`（3122 B，mtime `13:50:46.691519Z`）已经是随后那次运行写出的 `result = skipped` / `host.sandbox = restricted` / `dsh_startup_denied_kind = profile_write_denied` —— 与 §2 第 2 条记的覆盖现象同型，区别是这次原件**留下来了** |

**我复核了什么**：上表每一行的值都来自原件本身（`tree.digest = sha256:d1740cc8dca6853c1046abc5ca98272dbe282455fc38e582b7d6d087ff4b4778`）。
**这一节关闭的是 §9.6 第 1 条**（"真机端到端仍然没有真机读数"）——而且补上了 §5.1 第 1 条缺的那件事：
真机 pass 的 `reading_context` 现在有**真产物**（`host.sandbox=unrestricted`），不再只有合成探针。
「合成探针预测过 unrestricted」与「真机上采到了 unrestricted」是两条不同的证据，这里是后者。

### 10.2 `--hook` 形态的门禁在 `7864dd2` 上跑过

| 项 | 读数 |
| --- | --- |
| 使用者提供 | 推送时 pre-push（`--hook`）门禁在 `7864dd2` 上**通过** |
| 我复核到的旁证 | `.tmp/ci-local-logs/` 下 **32 个**分步日志：`01-repository-consistency-gate.log` 起于 **21:48:26**，`32-exemption-expiry-report-report-only.log` 止于 **21:52:30**；`.tmp/ci-local.lock` 的 mtime 同为 **21:52:30**；第 9 步（沙箱闭环）的产物被重写为 `result=skipped`（mtime `13:50:46Z` = 21:50:46 +08:00）。32 份日志里**没有** `INTERNALERROR` / `Traceback`（命中的 `FAIL` 字样都是用例名与 `[PASS]` 标记） |
| 我**没有**看到的 | 那次运行的**汇总行与退出码**（打在终端上，没有落盘）。因此"退出码 0"按**使用者提供**登记 |
| 形态差别 | `--hook` 与 `--full` 的**步集不同**：`FULL_ONLY_STEPS`（学习手册同步）在 `--hook` 下不执行 |

**这一节关闭的是 §9.6 第 4 条**（"本轮没有跑 `--hook` 形态"）。`--full` 在 `7864dd2` 上的读数
是**第 22 轮**的事，见 §11。

---

## 11 第 22 轮 · 审计 `reading_context`（`AUDIT_SCHEMA_VERSION` 1.2 → 1.3）落地读数与门禁

- **树**：HEAD = `7f8f77a`（跑门禁前 `git status --porcelain -uall` 空、`.tmp/ci-local.lock` 未被持有）。
- **本轮的提交**：`15be129`（§10 背景登记）、`7f8f77a`（本件：审计记录加 `reading_context` 与注册表摘要）、
  本提交（本文与设计目录索引）。
- **仪器落点**：`.tmp/step9/`（不提交）。

### 11.0 仪器与它的自证（AGENTS 第 45 条）

| 仪器 | 作用 | 规模 |
| --- | --- | --- |
| `.tmp/step9/probe_audit_records.py`（新） | 11 个 dsh 事件 fixture × **5 次** × 3 个模式（evidence / plain / paired），走真 Hook 路径，采**落盘后的记录**、单次调用耗时与字节 | 每轮 **120 次调用** |
| `extract_records.py`（新） | 把审计记录从计时载荷里抽出来——计时每次都不同，混进差集就废掉"差集几条"这个判据 | 24 个用例 |
| `compare_r3.py`（新） | R3：预注册键分类 + **残差逐字节**比较 + 六个判定字段扫描；`--self-control` 模式 | —— |
| `compare_latency.py`（新） | 逐用例 min / median 估计的增量 + 自证噪声包络 | 24 个点 |
| `ab_reading_context.py`（新） | 同进程**交替开关**那一项的配对 A/B（抵消时间漂移） | 11 fixture × 5 轮 × 2 臂 × 2 模式 |
| `measure_reading_context_cost.py`（新） | 直接测新增工作（含**被否掉的** `git rev-parse` 选项） | n=200 |
| `probe_verdict_lines.py`（新） | VERDICT 判定行矩阵 + 跨语言对侧字面量 | 144 行 |
| `.tmp/step3b/probe_decisions.py` / `json_field_diff.py` / `.tmp/step7/volatile.py` | 沿用（R1 与字段级差集） | —— |

**自证（自己对自己必须干净）**：

| 对照 | 读数 |
| --- | --- |
| 审计记录 before vs before-run2（残差口径） | `diffs=0 / residual_mismatch=0 / forbidden=0` |
| 审计记录 after vs after-run2（残差口径） | `diffs=0 / residual_mismatch=0 / forbidden=0` |
| 决策载荷 before vs after | 两份**逐字节相同**（23992 B、`cfad8c32c59a57a4…`） |
| VERDICT 判定行 before vs after | 两份**逐字节相同**（24403 B） |

**仪器第一版漏掉过一个每次都在变的时间戳（记下来）**：before/before-run2 的残差里出现过 3 条
`origin.observation.verified_at`（墙钟）。`json_field_diff` 的 UNSTABLE 名单里本来就有这个叶子，
所以**字段级差集看不见它**——是"残差逐字节"这把更严的尺子把它抓出来的。把它声明成运行期变化字段之后，
自证归零。这条留在记录里，因为"差集里多出 3 条"当时看起来**很像**真实差异；仪器错了，读数就会骗人。

### 11.1 R-d 逐条（21 号 §5 的预注册形状）

| # | 尺子 | 差集 | 结论 |
| --- | --- | --- | --- |
| R1 | 决策载荷（10 个场景，四把尺子里唯一不碰包装层的一把） | **0 条**：before/after 逐字节相同（23992 B、`cfad8c32c59a57a4…`，与 22 号记的第 19 轮同一个值） | `reading_context` **不进决策载荷** |
| R2' | VERDICT 判定行（144 行矩阵 + 插件侧按精确版本号读的字面量） | **0 条**：逐字节相同（24403 B）；`VERDICT_SCHEMA_VERSION` 仍 `1.0`，`policy-hook.plugin.mjs` 里的字面量仍 `1.0` | 判定行不在本次改动面内——**"不动"是被读出来的，不是被声明的** |
| R3 | Hook 审计记录（24 个用例、**51 条**记录） | **107 条 = 51 ×（`reading_context` 新增 + `audit_schema_version` 1.2→1.3）+ 5 × `pre_evidence.registry` 新增**；`unexpected=0`、残差**0 条不符**、六个判定字段 **0** 命中、结论/记录条数 **0** 处不一致 | 每条记录只多出**预注册的键与版本号** |

那 5 条 `pre_evidence.registry` 落在**取证真的收上来**的记录上：`evidence.pre-tool-use-write-{allow,block}`、
`paired.paired-allow`（两条记录）、`paired.paired-block`；其余记录没有这个键——
**"这次没有取证"与"取证了但没记版本"必须能分开读**（这也是它放在 `pre_evidence` 内、
而不是放进顶层 `reading_context` 的原因）。

### 11.2 硬约束①：延迟（增量不得超过 50 ms）

| 尺子 | 读数 |
| --- | --- |
| **直接测**（n=200） | `reading_context_for_record` **0.5258 ms**（中位数；其中 `declaration_block` 0.4829 ms、`host_block` 0.0006 ms）。每次 Hook 调用写 1~2 条记录 → 上限约 **1.1 ms/次** |
| **配对 A/B**（同进程交替开关） | evidence 模式增量中位数 **−1.8 ms**、最大 **+36.7 ms**；plain 模式中位数 **+1.6 ms**、最大 **+14.1 ms**；**0/11** 个 fixture 超过 50 ms |
| before/after 两轮采集（每 fixture 5 次） | min 估计：中位数 **+1.5 ms**、最大 **+34.7 ms**；median 估计：中位数 **+3.0 ms**、最大 **+50.1 ms**（**1 个点**） |
| 自证噪声包络 | before vs before-run2：**−25.8 … +14.3 ms**；after vs after-run2：**−78.9 … +1.5 ms**；交叉对照 before vs after-run2：最大 **+7.5 ms** |
| **被否掉的选项的代价** | `git rev-parse HEAD` **48.3967 ms**（中位数，n=200）——它一项就吃掉整个 50 ms 预算 |

**结论：增量在 1 ms 量级，11 个 fixture 没有一个超过 50 ms。** 上面那个 **+50.1 ms** 的单点落在
机器自证的噪声带里（同一台机器、**同一份代码**的两次采集，自身差值就能到 −78.9 ms），
而它对应的直接代价是 0.53 ms —— 这个点归因于机器负载，**不归因于本次改动**；
单独写出来，是因为"每项 5 次取中位数"这条口径下它确实出现了，隐掉它就是挑读数。

### 11.3 硬约束②：大小（失败关闭上限的余量不得低于 30%）

| 项 | before | after | 余量 |
| --- | --- | --- | --- |
| 最大单条记录（Phase 2 审计记录，UTF-8 字节） | **6574 B** | **7518 B** | `16384 − 7518 = 8866 B` → **54.11%**（下限 30%） |
| 51 条记录的增量分布 | —— | 最小 **+520 B**、最大 **+944 B** | —— |
| 上限来源 | `enforcement.audit.DEFAULT_MAX_RECORD_BYTES = 16384`（AGENTS 第 16 条） | | |

**口径诚实**：Hook 侧写审计用的是 `hooks.AuditLedger.append`，它**自己不设**字节上限——
那条上限是**审计链**（`FileAuditSink`）的失败关闭阈值，也是 AGENTS 第 16 条登记的那一个。
所以这里报的是"离那条被登记的上限还有多远"，不是"已经被它拦住过"。

### 11.4 硬约束③：兼容（1.2 不回写 · 1.2 与 1.3 混排的链必须过校验）

| 判据 | 读数 |
| --- | --- |
| 已有 1.2 记录不回写 | 用例 `test_a_1_2_record_is_not_rewritten_and_a_mixed_chain_still_verifies`：新记录写入后 `audit.read_bytes().startswith(before_bytes)`，第 1 行与写入前**逐字节相同** |
| 1.2 与 1.3 混排的链 | `enforcement.audit.FileAuditSink(audit).verify() == ()`；两类 Phase 2 记录都被算作**外来行**（`foreign_records()` 计数），不静默收编 |
| 版本断言 | `tests/unit/test_hook_skip_visibility.py` 的版本断言按协议自己的规则显式改成 `"1.3"`（第 55 条） |

### 11.5 门禁（`--full`）

**命令（逐字）**：`python tools/ci_local.py --full --python .venv/Scripts/python.exe`
**树**：HEAD = `7f8f77a`（跑前工作树空；本会话没有别的门禁作业）。

| 项 | 读数 |
| --- | --- |
| **显式退出码** | **0** —— `本机检查全部通过（31 步）；只报告 2 步（非零退出不计入失败）` |
| **耗时** | 门禁自己的汇总行 **5m 00.1s**（`=== 执行耗时（合计 5m 00.1s，33 步，最慢 5 步）===`） |
| 选组 | `改动文件 812 个；执行 31 步（本机跳过 11 步，登记豁免 2 步，只报告 2 步）` |
| 大头 | pytest **2m 09.2s**（43.1%）→ notebooks 1m 08.8s（22.9%）→ 编排闭环 1m 01.7s（20.5%）→ 阶段验收证据 7.2s → 验证器闭环 6.8s |
| 与第 21 轮对照 | 同一条命令在 `e71b5e0` 上是 **5m 35.6s / 33 步**，本轮 **5m 00.1s / 33 步**（**不相减**：改动面与机器负载都不同）。能对照的是同一步：pytest 2m06.6s → 2m09.2s（+2.6s）、notebooks 1m33.0s → 1m08.8s（−24.2s，**未归因**） |
| 只报告步骤 1 | 义务门禁：0 命中（退出码 0），`hits=0 / 1 个账本（不适用 1：没有账本可读，不算一次真实读数）` |
| 只报告步骤 2 | 豁免到期：0 命中（退出码 0），`HITS: 0 / declared=8 due=0 expired=0 unprovable=0` |
| 日志 | `.tmp/step9/ci-local-full-r22.log`（4956 B）+ `.tmp/ci-local-logs/` 下 **33 个**分步日志 |
| 第 9 步（沙箱闭环） | `ok 1.8s`；产物 `result=skipped`、`environment_skipped=true`、`dsh_startup_denied_kind=profile_write_denied`（被拒路径 `C:\Users\ZNM\.dsh\profiles\headless\cordis.yml`）、`host.sandbox=restricted`、`tree.revision=7f8f77a…` —— **受限上下文里的读数，不是真机读数**（第 45 条：环境跳过不是通过） |

**跑之前删掉了一个沙箱 ACL 残留（必须记下来）**：`.tmp/tmp/pytest-of-ZNM` 是**上一次**运行
（21:50 的 pre-push）留下的 `0o700` 残留目录：`os.scandir` 都被拒（`WinError 5`），
`pytest -n auto` 因此在**收集期** `INTERNALERROR`（`make_numbered_dir_with_cleanup` →
`PermissionError`）——与第 20 轮 §4.1/§4.2 同一个现象、同一条处置：**程序级放宽到
`danger-full-access`**，只删这**一个** pytest 落点目录（`removed=1`、`still there? False`），
随后 `-n auto` 恢复正常（`5 passed in 5.38s`）。放宽**只用在这一次删除上**：
本轮所有代码 / 文档 / 测试改动只用 `write` / `edit` 落树，按路径暂存，没有 `--no-verify`、
没有强推、没有 `cleanup.py`、没有直接跑 `tools/dsh_sandbox_loop.py`。

### 11.6 跑前快照 → 跑后逐个文件比对（第 9 步必然跑 `tools/dsh_sandbox_loop.py`）

**禁令照样遵守**：**没有**直接跑 `tools/dsh_sandbox_loop.py`；它只作为门禁第 9 步被执行。
快照 `.tmp/e2e/before-gate-r22/20260930T224415/manifest.json`（受控目录 55 个文件的
路径 / 字节 / mtime / sha256 + 产物副本 + HEAD + `git status`），跑后逐文件比对：

| 项 | 读数 |
| --- | --- |
| 受控目录 | before/after 都是 **55 个文件**；逐字节相同 **53**、内容变了 **2**、新增 0、消失 0 |
| 变了的两个 | `.tmp/phase-2-sandbox/logs/{allow-run,block-run}.txt`：`2ab540972f1d1a75… → 2dc1a97ba8eea1c8…`（两份内容相同：这次 dsh 真的起了进程，日志被重写） |
| 内容相同但 mtime 变了 | **6** 个（受控项目的 `dsh-adapter.yaml` / `hooks.json` / `patch.yml` / `AGENTS.md` / `order_controller.py` / `order_service.py`）——受控目录每次由闭环重建，**"内容没变"不等于"没被重写"**，两件事分开报 |
| 产物 | `3122 B → 3121 B`；`result=skipped` / `environment_skipped=true` 两边一致；`reading_context.host.dsh_home`：`<unset>` → `<outside-workspace>`，`tree.revision`：`7864dd2…` → `7f8f77a…`——**这正是 `reading_context` 要回答的问题**：两份读数不属于同一棵树、也不属于同一个环境 |
| 仓库侧 | HEAD 仍 `7f8f77a`；`git status --porcelain -uall` **空** |
| 这一步证明什么 | 门禁**没有动仓库**、**没有动受控项目的源码与配置**；它**不**证明端到端闭环跑通了（那是环境跳过） |

### 11.7 预算对账（`git show --numstat`，口径 = 新增行；按路径前缀分桶）

| 桶 | 台阶 4 累计 | 复核线（1.5×） | 硬上限（2.5×） |
| --- | --- | --- | --- |
| src | **681** | 1 950 | 3 250 |
| tests | **1 527** | 2 100 | 3 500 |
| tools | **893** | ——（21 号 §7 的表里没有这一桶，照旧单列） | —— |
| 数据 / 文档 | **815** | —— | —— |

**逐段**（提交集合照 21 号 §8 的基线 + 23 号 §5.4 的第 20 轮 + 第 21/22 轮）：

| 段 | 提交数 | src | tests | tools | 数据/文档 |
| --- | --- | --- | --- | --- | --- |
| 21 号 §8 基线（端到端建轴之前） | 6 | 0 | 598 | 670 | 103 |
| 第 20 轮（`reading_context` 前三件 + 记录） | 6 | 463 | 543 | 221 | 476 |
| 第 21 轮（裁定① + 覆盖账 + 记录） | 3 | 91 | 111 | 0 | 178 |
| 第 22 轮（背景登记 + Hook 审计） | 2 | 127 | 275 | 2 | 58 |
| **台阶 4 累计** | 17 | **681** | **1 527** | **893** | **815** |

**src 与 tests 都在复核线之内**（余量 1 269 / 573），没有触发"超过 1.5 倍就停下复核"。
本文件不计入上面的提交集合（它自己只加文档行）。

### 11.8 未核实 / 待评审

1. **两处与预注册形状的偏离，请评审裁定**：① `reading_context.tree` 只有 `status` / `scope` /
   `digest`，**没有 `revision`**（`git rev-parse HEAD` 48.4 ms，占满 50 ms 预算；受控项目常常
   不是 git 工作树，取不到会是常态）；② `host.sandbox` 恒为 `unknown`（Hook 不探测沙箱，
   与 21 号 §9.2 裁定④对 `check` 路径的口径相同）。两者都写在
   `hooks.reading_context_for_record` 的 docstring 里，不是顺手省掉的；
2. **`declarations.test_layout` 写 `not_applicable`**：取证流水线**确实读过**
   `validation/test-layout.yaml`（`report.configs` 里有它的 digest），但本台阶预注册的搬运范围
   只有 `registry`。它是"**没搬**"而不是"没有"——措辞按此定，若评审要它可读，
   下一轮把它一起搬（`report.configs["test_layout"]` 已经在那儿了）；
3. **延迟读数只属于这台机器这个上下文**：配对 A/B 抵消了时间漂移，但机器负载本身没有独立取证；
   那个 +50.1 ms 的单点只有"自证噪声带"这一个解释，没有做更细的归因；
4. **`--hook` 形态本轮没有跑**：只跑了 `--full`。§10.2 那次 `--hook` 是**使用者**在 `7864dd2` 上跑的；
5. **`git rev-parse` 的 48.4 ms 是这台机器上的读数**（Windows 子进程启动开销），别的平台上没有测；
6. **`tools/ci_local.py` / `tests/unit/test_ci_local*.py` / `tools/phase_evidence.py` 一个字都没动**
   （文件归属），`git push` / `git fetch` 没有做。

---

**本文件是七次提交**：§1–§4.1 在 `45b9962`（门禁之前），§4.2–§7 是第 20 轮门禁之后的补记，
§8–§9 是 2026-09-30 第二轮的裁定与落地读数；§10 是 `15be129`（第 22 轮的背景登记），
§11 是本提交（第 22 轮的门禁之后的落地读数）。切开写是刻意的：§4.1 是**事先**写下的放宽理由，
事后补写就变成了"先射箭再画靶"；§9 与 §11 的读数则在**跑完门禁之后**才写。
