# 2026-10-21 题库七项裁决（Lead 落成文本）

> **性质**：裁决记录 + 执行状态。来源 = 交接提示词 §3.4（2026-10-21 18:00 后接力的七项判定）。
> 本文**不产生新实验数据**，只把「已定的七件事」写成可引用、可复核的文本，并标明哪些还没落地。
> **依据**：`bank/README.md` §6 的七个待裁点、05 §5（读数纪律）、AGENTS 第 45/50/55 条。

## 0 一句话

题库冻结的七个待裁点全部落定：**每题独立冻结 `scoring.yaml`**（共享 T/C/A=40/30/30；T 记「通过数/48 + 加权分」）、
**修 bug 题接受「一次完整修复」**（不关 `pre_evidence`）、**旗舰 `data/refunds-v2.jsonl` 算树内允许写**、
**隐藏代码由每题独立子会话写且不得读 `reference/`（PLAN 与代码分两轮）**、**审批用 b-plan 本地 13 条 + 三族**、
**冻结顺序 = PLAN → 隐藏代码 → 参考解 → 实测天花板 → 签「可开跑」**、**题库索引更新留给 Lead**。

## 1 七项（问题 → 裁决 → 理由）

| # | 问题（`bank/README.md` §6） | 裁决 | 理由 |
| --- | --- | --- | --- |
| 1 | 评分器扩展方式：每题复制 vs 共享 | **每题独立冻结 `scoring.yaml`**；共享的 T/C/A=40/30/30 骨架照抄；**T 记「通过数/48 + 加权分」** | 独立复制边界清楚（改一题不污染另一题）；共享会新增一个载荷轴并要重跑一致性（§7） |
| 2 | 修 bug 题的「死锁读数」（红测试让中间态被 TESTING-002 拦） | **接受「一次完整修复才能过」**；不关 `pre_evidence`；中间态阻断写进过程读数 | 关取证 = 38 条规则进 `skipped_rules`，等价于不测证据面（选项 ③ 被否） |
| 3 | 旗舰 `data/refunds-v2.jsonl` 是否算树内允许写 | **算**（迁移产物留在树里） | 保留「在树里真的跑过迁移」的证据；隐藏 runner 仍在副本上跑 |
| 4 | 隐藏代码由谁写 | **每题一个独立子会话**，按 PLAN 写；**不得读 `reference/`**；PLAN 与代码分两轮 | 独立出题；Lead 只运行与复核（H1 同一口径） |
| 5 | 审批条子与命令族 | **`examples/dsh/b-plan/tool-registry.local.yaml`（13 条）+ `--family tests/scripts/readonly`**；建议 `--max-uses 1000 --ttl 86400`；run-manifest 记 `approval_sha256` 与族清单 | 题面命令含 `Get-Content`/`Select-String`/`Test-Path`，仓库 7 条覆盖不到；条子只由使用者签 |
| 6 | 何时签「可开跑」 | **顺序 = 签 PLAN → 隐藏代码 → 参考解 → 实测 T/C/A 天花板 → 签「可开跑」** | 天花板没实测就签字，等于不知道判据可满足；冻结顺序本身是一次判据 |
| 7 | 题库是否挂到 `testing/ab/README.md` 索引 | 本轮不写；**留给 Lead** | 索引更新会动共享文件，与逐题包解耦 |

## 2 执行状态（截至本文）

| # | 状态 | 证据 / 指针 |
| --- | --- | --- |
| 1 | **未落盘**：`scoring.yaml` 尚未写（T 的逐条权重表也未定；本裁决只定分母 48 与口径） | `bank/README.md` §4.8；本文件 §3 第 1 条 |
| 2 | 已接受；实现约束写进题库题面（修 bug 题 SPEC） | `tasks/bank-bugfix-first-failing-test/SPEC.md` |
| 3 | 已写进旗舰题面与允许写集合 | `tasks/bank-flagship-returns/task-package/allowed-writes.txt`（19 条含 `data/refunds-v2.jsonl`） |
| 4 | **旗舰已完成**：`hidden/runner.py`（48 条）+ `reference/tree/`（30 文件），同一独立子会话写、未读 `reference/`；Lead 复核 48/48、双跑同字节、基线 2/48 | `hidden/README.md`、`2026-10-21` 的交付读数（06 P-MNT-008） |
| 5 | 待 T0 装配：每臂复制 b-plan 本地注册表 + 审核 + 使用者签条子 | 交接提示词 §4.3；`readings/2026-10-21-experiment-freeze-adjudication.md` §2.5 |
| 6 | 前 3 步已做（PLAN 冻结、隐藏代码、参考解）；**天花板未测**，因此**尚未签「可开跑」** | 旗舰 `README.md` §3 与 `reference/README.md` §3 |
| 7 | 未做 | `testing/ab/README.md` |

## 3 未决与边界

1. **T 的「加权分」怎么加**：本裁决只给「通过数/48 + 加权分」的口径，**逐条权重表**必须在每题 `scoring.yaml` 里显式写下；
   没有权重表的 `scoring.yaml` 不算冻结。这里不替它编一个权重表。
2. **`scoring.yaml` 与 dgate2 的 `scorer.yaml` 不是同一份载荷**：前者是题库每题自己的判据（含 48 条 T 与 A/C 说明），
   后者是 dgate2 的冻结评分器（version 3）；两者各自建轴、互不复制字节。
3. **「一次完整修复」是构造约束，不是判据放宽**：中间态被拦仍记过程读数；T 只读最终树。
4. 本文件不覆盖题库其余 5 题的冻结包（只有 SPEC）；也不覆盖 A/B/C 臂与真机 run。

## 4 证据指针

- `docs/project/engineering-policy-platform/testing/ab/bank/README.md` §6（七个待裁点）与 §8（交付边界）
- `tasks/bank-flagship-returns/hidden/README.md`（作者独立性声明与读数）
- `tasks/bank-flagship-returns/README.md`（冻结状态与目录地图）
- `docs/project/engineering-policy-platform/readings/2026-10-21-experiment-freeze-adjudication.md` §2.5（部署复制与重审）
