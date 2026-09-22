# R1 板块拆分提案 v1（内核与板块分析师）

> 会议：平台操作系统（Platform OS）总体设计 · 第 1 轮 · 任务 task-1
> 事实基线：`docs/engineering-policy-platform/designs/os/meeting/r0-facts.md`（引用其 F1–F39 与 N1–N6，不另造口径）
> 标记：【实测】= 本轮真的跑过命令；【读码】= 读了源码或数据；【提案】= 尚未存在。
> 纪律：凡写进本文的命令、路由、字段名、路径都亲跑或读码，锚点写成 `文件:行`；查不到就写【未知，需核验】。
> 最高红线：界面层与脚本层不得出现第二份判定逻辑；判定只有 `policy.engine.evaluate` 一条路径（F5、F31）。

## 0. 结论先行

1. 平台今天已有 **8 个可运行板块**，缺的只是第 9 个（操作台）。"把它做成操作系统"的正确读法是"**内核 + 系统调用面 + 三类驱动 + 数据契约 + 门禁**"，不是"新写一个 OS"。
2. 板块的切割线**不是目录、也不是 Phase，而是"谁能产生结论"**：只有 S1 产生 `allow` / `allow_with_warnings` / `block`（F5、F31）；S2 翻译、S3 执行、S4 产证据、S5 取回语料、S6 传协议、S7 排下一步、S8 复跑门禁、S9 显示——**九者各司其职，多一个产生结论的都不行**。
3. **两个既有缺陷必须先修**，否则界面一上线就生产假的治理证据：新建规则文件绕过审批（`src/orchestration/nodes.py:94-97`）与 HTTP 面 `hash_drift` 硬编码空列表（`src/policy_api/runtime.py:679`）【读码】。
4. **F13 与工作树已经不一致**：F13 写"规则现 6 份"，实测 **26 份**（6 条受跟踪 + 20 条未跟踪），规则集哈希随之变化【实测】。这是"规则是数据"的必然代价，列为 §7 Q1。
5. 隐喻最大的危险是**把 "namespace" 读成 "隔离"**：`src/adapters/runtime.py:600-603` 的 namespace 只是台账键前缀，平台**没有任何**进程或文件系统沙箱（约束 17 自述"白名单不是沙箱"）。

## 1. 一页总览表：9 个板块

| # | 板块 | 一句话职责 | 对应仓库对象（F 编号 + 真实路径） | 今天存在？ | 唯一入口 | 该板块**不行使**的权力 |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | 判定内核 | 对固定上下文稳定给出 allow / allow_with_warnings / block 并逐条解释 | F13 `policies/**`（6 份受跟踪 + 20 份未跟踪）+ `src/policy/{models,loader,scope,context,engine,checkers,evidence}.py` | 【实测】`python -m policy.check --check-rules` → `rules: 26`、exit 0 | Python API `policy.engine.evaluate`（`src/policy/engine.py:109`）；CLI `python -m policy.check` | 不执行任何副作用；不读文件系统做判定（约束 6）；不产证据（约束 19）；不导入 Web / 工作流 / Agent SDK（约束 1） |
| S2 | 接入与适配 | 把各 Agent 的线协议转成规范事件，再把内核结论翻译回各协议的放行/阻断 | F17 `adapters/**`（3 个消费者）+ `src/adapters/{models,base,runtime,conformance,loader,dsh/}` | 【实测】`python -m adapters.cli matrix` → dsh FULL / generic-json READ-ONLY / legacy-post-only READ-ONLY | `python -m adapters.cli`（matrix/approve/check/inspect/events）；dsh 侧 `python -m adapters.dsh.hooks`（exit 0 / 2） | 不自造 allow/block；不猜 principal / layer / language（约束 8、25）；不改能力声明与已审核哈希（约束 24）；不"跳过治理"（约束 24） |
| S3 | 受控执行 | 授权绑到具体动作、只执行一次、事后必须交证据 | F15 `registry/**` + `src/enforcement/**` | 【实测】`python -m enforcement.cli registry --list` → 9 个工具、`approved=9`、exit 0 | `python -m enforcement.cli`（registry/precheck/execute/approve/trace/verify/self-check） | 不决定"这条规则管不管"（判定仍在内核）；不解析自然语言批准（约束 14）；不假装副作用可撤销（约束 15）；不提供沙箱（约束 17） |
| S4 | 验证器 | 把代码与外部工具输出变成确定性、可重放的证据 | F16 `validation/**` + `src/validators/**` | 【实测】`python -m validators.cli registry` → 7 个验证器、exit 0 | `python -m validators.cli`（check/pipeline/registry/probe） | 不产 allow / block（约束 19）；不能造出新规则（约束 22）；不按自由参数调用外部工具（约束 22） |
| S5 | 检索与语料 | 从离线镜像取回带来源、URL、许可与哈希的片段，并组装有预算的 Context | F14 `knowledge/**` + `src/retrieval/**` | 【实测】`python -m retrieval.cli stats` → `documents=27 chunks=535`、6 个数据集；`retrieval.cli verify` exit 0 | `python -m retrieval.cli`（index/query/context/verify/stats/rules/quarantine/vector） | 不用相似度当授权信号（约束 11）；不回退到"模型记忆里的规范"（约束 11）；不把查询原文拼进 SQL / FTS（约束 11）；不静默哈希漂移（约束 12） |
| S6 | 服务化传输边界 | 把内核、检索、验证器暴露成版本化的进程外契约 | F7 `api/openapi.json` + F18 `api/policy-api.yaml` + `src/policy_api/**` | 【实测】`python -m policy_api.cli self-check` → 18 项 `[ok]`、6 条 OpenAPI 路径、exit 0 | HTTP 6 条路由（`src/policy_api/contract.py:44-51`）；`python -m policy_api.cli`（serve/self-check/openapi/clients/smoke/seal） | 不做第二份业务逻辑（约束 30）；**没有 enforce 路由**（F8、约束 39）；不接受客户端自带证据或决策（约束 32）；服务身份不替用户扩权（约束 32） |
| S7 | 编排（消费者） | 只回答"下一步做什么"，按图推进并可恢复 | F5 / F36 `src/orchestration/**` | 【实测】`python -m orchestration.cli self-check` → 8 节点 / 6 条静态边 / 2 个条件分支、exit 0 | `python -m orchestration.cli`（self-check/graph/status/run） | 不自造 PASS/FAIL 与终态（约束 37）；不回落为本地判定（约束 35）；不自建写入路径（写走 S3，约束 39）；不在图状态里放正文（约束 36） |
| S8 | 证据与门禁 | 把"能不能上线"变成可复跑的检查与不可改写的证据 | F20–F25 `tools/**` + `.github/workflows/phase-8.yml` + `tests/**` | 【实测】`python tools/ci_local.py --list` → 本机 27 步 + 8 步仅 CI（bash-only） | `python tools/ci_local.py`（--full/--list/--hook/--python）；`python tools/phase_evidence.py` | 不做判定（它只跑别人的命令）；不改内核结论（门禁红 ≠ block，block 只由内核给）；不隐藏失败步骤的退出码 |
| S9 | 操作台 | 只读视图 + 影响面 + 审批展示（**今天无写路径**） | F26–F30 `docs/engineering-policy-platform/designs/console/**`（未跟踪） | 【读码】6 个 HTML + `assets/app.js` + `assets/style.css` + 生成的 `assets/data.js`；唯一真实请求是 `GET /v1/health/live`（`assets/app.js:402`） | 静态文件 `designs/console/index.html`（**今天没有 HTTP 路由**，N1、N3） | 不行使判定（红线 R1）；不行使提交（提交只能走 S3 的 `orc.policy.edit` + `action_hash`，约束 38、39）；不引入 LLM 判定（F29 反模式清单） |

**三条读表口径**

1. "唯一入口"只写**今天真实存在**的入口；同板块内的其他 CLI 子命令是这一入口的子命令，不另立入口。
2. "今天存在"用【实测】（本轮跑过该板块的清单或自检命令）或【读码】（只读了源码 / 数据）标注；两者都不成立才写【提案】。
3. "不行使"列是本表最有价值的一列：它回答"这块板子**不能**做什么"，是阻止板块膨胀成第二份判定逻辑的第一道约束。

## 2. 操作系统隐喻映射表

| 操作系统概念 | 本平台的真实对象（路径） | 相似点（可以借用） | 关键差异（不能借用） |
| --- | --- | --- | --- |
| 内核 | `src/policy/engine.py:109` 的 `evaluate(...)` + `policies/**` | 唯一判定路径，所有结论都从它出 | 内核**没有特权**：它不能执行副作用，连文件都不读（约束 6） |
| 系统调用 | 6 条 HTTP 路由（`src/policy_api/contract.py:44-51`）+ 7 个 CLI 入口包（F9）+ `evaluate(..., evidence=...)` | 受控、可枚举的对外界面 | **不是稳定 ABI**：三套版本各自演进（约束 7、31、36），见 M5 |
| 设备驱动 | `src/enforcement/drivers.py:38-44`（FileDriver / ProcessDriver / ShellCommandDriver / DelegatingDriver）+ `DriverKind` 5 值（`src/enforcement/models.py:195-202`）；`src/validators/adapters/`（ruff / mypy / pytest） | 把抽象动作落到真实副作用或真实子进程 | **无热插拔 / 无自动发现**：工具表是白名单 + 已审核哈希（约束 13、24），见 M6 |
| 文件系统 | 数据契约：`policies/**`、`knowledge/corpus.yaml`、`registry/tool-registry.yaml`、`validation/*.yaml`、`adapters/*/manifest.yaml`、`api/policy-api.yaml`；可写产物：`.tmp/**` | 有"路径 + 内容"的载体与读写纪律 | **数据契约不可自由写**；只有 `.tmp/` 是可丢弃的可写区（F19），见 M3 |
| 权限与主体 | 声明：`adapters/<agent_id>/manifest.yaml`；主体：`src/adapters/runtime.py` 只认显式声明；租户：`src/policy_api/auth.py`（租户只来自令牌）；授权：`src/enforcement/action.py` 的 `action_hash` | 有主体、权限、授权、时效、单次使用 | 没有 uid / ACL / cap：主体是**数据声明**（约束 24、26），租户是**令牌属性**（约束 32） |
| 进程与调度 | 图：`src/orchestration/**`；熔断：`src/adapters/runtime.py:600-603` 的命名空间 + 窗口计数；预算：`src/policy_api/timeout.py` | 有"下一步"、"上限"、"熔断" | 没有进程、没有抢占、没有优先级、没有公平性；见 M1、M2 |
| 包与安装 | 已审核清单：`registry/tool-registry.approved.json`、`adapters/approved.json`；依赖锁定：`requirements.lock`；钩子安装：`tools/install_hooks.py` | 有"装了什么"的清单与哈希绑定 | 无依赖求解、无签名、无卸载；哈希≠签名（F25 的诚实边界），见 M7 |
| 日志与审计 | 摘要链：`src/enforcement/audit.py`（`sequence` + `prev_digest`）；幂等台账：`src/enforcement/ledger.py`；请求级 JSONL：`src/policy_api/observability.py`；对外锚定：`policy_api.cli seal` | 追加写、可校验、脱敏、单条超限即失败关闭 | **摘要链不是防篡改日志**：删尾或整链重写发现不了（F25、约束 16、34） |
| 引导与自检 | `policy_api.cli self-check`、`enforcement.cli self-check`、`orchestration.cli self-check`、dsh `hooks --self-check`（`src/adapters/dsh/hooks.py`）、`tools/phase_evidence.py`、CI | 启动 / 上线前先验 | 失败表现为"拒绝启动或门禁转红"，不是内核 panic；自检**本身不判定**（约束 19 的同一精神） |

**隐喻的使用边界**：这张表只用来**解释**，不用来**推导**。凡是要写进接口、路由或字段的设计决定，依据必须回到 §7 的 `file:line`，而不是回到"操作系统一般怎么做"。

## 3. 隐喻不成立的地方

**M1 没有进程隔离：namespace 是台账键，不是地址空间。**
`src/adapters/runtime.py:600-603` 的 `ledger_key(namespace, event_id)` 只是把键拼成 `"<namespace>:<event_id>"`；`src/adapters/base.py:349-350` 的 `namespace` 取自 `ledger_alias` 或 `agent_id`。平台既没有容器、没有 chroot，也没有把 Agent 关进独立文件树——grep `container|chroot|namespace|sandbox|沙箱` 扫 `src/**/*.py` 命中 19 处，**全部**是台账键命名空间或关于宿主沙箱的注释（`src/adapters/runtime.py:600-603`、`src/adapters/models.py:86`、`src/validators/adapters/base.py:585`）【读码】。
会写出什么错误设计：把 `adapter` 边界当安全边界，设计"Agent A 读不到 Agent B 的受控工作区"；或把 `orc.fs.write` 的 `path_scope: workspace`（`registry/tool-registry.yaml:310`）解释成"沙箱已隔离"。
正确设计：隔离只有三条——**命名空间化的台账键**（约束 26）、**声明式能力上限**（约束 24）、**路径范围校验**（约束 8）。文件系统与进程级隔离属于运行时，本平台自述不在范围内（约束 17）。

**M2 编排不是调度器：它没有配额、没有优先级、没有队列。**
`src/orchestration/**` 是**消费者**：删掉整个包平台照常运行（约束 35，`tests/contract/test_orchestration_engine.py` 双向检查）；`src/orchestration/limits.py` 给的是**硬上限**（repair 轮次、工具调用、节点执行、token、费用、墙钟），击穿即 `needs_human`（`src/orchestration/errors.py:152-157`），不是"排队等资源"。grep `cron|scheduler|ThreadPool|ProcessPool|celery|queue.Queue|worker pool` 扫 `src/**/*.py` 命中 **0 处**【读码】。
会写出什么错误设计：把 `RunReport` 当平台审计源、把 checkpoint 当任务队列、设计"多租户共享调度与配额"——每一项都要在编排层长出一份平台状态，直接违反约束 36（图状态不放正文、不放凭据）。
正确设计：编排只回答"下一步做什么"（约束 35）；要观察进度读它自己的 `status`，要判定读内核的 Decision。

**M3 "文件系统"是不可写的数据契约，只有 `.tmp/` 是可写区。**
`policies/**` 改了要重新加载（`src/policy/loader.py:201` 任一文件失败即整体不加载）；`registry/tool-registry.yaml` 改了必须 `python -m enforcement.cli registry --approve --reviewer <name>` 重新审核，否则该工具不可用（约束 13）；`knowledge/corpus.yaml` 改了必须重跑 `retrieval.cli verify` → `index` → `tools/retrieval_eval.py`（约束 12、18）；`validation/**` 改了等于改证据口径（约束 21）。真正的可写、可丢弃目录只有 `.tmp/`（F19，`AGENTS.md` "临时文件与产物"）。
会写出什么错误设计：给界面一个"通用 YAML 编辑器"或"文件浏览 + 保存"，或让界面直接写 `policies/`——这正是既有评审的反模式清单第 7 条（自由文本 YAML 编辑器）与第 8 条（保存即生效）。
正确设计：写入只有两条路——**改数据 + 重新审核**（哈希绑定），或**走 S3 的受控执行链**（`orc.policy.edit`，`approval: required`，`registry/tool-registry.yaml:317-345`）。

**M4 内核不是"特权态"，判定与执行的分权靠数据结构而不是硬件。**
`src/policy/` 只能依赖标准库、pydantic、PyYAML（约束 1），**不能执行任何副作用**——执行能力全在 `src/enforcement/`（唯一的越界是一条应用层装配：`src/policy/check.py:49-51` 为了把注册表错误收敛成退出码 2 而导入 `validators.registry.RegistryError`）。反过来，**执行不能回头改判定依据**：`src/enforcement/precheck.py:365-370` 把内核结论当成输入项之一（check 名 `policy`），而不是自己算一遍。
会写出什么错误设计：为了"少一跳"让内核直接调用驱动，或让驱动在失败时"顺手续一个 allow"。
正确设计：依赖倒置——内核不导入能力层，能力层通过 `evaluate(..., evidence=...)` 与 `pre_execute` 反向调用它（约束 23）。

**M5 系统调用不是稳定 ABI：三套版本号各自演进。**
`policy.models.SCHEMA_VERSION = "1.0"` 与 `POLICY_VERSION = "phase-1"` 是决策协议与**世代名**（约束 7，且不跟随平台阶段）；`API_SCHEMA_VERSION` 是传输协议（约束 31）；`STATE_SCHEMA_VERSION` 是编排状态协议（约束 36）。实测 `policy_api.cli self-check` 打印"决策协议 1.0 / 世代 phase-1"，而配置版本是另一行 "1.0"。
会写出什么错误设计：用一个版本号统辖三层、把平台 Phase 当协议版本、或让界面自己推算协议版本。
正确设计：每个消费方按自己的版本判定兼容性；看不懂就拒绝（约束 3、7）。

**M6 设备驱动没有自动发现，也没有热插拔。**
工具表是 YAML 白名单 + 已审核哈希：`python -m enforcement.cli registry --list` 实测 9 个工具（`exec.bash` / `exec.pwsh` / `exec.run_code` / `fs.edit` / `fs.read` / `fs.write` / `orc.fs.edit` / `orc.fs.write` / `orc.policy.edit`）；`adapters/<agent_id>/manifest.yaml` 与 `adapters/approved.json` 同理（约束 24）；升级 Agent 版本必须**先更新工具表并补契约测试**（约束 8）。
会写出什么错误设计：设计"运行期自动发现 Agent / 自动注册工具"，或让模型自己声明"我这个动作属于哪一类"（约束 13 明确禁止）。
正确设计：新增能力 = 改数据 + 重新审核 + 补契约测试；`validators.cli probe` 只能**探测**外部工具是否就绪，不能注册。

**M7 "安装"没有依赖求解，也没有签名。**
`registry/tool-registry.approved.json` 与 `adapters/approved.json` 是**内容哈希清单**，不是签名包：`enforcement.cli registry --approve --reviewer <name>` 记录的是"谁在何时审了哪份哈希"。`requirements.lock` 由 `tools/lock_requirements.py` 从 pip 报告生成，是直接依赖锁，不是 SAT 求解结果。
会写出什么错误设计：设计"规则包仓库 + 依赖解析 + 版本区间求解"，或把已审核哈希当成"防篡改"（它只防"改完忘了重新审核"）。
正确设计：审核是**流程**，哈希是它的凭证；平台不承诺密码学强度，这一点必须在界面上显示，而不是被"绿勾"掩盖。

## 4. 板块间关系图（谁能调用谁）

实线 = 允许的调用方向；虚线 = 只传数据不传控制；`✗` = **结构性禁止**。

```text
                          ┌───────────────────────────────────────────────┐
   ① 消费方 / 入口        │ dsh Runtime（F17）· 编排 S7 · 人 · CI · 操作台 S9（提案）
                          └───────┬───────────────────────┬───────────────┘
                    线协议/Hook   │ CLI/HTTP              │ 静态页（今天无路由，N1/N3）
                                  ▼                       ▼
   ② 接入与协议转换      ┌─────────────────┐      ┌──────────────────┐
     S2 + S6             │ adapters/ (S2)  │      │ policy_api/ (S6) │  传输边界
                         └────────┬────────┘      └────────┬─────────┘
                                  │  policy.engine.evaluate(...)  ← 唯一判定路径（F31）
                                  ▼                        ▼
   ③ 判定内核 S1         ┌───────────────────────────────────────────┐
                         │ src/policy/  models·loader·scope·engine   │
                         └───────▲───────────────────────▲───────────┘
                    evidence=    │（依赖倒置：内核不导入能力层）
                                  │
   ④ 能力层             ┌────────┴───────┐   ┌──────────────┐   ┌────────────────┐
                        │ retrieval S5   │   │ validators S4│   │ enforcement S3 │
                        └────────┬───────┘   └──────┬───────┘   └───────┬────────┘
                                  │                  │                   │ 真实副作用
   ⑤ 数据与契约                    ▼                  ▼                   ▼
              policies/ · knowledge/ · registry/ · validation/ · adapters/ · api/  ·  .tmp/（可写）
                                  │
                                  ▼  只读消费，绝不写回
   ⑥ 证据与门禁 S8      tools/*.py · tests/** · .github/workflows/phase-8.yml · phase_evidence
```

| 关系 | 允许？ | 依据（AGENTS.md 约束编号） | 本轮怎么验证的 |
| --- | --- | --- | --- |
| S2 / S6 → S1（`evaluate`） | 允许，且是**唯一**判定入口 | 30、31 | `python -m policy_api.cli self-check` 的 `core_has_no_framework` 与 `decision_protocol_pinned` 两项 ok【实测】 |
| S3 → S1（pre-check 的 policy 项） | 允许，但只作为**输入项**，不由 S3 重算 | 23、30 | `src/enforcement/precheck.py:365-370`【读码】 |
| S4 → S1（传证据） | 允许，只传 `EvidenceBundle`，不传结论 | 19、23 | `src/validators/pipeline.py:28-44` 只构造证据模型【读码】 |
| S7 → S6（平台客户端） | 允许，且是**唯一**平台入口 | 35 | `src/orchestration/client.py:29` 只导入 `policy.models` 的协议解析，不导入 `policy.engine`【读码】 |
| S7 → S3（写入） | 允许，且**必须**走受控执行链 | 39 | `src/orchestration/tools.py:25-37` 直接装配 `pre_execute` / `ControlledExecutor` / `EnforcementLedger`【读码】 |
| S9 → S6（读取） | 允许（只读） | 30、32 | 原型今天唯一真实请求是 `GET /v1/health/live`（`console/assets/app.js:402`）【读码】 |
| 任何包 → S7 | **禁止** | 35 | 全仓 `src/**/*.py` 交叉导入扫描：没有任何包导入 `orchestration`【读码】 |
| S1 → Web 框架 / 工作流框架 / Agent SDK | **禁止** | 1、30 | 契约测试与 `self-check` 的 `core_has_no_framework`【实测】 |
| S6 → enforce / 驱动 | **禁止**（没有 enforce 路由） | 39、F8 | OpenAPI 实测 6 条路径，无 enforce【实测】 |
| S4 → allow / block | **禁止** | 19 | `src/policy/checkers.py:171-199` 由内核产出 critical，不由验证器给结论【读码】 |
| S8 → 改写内核结论 | **禁止** | 5、19 | 门禁只聚合退出码；口径表 §4 记 `tools/ci_local.py:253-285` 只 `return 0` / `return 1`【读码】 |
| 界面 / 脚本 → 第二份判定 | **禁止（最高红线）** | 30、F31 | 上表所有"允许"边都指向同一个 `evaluate`【读码】 |

## 5. 每个板块的接口面

### S1 判定内核（`src/policy/`）

- **输入**：规则目录（`policies/`，可重复 `--rules`）+ 显式上下文（`file` / `layer` / `language` / `module` / `project` / `agent` / `operation` / `workspace`）+ 可选 `evidence`。`policy.check --help` 实测列出以上全部选项。
- **输出**：`Decision`（`allow` / `allow_with_warnings` / `block`，`src/policy/models.py:255`）+ `matched_rules` / `skipped_rules`（后者必须带原因，`src/policy/checkers.py:32-33`）+ `rule_set_hash`。
- **失败关闭的显式状态**：退出码 `0` 通过 / `1` 违规或漂移 / `2` 配置与执行错误（`src/policy/check.py:71-73`，【实测】`--check-rules` 返回 0）；未知 checker / 未知 scope 维度 → 加载即报错（约束 3）；"没有任何验证器为某个 checker 供证" → `critical` 违规（`src/policy/checkers.py:190-199`，约束 20）。
- **不做**：见 §1 表格末列；补充一条：`skipped != 通过`（口径表 §3）。

### S2 接入与适配（`src/adapters/` + `adapters/`）

- **输入**：各 Agent 的线协议事件（dsh 的 stdin JSON / Hook 配置）；能力声明 `adapters/<agent_id>/manifest.yaml` + `adapter.yaml`。
- **输出**：规范事件 `AgentEvent`（`src/adapters/models.py`）+ 内核 Decision + 面向 Agent 的原因码。
- **失败关闭的显式状态**：`EXIT_ALLOW = 0` / `EXIT_BLOCK = 2`（`src/adapters/dsh/hooks.py:78-79`；`exit 1` 被刻意不用，见 `hooks.py:11-15`）；原因码是**受控枚举** `REASON_CODES`（`src/adapters/runtime.py:78-102`），含 `capability_unavailable` / `evidence_unavailable` / `enforcement_unavailable` / `trace_forged` / `request_busy` / `ledger_unavailable` / `unknown_tool` / `event_replay` / `event_id_reuse`。
- **【未知，需核验】**：`REASON_CODES` 是否是"全部可达码"没有单独门禁；本轮只做了静态读码，没有逐个构造事件验证可达性。

### S3 受控执行（`src/enforcement/` + `registry/`）

- **输入**：`ActionRequest`（工具 id + 规范化参数 + 主体 + 权限 + 上下文摘要 → `action_hash`，`src/enforcement/action.py`）+ 已审核注册表 + 可选人工审批记录。
- **输出**：`PreDecision` + 逐项检查结果，实测检查项名共 14 个：`registry` / `action_window` / `principal` / `permissions` / `command_allowlist` / `command_composition` / `command_fragments` / `approval` / `policy` / `circuit_breaker` / `rate_limit` / `ledger` / `ledger_claim` / `audit`（`src/enforcement/precheck.py`，含 `:429-433`、`:544-566`、`:632`、`:738`）。
- **失败关闭的显式状态**：任一 `CheckStatus.FAILED` 即 block（`precheck.py:82-86`；【实测】`registry --list` 全 `ok`）；原因码含 `schema_not_approved`（`src/enforcement/models.py:279`）、`audit_unavailable`（`:292`）、`command_composition_blocked` / `command_fragment_blocked`（`:302-303`）；事后验证三态 `repair_required` / `inconsistent` / `unsupported`（`src/enforcement/postcheck.py:11-14`、`:463`）。
- **不做**：不解析自然语言批准、不执行第二次同 `action_id`（约束 14）；审计与台账不可写则受治理动作不执行（约束 16）。

### S4 验证器（`src/validators/` + `validation/`）

- **输入**：目标文件 + `--workspace` + `--config-root` + 变更集（`--changed` / `--changed-from-git`）+ 验证器 allowlist。
- **输出**：`ValidationEvidence` / `EvidenceBundle`（带验证器 id 与版本、规则 id、文件与行列、严重级别、工具退出码与配置哈希；不含绝对路径与耗时，约束 19）；`validators.cli registry` 实测 7 个验证器：`py.source` / `py.ast` / `py.depgraph` / `py.docstring` / `tool.ruff` / `tool.mypy` / `tool.pytest`。
- **失败关闭的显式状态**：缺失 / 版本不符 / 超时 / 崩溃 / 配置错误 / 输出非法一律失败关闭（约束 20）；外部工具的失效分类里超时对应 `timeout`（`src/validators/adapters/base.py:9`）；未知 checker 或未实现的验证器 id 在**加载阶段**报错（`RegistryError` 定义在 `src/validators/registry.py:46`，"依赖未声明的验证器"见 `:132`、`:153`）；该注册表与内核的 checker 清单对齐（`src/validators/registry.py:22` 导入 `policy.checkers.SUPPORTED_CHECKERS`）；内核侧经 `src/policy/check.py:51` 导入的 `RegistryError` 收敛为退出码 2。
- **【未知，需核验】**：`validation/validators.yaml` 声明的 7 个验证器与 `pipeline.KNOWN_VALIDATOR_IDS` 的一致性由 CI 比对（F21），本轮未单独复跑该步骤。

### S5 检索与语料（`src/retrieval/` + `knowledge/`）

- **输入**：`knowledge/corpus.yaml`（6 数据集 / 27 条目）+ 查询文本 + 显式 `AccessScope`。
- **输出**：`RetrievalResult`：`status` ∈ `ok` / `empty` / `unavailable`（`src/retrieval/models.py:177-182`）+ 命中项（必带来源路径、URL、许可、文本哈希，约束 11）；Context 侧只有 `ok` / `knowledge_unavailable`（`:195-199`）。
- **失败关闭的显式状态**：不可用原因 `UnavailableReason`：`empty_query` / `no_results` / `index_missing` / `retrieval_failed` / `access_denied`（`src/retrieval/models.py:185-192`）；哈希漂移必须让 `retrieval.cli verify` 退出 1（约束 12；本轮【实测】无漂移、exit 0，所以这条路径**本轮未被触发**）。
- **不做**：不用相似度做授权；不因"没结果"而回退到模型记忆。

### S6 服务化传输边界（`src/policy_api/` + `api/`）

- **输入**：6 条 HTTP 路由的版本化 DTO + Bearer 令牌（`api/policy-api.yaml` 存令牌 sha256、租户、预算、限流）。
- **输出**：与本地完全相等的 Decision 载荷（JSON 值相等，字段顺序不属于契约，约束 30）+ 请求级 JSONL 摘要。
- **失败关闭的显式状态**：`ErrorCode` 受控枚举 + `STATUS_BY_CODE` 推导（`src/policy_api/errors.py:73-107`）：超时 `evaluate_timeout` / `retrieve_timeout` / `validate_timeout` → **504**；`knowledge_unavailable` / `evidence_unavailable` / `validator_unavailable` / `rule_set_unavailable` / `policy_busy` / `policy_unavailable` / `audit_unavailable` / `idempotency_unavailable` → **503**；`rate_limited` 429；`idempotency_key_conflict` 409；`unauthenticated` / `token_expired` 401；`token_scope_mismatch` / `forbidden` / `project_not_allowed` 403；`tenant_not_found` / `not_found` 404；`body_too_large` 413；`unsupported_media_type` 415。
- **不做**：没有 enforce 路由；不接受客户端带证据或决策；错误响应不泄露资源是否存在。

### S7 编排（`src/orchestration/`）

- **输入**：任务文件 / 需求文本（只留摘要，约束 36）+ checkpoint（`STATE_SCHEMA_VERSION`）+ 平台凭据（`rule_set_hash` / `index_version` / `tool_schema_hash` / 协议世代）。
- **输出**：`RunReport`（含 `engine`、状态、失败码）+ 新 checkpoint（单文件 + `os.replace` 原子替换，`src/orchestration/checkpoint.py:156`）。
- **失败关闭的显式状态**：终态只有 `blocked` / `needs_human` / `failed`，由 `STATUS_BY_CODE` 决定（`src/orchestration/errors.py:127-158`）；**未登记的失败码一律按 `failed`**（`errors.py:161-164`）；恢复时发现"开工未结算" → `side_effect_unknown` → `needs_human`（约束 39）。
- **实测**：`orchestration.cli self-check` 报告 `engine: langgraph 1.2.11；auto → langgraph`、8 节点 / 6 条静态边 / 2 个条件分支、exit 0。

### S8 证据与门禁（`tools/` + CI + `tests/`）

- **输入**：工作树改动范围（`ci_local.py` 实测本次"改动文件 47 个"）+ CI 事件。
- **输出**：步骤级结论（本机 27 步 + 仅 CI 8 步，【实测】`ci_local.py --list`）+ `.tmp/artifacts/phase-8-evidence.json`（F20）。
- **失败关闭的显式状态**：`ci_local.py` 只有 `0` / `1`（口径表 §4）；`retrieval.cli verify` 漂移退 1；`dsh_sandbox_loop.py` 环境不具备时**按环境跳过**（退出码 0 + reason + 复现命令，AGENTS.md"仓库现状"），**绝不把跑不了记成 pass**。
- **【未知，需核验】**：`python tools/phase_evidence.py` 当前是否仍为红，本轮未跑（术语与口径 §5 记载为"退出 1，根因是既有失败"）。

### S9 操作台（`designs/console/`，【提案】）

- **输入（今天）**：由 `build_site.py` 预先生成的 `assets/data.js`（真实数据来自 `policy.loader` / `corpus.yaml` / `docs/*/manifest.json` / `validation/validators.yaml` / `.tmp/retrieval/index.sqlite3` / `policy_api.runtime.ROUTES`，F28）。
- **输出（今天）**：6 个静态 HTML；唯一真实网络请求是 `GET /v1/health/live`（`assets/app.js:402`）；勾选与候选存 `localStorage["console.state"]`（`app.js:61`、`:71`）。
- **失败关闭的显式状态（今天没有）**：静态页没有失败语义。**【提案】**界面必须把 504 / 503 / 429 一律渲染成"没有结论"，把 `skipped_rules` 与 allow 视觉分开，把漂移渲染成"未核对"而不是"无漂移"（F29；约束 33；G1/G2 缺口）。
- **不做**：不判定、不提交、不引入 LLM 判定；提交只能经 `orc.policy.edit` + `action_hash`。

## 6. 落地顺序与依赖

**第 0 步（阻塞项，非新板块）**：修两个既有缺陷。B1 在 S7（`src/orchestration/nodes.py:94-97`：`old is None` 时一律落到 `WRITE_TOOL = orc.fs.write`，而该工具在 `registry/tool-registry.yaml:293-315` 是 `approval: none` 且路径没有 `policies/` 白名单）；B2 在 S6（`src/policy_api/runtime.py:679` 的 `"hash_drift": []`）。理由：它们各自打破一条对外承诺（"改规则要审批"、"漂移不许静默"），而操作台只会把这两条裂缝放大成界面上看得见的结论。

| 步骤 | 板块 / 能力 | 为什么排在这里 | 依赖 |
| --- | --- | --- | --- |
| 0 | 修 B1、B2 | 不修则后面每一步的"结论"都建立在假前提上 | 无 |
| 1 | S1 判定内核（只读暴露其结论） | 所有板块的结论来源，必须先稳定 | 无 |
| 2 | S4 / S5 / S6 的**只读**面 | 只暴露既有结论，零新增判定；S6 是唯一既有传输面 | S1 |
| 3 | S3 的**提交**面（`orc.policy.edit`） | 唯一能改"判定依据"的路径，必须最后开放写 | S1（allow）+ S4（证据）+ S3 自身审核 |
| 4 | S9 操作台 | 只做 1–3 的视图；一旦先做，它会自己长出判定与写路径 | S6 + S3 |
| 5 | 溯源（`rule_sources` 今天是空的，F14） | 它是本平台相对外部产品真正的增量，也是真正的欠账 | S5 索引 + S1 规则身份 |

**为什么不是"先做界面"**：界面是唯一**没有**自己的结论、却最容易长出结论的一层；先做界面等于先造第二份判定，违反最高红线（F31）。

### 被否决的拆分方案

| # | 被否决的方案 | 否决理由（具体到会写出什么） |
| --- | --- | --- |
| V1 | 按**六层架构**拆成 6 个板块 | 六层是**架构分层**（口径表 §1），不是部署或调用边界；层内子系统本来就跨层（Policy API 挂 ②+④、dsh 挂 ①+②）。按层拆会把"唯一入口"写成"每层一个入口"，而 S6 的传输边界与 S1 的判定路径必须是同一条（约束 30）。 |
| V2 | 按 **Agent** 拆（一个 Agent 一个板块） | 今天只有 dsh 是真实产品，另两个是合成协议夹具（F17、N6）；按 Agent 拆会把"能力上限由声明推出"（约束 24）变成"每个 Agent 一套逻辑"，正是约束 27 禁止的（核心测试不得长出 Agent 专用分支）。 |
| V3 | 按 **Phase 0–8** 拆成 9 个板块 | Phase 是**交付批次**，不是运行时边界（口径表 §2）。最直接的证据：Phase 2 与 Phase 6 落在同一个 `src/adapters/`；Phase 4（执行）与 Phase 5（证据）在运行时是两条不同链路、两组不同失败码，拆开才对。 |
| V4 | 按 **CLI 入口包**拆（7 个 `python -m` = 7 个板块） | 入口是**应用层装配**，不等于库边界：`src/policy/check.py:49-51` 自己在注释里写明"core（models/engine/context/scope/loader）不导入 Adapter，只有 CLI 在这装配验证器流水线"。按入口拆会把接口面写成命令行参数，丢掉真正的契约（Decision 载荷、证据模型、action_hash）。 |
| V5 | 把**检索**与**语料**拆成两个板块 | 语料是数据契约、检索是它的消费者（F14）。拆开最容易诱导的动作是"改语料但不重跑评测基线"——而这正是约束 18 与约束 12 要拦的（改语料必须重跑 `tools/retrieval_eval.py`，漂移必须让 `verify` 退 1）。 |

## 7. 事实引用与开放问题

### 7.1 本轮新增证据（`file:line` 或实测输出）

| # | 事实 | 证据 |
| --- | --- | --- |
| E1 | 规则条数实测 **26**，与 F13 的"现 6 份"不一致 | 【实测】`python -m policy.check --check-rules` → `rules: 26 (sha256:a6c9655aac58…)`、exit 0；`git ls-files policies` → 6 条；`git status --porcelain` 显示 20 条 `?? policies/coding/*.yaml` |
| E2 | 退出码口径 | `src/policy/check.py:71-73`（`EXIT_ALLOWED = 0` / `EXIT_VIOLATION = 1` / `EXIT_ERROR = 2`） |
| E3 | 请求侧有 6 条路由、无 enforce | `src/policy_api/contract.py:44-51`；`python -m policy_api.cli self-check` 实测 6 条路径 + 18 项 ok |
| E4 | 传输错误码 → 状态码 | `src/policy_api/errors.py:73-107`（504 三个超时；503 八个依赖不可用；429 / 409 / 401 / 403 / 404 / 413 / 415） |
| E5 | 编排终态映射与"未登记按 failed" | `src/orchestration/errors.py:127-158`、`:161-164` |
| E6 | 受控执行 pre-check 共 14 个检查项名 | `src/enforcement/precheck.py`（`registry` / `action_window` / `principal` / `permissions` / `command_allowlist` / `command_composition` / `command_fragments` / `approval` / `policy` / `circuit_breaker` / `rate_limit` / `ledger` / `ledger_claim` / `audit`） |
| E7 | 9 个受控工具与驱动映射 | 【实测】`python -m enforcement.cli registry --list`；`registry/tool-registry.yaml:293-315`（`orc.fs.write`：`approval: none`、`path_scope: workspace`）、`:317-345`（`orc.policy.edit`：`approval: required`、路径模式 `^policies/[A-Za-z0-9._/-]+$`） |
| E8 | B1：新建规则文件绕过审批 | `src/orchestration/nodes.py:67-68`（`WRITE_TOOL` / `PROTECTED_EDIT_TOOL`）、`:93-97`（`old is None` → `WRITE_TOOL`） |
| E9 | B2：`hash_drift` 硬编码空列表 | `src/policy_api/runtime.py:679` |
| E10 | namespace 只是台账键前缀 | `src/adapters/runtime.py:600-603`、`src/adapters/base.py:349-350` |
| E11 | dsh Hook 只认 0 / 2 | `src/adapters/dsh/hooks.py:78-79`、`:11-15` |
| E12 | 检索三态与五个不可用原因 | `src/retrieval/models.py:177-182`、`:185-192`、`:195-199` |
| E13 | 验证器 7 个、注册表门禁 | 【实测】`python -m validators.cli registry` → exit 0；`src/validators/registry.py:46`（`RegistryError`）、`:132`/`:153`（依赖未声明）、`:22`（对齐 `policy.checkers.SUPPORTED_CHECKERS`）；`src/policy/check.py:49-51` |
| E14 | 7 个 CLI 入口与子命令表 | 【实测】对 7 个包逐个跑 `--help`（policy.check / retrieval.cli / enforcement.cli / validators.cli / adapters.cli / orchestration.cli / policy_api.cli） |
| E15 | 三个自检 | 【实测】`policy_api.cli self-check`（18 项 ok）、`enforcement.cli self-check`（`tools=9 approved=9` + 一条 `exec.pwsh` 找不到 `pwsh` 的警告）、`orchestration.cli self-check`（langgraph 1.2.11） |
| E16 | 本机门禁步骤数 | 【实测】`python tools/ci_local.py --list` → 27 步 + 8 步"仅 CI（bash-only）" |
| E17 | 跨包导入方向 | 【读码】`src/**/*.py` 的 `^(from|import)` 扫描：无任何包导入 `orchestration`；`src/orchestration/client.py:29` 只导入 `policy.models`；`src/orchestration/tools.py:25-37` 导入 `enforcement`；`src/policy_api/observability.py:26` 复用 `enforcement.audit` 的脱敏函数 |
| E18 | 操作台现状 | 【读码】`designs/console/build_site.py:5-10`（6 页）、`assets/app.js:61`/`:71`（localStorage 键 `console.state`）、`:402`（唯一真实 fetch） |
| E19 | checkpoint 原子替换 | `src/orchestration/checkpoint.py:10`、`:156`（`os.replace`） |
| E20 | 子进程树终止的真实实现 | `src/validators/adapters/base.py:18`、`:580-607`（job object / `killpg` / `taskkill /T`） |

### 7.2 开放问题（每条：谁来裁决 / 需要什么证据）

| # | 问题 | 谁裁决 | 需要什么证据 |
| --- | --- | --- | --- |
| Q1 | 工作树 26 条规则 vs 受跟踪 6 条，哪个是"当前规则集"？规则集哈希因此漂移，影响 Phase 7 观测摘要与 Phase 8 checkpoint 兼容性（约束 36） | Lead + F 基线维护者 | 一条可复跑命令（如 `python -m policy.check --check-rules` 与其 `sha256`）+ 一句口径："规则集 = 工作树"还是"= 受跟踪文件" |
| Q2 | B1 是否在本轮设计里就修（`nodes.py:94-97`） | Lead | 修法二选一（路径判定一律走 `orc.policy.edit`，或给 `orc.fs.write` 加 `policies/` 拒绝规则）+ 一条契约测试 |
| Q3 | B2 止损是"界面显示未核对"还是"API 读真实漂移"（`runtime.py:679`） | Lead + S6 所有者 | `retrieval.corpus` 的漂移结果如何进 `retrieve` 响应；【未知，需核验】该结果的现成 JSON 形状 |
| Q4 | 操作台算不算第 9 个板块，还是 S6 的一个视图 | Lead | 它今天 untracked、无路由（F26、N1、N3）；需要一句"它是否拥有独立生命周期（版本、发布、回滚）" |
| Q5 | S8 门禁的既有红灯（工作树含非 ASCII 路径时 `test_changed_from_git_uses_the_working_tree` 失败）是否阻塞本设计落地 | Lead | 本轮未复跑全量 `pytest`；需要一次独跑记录（收集数 / 通过 / 失败 / 跳过 + 耗时） |
| Q6 | `.tmp/` 的可写区归谁、生命周期多长 | Lead | `tools/cleanup.py` 的白名单（`.tmp/`、`.pytest_cache/`、`.uv-cache/`、`__pycache__/`、`*.pyc`）与各阶段闭环目录（`.tmp/phase-2-sandbox/`、`.tmp/phase-4-demo/`、`.tmp/phase-5-demo/`、`.tmp/phase-8-orchestration/`）是否需要一个统一命名规则 |
| Q7 | S2 的 `REASON_CODES` 是否需要"可达性"门禁 | S2 所有者 | 逐个构造事件证明每个码可达，或明确"未使用的码是预留" |
| Q8 | 溯源（`rule_sources`）今天是空列表，谁负责补 | Lead + S5 所有者 | `python -m retrieval.cli rules --rule ARCH-001`（F14 实测退出 1："没有登记的来源溯源"）与补登记后的重跑记录 |
