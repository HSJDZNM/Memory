# 2026-10-22 题库 k≥3 Gate 0 离线激活探针（A/B，四题）

> **2026-10-22 前向注记（errata）**：本读数记录的是**构造改造前**的 Gate 0（未过：async / crossmodule /
data-migration 无激活、docs-config 方向反转）。按使用者拍板的选择 1 完成构造改造后重跑，
Gate 0 **通过**——读数见 `readings/2026-10-22-bank-k3-gate0-rerun.md`。原文保留，不改写。

> **性质**：离线、无模型、无真机会话的激活探针（C1-b §3.3 方法的复现）。起点 HEAD `861aad9`；
> 只写 `.tmp` 一次性现场与本读数；**不改判据、不改任何冻结件、不跑 27 run**。
> **判据来源**：`readings/2026-10-22-bank-k3-deliberations.md` §3.1（Gate 0 预注册）、
> `05-implementation-plan.md` §8 第 11 条、`testing/ab/bank/README.md` §4.1/§4.5。
> **结论边界**：探针回答「在冻结题包与 T3 配置的里程碑序列上，treatment 有没有改变判定的机会」，
> 不回答真实模型会不会走这条序列，也不回答 treatment 的效应大小。

## 0 一句话

四题跑完：**async 无激活、crossmodule 无激活（负对照符合预期）、data-migration 无激活、
docs-config 方向反转**（唯一主序列差异 = M4b，B 更严）。被选 3 题里设计方向激活 **0/3**、
主序列差异 **1/3**。按预注册（≥2 个被选题出现激活机会；async 无激活即停；docs 无激活且
migration 有激活才允许替换）**Gate 0 未过：不跑 27 run、不换题**。合法结论是
「在这 4 个冻结题包与 T3 配置下，treatment 没有设计方向的激活机会」，**不是**「treatment 无效」。

## 1 方法与输入

- **T3 配置（A/B 唯一差异）**：A 读 `testing/ab/dgate2/configs/before`，B 读 `configs/after`；
  两份只差 `validation/test-layout.yaml` 的 `production_patterns`（A 只 `src/**/*.py`，
  B 加 `tools/**/*.py`）。摘要：A `69e9d4bb…`，B `af70bee1…`。两臂 `batch_ledger.into_decision=true`、
  `max_targets=20`、`ttl_hours=24`（T3 平台代际，两臂同值）。
- **离线复现**：`python -m policy.check`（不是真机 Hook）。每臂一棵树、每臂自己的 settled 集：
  某步的 decision 属于 `{allow, allow_with_warnings}` 才落地并计入该臂 settled；被 block 的写不落地、
  不进批、也不进入后续树的当前内容。每步 `--changed` = 本步目标 + 该臂已 settled 成员
  （T3 批成员；按 `batch_ledger` 的 settle 口径），所以两臂的树在 blocked 步之后可能分叉。
- **写序列与内容**：各题 `task-package/milestones.md` 的写步；内容取该题 `reference/tree`；
  里程碑写明但 reference 没有的中间态（data-migration 的 M5a/M7a 测试骨架、crossmodule 的薄转发）
  用最小可运行内容，探针脚本里逐段注明。非 `.py` 目标按示例适配器的语言声明用 `text`。
- **判据面**：`decision`、`violations`、`served_checkers`、`selection.level` / `nodeids`；
  差异分「decision 变化」与「仅非 decision 变化」两类；方向按
  `B_more_permissive`（B 比 A 宽 = 设计方向，A block / B allow）与
  `B_stricter`（B 比 A 严 = 反向）标注。
- **附注形态（只做机制解释，不作主判据）**：`solo`（changed = 本步目标、批为空，即 C1-b §3.3 的旧 M5b 形态）、
  `tests_only`（目标 + settled 测试）、`reverse_order`（把同名测试从树里去掉，模拟实现先写、测试后写）。
- **证据**：探针脚本 `.tmp/k3/gate0/probe.py`，原始结果 `.tmp/k3/gate0/results.json`，
  逐题 A/B 树与附注树在 `.tmp/k3/gate0/<task>/` 下。`.tmp` 是一次性现场（cleanup 会删），
  复现命令见 §6。

## 2 逐题读数

### 2.1 bank-async-concurrency（14 文件基线；10 个写步）

| 步 | 目标 | A | B | A level | B level | 差异 |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | `tests/test_notify_model.py` | allow_with_warnings（pending 1） | 同左 | target | target | 无 |
| M2 | `src/shop/notify_model.py` | allow | allow | related | related | 无 |
| M3 | `tests/test_notify_worker.py` | allow_with_warnings（pending 1；STYLE-018 warning） | 同左 | related | related | 无 |
| M4 | `src/shop/notify_worker.py` | allow | allow | related | related | 无 |
| M5a | `src/shop/notification.py` | allow | allow | related | related | 无 |
| M5b | `tests/test_notification.py` | allow | allow | related | related | 无 |
| M6a | `docs/async.md` | allow | allow | — | — | 无 |
| M6b | `README.md` | allow | allow | — | — | 无 |
| M7 | `tests/test_notify_smoke.py` | allow_with_warnings（pending 1） | 同左 | related | related | 无 |
| M8 | `tools/notify_smoke.py` | allow | allow | related | related | 无（settled 测试在 changed 里） |

**附注（机制解释）**：M8 的 `solo` 形态 A **block**（`TESTING-002`，selection `none`，`failing_tests` 未被服务）、
B **allow**（selection `related`）——**设计方向只在「批为空」时出现**；`tests_only` 两臂都 allow
（仅 selection_level 不同 target/related）；`reverse_order` A allow / B **block**（B 更严）。
**结论：无激活**——T3 的批次把模型自己写并结算的测试带进 changed，A 不再因为 `tools` 不是生产文件而
选不到测试；里程碑序列上没有设计方向的差异。

### 2.2 bank-docs-config（13 文件基线；M5 是命令步、不是写判定）

| 步 | 目标 | A | B | A level | B level | 差异 |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | `tests/test_config.py` | allow_with_warnings（pending 1） | 同左 | target | target | 无 |
| M2 | `src/shop/config.py` | allow | allow | related | related | 无 |
| M3 | `config/app.yaml` | allow | allow | — | — | 无 |
| M4a | `tests/test_check_config.py` | **block**（`TESTING-002`） | **block**（同） | related | related | 无（两臂都阻断：基线没有 `tools/` 包，模块级 import 收集失败） |
| M4b | `tools/check_config.py` | **allow** | **block**（`TESTING-001`） | related | suite | **有：decision + violations + level；B 更严（方向反转）** |
| M5 | （`python tools/check_config.py …`；命令步） | — | — | — | — | 不进写序列 |
| M6a | `docs/config-migration.md` | allow | allow | — | — | 无 |
| M6b | `docs/config.md` | allow | allow | — | — | 无 |
| M7 | `README.md` | allow | allow | — | — | 无 |

**附注**：M4b 的 `tests_only` A allow / B block（B 更严）；`solo` 两臂都 block（decision 同，
violations/level 不同）；`reverse_order` A allow / B block（B 更严）。
**结论：方向反转**——唯一主序列差异是 M4b：M4a 的测试写被 `TESTING-002` 阻断后测试不在树里，
A 因为 `tools` 不是生产文件、只选到 `tests/test_config.py` 而 allow；B 因为 `tools` 是生产文件、
找不到同名测试而 `TESTING-001` block。该步只在「被 block 后仍按里程碑推进」的路径上出现，
探针不模拟模型重试/改写的真实行为。

### 2.3 bank-crossmodule-refactor（14 文件基线；负对照）

13 个写步（M2–M8b）全部 A/B 同 decision（M6a 两臂 `allow_with_warnings`：pending 1 + STYLE-018 warning；
其余 allow），selection level 同（docs/README 步为 `—`）；**无 `tools/` 写面**，按构造不应有 treatment 差异。
**结论：无激活（负对照成立）**。

### 2.4 bank-data-migration（13 文件基线；14 个写步）

M1 `tests/test_ledger_migration.py` 两臂 `allow_with_warnings`（pending 1 + STYLE-018 warning）；
M2–M8 两臂全 allow（selection `related`）；**M5b `tools/migrate_ledger.py` 与 M7b `tools/verify_ledger.py`
两臂都 allow**（同名测试骨架已 settled、按 stem 对上，`TESTING-001` 不缺测试）；M10a/M10b 两臂 allow。
**结论：无激活**。

**附注（同一机制，仅解释）**：M5b/M7b 的 `solo` 形态 A **block**（`TESTING-002`，level `none`）、
B **allow**（level `related`）——设计方向只在批为空时出现；`reverse_order` A allow / B **block**（B 更严）。
M9 的两条命令不是写类动作，其产物 `data/ledger-v2.jsonl` 不由写工具落地，故不进判定序列。

## 3 Gate 0 判定

| 题 | 主序列结论 | 设计方向步 | 反向步 | 仅非 decision 差异 | 关键读数 |
| --- | --- | --- | --- | --- | --- |
| bank-async-concurrency | **无激活** | — | — | — | 10 步同 decision / served / level；M8 两臂 allow |
| bank-docs-config | **方向反转** | — | M4b | — | M4b：A allow / B block（`TESTING-001`），B 更严 |
| bank-crossmodule-refactor | **无激活** | — | — | — | 13 步同；负对照成立 |
| bank-data-migration | **无激活** | — | — | — | 14 步同；M5b/M7b 两臂 allow |

**按预注册规则逐条**（`readings/2026-10-22-bank-k3-deliberations.md` §3.1）：

1. **≥2 个被选题出现激活机会**：被选 3 题（async / docs-config / crossmodule）主序列差异 **1/3**
   （docs 的方向反转）、设计方向激活 **0/3**；即使把方向反转计作「机会」也只有 1 个 → **不满足**。
2. **async 无激活 → 停止，不换题**：命中硬停规则。
3. **crossmodule 必须无激活（负对照）**：成立。
4. **替换条件**：docs 不是「无激活」（是方向反转）、data-migration 无激活 → **不允许**用 migration 替换。

**判定：`gate0_pass=false`。不跑 27 run；不替换；回到构造/重冻结（需使用者另裁）。**

## 4 这意味着什么 / 不意味着什么

**是**：

- 在 T3（批次进判定）下，模型自己写并结算的测试会进入后续写的 changed 集，`selection` 走 target/related，
  A 不再因为 `tools` 不是生产文件而「选不到测试」——C1-b 时代的 A block / B allow **在里程碑序列上不再出现**。
- 设计方向的机制仍然在：`solo`（批为空）下 async M8、migration M5b/M7b 都是 A block / B allow。
  它不是 T3 的配置，不能当主读数。
- 主序列唯一差异是 docs M4b 的 **B 更严**（方向反转），且出现在「测试写被 block、随后仍写实现」的路径上。
- 若模型偏离里程碑、先写实现后写测试（`reverse_order`），async / docs / migration 都是 A allow / B block
  （B 更严）——这是附注，不是预注册主判据；要用它必须显式改预注册，不能事后换判据。

**不是**：

- **不是**「treatment 无效」或「治理无效」：本探针只测一条机制（`production_patterns`）在里程碑序列上的
  可观测差异，没有模型行为、没有 run、没有 T/C/A。
- **不是**「题不可解」或「hidden/评分器有问题」：天花板读数与题包不受本探针影响。
- **不是**「换构造后也不会有激活」：见 §5 的最小构造候选。
- **不能**把 `solo` 的 A block / B allow 写成 T3 读数；**不能**把「无激活」写成 pass。

## 5 处置与下一步

- 按 §4 的失败关闭：**报告「treatment 无机会」，不跑 27 run**；不把「跑不成/无激活」记成 pass，
  也不书面放宽 bank §4.8 的记录缺口（最小 bank run-record 仍未实现，27 run 未跑）。
- 若使用者要重启 k≥3，最小构造候选（都动构造，需另裁并按冻结顺序重做）：
  1. **C1-b §7.3 形态**：基线自带同名工具测试（模型不写它）、模型只写 `tools/` 实现——A 因 `tools` 非生产
     选不到测试而 block，B 能选到基线测试而 allow；这是唯一被 C1-b 证明过、且在 T3 下仍成立的设计方向形态。
  2. **改 T3 的批策略**（例如只把「测试文件本身」的结算排除出 changed）：会改平台代际与既有读数，超出本轮。
  3. **接受方向反转假设**：只有 docs 在 T3 主序列上反向；async 命中硬停，不满足预注册。
- 无论选哪条，都要按 05 §8 记录：改了什么、为什么、旧读数作废、重测天花板与重冻结。

## 6 复现

仓库根、`PYTHONPATH=src`：

```powershell
# 四题全跑（每跑完一题重写 results.json）
.venv/Scripts/python.exe .tmp/k3/gate0/probe.py

# 只跑一题（可重复 --only）
.venv/Scripts/python.exe .tmp/k3/gate0/probe.py --only bank-async-concurrency
```

- 输出：`.tmp/k3/gate0/results.json`（含 `head` / `config` / 逐题 steps / conclusion / gate0）+
  逐题 `A/tree`、`B/tree`、附注树；脚本只写 `.tmp/k3/gate0` 父目录，不改仓库文件。
- 依赖：`.venv` 解释器、仓库 `policies/` / `validation/`、`dgate2/configs/{before,after}` 快照、
  各题 `task-package/milestones.md` 与 `reference/tree`。这些输入被冻结集引用时以冻结清单为准。
- 边界：不是真机 Hook；不模拟模型在 block 后的重试/改写；中间态是里程碑写明的最小内容；
  `solo` / `tests_only` / `reverse_order` 是附注形态，只有主序列进入判定。

## 7 证据指针

- 判据：`readings/2026-10-22-bank-k3-deliberations.md` §3.1；`05-implementation-plan.md` §8 第 11 条；
  `testing/ab/bank/README.md` §4.1/§4.5；`readings/2026-10-21-c1b-treatment-adjudication.md` §3.3/§7.3。
- 输入：`testing/ab/dgate2/configs/before/validation/test-layout.yaml`（`69e9d4bb…`）与
  `configs/after/validation/test-layout.yaml`（`af70bee1…`）；四题 `task-package/milestones.md`、`reference/tree`。
- 现场：`.tmp/k3/gate0/{probe.py,results.json}` 与逐题 `A/`、`B/`、附注树（一次性；cleanup 会删）。
