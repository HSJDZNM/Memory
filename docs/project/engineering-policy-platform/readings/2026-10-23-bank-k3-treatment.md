# 2026-10-23 题库 k≥3 · treatment 收尾（STEP 3）

> **生成**：2026-10-23T12:19:22+08:00（Asia/Shanghai）
> **HEAD**：`604da744e83492103fb3828b9ff458c584fb4fdb`
> **性质**：STEP 3 单步交付。只落三题 T 的**原值 + 方向计数 + 机制说明**；n=3，不写
> 「有效 / 显著 / 提升 / 优于 / 证明」，不写均值 / 中位数 / 百分比 / 区间 / 显著性，不做跨题总分。
> 不重跑 run 或测试、不改 hidden/scoring/freeze/臂配置、不写 run-record、不 push、不 cleanup。
> **口径一句话**：27 个 run 的 T 以各 run 的 `dimensions.T.summary`（21 份 `run-record.json`）或
> `t.summary`（6 份 `partial.json`，T-only）为原值，方向计数只按同题同 block 的 A/B/C 逐次比较；
> 机制只用臂配置差异、pre-execute 审计记录与最终树缺件说明，不从 T 反推效应。
> **证据目录**：`.tmp/k3/treatment/`（`summarize.py`、`summary.json`）。本文件是本次唯一受跟踪交付。
> **现场偏差（按 §0「现场优先」记录）**：§1 期望 HEAD `c4d3d57`，现场 `604da74`。多出的两个提交
> `a6d987e` / `604da74` 分别只新增 STEP 1/2 的读数文件（`git show --stat` 见 §1），不触达
> `.tmp/k3/runs27/`、hidden/scoring/freeze/臂配置，也不改任何 run-record；因此不影响本步的 T 读数。

## 1 开工核对（§1）

```text
$ git log --oneline -5
604da74 docs(bank): 落 k3 C/A 守卫读数
a6d987e docs(bank): 落 k3 H2 盲抽读数
c4d3d57 docs(bank): 补 27 run 的 HEAD 说明
e39300f docs(bank): 落 k3 27 run 最终读数（T-only 补充规则）
bac565d docs(bank): 落 k3 27 run 第 10/27 停点

$ git status --short
（无输出）

$ git show --stat --oneline 604da74
604da74 docs(bank): 落 k3 C/A 守卫读数
 .../readings/2026-10-23-bank-k3-guards.md          | 273 +++++++++++++++++++++
 1 file changed, 273 insertions(+)

$ git show --stat --oneline a6d987e
a6d987e docs(bank): 落 k3 H2 盲抽读数
 .../readings/2026-10-23-bank-k3-h2.md              | 308 +++++++++++++++++++++
 1 file changed, 308 insertions(+)
```

- 工作树干净；HEAD 与 §1 期望不同，但差异只来自 STEP 1/2 的读数提交（各 1 file changed，均只新增 readings）。
- 判据：本步读的是 `.tmp/k3/runs27/` 与 `analysis27.json` 的既有现场，两个提交都没有改这些文件、
  也没有改 hidden/scoring/freeze/exp-set/臂配置；继续执行，读数头部如实写偏差。

## 2 事实

### 2.1 必读核对（读了什么、用在哪）

| 来源 | 用到的位置 | 用途 |
| --- | --- | --- |
| `readings/2026-10-23-bank-k3-27runs.md` | `:13-17`（27/27 与 21+6）、`:31-43`（T 矩阵）、`:45-46`（确定性）、`:57-64`（共同检查）、`:80-88`（结论上限）、`:97-101`（边界） | T 原值与方向计数的**唯一引用来源** |
| `readings/2026-10-23-bank-k3-27runs-stop.md` | `:26-35`（async A-b1 停点）、`:39-44`（T-only 选项）、`:46-50`（边界） | 6 个 T-only 的来源与「不补造」口径 |
| `readings/2026-10-22-bank-k3-run-ready.md` | `:16-30`（freeze/审批/TTL）、`:89-108`（27 run 计划与签核）、`:108-119`（预存 errata） | 环境、签核范围与 errata |
| `readings/2026-10-22-bank-k3-deliberations.md` | `:117-168`（§3 门与预注册，结论上限在 `:163-168`） | n=3 能写/不能写的边界 |
| `readings/2026-10-23-bank-k3-h2.md` | `:272-289`（判定）、`:293-298`（边界） | 限制节的 H2 结论与缺口 |
| `readings/2026-10-23-bank-k3-guards.md` | `:179-196`（6 个 T-only 的 C/A）、`:235-244`（C/A 不改变 T 计数）、`:261-270`（边界） | 限制节的 C/A unavailable 口径 |
| `bank/README.md`（`testing/ab/bank/`） | `:59-62`（A 谓词与任务验收 A1–A… 的区别）、`:123`（crossmodule 无 treatment 差异）、`:152-167`（作废与读数口径） | 轴的定义与负对照 |
| `bank/harness/README.md` | `:110-131`（run.json 九键）、`:133-148`（冻结/作废） | 现场证据的位置 |
| `bank/run-record/README.md` | `:156-163`（三态）、`:165-176`（T）、`:181-215`（C/A）、`:279-314`（边界） | 「完整 run-record」与 T-only 的区别 |
| `tasks/bank-async-concurrency/README.md` | `:16-55`（基线/允许写）、`:105-108`（规则点）、`:230-264`（§8.6 A/B 设计方向实测）、`:272-291`（T 天花板） | async 的机制 |
| `tasks/bank-docs-config/README.md` | `:12-45`（基线/允许写）、`:131-148`（规则点）、`:220-224`（M1 的 A/B 设计方向） | docs 的机制 |
| `tasks/bank-crossmodule-refactor/README.md` | `:33-43`（允许写，无 `tools/`）、`:96-112`（规则点）、`:127-135`（天花板） | cross 的负对照机制 |
| 三题 `hidden/PLAN.md` | async `:167-263`（EN1–EN8、I3–I7）；docs `:49-80`（T18–T26、EN3–EN7、I3–I6）；cross `:1-30`（分组） | 失败 id 与缺件的对应 |
| `dgate2/configs/{before,after}/validation/test-layout.yaml` | before `:18-19`；after `:23-25` | 两臂 `production_patterns` 的唯一差异 |
| `bank/arm-configs/{A,B}/dsh-adapter.yaml` | 两份 `:51-55` | `pre_evidence.registry_root` 指向 before/after |
| `dgate2/c-arm/README.md` | `:30-37`（C 臂与 A/B 的差别） | C 是不治理对照 |
| `.tmp/k3/runs27/analysis27.json`、`run/run.json`、`run-record.json` / `partial.json`、`tree/.policy/audit.jsonl` | 27 个目录 | T 原值、缺件与 pre-execute 阻断的现场 |
| `.tmp/k3/freeze-<task>.json` | `manifest.combined_digest` 与 `counts` | 三份 freeze 摘要 |

### 2.2 T 原值（27 run）

引用 `readings/2026-10-23-bank-k3-27runs.md:15-16` 原文：

> T 原值：crossmodule 9 个全 **33/33**（A=B=C）；async A **14/30/31**、B **38/38/38**、C **38/38/38**；
> docs A **28/28/28**、B **36/36/36**、C **39/39/39**。按原口径 A 的 6 个 T-only 不是完整 run-record，
> 因此只作描述性读数，不写「有效/显著/提升」。

同文件 `:33-43` 的逐 block 矩阵：

| 题 | block | 臂序 | A | B | C |
| --- | --- | --- | --- | --- | --- |
| bank-crossmodule-refactor | b1 | A/B/C | 33/33 | 33/33 | 33/33 |
| bank-crossmodule-refactor | b2 | B/C/A | 33/33 | 33/33 | 33/33 |
| bank-crossmodule-refactor | b3 | C/A/B | 33/33 | 33/33 | 33/33 |
| bank-async-concurrency | b1 | A/B/C | **14/38**（T-only） | 38/38 | 38/38 |
| bank-async-concurrency | b2 | B/C/A | **30/38**（T-only） | 38/38 | 38/38 |
| bank-async-concurrency | b3 | C/A/B | **31/38**（T-only） | 38/38 | 38/38 |
| bank-docs-config | b1 | A/B/C | **28/39**（T-only） | 36/39 | 39/39 |
| bank-docs-config | b2 | B/C/A | **28/39**（T-only） | 36/39 | 39/39 |
| bank-docs-config | b3 | C/A/B | **28/39**（T-only） | 36/39 | 39/39 |

本步从现场文件独立复核（只读 JSON，不跑 runner）：

```text
$ .venv/Scripts/python.exe .tmp/k3/treatment/summarize.py
runs=27 complete_records=21 t_only=6
bank-async-concurrency: A=[14, 30, 31] B=[38, 38, 38] C=[38, 38, 38]
bank-docs-config: A=[28, 28, 28] B=[36, 36, 36] C=[39, 39, 39]
bank-crossmodule-refactor: A=[33, 33, 33] B=[33, 33, 33] C=[33, 33, 33]
```

- 21 份 `run-record.json` 的 `dimensions.T.summary` 与 6 份 `partial.json` 的 `t.summary` 逐项等于上表；
  两次 T 运行 `stdout_byte_identical=true`（21/21 record 的 `dimensions.T.determinism`，6/6 partial 的
  `t.byte_identical`）。
- 6 个 T-only 的 T 原值分别为 14/38、30/38、31/38、28/39、28/39、28/39；它们的 C/A 是
  `unavailable`，不是 0 分（`run-record/README.md:156-163`）。

### 2.3 方向计数

引用 `readings/2026-10-23-bank-k3-27runs.md:82` 原文：

> **T 原值方向计数**：crossmodule A=B 3/3（C 也同值）；async A<B 3/3（B=C 38/38）；
> docs A<B 3/3 且 B<C 3/3（36 vs 39）。

本步按同题同 block 逐次重算（`summary.json.directions`；`<` / `>` / `=` 是 T 原值的大小关系）：

| 题 | 比较 | `<` | `>` | `=` | 逐 block |
| --- | --- | --- | --- | --- | --- |
| crossmodule | A vs B | 0 | 0 | 3 | 33=33、33=33、33=33 |
| crossmodule | B vs C | 0 | 0 | 3 | 33=33、33=33、33=33 |
| crossmodule | A vs C | 0 | 0 | 3 | 33=33、33=33、33=33 |
| async | A vs B | 3 | 0 | 0 | 14<38、30<38、31<38 |
| async | B vs C | 0 | 0 | 3 | 38=38、38=38、38=38 |
| async | A vs C | 3 | 0 | 0 | 14<38、30<38、31<38 |
| docs | A vs B | 3 | 0 | 0 | 28<36、28<36、28<36 |
| docs | B vs C | 3 | 0 | 0 | 36<39、36<39、36<39 |
| docs | A vs C | 3 | 0 | 0 | 28<39、28<39、28<39 |

- 可以写的只有方向计数：async 与 docs 的 **A<B 3/3**，docs 的 **B<C 3/3**，cross 的 **A=B=C 3/3**。
- 本表不计算差值、不做均值 / 百分比 / 区间 / 显著性，也不给跨题合计。

### 2.4 「完整 run」口径：21 + 6

| 项 | 读数 | 证据 |
| --- | --- | --- |
| run 总数 | 27（3 题 × 3 臂 × 3 block） | `.tmp/k3/runs27/` 目录清单；`analysis27.json` 27 个元素 |
| 完整 `run-record.json` | **21**：cross 9 + async B/C 6 + docs B/C 6 | 21 份 record 的 `dimensions.T/C/A` 均可读 |
| T-only `partial.json` | **6**：async A b1–b3、docs A b1–b3 | `partial.json:8-9` `record_status=unavailable_c`；`c.status` / `a.status` 均 `unavailable` |
| 完整 run 的 T 维度 | 21/21 `recorded`，`determinism.checked=true`、两次逐字节相同 | `run-record.json` 的 `dimensions.T` |
| 6 个 T-only | 只有 T 是读数；C/A `unavailable`（`file_set missing`） | `readings/2026-10-23-bank-k3-guards.md:179-196` |

- **这 6 个 run 不计入「完整 run」统计**：上面的 21 是完整 run-record 的数量，T-only 的 6 个只作为
  **T 原值来源**参与 §2.2/§2.3，绝不与 21 份混读成同一口径的 C/A。
- 口径来源：`readings/2026-10-23-bank-k3-27runs.md:84`（「A 的 9 个 run 中 6 个是 T-only（C/A unavailable），
  按原口径不是完整 run-record；只能作描述性原值/方向」）；`run-record/README.md:279-299`（本载荷只采集、不判分）。
- 因此 §2.3 中所有涉及 async/docs **A 臂**的方向计数，依据的是 3 个 T-only 的 T 原值；
  cross 的 A 臂 3 个是完整 run-record。这一点直接决定下面能说/不能说的边界。

### 2.5 机制证据：A/B 的唯一配置差异与 pre-execute 阻断

**(a) 两臂配置差异只有 test-layout 快照。** A 与 B 的 `dsh-adapter.yaml` 除
`pre_evidence.registry_root` 外逐项相同：A 指 `configs/before`、B 指 `configs/after`
（`bank/arm-configs/A/dsh-adapter.yaml:51-55`、`.../B/dsh-adapter.yaml:51-55`）。两份 test-layout 的
`production_patterns` 不同：before 只有 `src/**/*.py`（`configs/before/validation/test-layout.yaml:18-19`），
after 另有 `tools/**/*.py`（`configs/after/validation/test-layout.yaml:23-25`）。两份 `sha256.txt` 的
`validation/test-layout.yaml` 摘要分别是 `69e9d4bb…` / `af70bee1…`。

**(b) 6 个 A run 都在 `tools/*.py` 的 create 上被 pre-execute 阻断。** 审计记录（hook 形态，无
`stage` 键）的 `decision=block`、`reason_code=policy_block`，violation 是 `TESTING-002@1` /
`critical`（`evidence.detail=uncovered_checker`），`pre_evidence.served_checkers` 缺 `failing_tests`：

| run | 审计位置 | file / operation | violation | served_checkers | test-layout 摘要 |
| --- | --- | --- | --- | --- | --- |
| bank-async-concurrency-A-b1 | `tree/.policy/audit.jsonl:38` | `tools/notify_smoke.py` / create | `TESTING-002@1` critical | missing_docstring, missing_tests, style_lint | `69e9d4bb…` |
| bank-async-concurrency-A-b2 | `tree/.policy/audit.jsonl:24` | `tools/notify_smoke.py` / create | 同上 | 同上 | `69e9d4bb…` |
| bank-async-concurrency-A-b3 | `tree/.policy/audit.jsonl:24` | `tools/notify_smoke.py` / create | 同上 | 同上 | `69e9d4bb…` |
| bank-docs-config-A-b1 | `tree/.policy/audit.jsonl:20` | `tools/check_config.py` / create | 同上 | 同上 | `69e9d4bb…` |
| bank-docs-config-A-b2 | `tree/.policy/audit.jsonl:20` | `tools/check_config.py` / create | 同上 | 同上 | `69e9d4bb…` |
| bank-docs-config-A-b3 | `tree/.policy/audit.jsonl:26` | `tools/check_config.py` / create | 同上 | 同上 | `69e9d4bb…` |

- 同一记录的 `pre_evidence.validators` 里 `tool.pytest@1.0` 的 reason 是
  「变更集里没有生产文件，测试选择不适用」；violation 的 message 是
  「没有验证器为 checker failing_tests 提供证据，拒绝在没有证据的情况下判定通过」。
- **B 的对照面**（docs B-b1 同一文件、同一操作）：`tree/.policy/audit.jsonl:27` 的
  `decision=allow`、`reason_code=enforcement_allow`，`served_checkers` 含 `failing_tests`，
  `test_layout.digest=af70bee1…`，`tool.pytest@1.0` 的 reason 是「选中的测试全部通过」。
- 这不是本步新造的判据：两题 README 的构造期实测已写明 A `block` / B `allow` 的设计方向与
  `selection.level`（async `README.md:248-260`；docs `README.md:220-224`）；规则点表同样把这条列成
  A 臂 `block` / B 臂 `allow`（async `README.md:105-108`）。

**(c) 最终树缺件与 T 失败的对应（只列缺件事实，不推断模型意图）。**

| run | 最终树缺的任务文件 | T 原值 | 失败 id |
| --- | --- | --- | --- |
| async A-b1 | `src/shop/notify_worker.py`、`tools/notify_smoke.py` | 14/38 | T09–T23、EN1–EN3、EN7、EN8、I1–I3、I7 |
| async A-b2 | `tools/notify_smoke.py` | 30/38 | EN1–EN3、EN7、EN8、I3、I5、I7 |
| async A-b3 | `tools/notify_smoke.py` | 31/38 | EN1–EN3、EN7、EN8、I3、I7 |
| docs A-b1/b2/b3 | `tools/check_config.py` | 28/39 | T19、T25、EN3–EN7、I3–I6 |
| docs B-b1/b2/b3 | 无缺件；`config/app.yaml` 仍是 v1（`retry: 3`） | 36/39 | T19、EN3、EN6 |
| docs C-b1/b2/b3 | 无缺件；`config/app.yaml` 已是 v2 | 39/39 | — |
| cross A/B/C（9 个） | 无缺件 | 33/33 | — |

- async A-b1 另有 `src/shop/notify_worker.py` 的 create 被 `TESTING-002@1` 阻断（5 条 violation，
  `tree/.policy/audit.jsonl:83`）；A-b2/b3 各有一次 `tests/test_notification.py` 的 `STYLE-002@1` 阻断
  （普通 error，不是 tools 选择问题）。本读数只记这些阻断是现场事实。
- docs 的 T19/EN3/EN6 都对「树里的 `config/app.yaml` 是 v2」有直接依赖
  （`hidden/PLAN.md:50`、`:65`、`:68`）；三份 B 树的 `config/app.yaml:4` 仍是 `retry: 3`
  （三份 C 树是 `retry_policy:`，见各树 `config/app.yaml:2-6`）。这一点是 B 与 C 在 docs 上的
  可见差异，**不是**某条规则在 B 上阻断了 config 写入（审计里没有该文件的 policy block）。

**(d) C 臂是不治理对照。** C 不加载 `--patch`、树里没有 `.policy`（`dgate2/c-arm/README.md:30-37`）；
27 run 现场里 C 的 audit 记录 0、批账本 0（`readings/2026-10-23-bank-k3-27runs.md:63`）。cross 的允许写
没有 `tools/`（`tasks/bank-crossmodule-refactor/README.md:33-43`、`task-package/allowed-writes.txt`），
按构造没有 A/B 的 M1 岔口，9 个 run 因此都是 33/33（`bank/README.md:123`）。

### 2.6 环境与冻结（一次实验、n=3）

| 项 | 读数 | 证据 |
| --- | --- | --- |
| 结构 | 3 题 × 3 臂 × 3 block；题序 cross → async → docs；块内 ABC/BCA/CAB；串行 | `readings/2026-10-23-bank-k3-27runs.md:29`、`:31-43` |
| 模型 / 宿主 | `deepseek-official/deepseek-flash`；app 自带 dsh `0.2.1-rc.2`；`headless` | 27runs `:21-25`；21 份 record 的 `platform_generation.host` |
| 沙箱 | `danger-full-access`（`host.sandbox=unrestricted`） | `run/run.json` 的 `sandbox.mode` |
| freeze | async `87a8bbf5…`（120）、docs `9e507374…`（119）、cross `4e8e4bcf…`（119） | `.tmp/k3/freeze-<task>.json` 的 `manifest.combined_digest`；27runs `:26` |
| 审批 / TTL | A `282b4925…`（2 条）、B `3c697d97…`（2 条）；TTL `2026-10-29T12:38Z` | `readings/2026-10-22-bank-k3-run-ready.md:26-28` |
| 运行结果 | 27/27 `exit.code=0`、`timeout=false`、`invalid=[]` | 27runs `:57-64`；21 份 record 的 `process.exit` / `process.invalid` |
| T 确定性 | 21/21 record `determinism.stdout_byte_identical=true`；6/6 partial `byte_identical=true` | `run-record.json` 的 `dimensions.T.determinism`；`partial.json` 的 `t` |

## 3 机制说明（只描述现场，不做判定）

### 3.1 A/B 的机制：tools 是不是生产文件

treatment 的交付路径是 `validation/test-layout.yaml` 快照：A 用 before（`production_patterns` 只有
`src/**/*.py`），B 用 after（另加 `tools/**/*.py`）。两题的任务都要新建一个 `tools/*.py` 脚本
（async `tools/notify_smoke.py`、docs `tools/check_config.py`），且 M1 就在批为空时写它
（async `README.md:240-246`、docs `README.md:220-224`）。在 A 的快照下，这个 create 没有生产文件
身份 → 测试选择为空 → `failing_tests` 没有被服务 → `TESTING-002@1` 以 `uncovered_checker` 阻断
（§2.5(b)）；B 的快照把它当生产文件 → 选到同名的基线测试并跑通 → allow。

这条机制与最终树的缺件直接对齐：async 三个 A run 都缺 `tools/notify_smoke.py`；docs 三个 A run 都缺
`tools/check_config.py`。async A-b2/b3 已把 `notify_worker.py` 写进树，所以 T 的 worker 核心用例
（T09–T23）都通过，只余入口/树形状类失败（EN1–EN3、EN7、EN8、I3、I5、I7）；async A-b1 连
`notify_worker.py` 也缺，T09–T23 与 I1/I2 一并失败（总表见 §2.5(c)）。docs A 的缺件同时导致
`tools.check_config` 相关的 EN3–EN7、I3–I6 与文件集合 T25 失败，其 T19 则与 B 一样来自
`config/app.yaml` 未迁移。

### 3.2 cross 的机制：没有 tools 写面

cross 的允许写 10 条里没有 `tools/`，任务也不要求新建脚本；A/B 的 test-layout 差异在这道题上没有
可作用的写面。9 个 run 的 T 都是 33/33（A/B/C 各 3 个），与「负对照按构造不应有 A/B 差异」一致
（`bank/README.md:123`）。这只是本批 3 个 block 的现场读数，不是对 cross 的普遍断言。

### 3.3 docs 的 B/C 差异：B 的最终树仍有 v1 配置

B 与 C 的 T 方向是 36<39（3/3）。现场可见的差别是：B 三个 block 的最终树里 `config/app.yaml` 都还是
`retry: 3`（`.../bank-docs-config-B-b*/tree/config/app.yaml:4`），C 三个 block 都已是
`retry_policy`（`.../bank-docs-config-C-b*/tree/config/app.yaml:2-6`）。这使 B 的 T19（树内配置已是 v2）、
EN3（脚本对树内合法配置退出 0）、EN6（脚本读树内配置且不改字节）同时失败。审计里没有
`config/app.yaml` 的 policy block；因此本读数把它记成「B 的最终树未完成配置迁移」这一事实，
不把它归因于某条规则，也不把 B/C 的差写成治理的因果。

### 3.4 方向计数与机制的关系（只到这一层）

- async：A<B 3/3；B=C 3/3。A 的 3 个方向都对应同一处 tools 写面阻断（§2.5(b)），B/C 的树都完整。
- docs：A<B 3/3（A 缺 `tools/check_config.py`，B 有）；B<C 3/3（B 的 `config/app.yaml` 仍是 v1，C 是 v2）。
- cross：A=B=C 3/3（无 tools 写面）。
- 以上只说明「本批 3 个 block 的 T 原值方向与这些现场差异同向出现」；n=3、单模型、单宿主，
  不写效应、不写因果、不外推。

## 4 限制与不能说的（边界、缺口、未覆盖）

### 4.1 n=3 与结论上限

- 本批是 **3 题 × 3 臂 × 3 block、1 个模型身份、1 个宿主、headless、`danger-full-access`**；不写
  均值 / 中位数 / 百分比 / 区间 / 显著性 / p 值，不写「有效 / 显著 / 提升 / 优于 / 证明」，不写跨题总分，
  不外推到其它模型 / 宿主 / 题目（`readings/2026-10-22-bank-k3-deliberations.md:163-168`）。
- 可以写的方向只有 §2.3 的计数（3/3 同向、3/3 同值）；不能把「3/3 同向」升级成 treatment 结论。
- T 只读最终树（`run-record/README.md:287`）；会话内的阻断、重试与账面过程不折算进 T。T 满分也不等于
  契约全满足（`readings/2026-10-22-bank-k3-deliberations.md:100`）。

### 4.2 6 个 T-only 的 C/A unavailable

- async A-b1/b2/b3、docs A-b1/b2/b3 只有 `partial.json`，没有 `run-record.json`；C/A 都是
  `unavailable`（`file_set missing`），不是 0 分、不是 pass。
- 这 6 个 run **不计入「完整 run」统计**（21），只作 T 原值来源；§2.3 的 async/docs A 臂方向计数
  依赖它们，因此不能把这三个方向计数读成「完整 run-record 上的 C/A 对照」。
- 不重跑、不补造、不用 T 反推 C/A，也不替换任何 run 目录。

### 4.3 H2（STEP 1）的边界

- H2 对 6 个抽样路径（51 个臂/block 版本）的判定是 **6/6 未发现断言改弱 / 绕过验收**：没有新增
  skip/xfail、没有空测试、没有 `assert True`、没有 try 吞断言、没有减少测试函数或收窄收集面
  （`readings/2026-10-23-bank-k3-h2.md:272-289`）。**没有发现削弱，因此不写进「发现削弱」的限制项。**
- 但 H2 只覆盖 10 个 `(task, path)` 中的 6 个（60%），未抽中 async `tests/test_notification.py`、
  `tests/test_notify_smoke.py` 与 cross `tests/test_order_controller.py`、`tests/test_order_repository.py`；
  且**盲抽不成立**（执行者已知臂标签），没有运行验证、没有变异自证（H2 `:284-298`）。
  因此 H2 不能外推成「27 个 run 的全部测试都没被削弱」。
- H2 另记了两处「覆盖弱但不构成削弱」：cross `tests/test_order_service.py` 只断言返回值、
  cross `tests/test_order_api.py` 只断言两个方法的 docstring（H2 `:276-281`）。本步不改变它们的判定。

### 4.4 C/A 守卫（STEP 2）与 T 的关系

- 21 份完整 record 的 C/A 读数在 `readings/2026-10-23-bank-k3-guards.md`：C 只有 `DOC-001@1`
  warning（69 条 / 7 run / 10 文件），A 只有 A5/A6/A7/A9 失败（19 次 / 10 run）；这些都不改变 T 的
  `passed/total`（guards `:235-244`）。
- 本步不重复 C/A 表、不把 C/A 的 `exit 1` 读成 T 失败，也不把 `allow` 读成「43 条规则都查过」
  （guards `:250-270`）。

### 4.5 预存 errata（已知、不改字节）

- `bank/COMMAND-FAMILIES.md` 的 sha 与三题 `scoring.yaml` 的 `command_families_sha256` 不符；
  async/docs README 的 `task-package/interfaces.md` 哈希行是文档抄写错误
  （`readings/2026-10-22-bank-k3-run-ready.md:108-119`）。
- 两项均**已知、不影响本批 T 读数**；本步只声明，不修一个字节，也不把它们算成新的 run 缺陷。

### 4.6 现场与操作边界

- 27 个 run 目录、`.tmp/k3/acl-residue/`、`.tmp/k3/runs27/` 均保留；未 cleanup、未 push、未改远端。
- 未重跑任何 run 或测试；未改 hidden/scoring/freeze/exp-set/臂配置/src/policies/validation；
  未写 21 份 run-record；未重签审批（A/B 审批与 TTL 见 §2.6）。
- 本步只新增本文件；机器可读证据在 `.tmp/k3/treatment/summary.json`（不提交）。
