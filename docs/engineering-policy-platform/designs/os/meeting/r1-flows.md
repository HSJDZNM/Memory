# R1 操作流程整理 v1（角色：操作流程分析师 · task-2）

> 依据：`docs/engineering-policy-platform/designs/os/meeting/r0-facts.md` 的 **F1–F39 / N1–N6**，只引用、不另造口径。
> 标记：【实测】= 本轮真跑过并留下退出码；【读码】= 读源码/数据并给 `file:line`；【提案】= 今天不存在；查不到写【未知，需核验】。
>
> **实测环境**：Windows + `pwsh`；Python 3.13.11（`python` 与 `.venv\Scripts\python.exe` 两套解释器结论一致）；
> 所有 `python -m ...` 均先 `$env:PYTHONPATH="src"`；工作目录 = 仓库根；**实测时刻 2026-09-22 20:33–20:45（+08:00）**。
>
> **⚠️ 本工作区是活的（本轮最重要的环境事实）**：`policies/` 规则文件在实测期间从 **26** 增到 **44**
> （`(Get-ChildItem policies -Recurse -File).Count`），新增文件全部未跟踪（`git status --porcelain policies`），由会议其他成员并发写入。
> 规则集身份随之漂移：20:33 `sha256:a6c9655a…` → 20:43:24 `sha256:a90e64ac…`（`python -m policy.check --check-rules`）。
> 后果（实测 + 读码）：绑定规则集身份的一切立刻失效——检索缓存、Phase 7 观测摘要（`rule_set_hash`）、
> Phase 8 checkpoint 凭据（`src/orchestration/checkpoint.py:54` `_REVALIDATE_DIMENSIONS`）。
> 因此本文所有条数都带时刻；**流程不依赖条数，依赖判定路径与失败语义**。
>
> **20:49 复测更正（工作区继续变化）**：语料条目 27 → **42**（`retrieval.cli verify` → `datasets=6 entries=42`）；
> `knowledge/corpus.yaml` 的 `rule_sources` 0 → **39 条**，`retrieval.cli rules --rule DOC-001` **exit 0**、
> `--rule STYLE-003` exit 0（带 chunk 级溯源），而 `--rule ARCH-001`、`--rule STYLE-013` 仍 exit 1。
> 因此 §C 台阶 7 与 §9 第 9 行的"溯源今天走不通"只对**部分规则**成立，已按上述实测修正口径。

## 0. 共用口径（八条流程只引用，不重复解释）

| # | 口径 | 锚点 |
| --- | --- | --- |
| 0.1 | 判定只有一条路径 `policy.engine.evaluate`；本地 / dsh / API / 编排都只是消费者 | F5、F31；`docs/architecture/功能清单.md:25-29` |
| 0.2 | 判定三值 `allow` / `allow_with_warnings` / `block`；`PASS` 只是 CLI 措辞 | `术语与口径.md:23`、`:276` |
| 0.3 | CLI 退出码 `0` 通过 / `1` 违规或漂移 / `2` 配置或执行错误 | `src/policy/check.py:71-73` |
| 0.4 | **退出 0 ≠ allow**：退出码只说明命令跑到最后，结论看决策载荷 | `术语与口径.md:170`；本文 B/D 各有一条实测反例 |
| 0.5 | `skipped_rules ≠ 通过`；跳过必须写明维度原因 | `术语与口径.md:27`、`src/policy/checkers.py:33` |
| 0.6 | 编排终态只有 `blocked` / `needs_human` / `failed`；由 `STATUS_BY_CODE` 推导 | `src/orchestration/errors.py:127-161` |
| 0.7 | API 错误码 → HTTP 状态由 `STATUS_BY_CODE` 推导，调用方不能自定义状态 | `src/policy_api/errors.py:73+` |
| 0.8 | 审计链是追加写摘要链，**不是防篡改日志**；对外锚定靠 `seal`，锚与日志必须分离 | F25、`src/policy_api/cli.py:207-213` |

**红线（对所有八条流程生效）**：`allow` / `allow_with_warnings` / `block` 只能由 `policy.engine.evaluate` 产出；
界面与脚本不得复算、不得用退出码代替载荷、不得把 `skipped` 当通过、不得在失败时降级为放行。
下文的"谁负责判定"列只回答两件事：这一步的**结论**谁产出、这一步**失败了会发生什么**。

---

## A. 首次装配与引导（clone → 能跑）

**触发者**：新加入的人或 Agent（无会话身份，见 N5）。
**前置状态**：只有仓库；无 `.venv` 时依赖未装；`.tmp/retrieval/` 索引是构建产物（F14、F19）。

| 步 | 动作（命令 / 路由） | 标记 | 结果 | 谁负责判定 |
| --- | --- | --- | --- | --- |
| A1 | `uv venv` → `uv pip install -r requirements.lock`（无 uv 时 `python -m pip install -r requirements.lock`） | 【实测】探测：`uv 0.7.19`、`requirements.lock` 与 `pyproject.toml` 均存在 | 依赖装齐 | 无判定；锁文件是唯一真相（README.md:29-45） |
| A2 | 让解释器找到 src 布局：`$env:PYTHONPATH = "src"` | 【实测】本轮全部命令都靠它 | 后续 `python -m ...` 可导入 | 无判定 |
| A3 | 规则集加载自检：`python -m policy.check --check-rules` | 【实测】exit 0；20:43:24 输出 `rules: 44 (sha256:a90e64ac…)` | 规则集可加载 | **`policy.loader` 判定**；任一条坏 → 整体不加载、exit 2（原子性） |
| A4 | 语料与镜像自检：`python -m retrieval.cli verify` | 【实测】exit 0：`corpus: knowledge/corpus.yaml v1 \| datasets=6 entries=27 \| OK`（20:33）；**20:49 复测为 `entries=42`** | 清单 / 许可 / sha256 一致 | **`retrieval.corpus` 判定**；漂移 → exit 1（F14、AGENTS 约束 12） |
| A5 | 索引重建：`python -m retrieval.cli index`；幂等询问：`... index --check` | 【实测】隔离库 `.tmp/r1-flows/index.sqlite3`：exit 0，`documents=27 chunks=535 oversized=6`；`--check` exit 0 `index is up to date` | 索引就绪 | 判定属于 indexer（幂等短路）；"要不要重建"由 `--check` 说，不由脚本猜 |
| A6 | 受控执行自检：`python -m enforcement.cli self-check` | 【实测】exit 0，`tools=9 approved=9`，**warning**：`exec.pwsh: 本机找不到 'pwsh'` | 注册表 / 审核 / 审计 / 台账 / 驱动就绪 | 注册表审核状态由 `enforcement.registry` 判定；warning 不是 pass |
| A7 | Hook 接线自检：`python -m adapters.dsh.hooks --config examples/dsh/dsh-adapter.yaml --hooks-config examples/dsh/hooks.json --self-check` | 【实测】exit 0，stderr `[policy] self-check ok` | 预算不等式与命令指向自检通过 | Hook 自己判定（dsh 侧超时/崩溃=放行，见 G） |
| A8 | API 装配 + readiness：`python -m policy_api.cli self-check` | 【实测】exit 0：`readiness: ready（2 个租户可服务）` + 18 项 `[ok]` | 配置 / 租户 / 契约 / 预算齐备 | `policy_api.ops.readiness_report`（`src/policy_api/ops.py:138-162`） |
| A9 | 契约快照：`python -m policy_api.cli openapi --check` | 【实测】exit 0 `与快照一致（api_version=1.0）` | 传输契约未漂移 | `contract.self_check`；漂移 → exit 1，只能显式 `--write` |
| A10 | 编排装配自检：`python -m orchestration.cli self-check` | 【实测】exit 0：langgraph 1.2.11、`auto → langgraph`、8 节点 / 6 边 / 2 分支 | 图 / 引擎 / 注册表 / checkpoint 就绪 | 编排自检只回答"装配是否可用"，不回答"允不允许" |
| A11 | 启动服务（需要 HTTP 面时）：`python -m policy_api.cli serve` | 【读码】`src/policy_api/serve.py:53-55`：readiness 未通过**拒绝启动** | —— | 就绪门禁由服务自己判定（F12） |

**显式失败状态与退出码**：A3 坏规则 → `2`（实测：我用 `.tmp/r1-flows/broken-rules/BAD-001.yaml` 造了未知 severity，stderr 逐字段列出 `Field required` / `severity: Input should be 'info','warning','error','critical'`）；A4 哈希漂移 → `1`；A9 契约漂移 → `1`；A10 缺 langgraph → `auto` 回落参考引擎并**如实写进 RunReport.engine**（唯一工作流框架导入点仍是 `langgraph_engine.py`，F5）。
**证据落点**：`.tmp/artifacts/`（阶段证据）、`.tmp/retrieval/index.sqlite3`（索引）、`api/openapi.json`（契约快照）。
**人工介入点**：无强制项；A6 的 warning 需要人决定"要不要装 `pwsh`"，否则 `exec.pwsh` 永远 `process_error`（G 有实测）。
**绝对不能由界面 / 脚本判定**：A3 的"规则集是否可用"、A4 的"是否漂移"、A8/A9 的就绪与契约结论。脚本能做的最多是**转发退出码**，转发不等于判定。

---

## B. 日常判定（本地 CLI 判定 → 决策协议载荷 → 检索上下文 → 证据）

**触发者**：人（终端）或 CI。
**前置状态**：A3–A5 已通过；被检查文件在工作区内。

| 步 | 动作（命令 / 路由） | 标记 | 结果 | 谁负责判定 |
| --- | --- | --- | --- | --- |
| B1 | 判定：`python -m policy.check examples/bad_controller.py --layer controller` | 【实测】exit **1**，末行 `FAIL: decision=block（error=1）`，违规含 `ARCH-001@1 @ dependency:10` | 结构化 Decision | **`policy.engine.evaluate`（唯一）**；CLI 只做包装与退出码 |
| B2 | 范围不匹配的反例：`... examples/good_controller.py --layer service` | 【实测】exit 0，`ARCH-001` 进 `skipped`：`layer service != controller` | "没规则管它"≠"规则放行" | **`policy.scope` 判定**；界面不得把 skipped 渲染成通过 |
| B3 | 机器可读载荷：`--json` 落盘 | 【实测】顶层键 `['context','evidence','exit_code','reported_imports','result','rule_set']`；`result.decision=block`、`schema=1.0`、`policy=phase-1` | 可被下游原样解析 | 协议由 `policy.models` 钉死（`SCHEMA_VERSION`/`POLICY_VERSION` 只从核心取值） |
| B4 | 证据：`policy.check` 已内联跑验证器 | 【实测】输出 `validators: py.ast@1.0 / py.depgraph@1.0 / py.docstring@1.0 / py.source@1.0 / tool.ruff@1.0` | 判定带证据 | 验证器**只产证据不判定**（F37、AGENTS 约束 19） |
| B5 | 检索上下文：`python -m retrieval.cli context "代码评审需要检查哪些方面" --decision .tmp/r1-flows/decision.json` | 【实测】exit 0，38 行输出；含权威块 `[P1] ARCH-001@1` 与参考块 `[K1] … url/license/text_hash/chunk` | Engineer Context | 检索**不授权**；权限只来自 `AccessScope`（F14、AGENTS 约束 11） |
| B6 | 无结果与不可用是两种状态：`retrieval.cli query "zzqqxx-不存在词项-zzqqxx"` | 【实测】exit **1**，`status: empty (no_results)` | 显式状态 | 由检索层判定；**不得回退到模型记忆** |

**实测踩坑（值得写进操作规范）**：PowerShell 的 `Out-File -Encoding utf8` 会给决策载荷写 BOM，
再喂给 `retrieval.cli context` 直接 exit **2**：`config error: 决策载荷不是合法 JSON（Unexpected UTF-8 BOM）`。
可用 `cmd /c "set PYTHONPATH=src&& python -m policy.check ... --json > .tmp\decision.json"` 规避（本轮实测 exit 0 的路径）。
**显式失败状态与退出码**：`1` = block/allow_with_warnings 或"无结果"；`2` = 配置或执行错误（决策载荷非法、规则损坏、缺 `--layer`）。
**证据落点**：决策载荷（`--json`）、`retrieval.cli stats` / `index --json` 的 run 报告、`tests/fixtures/decisions/` 协议快照。
**人工介入点**：需要人判的是"选哪条规则 / 要不要改规则"（台阶 4），不是"允不允许"。
**绝对不能由界面 / 脚本判定**：`decision` 三值与 `skipped_rules` 语义；界面只能原样渲染响应字段（B2 的红线同源）。

---

## C. 规则文档 → 可执行规则（台阶 1–7 全链路）

**触发者**：人（台阶 4 是唯一人工步骤）。
**前置状态**：镜像在 `docs/<mirror>/` 且带 `manifest.json`（F14）。
**注意**：台阶 1–7 与 Phase 0–8 是三套独立编号，图上另有门禁 ①②③（F6、术语与口径 §2）。

| 台阶 | 动作（命令 / 数据） | 标记 | 结果 / 门禁 | 谁负责判定 |
| --- | --- | --- | --- | --- |
| 1 镜像与哈希登记 | `docs/<mirror>/**` + `manifest.json`（6 套镜像） | 【读码】`src/retrieval/corpus.py`；【实测】`verify` 报 `datasets=6 entries=27` | 台阶 1 自身不挂门禁，产物被 ① 校验 | 无人判定；只登记 |
| 2 语料登记 | 改 `knowledge/corpus.yaml` → **门禁 ①**：`python -m retrieval.cli verify` | 【实测】exit 0 | 条目在 manifest 里、许可在、sha256 一致 | `retrieval.corpus` 判定；漂移 → exit 1 |
| 3 分块与索引 | `python -m retrieval.cli index` → **门禁 ②**：`index --check` | 【实测】27 文档 / 535 chunk / oversized 6；`--check` exit 0 | 表 `documents/chunks/chunks_fts/rule_sources/schema_meta` | indexer 判定幂等；"要不要重建"由 `--check` 说 |
| 4 提炼（唯一人工步骤） | 人读 chunk，选 checker 与字段 | 【读码】规则文档 §3 台阶 4 | 产物是"候选规则字段" | **人**；但"能不能成为规则"由台阶 5/6 的加载与覆盖判定 |
| 5 规则文件 | 写 `policies/<domain>/<ID>.yaml` → **门禁 ③**：`python -m policy.check --check-rules` | 【实测】exit 0（44 条）；坏规则 exit **2** | 原子加载：一条坏 = 全部不加载 | **`policy.loader`**；界面只能预演（G4 提案），不能自己校验 |
| 6 验证器覆盖 | `python -m validators.cli registry`；`python -m validators.cli probe` | 【实测】registry exit 0（`py.source/py.ast/py.depgraph/py.docstring/tool.ruff/tool.mypy/tool.pytest`）；probe exit 0 且报 `tool.mypy: unavailable`、`缺失或不匹配的关键工具：1（用到它们的规则会失败关闭）` | 每个 checker 必须有验证器产证据 | **`validators.registry` + `policy.checkers`**；缺工具 = critical 阻断，不是跳过（F39） |
| 7 生效、溯源与变更管理 | `python -m retrieval.cli rules --rule ARCH-001` | 【实测 20:33】exit **1**：`没有登记的来源溯源`；**【20:49 更正】**`rule_sources` 已从 0 增到 **39 条**：`--rule DOC-001`、`--rule STYLE-003` **exit 0**（带 chunk 级溯源），`--rule ARCH-001`、`--rule STYLE-013` 仍 exit 1 | 溯源是**约定**，登记位与校验已就位、**部分规则已登记** | 由检索层判定；"未登记"必须是显式状态，不得渲染成"无来源"或"已登记" |
| 7b 生效路径（写入侧） | 改注册表 → `python -m enforcement.cli registry --approve --reviewer <name>`；改 `policies/` → 走 `orc.policy.edit`（`approval: required`） | 【读码】`src/enforcement/cli.py:729-730`；`registry/tool-registry.yaml:317-345` | 未审核哈希不一致 → 该工具不可用（F15） | 授权判定只在 `enforcement.precheck`；**审批不是界面能自签的** |

**显式失败状态与退出码**：门禁 ① exit 1；门禁 ② exit 1（需重建）；门禁 ③ exit 2（配置错误）；台阶 6 缺工具 → 判定侧 critical → `block`（exit 1）。
**证据落点**：`verify` 的 run 报告、`index --json`（含 `index_version` 与逐文档 `hash_drift`）、`--check-rules` 的 `sha256`、`validators.cli registry`。
**人工介入点**：台阶 4（提炼）与台阶 7 的审批（改规则集 / 改注册表）。
**绝对不能由界面 / 脚本判定**：门禁 ③ 的加载结论与门禁 ② 的索引结论必须调用后端同一套代码（`policy.loader` / `retrieval.corpus`），
界面自抄枚举（checker 6 选 1、scope 6 维、severity 4 值）就是第二份判定逻辑（见 B2 争议）。

---

## D. Agent 接入（能力声明 → 审核哈希 → 工具表一致性 → Hook 接线自检 → 闭环）

**触发者**：接入方 + 人工审核人。
**前置状态**：`adapters/<agent_id>/` 有 manifest / adapter 配置 / 事件样本（F17）。

| 步 | 动作（命令 / 数据） | 标记 | 结果 | 谁负责判定 |
| --- | --- | --- | --- | --- |
| D1 | 能力声明落数据：`adapters/<agent_id>/manifest.yaml` | 【读码】F17；能力上限由声明推出（F35） | 上限 = `full` / `read_only` | `adapters.base` 判定上限；运行时不得猜 |
| D2 | 审核哈希：`python -m adapters.cli approve --reviewer <name>` | 【读码】`src/adapters/cli.py:425-433`；写 `adapters/approved.json` | 哈希进已审核清单 | 未审核或漂移 → 拒绝接入（F35） |
| D3 | 支持矩阵：`python -m adapters.cli matrix` | 【实测】exit 0：`dsh FULL`、`generic-json READ-ONLY`、`legacy-post-only READ-ONLY` | 三个消费者 | 矩阵由 manifest 推出，不由文字声明 |
| D4 | 协议一致性套件：`python -m adapters.cli check` | 【实测】exit 0：`一致性套件：87 项检查 / pass` | 事件 / 工具 / 阻断能力逐项对齐 | 场景是语义描述、Adapter 自己渲染；不支持必须显式失败 |
| D5 | 事件样本：`python -m adapters.cli events` | 【实测】exit 0，列出 3 个 Agent 的 fixture 路径 | 样本存在性 | 无判定 |
| D6 | 单条事件预检：`python -m adapters.cli inspect --agent dsh --event tests/fixtures/agent_events/dsh/pre-tool-use-edit-block.json --json` | 【实测】exit **0** 而 `outcome_code=context_error` | **退出 0 ≠ 结论** | 结论在载荷里；脚本不得读退出码替代 |
| D7 | Hook 接线自检：`--self-check`（同 A7） | 【实测】exit 0 | 预算不等式成立 | Hook 自检 |
| D8 | Hook 真实阻断：把 fixture 喂给 `python -m adapters.dsh.hooks ...` | 【实测】exit **2**，stderr `[policy] BLOCKED (context_error)`（fixture 的 `cwd=/workspace/demo-shop` 不在仓库内 → 失败关闭） | 阻断 | **Hook 自己判定**（dsh 侧超时/崩溃 = 放行，失败关闭由 Hook 保证，见 G2） |
| D9 | 闭环：`python tools/agent_loop.py` | 【实测】exit **0**：7 个场景全 PASS（阻断不执行 / 恰好执行一次 / 能力降级 / 跨 Agent 隔离 / trace 来源 / 熔断 / 矩阵分级），证据 `.tmp/artifacts/phase-6-agents-result.json` | 端到端可复现 | 每个场景的结论来自平台判定，不由脚本自造 |

**失败状态**：未审核哈希 / 哈希漂移 → 拒绝接入；`read_only` 上限的 Agent 拿到受治理动作 → `capability_unavailable`（F35）；未知事件 / 未知工具 / 缺路径 → 拒绝。
**证据落点**：`adapters/approved.json`、`support matrix` 输出、`.tmp/artifacts/phase-6-agents-result.json`、Hook 审计 JSONL。
**人工介入点**：D2（审核人签名）；升级 Agent 版本必须先更新工具表 + 补契约测试（AGENTS 约束 28）。
**绝对不能由界面 / 脚本判定**：能力上限、是否已审核、事件是否被阻断。界面只能显示服务端 / Hook 返回的结构化结论。

---

## E. 高风险写入（审批 → action_hash → pre-check → 执行一次 → post-check → 审计台账）

**触发者**：Agent 或编排层发起；人工门禁签发审批。
**前置状态**：注册表已审核；审计与台账可写。

| 步 | 动作（命令） | 标记 | 结果 | 谁负责判定 |
| --- | --- | --- | --- | --- |
| E1 | 只判不执行：`python -m enforcement.cli precheck --request <请求> --audit … --ledger …` | 【实测】exit 0：13 项检查 `registry / action_window / principal / permissions / command_* / approval / policy / rate_limit / circuit_breaker / ledger / audit` | dry-run 结论 | **`enforcement.precheck`**；顺序固定、首个 FAILED 即 block |
| E2 | 高风险缺审批：`execute --request <shell 请求>`（不带 `--approval`） | 【实测】exit **1**：`[failed] approval approval_required` → `final: blocked (approval_required)` | 不执行 | 审批校验由 `approvals` 判定（缺失/哈希不符/跨主体/过期四类拒绝） |
| E3 | 人工签发：`python -m enforcement.cli approve --request <shell 请求> --out .tmp/r1-flows/approval.json --granted-by alice --roles reviewer --ttl 300` | 【实测】exit 0，写出 `action_hash: sha256:046a4723…`、`expires_at` = granted_at+300s | 审批记录 | **人工门禁签发**；`action_hash` 由平台算，界面不得自算 |
| E4 | 受控执行一次（可逆写）：`execute --request <edit 请求>` | 【实测】exit 0：`ledger_claim claim-1ddcd1…` → `execution: executed` → `post-check: validated`（`content_matches` / `file_changed` / `file_syntax` / `diff_recorded sha256:58e637fd…`）→ `final: delivered` | 恰好执行一次 | `executor` + `postcheck`；证据不足 → `repair_required` |
| E5 | 幂等重放：同一 `action_id` 再执行 | 【实测】exit **1**：`[failed] ledger action_replay` → `execution: refused` → `final: blocked`，文件未被第二次改动 | 台账 + 审计两处拦 | **`ledger` / `audit` 判定**；界面"我确认过了"不构成幂等依据 |
| E6 | 高风险带审批执行：`execute --approval .tmp/r1-flows/approval.json` | 【实测】exit **1**：`approval allow` → `execution: failed (process_error)` → `post-check: repair_required` | 失败被如实记录 | 本机没有 `pwsh`（`self-check` 已 warning）；**缺 shell 不静默通过** |
| E7 | 重放审计链：`python -m enforcement.cli trace --action-id r1flows:call-edit-1 --audit …` | 【实测】exit 0：事件序 `pre_decision → execution → post_evidence → final_decision` | trace 可重放 | trace 判定由 `enforcement.trace` |
| E8 | 链完整性：`python -m enforcement.cli verify --audit … --check-registry` | 【实测】exit 0：`链记录=15 外来行=0 / 审计链校验通过` | 未被改动 | 由 `audit` 判定；**删尾与整链重写发现不了**（F25） |
| E9 | 闭环：`python tools/enforcement_loop.py` | 【实测】exit **0**：5 场景 PASS（允许一次 / 重放阻断 / 回滚 / 高风险阻断 / trace 可重放） | 端到端 | 证据 `.tmp/artifacts/phase-4-enforcement-result.json` |

**⚠️ 本轮发现（最值得注意的一条）**：E1/E4 的 `policy` 检查项在**请求没有 `policy_context`** 时是 `[skipped] allow`
——实测原文：`[skipped] policy allow 请求没有声明 policy_context：该动作没有文件维度，Phase 1 规则引擎不适用（显式跳过）`。
即：**受控执行链自身不会替你跑规则引擎**，"判定"必须由调用方（dsh Runtime / 编排层）先拿到 allow 再进门；
pre-check 里的 `policy` 只是把**已经带进来的**上下文复验一次。跳过有原因、也不是放行，但——**谁忘了带上下文，谁就少了一道门**。
这与 B1（新建规则文件走 `orc.fs.write`、`approval: none`，绕过人工审批）是同一类风险的两种形态，建议 Lead 一并裁决。

**失败状态与退出码**：`0` 允许或验证通过；`1` 阻断 / `repair_required` / `inconsistent` / `rolled_back`；`2` 配置或执行错误（注册表不合规或未审核、请求非法、审计链损坏）。
**证据落点**：审计 JSONL（`sequence` + `prev_digest`）、台账 JSONL、`approval.json`、post-check 的文件前后哈希与 diff 摘要。
**人工介入点**：E3（高风险审批）；E6 的 `repair_required` 与 `side_effect_unknown`（F36）。
**绝对不能由界面 / 脚本判定**：授权是否成立、是否重放、审计链是否完整、post-check 是否通过。界面只能显示 diff / `action_hash` / post_checks 与回滚能力声明。

---

## F. 编排运行与恢复（run → checkpoint → 规则集 / 索引变化 → 恢复时重评；审批失效；side_effect_unknown）

**触发者**：人（`orchestration.cli run`）或上层系统。
**前置状态**：Policy API 可用（编排**不**回落到本地判定）；注册表已审核；checkpoint 目录可写。

| 步 | 动作（命令 / 代码） | 标记 | 结果 | 谁负责判定 |
| --- | --- | --- | --- | --- |
| F1 | 装配自检 / 图定义：`python -m orchestration.cli self-check`、`... graph` | 【实测】两命令 exit 0；8 节点 / 6 边 / 2 条件分支；`auto → langgraph` | 图与引擎可用 | 自检只回答装配；分支只由结构化 Decision 决定（F36） |
| F2 | 跑任务：`python -m orchestration.cli run --task <task.json> --engine auto --api-url … --token … --checkpoints … --audit …` | 【读码】`src/orchestration/cli.py:87-113`；写类动作回到平台 `evaluate` 再进 Phase 4 链 | RunReport | **平台判定**；引擎与节点不许发明状态 |
| F3 | 落盘进度：单文件 + 原子替换（`os.replace`） | 【读码】`src/orchestration/checkpoint.py:137-156`；先执行、再路由、再把"下一步"落盘 | 崩溃不重跑已完成节点 | checkpoint 由编排自己判定；状态里没有墙钟字段 |
| F4 | 恢复决策：`plan_resume` | 【读码】`checkpoint.py:205-270`：`FRESH / RESUME / REVALIDATE / REAPPROVE / REFUSE`；维度 `_REVALIDATE=(rule_set_hash, index_version)`、`_REAPPROVE=(tool_schema_hash,)`、`_REFUSE=(policy_version, decision_schema_version)`（`:54-56`） | 不沿用旧 allow | **`plan_resume` 判定**；拿不到凭据按"变了"处理 |
| F5 | 规则集 / 索引变化 → 重评 | 【读码】`checkpoint.py:237-254`：清 `traces`/`validation`/`test_validation`/`contexts`，`stage` 回退到 `policy_retrieval` | 回到检索节点重新要 Decision | 由编排判定；**不沿用旧 allow** |
| F6 | 工具 schema 变化 → 审批作废 | 【读码】`checkpoint.py:255-267`：清 `approvals`，模式 `REAPPROVE` | 需重新审批 | 审批绑平台口径 `action_hash`（含 trace）（F38 对应 AGENTS 38） |
| F7 | 协议世代变化 → 拒绝恢复 | 【读码】`checkpoint.py:225-231` 抛 `ResumeError` | 直接拒绝 | 编排判定；`STATE_VERSION_UNKNOWN`/`CHECKPOINT_*` → `failed` |
| F8 | 副作用未知：恢复时发现"开工未结算" | 【读码】`src/orchestration/nodes.py:294` → `FailureCode.SIDE_EFFECT_UNKNOWN` → `NEEDS_HUMAN`（`errors.py:146`） | 不重放、不假装成功 | 编排判定；交给人 |
| F9 | 读进度：`python -m orchestration.cli status --task-id <id>` | 【读码】`cli.py:269-282`：无 checkpoint → stderr + `EXIT_UNHEALTHY(1)` | 阶段 / revision / 判定 / 失败码 | 无判定，只读取 |
| F10 | 闭环：`python tools/orchestration_loop.py` | 【实测】**exit 1**（20:46）：8 场景中 3 个失败——`编排可替换`（两引擎报告在 `artifacts` 上不同）、`checkpoint 与恢复`（`resume_mode=resume`，决策路径一致=False）、`人工审批`（第二次 `blocked` 且 `second_failure.code=policy_unavailable`：`evaluate 响应缺少 decision 对象`）；其余 5 个（端到端受控 / 循环上限 / 规则集变化不沿用旧 allow / 平台故障失败关闭 / 幂等不重放）PASS | 真端口 + 真受控执行 + 真 checkpoint 与恢复 | 根因见 §9.1：规则集增长越过幂等响应上限，重放只回 `{}` |

**实测补充（索引凭据的语义，值得写进设计）**：`index_version` **不是内容哈希**——它由 schema 版本 + generation 计数 + 摄取输入指纹组成（`src/retrieval/store.py:12-13`）。
实测：同一份语料连建两次，`corpus_input_hash` 不变（`sha256:e5eae504…`），`generation` 1 → 2，`index_version` 从 `sha256:9752ab54…` 变成 `sha256:834e714d…`。
含义：**重建一次索引就会让所有 checkpoint 的 `index_version` 凭据失效并触发 REVALIDATE**。方向是安全的（重评，不沿用旧 allow），但它把"内容没变"也当成"变了"——恢复代价与误报都需要 Lead 裁决。
**失败状态与退出码**：`blocked`（平台不可用 / trace 断裂 / 证据缺失）、`needs_human`（上限 / 审批不合法 / 副作用未知）、`failed`（编排自身损坏、未登记失败码）；CLI 侧 `self-check` 不健康 → 1。
**证据落点**：checkpoint 单文件（带 `state_digest` 与兼容性凭据）、`RunReport.engine`、`.tmp/artifacts/phase-8-orchestration-result.json`、受控执行的审计与台账。
**人工介入点**：审批节点（"图到达审批节点"≠用户批准）、`side_effect_unknown`、上限击穿。
**绝对不能由界面 / 脚本判定**：PASS/FAIL、是否可恢复、审批是否有效、副作用是否已发生。

---

## G. 故障与降级处置（显式状态与退出码）

| # | 故障 | 今天的行为（实测 / 读码） | 显式状态 | 退出码 / HTTP |
| --- | --- | --- | --- | --- |
| G1 | 规则集不可用 / 读不出来 | 【读码】`src/policy_api/services.py:84,91` 抛 `RULE_SET_UNAVAILABLE`；readiness `degraded`（`ops.py:149-151`）；`serve` 拒绝启动（`serve.py:53-55`） | `rule_set_unavailable` | **503**；CLI exit 2 |
| G2 | 索引 / 检索不可用 | 【实测】`policy_api.cli smoke --token local-dev-token` → `retrieve: 503`（该租户未配检索）；【读码】`runtime.py:596/633/690-693` | `knowledge_unavailable` | **503**；CLI `query` exit 1（`empty (no_results)` 与"不可用"分开报） |
| G3 | 验证器缺失 / 版本不符 | 【实测】`validators.cli probe` exit 0，但报 `tool.mypy: unavailable`、`缺失或不匹配的关键工具：1（用到它们的规则会失败关闭）` | 判定侧 `critical` 违规 | 本机判定 exit 1；API **503** `validator_unavailable` |
| G4 | 审计 / 观测日志不可写 | 【读码】`src/policy_api/observability.py:167-192` 抛 `AUDIT_UNAVAILABLE`；受治理动作不执行（AGENTS 约束 16） | `audit_unavailable` | **503**；enforcement exit 2 |
| G5 | 超时 / 服务不可达 | 【读码】`policy_api.errors` 的 `*_timeout` → 504（`errors.py:93-95`）；编排侧 `POLICY_UNAVAILABLE` → `blocked`（`errors.py:136`） | `evaluate_timeout` / `retrieve_timeout` / `validate_timeout` | **504 / 503**；**绝不等于 allow**（F32） |
| G6 | 外部工具缺失（命令类） | 【实测】`exec.pwsh` 本机无 `pwsh` → `execution: failed (process_error)` → `post-check: repair_required` | `process_error` / `repair_required` | **1**（不静默通过） |
| G7 | Hook 侧超时 / 崩溃（dsh 语义） | 【读码】`src/adapters/dsh/README.md:51-54,64-65,84-88,117-126`：dsh 把无退出码当**非阻断**；因此 Hook 自己保证失败关闭（内部预算 < 超时、异常全转 exit 2） | Hook `exit 2` | 【实测】喂 block fixture → exit **2** |
| G8 | 幂等冲突 / 重放 | 【实测】enforcement 重放 → `action_replay` block；【读码】API 幂等键重放返回原响应、换请求体 → 409 | `action_replay` / `idempotency_key_conflict` | **1** / **409** |
| G9 | 编排自身损坏 | 【读码】未知节点 / 未知路由标签 / 未登记失败码 → `failed`（`errors.py:128-135,161-163`） | `state_invalid` / `node_unknown` / … | 编排终态 `failed` |

**归纳**：失败一律取**更严**结论；`skipped` / warning / 环境跳过都必须写明原因（`tools/dsh_sandbox_loop.py` 环境跳过 = exit 0 + reason，**但绝不记成 pass**）。
**人工介入点**：G3（装不装外部工具）、G4（修审计落点）、G6（装 shell）、G8 的副作用未知。
**绝对不能由界面 / 脚本判定**：任何"降级 / 跳过 / 超时"都不得由界面翻译成"通过"；界面只显示服务端给的错误码与 `retryable`。

---

## H. 运维锚定与证据（观测日志、seal/verify、phase_evidence、cleanup）

| # | 动作 | 标记 | 结果 | 谁负责判定 |
| --- | --- | --- | --- | --- |
| H1 | 请求级观测：`api/policy-api.yaml` 的 `audit.path` + 租户 `audit_log` | 【读码】19 个字段的摘要行（request_id / tenant / decision / rule_set_hash / index_version / elapsed_ms / error / replayed…），写入前脱敏 | 可审计 | 观测层只记录，不判定 |
| H2 | 对外锚定：`python -m policy_api.cli seal --out .tmp/r1-flows/api-anchor.json` | 【实测】exit 0：`已写出锚：api-anchor.json（515 条记录）` | 链末值发布到日志之外 | `seal` 判定链末值 |
| H3 | 校验锚：`python -m policy_api.cli seal --verify .tmp/r1-flows/api-anchor.json` | 【实测】exit 0：`与锚一致（515 条记录，链末值 sha256:86325224…）` | 删尾 / 改写会被发现 | **锚 ≠ 防篡改日志**；锚必须与日志分离存放（`cli.py:207-213`） |
| H4 | 阶段证据：`python tools/phase_evidence.py` | 【实测】**exit 1 / `result: fail` / `failures: 9`**（20:46:02Z，`implementation_version` 尾缀 `-dirty`）：contract 184 例 / 1 失败、integration 345 例 / 7 失败、security 84 例 / 1 失败、unit 0 失败；`rule_set_hash=sha256:dc4e96ac…` | 规则集哈希 / 版本 / 测试结果 | 证据脚本只汇总；**红就是红**，不许调和 |
| H5 | 本机门禁：`python tools/ci_local.py`（`--list` 可预览） | 【实测】`--list` exit 0：本次 27 步（含测试 / 各闭环 / 契约 / 阶段证据），另 1 步在 Windows 跳过（bash-only） | 按改动范围选步 | `ci_local` 只有 0/1，不是退出码口径的所有者（术语与口径 §4） |
| H6 | 清理：`python tools/cleanup.py --dry-run` → `python tools/cleanup.py` | 【实测】dry-run exit 0，命中的是 `.tmp` / `__pycache__` / `.pytest_cache` / `.ruff_cache` 等白名单路径 | 临时产物用完即删 | 脚本只删白名单（F19） |

**证据落点总表**：`.tmp/artifacts/`（阶段证据、各闭环 JSON、锚）、`.tmp/retrieval/index.sqlite3`、`registry/tool-registry.approved.json`、`adapters/approved.json`、`api/openapi.json`、审计与台账 JSONL、checkpoint 单文件。

---

## 9. 流程中今天走不通的地方（引用 N1–N6 与 B1/B2）

| # | 卡点 | 卡在哪一环 | 替代命令 / 止损做法 |
| --- | --- | --- | --- |
| 1 | **B1 审批绕过**：新建规则文件（整文件 `content`）走 `orc.fs.write`（`approval: none`），`policies/` 前缀还被显式放行 | E（高风险写入）与 C 台阶 7b：写 `policies/` 的两条路径一条要审批、一条不要 | 【实测】E1 复现了 pre-check 的 13 项检查；`orc.policy.edit` 缺审批 = `approval_required`（block）。**今天没有替代命令**：只能靠"改规则必须走 `orc.policy.edit`"的约定 + 人工核对工具选择分支（`src/orchestration/nodes.py:93-97`）；【提案】把"目标在 `policies/**`"提升为工具选择的硬约束并补契约测试 |
| 2 | **B2 界面会抄一份枚举** | C 台阶 4/5、D 的能力矩阵：checker / scope / severity / 能力上限今天**没有只读接口** | 【实测】这些常数只能从 `validators.cli registry`、`adapters.cli matrix`、`policy.check --json` 的载荷里人工抄 → 界面自抄即第二份逻辑。替代：界面只渲染后端响应字段；【提案】G3/G5 的只读接口 |
| 3 | **N1 没有前端工程** | A、B、C 的"界面"今天不存在（无 `package.json`） | 用 CLI（本文 A–H 的命令）；原型是零构建静态页 + 生成器（F26–F30） |
| 4 | **N2 没有草稿规则存储** | C 台阶 4→5 之间：候选规则无载体、无版本、无状态机 | 今天只能在 `.tmp/` 里写临时规则目录做预演（【实测】我用 `.tmp/r1-flows/broken-rules/` 造坏规则拿到 exit 2）；**不得**把草稿写进 `policies/` |
| 5 | **N3 没有写路由、没有 CORS** | E、C 台阶 7b：界面点不动"生效" | 写入走 `python -m enforcement.cli execute` / 编排层；前端与 API 只能同源（F7 六条路由里没有 enforce，F8） |
| 6 | **N4 没有审批中心** | E3：审批是**文件**，没有"待审批列表" | `python -m enforcement.cli approve --out <文件>`，再把文件交给 pre-check 复验；【提案】查询接口 |
| 7 | **N5 没有多用户会话 / 前端身份** | A、E、H 的"谁在操作"：真实身份只有 3 个客户端 | 【实测】`python -m policy_api.cli clients`：`local-dev`(developer)、`dsh-agent`(developer)、`ops-monitor`(ops)，令牌只以 sha256 出现 |
| 8 | **N6 没有第二个真实 Agent / 没有真实 ChangeAuthor** | D、F 的"真实产品验证" | 【实测】`adapters.cli matrix` 只有 `dsh` 是 FULL，另两个是合成协议消费者；Phase 8 的候选改动来自可替换端口 |
| 9 | **溯源只覆盖部分规则**（不是 N，但同属"今天走不通"） | C 台阶 7：`rule_sources` 20:49 实测 **39 条** | `--rule DOC-001`/`STYLE-003` exit 0；`--rule ARCH-001`/`STYLE-013` exit 1「没有登记的来源溯源」；界面必须显示"未登记"，**不得**显示"无来源" |
| 10 | **索引重建即改凭据** | F：任何一次 `index` 都会让 checkpoint 的 `index_version` 失效 | 【实测】generation 1→2 即换 `index_version`；止损：恢复前先 `orchestration.cli status` 看凭据，接受重评 |

### 9.1 本轮实测到的"红线"：规则集在会议期间增长把两道门禁打红（与 B1/B2 同源）

三条同源证据（实测 20:33–20:46）：

1. **规则集被并发写大**：\`policies/\` 从 **26** 个文件（20:33，\`sha256:a6c9655a…\`）增到 **44** 个（20:43:24，\`sha256:a90e64ac…\`），
   新增文件全部**未跟踪**（\`git status --porcelain policies\`）。
2. **契约测试被"规则条数"打红**（隔离复跑仍失败）：
   \`python -m pytest tests/integration/test_cli.py::test_json_output_matches_policy_decision_contract -q\` →
   \`assert result["matched_rules"] == [...]\`，\`At index 2 diff: 'DOC-002@1' != 'STYLE-001@1'\`，\`Left contains 38 more items\`。
   即这条测试**硬编码了 6 条规则的期望**；规则集一变即红。\`phase_evidence\` 的 9 个失败里它是唯一在隔离下稳定复现的
   （另一条 \`test_ruff_codes_are_declared_and_selected_in_both_directions\` 隔离复跑 **1 passed**，属并发写入期的瞬时红）。
3. **幂等响应上限被越过后，重放退化成空体**：\`src/policy_api/idempotency.py:33\` \`_MAX_RESPONSE_BYTES = 8192\`。
   进程内实测（44 条规则、\`local-dev\` 租户，\`.tmp/r1-flows/probe_eval_size.py\`）：
   | 调用 | HTTP | 响应体 |
   | --- | --- | --- |
   | \`evaluate\`（不带 \`include_evidence\`） | 200 | **10762 字节**（已越界） |
   | \`evaluate\`（\`include_evidence=True\`） | 200 | **20245 字节** |
   | 同一 \`idempotency_key\` 重放 | 200 + \`Idempotency-Replayed: true\` | **2 字节 \`{}\`** |

> **与 F10 的失败码逐字对上**：消费者拿到 \`{}\` 就没有 \`decision\` 对象，编排层判成
> \`policy_unavailable\`（"evaluate 响应缺少 decision 对象"）→ \`blocked\`。
> 方向仍是失败关闭（没有 false allow），但**今天真实工作区上门禁与闭环是红的**。
> 【未确证】另两个失败场景（\`编排可替换\` 的 artifacts 差异、\`checkpoint 与恢复\` 的决策路径不一致）
> 与字节上限的因果关系我没有单独构造实验；它们与"人工审批"共享同一个 evaluate 客户端路径，属同一嫌疑范围，
> 需修掉上限后复跑才能定性。
> **设计含义**：判定响应的体积是**规则集规模的函数**；任何"带幂等键的判定调用"都可能静默退化成空体。
> 终稿必须写成：判定调用要么不带幂等键，要么客户端必须识别 \`Idempotency-Replayed: true\` 并按"未取到判定"处理
> （**绝不是 allow**）。

## 10. 开放问题（交给 Lead 与本轮其他成员）

1. **`policy_context` 缺省时的 `[skipped] policy`（E 节实测）是否可接受？** 受控执行链把"没有上下文"记为显式跳过；
   若调用方忘记带上下文，写入链上就没有规则判定。是"必须要求调用方带 `policy_context`，否则失败关闭"，还是维持现状？
2. **B1 的修法选哪一条**：工具选择硬约束（`policies/**` 只允许 `orc.policy.edit`），还是给 `orc.fs.write`/`orc.fs.edit` 的
   `file_path` 加 pattern 排除？两条都会改注册表 → 必须重新审核（F15）。
3. **`index_version` 是否应该只跟随内容**？现状含 generation 计数（实测），把"重建"当"变化"，安全但代价高、误报多。
4. **规则集身份在并发写入下如何冻结**？本轮 `policies/` 由 26 → 44 条（未跟踪文件）已经真实发生；
   如果操作平台的"提交"与应用并发，谁的规则集哈希算数？（与台阶 7 的生效语义直接相关）
5. **界面读 `hash_drift` 的口径**：API `retrieve` 响应里的 `index.hash_drift` 是硬编码 `[]`（评审 A3-2、G1），
   在 G1 落地前，界面必须写"未核对"；这条要不要写成验收断言？
6. **权威失败码表放在哪**？今天有三套：`policy_api.errors`（33 码）、`orchestration.models.FailureCode`（31 码）、
   CLI 退出码 0/1/2。界面要显示哪一种？混用会把 `needs_human` 显示成"未识别错误"。

---

## 附：本轮实测命令清单（可复现）

```powershell
$env:PYTHONPATH = "src"
python -m policy.check --check-rules                                   # 0（20:43:24 为 44 条 / sha256:a90e64ac…）
python -m policy.check examples/bad_controller.py --layer controller    # 1（decision=block，ARCH-001@1）
python -m policy.check examples/good_controller.py --layer service      # 0（ARCH-001 进 skipped）
python -m policy.check --check-rules --rules .tmp/r1-flows/broken-rules # 2（未知 severity → 逐字段报错）
python -m retrieval.cli verify                                          # 0（6 数据集 / 27 条目）
python -m retrieval.cli index --db .tmp/r1-flows/index.sqlite3 --json   # 0（27 文档 / 535 chunk / generation 1→2）
python -m retrieval.cli index --db .tmp/r1-flows/index.sqlite3 --check  # 0
python -m retrieval.cli query "代码评审需要检查哪些方面" --limit 3       # 0
python -m retrieval.cli query "zzqqxx-不存在词项-zzqqxx"                 # 1（empty / no_results）
python -m retrieval.cli rules --rule ARCH-001                           # 1（没有登记的来源溯源）
python -m retrieval.cli context "代码评审需要检查哪些方面" --decision .tmp/r1-flows/decision.json   # 0
python -m validators.cli registry                                       # 0
python -m validators.cli probe                                          # 0（mypy unavailable → 用到它的规则失败关闭）
python -m enforcement.cli registry --verify                             # 0（9 工具 / approved=9）
python -m enforcement.cli precheck   --request .tmp/r1-flows/edit-request.json --audit … --ledger …   # 0
python -m enforcement.cli execute    --request .tmp/r1-flows/edit-request.json --audit … --ledger …   # 0（delivered）
python -m enforcement.cli execute    --request .tmp/r1-flows/edit-request.json --audit … --ledger …   # 1（action_replay）
python -m enforcement.cli approve    --request .tmp/r1-flows/shell-request.json --out .tmp/r1-flows/approval.json --granted-by alice --roles reviewer --ttl 300   # 0
python -m enforcement.cli execute    --request .tmp/r1-flows/shell-request.json --audit … --ledger …  # 1（approval_required）
python -m enforcement.cli trace      --action-id r1flows:call-edit-1 --audit …                        # 0
python -m enforcement.cli verify     --audit … --check-registry                                       # 0（15 链记录 / 0 外来行）
python -m enforcement.cli self-check --audit … --ledger …               # 0（warning: 缺 pwsh）
python -m adapters.dsh.hooks --config examples/dsh/dsh-adapter.yaml --hooks-config examples/dsh/hooks.json --self-check   # 0
Get-Content tests/fixtures/agent_events/dsh/pre-tool-use-edit-block.json -Raw | python -m adapters.dsh.hooks --config examples/dsh/dsh-adapter.yaml --hooks-config examples/dsh/hooks.json   # 2（BLOCKED context_error）
python -m adapters.cli matrix                                           # 0
python -m adapters.cli check                                            # 0（87 项检查）
python -m adapters.cli events                                           # 0
python -m adapters.cli inspect --agent dsh --event tests/fixtures/agent_events/dsh/pre-tool-use-edit-block.json --json   # 0（outcome_code=context_error）
python -m policy_api.cli self-check                                     # 0（readiness ready / 2 租户）
python -m policy_api.cli openapi --check                                # 0
python -m policy_api.cli smoke --token local-dev-token                  # 0（live/ready/evaluate allow/retrieve 503）
python -m policy_api.cli clients                                        # 0（3 客户端 / token 只显示前 12 位）
python -m policy_api.cli seal --out .tmp/r1-flows/api-anchor.json       # 0（515 条记录）
python -m policy_api.cli seal --verify .tmp/r1-flows/api-anchor.json    # 0（链末值 sha256:86325224…）
python -m orchestration.cli self-check                                  # 0（langgraph 1.2.11 / auto → langgraph）
python -m orchestration.cli graph                                       # 0（8 节点 / 6 边 / 2 分支）
python tools/enforcement_loop.py                                        # 0（5 场景 PASS）
python tools/agent_loop.py                                              # 0（7 场景 PASS / 87 项一致性检查）
python tools/cleanup.py --dry-run                                       # 0
python tools/ci_local.py --list                                         # 0（27 步 + 1 步 Windows 跳过）
```

**本轮已回读（原"待补"两项，20:46 结果）**：
- `python tools/orchestration_loop.py` → **exit 1**：8 个场景 3 个失败（见 F10 与 §9.1）；
- `python tools/phase_evidence.py` → **exit 1**：`result: fail`、9 个失败（见 H4 与 §9.1）；
- 仍属【未知，需核验】：`docs/architecture/使用说明.md` 与既有 designs 实施记录未逐行核对；
  前端不存在代码可核对（N1–N5），其结论来自 API 实测与既有 design 文档。
