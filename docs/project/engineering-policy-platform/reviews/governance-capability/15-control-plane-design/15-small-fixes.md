# 15 · 台阶 3c 之前的小修：VERDICT 行核查、AGENTS 第 55 条版本轴、B4 正例

- **执行**：2026-09-29（本机）；控制面重构会话（**唯一写者**）。
- **树**：`C:\Users\ZNM\Downloads\Memory-rf` = 分支 `refactor/control-plane`；**前** = `466a75b`
  （本文件与代码在同一个新提交里落地，提交号见 §6）。
- **依据**：2026-09-29 裁定（**B4**：API 不加计数键、`API_SCHEMA_VERSION` 与
  `REQUEST_LOG_SCHEMA_VERSION` 都不动，只补正例测试）与 **AGENTS 第 55 条**（加键 / 改语义 = 按该协议
  自己的版本号递增）。
- **本文件是什么**：三件小修的**读数与理由**。**没有改任何判定路径**：`git diff` 里没有
  `src/policy/`、`src/validators/`、`src/policy_api/runtime.py`。

---

## 1 VERDICT 行核查（小修 a）

**问题**：台阶 3a（H1/H10 受控 reason）与 3b（pending 移出 `violations`）之后，N18 的判定行
（`[policy] VERDICT {…}`，Python 产出、JS 插件消费）**键或语义变没变**？变了就要按第 55 条把
`VERDICT_SCHEMA_VERSION` 1.0→1.1，并**两侧同批**改；没变就写下读数、**不升**。

### 1.1 仪器与口径

| 项 | 值 |
| --- | --- |
| 仪器 | `.tmp\verdict-check\probe_verdict.py`（sha256 `06E66FC31816B557AC65C68B662D66BBF1692B15D6C948E6A937EB5C3B3527BB`） |
| before 读数 | `.tmp\verdict-check\before.json`（sha256 `867F5A551CA382E0FEC46B5EE68173FEE32E74E669EA71D82CCEA069665D6CC5`） |
| after 读数 | `.tmp\verdict-check\after.json`（sha256 `CDB623F9B08EBCD472D54F27C7289D30901C471855540419E34C108563ABE57A`） |
| 字段差集 | `.tmp\verdict-check\verdict-field-diff.json`（sha256 `54F9844B9468E61CFCE0E150739BC5541778522C3336F4955286608172E65E43`，**count = 0**） |
| 差集工具 | `.tmp\step3b\json_field_diff.py`（台阶 3b 的原样复用，**本次未改一个字节**） |

- **前后两棵树**：before = `git archive 6fa800e` 解出的**基线树**（分支的开工点，
  `origin/feat/rules-and-os-platform` 的 tip），after = 当前树。**两棵树用同一份数据**
  （同一份 `policies/`、`registry/`、同一批夹具），只有 Hook 代码不同 —— 差集只可能来自代码。
- **口径**：11 个 `tests/fixtures/agent_events/dsh` 事件 fixture，各跑一次**生产入口**
  `python -m adapters.dsh.hooks`（真 stdin、过 `--hooks-config` 接线自检），外加 3 个专门造出来的
  判定行分支：`wiring_error`（hooks.json 不存在）、`startup_error`（配置读不了）、
  `evidence_unavailable`（声明并启用 pre_evidence，但提议内容重建不了）。共 **14 个用例**。
- **稳定性**：同一棵树上跑两遍，两遍逐字节相同（`same_tree_rerun_identical = true`）——
  判定行里没有墙钟字段。

### 1.2 读数（字段级）

| # | 字段路径 | before | after | 差 |
| --- | --- | --- | --- | --- |
| 1 | `cases[*].exit_code` | 14 个用例逐个取值 | **逐个相同** | 无 |
| 2 | `cases[*].verdict_lines`（原文） | 9 行判定行 | **逐字相同** | 无 |
| 3 | `cases[*].verdict_payloads`（解析后） | `{schema_version, reason_code, exit_code, hook_event?}` | **逐个相同** | 无 |
| 4 | `cases[*].verdict_key_sets` | 键集合 | **逐个相同** | 无 |
| 5 | 键的**并集**（全部用例） | `['exit_code', 'hook_event', 'reason_code', 'schema_version']` | **同一集合** | 无 |
| 6 | `hook_sha256` / `plugin_sha256` | `7a62b384…` / `a7be5bdb…` | `6680766d…` / `26aba823…` | **变了**（实现体量变了，见 1.4；这两个字段被差集工具按 `*sha256` 规则剔除，单列在此） |

**观察到的 reason_code 取值（14 个用例，两侧一致）**：`policy_block`、`context_error`（3 例）、
`permission_denied`、`startup_error`、`wiring_error`、`evidence_unavailable`。
判定行只在**阻断**时出现：`pre-tool-use-edit-allow` / `-write-allow` / `-read-not-governed` /
`post-tool-use-edit` 四个放行用例**一行都不写**（`verdict_line_count = 0`）。

### 1.3 关于 `warnings`：它不在判定行里

指令里那条"warnings 的键或语义变了没有"必须分开答，否则会把两件事混成一件：

| 事实 | 读数 |
| --- | --- |
| 判定行有没有 `warnings` 键 | **没有**。两个版本、全部 14 个用例的键并集都是那 4 个键，集合里没有 `warnings` |
| 插件读判定行的哪些键 | 只读 `schema_version`（精确等于 `'1.0'`，否则回落到"未知状态"）与 `reason_code`；解析段（31 行）两个版本**逐字相同** |
| `warnings` 到底是什么 | `hooks.py` 里的一个**局部变量**（HEAD `1242-1252`，基线 `1121-1130`）：把 `violations` 的 canonical id 拼成**给模型看的** stderr 正文（`[policy] ALLOWED WITH WARNINGS …`），不进判定行、不进审计记录的键集合 |
| 它的语义变了吗 | **变了**。台阶 3b 的 B1 追加了 `f"{finding.canonical_id}（待实现）"`（`warnings.extend`，HEAD `1250-1252`）——同一行里要能分开"真违规"与"待实现" |
| 那要不要升 `VERDICT_SCHEMA_VERSION` | **不要**。它不是判定行的键，也不是判定行的语义；它落在 D-1(b) 那一次提交里，而那次提交**已经**按第 55 条递增了**它所属的**协议轴（决策 `SCHEMA_VERSION` 1.0→1.1、审计 `AUDIT_SCHEMA_VERSION` 1.1→1.2）。第 55 条是"按**该协议自己的**版本号"，不是"任何文本变了都动 VERDICT" |

**另一件必须写下来的事**：`allow_with_warnings` 走的路径是 `exit_code = EXIT_ALLOW`，
`main()` 在写判定行**之前**就返回了（HEAD `2174-2183`）。也就是说即使 warnings 有机器可读的形态，
判定行这条通道也**结构上**不承载它 —— "放行 + 有警告"要靠审计记录与决策载荷读，不能靠判定行读。

### 1.4 代码级读数（补端到端覆盖不到的那部分）

端到端只跑得到 14 个用例；"调用点与取值域"要另外读，两者合起来才是完整答案：

| 项 | before | after |
| --- | --- | --- |
| `verdict_line(...)` 调用点 | 4 处：`wiring_error` / `startup_error` / `startup_error+hook_event` / `outcome.reason_code+hook_event` | **同一组 4 处，逐字相同** |
| `hooks.py` 里字面 `reason_code="…"` 的取值集合 | 15 个 | **同一集合（15 个）**；新增的两处 `reason_code="startup_error"` 是`origin_from_failure` 的入参（台阶 2 的归因），不是判定行调用点 |
| `VERDICT_SCHEMA_VERSION` / `VERDICT_PREFIX` | `"1.0"` / `"[policy] VERDICT "` | **一字不变**（Python `hooks.py:136-137`；JS `policy-hook.plugin.mjs:123-124`） |
| 冻结判定行形状的契约用例 | `tests/contract/test_policy_hook_chain.py::test_a_blocked_hook_call_writes_one_machine_readable_verdict` 断言**整份载荷恰好 4 个键** | 该用例在门禁里通过；形状未变 |

### 1.5 结论

**判定行的键集合、取值域与语义在 `6fa800e → 466a75b` 之间没有变化；`VERDICT_SCHEMA_VERSION` 保持
`"1.0"`，本次不升版。** 依据是上面三组读数（端到端 14 例 0 差集 + 调用点 / 取值域逐字相同 +
两侧语言各自的解析段逐字相同），不是"我觉得没改"。

### 1.6 这条检查**覆盖不到**什么（AGENTS 第 45 条）

- **未观察到**的阻断原因码：`enforcement_unavailable`、`enforcement_error`、`tool_not_registered`、
  `post_error`、`post_repair_required`、`allow_delegated` 等 —— 它们的"没变"只由 **1.4 的代码级读数**
  支撑（调用点与取值域），不由端到端用例支撑。
- **未核实**：真实 dsh 会话里"退出码 2 被归一化成 1"的那条路径（`src/adapters/dsh/README.md` §2.3）。
  本次探针读的是 **Hook 进程自己的退出码**（`subprocess.returncode`），**没有**经过 dsh 的归一化；
  跨侧分类器那一段由 `tests/contract/test_policy_hook_chain.py` 的真插件用例覆盖，不在本次读数里。
- **未核实**：判定行的消费方不止本仓库的插件（例如用户自己的桥）。唯一能证明"两侧一致"的是本仓库里
  这一对 Python/JS 与它们的契约用例。

---

## 2 AGENTS 第 55 条：版本轴清单补全（小修 b）

**改了什么**：把原来只列 4 条的"本仓库现有的版本轴"补成一张**分组清单**，并显式写成
**"列举，不是穷尽"**（判据是"这个载荷的键集合或语义变没变"，不是这张表在不在）。

| 组 | 新增进清单的轴 |
| --- | --- |
| 多 Agent 协议 | `CANONICAL_EVENT_SCHEMA_VERSION`、`ADAPTER_MANIFEST_SCHEMA_VERSION`、`ADAPTER_CONFIG_SCHEMA_VERSION`、`APPROVED_SCHEMA_VERSION`、`AGENT_RUNTIME_SCHEMA_VERSION`、`WIRING_SCHEMA_VERSION`、`CONFORMANCE_SCHEMA_VERSION`、`HOST_VERSION_SCHEMA_VERSION`、`HOST_VERSION_RECORD_SCHEMA_VERSION` |
| dsh Hook | `VERDICT_SCHEMA_VERSION`（**跨语言**：Python 与 `policy-hook.plugin.mjs` 同批改） |
| 受控执行与编排 | `ENFORCEMENT_SCHEMA_VERSION`、`REGISTRY_SCHEMA_VERSION`、`APPROVED_SCHEMA_VERSION`（enforcement）、`LEDGER_SCHEMA_VERSION`、`APPROVAL_SCHEMA_VERSION`、`CHECKPOINT_SCHEMA_VERSION` |
| API 与服务 | `API_CONFIG_SCHEMA_VERSION`、`IDEMPOTENCY_SCHEMA_VERSION`、`SNAPSHOT_SCHEMA_VERSION` |
| 检索与针脚 | `INDEX_SCHEMA_VERSION`、`CHUNKER_VERSION`、`RECEIPT_SCHEMA_VERSION`、`provenance.wiring_scope.SCHEMA_VERSION` |

**同时写明"不是轴的同名字段"**（防止后来者照表乱改）：`MIN_LANGGRAPH_VERSION` 是依赖下界；
`adapters/<id>/manifest.yaml` 的 `agent_version` / `protocol_version` 是产品与协议**声明**
（改了要重新审核 + 重录宿主观测，见第 54 条），不是载荷版本。

**为什么选"补全"而不是只把措辞改成"包括"**：清单里的每一条都有常量、有位置、有消费者，
逐条列出来比一句"包括"更能防止"表里没有 = 不用升"这种读法；而"列举，不是穷尽"这一句同时保留了
"包括"的开放性。**未核实**：清单是否穷尽 —— 判据是"仓库里所有**带版本号的载荷**"，本次按
`grep -rn "_SCHEMA_VERSION\s*=" src/` 的结果逐条登记（30 个常量），但**没有**逐条验证
每个常量都真的被消费方按版本号拒收。

---

## 3 B4 正例：`/v1/validation/evaluate` 的 pending（小修 c）

**裁定回顾**：B4 不加计数键（`API_SCHEMA_VERSION` / `REQUEST_LOG_SCHEMA_VERSION` 都不动），
pending 的可见性由**同一个响应体里的决策载荷**承接；**只补正例测试**。

**补的用例**：`tests/integration/test_api_http.py::test_validate_reports_a_pending_finding_through_the_decision_channel`

- 夹具形状：租户项目里先写 `tests/test_order_service.py`（`from shop.order_service import cancel_order`，
  这个名字还没落地）→ 真流水线 → `tool.pytest` 收集期失败 → 判定是「待实现」；
- 请求：`POST /v1/validation/evaluate`，`target=src/shop/order_service.py`、
  `changed=[src/shop/order_service.py]`、`context.operation=edit`（TESTING-001/002 的 scope 要求），
  规则集 = 租户自带的 ARCH-001 + `policies/testing/`（经 `extra_rules` 复制进租户边界内）；
- 断言（**判据逐条**）：

| # | 断言 | 读数 |
| --- | --- | --- |
| 1 | `summary.violations == len(decision["violations"]) == 0` | 通过 |
| 2 | `decision["pending_findings"]` 非空，且 `rule_id == TESTING-002` | 通过 |
| 3 | `decision["pending_findings"][0].evidence.value == "shop.order_service:cancel_order"` | 通过（说得出"因哪个项目内缺失的目标"） |
| 4 | `decision["decision"] == "allow_with_warnings"`，且 `summary.decision` 同值 | 通过 |
| 5 | 报告侧 `pending_implementation` 非空、`failing_tests` **不在** `served_checkers`、`blockers == []` | 通过 |
| 6 | 请求级 JSONL 行 `decision == "allow_with_warnings"`、`violations == 0`、`route == "validate"` | 通过 |

第 6 条是**顺带关掉的另一条覆盖缺口**：14 号 §5.2 登记过"本轮**没有**任何用例驱动出一条
`decision=allow_with_warnings` 且 `violations=0` 的 API 日志行"。

**这条用例不覆盖什么**：

- 它**不**证明"pending 不阻断"在所有形状下都成立（只证了这一种收集失败的形状）；
  反例（第三方包缺失 / 语法错误 / conftest 出错 / 断言失败）的边界由
  `tests/integration/test_validator_pipeline.py` 与 `tests/unit/test_validator_checkers.py` 覆盖。
- 它**不**证明 API 层对 pending 有任何特殊处理 —— 恰恰相反，它的价值在于证明**没有**：
  判定仍由 `policy.engine.evaluate` 一条路径给出，API 只是把同一份载荷传出去。
- 它**不**覆盖 `/v1/policy/evaluate`：那条路由结构上不产生 pending（没有证据），14 号 §5.2 的结论仍然成立。

---

## 4 复现命令（按顺序）

```powershell
# 1a：before 侧（基线树）
git archive -o .tmp/verdict-check/before.tar 6fa800e
tar -xf .tmp/verdict-check/before.tar -C .tmp/verdict-check/before
.venv\Scripts\python.exe .tmp\verdict-check\probe_verdict.py --tree .tmp/verdict-check/before --out .tmp/verdict-check/before.json

# 1a：after 侧（当前树）
.venv\Scripts\python.exe .tmp\verdict-check\probe_verdict.py --tree . --out .tmp/verdict-check/after.json

# 1a：字段级差集（自检必须 count=0 且 exit 0）
.venv\Scripts\python.exe .tmp\verdict-check\prepare_diffable.py
.venv\Scripts\python.exe .tmp\step3b\json_field_diff.py --before .tmp/verdict-check/before-diffable.json --after .tmp/verdict-check/after-diffable.json --out .tmp/verdict-check/verdict-field-diff.json

# 1c：B4 正例
.venv\Scripts\python.exe -m pytest tests/integration/test_api_http.py -k pending -q
```

---

## 5 未做 / 未核实（逐条写下来）

1. **未升 `VERDICT_SCHEMA_VERSION`**：结论见 §1.5；如果评审认为 `warnings` 的文本变化也必须体现在
   判定行（例如新增一个 `warnings` 键），那是**一次协议变更**：Python + JS 同批改、版本升 1.1、
   并把插件侧"版本不认识 → 未知状态"的用例重跑一遍 —— 请评审裁定，本次**没有**自行扩大爆炸半径。
2. **未核实**：§1.6 列的未观察原因码在真实会话里的行为（只有代码级读数）。
3. **未核实**：§2 的版本轴清单是否穷尽（只保证"grep 到的常量都登记了"）。
4. **本轮没有跑 `tools/cleanup.py`**（纪律要求），`.tmp/verdict-check/` 与 `.tmp/step3b/` 的产物
   保留在树上供评审复核。
5. **本轮没有 push**、没有用 `--no-verify`、没有强推、没有用 `git add -f`；
   改动**只用 `write` / `edit` 落树**，提交按路径暂存。

---

## 6 本次改动的文件与哈希

| 文件 | 处置 |
| --- | --- |
| `AGENTS.md`（第 55 条） | 补全版本轴清单 + "列举不是穷尽" + "不是轴的同名字段" |
| `tests/integration/test_api_http.py` | 新增 `test_validate_reports_a_pending_finding_through_the_decision_channel` |
| 本文件 | 新归档 |
