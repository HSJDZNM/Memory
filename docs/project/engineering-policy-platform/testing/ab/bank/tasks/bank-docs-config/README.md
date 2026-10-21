# bank-docs-config（文档 / 配置为主：配置键 retry 到 retry_policy 的迁移 · 冻结候选）

> **它是什么**：任务题库里的第 6 题——把订单示例项目的应用配置从 v1 迁到 v2（标量 `retry` 改成结构化
> `retry_policy`），补一个**严格只读**的加载器与一个**只读校验脚本**，并把 `docs/config.md`、新建的
> 迁移说明与 `README.md` 的配置一节同步到 v2。改动面以 `.md` / `.yaml` 为主，Python 只有两个文件。
> **冻结状态**：**基线 + task-package + C/A 判据已落盘可复核**；T 维度**未冻结**（`hidden/` 未落盘）、
> 参考解与天花板**未做**（§7）。**未经 Lead 签字**。
> **用法**：Lead 重置基线 → 以任务树为 cwd 起受治会话 → 首消息 = `task-package/first-message.md`；
> 跑完后按 `acceptance.md` + 隐藏验收 + 基线 diff 判分（C/A 见 `scoring.yaml`、`coverage.md`）。

## 1 基线（13 文件；除允许写集合里的 3 个外只读）

| 组 | 文件 | 来源 |
| --- | --- | --- |
| 订单示例项目（11） | `AGENTS.md`、`README.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_repository.py`、`src/shop/order_service.py`、`src/shop/order_controller.py`、`tests/test_order_repository.py`、`tests/test_order_service.py`、`tests/test_order_controller.py` | `bank-flagship-returns/baseline` 的同名 11 文件，**逐字节复制**（复制时逐文件 sha256 断言相同；也与 `examples/dsh/b-plan/sample-project` 逐字节相同） |
| 配置（1） | `config/app.yaml` | 本包构造：v1 口径（`app_name` / `retry: 3` / `feature_flags` 两项） |
| 文档（1） | `docs/config.md` | 本包构造：v1 的配置表（键 / 类型 / 默认值 / 说明） |

- **基线组合摘要**（算法 = 按相对路径排序的 `<sha256>  <relpath>` 清单文本再 sha256，与 `reset-arm.py` 的
  `_manifest_sha256` 逐字相同）：**`e259e2440044781413cb1d04bd0a4c4926898be7372126a66f79b5316d2eb8de`**（13 文件）。
- 基线起点干净：`python -m pytest -q` 得到 **3 passed**（exit 0；本包实测，见 §4）。
- **基线里没有**（任务要创建，预置 = 撤掉任务）：`docs/config-migration.md`、`src/shop/config.py`、
  `tests/test_check_config.py`、`tests/test_config.py`、`tools/check_config.py`。
  `reset-arm.py` 的 `TASK_CREATED` 会拒绝这 5 个文件出现在基线里。
- 基线**没有** `tools/__init__.py`（旗舰 baseline 的 `tools/__init__.py` / `config/refund_policy.yaml` /
  `data/refunds-legacy.jsonl` 属于退货题，不进本题基线）：`python tools/check_config.py` 作为脚本可跑，
  测试 import `tools.check_config` 走 Python 的 namespace package（见 `scoring.yaml` 的 `a9_note`）。

## 2 允许写 8 路径

`task-package/allowed-writes.txt`（字母序，8 行）：
`README.md`、`config/app.yaml`、`docs/config-migration.md`、`docs/config.md`、`src/shop/config.py`、
`tests/test_check_config.py`、`tests/test_config.py`、`tools/check_config.py`。

**允许写交集基线 = 3 个**（`README.md`、`config/app.yaml`、`docs/config.md`）；因此**冻结不动的基线文件 = 10 个**：
`AGENTS.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_controller.py`、
`src/shop/order_repository.py`、`src/shop/order_service.py`、`tests/test_order_controller.py`、
`tests/test_order_repository.py`、`tests/test_order_service.py`。这 10 个一个字节都不许改。

## 3 冻结哈希（脚本实算，不是手抄）

| 路径 | sha256 |
| --- | --- |
| `task-package/first-message.md` | `dd47ec6b7c6fc1ad8b4fb9e90ae794cbc0bd02e478d016efb060f95a0b4f53b5` |
| `task-package/milestones.md` | `55b8949e16f7e659b49f20494ebcc9639aba13eac02bb4d3c28b5eeadfdd6126` |
| `task-package/acceptance.md` | `a4df181e413cc0e6644dd0aca8bb3c2e1de1bae405a9c58a18571224e77730cc` |
| `task-package/interfaces.md` | `6e3a42f781e2a52b9cd0aad0b75fb74fe45cf0bf78517e1bdd85e4d43932638c` |
| `task-package/allowed-writes.txt` | `9290bab8427455963eb135fce2bd3474d78be52084f9d3bb1b3a3babc0fcbb7b` |
| `task-package/manifest.sha256` | `51a68b23791acb0c87e482fe435cad12fd77434163f49d9348ce114ac14bb772`（5 行，覆盖前 5 文件；与组合摘要同值——清单文本就是被哈希的字节） |
| `reset-arm.py` | `768638aca01f72e07b686b23229d44be96fa77b0343894d12ffe8229e764e76e`（不在 manifest 里；它只冻结基线） |
| `layers.yaml` | `d3a40a7578a4d8a5591c0dc95cabe4a302d60e8d2f47b4daf32a05813b206814` |
| `interfaces.yaml` | `91c3ce85e337d0fbfabb6d318519c41b487beab52f7a641fd59d131c17b981a2` |
| `scoring.yaml` | `34ae4b10d86baaeb49f15c4090189d8177372d4ccb5ab8e7611cb46b96fd4a0c`（自指不写进自己，见其 `scoring_sha256_note`） |
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
# 0) 看计划 / 重置（目标树默认 .tmp/bank-docs-config/tree，13 文件；不预置任何任务要创建的文件）
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-docs-config/reset-arm.py --dry-run
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-docs-config/reset-arm.py
#    退出码：0 = 重置并校验通过；1 = 前置缺失（基线缺失/文件数不对/摘要不符/基线混入任务文件）；2 = 校验失败

# 1) 记下 audit 起始行数（reset-arm 写进 .tmp/bank-docs-config/reset-manifest.json）

# 2) 装配受治配置（不在本包范围）：目标树 .policy 要有 approval.json、tool-registry.yaml /
#    tool-registry.approved.json、dsh-adapter.yaml、hooks.json、patch.yml；按**这棵树**审核 / 签发。
#    命令族见 bank/COMMAND-FAMILIES.md §6（tests / scripts / readonly 三族）。
#    用 bank/harness/scaffold_arms.py 建臂时，首消息须显式传 --first-message（它的默认探测只认
#    task-package/first-message.txt，本题按要求用 .md）；它调 reset-arm.py --target 并读 RESET-ARM-JSON。

# 3) 以任务树根为 cwd 起受治会话；首消息 sha256 必须等于 dd47ec6b...
```

**本题的命令族**（`exec.pwsh`，逐字形态见 `bank/COMMAND-FAMILIES.md` §6）：
`python -m pytest -q`（tests）、`python tools/check_config.py --config config/app.yaml`（scripts）、
`git diff --stat` / `git status --porcelain`（readonly）。**不需要** `python -m policy.check`（判定自动做）。

**本包实测过的命令**（读数照抄）：

| 命令 | 结果 |
| --- | --- |
| 在 13 文件基线副本里 `python -m pytest -q` | `3 passed`，exit 0 |
| `reset-arm.py --dry-run` | exit 0；打印 13 条期望文件、`baseline manifest sha256: e259e244...`、目标树 `.policy` absent |
| `reset-arm.py`（默认目标） | exit 0；`13/13 sha256 verified`；`RESET-ARM-JSON` 可解析（`status: ok`、`mismatches: []`）；写出 `.tmp/bank-docs-config/reset-manifest.json` |
| `policy.check src/shop/order_controller.py ... --layer controller`（基线树） | `allow`，exit 0；`matched_rules` 43、`skipped_rules` 0、5 个 checker 全 served |
| `structure_metrics.py --layers ... --interfaces ...`（基线树） | 10/10 pass，exit 0；`layers.entries=18`、`interfaces.entries=6` |

## 5 本题的读法（不是「跑完就算」）

- **四个维度分开读**：T（任务完成；**未冻结**）、C（规则遵守；`scoring.yaml` 的 `dimension_c`）、
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
| SEC-006 | style_lint | error | M2 加载器用 `yaml.load(handle, Loader=yaml.Loader)` 代替 `yaml.safe_load` | `block`（`SEC-006@1 error`） | 实测 |
| TESTING-001 | missing_tests | error | M2 / M4 新建生产 `.py` 却不写同名测试 | `block`（`TESTING-001@1 error`） | 实测 |
| TESTING-002 | failing_tests | error | M2 / M4 实现与测试不一致，相关测试红 | `block`（`TESTING-002@1 error`） | 规则数据（dgate2 同套规则实测过） |
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
| `baseline/`（13 文件） | 逐字节基线树（11 个来自旗舰 baseline + 2 个构造） | **已落盘**：组合摘要可复核 |
| `reset-arm.py` | 逐字节重置 + 摘要校验 + `RESET-ARM-JSON` + `reset-manifest.json` | **已实测**：dry-run + 真跑 13/13 |
| `layers.yaml` / `interfaces.yaml` | A 维度声明（18 文件 → 层；6 个非测试模块的公开面上限） | **已落盘**：基线树实测 10/10 pass |
| `scoring.yaml` | T/C/A 三维判据（T **未冻结**：`pending_hidden`、`case_ids: []`、`total: null`、`planned_min_total: 30`） | C/A 已写；T 待隐藏代码 |
| `coverage.md` | 43 条规则点 + A1–A10 + 隐藏面的逐项覆盖矩阵与实测读数 | 已写（8 直接 / 23 变异 / 12 不适用；`STYLE-004` 记实测负例） |
| `hidden/` | 隐藏验收 PLAN + runner + 用例（>= 30 条） | **未做**（下一批任务；`scoring.yaml` 的 `hidden_plan_sha256` / `hidden_runner_sha256` 写 `null`） |
| `reference/` | 参考解（模块 / 接口 / 文档要点 + 实现树） | **未做**（不参与判分） |
| 天花板 | 参考解上的 T/C/A 实测（`total` 的可达性与 A3 上限校准） | **未测**（依赖 `hidden/` 与 `reference/`） |

**完成度一句话**：基线、task-package、reset-arm、layers/interfaces、C/A 判据、覆盖表**已落盘并实测可复核**；
隐藏验收代码、参考解、天花板实测、T 的 `total` / `case_ids` 冻结**都没做**。

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
7. **`total` / `case_ids` 故意留空**：不伪造已冻结的 T（见 §7 与 `scoring.yaml` 的 `dimension_t.note`）。

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
