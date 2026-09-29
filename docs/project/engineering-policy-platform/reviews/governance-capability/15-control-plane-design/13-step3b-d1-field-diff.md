# 台阶 3b（D-1）· 字段级差集与受影响 fixture 清单（分析稿，**未落码**）

> 来源：`.tmp/step3b/REPORT.md`（分析会话产出，2026-09-29，基线树 `6b3dd36`/`07b726f`；`src/` 与 `tests/` 逐字节相同）。
> 状态：**待裁定后才落码**——3b 的提交必须同时改代码 / AGENTS 第 51 条 / 协议版本三者，
> 而「递增哪个协议版本」在 AGENTS 第 50–51 条与既有的 `AUDIT_SCHEMA_VERSION` 先例之间有真分歧，
> 因此本文件先交差集与清单，**不动任何源码**（裁定见本文 §5.3 的三个候选与代价）。
> 可执行仪器：`.tmp/step3b/probe_decisions.py`（10 场景、自检重跑逐字节相同）、
> `.tmp/step3b/json_field_diff.py`（递归逐字段、list 按标识键对齐）。before 读数 `decisions-before.json`
> （sha256[:16] `FB9A4269B6ED6711`）；自检 0 条 exit 0、负对照 8 条 exit 1。
# 台阶 3b（D-1(b)）· 字段级差集与受影响 fixture 清单

- **分析员**：analyst-3b-d1（**只读**；本文件与同目录脚本是唯一落盘产物）
- **树**：`C:\Users\ZNM\Downloads\Memory-rf`，分支 `refactor/control-plane` @ **6b3dd36**（`git rev-parse --short HEAD` 实测）
- **解释器**：`.venv\Scripts\python.exe`（3.13.x / 与 `11-step2-origin-closure.md` §6 同一颗）
- **判据**：方案 §台阶 3 的 **J1(b)**——`violations` 里**没有** pending 条目（`docs/project/engineering-policy-platform/designs/控制面重构方案.md:156`）
- **裁定原文**：`控制面重构方案.md:311`（D-1 行）——取 (b)：pending 移出 `violations`、改独立通道、**decision 仍为 `allow_with_warnings`（一个都不变）**、同批修订 AGENTS 第 51 条并递增记录协议版本
- **R-d 仪器与 before 读数**：`.tmp/step3b/probe_decisions.py`（sha256[:16] `CD01DB6FEB2E4FFD`）+ `.tmp/step3b/decisions-before.json`（`FB9A4269B6ED6711`，27288 B）+ `.tmp/step3b/json_field_diff.py`（`3B8D6C35B2B72F9B`）

> **读法警告（先读这一条）**：裁定里的"全部 decision 不变"指的是 **`decision` 这个值 / 判定结论**不变；
> **载荷本身必然变**（pending 换个位置就是载荷变更），否则 R-d 差集就不是 0 条。把"decision 不变"读成
> "整份载荷逐字节不变"会与同一行的"pending 移出 violations"直接矛盾。本报告按前者读，并把后者的
> 可取证据全部列出。

---

## 0 事实底稿（全部实测，非推测）

### 0.1 判定链路（现状）

| 环节 | 位置 | 读数 |
| --- | --- | --- |
| 造 warning 级 pending violation | `src/policy/checkers.py:169-196` | `severity=Severity.WARNING` 写死；`evidence.kind=rule.enforcement.checker`、`subject=test_modules[0]`、`value=missing_targets[0]`、`file=test_modules[0]`、`detail=reason + "；建议修复：" + fix` |
| 把它 extend 进 violations | `src/policy/checkers.py:149-166` | `_evidence_violations` 先 findings 再 pending |
| 证据类 checker 共用入口 | `src/policy/checkers.py:351-360` | 5 个证据类 checker **全部**指向 `_evidence_violations` |
| 引擎分派 | `src/policy/engine.py:142-159` | blocker → `blocker_violation`；pending 非空 → 走 handler；两者皆非 → `uncovered_checker_violation` |
| 排序 | `src/policy/engine.py:159` | `violations.sort(key=lambda item: item.sort_key)` |
| 决策表 | `src/policy/models.py:1028-1046` | 见 §2.1 |
| 构造期自洽校验 | `src/policy/models.py:953-961` | `expected_decision(self.violations, required_action=...)` 必须等于 `self.decision`，否则 `ValueError` |
| 载荷 | `src/policy/models.py:978-1004` | **10 个键**（实测）：`decision / matched_rules / policy_version / request_id / required_action / rule_set_hash / schema_version / skipped_rules / trace_id / violations` |

### 0.2 before 侧字段级读数（`.tmp/step3b/decisions-before.json`）

同一进程内重跑两遍逐字节相同（脚本自检 `same_tree_rerun_identical True`），无墙钟、无随机、无绝对路径。

| 场景 | 构造 | decision | required_action | violations 条数 | by_severity |
| --- | --- | --- | --- | --- | --- |
| `s1_allow` | 上下文路径，无命中 | `allow` | None | 0 | `{}` |
| `s2_warning` | `CODING-002`(warning) 命中 | `allow_with_warnings` | None | 1 | `{warning:1}` |
| `s3_block` | `ARCH-001`(error)+critical 命中 | `block` | None | 2 | `{error:1, critical:1}` |
| `s4_approval` | `requires_approval` 命中、无违规 | `block` | `approval` | 0 | `{}` |
| `s5_pending_only` | `TESTING-002` pending | `allow_with_warnings` | None | 1 | `{warning:1}` |
| `s6_pending_two_rules` | 两条测试规则，pending 覆盖两个 checker | `allow_with_warnings` | None | 2 | `{warning:2}` |
| `s7_pending_plus_finding` | `DOC-001` 真 error + pending | `block` | None | 2 | `{error:1, warning:1}` |
| **`s8_approval_plus_pending`** | `requires_approval` 命中 + pending | **`block`** | **`approval`** | **1（只有 pending）** | `{warning:1}` |
| `s10_approval_only_plus_pending` | 只有审批规则，pending 无规则可挂 | `block` | `approval` | 0 | `{}` |
| `s9_uncovered` | 无验证器供证 | `block` | None | 1 | `{critical:1}` |

`s5` 的 pending 条目（before，逐字段）：

```json
{"rule_id":"TESTING-002","rule_version":1,"severity":"warning",
 "message":"待实现（不是测试失败）：选中的测试 tests/test_order_service.py 因项目内还不存在的 shop.order_service:cancel_order 无法收集；本次写入被放行，但覆盖它的测试尚未能运行",
 "evidence":{"kind":"failing_tests","subject":"tests/test_order_service.py",
             "value":"shop.order_service:cancel_order","file":"tests/test_order_service.py",
             "detail":"待实现：…；建议修复：…"}}
```

**`s8` 是本台阶的关键读数**：今天确实存在 `decision=block` 且 `violations` 里**只有** pending 的批次。

---

## 1 协议字段清单：让 pending 走独立通道且 decision 不变

### 1.1 需要新增的字段（1 个）

| 项 | 取值 |
| --- | --- |
| 字段名 | **`pending_findings`**（备选 `pending_implementation`） |
| 类型 | `Tuple[Violation, ...] = ()` |
| 位置 | `src/policy/models.py:937`（`violations`）之后、`required_action` 之前 |
| 序列化键 | `to_decision_dict()` 新增第 11 个键 `"pending_findings"`（models.py:1002 之后） |
| 序列化形状 | **与 `violations` 条目逐字段同形**：`{rule_id, rule_version, severity, message, evidence}` |
| evidence 子对象 | **复用** `models.py:1013-1025` 的 `_evidence_payload`（同一函数，不另写一份） |
| 排序口径 | **同一把键**：`Violation.sort_key`（`models.py:910-913`＝`(canonical_id, evidence.value, evidence.subject)`），但**两个通道各排各的** |
| 构造期不变量 | 新通道条目 `severity is Severity.WARNING`（`model_validator`）；违反即 `ValueError` |
| 默认值 | `()`——旧调用点（`insufficient_context_violation` 等）与旧载荷解析行为不变 |

**为什么不叫 `violations`/`pending_violations`**：AGENTS 第 50 条"同名两义一律改名"。`violations` 的定义
被第 46 条钉死为"本次**真的报了违规**的规则"；pending 不是违规（`checkers.py:170-177` 自己的注释就
说"这条不是'检查发现了问题'"）。名字里带 `violation` 会把这个区分重新抹平。

### 1.2 被否决的两种取型（连同否决理由）

| 取型 | 形状 | 否决理由 |
| --- | --- | --- |
| **T2** 复用 `policy.evidence.PendingImplementation` | `Tuple[PendingImplementation, ...]` | ① **循环导入**：`evidence.py:22` 从 `.models` 导入，`models.py` 不能再反向导入——要么把模型搬到 `models.py`（跨模块移动），要么写第二份定义（漂移）。② **丢规则绑定**：`PendingImplementation`（`evidence.py:366-407`）没有 `rule_id`/`rule_version`，账本因而答不出"哪条规则的 checker 没跑成"。③ 补 `rule_id`/`rule_version` 会同时改 `EvidenceBundle`（`evidence.py:422`）与 `PipelineReport`（`pipeline.py:274`）的载荷 → **再触发一次 `EVIDENCE_SCHEMA_VERSION` / `PIPELINE_SCHEMA_VERSION` 递增**，同一件事要动两套协议版本 |
| **T3** 新模型 `PendingFinding` | `{rule_id, rule_version, message, evidence}`（无 `severity`） | 语义最干净（不携带恒为 warning 的 severity），但它与 `Violation` 只差一个字段，是**近乎重复的一份定义**；AGENTS 第 49/50 条（"一份声明"、"同名两义改写名"）都指向"能复用就别再定义第二份"。列为备选，不作首选 |

### 1.3 需要同步改的签名与调用点（**全部**，逐一给行号）

| # | 位置 | 现况 | 必改内容 |
| --- | --- | --- | --- |
| 1 | `src/policy/models.py:1028-1038` | `expected_decision(violations, *, required_action=None)` | 追加关键字参数 `pending: Tuple[Violation, ...] = ()` |
| 2 | `src/policy/models.py:1041-1046` | `_expected_decision(violations)` | 空判定改成 `if not violations and not pending: return ALLOW`；阻断判定**一字不动** |
| 3 | `src/policy/models.py:953-961` | `_decision_matches_findings` 只喂 `self.violations` | 必须喂 `pending=self.pending_findings`，否则引擎构造 `ValidationResult` **当场 `ValidationError`**（硬失败，不是静默） |
| 4 | `src/policy/models.py:978-1004` | `to_decision_dict` 10 键 | 追加 `"pending_findings": [...]`（形状同 `violations`） |
| 5 | `src/policy/checkers.py:149-166` `_evidence_violations` | 返回 `List[Violation]`（findings+pending 混在一起） | 拆成两条流：findings 走 `violations`、pending 走新通道。建议**新增** `pending_implementation_finding(rule, pending)` 而**保留** `_evidence_violations` 只产 findings |
| 6 | `src/policy/checkers.py:169` `pending_implementation_violation` | 名字里的 `_violation` 与"它不再是 violation"**同名两义** | 改名（如 `pending_implementation_finding`）或至少改注释；`__all__`（`checkers.py:56`）同步 |
| 7 | `src/policy/checkers.py:351-360` `_HANDLERS` | `Handler = Callable[..., List[Violation]]` | 若 handler 要一次返回两个通道，需扩返回类型；**五种证据类 checker 共用同一入口**，只需改一处 |
| 8 | `src/policy/engine.py:142-159` | 一个 `violations` 列表 | 分流：blocker/uncovered/findings → `violations`；pending → `pending_findings`；各自 `sort` |
| 9 | `src/policy/engine.py:166-175` | `ValidationResult(violations=tuple(violations), ...)` | 加 `pending_findings=tuple(pending)`，并把 pending 喂给 `expected_decision` |

**不动的字段（明确写下来）**：`EvidenceBundle.pending_implementation`（`evidence.py:422`）、
`PipelineReport.pending_implementation`（`pipeline.py:274`）、`PendingImplementation`（`evidence.py:366`）、
`EVIDENCE_SCHEMA_VERSION=1.2`（`evidence.py:56`）、`PIPELINE_SCHEMA_VERSION=1.2`（`pipeline.py:88`）。
**理由**：这三个对象描述的是"验证器这一侧发生了什么"，本台阶改的是"判定载荷怎么表达它"。
把它们一起改会让 `tests/contract/test_validator_protocol.py:105` 的
`set(EvidenceBundle().to_payload()) == set(model_fields) | {"schema"}` 与 :51/:70 的版本字面量同时动，
把一次改动扩成两套协议变更。

### 1.4 一个必须显式决策的派生属性

`src/policy/models.py:967-972` `severity_counts` 遍历的是 `self.violations`。改动后 pending-only 批次
会得到 `severity_counts == {}` 而 `decision == allow_with_warnings`。**这是对的**（severity 分布是
violations 的分布），但它必须写进 `ValidationResult` 的文档串——否则 `src/policy/check.py:630-633`
（`counts = result.severity_counts` → `detail` 为空 → `required_action=None`）会打印
`FAIL: decision=allow_with_warnings（required_action=None）` 这种**读不出理由**的行（见 §3.3）。

---

## 2 decision 不变的证明路径

### 2.1 现状真值表（实测，`.tmp/step3b/decisions-before.json` 的 `decision_table`）

`BLOCKING_SEVERITIES = {ERROR, CRITICAL}`（`models.py:233`）。

| violations 的 severity | required_action=None | required_action=approval |
| --- | --- | --- |
| `()` | `allow` | **`block`** |
| `{info}` | `allow_with_warnings` | `block` |
| `{warning}` | `allow_with_warnings` | `block` |
| `{error}` | `block` | `block` |
| `{critical}` | `block` | `block` |

### 2.2 改后的函数形状（最小证明程序）

```python
def expected_decision(violations, *, required_action=None, pending=()):
    if required_action is RequiredAction.APPROVAL:
        return Decision.BLOCK              # ① 一字不动，且仍是第一条
    if not violations and not pending:     # ② 唯一改动：空判定把 pending 也算进来
        return Decision.ALLOW
    if any(v.severity in BLOCKING_SEVERITIES for v in violations):  # ③ 一字不动，只读 violations
        return Decision.BLOCK
    return Decision.ALLOW_WITH_WARNINGS    # ④ 兜底
```

### 2.3 四种现有 decision 逐条不变

| decision | 改动前成立的条件 | 改动后 | 推理 |
| --- | --- | --- | --- |
| **allow** | 原 `violations` 为空且无审批 | 新 `violations` 为空 **且** `pending` 为空 → `allow` | 改动前"violations 为空"隐含"pending 为空"（pending 就在 violations 里）。改动把同一批数据拆成两个元组，②的空判定用"两者都空"重建了同一个谓词 |
| **allow_with_warnings** | 原 `violations` 非空且无阻断级 | 新 `violations` 非空 **或** `pending` 非空，且无阻断级 → `allow_with_warnings` | ③只读 `violations`；pending 条目的 severity **恒为 WARNING**（§1.1 的构造期不变量），进不了 `BLOCKING_SEVERITIES`。所以 ③ 不可能把"原来不阻断"变成"阻断"。原批次里 pending 贡献的 warning 从 ③ 消失，但它在②里以 `pending` 的身份出现，④ 的兜底结果一个字没变 |
| **block（违规路径）** | 原 `violations` 里有 `error/critical` | 新 `violations` 里有同一批 `error/critical` → `block` | ③ 读的仍是 `violations`；把 warning 级条目搬走**既不能造出也不能消掉**阻断级条目。反向也成立：改动后不可能出现"原来 block、现在不 block" |
| **block（审批路径）** | `required_action=APPROVAL` | 同左 → `block` | ① 是第一条且没动，`violations` / `pending` 的取值都不影响它。`tests/unit/test_decisions.py:166-177`（`violations==()` 也 block）本身就是既有回归测试 |

### 2.4 最容易破的那一条：**审批路径 + 只有 pending**（`s8`）

- **它今天真的能出现**（实测 `s8`）：规则 `{ARCH-004: requires_approval=true}` + `{TESTING-002: checker=failing_tests}`，
  证据包 `served_checkers=("forbidden_dependency",)`、`pending_implementation=(<一条 pending>,)` →
  `decision=block`、`required_action=approval`、`violations` = **1 条且只有那条 warning pending**。
- **是否走真实 43 条规则可达**：**不可达**。`grep -rn "requires_approval" policies/` → **0 匹配**
  （`grep -rn "approval" policies/` 也是 0）；只有合成规则集（测试 / 教科书 / tech-detail）才会出现。
  但判据必须按"可达的输入空间"写，不能按"当前规则集恰好没有"写。
- **破法**：把 `pending` 从②的空判定里漏掉 → `s5`/`s6`（pending-only，`allow_with_warnings`）
  **掉成 `allow`**，J1 的正面承诺（"先写测试不再被惩罚"的账本可读性）连带失效；
  把①挪到②之后并顺手用 `pending` 重算 → `s8`/`s4` 的 `block` 会掉。
- **第二处破法（构造期，硬失败）**：`models.py:953-961` 不同步改 → 引擎一构造 `ValidationResult`
  就 `ValidationError`。这是**好事**：没有静默通道。

### 2.5 建议的判据可执行化（J1(b) 的机器版本）

```python
def test_pending_is_not_a_violation():          # J1(b)
    result = evaluate(rules_with_testing_rule, ctx, evidence=bundle_with_pending_only)
    assert result.decision is Decision.ALLOW_WITH_WARNINGS      # 不变的那一半
    assert result.violations == ()                              # (b) 的一半
    assert [item.rule_id for item in result.pending_findings] == ["TESTING-002"]
    payload = result.to_decision_dict()
    assert payload["violations"] == []
    assert payload["pending_findings"]                          # 通道还在，只是不在 violations 里
    assert all("待实现" not in item["message"] for item in payload["violations"])
```

**只断言 `result.violations == ()` 不够**：那对"什么都不做"也成立（把 pending 整条丢掉即可）。
必须同时断言"通道里有东西"，否则判据会被"删功能"满足。

---

## 3 受影响断言与 fixture 清单

全仓 grep 口径：`violations`（tests 命中 172 处 / 30 文件）、`violations_by_severity`（20 处）、
`pending_implementation`（110 处）、`pending_for`、`pending`。下表只列**真的会被这次改动碰到**的。

### 3.1 A 类：**会变红**，必须显式更新（红是好事，它在逼改）

| # | file:line | 现在断言什么 | 改不改 / 怎么改 |
| --- | --- | --- | --- |
| A1 | `tests/unit/test_validator_checkers.py:476` | `[i.canonical_id for i in result.violations] == ["TESTING-002@1"]` | 改：分成两条断言（`violations == ()` + `pending_findings` 的 id） |
| A2 | `tests/unit/test_validator_checkers.py:477-484` | `violation = result.violations[0]`，再断言 `severity is WARNING`、message 含"待实现/本次写入被放行"、`severity_counts == {"warning": 1}` | 改：来源换成 `result.pending_findings[0]`；`severity_counts` 改成 `{}`（或删，见 §1.4） |
| A3 | `tests/unit/test_validator_checkers.py:495-501` | `payload["violations"][0]["severity"]=="warning"`、含"待实现"、`evidence["value"]` | 改：读 `payload["pending_findings"][0]` |
| A4 | `tests/integration/test_dsh_pre_evidence_hook.py:816` | `[i["rule_id"] for i in record["violations"]] == ["TESTING-900@1"]` | 改：`record["violations"] == []` + 新通道键（键名随 §1.1 定） |
| A5 | `tests/integration/test_dsh_pre_evidence_hook.py:817` | `record["violations_by_severity"] == {"warning": 1}` | 改：`{}`（该键的定义就是 violations 的分布） |
| A6 | `tests/integration/test_dsh_pre_evidence_hook.py:818` | `"待实现" in record["violations"][0]["message"]` | 改：读新通道 |
| A7 | `tests/contract/test_validator_protocol.py:253-269` | `SCHEMA_VERSION=="1.0"` + `to_decision_dict()` 的**精确 10 键集** | 改：加新键；版本字面量随 §4 定 |
| A8 | `tests/fixtures/decisions/{allow,warning,block,approval}.json` | 4 份协议快照逐字节比对（`test_decision_protocol.py:118`） | 必须重记：`$env:POLICY_UPDATE_SNAPSHOTS="1"; python -m pytest tests/contract -q`（**只有 Lead 能跑**；AGENTS 第 51 行区核心约束 7） |
| A9 | `api/openapi.json:753` `"x-decision-schema-version": "1.0"` | 契约快照 | 若 §4 采纳升版：`python -m policy_api.cli openapi --write`（`--check` 是 CI 门禁，AGENTS 第 31 条） |
| A10 | `tests/contract/test_decision_protocol.py:211 / :224`、`tests/unit/test_decisions.py:259`、`tests/integration/test_cli.py:251` | `policy_version == "phase-1"` | 若 §4 采纳升版，这 4 个字面量必须同步改 |

**A 类里"不会红但也在 3.1 语境里"的核对结果（明确排除）**：
- `tests/unit/test_validator_checkers.py:504-518`（pending 不掩盖别的 checker）：走 uncovered 路径，`violations[0]` 是 critical，**不变**。
- `tests/unit/test_validator_checkers.py:520-543`（blocker 赢过 pending）：**不变**。
- `tests/integration/test_dsh_pre_evidence_hook.py:852 / :891-892`（`violations == []` / `TESTING-900@1 error`）：分别对应"名字落地后 pending 消失"与"第三方包缺失仍是真违规"，**不变**。
- `tests/unit/test_validator_pending_implementation.py`（全篇）与 `tests/integration/test_validator_pipeline.py:618-653`：验的是**验证器/流水线层**，不经过决策载荷，**不动**。

### 3.2 B 类：**保持绿但语义静默流失**——必须补断言，否则"跑了、是绿的"变成假覆盖

这一类是本台阶**最危险**的一类：删掉 pending 的表达，测试仍然是绿的。

| # | file:line | 现在读什么 | 改动后会发生什么 | 必须补什么 |
| --- | --- | --- | --- | --- |
| B1 | `src/adapters/dsh/hooks.py:1144-1154` | `warnings = [v.canonical_id for v in decision.violations]` → 模型看到的 `[policy] ALLOWED WITH WARNINGS <tool> <file>: <ids>` | pending-only 批次 stderr 变成 `[policy] ALLOWED WITH WARNINGS write src/…: `（**id 列表为空**） | 该处必须同时读新通道（或对新通道另起一行）；`tests/integration/test_dsh_pre_evidence_hook.py:795` 只断言 `"ALLOWED WITH WARNINGS" in stderr` → **仍绿**，需加 `assert "TESTING-900@1" in completed.stderr` |
| B2 | `src/adapters/dsh/hooks.py:805-826` `violation_visibility` | 账本的 `violations`/`violations_by_severity` | Q7 记录的这两个键变空——A4/A5 会红，但 `tests/unit/test_hook_violation_visibility.py:441-468`（"allow 记录带 violations=[]"）那类**仍绿** | 新增一个"判定记录 = allow_with_warnings + violations=[] + 新通道非空"的用例，否则"判定了、没违规"与"判定了、有一条待实现"在账本上重新变得一样 |
| B3 | `src/adapters/dsh/hooks.py:172-177` `VIOLATIONS_NOTE` | 口径文本（"violations 是真的报了违规的规则…"） | 文本仍成立，但没有一个字提到新通道 | 口径文本必须补一句新通道是什么；`tests/unit/test_hook_violation_visibility.py:305-314` 只查"真的报了违规/参与过判定/allow_with_warnings"三个词 → **仍绿** |
| B4 | `src/policy_api/runtime.py:558, 577, 800, 807` | `"violations": len(result.violations)`（响应 summary + 请求级 JSONL） | Q7 场景经 API 会报 `violations: 0` 而 `decision=allow_with_warnings` | 保持 `violations` 语义不变 + **另加**一个 pending 计数键（只增不改）；`tests/unit/test_api_contract.py:88`、`tests/integration/test_api_http.py:172` 都不是 pending 场景 → **仍绿** |
| B5 | `src/policy/check.py:626-649` | `severity_counts` 与 `for violation in result.violations` | pending-only 时打印 `FAIL: decision=allow_with_warnings（required_action=None）` 且不列任何条目——**读不出理由** | 文本渲染必须有一个 pending 段（或在 :648 之后补一行）；**未核实有测试覆盖**（见 §6） |
| B6 | `src/policy/models.py:967-972` `severity_counts` | 属性文档 | pending-only → `{}` | 补文档串：本属性只统计 `violations` |
| B7 | `src/policy_api/runtime.py:727-735` | `for violation in result.violations` 造检索用的 `PolicyFact` | pending 不再进 facts（**这是对的**：它不是违规事实） | 无需改；写一行"不改且为什么"即可 |

**B 类的"决策值"全部不变**（§2），所以它们不会红——正因为不会红，才必须显式登记。

### 3.3 C 类：**不该动**（写下来，防止顺手改坏）

| file:line | 为什么不动 |
| --- | --- |
| `tests/unit/test_decisions.py:40-62` `test_decision_table` | 12 行真值表全部仍然成立。**建议新增**带 `pending` 参数的行，而不是改既有行 |
| `tests/unit/test_decisions.py:65-262` 其余 | 走上下文路径，与 pending 无关 |
| `tests/unit/test_hook_violation_visibility.py`（全篇，54 处） | 直接构造 `ValidationResult(violations=…)`，不经过 pending；`visibility["violations"]` 与 `to_decision_dict()["violations"][0]` 的逐字段比对（:272-276）自洽 |
| `tests/unit/test_dsh_pre_evidence.py:640-696` | 直接构造 warning violation 测 M3 分布，与 pending 无关 |
| `tests/contract/test_dependency_extraction_parity.py`、`test_dsh_adapter.py`、`test_enforcement_protocol.py:68/89`、`tests/unit/test_engine.py`、`test_models.py:325-350`、`test_loader.py:312-330`、`test_precheck.py:523`、`tests/security/test_multi_agent_adversarial.py:155` | 读 `violations` 但走 ARCH-001/critical 路径 |
| `tests/integration/test_rule_corpus.py`（12 处） | bad.py/good.py 反例走真实验证器；pending 不参与 |
| `tests/contract/test_validator_protocol.py:46-107`（除 :51/:70 版本字面量外） | 验的是 `EvidenceBundle`/`PipelineReport` 载荷，本台阶不动它们 |
| `tests/integration/test_api_http.py:163/172`、`tests/unit/test_api_contract.py:88` | 非 pending 场景；`violations` 计数的语义若保持"= len(decision.violations)"，它们不变 |
| `tests/contract/test_enforcement_protocol.py:68/89` | `pre_execute(...).decision.to_decision_dict()` 只做往返，键集不写死 |
| `tests/integration/test_cli.py:214-223` | 那是 CLI **包装层**的顶层键集，决策载荷嵌在 `result` 里 → 新键**不会**让它变红 |
| `tests/contract/test_orchestration_engine.py:397-420`、`tests/unit/test_orchestration_state.py:527` | 只断言"从核心取值"，不写死版本值 → 自动跟随 |
| `.tmp/q7-repro/q7_repro.py` 与 `runs/*/out/readings.json` | **不是仓库文件**；它的读数口径要在 after 侧重采（见 §5.4） |

### 3.4 生成物 / 门禁

| 生成物 | 现状读数（实测） | 本台阶后要不要重生成 |
| --- | --- | --- |
| `docs/project/architecture/tech-detail/**`（10 章） | `python docs/project/architecture/tech-detail/build_notebooks.py --check` → **exit 0，10 章全部"产物与内容源一致"，末行 `代码单元执行: 全部通过`** | **不需要**：`grep -rn "pending" docs/project/architecture/tech-detail` → **0 匹配**；没有任何一章写死决策载荷的键集。第 01 章（`cells.py:507-509`）、第 06 章（`:505`）、第 08 章（`cells.py:417/432`）只用 `to_decision_dict()` 的**自洽往返**与"两次运行相等"，新键两侧同增 → 仍相等。**但**：`tools/ci_local.py:156-161` 的 `HANDBOOK_PREFIXES` 含 `src/`，所以改 `src/policy/*` **会**触发这一步 → 必须保持绿（当前绿） |
| `docs/project/learning/**`（手册） | 未跑（重生成要几分钟，且我是只读分析员） | `tools/build_learning_notebook.py:1283-1323` 有 `requires_approval` 的演示单元 → **只改 src 不会改手册内容源**，所以 `build_learning_notebook.py` 的产物应当不变；**未核实**（见 §6） |
| `tests/fixtures/agent_events/dsh/*.json`（11 份） | `11-step2-origin-closure.md` §2 实测 11/11 判定全同 | **不变**：这些 fixture 不含 pending（判据见 §5.3） |
| `api/openapi.json` | `:753` 有 `x-decision-schema-version` | 仅在 §4 采纳升版时重生成 |
| `tools/phase_evidence.py` 的阶段证据 | `tools/phase_evidence.py:103-108, 589-591` 全部从核心取值 | 自动跟随，**不需要手改** |

---

## 4 协议版本：改哪个常量

### 4.1 "记录协议版本"的三种读法

| 读法 | 常量 | 定义处 | 它描述什么 | 本次是否该动 |
| --- | --- | --- | --- | --- |
| **(a) 决策协议** | `SCHEMA_VERSION = "1.0"` | `src/policy/models.py:104` | 决策载荷（`ValidationResult.to_decision_dict()`）的字段与语义 | **该动**：本台阶改的正是这份载荷 |
| (a′) 世代名 | `POLICY_VERSION = "phase-1"` | `src/policy/models.py:114` | 同一份载荷的"第几代" | **必须与 (a) 同进同退**，`models.py:111-112` 写死："`POLICY_VERSION` 只与 `schema_version` 同进同退" |
| (b) 证据协议 | `EVIDENCE_SCHEMA_VERSION = "1.2"` | `src/policy/evidence.py:56` | `EvidenceBundle` 的字段 | **不该动**：`EvidenceBundle.pending_implementation` 一个字段都不改 |
| (b′) 流水线协议 | `PIPELINE_SCHEMA_VERSION = "1.2"` | `src/validators/pipeline.py:88` | `PipelineReport` 的字段 | **不该动**，理由同上 |
| (c) 审计记录协议 | `AUDIT_SCHEMA_VERSION = "1.0"` | `src/adapters/dsh/hooks.py:113` | pre/post 审计记录的形状 | **有争议**，见 §4.3 |

### 4.2 推荐：动 `SCHEMA_VERSION`（1.0 → 1.1），`POLICY_VERSION` 同步

**正面理由（三条，全部有原文）**：

1. `models.py:102-103` 自己写着规则："任何字段增删或语义变化都必须显式改这里（`SCHEMA_VERSION`）"。
   本台阶**正是在做字段增删**（`violations` 少一类条目 + 新增一个键）。
2. `models.py:111`："`schema_version` 是唯一兼容轴：字段增删或语义变化时递增，消费方看不懂必须拒绝"。
   升到 1.1 之后，`SUPPORTED_SCHEMA_VERSIONS`（`models.py:105`）只认 1.1，1.0 的载荷被
   `parse_decision`（`models.py:1058-1062`）显式拒绝——这正是"pending 藏在 violations 里"这类
   旧载荷该有的下场：**读者不能靠"violations 里有条 warning"去猜它是不是 pending**。
3. 裁定原文（`控制面重构方案.md:311`）把三件事绑成一批："**代码 / AGENTS 第 51 条 / 协议版本 三者同批提交**"。
   三件里唯一"协议"属性的落点就是决策协议。

**升版的全部引用点（改一处会漏的那张清单）**：

| # | 位置 | 现况 | 处置 |
| --- | --- | --- | --- |
| 1 | `src/policy/models.py:104` | `SCHEMA_VERSION = "1.0"` | 改 |
| 2 | `src/policy/models.py:105` | `SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})` | 自动跟随；**若为了兼容而手工加回 "1.0"，等于让"看不懂就拒绝"失效**——不建议 |
| 3 | `src/policy/models.py:114` | `POLICY_VERSION = "phase-1"` | 同步改（新值待定，见下） |
| 4 | `src/policy/models.py:930 / :940` | 两个字段的默认值引用常量 | 自动跟随 |
| 5 | `tests/fixtures/decisions/{allow,warning,block,approval}.json` | 4 份快照各含 `schema_version` + `policy_version` | 用 `POLICY_UPDATE_SNAPSHOTS=1` 显式重记 |
| 6 | `tests/contract/test_validator_protocol.py:254` | `assert SCHEMA_VERSION == "1.0"` | 改字面量（该用例的**意图**"Phase 5 没动决策协议"仍然成立，只是它现在证明的是"1.1 的第 5 阶段"） |
| 7 | `tests/contract/test_decision_protocol.py:211` | `payload["policy_version"] == "phase-1"` | 改 |
| 8 | `tests/contract/test_decision_protocol.py:224` | `assert POLICY_VERSION == "phase-1"` | 改（注释已写"改动必须是有意的"） |
| 9 | `tests/unit/test_decisions.py:259` | `result.policy_version == "phase-1"` | 改 |
| 10 | `tests/integration/test_cli.py:251` | `result["policy_version"] == "phase-1"` | 改 |
| 11 | `api/openapi.json:753` | `"x-decision-schema-version": "1.0"` | `python -m policy_api.cli openapi --write` 重生成 |
| 12 | `src/policy_api/models.py:62` | `DECISION_PAYLOAD_SCHEMA_VERSION = SCHEMA_VERSION` | 自动跟随；`tests/contract/test_api_protocol.py:134` 是"从核心取值"的回归测试 → 仍绿 |
| 13 | `src/orchestration/models.py:345` | `policy_version: str = POLICY_VERSION` | 自动跟随 |
| 14 | `src/orchestration/checkpoint.py:56` | `_REFUSE_DIMENSIONS = ("policy_version", "decision_schema_version")` | **自动产生的后果**：升版后**旧 checkpoint 一律 REFUSE**（AGENTS 第 36 条的设计意图）。这不是缺陷，但必须在提交信息/记录里写明 |
| 15 | `tools/phase_evidence.py:103-108, 567-591` | 全部 import 自核心 | 自动跟随，阶段证据会自己改成新值——**不要手写** |
| 16 | `docs/project/engineering-policy-platform/**` 的历史文档（`phase-1-policy-engine.md:116` 等） | 记录"当时是 1.0" | **不改**：历史文档记录的是历史 |
| 17 | `AGENTS.md:18`（"Phase 1 的决策协议为 `SCHEMA_VERSION = "1.0"`"） | 仓库现状描述 | **必须同批改**（裁定要求 AGENTS 同批修订；第 18 行与第 51 条是同一批） |

**`POLICY_VERSION` 的新值**：按 `models.py:111-114` 只有"与 schema 同进同退"这一条规则，机械答案是
`"phase-2"`。**但这个名字读起来像平台阶段**——而 `models.py:113` 明说"不跟随平台阶段"，
`10-h4-field-diff.md` 那句"证据说 phase-5、载荷说 phase-1"的事故正是这个名字造成的误读。
两个可辩选项写在这里，**不由我拍板**：
- **P-a**：`"phase-2"`（沿用既有命名；改动最小；代价是把误读风险再留一代）；
- **P-b**：换成与 schema 对齐的世代名（如 `"1.1"`）。语义更准，但会打破"世代名"与"阶段名"的
  既有对照，且 §4.2 表里 6 处字面量都要按新形态改。

### 4.3 反驳意见（必须写下来，否则这个决定看起来没有代价）

**反驳 1：`AUDIT_SCHEMA_VERSION` 的先例是"加键不递增"。**
`src/adapters/dsh/README.md:422` 写着"既有字段与 `AUDIT_SCHEMA_VERSION = "1.0"` **一律不动**"，
而 P1（`reviews/governance-remediation/13-p1-p8-fix-round.md:43`、`01-hook-chain.md:131`）与台阶 2
（`11-step2-origin-closure.md` §2 第 3 行）**都在审计记录里加了新键而没有递增版本号**。
如果本次实现顺带在审计记录里加一个 `pending_findings` 键（B2 要求这么做），按这个先例它**不**触发
`AUDIT_SCHEMA_VERSION` 升版。**但这与 AGENTS 第 50 条"改载荷键必须按协议自己的规则显式递增版本号"
字面冲突**——本报告只能指认这个既有不一致，不能替 Lead 裁定；建议在 AGENTS 第 51 条的修订文字里
顺手把"审计记录加键算不算改协议"写成一条明确规则。

**反驳 2："递增记录协议版本"里的"记录"可能指审计记录，不是决策载荷。**
按字面，"记录"更像 `AUDIT_SCHEMA_VERSION`。**反对这种读法的证据**：(i) 审计记录的**形状**这次没变
（除非 New key，见反驳 1）；(ii) 变的确实是决策载荷的字段集合，而 `models.py:102` 把"字段增删"
与 `SCHEMA_VERSION` 一对一绑死；(iii) 裁定同句说"三者同批提交"，其中"AGENTS 第 51 条"讲的正是
**判定侧产出 warning 级 violation**，即决策载荷那一侧。

**反驳 3：升 `SCHEMA_VERSION` 的代价被低估了。**
升版会 (i) 让所有 **1.0 的历史载荷**（阶段证据归档、`reviews/` 里的 JSON 片段、`.tmp/` 旧读数）
在 `parse_decision` 下**一律拒绝**；(ii) 让**旧 checkpoint 全部 REFUSE**（表里第 14 行）；
(iii) 让 `api/openapi.json` 与 4 份快照同时变，把"一次改动"变成"一次协议迁移"。
**这条不是反对升版，而是要求把上面三条写进同批提交的说明里**——它们都是设计意图，但
"没说出来的设计意图"和"没预料到的副作用"在评审时长得一样。

**若最终不升版（不推荐，但要求写清代价）**：至少必须在 AGENTS 第 51 条里写明"1.0 载荷里
`violations` 不再含 pending"，否则"拒绝看不懂的载荷"这条核心约束（AGENTS 第 3/7 条）会
留下一个**同名不同义**的版本号——那比升版危险。

---

## 5 R-d 字段级差集：可执行方案

### 5.1 仪器（已落盘，可直接跑）

```powershell
# before（今天已跑过，见 §0.2）
.venv\Scripts\python.exe .tmp\step3b\probe_decisions.py --out .tmp\step3b\decisions-before.json

# after（Lead 落码后，同一条命令，只换输出名）
.venv\Scripts\python.exe .tmp\step3b\probe_decisions.py --out .tmp\step3b\decisions-after.json

# 差集（退出码 0 = 无差异，1 = 有差异）
.venv\Scripts\python.exe .tmp\step3b\json_field_diff.py `
    --before .tmp\step3b\decisions-before.json `
    --after  .tmp\step3b\decisions-after.json `
    --out    .tmp\step3b\field-diff.json
```

仪器设计（`probe_decisions.py`）：

- 只调 **`policy.engine.evaluate` 唯一判定入口**，读的是**决策载荷本身**（`to_decision_dict()`）+ `severity_counts` + `model_fields`；
- 输入**全是常量**：规则集 / 上下文 / 证据包均内联；**不含墙钟、不含绝对路径、不含随机**；
- 脚本**自己跑两遍**并断言逐字节相同，输出 `same_tree_rerun_identical` 与 sha256——不稳定的仪器不能做差集；
- 10 个场景覆盖四种 decision + pending 单/双 checker + pending 混真违规 + 审批门禁 + 失败关闭兜底。

### 5.2 必须剔除的不稳定字段（已内建在 `json_field_diff.py`）

`UNSTABLE_LEAF_KEYS` = `recorded_at / timestamp / elapsed_ms / duration_ms / verified_at / action_id / event_id / tool_use_id / generated_at`；
`UNSTABLE_LEAF_SUFFIXES` = `_digest / digest / sha256 / _sha256 / tree_digest`。

依据（不是猜的）：`11-step2-origin-closure.md` §2 第 4 行实测 `recorded_at=utc_now()` 进摘要
（`src/enforcement/audit.py:203, 329`），同一棵树上重跑也会漂移，是**墙钟漂移不是改动**。
**纪律**：`json_field_diff.py` 把剔除项**打印在输出里**（`excluded_leaf_keys` / `excluded_leaf_suffixes`），
因为被剔除的字段真的变了它是不会报的——"剔了什么"必须和"差在哪"一起读。

**注意**：§5.1 的引擎级探针**不含**这些字段（无墙钟），所以剔除项在这里主要是**为接续到
Hook/审计级差集（`.tmp/q7-repro/q7_repro.py` 那一路）时用的**。

### 5.3 负对照（自己会红，AGENTS 第 45 条）

```powershell
.venv\Scripts\python.exe .tmp\step3b\json_field_diff.py `
    --before .tmp\step3b\decisions-before.json `
    --after  .tmp\step3b\decisions-mutated-control.json `
    --out    .tmp\step3b\field-diff-negative-control.json
```

实测读数（`field-diff-negative-control.json` `303B346FCF1C3FED`）：**8 条差异，exit=1**，形状正是
D-1(b) 要产生的那种：

```
build.s5_pending_only.decision: "allow_with_warnings" -> "allow"            ← 故意制造的错
build.s5_pending_only.violations: 长度 1 -> 0
build.s5_pending_only.violations[('rule_id','TESTING-002')]: 删除（before = {…}）
build.s5_pending_only.payload.pending_findings: 新增 = […]
build.s5_pending_only.payload.violations: 长度 1 -> 0
```

同一仪器在**完全相同输入**上跑出 **0 条差异 / exit=0**（`field-diff-selfcheck.json` `87C129968822F7FC`）。
**一红一绿两个读数合起来才证明这把尺子在量东西。**

### 5.4 after 侧应当读到的形状（预注册，落码后逐条核对）

| 场景 | decision | violations | pending_findings | 说明 |
| --- | --- | --- | --- | --- |
| `s1`–`s4` | **相同** | **相同** | `[]`（新键） | 四种 decision 一个不变 |
| `s5`/`s6` | `allow_with_warnings` **不变** | **1→0 / 2→0** | 1 / 2 条 | J1(b) 的正面 |
| `s7` | `block` **不变** | 2→1（只剩 DOC-001） | 1 条 | 混批 |
| `s8` | `block` **不变** | 1→0 | 1 条 | **审批路径 + 只有 pending** |
| `s10` | `block` **不变** | 0 | `[]` | pending 无规则可挂 |
| `s9` | `block` **不变** | 1（critical） | `[]` | 失败关闭兜底 |

**预期差集条数**：每个含 pending 的场景 3 条（`decision` 之外的 violations 长度/元素删除 + 新键），
`s1`–`s4`/`s9`/`s10` 只多 1 条（`payload.pending_findings: 新增 = []`）。
**任何 `decision` 字段出现在差集里 = 违反了硬约束**，逐条红。

### 5.5 端到端那一层（可选，成本高，口径必须另写）

引擎级探针不覆盖 Hook/审计层。要覆盖 B1/B2/B4 这些"绿但静默"的地方，必须用
`.tmp/q7-repro/q7_repro.py`（**已存在的生产入口仪器**：`python -m adapters.dsh.hooks` 的 PreToolUse、
真 stdin、`--hooks-config` 过接线自检、`pre_evidence.enabled=true`、受治理工作区逐次全新副本）。
它的 `readings.json` 采集口径（实测 `runs/r2-function-cli/out/readings.json`）：
`hook_exit / decision / reason_code / layer / operation / violations / violations_by_severity /
pre_evidence_status / served_checkers / pending_implementation / pytest_status / pytest_reason /
tree_digest / target_sha256 / stderr_tail`。

**after 侧预期（预注册）**：`decision` 与 `reason_code` 仍是 `allow_with_warnings`、
`served_checkers` 与 `pending_implementation` 一字不变、`hook_exit` 仍是 0；
变的是 `violations`（1→0）、`violations_by_severity`（`{warning:1}`→`{}`）、
**`stderr_tail`（`[policy] ALLOWED WITH WARNINGS edit src/…: TESTING-002@1` → 冒号后为空）**。
最后这一条正是 B1：**它不会红，只能靠人去看。**

---

## 6 未核实清单

1. **`src/policy/check.py` 的文本渲染有没有测试覆盖 pending 路径**：未核实。我只确认 grep 到的
   `tests/integration/test_cli.py:205-271` 用的是无 pending 的夹具；**没有**穷举 `policy.check` 的全部入口。
   §3.2 B5 的"无覆盖"是**基于这次 grep 的结论**，不是全量证明。
2. **`docs/project/learning/**` 的手册是否需要重生成**：未核实。我只确认内容源
   （`tools/build_learning_notebook.py` 的 `PHASE_N_CELLS` 等）里没有 pending 字样相关的演示；
   `tools/check_notebook.py` 与生成器的逐字节比对**没有跑**（耗时且不属于本台阶判据）。
3. **`tests/integration/test_rule_corpus.py` 全量是否仍绿**：未核实。它是走真实验证器流水线的重用例，
   我没有跑（只读纪律 + 时间）。**论证**：它读 `result.violations`，而 pending 只在"项目内目标缺失"
   时产生，43 条规则的 bad.py/good.py 夹具不涉及该状态——**这是推理，不是读数**。
4. **`s8`（block + 只有 pending）在真实 43 条规则下是否可达**：**不可达**（`policies/` 下
   `requires_approval` 0 匹配，实测）；但"未来新增一条带审批的规则即可达"——我**没有**检查
   `registry/tool-registry.yaml` 的审批门禁是否会经另一条路（Phase 4 pre-check 的 approval 路径）
   造出 `required_action=approval` 的决策。`src/enforcement/precheck.py:415/511` 读的是
   `policy_decision.requires_approval`，看起来仍源自规则集，但**未核实**。
5. **全量 pytest / `tools/ci_local.py` 是否绿**：未核实，且**按纪律不能由我跑**（ci_local 取
   `.tmp/ci-local.lock` 排他锁）。我跑的是**定向套件**共 **292 passed**（210 + 82，两次命令），
   清单见 §7。定向套件 ≠ 全量门禁。
6. **`POLICY_VERSION` 升版后的新字面量**：未核实"应该叫什么"——这是人的命名决定（§4.2 给了 P-a/P-b）。
7. **`EVIDENCE_SCHEMA_VERSION` 是否会被 Lead 顺手一起动**：如果 Lead 选择 T2 取型（§1.2 已否决），
   就会连带升 `EVIDENCE_SCHEMA_VERSION`/`PIPELINE_SCHEMA_VERSION`。我按 T1 写的清单**不覆盖**
   那条路的引用点（`tests/contract/test_validator_protocol.py:51/70/104-107`、`pipeline.py` 载荷）。
8. **`PRE_EVIDENCE_STATUSES`（`hooks.py:149-155`）是否需要新增取值**：本台阶**不新增状态值**
   （`控制面重构方案.md:311` 明确"不新增 `not_evaluated`"），所以不需要。**未核实**的是：
   `pending_implementation` 作为 `ValidatorStatus` 的值是否已在这份清单里有对应位置——
   读 `:149-155` 是"取证阶段"的五态，与 `ValidatorStatus` 是两套枚举，**未逐项核对**。
9. **`observed_at` / `origin` 一族（台阶 2 的字段）是否受本台阶影响**：未核实，也没有理由受影响
   （本台阶不碰 `provenance/`）。列出来是为了让 after 侧差集**出现意外条目时不被当成噪声**。

---

## 7 附：本次跑过的命令与读数（可复核）

| 命令 | 读数 |
| --- | --- |
| `git rev-parse --short HEAD` | `6b3dd36`（`git status --porcelain` 有 2 个 docs 文件被改：`designs/控制面重构方案.md`、`15-control-plane-design/10-h4-field-diff.md`——**不是我改的**） |
| `.venv\Scripts\python.exe .tmp\step3b\probe_decisions.py --out .tmp\step3b\decisions-before.json` | sha256 `fb9a4269b6ed6711e7606d51fdd8e8dff485af9dbf78d1b435f40deaa67dff7a`，27288 B，`same_tree_rerun_identical True`，10 场景 |
| `.venv\Scripts\python.exe .tmp\step3b\json_field_diff.py --before …-before.json --after …-before.json` | `count 0`，**exit 0**（自检） |
| 同上，`--after …-mutated-control.json` | `count 8`，**exit 1**（负对照：decision/violations 长度/元素删除/新键） |
| `pytest -q --no-header tests/unit/test_decisions.py tests/contract/test_decision_protocol.py tests/unit/test_models.py tests/unit/test_engine.py tests/contract/test_validator_protocol.py tests/unit/test_validator_checkers.py tests/unit/test_validator_pending_implementation.py tests/unit/test_hook_violation_visibility.py` | **210 passed**（7.53s，1 warning：`.tmp/.pytest_cache` 写入被拒） |
| `pytest -q --no-header tests/integration/test_dsh_pre_evidence_hook.py tests/integration/test_validator_pipeline.py tests/unit/test_api_contract.py` | **82 passed**（29.25s） |
| `.venv\Scripts\python.exe docs/project/architecture/tech-detail/build_notebooks.py --check` | 10 章"产物与内容源一致，结构校验通过"，`代码单元执行: 全部通过`，**exit 0** |
| `grep -rn "requires_approval" policies/` | **0 匹配** |
| `glob tests/**/*pending*.py` | 只有 `tests/unit/test_validator_pending_implementation.py`（**没有** `tests/unit/test_evidence_pending.py`） |

**我没有做的事**（列出以免被读成做过）：没改任何 `src/` `tests/` `docs/` `AGENTS.md` `registry/` `validation/`
文件；没跑 `git add/commit/checkout/stash`；没跑 `tools/ci_local.py`；没设 `POLICY_UPDATE_SNAPSHOTS`；
没跑全量 pytest；没跑学习手册生成器。
