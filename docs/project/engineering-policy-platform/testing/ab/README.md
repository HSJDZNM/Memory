# 评测轨道索引（testing/ab/）

> **一句话定位**：`testing/ab/` 下各评测轨道的**入口索引**——只回答「先看哪一份、权威在哪」。
> **它不是判据、不改任何读数**：状态与计数以被链接的文件为准，本页不复制第二份真相。

## 1 入口

| 轨道 | 入口 | 一句话 |
| --- | --- | --- |
| A/B 实验协议 | [`ab-protocol.md`](ab-protocol.md) | 三臂定义、一次 run 产出什么、隔离与污染检测、配对与预注册、证伪条件 |
| 臂运行时与净化树 | [`arm-harness.md`](arm-harness.md) | 「控制臂读不到规则」要能被一条命令证明；仪器自证会红 |
| 测量仪器 | [`measurement-instruments.md`](measurement-instruments.md) | 六个量、独立性、自证；读数可被第二个人逐条重算 |
| 任务集 | [`task-sets.md`](task-sets.md) | 任务从哪来、怎么钉死、怎么在本机跑出外部判据 |
| 红队与试点 | [`redteam-and-pilot.md`](redteam-and-pilot.md) | 对协议与仪器的攻击清单、四项最小可行试验的原始读数 |
| 题库 | [`bank/README.md`](bank/README.md) | 6 题冻结题包 + 出题/判分/冻结规范；每题命令形态见 [`bank/COMMAND-FAMILIES.md`](bank/COMMAND-FAMILIES.md) |
| D 门 2 评测件 | [`dgate2/README.md`](dgate2/README.md) | 2026-10-19/20 的冻结评分器、任务包运行件与三臂 run 的受跟踪证据（状态为 2026-10-20 快照） |
| GUI 阶梯 | [`gui-ladder.md`](gui-ladder.md) | 在桌面 GUI 里逐级推进「受治 vs 不受治」，每级一个判决；读数在 [`gui-runs/`](gui-runs/) |

## 2 两轴状态（不合并成一档）

`可开跑` 是**人的签核门**（使用者），`k≥3` 是**实验门**（预注册 + Gate 0）；两者失败原因不同，不写成同一个状态字。

| 轨道 | 已落盘 / 读数 | 可开跑 | k≥3 |
| --- | --- | --- | --- |
| 题库 6 题（`bank/`） | T 天花板已测（旗舰 48/48；5 题 hidden 34/38/40/38/40，参考树全过）；hidden/reference 已落盘（同一子会话，H1 降级） | **未签（使用者）**；旗舰审批已签 ≠ 可开跑 | **未跑**：Gate 0 重跑通过（2026-10-22；async/docs 激活、2/3 → 待 §5.3 签核/27 run；见 [Gate 0 重跑读数](../../readings/2026-10-22-bank-k3-gate0-rerun.md)） |

题库的细节与逐题读数以 `bank/README.md` 与各题 README 为准；本表只给两轴状态。

## 3 读数与决策

- 题库 k≥3：3 题、Gate 0、H1 降级与复核、27 run 结构与结论上限——
  [`readings/2026-10-22-bank-k3-deliberations.md`](../../readings/2026-10-22-bank-k3-deliberations.md)。
- 题库 Gate 0（2026-10-22）：改造前四题离线探针与停止判定 [`readings/2026-10-22-bank-k3-gate0-activation.md`](../../readings/2026-10-22-bank-k3-gate0-activation.md)；构造改造后重跑通过 [`readings/2026-10-22-bank-k3-gate0-rerun.md`](../../readings/2026-10-22-bank-k3-gate0-rerun.md)。
- 题库历史读数（旗舰冒烟、天花板、5 题 hidden/reference、七项裁决）：`readings/2026-10-21-bank-*.md`。
- 判据与口径：[`05-implementation-plan.md`](../../05-implementation-plan.md) §5 与 [`04-open-work.md`](../../04-open-work.md) 5.92。
