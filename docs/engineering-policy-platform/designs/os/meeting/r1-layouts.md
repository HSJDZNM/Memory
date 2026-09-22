# R1 页面布局规划 v1（界面架构师 · 页面布局）

> 会议：《平台操作系统（Platform OS）总体设计》第 1 轮 · 共享任务 task-3。
> 唯一写入文件：`docs/engineering-policy-platform/designs/os/meeting/r1-layouts.md`。
> 事实编号沿用 [r0-facts.md](r0-facts.md) 的 **F1–F39 / N1–N6**；本文件新增亲测事实写 **V1–V24**（§0）。
> 标注：【实测】= 本轮亲自跑过命令并读到输出；【读码】= 亲自读了源码或数据；【提案】= 尚未存在。
> 最高红线：界面层不得出现第二份判定逻辑（判定只有 `policy.engine.evaluate` 一条路径，F5/F31）。

## 0. 本轮新增事实（V 编号，全体会议可直接引用）

| # | 事实 | 标注 | 依据 |
| --- | --- | --- | --- |
| V1 | 六条 HTTP 路由：`/v1/health/live`、`/v1/health/ready`、`/v1/knowledge/retrieve`、`/v1/ops/metrics`、`/v1/policy/evaluate`、`/v1/validation/evaluate` | 【实测】 | `python -m policy_api.cli self-check` → `[ok] openapi_paths`；承接 F7 |
| V2 | `health/live` 与 `health/ready` 在 **HTTP 面免令牌**：无 Authorization → 200 | 【实测】 | `GET /v1/health/live` → `{"api_version":"1.0","status":"live","service":"engineering-policy-platform","deployment":"local"}`；`GET /v1/health/ready` → 200、`state=ready`、`detail="2 个租户可服务"` |
| V3 | 同两个路由走**进程内** `runtime.handle` 时改成要令牌：缺 Authorization → 401 `unauthenticated` | 【实测】 | `app.py:295-320` 的 GET 直连函数、不过 `handle_route`；界面用进程内客户端自检会得到与浏览器不同的结论 |
| V4 | 无静态托管、无 CORS：`GET /` → **404 `not_found`**；`OPTIONS /v1/policy/evaluate` → **405 `method_not_allowed`**，响应无 `Access-Control-Allow-Origin` | 【实测】 | 承接 F26 / N3 |
| V5 | metrics 三重口径：无令牌 401；developer 令牌 403 `metrics_forbidden`；ops 令牌 200 | 【实测】 | 200 正文含 `metrics.routes.<route>.{requests,errors,mean_ms,p95_ms}`、`metrics.outcomes`、`metrics.decisions`、`tenants`、`readiness` |
| V6 | `evaluate` 的两种 allow **含义不同**：`layer=capability` → allow / matched=0 / skipped=26；`layer=controller` → allow / `matched_rules=["ARCH-001@1"]` / 每条 `skipped_rules[].reasons` 写明「checker … 需要验证器证据；本次调用只提供上下文，没有验证器流水线」 | 【实测】 | 界面「绿」必须按 matched>0 判定 |
| V7 | 决策载荷可依赖字段：`schema_version` / `decision` / `request_id` / `trace_id` / `rule_set_hash` / `matched_rules` / `skipped_rules`（末项仅当 `include_evidence=true`） | 【实测】+【读码】 | `src/policy_api/runtime.py:560-573` |
| V8 | 检索今天对**两个租户都不可用**：503 `knowledge_unavailable`、`retryable=false` | 【实测】 | detail「租户 X 没有配置检索语料清单；检索不可用时不得回退到模型记忆」 |
| V9 | 索引真实存在但只在离线侧可见：`documents=27 chunks=535 quarantined=0 truncated=0 oversized=6 embedded=0`；`index_version=sha256:834e714ddf21181a993f7448ca633ce1ae0b1a6cd55d2f8b98e6042c5caaace4 generation=2`；6 个数据集 | 【实测】 | `python -m retrieval.cli stats` |
| V10 | `python -m retrieval.cli verify` 退出 **0**：`corpus: knowledge/corpus.yaml v1 \| datasets=6 entries=27 \| OK` | 【实测】 | — |
| V11 | `python -m retrieval.cli rules --rule DOC-001` → `DOC-001: 没有登记的来源溯源`，退出 **1** | 【实测】 | 规则溯源今天为空，界面只能显示"未登记" |
| V12 | 3 个协议消费者：`dsh` FULL 0.1.5-rc.1；`generic-json` READ-ONLY third-party-0.9.0（主动收紧）；`legacy-post-only` READ-ONLY legacy-agent-2.4.7（没有声明执行前钩子） | 【实测】 | `python -m adapters.cli matrix`；承接 F17/F35 |
| V13 | 工具注册表 9 个工具；`orc.policy.edit` = `reversible_write / file_edit / approval=required / perms=repo.write` | 【实测】 | `python -m enforcement.cli registry --list`；承接 F15 |
| V14 | `python -m enforcement.cli self-check` → `tools=9 approved=9`，并带警告「exec.pwsh: 本机找不到 'pwsh'；该工具会被判 execution failed（process_error），不会静默通过」 | 【实测】 | 这条警告本身就是界面必须原样呈现的"降级态"范例 |
| V15 | 验证器 7 个、checker 6 个、rule_pack 2 个、stage 7 个 | 【实测】 | `python -m validators.cli registry` |
| V16 | `SUPPORTED_CHECKERS` 恰 6 个：`CONTEXT_CHECKERS={forbidden_dependency}`，`EVIDENCE_CHECKERS` 5 个 | 【读码】 | `src/policy/checkers.py:30-35` |
| V17 | 3 个客户端：`local-dev`(developer)、`dsh-agent`(developer)、`ops-monitor`(ops)；令牌只显示 sha256 前 12 位 | 【实测】 | `python -m policy_api.cli clients`；承接 N5 |
| V18 | 编排 `self-check`：8 节点 / 6 条静态边 / 2 个条件分支；`langgraph 1.2.11`；工具注册表身份 `sha256:5e84cd67…` | 【实测】 | `python -m orchestration.cli self-check` |
| V19 | `KNOWN_LAYERS` = 12 个值 + `unknown` | 【读码】 | `src/policy/check.py:77-92`；界面层下拉框**只能**从这里取值 |
| V20 | **规则集在会议期间持续变化**：2026-09-22 20:35–20:37（+08:00），`policies/` 的 YAML 份数 26 → 39 → 45，`RuleSet.identity` 依次 `sha256:a6c9655a…` → `sha256:1e8d47fe…` → `sha256:69e46230…` → `sha256:dc4e96ac…`；`git ls-files policies` 仍是 **6** 份（F13） | 【实测】 | 首屏哈希是**取数时刻快照**，不是常量 |
| V21 | 退出码 0 通过 / 1 违规或漂移 / 2 配置错误 | 【读码】 | `src/policy/check.py:71-73`；承接 F/口径 §6.5 第 21 条 |
| V22 | 既有原型把 `rule_set_hash` 烘死在静态页：`index.html:23` 与 `activation.html:23` 都写 `sha256:ed331a8d…`，KPI 写「6 规则」 | 【读码】 | 与 V20 的实测不符 |
| V23 | 既有原型的 `?` 与灰按钮**只有** `data-tip`；全目录 `tabindex\|aria-\|noscript\|<form` 命中 **0** 处 | 【实测】+【读码】 | `Select-String` 计数 0；`build_site.py:142-143` |
| V24 | `capability_unavailable` **不在** `policy_api`：全 `src/` 仅 `src/adapters/runtime.py:88,728,1284,1289` 与 `src/adapters/conformance.py:565,624-625` | 【读码】 | 6 条 HTTP 路由今天**产不出**它 |

## 1. 信息架构：板块 → 页面 → 标签页

板块名直接取 F2 六层规范短名（口径见 [术语与口径.md](../../../../architecture/术语与口径.md) §1），不另立名称；
两个跨层页面显式标「跨层」，与口径 §1「跨层子系统一处标跨层、不复制两份」同规则。

```text
平台操作系统 · 操作台
├─ 总览（跨层首页 · 唯一入口页）                          P1
├─ ① 消费方 / 入口
│   └─ 消费方与编排            [编排运行 | Agent 会话 | CI 门禁]   P7
├─ ② 接入与协议转换
│   └─ 边界与路由              [连接自检 | 路由表 | 适配器与能力声明] P6
├─ ③ 判定核心（唯一判定路径）
│   └─ 判定工作台              [单次判定 | 规则范围 | 决策载荷]     P2
├─ ④ 能力层
│   └─ 能力层                  [检索 | 受控执行 | 验证器]           P3
├─ ⑤ 数据与契约
│   └─ 数据与契约              [规则 | 语料与镜像 | 索引与分块 | 注册表与声明] P4
├─ ⑥ 证据与门禁
│   └─ 证据与门禁              [证据抽屉 | 加载门禁 | 闭环与阶段证据 | 审计与锚定] P5
└─ 治理写入【提案】             [候选池 | 起草 | 预演 | 提交与审批 | 溯源]  P8
```

页面共 8 个（在 7–10 区间内）。**没有任何页面叫"发布""生效""启用"**——今天没有那条路由（F7/F8/N3）。

| 板块 | 页面 | 该板块今天真实存在的东西 | 今天**不存在**、页面必须留白的 |
| --- | --- | --- | --- |
| 跨层 | P1 总览 | 六路由实测结果、规则集哈希/计数 | 审批待办、作业队列（N4/G8） |
| ① 消费方 / 入口 | P7 消费方与编排 | 3 个 Agent 声明、编排 self-check、CI workflow | 真实第二 Agent、真实 ChangeAuthor（N6） |
| ② 接入与协议转换 | P6 边界与路由 | 6 路由、免令牌 health、404/405 实测、`ROUTES` | 会话身份、CORS、静态托管（N3/N5） |
| ③ 判定核心 | P2 判定工作台 | `evaluate` 全字段、`skipped_rules` 原因 | 判定结果的"保存/复用"（幂等台账无读路由） |
| ④ 能力层 | P3 能力层 | 索引统计（CLI）、9 工具注册表、7 验证器 | 检索的 HTTP 读取路径（G1/G2） |
| ⑤ 数据与契约 | P4 数据与契约 | 45 份规则文件、6 镜像 manifest、3 客户端 | 草稿规则存储（N2） |
| ⑥ 证据与门禁 | P5 证据与门禁 | 审计链文件、ledger、`phase_evidence.py`、`seal` | 证据的 HTTP 读路由、阶段证据读路由 |
| 跨层【提案】 | P8 治理写入 | 只有"今天走 CLI + Phase 4"的事实 | 全页是【提案】：草稿存储、审批中心（N2/N4） |

## 2. 全局框架

```text
+==============================================================================+
| 顶栏  [服务·部署] [连接: live/ready]  租户[—] 项目[—]  规则集[sha256:dc4e96ac…] |
|       索引版本[不可用]    身份[令牌声明·未回读]   取数 20:36:58 +08:00         |
+==========+===================================================================+
| 侧栏      | 内容区（当前页面 + 标签页）                                        |
| 板块树    |                                                                   |
| （8 项）  |                                   +---------------------------+   |
|          |                                   | 证据抽屉（右侧滑出）        |   |
|          |                                   | decision / evidence /      |   |
|          |                                   | blockers / request_id      |   |
+==========+===================================+===========================+===+
| 状态条   取数时刻 · 令牌指纹 · 租户 · generation · 未知项计数 · 无 JS 提示     |
+==============================================================================+
```

### 2.1 顶栏字段与今天的数据来源

| 字段 | 数据来源（路由 / CLI） | 今天可用性 | 编号 |
| --- | --- | --- | --- |
| 服务名、部署 | `GET /v1/health/live` → `service`、`deployment` | 可用（**免令牌**） | V2 |
| 存活 / 就绪 | `live` 结果 + `ready` 的 `state`（`ready` / `degraded` / `not_ready`）+ `detail` | 可用（免令牌） | V2 |
| 租户 | **无 `/v1/session`**；ops 令牌可从 `metrics.tenants` 看到"**全部已装配**租户" | **不可用**（除 ops 只读展示） | N5 / F26 |
| 项目 | 同上，无路由 | **不可用** | N5 |
| 规则集哈希 + 计数 | `POST /v1/policy/evaluate` → `rule_set.hash`/`rule_set.rules`；或 `ready.tenants[].checks[rule_set]`（免令牌） | 可用，但**分钟级变化** | V6 / V20 |
| 索引版本 | **无路由**；只有 `python -m retrieval.cli stats` | **不可用** | V9 / G1 |
| 身份 / 角色 | **无路由**；只有令牌自己声明（`policy_api.cli clients` 是运维侧） | **不可用**（标"令牌声明，未由服务端回读"） | N5 / F26 |
| 取数时刻 | 前端时钟；响应头 `X-Elapsed-Ms` 是耗时不是时刻 | 可用 | V5 |

**V20 是顶栏设计的硬约束**：同一分钟内规则集哈希变了 4 次。顶栏必须把哈希渲染成
「哈希 + 取数时刻 + `generation`」，并在每次路由返回后刷新；把它当常量（如 V22 的静态烘死）会立刻说错话。

### 2.2 侧栏 / 内容区 / 证据抽屉 / 状态条

- **侧栏**：只放 §1 的 8 个页面；**不放任何"操作按钮"**。侧栏项本身不携带状态色，避免"没红就是绿"的暗示。
- **内容区**：一个页面 = 标题 + 标签页条 + 表格/表单 + 页脚"本页数据来源"（逐条写路由或 CLI 命令，抄 F30 的做法）。
- **证据抽屉**：全局唯一，由判定或验证结果触发。装载的字段只有三类，且**逐条写来源**：
  `decision.matched_rules` / `decision.skipped_rules[].reasons` / `decision.violations`（来自 V7）；
  `report.evidence` / `report.blockers` / `report.served_checkers` / `truncated_evidence`（来自 `/v1/validation/evaluate`）；
  `request_id` / `trace_id`。**抽屉里没有任何编辑控件**（AGENTS 约束 32：客户端不能自带证据或决策）。
- **状态条**：常驻三件事——取数时刻、令牌指纹（sha256 前 12 位，V17）、`generation`；外加"未识别错误码原样显示"的兜底位与 `<noscript>` 提示（§8）。

### 2.3 框架级不扩权规则（四条，全部可写成断言）

1. 顶栏的租户/项目控件**只读**：值只能来自令牌授权集合，且今天连"授权集合"都没有路由可查（N5）→ 渲染为灰色 + `?` 说明缺口与替代命令（F30）。
2. 任何"切换角色/以管理员运行"的控件**不存在**（AGENTS 约束 32：服务身份不替用户扩权）。
3. 证据抽屉只读；`decision_ref` 只能由本会话的 `evaluate` 产生，**不提供手填框**（`runtime.py:701-732`）。
4. 所有写入入口（P8）默认**全部灰色**，且悬停给出"今天没有对应路由"与替代命令（`python -m enforcement.cli precheck …`）。

## 3. 逐页设计

ASCII 线框里 `[灰]` = 今天没有对应路由的禁用控件；`?` = 悬停解释位（F30）。

### P1 总览（跨层首页）

```text
+---------------------------------------------------------------+
| 服务 engineering-policy-platform · local · [live] [ready]      |
+------------------------+--------------------------------------+
| 规则集 sha256:dc4e96ac… | 45 条 · generation phase-1 · 20:36:58 |
| 索引 535 chunk          | [不可用·无路由] ?  替代: retrieval.cli stats |
| 语料 6 数据集 / 27 篇    | [不可用·无路由] ?  替代: retrieval.cli verify |
| 工具 9 · 验证器 7        | [不可用·无路由] ?  替代: enforcement.cli registry --list |
+------------------------+--------------------------------------+
| 待处理：B1 新建规则文件绕过审批 · B2 HTTP 面漂移静默（静态条目）  |
| 入口：[判定工作台] [能力层] [数据与契约] [证据与门禁]            |
+---------------------------------------------------------------+
```

- **元素与来源**：连接卡 = `health/live` + `health/ready`（V2）；规则集卡 = `evaluate`/`ready`（V6/V20）；
  索引/语料/工具/验证器四格 = **只有 CLI**（V9/V10/V13/V15），故渲染为"不可用 + 替代命令"。
- **三态**：空态 = 未取数（显示"—"与取数时刻）；错态 = `ready` 非 200 或 `state != ready`，整卡转中性并显示 `detail`；
  降级态 = `state=degraded`（部分租户不可服务）时**逐租户**列出哪一个是 `ok:false`，禁止合并成一句"服务正常"。
- **角色**：developer 可见全部只读卡；ops 额外看到 `metrics` 入口。今日**无任何**写入口。
- **【提案】删除**：既有原型的"1 个待审批动作"KPI 在 N4 下无数据源，必须删（不是隐藏）。

### P2 判定工作台（板块 ③ 判定核心）

```text
+--------------------------------------------------------------------------------+
| 文件[src/policy/engine.py] 层[controller v] 语言[python v] 操作[edit v] [运行判定] |
| ? 层取值只来自 policy/check.py:77-92 的 12 个值 + unknown（V19）                  |
+-------------------+------------------------------------------------------------+
| 结论 allow        | matched 1 · skipped 44 · violations 0 · 2ms · budget 2000ms |
| ? 绿只在 matched>0 | rule_set_hash sha256:dc4e96ac…  [证据抽屉 ->]               |
+-------------------+------------------------------------------------------------+
| skipped_rules（逐条带 reasons）                                                  |
|  DOC-001@1  checker missing_docstring 需要验证器证据；本次调用只提供上下文…        |
|  …（44 条，可折叠；不得汇总成一行数字）                                            |
+--------------------------------------------------------------------------------+
| 上下文表单：依赖[A,B] 变更集[+] 请求/追踪 ID（留空即不伪造）  [灰]保存为用例 ?     |
```

- **元素与来源**：表单枚举 = `KNOWN_LAYERS`（V19）、`operation` 五值、`language` 自由串（空串 = 未知，规则会被跳过）；
  结果面板 = `evaluate` 响应（V7）。
- **三态**：空态 = 未提交（"本页没有任何结论"）；错态 = 400 `context_invalid`/`body_invalid` 或 401/403，原文错误码直显；
  降级态 = 504/503 → **不显示任何结论色**，只显示"本次没有结论"与 `retryable`（§7）。
- **角色**：developer 可用；ops 只读（可运行判定但页面标注"运维视角，判定内容与 developer 完全一致"）。
- **不扩权**：`[灰]保存为用例` 没有路由（幂等台账无读接口）；`layer` 不提供"自动推断"开关（AGENTS 约束 6：不得由文件名推断主体）。

### P3 能力层（板块 ④ 能力层 · 三个标签页）

```text
[检索] [受控执行] [验证器]
+--------------------------------------------------------------------------------+
| 检索                                                                             |
|  POST /v1/knowledge/retrieve  →  503 knowledge_unavailable                       |
|  ? 两个租户都没配检索语料（V8）；索引其实存在：535 chunk / generation 2（V9，CLI）  |
|  [灰]重建索引 ?  替代: python -m retrieval.cli index                              |
+--------------------------------------------------------------------------------+
| 受控执行                                                                          |
|  工具 9 个（orc.policy.edit: approval=required）   [灰]提交 ?  替代: enforcement.cli |
|  exec.pwsh 降级：本机找不到 'pwsh' → execution failed（process_error），不静默通过  |
+--------------------------------------------------------------------------------+
| 验证器                                                                            |
|  7 个验证器 / 6 个 checker（1 上下文类 + 5 证据类，V16）  requires 阶段 7 个         |
|  [灰]跑探针 ?  替代: python -m validators.cli probe                                |
+--------------------------------------------------------------------------------+
```

- **元素与来源**：检索标签 = `retrieve` 实测错误（V8）+ CLI 统计（V9/V10）；受控执行标签 = `enforcement.cli registry --list` 与 `self-check`（V13/V14）；
  验证器标签 = `validators.cli registry`（V15）+ `checkers.SUPPORTED_CHECKERS`（V16）。
- **三态**：空态 = 该标签今天完全没有可取数项（检索标签即是）；错态 = 展示 503 原文与 `retryable`；
  降级态 = V14 那条 `exec.pwsh` 警告必须**原样**出现在受控执行标签，禁止折叠成"配置正常"。
- **角色**：developer 可见三标签；ops 同视图。**检索标签对任何角色都显示 503**——不可用是环境事实，不是权限。

### P4 数据与契约（板块 ⑤ 数据与契约 · 四个标签页）

```text
[规则] [语料与镜像] [索引与分块] [注册表与声明]
+--------------------------------------------------------------------------------+
| 规则  45 份 / 45 条 · identity sha256:dc4e96ac… · 取数 20:36:58                   |
|  git 跟踪 6 份（F13）；工作树另有 39 份未跟踪 —— 界面必须分两列显示                 |
|  rule_sources：0 条 ?  实测 python -m retrieval.cli rules --rule DOC-001 退出 1    |
+--------------------------------------------------------------------------------+
| 语料与镜像  6 数据集 / 27 篇 / 6 个 docs/*/manifest.json                          |
|  漂移列：[未核对] ?  无路由读漂移；retrieve 里的 hash_drift 恒为 []（B2）          |
+--------------------------------------------------------------------------------+
| 索引与分块  535 chunk / 27 文档 / oversized 6 / truncated 0 / 隔离 0（CLI，V9）    |
|  [灰]浏览 chunk ?  替代: python -m retrieval.cli query "<词>"                     |
+--------------------------------------------------------------------------------+
| 注册表与声明  工具 9 · 验证器 7 · 适配器 3（dsh FULL / 2 个 READ-ONLY）             |
+--------------------------------------------------------------------------------+
```

- **元素与来源**：规则标签 = `evaluate.rule_set`（V6/V20）+ `git ls-files policies`（F13）+ V11；
  语料标签 = `retrieval.cli verify`（V10）+ `docs/*/manifest.json`（6 个，实测 glob）；索引标签 = V9；
  注册表标签 = V13/V15/V12。
- **三态**：空态 = "本工作树没有未跟踪规则文件"这类**真话**，不是"加载中"；错态 = CLI 退出码 + stderr 原文（V21 口径）；
  降级态 = 漂移只写 **[未核对]**（B2：`runtime.py:679` 的 `hash_drift` 恒为 `[]`，**不得**显示"无漂移"）。
- **角色**：developer / ops 只读同视图。【提案】author 在此页只有"加入候选池"的**只读勾选**（勾选只进浏览器本地，F30）。

### P5 证据与门禁（板块 ⑥ 证据与门禁 · 四个标签页）

```text
[证据抽屉] [加载门禁] [闭环与阶段证据] [审计与锚定]
+--------------------------------------------------------------------------------+
| 加载门禁                                                                          |
|  规则加载器：45 份全通过 / 原子（任一失败 = 整批不加载）  [灰]强制启用 ?            |
|  ? 没有"忽略门禁"开关；空规则集同样拒绝替换（约束 4）                              |
|  验证器注册表：7 个声明 / 6 个 checker 全覆盖（V15/V16）                            |
+--------------------------------------------------------------------------------+
| 闭环与阶段证据  6 个 *_loop.py + python tools/phase_evidence.py                   |
|  [灰]在页面里跑 ?  替代：命令行；阶段证据脚本当前退出 1（既有失败，非本页产物）      |
+--------------------------------------------------------------------------------+
| 审计与锚定  摘要链（sequence + prev_digest）不是防篡改日志；锚必须与日志分离          |
|  [灰]查看链 ?  替代：python -m enforcement.cli trace；seal --verify              |
+--------------------------------------------------------------------------------+
```

- **元素与来源**：加载门禁 = `policy.check --check-rules` 退出码（V21）+ `validators.cli registry`（V15）；
  闭环标签 = F10/F20；审计标签 = F25 + `policy_api.cli seal`。
- **三态**：空态 = "今天没有可读的证据链路由"（如实）；错态 = 注册表加载失败原文（不静默、不降级，口径 §3）；
  降级态 = 阶段证据退出 1 时显示"脚本为红 + 根因指向既有失败"，**不得**在页面上把它改写为"通过"。
- **角色**：developer / ops 同视图；ops 额外可用 `seal --verify`。【提案】approver 在此页只读。

### P6 边界与路由（板块 ② 接入与协议转换）

```text
[连接自检] [路由表] [适配器与能力声明]
+--------------------------------------------------------------------------------+
| [运行自检]（这是今天真的能发请求的按钮）                                          |
|  GET /v1/health/live   → 200  live / local          （免令牌）                    |
|  GET /v1/health/ready  → 200  ready / 2 个租户可服务 （免令牌）                   |
|  GET /                  → 404  not_found            （无静态托管，V4）             |
|  OPTIONS /v1/policy/evaluate → 405 method_not_allowed（无 CORS，V4）              |
+--------------------------------------------------------------------------------+
| 路由表 6 条（V1）                                                                |
|   evaluate / retrieve / validate  —— 需 Bearer + 租户                            |
|   metrics —— 需 Bearer + ops 角色       health / readiness —— 免令牌              |
+--------------------------------------------------------------------------------+
| 适配器  dsh FULL · generic-json READ-ONLY · legacy-post-only READ-ONLY（V12）      |
|  ? READ-ONLY = 拦不住写类动作，受治理动作得到 capability_unavailable，绝不跳过治理   |
+--------------------------------------------------------------------------------+
```

- **元素与来源**：全部来自 `/v1/health/*`、`ROUTES`（`runtime.py:73`）、`policy_api.cli self-check`、`adapters.cli matrix`（V12）。
- **三态**：空态 = 未点自检；错态 = 每个探针独立显示自己的状态码与错误码；降级态 = `state=degraded` 逐租户展开。
- **角色**：developer 可自检；ops 同视图。**本页不得出现"部署配置编辑"**（`api/policy-api.yaml` 是部署数据，不是界面可编辑项）。

### P7 消费方与编排（板块 ① 消费方 / 入口）

```text
[编排运行] [Agent 会话] [CI 门禁]
+--------------------------------------------------------------------------------+
| 编排  8 节点 / 6 静态边 / 2 条件分支 · 引擎 langgraph 1.2.11（V18）                |
|  [灰]启动运行 ?  替代：python -m orchestration.cli run --request <文件>           |
|  终态只有 blocked / needs_human / failed（STATUS_BY_CODE，src/orchestration/errors.py:127）|
+--------------------------------------------------------------------------------+
| Agent 会话  dsh 是唯一真实产品；第二真实 Agent 未接入（N6/F4）                      |
|  能力上限由声明推出；未审核 / 哈希漂移一律拒绝接入（约束 24）                        |
+--------------------------------------------------------------------------------+
| CI 门禁  .github/workflows/phase-8.yml · 本机同序 python tools/ci_local.py         |
+--------------------------------------------------------------------------------+
```

- **元素与来源**：V18、F4、F10、F21、F22。
- **三态**：空态 = "今天没有正在运行的编排"（**不是** 0/0 的假进度条）；错态 = 失败码 + 终态原文；
  降级态 = 引擎不可用时显示 `EngineUnavailableError` 语义（`engine="auto"` 的回落必须如实写进 `RunReport.engine`，约束 35）。
- **角色**：developer 只读；ops 只读。**本页不提供"让 Agent 重跑"的按钮**——那等于第二条触发路径。

### P8 治理写入【提案】（跨层，整页【提案】）

```text
[候选池] [起草] [预演] [提交与审批] [溯源]
+--------------------------------------------------------------------------------+
| 候选池  勾选来源 chunk（勾选只进浏览器本地 localStorage，F30）                     |
|  [灰]加入候选 ?  草稿规则存储不存在（N2）；今天只能人工写 policies/<domain>/<ID>.yaml |
+--------------------------------------------------------------------------------+
| 起草  受控字段：id / version / checker(6 选 1) / severity(4 选 1) / scope(6 维)   |
|  [灰]保存草稿 ?  没有写路由（F8/N3）                                              |
+--------------------------------------------------------------------------------+
| 预演  ? 必须调用 policy.loader 同一套代码；不得在界面复写校验（约束 30/31 红线）     |
|  [灰]预演  没有 POST /v1/rules/preview（G4）                                       |
+--------------------------------------------------------------------------------+
| 提交与审批  展示 action_hash / diff / post_check / 回滚能力                        |
|  [灰]提交审批 ?  真实入口只有 Phase 4 受控执行链 orc.policy.edit（F29/F33）         |
+--------------------------------------------------------------------------------+
```

- **元素与来源**：【提案】。今天可验证的只有它的**边界**：`orc.policy.edit` 存在且 `approval=required`（V13）、`rule_sources` 为空（V11）。
- **三态**：空态 = "本页所有写入路径今天都不存在"；错态 = 若未来落地，只能原样呈现后端错误码，**不得自造措辞**；
  降级态 = 预演失败时唯一允许的结论句是「**现网规则集未被替换**」（空集也拒绝替换，约束 4）。
- **角色**：今天所有角色都只读；【提案】author/reviewer/approver 只是**界面分区**，不是权限（F26/N5：没有前端身份）。

## 4. 首屏（今天就能显示的真实数据）

取数时刻 **2026-09-22T20:36:58+08:00**（本机时区）。**该时刻的实测值见下表右列**；
V20 已证明这些值分钟级变化，所以首屏必须显示"取数时刻"，且每个值都要带来源。

| # | 格子 | 字段 | 真实来源 | 今天 |
| --- | --- | --- | --- | --- |
| 1 | 服务 / 部署 | `service`、`deployment` | `GET /v1/health/live` | **可显示**：`engineering-policy-platform` / `local` |
| 2 | 连接状态 | `status`、`state`、`detail` | `/v1/health/live` + `/v1/health/ready` | **可显示**：`live` / `ready` / `2 个租户可服务` |
| 3 | 租户健康明细 | `ready.tenants[].checks[]` | `/v1/health/ready`（免令牌） | **可显示**：`fixture-shop`(46 条规则) / `local-dev`(45 条规则) |
| 4 | 规则集哈希 | `rule_set.hash` / `checks[rule_set].rule_set_hash` | `evaluate` 或 `ready` | **可显示**：`sha256:dc4e96ac…`（取数时刻值） |
| 5 | 规则计数 | `rule_set.rules` | `evaluate` | **可显示**：45（local-dev）/ 46（fixture-shop） |
| 6 | 协议版本 / 世代 | `api_version`、`policy_version`、`generation` | `evaluate` 响应 + `self-check` | **可显示**：`1.0` / `phase-1` |
| 7 | 判定结论（本会话最近一次） | `summary{decision,violations,matched,skipped}` | `evaluate` | **可显示**：allow / 0 / 1 / 44 |
| 8 | ops 指标 | `metrics.routes`、`metrics.outcomes` | `GET /v1/ops/metrics`（仅 ops） | **角色限**：developer 打不开（403） |
| 9 | 索引版本 | `index_version` | **无路由**；只有 `python -m retrieval.cli stats` | **不可用**（须显示替代命令） |
| 10 | chunk / 文档计数 | `chunks`、`documents` | **无路由**；只有 `retrieval.cli stats` | **不可用** |
| 11 | 语料完整性 | `datasets`、`entries` | **无路由**；只有 `retrieval.cli verify` | **不可用** |
| 12 | 漂移状态 | （无字段可读） | `retrieve.index.hash_drift` 恒为 `[]`（B2） | **只能显示「未核对」** |
| 13 | 规则溯源 `rule_sources` | 0 条 | **无路由**；`retrieval.cli rules --rule DOC-001` 退出 1 | **不可用**（可显示"未登记"） |
| 14 | 工具注册表 | 9 个工具 | **无路由**；`enforcement.cli registry --list` | **不可用** |
| 15 | 验证器 / checker 覆盖 | 7 / 6 | **无路由**；`validators.cli registry` | **不可用** |
| 16 | 适配器支持矩阵 | 3 消费者 | **无路由**；`adapters.cli matrix` | **不可用** |
| 17 | 当前身份 / 角色 | （无路由） | 只有令牌声明（N5） | **不可用** |
| 18 | 待审批列表 | （无服务） | N4：审批是文件/结构化记录 | **不可用**（页面必须留白） |

**首屏纪律**：第 9–18 行一律渲染为「**不可用** + `?` 悬停给出替代命令」，**不得**用 0、不得用"—"含糊过去，
更不得用静态值（V22 的 `sha256:ed331a8d…` 就是这样过期的）。

## 5. 与既有 designs/console 6 页的映射

| 既有页 | 覆盖 | 处置 | 去向 | 理由 |
| --- | --- | --- | --- | --- |
| `index.html` | 总览 | **保留（重做取数）** | P1 总览 | 结构成立；但 KPI「6 规则」与 `sha256:ed331a8d…` 是烘死的静态值（V22），实测已变（V20）；"1 个待审批动作"在 N4 下无数据源，删 |
| `data.html` | 镜像 / 语料 / 索引与分块 | **合并 + 降级** | P4 数据与契约（三标签） | 三块数据都真实；但今天**没有一条读路由**（G1/G2），页面只能"CLI 快照 + 替代命令"；chunk 勾选移到 P8（勾选只进本地，F30） |
| `authoring.html` | 提炼 / 规则文件 | **合并（整页【提案】）** | P8 治理写入 | 草稿存储不存在（N2）；留在主流程会让"保存草稿"看起来可用 |
| `gates.html` | 验证器覆盖 / 候选预演 | **拆分** | P3 验证器标签（只读）+ P8 预演标签（提案） | 只读的覆盖表今天可显示（V15/V16）；预演依赖同一个 `policy.loader`（不得在界面复写，红线），故必须与 P8 同页说明 |
| `activation.html` | 审批 · 生效 · 溯源 | **废弃为独立页** | 审批→P8；生效哈希→P1/P4；溯源→P4 | 审批中心不存在（N4）、写路由不存在（F8）；"生效"只有"下一次请求重载"这一条事实，挂在总览页比单开一页诚实 |
| `system.html` | 连接自检 / 路由表 / 缺口 / 红线 | **拆分** | 连接自检+路由表→P6；缺口 G1–G8 与红线 R1–R12→P6/P5 的静态说明块 | 可执行的探针（实测 200/404/405/401/403）与静态清单性质不同，混在一页会让"静态清单"冒充"实测"；缺口/红线不占独立页面 |

**保留的交互约定**（F30，逐条沿用，不重新发明）：`?` 悬停放解释；灰按钮 = 今天没有对应路由；
勾选状态存浏览器本地；**预演必须调用后端同一套代码**，不得在界面复写。

**必须一起改掉的两条既有缺陷**：B1（新建规则文件绕过审批）、B2（HTTP 面漂移静默）——
P8 与 P4 在两条修掉之前，相关格子只能显示"未核对 / 无数据源"，不得显示"正常"。

## 6. 【界面不扩权】的呈现规则

| # | 规则 | 依据 | 违反后果 |
| --- | --- | --- | --- |
| U1 | **不渲染不存在的按钮**：没有对应路由的功能，页面里连按钮元素都不出现（不是禁用） | F7/F8、N3 | 禁用按钮会被读成"权限不够，申请就行" |
| U2 | **灰按钮 = 今天没有对应路由**，且必须带 `?` 说明缺口与替代命令 | F30 | 灰按钮不带解释就是"死按钮"，用户会去猜 |
| U3 | **已禁用操作的悬停文案必须三段**：缺口是什么（G 编号/路由名）+ 替代命令（可直接复制）+ 为什么不能在前端补 | F30 + §5 | 替代命令缺失时用户会绕到界面外写文件 |
| U4 | **前端零判定**：颜色、文案、"通过/失败"全部由后端字段或错误码推导；前端只做"字段→文案"的映射 | F5/F31 | 出现第二份判定逻辑 = 违反最高红线 |
| U5 | **服务端字段缺失时不补默认值**：`skipped_rules` 缺省不存在时显示"未请求证据明细"，不显示"无跳过" | V7 | 把"没问"渲染成"没有" |
| U6 | **未知错误码原样显示**（码 + `detail` + `retryable`），不落到"其他错误" | `errors.py:29-107` 有 33 个码，其中若干今天无抛出点（V24） | 兜底分支缺失 = 新码上线即静默 |
| U7 | **角色只影响可见分区，不影响结论**：developer 与 ops 对同一请求必须看到同一份载荷 | F5/F31 | 页面出现"我的判定"与"他的判定"两套 |
| U8 | **数字必须带取数时刻与来源**：每个 KPI 灰字标注路由或 CLI 命令 | V20/V22 | 静态烘死的数字（`sha256:ed331a8d…`）已经证实会过期 |

## 7. 【失败语义的界面表达】对照表

颜色语义只用四种：**绿**（仅 allow 且 matched>0 且 skipped 已逐条解释）、**琥珀**（
`allow_with_warnings`）、**红**（`block`）、**中性灰**（没有结论 / 未知 / 不可用）。
**504、503、429 一律中性灰，绝不绿、绝不红**——红色是"判过了，结论是阻断"，不是"没判成"。

| 后端事实 | 界面文案（唯一允许的措辞） | 颜色 | 可点击动作 | **禁止渲染成** | 依据 |
| --- | --- | --- | --- | --- | --- |
| `decision=block` | 「判定：阻断（block）」+ 逐条 violation（rule_id@version / 严重级别 / 消息） | 红 | 打开证据抽屉；重跑判定 | "失败""错误"（那是传输层措辞）；"再试一次就通过" | `models.py:267-272`、V6 |
| `required_action=approval` | 「需要人工审批后才能继续」 | 红 | 只读展示（本页无审批入口） | 把审批渲染成"黄色提示"或"稍后自动通过" | `models.py:275-278`、`:989-990` |
| `decision=allow_with_warnings` | 「判定：允许，但有 N 条告警（不阻断）」 | 琥珀 | 打开证据抽屉 | 「通过」；与 block 共用红色 | `models.py:184-186,995-999` |
| `decision=allow` 且 `matched=0` | 「**没有规则覆盖这次上下文**（不是通过）」 | 中性灰 | 展开 skipped 明细、补上下文重跑 | 「检查通过」「合规」 | V6：实测 matched=0/skipped=26 |
| `decision=allow` 且 `matched>0` 且 `skipped_rules` 均有 reasons | 「本批规则判定通过」 | 绿 | 打开证据抽屉 | 把 skipped 计入 violations；把 skipped 当通过 | V6/V7、口径 §0 第 10 条 |
| `skipped_rules` 存在（不论 decision） | 「有 N 条规则**被跳过**，原因：…」（逐条列 rule_id + reasons） | 中性灰 | 逐条展开 | 「已检查」「通过」；只显示计数不显示原因 | V6/V7；`include_evidence=false` 时该键**不存在**，须显示"未请求明细" |
| 503 `knowledge_unavailable` | 「检索不可用：本次没有结论。不得回退到模型记忆」+ `detail` + `retryable` | 中性灰 | 重试（仅当 `retryable=true`）；查看替代命令 | 「没有找到相关内容」（无结果 ≠ 不可用）；「降级为不检索」 | V8、F14；实测 detail 原句即含"不得回退到模型记忆" |
| 503 `rule_set_unavailable` / `validator_unavailable` / `policy_busy` | 「依赖不可用：本次没有结论」 | 中性灰 | `policy_busy` 显示"退避重试" | 「没有规则 = 允许」；自动重试到成功 | `errors.py:96-102` |
| 503 `audit_unavailable` | 「服务端拒绝给出决定：决定记不下来，本次没有结论」 | 中性灰 | 无（重试无意义，`retryable=false`） | 「日志满了，先跳过审计」；显示成 allow | `errors.py:65,102`、F33（审计不可写则不执行） |
| 504 `evaluate_timeout` / `retrieve_timeout` / `validate_timeout` | 「超时：**没有结论**」+ 已耗时 / 预算 | 中性灰 | 重试（`retryable=true`）；调小 `budget_ms` | 任何绿色；"稍后自动放行"；把超时当"慢" | `errors.py:93-95`、AGENTS 约束 33 |
| `capability_unavailable` | 「该 Agent 不具备强制阻断能力，无法治理此类动作」 | 中性灰 | 只读；给出"升级声明后必须重新审核"的说明 | 「已跳过治理」「只读模式 = 安全」；**不得**渲染成 allow | V24、`adapters/runtime.py:88`、F35 |
| 429 `rate_limited` | 「请求被限流，稍后重试」 | 中性灰 | 退避重试 | 静默重试到成功；把限流藏成"慢" | `errors.py:91`、V5 |
| 409 `idempotency_key_conflict` | 「同一幂等键已有了结论（未重复执行）」 | 中性灰 | **必须换新键重发** | 同键换体重发；把重放 `{}` 当"没有结果" | `errors.py:89`；重放体可能为空 |
| 401 / 403 | 「凭据或边界不被接受」+ 原始 code | 中性灰 | 重新选择租户（仅 `token_scope_mismatch`） | 显示"租户不存在"；把 403 改成可重试 | F32 |
| `evidence_unavailable`（API 面不可达） | 无文案（不为它写专门分支） | — | — | 在页面上画一个假装能触发的提示条 | V24：6 条路由无抛出点 |
| 未识别错误码 | 「未知失败：<code>」+ `request_id` | 中性灰 | 复制 `request_id` | 归入"其他错误"的绿色或"无问题" | U6 |

**被禁止的文案（清单）**：把 skipped 说成"通过"；把超时说成"通过"或"稍后放行"；把 503 说成"没有规则/允许"；
把 `matched=0` 说成"合规"；把 `allow_with_warnings` 说成"通过"；把 `capability_unavailable` 说成"跳过治理"；
把漂移未核对说成"无漂移"；把摘要链说成"防篡改日志"；把审批通过说成"通用许可"；把空幂等重放说成"没有结果"。

## 8. 窄屏 / 无 JS / 可访问性

**结论：三者都需要，但都要按"今天没有前端工程"（N1）来定形——不做 SPA、不做构建链。**

- **窄屏（< 900px）**：侧栏收成顶部下拉；证据抽屉改为**整屏覆盖**（遮罩下正文不可点，避免"抽屉后面的按钮被误触"）；
  宽表（决策载荷、证据列表）一律**横向滚动 + 首列冻结**，**不做卡片化**——卡片化会把"逐条 skipped 原因"折叠掉，等于软化失败语义。
  顶栏允许换行成两行，但**规则集哈希与取数时刻必须同行显示**（U8）。
- **无 JS 降级**：【提案】但可完整定义。今天原型的所有交互（`?`、灰按钮、勾选）都靠 JS/属性实现（V23）。
  降级形态 = 服务端渲染的"只读快照页"：每个页面输出**最后一次取数**的纯 HTML 表 + 该次取数的命令与退出码。
  降级页**只展示、零交互**：没有按钮（连灰按钮都不渲染），每张表下方写"静态快照，取数时刻 T；刷新需 JS 或重跑命令"。
  判定类页面在无 JS 时**不渲染任何结论色**，只列出原始 JSON——避免"颜色"这一层成为第二份判定。
  落地前提是 P6/P3 那批读路由（G1–G6）；在那之前，无 JS 降级页只能覆盖"CLI 快照"部分。
- **可访问性**：**需要**，理由不是合规，而是本设计把**解释**当作核心功能——解释取不到，界面就不成立（F30 把全部说明放进 `?`）。
  今天原型在这一项上是**零分**：全目录 `tabindex` / `aria-*` / `noscript` / `<form>` 命中 **0** 处（V23），
  `?` 只是一个 `<span data-tip>`（`build_site.py:142-143`），键盘无法聚焦、读屏器读不到。
  【实测】且比 `?` 更严重的是：**灰按钮上的 `data-tip` 无法用键盘触发**——`disabled` 元素不进 tab 序列，
  于是"缺口 + 替代命令"恰好对键盘用户不可达（`build_site.py:388,521` 的两处就是这个形态）。
  **最低要求（【提案】，可写成断言）**：① 每个 `?` 用 `<button type="button">` + `aria-expanded`/`aria-describedby` 取代 `<span>`；
  ② 灰按钮改成 `aria-disabled="true"` 的**可聚焦**按钮（保留可聚焦性，才带得动悬停/聚焦说明），并保持"不带路由"的事实；
  ③ 结论色不得是唯一信号：绿/琥珀/红/灰四态各配一个**文字标签**（allow / allow_with_warnings / block / 没有结论）；
  ④ 表格首行用 `<th scope>`；⑤ 状态变化用 `aria-live="polite"` 播报，且**超时/503 的播报文案不得出现"通过"**。
  ⑥ 不引入任何 a11y 依赖库：N1 下无 `package.json`，纯 HTML/ARIA 已足够覆盖上述五条。

## 9. 给 Lead 的三个风险点

1. **首屏数据是"活的"，别让它被写成常量**：V20 实测同一分钟内 `policies/` 从 26 → 39 → 45 份、
   `RuleSet.identity` 四次变化；而既有原型把它烘死成 `sha256:ed331a8d…`（V22）。
   建议在总设计里立一条：**界面上的任何哈希/计数必须带取数时刻**，且**禁止**由静态生成器写死。
2. **"检索"这一整块今天在界面上只能显示 503**（V8），而索引其实是好的（V9/V10）。
   这是**缺口 G1/G2 的最硬证据**：没有读路由，能力层在界面上等于不存在。
   如果 OS 的总体设计要展示"能力层"，G1/G2 就是必须先落地的前置项，否则那一页只能靠 CLI 截图撑。
3. **`capability_unavailable` 在 API 面不可达**（V24，只存在于 Phase 6 runtime 与一致性套件）。
   它在第 7 节的对照表里有位置，但**不能**画进任何"路由会返回它"的界面分支；
   同理 `evidence_unavailable` 也不要为它写专门 UI。**跨层公共词汇 ≠ 可用错误码**——这正好是 U6 兜底分支存在的理由。

## 10. 本轮事实引用自查

- 所有出现过的路由、字段名、错误码、文件路径、命令，均在 §0 有对应的 V 编号或 F/N 编号。
- 未找到证据、按纪律标"不可用 / 未知"的项：**前端身份回读**（N5）、**审批列表**（N4）、
  **漂移真实值**（B2）、**索引/语料的 HTTP 读路径**（G1/G2）、**草稿存储**（N2）。
- 本文件未修改任何源码、数据、AGENTS.md 或既有 designs 文档；唯一写入是本文件自身。
