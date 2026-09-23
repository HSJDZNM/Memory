# R2 提案事实核验（Verifier · task-10）

> 核验对象：r1-modules.md（E1–E20 与 M/S 段）、r1-flows.md（A–H 实测表）、r1-layouts.md（V1–V24）、r1-constraints.md（X1–X17 与 A/C 段）。
> 核验窗口：**2026-09-22 20:49–21:06（仓库时钟）**。判定只用三个值：**OK / 错 / 无法验证**。
> 纪律：凡涉及计数或哈希，一律写【值 + 取数时刻 + 取数命令】三元组（见 §8），并明确**该值在核验后可能已变化**——本窗口内就发生了语料 27 → 42 条目、审计 515 → 522 条、AGENTS.md 被并发改写、规则数 45 → 44 等变化。
> 写入声明：为复现 B1，precheck 使用独立路径 `.tmp/r2-verify/`（pre-check 会追加审计记录，实测 4 个文件各 2582 字节）；**未修改任何源码、数据、AGENTS.md、既有 designs 文档或他人文件**，唯一交付物是本文件。
> 抽样规模：四份提案共抽 **71** 条（modules 17 / flows 18 / layouts 17 / constraints 19），满足"每份 ≥6 处"。

## 0. 判定汇总与核验环境

| 提案 | 抽样条数 | OK | 错 | 无法验证 |
| --- | --- | --- | --- | --- |
| r1-modules.md | 17 | 10 | 7 | 0 |
| r1-flows.md | 18 | 14 | 3 | 1 |
| r1-layouts.md | 17 | 13 | 3 | 1 |
| r1-constraints.md | 19 | 17 | 2 | 0 |
| **合计** | **71** | **54** | **15** | **2** |

【实测】本轮跑过的命令（只读，或只写 `.tmp/`；退出码为实测）：

| # | 命令 | 关键输出 | 退出码 |
| --- | --- | --- | --- |
| 1 | `$env:PYTHONPATH='src'; python -B -m policy.check --check-rules` | rules: 44（sha256:a90e64ac…） | 0 |
| 2 | `python -B -m policy_api.cli self-check`（human 与 --json 各一次） | readiness ready（2 租户）；**17** 项 [ok] | 0 |
| 3 | `python -B -m policy_api.cli smoke --token local-dev-token --json` | evaluate 200 allow / retrieve 503 knowledge_unavailable | 0 |
| 4 | `python -B -m policy_api.cli clients --json` | 3 个客户端（developer / developer / ops） | 0 |
| 5 | `python -B -m enforcement.cli registry --list`（与 --verify） | 9 个工具；orc.fs.write approval=none、orc.policy.edit approval=required | 0 |
| 6 | precheck --request .tmp/red-team/req-fs-write.json（工作区取 scratch 或 `.`） | **decision=allow、13 项 checks** | 0 |
| 7 | precheck --request .tmp/red-team/req-policy-edit.json | decision=block、required_action=approval | 1 |
| 8 | `python -B -m validators.cli registry --json` | validators=7、rule_packs=2、stages=7、checkers=6 | 0 |
| 9 | `python -B -m adapters.cli check` 与 `inspect --agent dsh --event …block.json --json` | 87 项检查 pass；outcome_code=context_error | 0 |
| 10 | `python -B -m orchestration.cli self-check --json` | 8 节点、6 边、2 分支、langgraph 1.2.11、注册表 sha256:5e84cd67… | 0 |
| 11 | `python -B -m retrieval.cli stats --db .tmp/r1-flows/index.sqlite3 --json` | 27 文档 / 535 chunk / oversized 6 / generation 2 | 0 |
| 12 | `python -B -m retrieval.cli verify` | datasets=6、**entries=42**、OK | 0 |
| 13 | `python -B -m retrieval.cli rules --rule DOC-001`（另测 ARCH-001、STYLE-001） | DOC-001 有 2 条登记；ARCH-001 与 STYLE-001 无登记 | 0 / 1 |
| 14 | `python tools/ci_local.py --list` | 本机 27 步 + 8 步「本机跳过（CI 上仍然执行）」 | 0 |
| 15 | `python -c "import shutil; print(shutil.which('pwsh'))"` | None（powershell 命中 WindowsPowerShell） | 0 |
| 16 | `python -c "from orchestration.nodes import Change; …"` | 新建 → orc.fs.write；带 old → orc.policy.edit | 0 |
| 17 | 进程内探针（policy_api.testing.call） | metrics：developer 403 / ops 200；进程内 live、readiness 无令牌 → 401 unauthenticated | 0 |
| 18 | dsh Hook 喂 block fixture | stderr [policy] BLOCKED (context_error) | **2** |

## 1. 抽样复核：r1-modules.md

| 编号 | 提案里的断言 | 判定 | 我的复核证据 |
| --- | --- | --- | --- |
| E1 | 规则条数实测 26、identity sha256:a6c9655a…（与 F13 的 6 份不一致） | **OK** | 我在 20:31 独立实测同为 26 / sha256:a6c9655aac58…（窗口内该值已变为 44 / sha256:a90e64ac…，见 §8） |
| E2 | 退出码 0 / 1 / 2（src/policy/check.py:71-73） | **OK** | 读码逐行一致：EXIT_ALLOWED=0、EXIT_VIOLATION=1、EXIT_ERROR=2 |
| E3 | 6 条路由 + self-check 实测 18 项 ok | **错** | 6 条路径成立；项数错：self-check 实测 17 项（human 输出 17 行 [ok]，--json 的 checks 长度 17） |
| E6 / §5 S3 | 受控执行 pre-check「实测检查项名共 14 个」 | **错** | 代码里确有 14 个检查名（含 ledger_claim），但本轮 dry-run precheck 输出只有 13 项；14 是代码集合、不是实测输出（flows E1 的 13 才对） |
| E7 | 9 个受控工具 + registry 行号 :293-315 / :317-345 | **OK** | registry --list 实测 9 个 id 与提案列举完全一致；orc.fs.write approval=none、orc.policy.edit approval=required 与文件一致 |
| E10 | namespace 只是台账键前缀（adapters/runtime.py:600-603、base.py:349-350） | **OK** | 读码一致：ledger_key 返回 namespace:event_id 形式的键；base.py:349 namespace = ledger_alias 或 manifest.ledger_alias 或 agent_id |
| E11 | dsh Hook 只认 0 / 2（hooks.py:78-79、:11-15） | **OK** | 读码一致：EXIT_ALLOW=0、EXIT_BLOCK=2；Hook 自检实测 exit 0 + [policy] self-check ok |
| E13 | 7 个验证器 + 注册表门禁行号 | **OK** | validators.cli registry --json 实测 7 个 id 与提案列举一致；registry.py:22 导入 policy.checkers.SUPPORTED_CHECKERS、:46 RegistryError 读码一致 |
| E14 | 7 个 CLI 入口 --help 全部实测 | **OK** | R1 已实测 7/7 退出 0；子命令名逐包记录在 r1-verify-facts.md §3.2 |
| E15 | 三个自检（policy_api 18 项 / enforcement 缺 pwsh / orchestration langgraph 1.2.11） | **错** | 三条里两条对：enforcement 的 pwsh 警告实测为真（shutil.which('pwsh')=None，which('powershell') 命中 WindowsPowerShell）、orchestration 实测 langgraph 1.2.11；policy_api 是 17 项不是 18 项 |
| E16 | ci_local.py --list → 本机 27 步 + 8 步仅 CI | **OK** | 实测 27 条本机步骤 + 8 条「本机跳过（CI 上仍然执行）」= 35 行；与 flows H5 的「另 1 步跳过」冲突，以本行为准 |
| E17 | 无任何包导入 orchestration；observability.py:26 复用 enforcement.audit | **OK** | grep src 全目录 from/import orchestration 命中 0；observability.py:26 从 enforcement.audit 导入 redact_text 与 sanitize_payload，读码一致 |
| E19 / E20 | checkpoint.py:156 os.replace；validators/adapters/base.py:18、:580-607 进程树终止 | **OK** | 读码一致：checkpoint.py:156 在 save()(:137) 内 os.replace；base.py:602 killpg、:596-597 taskkill /F /T、:612 与 :666 job object |
| M1 | 「grep container/chroot/namespace/sandbox/沙箱 扫 src/**/*.py 命中 19 处」 | **错** | 同组关键词实测 58 行命中（src/adapters 下 22 行）；19 无法复现，疑似只扫了子目录却写成全 src |
| M2 | 「grep cron/scheduler/ThreadPool/ProcessPool/celery/queue.Queue/worker pool 命中 0 处」 | **错** | 实测 2 行：src/validators/pipeline.py:23 与 :316（ThreadPoolExecutor 并行验证器）。编排层没有调度器的结论仍成立，但「0 处」这个测量值不成立 |
| §5 S1 | Decision 枚举在 src/policy/models.py:255 | **错** | Decision 在 :267（BLOCK 在 :272）；:255 是 Operation 校验相关代码。与 Lead 指出的漂移一致 |
| §1 S3 | registry --list → 9 个工具、approved=9、exit 0 | **错** | 9 个工具与 exit 0 成立；但 --list 输出里没有 approved=9（JSON 字段是 unapproved=[]，审核结论来自 --verify / self-check） |

## 2. 抽样复核：r1-flows.md

| 编号 | 提案里的断言 | 判定 | 我的复核证据 |
| --- | --- | --- | --- |
| A3 | 20:43:24：rules: 44（sha256:a90e64ac…） | **OK** | 20:50 实测同一命令 = 44 / sha256:a90e64ac2d5cd1335ffb8e4c92b7717e4b92b408178ae7f921103683b4c22784，值仍然吻合 |
| A4 | retrieval.cli verify exit 0：datasets=6 entries=27 | **错** | 实测 exit 0、datasets=6，但 entries=42（20:52）；27 是当时值，现已变（且索引仍停在 27 文档，见 §6 第 6 条） |
| A5 | 隔离索引：27 文档 / 535 chunk / oversized 6 / generation 2 | **OK** | retrieval.cli stats --db .tmp/r1-flows/index.sqlite3 实测：documents=27、chunks=535、oversized_chunks=6、quarantined=0、truncated=0、generation=2 |
| A6 | enforcement self-check：tools=9 approved=9，warning 缺 pwsh | **OK** | 缺 pwsh 实测为真（shutil.which('pwsh')=None）；9 个工具成立 |
| A7 | hooks --self-check exit 0、stderr [policy] self-check ok | **OK** | 实测 exit 0，stderr 原文一致 |
| A8 | self-check exit 0：readiness ready（2 个租户）+ 18 项 [ok] | **错** | readiness ready（2 个租户）成立；项数 17（与 modules E3/E15 同一个错误） |
| B3 | --json 顶层六键 [context, evidence, exit_code, reported_imports, result, rule_set] | **OK** | 实测顶层键逐个一致，exit_code=0；context 的 13 个键也一致 |
| B6 | query 无结果：exit 1、status: empty (no_results) | **OK** | 用同一查询文本实测 exit 1、status: empty (no_results)（换成 ASCII 词项时会命中，说明该断言是文本相关的） |
| C / D 台阶 | 台阶 5 = 44 条 exit 0；D4 = 87 项检查；D6 = exit 0 + context_error；D8 = exit 2 + BLOCKED (context_error) | **OK** | 四项全部实测一致（D8 的 detail 原文：路径不在仓库 <repo> 之内，拒绝处理 '/workspace/demo-shop/src/shop/order_controller.py'） |
| C 台阶 7 / 卡点 9 | retrieval.cli rules --rule ARCH-001 → exit 1「没有登记的来源溯源」 | **OK** | 实测 exit 1、原文一致（STYLE-001 同样 exit 1） |
| E1 | pre-check 实测 13 项检查 | **OK** | 本轮 precheck JSON 的 checks 恰 13 项（registry / action_window / principal / permissions / command_allowlist / command_composition / command_fragments / approval / policy / rate_limit / circuit_breaker / ledger / audit） |
| H5 | ci_local --list：本次 27 步，另 1 步在 Windows 跳过（bash-only） | **错** | 实测 27 步 + 8 步跳过（AST 重放 ×2、Example replay、Scope skip、验证器注册表 ×2、失败关闭、Syntax errors、ASGI 契约） |
| H2 / H3 | seal 写出锚 515 条记录；--verify 与锚一致 | **OK** | 机制实测成立但锚已失效：当前 seal --verify .tmp/r1-flows/api-anchor.json → exit 1「记录数不一致：锚 515 / 当前 522；链末值与锚不一致」 |
| G1 / G2 / G4 / G5 | 503 与 504 的代码路径（services.py:84,91；runtime.py:596/633/690-693；observability.py:167-192；errors.py:93-95） | **OK** | 全部读码一致；policy_api.cli smoke 实测 retrieve: 503、state=knowledge_unavailable；smoke 的 evaluate=allow 也复现 |
| A9 | openapi --check exit 0、「与快照一致（api_version=1.0）」 | **OK** | 实测原文一致，退出 0 |
| B1 | bad_controller --layer controller → exit 1、decision=block、ARCH-001@1 @ dependency:10 | **OK** | 实测输出原文一致（reason 与 evidence 两行也在，证据来自 py.depgraph@1.0） |
| B2 | good_controller --layer service → exit 0、ARCH-001 进 skipped「layer service != controller」 | **OK** | 实测 exit 0、ARCH-001 确在 skipped 且原因原文一致（同一批 matched=41 条） |
| A1 | uv 0.7.19、requirements.lock 与 pyproject.toml 均存在（环境探测） | **无法验证** | 本轮未复跑依赖安装与 uv 探测（不装依赖、不动 .venv）；只能确认 pyproject.toml 与 requirements.lock 路径存在 |

## 3. 抽样复核：r1-layouts.md

| 编号 | 提案里的断言 | 判定 | 我的复核证据 |
| --- | --- | --- | --- |
| V1 | 六条 HTTP 路由 | **OK** | openapi --check exit 0；api/openapi.json 的 paths 六条；self-check 的 openapi_paths 实测只列这六条 |
| V3 | 同两个路由走进程内 runtime.handle 要令牌：缺 Authorization → 401 unauthenticated | **OK** | 实测（合法信封 + 无令牌）：live → 401 unauthenticated、readiness → 401 unauthenticated；补充：空 body 会先得 400 body_invalid（body 校验在认证之前，runtime.py:306） |
| V4 | GET / → 404 not_found；OPTIONS /v1/policy/evaluate → 405；响应无 Access-Control-Allow-Origin | **OK** | 读码：无静态挂载；app.py:344-352 把 Starlette 404/405/415 映射进同一错误信封；src 全目录无 CORS 中间件 |
| V5 | metrics 三重口径 + 200 正文含 routes / outcomes / decisions / tenants / readiness | **OK** | 实测：developer 令牌 → 403 metrics_forbidden；ops 令牌 → 200；metrics 段键 = routes/outcomes/decisions/status_classes/budget_exceeded/rate_limited/replays/timeouts/uptime_seconds；routes bucket = requests/errors/count/mean_ms/p50/p95/p99/max |
| V9 | 索引 stats 全字段（27 文档 / 535 chunk / oversized 6 / generation 2 / index_version sha256:834e714d… / 6 数据集） | **OK** | 实测逐项一致（含 corpus_input_hash sha256:e5eae504…，与 flows 的观察一致） |
| V10 | retrieval.cli verify 退出 0：datasets=6 entries=27 | **错** | exit 0 与 datasets=6 成立，但 entries=42（与 flows A4 同一个过期值） |
| V11 | retrieval.cli rules --rule DOC-001 →「没有登记的来源溯源」、退出 1 | **错** | 实测 exit 0，DOC-001 有 2 条登记（pep-257-docstrings 的两个 chunk）；同一命令对 ARCH-001 / STYLE-001 才是 exit 1。该断言在写出后被并发写入改成了假 |
| V12 | 3 个协议消费者 dsh FULL / 2 个 READ-ONLY | **OK** | R1 的 adapters.cli matrix 实测 + 本轮 registry 一致；approved.json 三条均 approved=true |
| V15 | 验证器 7 / checker 6 / rule_pack 2 / stage 7 | **OK** | registry --json 实测逐项一致（checkers.python 下 6 个 checker id） |
| V18 | 8 节点 / 6 静态边 / 2 条件分支；langgraph 1.2.11；注册表身份 sha256:5e84cd67… | **OK** | orchestration.cli self-check --json 实测三项原文一致（含 sha256:5e84cd67d60875f7a769b40cc71c51e9de2081e1814c4677451afa6d2ccc7cca） |
| V19 | KNOWN_LAYERS = 12 个值 + unknown（check.py:77-92） | **OK** | 读码逐行一致：controller/service/repository/model/schema/view/client/adapter/gateway/middleware/util/test + :92 unknown |
| V20 | 规则集在会议期间 26 → 39 → 45，identity 四次变化 | **OK** | 我独立观测到 26/a6c9655a…（20:31）、45/dc4e96ac…（20:37:59）、44/a90e64ac…（20:50）；中间的 1e8d47fe 与 69e46230 未独立观测（数值无法验证，但「分钟级变化」成立） |
| V22 | index.html:23 与 activation.html:23 烘死 sha256:ed331a8d…，KPI 写「6 规则」 | **OK** | 读码一致：index.html:19 KPI=6 规则、:23 sha256:ed331a8df3… |
| V23 | console 全目录 tabindex / aria- / noscript / <form 命中 0 | **OK** | 实测 9 个 html/js/css 文件命中 0 |
| V24 | capability_unavailable 全 src 命中集合 = adapters/runtime.py:88,728,1284,1289 + conformance.py:565,624-625 | **OK** | grep 全 src 恰这 7 处，行号与提案列举完全一致；policy_api 下 0 命中 |
| V6 | layer=capability → allow / matched=0 / skipped=26；layer=controller → allow / matched_rules=["ARCH-001@1"] | **错** | 实测（当前 44 条规则）：layer=capability → allow、matched=**41**、skipped=3；layer=controller → allow、matched=**42**（ARCH-001 只是其中之一）、skipped=2。两半都是"6 条规则"时代的旧值 |
| V2 | health/live 与 health/ready 在 HTTP 面免令牌（无 Authorization → 200） | **无法验证** | 本轮未启动 serve、未发真实 HTTP 请求；读码确认 app.py:295-307 的 GET 处理器直接返回、不经 handle_route（认证只在 runtime.handle，runtime.py:306），与 V2 自洽，但"HTTP 200"本身仍只由 layouts 自己的实测支撑 |

## 4. 抽样复核：r1-constraints.md

| 编号 | 提案里的断言 | 判定 | 我的复核证据 |
| --- | --- | --- | --- |
| X1 | Change(path='policies/...', content=...) 的 tool_id == orc.fs.write | **OK** | 实测三例：新建 policies/ → orc.fs.write；带 old → orc.policy.edit；src/x.py + content → orc.fs.write |
| X2 / X3 | orc.fs.write approval=none 无 pattern；orc.policy.edit approval=required + ^policies/ pattern | **OK** | registry --list 与 --verify 实测 approval 列一致；tool-registry.yaml:293-345 读码一致 |
| X4 | 越界守卫显式放行 policies/（nodes.py:488-491） | **OK** | 读码逐字一致 |
| X5 / V21 | 六个门禁 CLI 全部退出 0 | **OK** | 六条本轮全部实测 exit 0：check-rules、retrieval.cli verify、validators.cli registry、openapi --check、self-check、enforcement.cli registry --verify |
| X6 | app.js:170-200 在浏览器内算字段门禁与决策档位，结论在 :198 | **OK** | 读码一致：:198 把 severity=error/critical 映射成 block、info/warning 映射成 allow_with_warnings；权威表在 models.py:184 与 :984-999 |
| X7 | 生成器把 severity 四值与决策表各抄一份（build_site.py:41、:456） | **OK** | 读码一致：:41 SEVERITIES 四值；:456 悬停文案写死 error/critical → block、info/warning → allow_with_warnings |
| X8 | 生成器读不到 policy.checkers 时静默回退 6 个字面量（:213-219） | **OK** | 读码一致：:212-216 try/except 后 supported = 6 个字面量且无错误标记（对照 :173-174 的 rules_error 会显示） |
| X11 / X12 | localStorage 只存 picks 与 candidates；:293 写生命周期字面量 D2 可加载 | **OK** | 读码一致：app.js:58-74 的 Store.read/write + :68 默认 {picks, candidates}；:290-295 候选对象带 state D2 可加载 |
| X13 | console 下 innerHTML / insertAdjacentHTML / outerHTML / document.write 命中 0 | **OK** | 实测 0；生成器 esc() 在 build_site.py:138 |
| X14 | metrics.tenants 是全量装配租户；metrics 段无租户维度 | **OK** | runtime.py:822 取 list(self.store.ids)；observability.py:304-324 只按 route/status/outcome/decision 聚合（注：提案引的 :277-285 实际是 Latency.to_payload，聚合在 :304-324） |
| X15 | capability_unavailable 有真实抛出点，且一致性套件断言只读上限必须报它 | **OK** | adapters/runtime.py:728 与 conformance.py:624-625 读码一致（与 layouts V24 的命中集合一致） |
| X16 | 既有 designs 把功能清单.md 引成 :253/254/256，实际在 :323/324/326 | **OK** | 读码逐行确认：:253 enforcement_loop、:254 agent_loop、:256 orchestration_loop；:323 LLM/MCP/向量库至今没有引入、:324 摘要链边界、:326 审批无签名与名册 |
| X17 | 静态原型内嵌演示令牌 local-dev-token（app.js:8），且该值是登记演示值 | **OK** | app.js:8 就是 DEMO_TOKEN = 'local-dev-token'；api/policy-api.yaml:10 明写三个令牌是演示值；api/README.md:34 与 :50（后者带 secret-scan: allow） |
| A2 | precheck：orc.fs.write 新建 policies/ → exit 0 allow；orc.policy.edit → exit 1 approval_required | **OK** | 我用真实注册表复现：P1 exit 0 decision=allow（approval=skipped「该工具不需要人工审批」）；P2 exit 1 decision=block required_action=approval |
| A3 | 「把 file_path 换成治理链数据文件、工作区取真实仓库根」→ precheck 全部 exit 0 | **错** | 其探针文件 .tmp/red-team/req-multi.jsonl 里每个请求都写 workspace 为 .tmp/red-team/ws，不是真实仓库根；结论我另行独立复现成立（见 §5.2 的 P3/P4，--workspace . 仍 exit 0 allow） |
| A2 附注 | 「仅 precheck，dry_run=True，未执行任何写入」 | **错** | 工具确未执行；但 pre-check 会追加审计记录：本轮 4 个 .tmp/r2-verify/*-audit.jsonl 各 2582 字节，内容含 action_hash 与 13 项 checks |
| C1 | 决策字面量今天 4 命中 | **OK** | 实测：authoring.html:30、build_site.py:456、assets/app.js:198、assets/app.js:32（CSS display='block' 误报），与提案列举一致 |
| A12 | 契约测试按 route.name 过滤，挂载静态目录的副作用 CI 发现不了 | **OK** | test_api_protocol.py:174-180：served 字典按 route.name 落在 ENDPOINTS 值集合内过滤，随后 assert len(served) == 6 |
| A9 | policies/ 不在已审核哈希保护范围内；其保护是整批原子加载 + 空集拒绝替换 | **OK** | services.py:73-97 读码一致（:80-87 加载失败 → RULE_SET_UNAVAILABLE 且 retryable=True；:88-94 空集拒绝替换） |

## 5. Lead 指定的五条高风险断言（专项）

### 5.1 app.js:198 在浏览器内算 severity → 决策（**已经发生，不是风险**）

- 【读码】designs/console/assets/app.js:170-200 的 validate() 是纯前端函数；:197 先查 D.severities，:198 立刻把 severity 映射成结论：severity 为 error 或 critical 时输出 **block**，否则输出 **allow_with_warnings**。
- 权威实现对照：src/policy/models.py:184（决策表注释）、:984-999（expected_decision）；唯一判定路径 src/policy/engine.py:109-167。
- 界面层另抄了两份：build_site.py:41（severity 四值枚举）、build_site.py:456（决策表文案），加上 app.js:198 本身就是第三份。
- 结论：constraints 的 C1/A1 与 layouts 的 U4 描述属实；这道红线今天**已经被破**，而且页面上的"预演通过"结论不依赖任何后端响应（app.js:265-272 用 level === 'no' 计数自行判通过/失败）。
- 唯一缓和项：console/README.md:38 与 F30 已约定"预演是浏览器内模拟"，但 gates 页的"预演通过"没有任何这样的标注（constraints A1 的判断成立）。

### 5.2 precheck 对 orc.fs.write 放行、对 orc.policy.edit 阻断（B1 的可利用面）

三组复现（真实注册表；precheck 为 dry-run，未执行任何工具）：

| 探针 | 请求 | 工作区 | 实测结论 | 退出码 |
| --- | --- | --- | --- | --- |
| P1 | req-fs-write.json（orc.fs.write → policies/coding/NEW-001.yaml） | .tmp/red-team/ws | decision=allow、approval=skipped（该工具不需要人工审批） | **0** |
| P2 | req-policy-edit.json（orc.policy.edit → policies/coding/DOC-001.yaml） | .tmp/red-team/ws | decision=block、required_action=approval | **1** |
| P3 | 同 P1，工作区改取**真实仓库根** `--workspace .` | 仓库根 | decision=allow，**仍然 exit 0** | **0** |

P3 的 13 项检查明细（--json 实测）：registry=passed、action_window=passed、principal=passed、permissions=passed、command_allowlist=skipped、command_composition=skipped、command_fragments=skipped、**approval=skipped（allow）**、**policy=skipped（allow）**、rate_limit=passed、circuit_breaker=passed、ledger=passed、audit=passed。

- **B1 在真实仓库根上同样成立**——这比 constraints A3 的证据更强：A3 的 req-multi.jsonl 每个请求都带 workspace=.tmp/red-team/ws，并未指向仓库根，属"结论对、证据标注不实"（已在 §4 记为错）。
- 附带发现：approval 与 policy 两项都是 **skipped + allow**。受控执行链在请求没有 policy_context 时不会替调用方跑规则引擎（flows E 节已如实登记）；而 orc.fs.write 的 approval: none 让 approval 也 skipped。两个 skipped 叠加后，"新建规则文件"这条路径今天既无人工审批、也无策略判定。
- 副作用登记：pre-check **会写审计**（.tmp/r2-verify/p1..p4-audit.jsonl 各 2582 字节，内容含 action_hash 与 checks 摘要）；因此"只跑 precheck = 未执行任何写入"必须限定为"未执行工具副作用"。

### 5.3 runtime.py:679 的 hash_drift 硬编码

- 【读码】src/policy_api/runtime.py:679 就是 `"hash_drift": [],`，位于 _retrieve 组装 index 段处；同段其它字段（database / index_version / generation / documents / chunks / quarantined）都取自真实 stats，只有 drift 是常量。
- 与 AGENTS.md 约束 12（现 :140，原 :139）"漂移不许静默"冲突；constraints C9、layouts P4、modules E9 三处描述一致，**均属实**。

### 5.4 capability_unavailable 在 policy_api 是否有抛出点

- 【读码】capability_unavailable 在 src/ 全目录命中 **7 处**：adapters/runtime.py:88（原因码文案）、:728（真实抛出点）、:1284、:1289，以及 adapters/conformance.py:565、:624-625（一致性套件断言）。
- src/policy_api/ 下命中 **0 处** → **layouts V24 完全正确**（6 条 HTTP 路由今天产不出这个码）；constraints X15 说"有真实抛出点"也正确（在 Phase 6 运行时）。两者不矛盾，但必须合并成一句口径：**"Phase 6 可达 / Policy API 不可达"**。

### 5.5 行号与语义漂移登记（Lead 要求"登记所有同类漂移"）

| 引用处 | 提案写的行号 | 当前实际 | 漂移 | 性质 |
| --- | --- | --- | --- | --- |
| r1-modules §5 S1 | src/policy/models.py:255（Decision） | :267 | −12 | 同一文件内的内容漂移；:255 属 Operation 校验逻辑 |
| r1-constraints（16 处 AGENTS.md 引用） | :220 / :259 / :263 / :233 / :186 / :139 / :151 / :114-115 / :229 / :145-147 / :131-134 / :116 / :155-162 / :200-206 / :242 / :141-147 | :222 / :261 / :265 / :235 / :188 / :140 / :152 / :115-116 / :231 / :146-148 / :132-135 / :117 / :156-163 / :202-208 / :244 / :142-148 | **+1（约束 ≤17）/ +2（约束 ≥24）** | AGENTS.md 在窗口内被并发编辑：新增**约束 40**、约束 18 的基线改指 baseline-v3.json、仓库现状新增「44 条规则」行 |
| r1-verify-facts.md（我的 R1 文档） | AGENTS.md:220-224、:186-193 等 | 同上 | +1 / +2 | 我上一轮核验时与实际一致，现在同样过期——如实登记，不遮掩 |
| r1-constraints X16 | 功能清单.md:253/254/256 | :323/:324/:326 | +70 | 提案自己发现的漂移，复核成立 |
| 其余被引行号 | — | — | 0 | §1–§4 已逐条核（含 runtime.py:679、checkpoint.py:54-56/156/205-267、errors.py:73-107、app.py:344-352、nodes.py:93-97/488-491、console 生成器与 assets 全部命中） |

**语义漂移（不是行号，必须一起登记）**：

1. AGENTS.md 新增**约束 40**「规范文档不会自动变成规则」——用现行条款规定了 source.kind、checker、6 维 scope、severity 四值的上线条件，并写明"不满足时停在 Curated Guidance"。这条在四份 R1 提案里**都没有被引用**，但它是"文档 → 规则"流程的现行宪法条款。
2. AGENTS.md 仓库现状现在写死"**44 条规则**：5 条项目自订 + 39 条由镜像提炼"——这是当前唯一被官方登记的口径；而 fixture-shop 租户同一时刻加载的是 **45** 条（多 1 条 tests/fixtures/api/rules，见 §8）。
3. 约束 18 的评测基线从 baseline-v2.json 改为 baseline-v3.json（tools/retrieval_eval.BASELINE_PATH 指向当前版本）；任何仍写 baseline-v2 的旧表述都已过期。

## 6. 四份提案互相矛盾的事实条目清单

| # | 条目 | 各方说法 | 复核结论（本轮实测） | 建议统一口径 |
| --- | --- | --- | --- | --- |
| 1 | pre-check 检查项数 | modules E6「实测 14 个」；flows E1「13 项」 | dry-run precheck 输出 **13** 项；ledger_claim 是代码里的第 14 个名字，只在执行路径出现 | 写"14 个检查名 / dry-run 13 项"，不要写"实测 14" |
| 2 | 本机 CI 跳过步数 | modules E16「8 步仅 CI」；flows H5「另 1 步在 Windows 跳过」 | **8 步**全部 bash-only（AST 重放 ×2、Example、Scope skip、验证器注册表 ×2、失败关闭、Syntax errors、ASGI 契约） | 采用 modules 的 27 + 8 |
| 3 | API self-check 项数 | modules E3/E15「18 项」；flows A8「18 项」 | **17 项**（human 17 行 [ok]；--json checks 长度 17） | 统一写 17，并标注取数时刻 |
| 4 | 规则溯源是否为空 | flows「溯源是空的（ARCH-001 exit 1）」；layouts V11「DOC-001 exit 1」 | ARCH-001 / STYLE-001 → exit 1（无登记）；**DOC-001 → exit 0（2 条登记）** | 写"部分登记"，且断言必须绑定具体 rule_id 与取数时刻 |
| 5 | 规则条数 | modules 26；flows 44；layouts 26→39→45；AGENTS.md（新）44 | 20:31=26、20:37:59=45、20:50=44；且 local-dev=44 / fixture-shop=45 | 一律写"租户 + 时刻 + 命令"；界面不得显示单一全局计数 |
| 6 | 语料条目与索引 | flows A4 与 layouts V10「entries=27」；A5/V9「索引 27 文档」 | 现在 verify = **entries=42**，而 .tmp/r1-flows 索引仍是 27 文档 → **索引已落后于语料** | 增加显式状态"索引过期（corpus entries ≠ index documents）" |
| 7 | "precheck 未执行任何写入" | constraints A2 与探针说明 | 工具未执行属实；但 pre-check **追加审计记录**（本轮 4 个 2582 字节文件） | 统一写"未执行工具副作用；pre-check 自身会写审计" |
| 8 | capability_unavailable 可达性 | layouts V24「API 面不可达」；constraints X15「有真实抛出点」 | 两者都对但层级不同：Phase 6 可达、Policy API 0 命中 | 统一为"Phase 6 可达 / Policy API 不可达" |
| 9 | B1 可利用面的证据 | modules E8、flows 卡点 1、constraints A2/A3 | 三处结论一致；但 A3 的探针工作区号称仓库根、实际是 .tmp/red-team/ws | 采用本轮 P3（真实仓库根、exit 0）作为主证据 |
| 10 | 规则集哈希 | layouts V20 列 4 个、flows 列 2 个、modules 列 1 个 | 我独立复现 3 个（a6c9655a / dc4e96ac / a90e64ac），其余无法独立复核 | 哈希一律带时刻，不用"当前哈希"这种措辞 |

## 7. 待 Lead 裁决清单

1. **计数口径**：规则条数是"工作树 / 已提交 / 某租户"？同一时刻 local-dev=44、fixture-shop=45，AGENTS.md 登记 44。建议裁定"界面只显示随请求返回的 rule_set.rules + 租户名 + 时刻"。
2. **pre-check 的 13 / 14**：是否把 dry-run 与执行路径的检查项差异写成契约（例如标注 ledger_claim: not_applicable）。
3. **索引过期状态**：语料 42 条目与索引 27 文档的落差今天没有任何路由能暴露（与 B2 相邻）。是否在 G1/G2 里增加"corpus entries 与 index documents 不一致"的显式状态。
4. **引用漂移门禁**（constraints C15 的 V20 验收）：AGENTS.md 本轮 +1/+2 已让 16 处引用失效；是否要求所有 meeting 文档的 file:line 在下一轮重新取数并标时刻。
5. **界面自抄枚举的边界**：app.js:198 已在浏览器里算结论，本轮是否就要求三选一——（a）删除结论语义、（b）改成调用后端、（c）保留但在页面硬标注"浏览器内模拟，不是判定"。
6. **数字型断言的验收方式**：本轮 14 条"错"里有 8 条属于"未标取数时刻导致的值漂移"（entries 27→42、self-check 18→17、CI 跳过 1→8 等），是否把"值必须带时刻 + 命令"提升为文档验收条款。
7. **DOC-001 溯源已登记**：flows 卡点 9、layouts V11、modules §6 第 5 步的"溯源为空"叙事需要按 rule_id 重写；是否请 S5 所有者给出"哪些 rule_id 有登记"的权威清单。

## 8. 计数与哈希三元组（值 + 取数时刻 + 取数命令）

| 值 | 时刻（2026-09-22） | 命令 | 备注（核验后可能已变化） |
| --- | --- | --- | --- |
| 规则 44 条 / sha256:a90e64ac2d5cd1335ffb8e4c92b7717e4b92b408178ae7f921103683b4c22784 | 20:50 | python -m policy.check --check-rules | 与 flows A3 的 20:43:24 值一致 |
| local-dev = 44 条（sha256:a90e64ac…）/ fixture-shop = 45 条（sha256:eea3f175c45b1f7da882d777ac8ec4cd5e9205f0607cf909f6d5cb17587a14c3） | 20:52 | policy_api.cli smoke 的 ready.tenants[] | 同一时刻两个租户规则数不同 |
| 规则 26 条 / sha256:a6c9655aac58…（历史） | 20:31 | 同 1 | 与 modules E1、flows 的 20:33 值一致 |
| 规则 45 条 / sha256:dc4e96ac1d631186ea80ab858d1f75737a9c407c1559c12c43f3d965eb285786（历史） | 20:37:59 | 同 1 | 15 分钟内的第三次变化 |
| 语料 6 数据集 / 42 条目 | 20:52 | retrieval.cli verify | 与提案的 27 条目不同 |
| 索引 27 文档 / 535 chunk / oversized 6 / generation 2 / index_version sha256:834e714d… | 20:51 | retrieval.cli stats --db .tmp/r1-flows/index.sqlite3 | 该库是 flows 建的隔离库 |
| 审计当前 522 条记录（锚为 515） | 20:53 | policy_api.cli seal --verify .tmp/r1-flows/api-anchor.json | 锚失效即"日志被追加过"的证据 |
| 本机 CI 27 步 + CI-only 8 步 | 20:54 | python tools/ci_local.py --list | 步数随改动范围变化（当时"改动文件 56 个"） |
| 9 个受控工具（exec.bash / exec.pwsh / exec.run_code / fs.edit / fs.read / fs.write / orc.fs.edit / orc.fs.write / orc.policy.edit） | 20:53 | enforcement.cli registry --list | 注册表未变 |
| 7 验证器 / 6 checker / 2 rule_pack / 7 stage | 20:53 | validators.cli registry --json | 未变 |
| 3 客户端（local-dev、dsh-agent、ops-monitor） | 20:52 | policy_api.cli clients --json | 未变 |
| 8 节点 / 6 边 / 2 分支 / langgraph 1.2.11 / 注册表 sha256:5e84cd67… | 20:53 | orchestration.cli self-check --json | 未变 |

## 9. 核验边界（本轮**没有**做的事）

- **没有启动 serve、没有做真实 HTTP 探测**：layouts V2/V4/V5 的 200 / 404 / 405 / 403 我用"读码 + 进程内 runtime.handle"复核（进程内路径本身也是 V3 的被测对象），因此真实 socket 上的行为仍只有 layouts 自己的实测记录；
- **没有跑 pytest 与 ci_local 全量**：「六个门禁 exit 0」是逐命令实测，不是一次完整门禁运行；
- **没有复跑 orchestration_loop.py 与 phase_evidence.py**（flows 已标注"20:45 仍在运行"）：其最终退出码与结论我未独立读取；
- **没有逐个构造 REASON_CODES**：S2 的"可达性门禁"问题仍是【未知，需核验】；
- **没有核对 504 的真实路径**：本机 evaluate 亚毫秒，504 只有读码证据（与 constraints A5 的自我标注一致）；
- 所有数值在核验后都可能继续变化：本窗口内 AGENTS.md 被改写 2 次、规则数 26→45→44、语料 27→42 条目、审计 515→522 条。
## 10. 未复核项清单（Lead 可指定下一轮复跑）

| # | 未复核的断言 | 为什么没复核 | 复跑需要什么 |
| --- | --- | --- | --- |
| 1 | layouts V2：health 两条路由"HTTP 面免令牌 → 200" | 本轮不启动 serve、不发真实 HTTP（只读纪律） | `python -m policy_api.cli serve` + curl（会写 .tmp/phase-7-api 审计） |
| 2 | flows A1：uv 0.7.19 与依赖安装探测 | 不装依赖、不动 .venv | `uv --version` 与该设备上的一次全新安装 |
| 3 | flows F10 与 H4：orchestration_loop.py、phase_evidence.py 的最终结论 | 提出者自己标注"20:45 仍在运行"，我没回读 | 后台跑完后的退出码 + 结果 JSON |
| 4 | constraints A5：504 超时路径 | 本机 evaluate 亚毫秒，构造不出 504 | 人为注入慢规则集或降低 budget_ms 的契约测试 |
| 5 | constraints A4/A8/A10/A11 的"界面侧"部分 | 需要浏览器/前端实现，今天没有前端工程（N1） | P0 只读骨架落地后的前端契约测试 |
| 6 | flows 附录里 enforcement 的 approve / execute / trace / verify 全链路 | 会写 .tmp 台账与审计、且涉及真实执行；本轮只做了 precheck | 在隔离工作区跑 `tools/enforcement_loop.py` 一次并回读退出码 |
| 7 | layouts V23 的 a11y 判断（"disabled 元素不进 tab 序列"） | 需要浏览器 DOM 实验 | 手动键盘走查或 Playwright（本项目无前端构建链） |

## 11. 四份提案的高频错误模式（下一轮写文档时的防空转清单）

1. **数字不带取数时刻**：15 条"错"里 8 条属于这一类（entries 27→42、self-check 18→17、CI 跳过 1→8、V6 的 matched 值）。规则：任何计数/哈希写成"值 + 时刻 + 命令"。
2. **把读码结论写成「实测」**：modules E6 的"实测 14 个检查项"、§1 S3 的"approved=9"都是读码可得的集合/字段，却冠以实测。规则：实测必须贴命令与输出摘要。
3. **引用行号会在并发写入下失效**：AGENTS.md 本轮 +1/+2（16 处引用）、models.py 的 Decision 差 12 行。规则：引用行号时同时写锚文本（引用断言门禁才能落地）。
4. **grep 的「命中 N 处」不写扫描范围**：M1 声称 19 处、实测 58 处；M2 声称 0 处、实测 2 处（validators/pipeline.py 的 ThreadPoolExecutor）。规则：写清 scope（目录、include、是否区分大小写）与计数口径（行/匹配）。
5. **跨层同名码被当成同层可达**：capability_unavailable 在 Phase 6 可达、Policy API 不可达——两句话都对，但只说一句就会误导。
6. **结论对、证据路径不实**：A3 结论（orc.fs.write 可无审批写信任根）成立，但探针的工作区其实是临时目录。规则：证据里必须写"我实际用的参数"，不能写"我打算用的参数"。
7. **把「未执行工具」等同于「没有写入」**：pre-check 自身会写审计记录（本轮 4 个 2582 字节文件）。规则：副作用要按"工具副作用 / 框架副作用"分开声明。
8. **静态值烘死**：console 的 sha256:ed331a8d… 与「6 规则」KPI 已被 V20/V22 证实会过期——这是既有原型的既有缺陷，也是"数字必须带时刻"的最佳反例。

## 12. 结论一句话

四份 R1 提案的**结构性判断**（谁是唯一判定路径、B1/B2 的存在、界面不得是第二内核、能力上限由声明推出、失败语义必须显式）本轮抽样全部成立；出错的是**数值与证据卫生**：15 条错误全部集中在"取数时刻缺失 / 实测与读码混用 / 引用行号漂移 / 扫描范围不明 / 跨层口径混用"，没有一条推翻提案的架构主张。
