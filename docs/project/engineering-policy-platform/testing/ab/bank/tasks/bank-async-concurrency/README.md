# bank-async-concurrency（并发 / 异步题型：同步通知队列 → 确定性 asyncio 工作队列）

> **它是什么**：题库 5 道题型题之一——在既有订单示例项目上把同步 `NotificationQueue` 升级成
> **确定性的 asyncio 工作队列**：有界队列、按 key 幂等去重、可取消、停机排空、异常不吞。
> 跨 model（`Notification`）与 service（`NotificationWorker`）两层，含一个冒烟脚本、3 个同名
> 测试文件、1 篇文档；旧队列保留并标注弃用。
> **冻结状态**：**pending_hidden**——基线、任务包、reset-arm、A 维度声明、C/A 判据
> 已落盘；**T 维度未冻结**（`scoring.yaml` 的 `dimension_t.status: pending_hidden`、
> `total: null`、`case_ids: []`、`planned_min_total: 30`）。隐藏验收代码、参考解、天花板实测
> **都还没有做**（见 §7）。
> **用法**：Lead 重置基线 → 以任务树为 cwd 起受治会话 → 首消息 = `task-package/first-message.md`；
> 跑完后按 `acceptance.md` + 隐藏验收（下一批）+ 树 diff 判分。

## 1 基线（14 文件；只读，除允许写集合里的 3 个）

| 组 | 文件 | 来源 |
| --- | --- | --- |
| 订单示例项目（11） | `AGENTS.md`、`README.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_controller.py`、`src/shop/order_repository.py`、`src/shop/order_service.py`、`tests/test_order_controller.py`、`tests/test_order_repository.py`、`tests/test_order_service.py` | `bank-flagship-returns/baseline` 的同名 11 文件，**逐字节复制**（与 `examples/dsh/b-plan/sample-project` 的 11 文件亦逐字节相同） |
| 脚本包（1） | `tools/__init__.py`（顶层包标记；只有一行模块 docstring） | `bank-flagship-returns/baseline/tools/__init__.py`，**逐字节复制**（sha256 `f66ec0041ebb636c9fdee98ff706cda2ef04ca40474f79b84027e1e0cb3618eb`） |
| 同步通知队列（2） | `src/shop/notification.py`（`NotificationQueue`：`append` / `pop` / `__len__`）、`tests/test_notification.py` | 本包构造 |

- **基线组合摘要**（按相对路径排序的 `<sha256>  <relpath>` 清单文本再 sha256，算法与
  `a3-task-v3/reset-arm.py` 的 `_manifest_sha256` 相同）：
  **`d12576d82488d3665ea38bacdb6b1a32e23b08caa979f316ca6ba07aadb581e8`**（14 文件）。
- 基线起点干净：`python -m pytest -q` → **4 passed**（本包已在 14 文件基线副本上实测，退出码 0）。
- **基线里没有**（= 任务要求模型创建的 7 个文件）：`docs/async.md`、`src/shop/notify_model.py`、
  `src/shop/notify_worker.py`、`tests/test_notify_model.py`、`tests/test_notify_smoke.py`、
  `tests/test_notify_worker.py`、`tools/notify_smoke.py`。`reset-arm.py` 会拒绝这 7 个文件出现在基线里。
- **第 14 个文件 `tools/__init__.py` 是 Lead 裁定的构造修复**：初版 SPEC §2 的 13 文件表没有它，导致
  M7/M8 双向阻断（先写 smoke 测试被 TESTING-002 拦、先写脚本被 TESTING-001 拦）；加入后 `tools` 是树里的
  顶层包，先写 smoke 测试走「待实现」。它**不是**任务要创建的文件、**不进允许写集合**、属于冻结不动的基线。
  修法、实测读数与它在 A 维度里的层（显式 `skip`）见 §8.1。

## 2 允许写 10 路径

`task-package/allowed-writes.txt`（字母序）：

`README.md`、`docs/async.md`、`src/shop/notification.py`、`src/shop/notify_model.py`、
`src/shop/notify_worker.py`、`tests/test_notification.py`、`tests/test_notify_model.py`、
`tests/test_notify_smoke.py`、`tests/test_notify_worker.py`、`tools/notify_smoke.py`。

**允许写集合 ∩ 基线 = 3 个**（`README.md`、`src/shop/notification.py`、`tests/test_notification.py`）；
因此**冻结不动的基线文件 = 14 − 3 = 11 个**：
`AGENTS.md`、`conftest.py`、`pytest.ini`、`src/shop/__init__.py`、`src/shop/order_controller.py`、
`src/shop/order_repository.py`、`src/shop/order_service.py`、`tests/test_order_controller.py`、
`tests/test_order_repository.py`、`tests/test_order_service.py`、`tools/__init__.py`。

（SPEC §3 原小标题写「允许写 9 路径」，与本包清单的 10 条矛盾；本轮已把 SPEC 标题与正文改成 10 条，
`allowed-writes.txt`、`scoring.yaml` 与本文三处一致。）

## 3 冻结哈希（脚本实算，不是手抄）

| 路径 | sha256 |
| --- | --- |
| `task-package/first-message.md` | `748f48ab2c11f463adf534df50f89ac5b69b427842960727294ab3d4935ada63` |
| `task-package/interfaces.md` | `9e11ef39b1539f7a2a4d33c2d284a6388dc89f156f958d017e19d5d13e0f10e5` |
| `task-package/acceptance.md` | `928cd817addf523c3f5041bc7a5fc6e47890724d73dacf8dd3fb7cc929e78636` |
| `task-package/allowed-writes.txt` | `1ad69cf570a6e0ccc20ec4dcd65727e195e12ded62570ae3f0b3cbbb22689a9f` |
| `task-package/milestones.md` | `134834c0061883f454d8a977c7af495eb29be742bb1bcebedd4caa9e3b63c2d5` |
| `task-package/manifest.sha256` | `58a5965ef36caac6a05c5f5918e23372dfbf25e642eb158d818c83d3e7016be7`（5 行，覆盖前 5 文件；它与组合摘要同值——清单文本就是被哈希的字节） |
| `reset-arm.py` | `157e2e080d1282ac0fa094c7cdab7bd04a1bd4e330e22d9c32ad120ad99f3ebf`（不在 manifest 里；它只冻结基线） |
| `layers.yaml` | `ba97221e9e42592d92191629c1f95994386046e57789730997277f7fb0a9ecf3` |
| `interfaces.yaml` | `fad6848215cdc0567619e6ccec334904eca76a4c2c929b8bdd04849883ecdeb4` |
| `scoring.yaml` | `a32a41b711139c4ee66f983a0415d48a908520e728be603805ce8d061ff6e31a`（自指摘要不写进自己；本行由构建时现算，freeze.json 另记） |

复核：对 `task-package/` 的前 5 个文件各算一次 sha256，与 `manifest.sha256` 的 5 行逐行比对
（本包构建时 **5/5 ok**；任一不符 => 该 run 作废）。

## 4 怎么用（Lead）

```powershell
# 0) 看计划 / 重置（目标树默认 .tmp/bank-async-concurrency/tree，14 文件；不预置任何任务文件）
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
# 3) 以任务树根为 cwd 起受治会话；首消息 sha256 必须等于 748f48ab2c11f463adf534df50f89ac5b69b427842960727294ab3d4935ada63
```

首消息复核：`first-message.md` 的 sha256 期望 `748f48ab2c11f463adf534df50f89ac5b69b427842960727294ab3d4935ada63`。

## 5 直接可触发规则点（本题的真实岔口）

**证据等级**：`实测` = 本包构建时在基线副本 + 构造变异上用真 `policy.check` 跑出来的 decision
（逐条读数见 `coverage.md` §2）；`规则数据` = 只核对了规则 YAML/配置、**没跑**；`未测` = 没跑。

| 规则 ID | checker | 级别 | 本题触发步骤 | 期望 decision | 证据等级 |
| --- | --- | --- | --- | --- | --- |
| TESTING-001 | missing_tests | error | 新建 `src/shop/notify_model.py` / `notify_worker.py` / `tools/notify_smoke.py` 却不带同名测试 | `block`（error） | **实测**：新建 `notify_model.py` 无测试 → `block`（violations=[TESTING-001]）；新建 `tools/notify_smoke.py` 无测试 → `block` |
| TESTING-002 | failing_tests | error | 异步用例写错/相关测试失败（真失败，不是「待实现」） | `block`（error） | **实测**：子进程驱动、脚本缺失 → `block`（violations=[TESTING-002]，`probe-async-p4b-tools-test-subprocess`）；模块级 import 的 smoke 测试在基线修好后走 pending（见本表最后一行） |
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
| TESTING-002 的 pending 通道 | failing_tests | error（规则）/ warning（findings） | 先写 `tests/test_notify_model.py` / `tests/test_notify_smoke.py` 而实现缺失（`shop` / `tools` 顶层包都已在树里） | `allow_with_warnings` + `pending_findings` | **实测**：两种形态都 → `allow_with_warnings`、`pending_findings=[TESTING-002]`、`violations=[]`（`probe-async-p3-pending` / `probe-async-m7-tools-pending`） |

## 6 本题的读法（不是「跑完就算」）

- **四个维度分开读**：T（任务完成；隐藏用例**未写**，`total` 未冻结）、C（规则遵守；`scoring.yaml` 的
  8 条 + 冻结文件 + 旁路）、A（结构；`layers.yaml` / `interfaces.yaml` + `tools/structure_metrics.py`）、
  过程（平台账本：被拒动作、原因码、`matched / skipped / served_checkers`）。**不许把过程读数折算进 T/C/A**。
- **`allow_with_warnings` 不是失败、也不是通过**：M1/M3 的「待实现」走 `pending_findings`
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
| `baseline/` | 14 文件基线树（逐字节；含与旗舰逐字节相同的 `tools/__init__.py`） | **已落盘**（组合摘要可复核；pytest 4 passed） |
| `reset-arm.py` | 逐字节重置 + 摘要校验 + reset-manifest.json | **已实测**（dry-run + 真跑 14/14；三种前置失败都退出 1） |
| `layers.yaml` / `interfaces.yaml` | A 维度声明（最终树 21 文件 → 层；非测试模块公开面上限） | **已写**；`structure_metrics` 加载通过，**基线副本 A1–A10 全 pass**（A9 5/5；`tools/__init__.py` 显式 `skip` 移出测量范围，理由见 §8.1）；7 个新建文件未落盘 → 声明为 unmatched；**最终树读数未测**（替身树只验证了 A9 的包初始化器口径：7/7，见 §8.1） |
| `scoring.yaml` | C/A 判据（已冻结）+ T 维度（pending_hidden） | **已写**（`total: null`、`case_ids: []`、`planned_min_total: 30`） |
| `coverage.md` | 43 条规则点 ○/—、A1–A10、隐藏行为面、实测读数 | **已写**（未实测项如实标未测） |
| `hidden/` | 隐藏验收代码 + PLAN + runner | **未做**（下一批独立子会话；T 因此未冻结） |
| `reference/` | 参考解（模块/接口/决策点 + 实现） | **未做** |
| 天花板实测 | 参考解上的 T/C/A 上限 | **未做** |

## 8 边界与已知构造问题（引用本包前必须读）

### 8.1 `tools/__init__.py` 与 M7/M8 的先后阻断（**已按 Lead 裁定修复**）

初版冻结包的 SPEC §2 列了 13 个基线文件，**不含 `tools/__init__.py`**；在 `pre_evidence` 开启的
默认治理下，这造成一个**双向阻断**（两个方向都在真 `policy.check` 上实测过，读数留在
`coverage.md` §2 的 `p4` / `p4b` / `p5` 三行）：

- 先写 `tests/test_notify_smoke.py`（模块级 `from tools.notify_smoke import main`）→ 顶层包 `tools`
  不在树里 → **不是** `pending_implementation`，而是真收集失败 → `block`（TESTING-002）；
- 先写 `tools/notify_smoke.py` → 没有同名测试 → `block`（TESTING-001）。

**Lead 裁定（本包已执行）**：基线加 `tools/__init__.py`，**13 → 14 文件**。该文件从
`bank-flagship-returns/baseline/tools/__init__.py` 逐字节复制（sha256
`f66ec0041ebb636c9fdee98ff706cda2ef04ca40474f79b84027e1e0cb3618eb`），**不进允许写集合**，
属于冻结不动的基线（`scoring.yaml` 的 `frozen_untouched` 因此从 10 个变 11 个）。任务要创建的文件
清单、允许写 10 条、里程碑顺序都不变；SPEC §2、`reset-arm.py`、`task-package/`、scoring 与本文的
文件数/摘要已同批更新。

**修后实测**（真 `policy.check`；`--workspace` = 14 文件基线 + 一份 `tests/test_notify_smoke.py`，
`--operation create`、`--layer test`、`--changed tests/test_notify_smoke.py`、固定 `--request-id`）：
`allow_with_warnings`、`violations=[]`、`pending_findings=[TESTING-002]`、
`pending_implementation[0].missing_targets=["tools.notify_smoke"]` —— M7 的「先写测试」现在走
「待实现」通道（AGENTS 第 51 条），M8 再把实现落地；**反向顺序**（先写 `tools/notify_smoke.py`
而不写测试）仍是 TESTING-001 `block`；子进程驱动、脚本缺失的用例仍是真失败 → TESTING-002 `block`。

**A 维度声明：`tools/__init__.py` 显式移出测量范围（`skip`，不是漏声明）**。理由是实测出来的：

- 按与旗舰同形的 `other` 声明测量**冻结基线**，A9 报 1 条 `tools/__init__.py: no_test_import`
  （基线里没有任何测试 import `tools.*` 子模块）→ 基线 A1–A10 只有 9/10；
- 而本题 A 读数以「基线 + 最终树都 A1–A10 全 pass」为冻结口径，因此按 Lead 裁定的备选
  （「若实测 A9 不成立，可改 skip」）改成 `skip`，并在这里与 `coverage.md` §4 **写明是显式移出**；
- 代价与补偿：它只有一行模块 docstring，不参与 A3 / A7 / A9 / A10 的统计；tools 的实质写面
  `tools/notify_smoke.py` 仍在 composition 层、仍被 A9 要求由 `tests/test_notify_smoke.py` 静态 import；
- 口径本身也实测过：在「14 文件基线 + `tools/notify_smoke.py` + import 它的测试」替身树上，
  `other` 声明得到 A9 7/7 pass、A1–A10 10/10（替身树只在 `.tmp/`，不随包交付）。
- **本轮独立复核**（同一替身树 16 文件、本包现行 `layers.yaml` / `interfaces.yaml`）：基线组合摘要重算
  `d12576d8…` 一致；`task-package/manifest.sha256` 5/5 逐行相符；`reset-arm.py --dry-run` exit 0；
  `structure_metrics` → 10/10 pass、exit 0（`declared_unmatched` 5、`undeclared` 空）。

### 8.2 SPEC 内部数字冲突（本包的选择）

| SPEC 处 | 两种读法 | 本包选择 | 理由 |
| --- | --- | --- | --- |
| §2「基线（14 文件…）」vs `bank/README.md` §1（原）与派单说明的「12 文件」 | 12 / 14 | **14**（11 订单项目 + 1 脚本包 + 2 同步队列） | SPEC §2 初版是 11+2=13；Lead 裁定加 `tools/__init__.py` 后为 14，§2 的表与标题已同批更新（§8.1）；本轮已把 bank/README §1 改为 14 |
| §3「允许写 9 路径」vs 同段清单 10 条 + 「共 10」 | 9 / 10 | **10** | 清单逐条可执行；本轮已把 SPEC 标题与正文改成 10 条（三处一致） |
| `bank/README.md`（原）「12 文件 / 5 新建 / 3 修改」vs 实际 | 12 / 14 | **14 文件、7 新建 + 3 修改 = 10** | 按 `baseline/` 14 文件与 `allowed-writes.txt` 10 条复算；本轮已同批修正 bank/README §1 |

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
- **改它 = 改构造**：任何改动（哪怕一个字节）都要按 05 §8 记录理由与回退，重新生成
  `task-package/manifest.sha256` / 基线摘要 / 本文件 §3 的哈希表；冻结后逐文件哈希不符 => 该 run 作废。
- **本包不声称已激活任何 treatment**：本题 SPEC 未给 A/B 臂（`scoring.yaml` 的 `treatment.arms` 为空）。
- **不跑真机会话、不 commit**：本包落地时只做了只读/本地验证（pytest、policy.check 探针、reset-arm、
  structure_metrics、哈希、文本规范）。
