# 2026-10-21 C4 回合末 steer 只读探针读数

> 性质：**只读探针读数**（共享任务 task-1，子会话 `probe-c4`）。依据
> `2026-10-21-new-session-prompt.md` §3.1、`05-implementation-plan.md` §3.1、
> `readings/2026-10-21-C1C2C4-adjudication-draft.md` §3。
> 范围：只验证**宿主能力**——`agent/turn-stopping` 是否到达监听器、`agent.steer` 是否存在、
> 调用后宿主是否重读收件箱并再跑一步；**不改判定、不改 `src/policy`、不改
> `src/adapters/dsh/policy-hook.plugin.mjs`、不新增任何阻断**。
> 不提交；本读数不跑 `ci_local`。

## 0 结论（一句话）

在**已安装宿主**（app.asar `@deepseek-ai/dsh-desktop` / bundled dsh **0.2.1-rc.2**）上，
`agent/turn-stopping` 会到达插件监听器，`agent.steer` 是函数，调用后宿主**重读收件箱并多跑一步**；
**宿主自身没有注入次数上限**（探针自设上限才停）；两例门（有/无未结清）在 headless 真机上成立。
**桌面 profile 未验证**（任务边界：不碰 desktop、不重启 GUI）。

## 1 静态事实：分发点与 `agent.steer`（已安装宿主 app.asar 内）

宿主文件均在 `<install>/resources/app.asar` 内；行号对应该 asar 条目解出的字节。

### 1.1 事件目录条目（`serial`）

`/dsh/node_modules/@deepseek-ai/dsh-tool-cordis/lib/types/api-catalog.js:4036-4042`：

```js
name: 'agent/turn-stopping',
mode: 'serial',
signature: '\'agent/turn-stopping\'(this: Scoped<Agent>, payload: { agent: Agent; turn: number; signal: AbortSignal }): Promise<void> | void',
summary: 'The turn is about to close: the model owes no response (no live tool calls, no fresh steering).',
description: 'The turn is about to close: ... Awaited before the boundary commits — a listener that objects steers (`agent.steer(...)`) and the machine re-reads its inbox: fresh steering runs another step, none closes the turn. ...'
```

### 1.2 分发点（回合收尾前）

`/dsh/node_modules/@deepseek-ai/dsh-agent-loop/lib/index.js:1000-1008`（`ReactLoopAgent.turn()` 内）：

```js
if (turnEnds && this.inbox.nextStep.length === 0) {
	await this.dispatch.serial("agent/turn-stopping", {
		turn,
		signal
	});
	signal.throwIfAborted();
}
if (turnEnds && this.inbox.nextStep.length === 0) break;
target = "next-step";
```

要点（每条都能在同一段代码里读到）：

1. **只在收件箱 `next-step` 为空时**派发；派发是 `await` 的 `serial`（监听器跑完才继续）；
2. 派发后**再查一次** `inbox.nextStep.length === 0`：监听器把消息塞进收件箱就会进入下一次循环，
   `target` 从 `"next-turn"` 改成 `"next-step"` ⇒ 同一回合多跑一步；
3. 派发实参只有 `{ turn, signal }`；`agent` 由分发器注入——
   `/dsh/node_modules/@deepseek-ai/dsh-agent/lib/types/dispatch.js:37-42`：
   `const fused = (payload) => ({ ...payload, agent });`，`:63-67` 的 `serial(name, payload)` 调用
   `ctx.serial(carrier, name, fused(payload))`。所以监听器拿到的是
   `{ agent, turn, signal }`（与 1.1 的签名一致），**监听器不需要自己找 agent**。

### 1.3 `agent.steer` 的实现

`/dsh/node_modules/@deepseek-ai/dsh-agent-loop/lib/index.js:800-814`（`ReactLoopAgent`）：

```js
send(message, target, wakeup) {
	const wakingAfterAbort = wakeup && this.phase.kind !== "idle" && this.phase.abort.signal.aborted;
	const resolvedTarget = wakingAfterAbort ? "next-turn" : target;
	this.inbox.splice(resolvedTarget, Infinity, 0, [message]);
	if (wakeup) this.wakeDriver(wakingAfterAbort);
}
followup(input) {
	this.send(input, "next-turn", true);
}
steer(input) {
	this.send(input, "next-step", true);
}
inject(input) {
	this.send(input, "next-step", false);
}
```

⇒ `steer` = **追加到 `next-step` 收件箱 + 唤醒驱动**；返回值是 `undefined`（不是 allow/block 判定）。
收件箱的"重读"就是 `turn()` 循环下一轮 `preStep` 里的 `this.inbox.claim(target, turn)`
（同一文件 `:103-110`，把 `next-step` 全部搬走并逐个发 `agent/inbox/claimed`）。

### 1.4 类型定义

- 事件签名：见 1.1（`.../dsh-tool-cordis/lib/types/api-catalog.js:4038`）；
- `Agent` 接口随包发布的可读声明（生成物，但它是 asar 里唯一带完整方法集的类型声明；
  `dsh-agent` 的 `lib/types/index.d.ts` 不在 asar 的 files 清单里）：
  `/dsh/node_modules/@deepseek-ai/dsh-agent-preset-registry/lib/typert.host.js:276-277`：
  ```ts
  export interface Agent {
      readonly id: SessionId;
      readonly options: AgentOptions;
      readonly session: Session;
      readonly inbox: Inbox;
      readonly status: AgentStatus;
      readonly ctx: Context;
      cancel(cause: AgentCancelCause, options?: CancelOptions): void;
      whenIdle(): Promise<void>;
      runMaintenance<T>(task: (signal: AbortSignal) => Promise<T>): Promise<T>;
      send(message: UserMessage, target: InboxTarget, wakeup: boolean): void;
      followup(message: UserMessage): void;
      steer(message: UserMessage): void;
      inject(message: UserMessage): void;
  }
  ```
- `UserMessage` 的**最小校验面**（探针据此手造消息、不 import `dsh-llm`）：
  `/dsh/node_modules/@deepseek-ai/dsh-session/lib/index.js:1194-1219` 的
  `assertMessageEventShape` 只要求 `{ id: 非空字符串, role: "user", source: { kind: 非空字符串 }, content: 数组 }`；
  对 `user/message` 不限制 `source.kind` 的具体取值（`assistant`/`system`/`tool` 才限制）。
  `createUserMessage` 本身只是补 `role: "user"` + 随机 `id` + 深冻结
  （`/dsh/node_modules/@deepseek-ai/dsh-llm/lib/index.js:37-42,59-64`）。

## 2 活体探针（隔离 DSH_HOME + headless profile）

### 2.1 环境与隔离

- 宿主 CLI：`<install>/resources/runtime/cli/bin/dsh.cmd`，`dsh --version` = **0.2.1-rc.2**（与 asar 内
  `@deepseek-ai/dsh` / `dsh-agent-loop` 的 package 版本一致）。**不是** PATH 上的全局 npm `dsh`
  （那个是 0.2.1-alpha.2，与本次静态受检的 asar 不同版本）。
- `<DSH_HOME>` = `<workspace>/.tmp/c4-probe/dsh-home`；profile 层只从本机既有形状
  `~/.dsh/profiles/headless` 复制四个小文件（`cordis.yml` / `cordis.patch.yml` / `package.json` /
  `pnpm-workspace.yaml`），**没有**复制 `profiles/node_modules`（bundle 由 app.asar 解析，`--dump-config` 已证明可解析）。
- 探针插件通过 **`--patch` 覆盖层**插入（`<workspace>/.tmp/c4-probe/patch-case-*.yaml`），
  不修改 profile 自己的 `cordis.patch.yml`；未碰 desktop profile、未重启用户的 GUI。
- 凭据：headless 只从**启动环境**读 `DEEPSEEK_API_KEY`（缺键时报
  `MISSING_CREDENTIAL: llm-deepseek: no API key for provider route "deepseek-official"; ...`）；
  探针在启动进程里设置该环境变量，值不打印、不落任何载荷；隔离 home 里的凭据复制件已删。

### 2.2 探针插件（只读）

`<workspace>/.tmp/c4-probe/turn-stopping-probe.plugin.mjs`（`apply(ctx, config)`，只写 JSONL 日志）：

- 订阅 `agent/turn-stopping`（主事件）、`agent/pre-step`（waterfall，记完即 `return next()`）、
  `agent/inbox/claimed`（收件箱被重读的直接证据）、`agent/status`（running/idle 边界）；
- 记录 `typeof agent` / `typeof agent.steer` / `inbox.nextStep.length`（注入前后）/ 注入是否发生 /
  steer 返回类型 / steer 抛错原文；日志写盘前把 `<DSH_HOME>`、`<HOME>`、`<workspace>` 换成 token；
- 注入条件与上限**完全由 config 决定**（`maxSteers`），不读任何规则集/注册表/批次账本。

三例的命令形状（每例一个覆盖层、一个独立日志）：

```powershell
$env:DSH_HOME = '<workspace>/.tmp/c4-probe/dsh-home'
$env:DEEPSEEK_API_KEY = <从本机凭据库读入启动环境；值不打印>
& '<install>/resources/runtime/cli/bin/dsh.cmd' --profile headless --patch '<workspace>/.tmp/c4-probe/patch-case-a.yaml' "Reply with exactly one word: pong."
```

### 2.3 三例真机结果

| 例 | `maxSteers` | stdout / exit | 关键日志（逐字，UUID 截断） |
| --- | --- | --- | --- |
| **B 没有未结清** | 0 | `pong` / 0 | `turn-stopping` 1 次：`steerType:"function"`、`inboxNextStepBefore:0`、`injected:false`、`reason:"maxSteers reached"`；随后 `status:"idle"`，回合正常结束 |
| **A 有未结清** | 1 | `step-two` / 0 | ① `turn-stopping#1`：`injected:true`、`steerReturnType:"undefined"`、`inboxNextStepBefore:0` → `inboxNextStepAfter:1`；② `inbox-claimed` 同一 messageId；③ `pre-step` `turn:1, step:2` 且 `messages:[{role:"user",sourceKind:"c4-turn-stopping-probe"}]`；④ `turn-stopping#2`：`injected:false`、`reason:"maxSteers reached"`、`inboxNextStepBefore:0`；⑤ `status:"idle"` |
| **C 重复注入（附加）** | 2 | `step-two` / 0 | 同一回合 `step:1→2→3`，`turn-stopping` 3 次、前两次都 `injected:true`（第二次 `inboxNextStepAfter:1`），第三次才因探针上限停止——证明**宿主没有自带注入次数上限**，上限必须由插件实现 |

A 例的逐字日志（仅把 messageId 截断为 `7d74bada…`，字段未删）：

```text
{"kind":"turn-stopping","label":"case-a-steer","occurrence":1,"turn":1,"agentType":"object","steerType":"function","followupType":"function","inboxType":"object","inboxNextStepBefore":0,"steersBefore":0,"injected":true,"messageId":"7d74bada…","steerReturnType":"undefined","steerThrew":null,"steersAfter":1,"inboxNextStepAfter":1}
{"kind":"inbox-claimed","turn":1,"id":"7d74bada…","role":"user","sourceKind":"c4-turn-stopping-probe"}
{"kind":"pre-step","turn":1,"step":2,"messageCount":1,"messages":[{"id":"7d74bada…","role":"user","sourceKind":"c4-turn-stopping-probe"}],"inboxNextStep":0}
{"kind":"turn-stopping","label":"case-a-steer","occurrence":2,"turn":1,"agentType":"object","steerType":"function","followupType":"function","inboxType":"object","inboxNextStepBefore":0,"steersBefore":1,"injected":false,"reason":"maxSteers reached","steersAfter":1,"inboxNextStepAfter":0}
```

### 2.4 对门的两句话

- **有未结清**：第一次 `turn-stopping` 注入后宿主重读收件箱、同一回合多跑一步；第二次 `turn-stopping`
  到达时探针按上限**不再注入**，回合正常结束（A 例）。
- **没有未结清**：`turn-stopping` 到达一次、不注入、回合正常结束（B 例）。

"第二次不再注入"是**探针自己的上限**（`maxSteers`），不是宿主拒绝——C 例把上限设成 2，
第二次注入照样被接受并多跑一步。这个口径必须写清：宿主只负责"收件箱非空就再跑"，防循环在插件侧。

## 3 三态与边界

| 事实 | 状态 | 证据 |
| --- | --- | --- |
| `agent/turn-stopping` 在 headless 真机上到达插件监听器 | **available** | B/A/C 三例的 `turn-stopping` 日志行；§1.2 的分发点 |
| `agent.steer` 在事件回调里存在且可调用 | **available** | `steerType:"function"`、`steerReturnType:"undefined"`、`inboxNextStepAfter:1` |
| 调用后宿主重读收件箱并再跑一步 | **available** | `inbox-claimed` + `pre-step step:2` + 同一回合第二次 `turn-stopping` |
| 桌面 profile 的插件 API 里同样可用 | **unavailable（未验证）** | 本任务边界：不碰 desktop profile；同一 asar 版本不等于同一 profile 的插件集 |
| 宿主对注入次数有上限 | **false（实测无）** | C 例：同一回合 `step:1→2→3`、两次注入都被接受 |

## 4 reading_context

| 字段 | 值 | 依据 |
| --- | --- | --- |
| `status` | **available** | 三例都跑通，§2.3 有逐字日志 |
| `host.entry` | headless（`--profile headless --patch <覆盖层>`） | §2.1/§2.2 命令 |
| `host.desktop_shell` | `@deepseek-ai/dsh-desktop` **0.2.1-rc.2** | asar `/package.json` |
| `host.dsh_runtime` | `@deepseek-ai/dsh` **0.2.1-rc.2**；`dsh-agent-loop` 同版本 | asar 内 package.json / 探针 `node` 行 |
| `host.node` | `v24.21.0` | `probe-loaded` 日志行 |
| `host.sandbox` | **restricted** | 本会话里一次越界 `mkdir` 被宿主拒绝（`EPERM: operation not permitted, mkdir '` 工作区外路径 `'`）；探针本身不需要工作区外写入，**未重试、未绕过**；探针与宿主解包只写 `<workspace>/.tmp/c4-probe` |
| `declarations` | **not_applicable** | 探针不读规则集/注册表/验证器/批次账本；不产生 allow/block |
| `tree` | `<workspace>/.tmp/c4-probe`（插件、覆盖层、asar 解包、日志） | 不涉及受治项目树 |
| `decisions` | **not_applicable** | 本读数不含任何 decision/exit code 语义（除 dsh 进程自身的 0） |

## 5 未取得 / 未核实（不许当成"通过"）

1. **桌面 profile 未验证**：headless 与 desktop 共用同一 asar 版本，但 desktop 的插件集、UI steer 队列、
   用户输入并发没有测；"桌面 profile 可用"仍是推断，不是读数。
2. **未在真实未结清来源上触发**：A 例的"有未结清"是探针 config 模拟的；没有接 C1-a 的批次账本，
   也没有验证"账本可读 → 注入"的链路。
3. **没有测注入循环的真实终止行为**：C 例证明宿主不设上限；三例都是探针主动停。若插件写错
   （例如模型每次都被 steer 出新的 "done"），本读数不证明宿主或模型侧有任何其他刹车。
4. **没有证明 `serial` 真的等待慢监听器**：代码是 `await this.dispatch.serial(...)`（§1.2），
   探针的监听器都很快；没构造"慢/抛错监听器"来验证等待与错误隔离（错误从 serial 冒泡会进入
   `turn()` 的 catch，按 `turn end error` 收口——未实测）。
5. **没有测取消/中断期间的 steer**：`signal` 已 abort 时注入的消息会留在收件箱还是被清掉，未测。
6. **没有测多 agent / 并发会话**：事件是 agent-scoped（分发器带 carrier），但本读数只跑单会话。
7. **模型依赖**：三例用真实 `deepseek-flash`；steer 之后"多跑一步"依赖模型对注入文本的反应，
   不是宿主保证的步数。换模型/换提示词会改变步数，但不会改变"收件箱非空就再跑"这条机制。
8. **没有性能读数**：注入带来的额外请求数/延迟/token 成本一概未测。
9. **没有验证 desktop 的 `agent.steer` 与 UI 队列的交互**（是否会出现在聊天记录、是否会与用户
   正在输入的消息抢同一个 `next-step` 收件箱）。

## 6 边界与回退

- 本探针**不是交付物**：只存在于 `<workspace>/.tmp/c4-probe/`，不接入 `policy-hook.plugin.mjs`，
  不改变任何 allow/block、退出码、审计或台账；仓库内除本读数外无改动。
- 回退 = 删 `<workspace>/.tmp/c4-probe/`；本读数引用的日志在该目录下（临时，`cleanup.py` 会删），
  读数本身含逐字引用，不依赖 `.tmp` 存活。

## 7 留给 Lead 的结论与文档更新点

1. **C4 能力结论：可用（headless 真机）**。建议把 05 §3.1 第 82 行"steer 是否在桌面 profile 的插件 API
   版本里可用，**尚未在真机验证**"改为"headless 真机已验证（本读数）；desktop profile 未验证"，
   裁定草案 §3 的"先做验证明"可以据此收口一半。
2. **若立项 C4 门禁**，三条设计约束有实测依据：
   - 注入条件必须来自结构化未结清（C1 批次账本），不能来自模型自述（草案 §3 已写，本读数补充：
     `turn-stopping` 的 payload 里没有 decision，插件只能看自己的状态）；
   - **上限必须由插件实现**（宿主无上限，C 例），建议 1 次/回合 + 第二次不注入的用例（A 例即形状）；
   - 注入文案与触发原因必须一起落账（会新增审计键 → 按 AGENTS 第 55 条给 `AUDIT_SCHEMA_VERSION` 升版）。
3. **04-open-work 目前没有 C4 行**（`grep 回合末|steer|turn-stopping` 只命中 C4 通道覆盖账，那是另一个 C4）：
   建议加一条 open-work（本读数 + "desktop 未验证 + 未接批次账本"两个残项）。
4. **不要现在改 `policy-hook.plugin.mjs`**：本任务边界明确不改；C4 是否立项由 Lead/使用者裁定，
   探针代码留在 `.tmp`，不升格进 `tools/`（升格需要按第 55 条建轴并补用例）。

## 8 证据指针

- **宿主文件**（app.asar 内，行号为解出字节的行号）：
  - `/dsh/node_modules/@deepseek-ai/dsh-agent-loop/lib/index.js:1000-1008`（`agent/turn-stopping` 分发 +
    收件箱复查 + `target = "next-step"`）；`:800-814`（`send/followup/steer/inject`）；`:103-110`（claim）；
  - `/dsh/node_modules/@deepseek-ai/dsh-agent/lib/types/dispatch.js:37-42,63-67`（`agent` 注入与 serial）；
  - `/dsh/node_modules/@deepseek-ai/dsh-tool-cordis/lib/types/api-catalog.js:4036-4042`（事件条目与原文）；
  - `/dsh/node_modules/@deepseek-ai/dsh-agent-preset-registry/lib/typert.host.js:276-277`（`Agent` 接口声明）；
  - `/dsh/node_modules/@deepseek-ai/dsh-session/lib/index.js:1194-1219`（`user/message` 最小校验面）；
  - `/dsh/node_modules/@deepseek-ai/dsh-llm/lib/index.js:37-42,59-64`（`createUserMessage`）；
  - 版本：asar `/package.json`、`/dsh/node_modules/@deepseek-ai/dsh/package.json`、
    `.../dsh-agent-loop/package.json` 均为 **0.2.1-rc.2**。
- **复现位置（临时，不是证据）**：`<workspace>/.tmp/c4-probe/` 下的 `turn-stopping-probe.plugin.mjs`、
  `patch-case-{a,b,c}.yaml`、`logs/case-{a,b,c}.jsonl` 与 asar 解包 `host/`；`cleanup.py` 会删掉它们，
  上文的逐字日志引用与本节的宿主文件才是本读数的证据。
- **命令**（每例都先设 `DSH_HOME` 与启动环境 `DEEPSEEK_API_KEY`，再执行）：

```text
dsh --profile headless --patch <workspace>/.tmp/c4-probe/patch-case-b.yaml "Reply with exactly one word: pong."   # stdout pong, exit 0
dsh --profile headless --patch <workspace>/.tmp/c4-probe/patch-case-a.yaml "Reply with exactly one word: pong."   # stdout step-two, exit 0
dsh --profile headless --patch <workspace>/.tmp/c4-probe/patch-case-c.yaml "Reply with exactly one word: pong."   # stdout step-two, exit 0
```

- **失败原文（已尝试命令的真实输出，供复现环境归因）**：
  - 第一次摆 profile 时 PowerShell 自动变量 `$home` 不可赋值，路径塌成工作区外的
    `...\profiles\headless`，宿主报 `Error: EPERM: operation not permitted, mkdir '<工作区外路径>'`；
    改用不同变量名后同一命令成功（不重试被拒路径、不绕过）。
  - 未设 `DEEPSEEK_API_KEY` 时：`dsh: MISSING_CREDENTIAL: llm-deepseek: no API key for provider route
    "deepseek-official"; store DEEPSEEK_API_KEY through the credentials service ... or export
    DEEPSEEK_API_KEY in the launching environment`。
