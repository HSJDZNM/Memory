# Phase 2 对象与关系：dsh Adapter

本文回答三个问题：**Phase 2 做了什么、系统里多了哪些对象、它们之间是什么关系**。
内容与仓库代码一致，每个对象都能在源码里找到对应定义。

对照阅读：

- 设计文档：[../../engineering-policy-platform/phases/phase-2-dsh-adapter.md](../../engineering-policy-platform/phases/phase-2-dsh-adapter.md)
- 前置调查与实测记录：[../../../src/adapters/dsh/README.md](../../../../src/adapters/dsh/README.md)
- 脱敏事件 fixture：[../../../tests/fixtures/agent_events/dsh/README.md](../../../../tests/fixtures/agent_events/dsh/README.md)
- 可执行讲解：[walkthrough.ipynb](walkthrough.ipynb) / [walkthrough.py](walkthrough.py)

---

## 一、任务内容

一句话目标：**让一个真实 Agent Runtime（dsh）第一次使用 Policy Engine，同时保持核心层不知道 dsh 的存在。**

完整链路：

    dsh PreToolUse 事件（stdin 上的 JSON）
      -> Adapter：验证 -> 字段规范化 -> PolicyEvent -> PolicyContext
      -> Policy Engine：ValidationResult
      -> allow：放行（exit 0，执行器恰好被调用一次）
      -> block：结构化违规（exit 2，执行器一次都不调用）

拆成六项可验收的具体工作（对应设计文档的六个开发步骤）：

| # | 工作 | 产物 | 可观察结果 |
| --- | --- | --- | --- |
| 1 | 保存最小原始事件 fixture | `tests/fixtures/agent_events/dsh/` | 10 个脱敏载荷，标注 dsh 版本与采集方式 |
| 2 | 纯映射 Adapter | `src/adapters/dsh/adapter.py` | 事件 -> PolicyEvent / PolicyContext，未知一律拒绝 |
| 3 | ControlledExecutor fake | `tests/integration/test_dsh_hook.py` | block 路径 0 次、allow 路径恰好 1 次 |
| 4 | pre-execute Hook | `src/adapters/dsh/hooks.py` | exit 0 放行、exit 2 阻断、任何异常都转成 2 |
| 5 | Agent 反馈 | `hooks.feedback_text` + `hooks.sanitize` | 规则 ID、级别、原因、证据、修复方向；无堆栈/绝对路径/密钥 |
| 6 | 真实沙箱闭环 | `tools/dsh_sandbox_loop.py` | 请求改坏文件被阻断，文件哈希不变 |

### Phase 2 相对 Phase 1 的新增（行为差异）

| 项 | Phase 0 / Phase 1 | Phase 2 | 理由 |
| --- | --- | --- | --- |
| 上下文来源 | 调用方显式传参（CLI / 测试） | dsh 事件 + adapter 配置声明 | 事件里没有的字段只能声明，不能推断 |
| layer / language | CLI 的 `--layer` / `--language` | 配置里的 `layers` / `languages` | 声明不命中 = 配置缺陷，失败关闭 |
| 决策之后 | 打印 + 退出码 | 执行或阻断（ControlledExecutor） | 策略第一次获得行为控制能力 |
| 失败语义 | 退出码 2 = 配置或执行错误 | **任何异常都转成 exit 2** | dsh 把崩溃、超时、非 0/2 都当"非阻断失败" |
| 事件来源 | 人手构造的上下文 | 脱敏的真实载荷 + 沙箱采集 | 契约必须来自实测，不能来自旧文档 |
| 新对象 | — | AdapterConfig、PolicyEvent、HookOutcome、AuditLedger … | 见第二节 |

本阶段**核心层一行未改**：`src/policy/` 仍然不 import 任何 Agent 类型。

---

## 二、对象清单

系统里的对象分五族：输入侧（事件与配置）、映射侧（纯函数与产物）、Hook 运行侧、审计与反馈、复用的核心层。

### 族 1：输入侧 —— dsh 事件与 adapter 配置

| 对象 | 类型 | 字段 | 说明 |
| --- | --- | --- | --- |
| dsh 事件载荷 | 映射（线协议） | session_id、transcript_path、cwd、hook_event_name、tool_name、tool_input、tool_use_id | 由 dsh 写在 Hook 的 stdin 上；**没有** layer/language/principal/依赖列表 |
| `AdapterConfig` | dataclass(frozen) | project_root、rule_dirs、agent_version、project、timeout_ms、layers、default_layer、languages、default_language、principal、trace_id、audit_log、rules_root、config_path，以及 Phase 4 的 registry_path、registry_approved_path、enforcement_ledger、approval_file | 显式上下文的唯一来源 |
| `LayerRule` | dataclass(frozen) | pattern、layer | path -> layer 的声明（glob，按声明顺序取第一个命中） |
| `LanguageRule` | dataclass(frozen) | pattern、language | path -> language 的声明 |
| `Principal` | 核心模型 | subject、roles | 只能由配置声明；事件里塞进来的主体信息被忽略 |

### 族 2：映射侧 —— 纯函数与产物

| 对象 | 类型 | 字段 | 说明 |
| --- | --- | --- | --- |
| `ToolSpec` | dataclass(frozen) | name、kind、operation、path_field、proposed_fields、note | 一个 dsh 工具的映射规格 |
| `ToolKind` | 枚举 | write / read_only / execute / no_file | 决定"是否构建上下文并评估策略"，不决定严重级别 |
| `TOOL_TABLE` | 映射 | 工具名 -> ToolSpec（31 项） | **白名单**：不在表里一律拒绝 |
| `PolicyEvent` | dataclass(frozen) | event_id、request_id、kind、agent、agent_version、tool、operation、file、layer、language、dependencies、payload_digest、payload_fields、session_id、cwd、trace_id | 规范化后的标准事件（tool.pre_execute） |
| `AdapterDecision` | dataclass(frozen) | governed、reason、event? | 是否受治理 + 原因 +（受治理时的）事件 |
| `DshEventError` | 异常 | — | 协议不符或配置不足以安全判定：一律失败关闭 |

关键函数（都在 `adapter.py`）：

| 函数 | 输入 -> 输出 | 职责 |
| --- | --- | --- |
| `read_payload` | 任意 JSON -> 映射 | 校验形状：必需字段齐全、类型正确、事件白名单 |
| `to_policy_event` | 载荷 + 配置 -> AdapterDecision | 工具表查询、路径归一、layer/language 解析、依赖提取 |
| `to_policy_context` | PolicyEvent + 配置 -> PolicyContext | 只搬运显式字段；module 刻意留空 |
| `proposed_dependencies` | 变更文本 -> 元组 | 行级词法提取顶层 import（不做语义推断） |
| `glob_match` | pattern + 仓库相对路径 -> bool | 双星跨目录、单星不跨目录、问号单字符 |
| `config_from_mapping` / `load_config` | YAML -> AdapterConfig | 拒绝未知字段、重复键、非正数超时 |

### 族 3：Hook 运行侧

| 对象 | 类型 | 字段 / 方法 | 说明 |
| --- | --- | --- | --- |
| `DshPreExecuteHook` | dataclass | config、rules、executor、evaluator、clock、ledger、capture_dir、handle(raw) | Adapter -> Engine -> 执行或阻断 |
| `ControlledExecutor` | Protocol | execute(event) -> ExecutionOutcome | 只在 allow 之后被调用，且至多一次 |
| `NullExecutor` | 类 | execute(event) | 生产执行器：Phase 2 里工具由 dsh 执行，放行即"允许执行一次" |
| `ExecutionOutcome` | dataclass(frozen) | status（executed / delegated / failed）、detail | 一次执行器调用的结果 |
| `HookOutcome` | dataclass(frozen) | exit_code、reason_code、stderr、stdout、decision、event、executed、elapsed_ms | 一次 Hook 处理的完整结果 |
| `PolicyTimeout` | 异常 | — | 判定超出内部预算（daemon 线程 + join(timeout)） |
| `run_hook` | 函数 | 载荷 + 配置路径 -> HookOutcome | 装配并执行一次调用；测试与 CLI 共用 |
| `check_wiring` | 函数 | config + hooks.json -> 错误文本 | 接线自检：文件存在、命令指向本 Hook、超时不等式 |
| `main` / `build_parser` | 进程入口 | — | 读 stdin、写 stderr、返回 0 或 2 |

### 族 4：审计与反馈

| 对象 | 类型 | 字段 / 方法 | 说明 |
| --- | --- | --- | --- |
| `AuditLedger` | 类 | path、lookup(event_id)、append(record) | 追加写 JSONL；同时充当幂等台账 |
| 审计记录 | JSONL 行 | audit_schema_version、timestamp、event_id、request_id、tool、operation、file、layer、language、dependencies、payload_digest、payload_fields、governed、decision、reason_code、exit_code、executed、elapsed_ms、matched_rules、skipped_rules、rule_set_hash | 只写摘要与结论，不写参数原文与源码 |
| `feedback_text` | 函数 | reason_code、event、decision、detail -> 文本 | 给模型的理由：规则、级别、证据、期望修复方向 |
| `sanitize` | 函数 | text、project_root、limit | 绝对路径换占位符、密钥样式打码、截断到 4000 字符 |

### 族 5：复用的核心层与接线产物

| 对象 | 位置 | 在 Phase 2 里的角色 |
| --- | --- | --- |
| `RuleSet` / `Rule` / `ValidationResult` / `Decision` / `Operation` | `src/policy/` | 策略判定；Phase 2 未改动核心层 |
| `repo_relative_path` | `policy/context.py` | 把绝对路径/反斜杠路径归一成仓库相对路径，越界即拒绝 |
| `load_rule_set` | `policy/loader.py` | 按 `rule_anchor` 加载规则（规则库可与被治理项目分离） |
| hooks.json / profile patch | `examples/dsh/` | 官方接线方式：把 dsh 的 Hook 桥指向 CLI |
| `policy-hook.plugin.mjs` | `src/adapters/dsh/` | 进程内插件：同一条线协议，替代官方桥完成 deny 传递 |
| fixture | `tests/fixtures/agent_events/dsh/` | 脱敏真实载荷，契约测试与手册共用 |

---

## 三、关系

### 3.1 组成关系

    dsh 事件载荷（JSON）                      AdapterConfig（YAML）
    |- session_id / tool_use_id               |- project_root / rules_root / rule_dirs
    |- hook_event_name                        |- layers    (n) -> LayerRule    {pattern, layer}
    |- tool_name / tool_input                 |- languages (n) -> LanguageRule {pattern, language}
    |- cwd（路径解析基准）                     |- default_layer / default_language
    |- transcript_path（恒为空串）             |- principal / trace_id / audit_log / timeout_ms

    AdapterDecision                           PolicyEvent
    |- governed (bool)                        |- event_id = session_id + ":" + tool_use_id
    |- reason (str)                           |- kind = "tool.pre_execute"
    |- event? -> PolicyEvent                  |- agent = "dsh"（版本单独记录）
                                              |- tool / operation（来自 ToolSpec）
                                              |- file（仓库相对路径）
                                              |- layer / language（来自配置）
                                              |- dependencies（来自变更文本）
                                              |- payload_digest / payload_fields

    DshPreExecuteHook                         HookOutcome
    |- config / rules                         |- exit_code (0 / 2)
    |- executor -> ControlledExecutor         |- reason_code
    |- ledger   -> AuditLedger                |- stderr（给模型的理由）
    |- evaluator（默认 policy.evaluate）       |- decision -> ValidationResult
    |- capture_dir                            |- event / executed / elapsed_ms

### 3.2 一次工具调用的流向

    dsh 想调用某个工具
       |  组装 PreToolUse 载荷（或由进程内插件组装）写到 Hook 进程的 stdin
       v
    read_payload            必需字段齐全？事件在白名单里？载荷类型正确？
       |  否 -> DshEventError -> 阻断（context_error）
       v
    to_policy_event         TOOL_TABLE 查工具；路径 -> 仓库相对路径；layer/language 查配置
       |  未知工具 / 缺路径 / 逃出 project_root / 没有声明 -> DshEventError -> 阻断
       |  已知但非写类工具 -> governed=False
       |    只读 -> 放行并记 not_governed（显式降级）
       |    执行类 -> 交给 Phase 4 门禁（注册表 / 权限 / 审批），拒绝则阻断
       v
    PolicyEvent -> to_policy_context -> PolicyContext
       |  AuditLedger.lookup(event_id)：已在台账里？ -> 阻断（event_replay / event_id_reuse）
       v
    _evaluate_with_budget(evaluate, rules, context, timeout_ms)
       |  超出预算 -> PolicyTimeout -> 阻断（policy_timeout）
       |  未知 decision 值 -> 阻断（unknown_decision）
       v
    ValidationResult
       |  block            -> 不调用执行器，exit 2，stderr = feedback_text(...)
       |  allow / warnings -> Phase 4 门禁（写类工具）-> 通过才继续
       |                      executor.execute(event) 恰好一次，exit 0
       v
    AuditLedger.append(摘要 + 结论) -> 进程以 0 或 2 退出

### 3.3 必须成立的不变量

| 不变量 | 含义 | 由谁保证 |
| --- | --- | --- |
| 纯映射 | Adapter 不加载规则、不决定 severity、不调用工具、不读文件内容、不访问网络 | `adapter.py` 的导入与职责边界 |
| 显式上下文 | layer / language / principal / module 只来自配置 | `AdapterConfig` 与 `to_policy_event` 的失败关闭 |
| 未知即失败关闭 | 未知工具、未知事件、缺字段、缺声明、未知决策值全部阻断 | `read_payload` / `to_policy_event` / `DshPreExecuteHook.handle` |
| 至多一次执行 | block 路径 0 次；allow 路径恰好 1 次；重放不产生第二次执行 | `DshPreExecuteHook._decide` + `AuditLedger` |
| 进程契约 | 放行时 stdout 为空；所有诊断写 stderr；退出码只用 0 与 2 | `hooks.main` |
| 不落原文 | 审计只有摘要、结论与规则身份；反馈不含堆栈、绝对路径、密钥 | `_payload_digest` / `sanitize` |
| 确定性 | 同一载荷两次映射得到同一个事件与同一个上下文 | `to_policy_event` 的稳定排序与摘要 |
| 核心层独立 | `src/policy/` 不 import dsh，也不 import `adapters` | 依赖方向：只有 `src/adapters/dsh/` 向下依赖核心层 |

---

## 四、边界与已知取舍

### 4.1 本阶段不做什么

| 不做 | 原因 | 何时做 |
| --- | --- | --- |
| 知识检索 / 向量库 | 先有确定性的行为控制，再谈知识 | Phase 3 |
| 真实工具执行与回滚 | 执行器必须绑定已授权的决策 | Phase 4（Hook 只授权，执行仍由 Agent 运行时完成） |
| AST / Lint / 类型检查 | 确定性代码证据属于验证器 | Phase 5 |
| MCP 工具与多 Agent 适配 | 工具表现在是白名单，MCP 需要声明式扩展 | Phase 6 |
| HTTP 服务 | 还没有进程外共享的需求 | Phase 7 |
| 让 Hook 自己改文件 | 放行就是"允许 dsh 执行一次"，Hook 不越权 | 不打算做 |
| 把规则写进 Prompt | 规则是数据，不是提示词 | 永不 |

### 4.2 明确写下来的取舍

1. **write 映射成 create**：dsh 的 write 是 create-or-overwrite，一个字符串表达不了两种语义。
   代价是"只为 edit 声明 operation 的规则不会命中 write"；需要同时覆盖时把 operation
   写成 `[create, edit]`（同维度多值 = OR）。代价是可见的：skipped_rules 会写出原因。
2. **执行类工具在 Adapter 层只认类别，判断交给 Phase 4**：pwsh / bash / run_code / workflow 的
   `kind=execute`，Hook 会把它们交给 Tool Registry 的执行前授权（注册表 / 权限 / 参数与命令白名单 /
   审批），Adapter 自己不做这类判断，也不假装检查过。
3. **matcher 留空**：Hook 的 matcher 写成具体工具名，新工具就永远不经过 Hook。
   过滤逻辑放在工具表里，因为只有它知道"未知工具"意味着什么。代价是每次工具调用都要起进程。
4. **module 留空、principal 只来自配置**：猜错模块会让规则在错误范围生效；
   主体（以及角色）只能显式声明，配错就等于没有权限——Phase 4 的门禁正是用它决定授权。
5. **两个阶段各管一半**：PreToolUse 负责授权（并留下执行前基线），PostToolUse 负责事后验证——
   副作用已经发生时它只能把结果标成「需要修复」（exit 2），**不会声称回滚成功**；
   语义不明的事件仍然一律拒绝，不猜测。
6. **失败关闭优先于可用性**：超时、崩溃、配置读不到都会让写操作被阻断。
   这会让误伤变多，但 dsh 侧的默认语义是"存活即放行"，方向不能反。
7. **进程内插件替代官方桥**：本机实测官方 `dsh-hooks-claude-code` 桥的 deny 没有传递到
   工具管线（证据见 `src/adapters/dsh/README.md` 第 7 节），因此沙箱闭环改用
   `policy-hook.plugin.mjs`。**线协议没有变**：Adapter 与 Hook 的契约、退出码语义、
   stderr 内容一个字都没改，变的只是"谁把事件递过来"。

### 4.3 后续阶段可以直接依赖的稳定契约

- `adapters.dsh.adapter.to_policy_event` / `to_policy_context`：任何 Agent 适配器都可以照着实现；
- `adapters.dsh.hooks.run_hook`：一次 Hook 调用的完整装配，测试与 CLI 共用；
- `HookOutcome`：allow / block 的唯一表示（exit_code + reason_code + stderr）；
- 审计 JSONL 的字段名与 `audit_schema_version`：证据与幂等台账的共同格式；
- 进程契约：`exit 0` 放行且 stdout 为空、`exit 2` 阻断且 stderr 即理由；
- `AdapterConfig` 的字段名：配置是唯一可评审的上下文来源。
