# 2026-10-22 题库 k≥3 · H1 定点修第三人复核

> 复核者 reviewer-k3（fresh context，只读；未改文件、未跑 27 run/run_session/ci_local）。本文件由 Lead 按其报告落盘。

## 0 一句话

7 条修复全部在 override 授权范围内落地；6 条完全消解；crossmodule 的 T26 仍留 1 条窄误伤（CommonMark 缩进代码块）。
crossmodule 剩余 flag = **1**（把 EN4 边界项计入为 2）——**≤2，override 不失效**。scoring/hidden 摘要/3 份 freeze/README T 读数独立实算自洽。

## 1 逐条判定

| flag | 修后断言 | 契约出处 | 结论 |
| --- | --- | --- | --- |
| async I5 | 任一 assert 文本含「已弃用」；保留原用例、无 skip | first-message L39；A11 | fixed |
| async EN5 | 只对 `# ` / `## ` break | first-message L40；A10 | fixed |
| docs I5 | 顶层 + 模块级 `ClassDef` 内 `test_*` 都数 | first-message L39；A9 | fixed |
| docs I7 | 删除（I1–I6） | 无契约出处 | deleted |
| cross T20 | 禁止 `shop.order_repository*`；仍要求 import `shop.order_service`；0 `OrderRepository` 引用 | first-message L27–28；A3/A4 | fixed |
| cross T26 | 接受三反引号或 `~~~`；仍要求围栏与三词 | first-message L41；A7 | fixed（原 flag）+ 残余窄误伤 |
| cross T21 | 删除；EN1 仍覆盖整树 | A6 无单文件要求 | deleted |

## 2 哈希 / freeze / T 读数（独立实算）

- total/case_ids 与 runner CASE_IDS 逐项相等：38/38、39/39、33/33。
- hidden 摘要 = scoring = freeze = README §3：async `599da13a…/ecaf9738…`；docs `769030ca…/b7ec0e64…`；cross `58ec4132…/5bd879f5…`。
- 最终 freeze：async `87a8bbf5…`(120)、docs `9e507374…`(119)、cross `4e8e4bcf…`(119)；三份 `--check --strict` PASS。
- T 读数（shim 下两遍，stdout 与 README 一致）：async ref `acf67b99…` 38/38、base `a6294c63…` 2/38；docs ref `6b55369d…` 39/39、base `c4ab7fb7…` 2/39；cross ref `3a0d46b5…` 33/33、base `f32db9c4…` 4/33。

## 3 复核后对齐与 errata

- 复核后只改文档/注释：async PLAN I5、cross PLAN T20/T26 叙述对齐 runner；cross runner 注释 T22-T26 / EN1/EN4；async README scoring 行改为实算 `bea34888…`。T20/T26 函数体未变，cross 读数不变。复核者先确认 PLAN 对齐与 7 条结论/剩余 flag=1；随后 Lead 按它的两处指正再修 async README scoring 行与 EN1/EN4 注释（纯文档/注释），并重算 async/cross freeze；语义判定仍以复核者已确认的 T20/T26 函数体为准。
- 预存错行（非本批）：async/docs README §3 的 `task-package/interfaces.md` 哈希错误（实算 `14e67c2e…` / `58b1d405…`；manifest 正确），不改字节，签核读数记 errata。
- 预存 open item：三题 scoring 的 `command_families_sha256` 写 `6943e988…`，当前 `COMMAND-FAMILIES.md` 实算 `d55f079f…`；该文件不在 freeze 根内。

## 4 shim 与 freeze

- shim 只把 `os.mkdir(0o700)` 映射为 0750，不改树/不改 hidden；不设时 docs ref 38/39 且仅 EN1 红。它是宿主依赖：27 run 必须让模型会话 pytest 与评分 runner 同环境（或统一 danger-full-access），并把形态写进 `run-record.platform_generation`。
- freeze PASS 只证明字节锁住，不证明 PLAN/README 叙述准确；叙述对齐与 errata 见 §3。

## 5 未覆盖

未跑 27 run / run_session / ci_local；未做真实模型行为、P1–P6、scaffold、dry-run、新 re-smoke；未重跑 C/A 与全仓 pytest；未逐个对照 108 条 case；未验证审批/TTL、Gate 0、H2。
