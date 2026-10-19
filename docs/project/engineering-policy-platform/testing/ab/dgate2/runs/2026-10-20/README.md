# 2026-10-20 D 门 2 A/B/C 三臂 run 记录

每臂一次 run 的受跟踪证据。判据与案例读数见 `readings/2026-10-20-D-gate2-ab-c-runs.md`；
评分器冻结与 17 字段契约见 `../scorer/` 与 `../run-manifest/`。

| 目录 | 内容 |
| --- | --- |
| `A/` | `arm-facts.json`（树摘要/session/启动方式/沙箱）、`run-record.json`（部分读数：C 只有 7/8 文件）、`run-manifest.json`（17 字段，14 recorded / 2 pending / 1 not_applicable） |
| `B/` | 同上；`run-record.json` 是 `run-record/collect.py` 的真实输出（T 40/40、C 23/24、A 9/10） |
| `C/` | 同上；不治理，`launch.patch=null`；run-record T 40/40、C 24/24、A 10/10 |
| `human-items.json` | H1（独立子会话作者）与 H4（not_applicable）已记；H2/H3 未提供 → 两份 pending |

## 复核命令

```powershell
cd C:/Users/ZNM/Downloads/Memory
$py = '.venv/Scripts/python.exe'
$t  = 'docs/project/engineering-policy-platform/testing/ab/dgate2/run-manifest/run_manifest.py'
foreach ($arm in 'A','B','C') {
  & $py $t --check  "docs/project/engineering-policy-platform/testing/ab/dgate2/runs/2026-10-20/$arm/run-manifest.json"           # 期望 0
  & $py $t --check  "docs/project/engineering-policy-platform/testing/ab/dgate2/runs/2026-10-20/$arm/run-manifest.json" --strict  # 期望 1（human_items_unrecorded）
}
```

## 边界

- 每臂 n=1；不写均值/百分比/显著性（05 §5.5）。
- A 的 `run-record.json` 不是采集器输出（采集器要求 8 个改动文件都存在）：它是 T/A 原始载荷与
  C 部分测量的摘要，`dimensions.C.status=partial`。
- `.tmp/dgate2-arms/` 是现场（审计、会话日志、树），`tools/cleanup.py` 会删；本目录是受跟踪副本。
- H2/H3 未做前，三份 manifest 的 `--strict` 一律失败；这不是缺陷，是「人工项未记」的显式状态。
