# 2026-10-21 C1-b 是否属于 treatment：裁决读数

> 性质：**裁决读数**（共享任务 task-7）。只读分析 + 一次离线复现；不改代码、不改 `examples/**`、不 commit、不 push、不跑真机。
> 起点：HEAD `0f580f8`（工作树干净；C1-b 已由 `951c9c1` 落地）。目标读者是 Lead；最终以 Lead/使用者确认后的 05 §8 记录为准。
> 依据：05 §4 C1 / §5，04 5.46 / 5.88，`readings/2026-10-21-C1-b-batch-into-decision.md`，`readings/2026-10-21-C1C2C4-adjudication-draft.md` §1，`testing/ab/dgate2/scorer/scorer.yaml`，`examples/dsh/b-plan/a3-task-v3/README.md`。
> 证据纪律：每条结论带文件:行或读数节号；不写汇总性结论；不写绝对路径/凭据。
> 路径口径：`src/**` / `examples/**` / `validation/**` 相对仓库根；`readings/**` / `testing/**` / `04-open-work.md` / `05-implementation-plan.md` 相对 `docs/project/engineering-policy-platform/`。

## 0 裁决

**T3：`batch_ledger.into_decision` 不属于 treatment，属于平台代际基线；A/B 两臂统一 `into_decision=true`、`max_targets=20`（C 臂无适配器，N/A），A/B 仍只差 `validation/test-layout.yaml` 的 `production_patterns`（A 仅 `src/**/*.py`，B 加 `tools/**/*.py`）。**

理由与代价，各一句：

1. **归因**：T1 会让 B−A 同时差 treatment 与批次语义；T3 把 C1-b 放进两臂同一代际，A/B 才仍是单变量对比。
2. **代际**：C1-b 的账本 1.1 / 审计 1.5 是平台能力升级（`src/adapters/dsh/batch_ledger.py:70`；`src/adapters/dsh/hooks.py:179`），不是某臂的策略差异；把它当 treatment 会把“平台升级”与“策略改动”混成一项。
3. **代价**：旧 n=1 读数与旧 M5b activation 不能再引用（第 5 节）；T3 下旧 M5b 的 A block 在离线复现里变成 allow（B 原本 allow；第 3.3 节），新题库必须先重证一个不被批次掩盖的 activation（第 7 节）。

## 1 三臂配置表

共同前提：三臂同一平台代码（HEAD `0f580f8` 或新冻结 HEAD）、同一宿主版本（task-6 冻结）、同一规则集与同一题库；A/B 的适配器配置只在 `pre_evidence.registry_root` 指向的 `validation/` 快照上不同——这是 treatment 的**交付路径**，不是第二项 treatment。

| 配置项 | A 臂（现状治理） | B 臂（treatment） | C 臂（不治理） |
| --- | --- | --- | --- |
| 平台代码 / 宿主 | 同一冻结 HEAD / 同一冻结 dsh 版本 | 同左 | 同左（不挂 Hook，宿主同版本） |
| `batch_ledger.enabled` | `true` | `true` | N/A（无适配器） |
| **`into_decision`** | **`true`** | **`true`** | **N/A（无批次判定路径）** |
| `max_targets` | `20` | `20` | N/A |
| `ttl_hours` | `24` | `24` | N/A |
| `pre_evidence.enabled` | `true` | `true` | N/A |
| `pre_evidence.registry_root` | `configs/before`（仓库相对标签） | `configs/after`（仓库相对标签） | N/A |
| `production_patterns` | `src/**/*.py` | `src/**/*.py` + `tools/**/*.py` | N/A |
| `test-layout.yaml` sha256 | `69e9d4bb…` | `af70bee1…` | N/A |
| `AUDIT_SCHEMA_VERSION`（观测） | `1.5` | `1.5` | N/A |
| `BATCH_LEDGER_SCHEMA_VERSION`（观测） | `1.1` | `1.1` | N/A |
| PIPELINE / EVIDENCE / 决策 | `1.4` / `1.2` / `1.1` | 同左 | N/A |
| adapter 配置 digest | run 时算 `sha256(.policy/dsh-adapter.yaml)` | 同左（值不同） | N/A |
| 预算不等式 | b-plan 冻结值 `20000 + 5000 < 30000`；按实际 `hooks.json` 复核 | 同左 | N/A |
| 审计 / 账本 | `.policy` 下 audit + 批次账本 | 同左 | 无审计、无账本 |
| treatment | 无 | `production_patterns` 增 `tools/**/*.py` | 显式“不治理” |

读表要点：

- **A/B 仍只差 treatment**：两臂 `into_decision`、`max_targets`、账本/审计版本、取证开关全部相同；适配器配置的唯一语义差异是 `registry_root` 指向 before/after（`testing/ab/dgate2/configs/README.md` §用途、§逐文件 sha256）。digest 会因这个路径值不同而不同——这是**预期差异**，不是第二次 treatment。
- **C 臂不受 C1-b 影响**：C 在 project_root 外、`launch.patch=null`、无 Hook/审计（`readings/2026-10-20-D-gate2-ab-c-runs.md` §1、§3；`testing/ab/dgate2/runs/2026-10-20/C/arm-facts.json`），`into_decision` 没有消费方。C 的配置表写 N/A 不是“没记录”，而是“这条路径不存在”。
- **D 校准臂**：无模型、固定 P+/P−/canary；单动作、批次为空，`into_decision` 不改变其结论，但仍必须用**同一冻结平台**重跑一次（第 6 节），否则 D 的读数也是旧代际。
- 表里的 digest 是“必须 run 时算”的字段，不是可手填的常数；旧 run 没有记录它（第 3.4 节）。

## 2 三种方案：能回答什么、不能回答什么

| 方案 | A `into_decision` | B `into_decision` | 能回答 | 不能回答 | 判断 |
| --- | --- | --- | --- | --- | --- |
| T1 | `false` | `true` | “treatment + C1-b 打包后，B 与 A 的产出是否不同” | 哪一部分是 treatment、哪一部分是批次；批次是否被模型行为触发（内生）；不能做单变量归因 | 不采纳 |
| T2 | `false` | `false` | “在 C1-b 关闭的平台上，treatment 是否改变产出”；旧 M5b activation 可保留 | 当前平台（C1-b 可用）下 treatment 是否仍有作用；TDD/批次题不激活；题面要求观察的 `pre_evidence.batch` / `batch.settlement` 不出现 | 作为旧代际对照可保留，不作为本轮主方案 |
| **T3** | **`true`** | **`true`** | **“在当前平台代际（C1-b 作为基线）下，treatment 是否改变产出”**；A/B 仍单变量；TDD/批次题可在两臂同样激活 | treatment 的**直接**效应与“批次被 treatment 间接触发”的效应不能拆开；C1-b 自身的因果效应；旧代际的结论 | **采纳** |

补充三条：

- **T3 不是“把 C1-b 当 treatment”**：treatment 是 2026-10-19 冻结的那一项数据改动（`production_patterns` 增 `tools/**/*.py`；`readings/2026-10-19-D-gate2-treatment.md` §2.5、§8 第 1 条；`examples/dsh/b-plan/a3-task-v3/README.md` 开头）。C1-b 是平台能力，`into_decision` 是它的开关；把开关在两臂设成同一值，才叫“基线”。
- **T2 的合理用途**：如果本轮只想复现旧代际的 treatment 结论（旧 M5b activation 仍成立），T2 是干净的；但新题库里的 TDD/修 bug 题会按单文件语义判，题面要求观察的批次键不存在，而且“当前平台”没有被测到。T2 不能与 T3 的新 run 合并。
- **T1 的合理用途**：只适合做“打包是否有效”的筛查；一旦要写“treatment 有效/无效”，B−A 的两件事无法拆开，违反 05 §5.5 的句式纪律。

## 3 证据

### 3.1 三臂配置与 treatment 的交付

- A/B 的输入快照：`testing/ab/dgate2/configs/README.md` §用途——“A 臂用 `before/`，B 臂用 `after/`，评分器用 `after/`”；两份只差 `test-layout.yaml` 一个文件（新增 6 行、删除 0 行；§自证）。
- 取值：before `69e9d4bbef6daf403ec090c59fbfda763cea5cf5894fa746b9f97ca03a63b3d3`（`production_patterns` 只有 `src/**/*.py`）；after `af70bee1bb8a886190cda33141d0ccf6d00acd0dde92383dddb0a30f37b9bf2a`（加 `tools/**/*.py`）。见 `configs/before/validation/test-layout.yaml:18-19`、`configs/after/validation/test-layout.yaml:18-25`。
- A/B 适配器配置的差异只在 `pre_evidence.registry_root` 指向上述两份快照；适配器其余字段（`test_paths` / `layers` / `languages` / `timeout_ms`）相同（`examples/dsh/dsh-adapter.yaml:33-73`；`configs/README.md` §用途）。
- C 臂：`launch.patch=null`、无 Hook、无 `.policy` 审计（`runs/2026-10-20/C/arm-facts.json`；`readings/2026-10-20-D-gate2-ab-c-runs.md` §1/§3）。

### 3.2 C1-b 打开时到底改了什么

- `BatchLedgerConfig`：`enabled` / `root` / `ttl_hours` / `into_decision`（默认 `False`）/ `max_targets`（默认 `20`，0 = 不并成员）——`src/adapters/dsh/adapter.py:572-596`；加载期解析与布尔校验在 `adapter.py:886-947`。
- 判定范围：`changed_files = {event.file} | batch_targets`，落到 `PipelineRequest.changed_files`——`src/adapters/dsh/pre_evidence.py:684-708`；批次视图只在 `into_decision=true` 且 `pre_evidence.enabled` 时构建（`src/adapters/dsh/hooks.py:1342-1401`）。`false` 时返回空成员 + `None`，审计不新增 `pre_evidence.batch` / `batch.settlement`；C1-a 的 `batch_ref` + `batch` 四态块保持不变（唯一差别是 `batch.schema_version` 值随账本轴走 1.1，C1-b 读数 §0 第 2 条；`hooks.py:1354-1363`）。
- 审计键：`batch.settlement` 只在声明 + `enabled` + `into_decision=true` 的最终判定行出现（`hooks.py:1071-1135`；`hooks.py:1089-1090`）；`pre_evidence.batch` 是 10 键块：`status / applied / members_digest / included / excluded / settled / truncated / skipped_lines / invalid_lines / note`（`hooks.py:1390-1400`；`pre_evidence.py:806-809`；`src/adapters/dsh/README.md:1125-1135`）。
- 结算口径：settle 只看最终 `exit_code`（0 = allowed），`content_sha256` 取取证提议的哈希；被 block / 未结算 / 未落地 / abandoned / legacy 只进 `excluded`（`hooks.py:1078-1085`；`README.md:1114-1123`）。
- 版本轴：`BATCH_LEDGER_SCHEMA_VERSION = "1.1"`（`src/adapters/dsh/batch_ledger.py:70-71`）；`AUDIT_SCHEMA_VERSION = "1.5"`（`src/adapters/dsh/hooks.py:179`）；PIPELINE 1.4 / EVIDENCE 1.2 / 决策 1.1 不动（`readings/2026-10-21-C1-b-batch-into-decision.md` §0 第 3 条、§2）。
- 实现读数：C1-b 读数 §3 的门 1–5（关/开判定逐字节相等、三步门与合并判定、19 条负例、审计键冻结、预算）与 §4 真机三次 edit。这些是**实现读数**，不是本轮冻结实验的读数；必须用冻结后的每臂适配器配置重跑（第 6 节）。

### 3.3 旧 M5b activation 在 T3 下不再成立（离线复现）

旧 activation 的原文：A 臂 `M5b = block / TESTING-002@1 critical / uncovered_checker`，B 臂 `allow`（`examples/dsh/b-plan/a3-task-v3/README.md:58-67`；`readings/2026-10-19-D-gate2-treatment.md` §2.3.5；`readings/2026-10-20-D-gate2-ab-c-runs.md` §3）。它的前提是：M5b 的目标 `tools/audit_demo.py` 在 A 臂不是生产文件，且 M5a 写下的 `tests/test_audit_demo.py` **不在**这一步的 changed 集里，于是 A 的测试选择是 `level="none"`，`failing_tests` 没被服务，按失败关闭报 `uncovered_checker`。

C1-b `into_decision=true` 恰好把这个前提改掉：M5a 的测试写已结算 allowed、内容哈希与磁盘一致，M5b 的 `changed_files` 会包含它（`hooks.py:1366-1401`；`pre_evidence.py:698-705`）。测试选择逻辑对“变更集里的测试文件”直接给 `level="target"`（`src/validators/selection.py:183-226`），于是测试真的跑起来。C1-b 读数门 2 的结论也是“on 与 merged/CLI 差集为空”（C1-b 读数 §3 门 2）。

本轮用旧 A 树做了**离线复现**（`policy.check`，不是真机 Hook；同一棵 A 树 + B 的 `tools/audit_demo.py` 作为提议内容）：

| 形态 | `--changed` | decision | violations | `served_checkers` | `selection.level` |
| --- | --- | --- | --- | --- | --- |
| 旧 M5b（单文件） | 只 `tools/audit_demo.py` | block | `TESTING-002@1` critical / `uncovered_checker` | 不含 `failing_tests` | `none` |
| T3 下 M5b（批次把测试带进 changed） | `tools/audit_demo.py` + `tests/test_audit_demo.py` | allow | 空 | 含 `failing_tests` | `target` |

边界：这是离线 `policy.check` 读数，输入与 C1-b 传给流水线的 `changed_files` 相同，但不是 Hook 的真实取证树/真实批次；它证明“旧 block 是单文件判定口径的产物”，不能替代第 6 节的冻结配置真机重读。**结论**：T3 下旧 M5b 的 A block / B allow 不再是可靠的 activation；新题库必须重新找 activation（第 7 节给了一个可行形态）。

### 3.4 冻结记录缺口：17 字段不够

- 17 字段清单：`testing/ab/dgate2/run-manifest/run_manifest.py:66-87`（`RUN_MANIFEST_SCHEMA_VERSION = "1.0"`）与 `testing/ab/dgate2/scorer/scorer.yaml:602-623` 逐字一致；`arms` 只抽取 `tree_digest / session_id / launch.patch / launcher_sandbox`，未知键**不拒绝、不复制**，另记原始 JSON 的 `source_sha256`（`run-manifest/README.md` §5 第 5 条；`run_manifest.py:1099-1114`）。
- 已经存在的适配器配置摘要：审计记录的 `reading_context.declarations.adapter_config` 是这一个配置文件的 sha256（`src/adapters/dsh/hooks.py:1242-1246`；`src/provenance/reading_context.py:161、294-302`）。但它在**审计**里，不在 run-manifest 里；旧现场审计落在 `.tmp`，cleanup 会删。
- `configs_after_sha256_txt` 记的是**评分器/参照配置** `configs/after`（旧 run-manifest 三臂同为 `3fea3de0…`），不是 A 臂实际使用的 `configs/before`（其 `sha256.txt` 是 `780dd26c…`）；scorer 也明确写“configs/before 是 A 臂输入快照，不在本清单里”（`testing/ab/dgate2/scorer/scorer.yaml:582`）。因此旧 run-manifest 无法单独证明 A/B 的 treatment 对照，更无法证明 `into_decision` 取值。
- 旧 run-manifest 的 `head` 也不足以充当代际证据：旧案例读数写 run 起点 HEAD `889c97c`（`readings/2026-10-20-D-gate2-ab-c-runs.md` §1），三份 run-manifest 的 `head` 却都写 `34b153c`（清单落盘提交，时间在 run 之后）；旧 A 的 `.policy/dsh-adapter.yaml` 没有进入 `runs/` 的受跟踪记录；旧 B 的现场配置不含 `batch_ledger` 段（旧代际）。旧记录不但缺 C1-b 字段，连“当时平台是哪一代”都证明不了。

### 3.5 判据原文位置

- 05 §4 C1（`05-implementation-plan.md:168`）；§5.1 四臂（`:183-192`）；§5.4 作废条件（`:209-211`）；§5.5 强度纪律（`:213-218`）。
- 04 5.46（`04-open-work.md:272`）、5.88（`:315`）。
- C1/C2/C4 草案 §1 把 C1 分成 C1-a（只报告）与 C1-b（进判定），并写明“C1-b 另行裁定”（`readings/2026-10-21-C1C2C4-adjudication-draft.md` §1）；本读数就是这次裁定。
- scorer 的作废条件（`testing/ab/dgate2/scorer/scorer.yaml:479-516`）与 17 字段（`:602-623`）；run-manifest 的版本轴（`testing/ab/dgate2/run-manifest/run_manifest.py:28-30、66-87`）。

## 4 冻结与记录

### 4.1 每臂必须记录的字段

| 字段 | 来源 / 怎么算 | 为什么必须记 |
| --- | --- | --- |
| `adapter_config.path` + `adapter_config.sha256` | 受治理项目的 `.policy/dsh-adapter.yaml`，单文件 sha256；与审计 `reading_context.declarations.adapter_config.digest` 比对 | 覆盖 `into_decision` / `max_targets` / `registry_root` / `pre_evidence` 等全部配置；旧记录完全没有 |
| `into_decision` / `max_targets` | 从配置显式读，**不要从 digest 反推** | 题面要求；人读 manifest 时能直接看到 |
| `batch_ledger_schema_version` | `BATCH_LEDGER_SCHEMA_VERSION`，并与账本行里观测到的 `schema_version` 比对 | 账本轴 1.1 是 C1-b 的协议证据；旧 run 是 1.0 |
| `audit_schema_version` | `AUDIT_SCHEMA_VERSION`，并与审计记录里观测到的 `audit_schema_version` 比对 | 审计轴 1.5 是 C1-b 的协议证据；旧 run 是 1.4 |
| `test_layout_sha256` | 本臂实际 `validation/test-layout.yaml` 的 sha256（A `69e9d4bb…` / B `af70bee1…`） | **A/B treatment 的唯一实质差异**；旧 manifest 只记了 after，A 的 before 没记 |
| `pre_evidence.enabled` / `timeout_ms`；`timeout_ms`；`hooks_timeout_ms` | 配置 + `hooks.json`；核对 `pre_evidence.timeout_ms + timeout_ms < hooks timeout` | 批次读取在取证外层预算内；预算不等式是 C1-b 门 5 的输入 |
| `host.dsh_version` | `adapters.cli host-version` / 冻结记录 | C1-b 真机用 0.2.1-rc.2，旧 A/B/C 用 0.2.1-alpha.2；宿主代际必须同一 |
| 观测的批次读数（计数） | 每条判定记录的 `pre_evidence.batch`：`status` / `applied` / `included` / `excluded` / `settled` / `truncated` / `members_digest`；`batch.settlement.status`；`unreadable` 计数 | 审计在 `.tmp` 会被 cleanup 删；冻结记录里没有它，就无法证明“这次真的按批次算了” |

### 4.2 17 字段够不够？

**不够。** 17 个字段里与平台代际相关的只有 `head`、`arms`（四类事实 + 原始 JSON 的 `source_sha256`）和 `configs_after_sha256_txt`（评分参照，不是臂配置）；`into_decision`、账本/审计版本、adapter 配置 digest、A 臂的 `before` 快照都不在载荷里。把值塞进 `arm-facts.json` 也不能解决“可读性”：`arms` 明确不复制未知键，只记原始文件哈希；读 manifest 的人看不到内容，且 `.tmp` 的原始文件不是冻结记录。

**建议（不实现）**：新增一个顶层字段，例如 `platform_generation`（每臂一个对象），装本臂的 `adapter_config.sha256` / `into_decision` / `max_targets` / `batch_ledger_schema_version` / `audit_schema_version` / `test_layout_sha256` / `dsh_version` / 预算三值；`RUN_MANIFEST_SCHEMA_VERSION` 由 `1.0` 升到 `1.1`（AGENTS 第 55 条：加键就是改协议）。**同批代价**：17 字段清单本身冻结在 `scorer.yaml` 的 `run_manifest_fields`（version 2），加字段必须把 scorer 升到 version 3、重新生成 `scorer/manifest.sha256` 并重冻；旧 run-manifest 内嵌的旧组合摘要因此全部失效。这是新 run 前的一次性成本，不能等跑完再补。

替代方案（不推荐）：只往 `arm-facts.json` 里加键，靠 `arms.source_sha256` 指回原文件。它能“事后可查”，但 manifest 不是自足的，消费方必须信任一个未进 17 字段契约的旁文件；与本仓库“冻结清单自足、逐字段可重算”的纪律相反。

## 5 作废清单

### 5.1 旧 run / 旧读数

| 对象 | 新配置下为什么不成立 | 处置 |
| --- | --- | --- |
| `testing/ab/dgate2/runs/2026-10-20/{A,B,C}/run-manifest.json` + `readings/2026-10-20-D-gate2-ab-c-runs.md` | 旧代际：HEAD `34b153c`（清单）/ run 起点 `889c97c`、dsh `0.2.1-alpha.2`、AUDIT 1.4 / 账本 1.0；没有 `batch.settlement` / `pre_evidence.batch`；旧 manifest 不记 adapter config digest / `into_decision`。T3 下 A 的 M5b 在离线复现里会变成 allow（B 原本 allow；第 3.3 节） | 作废为**新冻结的对照**；A/B 必须重跑；C 不受 C1-b 影响，但若题库/宿主变，三臂同题要求下也要重跑 |
| `readings/2026-10-19-D-gate2-treatment.md` §2.3.5 / `a3-task-v3/README.md` §3 的 M5a/M5b 表 | 旧 activation 是单文件判定口径的产物；T3 下 M5b 的 A 臂会被批次带进测试文件而 allow（离线复现；第 3.3 节）。它不再是“同一动作两臂不同 decision”的证明 | 机制读数保留（test-layout 改变测试选择是真的）；**end-to-end activation 作废**，必须在冻结配置 + 新题库上重读 |
| `readings/2026-10-21-C1-b-batch-into-decision.md` §3 门 1–5 / §4 真机三次 edit | 是**实现读数**（HEAD `4758679` 的 src 快照 + `.tmp` 现场配置），不是本轮冻结实验的读数；门 2 的场景与 M5b 不同，不能直接当 activation | 作为代码证据保留；用冻结后的每臂适配器配置重跑门 2/4/5 与真机两步/三步 |
| `runs/2026-10-20/A/run-record.json` | 已是 partial（C 只量了 7/8 文件；`testing/ab/dgate2/runs/2026-10-20/README.md`「边界」、案例读数 §6）；旧树/旧任务包 | 不参与任何新比较；新 run 重新采集 |
| 旧“治理强度”计数（block 数、`circuit_open`、`served_checkers`） | 旧代际的 block 数包含 M5b 的 stepwise 误伤；C1-b 会改变同一动作的判定范围与 served 集 | 只作旧案例叙述，不进新 run 的治理强度读数；新 run 按 `served_checkers` / `selection.level` / `check_volume` 重记 |
| D 校准门（P+ / P− / canary）的旧读数（`readings/2026-10-18-A3-dryrun-v2.md` §5） | 旧平台、旧宿主；虽然单动作批次为空，仍不是新冻结配置的读数 | 用冻结平台重跑一次（无模型，成本低） |

### 5.2 仍然有效的

- **机制事实**：`production_patterns` 增 `tools/**/*.py` 会改变测试选择（before/after 两份快照的差异、`selection.py` 的 production 判定）；这是 treatment 的机制，不因 C1-b 失效。
- **评分器工具本身**：`policy.check` / `structure_metrics` / hidden runner 在各自冻结树上的参考读数仍可作为仪器校准；但它们不是新 run 的 T/C/A 分数，且若 scorer 因新字段重冻，旧 manifest 的摘要全部失效。
- **C1-b 的代码级门**：门 1（false/true 判定逐字节相等）、19 条负例、预算读数仍是代码证据；只是不能当实验读数。

## 6 必须重跑的门

| 门 | 为什么 | 读数 / 通过条件 |
| --- | --- | --- |
| 冻结门：`make_manifest.py --check --strict` + run-manifest `--check --strict` | 若按 §4.2 新增字段，scorer/manifest 与 run-manifest 都要重冻；旧摘要不能沿用 | 退出 0；三臂 manifest 无 pending；新增字段 recorded |
| D 校准门（P+ 被拦、P− 放行、canary 仍 block；固定用 A/before 配置） | 旧读数在旧平台；冻结配置换代际后必须重证仪器 | 无模型、固定动作；P+ block、P− allow、canary block |
| C1-b 门 2：三步（实现→测试→conftest）逐步 decision 与合并判定逐个相等 | 旧门 2 是离线场景；A/B 冻结配置 + 真实批次下要重证 | 差集为空；`selection.level` 的 support→related 现场可见 |
| C1-b 门 4：审计键冻结 | 确认 `pre_evidence.batch` 10 键、`batch.settlement`、`unreadable` 分支在 A/B 两臂都按 1.5 出现 | 键集合与冻结清单一致；未声明/关闭时零新增 |
| C1-b 门 5：预算不等式 | 批次读取在 `pre_evidence.timeout_ms + timeout_ms` 外层预算内 | `20000 + 5000 < 30000`（或新配置的实际不等式）；batch_view 耗时在读数里 |
| 真机批次两步/三步 | 离线门 2 不是 Hook；必须在冻结配置下取得 `pre_evidence.batch.included` / `batch.settlement` | 至少 A/B 各一次；每一步的 `status` / `applied` / `included` / `settlement` 可读 |
| **T3 下的 treatment activation** | 旧 M5b 在 T3 下会消失（第 3.3 节）；没有新 activation，D 构造门不成立 | 同一固定动作在 A/B 得到不同 decision；优先用第 7 节的“基线测试 + 只写 tools 实现”形态 |
| T/C/A 三维 + 两次逐字节相同 | 新树/新题库的最终树读数；评分器要求固定 `--request-id` | runner 40/40、structure_metrics 10/10、`policy.check` 8 规则；两次 JSON 相同 |
| 人工项 H1–H4 | 冻结契约要求；H1 作者独立性、H2 抽样、H3 A4、H4 非确定性 | 四项 recorded；`--strict` PASS |
| 起点 / 宿主 / 审批 / 配置哈希 | 05 §5.4 作废条件；旧 run 的 head 记录已暴露“清单生成时点”问题 | 新 run 在干净 HEAD 生成 start manifest；adapter/hooks/registry/approval 哈希与记录一致；无 `unreadable` 计为 0 |
| C 臂重跑（条件） | C 不受 C1-b 影响；但新题库/新宿主/新首消息要求三臂同题 | 同一冻结首消息、同一基线、`launch.patch=null`、0 条治理记录 |

## 7 与题库的交互

> 新题库（task-8）尚未冻结；本节是**预注册的预期行为**，不是读数。题库落盘后必须按冻结题型重读，尤其是 activation 场景。

### 7.1 “先写失败测试”题

| 步骤 | `pre_evidence.batch`（T3） | `batch.settlement`（该步最终行） | 要观察的键 | 预期 |
| --- | --- | --- | --- | --- |
| 写测试文件（第一次写） | `status=empty`、`applied=false`、`included=[]` | `{status: allowed}`（Hook 的 exit 0；见下方口径） | `batch.settlement`、`selection.level=target`、`served_checkers` | 若测试因“待实现”而收集失败：`allow_with_warnings` + `pending_findings`；若测试真的失败：`TESTING-002` block（批次此时帮不上忙） |
| 写实现文件 | `status=applied`、`applied=true`、`included=[测试文件]`、`members_digest`、`excluded` | `{status: allowed}` 或 `blocked` | `included`、`members_digest`、`selection.level`（target/related）、`served_checkers` 含 `failing_tests` | 测试通过 → allow；测试失败 → `TESTING-002` block。**这正是批次语义的可见后果** |
| 写 conftest / 支撑文件 | `status=applied`（若前一步生产成员已结算） | 同上 | `included`、`selection.level` 从 support 变 related/package | 与合并判定一致；覆盖可能收窄（README §12.11 的 M1） |

关键判断：

- **两个 exit_code 口径必须分开**：Hook 的 `allow_with_warnings` 是 `EXIT_ALLOW=0`（`hooks.py:2152-2159`），所以 `_settle_batch` 会把它结算成 allowed；`policy.check` CLI 的同一 decision 退出码是 1（`src/policy/check.py:15`、`:499`）。不要拿 CLI 的 1 去推 Hook 的结算——这直接决定测试步能否进下一步的批次。
- **“写失败测试”本身可能被 `failing_tests` 拦住**：目标就是测试文件时，`selection.level=target` 会真的跑它；如果它因为真实 bug 失败，`TESTING-002` 会 block，提案结算为 blocked，下一步的批次把它放进 `excluded.blocked`，实现步退回单文件。题库要避免这种“先写红测试反而被自己的规则拦死”的构造，或预注册它是预期摩擦（像 v3 的 M1 预期红 pytest 那样，但那是**命令**，不是写测试文件）。
- 要让批次真正帮到实现步，测试步必须是 **allowed**（包括 `allow_with_warnings` 的待实现），且内容哈希与磁盘一致；blocked/unsettled/abandoned 都不进批次（`README.md:1114-1123`）。

### 7.2 “修 bug”题

- 若“先写失败测试”的测试是**基线里已有**的回归测试：模型只改源码；A/B 两臂的 `production_patterns` 对 `src/` 相同，批次不改变 treatment 对比；测试是否被选中取决于源文件与测试的 related/package 关系。这类题主要练 C1-b 的审计键，不是 treatment 的 activation。
- 若模型先写回归测试、再改源码：测试步若 real failure 被 block，后续批次无成员；若测试步被允许（待实现/通过），实现步批次包含它，回归测试被跑。预期行为同上表。
- 对实验设计最重要的一条：**T3 下 A/B 的 treatment 差异只可能出现在 `tools/` 目标上**；`src/` 目标的 bug 修复对两臂是同一套 production_patterns，不产生 treatment 差异。

### 7.3 旧 activation 的替代形态（给题库的建议）

旧 M5b 之所以翻面，是因为 A 的 `tools/audit_demo.py` 不是生产文件、且测试不在 changed 集里。T3 下若要保住 activation，至少有一道 `tools/` 题应满足：

- `tests/test_<tool>.py` **在基线里**（不是模型先写的），模型只写 `tools/<tool>.py`；
- 该测试在基线里 import 该工具，B 臂（`tools/**` 生产）能选到它并跑；A 臂（非生产、changed 集无测试）仍是 `level=none`，因此 `TESTING-002` 失败关闭。

这时批次里没有该测试（它不是模型本轮的 proposal），所以 **T3 不会把它吃掉**；同一动作 A block / B allow 仍可成立。反之，若所有 `tools/` 题都要求“先写测试”，批次会把测试带进 changed，A 臂也变成 `level=target`，旧 activation 消失——这是第 0 节说“必须重证 activation”的具体含义。

### 7.4 T3 下这些题要看的审计键

- 批次块：`pre_evidence.batch.status`（`empty` / `applied` / `partial` / `unreadable`）、`applied`、`included`、`excluded`（`blocked` / `unsettled` / `not_landed` / `abandoned` / `legacy`）、`settled`、`truncated`、`members_digest`；最终判定行的 `batch.settlement.status`。
- 选择与证据：`selection.level`（support → related/package 的现场）、`served_checkers` 是否含 `failing_tests`、`check_volume.complete` / `blocking_capable_skipped`。
- 不要只看 decision：TDD 题里“block 变 allow”可能是批次修好了 stepwise 误伤，也可能是 `unreadable` 降级导致的覆盖收窄；两者必须用 `status` / `included` / `served_checkers` 分开。

## 8 审批与失败关闭

### 8.1 审批链不变

- 批次不是授权：只有 `settle=allowed` 且内容哈希与磁盘一致的目标进入 `changed_files`；blocked / unsettled / not_landed / abandoned 只进 `excluded`（`README.md:1114-1123`）。写类动作仍走 Phase 4 的 pre-check / approval；`into_decision` 不签发、不替代任何审批。
- 结算只看最终 `exit_code`（`hooks.py:1080-1081`）；被 Phase 4 门禁拦下的动作没有执行，结算为 blocked，不会因批次变成 allowed。
- 因此“治理强度”的**授权**部分不受 C1-b 影响；受影响的是**证据范围**（`changed_files` → 测试选择 / served checkers）。

### 8.2 `unreadable` 降级与“治理强度”

C1-b 的设计是：账本读不出 → `pre_evidence.batch.status="unreadable"`、`applied=false`、changed 回退为 `(event.file,)`、stderr 一行 `BATCH VIEW UNAVAILABLE`、**不阻断**（`hooks.py:1375-1389`；`README.md:1131-1133`；`readings/2026-10-21-C1-b-batch-into-decision.md` §1 的 Q7 裁定，04 5.88 登记残项）。这**会影响**“治理强度”的读数：

- 它不是授权层的 fail-open，但它是**证据范围**的 fail-open：本来会被批次带进 changed 的测试/生产文件可能不在了，测试选择与 `served_checkers` 随之变化；同一条动作可能因为“没按批次算”而 block，也可能因为“本来会被 block 的 stepwise 误伤”不存在而 allow。
- 可接受边界（必须同时满足）：
  1. 每条 `pre_evidence_status=collected` 的判定记录在 `into_decision=true` 下都必须有 `pre_evidence.batch`；缺失 = 记录无效。`pre_evidence_status=unavailable` 的记录本来就没有 `pre_evidence.batch`（`hooks.py:2042-2045`），它是失败关闭，不是“没按批次算”，按第 2 条处理。
  2. 任一被计分的写动作出现 `status=unreadable` **或** `pre_evidence_status=unavailable` → 该 run 的该步记 **instrumentation-degraded**，不进“治理强度”比较；建议整 run 作废重跑（因为冻结配置的预期行为没有发生）。至少不得把它与干净 run 合并。
  3. `status=partial` / `truncated` / `excluded` 非空必须逐项记录；不能把 `partial` 当 `applied`。
  4. 治理强度按 `served_checkers` / `selection.level` / `check_volume` 报，不按 block 数报；“block 少了”不等于“治理弱了”，也可能是批次修好了 stepwise 误伤。
  5. 账本可写性属于部署前置：`.policy` 必须可追加；若不可写，`settle` 写 `unavailable`，下一步读成 `unsettled`，这是过程偏差，按第 1 条处理。
- 并发/无锁（04 5.88 ②）：同会话并发追加仍无锁/无 fsync；半行进 `skipped`/`legacy`，不成员；真机上更可能表现为 `partial` 或 `unsettled`。本实验不把“并发下没看到丢成员”当证明；出现即记录。

## 9 边界与未取得

- 本读数没有跑真机：第 3.3 节是离线 `policy.check` 复现（临时目录 `.tmp/c1b-treatment-probe`，不是受跟踪证据），不是 Hook 读数；真机重读是第 6 节的门。
- 新题库尚未冻结（task-8 进行中）；第 7 节是预期行为与审计键清单，不是新题库的读数。
- 未取得：`unsettled` 的真机现场（C1-b 读数 §6 残项 1）、并发锁/fsync（残项 2）、TTL 性能基线（残项 3）、新题库的 activation 实测。
- 本读数不签发任何审批、不修改任何冻结件；若 Lead 采纳 T3，05 §8 需新增一条变更记录（treatment 不变；C1-b 定为平台基线；旧 run 作废）。

## 10 给 Lead 抄进 04/06 的短句

**04 5.46 / 5.88（一行）**：C1-b 裁定为**平台代际基线（T3）**，不是 treatment——A/B 两臂统一 `into_decision=true, max_targets=20`（C 无适配器，N/A），A/B 仍只差 `validation/test-layout.yaml` 的 `production_patterns`；旧 A/B/C n=1（清单 HEAD `34b153c` / run 起点 `889c97c`、AUDIT 1.4/账本 1.0）与旧 M5b activation 作废，新 run 必须用冻结后的每臂 adapter 配置重跑 C1-b 门 2/4/5 与 activation。

**06（一条，可拆两行）**：D 门 2 的 C1-b 归属已裁为 T3（平台基线）；旧 n=1 与旧 M5b 不再引用；run-manifest 17 字段不足以记录平台代际（adapter config digest / `BATCH_LEDGER_SCHEMA_VERSION=1.1` / `AUDIT_SCHEMA_VERSION=1.5` / `into_decision` / A 臂的 `before` 快照），建议新增 `platform_generation` 字段并把 `RUN_MANIFEST_SCHEMA_VERSION` 1.0→1.1（同批 scorer 2→3、重生成 manifest）。

**风险短句**：T3 下旧 M5b 的 A block 在离线复现里变成 allow（B 原本 allow）；新题库若所有 `tools/` 题都要求“先写测试”，批次会把测试带进 changed，activation 消失——必须保留至少一道“基线测试 + 只写 tools 实现”的题，或在冻结读数里证明新的 activation，否则 D 构造门不成立。
