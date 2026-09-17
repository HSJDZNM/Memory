# Phase 4：Tool Enforcement

## 目标

把“给 Agent 规范建议”升级为“所有受控工具都经过执行前授权与执行后验证”。本阶段建立一条不可绕过的决策链。

## 动作分类

首版至少区分：

| 类别 | 示例 | 默认策略 |
| --- | --- | --- |
| 只读 | 读文件、列目录、检索文档 | 允许显式降级，但仍记录 |
| 可逆写入 | 编辑临时文件、生成报告 | 需要 pre-check 与 post-check |
| 破坏性写入 | 删除、覆盖、重置 | 缺少明确授权时 block |
| 外部副作用 | push、发布、发送请求 | 参数绑定授权与人工门禁 |
| 高权限执行 | shell、管理 API、密钥访问 | 最小权限、allowlist、默认 block |

分类由 Tool Registry 定义，不能由模型在调用时自行声明。

## 开发步骤

### 1. 建立 Tool Registry

每个工具记录稳定 ID、schema 版本、风险级别、允许参数、所需权限、是否需要 post-check 和超时。运行时工具描述与已审核哈希不一致时拒绝使用。

### 2. 生成 Action Request

把工具名、规范化参数、主体、PolicyContext、tool schema hash 和 request ID 组成不可变请求，并计算 action hash。

### 3. Pre-execute Policy

检查工具是否注册、主体是否有权、参数是否在 allowlist、前置测试/审批是否有效、决定是否绑定当前 action hash。允许结果必须有短有效期且不可被用于不同参数。

### 4. Controlled Executor

只有 `allow` 且所有绑定信息一致时执行。Executor 不解析自然语言批准。重复 action ID 返回已存在结果或拒绝，不能执行两次。

### 5. Post-execute Validation

执行后收集文件哈希、diff、退出码和工具结构化结果，再调用需要的 Validator。Post-check 失败时标记任务为 `repair_required`；是否能回滚由具体工具能力决定，不能假装所有副作用都可撤销。

### 6. 形成审计链

```text
用户请求 → 检索来源 → 模型提议 → Action Request
→ Pre Decision → 执行结果 → Post Evidence → Final Decision
```

日志按 OWASP Logging 指南测试注入、资源耗尽、权限和写入失败，并对敏感字段脱敏。

## 测试步骤

### Pre-check

- 未注册工具、未知 schema、越权主体和非法参数全部 block；
- allowlist 只允许完整匹配，不允许前缀绕过；
- action 参数变化后旧决定失效；
- 过期、已使用或不同主体的审批失效；
- Engine 超时或异常时高风险动作不执行；
- 检索内容声称“已批准”不影响授权。

### Executor

- block 时调用次数为 0；
- allow 时调用 1 次；
- 相同 action ID 重试不产生第二次副作用；
- Executor 收到未知 decision 或不完整绑定时拒绝；
- 工具返回中的指令文本只作为不可信结果保存。

### Post-check

- 文件写入后 hash 和 diff 与 action request 对应；
- AST/Lint/Test 失败产生 repair_required；
- 工具声称成功但目标未变化时报告不一致；
- 进程超时、部分写入和非零退出码有独立结果；
- 无法回滚的外部副作用在执行前要求更严格门禁。

### 日志失效与安全

- 日志字段支持换行、控制字符和超长参数而不发生注入；
- 日志不可写、磁盘空间不足或 AuditSink 超时的行为符合风险策略；
- 密钥、令牌、隐私字段被脱敏；
- 低权限主体不能读取完整审计参数；
- 高频工具请求触发速率限制或 circuit breaker。

## 观察点

观察同一工具调用在 pre-check 前、执行时和 post-check 后拥有不同状态。Policy Decision 是执行许可的一部分，不是给模型看的建议文本。

## 退出条件

- 所有受控写工具只能通过 Controlled Executor；
- 决定与主体、参数、工具 schema 和有效期绑定；
- 重放、过期、超时和日志失败均有测试；
- 高风险动作在任何关键组件失败时不会静默执行；
- 一条完整 trace 可被重放和解释。

通过后进入 [Phase 5](phase-5-code-validators.md)。

---

## 实施记录（2026-09，Phase 4 已完成）

本节记录实际落地的接口、数据结构、命令与偏差，避免文档与代码漂移。原始计划保留在上文。

### 前置调查：先把"能不能治理"这件事钉死

| 调查项 | 结论（本机实测） |
| --- | --- |
| dsh 工具参数形态 | `edit`=file_path/old_string/new_string/replace_all、`write`=file_path/content、`pwsh`=command/description/timeoutMs/workdir/run_in_background/sandbox_permissions/justification、`run_code`=code/description；参数名与 Hook 载荷里的 `tool_input` 一致（Phase 2 的 TOOL_TABLE 已核对） |
| 执行类工具现状 | Phase 2 把 pwsh / bash / run_code 登记为 `Execute` 并显式记 `not_governed`；Phase 4 必须把它们纳入受控链路，否则"能改文件的工具"没有前置授权 |
| 平台侧能不能自己执行 | `edit/write` 可以（文件驱动）；`pwsh` 需要机器上有 pwsh（本机没有 → 执行判 `failed(process_error)`，不静默通过）；`run_code` 只有 Agent 运行时能执行（平台侧 driver=none，执行器显式拒绝） |
| 幂等状态放哪 | 每个 Hook 都是新进程：幂等 / 授权单次使用 / 限流窗口必须落在文件上（追加写 JSONL，先追加再复核） |
| 审计链与 Phase 2 记录共存 | 同一个 `audit.jsonl` 里既有 Phase 2 的治理记录（无链字段），也有 Phase 4 的链式记录：`FileAuditSink` 只对自己的记录续链，外来行计数并在 `verify` 里如实报出 |
| 时间口径 | 所有时间带时区（UTC，Z 结尾）；不带时区的输入直接拒绝——否则"过期判断"会随机器漂移 |

### 实际新增与变化

| 位置 | 内容 |
| --- | --- |
| `registry/tool-registry.yaml` | 新增：数据化 Tool Registry（协议版本、风险级别、参数表、权限、角色→权限、审批角色、事后验证器、超时与限流、命令白名单）。6 个工具：fs.edit / fs.write / fs.read / exec.pwsh / exec.bash / exec.run_code |
| `registry/tool-registry.approved.json` | 新增：**已审核哈希清单**（由 `enforcement.cli registry --approve --reviewer <name>` 显式生成）。运行时描述与它不一致的工具不可使用 |
| `src/enforcement/models.py` | 新增：RiskLevel / EffectKind / DriverKind / ParamType / ParamSpec / ToolSpec / RateLimit / ActionRequest（含 action_hash）/ AuthorizationGrant / PreDecision / ExecutionRecord / FileEffect / FileBaseline / ProcessEffect / PostEvidence / PostDecision / FinalDecision / AuditRecord，以及 `SUPPORTED_POST_CHECKS` |
| `src/enforcement/registry.py` | 新增：注册表加载（拒绝重复键 / 未知字段 / 未声明权限 / 高风险无审批 / 无白名单的 shell）、schema_hash 计算、已审核哈希校验、角色→权限解析 |
| `src/enforcement/action.py` | 新增：参数 allowlist 与规范化（类型 / 长度 / 正则 / 枚举 / 路径作用域）、上下文摘要、action_hash 计算与脱敏视图 |
| `src/enforcement/approvals.py` | 新增：结构化人工审批（绑定 action_hash / 主体 / 时效 / 单次使用，授予者必须持有审批权限） |
| `src/enforcement/audit.py` | 新增：脱敏（密钥、绝对路径、控制字符）、体积上限、摘要链（sequence + prev_digest）、链校验与外来行计数 |
| `src/enforcement/ledger.py` | 新增：文件台账（认领 / 授权签发与单次消费 / 审批使用 / 限流窗口 / 失败计数） |
| `src/enforcement/precheck.py` | 新增：固定顺序的检查表（registry → action_window → principal → permissions → command_allowlist → approval → policy → rate_limit → circuit_breaker → ledger → audit）与短时效授权签发 |
| `src/enforcement/executor.py` | 新增：受控执行器（校验绑定 → 单次消费 → 认领 → 驱动执行一次 → 收集证据 → 事后验证 → 合成 FinalDecision） |
| `src/enforcement/drivers.py` | 新增：文件驱动（edit/write + 执行前快照）、argv 进程驱动、shell 命令驱动（白名单二次校验）、委托驱动（Agent 运行时） |
| `src/enforcement/postcheck.py` | 新增：执行后证据收集（前后哈希 / diff / 退出码）与内置验证器（file_changed / file_syntax / diff_recorded / exit_code_zero / target_exists）、回滚 |
| `src/enforcement/trace.py` | 新增：审计链校验与重放（按 action 分组判断阶段顺序；"没有 pre_decision 就没有执行/结论记录"） |
| `src/enforcement/cli.py、__main__.py` | 新增：registry / precheck / execute / approve / trace / verify / self-check 子命令 |
| `src/adapters/dsh/enforcement.py` | 新增：dsh × Phase 4 桥接（载荷 → Action Request；PostToolUse → 证据与终态；执行前基线写台账） |
| `src/adapters/dsh/adapter.py、hooks.py` | 变化：新增 `registry / registry_approved / enforcement_ledger / approval_file` 配置项；支持 PostToolUse；受控工具在引擎放行之后再过 Phase 4 门禁；执行类工具纳入受控链路 |
| `tests/unit/test_tool_registry.py、test_action_request.py、test_precheck.py、test_enforcement_audit.py` | 新增：36 + 21 + 36 + 22 个用例（含复核回归：组合命令、degrade 限制、认领释放、脱敏） |
| `tests/contract/test_enforcement_protocol.py` | 新增：12 个用例（协议不变量、跨进程哈希一致、注册表 ↔ dsh 工具表一致性） |
| `tests/integration/test_enforcement_executor.py、test_enforcement_cli.py、test_dsh_enforcement.py` | 新增：22 + 13 + 14 个用例（真实文件、真实子进程、真实 dsh Hook 路径；含"没写进去""伪造授权""示例请求可跑"等复核回归） |
| `tests/security/test_enforcement_adversarial.py` | 新增：11 个对抗用例（注入、越权、审批伪造、日志失效、路径逃逸） |
| `tools/enforcement_loop.py` | 新增：受控执行闭环（允许一次 / 重放阻断 / 失败回滚 / 高风险阻断 / trace 可重放），结论写给阶段证据 |
| `tools/phase_evidence.py` | CURRENT_PHASE=4，新增 enforcement 段（注册表事实、已审核哈希、角色权限、闭环结论） |
| `.github/workflows/phase-4.yml` | 替换 phase-3.yml：保留 Phase 0–3 的重放，追加注册表校验、自检、闭环、审计链校验与未知参数拒绝 |

### 决策链的形状（一条 trace 的六个位置）

```text
用户请求 / 模型提议
    ↓  (1) Action Request：工具身份 + schema 哈希 + 规范化参数 + 主体 + 权限 + 上下文摘要
        → action_hash（参数改一个字符就变）
    ↓  (2) Pre Decision：注册表 / 时效 / 主体 / 权限 / 参数与命令白名单 / 审批 / 规则引擎 / 限流 / 熔断 / 重放 / 审计
        → allow 时签发短时效、单次使用、与 action_hash 绑定的 grant
    ↓  (3) Execution：执行器只认 grant；认领 action_id（重复即拒绝）；驱动恰好执行一次
    ↓  (4) Post Evidence：文件前后哈希、diff 摘要、退出码、超时、工具返回值摘要（不可信数据）
    ↓  (5) Post Decision：validated / repair_required / inconsistent（回滚能力按工具声明）
    ↓  (6) Final Decision：delivered / blocked / repair_required / rolled_back / inconsistent
```

每一步都写进同一条摘要链（`sequence` + `prev_digest`），
`enforcement.cli trace --action-id …` 可以把它们按顺序重放出来。

### 与原始计划的偏差（都需要知道）

1. **"受控执行"在 dsh 链路里是"委托执行"。** dsh 的外部命令 Hook 只能放行或阻断，
   不能替 Agent 执行工具。因此受控工具在 dsh 侧走的是同一条 pre-check + 授权 + 审计链，
   但执行本身是**委托驱动**（delegated），事后证据由 PostToolUse 补齐；
   平台自己执行（文件驱动 / 进程驱动）走 `enforcement.cli execute`，两者共用同一个执行器实现。
2. **执行类工具没有文件维度，规则引擎显式跳过。** PolicyContext 以文件为锚（Phase 1 的契约），
   而 pwsh / run_code 没有目标文件。此时 `policy` 检查记为 `skipped` 并写明原因，
   授权完全由注册表（权限 / 参数白名单 / 命令白名单 / 审批）决定——绝不假装跑过规则引擎。
3. **未登记工具默认阻断。** `str_replace_editor`（标准装配未启用）与 `workflow`（线协议参数未核实）
   没有写进注册表：它们一旦被调用就是 `tool_not_registered`。这是失败关闭，不是遗漏——
   升级 dsh 后先核对参数表，再登记并重新审核。
4. **审批必须与具体 action_hash 绑定，因此"事先签发"等于"对着某次具体调用签发"。**
   首版把审批文件放在 adapter 配置的 `approval_file`（可选）：签发入口是
   `enforcement.cli approve --request <req.json>`。人在回路里的"申请—批准"流程属于 Phase 7（Policy API）。
5. **`audit.jsonl` 同时承载 Phase 2 与 Phase 4 的记录。** Phase 4 只对自己的记录续链，
   外来行计数并在 `verify` 输出里报出，不会被当成"链的一部分"。
6. **只读工具仍是"显式降级"。** `read/glob/grep` 一类动作不做 pre-check（每次调用都起进程做一次
   全量授权在首版是净负担），但它们在注册表里有 `risk=read_only` 的显式声明，且仍然进入审计。
   降级是写下来的策略，不是异常处理里的偷偷放行。
7. **Phase 2 的两条结论被 Phase 4 改变**（各自都有回归用例）：
   `pwsh` 不再是 `not_governed`（改为受控，默认阻断）；
   PostToolUse 不再是"未支持事件"（改为事后验证入口）。"未知事件失败关闭"仍然成立，用别的未知事件验证。
8. **测试配置默认声明主体与注册表。** Phase 4 起"受控工具必须有主体可追"，
   因此 `tests/conftest.py::write_dsh_config` 默认写 `principal: {subject: local-user, roles: [developer]}`
   与注册表路径；对应两个 Phase 2 用例（主体语义）同步更新，语义更严而不是更松。

### 失败关闭是怎么实现的

1. **注册表不可用 / 未审核 / 描述漂移** → 工具不可使用（`schema_not_approved`），
   Hook 侧连"引擎放行"都到不了执行器；
2. **主体缺失 / 权限不足 / 参数越界 / 命令不在白名单** → block，且给出具体缺失项；
3. **规则引擎阻断或超时** → block（超时不降级）；
4. **审计不可写** → 受治理动作默认 block（只有注册表显式声明 `audit_failure: degrade` 的只读工具才降级为 warning）；
5. **台账不可写** → block；**授权过期 / 被用过 / 绑定不一致** → 执行器拒绝执行（refused）；
6. **同一动作重放** → 台账 + 审计链双保险（删掉台账文件也拦得住）；
7. **限流 / 熔断** → 窗口与阈值来自注册表数据，超限即 block；
8. **事后验证失败** → 声明了 `file_snapshot` 的工具回滚，其余显式写 `rollback: unsupported`；
   回滚只在"平台自己执行且确实保存过快照"时发生——绝不对委托执行谎称回滚成功。


### 一处环境观察（与本阶段实现无关，但会影响证据解读）

`python tools/dsh_sandbox_loop.py`（Phase 2 的真实 dsh 闭环）在**被沙箱化的会话里**跑不通：
嵌套 dsh 会话继承了外层"需要审批但没有应答者 → 失败关闭"的策略，工具调用在到达 Hook 之前就被拒绝，
因此 `.tmp/artifacts/phase-2-sandbox-result.json` 的 `result=fail` 且 `diagnosis` 写着"Hook 从未被调用"。
这不是策略判定结果（审计里一条记录都没有），也不是 Phase 4 的回归：CI 上没有 dsh 时该脚本输出 `skipped` 并退出 0。
为了不让这类失败被误读成"被规则阻断"，脚本现在会在审计为空时显式写出 `diagnosis` 字段，阶段证据同样带上它。
Phase 4 自己的闭环（`python tools/enforcement_loop.py`）不依赖 dsh，在本机与 CI 都稳定通过。


### 两处按复核意见修正的语义（都有回归用例）

1. **`precheck` 是 dry-run。** 它只回答“如果现在执行会被允许吗”：不认领 `action_id`、
   不签发可用授权（`grant=null`）、不写限流台账，审计记录标注 `dry_run: true`。
   否则“先 precheck 再 execute”会因为 `action_id` 被自己占用而变成 `action_replay`，
   这是直觉操作会踩到的坑。真正占用 `action_id` 的是 `execute`。
2. **认领发生在审计之前。** 允许路径的顺序是 check → 认领 → 签发授权 → 写审计，
   这样审计里写下的决策与最终返回的决策永远一致（不会出现“pre 说 allow、实际却阻断”的自相矛盾）。
   代价是：如果认领之后审计仍写不进去，这个 `action_id` 已经被占用——失败关闭且可见，
   换一个新的 `action_id` 重试即可。
3. **已经执行过的 `action_id` 换参数复用时，原因码是 `action_id_reuse` 而不是 `action_replay`。**
   审计记录里没有 `action_hash` 时不再拿“当前请求的哈希”顶替，而是标记为未知来源，
   因此“这个 action 发生过”不会被误判成“就是这次这个动作”。


### 独立复核与修复（同一阶段内的第二轮）

实现完成后由一名独立复核者（不看本文档的自述、只跑代码）按计划书的验收条目做了对抗性验证，
报回 13 条问题（1 阻断 / 6 重要 / 6 次要），**除两条明确记为设计边界外全部已修复并补了回归用例**：

| # | 级别 | 问题 | 修复 | 回归用例 |
| --- | --- | --- | --- | --- |
| D1 | 阻断 | 命令白名单可被组合命令绕过：`^echo( .*)?$` 会放行 `echo hi ; 任意命令`，驱动又把整串交给 PowerShell 二次解析 | 新增结构性检查 `command_composition`：命令里出现 `;` `|` `&` 反引号 `$(` `${` `>` `<` 换行一律阻断（`command_composition_blocked`），驱动层再查一遍；夹具白名单故意带上 `( .*)?` 尾巴以便回归 | `test_compound_commands_are_structurally_blocked` |
| D2 | 重要 | 未登记的执行类工具 `workflow` 在 dsh Hook 侧被放行 | `not governed` 分支改为按 Adapter 工具表的 `kind` 判断：执行类工具一律进受控链路，注册表不认识的走 `tool_not_registered` | `test_unregistered_execute_tool_is_blocked_instead_of_degraded` |
| D3 | 重要 | 委派执行的 `write` 声称成功、目标却没变时仍判 validated | 新增事后验证器 `content_matches`（写入内容 / 替换结果必须与请求一致），`fs.write` 与 `fs.edit` 都声明它 | `test_delegated_write_that_did_not_write_is_inconsistent` |
| D4 | 重要 | 脱敏漏洞：`Authorization: Bearer <jwt>` 只吃掉前缀、JWT 原文落盘；POSIX 绝对路径不脱敏 | 通用密钥模式补可选 `bearer` 前缀整体匹配；绝对路径正则增加 `/home | /root | /etc | /usr | /var | /opt | /srv | /tmp | /mnt | /Users` 形态 | `test_bearer_tokens_and_posix_paths_are_redacted` |
| D5 | 重要 | `audit_failure: degrade` 未限定只读工具：高风险动作可在审计完全不可写时执行 | `ToolSpec` 增加跨字段不变量：`degrade` 只允许 `risk=read_only`，否则注册表加载失败 | `test_only_read_only_tools_may_degrade_the_audit` |
| D6 | 重要 | 文档示例 `execute examples/enforcement/edit-allow-request.json` 在任何干净仓库上必然失败（workspace 指向 `.tmp/phase-4-demo`，而闭环脚本把文件建在 `.tmp/phase-4-demo/workspace/`） | 示例的 `workspace` 改为 `.tmp/phase-4-demo/workspace`，README 说明先跑 `tools/enforcement_loop.py` 准备演示工作区 | `test_documented_example_requests_are_runnable` |
| D7 | 重要 | 带 `policy_context` 的请求 approve 与 execute 绑定不同的 action_hash（`_approve` 没传上下文）；规则目录拿工作区当锚点还会 `LoaderError` | `approve` 与 `execute` 共用同一条请求构造路径（`context_for_document`）；规则集锚点改为仓库根、上下文锚点仍是工作区 | `test_approve_and_execute_agree_when_the_request_has_a_policy_context` |
| D8 | 次要 | 审计不可写导致的 block 会烧掉 action_id（与“被阻断的尝试必须能重试”冲突） | 新增 `claim_released` 台账记录与 `active_claims()`：失败关闭时释放认领，审计修好后同一 action_id 可重试 | `test_audit_failure_releases_the_claim_so_a_retry_is_possible` |
| D9 | 次要 | `file_changed` 把“文件原本不存在”判成“缺少执行前基线”，声明了 `file_snapshot` 时还会把刚建好的文件删掉 | `FileEffect` 增加 `baseline_recorded`：区分“没有基线”与“基线说原本不存在”；新建文件是合法的变化 | `test_new_file_is_not_reported_as_missing_baseline` |
| D10 | 次要 | 未注册工具的阻断在 CLI / `pre_execute` 侧零记录 | `spec is None` 时也写一条 `pre_decision` 审计记录（尽力而为） | `test_unregistered_tool_block_is_audited` |
| D13 | 次要 | 执行器接受手工构造的 `AuthorizationGrant`（只校验结构，不校验来源） | 执行器要求授权必须在台账里登记过（`grant_recorded`）：只认本平台签发的凭据 | `test_forged_grant_is_rejected_by_the_executor` |
| D11 | 次要 | 审计链是无密钥摘要链：改中间/删中间能发现，**删尾或整链重写不能** | 记为设计边界（见下），不假装它是防篡改日志 | —— |
| D12 | 次要 | 审批记录自证角色：`granted_by_roles` 由同一条记录声明，没有签名与独立名册 | 记为设计边界，Phase 7 的审批 API 才引入鉴权与签名 | —— |

**已知边界（本阶段不做，已在上面记名）**：

1. **审计链不是防篡改日志**：`sequence + prev_digest` 能发现中间被改/被删，但删掉尾部或整链重算摘要无法被链本身发现。
   要对外证明“没被改过”需要外部锚定（把链尾摘要登记到别处 / 签名）；这属于 Phase 7 的 Policy API。
2. **审批的授予者角色来自审批文件自身**：首版把审批当作“人工门禁写下的结构化记录”，不做签名与独立审批人名册；
   伪造一个 `granted_by_roles=[reviewer]` 的文件即可自批。对外部敌手而言审批文件本身就在受信任边界内（与注册表、规则同级）。
3. **命令白名单的语义是“单条语句”**：组合命令默认阻断；确需组合时必须改注册表、重新审核，并说明为什么安全。

复核也独立确认了本阶段的关键主张：未注册 / 未审核 / 越权 / 非法参数 / 路径逃逸全部在构造或决策阶段被拒；
block 驱动 0 次、allow 恰好 1 次；同 pre 复用与删台账都拦得住；两进程并发认领恰好一个成功；
参数变一个字符旧授权立即失效；授权与审批的过期 / 跨主体 / 已用三种失效都被拒；
引擎超时与“检索片段声称已批准”都不能换来授权；post-check 能识别“没变化”与“语法坏了”并真的回滚；
注入载荷写盘后仍是单行；超长记录失败关闭；审计里不含参数原文。


### 复核之外：两个由手册编写过程暴露的口径问题（已修复）

1. **`precheck` 会占用 `action_id`**（写手册时按直觉“先 precheck 再 execute”发现的）：
   `precheck` 原本也认领 `action_id`，于是紧随其后的 `execute` 会被判成 `action_replay`，退出码 1。
   现在 `precheck` 是 **dry-run**：不认领、不签发可用授权（`grant=null`）、不写限流台账，审计记录标注 `dry_run: true`；
   真正占用 `action_id` 的是 `execute`。回归用例：`test_precheck_is_a_dry_run_and_does_not_block_the_real_execution`。
2. **`refused` 的执行记录会打断 trace 校验**：直接复用别的动作的 pre 决策时，执行器写下的 `execution(refused)`
   之前没有任何 `pre_decision`，`verify_chain` 会报“没有决策就不能有执行”，让 `trace` 退出 2。
   “没有决策就没有执行”这条不变量现在只针对**真的产生效果**的记录（`executed` / `delegated` / `failed` 与 `post_evidence`）；
   `refused` 恰恰是“没有决策 / 决策属于别的动作”时的合法留痕。回归用例：`test_refused_execution_without_a_decision_is_not_flagged`。

### 落地命令

    python -m enforcement.cli registry --verify            # 注册表与已审核哈希是否一致（不一致退出 2）
    python -m enforcement.cli registry --show fs.edit      # 单个工具的风险 / 权限 / 参数 / post-check
    python -m enforcement.cli registry --approve --reviewer <name>   # 复核后重新登记已审核哈希
    python -m enforcement.cli precheck --request examples/enforcement/edit-allow-request.json  # dry-run
    python -m enforcement.cli execute  --request examples/enforcement/edit-allow-request.json
    python -m enforcement.cli approve  --request examples/enforcement/shell-approval-request.json \
        --out .tmp/artifacts/approval.json --granted-by alice --roles reviewer --ttl 300
    python -m enforcement.cli trace --audit .tmp/artifacts/enforcement-audit.jsonl --action-id <id>
    python -m enforcement.cli verify  --audit .tmp/phase-4-demo/audit.jsonl
    python -m enforcement.cli self-check
    python tools/enforcement_loop.py                       # 受控执行闭环（结论进阶段证据）
    python -m pytest tests/unit -q                         # 388 用例
    python -m pytest tests/contract -q                     # 82 用例
    python -m pytest tests/integration -q                  # 147 用例
    python -m pytest tests/security -q                     # 20 用例
    python tools/phase_evidence.py                         # .tmp/artifacts/phase-4-evidence.json

### 验收证据

`python tools/phase_evidence.py` 生成的 `.tmp/artifacts/phase-4-evidence.json` 记录：
实现版本、规则集哈希、决策协议版本、Agent 适配器契约事实、
**受控执行事实**（注册表路径与摘要、已审核哈希与审核人、协议版本、6 个工具的风险级别 / 驱动 /
权限 / 参数名 / 事后验证器 / 回滚方式 / 限流参数 / schema 哈希、角色→权限表、授权有效期与上限、
审计单条上限、内置验证器清单、未审核工具清单）、
**受控执行闭环结论**（允许一次 / 重放阻断 / 失败回滚 / 高风险阻断 / trace 可重放，
以及每个场景的关键事实：action_hash、grant_id、diff 摘要、终态）、
每个套件的命令 / 用例数 / 失败数、性能基线、JUnit 报告路径与时间戳。
证据里不含任何工具参数原文、文件内容或审批内容。
