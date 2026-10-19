# 2026-10-19 本机门禁：D 门 2 开跑前置工具化之后

> 用途：记录 run-manifest / run-record 两件工具与两份读数入库之后的一次**全量本机门禁**。
> 起点 = 收口提交后的干净树（HEAD 473ff91）；命令与退出码照抄，结论只写读数。
> 证据规则：命令 → 退出码；`.tmp` 只作现场产物，主证据是本文件与测试/文档。

## 1 起点与命令

| 项 | 值 |
| --- | --- |
| HEAD | `473ff91`（docs(plan) 状态同步） |
| 工作树 | 干净（`git status --porcelain` 空） |
| 沙箱形态 | **danger-full-access**（运行时切换后的形态；与 R-A-GATE-04/05 的差别只在沙箱，见 §4） |
| 命令 | `.venv/Scripts/python.exe tools/ci_local.py --full --timings` |
| 覆盖 | 30 个正常步骤 + 4 个只报告步骤；改动文件 142（`origin/main...HEAD` 口径） |

## 2 读数

| 项 | 值 |
| --- | --- |
| 结论 | **30/30 ok，退出码 0**（`本机检查全部通过（30 步）；只报告 4 步`） |
| 总耗时 | **6m 08.5s**（`.tmp/ci-local-timings.json` 的 `total_seconds` = 368.474） |
| 全量测试 | `-m pytest tests/{unit,contract,integration,security} -q -n auto --dist loadfile` → **rc=0**，3m 04.0s |
| 只报告 4 步 | obligations 0 / exemption HITS 0 / instrument self-proof 0 / control-plane facts HITS 113（四格红 0，`test_path_declaration=113` 是既有声明面） |
| 步骤逐条 | `entries` 34 条，`returncode` 非 0 的 **0 条** |

### 2.1 最慢五步（`--timings` 汇总表原文）

| 耗时 | 占比 | rc | 步骤 |
| --- | --- | --- | --- |
| 3m 04.0s | 49.9% | 0 | Unit, contract, integration and security tests |
| 1m 12.9s | 19.8% | 0 | Orchestration closed loop |
| 59.7s | 16.2% | 0 | Tech-detail notebooks execute |
| 10.3s | 2.8% | 0 | Phase 8 acceptance evidence |
| 7.8s | 2.1% | 0 | Validator closed loop |

## 3 本次改动面在门禁里的覆盖

- **新增工具**：`dgate2/run-manifest/run_manifest.py` 与 `dgate2/run-record/collect.py` 都是 `docs/` 下的
  可执行脚本，**不接** `tools/ci_local.py` 的步骤（不新增阻断步骤，见 05 §2.3 冻结令）；它们的门是
  各自的定向用例（13 + 10 passed）与 `make_manifest.py --check --strict`（复核 PASS）。
- **全量测试**包含这两份新用例；`Text conventions` 覆盖新增的中文文档与 README（770 文件 0 问题）。
- **冻结面未动**：`scorer/manifest.sha256` 25 文件逐字节一致（`--check --strict` exit 0，组合摘要 `e3ef9e91…`）；
  `enforcement.cli registry --verify` rc=0；`adapters.cli wiring` / 阶段验收证据均 ok。

## 4 与历史门禁读数的关系（不追认、不覆盖）

| 读数 | 形态 | 结论 |
| --- | --- | --- |
| R-A-GATE-03（HEAD 98169bf） | 干净树 | 26/26、4m49.3s |
| R-A-GATE-05（HEAD 99fd894 + 文档） | danger-full-access、干净树 | 26/26、4m34.8s |
| R-A-GATE-04（HEAD bbd45c2） | **沙箱内**（workspace-write） | pytest 步骤跑不成（`.tmp` ACL）；不占绿不占红 |
| **本次 R-A-GATE-06** | danger-full-access、干净树、30 步 | **30/30、6m08.5s** |

**步骤数 26 → 30 的原因**：`--full` 把 4 个只在完整模式下执行的步骤也算了进来（本机跳过表与只报告表
的口径见 `tools/ci_local.py` 的输出首行）；不是新增了门禁步骤。**沙箱形态的差别不改变结论**：
R-A-GATE-04 的「跑不成」与本轮的「全绿」是两次不同构造下的读数，前者的处置见 D-20261018-04/D-20261018-05。

## 5 边界

- 本读数只证明**本机门禁在本轮改动面上全绿**；它不证明 A/B/C 主实验可开跑（后者仍差使用者确认，见 04 5.78）。
- `.tmp/ci-local-timings.json` 与 `.tmp/ci-local-logs/` 是现场产物，`python tools/cleanup.py` 会删；
  本文件记录的是当时的读数（时间、步骤名、耗时、退出码），不是可重放的缓存。
- 门禁的「只报告」步骤**不计入门禁失败**，其中的非零命中不是本轮引入；数值照抄，不做解释。
