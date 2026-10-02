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

**本文件是十二次提交**：§1–§4.1 在 `45b9962`（门禁之前），§4.2–§7 是第 20 轮门禁之后的补记，
§8–§9 是 2026-09-30 第二轮的裁定与落地读数；§10 是 `15be129`（第 22 轮的背景登记），
§11 是第 22 轮门禁之后的落地读数；§12 是第 23 轮（第三轮裁定与 `declarations.test_layout`
的改正读数）；§13 是第 24 轮的背景登记与两条裁定登记（`c0652b8`）；§14 是第 24 轮的落地读数
（`1bc5b8f`）与它被门禁抓到的那一处格式修正（`8baff4e`）；**§14.7 是本提交**（两次 `--full` 门禁读数）。
切开写是刻意的：§4.1 是**事先**写下的放宽理由，事后补写就变成了"先射箭再画靶"；
§9 / §11 / §12 / §14 的读数则在**跑完门禁之后**才写。

---

## 12 第 23 轮 · 2026-09-30 第三轮裁定与 `declarations.test_layout` 的改正（1.3 内，不升版）

- **执行**：2026-10-01（本机）；控制面重构会话（**唯一写者**）。
- **树**：起点 HEAD = `92a6dd1`（工作树干净）；改正提交 `096cb0d`；门禁在 `096cb0d` 上跑
  （跑前快照记的 HEAD 就是它）。
- **依据**：§11.8 的两条"请评审裁定"与一条"没搬"；AGENTS 第 45（仪器要能失败）/ 48（读数属于哪棵树）/
  50（口径诚实）/ 55（加键就是改协议）条。
- **仪器落点**：`.tmp/step10/`（不提交）。**before 侧在动手之前采集**
  （`decisions-before.json` / `verdict-before.json` / `audit-before.json` /
  `audit-before-run2.json`，采集时刻 00:34:34–00:34:54）。

### 12.1 裁定（2026-09-30 · 第三轮，三项）

§11.8 的原问题**一字不动地留在 §11.8**，便于复核"裁定的是不是当初问的那件事"：

| # | §11.8 的问题 | 裁定 | 落地 |
| --- | --- | --- | --- |
| ① | `reading_context.tree` 只有 `status` / `scope` / `digest`，没有 `revision` | **接受**：`git rev-parse HEAD` 单次实测 48.4 ms，一项就吃掉 50 ms 的增量预算；受控项目常常不是 git 工作树，取不到会是常态 | 不改（口径已写在 `hooks.reading_context_for_record` 的 docstring 里） |
| ② | `host.sandbox` 恒为 `unknown` | **接受**：Hook 不探测沙箱（探测要有副作用），与 21 号 §9.2 裁定④对 `check` 路径的口径相同 | 不改 |
| ③ | `declarations.test_layout` 写 `not_applicable` | **不接受——它与事实不符**：取证流水线**确实读过** `validation/test-layout.yaml`，`validators.pipeline` 已经算了它的摘要（`report.configs["test_layout"]`）。`AUDIT_SCHEMA_VERSION` 的 `1.3` **尚未发布**，因此**在 1.3 内改正、不升版** | 本轮唯一改动（§12.2） |

**三条都不改任何 allow / block、不新增阻断步骤、不改任何退出码。** 第 ③ 条是**协议形状的更正**：
"没搬"此前被写成了"没有"（§11.8 第 2 条自己写着"它是『没搬』而不是『没有』"）——改正之后，
"这条路径上没有这份声明"与"这次没搬"在记录里才分得开（第 50 条：同名两义一律改名）。

### 12.2 改动（提交 `096cb0d`，单独提交）

| 文件 | 改了什么 |
| --- | --- |
| `src/adapters/dsh/pre_evidence.py` | `_summary()` 新增 `test_layout`：`{path, digest, declared_in}`；`digest` 取自 `report.configs["test_layout"]`（**一个字节都不重算**），`path` 取自 `validators.registry.DEFAULT_TEST_LAYOUT` |
| `src/adapters/dsh/hooks.py` | `declarations.test_layout` 照 registry 那一支的做法取**同一份**摘要（`available` / `unavailable` / `not_applicable` 三态不变）；docstring 里那句"这条记录本身不依赖那份声明"删掉，换成裁定的口径与不升版的理由 |
| `tests/unit/test_hook_audit_reading_context.py` | 两条新用例：三处摘要同源；"不另算"的**会失败**检查（变异证明见下）+ 两处三态断言各一条 |
| `src/adapters/dsh/README.md` | §12.10 的键表加一行 `pre_evidence.test_layout`，`declarations` 一栏同步 |

**registry 那一支一个字节都没动**（刻意不抽公共函数，理由写在代码注释里）：R3 的差集里因此
没有 registry 的噪声——"不动"是被读出来的，不是被声明的。

**变异证明（AGENTS 第 45 条）**：把摘要侧接回 `validators.registry.config_digest`（= "另算一次"），
`test_the_test_layout_digest_is_not_computed_a_second_time` 立刻变红
（`AssertionError: [('pipeline', '…\\validation\\test-layout.yaml'), ('registry', 'validation/test-layout.yaml')]`；
`assert 2 == 1`）；撤回变异后 7 passed。**这条用例在"没做错"时是绿的，在"另算"时是红的。**

### 12.3 R-d 逐条（21 号 §5 的预注册形状 + 本轮指令）

**预注册形状（采集之前写下）**：本轮只允许两处变化——
① `pre_evidence.test_layout` **新增**；② `reading_context.declarations.test_layout` 的**状态变化**
（`not_applicable` → `available` + `path` + `digest`，或 → `unavailable` + `reason`）。
除此之外：**决策载荷 0 条差异、VERDICT 判定行 0 条差异**；六个判定字段
（`decision` / `violations` / `pending_findings` / `matched_rules` / `skipped_rules` / `required_action`）
一个都不许出现在任何差集里。

**仪器的时间线（照实写）**：`.tmp/step10/compare_r3.py` 的 `CreationTime` = `2026-10-01T00:34:24`，
早于 before 采集（00:34:44）与 after 采集（00:36:58）；采集完成之后只**追加**了一条
"digest 必须等于 `validation/test-layout.yaml` 的 sha256"的对照检查（`LastWriteTime` 00:37:38），
它**不放松任何判据**（只会更严）。

**仪器的自证（"自己对自己"必须 0 条）**：

| 对照 | 读数 |
| --- | --- |
| R3 before vs before-run2（残差口径） | `cases=24 diffs=0 unexpected=0 residual_mismatch=0 forbidden=0 same_source_mismatch=0 digest_mismatch=0` |
| R3 after vs after-run2（残差口径） | 同上，全 0 |
| R1 决策载荷 自证（`same_tree_rerun_identical`） | `True`（两次逐字节相同） |

| # | 尺子 | before | after | 差集 |
| --- | --- | --- | --- | --- |
| R1 | 决策载荷（10 个场景，四把尺子里唯一不碰包装层的一把） | 23992 B、`cfad8c32c59a57a4…` | **逐字节相同**（同 23992 B、同 sha256，与第 19/22 轮记的同一个值） | **0 条** |
| R2' | VERDICT 判定行（144 行矩阵 + 插件侧按精确版本号读的字面量） | 24403 B、`8b0f538e4bb97f1c…` | **逐字节相同**（24403 B、同 sha256） | **0 条**；`VERDICT_SCHEMA_VERSION` 仍 `1.0`，插件里的字面量仍 `1.0` |
| R3 | Hook 审计记录（11 个 fixture × 5 次 × 3 个模式；before/after 各 **51 条**记录） | 最大单条 7519 B | 最大单条 7823 B | **21 条，全部预注册**：`unexpected=0`、残差 **0** 条不符、六个判定字段 **0** 命中、`pre_evidence.test_layout.digest == declarations.test_layout.digest` **0** 处不符、digest 与文件 sha256 **0** 处不符 |

**21 条的分解**（脚本逐条给出，`R3-diff.json`）：

| 条数 | 差集 | 落在哪 |
| --- | --- | --- |
| 5 | `pre_evidence.test_layout: 新增` | 取证**收上来**的 5 条记录（`evidence.pre-tool-use-write-{allow,block}`、`paired.paired-{allow,block}`、`paired.paired-allow` 的第二条） |
| 5 + 5 | `declarations.test_layout.path: 新增`、`.status: not_applicable -> available` | 同上 5 条 |
| 3 + 3 | `.status: not_applicable -> unavailable`、`.reason: 新增` | `reason_code=evidence_unavailable` 的 3 条（**声明了取证却失败**：三态里的 unavailable，与 registry 同一口径） |

**一条必须写下来的口径**：`declarations.test_layout.digest` 在**字段级差集里看不见**
（`json_field_diff` 的 UNSTABLE 后缀名单里就有 `digest`）。它是靠**两条更严的尺子**抓的：
(a) 残差逐字节（把 after 的两处还原成 before 的形态后必须逐字节相同）；
(b) "digest 必须等于 `validation/test-layout.yaml` 的 sha256"这条对照。
第 22 轮记过同一件事（`origin.observation.verified_at`），这里再记一次：
**字段级差集不是全部，"差集里没有"不等于"没有变化"。**

### 12.4 三条硬约束（重新测一遍）

**① 延迟（增量不得超过 50 ms）**

| 尺子 | 读数 |
| --- | --- |
| **直接测**（n=200，本轮树） | `reading_context_for_record` **0.6203 ms**（中位数；其中 `declaration_block`（adapter 配置）0.5593 ms、`host_block` 0.0007 ms）；第 22 轮同口径是 0.5258 ms —— 差值是噪声量级，新增的那两处都是"取已有的值"（复制字符串），没有新计算 |
| **配对 A/B**（同一进程交替开关，11 个 fixture × 5 轮 × 2 臂） | evidence 模式增量中位数 **+2.104 ms**、最大 **+9.658 ms**；plain 模式中位数 **+1.178 ms**、最大 **+3.011 ms**；**0/11 + 0/11** 个 fixture 超过 50 ms |
| before/after 两轮采集（每 fixture 5 次 × 各侧两轮） | min 估计：中位数 **−7.7 ms**、最大 **+9.5 ms**；median 估计：中位数 **−20.0 ms**、最大 **+4.0 ms**、最小 −79.3 ms；**两种口径下 0/24 个点超过 50 ms** |
| 自证噪声包络 | before vs before-run2：−32.0 … +26.4 ms；after vs after-run2：−5.0 … +2.7 ms；交叉对照 before vs after-run2：−78.7 … +4.8 ms |
| **被否掉的选项的代价**（口径沿用第 22 轮） | `git rev-parse HEAD` **48.99 ms**（中位数，n=200）——它一项就吃掉整个 50 ms 预算，这就是 `tree` 不填 `revision` 的读数 |

**结论**：before→after 的最大增量（+9.5 ms）落在自证噪声带（同机同代码两次采集自身能差 −32.0 ms）之内，
且**没有一个点超过 50 ms**；直接测的新增工作是复制两个字符串。

**② 大小（失败关闭上限的余量不得低于 30%）**

| 项 | before | after | 余量 |
| --- | --- | --- | --- |
| 最大单条记录（Phase 2 审计记录，UTF-8 字节） | **7519 B** | **7823 B**（+304 B） | `16384 − 7823 = 8561 B` → **52.25%**（下限 30%） |
| 51 条记录的增量分布 | —— | 最小 **−1 B**、最大 **+305 B** | —— |
| 上限来源 | `enforcement.audit.DEFAULT_MAX_RECORD_BYTES = 16384`（AGENTS 第 16 条） | | |

**口径诚实**（与第 22 轮同一条）：Hook 侧写审计用的是 `hooks.AuditLedger.append`，它**自己不设**
字节上限——那条上限是**审计链**（`FileAuditSink`）的失败关闭阈值。所以这里报的是"离那条被登记的
上限还有多远"，不是"已经被它拦住过"。最小增量是 **−1 B**（`elapsed_ms` 的位数变化），
与本次改动无关，照实写出来。

**③ 兼容（1.2 不回写 · 1.2 与 1.3 混排的链必须过校验）**

| 判据 | 读数 |
| --- | --- |
| 已有 1.2 记录不回写 | `tests/unit/test_hook_audit_reading_context.py::test_a_1_2_record_is_not_rewritten_and_a_mixed_chain_still_verifies`：**1 passed**（`audit.read_bytes().startswith(before_bytes)`，第 1 行与写入前逐字节相同） |
| 1.2 与 1.3 混排的链 | 同一条用例里 `FileAuditSink(audit).verify() == ()`；两类 Phase 2 记录都被算作**外来行**（`foreign_records()` 计数），不静默收编 |
| 本轮 51 条记录的链 | 24 个用例的 `chain_issues` **全为空**；`foreign_records` 计数 1–3（Phase 4 的链记录，与第 22 轮同口径） |
| 版本断言 | `AUDIT_SCHEMA_VERSION` 仍 `1.3`（裁定：未发布，在 1.3 内改正、不升版） |

### 12.5 门禁（`--full`）

**命令（逐字）**：`python tools/ci_local.py --full --python .venv/Scripts/python.exe`
**树**：HEAD = `096cb0d`（跑前 `git status --porcelain -uall` 空；`.tmp/ci-local.lock` 未被持有，
本会话没有别的门禁作业）。**文档提交之后在最终树 `6718e8f` 上又跑了一次，读数见 §12.7。**

| 项 | 读数 |
| --- | --- |
| **显式退出码** | **0** —— `本机检查全部通过（31 步）；只报告 2 步（非零退出不计入失败）` |
| **耗时** | 门禁自己的汇总行 **4m 58.6s**（`=== 执行耗时（合计 4m 58.6s，33 步，最慢 5 步）===`）；外层秒表 **299.2 s** |
| 选组 | `改动文件 812 个；执行 31 步（本机跳过 11 步，登记豁免 2 步，只报告 2 步）` |
| 大头 | pytest **2m 05.2s**（41.9%）→ notebooks **1m 10.1s**（23.5%）→ 编排闭环 **1m 03.4s**（21.2%）→ 阶段验收证据 7.4s → 验证器闭环 6.3s |
| 与第 22 轮对照 | 同一条命令在 `7f8f77a` 上 **5m 00.1s / 33 步**，本轮 **4m 58.6s / 33 步**（**不相减**：改动面与机器负载都不同）。同一步能对照的是 pytest 2m09.2s → 2m05.2s（**−4.0s，未归因**）与 notebooks 1m08.8s → 1m10.1s（+1.3s） |
| 只报告步骤 1 | 义务门禁：0 命中（退出码 0），读数 `hits=0 / 1 个账本（不适用 1：没有账本可读，不算一次真实读数）` |
| 只报告步骤 2 | 豁免到期：0 命中（退出码 0），读数 `HITS: 0 / declared=8 due=0 expired=0 unprovable=0` |
| 日志 | `.tmp/step10/ci-local-full-r23.log`（**4956 B**，sha256 `8325075EE74596855C57CE7E2C388E9032DFB1ED4FD1030771311DF7700B2367`）+ `.tmp/ci-local-logs/` 下 **33 个**分步日志 |
| 第 9 步（沙箱闭环） | `ok 1.6s`；产物 `result=skipped`、`environment_skipped=true`、`dsh_startup_denied_kind=profile_write_denied`、`host.sandbox=restricted`、`tree.revision=096cb0d…` —— **受限上下文里的读数，不是真机读数**（第 45 条：环境跳过不是通过） |

### 12.6 跑前快照 → 跑后逐个文件比对（第 9 步必然跑 `tools/dsh_sandbox_loop.py`）

**禁令照样遵守**：**没有**直接跑 `tools/dsh_sandbox_loop.py`；它只作为门禁第 9 步被执行。
跑前快照 `.tmp/e2e/before-gate-r23/20261001T003844/manifest.json`（受控目录 69 个文件的
路径 / 字节 / mtime / sha256 + 产物副本 + HEAD + `git status`），跑后逐文件比对：

| 项 | 读数 |
| --- | --- |
| 受控目录 | before/after 都是 **69 个文件**；逐字节相同 **67**、内容变了 **2**、新增 0、消失 0 |
| 变了的两个 | `.tmp/phase-2-sandbox/logs/{allow-run,block-run}.txt`：`2ab540972f1d1a75… → 2dc1a97ba8eea1c8…`（两份内容相同：这次 dsh 真的起了进程，日志被重写） |
| 内容相同但 mtime 变了 | **6** 个（受控项目的 `dsh-adapter.yaml` / `hooks.json` / `patch.yml` / `AGENTS.md` / `order_controller.py` / `order_service.py`）——受控目录每次由闭环重建，**"内容没变"不等于"没被重写"**，两件事分开报 |
| 产物 | `3122 B → 3121 B`；两边都 `result=skipped` / `environment_skipped=true`；`reading_context.host.dsh_home`：`<unset>` → `<outside-workspace>`；`tree.revision`：`92a6dd1…` → `096cb0d…`——**这正是 `reading_context` 要回答的问题**：两份读数不属于同一棵树、也不属于同一个环境 |
| 仓库侧 | HEAD 仍 `096cb0d`；`git status --porcelain -uall` **空** |
| 这一步证明什么 | 门禁**没有动仓库**、**没有动受控项目的源码与配置**；它**不**证明端到端闭环跑通了（那是环境跳过） |

### 12.7 文档提交之后的两次门禁（第二次 `6718e8f`、第三次 = 最终树 `9bbff6f`）

**为什么再跑一次**：§12.5 那次跑在 `096cb0d` 上（改正提交之后）；本轮另外两个提交
（`025465a` 23 号 §12、`6718e8f` 24 号设计稿 + 索引）**都是文档**，但评审要拿到的最终树是
`6718e8f`——"最后一次门禁跑的不是最终树"这件事本身就该被消掉。

**命令（逐字）**：`python tools/ci_local.py --full --python .venv/Scripts/python.exe`
**树**：HEAD = `6718e8f`（跑前 `git status --porcelain -uall` 空；无并发门禁）。

| 项 | 读数 |
| --- | --- |
| **显式退出码** | **0** —— `本机检查全部通过（31 步）；只报告 2 步（非零退出不计入失败）` |
| **耗时** | 门禁汇总行 **4m 54.7s**（33 步）；外层秒表 **295.4 s** |
| 选组 | `改动文件 813 个；执行 31 步（本机跳过 11 步，登记豁免 2 步，只报告 2 步）`（比上一次多 1 = 24 号那个新文件） |
| 大头 | pytest **2m 02.6s** → notebooks **1m 10.2s** → 编排闭环 **1m 02.5s** → 阶段验收证据 7.2s → 验证器闭环 6.2s |
| 只报告两步 | 与 §12.5 逐字相同（义务门禁 `hits=0`；豁免到期 `HITS: 0 / declared=8 due=0 expired=0 unprovable=0`） |
| 日志 | `.tmp/step10/ci-local-full-r23b.log`（4956 B，sha256 `AD1290E918990DCE6C52AE90D82D72ED653CD45A2647A9221BC05824EB8CEB46`）+ `.tmp/ci-local-logs/` 下 **33 个**分步日志 |
| 第 9 步（沙箱闭环） | `ok 1.5s`；产物 `result=skipped`、`environment_skipped=true`、`host.sandbox=restricted`、`tree.revision=6718e8f…` |

**跑前快照 → 跑后比对**：`.tmp/e2e/before-gate-r23/20261001T004718/manifest.json`（受控目录 69 个文件）：

| 项 | 读数 |
| --- | --- |
| 受控目录 | before/after 都是 **69 个文件**；**逐字节相同 69**、内容变了 0、新增 0、消失 0 |
| 内容相同但 mtime 变了 | **8** 个（受控项目 6 个 + 两个日志）——"没变"与"没跑"分开报 |
| 产物 | `3121 B → 3121 B`；两边都 `result=skipped` / `environment_skipped=true`；`tree.revision`：`096cb0d…` → `6718e8f…`；`reading_context.run.id` 变了（**这一份保留 run**） |
| 仓库侧 | HEAD 仍 `6718e8f`；`git status --porcelain -uall` **空** |

**两次门禁的对照（不相减）**：`096cb0d` 上 **4m 58.6s / 31 步** → `6718e8f` 上 **4m 54.7s / 31 步**；
同一步能对照的是 pytest 2m05.2s → 2m02.6s（**−2.6s，未归因**）。**两次的显式退出码都是 0。**

**第三次（**最终树** `9bbff6f`）**：`9bbff6f` 相对 `6718e8f` 只多了 24 号 §6 的预算累计
（同一份文件 16 + / 12 −）。第三次就是**最终树本身**的那一次：

| 项 | 读数 |
| --- | --- |
| **显式退出码** | **0** —— `本机检查全部通过（31 步）；只报告 2 步（非零退出不计入失败）` |
| **耗时** | 门禁汇总行 **4m 54.1s**（33 步）；外层秒表 **294.8 s** |
| 选组 | `改动文件 813 个；执行 31 步（本机跳过 11 步，登记豁免 2 步，只报告 2 步）` |
| 大头 | pytest **2m 02.0s** → notebooks 1m 09.9s → 编排闭环 1m 02.7s → 阶段验收证据 7.2s → 验证器闭环 6.3s |
| 只报告两步 | 与前两次逐字相同（`hits=0`；`HITS: 0 / declared=8 due=0 expired=0 unprovable=0`） |
| 日志 | `.tmp/step10/ci-local-full-r23c.log`（4956 B，sha256 `11CB5238BA75C84D1086E7C3DAA6ABB1F05A6874608735454C59C9CDAC260187`）+ `.tmp/ci-local-logs/` 下 33 个分步日志 |
| 跑前快照 → 跑后 | `.tmp/e2e/before-gate-r23/20261001T005316/manifest.json`：69 个受控文件**逐字节相同 69**、内容变了 0；**8** 个被重写（内容相同、mtime 变）；产物 `3121 B → 3121 B`、`result=skipped`、`tree.revision=9bbff6f…` |
| 仓库侧 | HEAD 仍 `9bbff6f`；`git status --porcelain -uall` **空** |

**口径**：本节自己是一个**门禁之后**的文档提交——`9bbff6f` 是被门禁跑过的树，本节只把那次读数写进去
（与 §11 同一做法：读数是门禁之后写的）。**三次门禁的显式退出码都是 0。**

### 12.8 未核实 / 待评审

1. **真机端到端仍未在本轮采到**：第 9 步与第 22 轮一样是 `profile_write_denied` 的环境跳过；
   `host.sandbox=unrestricted` 的真机原件仍是 §10.1 那份（`7864dd2`），不是本轮树上的。
2. **pytest 的 −4.0s 未归因**：两次门禁的差不是归因；本轮没有逐用例计时。
3. **`declarations.test_layout` 的 `path` 取自常量而不是流水线实际加载路径**：
   取证路径上 `load_validation_config(root=anchor)` 用的就是 `anchor / DEFAULT_TEST_LAYOUT`，
   所以两者今天必然一致；但**声明里换一个 `test_layout` 路径**这种情形本台阶不支持
   （`pre_evidence` 只声明 `registry_root` 一个锚点）——要支持就得先有声明位。**未核实**。
4. **延迟读数只属于这台机器这个上下文**：配对 A/B 抵消了时间漂移，机器负载本身没有独立取证。
5. **本轮没有跑 `--hook` 形态**：只跑了 `--full`。
6. **`tools/ci_local.py` / `tests/unit/test_ci_local*.py` / `tools/phase_evidence.py` 一个字都没动**
   （文件归属）；`git push` / `git fetch` 没有做。
7. **待评审**：① `evidence_unavailable` 那 3 条记录把 `declarations.test_layout` 从
   `not_applicable` 改成 `unavailable` —— 它与 registry 那一支口径一致，但**它是本轮差集里
   除了"5 条 available"之外的第二类变化**，请确认这条也在预注册的"状态变化"之内；
   ② 本条改正落在 1.3 内、没有升版（与 2026-09-30 裁定①对 `OUTPUT_SCHEMA_VERSION` 1.2 的处置同型），
   请确认口径一致。
---

## 13 第 24 轮 · 背景登记与两条裁定登记（本提交只写文档）

- **执行**：2026-10-01（本机）；控制面重构会话（**唯一写者**）。
- **树**：起点 HEAD = `1e9df8c`（`git status --porcelain -uall` 空）。本提交**不改任何代码、
  数据与测试**：它只把使用者提供的两条真机读数、一条已知偏差与一条评审裁定登记下来。
- **依据**：§12.8 第 1 条（"真机端到端仍未在本轮采到"）与第 7 条①（`evidence_unavailable`
  那 3 条）；使用者 2026-10-01 的登记指令。
- **仪器**：本节**没有新造探针**——两个读数来自 `.tmp/e2e/` 下的**原件字节**
  （用 `Get-FileHash` / `Get-Item` 复核），其余来自 `git log`。§12.8 第 1 条与第 7 条①的
  **原问题一字不动地留在 §12.8**，便于复核"登记的是不是当初问的那件事"。

### 13.1 背景登记：使用者本机端到端的第二、第三条真机读数（`92a6dd1` 与 `1e9df8c`）

§10.1 登记过 `7864dd2` 上的一次真机 `result=pass`；本轮再登记两次，**两份都是原字节**
（使用者用 `Copy-Item` 从 `.tmp/artifacts/phase-2-sandbox-result.json` 复制），不是 §2 那种手抄件。

| 项 | 第 2 条（树 = `92a6dd1`） | 第 3 条（树 = `1e9df8c`，= 本轮起点） |
| --- | --- | --- |
| 原件 | `.tmp/e2e/pass-20260930T231438.json` | `.tmp/e2e/pass-20261001T030051.json` |
| 字节 / sha256 | **3662 B** / `5708F3C68890A8C972AA1B91F309B54E60F8C1D5FB7AC2A60C79F6FA2B7C1311` | **3606 B** / `B090F7C80A17DD76C120B17FD9DC6C9CF56308C81C2D207D459DD59EB8895B55` |
| 落盘时刻（mtime，UTC） | `2026-09-30T15:14:38.5115462Z` | `2026-09-30T19:00:50.9286632Z` |
| `timestamp` | `2026-09-30T15:14:37.400188Z` | `2026-09-30T19:00:49.115572Z` |
| 结论 | `result = pass`、`environment_skipped = false`、`schema_version = "1.2"` | 同左 |
| 宿主 | `host.sandbox = unrestricted`、`isolated_home = true`、`dsh_home = .tmp/phase-2-sandbox/dsh-home` | 同左 |
| 树 | `tree.revision = 92a6dd141543a6ab2c3a64d8f32af412569a4197`；`tree.digest = sha256:96a7754eaf80ea88…` | `tree.revision = 1e9df8cec7968f7530b1b3aac556e6a152ec0281`；`tree.digest = sha256:9813b85eb60c9c8d…` |
| 两个场景 | `block.passed = true`（`53b53a25162599fc… → 53b53a25162599fc…`，**文件未变**；`decision=block`、`exit_code=2`、`executed=false`、`reason_code=policy_block`）；`allow.passed = true`（`53b53a25162599fc… → 2972725e717804ec…`，**改了一次**；`decision=allow`、`exit_code=0`、`executed=true`） | 两个场景的哈希与判决**逐字相同**；`agent_version = 0.1.5-rc.1` |
| 规则集 | 两条都是 `rule_set_hash = sha256:50202675b6ca4013…`、`matched_rules = ["ARCH-001@1"]` | 同左 |

**我复核了什么**：上表每一行都来自原件本身（含两份的 `tree.revision` 与对应 git 提交逐字符相同：
`92a6dd1…` / `1e9df8c…`）；两个 sha256 是**本机重算**的，不是转抄。
**这一节关闭的是 §12.8 第 1 条**：真机 `host.sandbox = unrestricted` 的读数现在有**三条**
（`7864dd2` / `92a6dd1` / `1e9df8c`），且后两条落在本轮起点树上。

**口径（第 50 条：先说不算什么）**：

1. **原件在 `.tmp/` 下，不提交**：它是构建产物目录，随时可能被门禁第 9 步或 `cleanup.py`
   覆盖/删除；本节登记的是"这两个字节序列在这次会话里存在过、且被本机复核过"，**不是**可长期
   复核的仓库产物；
2. **"这两次真的是端到端跑出来的"是使用者提供的事实**：原件内容与一次完整闭环的载荷**同形**
   （两个场景 + 五份 `captured_payloads` + 两条日志名 + 完整 `reading_context`），
   但我**没有**亲眼看到这两次运行；我复核的是**字节**；
3. **远端状态未核实**：本会话不 `fetch`；`origin/refactor/control-plane` 这个**远端跟踪引用**
   指向 `1e9df8c`，但"远端此刻也是它"**未核实**。

### 13.2 已知偏差登记：1.3 的 `declarations.test_layout` 在已发布窗口里是 `not_applicable`

| 项 | 内容 |
| --- | --- |
| 窗口 | `feat`（= 本分支；已推送）**停在 `92a6dd1` 的那段时间**：本机 `23:18 – 03:04`（**使用者提供**；我没有 `fetch`，无法独立复核推送时刻） |
| 偏差 | 该窗口里已发布的 `AUDIT_SCHEMA_VERSION = "1.3"` 记录，其 `declarations.test_layout` 是 `not_applicable`；`096cb0d`（本机 `00:38:33`，第 23 轮）之后改成**同源摘要**（`available` + `path` + `digest`） |
| 处置 | **不升版、只登记**（使用者 2026-10-01 裁定）：`AUDIT_SCHEMA_VERSION` 仍是 `1.3`。§12.1 裁定③的理由（"1.3 尚未发布"）在当时成立，**事后**看它的前提不再成立——这条偏差就是它的代价 |
| 已核实 | `7f8f77a`（本机 22:44:01）引入 1.3；`92a6dd1`（22:51:03）是窗口起点树；`096cb0d`（次日 00:38:33）是改正提交；三者都在本分支上（`git log` 可复核） |
| 未核实 | 推送时刻（`23:18` / `03:04`）**只有使用者口径**；本会话不 `fetch`，本地 git 元数据不能证明远端状态 |

**规则（使用者 2026-10-01 定，写在这里供后来者引用）**：

> **版本进了 `feat` 即视为已发布；此后改语义必须升版。**

这条规则**不追溯**：上面的偏差按"只登记"处置，不回改、不补版号。它对本轮的直接后果是——
本轮两处改动**都是升版**：`WIRING_SCHEMA_VERSION` `1.2 → 1.3`、声明文件 `schema_version`
`"1" → "2"`（见 §14）。

### 13.3 评审裁定（2026-10-01）：`evidence_unavailable` 那 3 条改为 `unavailable` —— **接受**

§12.8 第 7 条①问的是："`evidence_unavailable` 那 3 条记录把 `declarations.test_layout`
从 `not_applicable` 改成 `unavailable`，请确认这条也在预注册的『状态变化』之内"。
**裁定：接受。** 口径与 registry 那一支一致——"声明了取证却失败"就是三态里的 `unavailable`，
不是 `not_applicable`（后者是"这条路径上没有这份声明"）。§12.8 第 7 条②（1.3 内改正、不升版）
本轮由 §13.2 的规则**部分覆盖**：当时的前提（1.3 尚未发布）事后不成立，但按"不追溯"处置。

---

## 14 第 24 轮 · `governs` 轴与声明差集落地读数（R-d）、待写声明清单与预算

- **执行**：2026-10-01（本机）；控制面重构会话（**唯一写者**）。
- **树**：R-d 的 **before 侧在动手之前**采集于 `1e9df8c`（工作树干净）；落地提交 **`76a7847`**
  （`src/` + `tests/` + 数据 + 文档同批），after 侧在 `76a7847` 上采集。本轮提交链：
  `26bf07b`（第 0.5 条：三条通道改判）→ `c0652b8`（§13 背景登记）→ `5b8e1c9`（24 号 §8.3 + 17 号 §8.2）
  → `76a7847`（本件落地）。
- **依据**：24 号设计稿 §2 / §3 / §5 / §6 与 **§8.3 的五条裁定 + 第 0.5 条**；AGENTS 第 45（仪器要能失败）/
  48（读数属于哪棵树）/ 50（口径诚实）/ 55（加键就是改协议）条。
- **仪器落点**：`.tmp/step11/`（不提交）。本节所有读数都可按 §14.8 的命令重采。

### 14.0 仪器、自证，与"仪器第一版是错的"

| 仪器 | 作用 | 出处 |
| --- | --- | --- |
| `probe_wiring_entries.py`（新） | R5/R6/R7：三个入口 × 两侧各跑两次（自证）+ 默认形态退出码 ×2 + 声明读数 ×2 | `.tmp/step11/` |
| `scan_R5.py`（新） | 第一把尺子（字段级）的差集**逐条分类** + 硬约束的**逐字段**核对 | `.tmp/step11/` |
| `scan_R5_raw.py`（新） | **第二把尺子**：不剔除任何叶子的残差比对（23 号 §12.3 的教训） | `.tmp/step11/` |
| `summarize_wiring.py`（新） | 把一份载荷压成可比的表（人读用，不参与判定） | `.tmp/step11/` |
| `probe_decisions.py`（沿用 3b） | R1：只调 `policy.engine.evaluate`，读决策载荷本身 | `.tmp/step3b/` |
| `probe_verdict_lines.py`（沿用第 22 轮） | R2'：144 行判定行矩阵 + 插件侧字面量 | `.tmp/step9/` |
| `json_field_diff.py` + `volatile.py`（沿用） | 字段级差集与已声明的随运行变化字段剥离 | `.tmp/step3b/`、`.tmp/step7/` |

**仪器第一版是错的（记下来）**：`probe_wiring_entries.py` 第一版把 `-m provenance.cli` 传了两遍
（`python -m provenance.cli -m provenance.cli wiring-scope …`），before 侧的声明读数因此是 **`rc=2`**
加一行 `invalid choice: provenance.cli`。它**当场就红了**（不是静默的 0）：改掉那一行 argv、重采，
`rc=0` 且两次逐字节相同。留在这里的理由与 §3.0 / §11.0 一样——**仪器错了，读数就会骗人**。

**自证（"自己对自己"必须 0 条）**：

| 对照 | 读数 |
| --- | --- |
| R5 before vs before-run2（字段级） | **0 / 0 / 0**（`default` / `check` / `require-runtime`） |
| R5 after vs after-run2（字段级） | **0 / 0 / 0** |
| R6 声明读数 两次 | 375 B（before 侧）/ 474 B（after 侧），两次**逐字节相同**（`selfcontrol_identical=True`） |
| R1 决策载荷 `same_tree_rerun_identical` | `True`（两侧都是 23992 B、`cfad8c32c59a57a4…`） |
| R2' VERDICT 两次 | 24403 B、`8B0F538E4BB97F1C…`（两侧相同） |

### 14.1 R-d 逐条（24 号 §5 的预注册形状）

| # | 尺子 | before | after | 差集 |
| --- | --- | --- | --- | --- |
| R1 | 决策载荷（10 个场景） | 23992 B、`cfad8c32c59a57a4…` | **逐字节相同**（同 23992 B、同 sha256） | **0 条** |
| R2' | VERDICT 判定行（144 行矩阵 + 插件字面量） | 24403 B、`8B0F538E4BB97F1C…` | **逐字节相同** | **0 条**；`VERDICT_SCHEMA_VERSION` 仍 `1.0`，插件字面量仍 `1.0` |
| R5 | 覆盖账 `--json`（三个入口，**新尺子**） | 23299 B | 46460 B | 每份 **18 条**（第一把尺子）= **17 条预注册** + 1 条例外（§14.2①）；残差尺子每份 **22 条** = 17 + 5 处归属读数（§14.2②） |
| R6 | 声明文件读数（`wiring-scope --check --json`） | 375 B（schema `"1"`） | 474 B（schema `"2"`） | **4 条**：`schema_version: "1" -> "2"`、`channel_kinds` / `covers` / `governs_tree` **新增**；`declared` / `by_decision` / `ids` **一条不动** |
| R7 | 门禁第 24 步（默认形态 `adapters.cli wiring`） | 退出码 **0 / 0** | 退出码 **0 / 0** | **0 条** |

**三个入口的退出码（两侧逐字相同）**：默认 **0**、`--check` **1**、`--require-runtime` **1**。
补充读数（默认会话观察，不进 R5 差集）：`wiring --json` 24131 B → 47292 B。

**硬约束（24 号 §5）逐条核对**：

| 判据 | 读数 |
| --- | --- |
| 差集里出现 `result` / `failures` / `counts` / `fact_counts` / `probe` / `tools` / `channels[].status` / `.wiring_status` / `.freshness_status` | **0 命中**（`scan_R5.py` 的分类器逐条扫三个入口） |
| 上述字段的**逐字段**相等（不靠差集反推） | 三个入口**全部 OK** |
| `reading_context` | **键骨架相同**；除五处归属读数外**逐字段相同**（§14.2②）；`run` 保留（裁定①只对 `check --json` 生效） |
| `--check` 的判据 | 仍只读 `failures`：`report.result == "fail"` → 1；`red_conditions` **一个字段都不读** |

**载荷增量（口径诚实）**：23299 → 46460 B（**+99.4%**）。新增四块的**紧凑 JSON**（不含缩进）合计
**10 591 B**（`differences` 9398 / `red_conditions` 487 / `account` 422 / `headline` 284），
12 个通道的 `governs` 合计 **+5 202 B**（紧凑口径）；`differences.declaration_conflicts` 一项就占 **8 421 B**
（12 条通道 × 6 个候选）。这份载荷没有体积上限，但"翻倍"必须写下来。

### 14.2 五处必须评审的偏离（逐条给出理由与备选）

**① R5 每份 18 条，不是预注册的 17 条。** 第 18 条是
`reading_context.tree.revision: "1e9df8c…" -> "76a7847…"`。预注册里那条"`reading_context` 一个都不许进差集"
按"**旁注的形状与内容不动**"读：before 与 after 本来就是**两棵树**，树身份 `revision` 换树是
`reading_context` 存在的理由本身（AGENTS 第 48 条）——把 `revision` 也剥掉，就等于让"这份读数属于哪棵树"
不可见。**请评审确认这条读法**（备选：把它也剥掉，R5 回到 17 条，代价是 after 侧读数不再自证属于 `76a7847`）。

**② 第二把尺子（残差，不剔除任何叶子）每份 22 条** = 17 条预注册 + 5 处**归属读数**：
`tree.revision`（换树）、`tree.digest`（树被改过）、`declarations.wiring_scope.digest`（声明文件升 schema `"2"`）、
`run.id` / `run.started_at`（本次运行）。第一把尺子（字段级）把后四个当"不稳定"剔掉了——
这正是 §12.3 记过的同一件事：**字段级差集不是全部**。第二把尺子存在的意义就是让它们**逐条可见**。

**③ `red_conditions.in_scope_not_wired.is_red` 取 `count > 0`，不是设计稿例子里的恒 `true`。**
24 号 §2.3 的例子里 `count: 0` 与 `is_red: true` 并排；落地取"此刻是否真的红着"，
因为恒 `true` 与 `count: 0` 并排会被读成"现在就红着"。"这是一条红条件"由**块本身的存在**、
`red_when` 与 `enforced: false` 表达。**请评审确认**（要改回恒 `true` 是一次显式的载荷语义变更）。

**④ "有意治理另一棵树"的默认值边界。** 裁定③ 对今天的 12 个通道都成立：**没有一条声明能绑定它们**
（`declaration_conflicts = 12`），因此 `tree.declared` 全是 `unknown`。但落地口径还定义了另一种情形：
**某条声明用 `covers` 覆盖了通道、却没写 `governs_tree`** → `declared` 取 schema 默认值 `self`
（24 号 §2.1 的字段表）。那时若 `relation = other`，通道行会同时出现"声明说治理本仓库这棵树"与
"证据说目标在探测根之外"这对**矛盾**，而按 §2.1 的边界它**不进五个差集**。今天没有这样的通道；
**要不要让"覆盖但没写 `governs_tree`"也取 `unknown`**（或给它第六格），请评审裁定。

**⑤ 第 0.5 条的读数在 `wiring-scope` 载荷里看不见。** 那三条改判改了 `reason` / `expires_at` / `renewals`，
而 `wiring-scope --check --json` 只报 `schema_version` / `declared` / `by_decision` / `ids`：
**0.5 前后这份载荷逐字节相同**（`R6-diff-step05.json` = **0 条**）；`adapters.cli wiring` 的载荷
同样逐字节相同（`-r05` 三份都是 23299 B）。0.5 的可见读数是：YAML 的 diff（18 + / 12 −）、
`wiring-scope --check` 退出码 **0**、`tools/exemption_expiry.py` 的 `HITS: 0 / declared=8 due=0 expired=0
unprovable=0`（与改动前逐字相同）。**"改判了却看不见"是一个缺口**，登记在此，不另建机制（本轮不新增载荷键）。

### 14.3 两条指令要求的用例 + 全量 pytest

| 用例 | 位置 | 判据 |
| --- | --- | --- |
| a) schema `"1"` 的声明文件仍能加载 | `tests/unit/test_provenance_wiring_scope.py::test_a_schema_1_declaration_still_loads` | `schema_version == "1"`、`channel_kinds == {}`、新字段落在默认值上 |
| b) 空 home 时三数不是 0 | `tests/contract/test_wiring_inventory.py::test_the_three_numbers_are_unavailable_not_zero_when_nothing_is_enumerated` | `discovered` / `measured` 都是 `unavailable` + `value: null` + reason；**对照节**证明"profiles 目录存在但是空的"是**真的 0** |

另外五条（本轮共新增 **7** 条）：显式 `covers` 优先并把没接线的 `in_scope` 通道记进红条件、同档冲突不猜、
`load_declared_scope` 读不到时的三态与绝对路径脱敏、无声明时 `account.declared` 不是 0、
schema `"2"` 新字段与未知取值拒绝。

**全量 pytest（本机，门禁之前的那一次）**：`2059 passed, 1 skipped in 125.36 s`（`-n auto --dist loadfile`；
skip 是既有的"Windows 不允许建符号链接"）。

### 14.4 待写声明清单（裁定③ 的交付物：**列出来，不替使用者写**）

**8 个"目标在工作区之外"的通道**（`<external>/…` 是 `wiring.py` 既有的渲染口径）：

| 通道 | 接线 / 留痕 | 证据字段（渲染成 `<external>/…` 的） | 今天 `tree.declared` |
| --- | --- | --- | --- |
| `dsh:governed` | wired / fresh | `hooks_config`、`audit_path`、`bridge.entry` | `unknown` |
| `dsh:governed-grade` | wired / fresh | 同上 | `unknown` |
| `dsh:governed-grade-approval` | wired / fresh | 同上 | `unknown` |
| `dsh:governed-wmsvc` | wired / fresh | 同上 | `unknown` |
| `dsh:verify-bc` | wired / never_written | 同上 | `unknown` |
| `dsh:verify-exit2` | hooks_config_missing / unevaluated | `bridge.entry` | `unknown` |
| `dsh:verify-gov` | wired / fresh | 同上（三处） | `unknown` |
| `dsh:verify-manual` | wired / fresh | 同上（三处） | `unknown` |

**另外 4 个通道三个目标一个都读不到**（patch 里根本没有桥）→ `tree.relation = unknown`：
`dsh:desktop`、`dsh:headless`、`dsh:verify-dead`、`dsh:web`（四个都是 `not_wired`）。

**今天 12/12 个通道的 `decision` 都是 `undeclared`**：声明文件里有 **6 条 `agent_runtime` 声明**
（`in_scope` 1 / `out_of_scope` 4 / `expected_absent` 1）落在同一个 kind 档，判决不一致，
而**没有任何一条写 `covers`**——按 §2.1 规则 3 不挑一个，12 条都进 `differences.declaration_conflicts`。
**要定夺某条通道，声明侧的最小形态是**：

```yaml
covers: ["dsh:governed", "dsh:governed-*"]   # 显式覆盖（优先于 kind 档）
governs_tree: other                          # 若这条通道**有意**治理另一棵树
tree_ref: <outside-workspace>                # 或仓库相对路径；只放指针、不放正文、不放绝对路径
```

若某条通道其实该由本仓库治理，则 `decision: in_scope` + `governs_tree: self`（默认，可不写）；
这两条路都会立刻在 `differences` 里显出后果（`out_of_scope_active` / `in_scope_not_wired`）。
**本轮一个字节都不替使用者写**（裁定③）。

### 14.5 预算对账（`git show --numstat`，口径 = 新增行，按路径前缀分桶）

| 桶 | 24 号 §6 的估算（本件） | 本轮实际 | 台阶 4 累计 | 复核线（1.5×） | 余量 |
| --- | --- | --- | --- | --- | --- |
| src | 60–120 | **701** | **1426** | 1 950 | **524**（用到 73%） |
| tests | 80–150 | **321** | **1933** | 2 100 | **167**（用到 92%） |
| tools | —— | 0 | 893 | —— | —— |
| 数据 / 文档 | —— | 191 | **1575** | —— | —— |

**超估算 3–6 倍（src）/ 2–4 倍（tests），必须写清楚花在哪**：`src/adapters/wiring.py` **633 行**
（新机制 + 口径注释与 docstring），`tests/contract/test_wiring_inventory.py` **225 行**，
`src/provenance/wiring_scope.py` 55 行，`src/adapters/cli.py` 13 行。这四份文件的 926 行新增里：
空行 109、纯注释 66，其余是代码与中文 docstring（口径注释在这个仓库里是交付物的一部分，不另计）。

**tests 桶到复核线还有 167 行（92%）**：本轮**没有**越过 2.1k 的复核线，因此不触发"停下来复核"；
但下一轮（R-h 仪器自证的设计稿）**只写文档**，不占 tests；若 R-h 之后还要给 governs 加用例，
必须先按 21 号 §8 的口径重算并请评审。

**最终读数（本节写完之后又多了两个文档提交）**：上表的"本轮实际"是在 `76a7847` 那一刻算的；
加上 §14（`1bc5b8f`）、它的格式修正（`8baff4e`）与 §14.7（`9bbc485`）之后——
**数据 / 文档 465**（台阶 4 累计 **1849**），**src / tests 一行没变**（这三个提交只改文档）。
两次门禁的显式退出码：第一次（`1bc5b8f`）**1**、第二次（`8baff4e`）**0**。

### 14.6 未核实 / 待评审

1. **`--observe-sessions` 被钉死为 0**：R5 的三份读数因此**不覆盖**"扫描 `$DSH_HOME/sessions`"那条路径
   （`tools` 块恒等是**钉死的**结果，不是"这条路径没变"的证明）。默认形态的补充读数（24131 → 47292 B）
   带着真实的会话观察，但两次采集之间会话记录会变，因此**不进差集**；
2. **载荷翻倍（+99.4%）**：没有体积上限，也没有为它设上限——记下来供评审决定要不要设；
3. **`covers` 的 glob 只认 `*`**（`?` 与 `[seq]` 当字面量）：没有实测"用户写了别的元字符"时的行为，
   只写清了口径（写错的 pattern 会落进 `discovered_not_declared`，不会静默生效）；
4. **同档冲突只在 `differences.declaration_conflicts` 里可见**，加载期不拒绝（本稿口径）。
   要改成加载期拒绝就是**新的 FATAL**，按 L5 得先有一轮 warn；
5. **真机端到端本轮没有新读数**：§13.1 登记的两份原件仍是最新的真机 pass（`92a6dd1` / `1e9df8c`）；
6. **`--hook` 形态本轮没跑**：门禁只跑 `--full`（§14.7）；
7. **`tools/ci_local.py` / `tests/unit/test_ci_local*.py` / `tools/phase_evidence.py` 一个字都没动**（文件归属）；
   `git push` / `git fetch` 没有做（`origin/refactor/control-plane` 这个远端跟踪引用仍指向 `1e9df8c`，
   "远端此刻的状态"**未核实**）；
8. **待评审**：§14.2 的五条（R5 的 18 vs 17、`is_red` 口径、`governs_tree` 默认值边界、0.5 的可见性缺口、
   预算超估算）。


### 14.7 门禁（`--full`）—— **两次**：第一次退 1（真的抓到了东西），第二次在最终树退 0

**命令（逐字，两次相同）**：`python tools/ci_local.py --full --python .venv/Scripts/python.exe`

**第一次（树 `1bc5b8f`）**：显式退出码 **1**，汇总行 **4m 56.9s / 33 步**。失败只有一处，而且是**真的**：

| 项 | 读数 |
| --- | --- |
| 失败步骤 | `[20/31] Text conventions (UTF-8 / LF / trailing whitespace)` `rc=1` |
| 原因 | `23-round20-reading-context-landing.md: 文件以多个空行结尾`——我用 `edit` 追加 §14 时，插入块自带的结尾换行与锚点行后原有的换行叠成了两个 |
| 处置 | `8baff4e`（**单独提交**，只删那一个空行）：`python tools/check_text_conventions.py` → 检查 654 个文本文件、问题 **0** 处 |
| 其它 | 其余 30 步全 ok（含第 9 步沙箱闭环、第 24 步覆盖账）；日志 `.tmp/step11/ci-local-full-r24.log`（**6612 B**、`9023B796A28F946D…`） |

**第二次（树 `8baff4e` = 本节落地之前的最终树）**：

| 项 | 读数 |
| --- | --- |
| **显式退出码** | **0** —— `本机检查全部通过（31 步）；只报告 2 步（非零退出不计入失败）` |
| **耗时** | 门禁自己的汇总行 **4m 57.7s**（`=== 执行耗时（合计 4m 57.7s，33 步，最慢 5 步）===`） |
| 选组 | `改动文件 813 个；执行 31 步（本机跳过 11 步，登记豁免 2 步，只报告 2 步）` |
| 大头 | pytest **2m 04.6s**（41.8%）→ notebooks **1m 10.3s**（23.6%）→ 编排闭环 **1m 03.2s**（21.2%）→ 阶段验收证据 7.1s → 验证器闭环 6.3s |
| 只报告步骤 1 | 义务门禁：0 命中（退出码 0），`hits=0 / 1 个账本（不适用 1：没有账本可读，不算一次真实读数）` |
| 只报告步骤 2 | 豁免到期：0 命中（退出码 0），`HITS: 0 / declared=8 due=0 expired=0 unprovable=0`（第 0.5 条续期之后仍是这个读数） |
| 第 9 步（沙箱闭环） | `ok 1.6s`；产物 `result=skipped`、`environment_skipped=true`、`host.sandbox=restricted`、`tree.revision=8baff4e…`——**受限上下文里的读数，不是真机读数**（第 45 条：环境跳过不是通过） |
| 第 24 步（本件落地的那一步） | `ok 0.8s`（默认形态、报告模式、退出 0）——**判据与退出码逐字不变** |
| 日志 | `.tmp/step11/ci-local-full-r24b.log`（**4956 B**、`FDE394E0846F656E…`）+ `.tmp/ci-local-logs/` 下 **33 个**分步日志 |

**两次的对照（不相减）**：`1bc5b8f` 上 **4m 56.9s / 失败 1 步** → `8baff4e` 上 **4m 57.7s / 失败 0 步**。
两次之间唯一的内容差别就是那一行文档格式——**门禁在这件事上是有效的**（AGENTS 第 45 条："跑了、是绿的"
只有在它**能红**的前提下才算覆盖）。

**跑前快照 → 跑后逐个文件比对**（第 9 步必然跑 `tools/dsh_sandbox_loop.py`；**禁令照样遵守**：
**没有**直接跑它，它只作为门禁第 9 步被执行）：

| 项 | 读数 |
| --- | --- |
| 快照 | `.tmp/e2e/before-gate-r24/20261001T033942/manifest.json`（**第一次门禁之前**采，因此它之后的**两次**运行都被这一次比对覆盖） |
| 受控目录 | before/after 都是 **81 个文件**；逐字节相同 **79**、内容变了 **2**、新增 0、消失 0 |
| 变了的两个 | `.tmp/phase-2-sandbox/logs/{allow-run,block-run}.txt`：`2ab540972f1d1a75… → 2dc1a97ba8eea1c8…`（两份内容相同：这次 dsh 真的起了进程，日志被重写） |
| 内容相同但 mtime 变了 | **6** 个（受控项目的 `dsh-adapter.yaml` / `hooks.json` / `patch.yml` / `AGENTS.md` / `order_controller.py` / `order_service.py`）——受控目录每次由闭环重建，**"内容没变"不等于"没被重写"** |
| 产物 | `3122 B → 3121 B`；两边都 `result=skipped` / `environment_skipped=true`；`tree.revision`：`1e9df8c…` → `8baff4e…`；`host.dsh_home`：`<unset>` → `<outside-workspace>`——**这正是 `reading_context` 要回答的问题**：两份读数不属于同一棵树、也不属于同一个环境 |
| 仓库侧 | HEAD 仍 `8baff4e`；`git status --porcelain -uall` **空** |
| 这一步证明什么 | 门禁**没有动仓库**、**没有动受控项目的源码与配置**；它**不**证明端到端闭环跑通了（那是环境跳过） |

**跑之前删掉了 pytest 的 ACL 残留（记下来）**：`.tmp/tmp/pytest-of-ZNM` 是我自己那次全量 pytest（§14.3）
留下的 `0o700` 残留——`pytest -n auto` 会在收集期 `INTERNALERROR`。本会话的文件策略是 `danger-full-access`，
因此直接删（`removed=1`、`still there? False`），**没有**申请任何放宽；两次门禁之前各删了一次。

### 14.8 复现命令（只读或只写 `.tmp`）

```powershell
# R5/R6/R7 的 before/after 采集（各自跑两次取自证）
.venv\Scripts\python.exe .tmp\step11\probe_wiring_entries.py --side before
.venv\Scripts\python.exe .tmp\step11\probe_wiring_entries.py --side after

# 第一把尺子（字段级）与它的分类 + 硬约束逐字段核对
.venv\Scripts\python.exe .tmp\step7\volatile.py --before .tmp/step11/wiring-default-before.json `
    --after .tmp/step11/wiring-default-after.json --out .tmp/step11/R5-diff-default.json
.venv\Scripts\python.exe .tmp\step11\scan_R5.py

# 第二把尺子（残差，不剔除任何叶子）
.venv\Scripts\python.exe .tmp\step11\scan_R5_raw.py

# R1 / R2 撇 / R6
.venv\Scripts\python.exe .tmp\step3b\probe_decisions.py --out .tmp/step11/decisions-after.json
.venv\Scripts\python.exe .tmp\step9\probe_verdict_lines.py --out .tmp/step11/verdict-after.json
.venv\Scripts\python.exe .tmp\step7\volatile.py --before .tmp/step11/scope-r05.json `
    --after .tmp/step11/scope-after.json --out .tmp/step11/R6-diff.json

# 预算对账
.venv\Scripts\python.exe .tmp\step11\budget.py 26bf07b c0652b8 5b8e1c9 76a7847
```

---

## 15 第 25 轮 · §14.2 六条裁定 + 第 0.5 条稳定性小修的背景登记（本提交只写文档）

- **执行**：2026-10-01（本机）；控制面重构会话（**唯一写者**）。
- **树**：写这一节时的 HEAD = `f4a46a6`（`git status --porcelain -uall` 为空）。
- **依据**：23 号 §14.2 的五处偏离与 §14.5/§14.6 的第 8 条待评审；24 号 §8.3 的裁定体例；
  AGENTS 第 45（仪器要能失败）/ 48（读数属于哪棵树）/ 50（口径诚实）/ 55（加键就是改协议）条。
- **本文件不是什么**：本节只**登记裁定与背景**——没有改任何代码、数据或载荷；
  第 0.5 / 1 / 2 步的落地与读数在 **§16**。

### 15.1 §14.2 的六条裁定（2026-10-01）

| # | 问题（§14.2 / §14.5） | 裁定 | 落地 |
| --- | --- | --- | --- |
| ① | R5 每份 **18** 条，不是预注册的 17 条（第 18 条 = `reading_context.tree.revision` 换树） | **接受**：before 与 after 本来就是**两棵树**，「这份读数属于哪棵树」必须与读数同时可见 → 写进**预注册规则** | 不改代码；规则口径见 §15.1.1 |
| ② | 第二把尺子（残差，不剔除任何叶子）每份 **22** 条 = 17 条预注册 + 5 处**归属读数** | **接受**：字段级差集不是全部，归属读数必须逐条可见 | 不改代码；口径见 §15.1.1 |
| ③ | `red_conditions.in_scope_not_wired.is_red` 取 `count > 0`，不是设计稿例子里的恒 `true` | **接受** | 不改代码（落地已是 `count > 0`） |
| ④ | 「写了 `covers` 但没写 `governs_tree`」时 `tree.declared` 的默认值 | **默认值改为 `unknown`**（不是 `self`）；**在 1.3 内改正、不升版** | 本轮第 1 步：`src/provenance/wiring_scope.py` + 字段表与 24 号 §2.1 同步；R-d 见 §16.1 |
| ⑤ | 第 0.5 条三条通道改判的读数在 `wiring-scope` 载荷里**看不见**（§14.2⑤ 的可见性缺口） | **由本轮的 `covers` 补上**：改判过的通道从此有显式的**连接键** | 本轮第 2 步：`adapters/wiring-scope.yaml`；读数见 §16.2 |
| ⑥ | `wiring --json` 载荷 23299 → 46460 B（**+99.4%**） | **接受**：这份载荷没有体积上限，「翻倍」必须写下来（已写在 §14.5） | 不改代码，也不为它设上限 |

#### 15.1.1 预注册规则（①与②的落点，从此生效）

**归属读数不进「形状不变」的判据，但必须逐条可见。** 落到 R-d 上就是两把尺子、两条规则：

1. **形状不变（第一把尺子，字段级）**：除预注册的那几条（版本轴、顶层新增键、通道新增键）外，
   只允许出现**归属读数**——`reading_context.tree.revision`（换树）、`tree.digest`（树被改过）、
   `declarations.wiring_scope.digest`（声明文件变过）、`run.id` / `run.started_at`（本次运行）。
   其它任何一条都按「未预注册」处理，必须逐条给出理由；
2. **逐条可见（第二把尺子，残差，不剔除任何叶子）**：上面五个路径**必须**在读数里出现，
   一个都不许被分类器吃掉——`tree.revision` 换了哪棵树、`tree.digest` 变没变，
   要能从差集本身读出来，而不是靠读者相信「那五个是归属读数」。

**为什么**：§12.3 与 §14.2② 记过同一件事——**字段级差集不是全部**；把归属读数从判据里剔掉，
换来的是「读数属于哪棵树」不可见，而那正是 `reading_context` 存在的理由（AGENTS 第 48 条）。

### 15.2 背景登记：2026-10-01 08:21 的 pre-push 门禁第 29 步报 `Policy API 502 unknown`

| 项 | 内容 |
| --- | --- |
| 时间 | 2026-10-01 08:21（使用者本机，`pre-push` 形态的门禁） |
| 步骤 | 第 29 步 = `Orchestration closed loop`（跑 `tools/orchestration_loop.py`）。**推算**：`--hook` 形态的本机步骤表共 30 步（`--full` 的 31 步里那条 `Learning notebooks are in sync` 被推迟），第 29 步正是编排闭环；使用者的那次日志没有进仓库，**这一步的编号是推算、不是核实** |
| 报错 | `Policy API 502 unknown`（**响应体为空**） |
| 同一棵树 | 同一天 03:04 的门禁全绿 |
| 平台侧 | **平台自身不产生 502**：`policy_api.errors.STATUS_BY_CODE` 的状态码集合是 400/401/403/404/405/409/413/415/429/500/503/504，**没有 502 这一档**；502 + 空响应体是**中间层**（代理 / 网关）的典型形态 |
| 推断 | **回环请求经过了系统代理**：`ApiPolicyClient` 用的是 `urllib.request.urlopen`，它按 `HTTP_PROXY` / `HTTPS_PROXY` / `no_proxy` 与平台设置决定是否走代理。**未核实**：没有抓到代理进程、没有代理日志、也没有复现那条 502 |
| 处置 | 第 0.5 条：**回环地址**（`127.0.0.1` / `::1` / `localhost`）改用**不读代理的 opener**；**非回环地址保持原样**（部署场景可能需要代理）；注入的 `opener` 参数优先级不变；用例用**伪造的代理环境变量**钉住这条行为（读数见 §16.0） |
| 不主张 | 这条处置**不证明** 08:21 那次 502 的成因；它只把一条**无法证伪的环境依赖**（回环请求读代理设置）从代码里去掉 |

**同一批的第二处小修（第 0.5 条 b）**：`tools/orchestration_loop.py` 里凡直接取 `requests[0]` 的场景
（`scenario_idempotent_action` 的 `run.runner.requests[0].action_id`；`scenario_human_approval` 早已有守卫）
在 `requests` 为空时**以 FAIL 收场并写明原因**（「前置场景失败，没有可复用的请求」），
不许让 `IndexError` 把真实原因盖成「场景自己崩了」——`main()` 的兜底会把异常记成 FAIL，
但**读的人只会看到 `IndexError`**，那是一条指错对象的理由（AGENTS 第 52 条的同一条纪律）。
---

## 16 第 25 轮 · 落地读数（第 0.5 条、裁定④、covers 数据、预算）与门禁

- **执行**：2026-10-01（本机）；控制面重构会话（**唯一写者**）。
- **依据**：23 号 §15 的六条裁定与第 0.5 条背景；24 号 §8.4 的 covers 裁定；
  AGENTS 第 45（仪器要能失败）/ 48（读数属于哪棵树）/ 50（口径诚实）/ 55（加键就是改协议）条。
- **树与提交链**：`f4a46a6`（本轮起点）→ `629eb22`（§15 + 24 号 §8.4，只写文档）→ `9064b51`（第 0.5 条）
  → `6787031`（裁定④ 的默认值改正）→ `0dd7358`（covers 数据，**只改** `adapters/wiring-scope.yaml`）
  → `f568a99`（声明读数用例）→ `9631617`（25 号 R-h 设计稿）→ 本节。
- **仪器落点**：`.tmp/step12/`（不提交）；本节读数都可用 §16.7 的命令重采。

### 16.0 环境自检、第 0.5 条与它的自证

**环境自检（先做，且它当场红了一次）**：

| 项 | 读数 |
| --- | --- |
| 起点 | 分支 `refactor/control-plane` @ `f4a46a6`，`git status --porcelain -uall` **空** |
| 解释器 | `.venv\Scripts\python.exe` = Python 3.13.11（打包自 Anaconda） |
| ACL 残留（**必须记下来**） | `.tmp/tmp/pytest-of-ZNM` 是上一轮全量 pytest 留下的受限权限目录。**实测**：`pytest -n auto` 在建立 basetemp 时 `PermissionError: [WinError 5] … pytest-of-ZNM` → `INTERNALERROR`（不是用例失败，是收集期就崩）。本会话的文件策略先是 `workspace-write`，`Remove-Item` / `[IO.Directory]::Delete` / 改名**三种都退「拒绝访问」**；策略改为 `danger-full-access` 之后一次删掉（`still there? False`），再跑 `pytest -n auto` → `13 passed in 4.06s` |
| 仪器在位 | `.tmp/step3b/probe_decisions.py`、`.tmp/step9/probe_verdict_lines.py`、`.tmp/step11/probe_wiring_entries.py`、`.tmp/step7/volatile.py`、`.tmp/step3b/json_field_diff.py` 都在 |

**第 0.5 条 a（回环地址不读代理）**：`ApiPolicyClient` 的 `base_url` 主机是 `127.0.0.1` / `::1` /
`localhost`（大小写不敏感）时用 `urllib.request.build_opener(urllib.request.ProxyHandler({}))`，
非回环地址保持 `urllib.request.urlopen`，注入的 `opener` 优先级不变。
**机制是读过标准库源码的**（不是猜）：`ProxyHandler.__init__` 为每个代理条目装一个 `<scheme>_open`
方法（`urllib/request.py:766-775`），空映射一个都不装；`add_handler` 只登记「有可识别方法」的处理器
（`:408-453`），于是这个 opener 上**根本没有代理处理器**，而 `build_opener` 的 skip 集合同时把
**读环境变量**的默认 `ProxyHandler` 去掉（`:555-564`）。

**第 0.5 条 b（空 `requests` 以 FAIL 收场）**：`scenario_idempotent_action` 新增守卫；
`scenario_human_approval` 早有守卫（此前无用例覆盖，本轮补上）。

**自证（AGENTS 第 45 条：修复前会红）**——两次显式变异，各自只红对应用例：

| 变异 | 结果 |
| --- | --- |
| 把 `_default_transport_opener` 换回 `urllib.request.urlopen` | `test_loopback_base_url_gets_an_opener_with_an_empty_proxy_table` **FAILED**（`1 failed, 3 passed`） |
| 把新守卫写成 `if False:` | `test_idempotent_scenario_reports_fail_instead_of_index_error` **FAILED**（`1 failed, 1 passed`） |
| 两次变异都撤回之后 | `6 passed in 0.32s` |

**用例里的对照**：伪造 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`（并删掉 `no_proxy`）之后，
**默认 opener 的代理表非空**（对照组，证明伪造的变量真的会被读走），而回环 opener 上**没有非空代理表**。
**未核实**：08:21 那条 `Policy API 502 unknown` 本身**没有被复现**——本轮只把一条无法证伪的环境依赖
（回环请求读代理设置）从代码里去掉，**不主张**它就是那次 502 的成因（§15.2 的「不主张」一字不改）。

### 16.1 第 1 步 · 裁定④：没写 `governs_tree` 读作 `unknown`（提交 `6787031`）

**改动**：`src/provenance/wiring_scope.py`（`governs_tree` 改为可选 + `declared_governs_tree()`；
`unknown` **不是可写取值**，写了加载期报错；`as_json` 的 `governs_tree` 摘要改为「只列写了的那些」）、
`src/adapters/wiring.py`（读 `declared_governs_tree()`；没写时把原因写进 `note`）、
`adapters/wiring-scope.yaml` 的**字段表注释**、24 号 §2.1（JSON 例子 + 字段表 + 更正注记）、两条用例。
**加载期 FATAL 一条没加**；`1.3` **没有升版**（1.3 尚未进 feat，同 `policy.check` 1.2 的先例）。

**R-d（两把尺子；before = `9064b51`，after = `6787031`；产物 `.tmp/step12/`）**：

| # | 尺子 | before | after | 差集 | 判定 |
| --- | --- | --- | --- | --- | --- |
| R1 | 决策载荷（10 个场景） | 23992 B | **逐字节相同** | **0 条** | ✅ |
| R2' | `VERDICT` 判定行（144 行 + 插件字面量） | 24403 B、`8B0F538E4BB97F1C…` | **逐字节相同** | **0 条**（`VERDICT_SCHEMA_VERSION` 仍 `1.0`） | ✅ |
| R5 | 覆盖账 `--json`（三个入口） | 46460 B | 46460 B | 第一把尺子每份 **1 条**（`reading_context.tree.revision` 换树）；残差尺子每份 **5 条**（5 处归属读数） | ✅ 0 条未预注册 |
| R6 | 声明文件读数 `wiring-scope --check --json` | 474 B | **逐字节相同** | **0 条** | ✅ |
| R7 | 门禁形态退出码 | 默认 0 / `--check` 1 / `--require-runtime` 1 | **逐个相同** | **0 条** | ✅ |

**硬约束逐字段核对（三个入口全 OK）**：`result` / `failures` / `counts` / `fact_counts` / `probe` /
`tools` / `channels[].status` / `.wiring_status` / `.freshness_status` /`channels[].governs` /
`account`+`differences`+`headline`+`red_conditions` 的键骨架 / `reading_context` 除归属读数外逐字段相同。
**`--check` 判据仍只读 `failures`**（一个字段都没动）。

### 16.2 第 2 步 · covers 数据（提交 `0dd7358`）与真实读数

**声明读数**（`provenance.cli wiring-scope --check --json`，474 → **988 B**）：

| 键 | before | after |
| --- | --- | --- |
| `declared` | 7 | **8**（新增 `dsh-verify-profiles`） |
| `by_decision` | in_scope 1 / out_of_scope 5 / expected_absent 1 | in_scope 1 / **out_of_scope 6** / expected_absent 1 |
| `covers` | `{}` | **6 条声明、10 条 pattern**（9 条精确 + `dsh:governed-*` 一条 glob） |
| `governs_tree` | `{}` | `{"governed-session-hook": "other"}`（其余声明**没写** = 读取侧 `unknown`） |
| 退出码 | 0 | **0** |

**覆盖账读数**（`adapters.cli wiring --json --now 2026-10-01T00:00:00+08:00 --observe-sessions 0`，
46460 → **34755 B**，**变小 11705 B**：`declaration_conflicts` 那 12 条候选清单消失了）：

| 格 | before | after（**实测**） | 预期 | 判定 |
| --- | --- | --- | --- | --- |
| `declaration_conflicts` | 12 | **0** | 0 | ✅ |
| `discovered_not_declared`（undeclared） | 0 | **0** | 0 | ✅ |
| `in_scope_not_wired` | 0 | **0**（`is_red: false`、`enforced: false`） | 0 | ✅ |
| `out_of_scope_active` | 0 | **3**（`dsh:verify-bc` / `dsh:verify-gov` / `dsh:verify-manual`） | 按真实结果报告 | ✅ 真实读数，**没有为归零改判** |
| `out_of_scope_expired` | 0 | **0** | —— | ✅ |
| `declared_not_discovered` | 1 | **2**（`ci-agent-runtime` / `agent-channel-inventory-report-mode`） | 未预注册 | ⚠ **见下** |
| `account` | discovered 12 / declared 7 / measured 7 | discovered **12** / declared **8** / measured **7** | —— | ✅ |
| `headline.machine_line` | `IN_SCOPE_NOT_WIRED: 0 / discovered=12 declared=7 measured=7` | `… declared=8 …` | —— | ✅ |

**12 条通道逐条读数**（`governs.decision` / `declared_by` / `tree.declared` / `tree.relation`）：

| 通道 | decision | declared_by | tree.declared | tree.relation |
| --- | --- | --- | --- | --- |
| `dsh:governed` / `-grade` / `-grade-approval` / `-wmsvc` | `in_scope` | `governed-session-hook` | **`other`** | `other` |
| `dsh:desktop` | `out_of_scope` | `desktop-entry-points` | `unknown` | `unknown` |
| `dsh:web` / `dsh:headless` / `dsh:verify-dead` | `out_of_scope` | 各自的声明 | `unknown` | `unknown` |
| `dsh:verify-bc` / `-exit2` / `-gov` / `-manual` | `out_of_scope` | `dsh-verify-profiles` | `unknown` | **`other`**（四条都是：三个目标渲染成 `<external>/…`） |

**裁定④ 在这里看得见**：`dsh:verify-*` 四条通道的 `relation=other`（证据说目标在探测根之外），
而声明侧**没写** `governs_tree` → `declared=unknown`。**若默认值还是 `self`**，这四行会同时读得出
「声明说治理本仓库这棵树」与「证据说不在探测根里」——**而这对矛盾不进五个差集**（24 号 §2.1 的边界），
会静默存在。这正是裁定④ 要修的东西。

**⚠ 两处必须评审的读数**（都**没有**为了好看去改判）：

1. **`out_of_scope_active = 3`**。`dsh-verify-profiles` 把四条测试 profile 定性为 `out_of_scope`，
   其中三条此刻**真的接上了线**（`wiring_status` 是 wired）。按方案的判据（§3.5 的五个差集、
   `out_of_scope_active` 是「声明不治理、却发现它在生效」），这是**真实缺口**，不是读错了：
   它要么该改判 `in_scope`，要么该拆掉那条通道上的桥。本轮**只报告**，一个字节都没改判；
2. **`declared_not_discovered` 由 1 变成 2**：显式 `covers` 生效之后，`kind` 档不再兜底，
   `ci-agent-runtime`（`expected_absent`）不再绑定任何通道，于是它出现在这个差集里。
   **它的 `reason` 文本此刻不精确**：该格对 `ci-agent-runtime` 写的是「本机没有发现它覆盖的那类通道」，
   而本机**有** `agent_runtime` 档的通道（12 条 `dsh-profile`）——只是它们都被显式 `covers` 领走了。
   这是 `wiring.py` 里**理由措辞**的问题（不是判定问题）：要么给这一格补第三种成因
   （「它的 kind 档有通道，但那些通道已被显式 covers 覆盖」），要么改这条声明的 `decision`。
   **本轮不动它**（第 2 步按指令只改数据文件）；登记在此，请评审定夺。

**R-d（before = `6787031`，after = `9631617` 上的 s2 读数）**：

| # | 尺子 | 读数 | 判定 |
| --- | --- | --- | --- |
| R1 | 决策载荷 | **逐字节相同**（23992 B） | ✅ |
| R2' | `VERDICT` 判定行 | **逐字节相同**（24403 B） | ✅ |
| R5 | 覆盖账三个入口 | 46460 → 34755 B；第一把尺子每份 **74 条**（73 条覆盖账数据 + `tree.revision`）、残差 **78 条** | ✅ **0 条未预注册** |
| R6 | 声明读数 | 474 → 988 B，第一把尺子 **11 条**（全是声明侧键） | ✅ |
| R7 | 退出码 | 默认 **0/0**、`--check` **1/1**、`--require-runtime` **1/1**、声明 `--check` **0/0** | ✅ |
| 硬约束 | 三个入口逐字段 | `result` / `failures` / `counts` / `fact_counts` / `probe` / `tools` / 通道两根轴与总状态 / 四块键骨架 / `reading_context`（除归属读数） | ✅ **全 OK** |

**豁免到期读数**（`tools/exemption_expiry.py`，只报告）：`HITS: 0 / declared=**9** due=0 expired=0 unprovable=0`
（7 条带 `expires_at` 的声明 + 2 条门禁只报告步骤），与预期一致；退出码 **0**。

**为什么有一个提交单独红**：`0dd7358` 只改数据文件（按指令），而 `tests/unit/test_provenance_wiring_scope.py`
钉住了那一份声明的读数，于是它单独红了一条（`1 failed, 2067 passed`）；下一个提交 `f568a99` 只改用例期望
（`16 passed`）。这条红**是数据文件与钉住它的用例分属两个提交的必然结果**，不是缺陷；
把两件事并进一个提交会违反「第 2 步只改 `adapters/wiring-scope.yaml`」。

### 16.3 预算对账（口径 = 新增行，`git diff --numstat f4a46a6..HEAD`）

| 桶 | 台阶 4 累计（§14.5，截至 `f4a46a6`） | 本轮属于台阶 4 的 | 本轮全部 | 台阶 4 累计（含本轮） | 复核线 | 余量 |
| --- | --- | --- | --- | --- | --- | --- |
| src | 1426 | **+41**（`wiring.py` 9 / `wiring_scope.py` 32） | +85（另含 `client.py` 44） | **1467** | 1950 | 483 |
| tests | 1933 | **+82**（`test_wiring_inventory.py` 4 / `test_provenance_wiring_scope.py` 78） | +287（另含两个新用例文件 205） | **2015** | 2100 | **85** |
| tools | 893 | 0 | +21（`orchestration_loop.py`） | 893 | —— | —— |
| 数据 / 文档 | 1849 | +34（声明）/ +92（文档，截至 `f568a99`） | 同 | 1975（截至 `f568a99`） | —— | —— |

**这一行必须补一句（口径诚实）**：上表的「本轮」是在 `f568a99` 那一刻算的；之后还有三个**只写文档**的
提交（25 号 R-h 设计稿 + README 索引、本节、§16.4 的第二次门禁读数），它们的文档行数合计约 **+471**，
因此「数据 / 文档」一格的台阶 4 累计到本节是 **≈2446**。**src / tests / tools 三列不受影响**
（本轮最后一次改代码 / 数据的提交是 `f568a99`），而复核线只对 src 与 tests 生效——**R-h 的结论不变**。

**第二个口径要单列**：若把第 0.5 条稳定性小修（src 44 / tools 21 / tests 205）也算进来，
「台阶 4 累计」是 **src 1511 / tests 2220** —— **tests 已经越过复核线 120 行**。
两个口径的差别就是这笔账算不算台阶 4 的；**请评审定夺**（25 号 §8 第 2 条）。
**两个口径下 R-h 的结论相同：tests 必然越过，src 不越过**（估计见 25 号 §7）。
### 16.4 门禁（`--full`）

**命令（逐字）**：`python tools/ci_local.py --full --python .venv/Scripts/python.exe`

| 次 | 树 | **显式退出码** | **耗时** | 步数 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 第一次 | `9631617`（本节落地之前的最终树） | **0** | 门禁自报 **5m 07.7s**（外部秒表 308.4 s） | 执行 **31** 步 + 只报告 **2** 步（本机跳过 11、登记豁免 2） | 全通过 |
| 第二次 | `c7736ab`（**本节落地之后**的树） | **0** | 门禁自报 **5m 10.3s**（外部秒表 311.1 s） | 同上（31 + 2；本机跳过 11、登记豁免 2） | 全通过 |

- **日志**：`.tmp/step12/ci-local-full-r25.log`（4988 B）；分步日志 `.tmp/ci-local-logs/`；
- **最慢五步**：`Unit, contract, integration and security tests` 2m 09.4s（42.0%）、
  `Learning notebooks are in sync` 1m 12.2s（23.5%）、`Orchestration closed loop` 1m 05.0s（21.1%）、
  `Phase 8 acceptance evidence` 7.6s、`Validator closed loop` 6.5s；
- **第 29 步（`--hook` 的编号）/第 30 步（`--full` 的编号）`Orchestration closed loop` = ok 1m 05.0s**
  ——§15.2 登记的那条 502 就发生在这个步骤上（**编号是推算**，见 §15.2）；
- **两条只报告步骤的读数**：义务门禁 `0 命中`（`hits=0 / 1 个账本（不适用 1：没有账本可读，不算一次真实读数）`）；
  豁免到期 `HITS: 0 / declared=9 due=0 expired=0 unprovable=0` ← **第 2 步的 `declared=9` 在门禁里读得到**；
- **判定行**：`本机检查全部通过（31 步）；只报告 2 步（非零退出不计入失败）`。
- **第二次的日志**：`.tmp/step12/ci-local-full-r25b.log`；最慢五步与第一次同（pytest 2m 13.2s / 手册 1m 11.5s /
  编排闭环 1m 04.8s / 阶段证据 7.4s / 验证器闭环 6.4s），两条只报告读数同（义务门禁 `0 命中`；豁免到期
  `HITS: 0 / declared=9`）；
- **覆盖边界（口径诚实）**：第二次跑在 `c7736ab`，把「记录这两次读数的那个提交」**记在门禁之后**——
  那个提交只改本节与 README 索引（文档），**没有再跑第三次门禁**；这与 §14.5 的「最终读数」注同一条口径，
  提交前重跑过 `tools/check_text_conventions.py`（657 个文本文件、问题 0 处）——上一次门禁退 1 就是栽在这一步。

### 16.5 跑前快照 → 跑后逐个文件比对（第 9 步必然跑 `tools/dsh_sandbox_loop.py`）

| 项 | 读数 |
| --- | --- |
| 快照 | `.tmp/e2e/before-gate-r25/20261001T092631/manifest.json`（HEAD `9631617`、`git status` 为空） |
| 受控目录 | before/after 都是 **81 个文件**；逐字节相同 **79**、内容变了 **2**、新增 0、消失 0 |
| 变了的两个 | `.tmp/phase-2-sandbox/logs/{allow-run,block-run}.txt`：`2ab540972f1d1a75… → 2dc1a97ba8eea1c8…`（两份内容相同：这次 dsh 进程真的起来了，日志被重写） |
| 内容相同但 mtime 变了 | **6** 个（受控项目的 `dsh-adapter.yaml` / `hooks.json` / `patch.yml` / `AGENTS.md` / `order_controller.py` / `order_service.py`）——受控目录每次由闭环重建，「内容没变」不等于「没被重写」 |
| 产物 | `3122 B → 3121 B`；两边都 `result=skipped` / `environment_skipped=true`；`tree.revision`：`f4a46a6… → 9631617…`；`host.dsh_home`：`<unset> → <outside-workspace>`——**这正是 `reading_context` 要回答的问题**：两份读数不属于同一棵树、也不属于同一个环境 |
| 仓库侧 | HEAD 仍 `9631617`；`git status --porcelain -uall` **空** |
| 这一步证明什么 | 门禁**没有动仓库**、**没有动受控项目的源码与配置**；它**不**证明端到端闭环跑通了（那是环境跳过） |

### 16.6 未核实 / 待评审

1. **08:21 那条 `Policy API 502 unknown` 没有被复现**：第 0.5 条的处置只去掉一条环境依赖，不主张成因（§15.2 / §16.0）；
2. **§16.2 的两处 ⚠**：`out_of_scope_active = 3` 是真实缺口；`declared_not_discovered` 那一格的 `reason` 措辞
   对 `ci-agent-runtime` 不精确——两条都**只报告、不改判**，请评审定夺；
3. **R-h 的预算与缩小方案**（25 号 §7）：整包会越过 tests 复核线 95–215 行；
4. **复核线的分子口径**：含不含第 0.5 条这类非台阶 4 的稳定性小修（两个口径分别是 2015 / 2220）；
5. **文件归属**：`tools/ci_local.py` / `tests/unit/test_ci_local*.py` / `tools/phase_evidence.py` **一个字都没动**；
   `git push` / `git fetch` 没有做（`origin/refactor/control-plane` 仍指向 `1e9df8c`，「远端此刻的状态」**未核实**）；
6. **ACL 残留是本机环境问题**（§16.0）：本轮删掉了它、没有修它的成因——
   「下一次全量 pytest 会不会再留一个」**未核实**；
7. **第 1 步在 R6 上看不见**：声明读数载荷逐字节相同（§16.1），因为当时的声明文件里没有 `covers`——
   「默认值改了」只在**有 covers 的树**上显形（§16.2 的通道行）。这不是缺口，但写下来，
   免得被读成「改了等于没改」；
8. **门禁只跑了 `--full`**；`--hook` 形态本轮没跑（§16.4 的步号推算基于 `_plan_steps(False)` 的读数，不是实跑）。

### 16.7 复现命令（只读或只写 `.tmp`）

```powershell
# 两把尺子（R1 / R2 撇 / R5 / R6 / R7 + 硬约束逐字段核对）
.venv\Scripts\python.exe .tmp\step12\scan_rd.py --left before --right after --profile step1
.venv\Scripts\python.exe .tmp\step12\scan_rd.py --left after --right s2 --profile step2

# 采集（before / after / s2 各跑一次；每个入口两次取自证）
.venv\Scripts\python.exe .tmp\step12\probe_wiring_entries.py --side s2
.venv\Scripts\python.exe .tmp\step3b\probe_decisions.py --out .tmp/step12/decisions-s2.json
.venv\Scripts\python.exe .tmp\step9\probe_verdict_lines.py --out .tmp/step12/verdict-s2.json

# 声明与到期读数（第 2 步的正题）
$env:PYTHONPATH='src'; .venv\Scripts\python.exe -m provenance.cli wiring-scope --check --json
.venv\Scripts\python.exe tools\exemption_expiry.py

# 门禁 + 快照比对
.venv\Scripts\python.exe tools\ci_local.py --full --python .venv/Scripts/python.exe
.venv\Scripts\python.exe .tmp\step12\snapshot_before_gate.py
.venv\Scripts\python.exe .tmp\step12\compare_after_gate.py
```

## 17 第 27 轮 · 2026-10-03 评审裁定①②③④⑤ 的落地读数与门禁（**WIRING 1.3 的定稿**）

- **执行**：2026-10-03（本机）；控制面重构会话（**唯一写者**）。
- **依据**：2026-10-03 的五条评审裁定（§17.1）、24 号 §8.5；AGENTS 第 45（仪器要能失败）/
  48（读数属于哪棵树）/ 50（口径诚实）/ 55（加键就是改协议）条。
- **树与提交链**：`088349a`（本轮起点）→ `f6cc503`（第 1 步：数据收尾，**只改**
  `adapters/wiring-scope.yaml`）→ `f0880b6`（用例期望，按指令另起一个提交）→
  `d930af8`（第 2 步：`reason` 文案）→ `d2d90fa`（第 3 步：第六格 + 24 号 §2.2 字段表）
  → 本节。
- **仪器落点**：`.tmp/step14/`（不提交）：`probe_wiring_entries.py`（三个入口 × 两次自证 +
  声明读数 + 默认形态退出码）、`scan_rd.py`（三把尺子 + 硬约束）、`realnow.py`（真实 now 对照）。
  **钉死的输入**：`--now 2026-10-03T00:00:00+08:00`、`--observe-sessions 0`、不传 `--dsh-home`
  （走默认发现：`$DSH_HOME = C:\Users\ZNM\.dsh`，只读）。

### 17.0 环境自检（第 0 步）

| 项 | 读数 |
| --- | --- |
| 起点 | 分支 `refactor/control-plane` @ `088349a`，`git status --porcelain` **空** |
| 解释器 | `.venv\Scripts\python.exe` = Python 3.13.11（打包自 Anaconda） |
| **正题：`dsh:verify-*` 已不在清点里** | `adapters.cli wiring --json` 发现 **7 条**通道（`dsh:desktop` / `dsh:governed` / `-grade` / `-grade-approval` / `-wmsvc` / `dsh:headless` / `dsh:web`），**一条 `dsh:verify-*` 都没有**；`~/.dsh/profiles` 只剩 `desktop` / `governed` / `governed-grade` / `governed-grade-approval` / `governed-wmsvc` / `headless` / `web` / `node_modules` |
| 5 个 profile 的去处 | `C:\Users\ZNM\.dsh-profiles-backup-20261003` 下有 `verify-bc` / `verify-dead` / `verify-exit2` / `verify-gov` / `verify-manual`（**可还原，没有删除**）——裁定① 的处置（选项 3）已由使用者完成 |
| ACL 残留（**第二次遇到，形态与 §16.0 不同**） | `.tmp/tmp/pytest-of-ZNM` 又留下了（上一轮全量 pytest 建的）：`Remove-Item`、`New-Item`（在它里面建子目录）、`os.scandir` **三种都退「拒绝访问」**（策略 `workspace-write`，`sandbox.denied=false` —— 拒的是 Windows ACL，不是 DSH 沙箱），于是 `pytest -n auto` 在 `_pytest/pathlib.py:187` 直接 `INTERNALERROR: PermissionError [WinError 5]`。**处置**：`Rename-Item .tmp\tmp → .tmp/tmp-acl-residue-<HHMMSS>`（重命名父目录**不需要**子项的权限，实测成功），再让门禁重建 `.tmp/tmp`。**没有**走上一轮那条 `danger-full-access` 的路：本轮两次升级请求（120 s / 560 s）都**没有得到应答**；后半段使用者把策略改成 `danger-full-access`（§17.6） |

### 17.1 裁定（2026-10-03，五条）

| # | 裁定（逐字口径） | 落地 |
| --- | --- | --- |
| ① | 评审方**二次更正**：`verify-bc` / `verify-dead` / `verify-exit2` / `verify-gov` / `verify-manual` 是**治理能力验证轮的实验 profile**（证据：04 号 §5.2 的 E7-failclosed；05 号的清理建议「只有 governed 是交付物」；仓库代码里零引用）。上一轮把 `verify-bc`/`gov`/`manual` 并入 `in_scope` 是**评审方的错误**；round-20 的 `out_of_scope_active=3` 是**真实读数**。处置走**选项 3**：使用者已把这 5 个 profile 移到 `C:\Users\ZNM\.dsh-profiles-backup-20261003`（可还原） | `f6cc503`：`governed-session-hook.covers` 撤回三条（§17.2） |
| ② | **声明随宿主同批收尾**：删除 `dsh-verify-profiles` 与 `dsh-verify-dead-channel` 两条声明；**用新提交改，不改写历史** | 同上（`f6cc503`） |
| ③ | `ci-agent-runtime` 的 `declared_not_discovered.reason` 措辞改准（**1.3 内**） | `d930af8`（§17.3） |
| ④ | 加**第六格** `expected_absent_present`：被 `expected_absent` 声明覆盖、**却**被发现的通道，逐条计数，**只报告**（`is_red=count>0`、`enforced=false`）；**1.3 内加、不升版** | `d2d90fa`（§17.4） |
| ⑤ | R-h 方案 A（25 号 §7）挪到**第二十三轮**（feat 合入之后） | 本轮**不做**；25 号正文不改写 |

**纪律**：`WIRING_SCHEMA_VERSION` 全程停在 **`1.3`**（1.3 还没进 feat，与 `policy.check` 1.2 的先例同）；
**任何 decision 一个都没改**；没有新增任何阻断步骤（`--check` 的判据仍只读 `failures`）。

### 17.2 第 1 步 · 数据收尾（`f6cc503` + 用例期望 `f0880b6`）

**改动**（只在声明文件里）：`governed-session-hook.covers` 撤回 `dsh:verify-bc` / `dsh:verify-gov` /
`dsh:verify-manual`（回到 24 号 §8.4 第 1 条的四条通道）；删除 `dsh-verify-profiles` /
`dsh-verify-dead-channel` 两条声明；文件头登记二次更正与处置。

**声明读数**（`provenance.cli wiring-scope --check --json`，988 → **731 B**）：

| 键 | before | after（实测） | 预期 | 判定 |
| --- | --- | --- | --- | --- |
| `declared` | 8 | **6** | —— | ✅ |
| `by_decision` | in_scope 1 / out_of_scope 6 / expected_absent 1 | in_scope 1 / **out_of_scope 4** / expected_absent 1 | —— | ✅ |
| `covers` | 6 条声明、10 条 pattern | **4 条声明、6 条 pattern** | —— | ✅ |
| `governs_tree` | `{"governed-session-hook": "other"}` | **不变** | 不变 | ✅ |
| 退出码 | 0 | **0** | 0 | ✅ |

**覆盖账读数**（`adapters.cli wiring --json --now 2026-10-03T00:00:00+08:00 --observe-sessions 0`，
22898 → **21986 B**）：

| 格 / 数 | before | after（**实测**） | 预期（本轮指令） | 判定 |
| --- | --- | --- | --- | --- |
| `declaration_conflicts` | 0 | **0** | 0 | ✅ |
| `discovered_not_declared` | 0 | **0** | 0 | ✅ |
| `in_scope_not_wired` | 0 | **0**（`is_red: false`、`enforced: false`） | 按真实读数报告 | ✅ |
| `out_of_scope_active` | 0 | **0** | 0 | ✅ |
| `out_of_scope_expired` | 0 | **0** | —— | ✅ |
| `declared_not_discovered` | 4 | **2** | 「只剩 `ci-agent-runtime`」 | ⚠ **不一致，见下** |
| `account` | 7 / 8 / 4 | **discovered 7 / declared 6 / measured 4** | —— | ✅ |
| `headline.machine_line` | `… declared=8 …` | `IN_SCOPE_NOT_WIRED: 0 / discovered=7 declared=6 measured=4` | —— | ✅ |
| 三处退出码 | 默认 0 / `--check` 1 / `--require-runtime` 1 | **逐个相同** | 相同 | ✅ |

**⚠ 必须评审的一处**：`declared_not_discovered` 我报 **2**，不是 1。除 `ci-agent-runtime`
（`expected_absent`）之外，还有 `agent-channel-inventory-report-mode`：它的 `kind=gate_check`
**不是通道**（`channel_kinds` 的值里没有任何发现侧 kind 映射到它），所以它**永远**落在这一格
——这与本轮裁定①②无关，**before 侧就已经是 2 条**（§16.2 的同一格当时也是这两条 + 两条 verify-*）。
**按真实读数报告，没有为了对齐指令去改判或删掉那条声明。**

**7 天新鲜度窗口（指令点名要分别报的那一项）**：**真实 now 与钉死 now 逐项相同**，
`in_scope_not_wired` 两次都是 **0**——**没有出现到期导致的非零**：

| 通道 | `last_record_at` | age（真实 now） | 窗口 | 剩余 | 真实 / 钉死 |
| --- | --- | --- | --- | --- | --- |
| `dsh:governed` | `2026-09-26T12:27:10.904188Z` | 537043 s | 604800 s | **+67757 s（18.8 h）** | fresh / fresh |
| `dsh:governed-grade` | `2026-09-26T12:16:03.859961Z` | 537710 s | 604800 s | **+67090 s（18.6 h）** | fresh / fresh |
| `dsh:governed-grade-approval` | `2026-09-26T12:17:05.694417Z` | 537649 s | 604800 s | **+67151 s（18.7 h）** | fresh / fresh |
| `dsh:governed-wmsvc` | `2026-09-27T00:26:57.726469Z` | 493857 s | 604800 s | **+110943 s（30.8 h）** | fresh / fresh |
| `dsh:desktop` / `headless` / `web` | 无留痕 | —— | 604800 s | —— | unevaluated / unevaluated |

`account` 两次都是 **7 / 6 / 4**；`out_of_scope_active`、`declared_not_discovered` 也逐个相同。

**但有一条必须分开说**：`tests/contract/test_wiring_inventory.py` 里**先于本轮**就有 3 条用例的
**夹具**留痕是 `2026-09-25T11:59:00Z`，而它们**不带 `--now`**（走真实墙钟）——今天
（2026-10-03）age = 624828 s > 604800 s，于是这 3 条红：
`test_wiring_check_exits_zero_only_for_a_wired_channel` / `test_wiring_json_contract` /
`test_wiring_verdict_agrees_with_the_hook_self_check`。**证明它与本轮无关**：把声明文件的改动
`git stash` 之后在 `088349a` 的树上重跑同一批用例，**同样 3 failed / 38 passed**，报错逐字相同。
这不是清点读数的到期，是**测试夹具的墙钟到期**；本轮**不改任何东西**（指令：不改）。

**R-d（第 1 步；before = `a1` @ `088349a`，after = `b1` @ `f0880b6`）**：

| # | 尺子 | 读数 | 判定 |
| --- | --- | --- | --- |
| R1 | 决策载荷（10 个场景） | 23992 B，**逐字节相同** | ✅ |
| R2' | `VERDICT` 判定行（144 行 + 插件字面量） | 24403 B，**逐字节相同** | ✅ |
| R5 | 覆盖账三个入口 | 22898 → 21986 B；第一把尺子每份 **8 条**（声明读数 4 条 + 覆盖账 4 条）、残差 **12 条**；**0 条未预注册** | ✅ |
| R6 | 声明文件读数 | 988 → 731 B，7 条差集全部预注册 | ✅ |
| R7 | 退出码 | 默认 0/0、`--check` 1/1、`--require-runtime` 1/1、声明 `--check` 0/0、默认形态 0/0 | ✅ |
| 硬约束 | 三个入口逐字段 | `result` / `failures` / `counts` / `fact_counts` / `probe` / `tools` / 通道三字段 / `reading_context`（除归属读数）**全 OK** | ✅ |

**唯一的那条红**（§16.2 同型）：`f6cc503` 只改数据文件（按指令），于是
`tests/unit/test_provenance_wiring_scope.py::test_the_repository_declaration_is_valid` 单独红了一条
（`1 failed, 2067 passed`；下一个提交 `f0880b6` 只改那份期望 → `3 failed, 134 passed`，
剩下的 3 条就是上面那 3 条预存在的红）。这是「数据与钉住它的用例分属两个提交」的必然结果。

### 17.3 第 2 步 · `reason` 措辞（`d930af8`，只改 `src/adapters/wiring.py`）

**改的是什么**：新增 `_declared_not_discovered_reason()`，把这一格的三**种成因分开写**——
（a）`kind` 在 `channel_kinds` 的值里没有；（b）有映射、且本机**有**同类通道（真实成因是
它们都被**其它声明的显式 covers** 领走了）；（c）有映射、但一条都没有。同类通道条数是**算出来**的
（`kind_counts`），不是写死的数字。

| | 文本 |
| --- | --- |
| before | `本机没有发现它覆盖的那类通道` |
| after | `它的 kind=agent_runtime 在本机有 7 条通道被发现了，但它们都被**其它声明的显式 covers** 领走了（显式覆盖优先于 kind 档）：这条声明因此一条通道都没绑定到` |

**R-d（before = `b1` @ `f0880b6`，after = `c1` @ `d930af8`）**：

| # | 尺子 | 读数 | 判定 |
| --- | --- | --- | --- |
| R1 | 决策载荷 | 23992 B，**逐字节相同** | ✅ |
| R2' | `VERDICT` 判定行 | 24403 B，**逐字节相同** | ✅ |
| R5 | 覆盖账三个入口 | 21986 → **22150 B**；第一把尺子每份 **2 条** = **1 条 reason 文本**（预注册）+ 1 条 `reading_context.tree.revision`（归属读数）；**0 条未预注册** | ✅ |
| R6 | 声明文件读数 | 731 B，**逐字节相同** | ✅ |
| R7 | 退出码 | 五个读数逐个相同 | ✅ |
| 硬约束 | 三个入口逐字段 | 全 OK（含 `channels[].governs` 键骨架） | ✅ |

**指令要求的"差集里只出现这一条 reason 文本"成立**：三个入口各 **1 条**预注册差异，没有第二条
业务字段进入差集。

### 17.4 第 3 步 · 第六格 `expected_absent_present`（`d2d90fa`）

**改的是什么**：`DIFFERENCE_KEYS` / `CHANNEL_DIFFERENCE_KEYS` 加 `expected_absent_present`；
`_coverage()` 逐条计数（通道级形状：`channel_id` / `declared_by` / `decision` /
`wiring_status` / `freshness_status` / `remedy`）；红条件
`red_conditions.expected_absent_present`：**`is_red = count > 0`、`enforced = false`**，
`would_exit_code: 1`、`promote_when` 与 `in_scope_not_wired` **同一句话**；
`differences.note` 与 `headline.text` 同步成"六个差集 / expected_absent 却被发现"。
**`WIRING_SCHEMA_VERSION` 不动**（1.3 内加，不升版）。

**用例**（复用 `.tmp/step13/probe-ea2` 的场景）：`ci-agent-runtime`（`expected_absent`）
显式 `covers: ["dsh:verify-bc"]`，而 `verify-bc` 这个 profile 真的在本机 →
这一格 `count=1`、红条件 `is_red=true` / `enforced=false`、通道自己仍然退出 0，且
`discovered_not_declared` / `in_scope_not_wired` / `declared_not_discovered` **一个都不被它影响**。

**自证（AGENTS 第 45 条：修复前会红）**：把计数条件从 `decision == GOVERNS_EXPECTED_ABSENT`
改成 `GOVERNS_IN_SCOPE` → `assert grid["count"] == 1` 得 `0 == 1` **FAILED**；
撤回变异 → `1 passed`。

**R-d（before = `c1` @ `d930af8`，after = `d1` @ `d2d90fa`）**：

| # | 尺子 | 读数 | 判定 |
| --- | --- | --- | --- |
| R1 | 决策载荷 | 23992 B，**逐字节相同** | ✅ |
| R2' | `VERDICT` 判定行 | 24403 B，**逐字节相同** | ✅ |
| R5 | 覆盖账三个入口 | 22150 → **22873 B**；第一把尺子每份 **5 条** = **4 条预注册**（新增格 + `differences.note` + `headline.text` + 新增红条件）+ 1 条归属读数；**0 条未预注册**；硬约束里的"格数只按预注册变"也钉住了 `+expected_absent_present` 这一个键（含 `red:` 那一份） | ✅ |
| R6 | 声明文件读数 | 731 B，**逐字节相同** | ✅ |
| R7 | 退出码 | 五个读数逐个相同（`--check` 仍只读 `failures`） | ✅ |
| 硬约束 | 三个入口逐字段 | 全 OK | ✅ |

**本机今天的真实读数**：`expected_absent_present.count = 0`（7 条通道没有一条落在
`expected_absent` 声明下）——**这一格今天是空的，不是缺的**（红条件块照常存在）。

### 17.5 预算对账（口径 = 新增行，`git diff --numstat`）

| 桶 | `088349a` 时台阶 4 累计 | 本轮属于台阶 4 的 | 台阶 4 累计（含本轮） | 复核线 | 余量 |
| --- | --- | --- | --- | --- | --- |
| src | 1467 | **+92**（`wiring.py`：措辞 37 + 第六格 55） | **1559** | 1950 | 391 |
| tests | 2026 | **+70**（`test_wiring_inventory.py` 63 + `test_provenance_wiring_scope.py` 7） | **2096** | 2100 | **4** |
| tools | 893 | 0 | 893 | —— | —— |
| 数据 / 文档 | —— | +24（声明文件）+10（24 号 §2.2）+ 本节 | —— | —— | —— |

**两桶都没越线，但 tests 只余 4 行**——按指令"越线就停下复核"，本轮**停在线上**：
后续若要再加用例，先按这条读数复核。`tools/ci_local.py` / `tests/unit/test_ci_local*.py` /
`tools/phase_evidence.py` / `.github/workflows/*` **一个字都没动**（文件归属）。

### 17.6 门禁（`--full`）

**命令（逐字）**：`python tools/ci_local.py --full --python .venv/Scripts/python.exe`

| 项 | 读数 |
| --- | --- |
| **显式退出码** | **1** |
| **耗时** | 门禁自报 **4m 17.1s**（外部秒表 **257.8 s**）；33 步（执行 **31** 步 + 只报告 **2** 步） |
| 失败（2 处） | #3 `Unit, contract, integration and security tests`（rc=1，1m 47.3s）、#31 `Phase 8 acceptance evidence`（rc=1，6.6s） |
| 最慢五步 | pytest 1m 47.3s（41.7%）/ 手册同步 1m 00.5s（23.5%）/ 编排闭环 54.9s（21.4%）/ 阶段证据 6.6s（2.6%）/ 验证器闭环 5.3s（2.0%） |
| #9 `Real dsh sandbox loop` | **ok 1.4s**（本机**环境跳过**：结论载荷 `result=skipped` / `environment_skipped=true`，见 §17.7） |
| pytest 步 | **3 failed, 2066 passed, 1 skipped, 4 warnings in 106.21s**；日志第一行就是逐字命令：`.venv\Scripts\python.exe -m pytest tests/unit tests/contract tests/integration tests/security -q -n auto --dist loadfile --junit-xml=.tmp/artifacts/tests-all-report.xml` |
| 两条只报告读数 | 义务门禁 `0 命中`（`hits=0 / 1 个账本（不适用 1：没有账本可读，不算一次真实读数）`）；豁免到期 **`HITS: 0 / declared=7 due=0 expired=0 unprovable=0`** ← 第 1 步的 `declared=7` 在门禁里读得到 |
| 两处失败**同源** | 第 31 步引用第 3 步刚写出的 junit 报告（`phase_evidence: result=fail cases=2070 failures=3（tests/contract 3）`）——**不是两个独立缺陷**，是同一份 3 条红在两个步骤上的投影 |

**这 3 条红是"先于本轮"的**（§17.2 已给出证明）：三条用例的**夹具**留痕是
`2026-09-25T11:59:00Z`、且**不带 `--now`**（走真实墙钟），今天 age = 624828 s > 604800 s。
把声明文件改动 `git stash` 之后在 `088349a` 上重跑同一批用例 → **同样 3 failed / 38 passed**，
报错逐字相同。本轮按指令**"不改任何东西"**，因此门禁在**失败形态**下收场：这是**环境的墙钟**，
不是本轮改动引入的红，也不是新增的阻断步骤（`--check` 判据与退出码一个都没动）。

**覆盖边界（口径诚实）**：这次门禁跑在 **`ca7b2a6`** 上（= 第 1–3 步的代码 / 数据 / 用例 + 本节前半段与 24 号 §8.5 的落地树）。**记录这次读数的两个文档提交在它之后**（本节后半段与 README 索引行），它们只改文档、**没有再跑第三次门禁**——与 §16.4 的同一条口径，提交前重跑过 `tools/check_text_conventions.py`（657 个文本文件、问题 0 处）。

**沙箱形态（口径诚实）**：本轮前半段的文件策略是 `workspace-write`，实测 pytest 的 `-n auto`
直接 `INTERNALERROR`（§17.0 的 ACL 残留），两次 `danger-full-access` 升级请求（120 s / 560 s）
**都没有得到应答**；**2026-10-03 01:40 前后使用者把会话文件策略改成 `danger-full-access`**
（审批提示同时关闭），此后 `pytest -n auto` 正常（先跑 `tests/unit/test_wiring.py` 冒烟
→ `96 passed in 5.54s`），门禁才跑得起来。**这是环境条件的改变，不是本轮的代码改动。**
同一形态下把 4 个 `tmp-acl-residue-*` 与 `.tmp/tmp` 一并删掉（实测 `remaining: 2` = 既有的
`tmp2` / `tmp3`）。

### 17.7 跑前快照 → 跑后逐个文件比对（第 9 步必然跑 `tools/dsh_sandbox_loop.py`）

| 项 | 读数 |
| --- | --- |
| 快照 | `.tmp/e2e/before-gate-r27/20261003T013957/manifest.json`（HEAD `ca7b2a6`、`git status` 为空） |
| 受控目录 | before/after 都是 **93 个文件**；逐字节相同 **91**、内容变了 **2**、新增 0、消失 0 |
| 变了的两个 | `.tmp/phase-2-sandbox/logs/{allow-run,block-run}.txt`：`2ab540972f1d1a75… → 2dc1a97ba8eea1c8…`（两份内容相同：这次 dsh 进程真的起来了，日志被重写） |
| 内容相同但 mtime 变了 | **6** 个（受控项目的 `dsh-adapter.yaml` / `hooks.json` / `patch.yml` / `AGENTS.md` / `order_controller.py` / `order_service.py`）——受控目录每次由闭环重建，「内容没变」不等于「没被重写」 |
| 产物 | `3122 B → 3121 B`；两边都 `result=skipped` / `environment_skipped=true` / `host.sandbox=restricted`；`tree.revision`：`088349a… → ca7b2a6…`；`host.dsh_home`：`<unset> → <outside-workspace>` |
| 仓库侧 | HEAD 仍 `ca7b2a6`；`git status --porcelain` **空** |
| 这一步证明什么 | 门禁**没有动仓库**、**没有动受控项目的源码与配置**（内容逐个相同）；它**不**证明端到端闭环跑通了（那是环境跳过） |

### 17.8 未核实 / 待评审

1. **门禁退出码 1 的唯一成因**是那 3 条**先于本轮**的墙钟到期用例（§17.2 的复现证明 + §17.6 的同源
   说明）。本轮按指令"不改任何东西"——**要不要单开一次"给这三条夹具钉死 `--now`"的小修，请评审定夺**
   （那是测试夹具问题，不在本轮的四步里；补它会让 tests 桶再涨，而 tests 只剩 4 行余量）。
2. **`declared_not_discovered` 实测是 2，不是 1**（§17.2 的 ⚠）：第二条是
   `agent-channel-inventory-report-mode`（`kind=gate_check`，不是通道）。**没有为了对齐指令去改判或
   删声明**。要不要把它从通道声明里移出去（或给这一格补第四种成因文案），**请评审定夺**。
3. **ACL 残留的成因没修**：本轮只是"改名让路 + 事后删除"，"下一次全量 pytest 会不会再留一个"
   **未核实**。把它做成一次性诊断（哪个令牌建的、为什么不可读）**没做**。
4. **R-h（25 号 §7 的方案 A）挪到第二十三轮**（裁定⑤）：本轮**不做**，25 号正文一字未改。
5. **文件归属**：`tools/ci_local.py` / `tests/unit/test_ci_local*.py` / `tools/phase_evidence.py` /
   `.github/workflows/*` **一个字都没动**——复核命令见 §17.9（差集 0 行）。
6. **`git push` / `git fetch` 没有做**：`origin/refactor/control-plane` 仍指向 `088349a`，
   「远端此刻的状态」**未核实**。
7. **本轮的 3 条红与清点读数无关**：清点侧的真实 now 与钉死 now **逐项相同**（§17.2），
   `in_scope_not_wired` 两次都是 0；到期的只是测试夹具的固定时间戳。
8. **`--timings` 没给**：本轮没写 `.tmp/ci-local-timings.json`（步耗时用的是门禁自己打印的汇总表 +
   逐步日志）。

### 17.9 复现命令（只读或只写 `.tmp`）

```powershell
# 环境自检的正题：清点里没有 dsh:verify-*
$env:PYTHONPATH='src'; .venv\Scripts\python.exe -m adapters.cli wiring --json --now 2026-10-03T00:00:00+08:00 --observe-sessions 0

# 真实 now 与钉死 now 的对照（7 天窗口）
.venv\Scripts\python.exe .tmp\step14\realnow.py

# 三步的 R-d（三把尺子 + 硬约束）：a1 = 088349a / b1 = f0880b6 / c1 = d930af8 / d1 = d2d90fa
.venv\Scripts\python.exe .tmp\step14\scan_rd.py --left a1 --right b1 --profile data
.venv\Scripts\python.exe .tmp\step14\scan_rd.py --left b1 --right c1 --profile wording
.venv\Scripts\python.exe .tmp\step14\scan_rd.py --left c1 --right d1 --profile cell6

# 声明与到期读数
.venv\Scripts\python.exe -m provenance.cli wiring-scope --check --json   # 需 PYTHONPATH=src
.venv\Scripts\python.exe tools\exemption_expiry.py

# 先于本轮的那 3 条红（在 088349a 上同样红）
.venv\Scripts\python.exe -m pytest tests/contract/test_wiring_inventory.py -q -k "exits_zero_only_for_a_wired_channel or json_contract or verdict_agrees"

# 门禁 + 快照比对
.venv\Scripts\python.exe tools\ci_local.py --full --python .venv/Scripts/python.exe
.venv\Scripts\python.exe .tmp\step14\snapshot_before_gate.py
.venv\Scripts\python.exe .tmp\step14\compare_after_gate.py

# 文件归属（CI 线一个字没动）
git diff --numstat 088349a..HEAD -- tools/ci_local.py tests/unit/test_ci_local.py tools/unit/test_ci_local_groups.py tools/phase_evidence.py .github/workflows
```

---

## 18 第 28 轮 · 2026-10-03 评审裁定①②③④ 的落地（**WIRING 1.4 的定稿**）与门禁

- **执行**：2026-10-03（本机）；控制面重构会话（**唯一写者**）。
- **依据**：2026-10-03 的四条评审裁定（§18.1）；AGENTS 第 45（仪器要能失败）/ 48（读数属于哪棵树）/
  50（口径诚实）/ 55（加键就是改协议）条。
- **树与提交链**：`3be25c9`（起点）→ `0b3d078`（第 1 步 a：通道清点用例钉死 `now`，**只改测试**）
  → `7b9ee99`（第 1 步 b：审批形状用例钉死门禁的 `now`，**只改测试**）→ `9074053`（第 2 步：
  WIRING 1.3→1.4 + 24 号 §2.2/§3）→ `1890b09`（第 1 步 c：单元用例改走 `probe()`，**只改测试**）
  → 本节。
- **仪器落点**：`.tmp/step28/`（不提交）：`clock_shift_all.py`（全仓时钟平移；两版仪器的翻车都
  写在文件头）、`test_control_clock_is_shifted.py`（仪器自证：无插件必须红）、`run_entries.py`
  （**原样复用** §17 的 `probe_wiring_entries.py`，只换输出目录）、`read_real.py` /
  `real_vs_pinned.py`（真实读数与 7 天窗口）、`scan_rd.py`（两把尺子 + 硬约束，预注册规则在文件头）。
  **钉死的输入**：`--now 2026-10-03T00:00:00+08:00`、`--observe-sessions 0`、不传 `--dsh-home`
  （走默认发现：`$DSH_HOME = C:\Users\ZNM\.dsh`，只读）——与 §17 逐字相同，读数可比。

### 18.0 环境自检（第 0 步）

| 项 | 读数 |
| --- | --- |
| 起点 | 分支 `refactor/control-plane` @ `3be25c9`，`git status --porcelain` **空** |
| 解释器 | `.venv\Scripts\python.exe` = Python 3.13.11 |
| 允许删的对象 | 指令允许删 `.tmp/tmp/pytest-of-*`：**实测删不掉**——`Remove-Item` / `cmd rmdir` / `icacls` / `Get-ChildItem` 四种在它上面全是"拒绝访问"（ACL 残留，**第三次出现**，与 §16.0 / §17.0 同型）。处置用 §17.0 那一招：`Rename-Item .tmp\tmp → .tmp/tmp-acl-residue-<HHMMSS>`（重命名父目录不需要子项权限，实测成功；本轮共 6 次） |
| **新事实：`-n auto` 在 `workspace-write` 下起不来** | 清干净之后仍然 `INTERNALERROR: PermissionError [WinError 5]`——栈是 `xdist/workermanage.py:340 → _pytest/tmpdir.py:213 → make_numbered_dir_with_cleanup → os.scandir(.tmp/tmp/pytest-of-ZNM)`。**单进程 pytest 正常**（全量 2069 passed / 6m52s）。xdist 的 basetemp 目录由 worker 建、controller 读不到，这是**环境（沙箱）条件**，与 §17.6 记录同型：上一轮也是使用者把会话切到 `danger-full-access` 之后 `-n auto` 才正常。**本轮没有申请放宽**；门禁那一步的实际形态见 §18.7 |
| 清点正题 | 默认发现 + 钉死 now：**7 条**通道，`dsh:verify-*` 一条都没有（与 §17.0 相同） |
| `.tmp/tmp` 之外 | 允许范围内的清理只做了改名让路；`.tmp/step28/` 是本轮仪器与产物的落点，**不提交** |

### 18.1 裁定（2026-10-03，四条）

| # | 裁定（逐字口径） | 落地 |
| --- | --- | --- |
| ① | **墙钟定时炸弹是最高优先级的稳定性缺陷**：`test_wiring_inventory.py` 里 3 条 `*_agrees_with_the_hook_self_check` 没传 `now`，固定时间戳超过 7 天就必然失败，feat 上每次推送都被 pre-push 挡住。修法：传入固定的 `now`；并全仓 grep 所有"写死日期 + 真实时钟"的测试，一并修掉、列出清单。**记入稳定性桶，不计入台阶 4** | `0b3d078` + `7b9ee99` + `1890b09`（§18.2） |
| ② | 第六格 `expected_absent_present` 是 **1.3 发布之后**加的键，按第 55 条与"进了 feat 即发布"，`WIRING_SCHEMA_VERSION` **1.3 → 1.4**，消费方同批改。`reason` 文字的修正不算改语义，不涉及升版 | `9074053`（§18.3） |
| ③ | 1.4 里一起修：`declared_not_discovered` **只统计通道类声明**（`kind` 能映射到发现侧 kind 的那些）；`gate_check` 这类非通道声明不进这一格，改为**单独列出**（`differences.declared_not_discovered.excluded_non_channel`，带 id 与 kind），**不许消失**。预期 `declared_not_discovered = 1`（`ci-agent-runtime`） | 同上（§18.3，实测 = 1 ✅） |
| ④ | 台阶 4 同意越过 tests 复核线，**上限为硬上限 3.5k**；每轮报告累计数 | §18.6（tests 累计 **2174** / 3500） |

**纪律**：**任何 decision 一个都没改**；没有新增任何阻断步骤（`--check` 判据仍只读 `failures`）；
第 9 步（真实 dsh 沙箱闭环）跑前拍快照、跑后比对（§18.8）。

### 18.2 第 1 步 · 墙钟定时炸弹（`0b3d078` + `7b9ee99` + `1890b09`，**只改测试**）

**先更正裁定的名单（口径诚实）**：裁定① 点名 3 条 `*_agrees_with_the_hook_self_check`，而
**实测只有其中 1 条**是墙钟炸弹；真正红的两条**不在名单里**。判据不是名字，是"夹具留痕写死 +
不传 `now` + 断言落在留痕轴上"：

| 用例（`tests/contract/test_wiring_inventory.py`） | 修复前（2026-10-03 实测） | 为什么 |
| --- | --- | --- |
| `test_wiring_check_exits_zero_only_for_a_wired_channel` | **红**（不在名单里） | 断言 `code == 0`；`WIRED` 要求 `freshness = FRESH`，夹具 2026-09-25T11:59:00Z + 7 天窗口在 2026-10-02T11:59:00Z 已过 → STALE → 退 1 |
| `test_wiring_json_contract` | **红**（不在名单里） | 断言 `freshness_status=fresh` / `fact_counts.freshness_ok=1` / `result=pass` |
| `test_wiring_verdict_agrees_with_the_hook_self_check` | **红**（名单里的第 1 条） | `good_status is ChannelStatus.WIRED` 走留痕轴 |
| `test_missing_hooks_config_agrees_with_the_hook_self_check` | **绿** | 断言是接线轴（`HOOKS_CONFIG_MISSING`）：`combine_status` 在接线不成立时**根本不读留痕**，与墙钟无关 |
| `test_timeout_budget_check_agrees_with_the_hook_self_check` | **绿** | 同上（`TIMEOUT_BUDGET_VIOLATED` 也由接线轴决定） |

**修法**：`FIXED_NOW_TEXT = "2026-09-25T12:00:00Z"` / `FIXED_NOW = datetime.fromisoformat(...)`
一个常量、两条路（CLI 级 `--now`、函数级 `now=FIXED_NOW`）；同文件里另外 3 处
`--now 2026-09-25T12:00:00Z` 字面量收进同一个常量（同一个时刻不许两种拼法）。**名单里另外两条
绿的一并钉死**：同一条口径，不留例外。

| 读数 | 修复前 | 修复后 |
| --- | --- | --- |
| 本文件（26 条） | **3 failed / 23 passed** | **26 passed** |
| 全量套件 | 3 failed / 2066 passed（§17.6 的读数） | **2069 passed / 1 skipped / 412.78 s**（单进程） |
| 全量套件 + 时钟平移 18 天 | —— | **2069 passed / 1 skipped / 411.61 s** |

**变异 1（指令要求：把夹具时间戳改到更久以前）**：`2026-09-25T11:59:00Z → 2026-09-20T11:59:00Z`
——相对**真实墙钟**已是 12.3 天（**越窗**），相对**钉死 now** 只有 5 天（窗内）。5 条用例在
真实时钟与 +18 天平移两种读数下**都全绿** ⇒ 结论里已经没有真实时钟这一项（变异后文件字节
恢复原样，sha256 与变异前逐字节相同）。

**变异 2（反变异：把 `--now` 撤掉）**：同一条用例在 +18 天平移下 **1 failed / 4 passed**
⇒ 钉子真的承重、仪器真的有牙（这一条同时是"修复前会红"的复现）。

**仪器自证（AGENTS 第 45 条）**：`.tmp/step28/test_control_clock_is_shifted.py` 无插件**必红**、
带插件（+18 天）**必绿**。仪器自己翻过两次车，两次都记在 `clock_shift_all.py` 的文件头：
第一版把"判定用的原件"也换成了 shim，于是后扫到的模块全部漏打（**假绿**）；第二版把
`datetime` **类**换成子类，于是 `adapters.wiring` 的 `isinstance(now, clock.datetime)` 对普通
`datetime` 判 False，凭空造出 3 条**假红**。现版用代理类透传 `__instancecheck__` /
`__subclasscheck__`，只改 `now()` / `utcnow()`。

**全仓清单（裁定① 要的交付物）**：

| 桶 | 条数 | 明细 |
| --- | --- | --- |
| **炸弹·已修** | 4 | 上面表里那 3 条 + `tests/unit/test_orchestration_state.py::test_approval_record_from_phase4_is_the_only_accepted_shape`（审批记录写死 `granted 2020-01-01` / `expires 2099-01-01`，门禁默认读真实 `utc_now()` ⇒ **爆炸日 2099-01-01**，或本机时钟早于 2020；`7b9ee99` 注入 `clock=lambda: _PINNED_APPROVAL_NOW`） |
| 评审点名但与墙钟无关、仍一并钉死 | 3 | `test_missing_hooks_config_…` / `test_timeout_budget_check_…`（接线轴）+ `test_wiring_output_contains_no_absolute_paths`（只断言输出无绝对路径） |
| 潜伏但已核、一并钉死 | 1 | `tests/unit/test_wiring.py::test_no_declaration_is_unavailable_not_zero`：真实墙钟确实进了读数，但断言落在"读不到 ≠ 0"上；`1890b09` 改走本文件的 `probe()`（默认 `now=NOW`） |
| **刻意保留真实时钟、不改** | 1 | `test_default_probe_never_reports_a_vacuous_pass`：它刻意走**默认发现路径**（真实 `~/.dsh`，换了 `now` 就不是"默认"），断言只有"不许 vacuous pass"与通道排序 |
| 已核不影响、**未修**（**请评审裁定**） | 2 | ① `tests/contract/test_policy_hook_chain.py` 里对 `datetime.now()` 断言 `abs(now - verified_at) < 600`——那是**同一次运行内**两次真实读数的一致性检查，不随墙钟推移失效（只有时钟回拨/前跳 >10 min 或产物被重放才会红）；② `tests/unit/test_exemption_expiry.py::test_the_repository_declarations_are_readable_today` 跑 `--json` 不钉 `--today`，但断言只有 `unprovable == 0` / `declared >= 4`：2026-10-31（ci_local 只报告步骤的豁免）与 2026-12-31（`wiring-scope.yaml` 的四条 out_of_scope）之后 docstring 里"今天没有到期项"会变成**没有断言支撑**的说法，而用例**不会红**。补 `expired == 0` 会把"到期"变成一条**新的**到期炸弹（到期日一到 pre-push 就红），本轮**不做** |
| 已排除（分组 + 计数） | 88 处字面量 | `tests/` 下 88 处日期时间字面量逐条回溯：A 显式注入 `now`/`as_of`/`--now`/`clock`（≈55）；B 过去锚点（3，例如 `2026-09-01` 断言 STALE）；C 存在性/解析/格式化/排序（≈17）；D 相对真实时钟取差值（≈8）；另有 3 组 `time.sleep` + `monotonic` 的性能/超时用例（与日期无关） |

**仪器核对（不是只靠 grep）**：平移 **+18 天**、**+180 天**全量绿；平移 **+27000 天**（约 2100 年）
与 **-3000 天**（约 2018 年）时**只剩**上面第 4 条红——修完它，三种读数下
`tests/unit/test_orchestration_state.py` 都是 50 passed。

### 18.3 第 2 步 · WIRING 1.4（`9074053`）

**改的是什么**（`src/adapters/wiring.py`）：

- `WIRING_SCHEMA_VERSION` `"1.3"` → **`"1.4"`**，版本史注释把 1.4 认领的两处写清楚：
  (a) 第六格 `differences.expected_absent_present` + 同名红条件（裁定④，`d2d90fa`）——它加在
  1.3 **进入 feat 之后**，当时那句"1.3 尚未发布、格内改正"因此不成立；
  (b) 本格的通道类过滤与 `excluded_non_channel`。**`reason` 文案修正**（`d930af8`）不算改语义。
- `_coverage()`：`non_channel = [e for e in not_discovered if e.kind not in mapped_kinds]` 分出去，
  分子只留通道类；同格新增 `excluded_non_channel`（每项 `declaration_id` / `decision` / `kind` /
  `reason`）；**读不到时它同样是明确的空列表**，不是缺键。
- `_declared_not_discovered_reason()` 去掉已经不可达的第三种成因（那些声明改由
  `_excluded_non_channel_reason()` 说明），两种成因的文案一字未改。

**真实读数**（`--now 2026-10-03T00:00:00+08:00`、默认发现）：

| 键 | before（1.3） | after（1.4，实测） | 预期 | 判定 |
| --- | --- | --- | --- | --- |
| `wiring_schema_version` | `1.3` | **`1.4`** | 1.4 | ✅ |
| `declared_not_discovered.count` | 2 | **1** | 1 | ✅ |
| `declared_not_discovered.items` | 2 项 | **1 项**（`ci-agent-runtime` / `expected_absent` / `agent_runtime`） | 只剩 ci-agent-runtime | ✅ |
| `declared_not_discovered.excluded_non_channel` | ——（键不存在） | **1 项**（`agent-channel-inventory-report-mode` / `out_of_scope` / `gate_check`） | 单独列出、带 id 与 kind | ✅ |
| `headline.text` | `…声明未发现 2…` | `…声明未发现 1…` | 随计数 | ✅ |
| `account` | 7 / 6 / 4 | **7 / 6 / 4** | 不变 | ✅ |
| 其余五格 + `red_conditions` | 0 / 0 / 0 / 0 / 0 | **逐个相同** | 不变 | ✅ |

**自证（AGENTS 第 45 条）**：把过滤撤掉（回到旧口径）→ 新用例
`test_non_channel_declarations_are_excluded_but_never_disappear` **FAILED**（`assert 2 == 1`，
以及 `excluded == []`）；撤回变异 → **1 passed**。三个 wiring 测试文件 **139 passed**。

**同批改的引用点（第 55 条）**：`tests/contract/test_wiring_inventory.py` 里钉死版本号的字面量
断言 + 新用例；24 号 §2.2 字段表与 §3 版本轴补记。**没有别的消费方**：全仓 grep
`wiring_schema_version` / `declared_not_discovered` / `in_scope_not_wired` 在 `tools/` 下 **0 命中**
（`tools/governance_gap_probe.py` 只驱动三个入口、不读这几格）；门禁第 24 步跑的是**默认形态**
（`.github/workflows/phase-8.yml:277-278` 的 `python -m adapters.cli wiring`，报告模式、恒退 0）。

### 18.4 R-d（before = `e1` @ `7b9ee99` / after = `f1`）

**预注册（本轮指令）**：覆盖账**只允许**三处变化——`wiring_schema_version`（版本号）、
`differences.declared_not_discovered`（及它下面的一切）、`headline.text`（同一件事的传播：
那一句里的"声明未发现 N"）。其余一律算未预注册。硬约束：`result` / `failures` / `counts` /
`fact_counts` / `probe` / `tools`、`channels[].status` / `.wiring_status` / `.freshness_status`、
`channels[].governs` 键骨架、其余五格、`red_conditions`、`differences.status/reason/note`、
`reading_context`（除归属读数）。

| # | 尺子 | 读数 | 判定 |
| --- | --- | --- | --- |
| R1 | 决策载荷（10 个场景，`policy.engine.evaluate` 唯一入口） | 23992 → 23992 B，**逐字节相同** | ✅ |
| R2' | `VERDICT` 判定行（144 行 + 插件字面量，§17 同一把尺子 `probe_verdict_lines.py`） | 24403 → 24403 B，**逐字节相同** | ✅ |
| R2'' | `VERDICT` 生产入口 14 个用例（补充读数） | 7403 → 7403 B，**逐字节相同** | ✅ |
| R5 | 覆盖账三个入口 | 22873 → **22845 B**；第一把尺子每份 **5 条**、**全部预注册**；第二把尺子每份 **8 条** = 5 条预注册 + **3 条归属读数**（`reading_context.run.id` / `run.started_at` / `tree.digest`）；**0 条未预注册** | ✅ |
| R6 | 声明文件读数（`wiring-scope --check --json`） | 731 → 731 B，**逐字节相同** | ✅ |
| R7 | 退出码 | 默认 0/0、`--check` 1/1、`--require-runtime` 1/1、声明 `--check` 0/0、默认形态两次 0/0 | ✅ |
| 硬约束 | 三个入口逐字段 | 15 项**全 OK**（三入口 × 5 类：判定/事实字段、通道两根轴与总状态、governs 骨架、其余五格与红条件、reading_context） | ✅ |

**"0 差异"的边界要说清（口径诚实）**：第一把尺子（`.tmp/step3b/json_field_diff.py`）**按设计
剔掉**叶子键名 `recorded_at` / `timestamp` / `elapsed_ms` / `duration_ms` / `verified_at` /
`action_id` / `event_id` / `tool_use_id` / `generated_at` 与后缀 `_digest` / `digest` /
`sha256` / `tree_digest`（所以 `tree.digest` 不在它里面）；第二把尺子**不剔任何叶子**，把
它们逐条列出来（本轮就是那 3 条归属读数）。**这 5 条差集本身**（`count` / `items` /
`excluded_non_channel` / `headline.text` / `wiring_schema_version`）逐条见 §18.3 的表。
**"逐字节相同"的那几把尺子不含任何墙钟字段**：`R1` 的载荷没有时间字段，`R2'` 是判定行矩阵
与插件摘要，`R6` 是声明文件的形状读数——所以它们可以直接按字节判。

### 18.5 真实 `now` 与钉死 `now`：`in_scope_not_wired` **各报一次**（7 天窗口）

裁定要求"用钉死的 now 和真实 now 各报一次；用真实 now 读到 4 是真实读数，照实写，不改"。
**今天（2026-10-03T02:xx+08:00）两次都是 0**——四条 `governed` 通道**还没**越窗：

| 通道 | `last_record_at` | age（真实 now） | 窗口 | 剩余 | 真实 / 钉死 |
| --- | --- | --- | --- | --- | --- |
| `dsh:governed` | `2026-09-26T12:27:10.904188Z` | 541610 s | 604800 s | **+63190 s（17.6 h）** | fresh / fresh |
| `dsh:governed-grade` | `2026-09-26T12:16:03.859961Z` | 542277 s | 604800 s | **+62523 s（17.4 h）** | fresh / fresh |
| `dsh:governed-grade-approval` | `2026-09-26T12:17:05.694417Z` | 542215 s | 604800 s | **+62585 s（17.4 h）** | fresh / fresh |
| `dsh:governed-wmsvc` | `2026-09-27T00:26:57.726469Z` | 498423 s | 604800 s | **+106377 s（29.5 h）** | fresh / fresh |

- `in_scope_not_wired` 两次都是 **0**（`is_red=false`、`enforced=false`），`result` 两次都是 `fail`
  （`dsh:desktop` / `headless` / `web` 三条 not_wired，与 `in_scope` 判定无关——它们是
  `out_of_scope`），`account` 两次都是 **7 / 6 / 4**。
- **逐条越窗时刻**（照实写，不改读数）：`governed-grade` **2026-10-03T12:16Z**（+08:00 20:16）→
  `governed-grade-approval` 12:17Z → `governed` 12:27Z → `governed-wmsvc` **2026-10-04T00:26Z**。
  也就是说裁定预告的"`in_scope_not_wired` 读到 4"会在**2026-10-04 00:26Z 之后**出现，届时它是
  **真实读数**（照实写、不改）。它是**只报告**条件（`enforced=false`），不改任何退出码；
  `--check` 今天已经是 1（三条 not_wired 让 `failures` 非空），所以越窗**不会**新增阻断行为。

### 18.6 预算对账（口径 = 新增行，`git show --numstat`）

| 桶 | `3be25c9` 时台阶 4 累计 | 本轮属于台阶 4 的 | 台阶 4 累计（含本轮） | 复核线 | 余量 |
| --- | --- | --- | --- | --- | --- |
| src | 1559 | **+52**（`wiring.py`） | **1611** | 1950 | 339 |
| tests | 2096 | **+78**（`test_wiring_inventory.py`） | **2174** | 2100（**已越线 +74**，裁定④ 允许） | 硬上限 3500 → 1326 |
| tools | 893 | 0 | 893 | —— | —— |
| 数据 / 文档 | —— | +11（24 号 §2.2/§3）+ 本节 | —— | —— | —— |

**稳定性桶**（裁定①：**不计入台阶 4**）：`0b3d078` tests +40/−11、`7b9ee99` tests +16/−2、
`1890b09` tests +4/−1 ⇒ **+60 / −14，只改测试**。
`tools/ci_local.py` / `tests/unit/test_ci_local*.py` / `tools/phase_evidence.py` /
`.github/workflows/*` **一个字都没动**（差集 0 行，复核命令见 §18.10）。

### 18.9 未核实 / 待评审

1. **`-n auto` 起不来是环境条件，不是代码问题**（§18.0）：本轮**单进程**跑的全量套件；
   门禁那一步的形态与实际读数见 §18.7。**要不要再申请一次 `danger-full-access` 让门禁回到
   §17.6 的 xdist 形态，请评审/使用者定夺**——本轮按"没有证据不申请"的纪律**没有**发起升级请求。
2. **裁定① 的名单与实测不一致**（§18.2）：名单里 3 条只有 1 条真红，另两条红的是
   `test_wiring_check_exits_zero_only_for_a_wired_channel` 与 `test_wiring_json_contract`。
   我按**实测**修（5 条 + 2 处预防性钉死），没有按名字修。
3. **`test_exemption_expiry.py` 的 docstring 比它的断言活得久**（§18.2 的清单）：**未修**，
   理由与两个备选写在表里——补 `expired == 0` 会制造一条**新的**到期炸弹，所以**请评审裁定**。
4. **文本形态只报计数**：`headline.text` 里只有"声明未发现 1"，非通道清单只在 `--json` 的
   `excluded_non_channel` 里。裁定③ 点名的是那个载荷键（"例如 …excluded_non_channel，带 id 和
   kind"），所以**人类输出没有加行**（"只加行"是允许的，但那是本轮预注册之外的改动）。
   **要不要在文本输出里也加一行，请评审裁定。**
5. **`declared_not_discovered` 的边界**：判据是"声明的 `kind` 出现在 `channel_kinds` 的值集里"。
   若某份声明文件**整个不写** `channel_kinds`，那么它的每一条"声明未发现"都会落进
   `excluded_non_channel`、`count` 读作 0。这是判定的直接推论（不是漏洞：那些条目一条都没消失），
   但**`channel_kinds` 缺失时这一格会读作 0** 这件事值得评审知道。
6. **R-h 方案 A 挪到第二十四轮**（25 号 §7）：本轮**不做**；25 号正文一字未改。
7. **`git push` / `git fetch` 没有做**（会话禁令）：「远端此刻的状态」**未核实**；
   `origin/refactor/control-plane` 停在 `088349a`，本地领先 9 个提交。
8. **`.tmp/tmp` 的 ACL 残留成因没修**：本轮仍是"改名让路"；下一次全量 pytest 会不会再留一个
   **未核实**（§17.8 第 3 条同款）。

### 18.10 复现命令（只读或只写 `.tmp`）

```powershell
# 环境自检的正题：清点里没有 dsh:verify-*；版本号与那一格
.venv\Scripts\python.exe .tmp\step28\read_real.py

# 真实 now 与钉死 now 各报一次（7 天窗口 + 逐条越窗时刻）
.venv\Scripts\python.exe .tmp\step28\real_vs_pinned.py

# 墙钟两点：修复前的 3 条红（在 3be25c9 上同样红）
.venv\Scripts\python.exe -m pytest tests/contract/test_wiring_inventory.py -q -k "exits_zero_only or json_contract or verdict_agrees"
# 仪器自证：无插件必须红、带插件必须绿
$env:PYTHONPATH = "$pwd\.tmp\step28;$pwd\src"
.venv\Scripts\python.exe -m pytest .tmp/step28/test_control_clock_is_shifted.py -q
.venv\Scripts\python.exe -m pytest .tmp/step28/test_control_clock_is_shifted.py -q -p clock_shift_all
# 全量：真实时钟 / 时钟 +18 天（本轮读数：两边都 2069 passed / 1 skipped）
.venv\Scripts\python.exe -m pytest tests/unit tests/contract tests/integration tests/security -q
$env:STEP28_SHIFT_DAYS = "18"
.venv\Scripts\python.exe -m pytest tests/unit tests/contract tests/integration tests/security -q -p clock_shift_all

# R-d（before = e1 @ 7b9ee99 / after = f1）：三把尺子 + 硬约束，退出码 0 = 没有未预注册
.venv\Scripts\python.exe .tmp\step3b\probe_decisions.py --out .tmp\step28\decisions-f1.json
.venv\Scripts\python.exe .tmp\step9\probe_verdict_lines.py --out .tmp\step28\verdictlines-f1.json
.venv\Scripts\python.exe .tmp\step28\run_entries.py --side f1
.venv\Scripts\python.exe .tmp\step28\scan_rd.py --left e1 --right f1

# 文件归属（CI 线一个字没动，差集应为空）
git diff --numstat 3be25c9..HEAD -- tools/ci_local.py tests/unit/test_ci_local.py tests/unit/test_ci_local_report_only.py tools/phase_evidence.py .github/workflows
```

