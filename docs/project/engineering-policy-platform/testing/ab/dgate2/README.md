# D 门 2 评测件（dgate2/）

**它是什么**：2026-10-19/10-20 对比实验「阶段 D 门 2」的全部受跟踪材料——**冻结的评分器**、
**任务包运行件**、**开跑前清单**、**读数采集器**与**三臂 run 的受跟踪证据**。
判据原文在 `../../readings/2026-10-19-D-gate2-treatment.md` 与 `05-implementation-plan.md` §4/§5；
执行记录在 `06-plan-progress.md`；本目录只回答「用什么判、跑了什么、证据在哪」。

## 1 目录地图

| 目录 | 是什么 | 冻结？ |
| --- | --- | --- |
| `scorer/` | 机读判据（`scorer.yaml`）、层与接口声明（`layers.yaml` / `interfaces.yaml`）、确定性清单生成器 `make_manifest.py` 与 `manifest.sha256` | **是**（`--check --strict` 门禁；改一个字节 = 换判据，旧读数作废） |
| `hidden/` | 30 条隐藏验收 + `runner.py`（T 维度） | **是**（在 scorer 清单里） |
| `configs/` | `before`（A 臂）与 `after`（B 臂/treatment）两份 9 文件配置快照，各带 `sha256.txt` | 是（`after` 在 scorer 清单里；`before` 由自己的 `sha256.txt` 冻结） |
| `c-arm/` | C 臂（不治理）装配器与冒烟读数 | 否（装配工具；读数在 README） |
| `run-manifest/` | 17 字段 run-manifest 的生成/校验器 + README + 用例（`RUN_MANIFEST_SCHEMA_VERSION 1.0`） | 否（工具；输入是上面那些冻结件） |
| `run-record/` | T/C/A 三维读数采集器 + README + 用例（`RUN_RECORD_SCHEMA_VERSION 1.0`） | 否（工具） |
| `runs/2026-10-20/` | A/B/C 各一次 run 的 `arm-facts.json` / `run-record.json` / `human-items.json` / `run-manifest.json` | 否（run 证据；改它不改变判据，但读数不可重跑） |

## 2 现状（2026-10-20）

- 冻结复核：`make_manifest.py --check --strict` → PASS（25 文件逐字节一致），组合摘要 `sha256:e3ef9e91…dd649a`。
- **A/B/C 各跑一次（n=1）**：A 未完成（M5b 被 `TESTING-002@1 uncovered_checker` 拦住；缺 demo → 收集错误 →
  第三次 post 失败触发熔断），B/C 完成；案例读数见 `../../readings/2026-10-20-D-gate2-ab-c-runs.md`。
- 三份 run-manifest 均 **16 recorded / 0 pending / 1 not_applicable**，`--check --strict` **PASS**；
  人工项 H2/H3 的复核记录在 `../../readings/2026-10-20-H2-bypass-sampling.md` 与
  `../../readings/2026-10-20-H3-a4-review.md`（抽样人/复核人记使用者，Lead 子会话代执行）。

## 3 复核命令

```powershell
cd C:/Users/ZNM/Downloads/Memory
$py = '.venv/Scripts/python.exe'

# 冻结门禁
& $py docs/project/engineering-policy-platform/testing/ab/dgate2/scorer/make_manifest.py --check --strict

# 三份 run-manifest（严格）
foreach ($arm in 'A','B','C') {
  & $py docs/project/engineering-policy-platform/testing/ab/dgate2/run-manifest/run_manifest.py `
    --check "docs/project/engineering-policy-platform/testing/ab/dgate2/runs/2026-10-20/$arm/run-manifest.json" --strict
}
```

## 4 边界（引用前必须读）

- **冻结件不是只读文件**：它们可以被改，但改了就是换判据；`manifest.sha256` 会红，旧 run 作废（05 §5.4）。
- **n=1 只作案例读数**：不写均值/提升/显著性；要写「值得扩试」需每臂 k≥3（05 §5.5）。
- **A 的 C 维度不完整**：`tools/audit_demo.py` 不存在，C 规则分只在 7/8 文件上量到 24/24，不能读成 30/30
  （04 5.79⑥）。A4 对「声明 composition 但文件不存在」是空真（A 的 `declared_unmatched`）。
- **任务包 v3 明写 M1/M5a 的「预期红」pytest**：两臂都会得到 `post_repair_required`；A 的第三次（缺 demo）
  触发熔断。这是构造摩擦，登记在 04 5.82。
- 装配必须用带 `governed-dev` 的 `examples/dsh/b-plan/tool-registry.local.yaml` + 已审核对
  （用仓库 `registry/tool-registry.yaml` 会让每个写/执行动作 `permission_denied`，A 首跑因此作废，
  见 04 5.82 与 D-20261020-01）。
- `.tmp/dgate2-arms/` 是现场（树、审计、会话日志），`tools/cleanup.py` 会删；受跟踪证据只有本目录与 `readings/`。
