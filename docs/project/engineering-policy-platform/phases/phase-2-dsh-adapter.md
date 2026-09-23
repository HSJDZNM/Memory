# Phase 2：dsh Adapter

## 目标

让一个真实 Agent Runtime 首次使用 Policy Engine，同时保持核心层不知道 dsh 的存在。先完成事件适配和 pre-check，再考虑任何 RAG 能力。

## 前置调查

实现前先在当前 dsh 版本上确认并记录：

1. 可用的 Extension / Hook 事件名称；
2. 事件是在工具参数确定前还是执行后触发；
3. 阻止工具的官方返回协议；
4. edit/write/delete/shell/git 等工具的实际参数结构；
5. Hook 超时和异常时 dsh 的默认行为；
6. 当前 Windows 本地运行方式。

调查结论固化为 Adapter README 和脱敏事件 fixture。不要根据旧文档猜接口。

## 计划结构

```text
src/adapters/dsh/__init__.py
src/adapters/dsh/adapter.py
src/adapters/dsh/hooks.py
tests/fixtures/agent_events/dsh/
tests/contract/test_dsh_adapter.py
tests/integration/test_dsh_hook.py
```

## 开发步骤

### 1. 保存最小原始事件 fixture

为每种目标工具保存 allow 与 block 场景，只保留协议字段并删除用户数据、绝对路径和密钥。fixture 标注 dsh 版本。

### 2. 实现纯映射 Adapter

Adapter 只完成：

```text
dsh Event → 验证 → 字段规范化 → PolicyEvent / PolicyContext
```

它不加载规则、不决定 severity、不调用工具、不拼接 Prompt。

### 3. 建立 ControlledExecutor fake

在测试中使用记录调用次数与参数的 fake executor。所有 pre-check 测试先证明 block 路径调用次数为 0，再接真实 dsh Hook。

### 4. 实现 pre-execute Hook

```text
dsh tool request
  → Adapter
  → Policy Engine
  → allow: 调用一次执行器
  → block: 返回结构化违规，不执行
```

Policy Engine 异常、上下文缺失或未知工具默认阻止写操作，并返回可诊断错误。

### 5. 设计 Agent 反馈

反馈包含规则 ID、严重级别、违规原因、相关证据和期望修复方向。不要把内部堆栈、绝对路径、完整规则库或敏感上下文返回给模型。

### 6. 在沙箱运行一个真实闭环

让 dsh 分别请求修改 good/bad 示例文件。只在受控临时项目中验证，不连接生产仓库或真实凭据。

## 测试步骤

### Adapter 契约测试

- edit 事件映射为 `operation=edit` 和规范化文件路径；
- agent 固定标识为 `dsh`，版本单独记录；
- request/trace/principal 字段完整保留；
- 未知事件、未知工具和缺失路径被拒绝；
- 额外载荷不进入核心模型；
- 同一个 event ID 重放得到相同上下文。

### Hook 行为测试

- block：executor 调用 0 次；
- allow：executor 调用 1 次且参数未被 Adapter 改写；
- Policy 超时：写操作不执行；
- Engine 返回未知 decision：不执行；
- Hook 重试相同 event ID：不重复执行；
- 错误反馈不包含绝对路径、密钥模式或内部堆栈。

### 真实集成测试

1. 启动受控 dsh 环境；
2. 发起 bad controller 编辑；
3. 确认文件哈希未变化并收到 `ARCH-001`；
4. 发起 good controller 编辑；
5. 确认只发生一次预期变更；
6. 关联原始事件、Policy Decision 和文件哈希。

## 观察点

重点观察“模型想调用工具”与“工具获准执行”是两个独立事实。此阶段第一次获得行为控制能力，而不只是 Prompt 建议。

## 退出条件

- dsh 版本和 Hook 契约有本地文档与 fixture；
- block/allow/timeout/replay 路径全部有自动化测试；
- 一个真实 dsh 沙箱流程通过；
- 核心 `src/policy` 不依赖 dsh；
- 仍未引入 RAG、API 或多 Agent 框架。

通过后进入 [Phase 3](phase-3-retrieval.md)。

---

## 实施记录（2026-09，Phase 2 已完成）

本节记录实际落地的接口、命令与偏差，避免文档与代码漂移。原始计划保留在上文。

### 前置调查：把 dsh 的 Hook 契约钉死

调查结论固化在 [src/adapters/dsh/README.md](../../../../src/adapters/dsh/README.md)，要点：

| 调查项 | 结论（dsh 0.1.5-rc.1 / Hook 包 0.1.5-rc.2） |
| --- | --- |
| Hook 事件 | dsh 没有自己的 hook 事件，靠两个方言桥复用 Claude Code / Codex 的 hooks.json；CC 方言支持 SessionStart / UserPromptSubmit / PreToolUse / PostToolUse / Stop / SubagentStart / SubagentStop |
| 触发时机 | PreToolUse ← tools/pre-execute：参数已解析、尚未执行；PostToolUse ← tools/post-execute：已执行，副作用不可撤销 |
| 阻断协议 | 外部命令的 **exit 2 = 阻断**（stderr 作为理由显示给模型）；其他非 0、启动失败、被超时杀掉，dsh 一律视为**非阻断失败**——工具照常执行 |
| 结构化阻断 | `{"decision":"block","reason":"..."}`，或 `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"..."}}`（hookEventName 必须等于当前事件名，否则整块被丢弃） |
| 工具参数 | 扁平 snake_case 工具名与参数：edit(file_path/old_string/new_string)、write(file_path/content)、read、pwsh(command/description/…)；pre-execute 拿到的是**未解析的原始路径**，基准是载荷里的 cwd |
| 超时 | hooks.json 里 timeout（秒），不写则用桥的 defaultTimeoutMs（默认 600000ms） |
| 本地运行 | Hook 命令由 pwsh 执行；一次性任务用 dsh --profile headless "任务"；用 --patch 叠加一层而不改动别人的 profile |

**最危险的一条**：hooks.json 读不到或语法错误时，dsh 不注册任何 hook、也不报错，Agent 照常启动。
"没有治理"和"治理通过"在外部看完全一样——这直接决定了下面第 4 步的设计。

### 实际新增与变化

| 位置 | 内容 |
| --- | --- |
| src/adapters/dsh/adapter.py | 新增：纯映射（dsh Event → PolicyEvent / PolicyContext）、TOOL_TABLE、显式 layer/language 声明、变更文本的依赖提取 |
| src/adapters/dsh/hooks.py | 新增：pre-execute Hook、ControlledExecutor 端口、JSONL 审计与幂等台账、失败关闭、CLI 入口 |
| src/adapters/dsh/policy-hook.plugin.mjs | 新增：进程内 shim 插件，把 tools/pre-execute 转发给 Python Hook（原因见下文偏差 1） |
| src/adapters/dsh/README.md | 新增：前置调查结论与接线说明 |
| tests/fixtures/agent_events/dsh/ | 新增：10 份脱敏真实事件 + 版本与更新规则说明 |
| tests/contract/test_dsh_adapter.py | 新增：26 个映射契约用例 |
| tests/integration/test_dsh_hook.py | 新增：24 个 Hook 行为用例（含真实子进程 CLI） |
| examples/dsh/ | 新增：hooks.json、dsh-adapter.yaml、profile-patch.yml |
| tools/dsh_sandbox_loop.py | 新增：可重放的真实 dsh 沙箱闭环 |
| tools/phase_evidence.py | CURRENT_PHASE=2，新增 agent_adapter 与 sandbox_loop 段 |

### 与原始计划的偏差（都需要知道）

1. **外部命令 Hook 的阻断在本机 dsh 上不生效，改用进程内 shim 插件转发。**
   实测：用 @deepseek-ai/dsh-hooks-claude-code 桥挂上 hooks.json 后，
   Hook 进程确实被调用（审计文件里有完整记录、退出码 2），但**工具仍然执行了**：
   文件哈希从 53B53A25… 变成 AC615C45…，模型也没有看到任何阻断理由。
   同一扩展点上自建的 30 行插件返回 permissionDecision 等价的 {kind:'deny', reason} 时，
   工具被正确阻断（模型看到 Error: …）。因此本阶段采用：
   **进程内插件只做转发，策略判定仍然全部在 Python Hook 里**——
   adapter/hooks 一行未改，线协议（stdin JSON、exit 2、stderr 理由）完全一致。
   桥的失败原因尚未定论（CLI 0.1.5-rc.1 与 Hook 包 0.1.5-rc.2 存在版本错配），
   已在 src/adapters/dsh/README.md 第 7 节记录复现步骤与最小实验。
2. **新增 rules_root 配置项**：规则库与被治理项目常常不在同一个仓库，而 Loader 需要一个
   锚点来计算规则来源路径并拒绝越界文件；默认等于 project_root。
3. **write 映射为 operation=create**：dsh 的 write 是 create-or-overwrite，一个字符串无法
   同时表达两种语义。只为 edit 声明 operation 的规则不会命中 write；需要同时覆盖时写
   operation: [create, edit]（同维度多值 = OR），且不命中会在 skipped_rules 里说明原因。
4. **execute 类工具（pwsh / bash / run_code）只记录不治理**：按阶段划分属于 Phase 4；
   审计里逐条记 not_governed，不假装检查过。
5. **Hook 的 matcher 必须留空（匹配全部工具）**：写成 edit|write 会让未列出的工具
   （含新版本新增的、MCP 带来的写工具）绕过 Hook。过滤放在 Adapter 的工具表里，
   因为只有它知道"未知工具"意味着什么。代价是每次工具调用起一个 Python 进程。

### 失败关闭是怎么实现的

dsh 的放行语义（超时/崩溃=放行、配置缺失=零 hook）不能提供任何保证，所以由 Hook 自己保证：

1. **内部预算 < dsh 超时**：hooks.json 写 timeout: 30（秒），adapter 配置写 timeout_ms: 5000；
   超预算自己判 block。--hooks-config 会在运行期检查这条不等式，不满足直接阻断；
2. **任何异常都转成 exit 2**：进程入口捕获所有异常，绝不让解释器以退出码 1 结束；
3. **接线自检**：hooks.json 不存在 / 不可解析 / 没有指向 adapters.dsh.hooks / 超时不等式不满足，
   都按阻断处理（python -m adapters.dsh.hooks --self-check）；
   同理，shim 插件在 ctx.shell 抛错（起不来、被杀、被沙箱拒绝）时也返回 deny；
4. **未知事件、未知工具、缺路径、缺少 layer 映射一律拒绝**，并给出可诊断信息。

### 真实沙箱闭环（受控临时项目，不接生产仓库与真实凭据）

工具：tools/dsh_sandbox_loop.py（可被另一位开发者重放）。项目在 .tmp/phase-2-sandbox/demo-shop，
规则用仓库真实 policies/，Hook 用 examples 里的同一套配置。

> 最近一次重放（`python tools/dsh_sandbox_loop.py`，退出码 0）的结构化结论保存在
> `.tmp/artifacts/phase-2-sandbox-result.json`，并被 `python tools/phase_evidence.py` 的 sandbox_loop 段引用。

| 场景 | 请求 | 结果 |
| --- | --- | --- |
| bad 编辑 | 用 edit 在 controller 的 import 区加 from repository import OrderRepository | 文件哈希 53B53A25… → 53B53A25…（**未变化**）；审计 decision=block、exit_code=2、matched_rules=[ARCH-001@1]、dependencies=[repository, service]；模型收到 ARCH-001@1 的理由与证据 |
| good 编辑 | 用 edit 在 controller 加一个 ping 方法 | 文件哈希发生变化，且文件里恰好只有这一处预期变更（哈希随模型的行文略有不同，断言的是"变了且内容符合预期"）；审计 decision=allow、exit_code=0、executed=true、matched_rules=[ARCH-001@1]（命中但未违规） |

原始事件、标准上下文、决策与文件哈希通过审计记录里的 event_id / request_id / payload_digest /
rule_set_hash 关联；采集到的原始载荷已脱敏成 tests/fixtures/agent_events/dsh/ 下的 fixture。

### 环境限制（重放时必须知道）

1. **受限沙箱下 Hook 无法工作**：dsh 用管道 stdio 启动 Hook 进程，在 workspace-write 受限
   沙箱里这类 spawn 直接以 EPERM 失败，而 dsh 把启动失败当作放行——于是"看起来接了策略、
   实际上全部放行"。真实闭环必须在不受该限制的环境里跑（本机用 danger-full-access 验证）。
   这正好说明第 4 节的自检与"shim 在 shell 抛错时 deny"不是多余的。
2. 与 Phase 0/1 相同：uv sync 在受限沙箱里无法探测解释器；pytest 缓存目录写不进去但不影响结果。
3. **不要用 --capture 采集后直接提交**：它是原始载荷，必须像 fixtures README 写的那样脱敏
   （去掉本机绝对路径、会话标识与任何用户数据）。

### 落地命令

    python -m pytest tests/unit -q            # 212 用例
    python -m pytest tests/contract -q        # 50 用例（协议快照 + dsh 映射契约）
    python -m pytest tests/integration -q     # 59 用例（CLI、性能基线、dsh Hook）
    python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml \
        --hooks-config .policy/hooks.json --self-check
    python tools/dsh_sandbox_loop.py          # 真实 dsh 沙箱闭环（本机验证项）
    python tools/phase_evidence.py            # .tmp/artifacts/phase-2-evidence.json

### 验收证据

python tools/phase_evidence.py 生成的 .tmp/artifacts/phase-2-evidence.json 记录：
实现版本、规则集哈希、决策协议版本、**Agent 适配器契约事实**（Hook 事件、阻断协议、
失败放行语义、受治理工具表、事件 fixture 清单）、**真实沙箱闭环结论**、
每个套件的命令/用例数/失败数、性能基线、JUnit 报告路径与时间戳。
