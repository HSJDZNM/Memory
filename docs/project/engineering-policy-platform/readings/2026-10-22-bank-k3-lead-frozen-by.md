# 2026-10-22 题库 k≥3 Lead 签字：最终 3 题的 T/C/A 判据冻结

> **性质**：Lead 对最终 3 题 `scoring.yaml` 的 `frozen_by` 签字记录（T/C/A 判据冻结），
> **不是**使用者签的「可开跑」。起点 HEAD `82139da` + 未提交签字改动；不跑 27 run。
> **判据来源**：`readings/2026-10-22-bank-k3-deliberations.md` §3.2/§3.3；`04-open-work.md` 5.92；
> 05 §8 第 11 条；`bank/README.md` §4.8。

## 0 一句话

最终 3 题（async / docs-config / crossmodule）的 `scoring.yaml` 的 `frozen_by` 由
`pending_lead_signature` 改为 `Lead`（2026-10-22）；**只冻结判据**，不冒充使用者签「可开跑」。
其余 2 题（bugfix / data-migration）保持 `pending_lead_signature`。

## 1 签字范围与值

| 题 | scoring sha256（签字后） | 冻结内容 | 备注 |
| --- | --- | --- | --- |
| bank-async-concurrency | `46c35cb07747a58f4789278065edacfddaf685761cdd58f3e2d163052b55ca23` | T 38 条（id 集不变）、C（effective_total 27）、A（10 谓词） | 2026-10-22 构造改造后；T 判据与 hidden 38/38 可复核 |
| bank-docs-config | `9c4737f309a4d61366dd925435d5a04d25d1db881fac9e74dbd930889e79c499` | T 40 条（id 集不变）、C（effective_total 27）、A（10 谓词） | 2026-10-22 构造改造后；T 判据与 hidden 40/40 可复核 |
| bank-crossmodule-refactor | `b955899b3eb79511a4aa99289484bd057f185df67efc3b610ef8a736911d6926` | T 34 条、C（effective_total 30）、A（10 谓词） | 未改造（负对照）；T 判据与 hidden 34/34 可复核 |

- 三份 `scoring.yaml` 的 `status: frozen` 不变；`frozen_by: Lead` 是**判据冻结人**。
- 改任一数值 = 换判据，必须同批重算 `frozen_inputs` 与 task-package manifest（本题未改数值，
  只改签字字段与相应说明文字；scoring 自身摘要随文本变化，见上表）。
- 两题（async / docs）的 `frozen_inputs` 已在构造改造后重算；crossmodule 未改造，
  其 `frozen_inputs` 与 hidden 摘要不变。

## 2 明确不表示什么

- **不表示「可开跑」**：发车许可仍由使用者签，签核读数要含 3 份 freeze 摘要、审批/题包 sha、
  TTL、Gate 0 与 H1 决定、H2 计划；`frozen_by: Lead` 只是判据冻结。
- 不表示 27 run 已具备条件：exp-set、臂配置、最小 bank run-record、re-smoke 等仍未完成。
- 不表示 hidden 作者独立性成立：H1 仍是降级形态（同一子会话写 hidden + reference），
  第三方逐条复核是另一件事（Gate 0 通过后才排期）。

## 3 其余题的状态

- bank-bugfix-first-failing-test / bank-data-migration：`frozen_by` 仍 `pending_lead_signature`；
  它们不在最终 3 题里，不签。
- 旗舰：`frozen_by` 已是 `Lead`（2026-10-21 冒烟包），不在本轮重新签。

## 4 证据指针与下一步

- 三份 scoring：`testing/ab/bank/tasks/<task>/scoring.yaml`（`frozen_by: Lead`）。
- 判据与结构：各题 `hidden/PLAN.md`、`hidden/runner.py`、`README.md` 的「天花板读数」节。
- Gate 0：`readings/2026-10-22-bank-k3-gate0-rerun.md`（通过）。
- 下一步（§5.3 剩余）：3 份 per-task exp-set、臂配置 token 化、最小 bank run-record/T-C-A 采集器、
  freeze `--write/--check --strict` ×3、scaffold 9 树、P1–P6 探针、dry-run、1 臂 re-smoke；
  然后请使用者重签 4 条审批（每臂 2 条 union、TTL 7 天）并签「可开跑」。
