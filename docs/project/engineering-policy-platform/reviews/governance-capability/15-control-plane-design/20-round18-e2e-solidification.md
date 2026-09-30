# 20 · 第 18 轮：端到端读数更正、`--isolated-home` 与豁免读数的机器行

- **执行**：2026-09-30 18:00–18:35（本机）；控制面重构会话（**唯一写者**）。
- **树**：分支 `refactor/control-plane`；**before** = `8ecb0a3`（第 17 轮末），三个提交依次落地：
  `4f461b1`（端到端读数更正，只动文档）→ `09322b0`（`--isolated-home` + ACL 配置失败分类器）→
  `35a4ddd`（豁免到期检查的机器行）；本文件是第四个提交。
- **依据**：本轮指令的四步；AGENTS 第 45（仪器要能失败）/48（证据属于哪棵树）/50（口径诚实）/
  52（失败关闭不等于理由正确）/53（合取落在同一条记录内）/55（加键就是改协议）/56（义务账）条；
  19 号 §3.1（端到端更正）与 §6 第 2 条（登记项）。
- **本文件是什么**：本轮的读数、改动、**没做 / 未核实 / 请评审裁定**，以及**交给 CI 会话的清单**。

---

## 0 一句话

第 1 步把「端到端 = skipped（本机）」更正成「**真机 pass / 受限沙箱里 skipped**」（§1）；
第 2 步加 `--isolated-home` 与「ACL 临时根落在工作区内」这条**有名字的配置失败**（§2）；
第 3 步让豁免到期检查的默认输出带上 `HITS:` 机器行，**`ci_local.py` 一个字节都没动**（§3）；
第 4 步门禁 `--full` **退出码 0 / 合计 13m 29.4s / 33 步全绿**（§4）；R-d 差集 **0 条**（§3.3）。

---

## 1 第 1 步：端到端读数更正（`4f461b1`，只动文档）

19 号 §3 第 2 行原写「JS 侧真实 dsh 端到端 = skipped（本机）」，并据此把"本机拿不到"当成
`reading_context` 的前置条件。**这条只对受限沙箱成立**：使用者真机上跑通过一次 `result=pass`。
原位更正 + 新增 §3.1（原件 sha256 `df2646db…ed30`、block/allow 两个场景的逐项读数、成立条件、
四条本机旁证、**12:15 那次 skipped 的出处与性质**、同一路径上 16:43:06Z 的第二次跳过、两条未核实）；
17 号 §8 第 2 行与归档 README 的摘要同步更正。读数细节不在这里重复，见 19 号 §3.1。

**改了哪三个文件**：`19-round17-registrations.md`、`17-step4-5-scope-assessment.md`、本目录 `README.md`。

---

## 2 第 2 步：`--isolated-home` 与「ACL 临时根落在工作区内」（`09322b0`）

### 2.1 开关：只改 dsh 子进程的 env

- `--isolated-home` 把 **dsh 子进程**的 `DSH_HOME` 指到 `.tmp/phase-2-sandbox/dsh-home`、
  `TEMP`/`TMP` 指到 `.tmp/phase-2-sandbox/dsh-tmp`；**本进程与仓库其它部分不受影响**，
  不给这个开关时行为一字不变（两条用例钉住：一条逐条比对父进程的三条变量，一条断言两个场景的
  子进程都拿到开关）。
- 两个隔离根与受控项目 `demo-shop` **平级**（不是它的子目录）：dsh 的 Windows ACL 沙箱要求
  「ACL 临时根在工作区之外」。有一条用例专门钉这个位置关系——把它挪进项目里就是造一条必红的形态。

### 2.2 分类器：有名字的**配置失败**（真失败，不许洗成环境跳过）

- **原文（外部契约）**：`Windows ACL temp root must be outside the workspace: workspace=<…>; temp=<…>`，
  出自本机安装的 dsh 包 `@deepseek-ai/dsh-sandbox-windows-acl` 的 `assertTempRootOutsideWorkspace()`
  （判据 `containsDirectory(workspaceRoot, tempRoot)`；该文件在本机 dsh 安装里的位置是
  `…/dsh-sandbox-windows-acl/lib/types-CutH1Lgc.js:513`）。**本机没有复现过这条消息**（见 §6 第 3 条）。
- **为什么是配置失败**：临时根是使用者与本脚本自己交给 dsh 的（`TEMP`/`TMP`，或 `--isolated-home`
  指到的目录），改一个变量就能过；而且门禁给每一步的临时根恰好是**仓库内**的 `.tmp/tmp`
  （`tools/ci_local.py` 的 `temp_root()`）——只要 dsh 把工作区算成仓库根，这条就会命中。
  把它读成"这台机器跑不了 dsh"，与把 projectDir 配错读成沙箱限制，是同一个错误。
- **判定与载荷**：`result=fail`、`environment_skipped=false`、退出码 1；
  `dsh_config_failure_kind=acl_temp_root_inside_workspace` + `dsh_config_failure_evidence`（证据行原文，
  `workspace=` / `temp=` 两个路径从它可读）；`reason` 写明**改成什么形态就能过**，并显式否掉
  「环境限制 / 策略判定」。
- **优先级**：与"环境跳过"的证据同时出现时，**配置失败胜出**（一条用例专门钉：同一份日志里既有
  原句、又有 temp scratch 被拒的崩溃块 → 必须报 fail，不许报 skipped）。
- 两个诊断根只在**同一行**里解析，且必须先是合法路径，取不到就留空（AGENTS 第 53 条）。

### 2.3 载荷与版本轴（**请评审裁定**）

`.tmp/artifacts/phase-2-sandbox-result.json` **没有版本轴**。本次为它新增 2 个键
（`dsh_config_failure_kind` / `dsh_config_failure_evidence`，名字全新、纯增不改）。
按 AGENTS 第 55 条的字面要求，载荷的键集合变了就该有一条自己的轴 —— 是否给它建
（例如 `SANDBOX_RESULT_SCHEMA_VERSION`）请评审裁定；**本轮不动它**，只登记。

### 2.4 验证（只用伪造日志与替身，没有起过 dsh）

- `tests/integration/test_dsh_sandbox_loop.py` **77 passed**（新增 10 条：伪造日志 9 条 + 子进程 env 接线 1 组）；
  它与该文件既有的 67 条同批跑。
- 反例形态也有名字：只有原句、两个诊断字段读不出来 → 仍然是配置失败（细节留空）；
  没有原句时行为与修前一致（既有 67 条一条没翻）。
- 与 `tests/contract/test_policy_hook_chain.py`、`tests/unit/test_hook_skip_visibility.py` 合跑 **118 passed**。

---

## 3 第 3 步：豁免到期检查的机器行（`35a4ddd`）

### 3.1 口径（改的是**默认输出**，不改载荷）

- 默认输出新增一行稳定的机器行：
  `HITS: <已过期条数> / declared=<n> due=<n> expired=<n> unprovable=<n>`；
  **hits 只数已过期**；`due`（提醒）与 `unprovable`（读不到）**另列、都不计入命中**。
  原来的 `counts:` 行原样保留（第 16/17/18 号引用的 `declared=… due=… expired=… unprovable=…`
  子串不许消失）。
- **没有动 `ci_local.py`**：它的 `report_only_hits()` 在"步骤没有 `--json`"时读文本 `HITS:` 行。
  这条行因此是**跨文件契约**，由跨侧用例守住（真的 `ci_local.REPORT_ONLY_STEPS` + 真的
  `report_only_hits()` + 真的默认输出）。

### 3.2 `--json` 载荷一个键都没加（第 55 条）

这个载荷没有版本轴，所以本轮**不加键**：机器读数走文本行。键集合由用例钉住——谁要加键，
就得同时决定版本轴怎么走（不是让同一个载荷在同一形状下多出几种键集合）。

### 3.3 读数

| 产物 | 读数 |
| --- | --- |
| 真实读数（ci_local 自己的 `run_report_only_steps`，不跑门禁） | **`HITS: 0 / declared=8 due=0 expired=0 unprovable=0`**（修前是「读不出命中数」） |
| R-d 差集 | `count = 0`（`.tmp/step6/decisions-after.json` sha256 `cfad8c32c59a57a49290759d54db020c57f9cb6a07f0fbdf7d759d9f13ad4588`、23992 B，与 19 号 §2 的 `.tmp/step5/decisions-after.json` **逐字节相同**） |
| 10 个场景 | 四种 decision + pending 一族 + 审批门禁 + 失败关闭对照：`decision` / `violations` / `pending_findings` / `matched_rules` / `skipped_rules` / `required_action` / 载荷键集合 / 模型字段集合逐个相同 |
| 回归 | `tests/unit/test_exemption_expiry.py` **9 passed**（新增 3 条） |

---

## 4 第 4 步：门禁读数（`--full`）

**命令**（树 = `35a4ddd`，工作树干净）：

```powershell
python tools/ci_local.py --full --python .venv/Scripts/python.exe
```

| 项 | 读数 |
| --- | --- |
| **显式退出码** | **0** —— `本机检查全部通过（33 步）；只报告 2 步（非零退出不计入失败）` |
| **耗时** | 脚本自己的汇总行 **13m 29.4s**（`=== 执行耗时（合计 13m 29.4s，35 步）===`）；外层秒表 **810.2s（13m 30.2s）** |
| 大头 | pytest **8m 15.2s**（61.2%；`2004 passed, 1 skipped in 493.32s`）→ notebooks 2m 08.0s → 编排闭环 1m 29.9s |
| 选组 | `改动文件 801 个；执行 33 步（本机跳过 11 步，登记豁免 2 步，只报告 2 步）` |
| 只报告步骤 1 | 义务门禁：0 命中（退出码 0），读数 `hits=0 / 1 个账本（不适用 1：没有账本可读，不算一次真实读数）` |
| 只报告步骤 2 | 豁免到期：0 命中（退出码 0），读数 **`HITS: 0 / declared=8 due=0 expired=0 unprovable=0`** —— 19 号 §6 第 2 条那条登记项**已闭合** |
| 与 17 轮的 8m09.4s 对照 | **不是同一台宿主负载下的同一个数**：本轮 pytest 一步 8m15.2s（占 61.2%）就是差额主体；两个数都记下来，**不互相减** |
| 日志 | `.tmp/step6/ci-local-full.log`（170352 B，sha256 `bb270eb89e13c01ce58660d333566fc8bfd4ca2b0672569ea72f5f5e217e1e64`） |

**门禁里那一步 dsh 闭环必须写清**：第 10 个执行步骤就是 `python tools/dsh_sandbox_loop.py`
（1.0s，rc=0）。它在本会话里**不可能真跑**——跑门禁之前先做过探针：往 `C:\Users\ZNM\.dsh\` 写一个
探针文件 → **被拒**（`UnauthorizedAccessException`）、未留文件；所以嵌套 dsh 在写
`profiles/headless/cordis.yml` 时就会 EPERM。这一步的产物因此是**环境跳过**：`result=skipped`、
`environment_skipped=true`、`dsh_startup_denied_kind=profile_write_denied`、被拒路径
`C:\Users\ZNM\.dsh\profiles\headless\cordis.yml`、`syscall=open`（`timestamp=2026-09-30T10:20:29.831054Z`）。
它与 12:15 / 16:43 两次**同形**，**不是端到端读数，也没有真跑过闭环**。

**跑之前先取证**（`.tmp/e2e/before-gate/20260930T181123/`：产物副本 + 27 个文件的清单
「路径 / 字节 / mtime / sha256」）。门禁之后逐文件比对：受控目录里**只有 `logs/allow-run.txt` 与
`logs/block-run.txt` 两个文件变了**（demo-shop 的源码与配置被逐字节相同地重写），
`dsh-home`（09:07:34）、`dsh-tmp`（09:07:51）、`demo-shop/.policy/audit.enforcement-ledger.jsonl`
（sha256 `307a40ab756aa885e2382b8eeeb0bdd3617bfe9246f6db1351ace8697d63ba10`，09:07:50）**一个字都没动**。
产物路径上的读数从 `04f2c7ed4f661c3380cf379f739d58d87f9989c74e138705e8970f1f890f7b9a`（16:43:06Z 那次跳过）
变成 `2f09d87df4bf2575003f6897a032292a8f9fe1ba6a8bafd2da26545e25399853`（本轮的跳过）——
**使用者指定的 pass 原件仍在** `.tmp/e2e/phase-2-sandbox-result.pass-20260930T010751Z.json`
（sha256 `df2646db896cf726d03cbdff0372783d96f2cffb01b3873034a583167859ed30`）。

---

## 5 交给 CI 会话的清单（这些文件本轮**一个字都没动**）

| # | 文件 | 要改什么 | 为什么 |
| --- | --- | --- | --- |
| 1 | `tools/README.md` | `dsh_sandbox_loop.py` 那一行 | 表里还写着"两类**环境跳过**"，现在多了 `--isolated-home` 开关与**第三类判定**（有名字的配置失败 `acl_temp_root_inside_workspace`，真失败、不跳过） |
| 2 | `tools/README.md` | `exemption_expiry.py` 那一行 | 默认输出的 `HITS:` 机器行与口径（hits = 已过期；`due` / `unprovable` 另列）没写进去 |
| 3 | `tools/ci_local.py` | `ReportOnlyStep.reads`（Exemption expiry 那条） | 写的是"`--json` 的 due / expired 两份清单"，但这一步的 args 里没有 `--json`，读数走的是文本 `HITS:` 行 |
| 4 | `tools/ci_local.py` | `run_report_only_steps()` 的 verdict 文案 | 它对**所有**只报告步骤都打 `0 命中（退出码 0）`；豁免到期检查的退出码**恒为 0**，所以 `HITS` 大于 0 时这句会自相矛盾（读数本身是对的，尾注是错的） |
| 5 | `AGENTS.md` / `.github/workflows/*` / `requirements*` / `pyproject.toml` / `validation/validators.yaml` / `tests/unit/test_ci_local*.py` / `tests/integration/test_validator_pipeline.py` | —— | 本轮**没有需要改的地方**（列出来是为了说明"一个字都没动"，不是待办） |

> 上面 1–4 都不阻断门禁，不改也不影响本轮的读数。

---

## 6 没做 / 未核实 / 请评审裁定

1. **未做（登记为候选）**：把 `--isolated-home` 这件事写进产物载荷（"这份读数属于哪个环境"）——
   它属于台阶 4 `reading_context` 的机制，本轮只登记不动手。
2. **请裁定**：`.tmp/artifacts/phase-2-sandbox-result.json` 要不要一条版本轴（§2.3）；同类问题在
   `tools/exemption_expiry.py` 的 `--json` 载荷上（§3.2，本轮用"不加键"回避）。
3. **未核实**：ACL 那条配置失败**本机没有复现过**——原句是从本机安装的 dsh 包里读出来的，
   分类器只有伪造日志用例，**没有一条来自真机**。
4. **未核实**：`.tmp/artifacts/phase-2-sandbox-result.json` 在 16:43:06Z 那次跳过的归属（19 号 §3.1 已登记）。
5. **未核实**：13m29.4s 与 8m09.4s 的差是不是**全部**来自宿主负载与沙箱开销（只按步骤耗时对照，
   没有做重复测量：pytest 一步就从 5m05.3s 涨到 8m15.2s）。
6. **未做**：没有 `git push` / `--no-verify` / 强推 / `git add -f` / `tools/cleanup.py`；
   改动只用 `write` / `edit` 落树，三个提交都**按路径暂存**；没有跑过 `--hook`。
7. **未核实**：本文件（第四个提交）**没有**再跑一次全量门禁；它只改文档，提交后补跑了
   `check_repo_consistency.py` 与 `check_text_conventions.py`（退出码 0）。
8. **本轮没有合并 `feat`**：按指令"CI 线合入 feat 之后，重构线再 merge feat"，本轮停在评审点。

---

## 7 复现命令（按顺序；只读或只写 `.tmp`）

```powershell
# 1 端到端原件（只读；应为 df2646db…ed30）
(Get-FileHash .tmp/e2e/phase-2-sandbox-result.pass-20260930T010751Z.json -Algorithm SHA256).Hash

# 2 第 2 步的两条读数（伪造日志 + 替身，不依赖 dsh）
.venv\Scripts\python.exe -m pytest tests/integration/test_dsh_sandbox_loop.py -q

# 3 第 3 步：真的 ci_local 读数路径（不跑门禁）
.venv\Scripts\python.exe .tmp\step6\probe_report_only.py

# 3b 第 3 步的 R-d 差集（应为 count=0）
$env:PYTHONPATH='src'
.venv\Scripts\python.exe .tmp\step3b\probe_decisions.py --out .tmp\step6\decisions-after.json
.venv\Scripts\python.exe .tmp\step3b\json_field_diff.py --before .tmp\step4\decisions-before.json --after .tmp\step6\decisions-after.json

# 4 门禁（本轮读数：退出码 0 / 13m 29.4s）
python tools/ci_local.py --full --python .venv/Scripts/python.exe
```

---

## 8 本轮改动的文件（按提交）

| 提交 | 文件 | 处置 |
| --- | --- | --- |
| `4f461b1` | `…/15-control-plane-design/19-round17-registrations.md` | §3 第 2 行原位更正 + 新增 §3.1（原件 sha256 / 四条旁证 / 12:15 出处 / 16:43 登记 / 未核实）+ §7 注释 |
| | `…/15-control-plane-design/17-step4-5-scope-assessment.md` | §8 第 2 行的回指同步更正 |
| | `…/15-control-plane-design/README.md` | 索引里 19 号的摘要同步更正 |
| `09322b0` | `tools/dsh_sandbox_loop.py` | `--isolated-home`（只改子进程 env）+ `acl_temp_root_failure()` 一族（分类器 / 理由 / 载荷 2 个键） |
| | `tests/integration/test_dsh_sandbox_loop.py` | 新增 10 条（伪造日志与子进程 env 接线，全部不依赖 dsh） |
| `35a4ddd` | `tools/exemption_expiry.py` | 默认输出新增 `HITS:` 机器行（`--json` 载荷未动） |
| | `tests/unit/test_exemption_expiry.py` | 新增 3 条（含跨侧契约与键集合钉子） |
| 第 4 个提交 | `…/15-control-plane-design/20-round18-e2e-solidification.md` | 本文件 |
| | `…/15-control-plane-design/README.md` | 索引新增本文件 |
