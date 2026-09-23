# Phase 4 受控执行：对象与关系

面向人的“这一阶段到底有什么”。讲三件事：**要解决什么问题**、**有哪些对象**、**它们之间是什么关系**。
想看代码跑起来什么样，读同目录的 `walkthrough.ipynb`；想知道为什么这么设计，读
`docs/project/engineering-policy-platform/phases/phase-4-tool-enforcement.md`。

## 1. 这一阶段解决什么问题

Phase 0-3 之后，系统已经能在工具执行**之前**说“不行”（策略引擎），也能告诉 Agent“该怎么做”（检索）。
但“说不行”只是一句话，真正改变世界的是工具调用本身。Phase 4 把这条链路补齐，回答五个问题：

    凭什么执行？→ 凭什么执行这一次特定的调用？
    执行了没有？→ 是执行了一次、零次，还是根本没执行？
    执行之后谁来验证？→ 谁证明“结果和请求对得上”？
    出了问题能不能撤销？→ 能力不足时怎么如实说？
    事后怎么解释？→ 一条 trace 能不能被重新读出来？

一句话边界：**授权不是一个字，而是一条与工具、参数、主体、schema 和有效期逐位绑定的凭据；
执行器只认凭据，也只执行一次。**

## 2. 对象清单

### 2.1 数据侧：Tool Registry（`registry/tool-registry.yaml`）

| 对象 | 是什么 | 关键字段 |
| --- | --- | --- |
| ToolSpec | 一条工具的**已审核描述** | `id`、`agent`、`tool_name`、`schema_version`、`risk`、`effect`、`driver`、`parameters`、`required_permissions`、`approval`、`post_checks`、`timeout_ms`、`rollback`、`rate_limit`、`allowed_commands`、`command_param`、`shell`、`audit_failure` |
| ParamSpec | 一个参数的允许形态 | `name`、`type`、`required`、`max_chars`、`max_items`、`pattern`、`enum`、`path_scope`、`escalating_values`、`requires_permission`、`secret` |
| RateLimit | 限流与熔断的门槛 | `max_calls`、`window_seconds`、`max_failures`、`breaker_seconds` |
| ToolRegistry | 一次加载的结果（不可变） | `tools`、`permissions`、`roles`、`approval_role`、`default_timeout_ms`、`grant_ttl_seconds`、`max_grant_ttl_seconds`、`approved` |
| 已审核哈希清单 | 上一次人工复核的结果 | `registry_digest`、`reviewed_by`、`approved_at`、`tools[].schema_hash` |

风险级别（`RiskLevel`）决定门禁强度：`read_only` / `reversible_write` 由 Agent 侧显式降级或走 pre-check；
`destructive_write` / `external_side_effect` / `privileged_execution` 属于高风险，`approval` 必须是 `required`。

### 2.2 请求与授权（一次调用的前半程）

| 对象 | 是什么 | 关键字段 |
| --- | --- | --- |
| ParamValue | 规范化后的单个参数值 | `name`、`type`、`value`、`chars`、`digest`、`secret` |
| ActionRequest | 不可变的动作请求 | `action_id`、`request_id`、`trace_id`、`agent`、`tool_id`、`tool_schema_hash`、`risk`、`effect`、`driver`、`params`、`param_digest`、`subject`、`roles`、`permissions`、`context_digest`、`workspace`、`created_at`、`expires_at`、`action_hash` |
| CheckResult | 一项检查的结论 | `check`、`status`、`reason_code`、`detail` |
| AuthorizationGrant | 短时效、单次使用的允许凭据 | `grant_id`、`action_hash`、`action_id`、`tool_id`、`tool_schema_hash`、`subject`、`permissions`、`issued_at`、`expires_at`、`single_use`、`nonce` |
| ApprovalRecord | 人工审批（结构化记录） | `approval_id`、`action_hash`、`action_id`、`tool_id`、`subject`、`granted_by`、`granted_by_roles`、`granted_at`、`expires_at` |
| PreDecision | 执行前决策 | `decision`、`reason_code`、`checks`、`grant`、`required_action`、`policy`、`dry_run`、`evaluated_at`、`expires_at` |
| PolicySummary | Phase 1 决策的只读摘要 | `decision`、`request_id`、`matched_rules`、`violations`、`payload` |

### 2.3 执行与证据（一次调用的后半程）

| 对象 | 是什么 | 关键字段 |
| --- | --- | --- |
| 驱动 | 真正动文件 / 起进程的一层 | `FileDriver`、`ProcessDriver`、`ShellCommandDriver`、`DelegatingDriver` |
| DriverResult | 驱动的一次结果 | `status`、`exit_code`、`timed_out`、`stdout`、`stderr`、`structured`、`snapshot` |
| FileSnapshot | 执行前快照（回滚的唯一依据） | `path`、`existed`、`content`、`mode` |
| ExecutionRecord | 一次执行的完整记录 | `status`、`reason_code`、`driver`、`exit_code`、`timed_out`、`duration_ms`、`stdout_digest`、`stderr_digest`、`output_excerpt`、`grant_id`、`started_at`、`finished_at` |
| FileBaseline | 执行前基线（delegated 工具靠它对比） | `path`、`existed`、`sha256`、`bytes`、`captured_at` |
| FileEffect | 单个文件的执行前后证据 | `sha256_before`、`sha256_after`、`bytes_before`、`bytes_after`、`changed`、`diff_digest`、`diff_excerpt`、`truncated` |
| ProcessEffect | 进程类证据 | `exit_code`、`timed_out`、`stdout_digest`、`stderr_digest`、`output_excerpt` |
| ValidatorOutcome | 一条验证器结论 | `validator`、`status`、`detail`、`evidence_digest` |
| PostEvidence | 执行后的全部证据 | `files`、`process`、`validators`、`untrusted_result_digest` |
| RollbackOutcome | 回滚结论 | `mode`、`status`（applied / skipped / unsupported / failed）、`restored` |
| PostDecision | 事后验证决策 | `status`、`reason_code`、`checks`、`rollback` |
| FinalDecision | 链路终态 | `outcome`、`reason_code`、`pre_decision`、`execution_status`、`post_status` |

### 2.4 台账与审计（跨进程的记忆）

| 对象 | 是什么 | 关键字段 |
| --- | --- | --- |
| EnforcementLedger | 幂等 / 授权单次使用 / 限流熔断的持久状态 | 记录类型 `claim`、`grant`、`grant_used`、`pre_decision`、`execution`、`approval_used` |
| LedgerClaim | 一次认领的结果 | `claimed`、`claim_id`、`reason`（`action_replay` / `action_id_reuse`） |
| AuditRecord | 审计链上的一条记录 | `sequence`、`stage`、`trace_id`、`action_id`、`request_id`、`tool_id`、`recorded_at`、`payload`、`prev_digest`、`digest` |
| AuditChain | 摘要链的纯计算 | `next_record`、`verify` |
| FileAuditSink | 追加写 JSONL 的审计端口 | `append`、`chain_records`、`verify`、`foreign_records`、`describe` |
| TraceReport / TraceEntry | 一条 trace 的重放结果 | `records`、`issues`、`entries`、`has_final` |

## 3. 对象之间的关系

### 3.1 主链路

    registry/tool-registry.yaml ──load_registry──▶ ToolRegistry ──approval_reason──▶ 可用 / 不可用
           │                                            │  permissions_for(roles)
           ▼                                            ▼
      工具身份 + 参数表 ───────────▶ build_action_request ──▶ ActionRequest（action_hash）
                                                                 │
                                             pre_execute（13 项检查）│
                                       ┌─────────────────────────┴──────────────────┐
                                       ▼ block                                      ▼ allow
                             PreDecision（无 grant）                    PreDecision + AuthorizationGrant
                                                                                 │
                                                             ControlledExecutor.execute
                                                   （校验绑定 → consume_grant → 驱动执行一次）
                                                                                 │
                                       ┌─────────────────────────────────────────┴──────────┐
                                       ▼ refused / failed                                  ▼ executed
                                 ExecutionRecord                              collect_evidence → validate
                                                                                        │
                                                                         PostDecision（+ RollbackOutcome）
                                                                                        ▼
                                                                                  FinalDecision
                                                                                        ▼
                          AuditStage：request → retrieval → proposal → action_request
                                      → pre_decision → execution → post_evidence → final_decision

### 3.2 五个哈希各绑住什么

    tool_schema_hash = sha256(ToolSpec 的执行语义)        # 改参数表 / 权限 / 限流 ⇒ 工具需重新审核
    param_digest     = sha256(规范化参数)                  # 参数差一个字符 ⇒ 摘要就不同
    context_digest   = sha256(PolicyContext + 检索来源)    # 上下文进授权，但不进审计原文
    action_hash      = sha256(工具身份 + schema 哈希 + 参数 + 主体 + 角色 + 权限
                              + 上下文摘要 + 工作区 + action/request/trace 标识)
                       └─ grant 与 approval 都绑它：参数变一个字符，旧凭据立刻失效
    diff_digest      = sha256(执行前后 diff 文本)          # 事后证据的可比对指纹
    prev_digest      = 上一条审计记录的 digest              # 审计链：改历史就会断链

### 3.3 状态机（同一个动作在不同阶段的状态不同）

| 阶段 | 取值 | 由谁给出 |
| --- | --- | --- |
| 决策 `Decision` | allow / allow_with_warnings / block | Phase 1 协议 |
| 检查 `CheckStatus` | passed / failed / skipped | `check_list` 的十三项检查（命令白名单与组合片段各一道） |
| 执行 `ExecutionStatus` | executed / delegated / failed / refused | `ControlledExecutor` |
| 事后 `PostStatus` | validated / repair_required / inconsistent / not_required | `validate` |
| 终态 `FinalOutcome` | delivered / blocked / repair_required / rolled_back / inconsistent | `_final` 合成 |

合成规则（`ControlledExecutor._final`）：

    pre = block            → blocked
    refused                → blocked        （“允许了但没执行”，没有副作用）
    failed                 → repair_required
    post = inconsistent    → inconsistent   （工具说成功、目标却没变）
    post = repair_required → rolled_back（真的回滚了）/ repair_required
    其余                   → delivered

### 3.4 四条容易混淆的边界

1. **决策 ≠ 执行**：`allow` 只是“允许”，CLI 的 `precheck` 是 **dry run**：不碰文件、
   不认领 `action_id`、不签发可用凭据（决策里 `dry_run: true`、`grant: null`），
   所以同一个请求紧接着 `execute` 仍然会真的执行。只有执行器调用驱动才产生副作用。
2. **执行 ≠ 验证**：文件变了不等于结果可接受。`validated` / `repair_required` / `inconsistent`
   是三个不同结论；“工具声称成功但目标没变”属于自相矛盾，不是成功。
3. **回滚 ≠ 没发生**：`rolled_back` 表示副作用被撤销，但 `post.status` 仍是 `repair_required`——
   “动作做砸了”这件事必须留在证据里。
4. **台账 ≠ 审计**：台账是可变的工作状态（认领、配额），审计链是只追加的证据。
   重放检测两处都看，删掉台账也绕不过审计链；两份记录都带 `action_hash`，
   因此“同一个动作重放”（`action_replay`）与“同一个 `action_id` 换了参数”（`action_id_reuse`）能分开。

### 3.5 失败关闭的位置（关键组件坏了会怎样）

| 关键组件失效 | 结果 |
| --- | --- |
| 审计不可写 | 受治理动作 block（`audit_unavailable`），并把已认领的 action 释放（台账里写 `claim_released`，修好之后同一个 action_id 可以重试）；只有 `risk=read_only` 的工具才允许声明 `audit_failure: degrade` 并降级成 `allow_with_warnings`（仓库注册表里没有这样的工具） |
| 台账不可读写 | block（`ledger_unavailable`） |
| 规则引擎超时 / 异常 | block（`policy_timeout` / `policy_block`） |
| 工具未注册 / schema 与已审核哈希不一致 | block（`tool_not_registered` / `schema_not_approved`） |
| 没有对应驱动 | refused（`driver_unavailable`）——不假装执行过 |
| 没有执行前快照 | 回滚写 `unsupported`——不假装回滚成功 |
| 授权过期 / 已被使用 / 与参数不符 | refused（`grant_expired` / `grant_reused` / `grant_invalid`） |
| 同一个 action 再来一次 | block（`action_replay` / `action_id_reuse`） |
| 命令含 `;` `|` `&` 反引号 `$(` `${` `>` `<` 或换行 | block（`command_composition_blocked`）：白名单正则的 `( .*)?` 尾巴挡不住“分号 + 第二条语句” |

## 4. 本阶段明确不做什么

- 不解析自然语言批准：审批必须是绑定 `action_hash` 的结构化记录；
- 不猜主体、角色或权限：只从显式字段取，取不到就 block（Adapter 也一样）；
- 不使用未注册的工具，也不使用描述与已审核哈希不一致的工具；
- 不假装执行过（没有驱动就 refused），不假装可撤销（没有快照就 unsupported）；
- 不重放副作用：同一个 `action_id` 绝不执行第二次（台账 + 审计链两处都拦）；
- 不把工具返回值当指令：只作不可信数据，只留摘要；
- 不把参数原文、密钥、绝对路径写进审计（脱敏 + 体积上限 + 摘要链）；
- 不在没有证据的情况下执行：审计与台账是执行的前置条件。

## 5. 想继续往下读

| 想知道 | 去哪 |
| --- | --- |
| 每步跑起来是什么样 | `walkthrough.ipynb`（或 `walkthrough.py`） |
| 为什么这样设计、边界在哪 | `docs/project/engineering-policy-platform/phases/phase-4-tool-enforcement.md` |
| 工具怎么登记、怎么重新审核 | `registry/tool-registry.yaml`、`python -m enforcement.cli registry --verify` |
| dsh 侧怎么接线（PreToolUse / PostToolUse） | `src/adapters/dsh/enforcement.py`、`src/adapters/dsh/README.md` |
| 闭环与阶段证据怎么复现 | `python tools/enforcement_loop.py`、`.tmp/artifacts/phase-4-enforcement-result.json` |
| 测试怎么盯这些性质 | `tests/unit/test_precheck.py`、`tests/integration/test_enforcement_executor.py`、`tests/security/test_enforcement_adversarial.py` |
