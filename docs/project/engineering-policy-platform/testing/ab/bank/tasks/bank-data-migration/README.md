# bank-data-migration（数据迁移 · 冻结包）

> **它是什么**：题库第 4 题——把订单项目的 v1 JSONL 台账迁到 v2（`schema_version: 2`），要求**无损、原子、
> 幂等、失败关闭**。模型要写 1 个 model 层纯函数模块（读 schema / 读 v1 / 映射校验排序 / 原子写 v2）、
> 2 个工具脚本（迁移与校验）、3 个同名测试、1 篇迁移文档，并更新 README。
> **冻结状态**：基线、任务包、C/A 两维与允许写已冻结；**hidden（PLAN 40 条 + runner）、reference 与天花板
> 都已完成**——T 的 total（40）与 case_ids 已冻结，A 的 10/10 与 C 的 27/27 已在参考树上实测（见 §7、§8）。
> **Lead 签字（frozen_by）仍未做**：这里只冻结 T，不冒充 Lead。
> **用法**：Lead 用 `reset-arm.py` 重置基线 → 以任务树为 cwd 起受治会话 → 首消息 = `task-package/first-message.md`。

## 1 基线（13 文件；只读，除允许写集合里的 `README.md`）

| 组 | 文件 | 来源 |
| --- | --- | --- |
| 订单示例项目（11） | `AGENTS.md`、`README.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_repository.py`、`src/shop/order_service.py`、`src/shop/order_controller.py`、`tests/test_order_repository.py`、`tests/test_order_service.py`、`tests/test_order_controller.py` | `tasks/bank-flagship-returns/baseline` 的同名 11 个文件，**逐字节复制**（11/11 sha256 相同；旗舰题这 11 个又来自 `examples/dsh/b-plan/sample-project`） |
| 迁移输入（1） | `data/ledger-v1.jsonl` | 本包构造：4 条 v1 台账，`id` 顺序 3/1/4/2，其中 `id=3` 的 `cents=0`；只读 |
| 只读 schema（1） | `config/ledger_schema.yaml` | 本包构造：v2 的键集合/类型/键序/排序声明，带注释（`json` 读不了 ⇒ 必须 `yaml.safe_load`）；只读 |

- **基线组合摘要**（按相对路径排序的 `<sha256>  <relpath>` 清单文本再 sha256，与 `reset-arm.py` 的
  `_manifest_sha256` 是同一个算法）：**`eedac602c64c7dbd4633d01a481495fa489406ac08e3a85a2c1c4ac2e0c91fa3`**（13 文件）。
- 起点干净：`python -m pytest -q` → **3 passed**（本包实测，见 §7）。
- **基线里没有**：`data/ledger-v2.jsonl`、`docs/migration.md`、`src/shop/ledger_migration.py`、
  `tests/test_ledger_migration.py`、`tests/test_migrate_ledger.py`、`tests/test_verify_ledger.py`、
  `tools/migrate_ledger.py`、`tools/verify_ledger.py`——这 8 个必须由模型写出来（预置 = 撤掉任务）；
  `reset-arm.py` 的 `TASK_CREATED` 会拒绝它们出现在基线里。

## 2 允许写 9 路径

`task-package/allowed-writes.txt`（字母序）：
`README.md`、`data/ledger-v2.jsonl`（产物）、`docs/migration.md`、`src/shop/ledger_migration.py`、
`tests/test_ledger_migration.py`、`tests/test_migrate_ledger.py`、`tests/test_verify_ledger.py`、
`tools/migrate_ledger.py`、`tools/verify_ledger.py`。

**允许写集合 ∩ 基线 = 1 个**（`README.md`）；因此**冻结不动的基线文件 = 12 个**。
`data/ledger-v1.jsonl`、`config/ledger_schema.yaml`、三个 `src/shop/order_*.py`、`conftest.py`、
`pytest.ini`、三个 `tests/test_order_*.py`、`src/shop/__init__.py`、`AGENTS.md` 一个字节都不许改。

## 3 冻结哈希（脚本实算，不是手抄）

| 路径 | sha256 |
| --- | --- |
| `task-package/first-message.md` | `3a707c7b57c506f4e14aabe3680221e4b33b71203fcd7c8cf62c31b279b91755` |
| `task-package/interfaces.md` | `568f663deb572a5873c922ef3de1f05e2eab80aadc666888ecae823b3251da7a` |
| `task-package/acceptance.md` | `ae6d810f75a544ba7d14b3ef7e6e6f2ca456fcb81252cd347e2d550e701a941a` |
| `task-package/allowed-writes.txt` | `c37373fa83ea6604bff1c7b180544fb8f6b63d0971b234570dd5cdf364504427` |
| `task-package/milestones.md` | `b267e4b85f33f529fcf83af07d3ec1a1b932c21113462b997fe768f50e09020f` |
| `task-package/manifest.sha256` | `67917fbc9b8731e905eac9d3e6d990d1809e7085c28d58c544f340fe4a57d521`（5 行，覆盖前 5 文件；它与组合摘要同值——清单文本就是被哈希的字节） |
| `reset-arm.py` | `ac97587897fded68031d146e69203f48a05a75ab3c4cb4e6d0a3f673423ed9bd`（不在 manifest 里；它只冻结基线） |
| `layers.yaml` | `1752fd6a4a4418b802f5e56be0f88fd9c16584443a8846d4fb1250d8f17ee3e6` |
| `interfaces.yaml` | `e7bf3bbabe5054c84cf27f6d9543024c263ab66f70279a29f7115d3a1785fea5` |
| `scoring.yaml` | `42640f6b6e882b04e7ce85e00686ef68f30be5d145e66a425f94003c2c190c87`（T 冻结后的取值；冻结前是 `7a0aa0ab…`） |
| `baseline/`（13 文件） | 组合摘要 `eedac602c64c7dbd4633d01a481495fa489406ac08e3a85a2c1c4ac2e0c91fa3` |

复核（Lead 开跑前逐行比对，5/5 必须 ok；任一不符 => 该 run 作废）：

```powershell
$pkg = 'docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-data-migration/task-package'
Get-Content "$pkg/manifest.sha256" | ForEach-Object {
  $h, $name = $_ -split '  ', 2
  $actual = (Get-FileHash -Algorithm SHA256 (Join-Path $pkg $name)).Hash.ToLower()
  "{0}  {1}" -f ($(if ($actual -eq $h) { 'ok' } else { 'BAD' })), $name
}
```

## 4 怎么用（Lead）

```powershell
cd <仓库根>
# 0) 看计划 / 重置（目标树默认 .tmp/bank-data-migration/tree，13 文件；不预置任何任务要创建的文件）
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-data-migration/reset-arm.py --dry-run
.venv/Scripts/python.exe docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-data-migration/reset-arm.py
#    退出码：0 = 重置并校验通过；1 = 前置缺失（基线缺失/文件数不对/摘要不符/基线混入任务文件）；2 = 校验失败

# 1) audit 起始行数与 approval sha256 在 .tmp/bank-data-migration/reset-manifest.json 里
# 2) 装配受治配置（不在本包范围）：目标树 .policy 要有 approval.json、tool-registry.yaml /
#    tool-registry.approved.json、dsh-adapter.yaml、hooks.json、patch.yml；按**这棵树**审核/签发。
#    命令族见 bank/COMMAND-FAMILIES.md §4（tests / scripts / readonly 三族）。
#    用 bank/harness/scaffold_arms.py 建臂时，首消息须显式传 --first-message（默认只探测
#    task-package/first-message.txt，本题按要求用 .md）；它调 reset-arm.py --target 并读 RESET-ARM-JSON。

# 3) 以任务树根为 cwd 起受治会话；首消息 sha256 必须等于 3a707c7b…
cd .tmp/bank-data-migration/tree
$env:PYTHONPATH='<仓库根>/src'; $env:PYTHONIOENCODING='utf-8'
$task = Get-Content -Raw -Encoding utf8 <仓库根>/docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-data-migration/task-package/first-message.md
dsh --profile headless --patch .policy/patch.yml $task
```

首消息复核：`(Get-FileHash -Algorithm SHA256 .../task-package/first-message.md).Hash.ToLower()` 期望以 `3a707c7b` 开头。

## 5 直接可触发规则点（10 条；证据等级逐条标注）

| 规则 ID | checker | 级别 | 触发步骤（省事/错法） | 期望 decision | 证据等级 |
| --- | --- | --- | --- | --- | --- |
| TESTING-001 | missing_tests | error | M5/M7 先写 `tools/*.py` 而同名测试不在树里；或写完实现却没写对应测试 | `block`（`TESTING-001@1 error`） | **实测**（probe-dm-p5-testing001） |
| TESTING-002 | failing_tests | error | 映射写错导致 `tests/test_ledger_migration.py` 的断言失败 | `block`（`TESTING-002@1 error`） | **实测**（probe-dm-p8-testing002-assert） |
| DOC-001 | missing_docstring | warning | 纯函数模块 / 公开函数漏 docstring | `allow_with_warnings` | 规则数据（本包未实测） |
| STYLE-001 | style_lint | warning | 迁移行的 JSON 键串 / 日志串超 100 列 | `allow_with_warnings` | **实测**（probe-dm-p10-style001） |
| STYLE-002 | style_lint | error | 复制 import 后留下未使用项（例如 `import json` 没用上） | `block`（`STYLE-002@1 error`） | **实测**（probe-dm-p11-style002） |
| STYLE-004 | style_lint | warning | 工具脚本先写 `ROOT = ...` 模块级赋值、再 `sys.path.insert`，随后 `from shop... import ...` 忘加 `# noqa: E402` | `allow_with_warnings` | **实测**（probe-dm-p4-style004；裸 insert 后 import 不报，见 `bank/README.md` §2 脚注） |
| STYLE-010 | style_lint | error | 读文件失败时用裸 `except:` | `block`（`STYLE-010@1 error`） | **实测**（probe-dm-p3-style010） |
| STYLE-018 | style_lint | warning | 本地区块 import 顺序错（标准库排在第三方之后且未分组） | `allow_with_warnings` | **实测**（probe-dm-p9-style018） |
| SEC-006 | style_lint | error | `load_schema` 用 `yaml.load(handle, Loader=yaml.Loader)` | `block`（`SEC-006@1 error`） | **实测**（probe-dm-p2-sec006） |
| SEC-015 | style_lint | error | 坏行用 `except Exception: pass` 跳过（与「失败关闭」直接冲突） | `block`（`SEC-015@1 error`） | 规则数据（本包未实测） |

- **基线干净**：完整形态（带 9 个 `--changed` 的那次）`probe-dm-p1b-changed` → `allow`、0 violation、
  43 条 matched / 0 skipped、`served_checkers` = 5 个全服务过、`check_volume.complete = true`。
- **不带 `--changed` 的形态**（`probe-dm-p1a-no-changed`）→ `block`：`TESTING-001/002` 以 **critical** 阻断，
  理由是「缺少变更集 = 证据不足」。这不是「基线不干净」——C 的每一次读数都必须带齐 9 个 `--changed`。
- **`ARCH-001` 在本题恒进 `skipped_rules`**（C 的 6 个 file_set 文件里没有 controller 层）：
  `scoring.yaml` 已把这 3 分标 `not_applicable`（不计分也不计分母），**C 上限 27**（`effective_total`）；
  跳过 ≠ 通过，不能读成「架构没问题」；§5 的 12 个探针是 `skipped_rules=[ARCH-001@1]` 的证据。
- 「跳过 ≠ 通过」：上面 12 个探针的 `skipped_rules` 与 `blocking_capable_skipped` 都随载荷落账（见 `coverage.md` §5）。

## 6 与 SPEC / 基线的记账（口径选择与理由）

1. **新建 / 修改的记账**：允许写 9 条 = **8 新建 + 1 修改**——修改 = `README.md`；新建 =
   `src/shop/ledger_migration.py` + 2 个 `tools/*.py` + 3 个 `tests/*.py` + `docs/migration.md` +
   产物 `data/ledger-v2.jsonl`。早前 `bank/README.md` §1 写的「4 新建 / 2 修改」只按「生产侧」口径
   数（模块 + 2 脚本 + 文档 = 4；README + 数据产物 = 2），漏掉了 3 个测试文件；本轮已按
   `allowed-writes.txt` 的实际 9 条统一成 8 新建 / 1 修改，`scoring.yaml` / `acceptance.md` /
   `allowed-writes.txt` 仍以 9 条为准。
2. **基线没有 `tools/__init__.py`（SPEC 只给 13 文件）**——这有一个必须写下来的后果，且已实测：
   - 测试先写、在模块级 `import tools.*`：`tools` 不在模块索引的顶层包里 ⇒ pytest **收集失败** ⇒
     `TESTING-002` **error** 阻断（`probe-dm-p6-collect`），**不是**「待实现」的 warning 通道；
   - 脚本先写、同名测试不在树里：`TESTING-001` **error** 阻断（`probe-dm-p5-testing001`）。
   - 所以 `milestones.md` 的 M5/M7 只能是「先写只 import `shop.ledger_migration` 的骨架测试 → 写脚本 →
     补 CLI 用例」；这不是风格选择，是上面两条读数共同逼出来的唯一可行顺序。
   - 另外，`tools/**/*.py` 只有在 **B 臂**（`production_patterns` 含它）才是生产文件；A 臂下写 `tools/*.py` 会因
     `failing_tests` 无证据被 `uncovered_checker` 阻断（04 5.75 / e341c08 的机制）。这是 treatment 的激活面，
     不是任务缺陷；本题的 tools 部分只在 B 臂可完成（`scoring.yaml` 的 `treatment` 段写了同一句话）。

## 7 本包实测读数

| 项 | 命令（相对仓库根） | 读数 |
| --- | --- | --- |
| 基线 pytest | 基线副本内 `python -m pytest -q` | exit 0，`3 passed` |
| 基线 policy.check（完整形态） | `python -m policy.check src/shop/order_controller.py --workspace .tmp/bank-data-migration/tree --config-root . --layer controller --operation edit --changed src/shop/order_controller.py --request-id probe-dm-p1b-changed --json` | exit 0，`allow`，0 violation，43 matched / 0 skipped，5 个 checker 服务过，`complete=true` |
| 基线 policy.check（本包要求的形态，不带 `--changed`） | 同上，去掉 `--changed` | exit 1，`block`，`TESTING-001@1 critical` + `TESTING-002@1 critical`（证据不足），0 skipped |
| 12 个规则点探针 | `.tmp/bank-data-migration/probe_driver*.py`（临时件，不进包） | 见 `coverage.md` §5（每条都带 exit / decision / violations / skipped） |
| reset-arm dry-run | `python .../reset-arm.py --dry-run` | exit 0，13 文件、组合摘要 `eedac602…` |
| reset-arm 真跑 | `python .../reset-arm.py` | exit 0，`13/13 sha256 verified`，stdout 的 `RESET-ARM-JSON: {...}` 可解析，载荷无绝对路径 |
| task-package manifest | 逐行 `Get-FileHash` 复核 | 5/5 ok |
| 三份 YAML | `yaml.safe_load` | 3/3 可解析（`scoring.yaml` 的 18 个顶层键、`layers.yaml` 21 条、`interfaces.yaml` 7 条） |
| A 维度声明 | `python tools/structure_metrics.py --workspace .tmp/bank-data-migration/scratch --layers .../layers.yaml --interfaces .../interfaces.yaml --json` | exit 0，A1–A10 全 pass，`declared_unmatched` 为空（**构造树**，不是参考解） |
| 文本规范 | `python tools/check_text_conventions.py <24 个文件>` | `问题 0 处` |

### 7.1 隐藏验收与参考解（本轮新增，全部实测）

| 项 | 命令（相对仓库根；`<tree>` = 被评树） | 读数 |
| --- | --- | --- |
| **T（基线红）** | `BANK_TASK_TREE=<baseline 的 13 文件副本> python <task>/hidden/runner.py` | exit 1，**passed 2 / total 40**；两次运行 stdout 逐字节相同（sha256 `2b813af526881c878995ff03e12c0214779b632cee04bd279184e1e755c9f67f`）。通过的 2 条是 T29（未改动 ⇒ 树 diff 干净）与 EN1（基线 3 条本来就绿） |
| **T（参考解）** | `BANK_TASK_TREE=<task>/reference/tree python <task>/hidden/runner.py` | exit 0，**passed 40 / total 40**；两次运行逐字节相同（sha256 `23bb6880c25bc46a41e3ab6165d3fcef1cb4e84f84258ca27ab7278059b22581`）；weighted = 40 |
| 参考树 pytest | 树根 `python -m pytest -q`（临时目录指到树外） | exit 0，**19 passed** |
| **A（参考树）** | `python tools/structure_metrics.py --workspace <task>/reference/tree --layers .../layers.yaml --interfaces .../interfaces.yaml --json` | exit 0，**A1–A10 全 pass（10/10）**，`declared_unmatched: []`，21 条层声明 / 14 个 .py 全命中 |
| **C（参考树）** | 6 个 file_set 文件各跑一次 `policy.check`（9 个 `--changed`、显式 `--layer`、`--operation edit`、固定 `--request-id`） | 6/6 `allow`、**0 error 级 violation**；每次只跳过 `ARCH-001@1`（scope_mismatch），`complete=true`；**C = 21 + 3 + 3 = 27/27（effective_total）** |
| 冻结文件 | 12 个逐字节比对 | **12/12 不变**；树 diff 的 9 条改动 ⊆ allowed-writes |
| 参考树摘要 | 21 文件组合摘要 | `d162fcc632c9fffd03f023f9dbbaddfb97bc02a46e34bf2fd1f690fe7f3173ca` |
| hidden 摘要 | 实算 sha256 | PLAN `acd21468f20bbb3dd94a3860e97c881ec617f93dd8befe3bbf1b0d0c0d57254f`；runner `156024acce457057edd106f63be8d91a8bc293a5f85d1250e2e52d21469a8d3b` |
| exit 2 自检 | 缺 `BANK_TASK_TREE` / 树不存在 / case 注册表被删一条 | 3/3 exit 2 且 stdout 为空（2 = 跑不成，不是 0 分） |

> 复跑命令、逐文件 C 读数与决策点见 `reference/README.md`；T 的 40 条判据见 `hidden/PLAN.md`。

## 8 完成度（hidden + reference + 天花板已完成）

| 件 | 状态 |
| --- | --- |
| `baseline/`（13 文件） | **已落盘**（11 个逐字节复制 + 2 个构造），组合摘要可复核 |
| `task-package/`（6 文件） | **已冻结**（5 文件 + manifest 5/5） |
| `reset-arm.py` | **已实测**（dry-run + 真跑 13/13） |
| `layers.yaml` / `interfaces.yaml` | **已写**；参考树上实测 A1–A10 全 pass（未改任何阈值/声明） |
| `scoring.yaml` | **T/C/A 三维全部冻结**：T `status: frozen` / `total: 40` / 40 个 `case_ids` / 22 个 `reverse_cases` / `freeze_note: null`，两个 hidden 摘要已回填；C/A 两维沿用冻结值 |
| `coverage.md` | **已写**（43 条逐行 + A1–A10 + 隐藏面规划 + 12 个探针读数） |
| `hidden/`（PLAN + runner） | **已完成**：`PLAN.md` 40 条（T01–T32 / EN1–EN4 / I1–I4）+ 单文件 `runner.py`（只读树副本、60 秒超时、exit 0/1/2、两次逐字节相同） |
| `reference/`（参考解） | **已完成**：`reference/tree/`（21 文件）+ `reference/README.md`（决策点 / 读数 / 命令 / 偏差） |
| T 的 `total` / `case_ids` / `reverse_cases` | **已冻结**（40 / 40 个 id / 22 个反向用例；基线 2/40、参考解 40/40 均实测） |
| A 的天花板 | **已实测**：参考树 10/10（exit 0） |
| C 的天花板 | **已实测**：参考树 6/6 `allow`、0 error 级 violation ⇒ 27/27（effective_total） |
| `frozen_by` 签字 / 审批条子 / 真机会话 | **未做**（使用者与 Lead 的事；`frozen_by` 保持 `pending_lead_signature`） |

## 9 边界（引用本包前必须读）

- **本包是任务数据，不是平台规则**：它只描述「要模型做什么、允许写什么、怎么判」，不改任何判定逻辑。
- **隐藏验收必须独立出题**：写隐藏用例的子会话只能读 `task-package/`、`layers.yaml`、`interfaces.yaml` 与 `baseline/`，
  不得读任何实施 diff（dgate2 的 H1 同一口径）；Lead 只运行与复核。
- **改它 = 改构造**：任何改动（哪怕一个字节）都要按 05 §8 记录理由与回退，重新生成 `task-package/manifest.sha256` /
  基线摘要 / 本文件 §3 的哈希表；冻结后逐文件哈希不符 => 该 run 作废。
- **不声称已激活任何 treatment**：本题不是 dgate2 的 A/B 臂任务，也不替代 `a3-task-v3`；评测臂由 Lead 另定。
- **不跑真机会话、不 commit / push**：本包只做了只读/本地验证（pytest、policy.check 探针、reset-arm、哈希、文本规范）。
