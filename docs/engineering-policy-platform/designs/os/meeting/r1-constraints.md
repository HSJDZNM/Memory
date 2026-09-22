# 约束、反模式与验收 v1（红队）

> 角色：**红队（约束、反模式与验收）**。共享任务 `task-4`。本文件攻击的对象是**尚未写出的 Platform OS 总体设计**，
> 因此它不附和任何主张：凡是设计里打算做的事，我先问"今天的代码允许它吗"。
> 证据分级：**【实测】**＝本轮真的跑过命令并贴出输出/退出码；**【读码】**＝读了源码或数据并给出 `file:line`；
> **【提案】**＝尚不存在，不得读成"已经做了"；**【未知，需核验】**＝查不到证据，禁止猜测。
> 编号口径：F1–F39 / N1–N6 直接引用 `r0-facts.md`，不另造；B1/B2 引用
> `designs/文档转规则操作平台-评审意见.md`（下文简称"评审意见"）；G1–G8 引用
> `designs/文档转规则操作平台-后端契约与连接证据.md`；R1–R12 引用 `designs/文档转规则操作平台-可行性评估.md` §4。

## 0. 本轮新增/复核的事实引用（可核验）

| # | 结论 | 依据 | 级别 |
| --- | --- | --- | --- |
| X1 | `Change(path="policies/coding/NEW-001.yaml", content="x").tool_id == "orc.fs.write"`；只有 `old is not None` 时才判 `policies/` 前缀 | `src/orchestration/nodes.py:93-97`；实测输出见 A2 | 【实测+读码】 |
| X2 | `orc.fs.write`：`approval: none`、`file_path` 只有 `path_scope: workspace`、**无 pattern** | `registry/tool-registry.yaml:293-315` | 【读码】 |
| X3 | `orc.policy.edit`：`approval: required`、`pattern: ^policies/[A-Za-z0-9._/-]+$` | `registry/tool-registry.yaml:317-345` | 【读码】 |
| X4 | 越界守卫**显式放行** `policies/` 前缀：`change.path != task.target and not change.path.startswith("policies/")` 才拒绝 | `src/orchestration/nodes.py:488-491` | 【读码】 |
| X5 | 六个门禁 CLI 本轮全部退出 0：`policy.check --check-rules`、`retrieval.cli verify`、`validators.cli registry`、`policy_api.cli openapi --check`、`policy_api.cli self-check`、`enforcement.cli registry --verify` | 本轮实测输出 | 【实测】 |
| X6 | 原型起草页在浏览器内**自己算**字段门禁与决策档位：`severity=error/critical → block`、`info/warning → allow_with_warnings` | `designs/console/assets/app.js:170-200`（结论在 :198） | 【读码】 |
| X7 | 生成器把 severity 四值与"决策表"**各抄一份**进界面层 | `designs/console/build_site.py:41`、`:456` | 【读码】 |
| X8 | 生成器读不到 `policy.checkers` 时**静默回退**到硬编码的 6 个 checker 字面量 | `designs/console/build_site.py:213-219` | 【读码】 |
| X9 | 原型门禁页把本地模拟结果渲染成"预演通过""加载成功：N 条规则通过"（退出码 2 是写死的文案） | `designs/console/assets/app.js:340-343`、`:364-366` | 【读码】 |
| X10 | 原型审批页把提交工具写死成 `orc.policy.edit`，与 X1 的运行期选择不一致 | `designs/console/assets/app.js:384` | 【读码】 |
| X11 | 原型 localStorage 只存 `picks` 与 `candidates`（键 `console.state`），**没有**审批字段 | `designs/console/assets/app.js:58-74`；F30 | 【读码】 |
| X12 | 原型把候选生命周期状态字面量 `'D2 可加载'` 写进 localStorage | `designs/console/assets/app.js:293` | 【读码】 |
| X13 | console/ 下 `innerHTML|insertAdjacentHTML|outerHTML|document.write` **0 命中**；生成器有 `esc()` | grep 实测；`build_site.py:138-139` | 【实测+读码】 |
| X14 | `metrics` 响应里的 `tenants` 是**全量装配租户**；`metrics` 段本身无租户维度（按 route/outcome/status/decision 聚合） | `src/policy_api/runtime.py:822`；`observability.py:277-285`、`:304-324` | 【读码】 |
| X15 | `capability_unavailable` 有真实抛出点，且一致性套件**断言**只读上限必须报它 | `src/adapters/runtime.py:88`、`:728`；`conformance.py:624-625` | 【读码】 |
| X16 | 既有 designs 文档把 `功能清单.md` 的引用写成 :253/:254/:256，实际在 **:323/:324/:326**（偏移约 70 行） | grep `docs/architecture/功能清单.md` 实测 | 【实测】 |
| X17 | 静态原型内嵌演示令牌 `local-dev-token` | `app.js:8`；该值确为登记演示值 `api/policy-api.yaml:10`、`api/README.md:34`、`:50` | 【读码】 |

**本轮探针**（未改任何源码/数据；全部落在 `.tmp/red-team/`，用真实注册表、`precheck` 子命令、`dry_run=True`，**未执行任何写入**）：
`.tmp/red-team/req-fs-write.json`、`req-policy-edit.json`、`req-multi.jsonl`、`out-a2.json`、`out-b2.json`。

---

## 1. 【OS 宪法】C1–C15

每条格式：**一句话规则 / 反例（具体到按钮或命令）/ 违反后的后果 / 如何验证**。

### C1 判定唯一：界面、脚本、编排一律不得产出 allow / block / severity→决策

- **反例**：起草页在浏览器里把 `severity=error` 渲染成"→ block"（`app.js:198`），用户据此认为已通过判定。
- **后果**：本地结论与 `policy.engine.evaluate` 分叉，审计失去意义（R1；`AGENTS.md:220` 约束 30；F5/F31）。
- **验证**：对 console/ 扫描决策字面量（`allow_with_warnings` / `→ block` / `'block'`）——【实测】今天 4 命中：
  `build_site.py:456` 与它生成的 `authoring.html:30`（同一句决策表文案）、`assets/app.js:198`（**真正的本地计算**）、
  `assets/app.js:32`（CSS `display='block'` 误报）。门禁应断言"命中集合 == 已知文案白名单"，任何新增命中即失败；
  另加断言：前端不得存在以 `severity` 为输入、以决策值为输出的函数。

### C2 状态前进只能由后端结论驱动，本地模拟不得写成"通过"

- **反例**：门禁页复选框一勾就显示"整批不加载（退出码 2）"，取消勾选就显示"加载成功：N 条规则通过"（`app.js:340-343`）。
- **后果**：D0–D7 成为客户端信念，而非服务端事实；C23 原子性在界面上变成可撤销的开关（R5）。
- **验证**：断言每个状态徽标的 data 源来自一次 HTTP 响应或 CLI 退出码；原型阶段必须在按钮上标"浏览器内模拟"（F30 已如此约定，缺机器可校验项）。

### C3 凡是"改判定依据"的写入（`policies/**`）一律人工审批，与"是否新建"无关

- **反例**：`Change(path="policies/coding/NEW-001.yaml", content=...)` → `orc.fs.write`，pre-check 无任何 FAILED（实测 A2）。
- **后果**：新建规则文件这条**最常走的路径**没有人工门禁，治理叙事与现实断裂（B1）。
- **验证**：`python -m orchestration.cli` 或单元断言 `Change(path="policies/x.yaml", content="y").tool_id == "orc.policy.edit"`；
  以及 A2 的 precheck 退出码必须为 1（今天为 0）。

### C4 审批绑定平台口径的 `action_hash`，客户端不得自算，也不得把"已批准"缓存成凭据

- **反例**：把候选的"已批准"标记写进 `localStorage`，刷新后仍显示可提交；或在页面上"先算并展示 action_hash"。
- **后果**：审批变成客户端可伪造的状态；参数变一个字符旧授权不失效（`AGENTS.md:259` 约束 38；`action.py:9-10`）。
- **验证**：断言行内不得出现 `localStorage.setItem` 写入语义含 approval/approved/批准；`action_hash` 只能来自 `src/enforcement/action.py` 或 `ToolRunner.binding()`。

### C5 失败关闭不许被任何页面软化：超时 / 503 / 504 / 429 / 未知码 = "没有结论"

- **反例**：顶栏把 `/v1/health/ready` 的 503 渲染成绿点；或给 504 配"稍后自动放行"文案。
- **后果**：失败关闭被界面抹平（R8；`AGENTS.md:233` 约束 33；F32）。
- **验证**：`python -m pytest tests/integration/test_api_http.py -k timeout or busy`；前端断言 504/503/429 不产生"继续"分支。

### C6 `skipped_rules` ≠ 通过；"没规则管它"不得渲染成"它合规"

- **反例**：`include_evidence` 缺省时响应**没有** `skipped_rules` 键（`runtime.py:572-573`），界面按缺省请求后只显示计数，
  却把 allow 标绿——用户看不到"6 条被跳过"的原因。
- **后果**：R6 被破；U+ 解释链断裂（`engine.py:129-136` 明确把证据类 checker 记进 `extra_skipped`）。
- **验证**：断言渲染函数只在 `include_evidence=true` 且 `skipped_rules[].reasons` 非空时才允许"通过"文案。

### C7 能力上限由声明推出；`capability_unavailable` 是**拒绝**，不是"跳过治理"

- **反例**：把 `legacy-post-only` 的受治理写动作显示为"该 Agent 不支持，已跳过"。
- **后果**：把"拦不住"洗成"不用拦"（`AGENTS.md:186` 约束 24；F35；`adapters/runtime.py:728`）。
- **验证**：`python -m pytest tests/contract/test_agent_adapters.py`；断言一致性套件对只读上限的 `capability_unavailable` 判定为 FAILED（`conformance.py:624-625`）。

### C8 已审核哈希所保护的数据（`registry/`、`adapters/approved.json`）不得被未审批写入

- **反例**：用一个 `approval: none` 的工具改写 `registry/tool-registry.approved.json`（实测 A3：precheck 退出 0）。
- **后果**：授权数据与审批数据可被同一条无门禁路径改写，F15/F17 的信任根失效（`AGENTS.md:141-147` 约束 13）。
- **验证**：断言任何写侧工具的 `file_path` 均不能命中 `^(registry|adapters|api|policies)/`（见 A3 建议修法）。

### C9 漂移不许静默；"未核对" ≠ "无漂移"

- **反例**：`retrieve` 响应的 `index.hash_drift` 是硬编码 `[]`（`runtime.py:679`），界面据此显示"无漂移"。
- **后果**：违反 `AGENTS.md:139` 约束 12（F13/R9），溯源链静默断裂（B2）。
- **验证**：`python -m retrieval.cli verify` 在自造漂移镜像下退出 1（评审 A2-3）；G1 落地前断言 UI 文案含"未核对"。

### C10 摘要链是摘要链，不是防篡改日志；锚必须与日志分离

- **反例**：审计页写"本页可证明未被改过"。
- **后果**：把"删尾/整链重写发现不了"的边界（`docs/architecture/功能清单.md:324`）粉饰成安全承诺（F25；`AGENTS.md:151` 约束 16）。
- **验证**：`python -m pytest tests/unit/test_enforcement_audit.py`；断言界面文案含"摘要链"且不含"防篡改/防修改"。

### C11 不可信文本永不作为 HTML 或结构化指令解析

- **反例**：镜像 chunk 正文含 `<script>`（评审 B5 实测原样经 `hits[].text` 返回）被 `innerHTML` 渲染。
- **后果**：P0 只读页即存在存储型 XSS 面。
- **验证**：`grep -rn "innerHTML" designs/console/` 必须 0 命中（今天成立，X13）；新增断言：所有第三方文本走 `esc()` 或 `textContent`。

### C12 未知一律失败关闭，不得有"读不到就用兜底值"的路径

- **反例**：`build_site.py:213-219` 在 `policy.checkers` 导入失败时回退到硬编码的 6 个 checker（X8）。
- **后果**：界面拿旧清单当新事实，且**不报错**——正是 `AGENTS.md:114-115` 约束 3 禁止的静默降级（F39）。
- **验证**：断言生成器在核心导入失败时必须写 `checkers_error` 并让页面显示错误（对照 `build_site.py:173-174` 的 `rules_error` 已有先例）。

### C13 临时产物只在 `.tmp/`；OS 的任何默认路径不得指向真实仓库

- **反例**：G4 预演把 `repo_root` 放宽到临时目录（那等于关掉逃逸检查），或把受控工作区默认成仓库根后直接写入。
- **后果**：预演变成副作用；越界检查失效（G4 实测表第 4 行）。
- **验证**：断言预演目录落在 `.tmp/`；`python tools/cleanup.py --dry-run` 能列出全部产物（F19）。

### C14 证据只由服务端流水线产出；客户端不得自带证据或决策

- **反例**：界面提供"编辑 EvidenceBundle"框，或允许手填 `decision_ref`。
- **后果**：客户端自证通过（R2；`AGENTS.md:229` 约束 32；`runtime.py:701-732`）。
- **验证**：`python -m pytest tests/security/test_api_adversarial.py`；断言请求 DTO 里不存在 evidence/decision 字段。

### C15 文档里的每个 `file:line` 都必须可复核；引用漂移视为缺陷

- **反例**：既有 designs 文档引 `功能清单.md:253/254/256`，实际在 :323/:324/:326（X16，偏移约 70 行）。
- **后果**：验收条目"看起来有依据"却指不到东西；本文件本身也会随代码漂移。
- **验证**：新增门禁脚本对 R1 文档里的 `path:line` 断言"该行确实包含引用时的锚文本"；无法自动化的写【未知，需核验】。

---

## 2. 攻击设计 A1–A14

每条：**攻击步骤 → 是否被挡住 → 依据 → 缺口与补法**。目标是证明"哪里没有挡住"，不是复述设计意图。

### A1 把 OS 做成第二判定（**已经发生，不是风险**）

- **步骤**：打开 `authoring.html`，选 checker、填 severity，点"预演门禁"→ 页面在浏览器内跑 `validate()`，输出
  `checker_covered`/`rule_body_incomplete`/`severity_unknown`，并把 severity 直接映射成 `block`/`allow_with_warnings`。
- **挡住？** **没有**。`app.js:170-200` 全在客户端；`build_site.py:41` 抄了 severity 四值、`:42-115` 抄了每个 checker 的规则体字段与必填性、
  `:456` 把决策表写进悬停提示。这直接违反 R1 与 `可行性评估.md` §3 的自我承诺"前端不做任何判定"。
- **依据**：X6/X7；权威实现是 `src/policy/models.py:175-184`（severity 枚举与决策表注释）、`:984`（决策表函数）、
  `src/policy/checkers.py:30-37`（`CONTEXT_CHECKERS`/`EVIDENCE_CHECKERS`/`SUPPORTED_CHECKERS`）。
- **缺口与补法**：① 枚举/维度/规则体模板只能来自只读接口（G3/G5）；② 删掉 `validate()` 的"结论"语义，
  只保留输入形状约束，结论一律来自后端；③ 原型必须在页面上明确标"本页结论是浏览器内模拟，不是判定"——F30 已有此约定，
  但 `gates` 页的"预演通过"没有任何这样的标注。

### A2 借 OS 新建规则文件绕过审批（B1）——**我用真实注册表复现了**

- **步骤**：构造整文件写入（无 `old_string`）到 `policies/`，不带任何审批，跑 pre-check。
- **命令（实测）**：`python -m enforcement.cli precheck --request .tmp/red-team/req-fs-write.json --workspace .tmp/red-team/ws --json`
- **结果（实测）**：`EXIT-A=0`，`decision=allow`，`approval = skipped / allow（"该工具不需要人工审批"）`，
  registry/action_window/principal/permissions/rate_limit/circuit_breaker/ledger/audit **全 passed**。
- **对照（实测）**：同环境把工具换成 `orc.policy.edit`（改已有规则）→ `EXIT-B=1`，`decision=block`，`approval = failed / approval_required`。
- **挡住？** **没有**。root cause 是 `nodes.py:93-97`：`tool_id` 只看 `old is not None`，不看路径；
  `orc.fs.write` 的 `approval: none`（X2）与 `nodes.py:488-491` 对 `policies/` 的**显式放行**（X4）叠加。
- **补法（三选一或叠加）**：① 工具选择以"路径 + 是否新建"共同判定；② 给 `orc.fs.write` 的 `file_path` 加 pattern 排除 `policies/`；
  ③ 越界守卫改为"目标在 `policies/**` 时只允许走 `orc.policy.edit`"。**不补的代价**：P2 一上线就生产假的治理证据（评审 C3）。
- **注意**：这条路径仍受 Phase 4 台账/审计/限流约束，**可追溯但无人工门禁**——不要把"可追溯"当成"挡住了"。

### A3 扩大版：`orc.fs.write` 可无审批改写**整个工作区**，含信任根数据

- **步骤**：把 A2 的 `file_path` 换成治理链自己的数据文件，工作区取**真实仓库根**，仍不带审批。
- **结果（实测，仅 precheck，`dry_run=True`，未执行写入）**：
  `policies/coding/RT-999.yaml` → exit 0；`registry/tool-registry.yaml` → exit 0；
  `registry/tool-registry.approved.json` → exit 0；`adapters/approved.json` → exit 0；`api/policy-api.yaml` → exit 0。
- **挡住？** **没有**。`path_scope: workspace` 只保证"在工作区内"，不表达"哪些路径不许写"（X2）；
  `AGENTS.md:145-147` 约束 14 的"改注册表必须重新审核"是**流程要求**，不是 pre-check 的结构性阻断。
- **缺口**：已审核哈希是信任根（F15/F17），却与普通源码共享同一条无门禁写路径。
- **补法**：把"信任根目录"提升为结构性拒绝清单（`registry/`、`adapters/*/manifest.yaml`、`adapters/approved.json`、`api/policy-api.yaml`），
  或改成"正向白名单 + 默认拒绝"——注意两者的默认行为相反，见开放问题 O3。
- **诚实标注**：改写注册表会使所有工具立即变为未审核（自伤式 DoS），但这不改变"没有门禁"这个事实。

### A4 界面把 `skipped_rules` 当 allow

- **步骤**：界面按缺省（不带 `include_evidence`）调 `evaluate`，拿到 `allow` + `summary.skipped=6`，渲染成绿点。
- **挡住？** **部分挡住**。后端把跳过原因写进 `result.skipped_rules`（`engine.py:129-136`、`:164`），
  但只有 `include_evidence=true` 才随响应返回（`runtime.py:572-573`）——**缺省请求下界面拿不到 reasons**。
- **依据**：X6 之外的 `runtime.py:556-562`（summary 只有计数）与 `:572-573`。
- **缺口**：F30 与前端文档 §3.5/§4.1 要求"逐条列出跳过原因"，却没把"必须显式请求证据"写成请求要求。
- **补法**：① 界面强制带 `include_evidence=true`；② 或后端在 `skipped>0` 时对缺省请求返回可读原因摘要（需契约变更）；
  ③ 断言：`skipped>0` 且响应无 `skipped_rules` 键时，界面**不得**渲染"通过"。

### A5 把超时 / 服务不可达显示成通过

- **步骤**：让 `evaluate` 返回 504 `evaluate_timeout` 或 503 `rule_set_unavailable`，界面照常显示结果。
- **挡住？** **服务端挡住了，界面侧没有实现可查**。服务端由 `errors.STATUS_BY_CODE` 推导状态码（`AGENTS.md:233` 约束 33），
  `services.py:80-94` 在规则集不可加载/变空集时抛 `rule_set_unavailable` 且 `retryable=True`；504 不落幂等台账。
  dsh 侧的"超时/崩溃在 Agent 侧等于放行"是 `AGENTS.md:131-134` 约束 10 的已知事实，失败关闭靠 Hook 自身预算 + 异常转 exit 2（`src/adapters/dsh/hooks.py:13-14`）。
- **缺口**：**今天没有任何前端实现**（N1），所以"界面不软化失败关闭"目前**不可验收**，只有原型里的静态文案。
  验收必须写成"纯函数级断言"，见 V4/V5，而不能写成"页面看起来对"。
- **【未知，需核验】**：本机 `evaluate` < 1ms，504 未能自然构造（评审 C4 同样未构造），504 路径只有读码证据。

### A6 把摘要链说成防篡改日志

- **步骤**：在溯源页写"审计链可证明规则未被篡改"，并据此把漂移列标绿。
- **挡住？** **文档侧挡住了，界面侧没有载体**。`功能清单.md:324` 已自述"删尾部或整链重写发现不了"；
  对外锚定是 `python -m policy_api.cli seal --out <锚>`（F25），且 AGENTS.md 要求锚与日志分离。
- **缺口**：界面要展示"锚定状态"，但今天没有读取锚的 HTTP 面（G1/G2 都不含锚）；没有数据就会退化成静态口号。
- **补法**：在 G 清单里显式增加"锚定状态"只读项，或明写"本页只展示摘要链，锚定状态需在终端执行 seal --verify"。

### A7 用 `localStorage` 当审批凭据

- **步骤**：把"已批准/可提交"存进 `localStorage['console.state']`，刷新后仍可提交。
- **挡住？** **今天不构成凭据**（X11：只存 `picks` 与 `candidates`），但**前身已经出现**：
  `app.js:293` 把生命周期状态字符串 `'D2 可加载'` 落进同一个 localStorage 对象（X12）。
- **后果预演**：一旦 P1/P2 把 D0–D7 状态持久化在客户端，"状态前进只能由后端结论驱动"（C2、R1）就变成客户端可写。
- **补法**：① localStorage 只允许存**输入**（勾选、表单草稿），禁止存**状态结论**；
  ② 断言 `console.state` 的 schema 里不存在 state/approved/verified 一类字段；③ 审批凭据只能来自 Phase 4 记录。

### A8 `metrics` 页跨租户泄露

- **步骤**：持 `ops` 令牌（或 `metrics_clients` 里的客户端）调 `GET /v1/ops/metrics`，读取租户清单。
- **挡住？** **最小权限挡住了，信息面没挡住**。授权是 `ops` 角色或 `metrics_clients`（`ops.py:37-43`；F7），
  developer 令牌实测 403 `metrics_forbidden`；但响应里 `"tenants": list(self.store.ids)` 是**全量装配租户**（`runtime.py:822`，X14）。
- **收窄结论**：`metrics` 段本身**无租户维度**（`observability.py:277-285`、`:304-324` 按 route/outcome/status/decision 聚合），
  所以这不是"跨租户的业务数据泄露"，而是**租户存在性/命名泄露**。既有文档已提示"不能当租户选择器"（G6）。
- **补法**：G6 的 `/v1/session` 落地后，把 `metrics.tenants` 收敛为"本令牌授权集合"，或直接移除；改之前界面不得使用它。

### A9 OS 直接写 `policies/` 或 `registry/`，绕过已审核哈希

- **步骤**：前端（或桌面壳形态 C）直接 `fs.write` 到 `policies/`；或写 `registry/tool-registry.yaml` 后重签 `approved.json`。
- **挡住？** **形态 C 被红线挡住（文档层面），运行期没有挡住**。
  `policy_api` 只有 6 条只读语义路由（`runtime.py:73`，F7/F8），没有 enforce 路由；
  但 A3 已证明 `orc.fs.write` 的 pre-check 对 `registry/`、`adapters/approved.json`、`api/policy-api.yaml` 全部放行（实测）。
- **关键区分**：`policies/` 的文件**不在已审核哈希保护范围内**——它的保护是"加载时整批原子 + 空集拒绝替换"
  （`services.py:73-97`【读码】）；哈希只在加载后以 `RuleSet.identity` 形式暴露为 `rule_set.hash`。
  所以攻击的真实形态不是"绕过哈希校验"，而是**无审批地改变判定依据**，再让下一次请求整份重载。
- **补法**：C8 + A3 的结构性拒绝清单；并补"规则文件变更必须可追到一次 `orc.policy.edit` 台账记录"的断言。

### A10 把 `capability_unavailable` 当成"跳过治理"

- **步骤**：把 `legacy-post-only`（`blocking: post_only`）的受治理写动作在界面显示为"该 Agent 不支持阻断，本次跳过"。
- **挡住？** **核心层挡住了**：`src/adapters/runtime.py:728` 是真实抛出点，文案是"该 Agent 不具备强制阻断能力，无法治理此类动作"；
  一致性套件**断言**只读上限必须报告 `capability_unavailable`（`conformance.py:624-625`，X15）。
- **缺口**：界面层没有任何"这是拒绝"的语义约束；已有反模式清单（前端 §5）未列出这一条。
- **补法**：把 `capability_unavailable` 写进界面错误映射表并明确"必须渲染为阻断/需要人工"，不得出现"跳过"字样。

### A11 静态页内嵌令牌

- **步骤**：控制台以静态资源形态发布，`assets/app.js` 里带着 `DEMO_TOKEN`，任何能打开页面的人都拿到它。
- **挡住？** **今天不算泄露**（X17）：`local-dev-token` 是 `api/policy-api.yaml:10` 明确标注的演示值，
  且在 `api/README.md:34/:50` 登记（后者带 `secret-scan: allow`）。
- **缺口**：**模式是危险的**——令牌进入客户端分发物后，`G7` 的"控制台只发起 + 展示"就必须改成"令牌由用户会话提供"，
  而不能沿用"把 token 编译进 JS"。另外 `app.js:402` 把探针目标写死成 `http://127.0.0.1:8088`，与"同源"结论（N3）冲突。
- **补法**：P0 只读骨架允许演示令牌，但必须在页面上标注"演示凭据，仅限本地"；P1 起令牌不得出现在静态产物里。

### A12 挂载点取 `/`，让统一错误信封失效

- **步骤**：把静态目录挂到 `/`，然后访问未知路径 / 错方法。
- **挡住？** **没有挡住，只有文档前提**。评审实测：挂载后未知 POST 由 404 变 405、真实路由错方法由 405 变 404（评审 A2-6）；
  `AGENTS.md:233` 约束 33 要求错误码由 `STATUS_BY_CODE` 推导，此变化使该承诺对未知路径不再统一。
- **缺口**：契约测试按 `route.name` 过滤（`tests/contract/test_api_protocol.py:174-178`），**挂载的副作用不会被 CI 发现**。
- **补法**：P0 前提"挂载点避开 `/`"必须写成回归测试：断言挂载前后未知路径 404 与错方法 405 语义一致。

### A13 引用漂移让"验收"失去支点

- **步骤**：按 designs 文档里的 `功能清单.md:253` 去核对"不引入 LLM"，发现该行是工具表。
- **挡住？** **没有**。实测：真实位置是 `docs/architecture/功能清单.md:323`（LLM/MCP/向量库未引入）、`:324`（摘要链边界）、`:326`（审批无签名与名册），
  与文档写的 :253/:254/:256 相差约 70 行（X16）。
- **后果**：R12/R10/R4 这些红线的"依据"实际指不到东西；OS 设计若继续引用这些编号，会把这套漂移再复制一遍。
- **补法**：C15 的引用断言门禁；本文件对 `功能清单.md` 一律使用**本轮实测的行号**。

### A14 生成器的硬编码回退（静默降级）

- **步骤**：让 `from policy.checkers import SUPPORTED_CHECKERS` 失败（改名/依赖缺失），重建页面。
- **挡住？** **没有**：`build_site.py:216` 直接回退到 6 个字面量，页面照常显示"checker 已实现/无验证器供证"，不报错（X8）。
- **对照**：同一函数里读规则集的失败**会**写 `rules_error` 并显示（`build_site.py:173-174`）——说明"报错"在本仓库是既有惯例，
  兜底回退是**偏离惯例**，不是风格问题。
- **补法**：与 C12 同；把回退改成显式错误分支，并加一条断言"核心数据读取失败时页面必须出现错误标记"。

---

## 3. 可断言验收 V1–V22

格式：**给定…当…则…**。凡能落到现有测试目录或 CLI 退出码的，直接给出落点；落不到的标注【提案：需新增测试】。

| # | 验收条目 | 落点 |
| --- | --- | --- |
| V1 | 给定一个路径以 `policies/` 开头、只有 `content` 没有 `old` 的 `Change`，当读取 `tool_id`，则等于 `orc.policy.edit` | `tests/unit/`【提案：需新增，今天为 `orc.fs.write`】 |
| V2 | 给定 `registry/tool-registry.yaml` 的真实注册表，当对 `orc.fs.write` 提交 `policies/**` 目标且不带审批，则 pre-check 为 `block` 且退出码 1 | `python -m enforcement.cli precheck …`（今天退出 0，X5 之外的实测 A2） |
| V3 | 给定任一 `policies/`、`registry/`、`adapters/approved.json`、`api/policy-api.yaml` 目标，当走任何 `approval: none` 的写工具 pre-check，则必须 `block` | `tests/security/test_enforcement_adversarial.py`【提案：需新增用例】 |
| V4 | 给定 504 / 503 / 429 任一响应，当界面状态计算出结果，则其 kind 只能是"没有结论"，且不存在通往"继续"的转移 | `tests/unit/`（纯函数）【提案：需新增测试】 |
| V5 | 给定 `skipped>0` 且请求未带 `include_evidence`，当渲染结果，则不得出现"通过/允许" | `tests/unit/`【提案：需新增测试】 |
| V6 | 给定同一上下文，当本地与经 API 各判定一次，则两份决策载荷 JSON 值相等 | `tools/api_loop.py`（`AGENTS.md:220` 约束 30；F31） |
| V7 | 给定含一条坏文件的规则目录，当加载规则集，则整批失败且**现网规则集未被替换** | `tests/unit/test_loader.py`、`services.py:73-97` |
| V8 | 给定规则目录被清空而现网规则集非空，当请求判定，则 503 `rule_set_unavailable`（空集不得替换） | `tests/integration/test_api_http.py` |
| V9 | 给定自造漂移镜像，当跑 `python -m retrieval.cli verify`，则退出 1；且界面在 G1 落地前只能显示"未核对" | CLI 退出码（评审 A2-3）；UI 断言【提案】 |
| V10 | 给定 `legacy-post-only` 的受治理写动作，当经多 Agent 运行时执行，则得到 `capability_unavailable` 且**不是** allow | `tests/contract/test_agent_adapters.py`、`conformance.py:624-625` |
| V11 | 给定 developer 令牌，当调 `GET /v1/ops/metrics`，则 403 `metrics_forbidden` | `tests/integration/test_api_http.py` |
| V12 | 给定多租户令牌且不带 `tenant`，当调 `POST /v1/policy/evaluate`，则 403 `token_scope_mismatch` | `tests/integration/test_api_http.py` |
| V13 | 给定同一 `action_id` 的第二次执行请求，当经执行器运行，则被台账阻断且**不产生第二次副作用** | `tests/integration/test_enforcement_executor.py` |
| V14 | 给定 `orc.policy.edit` 的审批记录，当把参数改一个字符，则旧审批失效（`action_hash` 不符） | `tests/unit/test_precheck.py`、`approvals.py:106-108` |
| V15 | 给定未知 `api_version` / 未知字段 / 未知 checker，当加载或调用，则报错而非静默忽略 | `tests/contract/test_api_protocol.py`、`tests/unit/test_loader.py` |
| V16 | 给定控制台静态产物，当扫描渲染路径，则 `innerHTML` / `insertAdjacentHTML` / `outerHTML` / `document.write` 命中为 0 | grep 门禁【提案：加进 `tools/ci_local.py`】 |
| V17 | 给定 `console.state` 的 schema，当持久化，则不含任何 approval/approved/state 结论字段 | 【提案：需新增测试】 |
| V18 | 给定 `build_site.py` 无法导入核心 checker 清单，当重建站点，则页面出现显式错误标记，不得回退到硬编码列表 | 【提案：需新增测试】 |
| V19 | 给定静态挂载点不为 `/`，当访问未知路径与错方法，则 404/405 语义与挂载前一致 | `tests/contract/test_api_protocol.py`【提案：需新增用例】 |
| V20 | 给定本 R1 文档，当扫描全部 `path:line` 引用，则每一处指向的行都包含所引锚文本 | 【提案：新增引用漂移门禁，见 C15/X16】 |
| V21 | 给定仓库六个门禁命令，当顺序执行，则退出码全为 0 | 本轮实测：`policy.check --check-rules`、`retrieval.cli verify`、`validators.cli registry`、`policy_api.cli openapi --check`、`policy_api.cli self-check`、`enforcement.cli registry --verify` 全部 exit 0 |
| V22 | 给定任何"OS 页面/脚本产出的结论"，当追溯其数据源，则必须能指回一次 HTTP 响应字段或一次 CLI 退出码 | 人工 + 【提案：前端契约测试】 |

---

## 4. 对【操作系统】这个隐喻本身的批判

隐喻不是中性的：它决定人们会**默认**哪些操作存在。以下五条是它在什么情况下会诱导错误设计。

### M1 "操作系统"暗示可以把规则**安装 / 卸载**

- **诱导**：设计出"启用这条规则 / 停用那条规则"的开关，或"卸载某条规则后立刻生效"。
- **事实**：规则集的语义是**整批原子加载**，任一文件失败即整批不加载，且**空集拒绝替换**正在服务的规则集
  （`services.py:80-94`，AGENTS.md:116 约束 4）。没有"单条卸载"这种操作语义；"停用"只能表达为把它从目录里移除后的**整批重载**。
- **正确形态**：把"生效"表达成**一次原子替换 + 前后 `rule_set_hash` 对比**（R5），而不是 per-rule 开关。
  前端反模式 5.2"忽略门禁/强制启用开关"就是这条隐喻的产物。

### M2 "操作系统"暗示界面是**第二个内核**（控制面板高于被控对象）

- **诱导**：既然有"系统面板"，面板就应当能做系统能做的任何事，包括写入、重载、改配置。
- **事实**：界面今天连"系统调用"都没有——只有 6 条**只读/判定语义**路由（`runtime.py:73`，F7），
  且 **API 没有 enforce 路由**（F8、`AGENTS.md:263` 约束 39）；权限唯一来源是令牌（`auth.py:167-186`），不是页面位置。
- **正确形态**：把 OS 当**仪表盘 + 申请单**：能看见、能发起、不能自己执行。G7 已经给出正确结论——提交接入点**不开在 `policy_api` 里**。

### M3 "操作系统"暗示存在**进程隔离 / 沙箱**

- **诱导**：认为"受控执行"等于"跑在沙箱里"，于是放松对命令白名单的警惕。
- **事实**：`AGENTS.md:155-162` 约束 17 明说"**白名单不是沙箱**：会读仓库内配置的命令仍可能被改写成执行外部命令，
  真正的隔离属于运行时的文件系统与进程沙箱，**不在本阶段**"。今天的隔离只有三条：
  命名空间隔离 + trace 来源校验 + 窗口熔断（`AGENTS.md:200-206` 约束 26）。
- **正确形态**：把"隔离"写成**可删除性**与**结构拒绝**：删掉 `src/orchestration/` 平台照常运行
  （`tests/contract/test_orchestration_engine.py`；`AGENTS.md:242` 约束 35），比"内核态/用户态"的类比可靠得多。

### M4 "操作系统"暗示有**调度器**（OS 会自己决定下一步）

- **诱导**：设计出"平台自动重试 / 自动回滚 / 自动放行"的隐式行为。
- **事实**：编排层是**消费者**，不是平台的一部分（`AGENTS.md:242` 约束 35）；分支**只由结构化 Decision 决定**，
  终态只由失败码决定（`:255` 约束 37）；恢复发现"开工未结算"即 `side_effect_unknown` **交给人**，不重放也不假装成功（`:263` 约束 39）。
- **正确形态**：没有"默认放行"的路径。任何"自动"都必须能在 `errors.STATUS_BY_CODE` 里找到那个把流程停下来的码。

### M5 "操作系统"暗示 `policies/` 是**可读写的文件系统**

- **诱导**：推出 `mv` / `cp` / `rm` / "另存为"这类操作语义。
- **事实**：注册表只给了两个写 driver（`file_write` / `file_edit`，`registry/tool-registry.yaml:300`、`:324`），
  写规则的那一个还额外要求 `old_string` 与 `^policies/…` pattern（X3）——**没有"整文件替换规则"这个受控操作**。
  而 A2 恰好证明：整文件写入会掉到另一个无审批工具上。也就是说隐喻诱导出的"最自然的操作"（新建文件）
  今天走的是**最不安全的路**。

---

## 5. 开放问题（留给 Lead 与后续轮次裁定）

1. **O1**（C9/B2）G1 落地前，漂移列写"未核对"是止损；但"未核对"是否应当**阻断提交**？今天没有任何路由能提供漂移事实，
   "不阻断"意味着允许在未知状态下推进——这条需要 Lead 给出明确取舍，否则 P2 会在不确定的溯源上盖章。
2. **O2**（A1/C1）原型的 `validate()` 与 G3 的关系：是"先删前端判定再上 P1"，还是"G3 到位后前端只保留输入形状"？
   两种顺序的验收条目不同；若选后者，必须补一条"前端不得引入新的结论字段"的断言。
3. **O3**（A3/C8）`orc.fs.write` 的收口方式：**正向白名单**（默认拒绝，新增目录要显式声明）与
   **负向拒绝清单**（`policies/`、`registry/`…，默认放行）对"未来新增的敏感目录"行为**相反**。
   我倾向正向白名单，但这会改变现有工具表语义（需重新审核 + 契约测试）。
4. **O4**（C4/R4）审批人名册缺失是既有事实（`功能清单.md:326`）。在"无签名、无名册"的前提下，
   OS 的审批页展示"审批人由 Phase 4 记录决定"是否足够？若 P3 引入 AI 辅助起草，外部义务会升级（`可行性评估.md` §8 的 EU AI Act Art.14 讨论）——**该义务的适用性我未独立核实**，标【未知，需核验】。
5. **O5**（A12）同源静态挂载"避开 `/`"是否足够，还是必须走反向代理同源（D 形态）？前者仍需承担
   "前端缺陷连带判定进程"的代价；后者多一个部署件。这条影响 P0 的形态选择。
6. **O6**（A7/C2）localStorage 允许持有到哪一层？我的立场：**只能存输入，不能存状态结论**。需要 Lead 确认，
   否则 P1 的"草稿"很可能顺手把 D0–D7 落进客户端。
7. **O7**（A8）`metrics.tenants` 是否收敛为"本令牌授权集合"？收敛后与 G6 的"诱饵"论证冲突，
   但保留了"租户存在性"泄露；不收敛则界面永远不能用它。需要一个明确的对外口径。
8. **O8**（A14/C12）`build_site.py:216` 的硬编码兜底是删除还是改为显式错误？删除会让站点在核心缺失时不可用——
   这正是失败关闭的应有行为，但会让本地预览更脆。
9. **O9**（C15/X16）引用漂移是普遍现象（`功能清单.md` 偏移约 70 行；`src/adapters/runtime.py` 的 866-886 vs 871-919 也已被评审记录）。
   是否要为 `docs/` 引入引用断言门禁？成本与收益需要 Lead 权衡。
10. **O10**（A2/A3）**我最想请 Lead 注意的一条结论**：B1 不是"新建规则文件"这一个按钮的问题，
    而是"**`orc.fs.write` 在真实仓库根上无审批地放行任意路径**"（实测 A3，含 `registry/tool-registry.approved.json` 与 `adapters/approved.json`）。
    只要这条不改，OS 的任何"提交"按钮都建立在一个已经有后门的执行链上；先修 B1 再谈 P2 是必要条件，不是可选项。
    同时我必须诚实标注反方最强论点：该路径**可追溯**（台账 + 审计链已写，实测 audit `sequence=1` passed），
    所以它不是"无声的"后门，而是"有账无门禁"的后门——这会削弱"必须先修"的说服力吗？我认为不会，
    因为 OS 的卖点正是"变更必须有人批准"，而台账记录的是**发生过**，不是**被批准过**。

---

## 附：本轮最小复现清单

```powershell
# 全部落在 .tmp/red-team/，未改源码与既有文档；precheck 为 dry_run，未执行任何写入
$env:PYTHONPATH = 'src'
python -c "from orchestration.nodes import Change; print(Change(path='policies/coding/NEW-001.yaml', content='x').tool_id)"
python -m enforcement.cli precheck --request .tmp/red-team/req-fs-write.json    --workspace .tmp/red-team/ws --json   # 实测 exit 0
python -m enforcement.cli precheck --request .tmp/red-team/req-policy-edit.json --workspace .tmp/red-team/ws --json   # 实测 exit 1
python -m policy.check --check-rules; python -m retrieval.cli verify; python -m validators.cli registry
python -m policy_api.cli openapi --check; python -m policy_api.cli self-check; python -m enforcement.cli registry --verify
```

**本文件未做的事（如实标注）**：未执行任何写入型工具（只有 `precheck`）；未跑全量 `pytest`；
未构造 504 超时（本机 evaluate < 1ms）；未做浏览器 DOM 渲染实验（XSS 只有响应形状证据，评审 B5）；
未核实 `功能清单.md` 中关于外部法规义务的转述是否适用。
