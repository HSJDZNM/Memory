# bank-docs-config（文档 / 配置为主：配置键 retry 到 retry_policy 的迁移 · 冻结候选）

> **它是什么**：任务题库里的第 6 题——把订单示例项目的应用配置从 v1 迁到 v2（标量 `retry` 改成结构化
> `retry_policy`），补一个**严格只读**的加载器与一个**只读校验脚本**，并把 `docs/config.md`、新建的
> 迁移说明与 `README.md` 的配置一节同步到 v2。改动面以 `.md` / `.yaml` 为主，Python 只有两个文件。
> **冻结状态**：基线 + task-package + C/A 判据 + **hidden（T 已冻结）+ reference + 天花板已完成**
> （§7 与 §7.1 的实测读数）。T = **39 条**（`hidden/PLAN.md`），`scoring.yaml` 的 `case_ids` 与
> runner 的 `CASE_IDS` 逐个相等。**由 Lead 于 2026-10-22 签字**（`frozen_by = Lead`）；“可开跑”仍由使用者另签。
> **用法**：Lead 重置基线 → 以任务树为 cwd 起受治会话 → 首消息 = `task-package/first-message.md`；
> 跑完后按 `acceptance.md` + 隐藏验收 + 基线 diff 判分（C/A 见 `scoring.yaml`、`coverage.md`）。

## 1 基线（14 文件；除允许写集合里的 4 个外只读）

| 组 | 文件 | 来源 |
| --- | --- | --- |
| 订单示例项目（11） | `AGENTS.md`、`README.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_repository.py`、`src/shop/order_service.py`、`src/shop/order_controller.py`、`tests/test_order_repository.py`、`tests/test_order_service.py`、`tests/test_order_controller.py` | `bank-flagship-returns/baseline` 的同名 11 文件，**逐字节复制**（复制时逐文件 sha256 断言相同；也与 `examples/dsh/b-plan/sample-project` 逐字节相同） |
| 配置（1） | `config/app.yaml` | 本包构造：v1 口径（`app_name` / `retry: 3` / `feature_flags` 两项） |
| 文档（1） | `docs/config.md` | 本包构造：v1 的配置表（键 / 类型 / 默认值 / 说明） |
| 测试（1） | `tests/test_check_config.py` | 本包构造：**静态契约测试**（`tools/check_config.py` 不存在时 skip，存在时检查公开面）；M5 改写为行为测试（改写后不再 skip） |

- **基线组合摘要**（算法 = 按相对路径排序的 `<sha256>  <relpath>` 清单文本再 sha256，与 `reset-arm.py` 的
  `_manifest_sha256` 逐字相同）：**`dd0e563ec8c6473472f5d1705964908c4e2a61a69e31cd8b30b0e2d3b2176773`**（14 文件）。
- 基线起点干净：`python -m pytest -q` 得到 **3 passed, 1 skipped**（exit 0；skip 的那条就是静态契约测试，
  它等 `tools/check_config.py` 出现在 M1；本包实测，见 §4）。
- **基线里没有**（任务要创建，预置 = 撤掉任务）：`docs/config-migration.md`、`src/shop/config.py`、
  `tests/test_config.py`、`tools/check_config.py`。
  `reset-arm.py` 的 `TASK_CREATED` 会拒绝这 4 个文件出现在基线里。
- **`tests/test_check_config.py` 在基线里**（第 14 个文件，静态契约测试）：M1 写 `tools/check_config.py`
  时它就是「同名测试」，M5 把它改写成行为测试。它**在**允许写集合里（允许写与基线的交集因此是 4 个），
  最终树仍是 18 文件、逐字节与 `reference/tree` 相同。
- 基线**没有** `tools/__init__.py`（旗舰 baseline 的 `tools/__init__.py` / `config/refund_policy.yaml` /
  `data/refunds-legacy.jsonl` 属于退货题，不进本题基线）：`python tools/check_config.py` 作为脚本可跑，
  测试 import `tools.check_config` 走 Python 的 namespace package（见 `scoring.yaml` 的 `a9_note`）。

## 2 允许写 8 路径

`task-package/allowed-writes.txt`（字母序，8 行）：
`README.md`、`config/app.yaml`、`docs/config-migration.md`、`docs/config.md`、`src/shop/config.py`、
`tests/test_check_config.py`、`tests/test_config.py`、`tools/check_config.py`。

**允许写交集基线 = 4 个**（`README.md`、`config/app.yaml`、`docs/config.md`、`tests/test_check_config.py`）；
因此**冻结不动的基线文件 = 10 个**：
`AGENTS.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_controller.py`、
`src/shop/order_repository.py`、`src/shop/order_service.py`、`tests/test_order_controller.py`、
`tests/test_order_repository.py`、`tests/test_order_service.py`。这 10 个一个字节都不许改。

## 3 冻结哈希（脚本实算，不是手抄）

| 路径 | sha256 |
| --- | --- |
| `task-package/first-message.md` | `8c303fad01dbb72f602dd37d119423c928548190ce8466314485de27c807ea41` |
| `task-package/milestones.md` | `d1002ea4d8151d89b31c0d8e766bbfc72212f8a3cdcb186a7236b0a33ef05050` |
| `task-package/acceptance.md` | `d5573283010d77794476f942a04cb6581daff0a42ba481e298e42fa63995fb42` |
| `task-package/interfaces.md` | `6e3a42f781e2a52b9cd0aad0b75fb74fe45cf0bf78517e1bdd85e4d43932638c` |
| `task-package/allowed-writes.txt` | `9290bab8427455963eb135fce2bd3474d78be52084f9d3bb1b3a3babc0fcbb7b` |
| `task-package/manifest.sha256` | `7c1d3ebca6e0fcf4080340516500833ebcebb041da7c4dcaa31e81b3d7ed6031`（5 行，覆盖前 5 文件；与组合摘要同值——清单文本就是被哈希的字节） |
| `reset-arm.py` | `df79bcd013f98ec64075bbb1c3732ec48c9bc49150ef83f6e2e497861810ec29`（不在 manifest 里；它只冻结基线） |
| `layers.yaml` | `62ae060026cb4e164d1233cf7b8280ebeb8ad1c107e2fbf509f067f63befbe56` |
| `interfaces.yaml` | `91c3ce85e337d0fbfabb6d318519c41b487beab52f7a641fd59d131c17b981a2` |
| `scoring.yaml` | 不进 manifest（自指不写进自己，见其 `scoring_sha256_note`）：本批内容改过，现值由冻结集现场实算，本表不抄一个会失效的数 |
| `hidden/PLAN.md` | `769030ca259d4eafd90c2241dbc8b61964a0b46679194fb1e1eb0817e3e6a5cb`（39 条；T 冻结输入） |
| `hidden/runner.py` | `b7ec0e64744ed1f3abe5195c8db1c00eba2ca264b780a1b2b73532363901945f`（T 冻结输入） |
| `baseline/tests/test_check_config.py` | `74195daf2acc69e66de423a664e1239b8c66d5a5f06a40685c4867eed3277d69`（基线第 14 个文件；M5 改写为行为测试） |
| `baseline/`（14 文件组合摘要） | `dd0e563ec8c6473472f5d1705964908c4e2a61a69e31cd8b30b0e2d3b2176773`（`reset-arm.py` / `hidden/runner.py` / `scoring.yaml` 三处同值） |
| `coverage.md` | 不进 manifest（覆盖表不是判据输入）；改动它不改判分 |

复核（Lead 开跑前逐行比对，5/5 必须 ok；任一不符 => 该 run 作废）：

```powershell
$pkg = 'docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-docs-config/task-package'
Get-Content "$pkg/manifest.sha256" | ForEach-Object {
  $h, $name = $_ -split '  ', 2
  $actual = (Get-FileHash -Algorithm SHA256 (Join-Path $pkg $name)).Hash.ToLower()
  "{0}  {1}" -f ($(if ($actual -eq $h) { 'ok' } else { 'BAD' })), $name
}
```

（本包已用等价脚本复核：5/5 ok，见 §4。）

## 4 怎么用（Lead）

```powershell
cd <仓库根>
# 0) 看计划 / 重置（目标树默认 .tmp/bank-docs-config/tree，14 文件；不预置任何任务要创建的文件）
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-docs-config/reset-arm.py --dry-run
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-docs-config/reset-arm.py
#    退出码：0 = 重置并校验通过；1 = 前置缺失（基线缺失/文件数不对/摘要不符/基线混入任务文件）；2 = 校验失败

# 1) 记下 audit 起始行数（reset-arm 写进 .tmp/bank-docs-config/reset-manifest.json）

# 2) 装配受治配置（不在本包范围）：目标树 .policy 要有 approval.json、tool-registry.yaml /
#    tool-registry.approved.json、dsh-adapter.yaml、hooks.json、patch.yml；按**这棵树**审核 / 签发。
#    命令族见 bank/COMMAND-FAMILIES.md §6（tests / scripts / readonly 三族）。
#    用 bank/harness/scaffold_arms.py 建臂时，首消息须显式传 --first-message（它的默认探测只认
#    task-package/first-message.txt，本题按要求用 .md）；它调 reset-arm.py --target 并读 RESET-ARM-JSON。

# 3) 以任务树根为 cwd 起受治会话；首消息 sha256 必须等于 8c303fad...
```

**本题的命令族**（`exec.pwsh`，逐字形态见 `bank/COMMAND-FAMILIES.md` §6）：
`python -m pytest -q`（tests）、`python tools/check_config.py --config config/app.yaml`（scripts）、
`git diff --stat` / `git status --porcelain`（readonly）。**不需要** `python -m policy.check`（判定自动做）。

**本包实测过的命令**（读数照抄）：

| 命令 | 结果 |
| --- | --- |
| 在 14 文件基线副本里 `python -m pytest -q` | `3 passed, 1 skipped`，exit 0（skip = 静态契约测试） |
| `reset-arm.py --dry-run` | exit 0；打印 14 条期望文件、`baseline manifest sha256: dd0e563e...`、目标树 `.policy` absent |
| `reset-arm.py`（默认目标） | exit 0；`14/14 sha256 verified`；`RESET-ARM-JSON` 可解析（`status: ok`、`mismatches: []`）；写出 `.tmp/bank-docs-config/reset-manifest.json` |
| `policy.check src/shop/order_controller.py ... --layer controller`（基线树） | `allow`，exit 0；`matched_rules` 43、`skipped_rules` 0、5 个 checker 全 served |
| `structure_metrics.py --layers ... --interfaces ...`（基线树） | 10/10 pass，exit 0；`layers.entries=18`、`interfaces.entries=6` |

## 5 本题的读法（不是「跑完就算」）

- **四个维度分开读**：T（任务完成；**已冻结 39 条**，读数见 §7.1）、C（规则遵守；`scoring.yaml` 的 `dimension_c`）、
  A（结构；`layers.yaml` / `interfaces.yaml` + `tools/structure_metrics.py`）、过程（平台账本）。
  **不许把过程读数折算进 T/C/A**。
- **`allow_with_warnings` 不是失败、也不是通过**：DOC-001 / STYLE-001 / STYLE-018 命中时 decision 是它，
  exit 1 只表示「不是 ALLOW」，阻断判定只读 `violations`。
- **跳过 ≠ 通过**：每次 `policy.check` 的 `skipped_rules` 与 `check_volume.blocking_capable_skipped` 必须一起读。
  本题 4 个被测 `.py` 上 ARCH-001 会因 `scope_mismatch` 进 `skipped_rules`（`blocking_capable_skipped=1`）；
  `scoring.yaml` 已把它的 3 分标 `not_applicable`（不计分也不计分母），**C 上限 27**（`effective_total`），
  读 C 必须带 `effective_total`。
- **文档类目标的读数是「没查」不是「通过」**：对 `.md` 走验证器路径得到
  `language_coverage.status = not_covered_by_design`、`served_checkers = []`、`effective_rule_count = 0`
  （decision 写 `allow`）。所以 `docs/config.md` / `docs/config-migration.md` 的正确性**只能**靠隐藏验收与
  A6–A8 的结构判据（本包实测，见 `coverage.md` §7.9）。
- **n=1 只作案例读数**：不写均值 / 提升 / 显著；要写「值得扩试」需每臂 k>=3（`bank/README.md` §5）。

## 6 直接可触发规则点（8 条；另 1 条 STYLE-004 是实测负例，见下）

| rule_id | checker | severity | 触发步骤 | 期望 decision | 证据等级 |
| --- | --- | --- | --- | --- | --- |
| SEC-006 | style_lint | error | M3 的加载器用 `yaml.load(handle, Loader=yaml.Loader)` 代替 `yaml.safe_load` | `block`（`SEC-006@1 error`） | 实测 |
| TESTING-001 | missing_tests | error | M3 新建 `src/shop/config.py` 却不写 `tests/test_config.py`（`tools/check_config.py` 在 M1 由基线的同名静态契约测试兜底） | `block`（`TESTING-001@1 error`） | 实测 |
| TESTING-002 | failing_tests | error | M2 / M3 / M5 的实现与测试不一致，相关测试红（M1 的 A 臂是「选不到测试」→ 无证据，同样以 `TESTING-002` 阻断） | `block`（`TESTING-002@1 error`） | 规则数据（dgate2 同套规则实测过） |
| DOC-001 | missing_docstring | warning | 加载器 / 脚本漏模块或函数 docstring | `allow_with_warnings` | 实测 |
| STYLE-001 | style_lint | warning | 迁移说明或错误消息一行 > 100 列 | `allow_with_warnings` | 实测 |
| STYLE-002 | style_lint | error | 改完留下未使用 import | `block`（`STYLE-002@1 error`） | 实测 |
| STYLE-010 | style_lint | error | 加载器用裸 `except:` 吞异常 | `block`（`STYLE-010@1 error`） | 实测 |
| STYLE-018 | style_lint | warning | import 分组乱序（`import yaml` 排在 `from pathlib` 前） | `allow_with_warnings` | 实测 |

**STYLE-004 已按实测改成 ○（留作变异）**：本题自然写法是裸 `sys.path.insert(...)` 后 import，ruff 0.14.13
不报 E402（§7.7 实测）；同一配置下先写模块级赋值（如 `ROOT = ...`）再 insert+import 才报（e402b 对照）。
三处已同批统一：`bank/README.md` §2 该格改 ○ 并加脚注、SPEC §4 移到「其余」、本文与 `coverage.md` 记
「实测（负例）」。题面仍要求 `# noqa: E402`：那是代码约定，不是判据，隐藏用例不应断言它。
逐条判据、○ / — 的 23 + 12 条与理由、实测命令与读数见 `coverage.md`。

## 7 本包目录地图与完成度

| 路径 | 是什么 | 状态 |
| --- | --- | --- |
| `task-package/`（6 文件） | 首消息 / 里程碑 / 验收表（A1–A10）/ 接口契约 / 允许写 / manifest | **已落盘**：5/5 哈希复核通过 |
| `baseline/`（14 文件） | 逐字节基线树（11 个来自旗舰 baseline + 3 个构造：`config/app.yaml`、`docs/config.md`、`tests/test_check_config.py`） | **已落盘**：组合摘要可复核 |
| `reset-arm.py` | 逐字节重置 + 摘要校验 + `RESET-ARM-JSON` + `reset-manifest.json` | **已实测**：dry-run + 真跑 14/14 |
| `layers.yaml` / `interfaces.yaml` | A 维度声明（18 文件 → 层；6 个非测试模块的公开面上限） | **已落盘**：基线树实测 10/10 pass |
| `scoring.yaml` | T/C/A 三维判据（T **已冻结**：`frozen`、`total: 39`、39 个 `case_ids`、两个 hidden 摘要实算） | C/A 已写并可复核；T 与 runner 同批冻结 |
| `coverage.md` | 43 条规则点 + A1–A10 + 隐藏面的逐项覆盖矩阵与实测读数 | 已写（8 直接 / 23 变异 / 12 不适用；`STYLE-004` 记实测负例） |
| `hidden/` | 隐藏验收 PLAN + runner（`T01–T26` + `EN1–EN7` + `I1–I6`，39 条） | **已落盘**：基线 **2/39**、参考树 **39/39**；两次输出逐字节相同 |
| `reference/` | 参考解（18 文件实现树 + README：决策点 / 读数 / 命令 / 与 SPEC 的偏差） | **已落盘**（不参与判分；树组合摘要 `69b6fda3…`） |
| 天花板 | 参考解上的 T/C/A 实测（`total` 的可达性与 A3 上限校准） | **已实测**：T 39/39 · C 27/27（effective_total）· A 10/10 |

**完成度一句话**：基线、task-package、reset-arm、layers/interfaces、C/A 判据、覆盖表**已落盘并实测可复核**；
隐藏验收（39 条）与参考解**已落盘**，T/C/A 天花板**已实测**（§7.1），T 的 `total` / `case_ids` **已冻结**；
剩下的只有 Lead 签字与真机 A/B 冒烟（不在本包范围）。

### 7.1 本批实测读数（给 Lead 与读数者；命令见 `reference/README.md` §4）

| 维度 | 读数 | 一次读数是什么 |
| --- | --- | --- |
| T（隐藏验收） | 基线 **2 / 39**；参考树 **39 / 39**（exit 0） | `BANK_TASK_TREE=<tree> python hidden/runner.py`；同一 cwd + 同一棵树两次 stdout 逐字节相同：参考树 `sha256 6b55369d9b51ec8c93ebf9bb1bd73252f6b1ff7f7778b8a6d989fa990aa599d4`、基线 `sha256 c4ab7fb77a6f0b8fde1b17af5a6b53c0becd0fc56f05ba78b9f69eb48fba620f`（基线树 = `<本包>/baseline`；本批读数在 `DSH_PYTEST_MODE_SHIM=1` 下取得，见下注） |
| pytest | **18 passed**，exit 0；`--collect-only -q` = **18 collected** | 在参考树**副本**里跑 `python -m pytest -q`（树本身一个字节都不写） |
| C（规则遵守） | 4/4 文件 `allow`，**0 条 violations**；`effective_total = 27` → **27 / 27** | 逐文件 `policy.check`（`--changed` 8 条全量、固定 `--request-id`、`--layer` 取 `layers.yaml`）：4 个文件都 `matched_rules` 42、`skipped_rules=[ARCH-001@1]`（`layer != controller`）、`served_checkers=[failing_tests, missing_docstring, missing_tests, style_lint]`、`check_volume.complete=true`、`blocking_capable_skipped=1` |
| A（结构） | **10 / 10 pass**，exit 0 | `structure_metrics.py --workspace <reference-tree> --layers layers.yaml --interfaces interfaces.yaml --json`；`workspace_scope`：12 个 .py、`undeclared=[]`、`declared_unmatched=[]`、`unresolved=0` |

- **C 的逐文件 decision**：`src/shop/config.py`（model）、`tests/test_check_config.py`（test）、
  `tests/test_config.py`（test）、`tools/check_config.py`（composition）全部 `allow` / exit 0；
  ARCH-001 在这 4 个文件上都是 `scope_mismatch` 跳过（**跳过不是通过**），按 `not_applicable` 不计分也不进分母。
- **基线读数不是 0/39 也不是「跑不成」**：`T26`（10 个冻结文件逐字节）与 `EN1`（基线 3 条测试本来就绿，
  静态契约测试此时 skip、不影响 EN1 的「无失败」判定）在基线上成立；其余 37 条按「缺件 / v1 配置 / 缺文档」红。
  **基线红是构造带来的**，不是 runner 失败。
- **stdout 摘要怎么读**：这两个 `sha256` 是 runner 写到 stdout 的字节摘要（UTF-8；Windows 上 `sys.stdout` 把 `\n` 转成 `\r\n`）。PowerShell 5.1 的 `>` 会把输出重新编码成 UTF-16，直接哈希那个文件得不到本值——要复现得用程序捕获原始字节。
- **测量环境注（2026-10-22 H1 重测）**：本机 Python 3.13.11 / Windows 的 `os.mkdir(mode=0o700)` 会生成当前令牌不可读的显式 ACL，pytest 的 `tmp_path` 报 WinError 5；不加处理时 docs 参考树是 **38/39（仅 EN1 红）**，不是判据变化。上表的 T 读数在 `DSH_PYTEST_MODE_SHIM=1`（只把 0700 映射为 0750，不改判据、不改树）下取得；环境限制另记在 `readings/` 的 k3 读数里。
- **文档类目标仍不在规则证据面里**：`.md` / `.yaml` 走验证器路径得到
  `language_coverage.status = not_covered_by_design`、`served_checkers = []`；文档正确性由隐藏 T20–T24 判，
  **不许**把那条 allow 读成「规则查过」。

### 7.2 隐藏用例的「能不能红」（5 处显式变异，参考树副本上做）

参考树副本（`.tmp/bank-docs-config-author/mut-*/tree`）上逐处做一处缺陷、跑一遍 runner，读失败的 id：
**变异不是判分，只证「断言不是空的」**（守 AGENTS 第 45 条：自己的仪器也要能失败）。

| 变异 | 失败的隐藏用例 | 说明 |
| --- | --- | --- |
| 加载器把 `yaml.safe_load(text)` 换成 `yaml.load(text, Loader=yaml.Loader)` | `T18` | 不安全加载器只由 AST 断言（T01–T17 行为面照旧通过） |
| 去掉 `isinstance(value, bool)` 的判断（bool 冒充 int） | `T11`、`T12`、`T17`、`EN1` | `max_attempts: true` / `jitter: 1` 被接受；参考解自己的测试也红 |
| 把 `app_name` 的错误消息从 `path.name` 改成 `str(path)` | `T17` | 只泄漏一条消息也会红（7 类失败逐条检查）——这条变异最初**没被抓到**，因此把 T17 从 4 类扩到 7 类 |
| 把 `README.md` 的 `## 配置` 标题改名 | `T23`、`T24` | 标题序列与「其余小节逐字节」两条判据都响 |
| 删掉 `tests/test_config.py` | `T25`、`EN2`、`I5` | 文件集合、收集数、测试形态同时响 |

## 8 构造决定与与 SPEC 的偏差（读之前先看）

1. **基线的 11 文件口径**：SPEC §2 说「`bank-flagship-returns/baseline` 的 11 个文件」。旗舰 baseline 是 14 个文件，
   其中「订单示例项目 11」= 本题取的 11 个（含 `AGENTS.md` / `README.md`）；另外 3 个
   （`tools/__init__.py`、`config/refund_policy.yaml`、`data/refunds-legacy.jsonl`）是退货题的输入，**未取**。
   这 11 个与旗舰 baseline 逐字节相同（复制时逐文件 sha256 断言，并与 `examples/dsh/b-plan/sample-project` 比对一致）。
2. **README 的「配置一节」是新增，不是改既有一节**：`README.md` 必须与示例项目逐字节相同（第 1 条），
   而示例项目的 README 没有配置节。所以题面写成「在 `## 跑测试` 之后、`## 这份项目为什么长这样` 之前**新增**
   `## 配置` 一节」，A8 按这个判。**与 SPEC §3 的措辞（「改 README.md 的配置一节链接」）不同**，理由是不许改基线字节。
3. **STYLE-004 是实测负例**（§6）：原 SPEC §4 与 `bank/README.md` §2 都把它列为可直接触发；本轮收口按实测
   统一成 **○（留作变异）+「实测负例」**——裸 `sys.path.insert(...)` 后 import 在 ruff 0.14.13 上不报 E402，
   只有先写模块级赋值（如 `ROOT = ...`）再 insert+import 才报（§7.7 与 e402b 对照）。
4. **`interfaces.yaml` 的 `order_repository` 上限取 4**（基线实际 3 个公开定义 + 1 余量），旗舰题那份是 5
   （那个任务的参考解要给 `get` 留位置，本题不改它）。
5. **`config/app.yaml` 迁完的取值是冻结的**（`max_attempts: 3`、`backoff_ms: 100`、`jitter: true`）：
   SPEC 只给了键名，取值由本包钉死，否则 A3 / A6 与隐藏用例没有唯一答案。
6. **`docs/config.md` 的表头与类型列是逐字判据**（A6）：这样「文档与加载器一致」才是机器可判的；
   比较口径是「去掉首尾空白与反引号后逐字相等」，写在 `acceptance.md` 的补充口径里。
7. **基线的第 14 个文件是静态契约测试**（`tests/test_check_config.py`）：它不是判据的替代品，而是为了让 M1
   （写 `tools/check_config.py`）在 T3 下出现设计方向激活——A 臂（`tools` 非生产文件）选不到测试、
   以 `TESTING-002` 阻断（selection level `none`），B 臂（`tools` 是生产文件）选到这份基线测试并跑通（allow）。
   静态测试在工具文件不存在时 skip（基线 pytest = 3 passed, 1 skipped）；M5 把它改写为行为测试，
   因此最终树仍是 18 文件、与 `reference/tree` 逐字节相同。
8. **`total` / `case_ids` 先空后冻**：隐藏代码落盘之前不伪造已冻结的 T（`pending_hidden`）；本批
   由独立出题子会话写 `hidden/PLAN.md` + `hidden/runner.py`（39 条）后**同批**冻结为
   `frozen / total: 39 / 39 个 case_ids`，两个 hidden 摘要由实算写入（见 §3 与 §7.1），
   `frozen_by` = `Lead`（2026-10-22；只冻结 T/C/A 判据，**不签“可开跑”**）。

## 9 边界（引用本包前必须读）

- **本包是任务数据，不是平台规则**：它只描述「要模型做什么、允许写什么、怎么判」，不改任何判定逻辑。
- **隐藏验收必须独立出题**：写隐藏代码的子会话不得读本包的任何实施 diff（dgate2 的 H1 同一口径）。
- **改它 = 改构造**：任何改动（哪怕一个字节）都要按 `bank/README.md` §4 记录理由与回退，并重新生成
  `task-package/manifest.sha256` / 基线摘要 / 本文件 §3 的哈希表与 `scoring.yaml` 的 `frozen_inputs`；
  冻结后逐文件哈希不符 => 该 run 作废。
- **临时文件只在 `.tmp/bank-docs-config/`**：本包的实测都在那里（`tree/` 是重置目标、`probe/` 是变异副本、
  `pc-*.json` 是判定载荷、`reset-manifest.json` 是重置清单）；它们都是构建产物，不提交。
- **不跑真机会话、不 commit / push**：本包落地时只做了只读 / 本地验证（pytest、policy.check、structure_metrics、
  reset-arm、哈希复核、文本规范）。
