# 2026-10-22 题库 k≥3 · H1 阈值用户改判（本批定点修）

> **性质**：使用者对 H1 复核命中「单题 flag >2」阈值后的**书面改判**（只覆盖本批 3 题）。
> 依据：`readings/2026-10-22-bank-k3-h1-review.md`；一次性裁决备忘 `.tmp/deliberation/h1-threshold.md` §4 的措辞。
> 起点 HEAD `fc5cffc`；本读数只落裁决与影响面，**不是「可开跑」签字**。

## 0 裁决

**用户改判（2026-10-22，使用者 dshznm，会话内选择 2）**：
H1 第三方复核在 `bank-crossmodule-refactor` 命中预注册阈值「单题 flag >2 → 停/重出该题 hidden」
（3 条：T20 / T21 / T26）。使用者书面决定：**本批不重出 crossmodule hidden**，改为
「定点修 + 重冻结 + 重测 + 第三人复核」；同批处理 async 的 I5 / EN5 与 docs 的 I5 / I7。
理由：三条均为 hidden 比首消息严的非核心口径，参考解 34/34 与常见合法解不受影响，三臂共模、
不改变 A/B 的 δ 对比；重出与时间窗/成本不相称。

**同批修复清单（本改判覆盖的唯一范围）**：

| 题 | 修复 | T 条数 |
| --- | --- | --- |
| async | I5（docstring 断言代理放宽）、EN5（正文扫描只对一/二级标题结束） | 38 → 38 |
| docs | I5（测试函数计数含 class 内 `test_*` 方法）、**删除 I7**（loader 不 import shop 无契约出处） | 40 → **39** |
| crossmodule | T20（import 白名单改为负列表）、T26（接受三反引号与波浪线围栏）、**删除 T21**（单文件 pytest 无契约出处） | 34 → **33** |

## 1 影响面

- **规则文本不变**：`readings/2026-10-22-bank-k3-deliberations.md` §3.2 的阈值、05 §5.4/§5.5 与 §8 第 11 条
  对**本批之后**的同类题仍按原字面执行；本改判**只覆盖本批 3 题的这 7 条 flag**，不是对阈值的修订。
- **作废/取代**：`readings/2026-10-22-bank-k3-h1-review.md` 的 crossmodule「停/重出」机械结论；
  本批三题旧 hidden 摘要；docs 的 T `total=40` 与旧 `case_ids`；crossmodule 的 T `total=34` 与旧 `case_ids`；
  3 份旧 freeze 的 `combined_digest`；run-ready 读数里的旧 freeze 摘要。
- **不变**：三题 task-package（首消息/验收表/允许写/manifest）、baseline、`reference/tree`、C/A 判据与分母、
  arm 配置、审批条子（TTL `2026-10-29T12:38Z`；返工本身不需重签）、Gate 0 读数（构造未变）、
  27 run 结构（3×3×3、题序/臂序）、H2 预注册。
- **重算/重跑**：三题 runner/PLAN 与 `frozen_inputs.hidden_*`；docs `dimension_t.total/case_ids`（39）；
  crossmodule `dimension_t.total/case_ids`（33）；三题 README §3 哈希行；3 份 freeze `--write`/`--check --strict`；
  三题基线红 + 参考树 T（38/38、39/39、33/33）；1 臂 re-smoke 随新 freeze 重跑。
- **删用例不升 `bank-scoring` 版本**：只改 `dimension_t.total/case_ids` 的**值**，键集合与形状不变；
  T 判据值变化记在本改判与 freeze 读数里，旧 T 读数作废。
- **复核**：修由非 hidden 作者执行；async I5/EN5、docs I5、crossmodule T20/T26 与两处删除由第三方逐条复核；
  **若重审 crossmodule 仍 >2 flag，本改判自动失效，转「完整重出 crossmodule hidden」**。
- **结论口径**：只写「固定 hidden 件（新 hash）下的臂间对比」；不写「独立出题」；三题仍记 H1 降级。

## 2 两条 errata

1. async 的 flag 数由 1 更正为 **2（I5、EN5）**（EN5 = runner 遇任意 `#` 行就 break；PLAN 口径是到下一个二级标题）。
2. H1 复核读数 §2 原引用的「交接提示 §10」在仓库中不可复核（现行 handoff 只有 §0–§6）；
   阈值原文以 `readings/2026-10-22-bank-k3-deliberations.md` §3.2 为准（已在该读数更正）。

## 3 还需要签什么

- **本改判**：已由使用者在会话内选择 2 并授权；本读数即落点，不再需要第二个签名。
- **「可开跑」**：**唯一剩余的新签名**（使用者）。时点在：三题修复 + 重冻结 + 重测 + 第三方复核 +
  1 臂 re-smoke 之后；签在受跟踪读数（含 3 份新 freeze 摘要、审批 sha、TTL、Gate 0、H1 改判、H2 计划）。
- **审批条子**：A/B 各 2 条已签，TTL 到 **2026-10-29T12:38Z（+08 20:38）**；本批修复不改变 arm 配置，
  **不需要重签**；但若 27 run 窗口跨过该时刻、或重新物化/改臂配置，则必须重签（批内重签 = 换代际）。
- **H2 盲抽**：不是签名项，是「不知道臂分配的复核者」执行并写 `run-record.bypass_sampling`。
- 27 run 本身不需要额外签名；「可开跑」覆盖。

## 4 证据指针

- 裁决备忘：`.tmp/deliberation/h1-threshold.md`（一次性；cleanup 后不可读，本读数承接结论）。
- H1 复核：`readings/2026-10-22-bank-k3-h1-review.md`；逐条表 `.tmp/k3/h1/*.md`。
- 预注册：`readings/2026-10-22-bank-k3-deliberations.md` §3.2；05 §8 第 11 条。
- 审批/TTL：`.tmp/k3/arm-configs/{A,B}/approval.json`（A `282b4925…` / B `3c697d97…`）。
