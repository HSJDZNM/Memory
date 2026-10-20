# 2026-10-20 D 门 2 A/B/C 三臂 run 记录

每臂一次 run 的受跟踪证据。判据与案例读数见 `readings/2026-10-20-D-gate2-ab-c-runs.md`；
评分器冻结与 17 字段契约见 `../scorer/` 与 `../run-manifest/`。

| 目录 | 内容 |
| --- | --- |
| `A/` | `arm-facts.json`（树摘要/session/启动方式/沙箱）、`run-record.json`（部分读数：C 只有 7/8 文件）、`run-manifest.json`（17 字段，14 recorded / 2 pending / 1 not_applicable） |
| `B/` | 同上；`run-record.json` 是 `run-record/collect.py` 的真实输出（T 40/40、C 23/24、A 9/10） |
| `C/` | 同上；不治理，`launch.patch=null`；run-record T 40/40、C 24/24、A 10/10 |
| `{A,B,C}/human-items.json` | 每臂一份：H1（独立子会话作者）、H2（抽样结论；抽样人 dshznm，Lead 子会话 h2-sampling 代执行）、H3（A4 复核；复核人 dshznm，Lead 子会话 h3-a4-review 代执行）、H4（not_applicable） |

## 复核命令

```powershell
cd C:/Users/ZNM/Downloads/Memory
$py = '.venv/Scripts/python.exe'
$t  = 'docs/project/engineering-policy-platform/testing/ab/dgate2/run-manifest/run_manifest.py'
foreach ($arm in 'A','B','C') {
  & $py $t --check  "docs/project/engineering-policy-platform/testing/ab/dgate2/runs/2026-10-20/$arm/run-manifest.json"           # 期望 0
  & $py $t --check  "docs/project/engineering-policy-platform/testing/ab/dgate2/runs/2026-10-20/$arm/run-manifest.json" --strict  # 期望 0（H2/H3 已复核并记录）
}
```

## 边界

- 每臂 n=1；不写均值/百分比/显著性（05 §5.5）。
- A 的 `run-record.json` 不是采集器输出（采集器要求 8 个改动文件都存在）：它是 T/A 原始载荷与
  C 部分测量的摘要，`dimensions.C.status=partial`。
- `.tmp/dgate2-arms/` 是现场（审计、会话日志、树），`tools/cleanup.py` 会删；本目录是受跟踪副本。
- H2/H3 的复核记录在 `readings/2026-10-20-H2-bypass-sampling.md` 与 `readings/2026-10-20-H3-a4-review.md`；
  抽样人/复核人记 dshznm（使用者授权），机械执行由 Lead 子会话完成并在两份读数里写明。
