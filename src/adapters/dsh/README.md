# dsh Adapter

把 dsh 的工具调用事件翻译成核心策略协议，并在工具执行前做出 allow / block 判定。
本文件是 Phase 2 **前置调查的固化结果**：下面每条结论都来自本机 dsh 的实际源码或实际运行，
不是从旧文档抄来的接口。改动本文档前请先重新核对版本与证据。

## 1. 版本与证据来源

| 项 | 值 |
| --- | --- |
| dsh CLI | 0.1.5-rc.1（dsh --version） |
| Hook 相关包 | dsh-hook-protocol / dsh-hooks-claude-code / dsh-hooks-codex / dsh-base 为 0.1.5-rc.2 |
| 实现位置 | C:\Users\ZNM\Downloads\study\.cache\npm-cache\_npx\1e7f6d9597241db0\node_modules\@deepseek-ai\ |
| 平台 | Windows，node v24.19.0，hook 命令由 pwsh 执行 |
| 事件 fixture | tests/fixtures/agent_events/dsh/（脱敏后的真实载荷） |

注意：同一次安装里 CLI 与 Hook 包的补丁版本号并不一致，因此"dsh 版本"必须按包分别记录，
升级后要重跑 fixture 契约测试与沙箱闭环。

## 2. 调查结论（Phase 2 文档要求的 6 项）

### 2.1 可用的 Hook 事件名

dsh 自己**没有**一套独立的 hook 事件；它通过两个"方言桥"复用 Claude Code / Codex 的 hooks.json。
Claude Code 方言（dsh-hooks-claude-code：src/index.ts 的 CLAUDE_EVENTS）支持：

    SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop,
    SubagentStart, SubagentStop

Codex 方言少 SubagentStart / SubagentStop。Phase 2 只接入 PreToolUse；G2 修复后 PreToolUse 与 PostToolUse 都接入（见第 9.1 节）。

### 2.2 事件在参数确定前还是执行后触发

| Hook 事件 | dsh 内部扩展点 | 时机 |
| --- | --- | --- |
| PreToolUse | tools/pre-execute | 参数已解析、**尚未执行**（可阻断） |
| PostToolUse | tools/post-execute | 已执行（只能把结果标成错误，副作用无法撤销） |
| UserPromptSubmit | agent/pre-step | 收到提示词时 |
| Stop | agent/turn-stopping | 回合即将结束 |
| SessionStart | agent/session-start | 会话开始（第 1 轮之前） |

PreToolUse 拿到的工具参数是**未解析的原始字符串**：路径要用载荷里的 cwd
（dsh 传的是 agent.session.header.cwd）才能变成绝对路径。

### 2.3 阻止工具的官方返回协议

Hook 是一个外部命令，它的**退出码**就是决定：

| 退出码 | dsh 的语义 |
| --- | --- |
| 0 | 放行；stdout 若以 { 开头会被解析为结构化输出 |
| 2 | **阻断**：工具不执行，stderr 作为理由显示给模型 |
| 其他非 0 | **非阻断失败**：只记日志，工具照常执行 |
| 启动失败 / 被超时杀掉 | 无退出码，同样**不阻断** |

结构化写法（本 Adapter 默认用退出码，结构化写法保留给需要 ask 的场景）：

    {"decision": "block", "reason": "..."}                      # 顶层只认 approve / block
    {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",                          # 必须等于当前事件名
        "permissionDecision": "deny",                            # allow / deny / ask
        "permissionDecisionReason": "..."}}

两条失败语义直接决定了本 Adapter 的安全设计：**"崩溃"和"超时"在 dsh 这边等于放行**，
所以失败关闭只能由 Hook 自己保证（见第 4 节）。

### 2.4 工具名与参数结构

工具名是扁平 snake_case 字符串，参数同样是 snake_case。与写操作有关的：

| 工具 | 参数 | 层内映射 |
| --- | --- | --- |
| edit | file_path / old_string / new_string / replace_all | operation=edit |
| write | file_path / content | operation=create |
| str_replace_editor | command / path / file_text / new_str / ... | operation=edit（标准装配里不启用） |
| read / read_image | file_path | 只读：不做前置授权，但**目标必须在受控项目内**，越界拒绝 |
| glob / grep | pattern / path | 只读：同上；未给 path 时按会话 cwd 判定范围，两者都证明不了就拒绝 |
| pwsh / bash | command / description / timeoutMs / workdir / run_in_background / sandbox_permissions / justification | 执行类，**Phase 4 已纳入受控链路**（注册表 exec.pwsh / exec.bash） |
| run_code | code / description | 执行类，**Phase 4 已纳入受控链路**（registry exec.run_code；平台侧 driver=none） |

**本版本没有独立的删除工具**：模型删文件只能通过 shell 或 run_code。
写类工具可选带 sandbox_permissions / justification，本 Adapter 不使用它们做判定。

### 2.5 Hook 超时与异常时 dsh 的默认行为

- hooks.json 里每个命令 hook 可以写 timeout（秒）；不写时用桥的 defaultTimeoutMs（默认 600000ms）；
- 超时后 dsh 杀掉 Hook 进程，得到"无退出码"，按**非阻断失败**处理——工具仍然执行；
- Hook 崩溃、命令写错、解释器找不到，同样是**非阻断失败**；
- hooks.json 本身读不到或语法错误时，dsh **不注册任何 hook** 并且不报错，
  Agent 照常启动——这是一条最危险的静默失效路径，因此运行期必须自检（见第 4 节）。

### 2.6 Windows 本地运行方式

- 可执行入口：dsh（npm shim 位于 ...\_npx\1e7f6d9597241db0\node_modules\.bin\dsh）；
- Hook 命令由 pwsh 以 -NoLogo -NoProfile -NonInteractive -Command 执行，因此命令按 PowerShell 语法写；
- 一次性任务：dsh --profile headless "任务描述"（答案写 stdout，退出码 0 完成 / 1 失败）；
  **没有** -p / --print / dsh run 这些写法；
- profile 层：$DSH_HOME/profiles/<name>/cordis.patch.yml，或用 --patch <file> 叠加一层而不改动别人的文件。

## 3. 接线方式

两层配置，缺一层都不会生效：

    # 第一层：把桥挂到 profile 上（examples/dsh/profile-patch.yml）
    dsh --profile headless --patch <patch.yml> "任务"

    # 第二层：patch 里 config.configPath 指向的 hooks.json（examples/dsh/hooks.json）
    {"hooks": {"PreToolUse": [{"hooks": [{"type": "command",
       "command": "python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml ...",
       "timeout": 30}]}]}}

**matcher 必须留空（匹配全部工具），不要写 edit|write。**
Hook 的 matcher 是 dsh 侧的过滤器：写成具体工具名，未列出的工具（包括 dsh 新版本新增的、
MCP 带来的写工具）就永远不会经过 Hook。过滤逻辑放在 Adapter 的工具表里，
因为只有它知道"未知工具"意味着什么。代价是每次工具调用都会起一个 Python 进程。

## 4. 失败关闭是怎么实现的

dsh 的放行语义（第 2.3、2.5 节）不能提供任何保证，所以本 Adapter 自己保证三件事：

1. **内部预算严格小于 dsh 超时**：hooks.json 写 timeout: 30（秒），adapter 配置写
   timeout_ms: 5000；策略判定超过内部预算就自己判 block。反过来的话 dsh 会先杀进程，
   而被杀等于放行。--hooks-config 会让运行期检查这条不等式，不满足直接阻断。
2. **任何异常都转成 exit 2**：进程入口捕获所有异常，绝不让解释器以退出码 1 结束。
3. **接线上线自检**：hooks.json 不存在 / 不可解析 / 没有指向 adapters.dsh.hooks /
   超时不等式不满足，都按阻断处理；**没有 --hooks-config 也算失败**（G12，见第 9.4 节），--self-check 是它的显式入口。

另有两条同源的规则：

- **未知工具失败关闭**：TOOL_TABLE 是白名单，未登记的工具（例如新版本新增的写工具、
  mcp__ 开头的 MCP 工具）一律阻断，并提示先更新工具表并补契约测试；
- **未知事件失败关闭**：非 PreToolUse 的事件一律拒绝，不猜测语义。

## 5. 显式上下文：不猜，声明不出来就拒绝

dsh 的载荷里有 session_id / cwd / tool_name / tool_input / tool_use_id，
但**没有** layer、language、project、principal、依赖列表。核心协议要求这些字段是显式的，
因此 Adapter 用一个可评审的配置文件提供它们（examples/dsh/dsh-adapter.yaml）：

| 字段 | 来源 | 缺失时的行为 |
| --- | --- | --- |
| file | 工具参数 + 载荷 cwd → 仓库相对路径 | 逃出 project_root 时拒绝 |
| operation | 工具表：edit=edit、write=create | 未登记的工具直接拒绝 |
| layer | 配置里的 layers（path → layer，按声明顺序取第一个命中） | 失败关闭（除非显式 default_layer） |
| language | 配置里的 languages | 命中不到且没有 default_language 时失败关闭 |
| dependencies | 本次变更文本里的顶层 import（词法提取，不做语义推断） | 无 import 时为空 |
| project / principal / trace_id | 配置 | 留空，绝不从文件名、目录或用户消息推断 |

关于 dependencies：预执行门禁问的是"这次改动引入了什么"，所以只看变更片段
（edit 的 new_string、write 的 content），而不是磁盘上已有的文件内容——
后者属于 Phase 4 的 post-execute 与 Phase 5 的 Validator。
edit 的 new_string 通常是代码片段而不是完整模块，因此用行级词法提取而不是 ast.parse。

## 6. 与 Phase 2 计划的偏差（都需要知道）

1. **新增 rules_root 配置项**：规则库与被治理项目常常不在同一个仓库，
   而 Loader 需要一个锚点来计算规则来源路径并拒绝越界文件。
   默认等于 project_root；规则来自外部规则库时必须显式声明。
2. **write 映射为 operation=create**：dsh 的 write 是 create-or-overwrite，一个字符串
   没法同时表达两种语义。映射到 create 意味着**只为 edit 声明 operation 的规则不会命中 write**；
   需要同时覆盖时把 operation 写成 [create, edit]（同维度多值 = OR）。
   这种"规则不命中"不会静默：skipped_rules 里会写出 operation 不匹配的原因。
3. **execute 类工具在 Phase 2 只记录不治理，Phase 4 起纳入受控链路。**
   Phase 2 把 pwsh / bash / run_code 登记为 Execute 并在审计里显式记 not_governed；
   Phase 4 把它们交给 Tool Registry（风险级别、参数白名单、命令白名单、权限、审批、限流），
   授权与具体 action_hash 绑定。只读工具（read / glob / grep）仍然"允许显式降级但仍记录"——
   这是写下来的策略，不是异常处理里的偷偷放行。
   降级的是**授权链路**，不是**范围校验**：注册表给只读工具声明了 `path_scope: workspace`，
   因此 Adapter 会把目标路径归一化后写进审计（范围等于项目根时记为 `.`），
   越界、穿越、或者既没有路径也没有 cwd 时一律失败关闭。
4. **matcher 留空**：与"最小权限"直觉相反，但原因见第 3 节——窄 matcher 会让新工具绕过 Hook。
5. **hooks.py 与 adapter.py 之外没有第三个模块**：配置解析、glob 匹配与依赖提取
   都放在 adapter.py，因为它们同属"把 dsh 事件规范化成核心协议"这一件事。

## 7. 实测偏差：外部命令桥在本机不能阻断

按官方接线方式（'@deepseek-ai/dsh-hooks-claude-code' + hooks.json）挂上后，本机实测的现象是：

1. Hook 进程**确实被调用**：审计 JSONL 里有完整记录（decision=block、exit_code=2、matched_rules=[ARCH-001@1]）；
2. 但**工具仍然执行了**：文件哈希从 53b53a25… 变成 ac615c45…，模型也没有看到任何阻断理由；
3. 把同一条 Hook 命令换成一句 exit 2 做最小复现，工具同样没有被阻断；
4. 在同一扩展点上，自建插件返回 {kind:'deny', reason} 时，工具被正确阻断，
   模型看到 Error: <reason>；
5. 用 node 直接调用该桥的 apply()（喂同一份 hooks.json）时，它确实注册了 tools/pre-execute，
   exit 2 也会被解码成阻断决策。

结论：问题出在"桥的 deny 没有传递到 dsh 的工具管线"这一段，**不在 Hook 命令、配置形状或退出码**。
可疑方向是 CLI 0.1.5-rc.1 与 Hook 包 0.1.5-rc.2 的版本错配；升级 dsh 后要重新验证。
因此本阶段采用 **src/adapters/dsh/policy-hook.plugin.mjs**：一个 30 行的进程内插件，
只把 tools/pre-execute 转发给同一条 Python Hook 命令，线协议完全不变
（stdin JSON、exit 0 放行、exit 2 阻断、stderr 即理由），并额外做了两件桥没做的事：

- ctx.shell 抛错（起不来、被杀、被沙箱拒绝）时返回 deny，而不是静默放行；
- 除 0 与 2 之外的退出码一律 deny（未知状态按失败关闭）。

复现这一整段的最小步骤：

    # 1) 准备受控项目与配置（自动生成）
    python tools/dsh_sandbox_loop.py --keep
    # 2) 用桥而不是插件重跑：把 .tmp/phase-2-sandbox/demo-shop/.policy/patch-plugin.yml
    #    换成上面注释里的 hooks-claude-code 版本，再执行
    dsh --profile headless --patch <patch.yml> "用 edit 工具在 src/shop/order_controller.py 的 import 区加一行 'from repository import OrderRepository'"
    # 3) 观察：.policy/audit.jsonl 里有 block 记录，但文件内容已经变了

### 7.1 受限沙箱里 Hook 起不来（Phase 7 期间定位，机制已确认）

在**受限沙箱**（禁止跨进程管道 stdio 的执行环境）里，本机闭环的表现是：
审计为空、文件哈希不变、dsh 退出码 0 —— 看起来像"什么都没发生"。逐层定位后的机制：

1. 插件从 `ctx.on('tools/pre-execute')` 拿到调用后，用 **`ctx.shell`** 运行 Hook 命令；
2. 而 dsh 的 shell 服务是用**管道 stdio** 捕获 Hook 的 stdin/stdout/stderr 的
   （证据：`@deepseek-ai/dsh-hook-protocol/lib/index.js` 的 `runHook` —— 它把序列化后的
   载荷交给 `bash.run(bash.resolve(request))`，再从 `result.stdout.text` 解码决策）；
3. 受限沙箱下 `spawn` 直接 EPERM（最小复现：Node 里 `spawnSync(python, …, {encoding:'utf-8'})`
   → `EPERM`；换成 `stdio:'inherit'` 或文件重定向则成功）；
4. 插件的 catch 把它翻译成 `{kind:'deny'}`（这是**正确的失败关闭**），于是模型的
   **每一次**工具调用都被拒——包括只读的 read/grep，会话只能退化成纯文本回答；
5. 没有任何 Hook 进程被启动过，因此审计文件根本不会出现。

**换接线方式绕不过去**：命令桥 `dsh-hooks-claude-code` 走的是同一个 `ctx.shell`
（同一个 `runHook`）。要在这类环境里跑闭环，只能在不受限的 shell 里执行：

    cd .tmp/phase-2-sandbox/demo-shop
    dsh --profile headless --patch .policy/patch.yml \
        "用 edit 工具在 src/shop/order_controller.py 的 import 区加一行 'from repository import OrderRepository'"

因此 `tools/dsh_sandbox_loop.py` 会把这种情况判成 **`skipped`（环境跳过，退出码 0）** 并写出
`reason` / `sandbox_blocked_spawn` / `reproduce` 三样东西：它既不把"跑不了"报成 pass
（那会伪造证据），也不把它报成 fail（那是环境限制，不是策略结论）。

## 8. Phase 4 追加的接线（受控执行）

Phase 4 之后，受控工具（写类 + 高权限执行类）在 Hook 里多走一段授权链：

    PreToolUse  载荷 → Tool Registry 解析工具 → Action Request（action_hash）
                → enforcement pre-check（主体/权限/参数白名单/命令白名单/审批/规则/限流/审计）
                → allow：签发短时效 grant（dsh 之后执行）→ 记录执行前基线
    PostToolUse 载荷 → 取回基线 → 收集执行后证据（哈希/diff/退出码）→ 验证 → 写终态

因此 adapter 配置新增三个必需项（缺任一项，受控工具一律阻断，而不是"规则没意见就放行"）：

    principal:            { subject: local-user, roles: [developer] }   # 主体只能显式声明
    registry:             <仓库>/registry/tool-registry.yaml            # 工具授权表（数据）
    registry_approved:    <仓库>/registry/tool-registry.approved.json   # 已审核哈希
    enforcement_ledger:   .policy/enforcement-ledger.jsonl              # 幂等 / 授权 / 限流台账（可选）
    approval_file:        .policy/approval.json                         # 高风险动作审批（可选）

两条与 Phase 2 不同的行为（都有回归用例）：

- **pwsh / bash / run_code 不再记 not_governed**：它们进入受控链路，默认没有 shell.exec 权限或没有
  绑定审批时直接阻断；未登记的工具（例如 workflow / str_replace_editor）一律 tool_not_registered；
- **PostToolUse 不再是"未支持事件"**：它成为事后验证入口，退出码 2 表示"这次执行的结果不可信、
  需要修复"（副作用无法撤销，dsh 只能把工具结果标成错误）。

## 9. 治理覆盖缺口修复（G2 / G3 / G11 / G12）

本轮修复的出发点是实测缺口清单（`docs/project/engineering-policy-platform/reviews/governance-coverage-gaps.md`）
与根因分析（同目录 `governance-remediation/00-remediation-plan.md` 的 R1）。四条都长在"两层之间有没有接上"
这条接缝上，因此每条都配了**会失败的检查**，而不是只改代码。

### 9.1 G2 · 事后钩子成对注册（R1）

**修前**：进程内插件只注册 `tools/pre-execute`，于是工具注册表为每个工具声明的 `post_checks`
从来没有被执行过（实测 26 次受治理动作的事后台账 0 条）。Python 侧其实是完整的
（hooks.py 的 `post_execute_outcome`、enforcement.py 的 `post`、postcheck 的逐项验证）——
缺的就是那一行注册，而且它不会让任何单侧测试变红。

**修后**：`policy-hook.plugin.mjs` 同时注册两个事件。真实 API 签名（已核对本机 dsh 0.1.6-alpha.2 的
`@deepseek-ai/dsh-hooks-claude-code/lib/index.js:251-294`）：

    ctx.on('tools/pre-execute',  async (exec, next) => …)           // 返回 {kind:'deny', reason}
    ctx.on('tools/post-execute', async (exec, result, next) => …)   // 返回 {kind:'block', feedback:[{type:'text',text}]}

- pre 阶段：exit 2 → `{kind:'deny'}`，工具不执行；
- post 阶段：副作用已经发生，只能用 `{kind:'block', feedback}` 把这次工具结果**标成错误**，
  语义是"结果不可信 / 需要修复"，与 hooks.py 的 exit 2 语义一致，绝不假装回滚；
- post 载荷带 `tool_response`（content blocks 折叠成文本，超过 4000 字符截断并在文本里标注）
  与 `tool_use_id`，字段口径与 Python 侧 `enforcement.post_event_fields()` 一致；
- 审计与台账里，每次调用都带 `hook_event`（PreToolUse / PostToolUse）与 `action_id`，
  于是"成对"这件事可以在一份产物上直接判定。

**会失败的检查**：

- `tests/contract/test_policy_hook_chain.py::test_the_plugin_registers_pre_and_post_together`
  （源码级成对断言）与 `::test_the_plugin_forwards_post_execute_with_the_tool_response`
  （真实 node + 可注入的假 ctx，观察注册表与转发载荷）；
- `::test_an_allowed_governed_edit_leaves_both_pre_and_post_stages`：跑真实 pre + post 两段，
  在 audit.jsonl 与 enforcement-ledger.jsonl 上断言**任一放行的受治理动作必须同时有 pre 与 post**，
  且 post 必须走到 `post_validated` 终态；`::test_the_pairing_check_itself_can_fail`
  证明这条检查本身会红（只有 pre、没有 post 的动作会被点出来）。

### 9.2 G3 · 跳过可见性（只标注，不接 Phase 5 流水线）

受治理动作的审计记录（**只增不改**）新增：

| 字段 | 含义 |
| --- | --- |
| `effective_rule_count` | 本次**真的参与判定**的规则数（总规则数 - 跳过数） |
| `skipped_rule_count` | 被跳过的规则数（**跳过 ≠ 通过**） |
| `skipped_reason` | 跳过原因按 checker 归类，例如 `{"style_lint": 39}` |
| `checker_scope` / `checker_scope_note` | pre-execute 路径只做文本类 checker（`policy.checkers.CONTEXT_CHECKERS`） |
| `skipped_rule_ids_unknown` | 跳过名单里出现"规则集里没有"的 rule_id（不能静默消失） |

没有文件维度的受控动作（pwsh / run_code 等）写 `effective_rule_count: 0` +
`skipped_reason: {"phase1_not_applicable": N}`：Phase 1 一条规则都没跑，不留空让人误读成"查过了"。
既有字段（`matched_rules` / `skipped_rules` / …）与 `AUDIT_SCHEMA_VERSION = "1.0"` 一律不动。

**会失败的检查**：`tests/unit/test_hook_skip_visibility.py`（确定性单测 + 真实产物的字段断言，
含"既有字段只增不改"的清单与 `skipped_reason` 归类）。

### 9.3 G11 · 注入留痕（如实标注为近似）

会进入 AI 上下文的项目约定文档（`CONTEXT_DOCUMENTS = ("AGENTS.md", "CLAUDE.md")`）的来源路径 +
sha256，在**会话内第一次 Hook 调用**时写一条 `reason_code: "context_injection"` 的记录
（每会话一次，靠 `AuditLedger.has_record` 去重；它追加在判定记录之后，因此"首行 = 本次判定"
这条既有约定不变）。

- 只按显式声明的文件名在项目根查找：不扫目录，也不从内容推断"它算不算项目约定"；
- 读不到的文档显式写 `present: false`——"没有这个文件"同样是一条要写下来的结论；
- 记录里 `approximate: true` + note 明说：dsh 的 SessionStart 没有接到本 Hook，
  这是"本会话第一次工具调用"这个时刻，**不是真实注入时刻**；本轮也不做注入内容的策略校验
  （载荷里没有"注入了什么"的事实，猜一份再判它等于把推断当证据）。

**会失败的检查**：`test_the_session_records_which_context_documents_are_in_play`（哈希、present
与"排在判定之后"的断言）与 `test_the_injection_record_is_written_once_per_session`。

### 9.4 G12 · 接线自检缺席 = 失败关闭

`check_wiring()` 在 `hooks_config_path is None` 时**返回错误**（修前返回空串 = 通过）。
CLI 是生产入口，`main()` 默认 `allow_unverified_wiring=False`：缺 `--hooks-config`
的 Hook 命令会被判 `wiring_error` 并以退出码 2 阻断每一次工具调用，而不是静默放行。
唯一的出路是显式命名的 `--allow-unverified-wiring`（默认关闭；用它本身应当在证据里写明）。

库内调用 `run_hook(..., allow_unverified_wiring=True)` 是**显式的**默认宽松：它服务于集成测试、
学习手册与探针（它们不是"由 Agent 运行时启动的 Hook 进程"），生产入口不宽松。这条不对称是刻意的，
理由与代价写在 `hooks.py::run_hook` 的 docstring 里。

插件侧的同一契约：exit 非 0 非 2 一律拒绝；`ctx.shell` 抛错（起不来 / 被杀 / 被沙箱拒）也一律拒绝。

**会失败的检查**：`test_self_check_without_hooks_config_is_fail_closed`、
`test_the_only_way_out_is_the_named_waiver`、
`test_a_hook_call_without_hooks_config_blocks_instead_of_allowing`、
`test_the_plugin_denies_every_non_zero_non_two_exit_code_and_every_spawn_failure`
（均在 `tests/contract/test_policy_hook_chain.py`）。

## 10. 复现命令

    # 契约测试（fixture → PolicyContext）
    python -m pytest tests/contract/test_dsh_adapter.py -q

    # Hook 行为测试（假执行器：block 0 次 / allow 1 次 / 超时 / 重放 / 脱敏 / CLI）
    python -m pytest tests/integration/test_dsh_hook.py -q

    # 接线自检（放行时 stdout 与 stderr 都必须干净）
    python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml \
        --hooks-config .policy/hooks.json --self-check

    # Phase 4：受控执行链路（注册表 / 授权 / 台账 / 审计 / 事后验证）
    python -m pytest tests/integration/test_dsh_enforcement.py -q

    # G2 / G12：成对契约（真插件 + 假 ctx、真实产物、CLI 失败关闭）
    python -m pytest tests/contract/test_policy_hook_chain.py -q

    # G3 / G11：跳过可见性与注入留痕的审计字段
    python -m pytest tests/unit/test_hook_skip_visibility.py -q

    # 审计里必须能看到成对阶段（hook_event）与"查了几条规则"
    python -c "import json,pathlib; [print(r.get('hook_event'), r.get('reason_code'), r.get('effective_rule_count'), r.get('skipped_rule_count')) for r in map(json.loads, pathlib.Path('.policy/audit.jsonl').read_text(encoding='utf-8').splitlines())]"

    # 真实沙箱闭环（受控临时项目，不连接生产仓库与真实凭据）
    python tools/dsh_sandbox_loop.py
    dsh --profile headless --patch <patch.yml> "用 edit 工具修改 src/shop/order_controller.py"

沙箱闭环的完整步骤、断言与观测结果见 docs/project/engineering-policy-platform/phases/phase-2-dsh-adapter.md
的"实施记录"一节。
