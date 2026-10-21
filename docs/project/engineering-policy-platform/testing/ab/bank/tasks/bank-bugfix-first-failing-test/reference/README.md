# 参考解（bank-bugfix-first-failing-test）

> **它是什么**：本题的参考解树 `reference/tree/`（13 文件）+ 这一页读数。它用于实测 **T 的可达性**、
> **C 的天花板**与 **A 的 10/10**；**不参与判分**（`scoring.yaml` 的判据只有三条：隐藏 runner / policy.check /
> structure_metrics）。
> **它不是什么**：不是「唯一正确写法」。题目只量**行为**（副本语义、签名、文档三节、树形状），
> 实现写法可以不同——例如 `row = dict(payload)` 换成 `copy.copy(payload)`（需要 `import copy`，
> 且不能留成未使用 import）同样满足全部隐藏用例。
> **作者独立性**：`hidden/` 由同一子会话**先写**（PLAN → runner），参考解在其后写；写 `hidden/` 时
> **没有任何参考实现可看**（本题此前不存在 `reference/`）。因此「隐藏用例是照着参考解写的」这条风险
> 在本题不成立；反向风险（参考解照着隐藏用例写）由 `hidden/PLAN.md` 先冻结、且 PLAN 的 38 条判据
> 全部来自 `SPEC.md`/`task-package/` 兜住。

## 1 树与改动

`reference/tree/` = 11 文件基线 + 2 个新建；**8 个冻结文件逐字节不变**。
树组合摘要（算法与 `reset-arm.py` 相同：按相对路径排序的 `<sha256>  <relpath>` 清单文本再 sha256）：
**`12c8430cd37469dd63c4881cb23ee9b82fbf71c949a9bbf622ef191fa12462ee`**（13 文件）。

| 路径 | 动作 | sha256 |
| --- | --- | --- |
| `src/shop/order_repository.py` | 改（只改 `insert` 的实现） | `4d4b685f7ce3bbd729a9004b5f20ce0e77701d1be3d514788272398b4b90f054` |
| `tests/test_order_repository.py` | 改（原两条用例逐字保留 + 追加三条） | `282182422d54c24e8728936482627cbc6a73dfa1322911bc913519da9bd78e60` |
| `README.md` | 改（只加一行到「跑测试」一节） | `1f3cff9914c028ce51ba955a92a409ef3ffd8ba5a82223e3a4a904b2e712d3d6` |
| `tests/test_order_service_copy.py` | 新建 | `a56d98ac1621c627c5b6b641b36362bba385c7b18ab6a93c0eaaac1c06cf6a50` |
| `docs/fix-notes.md` | 新建 | `6c1456b45739179cd3e0960688fbbe670af1d4334c34a66ce274d7096a876509` |

**交叉验证（不是抄来的，是同一份契约的必然结果）**：`src/shop/order_repository.py` 的摘要
`4d4b685f…` 与 `bank-flagship-returns/baseline/src/shop/order_repository.py` **逐字节相同**——
本题基线就是把旗舰题那份正确实现换成了别名版本，参考解把它恢复了回去。这条巧合是
「修复语义被上游同一份接口契约钉死」的旁证，不是参考解从旗舰题复制（写它时只看了本题 SPEC 与
`interfaces.md` §2 的示例）。

## 2 决策点（写完再看，逐条给理由）

| # | 决策 | 理由 |
| --- | --- | --- |
| D1 | `insert` 只改方法体：`row = dict(payload)` → append → `return dict(row)` | `interfaces.md` §2 的「修复后（语义逐字要求）」就是这三行；两个方向各复制一次，才同时挡住「改入参」与「改返回值」 |
| D2 | 不用 `copy.copy` / `copy.deepcopy` | `dict(...)` 是 `interfaces.md` 写明的浅拷贝口径，也不需要新增 import（A10/I4 不必再判「这个 import 是否真的被用到」） |
| D3 | `listing` 一个字不动 | 基线里它已经是 `[dict(row) for row in self._rows]`；`SPEC.md` §3 明确「已经返回副本（不要改坏）」——动了就同时踩隐藏用例与 A1 |
| D4 | 新增三条用例**不改动**原有两条的任何一个字节 | `interfaces.md` §5.1 要求「原样保留（断言逐字不改；可以追加、不可以删除或改写）」；隐藏 `T14/T15` 用 AST 有序前缀判 |
| D5 | 新用例按「改入参 / 改返回值 / 两次 `listing`」三条各写一个函数 | 题面「三类用例」；分成三个函数后失败信息直接指认是哪一类语义坏了，也顺手把 `T16` 的「≥3 个测试函数」满足掉 |
| D6 | `README.md` 的改动**只有一行**（且是逻辑上的一行） | 首消息 §9 与 `interfaces.md` §6 都写「只改『跑测试』一节的一行；结构表、其它章节不动」；隐藏 `T19` 会逐节比对，多改一节就红 |
| D7 | `docs/fix-notes.md` 三个二级标题逐字用 `## 根因` / `## 修法` / `## 验证` | 隐藏 `T18` 逐字比对标题；三节都要有正文（只有标题 = 红） |
| D8 | 「修法」一节里贴三行代码，不贴 diff | 文档是给人读的结论，diff 属于 git；隐藏用例只判标题与正文非空，不判内容形态 |
| D9 | 不在实现里加 `try/except`、不加类型校验、不加断言 | `interfaces.md` §4：不新增异常分支；`I3` 逐条件判 `insert`/`listing` 体内没有 `Try`/`Raise` |
| D10 | 不新建第 14 个文件（例如 `src/shop/copy_util.py`） | 允许写只有 5 条；新建 helper 会同时踩 `I6`（文件集 ⊆ 13）与 `TESTING-001`（新生产文件缺测试） |

## 3 实测读数（2026-10-22，本机 `.venv` = Python 3.13.11；命令见 §4）

| 维度 | 读数 | 说明 |
| --- | --- | --- |
| **T** | **38 / 38**（exit 0） | 两条不同进程的读数**逐字节相同**：stdout sha256 `ed06ff777b9dd0d55f4408fd76f2966bee7b1039578cf91a39c6cefbd550a041` |
| T（基线对照） | **21 / 38**（exit 1） | 基线读数同样逐字节相同：sha256 `c25d9de95de572eeb5031ba212f328a8e5490c85a0aacd1dcdd64129e2903b5c`；即 17 条在基线上红、在参考树上绿 |
| **pytest** | `9 passed`，exit **0**；`--collect-only` = **9**（基线 4） | 在被评树的**副本**里跑，参考树本身仍是 13 文件（无 `__pycache__` / `.pytest_cache` 残留） |
| **A** | **10 / 10**（exit 0） | `workspace_scope.files = 9`、`declared_unmatched = []`、`declared_non_python = [AGENTS.md, README.md, docs/fix-notes.md, pytest.ini]`；A1–A10 全 `pass` |
| **C** | **27 / 27**（`effective_total = 27`） | 3 个被测 `.py` 全部 `decision = allow`、`violations = []`、`skipped_rules = [ARCH-001@1]`（**结构性不适用**，不计分也不计分母） |
| C 计分明细 | 规则段 21/21 + 冻结未改 3/3 + 无旁路 3/3 | 规则段 = 7 条适用规则 × 3（8 条里 ARCH-001 因 `layer != controller` 每次进 `skipped_rules`） |
| 过程读数（只描述，不进分） | `matched_rules = 42`、`complete = true`、`blocking_capable_skipped = 1`（`scope_mismatch`）、`served_checkers = [failing_tests, missing_docstring, missing_tests, style_lint]`、`pending_findings = 0` | **跳过 ≠ 通过**：那 1 条 error 级跳过就是 ARCH-001；C 已把它标 N/A |
| 加权分（按 `scoring.yaml`） | T `round(40 × 38 / 38) = 40` / C `27`（满分 27）/ A `30`（10 × 3） | T 的 total 已冻结为 38（见 `scoring.yaml`） |

**规则集哈希**（3 次运行相同）：`sha256:73845ef515236940266b682631c02dec84c06886fa27a1e99f57e66284fae7d4`。
**结论**：本题的 T/C/A 天花板在参考解上**三维齐备且全满**——T 38/38、C 27/27（N/A 后上限）、A 30/30
（10 条谓词全过）。这不是「任务简单」的证据，而是「判据能被一个合规解法同时满足」的证据；
n=1，不写均值/显著性（`bank/README.md` §5）。

## 4 命令（逐条可复制；cwd = 仓库根）

```powershell
$task = 'docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-bugfix-first-failing-test'

# T：隐藏验收（只读被评树；两次运行应逐字节相同）
$env:BANK_TASK_TREE = "$task/reference/tree"
.venv/Scripts/python.exe "$task/hidden/runner.py"
# 退出码 0 = 全过 / 1 = 有失败 / 2 = 跑不成

# pytest：在副本里跑，别在有 .py 的参考树里跑（否则留下 __pycache__）
Copy-Item -Recurse -Force "$task/reference/tree" .tmp/reference-check
Push-Location .tmp/reference-check; python -m pytest -q; Pop-Location

# A：结构谓词（10 条）
.venv/Scripts/python.exe tools/structure_metrics.py --workspace "$task/reference/tree" `
  --layers "$task/layers.yaml" --interfaces "$task/interfaces.yaml" --json

# C：逐文件判定（3 个被测 .py；--changed 是 append，5 条允许写各写一次）
$env:PYTHONPATH = 'src'
$changed = @('README.md','docs/fix-notes.md','src/shop/order_repository.py',
             'tests/test_order_repository.py','tests/test_order_service_copy.py')
.venv/Scripts/python.exe -m policy.check src/shop/order_repository.py `
  --workspace "$task/reference/tree" --config-root . --layer repository --operation edit `
  --changed $changed[0] --changed $changed[1] --changed $changed[2] --changed $changed[3] `
  --changed $changed[4] --request-id bank-bugfix-reference-order_repository --json
# 另两个文件把 <file>/--layer 换成 tests/test_order_repository.py|test 与
# tests/test_order_service_copy.py|test；--request-id 每次不同（固定值是为了两次读数可比）
```

## 5 与 SPEC / 候选清单的偏差（逐条写明选哪边）

| # | 事项 | 本参考解 / 本隐藏实现的选择 | 理由 |
| --- | --- | --- | --- |
| 1 | `SPEC.md` §5 建议隐藏条数 32；`scoring.yaml.planned_min_total = 30` | **38 条**（T19 + EN6 + I13） | 派单给的范围是 34–40；分组按旗舰同形的 T/EN/I（`coverage.md` §6 的 `BASE/T/N` 映射见 `hidden/PLAN.md` §5） |
| 2 | `coverage.md` T12 写「assert 总数 ≥ 5（原 3 + 新 ≥3）」 | **≥ 6** | 3 + 3 = 6，原文算术自相矛盾；`interfaces.md` §5.1 与 `acceptance.md` A4 都写「至少 3 条新断言」，≥6 才是它的合取 |
| 3 | `SPEC.md` §3「README 改一行」 | 参考解真的只加一行（`1f3cff99…`） | 隐藏 `T19` 会逐节比对：除「跑测试」之外的基线章节必须逐字不变 |
| 4 | 本题 `README.md` §5 说「T 现在是待定」 | 本轮把 T 冻结为 **38** 并实测 38/38 | 隐藏代码 + 参考解已落盘，`scoring.yaml` 的 `status` / `total` / `case_ids` / 两个 hidden 摘要同批冻结 |
| 5 | `SPEC.md` §2 说起点「2 failed, 2 passed」 | 隐藏 `EN5` **在 runner 内嵌的基线树上**实测复现这条读数 | 运行时不读包内 `baseline/`（README 视为可能被移走）；内嵌 10 个基线文件源码，其中 9 个用于重建基线树 |
| 6 | `SPEC.md` §4 的 7 条直接可触发规则 | 参考解让其中 **0 条**在最终树上命中（`decision = allow`） | 那 7 条是「省事写法会命中」的岔口，不是「必须命中」；参考解走的是正确路径，C 读数应为满 |
| 7 | `scoring.yaml.dimension_t.case_groups` 原写 `BASE/T/N` | 本轮按实际的 **T/EN/I** 改（键集合不变，只改取值） | 冻结记录必须与实际 id 集合一致；id 前缀对不上会让「case_ids 与 runner 实际 id 相等」这条自相矛盾 |

## 6 参考解**不**声称的事

- **不声称「一次改对」是唯一解**：`SPEC.md` §7 的死锁读数（半修 → `TESTING-002@1 error` → `block`）是**过程**读数，
  参考解只证明「完整修复后 T/C/A 三维全满」；中间步被不被拦由 `policy.check` 的 `failing_tests` 决定，不在 T 里。
- **不声称 `allow` 等于「架构没问题」**：`ARCH-001` 在 3 个被测文件上每次都因 `layer != controller` 进 `skipped_rules`；
  C 的 3 分已标 `not_applicable`，跳过 ≠ 通过。
- **不声称覆盖 43 条规则**：本题的直接面是 7 条（`coverage.md` §2），其余 24 条只是「留作变异」、12 条结构性不适用。
