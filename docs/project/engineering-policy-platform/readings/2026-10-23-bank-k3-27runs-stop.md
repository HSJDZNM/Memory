# 2026-10-23 题库 k≥3 · 27 run 状态（第 10/27 停点）

> **性质**：27 run 的**停点读数**，不是 treatment 结论。按失败关闭，记录到这里；是否继续由使用者裁定。
> 起点 HEAD `bcbc74c`（可开跑已签）；不 push。27 run 现场 `.tmp/k3/runs27/`（一次性）。

## 0 一句话

27 run 跑到 **10/27**：crossmodule 的 9 个 run 全部完成（A/B/C × 3 block，T 均 33/33、C 8 allow、A 10/10）；
第 10 个 async A-b1 也 exit 0 / invalid=[]，但最终树缺 `src/shop/notify_worker.py` 与 `tools/notify_smoke.py`，
run-record collector 因 C 的 file_set 缺文件报 `InputError`。按「记录字段缺失 → 停，不记 pass」停在 10/27；
**未继续 11–27**，等使用者裁定是否按 T-only 规则继续。

## 1 已完成：crossmodule 9 run（对照）

| block | 臂序 | 各 run T | C | A |
| --- | --- | --- | --- | --- |
| 1 | A/B/C | 33/33、33/33、33/33 | 8/8 allow | 10/10 |
| 2 | B/C/A | 33/33、33/33、33/33 | 8/8 allow | 10/10 |
| 3 | C/A/B | 33/33、33/33、33/33 | 8/8 allow | 10/10 |

- 9 份 run-record 已用 `--model deepseek-official/deepseek-flash`（从 session header 取）重新采集；
  T 33/33、C 8/8 `allow`、A 10/10，与 A/B/C 无方向差（负对照符合预期）。
- 记录：`.tmp/k3/runs27/bank-crossmodule-refactor-{A,B,C}-b{1,2,3}/run-record.json`。

## 2 停点：async A-b1

- `run.json`：exit 0 / timeout=false / `invalid=[]`；decisions allow 15 / allow_with_warnings 18 / block 2；
  reasons 含 `circuit_open 7`；diff created 4 / changed 4 / unchanged 11；最终树缺
  `src/shop/notify_worker.py`、`tools/notify_smoke.py`（任务未完成）。
- 手工 T（hidden runner，仅 T）：**14/38**；失败 id 与 `t-only.json` 见
  `.tmp/k3/runs27/bank-async-concurrency-A-b1/`（该文件是 PowerShell 重定向的 UTF-16；读时用 utf-16）。
- collector：`collect: 输入声明不可读：--tree 里没有被测文件：src/shop/notify_worker.py`，退出 2；
  按失败关闭未写 run-record，也未继续后续 run。
- 这是 **A 臂 M1 阻断 + 模型停止**的 treatment 结果，不是仪器崩溃；但没有 C/A 字段，不能按原口径记 pass。

## 3 未跑与待裁定

- 未跑：11–27（async 其余 8 + docs 9），现场停在 `.tmp/k3/runs27/`。
- 选项：
  1. **T-only 继续**（需使用者明确授权为 27 run 的预注册补充规则）：保留 async A-b1 为 T=14/38、
     C/A `unavailable`；后续缺 C 文件的 run 同样处理；27 个都保留，结论只写 T 原值/「跑不成」。
  2. **停在这里**：不再跑；结论写「跑不成 + 原因 + 复现指针」。
  3. **替换重跑**该 block：不推荐（按完成度挑 run 会引入选择偏倚）。

## 4 边界

- 本读数不是 27 run 结果；没有 treatment 结论，也不写均值/百分比。
- crossmodule 9 run 是完成的；async A-b1 是 T-only 的停点样本，C/A 缺。
- 审批 TTL `2026-10-29T12:38Z` 仍覆盖；未改臂配置/审批。
- 现场与 ACL 残留未清理；未 push。
