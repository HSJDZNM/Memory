# 18 · 第 16 轮：2026-09-30 裁定的执行（包装层版本轴、义务门禁接门禁、台阶 4 写声明）

- **执行**：2026-09-30（本机）；控制面重构会话（**唯一写者**）。
- **树**：分支 `refactor/control-plane`；**before** = `b23db01`（第 15 轮末），
  三个提交依次落地：`843f6dd`（修正）→ `6ad7376`（义务门禁 → ci_local 只报告）→
  `60f0db5`（台阶 4 写声明 + 到期检查）；本文件是第四个提交。
- **依据**：2026-09-30 裁定（**总原则** + R16-1…R16-4，已写进方案 §10 的
  「2026-09-30 裁定」小节）；AGENTS 第 55 条（加键就是改协议）、第 56 条（义务账）、
  第 45 条（仪器要能失败）、第 50 条（口径诚实）。
- **本文件是什么**：这一轮的**读数、差集、声明清单、预算对账**，以及
  **没做 / 未核实 / 请评审裁定**。它不替代方案的任何一节。

---

## 0 一句话

本轮**没有改任何判定路径**（决策载荷 10 个场景字段级差集 **0 条**）；
四件事：① 包装置于版本轴（`output_schema_version = "1.1"`，1.0 追认为 3c 之前的形状）；
② 义务门禁从"不在任何门禁里"变成 `ci_local` 的**只报告步骤**（非零退出只打印命中数）；
③ 台阶 4 只做**写声明** 5 条 + **只报告**的到期检查（机制一条都没建）；
④ 记录"合并 feat"这条指令在本树上的真实读数（**Already up to date**，见 §1）。

---

## 1 合并 `origin/feat/rules-and-os-platform`：读数与结论

指令要求"手工解决 AGENTS.md 与 tests/integration/test_validator_pipeline.py 的冲突，单独提交"。
**本树上不存在这次合并**，读数如下（三条互相印证）：

| # | 读数 | 命令 |
| --- | --- | --- |
| 1 | `origin/feat/rules-and-os-platform` = `6fa800e`（2026-09-28 23:16:24 +0800） | `git for-each-ref refs/remotes/origin` |
| 2 | `git merge-base refactor/control-plane origin/feat/rules-and-os-platform` = `6fa800e`，且 `git merge-base --is-ancestor …` **退出 0**——feat 已是 HEAD 的祖先 | 同上 |
| 3 | `git merge --no-edit origin/feat/rules-and-os-platform` → **`Already up to date.`**（退出码 0），`git status --porcelain` 仍为空 | 实测 |

**为什么冲突没有发生**：这次合并**已经在上一轮做过**——提交
`4241217`（2026-09-29 00:30:40，`chore(merge): 合并 feat/rules-and-os-platform（README 表冲突手工解决）`，
父提交 `aa3879e` + `6fa800e`）就在本分支的历史里（`git merge-base --is-ancestor 4241217 HEAD` 退出 0）。
自那以后 feat 没有新提交（fetched ref 未变），所以**没有可解冲突、也没有可提交的合并内容**。
按纪律**不伪造一个空合并提交**：`git merge` 对祖先不会产生提交，这是 git 的语义，不是省略。

**这一条要请评审确认**：如果评审期望的是一次"重放 feat → 本分支"的合并，那么它的正确形态是
**本分支已经包含 feat**（feat 是祖先），而不是再造一个空合并。若评审手上有一棵 feat 已经前进的树，
请给出具体的 `origin/feat` 提交号——本次读数只对本机 fetch 后的 ref 成立（**未核实**：远端此刻的真实状态，
本轮按禁令**没有 fetch / push**）。

---

## 2 `tool.pytest` 的第 55 条核查：**不升**（读数逐条）

**指令口径**：证据里能追溯到 `validation/validators.yaml` 的摘要就**不升**，否则把 `tool.pytest`
的声明版本升到 **1.1**（证据里的标识是 `tool.pytest@1.0`）。

| # | 读什么 | 读数 | 命令 / 出处 |
| --- | --- | --- | --- |
| R1 | `validation/validators.yaml` 的 sha256 | `06bfce18cb02cbfda72f5c2db01bcd9dbabade782cf946721f80d770c809a9f5` | `hashlib.sha256` |
| R2 | `policy.check --json` 的 `evidence.configs.registry` | `sha256:06bfce18…a9f5` —— **与 R1 逐字符相同**（`config_digest()` 的输出） | 实跑 `policy.check src/policy/obligations.py --changed … --operation edit --json` |
| R3 | `tool.pytest` 的记录 | `validator="tool.pytest@1.0"`、`tool.config="validation/pytest.ini"`、`tool.config_sha256="sha256:83d818b4…5c36"`（= pytest.ini 的摘要，**不是**注册表摘要） | 同上 |
| R4 | Hook 路径的 `pre_evidence` 摘要（审计记录） | **没有**注册表摘要：字段是 `registry_resolution / validators_requested / validators[] / …`（`src/adapters/dsh/pre_evidence.py` 的 `_summary`，逐键读过） | 代码级读数 |

**结论：不升。** 依据是 R2——**证据段里能直接读到 `validators.yaml` 的摘要**（`evidence.configs.registry`，
契约测试 `tests/contract/test_validator_protocol.py:319-321` 也钉住了它必须以 `sha256:` 开头），
读者据此能判定这条读数出自哪一版注册表，不需要再靠 `tool.pytest@1.0` 这一个字符串去猜行为。

**同一读数暴露的缺口（登记，不改）**：R4 显示 **Hook 路径的审计摘要没有搬这份摘要**——
同一条 `tool.pytest@1.0` 在账本里对应三种行为（H4 之前 / H4 之后 / 3b 之后）。
升 `tool.pytest` 到 1.1 **修不了**它（改名不等于给出摘要），真正的处置是给 `pre_evidence` 摘要
加注册表摘要键——那是**审计记录的键集合变化**，按第 55 条要递增 `AUDIT_SCHEMA_VERSION`（1.2 → 1.3）。
**请评审裁定**：要不要在下一轮做（本轮按"不新增协议变更"的稳定性口径**停在门口**）。
**升版的反面代价也给出**（供评审对照）：`tool.pytest@1.0` 被 5 处测试断言
（`tests/integration/test_validator_cli.py`、`tests/integration/test_dsh_pre_evidence_hook.py`、
`tests/unit/test_validator_pending_implementation.py`）与 14 处文档读数引用，全部要同批改。

---

## 3 R-d 字段级差集（**先交差集**，仪器未改一个字节）

仪器是台阶 3b 的那一台：`.tmp/step3b/probe_decisions.py`（只调 `policy.engine.evaluate`）与
`.tmp/step3b/json_field_diff.py`；**before 侧在动手之前采集**（`b23db01` 树）。

| 产物 | sha256 | 说明 |
| --- | --- | --- |
| `.tmp/step4/decisions-before.json` | `CFAD8C32C59A57A49290759D54DB020C57F9CB6A07F0FBDF7D759D9F13AD4588` | 动手前（10 个场景，23992 B） |
| `.tmp/step4/decisions-after-final.json` | 见文件（内容与 before 逐字段相同） | 三个提交之后 |
| `.tmp/step4/field-diff-final.json` | —— | **count = 0**（`DIFF_EXIT=0`） |
| `.tmp/step4/wrapper-before.json` | `C3E8BAB519F0320FFAF3A3E98046E264EFE147DBA1E6CA37C0CFE8A629DDCEB5` | 动手前的 CLI 包装读数 |
| `.tmp/step4/wrapper-field-diff-final.json` | —— | **count = 5**，全部由那一个新键解释（`WRAPPER_DIFF_EXIT=1`，非零正是"有差异"） |

**决策载荷（`result`）**：10 个场景（四种 decision + pending 一族 + pending 与真违规混批 +
审批门禁 + 失败关闭对照）的 `decision` / `violations`（含内容）/ `pending_findings` /
`matched_rules` / `skipped_rules` / `required_action` / 载荷键集合 / 模型字段集合**逐个相同**，
差集 **0 条**——**"任何 decision 都不许变"这条裁定是可复核地成立的**。

**CLI 包装**：差集恰好 5 条，全部是同一个事实的不同侧面：
`output_schema_version: null → "1.1"`、`top_keys` 长度 8 → 9、以及三条下标位移
（`reported_imports` / `result` / `rule_set` 各后移一位）。`result` 与 `check_volume` **不在差集里**。

---

## 4 `output_schema_version = "1.1"`（R16-2）：动了哪些引用点

| 落点 | 处置 |
| --- | --- |
| `src/policy/check.py` | 新增 `OUTPUT_SCHEMA_VERSION = "1.1"`（含"1.0 追认"的常量注释）、docstring 的包装层说明、`__all__`、`render_json` 的载荷 |
| `AGENTS.md` 第 55 条 | 版本轴清单的「判定与证据」组新增 `policy.check.OUTPUT_SCHEMA_VERSION`（写明它不是决策载荷） |
| `README.md` | `--json` 一节列出包装的 8 个键，并写明包装与协议各自演进 |
| `docs/project/architecture/使用说明.md` | ⑤ 机器可读输出那段补一行包装版本 |
| `tests/integration/test_cli.py` | 顶层键集合断言 8 → 9，并断言 `== OUTPUT_SCHEMA_VERSION` |
| `tools/build_learning_notebook.py` | phase-0 / phase-1 两处键清单（`expected_top`）+ 两处说明文字 + 一处注释 |
| `docs/project/learning/phase-0/walkthrough.{ipynb,py}` | 重生成产物（`python tools/build_learning_notebook.py`；`--check` 复跑退出 0） |

**未核实**：仓库外是否有消费方按"顶层键集合恰好等于旧集合"读 `--json`（仓库内没有这种断言；
`tests/integration/test_cli.py` 的那一条是仓库内唯一一处，已同批改）。

---

## 5 义务门禁接进 `ci_local`（R16-4 的前半）：只报告 + 到期豁免

**形态**：`tools/ci_local.py` 新增 `REPORT_ONLY_STEPS`（`NamedTuple`，每条必填
`name / args / reason / expires_at / adopted / reads`）与 `run_report_only_steps()`。
两条步骤**不在 workflow 里**（账本与宿主状态都在 `.tmp`，CI 上没有可读对象；也不给 CI 增加阻断步）：

| 步骤 | 命令 | 豁免到期 | 读数 |
| --- | --- | --- | --- |
| `Obligations gate (report only)` | `tools/obligations_gate.py --ledger .tmp/obligations/repo.jsonl --json` | **2026-10-31** | `hits` / `ledger_count`（结构化优先） |
| `Exemption expiry report (report only)` | `tools/exemption_expiry.py` | 2026-12-31 | `due` / `expired` 两份清单 |

**只报告的语义（可复核）**：任何非零退出（含启动失败）**不进 `failures`**，只打印一行
`REPORT-ONLY: <name> —— 退出码 N；读数 …；豁免到期 …（不计入门禁失败）`；
读不出命中数就照实说"读不出命中数"（不静默、也不把读不到变成结论）；
`--hook` 模式下**完全不出声**（钩子"成功时保持安静"的契约优先于读数可见性，
读数留给常规运行与 `--list`）。`--list` 把两条豁免连同理由/到期日/读数口径一并列出。

**本机实测（本轮）**：`obligations_gate --ledger .tmp/obligations/missing.jsonl` →
`HITS: 1 / 1`、退出码 1（账本不存在 = "没有依据"，门禁按命中处理——这是既有口径，不是本轮引入的）；
`exemption_expiry` → `declared=8 due=0 expired=0 unprovable=0`、退出码 0。

**升格判据不变**：仍然是 L5 的「跑过 N≥1 次且 0 命中，且 0 命中必须来自至少一次真实读数」；
本轮把它**接进本机门禁**只是让它"会被跑"，没有把任何一次命中变成阻断。

---

## 6 台阶 4 · 五条写声明（R16-4 的后半）

| # | 写声明 | 落点 | 读数 |
| --- | --- | --- | --- |
| 1 | 退出码语义（0/1/2/3） | `tools/README.md` 新增「门禁退出码」节；`ci_local.py` 的门禁步骤表写明本脚本只返回 0/1/2（3 属于 `provenance.cli` 的封条语义） | 表写进数据即可（方案 §5.3 已给表） |
| 2 | 会话窗口 | 方案 §4 台阶 4 的「写声明」小节 | 服务对象已由台阶 −2 的"每会话一棵树 + `.tmp/ci-local.lock`"承接 |
| 3 | 写权租约 | 同上 | 隔离 + 排他锁 + 单写者已覆盖 W1/W7；新机制没有服务对象 |
| 4 | 3 条未声明通道 | `adapters/wiring-scope.yaml`：`dsh-web-channel` / `dsh-headless-channel` / `dsh-verify-dead-channel`，`out_of_scope` + `expires_at=2026-10-31` + 理由「待使用者确认接线与否」 | `declared 3 → 7`（in_scope 1 / out_of_scope 5 / expected_absent 1）；`wiring-scope --check` 退出 0；**不接任何线** |
| 5 | CI 注释里的边界裁定 | `agent-channel-inventory-report-mode`（`kind=gate_check`，`expires_at=2026-12-31`） | 同上；来源写明 `.github/workflows/phase-8.yml:266-272` |

**到期检查（只报告）**：新增 `tools/exemption_expiry.py`，读 `adapters/wiring-scope.yaml`
（经 `provenance.wiring_scope.load_wiring_scope`，不自己解析 YAML）与 `ci_local` 的
`REPORT_ONLY_STEPS`；**≤14 天提醒（`DUE`）、过期标红（`RED`）**，退出码**恒为 0**，
读不到写 `unprovable`。14 天规则**只有这一份实现**（`state_for()`，四个边界由回归钉住）。

**"现有加载器会不会因过期直接报错"——先查再动，读数如下**：`src/provenance/wiring_scope.py`
只有 `_require_date()`（校验 ISO 格式），**没有任何"今天"的比较**（全文读过，175 行）——
因此到期读数放在加载器之外，**加载期的形状校验一个字没改**，
本轮也**没有引入任何加载期 FATAL**（符合"本轮不新增阻断步骤"）。

**只加行、没加键**：`adapters/wiring-scope.yaml` 的 `schema_version` 保持 `"1"`——
第 55 条的判据是"键集合或语义变没变"，加声明行不改键集合（`declared` 从 3 变到 7 是**数据**）。
**请评审确认**这一口径；若评审认为"声明集合本身是被消费的协议"，处置是递增
`provenance.wiring_scope.SCHEMA_VERSION` 并同批改 `as_json()` 的消费方与测试。

---

## 7 预算对账（口径 `len(text.splitlines())` / numstat，与 §7 同）

`git diff --numstat b23db01..60f0db5`（本文件之前的那三个提交）：

| 桶 | 新增 / 删除 | 主要构成 |
| --- | --- | --- |
| src | +22 / −3 | `src/policy/check.py`（包装版本轴） |
| tests | +282 / −2 | 两个新回归文件（162 + 113）+ `test_cli.py` 的键集合断言 |
| tools | +452 / −11 | `exemption_expiry.py` 231（新）+ `ci_local.py` 166 / −4 + `obligations_gate.py` 3 / −1 + 生成器 14 / −5 + `README.md` |
| 数据 | +70 | `adapters/wiring-scope.yaml` 的四条声明与注释 |
| 文档 | +16 / −10（另有方案 +40 / −1、AGENTS +7 / −3、README +5 / −1 等，git 对非 ASCII 路径加引号，本表按前缀分组时会落到"其他"） | 方案 §7/§10、学习手册重生成产物、AGENTS 第 55/56 条 |

**台阶 4 的预算对照**（§7.1 的上调后上限：src 3.25k / tests 3.5k）：本轮台阶 4 的**写声明**部分
src **0 行**、tests +275（两条回归），远在区间内——因为它按裁定**只做声明**，不建机制。
**台阶 3 的累计口径**已按 R16-3 重记在方案 §7 / §7.1（本机读数：src 新增 1302 / 净增 1223，
1.63× / 1.53×；裁定里的 ≈1.36k 是"1.7 倍"，两者差在数法上、结论相同）。

---

## 8 未做 / 未核实 / 请评审裁定

1. **未做（按裁定）**：台阶 4 的**机制**（`governs` 轴、`reading_context`、声明差集与五个差集、
   豁免到期机制、仪器自证 R-h）与**台阶 5**（`validation/control-plane.yaml`、合并谓词、跨源互证）
   一条都没建；本轮只写声明与只报告读数。
2. **未做**：`.github/workflows/phase-8.yml` **一个字节没改**——两条只报告步骤是本机的，
   CI 步骤表因此不变（`unregistered_steps()` 仍然为空，读数见门禁运行）。
3. **未核实**：远端 `origin/feat/rules-and-os-platform` 此刻的真实状态（本轮按禁令没有 fetch）。
4. **未核实**：`tool.pytest` 在 Hook 审计摘要里的"行为可追溯性"缺口的影响面（§2 R4）；
   处置建议与代价已给出，**请评审裁定**是否在下一轮做。
5. **未核实**：`adapters/wiring-scope.yaml` 加行**不升 `schema_version`` 这条口径（§6 末）——
   请评审确认或改判。
6. **未核实**：仓库外是否有消费方按"顶层键集合恰好等于旧集合"读 `policy.check --json`（§4）。
7. **本轮新增的两个只报告步骤没有被任何 CI 步骤覆盖**：它们在 CI 上不跑（本机专属），
   因此"豁免到期"这件事在 CI 上不可见——这是**有意**的（CI 上没有账本 / 宿主状态），
   但评审若要求在 CI 上也可见，处置是加一条"总是退 0"的 workflow 步骤（本轮没有加）。
8. **本轮没有跑 `tools/cleanup.py`**；`.tmp/step4/`、`.tmp/step3b/` 的产物保留供评审复核。
9. **本轮没有 push**、没有 `--no-verify`、没有强推、没有 `git add -f`；
   改动**只用 `write` / `edit` 落树**，提交按路径暂存。

---

## 9 复现命令（按顺序，全部只读或写 `.tmp`）

```powershell
# 0 合并读数（应为 Already up to date）
git merge-base refactor/control-plane origin/feat/rules-and-os-platform   # -> 6fa800e
git merge --no-edit origin/feat/rules-and-os-platform                     # -> Already up to date.

# 1 tool.pytest 的追溯读数（R1/R2/R3）
.venv\Scripts\python.exe -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('validation/validators.yaml').read_bytes()).hexdigest())"
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m policy.check src/policy/obligations.py --changed src/policy/obligations.py --operation edit --json > .tmp\probe\check.json

# 2 R-d 差集（before 侧已固化在 .tmp/step4/decisions-before.json）
.venv\Scripts\python.exe .tmp\step3b\probe_decisions.py --out .tmp\step4\decisions-after-run.json
.venv\Scripts\python.exe .tmp\step3b\json_field_diff.py --before .tmp\step4\decisions-before.json --after .tmp\step4\decisions-after-run.json --out .tmp\step4\field-diff-run.json

# 3 只报告步骤与到期检查
.venv\Scripts\python.exe tools\ci_local.py --list
.venv\Scripts\python.exe tools\obligations_gate.py --ledger .tmp\obligations\missing.jsonl
.venv\Scripts\python.exe tools\exemption_expiry.py

# 4 声明文件与包装版本
.venv\Scripts\python.exe -m provenance.cli wiring-scope --check --json
$env:PYTHONPATH='src'; .venv\Scripts\python.exe -m policy.check examples/good_controller.py --layer controller --json

# 5 门禁（本轮 step 5 的两次运行；读数单独记录）
.venv\Scripts\python.exe tools\ci_local.py --full --python .venv/Scripts/python.exe
.venv\Scripts\python.exe tools\ci_local.py --hook --python .venv/Scripts/python.exe
```

---

## 10 本次改动的文件（按提交）

| 提交 | 文件 | 处置 |
| --- | --- | --- |
| `843f6dd` 修正 | `src/policy/check.py` | 包装版本轴（常量 / docstring / `__all__` / `render_json`） |
| | `AGENTS.md` | 第 55 条登记 `policy.check.OUTPUT_SCHEMA_VERSION` |
| | `README.md`、`docs/project/architecture/使用说明.md` | 包装键清单与版本说明 |
| | `tests/integration/test_cli.py` | 顶层键集合断言 8 → 9 |
| | `tools/build_learning_notebook.py` + `docs/project/learning/phase-0/walkthrough.{ipynb,py}` | 键清单同步 + 重生成 |
| | 方案 `控制面重构方案.md` | §7 台阶 3 累计口径、§7.1 的 2026-09-30 补记、§10 的裁定小节 |
| `6ad7376` 义务门禁 → 门禁 | `tools/ci_local.py` | `REPORT_ONLY_STEPS` + 只报告执行路径 + `--list` 可见 |
| | `tools/exemption_expiry.py`（新） | 到期检查（只报告，退出码恒 0） |
| | `tools/obligations_gate.py`、`tools/README.md`、`AGENTS.md` 第 56 条 | 口径同步（"不在步骤表里"现在是错的） |
| | `tests/unit/test_ci_local_report_only.py`、`tests/unit/test_exemption_expiry.py`（新） | 12 条回归 |
| `60f0db5` 台阶 4 写声明 | `adapters/wiring-scope.yaml` | 四条声明（三条通道 + CI 注释裁定） |
| | `tools/README.md` | 「门禁退出码」节（0/1/2/3 + 编排器自己的退出码） |
| | `tools/ci_local.py` | docstring 的门禁步骤表与退出码 |
| | 方案 `控制面重构方案.md` | §4 台阶 4 的「写声明」小节（5 条 + 到期检查） |
| 本文件 | `18-round16-rulings-execution.md` + 归档 `README.md` 索引 | 新归档 |

**执行纪律**：只用 `write` / `edit` 落树；按路径暂存；没有 `--no-verify`、没有强推、
没有 `git add -f`、没有 `tools/cleanup.py`。
**墙钟**：本轮从勘察到三个提交约 4 小时（含一次全量门禁基线运行 20 分钟）；
门禁（`--full` 与 `--hook`）的读数按 16 号 §9 的同一纪律在提交后单独记录。
