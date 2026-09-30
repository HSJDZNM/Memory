# 台阶 3b（D-1(b)）· 落码与读数（实施记录）

- **执行者**：控制面重构的**唯一写者**（本会话）
- **树**：`C:\Users\ZNM\Downloads\Memory-rf`，分支 `refactor/control-plane` @ **`3ca3c36`**（开工读数）
- **解释器**：`.venv\Scripts\python.exe`（3.13.11）
- **裁定**：`docs/project/engineering-policy-platform/designs/控制面重构方案.md` §10 的 **D-1b** 行
  （2026-09-29，使用者授权代定）；字段级差集与分析依据见同目录 `13-step3b-d1-field-diff.md`
- **状态**：**已落码 + R-d 通过 + 本机门禁 33/33 全绿**。3c（义务账，按 L5 以 warn 跑一轮）与
  §3.6 评估**未开始**，按裁定留到下一轮。

---

## 0 一句话

`pending`（「待实现」）从 `violations` 移入**独立通道** `pending_findings`，
**四种 decision 逐个不变**（J1 的硬约束），决策协议 1.0→1.1、判定记录 1.1→1.2，
统一版本规则写进 AGENTS 第 55 条；B 类 7 处"绿但静默流失"的地方补上了断言。

---

## 1 落码清单

### 1.1 13 号 §1.3（9 项，逐项）

| # | 位置 | 落点（改后行号） | 处置 |
| --- | --- | --- | --- |
| 1 | `expected_decision` 追加 `pending` 关键字参数 | `src/policy/models.py:1087` | 已改；默认 `()`，旧调用点行为不变 |
| 2 | 空判定改成"两个通道都空" | `src/policy/models.py:1109` | 已改（`if not violations and not pending`）；**阻断判定一字不动**，仍只读 `violations` |
| 3 | 构造期自洽校验喂 pending | `src/policy/models.py:975/993` | 已改；另加**构造期不变量** `_pending_findings_are_advisory`（severity 必须 WARNING） |
| 4 | `to_decision_dict` 新增第 11 个键 | `src/policy/models.py:1042` 之后 | 已改，形状与 `violations` 条目**逐字段同形**（复用 `_evidence_payload`） |
| 5 | `_evidence_violations` 拆两条流 | `src/policy/checkers.py:162` | 已改，返回 `CheckerFindings(violations, pending_findings)`；`_finding_violations` 只产 findings |
| 6 | `pending_implementation_violation` 改名 | `src/policy/checkers.py:182` | 已改为 `pending_implementation_finding`（`__all__` 同步） |
| 7 | `Handler` 返回类型 | `src/policy/checkers.py:101` / `:89` | 已扩为 `CheckerFindings`；五种证据类 checker 仍共用 `_evidence_violations` 一个入口 |
| 8 | 引擎分派两条流 | `src/policy/engine.py:142-187` | 已改：两个列表**各排各的**（同一把 `Violation.sort_key`），不按文本猜通道 |
| 9 | `ValidationResult` 构造 | `src/policy/engine.py:180-187` | 已改：`pending_findings=tuple(...)` 并喂给 `expected_decision` |

**明确不动的字段（原样）**：`EvidenceBundle.pending_implementation`、`PipelineReport.pending_implementation`、
`PendingImplementation`、`EVIDENCE_SCHEMA_VERSION = "1.2"`、`PIPELINE_SCHEMA_VERSION = "1.2"`——
理由同 13 号 §1.3 末尾：本台阶改的是"判定载荷怎么表达它"，不是"验证器那一侧发生了什么"。

### 1.2 13 号 §4.2（升版引用点，逐项）

| # | 位置 | 读数 |
| --- | --- | --- |
| 1 | `src/policy/models.py:108` | `SCHEMA_VERSION = "1.1"` |
| 2 | `SUPPORTED_SCHEMA_VERSIONS` | 自动跟随 → 只认 `{"1.1"}` |
| 3 | `src/policy/models.py:123` | `POLICY_VERSION = "decision-1.1"`（裁定原文） |
| 4 | 字段默认值引用常量 | 自动跟随 |
| 5 | `tests/fixtures/decisions/{allow,warning,block,approval}.json` | **显式重记**（`POLICY_UPDATE_SNAPSHOTS=1`），见 §2.5 |
| 6 | `tests/contract/test_validator_protocol.py` | 字面量 `"1.1"` + 键集 11 个（注释写明"1.0→1.1 是台阶 3b 动的，不是 Phase 5） |
| 7–8 | `tests/contract/test_decision_protocol.py:211/224` | `"decision-1.1"` |
| 9 | `tests/unit/test_decisions.py:259` | `"decision-1.1"` |
| 10 | `tests/integration/test_cli.py:251` | `"decision-1.1"` |
| 11 | `api/openapi.json` | `openapi --check` 先报 2 处漂移（`x-decision-schema-version`、`x-policy-generation`），再 `--write` 重生成 |
| 12–13 | `policy_api.models.DECISION_PAYLOAD_SCHEMA_VERSION` / `orchestration.models.policy_version` | 自动跟随（从核心取值） |
| 14 | `orchestration/checkpoint.py` 的 `_REFUSE_DIMENSIONS` | 自动产生的后果：**旧 checkpoint 一律 REFUSE**（正面证明见 §4.2） |
| 15 | `tools/phase_evidence.py` | 自动跟随（从核心 import），未手写 |
| 16 | 历史文档（`phase-1-policy-engine.md` 等） | **不改**：历史文档记录的是历史 |
| 17 | `AGENTS.md` 第 18 条 | 已改（1.1 / decision-1.1 / "1.0 的载荷一律拒收"） |
| **+** | `tests/unit/test_hook_skip_visibility.py:310` | **13 号清单漏了这一条**（清单写在台阶 3a 之前，当时审计版本还是 1.0）：`AUDIT_SCHEMA_VERSION == "1.2"` |
| **+** | `src/adapters/dsh/README.md:422` | 同样漏了：原文写死 `AUDIT_SCHEMA_VERSION = "1.0"`（3a 之后就已经过时），已改成"随键集合走 + 历史先例登记" |

**另外两处 13 号清单没有、但升版必然触发的生成物**（"生成器是唯一真相源"，`--check` 是门禁）：

| 生成物 | 处置 |
| --- | --- |
| `tools/phase7_cells.py`（学习手册 Phase 7） | 生成期断言 `decision_versions == ('1.0','phase-1')` → `('1.1','decision-1.1')`；两处 markdown 版本表与一处**小结打印**同步（打印改成从变量取值，不再写死字面量） |
| `docs/project/architecture/tech-detail/06-Policy-API/cells.py` | 内容源里 `assert decision_versions == ("1.0","phase-1")` 与三处版本表/小结同步；两份 notebook 均已重新生成 |
| `tools/build_learning_notebook.py` | Phase 0/1 的"文档写过的决策载荷字段"清单补上 `pending_findings`（两处 `expected_decision`），并修正 Phase 1 术语表的 `1.0` |

> 口径说明：`tools/**` 里其余的 `"1.0"` 字面量经逐条核对属于**别的协议**
> （AgentEvent 的 `schema_version`、API 配置文件自己的 `schema_version`、
> 工具注册表的 ToolSpec / ValidatorSpec 版本、provenance 自己的协议）——**不属于本台阶**。

### 1.3 B 类 7 处（"保持绿但语义静默流失"，逐处）

| # | 位置 | 处置 | 补的断言在哪 |
| --- | --- | --- | --- |
| B1 | `src/adapters/dsh/hooks.py:1249`（给模型看的 stderr） | **改**：`warnings` 追加 `f"{id}（待实现）"` | `tests/integration/test_dsh_pre_evidence_hook.py`：`"TESTING-900@1" in stderr` + `"待实现" in stderr` |
| B2 | `src/adapters/dsh/hooks.py:912`（账本） | **改**：新增 `pending_findings` 键（条目形状与 `violations` 逐字段相同；**恒存在**，空时是 `[]`） | `tests/unit/test_hook_violation_visibility.py::test_a_pending_only_decision_is_distinguishable_from_a_clean_one` |
| B3 | `src/adapters/dsh/hooks.py:185`（`VIOLATIONS_NOTE`） | **改**：口径文本补第三通道 | 同文件 `test_the_note_writes_down_the_two_meanings` 补两条断言 |
| B4 | `src/policy_api/runtime.py`（响应 `summary` + 请求级 JSONL） | **只补断言，不加键**（理由见 §5.1） | `tests/integration/test_api_http.py` 两处：`summary.violations == len(decision["violations"])`、`decision["pending_findings"] == []` |
| B5 | `src/policy/check.py`（文本渲染） | **改**：pending 段 + 理由行不再为空；单条渲染抽成 `_finding_lines` **两个通道共用一份** | `tests/unit/test_validator_checkers.py::test_pending_only_prints_a_reason_line_instead_of_an_empty_one`（断言 `required_action=None` **不出现**） |
| B6 | `src/policy/models.py:1008`（`severity_counts`） | **改**：文档串写明"只统计 violations" | A1/A2 用例补 `result.severity_counts == {}` |
| B7 | `src/policy_api/runtime.py:727`（检索 `PolicyFact`） | **不改**（pending 不是违规事实），写下一行"为什么不改" | 无（登记即结论） |

### 1.4 AGENTS 与方案

- **AGENTS 第 51 条**：判定侧改成"产出 warning 级的**独立发现**"，写明 D-1(b) 的裁定与理由、
  J1(b)、以及"空判定要求两个通道都空 / 阻断判定只读 violations / 构造期不变量"。
- **AGENTS 新增第 55 条**：统一版本规则——任何协议载荷**加键或改语义**都按**该协议自己的**版本号递增；
  列出本仓库**五条版本轴**；把 P1 与台阶 2"加键未升版"登记为**历史先例、只登记不回改**。
- **AGENTS 第 31 条**：把"删字段或改语义 = 新 API 版本"补成"删字段、**新增键**或改语义"，指向第 55 条。
- **方案 §10**：新增 **D-1b** 行 + "D-1b 的执行口径"小节（协议选型、两个必写进提交说明的后果、明确不做的事）。

---

## 2 R-d 读数（判据：13 号 §5.4 的预注册形状）

### 2.1 仪器与产物

| 产物 | sha256 | 字节 |
| --- | --- | --- |
| `.tmp/step3b/decisions-before.json`（分析会话采集，本台阶未改） | `FB9A4269B6ED6711E7606D51FDD8E8DFF485AF9DBF78D1B435F40DEAA67DFF7A` | 27288 |
| `.tmp/step3b/decisions-after.json` | `CFAD8C32C59A57A49290759D54DB020C57F9CB6A07F0FBDF7D759D9F13AD4588` | 23992 |
| `.tmp/step3b/field-diff.json` | `AC9377022B4C6D3469259B1778E2AABD7B1F77839E1E9D4C9BA2823255C3D310` | 23910 |
| `.tmp/step3b/field-diff-selfcheck.json` | `48966A39411A67A1D7A6596F477E0DDA6049AC430F7156B47D0800D97C5B274A` | 434 |
| `.tmp/step3b/field-diff-negative-control.json` | `7CEC5CB1712728C3121E6152C225F634EFD205CC068B1B3C6341C71202C2F5D1` | 1875 |
| `.tmp/step3b/verify_after.py`（本轮新增的核对脚本） | `71335C6AEB90EBE2940916D2121D227F56E6F431468EC6BC7009C1FD4C650867` | 5111 |

仪器自检：`same_tree_rerun_identical True`（同一进程内重算两遍逐字节相同）。
`json_field_diff.py` 仍按原样调用，**未改一个字节**（它的口径是本次的尺子）。

**after 侧体积变小是预期的，不是丢内容**：探针把 `payload.violations` 与顶层 `violations`
各记一份；pending 移出后同一条说明从"两份"变成"一份（`payload.pending_findings`）"。

### 2.2 对照 §5.4（逐条）

| 场景 | decision（before → after） | §5.4 预期 | violations | pending_findings | 结论 |
| --- | --- | --- | --- | --- | --- |
| `s1_allow` | `allow` → `allow` | 相同 | 0 → 0 | 0 | 相符 |
| `s2_warning` | `allow_with_warnings` → 同 | 相同 | 1 → 1 | 0 | 相符 |
| `s3_block` | `block` → `block` | 相同 | 2 → 2 | 0 | 相符 |
| `s4_approval` | `block`（approval） → 同 | 相同 | 0 → 0 | 0 | 相符 |
| `s5_pending_only` | `allow_with_warnings` → 同 | **不变** | **1 → 0** | **1** | 相符（J1(b) 的正面） |
| `s6_pending_two_rules` | `allow_with_warnings` → 同 | **不变** | **2 → 0** | **2** | 相符 |
| `s7_pending_plus_finding` | `block` → `block` | **不变** | **2 → 1**（只剩 DOC-001） | **1** | 相符（混批） |
| `s8_approval_plus_pending` | `block`（approval） → 同 | **不变** | **1 → 0** | **1** | 相符（**审批路径 + 只有 pending**，最容易破的一条） |
| `s10_approval_only_plus_pending` | `block`（approval） → 同 | 不变 | 0 → 0 | 0 | 相符 |
| `s9_uncovered` | `block` → `block` | 不变 | 1（critical） → 1 | 0 | 相符（失败关闭兜底） |

**硬约束（机器核对，不是眼看）**：

- 差集条数 **236**；其中出现 `.decision` 的行 **0**、出现 `.required_action` 的行 **0**、
  出现 `decision_table` 的行 **0**；
- `decision_table`（`expected_decision` 的 10 行真值表）**逐字节相同**；
- 逐场景 `decision` 与 `required_action` 全等（§2.2 表）；
- 载荷键集合 = 旧 10 键 + `pending_findings`（无删除）；
- 除 `schema_version` / `policy_version` / `violations` / `pending_findings` 外，
  **旧键的值一处未漂移**。

**J1(b)**：after 侧所有 10 个场景的 `violations` 里，`message` 含"待实现"的条目数 = **0**；
同时 `pending_findings` 非空（s5/s6/s7/s8）——只断言前者会被"把功能删掉"满足，所以两者一起断言。

**形状**：`pending_findings` 的每一条与 `violations` 条目**键集合相同**
（`rule_id / rule_version / severity / message / evidence`）且 `severity == "warning"`。

### 2.3 负对照与自检（AGENTS 第 45 条：仪器必须能红）

| 运行 | 读数 | 退出码 |
| --- | --- | --- |
| 自检：`--before before.json --after before.json` | `count 0` | **0** |
| 负对照：`--before before.json --after decisions-mutated-control.json` | `count 8`（含 `s5_pending_only.decision: allow_with_warnings -> allow` 这条**故意制造的错**） | **1** |
| 正式差集：before → after | `count 236` | 1（**有差异是预期的**，R-d 要求交出差异） |

一红一绿合起来才证明这把尺子在量东西：**同一仪器在相同输入上 0 条 / exit 0，
在"decision 被改动"的输入上立刻报出那条 decision**。

### 2.4 只跑引擎级探针覆盖不到的地方（登记，不声称覆盖）

13 号 §5.5 的端到端仪器（`.tmp/q7-repro/q7_repro.py`，真 Hook + 真 stdin + `pre_evidence`）
**本轮没有跑**：它的读数口径要另写，且 R-d 的判据是 §5.4 的引擎级形状。
Hook 侧的 B1/B2 由**真实产物的集成用例**覆盖
（`test_dsh_pre_evidence_hook.py` 走生产 CLI + 真流水线 + 真审计文件），
但那不是 §5.5 的 `readings.json` 口径——**不要把两者读成同一件事**。

---

## 3 门禁读数

**原文命令**（与裁定给的完全一致，两次都是这一条）：

```powershell
.venv\Scripts\python.exe tools/ci_local.py --full --python .venv\Scripts\python.exe
```

跑了**两次**：第一次在写本记录之前，第二次在本记录落树之后（最终树）。**归档读数是第二次**：

| 项 | run1（未含本记录） | **run2（最终树，归档）** |
| --- | --- | --- |
| 选组行 | `改动文件 786 个；执行 33 步（本机跳过 11 步，登记豁免 2 步）` | `改动文件 787 个；执行 33 步（本机跳过 11 步，登记豁免 2 步）` |
| 步骤 | 33/33 `rc=0` | **33/33 `rc=0`**，非 0 计数 **0** |
| 结论行 | `本机检查全部通过（33 步）` | `本机检查全部通过（33 步）` |
| 进程退出码 | **0** | **0** |
| 合并测试 | `1946 passed, 1 skipped, 3 warnings in 304.01s` | `1946 passed, 1 skipped, 3 warnings in 333.03s (0:05:33)` |
| 总耗时 | 8m 26.2s | **9m 03.8s**（测试 5m34.6s / 学习手册 1m21.6s / 编排闭环 1m10.2s） |
| 全量日志 | — | `.tmp/step3b/ci-local-full.log`（168924 B，sha256 `FB3E6E19661DCC4B796B6D3FC2BF7B176C9F08CFA59DB3560F02E7C0DB753518`） |

skip 的唯一一条 = `tests/unit/test_validator_facts.py`（本机不允许创建符号链接，Windows 需要开发者模式）。

> **一处必须说清的口径**：run2 的 `改动文件` 比 run1 多 1，多出来的就是本文件本身；
> run2 之后本文件**只改过本节这几个数字**（路径集合没变，而 `改动文件` 是按路径计的，
> 所以 787 仍然成立）。除本节外，本记录描述的所有读数都出自上面那两次运行。

**测试增量对账**（把数字接上，而不是只说"绿了"）：上一台阶（3a）的读数是 `1942`
（1934 + 新增 8，见提交 `3ca3c36` 的更正文），本轮 **1946 = 1942 + 4**，新增的 4 条正是：

1. `test_the_pending_channel_refuses_a_blocking_severity`（构造期不变量）
2. `test_pending_only_prints_a_reason_line_instead_of_an_empty_one`（B5）
3. `test_decision_table_with_the_pending_channel`（U2 的真值表）
4. `test_a_pending_only_decision_is_distinguishable_from_a_clean_one`（B2）

**"改动文件 786 个"不是本轮引入的异常**：它是 `ci_local._changed_paths()` 相对基线
（`origin/main...HEAD`）算出来的累计值，历史读数 `759`（10 号）→ `773`（11 号）→ `786`（本轮）单调增长；
`--full` 下它只用于打印，不参与选组。

**编排闭环那一步的 `fail（未接线 / 无留痕 6 个通道）` 是本机通道清点，不是本台阶的红**：
该步骤不加 `--check` 时退出码为 0，且它清点的是**宿主 profile patch 有没有挂策略桥**
（desktop / headless / web 等），与本轮改的判定载荷无关。**逐项核实过**：6 条都是
`not_wired` / `hooks_config_missing` / `audit_never_written`，没有一条提到 decision / pending / 协议版本。

**门禁期间没有并发**：本轮只跑这一次 `ci_local.py`（AGENTS 第 5 条的排他锁要求），
两份 notebook 的重新生成也都在它之前完成。

---

## 4 两个破坏性后果的正面证明

### 4.1 1.0 的决策载荷会被拒收

```text
$ .venv\Scripts\python.exe -c "parse_decision({'schema_version':'1.0', ...})"
1.0 payload rejected: 未知决策协议版本 '1.0'；本实现只接受 ['1.1']，拒绝消费
current schema 1.1 generation decision-1.1
```

这条不是"顺手拒绝"：读者不能靠"violations 里有一条 warning"去猜它是不是 pending——
那正是同名两义（AGENTS 第 50 条）在协议层的形态。

### 4.2 旧 checkpoint 一律 REFUSE

`orchestration/checkpoint.py` 的 `_REFUSE_DIMENSIONS = ("policy_version", "decision_schema_version")`；
`tests/unit/test_orchestration_state.py::test_plan_resume_generation_change_refuses`
（参数化覆盖这两个维度）在门禁里**通过**。本台阶两个维度**同时**变了，
所以任何 1.0/phase-1 时期写下的 checkpoint 恢复时都会得到 `ResumeError` →
`FailureCode.CHECKPOINT_INCOMPATIBLE`（AGENTS 第 36 条的设计意图：协议世代变了直接拒绝恢复）。

---

## 5 未做 / 未核实 / 未覆盖（逐条写下来）

### 5.1 13 号 B4 的"另加一个 pending 计数键"——**未做**（登记待裁）

- **13 号原文**要求：`src/policy_api/runtime.py` 的响应 `summary` 与请求级 JSONL
  "保持 `violations` 语义不变 + 另加一个 pending 计数键（只增不改）"。
- **未做的理由**：按本台阶新写的统一规则（AGENTS 第 55 条），给 API 载荷加键要递增
  `API_SCHEMA_VERSION`（1.0→1.1，**会拒收 1.0 的客户端**）、给 `RequestLogEntry` 加键要递增
  `REQUEST_LOG_SCHEMA_VERSION`（1.0→1.1）。这两项**破坏性后果不在裁定的清单里**
  （裁定只列了"1.0 载荷会被拒收"与"旧 checkpoint REFUSE"），且会连带
  `tools/api_loop.py` 的 8 处 `api_version` 字面量、`tools/phase7_cells.py:837` 的生成期断言
  与手册重生成。**超出授权范围时停在门口并登记，而不是自行扩大爆炸半径。**
- **替代的断言（已补）**：`summary.violations` 与 `decision["violations"]` 逐字段一致，
  且 pending 的可见性由**同一个响应体里的决策载荷**承接
  （`decision["pending_findings"]`，测试断言它是明确的空列表）。
- **请评审裁定**：要么授权这两处升版（连带清单已写在方案 §10），要么把第 55 条的范围写成
  "只覆盖写侧载荷、读侧附加键不算"。

### 5.2 B4 的**正例**（pending-only 经 API）没有测试覆盖

- `/v1/policy/evaluate` 走 `evaluate(rules, context)`（无证据），**结构上不可能**产生 pending；
- `/v1/validation/evaluate` 能（它跑真流水线并把 `EvidenceBundle` 交给引擎），
  但要造出 pending 需要一份"选中的测试 import 项目内不存在的模块"的 **API 夹具**
  （`tests/api_support.py` 的项目是固定形状的），本批未建。
- 因此 `test_api_http.py` 里补的是**不变量断言**（`summary.violations == len(decision["violations"])`
  与 `decision["pending_findings"] == []`），**不是 pending 正例**。
  按 AGENTS 第 45 条：**这条检查覆盖不到**，不许把它读成"经 API 的 pending 已经验过"。
- 同一条限制也适用于**请求级 JSONL**：本轮**没有**任何用例驱动出一条
  `decision=allow_with_warnings` 且 `violations=0` 的 API 日志行。

### 5.3 其他未核实项

1. **`.tmp/q7-repro/q7_repro.py`（§5.5 的端到端读数）没跑**：见 §2.4。
   13 号 §5.5 预注册的 `stderr_tail` 形状是"冒号后为空"——**本轮 B1 落了码**，
   所以那条预注册形状**不再是 after 侧的预期**（现在的预期是冒号后有 `TESTING-…（待实现）`）。
   这是 B1"必须补什么"与 §5.5"可选"两处之间的口径差，**未在真实 endl-to-end 仪器上实测**。
2. **`tests/integration/test_rule_corpus.py` 全量是否仍绿**：门禁的合并测试步骤**包含**它并全绿
   （1946 passed），但本轮**没有单独观察**那 12 处 `violations` 断言各自的读数。
3. **`s8`（block + 只有 pending）在真实 43 条规则下仍不可达**（`policies/` 下
   `requires_approval` 0 匹配，读数沿用 13 号 §6 第 4 条）；本轮**没有**重新核
   Phase 4 pre-check 是否会经另一条路造出 `required_action=approval`。
4. **`POLICY_VERSION = "decision-1.1"` 这个名字**是裁定给的；本轮只核实了"它与
   `SCHEMA_VERSION` 同进同退"这条不变量仍成立（`test_policy_version_is_the_protocol_generation_not_the_platform_phase` 绿），
   **没有**核实阶段证据、编排 checkpoint 快照等所有消费方对**新命名形态**的展示是否都自然。
5. **`docs/project/learning/**` 与 `tech-detail/**` 的重生成**：两份 `--check` 都绿（门禁里），
   但本轮**没有逐字读**重新生成出来的 phase-1 / phase-6 / phase-7 手册正文。
6. **本轮没有跑 `tools/cleanup.py`**（纪律要求），`.tmp/` 产物保留在树上供评审复核。
7. **本轮没有 push**、没有用 `--no-verify`、没有强推、没有用 `git add -f`。

---

## 6 复现命令（按顺序）

```powershell
# R-d：after 侧读数
.venv\Scripts\python.exe .tmp\step3b\probe_decisions.py --out .tmp\step3b\decisions-after.json

# 差集 / 自检 / 负对照（自检必须 0 且 exit 0；负对照必须 8 且 exit 1）
.venv\Scripts\python.exe .tmp\step3b\json_field_diff.py --before .tmp\step3b\decisions-before.json --after .tmp\step3b\decisions-after.json --out .tmp\step3b\field-diff.json
.venv\Scripts\python.exe .tmp\step3b\json_field_diff.py --before .tmp\step3b\decisions-before.json --after .tmp\step3b\decisions-before.json --out .tmp\step3b\field-diff-selfcheck.json
.venv\Scripts\python.exe .tmp\step3b\json_field_diff.py --before .tmp\step3b\decisions-before.json --after .tmp\step3b\decisions-mutated-control.json --out .tmp\step3b\field-diff-negative-control.json

# 逐条对照 §5.4 + 硬约束 + J1(b)
.venv\Scripts\python.exe .tmp\step3b\verify_after.py

# 门禁（原文命令）
.venv\Scripts\python.exe tools/ci_local.py --full --python .venv\Scripts\python.exe
```

> 纪律说明：本轮改动**只用 `write` / `edit` 落树**，提交按路径暂存；
> 没有 `--no-verify`、没有 `git add -f`、没有强推、没有跑 `tools/cleanup.py`。
