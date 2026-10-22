# bank-async-concurrency（并发 / 异步题型：同步通知队列 → 确定性 asyncio 工作队列）

> **它是什么**：题库 5 道题型题之一——在既有订单示例项目上把同步 `NotificationQueue` 升级成
> **确定性的 asyncio 工作队列**：有界队列、按 key 幂等去重、可取消、停机排空、异常不吞。
> 跨 model（`Notification`）与 service（`NotificationWorker`）两层，含一个冒烟脚本、2 个新建同名
> 测试文件 + 1 个基线静态契约测试（M8 改写为行为测试）、1 篇文档；旧队列保留并标注弃用。
> **冻结状态**：**hidden + reference + 天花板已完成**——基线、任务包、reset-arm、A 维度声明、
> C/A 判据、隐藏验收（T）与参考解**全部落盘**，T 已冻结：`dimension_t.status: frozen`、
> `total: 38`、`case_ids = T01-T23 / EN1-EN8 / I1-I7`、两个 hidden 摘要是实算值。
> **实测天花板**：参考树 T **38/38**、A **10/10**、C **27/27**（`effective_total = 27`）、
> `pytest` 22 passed；基线 T **2/38**（起点红）。逐条读数见 **§9**。
> `frozen_by` = `Lead`（2026-10-22）：冻结的是读数依据，**“可开跑”仍由使用者另签**。
> **用法**：Lead 重置基线 → 以任务树为 cwd 起受治会话 → 首消息 = `task-package/first-message.md`；
> 跑完后按 `acceptance.md` + 隐藏验收（`hidden/runner.py`）+ 树 diff 判分。

## 1 基线（15 文件；只读，除允许写集合里的 4 个）

| 组 | 文件 | 来源 |
| --- | --- | --- |
| 订单示例项目（11） | `AGENTS.md`、`README.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_controller.py`、`src/shop/order_repository.py`、`src/shop/order_service.py`、`tests/test_order_controller.py`、`tests/test_order_repository.py`、`tests/test_order_service.py` | `bank-flagship-returns/baseline` 的同名 11 文件，**逐字节复制**（与 `examples/dsh/b-plan/sample-project` 的 11 文件亦逐字节相同） |
| 脚本包（1） | `tools/__init__.py`（顶层包标记；只有一行模块 docstring） | `bank-flagship-returns/baseline/tools/__init__.py`，**逐字节复制**（sha256 `f66ec0041ebb636c9fdee98ff706cda2ef04ca40474f79b84027e1e0cb3618eb`） |
| 同步通知队列（2） | `src/shop/notification.py`（`NotificationQueue`：`append` / `pop` / `__len__`）、`tests/test_notification.py` | 本包构造 |
| 基线静态契约测试（1） | `tests/test_notify_smoke.py`（静态检查 `tools/notify_smoke.py` 的公开面：有 `main()`、有 `__main__` 入口、不写文件；工具不存在时 `pytest.skip`） | 本包构造（2026-10-22 加；M8 由模型改写为行为测试，最终树里是行为测试） |

- **基线组合摘要**（按相对路径排序的 `<sha256>  <relpath>` 清单文本再 sha256，算法与
  `a3-task-v3/reset-arm.py` 的 `_manifest_sha256` 相同）：
  **`9739ecf0892fc2ce9a4a6354597f5c0b35aef04c297ee46bd51ac77cec3899d8`**（15 文件）。
- 基线起点干净：`python -m pytest -q` → **4 passed, 1 skipped**（跳过的是基线静态契约测试：此时工具文件还不存在；本包已在 15 文件基线副本上实测，退出码 0）。
- **基线里没有**（= 任务要求模型创建的 6 个文件）：`docs/async.md`、`src/shop/notify_model.py`、
  `src/shop/notify_worker.py`、`tests/test_notify_model.py`、`tests/test_notify_worker.py`、
  `tools/notify_smoke.py`。`reset-arm.py` 会拒绝这 6 个文件出现在基线里；`tests/test_notify_smoke.py`
  不在此列（基线静态契约测试，在允许写集合里）。
- **第 14 个文件 `tools/__init__.py` 是 Lead 裁定的构造修复**：初版 SPEC §2 的 13 文件表没有它，导致
  smoke 测试与脚本的双向阻断（先写 smoke 测试被 TESTING-002 拦、先写脚本被 TESTING-001 拦）；加入后
  `tools` 是树里的顶层包，当时先写 smoke 测试走「待实现」（§8.1）。它**不是**任务要创建的文件、
  **不进允许写集合**、属于冻结不动的基线。
  修法、实测读数与它在 A 维度里的层（显式 `skip`）见 §8.1。
- **第 15 个文件 `tests/test_notify_smoke.py` 是 2026-10-22 的构造变更（C1-b §7.3 形态）**：基线自带
  同名静态契约测试，模型在 M1 先写 `tools/notify_smoke.py`（不运行脚本），M8 再把它改写为行为测试；
  **最终树与改前逐字节相同**。它**不在新建集合**、**在允许写集合里**（因此允许写 ∩ 基线 = 4、冻结仍是 11）。
  动机（T3 下批次会把模型自己写的测试带进 `changed`，async 因此无激活）、改法与 A/B 实测见 §8.6。

## 2 允许写 10 路径

`task-package/allowed-writes.txt`（字母序）：

`README.md`、`docs/async.md`、`src/shop/notification.py`、`src/shop/notify_model.py`、
`src/shop/notify_worker.py`、`tests/test_notification.py`、`tests/test_notify_model.py`、
`tests/test_notify_smoke.py`、`tests/test_notify_worker.py`、`tools/notify_smoke.py`。

**允许写集合 ∩ 基线 = 4 个**（`README.md`、`src/shop/notification.py`、`tests/test_notification.py`、
`tests/test_notify_smoke.py`）；因此**冻结不动的基线文件 = 15 − 4 = 11 个**：
`AGENTS.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_controller.py`、
`src/shop/order_repository.py`、`src/shop/order_service.py`、`tests/test_order_controller.py`、
`tests/test_order_repository.py`、`tests/test_order_service.py`、`tools/__init__.py`。

（SPEC §3 原小标题写「允许写 9 路径」，与本包清单的 10 条矛盾；本轮已把 SPEC 标题与正文改成 10 条，
`allowed-writes.txt`、`scoring.yaml` 与本文三处一致。）

## 3 冻结哈希（脚本实算，不是手抄）

| 路径 | sha256 |
| --- | --- |
| `task-package/first-message.md` | `62afc50a95e7e91616fc1bed3ba193dd9d8ec9c381f38059151677fcf31a38dd` |
| `task-package/interfaces.md` | `9e11ef39b1539f7a2a4d33c2d284a6388dc89f156f958d017e19d5d13e0f10e5` |
| `task-package/acceptance.md` | `1d3ea8d9fa8be7ccc19d0593bd0461f368ac11cbbec57d63d5102b4c51adef04` |
| `task-package/allowed-writes.txt` | `1ad69cf570a6e0ccc20ec4dcd65727e195e12ded62570ae3f0b3cbbb22689a9f` |
| `task-package/milestones.md` | `ff6708746f8dbc6e760a8bd201e5270058b170b8bace130ce3fafd4f7b847985` |
| `task-package/manifest.sha256` | `b7926c2cd3f176da00ec447ed82b14dc9ec219c0e279442650e4a551978b9f68`（5 行，覆盖前 5 文件；它与组合摘要同值——清单文本就是被哈希的字节） |
| `reset-arm.py` | `07a741da5afdcac16daea4b5f38d76eca50aea3a72f80d05f17297be73d61621`（不在 manifest 里；它只冻结基线） |
| `layers.yaml` | `5d7b37fc4fae069c4968b17dfffb45d0ee308dbac6395707e4f1af3e6648536e` |
| `interfaces.yaml` | `fad6848215cdc0567619e6ccec334904eca76a4c2c929b8bdd04849883ecdeb4` |
| `scoring.yaml` | `bea34888c595cbdda25410dca24b9d0b6a77aa3e7d6190e960af9fb873c0d499`（自指摘要不写进自己；本行是**2026-10-22 H1 重冻之后**的现算值，freeze.json 另记） |
| `hidden/PLAN.md` | `599da13ad30168ff6dff4a31c5c4d8e434fae96c6b03bd6fdcc0c866c5289222`（38 条，见 §9） |
| `hidden/runner.py` | `ecaf97387f8ecc7f8d5fe7c2adec9c870fae6252b5947aeae7e6df57421177e1`（单文件自包含） |

复核：对 `task-package/` 的前 5 个文件各算一次 sha256，与 `manifest.sha256` 的 5 行逐行比对
（本包构建时 **5/5 ok**；任一不符 => 该 run 作废）。

## 4 怎么用（Lead）

```powershell
# 0) 看计划 / 重置（目标树默认 .tmp/bank-async-concurrency/tree，15 文件；不预置任何任务文件）
python docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-async-concurrency/reset-arm.py --dry-run
python docs/project/engineering-policy-platform/testing/ab/bank/tasks/bank-async-concurrency/reset-arm.py
#    退出码：0 = 重置并校验通过；1 = 前置缺失（基线缺失/文件数不对/摘要不符/基线混入任务文件）；
#            2 = 校验失败（mismatches / extra / undeletable）
# 1) 记下 audit 起始行数（reset-arm 会写进 .tmp/bank-async-concurrency/reset-manifest.json）
# 2) 装配受治配置（不在本包范围）：目标树 .policy 要有 approval.json、tool-registry.yaml /
#    tool-registry.approved.json、dsh-adapter.yaml、hooks.json、patch.yml；按**这棵树**审核/签发。
#    命令族见 bank/COMMAND-FAMILIES.md §5；用 bank/harness/scaffold_arms.py 建臂时，首消息须显式传
#    --first-message（它默认只探测 task-package/first-message.txt，本题按要求用 .md）；
#    它调 reset-arm.py --target 并读 stdout 的 RESET-ARM-JSON。
# 3) 以任务树根为 cwd 起受治会话；首消息 sha256 必须等于 62afc50a95e7e91616fc1bed3ba193dd9d8ec9c381f38059151677fcf31a38dd
```

首消息复核：`first-message.md` 的 sha256 期望 `62afc50a95e7e91616fc1bed3ba193dd9d8ec9c381f38059151677fcf31a38dd`。

## 5 直接可触发规则点（本题的真实岔口）

**证据等级**：`实测` = 本包构建时在基线副本 + 构造变异上用真 `policy.check` 跑出来的 decision
（逐条读数见 `coverage.md` §2）；`规则数据` = 只核对了规则 YAML/配置、**没跑**；`未测` = 没跑。

| 规则 ID | checker | 级别 | 本题触发步骤 | 期望 decision | 证据等级 |
| --- | --- | --- | --- | --- | --- |
| TESTING-001 | missing_tests | error | 新建 `src/shop/notify_model.py` / `notify_worker.py` 却不带同名测试（`tools/notify_smoke.py` 有基线静态契约测试，不属于这一形态） | `block`（error） | **实测**：新建 `notify_model.py` 无测试 → `block`（violations=[TESTING-001]，`probe-async-p2-missing-tests`）；在没有同名测试的树上写 `tools/notify_smoke.py` 同样是 `block` |
| TESTING-002 | failing_tests | error | 异步用例写错/相关测试失败（真失败，不是「待实现」） | `block`（error） | **实测**：子进程驱动、脚本缺失 → `block`（violations=[TESTING-002]，`probe-async-p4b-tools-test-subprocess`） |
| TESTING-002 的 M1 设计方向步 | failing_tests | error | M1 写 `tools/notify_smoke.py`（批为空）：`tools` 是不是生产文件由 treatment 决定 | A **`block`** / B **`allow`** | **实测**（`probe-async-m1-design`）：A `block`（violations=[TESTING-002]、`selection.level=none`、`failing_tests` 未被服务）；B `allow`（`selection.level=related`、nodeids 含 `tests/test_notify_smoke.py`） |
| DOC-001 | missing_docstring | warning | 类/函数/模块漏 docstring | `allow_with_warnings` | **实测**：无 docstring 的 model + 绿测试 → `allow_with_warnings`（2 条 warning） |
| STYLE-001 | style_lint | warning | 单行超过 100 列 | `allow_with_warnings` | **实测**：超长行 → `allow_with_warnings`（1 条 E501） |
| STYLE-002 | style_lint | error | 改完留下未使用 import | `block`（error） | **实测**：`import json` 未用 → `block`（1 条 F401） |
| STYLE-004 | style_lint | warning | `ROOT = Path(...)` 后 `sys.path.insert` 再 import shop 而忘 `# noqa: E402` | `allow_with_warnings` | **实测**：该形态 → `allow_with_warnings`（1 条 E402）；**只有 `sys.path.insert` 紧跟 import 时不报**（ruff 0.14.13 的特例，见 §8.4） |
| STYLE-018 | style_lint | warning | import 分组/排序错（`from pathlib import Path` 在 `import sys` 之前） | `allow_with_warnings` | **实测**：`allow_with_warnings`（1 条 I001） |
| SEC-011 | style_lint | error | 用 `random.random()` 生成事件 id / 抖动 | `block`（error） | **实测**：`block`（1 条 S311） |
| SEC-015 | style_lint | error | `except Exception: pass` / 裸 `except: pass` 静默吞异常 | `block`（error） | **实测**：裸 `except: pass` → `block`（SEC-015 + STYLE-010 各 1 条） |
| STYLE-010 | style_lint | error | 裸 `except:`（SPEC 记作 ○，但同一行会被 SEC-015 兜住） | `block`（error） | **实测**：与 SEC-015 同次命中（2 条 error） |
| ARCH-001 | forbidden_dependency | error | 本任务不碰 controller；8 个被测 .py 都不在 controller 层 | 不适用（scope 不匹配）；C 的 3 分已标 `not_applicable`（`effective_total` 27） | **实测**：8 个被测 .py 上 `skipped_rules` 都是 `[ARCH-001@1]`（跳过 ≠ 通过）；基线 `order_controller.py` 探针上它真的参与判定并 `allow`（见 §6） |
| SEC-006 | style_lint | error | 本任务不读 YAML | — | **规则数据**（未跑） |
| TESTING-002 的 pending 通道 | failing_tests | error（规则）/ warning（findings） | 先写 `tests/test_notify_model.py` / `tests/test_notify_worker.py` 而实现缺失（`shop` 顶层包已在树里） | `allow_with_warnings` + `pending_findings` | **实测**：→ `allow_with_warnings`、`pending_findings=[TESTING-002]`、`violations=[]`（`probe-async-p3-pending`）；smoke 的历史形态（M7 先写测试）读数留在 `coverage.md` §2 |

## 6 本题的读法（不是「跑完就算」）

- **四个维度分开读**：T（任务完成；`hidden/runner.py` 的 38 条，基线 2/38、参考树 38/38，见 §9）、C（规则遵守；`scoring.yaml` 的
  8 条 + 冻结文件 + 旁路）、A（结构；`layers.yaml` / `interfaces.yaml` + `tools/structure_metrics.py`）、
  过程（平台账本：被拒动作、原因码、`matched / skipped / served_checkers`）。**不许把过程读数折算进 T/C/A**。
- **`allow_with_warnings` 不是失败、也不是通过**：M2/M4 的「待实现」走 `pending_findings`
  （AGENTS 第 51 条）；exit 1 只表示「不是 ALLOW」，阻断判定只读 `violations`。
- **n=1 只作案例读数**：不写均值/提升/显著；要写「值得扩试」需每臂 k≥3。
- **跳过 ≠ 通过**：每次 `policy.check` 的 `skipped_rules` 与 `check_volume.blocking_capable_skipped`
  必须一起读（本题基线读数：`src/shop/notification.py`（`--layer service`）→ `skipped_rules=[ARCH-001@1]`、
  `blocking_capable_skipped=1`、`missing_dimensions=[]`、`complete=true`；`src/shop/order_controller.py`
  （`--layer controller`）→ `allow`、`skipped_rules=[]`、5 个 checker 全部 served、`blocking_capable_skipped=0`）。
  C 的分母也据此调整：`ARCH-001` 的 3 分标 `not_applicable`（不计分也不计分母），**C 上限 27**，
  读 C 必须带 `effective_total`。

## 7 本包目录地图与完成度

| 路径 | 是什么 | 状态 |
| --- | --- | --- |
| `task-package/` | 首消息 / 里程碑 / 验收表 / 接口契约 / 允许写 / manifest | **已落盘**（字节固定，manifest 5/5 可复核） |
| `baseline/` | 15 文件基线树（逐字节；含与旗舰逐字节相同的 `tools/__init__.py` 与基线静态契约测试 `tests/test_notify_smoke.py`） | **已落盘**（组合摘要可复核；pytest 4 passed, 1 skipped） |
| `reset-arm.py` | 逐字节重置 + 摘要校验 + reset-manifest.json | **已实测**（dry-run + 真跑 15/15；三种前置失败都退出 1） |
| `layers.yaml` / `interfaces.yaml` | A 维度声明（最终树 21 文件 → 层；非测试模块公开面上限） | **已写**；`structure_metrics` 加载通过，**基线副本（15 文件）与参考树都 A1–A10 全 pass**（§9.3；`tools/__init__.py` 显式 `skip` 移出测量范围，理由见 §8.1）；6 个新建文件在基线副本里声明为 unmatched |
| `scoring.yaml` | T/C/A 三维判据 | **已冻结**（`status: frozen`、`dimension_t.status: frozen`、`total: 38`、38 条 `case_ids`、`freeze_note: null`；`frozen_by` = `Lead`（2026-10-22）） |
| `coverage.md` | 43 条规则点 ○/—、A1–A10、隐藏行为面、实测读数 | **已写**（未实测项如实标未测） |
| `hidden/` | `PLAN.md`（38 条：T01–T23 / EN1–EN8 / I1–I7）+ `runner.py`（单文件自包含） | **已完成**：基线 **2/38**、参考树 **38/38**；两次输出逐字节相同（§9） |
| `reference/` | 参考解（`README.md` 决策点 + `tree/` 21 文件） | **已完成**：`pytest` 22 passed、`smoke` 2 条、允许写 10 条逐条落地（§9） |
| 天花板实测 | 参考树上的 T/C/A 上限 | **已完成**：T 38/38、C 27/27（`effective_total` 27）、A 10/10（§9） |

## 8 边界与已知构造问题（引用本包前必须读）

### 8.1 `tools/__init__.py` 与 smoke 测试的先后阻断（**已按 Lead 裁定修复**；现行里程碑见 §8.6）

初版冻结包的 SPEC §2 列了 13 个基线文件，**不含 `tools/__init__.py`**；在 `pre_evidence` 开启的
默认治理下，这造成一个**双向阻断**（两个方向都在真 `policy.check` 上实测过，读数留在
`coverage.md` §2 的 `p4` / `p4b` / `p5` 三行）：

- 先写 `tests/test_notify_smoke.py`（模块级 `from tools.notify_smoke import main`）→ 顶层包 `tools`
  不在树里 → **不是** `pending_implementation`，而是真收集失败 → `block`（TESTING-002）；
- 先写 `tools/notify_smoke.py` → 没有同名测试 → `block`（TESTING-001）。

**Lead 裁定（本包已执行）**：基线加 `tools/__init__.py`，**13 → 14 文件**。该文件从
`bank-flagship-returns/baseline/tools/__init__.py` 逐字节复制（sha256
`f66ec0041ebb636c9fdee98ff706cda2ef04ca40474f79b84027e1e0cb3618eb`），**不进允许写集合**，
属于冻结不动的基线（`scoring.yaml` 的 `frozen_untouched` 因此从 10 个变 11 个）。当时的任务要创建的
文件清单、允许写 10 条、里程碑顺序都不变；`reset-arm.py`、`task-package/`、scoring 与本文的
文件数/摘要已同批更新。

**当时的修后实测**（真 `policy.check`；`--workspace` = 14 文件基线 + 一份 `tests/test_notify_smoke.py`，
`--operation create`、`--layer test`、`--changed tests/test_notify_smoke.py`、固定 `--request-id`）：
`allow_with_warnings`、`violations=[]`、`pending_findings=[TESTING-002]`、
`pending_implementation[0].missing_targets=["tools.notify_smoke"]` —— 当时 M7 的「先写测试」走
「待实现」通道（AGENTS 第 51 条）。**2026-10-22 起里程碑不再走这个顺序**：M1 先写
`tools/notify_smoke.py`、由基线静态契约测试检查公开面（§8.6）；`tools/__init__.py` 仍留在基线里，
它让 `tools` 是顶层包，基线测试才能被收集。子进程驱动、脚本缺失的用例仍是真失败 → TESTING-002 `block`
（`probe-async-p4b-tools-test-subprocess`）。

**A 维度声明：`tools/__init__.py` 显式移出测量范围（`skip`，不是漏声明）**。理由是实测出来的：

- 按与旗舰同形的 `other` 声明测量**冻结基线**，A9 报 1 条 `tools/__init__.py: no_test_import`
  （基线里没有任何测试 import `tools.*` 子模块）→ 基线 A1–A10 只有 9/10；
- 而本题 A 读数以「基线 + 最终树都 A1–A10 全 pass」为冻结口径，因此按 Lead 裁定的备选
  （「若实测 A9 不成立，可改 skip」）改成 `skip`，并在这里与 `coverage.md` §4 **写明是显式移出**；
- 代价与补偿：它只有一行模块 docstring，不参与 A3 / A7 / A9 / A10 的统计；tools 的实质写面
  `tools/notify_smoke.py` 仍在 composition 层、仍被 A9 要求由 `tests/test_notify_smoke.py` 静态 import；
- 口径本身也实测过：在「14 文件基线 + `tools/notify_smoke.py` + import 它的测试」替身树上，
  `other` 声明得到 A9 7/7 pass、A1–A10 10/10（替身树只在 `.tmp/`，不随包交付）。
- **当时的独立复核**（同一替身树 16 文件、本包现行 `layers.yaml` / `interfaces.yaml`）：基线组合摘要重算
  （14 文件基线）`d12576d8…` 一致；`task-package/manifest.sha256` 5/5 逐行相符；`reset-arm.py --dry-run` exit 0；
  `structure_metrics` → 10/10 pass、exit 0（`declared_unmatched` 5、`undeclared` 空）。

### 8.2 SPEC 内部数字冲突（本包的选择）

| SPEC 处 | 两种读法 | 本包选择 | 理由 |
| --- | --- | --- | --- |
| §2「基线（15 文件…）」vs `bank/README.md` §1（原）与派单说明的「12 文件」 | 12 / 15 | **15**（11 订单项目 + 1 脚本包 + 2 同步队列 + 1 基线静态契约测试） | SPEC §2 初版是 11+2=13；Lead 裁定加 `tools/__init__.py` 后为 14；2026-10-22 加基线静态契约测试后为 15（§8.6）。`bank/README.md` 第 5 行（本题包之外）与设计规格快照 `SPEC.md` §2 仍是「14 / 7 新建」的旧计数——本轮只同步判据面与首消息面，二者留给 Lead 同批处置 |
| §3「允许写 9 路径」vs 同段清单 10 条 + 「共 10」 | 9 / 10 | **10** | 清单逐条可执行；本轮已把 SPEC 标题与正文改成 10 条（三处一致） |
| `bank/README.md`（原）「12 文件 / 5 新建 / 3 修改」vs 实际 | 12 / 15 | **15 文件、6 新建 + 4 修改 = 10** | 按 `baseline/` 15 文件与 `allowed-writes.txt` 10 条复算（`tests/test_notify_smoke.py` 是基线文件、在允许写里，M8 改写） |

### 8.3 构造器多了一个可选参数（相对 SPEC §3 的签名）

SPEC §3 只写 `__init__(self, queue_size: int = 4)`，但 §5 的隐藏要点要求「两个 worker 消费**同一队列**」。
本包把签名定为 `__init__(self, queue_size: int = 4, queue: asyncio.Queue | None = None)`：新增的
**可选**关键字用来注入共享队列，原有调用形态（`NotificationWorker()` / `NotificationWorker(queue_size=2)`）
字节级不变。若 Lead 要求逐字照 SPEC，则 A7 不可表达，隐藏用例应删掉该条并同步改 `acceptance.md` /
`interfaces.md` / 首消息（改 = 换构造）。

### 8.4 STYLE-004 的触发形态（实测细节）

ruff 0.14.13 **不报**「裸 `sys.path.insert(...)` 后紧跟 import」的 E402；但报「先有模块级赋值
（如 `ROOT = Path(__file__).resolve().parents[1]`）再 `sys.path.insert`，再 import」的 E402。
本题的真实 smoke 脚本通常是后者，所以 §5 表里把它记为可触发；若模型写成前者，STYLE-004 不会有读数
（不是「通过」，是「没有命中这条规则的形态」）。

### 8.5 其它边界

- **本包是任务数据，不是平台规则**：它只描述「要模型做什么、允许写什么、怎么判」，不改任何判定逻辑。
- **隐藏验收必须独立出题**：写隐藏代码的子会话不得读参考解、不得看任何实施 diff（dgate2 H1 同一口径）；
  PLAN 可以先于代码冻结，但**开跑前必须代码落盘**（pending 不是通过）。
  **本批是降级形态（如实记录）**：隐藏与参考解由**同一个子会话**完成，顺序是「PLAN + runner 先落盘 →
  跑出基线红 2/38 → 才写 `reference/tree`」，写隐藏时没有读过任何参考实现（当时本题 `reference/` 还不存在）；
  但作者知道自己的实现意图，因此不满足「未参与实施」的字面要求。下一道同类题若要严格口径，须换一个子会话出题。
- **改它 = 改构造**：任何改动（哪怕一个字节）都要按 05 §8 记录理由与回退，重新生成
  `task-package/manifest.sha256` / 基线摘要 / 本文件 §3 的哈希表；冻结后逐文件哈希不符 => 该 run 作废。
- **本包不声称已激活任何 treatment**：`scoring.yaml` 的 `treatment.arms` 仍为空；A/B 只在离线探针里由
  `testing/ab/dgate2/configs/{before,after}` 提供（§8.6），那是一次构造读数、不是一个 run。
- **不跑真机会话、不 commit**：本包落地时只做了只读/本地验证（pytest、policy.check 探针、reset-arm、
  structure_metrics、哈希、文本规范）。

### 8.6 2026-10-22 构造变更：基线静态契约测试与 M1 的设计方向步

**动机**：Gate 0（`readings/2026-10-22-bank-k3-gate0-activation.md`）在 T3 配置下实测 **async 无激活**：
T3 的批次会把模型自己写并结算的测试带进后续动作的 `changed` 集，A 也因此选得到测试——C1-b §7.3 的
「A 选不到测试 → `TESTING-002` block、B 选得到 → allow」在旧里程碑序列上不再出现。该读数的 §5
给出的最小构造候选 1 就是本批采用的形态。

**改法（只动构造，不动最终树）**：

- 基线加第 15 个文件 `tests/test_notify_smoke.py`——**基线静态契约测试**：工具文件存在时检查
  `tools/notify_smoke.py` 的公开面（有 `def main(`、有 `__name__ == "__main__"`、不含 `open(` 与
  `write_text`），不存在时 `pytest.skip`（所以基线 `pytest` = **4 passed, 1 skipped**）；
- 里程碑把写 `tools/notify_smoke.py` 提到 **M1**（批为空、本步不运行脚本）；**M8** 由模型把基线
  静态测试**改写为行为测试**（`from tools.notify_smoke import main` + 调用 + 断言去重后 2 条），
  最终树与改前**逐字节相同**（`reference/tree` 一个字节没改）；
- 允许写仍是 10 条：`tests/test_notify_smoke.py` 从「新建」变成「基线已有、模型改写」；因此
  新建 = 6、允许写 ∩ 基线 = 4、冻结仍是 11、文件集仍是 21。

**A/B 实测**（`probe-async-m1-design`，真 `policy.check`；树 = 15 文件基线 +
`reference/tree/tools/notify_smoke.py`，`--changed tools/notify_smoke.py`（批为空）、
`--operation create`、`--layer composition`、固定 `--request-id`；两臂唯一差异 =
`validation/test-layout.yaml` 的 `production_patterns`：A 只 `src/**/*.py`，B 加 `tools/**/*.py`）：

| 臂 | decision | violations | selection.level | nodeids | 服务过的 checker |
| --- | --- | --- | --- | --- | --- |
| A（`configs/before`） | **`block`** | `[TESTING-002]` | `none` | `[]` | 3 个（**缺 `failing_tests`**：选不到测试 = 没被服务） |
| B（`configs/after`） | **`allow`** | `[]` | `related` | `[tests/test_notify_smoke.py]` | 4 个（含 `failing_tests`） |

这就是 C1-b §7.3 的设计方向（A block / B allow），而且发生在**批为空**的 M1：模型自己写的测试
进不了 `changed`。两臂的 `skipped_rules` 都是 `[ARCH-001@1]`（`tools/` 是 composition 层），
`check_volume.complete=true`、`blocking_capable_skipped=1`。

**没变的东西**：`reference/tree`（21 文件构造）一个字节没改；T 仍 38 条、参考树 38/38、C 27/27、
A 10/10；基线 T 仍 2/38。构造变更的理由、改法与旧读数作废关系按 05 §8 记在本节与
`readings/2026-10-22-bank-k3-gate0-activation.md` §5。

## 9 天花板读数（hidden + reference 已完成；本机实测，2026-10-21 批次，2026-10-22 构造变更后复测 T）

> 口径：三个维度分开读、都带分母；**n=1 只写案例读数**，不算均值/提升/显著（bank/README.md §5）。
> 环境：Windows + `.venv/Scripts/python.exe`（Python 3.13.11、pytest 9.1.1）；C 的 style_lint 用 ruff 0.14.13。
> 树：基线 = 本包 `baseline/`（15 文件）；参考树 = `reference/tree/`（21 文件）。

### 9.1 T（隐藏验收 `hidden/runner.py`，38 条）

| 树 | 命令 | exit | passed/total | 两次输出 sha256 |
| --- | --- | --- | --- | --- |
| 基线 | `BANK_TASK_TREE=<任务包>/baseline python hidden/runner.py` | 1 | **2 / 38** | `a6294c63da6b3149532a602a39bb4737bf9d29ca8f0b4b6723eb1b444881f47d`（两次相同） |
| 参考树 | 同一命令（`BANK_TASK_TREE=<任务包>/reference/tree`） | 0 | **38 / 38** | `acf67b9950f1641c77db5f349de7cecfa49fa0f76d393e6a723d7933dded80f5`（两次相同） |

- 38 条 = **T01–T23**（模型 / worker 核心行为）、**EN1–EN8**（入口：冒烟脚本、文档、README、全树 pytest、
  收集数）、**I1–I7**（接口与树形状：签名、AST 确定性、旧队列弃用、冻结文件、改动集合）；**反向用例 8 条**：
  T04 / T05 / T06 / T13 / T18 / T19 / T20 / T22。逐条的断言要点与反向构造见 `hidden/PLAN.md`。
- 两次输出的 sha256 是**载荷的函数**：依赖 `tree` 标签（= `BANK_TASK_TREE` 的仓库相对形式）与
  runner 的树形状常数（I7 的 `changed` 计数随基线集合变化，本批 3 → 4）。上表是 2026-10-22
  **H1 定点修后**用仓库相对路径复测的值；换一个标签或用旧常数，哈希就不同（那不是判定变化）。
  旧 14 文件基线的 `7941facf…` 与旧参考树 `3d216ebc…` 只留在 `reference/README.md` §3 的历史读数脚注里。
- 基线为什么只过 2 条：`EN7`（基线 pytest 本来就绿，是必要条件不是充分条件）与 `I6`
  （基线当然没动冻结文件）；其余 36 条因缺文件 / 缺语义而红。**起点红**是设计目标，不是缺陷。
- 契约：树只从 `BANK_TASK_TREE` 读、**只在副本上跑**（pytest / 冒烟 / 导入都在临时副本里，退出即删）、
  stdout 唯一 JSON、无时戳 / run id / 绝对路径、子进程 60 秒超时、exit 0 / 1 / 2。实测
  `BANK_TASK_TREE` 缺失与树不存在都退 **2**（判不了，不是 0 分）；运行前后基线组合摘要不变
  （`9739ecf0…`）=> 被评树一个字节没写。

### 9.2 参考树（`reference/tree/`）

- 21 文件 = 15 基线 + 6 新建；与基线的 diff **恰为 10 条允许写**（4 改 + 6 新建），基线 11 个冻结文件逐字节不变。
- `python -m pytest -q` → **22 passed**、exit 0（基线 4 passed + 1 skipped；参考树里 `tests/test_notify_smoke.py` 是行为测试，新增 7 + 9 + 1 个用例与新断言）。
- `python tools/notify_smoke.py` → exit 0，单行 JSON：
  `[{"key": "smoke-1", "kind": "email", "order_id": 1}, {"key": "smoke-2", "kind": "sms", "order_id": 2}]`。
- 决策点与踩到的坑见 `reference/README.md`（例如 A7 对**公开内嵌函数**也要 docstring、DOC-004 的 D401 会咬
  以 `action()` 开头的中文 docstring）。

### 9.3 A（`tools/structure_metrics.py`，schema 1.1）

命令：

```powershell
.venv/Scripts/python.exe tools/structure_metrics.py --workspace <reference/tree> --layers <task>/layers.yaml --interfaces <task>/interfaces.yaml --json
```

读数：**exit 0、10/10 pass**（A1–A10 全 pass）。关键计数：A1 违规边 0 / unresolved 0；A2 13 边 16 点 0 环；
A3 8 模块 20 个公开定义、超上限 0；A4 违规 0（默认装配 2 处计入证据）；A5 57 函数 0 超阈值；
A6 16 文件 57 函数 0 超长；A7 64 定义 0 缺失；A8 扇出 0 超阈值、unresolved 0；**A9 覆盖 8/8 生产文件**；
A10 动态 / 通配 import 0。**没有改 layers.yaml / interfaces.yaml 的任何阈值或声明来凑 A**——
两份声明的 sha256 与 `frozen_inputs` 一致（`5d7b37fc…` / `fad68482…`）。

### 9.4 C（8 次 `python -m policy.check`，`--operation edit` + 10 条 `--changed` + 固定 `--request-id`）

| 文件 | `--layer` | exit | decision | violations | skipped_rules | `blocking_capable_skipped` | complete |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `src/shop/notification.py` | service | 0 | `allow` | [] | `[ARCH-001@1]` | 1 | true |
| `src/shop/notify_model.py` | model | 0 | `allow` | [] | `[ARCH-001@1]` | 1 | true |
| `src/shop/notify_worker.py` | service | 0 | `allow` | [] | `[ARCH-001@1]` | 1 | true |
| `tests/test_notification.py` | test | 0 | `allow` | [] | `[ARCH-001@1]` | 1 | true |
| `tests/test_notify_model.py` | test | 0 | `allow` | [] | `[ARCH-001@1]` | 1 | true |
| `tests/test_notify_smoke.py` | test | 0 | `allow` | [] | `[ARCH-001@1]` | 1 | true |
| `tests/test_notify_worker.py` | test | 0 | `allow` | [] | `[ARCH-001@1]` | 1 | true |
| `tools/notify_smoke.py` | composition | 0 | `allow` | [] | `[ARCH-001@1]` | 1 | true |

- **没有 error 级（也没有 warning 级）violation**；每次 4 个 checker served
  （`failing_tests / missing_docstring / missing_tests / style_lint`），`ARCH-001` 因 `layer != controller`
  进 `skipped_rules`——**跳过不是通过**，这正是 C 的分母要按 `effective_total` 读的原因。
- C 计分：7 条适用规则 × 3 = **21** + 冻结文件未改 **3** + 无旁路 **3** = **27 / 27**
  （`effective_total = 27`；`ARCH-001` 的 3 分 `not_applicable`，不计分也不计分母）。
- 旁路三项也逐条实测：控制面目录（`policies/ registry/ validation/ adapters/ api/`）在参考树里都不存在；
  每个新测试文件 / M8 改写后的基线测试都有 assert（13 / 21 / 3 条）且无 `skip / skipif / xfail`；
  `--collect-only -q` 收集 **22** 条（≥7）；树 diff ⊆ 10 条允许写。

### 9.5 换算（与 40 / 30 / 30 同口径）

| 维度 | 读数 | 加权 |
| --- | --- | --- |
| T（参考树） | 38 / 38 | `round(40 × 38 / 38) = 40` |
| C（参考树） | 27 / 27 | C 按 passed/effective_total 读（27/27）；不折算成 30 |
| A（参考树） | 10 / 10 | 30 |
| T（基线，作对照） | 2 / 38 | `round(40 × 2 / 38) = 2` |

**这是 n=1 的案例读数**（一棵参考树、一台宿主）：它证明「38 条可过、A 可 10/10、C 可 0 error」，
不证明任何模型会达到，也不构成对照实验。

### 9.6 本批写面与 `coverage.md` 的关系

本批只改：`hidden/`（新增 PLAN + runner）、`reference/`（新增 README + tree）、`scoring.yaml`（T 冻结）、
`README.md`（本文）。**没有改 `coverage.md`**：它 §5 / §6 的「隐藏验收未写、全部未测」是**当时**的如实状态，
本批用本节取代那部分读数（此句就是取代关系的记录）。要改 coverage.md 需要按 05 §8 另记理由并重算它的
哈希，不在本批写面内。

**2026-10-22 另有一批构造变更**：基线 +1（`tests/test_notify_smoke.py` 静态契约测试）、里程碑 M1/M8
重排、`hidden/runner.py` 的树形状常数、`task-package/`、`scoring.yaml` 与本文 §3/§8.6/§9 的计数与摘要
同批更新；`coverage.md` 也补了该测试的证据形态（§2 的 `probe-async-m1-design`）。变更理由、改法与
A/B 实测见 §8.6。
