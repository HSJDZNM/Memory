# 24 · 台阶 4 · `governs` 轴与声明差集设计稿（**只报告**，只写文档）

- **执行**：2026-10-01（本机）；控制面重构会话（**唯一写者**）。
- **树**：分支 `refactor/control-plane`；写这份稿子时的 HEAD = `025465a`（本轮 `test_layout` 改正
  `096cb0d` 与它的读数 `025465a` 已落地，写稿前 `git status --porcelain -uall` 为空）。
- **依据**：方案 §3.5（三数分离与顶层键白名单）与 §4 台阶 4、附录 §B.3（反方判决条件第 2 条）；
  17 号 §2.3 第 1、3 条（`governs` 轴与声明差集都判"**建机制**"）与 §2.2（12 个通道的实数）；
  21 号 §2.5（覆盖账的 `reading_context` 与"顶层键白名单"的原位）；23 号 §9.3 / §11（覆盖账与审计
  两次落地的 R-d 口径）；04 号 §5 的 L6（governs 分档、禁比例、`--environment`、渲染基准等六处）；
  AGENTS 第 45（仪器要能失败）/ 48（读数属于哪棵树）/ 50（口径诚实）/ 55（加键就是改协议）/
  56（账本不存在 = 不适用）条。
- **本文件是什么**：台阶 4 里 `governs` 轴与声明差集这两件的**设计稿**——要加的键、分档与覆盖规则、
  三数与五个差集的定义、**只报告期怎么表达 `in_scope_not_wired` 这条红条件**、版本轴与同批改动、
  消费方、R-d 预注册形状、预算与落地顺序。
- **本文件不是什么**：不是开工单，也不是排期。**本文没有改任何代码、任何载荷、任何数据文件**；
  `governs` 轴、声明差集、豁免到期机制、仪器自证（R-h）仍按 **D-2 冻结**，本文只给形状。

---

## 0 一句话

把"**谁在范围内、谁声明过、声明与发现差在哪**"做成**可读的整数与清单**，并且在解冻之前
**一条退出码都不接**：`in_scope_not_wired` 用"**显式的红 + 显式的未接线**"表达
（`red_conditions.in_scope_not_wired.enforced = false`）——它就是将来那条红条件的**预注册形态**，
而不是一条被悄悄推迟的检查。

---

## 1 它要回答什么（判据 + 今天的三条读数）

### 1.1 判据（可证伪）

1. **正面判据**：只凭 `wiring --json` 一份载荷，必须能回答：本机**发现**了几个通道、声明文件
   **覆盖**了几个、"声明在范围内却没接线"的有几个——**不必**去读声明文件、也不必去读 probe 日志；
2. **反面判据（今天就能验）**：今天 `dsh:desktop` 的 `not_wired` 与"**没人声明过它算什么**"
   在载荷里长得**一样**（都是 `status: not_wired`）；分不开，这一项就还没有 `governs` 轴；
3. **不改变的判据**：落地前后 `channels[].status` / `wiring_status` / `freshness_status` /
   `result` / `failures` / 两份退出码**逐个相同**（R-d，见 §5）。

### 1.2 今天的三条读数（实跑，树 `025465a`）

| # | 读数 | 出处 |
| --- | --- | --- |
| 1 | `python -m adapters.cli wiring --json --now 2026-10-01T00:00:00+08:00` → **24131 B**；顶层 **13 个键**里**没有** `account` / `differences` / `headline`；`result=fail`、`counts={total:12, wired:6, failed:6}`、`fact_counts={wiring_ok:7, freshness_ok:6}` | `.tmp/step10/wiring-now.json` + `.tmp/step10/probe_wiring_now.py` |
| 2 | 12 个通道**全是** `kind=dsh-profile`；`dsh:desktop` / `dsh:headless` / `dsh:web` / `dsh:verify-dead` = `not_wired`，`dsh:verify-exit2` = `hooks_config_missing`，`dsh:verify-bc` = `audit_never_written`，其余 6 个 `wired` | 同上 |
| 3 | 声明文件 `adapters/wiring-scope.yaml`：`declared: 7`、`by_decision={in_scope:1, out_of_scope:5, expected_absent:1}`；到期读数 `HITS: 0 / declared=8 due=0 expired=0 unprovable=0`（8 = 6 条带 `expires_at` 的声明 + 2 条门禁只报告步骤） | `provenance.cli wiring-scope --check` / `tools/exemption_expiry.py` |

**两条今天就能看见的缺口**（不是猜测，是上面读数直接读出来的）：

- **声明与通道之间没有连接键**：7 条声明里 **5 条**是 `kind=agent_runtime`（`governed-session-hook`
  是 `in_scope`，另外 4 条是 `out_of_scope`）——**同档不同判决**，而条目里**没有**任何字段说明
  "这条声明管哪些通道"。所以 `covers`（§2.1）不是锦上添花，是这份设计成立的前提；
- **8 个通道的目标在工作区之外**（`hooks_config` / `audit_path` / `bridge.entry` 渲染成
  `<external>/…`，这是 `wiring.py` 既有的口径）：它们事实上在**治理另一棵树**，而声明文件里
  **一个字节都没有**说这件事是不是有意的。这正是"「有意治理另一棵树」的声明位"要补的空。

---

## 2 设计

### 2.1 `governs` 轴（按 `kind` 分档 + 「有意治理另一棵树」的声明位）

**要加的键**（`channels[]` 内，一个对象；名字复用既有词汇）：

```json
"governs": {
  "decision": "in_scope",              // in_scope | out_of_scope | expected_absent | undeclared
  "declared_by": "governed-session-hook",  // 声明条目的 id；undeclared 时为 null
  "declaration_kind": "agent_runtime",     // 声明侧的 kind（发现侧是 dsh-profile）
  "expires_at": "2026-12-31",              // 没有到期日写 null
  "expired": false,                        // 只报告：不改 status / 不改退出码
  "tree": {
    "relation": "other",                   // self | other | unknown（由通道自己声明的目标算出）
    "declared": "unknown",                 // self | other | unknown（声明里的 governs_tree；**没写 = unknown**，裁定④）
    "declared_by": null,
    "evidence": ["hooks_config", "audit_path", "bridge.entry"]  // relation 是从哪几个字段读出来的
  },
  "note": "…"                              // 一句话，人读；undeclared / 冲突时写明原因
}
```

**分档与覆盖（三条规则，按优先级）**：

| # | 规则 | 为什么 |
| --- | --- | --- |
| 1 | **显式 `covers` 优先**：声明条目可带 `covers: ["dsh:governed", "dsh:governed-*", …]`（glob 作用于 `channel_id`） | 5 条 `agent_runtime` 声明同档不同判决；没有显式覆盖就只能靠猜 |
| 2 | **`kind` 档兜底**：发现侧 `kind` → 声明侧 `kind` 的映射是**数据**（`wiring-scope.yaml` 新增 `channel_kinds: {dsh-profile: agent_runtime}`）；未映射的发现 kind → `decision=undeclared` + `note`，**不猜** | "按 `kind` 分档"要能被读出来，而不是写死在代码里 |
| 3 | **同档冲突不挑一个**：同一通道被多条**同级**声明命中而 `decision` 不同时，该通道写 `decision=undeclared` + `note`，并把冲突写进 `differences.declaration_conflicts`（§2.2） | 配置自相矛盾时挑一个 = 把"读的是哪条声明"变成猜的（核心约束 3） |

**「有意治理另一棵树」的声明位**（数据侧，`wiring-scope.yaml` 的条目新增两个可选字段）：

| 字段 | 取值 | 语义 |
| --- | --- | --- |
| `governs_tree` | `self` / `other`；**没写 = `unknown`**（2026-10-01 裁定④，见 §8.4） | 这条声明覆盖的通道**有意**治理另一棵树（不是本仓库这棵树）；**没写不替它认领 `self`** |
| `tree_ref` | 指针：仓库相对路径，或 `<outside-workspace>` | **只放指针、不放正文、不放绝对路径**（第 16/34 条）；`governs_tree=self` 时不写 |

> **更正（2026-10-01 裁定④，在 1.3 内改正、不升版）**：`governs_tree` 的原口径是「`self`（默认）」。
> 裁定④ 把**没写**的读法改成 `unknown`——理由：按 §2.1 的边界，「`relation=other` 而
> `tree.declared != other`」**不进五个差集**，于是「默认 `self` + 证据 `other`」这对矛盾会
> **静默存在**；而「拿不出证据写 `unknown`」与裁定③ 是同一条纪律。`unknown` **不是可写取值**
> （写进声明文件会被加载期拒绝），它只是读取侧对「没写」的翻译；`tree.declared_by` 仍写覆盖它的
> 声明 id，所以「没有声明覆盖」与「声明覆盖了但没写」分得开。裁定理由见 **§8.4**，落地与 R-d 见
> **23 号 §16.1**。

通道行的 `tree.relation` 由**通道自己声明的目标**算出：`hooks_config` / `audit_path` /
`bridge.entry` 里出现 `<external>/…`（`wiring.py` 既有的渲染口径，不新造一套）→ `other`；
三个字段都读不到 → `unknown`；其余 → `self`。今天是 **8 个通道** `relation=other`、
**0 条声明**写过 `governs_tree`。

**边界（先写下来）**：`relation=other` 而 `tree.declared != other` **不进差集**——
差集是"声明 × 发现"的闭集（方案 §3.5）；这件事只出现在通道行与 `headline` 的注里。
**要不要给它一格，请评审裁定**（§8）。
> **2026-10-03 补记**：第六格最后给了另一个问题——`expected_absent_present`（声明说这条通道
> 按设计不该在，而它被发现了）。上面这条"树声明与实际不一致"仍然**不进**任何一格，见 **§8.5**。

### 2.2 声明差集（三数 + 六个差集）

**要加的顶层键**：`account` / `differences` / `headline`。

> **一条必须先说的冲突**：方案 §3.5 写"顶层**只允许** `account` / `differences` / `channels` /
> `reading_context` / `headline`"，而今天的载荷有 **13 个键**（`probe` / `counts` / `fact_counts` /
> `failures` / `tools` / `result` / `environment_skipped` / `skip_reason` / `reproduce` /
> `reading_guide` / `wiring_schema_version` …），其中 `result` / `failures` 是 `--check` 的判据、
> `probe` 是"这次探测读了哪些根"的唯一读数——把它们合并成 5 个键是**破坏性重排**，会让门禁第 24 步
> 与契约测试同时改口径。**本稿的读法是**：白名单管的是**覆盖账这一族**的键名与量纲
> （禁 `ratio` / `percent` / `coverage`、禁浮点），既有的报告外壳**一个键都不删**；
> "收敛成 5 个键"如果要，请另开一次显式裁定（§8 第 6 条）。

**`account` 三数**（一律整数）：

| 键 | 定义（口径写死） | 今天 |
| --- | --- | --- |
| `discovered` | 本次探测**真实发现**的通道数 = `len(channels)` | 12 |
| `declared` | 声明文件里**读到的**声明条目数（`provenance.wiring_scope` 的 `scope` 长度） | 7 |
| `measured` | 发现的通道里**两根事实轴都真的评过**的个数（`freshness_status != "unevaluated"`） | 7 |

- **读不到不是 0**：声明文件读不到时 `declared` 写 `null`，并给
  `declared_status: "unavailable"` + reason（第 56 条"账本不存在 = 不适用"的同一条口径）；
  "候选根全不可达而三数全 0"是**反退化**要抓的形态（方案 §4 台阶 4），所以 `0` 与
  `unavailable` 必须分得开；
- **三数不许合并**成一个数或百分比（方案 §B.3 第 1 条）；
- `measured` 另有候选口径"至少接线轴有结论"=12；本稿按**两根轴都评过**（=7），
  因为它才区分得出"量过"与"读不到"（§8 第 1 条请评审确认）。

**`differences` 六个差集**（每格 = `count` 整数 + `items` 列表；列表按 `channel_id` 稳定排序；
每项带 `channel_id` / `declared_by` / `decision` / `wiring_status` / `freshness_status` / `remedy`；
第六格是 **2026-10-03 裁定④** 在 1.3 内补的，口径见 **§8.5**）：

| 键 | 定义 | 今天（**预测**，机制未落地） |
| --- | --- | --- |
| `discovered_not_declared` | 发现到、却没有声明覆盖 | 依赖 `covers` 怎么写——**未核实** |
| `declared_not_discovered` | **通道类**声明里"声明了、本机没发现"的那些——判据是 `kind` 出现在 `channel_kinds` 的**值集**里；非通道声明不进这一格，逐条列在同格的 `excluded_non_channel`（**2026-10-03 裁定③**，WIRING 1.3→1.4） | **1**（`ci-agent-runtime`）；`agent-channel-inventory-report-mode`（`kind=gate_check`）在 `excluded_non_channel` 里，带 id 与 kind |
| `in_scope_not_wired` | 声明 `in_scope`、而通道两根轴不都成立 | **红条件**；候选见 §2.3 |
| `out_of_scope_active` | 声明 `out_of_scope`、而 `wiring_status=wired` | 0（4 条 `out_of_scope` 通道都不 wired） |
| `out_of_scope_expired` | 声明 `out_of_scope` 且 `expires_at` 已过 | 0（今天 2026-10-01；最近一条 2026-10-31） |
| `expected_absent_present` | 声明 `expected_absent`、而这条通道**被发现了**（第六格，2026-10-03 裁定④；1.3 内加、**不升版**） | 0（本机 7 条通道没有一条落在 `expected_absent` 声明下）；probe-ea2 那个场景里是 **1** |

**`headline`**：一句稳定的人读文本 + 一条**机器行**（与 `HITS:` 同型：只加行、不改既有行）：

```text
IN_SCOPE_NOT_WIRED: 0 / discovered=12 declared=7 measured=7
```

### 2.3 `in_scope_not_wired` 这条红条件在**只报告期**怎么表达

方案 §B.3 第 2 条要求它是**红条件**，台阶 4 的"红→绿"也写着它的退出码。**但本轮只报告、
不新增阻断步骤**，所以它的表达分四层，缺一层都会变成"悄悄推迟"：

| 层 | 形态 | 说明 |
| --- | --- | --- |
| ① **看得见** | `differences.in_scope_not_wired.items` 逐条列出（含 `remedy`）；人类输出一行 `IN_SCOPE_NOT_WIRED: <count>` | 机器行是跨文件契约（与 `HITS:` 同一条纪律：只加行、不改既有行） |
| ② **标得明**（本稿的新词） | 顶层 `red_conditions` 块把它写成**显式状态** | `enforced: false` 是**声明出来的**"还没接线"，不是"忘了"；`ToolDriftReport.report_only = true` 是既有同型先例 |

```json
"red_conditions": {
  "in_scope_not_wired": {
    "count": 0,
    "is_red": true,
    "enforced": false,
    "would_exit_code": 1,
    "promote_when": "跑过 N≥1 次且 0 命中（0 命中必须来自至少一次真实读数）——与 L5 上线闸同型",
    "note": "只报告期：本块不改任何退出码；--check 的判据与今天逐字相同"
  }
}
```

| 层 | 形态 | 说明 |
| --- | --- | --- |
| ③ **退出码一个都不动** | 默认形态仍退 **0**；`--check` 仍只按两根轴的合取判（`failures` 非空即 **1**），**不读** `in_scope_not_wired` | 门禁第 24 步跑的是**默认形态**（`.venv/bin/python -m adapters.cli wiring`，报告模式、总是退 0），所以"接不接线"都不改变今天的行为 |
| ④ **升格路径写死** | `enforced: false → true` = 一次**显式提交**：`--check` 判据变更 + `WIRING_SCHEMA_VERSION` 同批再动一格 + 门禁步骤表/CI 的显式改动；且必须先跑满一轮"0 命中来自至少一次真实读数" | **这一步不在本文的落地范围里**（要另走评审 + L5 同型的一轮） |

**为什么不是"等机制建好再说"**：只报告期最容易出的错不是"少了一条检查"，而是**读的人以为
已经有了一条检查**。`enforced: false` 把这件事变成载荷里的一等公民：今天谁问"这条红条件生效了吗"，
答案在字段里，不在人的记忆里。

### 2.4 不许出现的键（量纲纪律）

`account` / `differences` / `headline` 三块里**不许**出现 `ratio` / `percent` / `coverage` /
`rate` 这类键名，计数一律整数、禁浮点（`stale_after_seconds` 这类**既有**的秒数是输入不是比例，
不在此列）；差集的每一项都带得出发它的**那条声明**或**那次发现**（`declared_by` / `channel_id`），
不做"合并成一个数"的渲染。

---

## 3 版本轴与同批改动（第 55 条）

| # | 载荷 | 现版本 | 目标 | 同批要改的引用点 |
| --- | --- | --- | --- | --- |
| 1 | 覆盖账报告（`adapters.cli wiring --json`） | `WIRING_SCHEMA_VERSION = "1.2"` | **1.3** | `tests/contract/test_wiring_inventory.py`（版本断言 + `reading_context` 断言）、`tests/unit/test_wiring.py`、17 号 §2.3、21 号 §2.5、AGENTS 第 55 条那一行的登记 |
| 2 | 边界声明 `adapters/wiring-scope.yaml` | `schema_version: "1"`（`provenance.wiring_scope.SCHEMA_VERSION`） | **"2"** | **同一个提交**：未知字段是加载期报错，加 `channel_kinds` / `covers` / `governs_tree` / `tree_ref` 必须动这个轴 |
| 3 | 豁免到期读数 | `EXEMPTION_REPORT_SCHEMA_VERSION = "1.1"` | **不动** | 它读的是声明文件本身（YAML），键集合不变；到期读数仍是**唯一实现**，`governs.expired` 只是把同一个字段搬进通道行 |

**一次提交还是一批**：本稿按"**一次提交**"设计（`governs` 与差集同属覆盖账；分两次落地会让
"通道有 `governs`、顶层没有 `differences`"成为中间态）。**拆开落地时每拆一次都要再递增一格**
（1.3、1.4 …），并把中间态的读法写出来——"只增不改"不是跳过升版的理由（第 55 条）。

**不是版本轴的同名字段**：`wiring-scope.yaml` 的 `expires_at` / `owner` 是声明内容，
不随载荷版本走；`--check` / `--require-runtime` 是 CLI 开关，不是协议。

> **2026-10-03 补记（第 28 轮 · WIRING 1.3 → 1.4）**：上面那句"拆开落地时每拆一次都要再递增
> 一格"在**裁定③**上兑现了——`declared_not_discovered` 只统计通道类声明、非通道声明进同格的
> `excluded_non_channel`，**同一格的 count / items 换了口径、再多一个键**，所以
> `WIRING_SCHEMA_VERSION` 1.3 → **1.4**（1.3 已随 feat 发布 = `088349a`，不再走"尚未发布、
> 格内改正"那条路；AGENTS 第 55 条）。同批改的引用点：`src/adapters/wiring.py`（常量 +
> 版本史注释）、`tests/contract/test_wiring_inventory.py`（钉死版本号的字面量断言 + 一条新用例）、
> 本文件 §2.2 的那一行。**只报告不变**：`--check` 判据、退出码、`result` / `failures` /
> `counts` / `fact_counts`、两根事实轴、`red_conditions` 与其余五格一个字段都不动
> （R-d 逐条见 **23 号 §18**）。

---

## 4 消费方总表

| 载荷 | 消费方 | 读法 | 加键会不会坏 |
| --- | --- | --- | --- |
| `wiring --json` | `tests/contract/test_wiring_inventory.py`、`tests/unit/test_wiring.py`、`tools/governance_gap_probe.py`、17 号清单的复核者、评审 | 逐键 + 版本断言 | 不会（版本断言要先改） |
| `wiring` 文本输出 | 本机使用者、门禁第 24 步的日志读者 | 人读 + `IN_SCOPE_NOT_WIRED:` 机器行 | 只加行；既有行不动 |
| `wiring-scope.yaml` | `provenance.wiring_scope`（加载期形状校验）、`tools/exemption_expiry.py`（到期）、`governs`（本设计） | 结构化读 | **会**：未知字段是加载期错误 → 必须同批改 `schema_version` |
| `--check` 的退出码 | 使用者、契约测试 | 0 / 1 / 2 | **不变**（`enforced: false`） |

**不新增消费方**：本稿不要求门禁、CI 或 Hook 读 `account` / `differences`；
它们只出现在 `--json` 与文本输出里。

---

## 5 R-d 预注册形状（落地后逐条核对）

| # | 尺子 | 场景 | 预期差集 | 硬约束 |
| --- | --- | --- | --- | --- |
| R1 | 决策载荷（3b 那台，10 个场景） | 全部 | **0 条** | `decision` / `violations` / `pending_findings` / `matched_rules` / `skipped_rules` / `required_action` 一个都不许出现 |
| R2' | VERDICT 判定行（144 行矩阵 + 插件字面量） | 全部 | **0 条**（逐字节相同） | 同上 |
| R5 | 覆盖账 `--json`（**新尺子**：同一 `--now`、同一 `--dsh-home`；before/after 各跑两次取自证） | 三个入口：默认 / `--check` / `--require-runtime` | 每份 **4 + 12** 条：`wiring_schema_version: "1.2" -> "1.3"`、`account: 新增`、`differences: 新增`、`headline: 新增`，以及 **12 个通道各一条** `governs: 新增`（若同批再加 `red_conditions`，就是 5 + 12） | `result` / `failures` / `counts` / `fact_counts` / `channels[].status` / `.wiring_status` / `.freshness_status` / `probe` / `tools` / `reading_context` **一个都不许进差集**；`--check` 的退出码不变 |
| R6 | 声明文件 | `wiring-scope --check` 的读数 | 只多出 `schema_version: "1" -> "2"` 与新增字段；**`by_decision` 分布不变** | 加载期**不新增** FATAL |
| R7 | 门禁第 24 步 | `python -m adapters.cli wiring`（默认形态） | 退出码**三处全 0** | 步骤日志里"ok"不变 |

**仪器**：沿用"跑真 CLI 子进程、采整份 JSON"（`.tmp/step7/probe_check_wrapper.py` 的同型做法）
与 `.tmp/step10/` 的 R3 口径（先自证再判定：同一侧跑两次，差集必须 0 条）。
**before 侧必须在动手之前采集**（第 48 条的同一条纪律）。

---

## 6 预算（口径 = 新增行，`git show --numstat`）

**台阶 4 累计**（23 号 §11.7 的读数覆盖到 `7f8f77a`；本轮第 23 轮的
`declarations.test_layout` 改正 `096cb0d` 已经花掉的也要算进来——"累计"不是"上一轮为止"）：

| 桶 | 到 `7f8f77a` | 本轮 `096cb0d` | 台阶 4 累计 | 复核线（1.5×） | 硬上限（2.5×） | 余量（到复核线） |
| --- | --- | --- | --- | --- | --- | --- |
| src | 681 | **+44**（`pre_evidence.py` 15 + `hooks.py` 24 + `dsh/README.md` 5） | **725** | 1 950 | 3 250 | 1 225 |
| tests | 1 527 | **+85**（两条新用例 + 两处三态断言） | **1 612** | 2 100 | 3 500 | 488 |
| tools | 893 | 0 | 893 | ——（方案 §7 的表里没有这一桶，照旧单列） | —— | —— |
| 数据 / 文档 | 815 | `096cb0d` 0；本轮的三个文档提交（`025465a` / `6718e8f` / `acefa68`）另加 535 | **1 350** | —— | —— | —— |

**口径**：与 23 号 §11.7 的 `budget.py` 同一条——按路径前缀分桶（`src/` / `tests/` / `tools/`，
其余进数据 / 文档），所以 `src/adapters/dsh/README.md` 落 **src** 桶。

**这一件（`governs` 轴 + 声明差集）的估算**（21 号 §8 的覆盖账行：src 60–120、tests 80–150）：
落地后累计 **src ≤ 845**（余量 ≥ 1 105）、**tests ≤ 1 762**（余量 ≥ 338）。**两桶都在复核线之内**；
但 tests 桶已经到复核线的 **77%**——落地时按累计口径重算，超过 1.5 倍就停下复核。

---

## 7 落地顺序（**不新增阻断步骤**）

| 步 | 内容 | 退出码 |
| --- | --- | --- |
| 1 | **数据侧先落**：`wiring-scope.yaml` 加 `channel_kinds` / `covers` / `governs_tree` / `tree_ref` + `schema_version: "2"`——**只有声明、没有机制**，加载期照旧只校验形状 | 不变 |
| 2 | **报告侧**：`channels[].governs` → `account` → `differences` → `red_conditions` → `headline`，一个提交 | 不变 |
| 3 | 两次提交都**不新增阻断步骤、不改任何退出码**；门禁第 24 步仍是报告模式 | 不变 |
| 4 | **升格**（`enforced: true` + `--check` 接红条件 + 门禁步骤）**不在本稿范围**：另走一次评审 + L5 同型的一轮真实读数 | 那时才动 |

**回退**：第 1、2 步各自单独提交、单独回退（数据侧回退不会让报告读不出来——报告侧读不到新字段时
按"未声明"处理，不允许崩）。

---

## 8 未核实 / 请评审裁定

> **2026-10-01 的裁定写在 §8.3**；下面两节是**原问题**，一字不动地留在原处，
> 便于复核"裁定的是不是当初问的那件事"。

**未核实（逐条）**：

1. §2.2 "今天"一列的三数与差集是**预测**，不是读数——机制没落地，`covers` 也还没写；
2. `measured` 的两个候选口径（"两根轴都评过" = 7 与"至少接线轴有结论" = 12）没有实测对比；
3. `relation=other` 的 8 个通道里，哪些是**有意**治理另一棵树、哪些其实该在范围内：
   **没有声明，本文不替评审决定**；
4. 12 个通道的 `covers` 具体怎么写（glob 语法与 `channel_id` 的匹配语义）没有逐条设计；
5. 声明文件升到 `"2"` 之后，旧读法（只读 `scope`）的兼容性**没有实测**；
6. CI 形态（没有 Agent 运行时、`result=skipped`）下 `account` 三数怎么写——`0 / 0 / 0` 与
   "不适用"必须分得开，本稿**未定**（第 56 条的同一条口径）；
7. 本稿的行数与预算估算没有实跑（只写了 21 号 §8 的区间），落地后按 `numstat` 重记。

**请评审裁定（六条）**：

1. `measured` 的口径（§2.2）：两根轴都评过（本稿）还是至少接线轴有结论；
2. `covers` 是否作为声明条目的**显式字段**（本稿），还是只按 `kind` 档 + 通道 id 前缀约定；
3. **同档多条声明冲突**时：只报告（`differences.declaration_conflicts`，本稿）还是**加载期拒绝**
   （后者是新的 FATAL，按 L5 要先有 warn 期）；
4. `relation=other` 而 `tree.declared != other` 要不要**第六格差集**（本稿：不进五个差集，
   只在通道行与 `headline` 注里）；
5. 落地粒度：一次提交（1.2 → 1.3）还是拆两次（每次各自递增）；
6. 方案 §3.5 的"顶层只允许 5 个键"与今天的 13 键怎么处置：① 本稿的读法
   （白名单管覆盖账这一族的**键名与量纲**，既有外壳一个键不删）；② 另开一次**破坏性重排**
   的裁定（改 `--check` 判据、契约测试与门禁第 24 步）。

### 8.3 裁定（2026-10-01 · 使用者授权评审方定夺）

下面五条就是本文件的**裁定**。它们与 §2 的设计在**三处**不同，三处都按裁定改口径、
并在这里登记偏离。

| # | 原问题 | 裁定（逐字口径） | 对本文的偏离 |
| --- | --- | --- | --- |
| ① | §3 表格第 2 行（声明文件的版本轴） | 声明文件 schema **"2"**：加载器**同时接受 "1" 和 "2"**，新字段一律可选；**不许新增任何加载期 FATAL** | §3 只写了 "1 → 2"；补上"兼容 1"与"不新增 FATAL"两条约束。**读法**：FATAL 的口径 = "不得让今天的合法文件变成非法"；对**新字段**的未知枚举取值（如 `governs_tree: othr`）仍按核心约束 3 报错，不静默忽略——请评审确认这条读法 |
| ② | §8 请评审第 6 条（方案 §3.5 的"顶层只允许 5 个键" vs 今天 13 键） | 现有 **13 个顶层键不删不改名**；方案 §3.5 改为"**本台阶只新增 `account` / `differences` / `headline` / `red_conditions` 四个**"，并登记这处偏离 | §2.2 的三键变**四键**：`red_conditions` **是**新增的四个之一（§2.3 的只报告期表达因此一起落地） |
| ③ | §8 未核实第 3 条（§2.1 里 8 个 `<external>` 通道哪些是**有意**治理另一棵树） | **按证据判定**；拿不出证据写 `unknown`；**需要写声明的列成清单交使用者，本轮不替使用者写** | §2.1 把"没有声明"写成 `declared: null`；落地改成 **`unknown`**——`null` 与"读不到"分不开（第 50 条：同名两义一律改名） |
| ④ | §8 未核实第 6 条（CI `skipped` 形态下 `account` 三数怎么写） | **三数写 `unavailable`（带 reason），不许写 0**（与 AGENTS 第 56 条"账本不存在 = 不适用"同一条口径） | §2.2 只写了"声明文件读不到时 `declared` 写 `null`+"；扩到**三个数**与**整个 `differences` 块** |
| ⑤ | §8 请评审第 1 条（`measured` 的两个候选口径） | 只取**已有真实读数支撑**的口径 = §2.2 的"**两根事实轴都真的评过**"（`freshness_status != "unevaluated"`） | 否掉"至少接线轴有结论"那一档：它会把**从未评估过留痕**的通道算成"量过" |

**落地归属**（谁在哪一步做）：

| # | 落地 |
| --- | --- |
| ① | `src/provenance/wiring_scope.py`（`SCHEMA_VERSION = "2"` + 接受集合 `("1", "2")`）与 `adapters/wiring-scope.yaml` 升 "2"，**同一个提交** |
| ② | `src/adapters/wiring.py` 顶层**只加四个键**，既有 13 个一个不动；`--check` 判据与门禁第 24 步退出码逐字不变 |
| ③ | 8 个通道写 `tree.relation = "other"`（证据 = `hooks_config` / `audit_path` / `bridge.entry` 渲染成 `<external>/…`）、`tree.declared = "unknown"`；**待写声明的清单在 23 号 §14.4**（本轮不写声明） |
| ④ | `account` 三数与 `differences` 各格在"没枚举到通道"或"声明读不到"时写 `status: "unavailable"` + `value`/`count: null` + `reason` |
| ⑤ | `account.measured` = `freshness_status != "unevaluated"` 的通道数 |

**同一批的第 0.5 条（先于 ①落地）**：使用者 2026-10-01 授权评审方定夺三条通道的改判
（`dsh-web-channel` / `dsh-headless-channel` / `dsh-verify-dead-channel`）：**三条都保持**
`out_of_scope`，改的是 reason 与到期日（`2026-10-31 → 2026-12-31`，各加一条 `renewals`，
`at=2026-10-01`）。落地在提交 `26bf07b`（**只改** `adapters/wiring-scope.yaml`），
结论同时写进 **17 号 §8.2**。

### 8.4 裁定（2026-10-01 · 使用者授权评审方定夺）：`covers` 数据与「没写 `governs_tree`」的默认值

§8 未核实第 3 条（8 个 `<external>` 通道里哪些是**有意**治理另一棵树）、第 4 条（12 个通道的
`covers` 具体怎么写）与请评审第 4 条（`relation=other` 而 `tree.declared != other` 要不要第六格）
在这一轮由使用者授权评审方定夺。裁定如下——数据落在 `adapters/wiring-scope.yaml`，
**只写声明、不接任何线**（本轮第 2 步；读数见 23 号 §16.2）：

| # | 通道（发现侧） | 裁定（声明侧） | 理由 |
| --- | --- | --- | --- |
| 1 | `dsh:governed` / `dsh:governed-grade` / `dsh:governed-grade-approval` / `dsh:governed-wmsvc` | 由既有声明 `governed-session-hook` 显式覆盖：`covers: ["dsh:governed", "dsh:governed-*"]` + `governs_tree: other` + `tree_ref: .tmp/governance-capability-*` | 这 4 条就是平台的**受控会话**本身（声明已是 `in_scope`），但它们的 `hooks_config` / `audit_path` / `bridge.entry` 三个目标都渲染成 `<external>/…`——**证据说**它们治理的是另一棵树，声明侧现在**承认**这件事，这正是 §2.1 那个声明位存在的理由。`tree_ref` 只放指针（仓库相对，不放正文、不放绝对路径） |
| 2 | `dsh:desktop` | `desktop-entry-points` 加 `covers: ["dsh:desktop"]` | 把「`dsh:desktop` 正对应清单甲第 1 条」从**巧合**变成**连接键**（17 号 §2.2 的注）；既有声明的语义一个字不改 |
| 3 | `dsh:web` / `dsh:headless` / `dsh:verify-dead` | 各自的既有声明各加一条 `covers`（一条通道一条） | 同上：§14.2⑤ 的可见性缺口正是「改判了却看不见」——显式 `covers` 让每条通道都能读到自己**被哪条声明覆盖**，而不是靠 kind 档去猜 |
| 4 | `dsh:verify-bc` / `dsh:verify-exit2` / `dsh:verify-gov` / `dsh:verify-manual` | **新增**一条声明 `dsh-verify-profiles`（`out_of_scope`、`kind=agent_runtime`、`owner=host`、四条 `covers`、`expires_at=2026-12-31`、`renewals=[]`），reason 写「早先治理能力验证轮留下的测试 profile，与 `dsh-verify-dead-channel` 同组；使用者删除 profile 时须同批删除本声明」 | 这 4 条与 `dsh:verify-dead` 是**同一批**测试 profile，今天没有任何声明；而 §2.1 规则 3（同档冲突不挑一个）会把 12 条通道**全部**写成 `undeclared`。新增声明是**收缩承诺面**的动作（方案 §3.6 的判据）：不是接线，只是把「没人声明过」变成「声明过、且带到期日」 |
| 5 | （口径）「写了 `covers` 但没写 `governs_tree`」的默认值 | **`unknown`**（不是 `self`）；**在 1.3 内改正、不升版**（23 号 §15.1 裁定④） | §2.1 的字段表把默认值写成 `self`——那是一个**没人写过的声明值**；而按 §2.1 的边界，「`relation=other` 而 `tree.declared != other`」**不进五个差集**，于是「默认 `self` + 证据 `other`」这对矛盾会**静默**存在。默认 `unknown` 与裁定③（拿不出证据写 `unknown`）是同一条纪律；`tree.declared_by` 仍写覆盖它的声明 id，因此「没有声明覆盖」与「声明覆盖了但没写 `governs_tree`」仍然**分得开** |

**第 0.5 条的可见性缺口（§14.2⑤）因此闭合**：三条改判过的通道（`dsh:web` / `dsh:headless` /
`dsh:verify-dead`）现在各自有显式 `covers`，它们出现在 `governs.declared_by` 里——
「改判了却看不见」不再是缺口，**同一个载荷**里就能读到。

**不改变的东西**（同一条纪律，逐条写下来）：`--check` 的判据与退出码、`result` / `failures` /
`counts` / `fact_counts`、`channels[].status` / `wiring_status` / `freshness_status`、决策载荷与
`VERDICT` 判定行——**一个字段都不动**。`out_of_scope_active` 这类读数**按真实结果报告**，
不为归零改判（本轮的真实读数见 23 号 §16.2）。

### 8.5 裁定（2026-10-03 · 评审方二次更正）：实验 profile 的收尾、第六格与 `reason` 文案

§8.4 第 4 条（新增 `dsh-verify-profiles`，把 `verify-bc` / `verify-exit2` / `verify-gov` /
`verify-manual` 收进一条测试 profile 声明）与 §8 请评审第 4 条（`relation=other` 而
`tree.declared != other` 要不要第六格）在这一天被**二次更正**。逐条裁定与落地（读数见 23 号 §17）：

| # | 原问题 | 裁定（逐字口径） | 落地 |
| --- | --- | --- | --- |
| ① | §8.4 第 4 条 + 第 26 轮把三条并入 `governed-session-hook` | `verify-bc` / `verify-dead` / `verify-exit2` / `verify-gov` / `verify-manual` 是**治理能力验证轮的实验 profile**，**不是受控会话**（04 号 §5.2 的 E7-failclosed；05 号的清理建议「只有 governed 是交付物」；仓库代码里零引用）。第 26 轮那次并入是**评审方的错误**；round-20 的 `out_of_scope_active=3` 是**真实读数** | `f6cc503`：`governed-session-hook.covers` 撤回三条（**decision 一个都没改**） |
| ② | §8.4 第 4 条新增的那两条声明 | 使用者已把这 5 个 profile 移到 `C:\Users\ZNM\.dsh-profiles-backup-20261003`（可还原，没有删除）；**声明随宿主同批收尾**：删除 `dsh-verify-profiles` 与 `dsh-verify-dead-channel` | 同上 |
| ③ | §2.1 里这一格的 `reason` 口径 | `declared_not_discovered` 的 `reason` 要按**真实成因**分开写：kind 没映射 / kind 有映射且本机有同类通道（被别人的显式 covers 领走了）/ 有映射但一条都没有 | `d930af8` |
| ④ | §8 请评审第 4 条（第六格给谁） | 第六格给 **`expected_absent_present`**（声明 `expected_absent`、**却**被发现的通道），**不是**给"树声明与证据不一致"；只报告：`is_red=count>0`、`enforced=false`、`would_exit_code=1`；**1.3 内加、不升版** | `d2d90fa`（§2.2 的字段表已同步） |
| ⑤ | 25 号 §7 的 R-h 方案 A | 挪到**第二十三轮**（feat 合入之后） | 本轮不做 |

**"树声明与证据不一致"（`relation=other` 而 `tree.declared != other`）仍然不进任何一格**——
它在通道行与 `headline` 的注里可见（§2.1 的边界不动）；第六格被另一个问题拿走了，这件事本身
写在 §2.1 的 2026-10-03 补记里，免得下次有人按"第六格"去读它。

**不改变的东西**（同一条纪律）：`--check` 的判据与退出码、`result` / `failures` / `counts` /
`fact_counts`、`channels[].status` / `wiring_status` / `freshness_status`、决策载荷与
`VERDICT` 判定行——**一个字段都不动**；`WIRING_SCHEMA_VERSION` 仍 `1.3`。

---

## 9 复现命令（只读）

```powershell
# §1.2 第 1、2 行：覆盖账载荷（13 个顶层键、12 个通道的两根轴、8 个 <external> 目标）
.venv\Scripts\python.exe .tmp\step10\probe_wiring_now.py

# §1.2 第 3 行：声明文件的整数与决策分布（需要 PYTHONPATH=src）
.venv\Scripts\python.exe -m provenance.cli wiring-scope --check

# 到期读数（只报告：唯一实现）
.venv\Scripts\python.exe tools\exemption_expiry.py

# 门禁第 24 步跑的那一条（报告模式、总是退 0）
.venv\Scripts\python.exe -m adapters.cli wiring
```

---

**本文件是第 23 轮的第三个提交**（前两个：`096cb0d` 的 `declarations.test_layout` 改正与
`025465a` 的 23 号 §12）；索引见同目录 `README.md`。

**2026-10-01 第 25 轮补记**：本文件新增 §8.4（`covers` 数据与「没写 `governs_tree`」默认值的裁定）。
