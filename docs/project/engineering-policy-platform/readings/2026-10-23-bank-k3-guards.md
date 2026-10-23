# 2026-10-23 题库 k≥3 · C/A 守卫逐条读数（STEP 2）

> **生成**：2026-10-23T12:11:43+08:00（Asia/Shanghai）
> **HEAD**：`a6d987e76d7d1ac89964afef7177cd3fadda9364`
> **性质**：STEP 2 单步交付。对象是 `.tmp/k3/runs27/<task>-<arm>-b<block>/run-record.json` 的 21 份
> C/A 读数；6 个 T-only 的 C/A 记 `unavailable`，不重跑、不补造。不评分、不改 hidden/scoring/freeze/
> 臂配置、不写 run-record、不 push、不 cleanup。
> **口径一句话**：C 只读 `dimensions.C` 的文件级 decision 分布与 violations（条数 + 规则级别）；
> A 只读 `dimensions.A.failed_ids`（`structure_metrics` 的 10 条结构谓词）。两者都是回归守卫读数，
> 不是 T 的分值，也不是 treatment 结论。

## 1 开工核对与证据来源

### 1.1 §1 开工核对（命令原文与输出）

```text
$ git log --oneline -5
a6d987e docs(bank): 落 k3 H2 盲抽读数
c4d3d57 docs(bank): 补 27 run 的 HEAD 说明
e39300f docs(bank): 落 k3 27 run 最终读数（T-only 补充规则）
bac565d docs(bank): 落 k3 27 run 第 10/27 停点
bcbc74c docs(bank): 使用者签可开跑（dshznm）

$ git status --short
（无输出）
```

**与 §1 期望的偏差（按 §0「现场优先」记录，不据此改口）**：期望 HEAD 是
`c4d3d57`，现场是 `a6d987e`。`git show --stat --oneline a6d987e` 显示它只新增
`docs/project/engineering-policy-platform/readings/2026-10-23-bank-k3-h2.md`（1 file changed,
308 insertions），没有改 `hidden/**`、`scoring.yaml`、freeze/exp-set、臂配置、`src/**`、
`policies/**`、`validation/**`，也没有改 21 份 run-record。**判据**：本步读的是 `.tmp/k3/runs27/`
下已落盘的 run-record 与 partial 文件，STEP 1 的提交通道不触达这些字段；工作树干净，
因此不影响本步 C/A 读数，继续执行。

### 1.2 证据来源（读了什么、用在哪）

| 来源 | 读到的位置 | 用于 |
| --- | --- | --- |
| `readings/2026-10-23-bank-k3-27runs.md` | `:13-17`（27/27 与 21+6）、`:33-43`（T 矩阵）、`:45-46`（21 完整 + 6 T-only）、`:48-55`（停点与补充规则）、`:66-78`（C/A 守卫表）、`:99-101`（边界） | T 原值来源、C/A 交叉核对 |
| `readings/2026-10-23-bank-k3-27runs-stop.md` | `:26-35`（async A-b1 停点与 T-only 原因）、`:39-44`（T-only 规则来源） | 6 个 T-only 的 unavailable 口径 |
| `readings/2026-10-22-bank-k3-run-ready.md` | `:16-30`（3 份 freeze、审批 A/B sha、TTL）、`:89-106`（27 run 计划、结论上限）、`:108-119`（预存 errata） | 冻结/审批/TTL 与「T 满分不等于契约全满足」 |
| `readings/2026-10-22-bank-k3-deliberations.md` | `:95-101`（T 的解释力边界）、`:117-168`（§3 预注册、TTL、结论上限）、`:190-195`（纪律） | 只写原值/方向、不写 treatment 的边界 |
| `readings/2026-10-20-H2-bypass-sampling.md` | `:15-50`（抽样方法与三态） | 确认 H2 是另一条抽样通道，不参与本步 C/A |
| `testing/ab/bank/README.md` | `:59-62`（10 条 A 谓词是结构谓词，不是任务验收 A1–A10）、`:152-167`（作废条件与读数口径） | A 轴的定义与边界 |
| `testing/ab/bank/harness/README.md` | `:109-131`（run.json 九键）、`:133-148`（冻结与作废） | 21 份 record 的运行上下文 |
| `testing/ab/bank/run-record/README.md` | `:54-65`（采集器退出码）、`:76-153`（schema 1.0 十键）、`:156-163`（三态）、`:181-215`（C/A 逐字段）、`:270-314`（确定性、C 的 config root、A 的读法、边界） | 字段名、三态、C/A 语义 |
| 三题 `task-package/acceptance.md` | 各自 `:8-20` 左右（任务验收 A1–A…） | 区分「任务验收 A1–A10」与「结构谓词 A1–A10」 |
| 三题 `scoring.yaml` | `dimension_a.predicates`（cross `:250-257`、async `:267-274`、docs `:263-270`）、`dimension_c.file_set` | A 谓词 id/名字/阈值、C 文件集 |
| 三题 `README.md` | cross `:115-135`（四维分开读、C 30/30、ARCH-001 只在 controller 参与）、async `:266-333`（T/A/C 天花板与 skip 口径）、docs `:114-129`（allow_with_warnings、跳过≠通过、文档类目标不取证） | C/A 读法与本次观测的对照 |
| 三题 `hidden/PLAN.md` 与 `hidden/runner.py` | PLAN `:1-30`（用例分组/契约）；runner `CASE_IDS` 与 `SCHEMA_VERSION`（cross `:45-50`、async `:44-48`、docs `:49-53`） | T 的分母是隐藏用例，和 A 的结构谓词不是同一条轴 |
| `testing/ab/dgate2/configs/before/validation/test-layout.yaml` 与 `after/...` | before `:18-19`、after `:23-25`：唯一差异是 after 的 `production_patterns` 多 `tools/**/*.py` | 说明 treatment 的 test-layout 快照差异；C 的 `config_root` 固定仓库根，不据此把差异读进 C |
| `.tmp/k3/freeze-<task>.json` / `.tmp/k3/exp-set-<task>.json` | 3 份 freeze 的 `combined_digest` 与 entries：async `87a8bbf5…`(120)、docs `9e507374…`(119)、cross `4e8e4bcf…`(119) | 与 run-ready 的冻结值核对 |
| `.tmp/k3/runs27/<run>/run-record.json` | 21 份，字段路径见 §2；逐 run 行号锚点见 §2.2/§2.3 | 本步主表 |
| `.tmp/k3/runs27/<run>/partial.json` | 6 份，行号见 §2.5 | 6 个 T-only 的 unavailable 读数 |

**机读证据（只读脚本，放在 `.tmp/k3/guards/`，不提交）**：

```text
.venv/Scripts/python.exe .tmp/k3/guards/extract.py .tmp/k3/guards/extract.json
  -> exit 0；21 份 record + 6 份 partial 的逐文件/逐字段展开
.venv/Scripts/python.exe .tmp/k3/guards/summarize.py .tmp/k3/guards/summary.json
  -> exit 0；紧凑 C/A 摘要（decision 分布、violations、级别、A failed_ids）
.venv/Scripts/python.exe .tmp/k3/guards/verify.py
  -> exit 0；21/21 不变量与合计（本文件 §2.1/§2.3/§2.4 的机读来源）
.venv/Scripts/python.exe .tmp/k3/guards/anchors.py
  -> exit 0；21 份 record 的 `A.failed_ids` / `C.summary.decisions` / violations 行号锚点
```

## 2 事实

### 2.1 21 份 record 的共同不变量

| 项 | 读数（21 份合计） | 证据 |
| --- | --- | --- |
| record 数 | 21 份 `run-record.json`；另有 6 份 `partial.json`（T-only） | `.tmp/k3/runs27/` 目录清单 |
| C/A 状态 | 21/21 `C.status=recorded`、`A.status=recorded`；`summary.all_recorded=true`；`unavailable_dimensions=[]` | `verify.py` 输出；`run-record.json` 的 `summary` |
| 规则集 | 21/21 的 `C.summary.rule_set_hashes` 都是单值 `sha256:73845ef515236940266b682631c02dec84c06886fa27a1e99f57e66284fae7d4` | `run-record.json` 的 `dimensions.C.summary.rule_set_hashes` |
| C 文件数与完整度 | cross/async 每 run 8 文件、docs 每 run 4 文件；144/144 文件 `check_volume.complete=true`，`check_volume_complete == files` | `run-record.json` 的 `dimensions.C.summary` |
| C 选择级别 | 144/144 文件 `selection.level=related` | 同上 |
| C 的 skip | 135/144 文件 `skipped_rule_ids=["ARCH-001@1"]`、`blocking_capable_skipped=1`、`matched=42`；9/144 文件（cross 的 `src/shop/order_controller.py`，layer=controller）无 skip、`served_checkers` 多 `forbidden_dependency`、`matched=43` | `run-record.json` 的 `dimensions.C.files[]` |
| C 的 decision | 无 `block`；有 warning 的 run 的 C 维度 `exit_code=1`，其余 `0` | `run-record.json` 的 `dimensions.C.exit_code` |
| C 文件级 decision 合计 | 144 个文件 = 134 `allow` + 10 `allow_with_warnings`；`block` 0 | `summary.json` 与 §2.2/§2.3 |
| A 的读数 | 10 谓词/run；21 run = 210 谓词，191 pass / 19 fail；A 维度 `exit_code` 0 或 1 | `run-record.json` 的 `dimensions.A` |
| 过程上下文 | 21/21 `process.exit={code:0,timeout:false}`、`process.invalid=[]`；模型 `deepseek-official/deepseek-flash`；dsh `0.2.1-rc.2` / `app_bundled`；sandbox `danger-full-access`（`host.sandbox=unrestricted`）；`start.worktree_clean=true` | `run-record.json` 的 `process` / `platform_generation.host` / `start` |
| 起点 HEAD | cross 9 份 `bcbc74c…`；其余 12 份 `bac565d…` | `run-record.json` 的 `start.head`；与 `readings/2026-10-23-bank-k3-27runs.md:8-9` 一致 |
| T 确定性 | 21/21 `determinism.checked=true`、`stdout_byte_identical=true`、`exit_code_identical=true` | `run-record.json` 的 `dimensions.T.determinism` |

> **两个字段读法**：`run-record.json` 没有 run 级单一 `C decision` 字段。本文件的「C decision」是
> `dimensions.C.summary.decisions` 的**文件级分布**（例如 `6 allow + 2 allow_with_warnings`）。
> C/A 维度的 `exit_code=1` 是「有 warning / 有谓词 fail」的读数，不是 `block` 或 `unavailable`
> （`run-record/README.md:54-65` 的采集器退出码与 `:209-215` 的 A 退出码分开；维度自己的三态在
> `:156-163`）。本步没有把 `exit 1` 读成失败，也没有把 `allow` 读成「全规则都查过」。

### 2.2 主表：21 份 run-record 的 C/A

`warn = allow_with_warnings`；「C violations」的级别由 `rule_id` 回查 `policies/<domain>/<ID>.yaml`
的 `severity`（本批出现的规则见 §2.3）。`A 失败数` = `len(dimensions.A.failed_ids)`。

| run_id | 题 | 臂 | block | C decision | C violations（条数 + 级别） | A failed_ids | A 失败数 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bank-crossmodule-refactor-A-b1 | crossmodule | A | 1 | 8 allow | 0 | — | 0 | A 10/10；C 8/8 complete |
| bank-crossmodule-refactor-A-b2 | crossmodule | A | 2 | 8 allow | 0 | — | 0 | A 10/10；C 8/8 complete |
| bank-crossmodule-refactor-A-b3 | crossmodule | A | 3 | 8 allow | 0 | — | 0 | A 10/10；C 8/8 complete |
| bank-crossmodule-refactor-B-b1 | crossmodule | B | 1 | 8 allow | 0 | — | 0 | A 10/10；C 8/8 complete |
| bank-crossmodule-refactor-B-b2 | crossmodule | B | 2 | 8 allow | 0 | — | 0 | A 10/10；C 8/8 complete |
| bank-crossmodule-refactor-B-b3 | crossmodule | B | 3 | 8 allow | 0 | — | 0 | A 10/10；C 8/8 complete |
| bank-crossmodule-refactor-C-b1 | crossmodule | C | 1 | 8 allow | 0 | — | 0 | A 10/10；C 8/8 complete |
| bank-crossmodule-refactor-C-b2 | crossmodule | C | 2 | 8 allow | 0 | — | 0 | A 10/10；C 8/8 complete |
| bank-crossmodule-refactor-C-b3 | crossmodule | C | 3 | 8 allow | 0 | — | 0 | A 10/10；C 8/8 complete |
| bank-async-concurrency-B-b1 | async | B | 1 | 6 allow + 2 warn | 11 warning / 0 error | A5, A6, A7 | 3 | A 7/10；C 8/8 complete |
| bank-async-concurrency-B-b2 | async | B | 2 | 7 allow + 1 warn | 8 warning / 0 error | A6, A7 | 2 | A 8/10；C 8/8 complete |
| bank-async-concurrency-B-b3 | async | B | 3 | 6 allow + 2 warn | 9 warning / 0 error | A6, A7 | 2 | A 8/10；C 8/8 complete |
| bank-async-concurrency-C-b1 | async | C | 1 | 7 allow + 1 warn | 8 warning / 0 error | A7 | 1 | A 9/10；C 8/8 complete |
| bank-async-concurrency-C-b2 | async | C | 2 | 7 allow + 1 warn | 9 warning / 0 error | A6, A7 | 2 | A 8/10；C 8/8 complete |
| bank-async-concurrency-C-b3 | async | C | 3 | 7 allow + 1 warn | 9 warning / 0 error | A6, A7 | 2 | A 8/10；C 8/8 complete |
| bank-docs-config-B-b1 | docs | B | 1 | 4 allow | 0 | A5, A9 | 2 | A 8/10；C 4/4 complete |
| bank-docs-config-B-b2 | docs | B | 2 | 4 allow | 0 | — | 0 | A 10/10；C 4/4 complete |
| bank-docs-config-B-b3 | docs | B | 3 | 4 allow | 0 | A5, A9 | 2 | A 8/10；C 4/4 complete |
| bank-docs-config-C-b1 | docs | C | 1 | 4 allow | 0 | — | 0 | A 10/10；C 4/4 complete |
| bank-docs-config-C-b2 | docs | C | 2 | 2 allow + 2 warn | 15 warning / 0 error | A7, A9 | 2 | A 8/10；C 4/4 complete |
| bank-docs-config-C-b3 | docs | C | 3 | 4 allow | 0 | A9 | 1 | A 9/10；C 4/4 complete |

**逐 run 行号锚点**（每条记录内 `run-record.json` 的行号；`A.failed_ids` 在 `dimensions.A`，
`C.summary.decisions` 在 `dimensions.C.summary`）：

| 组 | C.summary.decisions | A.failed_ids |
| --- | --- | --- |
| crossmodule A/B/C，b1–b3 | `run-record.json:643`（9 份相同） | `run-record.json:369`（9 份相同） |
| async B，b1 / b2 / b3 | `:661` / `:656` / `:658` | `:369` / `:369` / `:369` |
| async C，b1 / b2 / b3 | `:655` / `:657` / `:657` | `:369` / `:369` / `:369` |
| docs B，b1 / b2 / b3 | `:343` / `:340` / `:343` | `:189` / `:189` / `:189` |
| docs C，b1 / b2 / b3 | `:340` / `:360` / `:342` | `:189` / `:189` / `:189` |

### 2.3 C 的逐文件 violations（7 个 run，10 个文件）

21 份 record 的 144 个文件里，只有 10 个文件有 violations；10 个文件的 `decision` 都是
`allow_with_warnings`，`violations` 条数与 `violation_rules` 长度逐项相等。全部 69 条都指向
`DOC-001@1`；没有 error 级、没有其他规则 id。

| run_id | file | decision | violations | rule（`<id>@<version>`） | 行号锚点 |
| --- | --- | --- | --- | --- | --- |
| bank-async-concurrency-B-b1 | `tests/test_notify_worker.py` | allow_with_warnings | 10 | DOC-001@1 | `run-record.json:590` / `:622` |
| bank-async-concurrency-B-b1 | `tools/notify_smoke.py` | allow_with_warnings | 1 | DOC-001@1 | `:632` / `:655` |
| bank-async-concurrency-B-b2 | `tests/test_notify_worker.py` | allow_with_warnings | 8 | DOC-001@1 | `:589` / `:619` |
| bank-async-concurrency-B-b3 | `tests/test_notify_worker.py` | allow_with_warnings | 8 | DOC-001@1 | `:589` / `:619` |
| bank-async-concurrency-B-b3 | `tools/notify_smoke.py` | allow_with_warnings | 1 | DOC-001@1 | `:629` / `:652` |
| bank-async-concurrency-C-b1 | `tests/test_notify_worker.py` | allow_with_warnings | 8 | DOC-001@1 | `:588` / `:618` |
| bank-async-concurrency-C-b2 | `tests/test_notify_worker.py` | allow_with_warnings | 9 | DOC-001@1 | `:589` / `:620` |
| bank-async-concurrency-C-b3 | `tests/test_notify_worker.py` | allow_with_warnings | 9 | DOC-001@1 | `:589` / `:620` |
| bank-docs-config-C-b2 | `tests/test_check_config.py` | allow_with_warnings | 3 | DOC-001@1 | `:254` / `:279` |
| bank-docs-config-C-b2 | `tests/test_config.py` | allow_with_warnings | 12 | DOC-001@1 | `:289` / `:323` |

**级别来源**：`policies/coding/DOC-001.yaml:3-4`（`id: DOC-001` / `version: 1`）与 `:9`
（`severity: warning`）。run-record 1.0 只保留 `violations`（条数）与 `violation_rules`
（`<id>@<version>`），不保留 message/severity（`run-record/README.md:196-201`）；本表的
「warning」是从 rule id 回查规则数据得到的，不是从 decision 文本推断的。

### 2.4 A 的失败谓词（19 次失败，10 个 run）

A 的 id 是 `scoring.yaml` 的 `dimension_a.predicates`（`structure_metrics` 1.1 的 10 条结构谓词），
**不是** `task-package/acceptance.md` 的任务验收 A1–A…。三题的谓词同名同阈值：

| id | 名称（阈值） | 失败的 run（次数） |
| --- | --- | --- |
| A5 | 函数复杂度（圈复杂度 > 10 的函数 0 个） | async B-b1；docs B-b1；docs B-b3（3） |
| A6 | 文件/函数长度（文件 > 200 行或单函数 > 50 行 0 处） | async B-b1/b2/b3；async C-b2/b3（5） |
| A7 | docstring 覆盖（模块与公开定义缺失 0 处） | async B-b1/b2/b3；async C-b1/b2/b3；docs C-b2（7） |
| A9 | 测试对应完备（每个生产文件都有测试层静态 import） | docs B-b1/b3；docs C-b2/b3（4） |
| A1 / A2 / A3 / A4 / A8 / A10 | 分层方向 / 依赖无环 / 公开符号最小面 / 组合根唯一 / 依赖扇出 / 无动态执行 | 0 次 |

- 谓词声明：cross `scoring.yaml:250-257`、async `:267-274`、docs `:263-270`；三题的 A5/A6/A7/A9
  名称与阈值相同。结构谓词与任务验收的区分见 `testing/ab/bank/README.md:59-62`。
- 19 次失败分布在 10 个 run：async B 3/3、async C 3/3、docs B 2/3、docs C 2/3；cross 9/9 无失败。
  另外 11 个 run 是 A 10/10（cross 9 + docs B-b2 + docs C-b1）。
- 有 7 个 run 的 A7 失败，恰与有 `DOC-001@1` warning 的 7 个 run 是同一集合
  （`verify.py` 的 `A7_fail_set == DOC001_run_set: True`）；本读数不据此推断因果，只记这个重合。

### 2.5 6 个 T-only：C/A 记 unavailable（不重跑）

这 6 个 run 只有 `partial.json`，没有 `run-record.json`；`partial.json` 的 `record_status` 是
`unavailable_c`，`c.status` 与 `a.status` 都是 `unavailable`、`reason` 都是 `file_set missing`。
按使用者授权的 T-only 补充规则，C/A 记 `unavailable`，不补造、不推断、不重跑。

| run_id | 题 | 臂 | block | C | A | 证据 |
| --- | --- | --- | --- | --- | --- | --- |
| bank-async-concurrency-A-b1 | async | A | 1 | unavailable（file_set missing：`src/shop/notify_worker.py`） | unavailable（同左） | `partial.json:8-9`、`:45-51` |
| bank-async-concurrency-A-b2 | async | A | 2 | unavailable（file_set missing） | unavailable（同左） | `partial.json:8`、`:29-35` |
| bank-async-concurrency-A-b3 | async | A | 3 | unavailable（file_set missing） | unavailable（同左） | `partial.json:8`、`:28-34` |
| bank-docs-config-A-b1 | docs | A | 1 | unavailable（file_set missing） | unavailable（同左） | `partial.json:8`、`:32-38` |
| bank-docs-config-A-b2 | docs | A | 2 | unavailable（file_set missing） | unavailable（同左） | `partial.json:8`、`:32-38` |
| bank-docs-config-A-b3 | docs | A | 3 | unavailable（file_set missing） | unavailable（同左） | `partial.json:8`、`:32-38` |

- async A-b1 的 `reason` 点名了缺件：`collect refused C file_set missing src/shop/notify_worker.py;
  user-authorized T-only rule`（`partial.json:9`）；其余 5 份只写 `file_set missing`（不补造具体文件名）。
- 6 个 T-only 的 T 原值仍在 `partial.json`（不属本步交付），本步只读它们的 C/A 状态。

### 2.6 与 `readings/2026-10-23-bank-k3-27runs.md` 交叉核对

| 27runs 位置 | 已写读数 | 本步逐项核对 | 结果 |
| --- | --- | --- | --- |
| `:33-43`（T 矩阵） | cross 9×33/33；async B/C 各 3×38/38；docs B 3×36/39、docs C 3×39/39 | 21 份 record 的 `dimensions.T.summary` | 逐项相同 |
| `:70-74`（C decision） | cross 9×8/8 allow；async B b1/b2/b3 = 6/2、7/1、6/2；async C b1/b2/b3 = 7/1、7/1、7/1；docs B 3×4 allow；docs C b1/b2/b3 = 4、2+2、4 | §2.2 的 C decision 列 | 逐项相同 |
| `:70-74`（C violations） | cross 9×0；async B 11/8/9；async C 8/9/9；docs B 3×0；docs C 15（只在 b2） | §2.3 的逐文件表 | 逐项相同 |
| `:70-74`（A passed/total） | cross 9×10/10；async B 7/10、8/10、8/10；async C 9/10、8/10、8/10；docs B 8/10、10/10、8/10；docs C 10/10、8/10、9/10 | §2.2 的 A 列与 §2.4 的失败集合 | 逐项相同 |
| `:75`（A 臂 unavailable） | async/docs A 的 6 个 C/A `unavailable` | §2.5 的 6 份 `partial.json` | 相同 |
| `:45-46`（21 完整 + 6 T-only） | 21 个完整 run-record + 6 个 T-only | 目录文件计数 | 相同 |
| `:57-64`（共同检查） | 27/27 exit 0、invalid=[]、freeze/host/首树通过 | 21 份 record 的 `process.exit` / `process.invalid` / `start.worktree_clean` / `host` | 在 21 份上全部成立 |

**不一致点名**：本步没有发现与 27runs 已写 C/A/T 读数不一致的项；因此没有需要改口的句子。
27runs §6 的 T 句子只引用 T（`:80-88`）；按 TAKEOVER-SPEC §4 的口径，本步的 C/A 失败
不改变 T 的计数。

## 3 判定（限定在 TAKEOVER-SPEC §4 口径内）

### 3.1 哪些 warning 出现过

**只有 `DOC-001@1`（warning）**：69 条，分布在 7 个 run、10 个文件（§2.3）。没有 error 级
violation，没有第二个 rule id。`DOC-001` 是 `missing_docstring` checker 的 warning
（`policies/coding/DOC-001.yaml:9-12`），不是阻断级规则。

### 3.2 哪些 A 失败出现过

**只有 A5、A6、A7、A9**：19 次失败，分布在 10 个 run（§2.4）。A1/A2/A3/A4/A8/A10 在 21 份
record 上一次都没有失败。A5/A6/A7/A9 都是 `structure_metrics` 的结构谓词，不是任务验收的
A1–A10（`testing/ab/bank/README.md:59-62`）。

### 3.3 逐条判断「是否影响对 T 的解释」

只使用 TAKEOVER-SPEC §4 要求的两种措辞；每条的「T 的计数」指 hidden runner 的 `passed/total`。

| 项 | 出现的 run | 判断 |
| --- | --- | --- |
| `DOC-001@1` warning（69 条） | async B 3、async C 3、docs C-b2 | **不改变 T 的计数** |
| A5 函数复杂度（3 次） | async B-b1、docs B-b1、docs B-b3 | **不改变 T 的计数** |
| A6 文件/函数长度（5 次） | async B-b1/b2/b3、async C-b2/b3 | **不改变 T 的计数** |
| A7 docstring 覆盖（7 次） | async B 3、async C 3、docs C-b2 | **不改变 T 的计数** |
| A9 测试对应完备（4 次） | docs B-b1/b3、docs C-b2/b3 | **不改变 T 的计数** |

判断依据（不是结论句）：T 是 `hidden/runner.py` 的用例计数（PLAN 的 T/EN/I 分组，
`hidden/PLAN.md:1-30`；runner 的 `CASE_IDS` / `SCHEMA_VERSION` 见三题 runner 的 `:44-53`），
C 是 `policy.check` 的文件级 decision，A 是 `structure_metrics` 的 10 条结构谓词；三者是分开的
读数轴，C/A 的 `exit 1` 也不改写 T 的 `passed/total`。27runs 的 §5 已逐 run 写出 A 的
`passed/total`，`§6` 的 T 句子只引用 T（`:80-88`），所以本步没有发现需要改写的 T 句子。

> 这里**不写**「因此结论成立」；本步只回答 C/A 读数与它们对 T 计数的影响。

## 4 不能说的（边界、缺口、未覆盖）

- **不能说 treatment 效应**：本步没有 A/B/C 的对照比较，也没有 `before/after` 的 C 差异；C 的
  `config_root` 固定仓库根（`run-record/README.md:284-286`），A/B 的 test-layout 快照差异
  （before `:18-19` vs after `:23-25`）没有被读进 C 的判定。C/A 只是回归守卫，不是 T 的替代或总分。
- **不能说 C 的分数**：run-record 没有分数字段；本步没有计算 C 的 weighted / `effective_total` /
  `not_applicable` 折算。`allow` 不等于「43 条规则都查过」：135/144 文件有
  `skipped_rule_ids=["ARCH-001@1"]`（`blocking_capable_skipped=1`），只有 cross 的 9 个
  `order_controller.py` 无 skip；按题 README 的口径，**跳过不是通过**（`tasks/bank-docs-config/README.md:121-124`、
  `tasks/bank-async-concurrency/README.md:329-331`）。
- **不能把 A 的 id 混成任务验收**：本步的 A5/A6/A7/A9 是 `structure_metrics` 的结构谓词；
  `task-package/acceptance.md` 的 A1–A12（按题）是另一张表（例如 async 的 A5 = 停机排空、A6 = 取消、
  A7 = 共享队列、A9 = notify_smoke）。两者都叫「A#」，但不是同一判据。
- **不能推断 6 个 T-only 的 C/A**：它们没有 `run-record.json`；`partial.json` 只给
  `unavailable/file_set missing`，不能补造成 pass/fail，也不能用 T 原值反推 C/A。
- **不能复原每条违规的原文**：run-record 1.0 只保留条数与 `violation_rules`，不保留
  message/severity；本步的「warning」是从 `policies/coding/DOC-001.yaml:9` 回查的，无法从
  run-record 复原每条违规的文本、行号或 checker 输出。
- **不能把 21 份的 C/A 外推到 27 run**：21 份是 `all_recorded=true` 的完整 record；6 个 T-only
  的 C/A 是 unavailable。21 份的 `C.summary.rule_set_hashes` 只有一份规则集哈希
  `sha256:73845e…`，但这只是该批 21 次采集的读数，不是跨批/跨宿主的不变量。
- **不能外推**：n=3、1 个模型身份（`deepseek-official/deepseek-flash`）、app 自带 dsh 0.2.1-rc.2、
  headless、`danger-full-access`；本步没有重跑、没有新采集、没有新审批。
- **预存 errata 不在本步范围**：`COMMAND-FAMILIES.md` 的 sha 与 scoring 的
  `command_families_sha256` 不符、async/docs README 的 `task-package/interfaces.md` 哈希行错，
  本步已知、未改字节（`readings/2026-10-22-bank-k3-run-ready.md:108-119`）。
