# 2026-10-22 题库 k≥3 Gate 0 重跑（构造改造后）

> **性质**：离线、无模型、无真机会话的 Gate 0 重跑（C1-b §3.3 方法）。构造改造后的读数；
> 起点 HEAD `614c2ad` + 未提交的两题改造；只写 `.tmp` 与本读数；**不改判据、不跑 27 run、不签可开跑**。
> **背景**：改造前的 Gate 0 未过（`readings/2026-10-22-bank-k3-gate0-activation.md`）；使用者拍板
> 选择 1「按 C1-b §7.3 回构造」。本轮改造见 §1，重跑判定见 §4。

## 0 一句话

async 与 docs-config 各加一条**基线静态契约测试**、把工具写步提前到 M1；重跑 Gate 0：
**async 激活、docs-config 激活、crossmodule 无激活（负对照成立）、data-migration 无激活**。
被选 3 题设计方向激活 **2/3** → **Gate 0 通过**；不替换，进入 §5.3（签核/27 run 的前置）。

## 1 构造改造（只动两题；最终树逐字节不变）

- **bank-async-concurrency**：`baseline/` 14→15，新增 `tests/test_notify_smoke.py`（静态契约测试：
  工具文件不存在时 `pytest.skip`；存在时检查 `main()` / `__main__` / 只读）。M1 改写为
  「写 `tools/notify_smoke.py`」；原来的「M7 写测试」改为「M8 把基线静态契约测试改写为行为测试」。
  `reset-arm.py`、first-message/milestones/acceptance、SPEC/interfaces、layers、hidden、scoring、
  README/coverage 同批更新；`reference/tree` **0 改动**。
- **bank-docs-config**：`baseline/` 13→14，新增 `tests/test_check_config.py`（同形静态契约测试）。
  M1 改写为「写 `tools/check_config.py`」；原来的「M4 写测试」改为「M5 改写基线静态契约测试」；
  同批更新其余文件；`reference/tree` **0 改动**。
- **机制**：M1 是本次会话的**第一个写动作**，批为空；A（`tools` 非生产文件）的 changed 里没有测试，
  `selection.level=none`、`failing_tests` 未被服务 → `TESTING-002` block；B（`tools` 是生产文件）
  按 stem 选到基线同名测试 → 跑通 → allow。这正是 C1-b §7.3 的设计方向；改造前的 v1 里，
  T3 的批次把模型自己写并结算的测试带进 changed，A 也选得到测试，所以设计方向消失。
- **最终树不变**：两题 `reference/tree` 的 git 改动为 0；参考树 hidden 分别 **38/38、40/40**；
  基线 pytest 分别 **4 passed + 1 skipped**、**3 passed + 1 skipped**（skip 的是静态契约测试）。
- **隐藏件只改常数/清单/注释**：id 与总数不变（38 / 40）；scoring 只改 `frozen_inputs` 与计数文本；
  `frozen_by` 仍是 `pending_lead_signature`（Lead 签字是 §5.3 的另一件事）。

## 2 方法与输入

- **T3 配置**：A 读 `testing/ab/dgate2/configs/before`，B 读 `configs/after`；唯一差异仍是
  `validation/test-layout.yaml` 的 `production_patterns`（B 加 `tools/**/*.py`）。
- **离线复现**：`python -m policy.check`；每臂一棵树 + 自己的 settled 集；只有
  `{allow, allow_with_warnings}` 的写落地并进 settled；每步 `--changed` = 本步目标 + 该臂 settled
  （T3 批成员）；被 block 的写不落地、不进批。
- **序列**：改造后的 milestones（M1 工具 → 其余写步 → 测试改写步）；内容取 `reference/tree`。
- **判据面**：`decision` / `violations` / `served_checkers` / `selection.level` / `nodeids`；
  设计方向 = `B_more_permissive`（A block / B allow）。
- **证据**：`.tmp/k3/gate0-v2/probe_v2.py`（复用 v1 脚本、只替换两题的新序列）与
  `.tmp/k3/gate0-v2/results.json`；v1 现场 `.tmp/k3/gate0` 保留。`.tmp` 是一次性现场（cleanup 会删）。

## 3 逐题读数（主序列）

### 3.1 bank-async-concurrency（激活）

| 步 | A | B | 差异 |
| --- | --- | --- | --- |
| M1 `tools/notify_smoke.py` | **block**（`TESTING-002`，level `none`，`failing_tests` 未 served） | **allow**（level `related`，nodeids=`tests/test_notify_smoke.py`） | **decision + violations + served + level + nodeids；B 更宽（设计方向）** |
| M2–M7 的写步 | 全部落地 | 全部落地 | 仅 level/nodeids 的差异（同 decision），不改变判定 |
| M8 `tests/test_notify_smoke.py`（改写） | allow_with_warnings（level `related`） | allow（level `related`） | decision 不同（B 更宽；次级） |

**结论：激活**（M1 的设计方向；M8 是次级差异）。M1 的 `tests_only` / `solo` 对照同为
A block / B allow；`reverse_order` 两臂都 block（同 decision，差异在 violations/level）。

### 3.2 bank-docs-config（激活）

| 步 | A | B | 差异 |
| --- | --- | --- | --- |
| M1 `tools/check_config.py` | **block**（`TESTING-002`，level `none`，`failing_tests` 未 served） | **allow**（level `related`，nodeids=`tests/test_check_config.py`） | **decision + violations + served + level + nodeids；B 更宽（设计方向）** |
| M2–M4 | 全部落地 | 全部落地 | 仅 level/nodeids |
| M5 `tests/test_check_config.py`（改写） | **block**（工具未落地，测试 import 失败） | **allow** | decision 不同（B 更宽；次级） |

**结论：激活**（M1 的设计方向；M5 是次级差异）。

### 3.3 bank-crossmodule-refactor（负对照）

13 个写步 A/B 全同（M6a 两臂 `allow_with_warnings`，其余 allow）；无 `tools/` 写面。
**结论：无激活（负对照成立）**。

### 3.4 bank-data-migration（未入选，仅核对）

14 个写步 A/B 全同（M5b/M7b 双 allow）。**结论：无激活**（未入选，不影响本轮判定）。

## 4 Gate 0 判定

| 题 | 结论 | 关键证据 |
| --- | --- | --- |
| bank-async-concurrency | **激活** | M1：A block `TESTING-002` / B allow，B 更宽 |
| bank-docs-config | **激活** | M1：A block `TESTING-002` / B allow，B 更宽 |
| bank-crossmodule-refactor | 无激活 | 13 步全同（负对照） |
| bank-data-migration | 无激活 | 14 步全同 |

按预注册（`readings/2026-10-22-bank-k3-deliberations.md` §3.1）：

1. **≥2 个被选题出现设计方向激活**：2/3（async + docs） → **满足**。
2. **async 无激活即停**：async 是激活 → 不命中。
3. **crossmodule 必须无激活（负对照）**：成立。
4. **替换**：不需要（docs 已激活；migration 不入选）。

**判定：`gate0_pass=true`。** 不替换；下一步是 §5.3 的签核与 27 run 前置（不是直接跑 27 run）。

## 5 边界（引用前先读）

- 这是**离线探针**，不是 Hook/真机会话；它证明「里程碑序列上 treatment 会改变判定」，
  不证明模型会按这条序列走，也不证明效应大小。
- A 在 M1 被 block 后模型可能改道/重试；探针不模拟这些行为。激活本身是**一次真实写序列**的读数。
- 最终树的目标内容没有变（`reference/tree` 0 改动），hidden 的 id/总数没变；改的是基线里的
  一条静态契约测试、里程碑顺序与相应哈希。
- 构造改造前的 v1 读数保留为历史（`readings/2026-10-22-bank-k3-gate0-activation.md`），不重写。
- **不把 Gate 0 通过读成「treatment 有效」**：下一步仍是 §5.3 签核、27 run 与预注册判定。

## 6 复现

仓库根、`PYTHONPATH=src`：

```powershell
.venv/Scripts/python.exe .tmp/k3/gate0-v2/probe_v2.py
```

- 输出：`.tmp/k3/gate0-v2/results.json` + 逐题 A/B 树；脚本复用 `.tmp/k3/gate0/probe.py` 的判定函数，
  只替换 async / docs 的新写序列；v1 现场不动。
- 两题的基线/参考树重置与 T 复算：各题 `reset-arm.py --dry-run`；
  `BANK_TASK_TREE=<task>/reference/tree python <task>/hidden/runner.py`（38/38、40/40）。

## 7 证据指针

- 改造前：`readings/2026-10-22-bank-k3-gate0-activation.md`（v1 未过；保留）。
- 预注册：`readings/2026-10-22-bank-k3-deliberations.md` §3.1；`05-implementation-plan.md` §8 第 11 条。
- 两题改造：各题 `README.md` 的「构造变更」节、`task-package/{first-message,milestones,acceptance,interfaces}.md`、
  `baseline/tests/test_{notify_smoke,check_config}.py`、`hidden/PLAN.md`、`scoring.yaml`。
- 探针现场：`.tmp/k3/gate0-v2/{probe_v2.py,results.json}`；v1 现场 `.tmp/k3/gate0/`（一次性）。
