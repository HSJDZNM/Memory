# Memory

开发仓库根目录。当前承载一个**独立于具体 Coding Agent 的软件工程治理层**：
把工程规范变成机器可执行的规则，对固定上下文稳定地给出 allow / allow_with_warnings / block，
并留下"命中了哪些规则、跳过了哪些、为什么"的可重放审计证据。

> 当前进度：**Phase 0 至 Phase 8 的仓库实现已完成**。Phase 6 交付了规范事件 Schema、
> 数据化能力声明、一致性套件与多 Agent 运行时的隔离/熔断/能力降级；Phase 7 把核心能力
> 服务化：版本化 DTO 与 OpenAPI 快照、Bearer 认证、租户/项目隔离、墙钟预算与幂等、
> 请求级观测与可对外锚定的摘要链——API 只增加部署与信任边界，判定仍只有
> `policy.engine.evaluate` 一条路径；Phase 8 在其上加了一层**可恢复的上层编排**
> （`src/orchestration/`）：LangGraph 驱动"需求 → 检索 → 规划 → 实施 → 验证 ⇄ 修复 →
> 测试 → 收尾"，但**只当消费者**——每次动手仍然回到平台要一个结构化 Decision，
> 循环有硬上限、checkpoint 带兼容性凭据、人工审批与参数绑定、平台不可用即停下。
> 当前只有 `dsh` 是真实产品接入；`generic-json`、`legacy-post-only` 与 Phase 7 的
> `http-api` 都是合成协议消费者，因此“第二个真实 Agent 产品验证”仍是外部验收项；
> Phase 8 的候选改动同样来自可替换端口（`ChangeAuthor`），真实模型作者尚未接入。
> Phase 0 的 YAML Rule → Loader → Engine → CLI 链路、Phase 1 的 Context/Scope/Decision、
> Phase 2 的 dsh Adapter 与 pre-execute Hook、Phase 3 的离线检索、Phase 4 的受控执行、
> Phase 5 的代码验证器仍然有效，并被后续阶段的测试继续覆盖。
> 阶段计划见 [Engineering Policy Platform 文档集](docs/engineering-policy-platform/README.md)。

## 快速开始

环境要求：Python ≥ 3.11。以下命令均已在本仓库实际执行验证。

### 安装

依赖锁定以 [requirements.lock](requirements.lock) 为准（固定直接依赖的版本，CI 与本地用同一份）。
推荐用 [uv](https://docs.astral.sh/uv/) 建虚拟环境并从锁文件安装：

```powershell
uv venv
uv pip install -r requirements.lock
```

没有 uv 时，用现有解释器从同一份锁文件安装：

```powershell
python -m pip install -r requirements.lock
```

> 本仓库**没有提交 `uv.lock`**：生成它需要在能探测解释器的环境里运行 `uv lock`（受控沙箱会拒绝）。
> 因此在锁文件这件事上只有一份真相——`requirements.lock`；`uv sync` 在没有 `uv.lock` 时是重新解析，
> 不是锁定安装，CI 里不使用它。`python tools/check_repo_consistency.py` 会守住这条一致性。

### 运行规则检查（CLI）

```powershell
# 反例：Controller 直接依赖 Repository。Phase 5 起依赖由 AST / 依赖图给出，退出码 1
uv run python -m policy.check examples/bad_controller.py --layer controller

# 正例：Controller 只依赖 Service，退出码 0
uv run python -m policy.check examples/good_controller.py --layer controller

# 范围不匹配：layer=service 时 ARCH-001 不参与判断，输出会列出跳过原因，退出码 0
uv run python -m policy.check examples/good_controller.py --layer service

# 显式声明依赖（重放历史场景）：覆盖 AST 证据，输出里会标注来源
uv run python -m policy.check examples/bad_controller.py --dependencies repository

# 只校验规则集本身（配置损坏时退出码 2）
uv run python -m policy.check --check-rules
```

未使用 uv 时，`python -m policy.check` 需要先让解释器找到 `src/`：

```powershell
$env:PYTHONPATH = "src"     # 让解释器找到 src/；CI 也用同一条路径
python -m policy.check examples/bad_controller.py --dependencies repository
```

上面用 `uv run` 的写法等价于在已装好依赖的环境里 `python -m ...`：本项目不把 `src/` 装进
site-packages，而是靠 `PYTHONPATH=src`（CI 的 workflow 里就是这条）。
学习手册不受这条限制：各阶段的 notebook 与 `walkthrough.py` 会自己把 `src/` 与 `tools/` 加进搜索路径。

退出码：`0` 通过（allow）、`1` 发现违规（block / allow_with_warnings，含需要人工审批的 block）、
`2` 配置或执行错误（规则不可读、规则损坏、上下文不完整、未知 checker）。

加 `--json` 得到机器可读输出：顶层是 CLI 包装（`context` / `rule_set` / `reported_imports` / `exit_code`），
其中 `result` 就是带 `schema_version` 的决策协议载荷，可被 `policy.parse_decision` 原样解析回来。

常用参数：`--layer`（安全关键维度，不传时按文件名推断并在输出中标明）、`--module`（只接受显式传入）、
`--operation`（受控枚举）、`--trace-id`（串联检索/决策/执行，不传即留空）、`--task`、`--agent`、`--project`。

### 把策略接到 dsh（Phase 2）

dsh 的工具调用会先经过 Adapter 与 Policy Engine，再决定是否执行：

```text
dsh tool request
  → adapters.dsh.adapter（纯映射：dsh Event → PolicyEvent / PolicyContext）
  → Policy Engine
  → allow：执行一次；block：返回结构化违规，不执行
```

接线分两层（示例都在 examples/dsh/）：

```powershell
# 1) 受治理项目的 .policy/ 下放两份配置：
#    dsh-adapter.yaml：显式声明 project_root / rules / layers / languages / 内部预算
#    hooks.json：声明 Hook 命令（matcher 留空 = 匹配全部工具，避免新工具绕过门禁）
# 2) 把进程内转发插件挂到 profile 上；受控沙箱闭环可以直接跑：
uv run python tools/dsh_sandbox_loop.py     # bad 编辑被阻断且文件哈希不变 / good 编辑放行一次

# 只做接线自检：hooks.json 是否存在、命令是否指向本适配器、内部预算是否小于 dsh 超时
$env:PYTHONPATH = "src"
python -m adapters.dsh.hooks --config examples/dsh/dsh-adapter.yaml `
    --hooks-config examples/dsh/hooks.json --self-check
```

Hook 就是一个读 stdin JSON、按退出码表态的命令：**exit 0 = 放行，exit 2 = 阻断（stderr 即理由）**。
dsh 对"超时 / 崩溃 / 配置读不到"一律按放行处理，所以失败关闭由 Hook 自己保证
（内部预算小于 dsh 超时、异常全部转成 exit 2、运行期接线自检）。设计与证据见
[Adapter README](src/adapters/dsh/README.md)。

### 离线规范检索（Phase 3）

从仓库已有的官方文档镜像里检索与任务相关的片段，并组装成**带来源、长度受控**的 Engineering Context。
检索只回答"找到什么值得告诉 Agent"，不负责授权，也不执行任何工具。

```powershell
# 1) 校验摄取清单：数据集、许可、镜像 manifest 与本地文件哈希（漂移会退出 1）
uv run python -m retrieval.cli verify

# 2) 幂等重建索引（SQLite FTS5，产物在 .tmp/retrieval/ 下，可随时删掉重建）
uv run python -m retrieval.cli index
uv run python -m retrieval.cli index --check     # 只问"要不要重建"

# 3) 检索与组装上下文（--json 得到机器可读载荷）
uv run python -m retrieval.cli query "代码评审需要检查哪些方面" --limit 5

# --decision 接的是**真实存在**的决策载荷：既可以是仓库里的协议快照，
# 也可以先用 CLI 生成一份（下面这条是生成 + 消费的完整链路）
uv run python -m policy.check examples/bad_controller.py --layer controller --json > .tmp/decision.json
uv run python -m retrieval.cli context "代码评审需要检查哪些方面" --decision .tmp/decision.json
uv run python -m retrieval.cli context "代码评审需要检查哪些方面" --decision tests/fixtures/decisions/block.json

# 4) 固定评测集基线：FTS5 门槛决定退出码，向量检索只作为对照记录
#    查询与门槛在 tests/fixtures/retrieval_eval/queries.yaml，
#    记录在案的结果在 tests/fixtures/retrieval_eval/baseline-v3.json
#    （tools/retrieval_eval.BASELINE_PATH 指向当前版本，旧版基线留在同一目录作为历史）：
#    排名或指标变了就会失败，除非显式重新记录（--record）并递增评测集版本
uv run python tools/retrieval_eval.py --method both
```

未安装项目时，同样可以先用 `$env:PYTHONPATH = "src"` 再运行上面的 `python -m retrieval.cli ...`。

语料、许可与预算都是数据：新增/移除语料只改 [knowledge/corpus.yaml](knowledge/corpus.yaml)，
中文术语到英文术语的受控映射在 [knowledge/query_expansion.yaml](knowledge/query_expansion.yaml)。
"没有结果"与"知识不可用"是两个显式状态：`query` 在无命中时退出码为 1，
Context 在检索不可用时只输出 `knowledge_unavailable`，**绝不回退到模型记忆里的规范**。
每条片段都带来源路径、URL、许可与文本哈希，引用 ID（`[K1]`、`[K2]`…）可直接追溯。

### 受控执行（Phase 4）

规则说"这件事不合规"，受控执行说"这件事根本没被执行"：所有受控工具都要先拿到
与**具体参数**绑定的短时效授权，执行后还要交出证据。

```powershell
# 1) Tool Registry 是数据：风险级别、参数白名单、权限、审批门禁、事后验证器都在
#    registry/tool-registry.yaml 里；运行时描述与已审核哈希不一致的工具不可使用
uv run python -m enforcement.cli registry --verify
uv run python -m enforcement.cli registry --show fs.edit

# 2) 只做执行前决策（授权 / 阻断），不执行任何工具，也不占用 action_id（dry-run）
uv run python -m enforcement.cli precheck --request examples/enforcement/edit-allow-request.json

# 3) 受控执行：pre-check → 短时效 grant → 执行一次 → 事后验证（哈希 / diff / 语法）
uv run python -m enforcement.cli execute --request examples/enforcement/edit-allow-request.json

# 4) 高风险动作（pwsh / bash / run_code）默认阻断：先由人工门禁签发与 action_hash 绑定的审批
uv run python -m enforcement.cli approve --request examples/enforcement/shell-approval-request.json `
    --out .tmp/artifacts/approval.json --granted-by alice --roles reviewer --ttl 300
uv run python -m enforcement.cli execute --request examples/enforcement/shell-approval-request.json `
    --approval .tmp/artifacts/approval.json

# 5) 一条 trace 从决策到终态可以重放；审计链被改动或删记录都会失败
uv run python -m enforcement.cli trace --audit .tmp/artifacts/enforcement-audit.jsonl --action-id <id>
uv run python -m enforcement.cli verify --audit .tmp/artifacts/enforcement-audit.jsonl

# 6) 上线自检：注册表 / 审核 / 审计 / 台账 / 驱动
uv run python -m enforcement.cli self-check

# 7) 受控执行闭环（允许一次 / 重放阻断 / 失败回滚 / 高风险阻断 / trace 可重放）
uv run python tools/enforcement_loop.py
```

> 两条使用提示：
> 1. 示例请求里的 `action_id` 是固定的：第二次执行会被**正确地**判成重放（`action_replay`，退出码 1）。
>    要重复演示就换一个 `action_id`，或先 `python tools/cleanup.py` 清掉 `.tmp/` 下的台账与审计。
> 2. 命令类示例（`exec.pwsh` / `exec.bash`）需要本机真的装了对应的 shell；
>    没有装时执行结果是 `failed(process_error)` / `repair_required`（退出码 1）——不会静默通过，
>    `enforcement.cli self-check` 也会把缺 shell 作为 warning 报出来。

**退出码**：`0` 允许或验证通过；`1` 阻断 / 需要修复（block、repair_required、inconsistent、rolled_back）；
`2` 配置或执行错误（注册表不合规或未审核、请求不合法、审计链损坏、用法错误）。

**命令类工具的最小权限**：注册表里的命令白名单只做完整匹配，而且命令里出现 `;` `|` `&` 反引号 `$(` `${` `>` `<`
或换行时**一律阻断**（`command_composition_blocked`）——单靠 `( .*)?` 这类正则会被 `echo hi ; 任意命令` 绕过。
命令里出现**被禁片段**（`../`、`..\`、`--output`、`--ext-diff`、`--no-index`）时同样阻断
（`command_fragment_blocked`）：白名单只描述"命令长什么样"，描述不了"这个选项会干什么"——
`git diff --output=<文件>` 完整匹配白名单，却会把内容写到受控工作区外的任意路径。
需要组合命令或被禁片段时必须改注册表、重新审核，并说明为什么安全。
**白名单不是沙箱**：任何被允许的命令只要会读仓库内的配置（`.git/config`、`.gitattributes` 的
textconv/filter），就仍可能被改写成执行外部命令；真正的隔离要靠运行时的文件系统与进程沙箱。

**已知边界**（不假装做到）：审计链是追加写的摘要链，能发现中间被改/被删，但**删尾部或整链重写发现不了**
（对外证明需要 Phase 7 的外部锚定/签名）；审批首版是“人工门禁写下的结构化记录”，不做签名与独立审批人名册。

**授权为什么不能“换参数复用”**：`action_hash` 覆盖工具身份、schema 哈希、规范化参数、主体、
权限、上下文摘要与 request/action 标识。参数改一个字符，哈希就变，旧授权立即失效——
这是数学，不是自觉。

### 代码验证器（Phase 5）

规则说"这件事不合规"，验证器负责给出**确定性证据**：代码 → AST → 依赖图 → Lint → 类型 → 测试 → 证据 → Policy。

```powershell
# 1) 验证器注册表是数据：谁能产生证据、在哪个阶段、用哪个工具、缺工具时算不算失败关闭
uv run python -m validators.cli registry
uv run python -m validators.cli registry --show tool.ruff

# 2) 外部工具探针：可用性、版本区间、配置文件（缺失就是 unavailable，不降级）
uv run python -m validators.cli probe

# 3) 只产出证据（不做 allow/block），退出码 0/1/2
uv run python -m validators.cli check examples/bad_controller.py --layer controller

# 4) 证据 + 判定（与 policy.check 同一条链路）
uv run python -m validators.cli pipeline examples/bad_controller.py --layer controller

# 5) 测试验证器：按变更集选择最小相关测试（--operation edit 才会触发测试规则）
uv run python -m policy.check tests/fixtures/validators/project/src/shop/order_service.py \
    --layer service --workspace tests/fixtures/validators/project \
    --operation edit --changed src/shop/order_service.py

# 6) 验证器闭环（AST 证据 / 失败关闭 / 测试选择 / 可重放 / 工具可追溯）
uv run python tools/validator_loop.py
```

**失败关闭**：关键验证器缺失、版本不符、超时、崩溃、配置错误、输出非法或"没有验证器为某个
checker 提供证据"时，需要它的规则以 `critical` 违规阻断——同一批里的其他 PASS 抵消不了它。
语法错误、动态 import 目标不是常量、项目内模块解析失败同样阻断：**解析不了的文件不能被判定为
"没有依赖问题"**。

**证据与判定分离**：验证器只产证据（`ValidationEvidence`），最终 allow / block 仍由 Policy Engine
决定；证据里带验证器 ID/版本、规则 ID、文件与行列、工具退出码、配置文件哈希，可逐条追溯。
证据不写进决策协议（协议仍是 `1.0`）：它在 `--json` 的 `evidence` 段与 `validators.cli` 里。

**外部工具**：Ruff / mypy / pytest 都是"外部工具"而不是本项目的 Python 依赖——版本区间与配置文件
在 `validation/validators.yaml`（数据）里声明，探针负责发现，缺失即失败关闭。
**前提**：`policies/coding/STYLE-*.yaml` 需要 PATH（或当前解释器同目录）上有 Ruff `>=0.6,<1`；
没有它时连正例都会以 `tool.ruff@1.0 unavailable` 失败关闭（`python -m validators.cli probe` 可自查）。
规则用到的诊断码全部来自 Ruff：`policies/coding/STYLE-*.yaml`（PEP 8）、`policies/coding/DOC-00{2..5}.yaml`（PEP 257 的形态要求）、
`policies/security/SEC-*.yaml`（OWASP Cheat Sheet）。**"规则声明了某个码"与"这个码被 `validation/ruff.toml` 选中"必须双向一致**，
否则那条规则永远拿不到证据（契约测试 `test_ruff_codes_are_declared_and_selected_in_both_directions` 守着它）。
类型检查端口与失败语义已经就位，但没有启用类型规则：本机与 CI 都没有装 mypy，
启用它会让所有 Python 文件在缺工具时一次性判红——这是数据决定的事，不是代码决定的。
逐篇的"哪篇文档变成了哪条规则、哪篇没有"见 `docs/architecture/规则转化覆盖报告.md`。

### 多 Agent 适配（Phase 6）

同一套规则与决策协议要服务多个 Agent Runtime。做法是把"某家 Agent 的报文"翻译成
**规范事件**，判定只在核心层发生一次：

```text
Agent Runtime → Adapter.to_policy_event → AgentRuntime.handle → Policy Engine
             → Adapter.to_agent_response → Agent Runtime
```

每家 Agent 的差异（事件名、字段名、工具名、阻断与审批能力）都必须写在
`adapters/<agent_id>/manifest.yaml` 里，并且**必须经过审核**——
哈希存在 `adapters/approved.json`，改声明就要重新审核：

```powershell
uv run python -m adapters.cli matrix                              # 支持矩阵（full / read_only / unsupported）
uv run python -m adapters.cli approve --reviewer <name>           # 审核能力声明（改完 manifest 必须重新跑）
uv run python -m adapters.cli check                               # 一致性套件：所有 Adapter 对同一组语义事件给同一套结论
uv run python -m adapters.cli events                              # 每个 Agent 的兼容性 fixture 是否存在
uv run python -m adapters.cli inspect --agent dsh --event e.json  # 看一条事件被翻译成了什么
uv run python tools/agent_loop.py                                 # 多 Agent 闭环（等价结论 / 执行一次 / 隔离 / trace / 熔断）
```

现在的支持矩阵（数据来源是 manifest，不是这段文字）：

| Agent | 上限 | 依据 |
| --- | --- | --- |
| `dsh` | **full 能力上限** | 有 PreToolUse（exit 2 阻断）与 PostToolUse；写动作还必须在运行时注入 Phase 5 evidence provider 与 Phase 4 enforcer |
| `generic-json` | **只读** | 协议完整，但接入方主动声明 `read_only`：写类动作显式拒绝 |
| `legacy-post-only` | **只读** | 只有 PostToolUse：副作用已经发生才能标错，不是阻断 |

这里的 `full` 是 manifest 推导出的**能力上限**，不是“所有工具都已登记并自动接线”。
目前 Phase 4 Tool Registry 未登记的 dsh 写类工具会得到 `enforcement_unavailable`，不会绕过治理。

四条硬规则：

1. **能力不足必须显式失败**：拦不住写类动作的 Agent 不会被标成完整 enforcement，
   受治理动作得到 `capability_unavailable`，而不是"跳过治理"；
2. **写链必须完整**：写类动作必须同时拿到 Phase 5 `EvidenceBundle`、Policy allow 与 Phase 4
   pre-check 授权；缺任一端口都失败关闭，PostToolUse 只做事后验证，绝不再次调用工具；
3. **跨 Agent 隔离**：审计与幂等键是 `<adapter.namespace>:<event_id>`，A 的判定不会替 B 放行，
   主体只认 Adapter 的显式声明（载荷自称会被拒绝），伪造父 trace 一律拒绝；
4. **循环可终止**：同一 Agent 在时间窗口内的受治理事件数到上限即熔断，
   两个 Agent 互相触发不会把预算烧完。

规范事件的外部 `payload` 只允许 `path` / `params` / `text` / `cwd`；依赖、结果存在性、
请求视图和摘要都由平台内部生成，外部载荷不能覆盖。

新增一个 Adapter 的完整流程（不需要改核心层）见
[Phase 6 实施记录](docs/engineering-policy-platform/phases/phase-6-multi-agent-adapters.md#实施记录)。

### Policy API（Phase 7）

核心能力可以经 HTTP 服务化，但**判定仍然只有一条路径**：`policy.engine.evaluate`。
API 只增加部署与信任边界（认证、租户隔离、预算、幂等、观测），不复制一份业务逻辑——
本地 SDK 与经 API 的决定整份相等（决策载荷 JSON 值相等；字段顺序不属于契约），
这条由闭环工具证明而不是由文档声明。

```powershell
$env:PYTHONPATH = "src"

# 1) 装配 / readiness / 传输契约自检（配置、租户、规则集、索引、验证器、观测日志）
uv run python -m policy_api.cli self-check

# 2) OpenAPI 契约快照：漂移即退出 1，改契约必须显式评审后 --write
uv run python -m policy_api.cli openapi --check

# 3) 进程内最小链路（不开端口）：live → ready → evaluate → retrieve
uv run python -m policy_api.cli smoke --token local-dev-token

# 4) 起服务（默认 http://127.0.0.1:8088；readiness 未过则拒绝启动）
uv run python -m policy_api.cli serve

# 5) 观测日志的对外锚定：封出链末值 / 校验日志是否被删尾或改写
uv run python -m policy_api.cli seal --out .tmp/artifacts/api-anchor.json
uv run python -m policy_api.cli seal --verify .tmp/artifacts/api-anchor.json

# 6) API 闭环（真端口 uvicorn）：八个场景，见下
uv run python tools/api_loop.py
```

闭环证明八件事：本地引擎与 HTTP API 的决策载荷**整份相等**（JSON 值相等，字段顺序不属于契约）；
两个协议消费者
（`generic-json` 进程内 / `http-api` 经 HTTP）对同一组语义场景走到同一套结论；
超时返回 504 而不是 allow；策略服务不可达时 Adapter 得到 `policy_unavailable` 的阻断；
幂等键重放返回原响应且换请求体得到 409；跨租户引用别人的 `decision_ref` 得到 403；
规则集不可用时 readiness 失败且 evaluate 得到 `rule_set_unavailable`；
观测日志的摘要链能对外锚定且删尾会被发现。

**部署数据在 [`api/`](api/README.md)**：租户边界、客户端令牌（只存 sha256）、
预算与限额、观测落点都在 [`api/policy-api.yaml`](api/policy-api.yaml) 里；
传输契约快照是 [`api/openapi.json`](api/openapi.json)。本仓库里的令牌是演示值
（`local-dev-token` / `dsh-agent-token` / `ops-monitor-token`），不是真实凭据。

**失败语义**：未认证 401、项目越权 403、限流 429、超大请求 413、幂等冲突 409、
预算耗尽 504（`*_timeout`）、依赖不可用 503（`rule_set_unavailable` /
`knowledge_unavailable` / `validator_unavailable` / `audit_unavailable`）。
**没有任何一条路径默认 allow**：超时、不可达、规则集读不出来都只会更严。

### LangGraph 编排（Phase 8）

`src/orchestration/` 是**上层编排消费者**：它回答"下一步做什么"，平台回答"允不允许"。
图状态只存引用（任务、阶段、artifact 哈希、Policy trace、验证摘要、计数与审批引用），
**不存正文**；每个节点单一职责，写类动作先问平台（evaluate）再交给 Phase 4 的受控执行链；
PASS/FAIL 只由结构化 Decision 决定，终态只由失败码决定（`blocked` / `needs_human` / `failed`）。

```powershell
$env:PYTHONPATH = "src"

# 1) 装配自检：图定义 / 引擎可用性（auto → langgraph 或参考引擎）/ 注册表审核 / checkpoint / 状态协议
uv run python -m orchestration.cli self-check

# 2) 图定义：节点、静态边与条件分支（分支名就是路由标签）
uv run python -m orchestration.cli graph

# 3) 跑一个任务（任务文件是数据：目标、验收条目与候选改动都在里面；需要可用的 Policy API）
uv run python -m orchestration.cli run --task .tmp/phase-8/task.json --engine auto

# 4) 读 checkpoint 摘要：阶段、revision、判定与失败码（恢复前先看这个）
uv run python -m orchestration.cli status --task-id demo-1

# 5) 编排闭环（真端口 uvicorn + 真受控执行 + 真 checkpoint 与恢复）
uv run python tools/orchestration_loop.py
```

**编排层只当消费者**：只有 `langgraph_engine.py` 导入工作流框架（构造引擎时延迟导入 +
主版本校验，不可用即 `EngineUnavailableError`）；核心层从不导入本包——删掉
`src/orchestration/`，规则、检索、验证器、受控执行与 API 照常独立运行。
`engine="auto"` 在没有 LangGraph 时回落到参考引擎，并在报告里**如实写明**用的是哪一个。

**恢复语义**（最容易被误解的一段）：`StepExecutor` 先执行、再路由、再把"下一步"落盘，
所以"checkpoint 之后崩溃"不会重跑刚完成的节点；checkpoint 带一轮的兼容性凭据
（`rule_set_hash` / `index_version` / `tool_schema_hash` / 协议世代），恢复时与**当前平台**
比对——规则集或索引变了就清掉旧 trace 与旧验证结果回到检索节点重评（**不沿用旧 allow**），
工具 schema 变了旧审批作废，协议世代变了直接拒绝恢复，拿不到凭据按"变了"处理。
副作用之前先写一笔"意图"并立刻刷盘：恢复时发现"开工未结算"就交给人
（`side_effect_unknown`），既不重放也不假装成功。

**失败语义**：平台不可用 / trace 断裂 / 证据缺失 → `blocked`；上限击穿（repair 轮次、
工具调用、节点执行、token、费用、墙钟）、审批不合法、副作用状态未知 → `needs_human`；
编排自身损坏（未知节点、未知路由标签、checkpoint 版本不可读）→ `failed`。
**没有任何一条路径是"默认放行"**：正反例见 `tests/security/test_orchestration_adversarial.py`
与 `tools/orchestration_loop.py`。

### 测试

```powershell
uv run python -m pytest tests/unit -q            # 575 用例：模型、规范化、范围矩阵、决策聚合、分块/查询/Context、注册表/参数/授权/审计、AST 事实/依赖图/适配器分类、API DTO/配置/预算/幂等/指标、编排状态/上限/失败码/checkpoint/审批语义
uv run python -m pytest tests/contract -q        # 182 用例：决策协议快照 + dsh/多 Agent 映射契约 + 检索端口契约 + 受控执行协议 + 验证器证据协议 + API 传输契约（OpenAPI 快照 / 版本钉死 / 核心层不依赖框架）+ 编排引擎等价（两个引擎逐字段一致）与依赖方向
uv run python -m pytest tests/integration -q     # 258 用例：真实 CLI、性能基线、dsh Hook、检索索引/基线、受控执行器与闭环、验证器流水线、多 Agent 运行时、HTTP API（ASGI 进程内）、编排恢复/幂等/平台故障与真注册表端到端
uv run python -m pytest tests/security -q        # 84 用例：注入、越权、缓存失效、检索与验证器失败关闭、审批伪造、日志失效、多 Agent 对抗、API 未认证/跨租户/不可达（不返回 allow）、编排的伪造审批与恢复绕过
uv run python -m pytest -q                       # 全部收集 1099 用例；本机实跑 1098 passed、1 skipped（Windows 不允许普通用户创建符号链接）
```

### 记录性能基线

```powershell
uv run python tools/policy_bench.py --counts 10 100 1000
```

固定随机种子生成规则，记录每次评估的耗时与内存峰值。**只建立基线，不做优化**。

### 想搞懂代码在做什么

看学习手册：每个阶段一份，用真实模块逐段演示，每个代码单元后面都写明"这段输出说明了什么"。

| 手册 | 内容 |
| --- | --- |
| [Phase 0](docs/learning/phase-0/walkthrough.ipynb) | 一条规则从 YAML 到 PASS/FAIL 的完整链路 |
| [Phase 1](docs/learning/phase-1/walkthrough.ipynb) | 上下文规范化、范围匹配、严重级别与可解释决策 |
| [Phase 2](docs/learning/phase-2/walkthrough.ipynb) | dsh 事件映射、Hook 阻断、失败关闭与真实沙箱闭环 |
| [Phase 3](docs/learning/phase-3/walkthrough.ipynb) | 分块、FTS5 检索、来源控制、Context 预算与"知识不可用" |
| [Phase 4](docs/learning/phase-4/walkthrough.ipynb) | 工具注册表、参数绑定的授权、受控执行、事后验证与审计链重放 |
| [Phase 5](docs/learning/phase-5/walkthrough.ipynb) | AST 事实与依赖图、外部工具适配器与失效分类、测试选择、证据 → 判定与失败关闭 |
| [Phase 6](docs/learning/phase-6/walkthrough.ipynb) | 规范事件、能力声明与支持矩阵、一致性套件、跨 Agent 隔离与循环熔断 |
| [Phase 7](docs/learning/phase-7/walkthrough.ipynb) | DTO 与领域模型分离、错误码 → 状态码、租户与令牌边界、预算与超时、幂等台账、本地与经 API 的决策整份相等 |
| [Phase 8](docs/learning/phase-8/walkthrough.ipynb) | 最小图状态、循环上限、两个引擎跑同一份 spec、checkpoint 与恢复、人工审批、失败关闭表 |

不想开 Jupyter 就运行同内容的纯 Python 版本（`walkthrough.py`）。

### 生成阶段验收证据

```powershell
uv run python tools/phase_evidence.py            # 默认写到 .tmp/artifacts/phase-8-evidence.json
```

证据包含实现版本、规则集哈希（`sha256:...`）、测试命令、用例数、失败数与 JUnit 报告路径，
格式遵循[测试策略](docs/engineering-policy-platform/testing/test-strategy.md)，不记录密钥或隐私数据。

### 清理临时文件

所有会话产物都写在 `.tmp/`（pytest 缓存、阶段证据、notebook 演示文件），该目录已在 `.gitignore` 中。
用完即删，仓库无需保留：

```powershell
uv run python tools/cleanup.py --dry-run   # 先看会删什么
uv run python tools/cleanup.py             # 删除 .tmp/、__pycache__/、.pytest_cache/、.uv-cache/
```

## 目录结构

```text
.
├── .github/workflows/phase-8.yml      # CI：单元 / 契约 / 集成 / 对抗测试、AST 证据重放、验证器闭环、检索基线、注册表审核、受控执行闭环、多 Agent 一致性套件与支持矩阵、API 自检 / OpenAPI 快照 / API 闭环、手册与证据
├── docs/
│   ├── architecture/                  # 本仓库的技术架构图（draw.io 两页）与三份说明：功能清单 / 使用说明 / 规则文档转化为规则
│   ├── dora-capabilities/             # DORA 软件交付能力指南离线镜像（37 篇）
│   ├── dotnet-design-guidelines/      # .NET Framework 设计准则离线镜像（49 篇）
│   ├── engineering-policy-platform/   # 本项目的分阶段架构、契约与测试路线
│   ├── gitlab-code-review/            # GitLab 评审规范离线镜像（20 篇）
│   ├── google-eng-practices/          # Google 工程实践指南离线镜像（14 篇）
│   ├── learning/                      # 面向人的学习手册（按阶段：phase-0 … phase-8）
│   ├── owasp-cheatsheets/             # OWASP 代码安全指南离线归档（118 篇）
│   └── python-pep-code-style/         # PEP 8 / PEP 257 文档镜像（11 篇）
├── examples/                          # 可重放的 CLI 示例（正例 / 反例）
├── examples/dsh/                      # dsh 接线示例：hooks.json / dsh-adapter.yaml / profile-patch.yml
├── examples/enforcement/              # 受控执行示例请求（编辑 / 高风险命令 + 审批）
├── knowledge/
│   ├── corpus.yaml                    # Phase 3 摄取清单：数据集、许可、tier、可见性、检索预算
│   └── query_expansion.yaml           # 受控中英术语表（跨语言词法桥接，只登记术语）
├── policies/                          # 规则是数据：43 条 = architecture（ARCH-001）+ coding（DOC/STYLE）+ testing（TESTING）
│                                      #   + security（SEC-*，由 OWASP 镜像提炼）；每条 standard 规则带正反例夹具与 chunk 级溯源
├── adapters/                          # Phase 6 能力声明（数据）：每个 Agent 的 manifest + adapter 配置 + 事件样本 + 已审核哈希
├── registry/                          # Phase 4 Tool Registry：工具授权表 + 已审核哈希清单
├── validation/                        # Phase 5 验证器数据：注册表、项目档案（语言/组件）、测试布局、工具配置
├── api/                               # Phase 7 部署数据：policy-api.yaml（租户/客户端/预算）+ openapi.json（传输契约快照）
├── src/policy/                        # 核心库：models / evidence / checkers / context / scope / loader / engine / check
├── src/validators/                    # Phase 5 验证器：python_ast / depgraph / docstrings / selection / pipeline / cli / adapters
├── src/enforcement/                   # Phase 4 受控执行：registry / action / approvals / audit / ledger / precheck / executor / drivers / postcheck / trace / cli
├── src/adapters/                      # Phase 6 适配层：models（规范事件）/ base（协议与注册表）/ runtime（多 Agent 隔离与熔断）/ conformance（一致性套件）/ cli
├── src/adapters/dsh/                  # Phase 2 dsh Adapter：adapter（纯映射）/ hooks（Hook 与审计）/ README
├── src/retrieval/                     # Phase 3 检索层：chunker / corpus / store / indexer / query / retriever / vector / context / cli
├── src/policy_api/                    # Phase 7 服务化层：models（DTO/版本）/ errors / config / auth / services / runtime / timeout / idempotency / observability / ops / app（FastAPI）/ contract / cli / testing / probe（HTTP Adapter）
├── src/orchestration/                 # Phase 8 编排层（平台消费者）：models / errors / limits / checkpoint / approvals / client / tools / nodes / graph / engines / langgraph_engine / runtime / cli / README
├── tests/
│   ├── fixtures/validators/           # Phase 5 夹具项目 + 假工具（失效与边界行为）
│   ├── fixtures/agent_events/         # Phase 2/6 事件样本与一致性套件的探针工作区
│   ├── fixtures/api/                  # Phase 7 API 夹具（租户规则 + 演示令牌说明）
│   ├── unit/                          # 模型、规范化、范围矩阵、决策聚合、分块、查询、Context、AST/依赖图/适配器、API DTO/配置/预算/幂等
│   ├── contract/                      # 决策协议快照、dsh 映射契约、多 Agent 能力声明与规范事件契约、检索端口契约、API 传输契约与 OpenAPI 快照
│   ├── integration/                   # 真实 CLI 子进程、性能基线、检索索引与增量、多 Agent 一致性套件与隔离、HTTP API（ASGI 进程内）
│   ├── security/                      # 对抗测试：注入、越权、缓存失效、检索失败关闭、伪造 trace、跨 Agent 越权、API 未认证/跨租户/不可达、编排的伪造审批与平台故障
│   ├── orchestration_support.py       # Phase 8 测试助手（脚本化客户端、受控工作区、装配与运行）
│   └── fixtures/                      # 决策快照、dsh 事件、检索语料与固定评测集
├── tools/                             # 仓库脚本：阶段证据、性能基线、检索评测、dsh 沙箱闭环、多 Agent 闭环、API 闭环、编排闭环、notebook 生成、清理
├── pyproject.toml                     # 依赖清单、包配置、pytest 配置
├── requirements.in / requirements.lock # 直接依赖与锁定版本
├── README.md
└── .tmp/                              # 会话临时产物（证据、pytest 缓存、notebook 演示），用完可删
```

## 技术栈

| 项 | 选择 | 说明 |
| --- | --- | --- |
| 语言 | Python ≥ 3.11（本机验证 3.13.11） | 文档选型 Phase 0–1 指定 |
| 依赖 | pydantic 2、PyYAML 6；FastAPI + uvicorn（Phase 7 传输层）；langgraph 1.2（Phase 8 编排层） | 类型化规则与 YAML 解析；**核心层不依赖 Web 框架，也不依赖工作流框架**——只有 `src/policy_api/app.py` 需要前者，只有 `src/orchestration/langgraph_engine.py` 需要后者（构造引擎时延迟导入 + 版本校验，不可用即失败关闭） |
| 检索 | SQLite FTS5（标准库 sqlite3，无第三方依赖） | Phase 3 的可解释检索基线；向量检索是可替换端口，本阶段**未采纳**（评测见阶段记录） |
| 受控执行 | 标准库 + pydantic（无第三方依赖） | Phase 4：Tool Registry 是数据（YAML），授权 / 幂等 / 审计链落在追加写 JSONL 上，执行驱动按注册表声明选择 |
| 测试 | pytest 8+（本机验证 9.1.1） | 单元 + 契约 + 集成 + 对抗四层；API 用进程内 ASGI 客户端（httpx），不需要端口 |
| 包管理 | uv（建虚拟环境与安装）；锁文件是 `requirements.lock` | 仓库未提交 `uv.lock`，依赖锁定以 `requirements.lock` 为准，CI 从它安装 |
| CI | GitHub Actions | `.github/workflows/phase-8.yml`（Phase 0–4 重放、AST 证据重放、验证器注册表/探针/闭环、检索基线、注册表审核、受控执行闭环、多 Agent 一致性套件/支持矩阵/闭环、API 自检/OpenAPI 快照/API 闭环、仓库一致性、凭据扫描） |
| 代码验证器 | 标准库 ast + 外部工具（Ruff / mypy / pytest 均由探针发现，不是包依赖） | Phase 5：注册表与项目档案是数据（`validation/`），证据带版本与配置哈希，缺工具即失败关闭 |

Phase 0–4 明确不引入：LangGraph、向量数据库、FastAPI、MCP、Agent SDK 与任何 LLM 调用；
Phase 7 引入了 FastAPI/uvicorn（只在传输层），Phase 8 引入 LangGraph（只在编排层，且只是消费者）。
向量数据库、MCP 与任何 LLM 调用至今没有引入。
Phase 2 里 dsh 只作为**外部进程与线协议**存在：适配器不导入 dsh 的类型，核心层更不知道 dsh 的存在。
Phase 3 的检索层不导入任何 Agent SDK、Web 框架或向量库：embedding 是端口（`retrieval.vector`），
用确定性本地实现做对照评测；固定评测集显示它没有跑赢 FTS5，因此没有进入默认链路。
依赖引入门禁见[技术选型与目标目录](docs/engineering-policy-platform/03-technology-and-layout.md)。

## 架构约定

- 规则是数据，不是提示词：`policies/**/*.yaml` 由 Loader 解析为不可变模型；
- 核心层（`src/policy`）不导入任何 Agent 框架、Web 框架或向量库；
- 未知顶层字段、未知严重级别、未知 scope 维度、未知操作、未知 enforcement 一律报错，不静默忽略；
- 一次加载要么全部成功、要么不替换规则集；
- 相同输入必须得到相同结论，violation 按 `rule_id` 稳定排序，规则集哈希与加载顺序无关；
- 上下文只接受显式字段：不根据文件名推断主体、权限或审批状态；
- 决策协议带 `schema_version`，未知版本拒绝消费，绝不降级为 allow；
- Agent Adapter 只做协议转换：不猜 layer/language/principal，声明不出来就失败关闭；
  未知事件、未知工具、缺失路径一律拒绝，并把"不受本阶段治理"显式记进审计；
- 检索层的原始输入永不拼进 SQL / FTS 表达式：先规范化成受控词项，再以参数形式查询；
- 权限只来自显式 AccessScope，查询文本不能扩权；返回项必须带来源路径、URL、许可与文本哈希；
- 检索不可用时返回 `knowledge_unavailable`，绝不回退到"模型记忆里的规范"，
  相似度分数只用于内部排序，绝不作为授权信号；
- 受控工具的授权与**具体动作**绑定：`action_hash` 覆盖工具 schema、规范化参数、主体与上下文，
  参数变化即失效；授权短时效、单次使用，执行器不解析任何自然语言批准；
- 风险分类、参数白名单、权限、审批门禁与事后验证器都是 `registry/tool-registry.yaml` 里的数据，
  模型不能自行声明"我这个动作属于哪一类"；运行时描述与已审核哈希不一致的工具不可使用；
- 执行后必须交证据（文件前后哈希、diff 摘要、退出码，证据不足按 `repair_required` 处理），
  回滚能力按工具声明：声明不了就写 `unsupported`，绝不假装所有副作用都可撤销；
- 编排层是**消费者**：它只回答"下一步做什么"，判定仍只有平台一条路径，
  而且是仓库里唯一导入工作流框架的地方——删掉 `src/orchestration/`，平台照常独立运行；
- 图状态里不放正文：需求原文、文件内容、工具输出与凭据只以摘要/引用存在，
  checkpoint 是"单文件 + 原子替换"并带版本与兼容性凭据，相同输入得到逐字节相同的状态；
- PASS/FAIL 只由结构化 Decision 决定，终态只由失败码决定（`blocked` / `needs_human` / `failed`），
  未知路由标签、未知节点、非契约返回值一律失败关闭；
- 恢复不沿用旧 allow：规则集、索引或工具 schema 变了就清掉旧 trace 与旧验证结果重新评估，
  拿不到当前凭据也按"变了"处理；恢复还会清掉上一轮的失败标记；
- 人工审批绑的是平台口径的 `action_hash`（覆盖参数、主体、工具 schema、上下文与 trace），
  "图到达了审批节点"永远不等于用户批准；副作用前先写"意图"并立刻刷盘，
  恢复时发现"开工未结算"即交给人（`side_effect_unknown`），不重放也不假装成功。

## 约定

### 提交信息

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```text
<type>(<scope>): <subject>
```

常用 type：`feat`、`fix`、`docs`、`refactor`、`test`、`chore`、`perf`、`build`、`ci`。
主题行使用祈使语气，不超过 72 字符；破坏性变更在正文以 `BREAKING CHANGE:` 说明。

### 分支

主分支为 `main`。功能开发使用 `feat/<topic>`、修复使用 `fix/<topic>`。

### 文本文件

统一使用 UTF-8 编码与 LF 换行（由 `.gitattributes` 强制，不依赖各机器的 `core.autocrlf`）。
提交前请删除行尾空白，文件以单个换行符结尾（由 `.editorconfig` 提示）。
