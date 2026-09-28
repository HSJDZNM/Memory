# 10 · 台阶 1（H4）字段级差集、受影响清单与红→绿读数

- **执行**：2026-09-28 23:35–23:55 +08:00（本机）；控制面重构会话（唯一写者）。
- **源码树（提交对象）**：`C:\\Users\\ZNM\\Downloads\\Memory-refactor` = 分支 `refactor/control-plane` @ `cb73617`（台阶 −1② 的提交）+ 本台阶改动（三个源码文件 + 一条新检查）。
- **测试证据所属树（必须写清，AGENTS 第 48 条）**：`C:\\Users\\ZNM\\Downloads\\Memory\\.tmp\\h4-shadow`——同一个提交 `cb73617` 的 `--detach` 影子 worktree，位于 session workspace 内。
  **为什么要影子树**：本机沙箱不允许子进程写 `../Memory-refactor`（实测 `os.open(O_CREAT)` → `PermissionError errno=13`，连 `New-Item` 建目录也被拒），而 `tests/conftest.py:34` 会把会话临时根固定成 `<repo>/.tmp/tmp`——在重构树里跑 pytest 在 conftest 导入期就起不来。影子树与重构树**逐文件对应**（四个文件的 sha256 两边相同，见 §5），因此读数是它的，结论是重构树的。
- **解释器**：`C:\\Users\\ZNM\\Downloads\\Memory\\.venv\\Scripts\\python.exe`（3.13.11 / pytest 9.1.1）——与 `08` 里门禁的 `CI_LOCAL_PYTHON` 同一个解释器。
- **本文件是什么**：台阶 1 的 R-d（字段级差集）、受影响 fixture 清单与 R-f 红→绿读数。原件在 `Memory\\.tmp\\h4\\`（读数与 junit）与 `Memory-refactor\\.tmp\\`（探针脚本），`tools/cleanup.py` 之后不可复核。

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

---

**签署口径**：本文件每个数字都能用上面的命令重算；凡我没亲自跑出来的，都标了「未核实」。
