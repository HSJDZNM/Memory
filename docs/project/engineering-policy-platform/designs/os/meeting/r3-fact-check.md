# R3 终稿事实核验（Verifier · task-13）

> 核验对象：01-板块拆分.md、02-操作流程.md、03-页面布局.md（三份终稿），约束口径取 04-会议纪要与裁决.md 的 D1–D15。
> 核验窗口：**2026-09-22 21:05–21:25（仓库时钟）**。判定只用三个值：**OK / 错 / 无法验证**。
> 方法：逐条核 **file:line 的行内容**、**命令是否存在与退出码/输出是否一致**、**数字是否带取数时刻且时刻与值自洽**；只跑只读命令（ASGI 用进程内 TestClient，不起端口）。
> 写入声明：唯一交付物是本文件；探针脚本与临时产物写在 `.tmp/r3-verify/`（AGENTS 约定的临时区），**未改任何源码、数据、AGENTS.md 或其它终稿**。

## 0. 判定汇总

| 区块 | 条数 | OK | 错 | 无法验证 |
| --- | --- | --- | --- | --- |
| A 路由与可达性（7 条路由、5 个 0 抛出点、空壳重放、dry_run 审计、提交判据） | 7 | 7 | 0 | 0 |
| B 命令与退出码 | 9 | 6 | 1 | 2 |
| C 数字三元组 | 11 | 9 | 0 | 2 |
| D file:line | 8 | 5 | 3 | 0 |
| E 裁决纪律（D1–D15）落实 | 8 | 6 | 2 | 0 |
| **合计** | **43** | **33** | **6** | **4** |

结论一句话：**终稿的事实骨架成立**——Lead 点名的六项高风险断言（7 条路由、5 个 0 抛出点、capability_unavailable 两句、空壳重放、dry_run 写审计、approval.status 判据）**全部核验通过**；6 条「错」集中在**行号不准**（3 条）与**纪律/数值标注**（3 条），没有一条推翻结构性结论。

## 1. 判定表

### 1.1 路由与可达性

| 编号 | 核验对象（终稿里的断言） | 判定 | 证据 |
| --- | --- | --- | --- |
| A1 | 01 §5.6 / 03 P6：路由表 **7 条**（6 条契约 + 未认证的 GET /v1/openapi.json） | **OK** | ASGI 实测（TestClient，进程内）：/v1/openapi.json → **200 无令牌**、/v1/health/live → 200、/v1/health/ready → 200、GET / → 404 not_found、OPTIONS /v1/policy/evaluate → 405 method_not_allowed、/v1/ops/metrics developer → 403 metrics_forbidden、ops → 200；契约 paths 恰 **6** 条且**不含** /v1/openapi.json |
| A2 | 03 §4 第 8 行 / 02 附则 C：openapi.json 标「未认证 / 非契约」 | **OK** | 同上：无 Authorization 得 200；contract.ENDPOINTS 六条（contract.py:44-51）+ app.py:181 设 openapi_url |
| A3 | 04 X5 / 01 §5.6 / 03 §7：capability_unavailable、evidence_unavailable、policy_unavailable、query_invalid、target_invalid **0 个抛出点** | **OK** | grep 全 src：这五个码只出现在 errors.py 的枚举与 STATUS_BY_CODE 映射（:80/:81/:97/:98/:101），**没有任何 ErrorCode.X 使用点**；对照 RULE_SET_UNAVAILABLE / VALIDATOR_UNAVAILABLE 确有 raise 点（services.py:84/91/179/191） |
| A4 | 02 附则 C / 01 §5.2 / 03 I9+§7：capability_unavailable 必须「Phase 6 可达 + Policy API 0 抛出点」两句同时写 | **OK** | 三处都写全了：02 附则 C 明写两句；01 §5.2（拒绝，不是跳过治理）+ §5.6（0 抛出点）；03 I9 与 §7 行 360（「只在 Phase 6 多 Agent 运行时可产生」）。**唯一口径瑕疵见 §2-3** |
| A5 | 01 §5.6 / 02 G10 / 03 §7：空壳重放 = 200 + {} + Idempotency-Replayed: true = 没有结论 | **OK** | 本轮复现（同一 idempotency_key、带 include_evidence）：首次 200 / **13606 字节** → 重放 200 / **2 字节 {}** / header `Idempotency-Replayed: true`；同键换请求体 → 409 idempotency_key_conflict。代码侧：idempotency.py:240「响应体超限时只记状态码」+ runtime.py:331 写头 |
| A6 | 02 附则 B / 03 P5 行 198：precheck --dry_run「无真实副作用，但**仍会追加审计 JSONL**」 | **OK** | precheck.py:495 dry_run 形参；:499-501 文档字符串明写「不认领 action_id、不签发可用授权、不写限流台账，审计记录上标注 dry_run」；:534 条件含 `not dry_run`；R2 实测 4 个审计文件各 2582 字节 |
| A7 | D8 第 4 条 / 02 §0.1 / 03 P8：提交节点唯一判据 `approval.status == passed` | **OK** | CheckStatus.PASSED = "passed"（enforcement/models.py:233）；ReasonCode.APPROVAL_REQUIRED / APPROVAL_INVALID（:286-287）都存在；02 §0.1 与 03 P8/V8 表述一致（skipped / failed / 过期都不等于通过） |

### 1.2 命令与退出码

| 编号 | 核验对象（终稿里的断言） | 判定 | 证据 |
| --- | --- | --- | --- |
| B1 | 02 H5 / 03 P7：ci_local --list = 本地 27 步 + 仅 CI 8 步 | **OK** | 实测 27 条「本次会跑」+ 8 条「本机跳过（CI 上仍然执行）」= 35 条在范围内。03 P7 写「本机 35 步」含义含混（见 §2-5），建议与 02 对齐 |
| B2 | 01 §1 / 02 §1-A：各 self-check、openapi --check、registry --verify 退出 0 | **OK** | 本轮复测：policy_api.cli self-check 0、openapi --check 0、orchestration.cli self-check 0、enforcement.cli registry --verify 0、policy.check --check-rules 0 |
| B3 | 02 §2.2 / 03 §4 行 12：DOC-001 exit 0（2 条）、STYLE-003 exit 0（2 条）、ARCH-001 exit 1、STYLE-013 exit 1 | **OK** | 四条逐条实测：DOC-001 → 0 且 2 行溯源；STYLE-003 → 0 且 2 行；ARCH-001 → 1「没有登记的来源溯源」；STYLE-013 → 1 同文 |
| B4 | 02 §1-E E1：precheck 13 项检查；dry_run 不产生 ledger_claim（precheck.py:534） | **OK** | R2 实测 checks 恰 13 项（含 audit、无 ledger_claim）；代码 :534 逐字一致 |
| B5 | 02 §1-F F10：崩溃 `IndexError: list index out of range` @ tools/orchestration_loop.py:1413 | **OK** | 该文件 1583 行；:1413 逐字是 `action_id = run.runner.requests[0].action_id` —— 空列表时正是 IndexError 的部位（行号引用成立；运行结果本身见 C9） |
| B6 | 02 §1-B B5：query 查不到 → exit 1、status: empty (no_results) | **OK** | R2 用同一查询文本实测 exit 1、原文一致 |
| B7 | 02 §1-B B3：retrieval.cli context … → exit 0、**38 行** | **错** | 本轮同一命令实测 **37 行**（exit 0）。该命令依赖 .tmp/r1-flows/decision.json（20:36 的规则集快照），行数不可稳定复现 —— 见 §2-1 |
| B8 | 02 §1-E E2–E8、§1-I E9：execute / approve / trace / verify 与 enforcement_loop、agent_loop 的实测输出与退出码 | **无法验证** | 本轮为只读核验，未复跑这些写型命令（会写 .tmp 台账与审计、涉及真实执行）；其输入产物（.tmp/r1-flows/*.json、approval.json、ledger.jsonl）确实存在 |
| B9 | 02 §1-H H4：phase_evidence **exit 1 / result: fail / failures: 9**（contract 184 例 1 失败、integration 345 例 7 失败、security 84 例 1 失败） | **无法验证** | 历史长任务（会跑全量 pytest 并写 .tmp/artifacts）；本轮未复跑。其 rule_set_hash=sha256:dc4e96ac… 与 20:37:59 实测的 45 条规则集一致，内部自洽 |

### 1.3 数字三元组

| 编号 | 核验对象（终稿里的断言） | 判定 | 证据 |
| --- | --- | --- | --- |
| C1 | 02 §0.2 / §1-C 台阶 5：规则 **44 条 / sha256:a90e64ac…**（20:56:12） | **OK** | 本轮复测逐字一致：rules: 44（sha256:a90e64ac2d5cd1335ffb8e4c92b7717e4b92b408178ae7f921103683b4c22784） |
| C2 | 02 §5：两 root 检查 **45 条 / sha256:eea3f175…**（含 tests/fixtures/api/rules） | **OK** | 本轮复测一致：rules: 45（sha256:eea3f175c45b1f7da882d777ac8ec4cd5e9205f0607cf909f6d5cb17587a14c3） |
| C3 | 02 §0.2 / §1-C 台阶 5：受跟踪基线 **6**（git ls-files policies） | **OK** | 本轮复测 6 |
| C4 | 02 §1-A A4 / §1-C 台阶 2 / 03 P1：verify = datasets=6 entries=42 | **OK** | 本轮复测：corpus: knowledge/corpus.yaml v1 ／ datasets=6 entries=42 ／ OK，exit 0 |
| C5 | 02 §1-C 台阶 3 / 03 P1+P4：索引 42 文档 / 1013 chunk / oversized 8 / truncated 0 / 隔离 0 / generation 4 / index_version sha256:814f1b82… | **OK** | 本轮 retrieval.cli stats --json 逐项一致（documents=42、chunks=1013、oversized_chunks=8、truncated_chunks=0、quarantined=0、generation=4、index_version=sha256:814f1b82b714a533b8ae8a13d681c208a7bd0bd1b613cf92d8371e0790dc287e） |
| C6 | 03 §4 第 3 行：fixture-shop 45 条 / local-dev 44 条 | **OK** | 两条证据一致：本轮两 root 检查 = 45、单 root = 44；R2 的 smoke 输出 ready.tenants[] 同值（fixture-shop 45 / local-dev 44） |
| C7 | 02 §1-C 台阶 1：镜像数 **6**（docs/*/manifest.json） | **OK** | 本轮复跑文档给出的同一条命令 → 6 |
| C8 | 03 P2/§7 的字节数：首次 **13170** → 重放 2；02 §1-F B3 的 **10762 / 20245** | **无法验证** | 机制与量级复现（本轮同参数：带证据 13606 字节；重放 2 字节），但具体字节数随上下文（file/layer/matched 条数）变化，文档未给取得该值的上下文参数 —— 见 §2-2 |
| C9 | 02 §1-F F10：orchestration_loop **result: fail / 7 个失败 / 48.1s**（20:57–21:02）；04 X7 记 3 个失败（更早一次） | **无法验证** | 历史运行值；本轮未复跑（会写 .tmp/phase-8-orchestration 并耗时约 1 分钟）。04 X7 与 02 正文自述的「20:46 三个失败」互相一致，不构成矛盾 |
| C10 | 03 §4 第 6 行 / P2 线框：判定摘要 **allow / 0 / 0 / 44**（matched 0 / skipped 44） | **OK** | 进程内 API 实测（layer=capability、language=python、无 evidence）：allow、matched=0、skipped=44 —— 与线框一致。**口径提示**：同一上下文走 policy.check CLI（内联跑验证器、带 evidence）得到 matched=41 / skipped=3，两者不是同一个入口的证据条件，读者不要混读 |
| C11 | 02 H2/H3：seal 写出锚 **515 条**、链末 sha256:86325224…（20:40） | **OK** | 带时刻的历史值；R2 复核当前 seal --verify 报「锚 515 / 当前 522」exit 1 —— 说明该值确实只是 20:40 的快照，文档写法无错 |

### 1.4 file:line

| 编号 | 核验对象（终稿里的断言） | 判定 | 证据 |
| --- | --- | --- | --- |
| D1 | 01 §5.6 路由表来源 `contract.py:45-50 + app.py:181`；03 P6 同 | **OK** | contract.py:44-51 是六元组（:45-50 即六条路径行）；app.py:181 逐字为 `openapi_url="/v1/openapi.json"` |
| D2 | 02 §0.3：API 错误码 → 状态 `src/policy_api/errors.py:73-102` | **错** | STATUS_BY_CODE 从 :73 开始、到 **:107** 收尾（含 :103-107 的 METRICS_FORBIDDEN / INTERNAL_ERROR / NOT_FOUND / METHOD_NOT_ALLOWED）。:73-102 漏掉最后 5 条 —— 见 §2-4 |
| D3 | 02 §0.3 / G9：编排「未登记失败码按 failed` `orchestration/errors.py:161-163` | **错** | 默认值落在 **:164** `return STATUS_BY_CODE.get(error.code, RunStatus.FAILED)`；:161-163 只有函数签名与文档字符串 —— 引用漏掉了实现那一行 |
| D4 | 02 §1-F F2：`src/orchestration/cli.py:87-113` 说明「写类动作回到平台 evaluate 再进 Phase 4 链」 | **错** | :87-113 逐行是 **build_config**（workspace / checkpoints / approvals / registry 路径装配），与「回到平台 evaluate」无关。run 命令在 :298 runner 之前由 argparse 定义（:355），写入回平台链在 orchestration/tools.py 与 nodes.py —— 见 §2-1 |
| D5 | 02 §1-F F9：`cli.py:269-282`：无 checkpoint → stderr + exit 1 | **OK** | orchestration/cli.py:266-284：:269 打印「没有找到 … 的 checkpoint」到 stderr、:270 return EXIT_UNHEALTHY(=1)，:271-284 是 payload |
| D6 | 01 §5.3 / 02 台阶 7b / 03 P8：nodes.py:93-97、:67-68、:95-97；tool-registry.yaml:293-315 / :317-345 | **OK** | 四组行号逐条读码一致（nodes.py:67-68 两个工具常量；:93-97 tool_id 分支；registry 两段 approval: none / required） |
| D7 | 02 §0.3 与 03 引用的其它行号：check.py:71-73、idempotency.py:33、runtime.py:679/:676-683、store.py:12-13、check.py:77-92、checkers.py:30-37、cli.py:207-213、precheck.py:499-500/:534、enforcement/cli.py:729-730、serve.py:53-55、services.py:84,91、ops.py:149-151、observability.py:167-192、errors.py:93-95/:127-158/:128-135/:136/:146、checkpoint.py:54-56/:137-156/:205-270/:225-231/:237-254/:255-267、dsh README:51-54,64-65,84-88,117-126、workflow:50 | **OK** | 全部逐条抽读一致（workflow:50 = `run: .venv/bin/python -m policy.check --check-rules`；idempotency.py:33 = `_MAX_RESPONSE_BYTES = 8192`；store.py:12-13 注释含「generation 计数」；dsh README 段落在 51-54/64-65/84-88/117-126 内） |
| D8 | 01 §8 指向的会议文件（r0-facts、r1-modules §7、r2-review-kernel §1、r2-review-redteam §0） | **OK** | meeting/ 下 11 份文件全部存在，含 r2-review-redteam.md 与 r2-review-flows.md（引用的文件不是悬空引用） |

### 1.5 裁决纪律（D1–D15）落实

| 编号 | 核验对象（终稿里的断言） | 判定 | 证据 |
| --- | --- | --- | --- |
| E1 | D2 数字纪律：终稿每个数字都带取数时刻 + 命令 | **错** | 局部不达标：03 §2 顶栏线框、P2 线框里的「13170 字节」「matched 0 · skipped 44」、02 §1-B B4/B6 的行数没有取数命令/上下文参数；正文其余数字（规则数、条目数、索引、CI 步数）都带时刻。见 §2-2 |
| E2 | D10：终稿不得出现「当前全绿」这类总结性断言 | **OK** | 02 §0.1 明写禁止，并在 §1-H 用逐条命令替代；01/03 通篇没有「全绿/全部通过」总结句（03 P5 明写「本文件不写全部通过」） |
| E3 | D7：界面第二判定必须删除（不是标注模拟） | **OK** | 01 §4 / 03 I2 + P8 + V1/V2 都写明删除；原型两处违反复核成立：app.js:198（severity→决策）、app.js:361-366（勾选即显示「预演通过」） |
| E4 | D3：B1 修复前不得展示 action_hash / post_checks / 审批人三块 | **OK** | 02 §1-E 末与 §2.1 B1、03 P8 与 V13 都写成硬约束，且给出「不可用 + 原因 + 替代命令」形态 |
| E5 | D11：溯源逐规则三态，不许整页断言 | **OK** | 02 §2.2 四行逐规则实测表；03 P4 要求三态可单独显示；本轮实测与表内四条状态完全一致 |
| E6 | D15：file:line 可复核；既有漂移登记为本设计之外的缺陷 | **错（部分）** | 01 §8 正确登记了 models.py:267 与功能清单偏移；但**终稿自身新增了 3 处行号缺陷**（§2 的 D2/D3/D4），与 D15 的「每个 file:line 都能复核」不达标 |
| E7 | D6：可达性三值（可用 / 存在但 0 抛出点 / 不存在）落进页面 | **OK** | 01 §1 表头定义三值 + §5.6 列出五个 0 抛出点码；03 I9 / U10 / V12 规定「只在契约表灰显、不画分支」 |
| E8 | D12：安装 / 卸载 / 调度器 / 沙箱 / 第二内核五词只写成「隐喻，不成立」 | **OK** | 01 §3 的 M1–M7 逐条否定；03 U12 明文禁止肯定用法；02 附则 D 同口径 |

## 2. 错误与不精确项清单（每条：反例证据 + 建议改法）

**2-1（最严重）02 §1-F F2 的 file:line 指向了另一个函数。**
反例证据：02 写「【读码】src/orchestration/cli.py:87-113：写类动作回到平台 evaluate 再进 Phase 4 链」；实读 :87-113 是 build_config（workspace / checkpoints / approvals / registry / audit / ledger 路径装配 + RunLimits），**没有一处**涉及 evaluate 或 Phase 4。该文件里 run 的入口是 :298 run_command、参数在 :355；「写类动作回平台再进受控链」的实现位于 src/orchestration/tools.py 与 nodes.py。
建议改法：把该格拆成两条引用——「CLI 侧：src/orchestration/cli.py:266-284（status）/ :298（run_command）」+「写入回平台：src/orchestration/tools.py 的 pre_execute / ControlledExecutor 装配（01 §4 已引用该文件，可直接复用）」。

**2-2 字节数与行数是「上下文相关的量」，终稿却写成裸数字。**
反例证据：按 03 §7 的机制复现得到「首次 13606 字节 → 重放 2 字节 + Idempotency-Replayed: true」，而 03 写 13170、02 写 10762 / 20245；同一 evaluate 在不同 file / layer / matched 条数下字节数不同。02 §1-B B3 的「38 行」本轮实测为 37 行（该命令还依赖 20:36 的 .tmp/r1-flows/decision.json 快照）。
建议改法：字节数与行数写成「值 + 上下文参数 + 时刻」（例如「file=examples/good_controller.py、layer=capability、include_evidence=true、44 条规则、20:56 → 13606 字节」）；或只保留方向性断言「首次 > 8192 → 重放 **2 字节 + Idempotency-Replayed: true**」（这一条可复现）。

**2-3 capability_unavailable 两句写全了，但 02 附则 C 的路由计数与 01/03 不一致。**
反例证据：02 附则 C 写「Policy API 的 **6 条**路由里 0 个抛出点」，而 01 §5.6 与 03 P6 的定稿路由表都是 **7 条**（含未认证的 GET /v1/openapi.json）。
建议改法：统一为「**6 条契约路由**（OpenAPI paths 内）0 抛出点；第 7 条未认证端点不参与错误码口径」。

**2-4 02 §0.3 的两处行号范围不精确。**
反例证据：① `src/policy_api/errors.py:73-102` —— STATUS_BY_CODE 实际从 :73 到 **:107**，:103-107 还有 METRICS_FORBIDDEN / INTERNAL_ERROR / NOT_FOUND / METHOD_NOT_ALLOWED；② `orchestration/errors.py:161-163` —— 「未登记失败码一律按 failed」的**实现行是 :164**，:161-163 只有签名与 docstring。
建议改法：分别改为 :73-107 与 :161-164。

**2-5 03 P7 的「本机 35 步」含义含混。**
反例证据：ci_local --list 的输出结构是「本次会跑：」27 条 + 「本机跳过（CI 上仍然执行）：」8 条；35 是二者之和，不是「本机执行的步数」。02 H5 的写法（本地 27 / 仅 CI 8）才是精确的。
建议改法：改为「本机 27 步 + 仅 CI 8 步（bash-only），本机不跑也不记 pass」。

**2-6 D15 的「file:line 可复核」在终稿自身未完全达标。**
反例证据：01 §8 正确登记了两处既有漂移（models.py:267、功能清单.md 偏移约 70 行），但终稿新增了 2-1、2-4 的 3 处行号问题；03 §5 与 §7 引用的 app.js:361-366 / app.js:198 则**逐字成立**（:361-366 是「预演」按钮与「预演通过」文案）。
建议改法：把 D15 的执行细则写成「引用行号必须同时给锚文本」，并在 P-1 里加一条最小引用断言（只覆盖三份终稿的 file:line 集合）。

## 3. 终稿里仍然没有证据的断言（本轮无法独立复核）

| # | 断言（出处） | 为什么没有证据 | 复核需要什么 |
| --- | --- | --- | --- |
| 1 | 02 §1-E E2–E8、§1-I E9 的 enforcement 实测输出（approval_required、delivered、action_replay、repair_required、15 链记录） | 属写型命令（写 .tmp 台账/审计、涉及真实执行），本轮只做只读核验 | 在隔离工作区跑 tools/enforcement_loop.py 与 .tmp/r1-flows/*.json 各一次并回读退出码 |
| 2 | 02 §1-H H4：phase_evidence **exit 1 / failures 9 / 三个套件的用例数** | 历史长任务（全量 pytest + 写 .tmp/artifacts），本轮未复跑 | 单独跑一次 phase_evidence.py 并回读结果 JSON 的 suites 段 |
| 3 | 02 §1-F F10：orchestration_loop **7/8 失败、48.1s**；04 X7 的「3 个失败」 | 同上一类：耗时约 1 分钟、写 .tmp/phase-8-orchestration | 跑一次并回读 result 段与首条崩溃 traceback |
| 4 | 03 §7 / 02 §1-F 的字节数（13170 / 10762 / 20245）与 02 §1-B 的「38 行」 | 上下文相关量，终稿未给取得该值的参数 | 按 §2-2 的方式补上上下文参数后重跑 |
| 5 | 02 §1-B B4 的「policy=phase-1」与 B6 的验证器版本列表 | 依赖 20:36–20:37 的载荷快照，本轮未逐字段回读同一份载荷 | 重跑一次 --json 并逐字段比对 |
| 6 | 03 §2.1 的「GET /v1/health/live / ready 实测 **200**」是否在真实 socket 上成立 | 我用进程内 ASGI TestClient 得到 200（同一 ASGI 应用），但**没有起 uvicorn 端口** | 起一次 serve（会写 .tmp/phase-7-api 审计）后用 curl 复测 |
| 7 | 04 §1 的「R0 勘误 OK 42 / 错 3 / 无法验证 0」 | 那是 R1 的核验结论，本轮未重跑 r0 的 45 条逐条核验 | 复跑 meeting/r1-verify-facts.md 的判定表 |

## 4. 本轮实测命令清单（可复现；全部只读，ASGI 走进程内）

| # | 命令 | 关键结果 |
| --- | --- | --- |
| 1 | python -B -m policy.check --check-rules | rules: 44（sha256:a90e64ac…），exit 0 |
| 2 | python -B -m policy.check --check-rules --rules policies --rules tests/fixtures/api/rules | rules: 45（sha256:eea3f175…），exit 0 |
| 3 | git ls-files policies | 6 行 |
| 4 | python -B -m retrieval.cli verify | datasets=6 entries=42，exit 0 |
| 5 | python -B -m retrieval.cli stats --json | 42 文档 / 1013 chunk / oversized 8 / truncated 0 / 隔离 0 / generation 4 / sha256:814f1b82… |
| 6 | python -B -m retrieval.cli rules --rule DOC-001 / STYLE-003 / ARCH-001 / STYLE-013 | 0（2 条）/ 0（2 条）/ 1 / 1 |
| 7 | python tools/ci_local.py --list | 27 条本机 + 8 条仅 CI |
| 8 | python -B -m policy_api.cli openapi --check | 与快照一致（api_version=1.0），exit 0 |
| 9 | 进程内 TestClient：GET /v1/openapi.json、/v1/health/live、/v1/health/ready、GET /、OPTIONS /v1/policy/evaluate、GET /v1/ops/metrics（developer / ops） | 200 无令牌 / 200 / 200 / 404 not_found / 405 method_not_allowed / 403 metrics_forbidden / 200；契约 paths 6 条且不含 /v1/openapi.json |
| 10 | 进程内 evaluate 两次同幂等键（.tmp/r3-verify/probe_idem.py） | 首次 200 / 13606 字节；重放 200 / 2 字节 {} / Idempotency-Replayed: true；同键换体 409 |
| 11 | 进程内 evaluate（layer=capability、language=python、无 evidence） | allow / matched 0 / skipped 44（与 03 P2 线框一致） |
| 12 | 本地 build_context + evaluate（无 evidence）与 policy.check CLI（内联验证器、带 evidence）对照 | 0/44 与 41/3 的差异来自 evidence 条件，不是判定分叉 |
| 13 | grep ErrorCode.(CAPABILITY_UNAVAILABLE / EVIDENCE_UNAVAILABLE / POLICY_UNAVAILABLE / QUERY_INVALID / TARGET_INVALID) 全 src | 0 个使用点（只在 errors.py 枚举与状态映射中定义） |
| 14 | 读码：precheck.py:495/499-501/534、idempotency.py:33/240、models.py:233/286-287、orchestration/errors.py:161-164、orchestration/cli.py:87-113/266-284、errors.py:73-107、nodes.py:93-97、dsh README 四段、workflow:50 | 见 1.4 各行 |

## 5. 与第 2 轮结论的衔接

- R2 的 15 条「错」里属于**数值未带时刻**的一类，在终稿里已明显改善（规则数、条目数、索引、CI 步数、逐规则溯源都带了时刻与命令）；本轮 6 条错里只剩 1 条（2-2 的字节数/行数）属同类。
- R2 指出的 capability_unavailable「Phase 6 可达 / Policy API 不可达」口径，终稿三处都写全了（A4），只剩 02 附则 C 的「6 条 vs 7 条」措辞（2-3）。
- R2 未覆盖、本轮新发现的最高价值一条是 **D4**：F2 的 file:line 指向 build_config；这类「行号存在但内容不对」比行号漂移更隐蔽，建议写进 D15 的执行细则（引用必须带锚文本）。
