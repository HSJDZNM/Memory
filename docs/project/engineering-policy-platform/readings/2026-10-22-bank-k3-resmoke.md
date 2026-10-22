# 2026-10-22 题库 k≥3 · 1 臂 re-smoke（async A，真机 n=1）

> **性质**：真机 re-smoke（**不是 k≥3**）：只跑 1 题 1 臂 1 次，验证 `run_session.py` 1.1 的自动化路径
> （隔离 `DSH_HOME` / profile 沙箱覆盖 / `TEMP` 重定向）与治理链自检；**不计入 k**、不写 treatment 效应。
> 起点 HEAD `79ccfb3`（工作树干净）；审批：A/B 各 2 条、TTL 到 `2026-10-29T12:38Z`；凭据由使用者注入启动环境。
> 读数现场：`.tmp/k3/runs/bank-async-concurrency-A-resmoke/`（一次性，cleanup 会删）。

## 0 一句话

async 题 A 臂一次真机 run：**exit 0、`invalid=[]`**、246 条读数（137 条审计 / 11 条写提议 / 11 条 settle）、
墙钟 323.5 s；五条冒烟判据全部有读数支撑。**最关键的构造证据**：M1 写 `tools/notify_smoke.py` 被
`policy_block` 拦下且批次 settle=`blocked`，最终树因此缺该工具（20 文件而不是 21）——离线 Gate 0 预测的
A 臂设计方向阻断在真机上发生了。

## 1 环境与启动

| 项 | 读数 |
| --- | --- |
| 宿主 | app 自带 dsh **0.2.1-rc.2**（`source=app`） |
| 入口 | `headless`；隔离 profile 4 文件、`cordis.patch.yml` 沙箱覆盖已写 |
| 沙箱 | 控制器/测量与 dsh 子进程均 `danger-full-access`（`launch.sandbox_mode=danger-full-access`） |
| DSH_HOME / TEMP | 隔离目录；`launch.temp=isolated` |
| 审批 | A 臂 `approval.json` `282b4925…`（2 条，schema 1.3） |
| 冻结 | `7caf8825…`（120 条）`--check --strict` PASS；arm-tree PASS（placeholders=0） |
| 墙钟 | **323.5 s**；`exit.code=0`、`timeout=false` |

## 2 五条冒烟判据

| # | 判据 | 读数 | 结论 |
| --- | --- | --- | --- |
| 1 | 无平台自锁 | exit 0、`invalid=[]`；`circuit_open` 3 条是 pwsh 速率熔断的过程事实 | **通过** |
| 2 | 每个写动作有 decision + `batch_ref` | 20 条写类 `PreToolUse` 全部有 `batch_ref`；11 条 proposal ↔ 11 条 settle（**9 allowed / 2 blocked**）；2 条 block 是 `tools/notify_smoke.py`（设计方向）与 `tests/test_notification.py`（编辑被拦后改 write 落地） | **通过** |
| 3 | post_validated 或显式 repair | `post_validated` 13 + `post_repair_required` 3；`post_error` 5 条全部 `executed=false`（04 5.90 的回声，已知边界） | **通过（附过程读数）** |
| 4 | 预算不等式 | `pre_evidence.timeout_ms=20000` + `timeout_ms=5000` < hooks `timeout=30000`；审计 `elapsed_ms` 最大 **2166 ms** | **通过** |
| 5 | 审计链可逐条复核 | 执行层 staged 记录 56 条、`prev_digest` 链 **0 处断裂**；`audit_schema_version=1.5`、批次账本 schema **1.1** | **通过** |

## 3 构造激活的真机证据

- `tools/notify_smoke.py` 的 `PreToolUse`：`reason_code=policy_block`、`executed=false`、
  `batch.settlement.status=blocked`；批次账本该 proposal 的 settle 是
  `outcome=blocked, reason_code=policy_block`。
- 最终树 `diff.created=5`（应有 6 个新建）、`changed=4`、`unchanged=11`——缺的正是
  `tools/notify_smoke.py`。这是 A 臂在 M1 的设计方向阻断（`tools` 非生产文件 → 选不到基线静态测试
  → `TESTING-002`），不是跑不成。
- 其余 10 条写提议 9 条 allowed（另一条 blocked 见上），模型继续完成了 model/worker/tests/docs/README；
  任务未完成是 treatment 的直接结果，**本 run 不作为 T 读数**。

## 4 边界

- **n=1、1 题、1 臂**：只验证仪器与治理链，不是 k≥3，不写均值/百分比/显著/「值得扩试」。
- 任务未完成（缺 `tools/notify_smoke.py`）；不跑 T/C/A，不把本 run 记成 pass 或 fail 的 treatment 效应。
- `post_error` 5 条是 04 5.90 的已知回声（被拒/未执行调用仍收到 PostToolUse）；实验期接受为边界。
- 跑不成与失败关闭仍然成立：本 run 的 `invalid=[]` 与 exit 0 是「跑成了」，但任务完成度另算。
- 现场 `.tmp/k3/runs/...` 是一次性；长期证据以本读数与后续 run-record 为准。

## 5 下一步

H1 第三方逐条可追溯性复核（3 题）→ 可开跑读数（3 份 freeze 摘要 + 审批 sha + TTL + Gate 0 + H1/H2）
交使用者签 → 27 run。本 re-smoke 不替代 k≥3。
