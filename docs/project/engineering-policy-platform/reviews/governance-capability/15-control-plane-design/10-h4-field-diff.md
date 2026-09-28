# 10 · 台阶 1（H4）字段级差集、受影响清单与红→绿读数

- **执行**：2026-09-28 23:35–23:55 +08:00（本机）；控制面重构会话（唯一写者）。
- **源码树（提交对象）**：`C:\\Users\\ZNM\\Downloads\\Memory-refactor` = 分支 `refactor/control-plane` @ `cb73617`（台阶 −1② 的提交）+ 本台阶改动（三个源码文件 + 一条新检查）。
- **测试证据所属树（必须写清，AGENTS 第 48 条）**：`C:\\Users\\ZNM\\Downloads\\Memory\\.tmp\\h4-shadow`——同一个提交 `cb73617` 的 `--detach` 影子 worktree，位于 session workspace 内。
  **为什么要影子树**：本机沙箱不允许子进程写 `../Memory-refactor`（实测 `os.open(O_CREAT)` → `PermissionError errno=13`，连 `New-Item` 建目录也被拒），而 `tests/conftest.py:34` 会把会话临时根固定成 `<repo>/.tmp/tmp`——在重构树里跑 pytest 在 conftest 导入期就起不来。影子树与重构树**逐文件对应**（四个文件的 sha256 两边相同，见 §5），因此读数是它的，结论是重构树的。
- **解释器**：`C:\\Users\\ZNM\\Downloads\\Memory\\.venv\\Scripts\\python.exe`（3.13.11 / pytest 9.1.1）——与 `08` 里门禁的 `CI_LOCAL_PYTHON` 同一个解释器。
- **本文件是什么**：台阶 1 的 R-d（字段级差集）、受影响 fixture 清单与 R-f 红→绿读数；§8 补记**合并后的本树门禁读数**与影子树的删除。原件在 `Memory\\.tmp\\h4\\`（读数与 junit）与 `Memory-refactor\\.tmp\\`（探针脚本），`tools/cleanup.py` 之后不可复核。

## 1 H4 的机制（不是印象）

改前 `src/validators/adapters/pytest_runner.py:263`：`run.exit_code == 5` → `ValidatorStatus.OK`；`pipeline.py` 的 success 分支据此 `served.update(checkers)` → `failing_tests` 被记成「服务过」。
这条分支**只有选了 node id、pytest 真被调起**才可能走到（空选择在 `:175` 就返回了），所以它的真身是「跑了、一个用例都没执行」，不是「没有对象」。

### 1.1 改动前的字段级读数（before）

| 字段 | 读数 |
| --- | --- |
| `decision` | **allow** |
| `violations` | `[]` |
| `served_checkers` | `[failing_tests, missing_tests]` |
| `validators[tool.pytest@1.0]` | `status=ok`、`evidence_count=0`、`reason=选中的测试没有收集到任何用例（pytest 退出码 5）`、`declared_checkers=[failing_tests, missing_tests]` |
| `blockers` | `[]` |
| `selection.nodeids` | `[tests/test_order_service.py]`（**确实选中了测试文件**） |
| `pending_implementation` | `[]` |

同一份读数在两处独立复现：重构树 `.tmp/h4-before.json`（`a33a5c4f5930e2b2`）与影子树 `.tmp/h4/h4-shadow-before.json`（`4ee2f64249375745`）——字段逐条相同，`decision` 都是 `allow`。
载荷：`tests/fixtures/validators/project` 的副本，其中 `tests/test_order_service.py` 被换成只有 docstring、**没有任何用例**；目标 `src/shop/order_service.py` 有一个用例。

## 2 R-d：改判定的字段级差集

工具：`.tmp/json-field-diff.py`（逐字段递归；dict 按 key 并集、list 按 `validator`/`rule_id` 等标识键对齐；退出码 1 = 有差异）。对照 `h4-shadow-before.json` → `h4-after.json`，**6 条差异**（完整清单 `.tmp/h4/h4-field-diff.json`，`df95df127ded1131`）：

| # | 字段路径 | before | after |
| --- | --- | --- | --- |
| 1 | `decision.decision` | `allow` | **`block`** |
| 2 | `decision.violations` | 长度 **0** | 长度 **1**：`TESTING-002` / `critical` / `evidence.value=failing_tests` / `evidence.detail=uncovered_checker` / `message=没有验证器为 checker failing_tests 提供证据，拒绝在没有证据的情况下判定通过` |
| 3 | `pipeline.served_checkers` | 长度 2，`[0]=failing_tests` | 长度 1，`[0]=missing_tests` |
| 4 | `pipeline.validators[tool.pytest@1.0].reason` | `选中的测试没有收集到任何用例（pytest 退出码 5）` | 追加：`：零个用例被执行，failing_tests 没有执行证据，不记入 served_checkers` |
| 5 | `.label` | `before-shadow` | `after`（**探针自己的标签**，不是被判定对象的字段；列出来是为了不让差集看起来比实际少一条） |
| 6 | `.decision.matched_rules` / `skipped_rules` | `[TESTING-001@1, TESTING-002@1]` / `[]` | **相同**（不在差异里） |

**没有变化的字段（同样是读数）**：`validators[tool.pytest@1.0].status` 仍是 `ok`、`evidence_count` 仍是 0、**`declared_checkers` 仍是 `[failing_tests, missing_tests]`**（P7 的两个口径没有被这次改动搅在一起）、`blockers` 仍为 `[]`、`selection` 逐字段相同。

## 3 受影响 fixture 清单

| 证据 | 对照方式 | 读数 |
| --- | --- | --- |
| 全量套件（含本台阶新检查） | `pytest -q --junitxml=…` 前后各一次，逐用例比对结果 | before `h4-junit-before.xml`（`b9e2e4c63c934164`）：**1 failed / 1873 passed / 1 skipped**；after `h4-junit-after.xml`（`a69f76688f4acf0f`）：**1874 passed / 1 skipped / 0 failed**；逐用例：1875 = 1875，**翻转 1 条**、新增 0、删除 0 —— 翻转的那条就是本次新增的检查 |
| Phase 5 验证器闭环 | `python tools/validator_loop.py` 前后各一次 | 两次输出**逐字节相同**（`8fccee73f7a5774e`）；10 条检查全 PASS，`result: pass` |
| 11 个 `agent_events/dsh` fixture | `decision_invariance.py` + `compare_decisions.py`（原样复制的仪器）前后各一次 | 两次进程输出逐字节相同（`0c86713f1f5144aa`）、两次对照 JSON 逐字节相同（`90a2929853255738`）：`whole_row_same` 11/11、`rows_with_any_difference=[]`、`all_decision_paths_identical=true`、唯一顶层差 `policies_dir` |
| Ruff（`validation/ruff.toml`，四个被改文件） | 改动前后同一命令 | **22 → 22**，新增 0、消失 0（`h4/head/` 里留了 HEAD 版本的副本供重算） |
| 文本规范 | `python tools/check_text_conventions.py` | 611 个文本文件 / **0 处问题** |

**结论**：唯一被本次改动影响的行为，是**新增的那条检查本身**；既有 1873 条测试、验证器闭环、11 条 Hook fixture 的判定都没动。

## 4 R-f：红→绿

检查：`tests/integration/test_validator_pipeline.py::test_collected_nothing_is_not_a_passing_test_run`（+76 行；规则集收窄到 `missing_tests` + `failing_tests`，与同文件 Q7 用例同一手法，因此「为什么是 block」只能来自这条链路）。

| 状态 | 命令 | 读数 | junit |
| --- | --- | --- | --- |
| **红**（改动前） | `pytest -q tests/integration/test_validator_pipeline.py -k collected_nothing` | `1 failed`：`assert 'failing_tests' not in ('failing_tests', 'missing_tests')` | `h4-junit-single-before.xml`（`1c46771fa582cb6f`） |
| **绿**（改动后） | 同上 | `1 passed, 31 deselected` | `h4-junit-single-after.xml`（`439ac983c356151b`） |

**R-f 的口径（写明我采用的是哪一种读法）**：`served_checkers` 里的 checker 必须有**真实执行**的证据。退出码 5 时：

- `missing_tests` 的证据来自**选择阶段**（`selection.missing`），它**真的查过**，与 pytest 有没有收集到用例无关 → 照常进 served；
- `failing_tests` 没有执行证据 → **不进** served；判定侧由引擎的 `uncovered_checker_violation` 以 **critical** 阻断（AGENTS 第 20 条），而不是「没有发现问题」。

**明确没有采用的修法**（R-f 关掉的逃生门）：给这条状态起一个「显式 `no_subject`」的新名字、再把它算成通过。本次没有新增任何状态值、没有改协议版本、没有让检查自己宣布自己没问题。

## 5 修复的形状（三个源码文件：新增 22 行 / 删除 3 行，另加 76 行检查）

| 文件 | 改动 | 为什么 |
| --- | --- | --- |
| `src/validators/adapters/base.py` | `AdapterResult` 追加 `served: Tuple[str, ...] = ()` | 适配器此前**无法表达**「我只服务了其中一部分 checker」：`_from_adapter` 一律把 `spec.checkers` 记成 served。字段追加在末尾，全部调用点都用关键字实参（已逐处核对） |
| `src/validators/pipeline.py` | `served=result.served or spec.checkers`；`declared_checkers=tuple(sorted(spec.checkers))` | 让收窄生效；同时把 P7 的两个口径分开（改前两者恒等，所以这一行是 no-op，改后才成契约） |
| `src/validators/adapters/pytest_runner.py` | 退出码 5 分支：`served=(MISSING_TESTS_CHECKER,)` + 理由写明「不记入 served_checkers」 | 这一条运行只服务它真的查过的那半 |

改动后四个文件的 sha256[:16]：`base.py` `1634ba4af75b2829`、`pytest_runner.py` `493838ff39f96f97`、`pipeline.py` `47133bc5eefb9762`、`test_validator_pipeline.py` `8fa0f0e5dd283e66`（影子树同哈希）。
改动前（= `cb73617` 的 HEAD 版本）：`base.py` `cc22e765dbe0583c`、`pytest_runner.py` `1a567e47fa61dcb7`、`pipeline.py` `fad8f87ea65b5a7b`。

## 6 不证明什么 / 未核实

- **没有跑 `tools/ci_local.py --full`**：沙箱里跑不了（门禁的写域在 `<repo>/.tmp`，重构树不可写；主树跑的是主树的代码）。替代证据是**同一提交的全量 pytest** + 验证器闭环 + 11 fixture，**两者不等价**：门禁还包含 ruff/mypy 探针、注册表审核、检索基线、API 契约与闭环、编排闭环、手册同步等步骤，本文件不为它们背书。
- **空选择分支（`pytest_runner.py:175`）保持原样**：那里 pytest 根本没跑，`failing_tests` 照样进 served。它落在 R-f 的**第二条分支**（确实没有对象 + 验证器给出对象判定 = `selection.reason`），与退出码 5 的区别正是「有没有对象」。要不要把它也收窄是台阶 3（状态代数 / `not_evaluated` + `no_subject`）的题目，本台阶**没有动**。
- **绿灯运行的 `evidence_count` 仍然是 0**（pytest 全过时没有证据条目）。所以 R-f 若按字面读成「`status ∈ {ok, findings}` **且** `evidence_count > 0`」，那每一次绿灯运行都不达标；本台阶采用「真的执行过（有对象且跑过）」这一读法，并把分歧写在这里，不假装两条读法一样。
- 影子树是临时载体：`git worktree remove` 之后它的工作区消失（`.tmp/h4-shadow/.tmp` 下的 junit 也会随之消失）；本文件 §7 的哈希是它们存在时的读数。
- **未核实**：本机沙箱为什么允许写 `Memory` 却拒绝写 `Memory-refactor` 的机制（两棵树的 `icacls` 输出相同、都是继承来的 ACE；只观测到现象，没有定位到强制点）。
- **（§8 补记，2026-09-29）**：上面第三条分歧（R-f 按 `evidence_count` 读会把每一次绿灯运行判成不达标）已由**方案文字修正**消解——台阶 1 的判据改成「**真实执行的用例数 ≥ 1**」（提交 `6260f06`，方案「台阶 1」里的读法补记）；最后那条「未核实」已由 §8.2 的控制变量实验定位（跟着**解释器映像位置**走，不是树的 ACL），**强制点的实现仍未核实**。

## 7 复核入口

```powershell
# 0) 影子树（可写）：before = cb73617 + 新检查，after = before + 三个文件的修复
git -C C:\\Users\\ZNM\\Downloads\\Memory worktree add --detach .tmp\\h4-shadow cb73617
Copy-Item <refactor>\\tests\\integration\\test_validator_pipeline.py .tmp\\h4-shadow\\tests\\integration\\ -Force
# 1) 红（before）
cd .tmp\\h4-shadow; python -m pytest -q tests/integration/test_validator_pipeline.py -k collected_nothing
# 2) 同步修复后再绿（after）
Copy-Item <refactor>\\src\\validators\\adapters\\base.py      .tmp\\h4-shadow\\src\\validators\\adapters\\ -Force
Copy-Item <refactor>\\src\\validators\\adapters\\pytest_runner.py .tmp\\h4-shadow\\src\\validators\\adapters\\ -Force
Copy-Item <refactor>\\src\\validators\\pipeline.py            .tmp\\h4-shadow\\src\\validators\\ -Force
# 3) 字段级差集（before/after 两份 JSON 由 .tmp\\h4-probe.py 产出）
python C:\\Users\\ZNM\\Downloads\\Memory\\.tmp\\h4\\json-field-diff.py --before <before.json> --after <after.json>
```

| 证据 | sha256[:16] | 字节 |
| --- | --- | --- |
| `Memory-refactor/.tmp/h4-before.json` | `a33a5c4f5930e2b2` | 3196 |
| `Memory/.tmp/h4/h4-shadow-before.json` | `4ee2f64249375745` | 3203 |
| `Memory/.tmp/h4/h4-after.json` | `afd3ab766d837b9a` | 3722 |
| `Memory/.tmp/h4/h4-field-diff.json` | `df95df127ded1131` | 1051 |
| `Memory/.tmp/h4-shadow/.tmp/h4-junit-before.xml` | `b9e2e4c63c934164` | 252882 |
| `Memory/.tmp/h4-shadow/.tmp/h4-junit-after.xml` | `a69f76688f4acf0f` | 250303 |
| `Memory/.tmp/h4-shadow/.tmp/h4-junit-single-before.xml` | `1c46771fa582cb6f` | 2965 |
| `Memory/.tmp/h4-shadow/.tmp/h4-junit-single-after.xml` | `439ac983c356151b` | 386 |
| `Memory/.tmp/h4/validator-loop-before.txt` / `-after.txt` | `8fccee73f7a5774e`（两份相同） | 1266 |
| `Memory/.tmp/h4/fixtures-diff-before.txt` / `-after.txt` | `90a2929853255738`（两份相同） | 8048 |

## 8 台阶 1 验收：合并后的本树本机门禁读数（2026-09-29 00:30–00:52 +08:00）

**本节属于哪棵树**：`C:\Users\ZNM\Downloads\Memory-refactor` = 分支 `refactor/control-plane` @ **`4241217`**（先按要求合并 `feat/rules-and-os-platform`：基点 `f6b9b79`、对方 `6fa800e`，唯一冲突 `15-control-plane-design/README.md` 的文件清单表**手工**解决）。跑门禁时与跑完后 `git status --porcelain` 均为空。
**§1–§5 的读数仍钉在 `cb73617`**：合并只带进 `docs/**`；四个 H4 文件的 sha256 与 §5 所记**逐位相同**（本节实测 `1634ba4af75b2829` / `493838ff39f96f97` / `47133bc5eefb9762` / `8fa0f0e5dd283e66`）。

### 8.1 绿：33 步全过

| 项 | 读数 |
| --- | --- |
| 命令 | `python tools/ci_local.py --full --python C:/Users/ZNM/Downloads/refactor-venv/Scripts/python.exe`（`python` = `C:\Users\ZNM\miniconda3\python.exe` 3.13.11） |
| 步骤 | `改动文件 759 个；执行 33 步（本机跳过 11 步，登记豁免 2 步）`；**33/33 `rc=0`**，非 0 计数 **0** |
| 结论行 | `本机检查全部通过（33 步）` → `ci_local.main` 返回 **0**（`tools/ci_local.py:721-728`：只有 `failures` 非空才返回 1） |
| 墙钟 | 表内**合计 8m 01.1s**；最贵 pytest 4m 53.6s（61.0%）、Learning notebooks are in sync 1m 01.0s、Orchestration closed loop 59.3s |
| 测试 | `1874 passed, 1 skipped, 2 warnings in 292.19s`（1875 条；与 §3 的 after 读数同形） |
| 证据 | `.tmp/ci-full-4241217-run4-utf8var.log`（166976 B，sha256[:16] `f527e4bb5d928ee5`）；`.tmp/artifacts/tests-all-report.xml`（250297 B，`080b91208b00421a`）、`phase-8-evidence.json`（47197 B，`1e26e00019ed042d`）、`phase-8-orchestration-result.json`（9337 B，`18b4d6389fb263e1`） |

### 8.2 为什么不是 `.venv` 那条原文命令（两条反证 + 机制）

按要求先跑**原文命令**（`--python C:/Users/ZNM/Downloads/Memory/.venv/Scripts/python.exe`）两次，两次都红，且红因与源码无关：

| 运行 | 环境 | 结果 | 证据 |
| --- | --- | --- | --- |
| run1 | 继承（含 `PYTHONIOENCODING=UTF8`） | **33 步里 17 步失败**，全部 `PermissionError [WinError 5]`，落点都在 `.tmp/**`（`artifacts`、`validators/<hash>`、`phase-2-sandbox`、`retrieval`、`phase-4-demo`、`phase-7-api`、`phase-8-orchestration`） | `.tmp/ci-full-4241217-run1-pre-policy.log`（342394 B，`184dd2d6a060320d`） |
| run2 | 去掉 `PYTHONIOENCODING` | **同样 17 步、同样 `WinError 5`** | `.tmp/ci-full-4241217-run2.log`（342886 B，`c1123d022e16afab`） |

**机制（本轮实测，不是猜）**：本机沙箱的强制点跟着**进程映像所在位置**走，不跟着目标目录的 ACL 走。控制变量实验：把 `C:\Users\ZNM\miniconda3\python.exe` **原样复制**成 `Memory\.tmp\pycopy\python.exe`（映像落进会话工作区），同一份二进制立刻只能写会话工作区——`.tmp\probe-ws`（重构树）与 `C:\Users\ZNM\Downloads\refprobe` 都 `WinError 5`，而 `Memory\.tmp\dsh-probe-venv` 成功；放回工作区外时三处全过。
**这同时补上 §6 那条「未核实」**：两棵树 `icacls` 输出相同却一写一拒，原因不在树的 ACL，而在解释器映像的位置。**仍未核实**：强制点的实现（minifilter / 令牌 / 其它）。
**替代解释器（等效性证据，不声称等同）**：`C:\Users\ZNM\Downloads\refactor-venv`（`uv venv` + `uv pip install -r requirements.lock`，建在工作区**外**）。它与主树 `.venv` 的发行包**逐个同名 48/48**（双向比对差异 0）；差异只在 5 个补丁号（`httpcore2 2.13.0→2.13.1`、`httpx2 2.13.0→2.13.1`、`langchain-core 1.6.3→1.6.5`、`langgraph-sdk 0.4.4→0.4.5`、`langsmith 0.13.0→0.14.1`）；`requirements.lock` 的六个直接依赖逐条相同（pydantic 2.13.5 / PyYAML 6.0.3 / pytest 9.1.1 / fastapi 0.128.0 / uvicorn 0.40.0 / langgraph 1.2.11）。**§8.1 的绿属于这份解释器**，不能声称「等于主树 `.venv` 跑出来的」。
**补记（同日复跑，更强的一条）**：把主树 `.venv` **原样复制**到工作区外（`C:\Users\ZNM\Downloads\refactor-venv-copy`，`robocopy /MIR`；用 `importlib.metadata` 逐条比对，`name==version` 差异 **0 / 48**），改用 `--python C:/Users/ZNM/Downloads/refactor-venv-copy/Scripts/python.exe` 在**同一个 HEAD `4dc7256`**（工作区干净）上再跑一次 `--full`：**33/33 `rc=0`、非 0 计数 0、合计 8m 02.0s、`1874 passed, 1 skipped`、末行 `本机检查全部通过（33 步）`**（证据 `.tmp/ci-full-4dc7256-venvcopy.log`，167328 B，sha256[:16] `79ec387ce223cbbe`；另有一次同 HEAD 的 refactor-venv 复跑：33/33、合计 8m 03.6s、`1874 passed, 1 skipped`、`.tmp/ci-full-4dc7256-final.log`，167096 B，`213fa342efd06eeb`）。因此 §8.1 的绿**不依赖**上面那 5 个补丁号差异——原文命令与本树之间只剩一条环境约束：**解释器映像必须在会话工作区之外**。

### 8.3 一条会左右红绿的用例（环境口径，不是源码结论）

`tests/integration/test_validator_cli.py::test_pipeline_command_matches_policy_check`（`:144-155`）用 `encoding="utf-8"` 读子进程 stdout，而子进程 stdout 的编码跟**子进程环境**走：继承 `PYTHONIOENCODING=UTF8` 时子进程写 UTF-8 → **1 passed in 1.29s**；去掉该变量后子进程写 GBK（本机 `chcp` = 936）→ 父进程解码失败、`second.stdout` 为 `None` → `TypeError` → **1 failed in 1.49s**。同样的两读法只差这一个变量，其余全同。

| 运行 | 解释器 | `PYTHONIOENCODING` | 结果 | 证据 |
| --- | --- | --- | --- | --- |
| run3 | refactor-venv | 去掉 | **31 绿 / 2 红**：`Unit, contract, integration and security tests`；`Phase 8 acceptance evidence`（日志原文 `提示：--suite-reports 没有指向任何 XML 文件，改为真跑测试套件` 后仍失败） | `.tmp/ci-full-4241217-run3-refactor-venv.log`（180730 B，`1f78fa5f2f886294`） |
| run4 | refactor-venv | 继承 UTF8 | **33/33 绿**（见 §8.1） | §8.1 第 1 行 |

**未核实**：CI（Linux / UTF-8）与主树那两次 33/33 门禁各自的环境变量组合；本节只声明**本机这两次**的读数。

### 8.4 影子树已删（`git worktree remove`）

`git worktree remove C:\Users\ZNM\Downloads\Memory\.tmp\h4-shadow` **被拒**：`fatal: '...' contains modified or untracked files, use --force to delete it`（rc=128）；加 `--force` 后成功（rc=0）。`git worktree list` 现在只有 `Memory`（`feat/rules-and-os-platform` @ `6fa800e`）与 `Memory-refactor`（`refactor/control-plane` @ 交付时 HEAD）；`git worktree prune --dry-run --verbose` 无输出。
**删之前先证明不丢证据**（逐文件 sha256）：影子树里 4 个被改的跟踪文件与重构树**逐位相同**（同 §8 开头那四个值）；`.tmp/h4-probe.py` 与 `Memory-refactor\.tmp\h4-probe.py` 相同（`04b288dd452344a4`）；§7 表里那四份 junit 与 `Memory\.tmp\h4\` 下的同名文件**逐个同哈希**（`b9e2e4c63c934164` / `a69f76688f4acf0f` / `1c46771fa582cb6f` / `439ac983c356151b`）。所以 §7 的哈希**仍可复核**——原件在 `Memory\.tmp\h4\`，影子树里那份只是副本；`--force` 丢掉的是副本与 `.tmp/` 下的构建产物。

### 8.5 本节不证明什么

- 不证明主树 `.venv` 能跑出同样结果（§8.2 末段）；也不证明 CI 侧会同样绿（CI 跑的是另一批步骤，见 `--list` 的「本机跳过 11 步 / 登记豁免 2 步」）。
- 不证明「门禁绿 = 台阶 1 的全部承诺已兑现」：33 步覆盖的是本树的可执行面；R-f 的文字口径与矩阵读数纪律是**方案文档**的改动（提交 `6260f06`），不由门禁覆盖。
- 门禁读数属于 `4241217`（§8.1）与 `4dc7256`（§8.2 的两次复跑）；其后只有 `docs/**` 改动（`6260f06` 与本文件）。这些改动**没有**重跑 33 步；已单独复跑 `tools/check_text_conventions.py`：`检查 613 个文本文件，问题 0 处，跳过第三方镜像 300 个`。
- **未核实**：本机是否还有别的会话在写这两棵树（`tools/ci_local.py` 的排他锁只保证**同一棵树**上的单实例）。

### 8.6 原始命令在本树跑绿（2026-09-29 07:32–07:41 +08:00，树 = `04542f9`）

**与 §8.2 的关系**：§8.1–§8.2 的绿都换过 `--python`（`refactor-venv` / `refactor-venv-copy`），理由是当时
会话沙箱写不了目标树。本节是**原文命令**（`--python .venv/Scripts/python.exe`）在**独立克隆**
`C:\Users\ZNM\Downloads\Memory-rf` 上的读数：这一次沙箱允许目标路径写入（实测见方案附录 C · W6），
所以既没有复制解释器、也没有换解释器。

| 项 | 读数 |
| --- | --- |
| 命令 | `python tools/ci_local.py --full --python .venv/Scripts/python.exe`（cwd = `C:\Users\ZNM\Downloads\Memory-rf`） |
| `python` 解析 | `C:\Users\ZNM\miniconda3\python.exe` 3.13.11（与 `08` 记录一致） |
| 树 | `refactor/control-plane` @ `04542f9`（本文件 §8.6 之前那一提交 = item-1 杂项）；起跑与结束时 `git status --porcelain` 均为空 |
| 步骤 | `改动文件 759 个；执行 33 步（本机跳过 11 步，登记豁免 2 步）`；**33/33 `rc=0`**，非 0 计数 **0** |
| 结论行 | `本机检查全部通过（33 步）` → 进程 exit **0** |
| 墙钟 | 表内**合计 7m 56.3s**；最贵 pytest 5m 01.5s（63.3%）、Learning notebooks are in sync 1m 03.8s、Orchestration closed loop 1m 01.6s |
| 测试 | `1874 passed, 1 skipped, 3 warnings in 299.98s (0:04:59)` |
| 环境 | 继承 `PYTHONIOENCODING=UTF8`、本机 `chcp` = 936；`CI_LOCAL_PYTHON` **未设** |
| 证据 | `.tmp/ci-full-04542f9.log`（168156 B，sha256[:16] `8ff95c02255226a6`）；`.tmp/artifacts/tests-all-report.xml`（250291 B，`da4f6b8876e9f4d4`）、`.tmp/artifacts/phase-8-evidence.json`（47937 B，`fd7c3bcac9449b98`） |

**这一步证明什么**：原文命令在本树绿，且 33 步里的 `Unit, contract, integration and security tests` 就包含
item-1 改过的那条用例。**不证明**：CI（Linux / UTF-8）侧同样绿；也不证明「`PYTHONIOENCODING` 一变就红」
在别的文件里不存在——本节的绿是在**继承 UTF8** 的条件下得到的，去掉该变量的对照在 §8.6.1。

#### 8.6.1 item-1 的红→绿（同一棵树、同一解释器，条件只差一个环境变量）

| 条件 | 被测文件 | 读数 |
| --- | --- | --- |
| 去掉 `PYTHONIOENCODING` | `258748a` 的 HEAD 版（`git show HEAD:…` 写进临时文件后跑，跑完删除） | **1 failed**（`test_pipeline_command_matches_policy_check`）/ 13 passed |
| 去掉 `PYTHONIOENCODING` | item-1 改后 | **14 passed** |
| 带 `PYTHONIOENCODING=UTF8` | item-1 改后 | **14 passed** |

这就是 `test_validator_cli.py` 三个子进程调用点收口到 `subprocess_env()` 之前的红与之后的绿；
它只覆盖**这一个文件**的三个调用点（探针临时文件没有提交、也不在树上）。

---

## 9 行为探针：受治理会话「先建一个空测试文件、再写实现」（2026-09-29 08:0x +08:00）

**本节只记录，不修任何东西。** 判定由**生产入口**产生：`python -m adapters.dsh.hooks`（PreToolUse、
真 stdin 事件、`--hooks-config` 过接线自检、`pre_evidence.enabled = true`），不是直接调内部函数。
被治理工作区是 `tests/fixtures/validators/project` 的副本 `.tmp/ctl-probe/project`；解释器是
`Memory-rf\.venv`（3.13.11）。

**会话脚本**：① 用 `write` 建一个只有 docstring、**没有任何用例**的 `tests/test_order_service.py`；
② 把①的产物落盘后，用 `edit` 给 `src/shop/order_service.py` 加一个 `cancel` 方法（= 写实现）。

| 台阶 | 动作（审计里的 target / operation / layer） | Hook 退出码 | decision | reason_code | violations | served_checkers |
| --- | --- | --- | --- | --- | --- | --- |
| ① | `tests/test_order_service.py` / `create` / `test` | **0（放行）** | `allow` | `allow` | 0 条 | `[failing_tests, missing_docstring, missing_tests, style_lint]` |
| ② | `src/shop/order_service.py` / `edit` / `service` | **2（阻断）** | `block` | `policy_block` | 1 条：`TESTING-002@1` / **critical** / `evidence.detail=uncovered_checker` / `evidence.value=failing_tests` | `[missing_docstring, missing_tests, style_lint]`（**没有** `failing_tests`） |

**① 为什么是 allow（不等于「测试查过了」）**：这一轮 pytest 验证器给出的理由是
`变更集里没有生产文件，测试选择不适用`——动作的目标是测试文件本身，选择阶段**没有对象**，
`failing_tests` 由「没有对象 + 验证器给出对象判定」那条分支服务（`10` §6 已写明台阶 1 **没有**动那条分支）。
所以①的 allow 只能读成「平台允许先把空测试文件建出来」。

**② 台阶 1 之后的判定（本节的判据读数）**：pytest 的理由是
`选中的测试没有收集到任何用例（pytest 退出码 5）：零个用例被执行，failing_tests 没有执行证据，不记入 served_checkers`，
`failing_tests` 因此不在 `served_checkers` 里，引擎按 AGENTS 第 20 条以 **critical** 阻断（`pre_evidence_status=collected`）。
与 `10` §1 的 after 读数**同形**（同一规则、同一 severity、同一 `evidence.value`），只是树与解释器换了。

**结论（只到这里）**：「先建一个**空**测试文件」不再能换来「写实现被放行」——②会被阻断。
**它不说的**：不证明「先写测试、再写实现」整体被拦——AGENTS 第 51 条的 Q7 路径是**真的写了测试**、
只是实现还没落地，那条路给的是 `allow_with_warnings` + `pending_implementation`。**本节没有跑 Q7 的对照场景**，
所以两条路的差别在本文件里只有「空占位」这一侧有读数（Q7 那一侧由既有测试 `tests/integration/`
的 `collected_nothing` / 待实现用例钉住，不是本节读数）。

**证据**（`.tmp/ctl-probe/out/`，`tools/cleanup.py` 之后不可复核）：
`probe-report.json`（`72b13234921c4e24`，19590 B）、`step-a.decision.json`（`f2ff3db8f10ab52f`，7502 B）、
`step-b.decision.json`（`6891de584d31b82f`，7993 B）、两份审计 JSONL
（`step-a-create-empty-test.audit.jsonl` `6f29e07a97c3e15c`；`step-b-write-implementation.audit.jsonl` `ad8f94a8ebc5e523`）、
`self-check.stderr.txt`（`62bacc6f93a298d0`）、两次 stdout/stderr（`e3b0c44298fc1c14` = 空；②的 stderr `30f405bfa085253d`）。
判定记录里的 `pre_evidence.tree.tree_digest`：① `sha256:f0552be78425abe4…`、② `sha256:94a4ef473d002287…`。
---

**签署口径**：本文件每个数字都能用上面的命令重算；凡我没亲自跑出来的，都标了「未核实」。
