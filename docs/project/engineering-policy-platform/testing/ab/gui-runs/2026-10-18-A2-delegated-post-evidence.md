> 来源：.tmp/a2-571/REPORT.md（A2 探针报告，2026-10-18）。
> 归档时间：2026-10-18。
> 本文件是 06 证据落点（P-A2-001）；.tmp 产物会被 cleanup 删除，SHA256SUMS.txt 的 sha256 清单在本文件 §7 保留。

# A2 探针报告 · 5.71「exec.pwsh 走 delegated 支路时的事后证据形状」

> 任务：task-2 · A2（05 §4 阶段 A）。只读探针，不改仓库代码；过程产物在 .tmp/a2-571/（cleanup 后不再存在，读数与 sha256 清单见本文件）。
> 起点锁：HEAD 6167fad81077ee43fb29c98297f7512d2d866273；Python 3.13.11；PowerShell 5.1.26100.9444；git 2.43.0.windows.1。
> 写入区纪律：本探针只写 .tmp/a2-571/；对受治项目 C:/Users/ZNM/Downloads/Comparison-test/Governance 只读。

## 0 结论（三态判定）

**5.71 那一枪是「真阳性」：命令真的以退出码 1 失败，事后核对判 repair_required 是对的。**

- **「假阳性」不成立**：空输出本身不参与判定（源码 src/enforcement/postcheck.py#L484-L494 只读 process.timed_out / process.exit_code）；探针 C1（空 stdout + 退出 0）判 validated，C2（非空 stdout + 退出 0）也判 validated。
- **「delegated 支路事后证据天然不足（能力边界）」不成立**（对 dsh 桥接这条实际路径）：同一条 delegated 支路、同一会话 16:14:00 的 python -m pytest -q（退出 0）判 post_validated；探针 C1/C2 同样判 validated。L4 的 POST_EVIDENCE 里写着 process.exit_code = 1、validator 明细「退出码 1」——退出事实在、且被正确读取。
- **「证据不足」不成立**：5.71 缺的那一行记录就在同一份审计文件里；16:09:48 的会话 transcript 原文是 [stderr] fatal: not a git repository (or any of the parent directories): .git + [exit code: 1]。
- **「待解释」的来源是读错了三处字段**（见 §2）：PostToolUse 审计记录里的 exit_code=2 是 Hook 进程自己的退出码、executed=false 是 PostToolUse 的 HookOutcome 默认值；台账 execution 记录本来就不存 exit_code；命令退出码只在 stage=post_evidence 的 payload.process.exit_code。
- **确实存在的边界是「解释性证据」而非「判定证据」**：delegated 桥接构造的 ExecutionRecord 不填 stdout/stderr（src/adapters/dsh/enforcement.py#L436-L454），于是 post_evidence.payload.process.output_excerpt 恒为空串、stdout/stderr 摘要恒为 null——非零退出「判得对」但「说不清为什么」。L4 §4 把「审计里 output_excerpt 为空」读成「命令输出为空」正是这个缺口的直接后果（L4 §4 的「工作区干净、porcelain 输出为空」是误读：stdout 空，stderr 是 fatal）。
- 另有一条**与 L4 无关的**能力边界：Phase 4 通用 DelegatingDriver（src/enforcement/drivers.py#L708-L720）不产生退出码，若把它与 post_checks: [exit_code_zero] 组合，必然判 repair_required（探针 D1）；但 exec.pwsh 在 GUI 里不经过这个驱动，而是走 dsh 桥接的 EnforcementBridge.post。

## 1 L4 那一枪的记录复算（action_id 与数值逐字）

会话 session-b8bed3f6-b0a7-4c82-a798-a42c710dcd73，action_id
session-b8bed3f6-b0a7-4c82-a798-a42c710dcd73:call_00_hbf6dmXCWlNvctJUaSvh3440:ptc:2，
命令 git status --porcelain=v1，cwd = C:/Users/ZNM/Downloads/Comparison-test/Governance。

| 记录 | 来源 | 关键字段（原文） |
| --- | --- | --- |
| 审计 PreToolUse | .policy/audit.jsonl（hook_event=PreToolUse） | reason_code=enforcement_allow（16:09:48.078），随后 reason_code=allow_delegated、governed=true、scope_note=Phase 4 受控执行：高权限动作放行，由 Agent 运行时执行（16:09:48.155） |
| 审计 post_evidence | 同文件，stage=post_evidence（16:09:51.392） | status=repair_required、reason_code=post_check_failed、process={exit_code: 1, timed_out: false, output_excerpt: 空串, stdout_digest: null, stderr_digest: null}、validators=[{validator: exit_code_zero, status: failed, detail: "退出码 1"}]、untrusted_result_digest=sha256:46af249d5c82bf5763a31ffe37e3417718d651eb75206627891ea702ffc19de3 |
| 审计 final_decision | 同文件，stage=final_decision（16:09:51.574） | outcome=repair_required、execution_status=delegated、pre_decision=allow、detail="exit_code_zero: 退出码 1" |
| 审计 PostToolUse（Hook 结果行） | 同文件，hook_event=PostToolUse（16:09:51.580） | reason_code=post_repair_required、exit_code=2、executed=false |
| 台账 execution | .policy/enforcement-ledger.jsonl（16:09:51.578） | kind=execution, status=delegated, ok=false, risk=privileged_execution, limit_key=local-user|exec.pwsh；**键集合里没有 exit_code** |
| 宿主原始结果（transcript） | ~/.dsh/sessions/--C-Users-ZNM-Downloads-Comparison-test-Governance--/session-b8bed3f6.../session.v4.jsonl.zstd | [stderr] fatal: not a git repository (or any of the parent directories): .git [exit code: 1]；模型侧提示 POST-CHECK repair_required ... detail: exit_code_zero: 退出码 1 |

**同会话对照枪（B）**：16:14:00 的 python -m pytest -q（action_id ...:call_00_mbBjTQrngcwZI9FNP89u7802:ptc:1）
post_evidence.process.exit_code=0、validator「退出码 0」、status=validated，台账 execution.status=delegated, ok=true（同样没有 exit_code 键），
PostToolUse 记录同样 executed=false、exit_code=0。**同一 delegated 支路可以判 validated。**

**全历史普查（P3）**：受治项目 audit.jsonl 里 tool_id=exec.pwsh 的 stage=post_evidence 共 28 条：
4 条 validated（全部 python -m pytest -q、exit 0）、3 条 repair_required（全部为 git status --porcelain[-=v1] / git show HEAD:README.md、**exit 1**）、21 条 status=null（post_without_pre 占位：没有 pre-check，既证明不了授权也证明不了拒绝，不是事后判定）。
其中 16:09:51（L4）与 17:33:54 / 17:34:00（L5–L8 会话 session-0ec9c5e0-…）三条 repair_required 的 validator 明细逐字相同：("exit_code_zero","failed","退出码 1")；后两条 transcript 同样含 fatal: not a git repository。**受治项目不是 git 仓库**，所以三条 git 命令都真实失败。

## 2 逐字段回答

### 2.1 post_repair_required 在哪一行、因为缺哪个字段产生？

不是「缺字段」产生的，是 **exit_code 非 0** 产生的：

1. EnforcementBridge.post 从 PostToolUse 载荷的 tool_exit_code 取命令退出码（src/adapters/dsh/enforcement.py#L436-L454），构造 ExecutionRecord(status=DELEGATED)；
2. collect_evidence 因 spec.effect=process 生成 ProcessEffect(exit_code=record.exit_code, ...)（src/enforcement/postcheck.py#L202-L211）；
3. validate 执行 exit_code_zero（src/enforcement/postcheck.py#L484-L494）：process.exit_code != 0 → _outcome(..., False, "退出码 1")；
4. failed 列表含 exit_code_zero → PostStatus.REPAIR_REQUIRED + ReasonCode.POST_CHECK_FAILED（src/enforcement/postcheck.py#L326-L337）；
5. Hook 层把状态渲染成 post_{status} = post_repair_required，退出码 EXIT_BLOCK=2（src/adapters/dsh/hooks.py#L2237-L2252，常量 #L133-L134）。
   若是「拿不到退出码」，明细会是「命令没有退出码：结果不可判定」（postcheck.py#L490-L491），而 L4 的明细是「退出码 1」——**这证明 L4 拿到并读到了宿主退出码**。

### 2.2 exit_code=2 与 executed=false 各自来自哪一层？

- exit_code=2（PostToolUse 审计记录）：**Hook 进程自身的退出码**（阻断语义），不是命令退出码；写入口在 src/adapters/dsh/hooks.py#L949-L973（payload["exit_code"] = outcome.exit_code），post 阻断时在 #L2237-L2252 设为 EXIT_BLOCK。
- executed=false（PostToolUse 审计记录）：HookOutcome.executed 的**默认值 False**（src/adapters/dsh/hooks.py#L516）；_post_decision_outcome 从不设置这个字段。因此**所有** PostToolUse 记录都是 executed=false：本探针 C1–C5 五格（含两格 validated）全部 false，L4 的 B 枪（post_validated）也是 false。它不表示「命令没有执行」。
  （PreToolUse 的 executed=false 是另一条语义：_decide_via_enforcement 显式写 executed=False，因为平台自己没执行、交给宿主，见 hooks.py#L2038-L2059；普通 _decide 路径则用 execution.status in {executed, delegated}，见 #L1800-L1836。）
- 命令退出码只在 stage=post_evidence 的 payload.process.exit_code（src/adapters/dsh/enforcement.py#L491-L493）；台账 execution 记录没有这个字段，是因为 EnforcementLedger.record_execution 的签名/载荷不含 exit_code（src/enforcement/ledger.py#L531-L554）——这是**设计如此**，不是丢证据；B 枪 ok=true 同样没有该键。

### 2.3 空输出是否真的影响判定？

**不影响。** exit_code_zero 的判据只有 timed_out 与 exit_code，不读任何 stdout/stderr/output_excerpt（postcheck.py#L484-L494）；collect_evidence 造进程证据也只由 effect=process / exit_code is not None / timed_out 触发（#L202-L211）。探针四形态 + 一对照见 §3：
C1（空输出，exit 0）validated；C2（非空，exit 0）validated；C3（stdout 空，exit 1）repair；C4（非空，exit 1）repair；C5（空输出，无退出事实）repair（「命令没有退出码」）。

### 2.4 为什么「工作区干净、porcelain 输出为空」是误读？

- git status --porcelain=v1 在**非 git 仓库**里：stdout 为空，stderr 为 fatal: not a git repository (or any of the parent directories): .git，Windows PowerShell 包装后退出码 **1**（本机实测；见 §3 复现命令与 L4 transcript）。「stdout 空」≠「树干净」。
- 更关键：delegated 桥接构造的 ExecutionRecord 不填 stdout/stderr（enforcement.py#L436-L454），所以 post_evidence.process.output_excerpt **恒为空串**、stdout_digest/stderr_digest 恒 null——**无法从审计判断输出是否为空**。探针 C2/C4 明明有非空输出，审计里同样是空。L4 §4 的「输出为空」只能来自 transcript/stdout 印象，不能来自审计字段。

## 3 最小复现（真实执行链 + fake 边界）

**被测真实代码**（不是 fake 被测逻辑）：
adapters.dsh.enforcement.EnforcementBridge.pre/post → enforcement.precheck.pre_execute → enforcement.registry.load_registry → enforcement.postcheck.collect_evidence/validate → enforcement.ledger.EnforcementLedger / enforcement.audit.FileAuditSink；Hook 结果形状用真实的 adapters.dsh.hooks._post_decision_outcome；P2 用真实的 enforcement.executor.ControlledExecutor + DelegatingDriver/ShellCommandDriver。

**fake 边界（只有宿主侧两处）**：
1. 命令由探针通过系统 powershell -NoLogo -NoProfile -NonInteractive -Command … 执行（本机没有 pwsh 7）。L4 transcript 显示宿主工具给出同样的 stderr 与 [exit code: 1]，且审计 process.exit_code=1 与之一致；故这条 fake 对本次定性不构成分歧。
2. PostToolUse 载荷按插件源码的转发规则手工构造：tool_response（字符串）+ tool_exit_code（仅当 result.value.exitCode 是整数，照抄 policy-hook.plugin.mjs#L99-L121）。插件真实分支见 policy-hook.plugin.mjs#L678-L711。
**其余一律真实**：注册表（受治项目的 tool-registry.local.yaml + tool-registry.approved.json）、审批条子（approval.json 的副本，**仅把 expires_at 改到 2030**，其余字段逐字不变；原件已过期）、授权、审计、台账、post-check 全部走仓库代码。审批侧：L4 的 approval-pwsh-readonly（binding=pattern，模式 ^git (status|diff|log|show)( .*)?$）覆盖该命令（模式整串匹配见 src/enforcement/approvals.py#L490-L580；按 tool_id/形状选择见 #L368-L447，选择不改判定），P1 复用其副本。

### 3.1 P1：dsh delegated 桥接 × 五格

| 格 | cwd / 命令 | 宿主 stdout / stderr | exit | 载荷带 tool_exit_code | post 判定 | 台账 execution | PostToolUse HookOutcome |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1 干净仓库 | repo-clean / git status --porcelain=v1 | 空 / 空 | 0 | 是 | validated（"退出码 0"） | delegated, ok=true，无 exit_code 键 | exit=0, post_validated, executed=false |
| C2 脏仓库 | repo-dirty / 同上 | 非空（30B） / 空 | 0 | 是 | validated（"退出码 0"） | delegated, ok=true | exit=0, post_validated, executed=false |
| **C3 = L4 复现** | Comparison-test/Governance（非 git 仓库）/ 同上 | **空** / **fatal: not a git repository** | **1** | 是 | repair_required（"**退出码 1**"） | delegated, ok=false，无 exit_code 键 | exit=2, post_repair_required, executed=false |
| C4 脏仓库 + 非零 | repo-dirty / git diff --exit-code | 非空（125B） / warning | 1 | 是 | repair_required（"退出码 1"） | delegated, ok=false | exit=2, post_repair_required, executed=false |
| C5 无退出事实 | repo-clean / git status --porcelain=v1 | 空 / 空 | 0 | **否** | repair_required（"**命令没有退出码：结果不可判定**"） | delegated, ok=false | exit=2, post_repair_required, executed=false |

**C3 与 L4 那一枪逐字段相等**：post_evidence 的 status/reason/process.exit_code/validators 明细、台账 execution 的 status/ok/无 exit_code、HookOutcome 的 exit_code=2 / executed=false / reason=post_repair_required——全部一致（L4 的 process 也带 output_excerpt 空串、digest null）。
**C1 vs C3**：同一个命令、同一个受治桥接、同样的空 stdout；差别只有 cwd 是否 git 仓库（退出码 0 vs 1）。这就是「空输出不决定判定」的直接对照。

### 3.2 P2：Phase 4 执行器的 delegated 驱动 vs 平台自执行

| 格 | driver | record | post | 台账 |
| --- | --- | --- | --- | --- |
| D1 | DelegatingDriver | status=delegated, exit_code=null, output_excerpt 空串 | repair_required / post_check_failed，明细「命令没有退出码：结果不可判定」 | delegated, ok=false |
| D2 | ShellCommandDriver（powershell 前缀） | status=executed, exit_code=0 | validated（"退出码 0"） | executed, ok=true |

D1 说明：**通用 DelegatingDriver + exit_code_zero 这条组合是能力边界**（没有退出码可读，失败关闭地判 repair_required）。但 exec.pwsh 的注册表声明是 driver: shell_command，GUI 的 delegated 路径由 dsh 宿主执行、由 EnforcementBridge.post 从载荷取退出码，**不经过 D1**。5.71 第三列把 src/enforcement/executor.py（以及 drivers.py 的 shell_command）当作实际路径，指错了对象。

## 4 定性：为什么两个候选假设都不成立

| 候选 | 判据 | 读数 | 裁决 |
| --- | --- | --- | --- |
| 假阳性（空输出/宿主退出码被误判） | 若空输出影响判定，C1 应 repair | C1 空输出+exit0 → validated；C2 非空+exit0 → validated；C4 非空+exit1 → repair；C5 空+无退出码 → repair（失败关闭） | **不成立** |
| 能力边界（delegated 支路事后证据天然不足） | 若结构上拿不到退出码，C1/C2 与 L4-B 都不能 validated | C1/C2 validated；L4-B（pytest，delegated）post_validated；L4-A 的 post_evidence 明确 process.exit_code=1 | **不成立（对 dsh 桥接路径）** |
| 真阳性 | 命令是否真的失败？ | transcript：fatal: not a git repository + [exit code: 1]；受治项目至今没有 .git；C3 在同一 cwd 复现 exit 1；L5–L8 两条 git 命令同形 | **成立** |

**仍然值得登记的「边界」有两条，但都不是本枪判定的边界**：
1. **解释性证据缺口**：delegated 桥接不把 stdout/stderr 摘要/摘录写进 post_evidence.payload.process（恒空），所以「判得对」却「说不清为什么」；这也让「输出为空」这类误读有了土壤。判据本身（exit_code_zero）不依赖输出，故修它不是改 allow/block，而是补证据。
2. **通用 DelegatingDriver × exit_code_zero** 永远 repair_required（D1）。当前 exec.pwsh 不走它；若未来有工具在注册表里声明 driver: none + post_checks: [exit_code_zero]，应加载期拒绝或显式写明。

## 5 建议（阶段 A 只报告，以下均未改仓库）

### 5.1 文档/台账（零代码风险，建议立即做）
1. docs/project/engineering-policy-platform/04-open-work.md#L295（5.71 行）：把「本轮数据不足以判定」改成「**真阳性**：命令在非 git 仓库里退出 1；post-check 判 repair_required 正确」。第三列改为真实路径：src/adapters/dsh/enforcement.py#L432-L527（EnforcementBridge.post，含 process.exit_code 落审计）＋ src/enforcement/postcheck.py#L326-L337 / #L484-L494；registry/tool-registry.local.yaml 是受治项目副本（未跟踪），仓库里是 registry/tool-registry.yaml#L129-L143。
2. docs/project/engineering-policy-platform/testing/ab/gui-runs/2026-10-11-L4.md §4：更正「工作区干净、porcelain 输出为空」为「**受治项目不是 git 仓库**：stdout 空、stderr fatal: not a git repository、exit 1」；补一行 post_evidence.process.exit_code=1 / validators「退出码 1」；§0/§1 的「待解释」改判。
3. src/adapters/dsh/README.md §9.5（N16 那节，已有「拿不到退出码 → repair_required」）补 4 行读法：
   - 命令退出码 = post_evidence.payload.process.exit_code（唯一权威）；
   - PostToolUse 审计行的 exit_code = Hook 自身退出码（2=post 阻断、0=放行）；
   - PostToolUse 审计行的 executed = HookOutcome.executed，post 路径恒 false，不表示命令未执行；
   - 台账 execution 记录没有 exit_code 字段，ok 才是事后结论。

### 5.2 如果要把「解释性证据」也补齐（Phase B 候选，需裁定 + 版本链）
- 最小改动：src/adapters/dsh/enforcement.py::post 把 event.response_excerpt（或按行拆出的 stdout/stderr 摘要）填进 ExecutionRecord.output_excerpt（字段已存在，enforcement/models.py），ProcessEffect.output_excerpt 会自动呈现；不可信数据需脱敏 + 截断（audit.redact_text 口径）。
- 若要新增键（如 post_status / hook_exit_code）则按 AGENTS 第 55 条升 AUDIT_SCHEMA_VERSION（现 1.3）并同批更新消费方。
- 纯文档口径（不改字段）也可先做：把「PostToolUse 的 executed/exit_code 是 Hook 字段」写死进 README，并让 verdict 类读数只读 post_evidence。

### 5.3 注册表（数据改动，需重新审核；可选）
- registry/tool-registry.yaml 的 exec.pwsh.notes 加一句：「delegated 支路 exit_code_zero 依赖宿主在 PostToolUse 转发 tool_exit_code；缺失时失败关闭判 repair_required（src/adapters/dsh/README.md §9.5），不是命令失败」。改完必须 python -m enforcement.cli registry --approve --reviewer <name>。

## 6 仍未验证什么

1. **真机宿主的 pwsh 工具本身**没有在探针里被直接调用：本机只有 Windows PowerShell 5.1（无 pwsh 7）。依据是插件源码的 result.value 形状 + L4 审计 process.exit_code=1 + transcript。宿主在其它形态（后台/超时/被取消/结构化结果）是否一定转发 tool_exit_code，未验证。
2. **pwsh 7 / 非 Windows 的退出码映射**未验证（本机 powershell 5.1 把 git 的 128 映射成 1；L4 宿主也报 1）。
3. **L4 项目审计是活跃追加文件**：本次读取期间从 21,999,792 B 长到 ≥23,461,507 B（其它会话在写，仍在增长；locks.json 只对最后一次读取时点成立）。locks.json 里的 sha256 只对读取时点成立；三条 repair_required 记录的 action_id/字段已固化在产物里，但重新跑 census 可能看到更多行。
4. **探针依赖本机受治项目路径** C:/Users/ZNM/Downloads/Comparison-test/Governance 与它的本地注册表/审批副本；registry/tool-registry.local.yaml 不在仓库里（git ls-files registry/ 只有 yaml + approved.json）。换机器不能原样重放。
5. 21 条 status=null 的 post_evidence（post_without_pre）不在 5.71 范围，未逐条判定它们对其它判据的影响。
6. 「解释性证据」修复未实现，因此未验证它是否会影响审计 schema 的消费方（enforcement.cli verdict、trace 校验等）。

## 7 产物、复现命令与 sha256

过程产物在 .tmp/a2-571/（cleanup 后不再存在）；本文件保留读数与 SHA256SUMS.txt 的 sha256 清单原文。关键读数：
- l4_summary.json（L4 两枪逐字段摘要；含 transcript 原文）
- l4_action_audit_dump.json（按 action_id 抽出的全部审计记录：pre_decision / post_evidence / final_decision / 两条 hook 行）
- p3/exec_pwsh_post_census.json（28 条 post_evidence 普查：4 validated / 3 repair_required / 21 null）
- p1/p1_results.json + p1/ledger-*.jsonl + p1/audit-*.jsonl（C1–C5 每格真实台账/审计）
- p2/p2_results.json + 同目录台账/审计（D1/D2）
- locks.json（HEAD、L4 audit/ledger/registry/approval 的尺寸+sha256、解释器版本）

复现命令（均为本机实际跑过，退出码 0）：

    $env:PYTHONPATH='src'
    .venv/Scripts/python.exe .tmp/a2-571/scan_l4.py                 # 退出码 0：从 22MB audit 抽 L4 会话记录
    .venv/Scripts/python.exe .tmp/a2-571/extract_action_audit.py    # 退出码 0：按 action_id 抽全量记录
    .venv/Scripts/python.exe .tmp/a2-571/scan_transcript.py         # 退出码 0：L4 transcript 里的宿主 stderr/exit
    .venv/Scripts/python.exe .tmp/a2-571/scan_pwsh_post_census.py   # 退出码 0：28 条 post_evidence 普查
    .venv/Scripts/python.exe .tmp/a2-571/scan_l5l8_transcript.py    # 退出码 0：L5-L8 两条 git 命令的宿主输出
    .venv/Scripts/python.exe .tmp/a2-571/probe_delegated_bridge.py  # 退出码 0：P1 C1-C5 真实桥接复现
    .venv/Scripts/python.exe .tmp/a2-571/probe_executor_delegated.py# 退出码 0：P2 D1-D2
    .venv/Scripts/python.exe .tmp/a2-571/write_locks_and_hashes.py  # 退出码 0：locks + sha256 清单

**06 台账**：本文件即受跟踪读数落点（P-A2-001），06 §4 可直指本文件；.tmp/a2-571/ 是过程产物，cleanup 后不再存在，本文件保留读数与 sha256 清单（见下）。

### sha256 清单（归档时点，取自 .tmp/a2-571/SHA256SUMS.txt）

    sha256:c6a1e57394d3f70fdba2798d536857da16964cf0c365535a31ef7c2bfc0b428a  approval.json
    sha256:51221dd9d1912fb3246319861f080132d1a2338c9fae549a2cf3f63cb0893970  check_null_post_evidence.py
    sha256:b714ba5b707abc6dd3516b235c4746e7a927097d90790b5509ef25273ccff574  check_p1_process_shape.py
    sha256:24b448b556f3a81cf80fe4064dba4e3c977a2962311e580e7c6bfbae2319bd6d  extract_action_audit.py
    sha256:02021356dc0f6225e2d0cada2a33a1217eacbc8f63d6bf677605235305ea28d0  extract_action_pair.py
    sha256:d47d8543c8ec8b308431204f833527c6e8538578e8e9cafa49129c675ca36ebd  l4_action_audit_dump.json
    sha256:14e6aab3417090367ca9651d2e5901714dbe77e9677c37389cb05dc3575f25a9  l4_action_pair.json
    sha256:4695f8e6a46c3ac1df96b1bbfd624bc9a3bdf4dd2eb4353ede82574f39285d33  l4_records.json
    sha256:46a9e5810ebf95e2f57e96628c1cfecb327f27542abc9af9657bd7f0e3344cad  l4_summary.json
    sha256:23c8c1cdf897a1c4b4859194948cf0871a8b68e740c685c9331b11e79198f160  l4_transcript_extract.json
    sha256:1c8921efb04309069ff73ce9fb1c4d4eb0f0c0aa0063a1ea622c01eec5788f9e  locks.json
    sha256:e9865575e658f9e1c51ef42c1df0d11bb435e0bf23a22c26d42946b8494f4fc0  p1/audit-C1_repo_clean_empty_stdout_exit0.jsonl
    sha256:fad702b75d531aaea144d9202ad60da64c172dccd4363384098f2d6305b28765  p1/audit-C2_repo_dirty_nonempty_stdout_exit0.jsonl
    sha256:921198dd77491202f276df72153969f0f55c17c080b1b57bd8dd996a178b6dff  p1/audit-C3_norepo_empty_stdout_exit1_L4shape.jsonl
    sha256:94f1da1b7189d35ca3c5b9c5356227049995ecc695033994721334fe2441ab7a  p1/audit-C4_repo_dirty_nonempty_stdout_exit1.jsonl
    sha256:db48a755c37cc9f82d2e5f0e1d1395fca7d0989a5b59ddb6f284010a4fed68f2  p1/audit-C5_repo_clean_exit0_no_exit_fact.jsonl
    sha256:a44fd1d9d021389ff5bba38d4ea9b84b1e51250fd6544e066201c66cc5592bdf  p1/ledger-C1_repo_clean_empty_stdout_exit0.jsonl
    sha256:2e79918f18143155b563de949bb90f0f1746ad27ba3970fc2adb29a7d5ff01c2  p1/ledger-C2_repo_dirty_nonempty_stdout_exit0.jsonl
    sha256:15ba876b49a5ed4a625cced48b49c99205c09350e69fca50adcd11fd84b748ab  p1/ledger-C3_norepo_empty_stdout_exit1_L4shape.jsonl
    sha256:07636e123101a4362273bbaeaf2f67fd7df5551dd2a13ba0a8adebbedcb578a2  p1/ledger-C4_repo_dirty_nonempty_stdout_exit1.jsonl
    sha256:0e0318276589b0f700e2bbf27fcb6ef264b3d3ea21d36649f84cb16bd809be07  p1/ledger-C5_repo_clean_exit0_no_exit_fact.jsonl
    sha256:3ca80c1ab4931f541d1245eba1132fa14dd9f84f60f3a7d68b6cf5f8e7b5b6d9  p1/p1_results.json
    sha256:c4e301fbded1792991432e3af61fe0d4515412ecbf3d781c6b67f9aae98498ca  p2/audit-D1_executor_delegating_driver.jsonl
    sha256:e6c19357c2a54ff4e433b2e09e8a12fc8b5b495e2e3b65825ef7d01e5ea79ff3  p2/audit-D2_executor_shell_command_driver.jsonl
    sha256:d7842fde973e7366c73569a8ba1009edacb512a3d7fe3c18236a60e5916a1a43  p2/ledger-D1_executor_delegating_driver.jsonl
    sha256:ff1356878d935c31437a3ba2f3261f2724200f2b6002c984faace3aaf580c5f5  p2/ledger-D2_executor_shell_command_driver.jsonl
    sha256:f5c361836e99aefaec9efc23321fc3e7333bb2da6ea77ebd2fcc88b8578dec7e  p2/p2_results.json
    sha256:4107bbdf5d9d39f015776d66f041a42eae96eb11a9ae385350187420db60f979  p3/exec_pwsh_post_census.json
    sha256:2ee2ca727beddd14892c905b8b04f6acae282e37962661988990d7640b5e6dfd  p3/l5l8_transcript_git_calls.json
    sha256:01759fa9df4de8fe1020536363f8053dfeb08e10a49e92ebf11410205920b46e  p3b_print_repair_actions.py
    sha256:fe4e52a1c7cc05a7d14bc2f3e1e428918f96a67a5a9fd443bd73b111489b7aa2  prepare_approval_fixture.py
    sha256:174a65165ec6544510164addc7eb82fbb33ce7361330ff6551b5b09408fe25da  probe_delegated_bridge.py
    sha256:96648c4a4f65b1d6178fd8dc7ada6e5473eb18c75644f1a4f733e9d6268adfac  probe_executor_delegated.py
    sha256:8ea49765f73d5b1942a3f5e642e3171f885ca331e885819e6b8c54d9df78cd89  REPORT.md
    sha256:230059ca4b6fb823b5f4f8a22ef76ed66a37c539cd06c87a66640c4e013b7a09  scan_l4.py
    sha256:1280f4f01ad60a5891be58552d15ec8a4d2db4e405f5a00186e7628c31094e6c  scan_l5l8_transcript.py
    sha256:e4416be977b6e6d5d08245277cef3db922a6c5126323ed8e1fe7281be40d1fec  scan_pwsh_post_census.py
    sha256:65f993b830244e4afe5618dfb936b67f3d8d47a445f4df32e653774b9d9d9259  scan_transcript.py
    sha256:36985a913bb6c5b7f34468a71540707677f851ecd32e7103b57f8b8b89b47c6f  summarise_l4.py
    sha256:d95311e5ba5ff1012ef300b0a520914b866a75fbe8d6682291b5a628a97f47c5  summary.json
    sha256:d1bc37c92d6200bfece2e37eec934c3519d8c9b94961a5a3315e0945ea2392dd  write_locks_and_hashes.py

注：以上哈希对应 .tmp/a2-571/ 下的原件；本归档文件是它们的可读副本，不参与该清单的哈希计算。
