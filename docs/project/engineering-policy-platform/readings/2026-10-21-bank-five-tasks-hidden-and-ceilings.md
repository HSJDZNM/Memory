# 2026-10-21 题库其余 5 题隐藏验收、参考解与天花板

> **性质**：实现 + 实测读数（Lead 复核）。起点 HEAD c5e607e（收口与提交之后）+ 未提交的 5 题 hidden/reference。
> **范围**：只写 5 个题型任务目录（bank-crossmodule-refactor / bank-bugfix-first-failing-test /
> bank-data-migration / bank-async-concurrency / bank-docs-config）与 .tmp 一次性现场；
> **不改** src/**、examples/**、registry/**、dgate2 冻结件、bank/harness、旗舰题。
> **纪律**：n=1 的天花板只作案例；不写 treatment 效果、不写「值得扩试」；k≥3 未跑。

## 0 一句话

5 题各自由一个独立子会话按 SPEC 先写 hidden/PLAN.md 与 hidden/runner.py、再写 reference/tree 与 reference/README.md；
Lead 独立复核：每题基线红、参考树 T 全过、pytest 全绿、C 0 error violation（effective_total 27 或 30）、A 10/10。
T 已在各题 scoring.yaml 冻结（total 34/38/40/38/40）；**「可开跑」签字与 k≥3 未做**。

## 1 方法

1. 每题独立子会话：先写 hidden/PLAN.md（>=30 条，T/EN/I 分组 + 反向构造），再写 hidden/runner.py（契约同旗舰：
   BANK_TASK_TREE 传树、只在副本上跑、stdout 唯一 JSON、exit 0/1/2、60s 超时、无绝对路径/时戳/run id），
   跑基线红并做两次逐字节比对，然后写 reference/tree 与 reference/README.md，最后实测 T/C/A。
2. 写 hidden 时本题 reference/ 尚不存在；没有读旗舰 reference/ 或其它题 reference/。
3. Lead 复核（不采信子会话自报）：在**交付的 reference/tree** 上直接跑 hidden（不先跑 pytest，避免污染树）、
   在基线上跑 hidden、跑 pytest、structure_metrics、对 dimension_c.file_set 逐文件跑 policy.check；
   并核对 scoring.yaml 的 total / case_ids 与 runner 实际 id 集合相等、hidden 摘要实算一致、树无缓存残留。

## 2 逐题读数（Lead 复核，2026-10-21）

| 题 | PLAN | T 基线 | T 参考树 | pytest | C（effective） | A | T 加权 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bank-crossmodule-refactor | 34 | 4/34 | 34/34 | 8 passed | 30/30 | 10/10 | 40 |
| bank-bugfix-first-failing-test | 38 | 21/38 | 38/38 | 9 passed | 27/27 | 10/10 | 40 |
| bank-data-migration | 40 | 2/40 | 40/40 | 19 passed | 27/27 | 10/10 | 40 |
| bank-async-concurrency | 38 | 2/38 | 38/38 | 22 passed | 27/27 | 10/10 | 40 |
| bank-docs-config | 40 | 2/40 | 40/40 | 18 passed | 27/27 | 10/10 | 40 |

- C 的 27 = 规则段 7×3（ARCH-001 在四题结构性不适用，not_applicable 不计分不计分母）+ 冻结文件 3 + 无旁路 3；
  crossmodule 的 file_set 含 controller，ARCH-001 适用，C = 8×3 + 3 + 3 = 30。
- 每题 8 个 checker / 规则集在参考树上均无 error 级 violation；ARCH-001 在非 controller 文件上进 skipped_rules
  （blocking_capable_skipped=1），**不读成通过**。
- 基线红是构造（这些题的 SPEC 就要求先有失败/多步改动），不是环境故障；两次运行 stdout 逐字节相同。
- 运行 hidden 前后参考树摘要不变；交付树无 __pycache__ / .pytest_cache。

## 3 冻结记录

- 各题 scoring.yaml：顶层 status=frozen、frozen_by 仍 pending_lead_signature（**只冻结 T，不冒充 Lead 签字**）；
  dimension_t.status=frozen、total 见上表、case_ids 与 runner 的 CASE_IDS 集合相等、freeze_note=null、
  planned_min_total=null；frozen_inputs.hidden_plan_sha256 / hidden_runner_sha256 为实算值。
- 题任务包 manifest、baseline、layers.yaml、interfaces.yaml 都未改（哈希与 pending 版一致）。
- 本题评分器轴仍是 bank-scoring/2；判据数值（T 分母、C 规则与 effective_total、A 10 谓词）一个字未改。

## 4 作者独立性与边界（引用前先读）

- **降级形态**：5 题的 hidden 与 reference 由同一子会话按顺序产出（先 PLAN/runner、跑基线红、后写参考解）。
  写 hidden 时本题 reference/ 不存在，也没有读旗舰或其它题的 reference/；但作者知道自己的实现意图，
  不满足 bank/README.md §4.3「未参与实施」的字面要求。run-record 的 hidden_author 必须如实记这一点。
- **task-package/acceptance.md 的「隐藏用例尚未落盘」是构造期快照**：它在 manifest.sha256 里被钉住，
  改一个字节要重生成 manifest 与冻结哈希，因此本轮不动；当前状态以各题 README 的「天花板读数」节为准。
- **coverage.md 是快照**：本轮只在各题 coverage.md 顶部加「2026-10-21 深夜状态」块，正文未重写；
  引用覆盖表时必须同时读该状态块与 README 读数。
- **一处未复现的报告**：docs-config 子会话称 policy.check 的 reading_context.tree.digest 在同输入两次运行间变化；
  Lead 在参考树副本上两次运行整份载荷逐字节相同，**未复现**。若未来再出现，按 result + check_volume 判
  非确定性，而不是整份载荷。

## 5 与 SPEC 的偏差（摘要，逐题细节见各自 reference/README.md）

- crossmodule：T05 的旧名扫描必须排除冻结文件 conftest.py（标准库 sys.path.insert 不是废弃 API）；
  T08 不判嵌套对象隔离（基线是浅拷贝，强行要求会与「行为不变」冲突）；docs/api.md 的迁移示例要出现 add( / list_all(。
- bugfix：隐藏 38 条按 T/EN/I 实际分组；T16 取「至少 6 个 assert」（SPEC/coverage 的 5 与 3+3 算术矛盾，取一致解释）；
  README 只加 1 行，T19 逐节比对基线其余二级节。
- data-migration：load_schema 收紧一档（key_order 必须恰等于 v2 的 6 个键名）；T31 抓不到「断言改弱」，
  归 H2 抽样；data/ledger-v2.jsonl 由 CLI 在参考树上生成（与 SPEC 一致）。
- async：构造器多一个可选 queue 参数（README §8.3 既有裁定，用于两个 worker 共享同一队列；SPEC §3 只写 queue_size，
  若要逐字照 SPEC 则 T21 必须删）；A7 会咬公开的内嵌函数（scenario 改私有并补 docstring）；DOC-004 会咬以 action() 开头的中文 docstring。
- docs-config：T 取 40 条；T17 覆盖 7 类失败（4 类抓不住单点绝对路径泄漏）；tests/test_check_config.py 显式把项目根插进 sys.path；
  README 是插入「## 配置」一节（沿用任务包构造决定）。

## 6 未做

- **「可开跑」签字**（使用者）；本轮只做到「天花板可满足、T 已冻结」。
- **k≥3**：未跑；不写 treatment 效果或「值得扩试」。
- **k≥3 前的重冻结/重脚手架**：5 题不在当前冻结集（当前 .tmp/bank/freeze.json 只含旗舰）；选 3 题做 k≥3 时要新建实验集、
  重冻结、重脚手架，并按 2026-10-21 冒烟判据核每臂 run.json/审计/批次/post。

## 7 证据指针

- 各题：hidden/PLAN.md、hidden/runner.py、reference/tree、reference/README.md、README.md 的「天花板读数」节、scoring.yaml。
- Lead 复核现场：.tmp/lead-verify-{bugfix,crossmodule,data-migration,async,docs-config}（一次性，cleanup 会删）。
- 上一轮收口：readings/2026-10-21-bank-flagship-abc-smoke.md、readings/2026-10-21-bank-flagship-arms-and-ceiling.md。
