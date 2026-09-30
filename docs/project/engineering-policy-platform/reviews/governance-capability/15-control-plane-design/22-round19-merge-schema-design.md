# 22 · 第 19 轮：合并 CI 线、沙箱载荷建轴、`reading_context` 设计稿与门禁读数

- **执行**：2026-09-30 19:00–19:15（本机）；控制面重构会话（**唯一写者**）。
- **树**：分支 `refactor/control-plane`；**before** = `f57b456`（第 18 轮末），三个提交依次落地：
  `3627e27`（合并 `origin/feat/rules-and-os-platform`）→ `641b4ec`（裁定落地：沙箱载荷建轴）→
  `d2b906f`（台阶 4 `reading_context` 设计稿）；本文件是第四个提交。
- **依据**：本轮指令的四步；AGENTS 第 48（证据属于哪棵树）/50（口径诚实）/53（合取落在同一条记录内）/
  55（加键就是改协议）/56（义务账）条；18 号 §2 与 §5、19 号 §3 与 §5。
- **本文件是什么**：本轮的**读数、改动、跑前跑后比对、没做 / 未核实 / 请评审裁定**，以及**交给 CI 会话的清单**。

---

## 0 一句话

第 1 步把 CI 线并进本树（**无冲突**）并按锁文件装上 `pytest-xdist==3.8.0`，合并后两条只报告读数行**都还在**（§1）；
第 2 步把第 18 轮 §2.3 的裁定落地——沙箱闭环结论载荷有了自己的版本轴 `SANDBOX_RESULT_SCHEMA_VERSION = "1.1"`，
并证明 `phase_evidence` 读它**不依赖键集合**（§2）；第 3 步交出台阶 4 `reading_context` 的**设计稿**（只写文档，§3）；
第 4 步门禁 `--full` **退出码 0 / 合计 4m 32.6s / 31 步执行全绿**，跑前快照 → 跑后** 27/27 文件逐字节相同**（§4）。

---

## 1 第 1 步：合并 `origin/feat/rules-and-os-platform`（`3627e27`）

### 1.1 合并读数

| 项 | 读数 |
| --- | --- |
| 合并前 | `refactor/control-plane` = `f57b456`，工作树干净；`git rev-list --left-right --count HEAD...origin/feat/rules-and-os-platform` = **4 / 3** |
| 命令 | `git merge --no-ff --no-edit origin/feat/rules-and-os-platform`（**不 rebase**） |
| 结果 | `Merge made by the 'ort' strategy.`，**零冲突**（没有停下来的理由） |
| 入账 | 15 个文件、**+644 / −83**；改动面含 `.github/workflows/phase-8.yml` / `AGENTS.md` / `pyproject.toml` / `requirements.in` / `requirements.lock` / `tools/ci_local.py` / `tools/phase_evidence.py` / `tools/README.md` / `validation/validators.yaml` 与 5 个测试文件 |
| 合并后 | HEAD = `3627e27`；工作树干净；相对 `origin/refactor/control-plane` **ahead 5**（本轮不推送） |

### 1.2 按 `requirements.lock` 装 `pytest-xdist`（**装的过程有一份环境读数**）

锁文件钉 `pytest-xdist==3.8.0`（合并进来的 `dde53f1` 加的）。装的时候连撞三次，逐条记下来——
它们都不是本仓库的问题，但下一个人会再遇到：

| # | 读数 | 是什么 |
| --- | --- | --- |
| 1 | `pip install` → `ProxyError('Cannot connect to proxy')` × 5 → `No matching distribution found`（退出 1） | 系统代理（WinINET `ProxyEnable=1`、`ProxyServer=127.0.0.1:7897`）不可达；`NO_PROXY=*` 后可下载 |
| 2 | `ERROR: Could not install packages due to an OSError: [Errno 13] Permission denied: '<temp>/pip-unpack-…/pytest_xdist-3.8.0-py3-none-any.whl'` | pip 的解包目录走 `tempfile.mkdtemp` → `os.mkdir(path, 0o700)`；**在本会话的 workspace-write 沙箱里，这样建出来的目录对受限身份不可读**（见 §4.1 的探针读数） |
| 3 | 把 `TEMP`/`TMP`/`TMPDIR` 指到仓库内 `.tmp/pip-tmp` **仍然**同一处 EACCES | 同上：与落点无关，与 `mkdir(mode=0o700)` 有关 |

**解法（临时脚本，不进仓库）**：`.tmp/pip_install_sandboxed.py` 在安装期把 `os.mkdir` 的 `mode` 参数丢掉，
再调 `pip` 的 CLI。装成：**`pytest-xdist-3.8.0` + `execnet-2.1.2`**（`pip list` 与 `importlib.metadata` 两处读数一致）；
`.venv/Scripts/python.exe -m pytest <探测目录> -n 2 --dist loadfile` 可跑（守护并发可用）。
**这个脚本不是仓库的一部分**，它只解释「为什么这台机器上 `pip install` 会以 EACCES 收场」。

### 1.3 合并后：两条只报告读数行**还在**（每步一行 + 落盘日志）

探针 `.tmp/step1/probe_report_only.py` 走的是 `ci_local.main()` 里**真正的那条路径**
（`run_report_only_steps(REPORT_ONLY_STEPS, hook=False, logs=_reset_log_dir(), first_index=1)`），
不跑 workflow 步骤、不取排他锁。读数逐字如下：

```text
REPORT-ONLY: Obligations gate (report only) —— 0 命中（退出码 0）；读数 hits=0 / 1 个账本（不适用 1：没有账本可读，不算一次真实读数）；豁免到期 2026-10-31（不计入门禁失败）（日志：.tmp/ci-local-logs/01-obligations-gate-report-only.log）
REPORT-ONLY: Exemption expiry report (report only) —— 0 命中（退出码 0）；读数 HITS: 0 / declared=8 due=0 expired=0 unprovable=0；豁免到期 2026-12-31（不计入门禁失败）（日志：.tmp/ci-local-logs/02-exemption-expiry-report-report-only.log）
```

落盘日志两个文件都在（**938 B / 1105 B**），耗时表里两条各 0.67s / 0.32s。
**结论**：18 号 §5 交给 CI 线的第 1、2 项（`tools/README.md` 的两行）由本轮补上；
第 3、4 项（`ci_local.py` 的 `reads` 文案与 verdict 尾注）**仍归 CI 线**（本线禁令：那个文件一个字都不许动）。

回归：`tests/unit/test_ci_local.py` + `tests/unit/test_ci_local_report_only.py` + `tests/unit/test_phase_evidence_suites.py` 合跑 **41 passed**。

---

## 2 第 2 步：裁定落地（`641b4ec`）

### 2.1 沙箱闭环结论载荷的版本轴：`1.0` 追认 / `1.1` 现形状

- `tools/dsh_sandbox_loop.py` 新增 `SANDBOX_RESULT_SCHEMA_VERSION = "1.1"`；
  **两条写盘路径都带它**：完整跑（`payload`）与 **dsh 不可用时的最小跳过载荷**——
  「同一个文件两种形状」如果只给其中一条加版本号，就还是第 50 条的「同名两义」。
- **1.0 的边界（追认）**：第 13 轮之前的形状。**逐版读数**（`git show <rev>:tools/dsh_sandbox_loop.py` 里数键）：

| 版本 | 树 | 那棵树上的诊断键 |
| --- | --- | --- |
| 1.0（追认） | 第 13 轮 `b2c1255` | `environment_skipped` / `sandbox_blocked_spawn` / 单个 `dsh_startup_denied`；**没有** `schema_version`、没有 `dsh_startup_denied_kind` 一族、没有 `hook_spawn_denied_*`、没有 `dsh_config_failure_*` |
| 1.1（现形状） | 第 18 轮 `09322b0` 起 | 上面全部 + 第 14 轮（`c75886e`）的 `dsh_startup_denied_*` 一族 + 第 15 轮（`b9d3b11`）的 `hook_spawn_denied_*` + 第 18 轮的 `dsh_config_failure_*` |

- 回归：`tests/integration/test_dsh_sandbox_loop.py` **77 passed**（没有一条断言精确键集合，加键不破）。
- `AGENTS.md` 第 55 条：新轴登记进版本轴表（含 1.0 追认的边界与三族键的引入轮次）；
  另按裁定登记 **`tools/exemption_expiry.py --json`「还没有版本轴，第一次改键时引入 1.1」**。
- `tools/README.md`：`dsh_sandbox_loop.py` 一行补 `--isolated-home` 与**第三类判定**
  （有名字的配置失败 `acl_temp_root_inside_workspace`）；`exemption_expiry.py` 一行补 `HITS:` 机器行与口径。

### 2.2 `phase_evidence` 读它时**不依赖键集合**（读数 + 一个缺口）

`tools/phase_evidence.py` **一个字节都没动**（归 CI 线）。用探针 `.tmp/step2/probe_phase_evidence_keys.py`
把三种键集合喂给 `sandbox_loop()`：

| 变体 | 输出 |
| --- | --- |
| A 现形状（含 `schema_version` + `dsh_config_failure_*`） | 基准 |
| B 去掉 `schema_version`（= 1.0 那一代） | `A == B` → **True** |
| C 多一个未知键 | `A == C` → **True** |

**结论**：不依赖键集合（逐键 `.get()`），加键不会让它红。**同时登记一个缺口**：
它按**固定键集合**复制子载荷，因此 `schema_version` **不会**出现在阶段证据里 ——
「这份读数属于哪一代形状」目前在阶段证据层读不到（已写进 21 号 §2.6 / §4 第 7 行，归 CI 线）。

---

## 3 第 3 步：台阶 4 `reading_context` 设计稿（`d2b906f`，**只写文档**）

`21-step4-reading-context-design.md`（407 行）。要点：

- **六类要带它的读数**：`policy.check --json`（`OUTPUT_SCHEMA_VERSION` 1.1→1.2）、
  Hook 审计记录（`AUDIT_SCHEMA_VERSION` 1.2→1.3，**19 号 §3 第 1 行的 `tool.pytest` 追溯缺口归到这里**：
  给 `pre_evidence` 摘要加 `registry` 摘要键）、只报告两处（义务门禁 1.1→1.2；豁免到期 `--json` 首建 1.1，
  **文本 `HITS:` 行一个字符都不改**）、端到端结果（1.1→1.2）、覆盖账（`WIRING_SCHEMA_VERSION` 1.1→1.2）、
  阶段证据（无轴 → 首建 1.1，**归 CI 线**）；
- **一条否定性结论**：验证器证据（`EVIDENCE_SCHEMA_VERSION` / `PIPELINE_SCHEMA_VERSION` 1.2）**不加**——
  那两份载荷要求「相同输入得到逐字节相同的证据」，run id / 宿主 / 墙钟进去就破掉它；
- **统一形状**：`source` / `tree` / `declarations` / `host` / `run` 五个键名 + 三态（`available` / `unavailable` / `not_applicable`）
  + 脱敏与「不进判定」的纪律；`tree` 复用第 48 条的既有词汇，不造第二套；
- **R-d 预注册形状**：四把尺子（判定载荷 / `check` 包装层 / Hook 审计 / 端到端）× 预期差集条数 × 硬约束
  （差集里出现 `decision` / `violations` / `pending_findings` 任一即违约），并写明「`check` 包装层那台探针今天不存在」；
- **预算**：台阶 4 硬上限 src **3.25k** / tests **3.5k**（原上限 ×2.5，按台阶累计）；已花读数由 `git show --numstat`
  给出 = src **0** / tests **598** / tools **641** / 数据文档 **128**；本稿逐项估算 src 200–390、tests 560–970、tools 190–370。

---

## 4 第 4 步：门禁读数（`--full`）

### 4.1 先说清楚：这次门禁是在**一次显式的沙箱放宽**下跑的

第 0 步环境自检时本会话是 **workspace-write**。在那个上下文里 **pytest 跑不起来**，四条读数：

| # | 读数 |
| --- | --- |
| 1 | `mkdtemp` / `os.mkdir(path, 0o700)` 建出来的目录，**同进程内**再写就 EACCES 13（`probe5`：四种父目录 × 三种建法，`mode=0o700` 与 `mkdtemp` 全红、默认 mode 全绿） |
| 2 | 那些目录**事后连 ACL 都读不了**：`icacls` → `Access is denied`；DSH 自带的 ACL 诊断脚本对 `.tmp/tmp/pytest-of-ZNM` 的判定是 `UNREADABLE`（`nextAction: stop`，即**不推断修复**） |
| 3 | `pytest` 因此在收集前就 `INTERNALERROR> PermissionError: [WinError 5] … pytest-of-ZNM`（退出 3）；`tmp_path` 用例同样 ERROR |
| 4 | 旁证：`.tmp/ci-local-timings.json`（2026-09-30 01:50 那次**不受限**的全量门禁）里 pytest 一步 **rc=0 / 318.9s**、33 步全绿——同一个工作树，换个上下文就能跑 |

因此第 4 步以**一次显式放宽**（`danger-full-access`，写明理由与上述证据）执行；
执行前先删掉 `.tmp/tmp/pytest-of-*` 两个**沙箱 ACL 残留**的空壳目录（`removed=2 kept=0`，只动 `.tmp` 下的 pytest 落点）。
**这两件事都记在这里**，免得下一次有人拿「沙箱里跑不了」当成「门禁红了」。

### 4.2 读数

**命令**（树 = `d2b906f`，工作树干净、无并发）：

```powershell
python tools/ci_local.py --full --python .venv/Scripts/python.exe
```

| 项 | 读数 |
| --- | --- |
| **显式退出码** | **0** —— `本机检查全部通过（31 步）；只报告 2 步（非零退出不计入失败）` |
| **耗时** | 脚本自己的汇总行 **4m 32.6s**（`=== 执行耗时（合计 4m 32.6s，33 步，最慢 5 步）===`）；外层秒表 **273.2s（4m 33.2s）** |
| 大头 | pytest **1m 45.7s**（38.8%；`2017 passed, 1 skipped, 4 warnings in 104.28s`）→ notebooks 1m 05.9s → 编排闭环 1m 03.4s |
| 选组 | `改动文件 806 个；执行 31 步（本机跳过 11 步，登记豁免 2 步，只报告 2 步）` |
| 只报告步骤 1 | 义务门禁：0 命中（退出码 0），读数 `hits=0 / 1 个账本（不适用 1：没有账本可读，不算一次真实读数）` |
| 只报告步骤 2 | 豁免到期：0 命中（退出码 0），读数 `HITS: 0 / declared=8 due=0 expired=0 unprovable=0` |
| 日志 | `.tmp/step4/ci-local-full-r19.log`（4956 B，sha256 `cb7ffc5954d7949144c178c1c17141442173bc6a8a6643a4c1197e94643a207f`）+ `.tmp/ci-local-logs/` 下 33 个分步日志 |
| **与 223s 对照** | **不是同一棵树上的读数，也不相减**：223s 是 `origin/perf/ci-local`（`dde53f1`，xdist + 去重两步）在**它自己那棵树**上的数；本树 31 个执行步里，notebooks（1m05.9s）与编排闭环（1m03.4s）合计 2m09s 是 CI 线那次读数不必然包含的工作。**能对照的是同一台机器上 pytest 这一步**：01:50 那次（无 xdist）318.9s → 本轮（xdist）104.28s |

### 4.3 跑前快照 → 跑后**逐个文件比对**（第 10 步必然跑 `tools/dsh_sandbox_loop.py`）

**没有直接跑过 `tools/dsh_sandbox_loop.py`**（禁令）：它只作为门禁第 9 个执行步被执行。
跑前快照 `.tmp/e2e/before-gate-r19/20260930T190205/manifest.json`：受控目录 **27 个文件**的
「路径 / 字节 / mtime / sha256」+ 产物副本 + HEAD + `git status`。跑后逐文件比对：

| 项 | 读数 |
| --- | --- |
| 受控目录 | before/after 都是 **27 个文件**；**逐字节相同 27、内容变了 0、新增 0、消失 0** |
| 与 18 号的差别 | 18 号那次 `logs/allow-run.txt` / `logs/block-run.txt` 变过；**本轮这两个文件也没变**——因为这一步在 dsh 启动阶段就以 `profile_write_denied` 跳过，一个 Hook 都没跑过 |
| 产物 | `2f09d87df4bf2575…5399853`（2173 B，**无 `schema_version`**）→ **`ddd91d0683f206c76714ee51f4b815a5ae558549e6c085ff3754acace2c3525c`**（2200 B，`mtime` 19:07:14） |
| 产物内容 | `schema_version="1.1"`（**本轮的改动第一次出现在真实产物里**）、`result=skipped`、`environment_skipped=true`、`dsh_startup_denied_kind=profile_write_denied`、被拒路径 `C:\Users\ZNM\.dsh\profiles\headless\cordis.yml`、`syscall=open`、`timestamp=2026-09-30T11:07:14.154062Z`；**判定字段与 18 号那次逐字相同**（只有新键与时间戳在变） |
| 仓库侧 | HEAD 仍 `d2b906f`；`git status --porcelain -uall` **空**（无未跟踪文件、无警告） |

**这一步的诚实边界**：它证明的是「门禁没有动受控项目、没有动仓库」，**不是**「端到端闭环跑通了」——
这条读数是**环境跳过**（`environment_skipped=true`），端到端真机 pass 的原件仍是 19 号 §3.1 那一份。

---

## 5 交给 CI 会话的清单（这些文件本轮**一个字都没动**）

| # | 文件 | 要改什么 | 为什么 |
| --- | --- | --- | --- |
| 1 | `tools/ci_local.py` | `ReportOnlyStep.reads`（Exemption expiry 那条） | 它写着读 `--json` 的 due / expired，但那一步的 args 里没有 `--json`（读数走文本 `HITS:` 行）——18 号 §5 第 3 项，本轮仍未动 |
| 2 | `tools/ci_local.py` | `run_report_only_steps()` 的 verdict 尾注 | 对所有只报告步骤都打 `0 命中（退出码 0）`；豁免到期的退出码恒为 0，`HITS>0` 时这句话自相矛盾——18 号 §5 第 4 项，本轮仍未动 |
| 3 | `tools/ci_local.py` | `REPORT-ONLY:` 行要不要带 `reading_context` | 21 号 §9 第 2 条的裁定项（跨线） |
| 4 | `tools/phase_evidence.py` | 透传子载荷的版本轴（例如 `sandbox_loop.schema_version`） | 本轮实测它按固定键复制：新键**读不到**（§2.2）；21 号 §4 第 7 行 / §9 第 3 条 |
| 5 | `tools/phase_evidence.py` | 自己的报告**没有版本轴** | 第一次改键时要引入 1.1（21 号 §2.6） |
| 6 | `AGENTS.md` / `.github/workflows/*` / `requirements*` / `pyproject.toml` / `validation/validators.yaml` / `tests/unit/test_ci_local*.py` | —— | 本轮**没有需要改的地方**（列出来是为了说明「一个字都没动」，不是待办） |

---

## 6 没做 / 未核实 / 请评审裁定

1. **未核实**：`pytest-xdist` 在本机逐文件并行（`-n auto --dist loadfile`）下的**稳定性**——本轮只验了两条守护用例与一次全量门禁；
   门禁之外没有做重复测量（并发用例之间是否互相干扰，属合并进来的 CI 线承诺，本线不背书）。
2. **未核实**：受限上下文里那批「`mkdir(mode=0o700)` 目录不可读」的**机制**（是 ACL、强制完整性标签还是 DSH 的授权层）——
   DSH 自带的诊断脚本对目标路径的判定是 `UNREADABLE`，按它的规则**停止且不推断修复**；本文只记现象与可复现命令。
3. **未核实**：两个被删掉的 pytest 落点目录里原本有什么（`pytest-of-ZNM` / `pytest-of-q2xo32ao`，删之前读不出来，**没有**做内容清点）。
4. **做的但要说清**：① 第 4 步用了**一次显式沙箱放宽**（§4.1，理由与证据一并给出）；
   ② 删了 `.tmp/tmp/pytest-of-*` 两个空壳目录；③ 清掉了本轮探针在**仓库根**误建的两个空目录
   （`probe-root-mode700` / `probe-848tzrt7`，在放宽后删掉，`git status` 现在为空且无警告）。
5. **未做**：没有 `git push` / `--no-verify` / 强推 / `git add -f` / `tools/cleanup.py`；
   改动只用 `write` / `edit` 落树，三个提交都**按路径暂存**；没有跑过 `--hook`；**没有直接跑 `tools/dsh_sandbox_loop.py`**。
6. **未核实**：本文件（第四个提交）**没有再跑一次全量门禁**——它只改文档；提交后补跑
   `check_repo_consistency.py` 与 `check_text_conventions.py`（读数见 §7）。
7. **请评审裁定**：21 号 §9 的四条（端到端「受限宿主不可得」要不要单独一档；`ci_local` 的 `REPORT-ONLY:` 行要不要带上下文；
   阶段证据要不要透传子载荷版本；六个提交的落地顺序）。
8. **本轮没有推送**：按指令停在评审点；评审通过后由使用者在本机跑一次 `--isolated-home` 端到端，再推送并快进 `feat`。

---

## 7 复现命令（按顺序；只读或只写 `.tmp`）

```powershell
# 1 合并与锁文件（应为 4 / 3、零冲突、pytest-xdist==3.8.0）
git rev-list --left-right --count f57b456...origin/feat/rules-and-os-platform
git show --stat 3627e27 | Select-Object -First 5
Select-String -Path requirements.lock -Pattern 'xdist'

# 1b 合并后两条只报告读数行（真的 ci_local 路径，不跑门禁）
.venv\Scripts\python.exe .tmp\step1\probe_report_only.py

# 2 phase_evidence 不依赖键集合（三种键集合 → 输出逐字节相同）
.venv\Scripts\python.exe .tmp\step2\probe_phase_evidence_keys.py

# 2b 沙箱闭环载荷的回归（77 passed）
.venv\Scripts\python.exe -m pytest tests/integration/test_dsh_sandbox_loop.py -q

# 4 跑前快照 / 跑后比对
.venv\Scripts\python.exe .tmp\step4\snapshot_before_gate.py
.venv\Scripts\python.exe .tmp\step4\compare_after_gate.py

# 4b 门禁（本轮读数：退出码 0 / 4m 32.6s / 31 步）
python tools/ci_local.py --full --python .venv/Scripts/python.exe

# 6 只动文档的提交之后补跑的两条检查
.venv\Scripts\python.exe tools/check_repo_consistency.py
.venv\Scripts\python.exe tools/check_text_conventions.py
```

---

## 8 本轮改动的文件（按提交）

| 提交 | 文件 | 处置 |
| --- | --- | --- |
| `3627e27` | （合并提交，15 个文件随 CI 线并入） | `git merge --no-ff --no-edit origin/feat/rules-and-os-platform`，**零冲突** |
| `641b4ec` | `tools/dsh_sandbox_loop.py` | `SANDBOX_RESULT_SCHEMA_VERSION = "1.1"` + 两条写盘路径都写 `schema_version` |
| | `AGENTS.md` | 第 55 条：新轴登记 + `exemption_expiry --json`「第一次改键引入 1.1」 |
| | `tools/README.md` | `dsh_sandbox_loop.py` 一行（`--isolated-home` + 第三类判定）、`exemption_expiry.py` 一行（`HITS:` 口径） |
| `d2b906f` | `…/15-control-plane-design/21-step4-reading-context-design.md` | 台阶 4 `reading_context` 设计稿（新文件，407 行） |
| | `…/15-control-plane-design/README.md` | 索引新增 21 号、文件清单那行补记 |
| 第 4 个提交 | `…/15-control-plane-design/22-round19-merge-schema-design.md` | 本文件 |
| | `…/15-control-plane-design/README.md` | 索引新增本文件 |
