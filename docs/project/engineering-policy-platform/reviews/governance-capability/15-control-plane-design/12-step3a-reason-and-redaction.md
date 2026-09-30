# 台阶 3a · H1/H10 受控 reason 与归因路径脱敏（实施记录）

> 写于 2026-09-29，分支 `refactor/control-plane`。实施提交 `73d7fbe`（前置文档提交 `3d86ad2` / `07b726f`）。
> 使用者裁定（2026-09-29，已写进方案 §10 处置列）：绝对路径**不开例外**，按 AGENTS 第 16 条脱敏；
> `observation.result` 进审计与 ORIGIN 行之前先过 `sanitize`；预算上限 = 原估算 × 2.5、实测超 1.5 倍即停下复核。

## 0. 环境自检（开工前）

| 项 | 读数 |
| --- | --- |
| 会话工作区根 | `C:\Users\ZNM\Downloads\Memory-rf`（= 会话 cwd；`pwsh` 的 `$PWD` 与 `[Environment]::CurrentDirectory` 都是它） |
| 它是不是 Memory-rf | **是**（`git rev-parse --show-toplevel` 同值；分支 `refactor/control-plane` @ `6b3dd36`） |
| `write` / `edit` 能否写本树 | **能**：`.tmp/fs-probe/write-edit-probe.txt` 建 → 改 → 读回 `alpha=2`（该文件是上一轮留下的现场，本轮逐字读回同一内容）；本轮全部落树改动只用 `write` / `edit` |
| 工作区之外的对照 | `Memory\.tmp\fs-probe-outside.txt` **不存在**（该轮被拒的读数没有留下产物，见「未核实」第 1 条） |

## 1. 提交

| # | 提交 | 内容 |
| --- | --- | --- |
| 1a | `3d86ad2` | `docs(reviews)`：15 轮 10 号 §9.2（Q7 矛盾观测定位为探针写法） |
| 1b | `07b726f` | `docs(designs)`：方案附录 C W6/W7、§11、§7.1，并写入 2026-09-29 的三条裁定（§10 处置列 + §3.6 两个补记小节） |
| 2 | `73d7fbe` | `feat(control-plane)`：**本台阶 3a**（H1/H10 受控 reason + 归因路径脱敏） |

## 2. R-d：改前 vs 改后的**字段级**差集

口径：`.tmp/rd-diff-r15/rd_emit.py` 在**固定契约**上 emit 判定载荷（4 个决策快照用例 +
1 个审批门禁用例 + 1 个 `pending_implementation` 用例），`rd_diff.py` 递归逐字段比对，
剔除 `timestamp` / `recorded_at` / `elapsed_ms` 与摘要类字段。

**读数：`{"differences": [], "count": 0}`**——6 个用例、改前改后**逐字段相等**。

| 通道 | 改前 | 改后 | 差集 |
| --- | --- | --- | --- |
| **决策载荷**（`policy.models.ValidationResult.to_decision_dict`） | 10 键 | 10 键 | **0 条**（含 `violations` 内容逐字段相等） |
| `SCHEMA_VERSION` / `POLICY_VERSION` | `1.0` / `phase-1` | `1.0` / `phase-1` | **不变** |
| **审计记录**（`hooks.AuditLedger`） | `AUDIT_SCHEMA_VERSION = 1.0` | `1.1` | 新增键 `decision_reason`（只在 block 且能归类时写；allow 与说不出来都不写） |
| **编排状态**（`ValidationSummary`） | 9 键 | 10 键 | 新增 `reason_code`（派生 + 自洽校验） |
| **编排状态**（`ViolationRef`） | 6 键 | 8 键 | 新增 `evidence_kind` / `evidence_value` |
| `STATE_SCHEMA_VERSION` | `1.0` | `1.1` | 递增（旧 checkpoint 显式拒绝恢复） |

三条读数（`.tmp/rd-diff-r15/probe_channels.py` 原文）：`audit decision_reason(approval) = approval_required`；
`audit decision_reason(policy block) = policy_violation`；`reason_code` 与发现不一致时构造即失败
（`ValidationSummary(..., required_action=approval, reason_code=policy_violation)` → ValidationError）。

### 2.1 受影响 fixture 清单

| fixture / 断言 | file:line | 现在断言什么 | 本次是否要改 |
| --- | --- | --- | --- |
| 四份决策快照 | `tests/fixtures/decisions/{allow,warning,block,approval}.json` | 决策载荷逐字段 | **不改**（差集 0 条；`approval.json` 的 `block + violations: []` 正是 H1 的合法形态） |
| 审计协议字面量 | `tests/unit/test_hook_skip_visibility.py:309` | `AUDIT_SCHEMA_VERSION == 1.0` | **改**：显式改成 `1.1`（协议自己的规则） |
| 编排状态协议字面量 | `tests/contract/test_orchestration_engine.py:397,406` | `STATE_SCHEMA_VERSION == 1.0` | **改**：显式改成 `1.1` |
| 归因载荷形状 | `tests/integration/test_dsh_origin_attribution.py`（新增 1 条） | —— | **新增**：ORIGIN 行里绝对路径两种写法都不许存活 |
| 归因正则两族 | `tests/integration/test_dsh_origin_attribution.py`（新增 1 条 helper 驱动） | —— | **新增**：全角括号 / 含空格两族 |
| 审计归类 | `tests/unit/test_hook_violation_visibility.py`（新增 1 条） | —— | **新增**：`decision_reason` 的受控归类 |
| 修复节点动作表 | `tests/unit/test_orchestration_repair_reason.py`（新增文件，5 条） | —— | **新增**：R1/R2/R3 + 归类派生 |

**为什么现有套件一条都不会因「通道边界脱敏」而红**：全仓 grep（violations / enforcement_detail /
wiring / pre_evidence 都有 `assert str(x) not in dumped` 这类「缺席断言」）**唯独 `origin` 这一栏一条都没有**。
也就是说：这个缺陷存在时套件是全绿的——它本身就是一条 AGENTS 第 45 条的缺陷，处置是**新增**用例而不是改用例。

## 3. 改了什么（按文件）

| 文件 | 改动 | 行数（`len(text.splitlines())`） |
| --- | --- | --- |
| `src/adapters/dsh/hooks.py` | `_ABS_PATH_BOUNDARY` 补全角标点；新增 `_ABS_PATH_RELAXED`（含空格路径）；`sanitize()` 两遍；`origin_line()` 过 `_sanitized`；`_fail()` 的 origin 过 `_sanitized`；新增 `decision_reason()`（受控归类）；审计版本 1.1 | +86 / −5 |
| `src/orchestration/models.py` | 新增受控闭集与 `decision_reason()`；`ViolationRef` 增证据通道；`ValidationSummary` 增 `reason_code` + 派生/自洽校验 | +108 / −3 |
| `src/orchestration/client.py` | 承接 `models` 的归类函数（再导出）；`_violations_from` 搬证据通道；两个 `summary()` 填 `reason_code` | +38 / −2 |
| `src/orchestration/nodes.py` | `repair()` 先读受控 reason；新增 `_stop_unrepairable()` | +79 / −2 |
| `tests/unit/test_orchestration_repair_reason.py` | 新增（5 条） | +149 |
| 其余 4 个测试文件 | 新增 3 条 + 2 处显式版本字面量 | 见 §2.1 |

**台阶 3 的预算**（裁定：上限 = 原估算 × 2.5）：src 上限 **2.0k** / tests 上限 **2.25k**。
本台阶实测 **src +311**、**tests +149**（新增行数口径；含被替换的旧行则为 +311/−12 与 +149/−3）。
与原估上限之比：src **0.16×**、tests **0.07×**——**远在 1.5 倍复核线之内**，不需要停下复核。

## 4. 状态映射表（方案 §3.3 的台阶 3 验收项）

**说明**：本表**只列已有状态**，不发明取值（D-1 裁定明确「本次不新增 `not_evaluated` 状态值」）。
「本次处置」列写的是**本台阶**对它做了什么；`—` 表示本台阶不动它。

| # | 状态族 | 定义处 | 取值 | 本次处置 |
| --- | --- | --- | --- | --- |
| 1 | `Decision` | `policy/models.py:314` | `allow` / `allow_with_warnings` / `block` | —（决策协议不动） |
| 2 | `Severity` | `policy/models.py:222` | `info` / `warning` / `error` / `critical` | — |
| 3 | `RequiredAction` | `policy/models.py:322` | `approval` | **参与归类**：`approval` → `approval_required` |
| 4 | `ValidatorStatus` | `policy/evidence.py:67` | 11 值（含 `pending_implementation`） | —（属台阶 3b / 3c） |
| 5 | `PRE_EVIDENCE_STATUSES` | `adapters/dsh/hooks.py:149` | 5 值 | — |
| 6 | `ValidatorStatus` 的两个「都不是」 | `policy/evidence.py:97,102` | `not_selected` / `pending_implementation` | —（3b 处理 `pending`） |
| 7 | `CheckerJudgement` outcome | `validators/pipeline.py:94` | `empty` / `unanalyzed` | — |
| 8 | `language_coverage.status` | `validators/pipeline.py:106` | 3 值 | — |
| 9 | `check_volume.skipped_by_reason` | `policy/check.py:431` | 3 值 | — |
| 10 | `ReasonCode`（Phase 4） | `enforcement/models.py:308` | 36 值（含 `approval_required`） | —（编排层的受控 reason 是**另一套**，命名刻意区分） |
| 11 | `CheckStatus` / `ExecutionStatus` / `PostStatus` / `FinalOutcome` | `enforcement/models.py:267-292` | 各自封闭 | — |
| 12 | `REASON_CODES`（Agent 适配层） | `adapters/runtime.py:78` | 23 文案键 | — |
| 13 | `StageStatus` / `RunStatus` / `FailureCode` | `orchestration/models.py:132+`、`errors.py:127` | 5 / 5 / 30 值 | **接线**：`APPROVAL_MISSING → NEEDS_HUMAN`、`EVIDENCE_UNAVAILABLE → BLOCKED` 由 `repair()` 真正走到 |
| 14 | `AttemptOutcome` | `enforcement/verdict.py:45` | 5 值 | — |
| 15 | `RetrievalStatus` / `UnavailableReason` / `ContextStatus` | `retrieval/models.py:177` | 3 / 5 / 2 值 | — |
| 16 | `ViolationRef`（编排层） | `orchestration/models.py:230` | 6 键 → **8 键** | **新增证据通道** `evidence_kind` / `evidence_value` |
| 17 | `ValidationSummary.reason_code`（本轮新增） | `orchestration/models.py:246` | `approval_required` / `policy_violation` / `evidence_unavailable` / `None` | **新增**（受控闭集 + 自洽校验） |
| 18 | 审计 `decision_reason`（本轮新增） | `adapters/dsh/hooks.py`（`AUDIT_SCHEMA_VERSION = 1.1`） | 同 17 值域 | **新增**（allow 与说不出来都不写这个键） |

**这张表能读出的三件事**（本台阶的实际交付）：

1. 「没判 / 没查」在平台里仍有**六套**表示（#4 的两个「都不是」、#7、#8、#9，加上 `_fail()` 记录里没有
   `violations` 键、`ViolationRef` 丢证据）；本台阶只补了其中两个洞（#16 的证据通道、#17/#18 的受控 reason），
   **没有**把它们合并成一维——合并需要状态代数，属台阶 3 的另一半，不在本次授权内。
2. `block + violations=[]` 在判定层**只有一种合法形态**：`required_action=approval`。两种证法：
   （a）`ValidationResult` 的自洽校验拒绝「block 且无 violations 无 required_action」的构造；
   （b）穷举 `Decision.BLOCK` 的构造点，判定层只有 `expected_decision` 一处（`engine.py:161-167`）。
   所以 `repair()` 的「说不出理由就抛契约错误」是**可达但今天构造不出来**的兜底，不是死代码。
3. `REASON_CODES`（编排层，#17）与 `ReasonCode`（Phase 4，#10）**是两套**且刻意不互相导入：
   `src/policy` 与 `src/orchestration` 对 `enforcement` 都零依赖（核心层约束），
   合并它们要先决定谁是真源，属台阶 5 的事实表。

## 5. 本机门禁

| 项 | 读数 |
| --- | --- |
| 命令 | `python tools/ci_local.py --full --python .venv/Scripts/python.exe`（cwd = 仓库根） |
| 步骤 | `改动文件 776 个；执行 33 步（本机跳过 11 步，登记豁免 2 步）`；**33/33 `rc=0`** |
| 结论行 | `本机检查全部通过（33 步）`；进程 exit **0** |
| 墙钟 | 表内**合计 8m 01.3s**；最贵 pytest 5m 07.5s（63.9%）、Learning notebooks 1m 02.7s、Orchestration closed loop 1m 01.7s |
| 测试 | `1942 passed, 1 skipped, 3 warnings in 305.38s`（台阶 2 门禁原文是 `1934 passed`：**新增 8 条**） |
| 证据 | `.tmp/ci-full-step3a-run2.log`（168714 B，sha256[:16] `E4CD484BA6134D3F`）；`.tmp/artifacts/tests-all-report.xml`（259463 B，`BF118B1A7F9F8C5B`）、`phase-8-evidence.json`（47941 B，`39F73B18EF043135`） |

**第一次跑是红的，红因在文本规范**（不是本台阶的源码改动）：`Text conventions` `rc=1`，报
`12-step3a-reason-and-redaction.md: 文件未以单个换行符结尾`（新建文档时漏了结尾换行）。
补上后复跑才有上表的 33/33——**把这次红记在这里**：门禁第一次挡住的是本台阶新增文档的格式问题。
（第一次的读数：`.tmp/ci-full-step3a.log`，失败 1 处 = 文本规范 32/33。）

**这一步证明什么**：原文命令在本树跑绿，33 步里包含本台阶新增/改动的 6 个测试文件。
**不证明**：CI（Linux / UTF-8）侧同样绿；也不证明封条（台阶 0 的 R-e）接进了门禁——**它没有**。

## 6. 自证会红（AGENTS 第 45 条）

| # | 检查 | 修复前 | 修复后 |
| --- | --- | --- | --- |
| 1 | `sanitize` 全角括号（Windows 路径） | 原样漏过（全角括号不在边界类里） | `点名（<abs>）` |
| 2 | `sanitize` 全角括号（POSIX 路径） | 原样漏过 | `点名（<abs>）` |
| 3 | `sanitize` 含空格路径 | `<abs> Files\nodejs\node.exe ENOENT`（半截路径） | `spawn <abs>` |
| 4 | ORIGIN 行 | `object.source` / `observation.result` 带本机绝对路径（真实 CLI，exit 2） | 两种写法都不存活；`object.value` 仍是末段名、`fix` 仍非空 |
| 5 | `repair()`（审批门禁） | 抛 `NodeContractError` → 终态 **FAILED** | `NEEDS_HUMAN`，且不产生任何 Change |

读数 1–3 的对照（`.tmp/rd-diff-r15/probe_mutation2.py`，**同一组样本**分别喂改动前的 sanitize 与现实现）：

```text
fullwidth-paren    OLD=点名（C:\Users\zoe\.ssh\config.yaml）      NEW=点名（<abs>）
spaced-path        OLD=spawn <abs> Files\nodejs\node.exe ENOENT     NEW=spawn <abs>
posix-fullwidth    OLD=点名（/home/zoe/secret/config.yaml）          NEW=点名（<abs>）
```

读数 4 的写法（**不新造正则**，用具体串做缺席断言）：`leaked_paths(text, *absolute)` 断言两种写法都不在文本里——
宽泛正则的边界一放宽就会把仓库相对路径判成绝对路径，那是本仓库反复踩过的「仪器假阳」。

## 7. 口径与取舍（写清代价）

1. **含空格路径的脱敏是保守的**：`spawn C:\Program Files\nodejs\node.exe ENOENT` → `spawn <abs>`，
   同一行里路径之后的诊断词**一起被抹掉**。「哪些空格属于路径」在没有引号的语言里不可判，
   取舍按失败关闭写：**宁可多抹，也不留半截路径**（半截路径正是要修的缺陷）。这个代价不假装没有。
2. **两个 profile 没有合并**：`hooks.sanitize`（面向模型 / 诊断）与 `enforcement.audit.redact_text`（审计）
   在占位名、正则、密钥组数、控制字符、长度上限、截断标记上共 6 处不同；库内先例（`hooks.py:1186-1193`）
   已经判过「别拿面向模型的 4000 截断去洗审计明细」。本台阶的做法是**共用一条不变量 + 两个 profile**：
   两者都必须让绝对路径不存活（各自的用例钉住），而**不**合并成一个函数。
3. **JS 侧不动**：全仓的 ORIGIN 行产出者只有 Python 一处；JS 的 `buildOrigin` 是纯函数（`plugin.mjs:248`），
   脱敏需要 `project_root` 语境而 JS 没有——「先脱敏再进载荷」会破坏两侧的纯函数对称性，故不改载荷层。
4. **决策协议一个字不动**：受控 reason 全部是**派生**的。这是本次裁定「递增记录协议版本」在 3a 的落法：
   审计协议与状态协议各按自己的规则递增，**决策协议留给 3b**。

## 8. 不证明什么 / 未核实

1. **未核实**：工作区外被拒的那条读数（`Memory\.tmp\fs-probe-outside.txt`）**没有留下产物**——
   文件今天不存在，因此「当时确实被拒」只有文档里的自述，没有可复核的现场。
2. **未核实**：`_read_text`（`provenance/origin_runtime.py:54-66`）的 `OSError` 带路径是用 monkeypatch 造出来的；
   真机上哪种条件触发它，本台阶没有真机读数。
3. **未核实**：JS 侧真机 `node.exe` 绝对路径串来自文档自述（`11-step2 §7.5:200`），无真机 dsh 会话原文。
4. **不证明**「归因一定对」：本台阶只保证归因**不把绝对路径带出去**，核验判据本身的覆盖边界未变。
5. **不证明** H10 的完整语义：`.tmp/round-15/design/C/C-position.md`（H10 的权威定义处）已不在树里，
   本台阶的读法是从被点名的代码路径反推的（`blocker_violation` / `_violations_from` 的丢字段）。
6. **不证明**门禁会拦住这一类缺陷：新增用例只覆盖 ORIGIN 行、审计归类与 `repair()` 的动作表；
   `tools/ci_local.py` 的 33 步里**没有**任何一步跑「origin 里不许有绝对路径」的检查——它由测试守，不由门禁守。
7. **未核实**：`evidence_unavailable` 在真实 `pre_evidence` 失败会话里的 `object.value` 形态（只复刻了 `_origin_for` 的同组实参）。
