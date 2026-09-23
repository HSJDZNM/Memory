# R2 交叉评审：界面布局与红队约束（内核与板块分析师）

> 会议：《平台操作系统（Platform OS）总体设计》第 2 轮 · 共享任务 task-6。
> 评审对象：`r1-layouts.md`（ui-architect，task-3）、`r1-constraints.md`（red-team，task-4）。
> 本文件唯一写入；`r1-modules.md` 已冻结，本节对它的修正只写在 §5「我承认被推翻的地方」，不改原文。
> 标注：【复核实测】= 本轮我亲自跑过并贴输出；【复核读码】= 我亲自读了源码/数据并给 `file:line`；【同意/反对/要求收敛】为判定。

## 0. 复核方法与边界

本轮我独立跑的探针（全部只读；未改任何源码、数据、他人文档）：

```powershell
$env:PYTHONPATH = 'src'
# 1) 能力码分层
Select-String -Path src/**/*.py -Pattern 'capability_unavailable'
Select-String -Path src/policy_api/*.py -Pattern 'EVIDENCE_UNAVAILABLE|POLICY_UNAVAILABLE|QUERY_INVALID|TARGET_INVALID'
# 2) 工具选择与 pre-check（dry_run，未执行任何写入）
python -c "from orchestration.nodes import Change; print(Change(path='policies/coding/REVIEW-999.yaml', content='x').tool_id)"
python -m enforcement.cli precheck --request .tmp/red-team/req-fs-write.json    --workspace .tmp/red-team/ws --json
python -m enforcement.cli precheck --request .tmp/red-team/req-policy-edit.json --workspace .tmp/red-team/ws --json
# 3) 规则集与原型
python -m policy.check --check-rules
Select-String -Path docs/project/engineering-policy-platform/designs/console -Recurse -Pattern 'innerHTML|insertAdjacentHTML|outerHTML|document.write'
```

**无副作用声明**：两次 `precheck` 均为 `dry_run=true`，未产生写入——跑完前后 `.tmp/red-team/` 下最新文件时间戳仍是 `20:36`，而我运行时刻是 `20:44`【复核实测】。它们的 `audit: sequence=399/400` 是"审计可写性检查"读数，不是新记录。

## 1. 引用抽查（8 处，含 Lead 点名的 3 条）

| # | 被抽查的断言 | 出处 | 我的复核 | 结论 |
| --- | --- | --- | --- | --- |
| P1 | `capability_unavailable` 在 `policy_api` **0 个抛出点** | layouts V24、§9 风险 3 | 【复核读码】全 `src` grep：**7 处全部在 `src/adapters/`**（`runtime.py:88` 文案、`:728` 真实抛出、`:1284`、`:1289`、`conformance.py:565`、`:624-625`）；`src/policy_api` **0 命中** | **成立**，且与 V24 列出的行号逐个一致 |
| P2 | 原型在**浏览器内**算 `severity → 决策` | X6、A1 | 【复核读码】`console/assets/app.js:170-200` 是纯客户端 `validate()`；`:198` 即 `severity==='error'||'critical' ? 'block' : 'allow_with_warnings'` | **成立，且比原描述更重**：它还自己判 checker 覆盖（`:177-178`）、规则体必填（`:180-182`）、未知字段（`:184-186`）、codes 大写（`:187-194`） |
| P3 | pre-check **放行** `orc.fs.write` 写 `policies/` | X1/X2/A2 | 【复核实测】`Change(path='policies/coding/REVIEW-999.yaml', content='x').tool_id` → `orc.fs.write`；`precheck` 用真实注册表 → **EXIT=0、`decision=allow`**，`approval=skipped/allow（"该工具不需要人工审批"）`，registry/action_window/principal/permissions/rate_limit/circuit_breaker/ledger/audit 全 `passed` 或 `skipped` | **成立** |
| P4 | 对照组：`orc.policy.edit` 必须被挡 | A2 对照 | 【复核实测】同环境 → **EXIT=1、`decision=block`**、`approval=failed/approval_required`（"该动作需要人工审批，但没有提供与当前 action_hash 绑定的审批记录"） | **成立**（同一注册表、同一工作区，唯一变量是工具） |
| P5 | 决策字面量扫描"4 命中" | C1 | 【复核读码】真命中 3 处：`build_site.py:456`、其生成的 `authoring.html:30`、`app.js:198`；第 4 处 `app.js:32` 确为 `box.style.display = 'block'` 的 CSS 误报 | **成立**，数字与归类都准确 |
| P6 | 引用漂移约 70 行 | X16、A13 | 【复核读码】`docs/project/architecture/功能清单.md:251-258` 是 `tools/` 脚本表；LLM/MCP/向量库在 `:323`、审计链边界在 `:324`、审批无签名在 `:326` | **成立** |
| P7 | `evidence_unavailable` 在 API 面不可达 | layouts §7、U6 | 【复核读码】`src/policy_api` 下该码只有 2 处：`errors.py:59`（枚举）+ `:97`（状态映射），**无 `raise`**；同类还有 `policy_unavailable`（`:64/:101`）、`query_invalid`（`:39/:80`）、`target_invalid`（`:40/:81`），各恰好 2 处 | **成立并可量化**：至少 **4 个码今天 0 抛出点** |
| P8 | 检索对**两个租户**都不可用 | layouts V8 | 【复核读码】`api/policy-api.yaml:47-78`：`local-dev` 的 `retrieval` 段被整段注释（`:58-64`），`fixture-shop` **没有** `retrieval` 段 | **成立（读码级）**；我未发真实 HTTP 请求，等级低于 layouts 的【实测】但结论一致 |

### 1.1 复核输出摘录（原文片段，未改写）

**P3/P4 的正反例（同一注册表、同一工作区、唯一变量是工具）**：

```text
# A) tool_id 选择（真实 Change 模型，非手写 JSON）
$ python -c "from orchestration.nodes import Change; print(Change(path='policies/coding/REVIEW-999.yaml', content='x').tool_id)"
tool_id= orc.fs.write

# B) orc.fs.write → policies/coding/NEW-001.yaml
"approval": { "check": "approval", "status": "skipped", "reason_code": "allow",
              "detail": "该工具不需要人工审批" }
"pre": { "decision": "allow", "required_action": null, "reason_code": "allow", "dry_run": true }
EXIT=0

# C) orc.policy.edit → policies/coding/DOC-001.yaml（对照组）
"approval": { "check": "approval", "status": "failed", "reason_code": "approval_required",
              "detail": "该动作需要人工审批，但没有提供与当前 action_hash 绑定的审批记录" }
"pre": { "decision": "block", "required_action": "approval", "reason_code": "approval_required" }
EXIT=1
```

**同一份输出里还有一条必须写进终稿的事实**：A 组的 `policy` 检查项是
`status=skipped / reason_code=allow / detail="请求没有声明 policy_context：该动作没有文件维度，Phase 1 规则引擎不适用（显式跳过）"`。
也就是说：同一个 `skipped` 在 `approval` 项里等于"没有门禁"，在 `policy` 项里等于"规则不适用"——**接口面必须靠 `reason_code` 区分，不能靠 `status`**（这正是我在 §5 第 3 条承认的简化错误）。

**P1 的分布（全 `src` 7 处，逐行）**：

```text
src/adapters/runtime.py:88      "capability_unavailable": "该 Agent 不具备强制阻断能力，无法治理此类动作"
src/adapters/runtime.py:728     code="capability_unavailable",          <- 唯一真实抛出点
src/adapters/runtime.py:1284    "capability_unavailable",
src/adapters/runtime.py:1289    "capability_unavailable",
src/adapters/conformance.py:565 capability_limited = first.outcome_code == "capability_unavailable"
src/adapters/conformance.py:624 first.response.reason_code == "capability_unavailable",
src/adapters/conformance.py:625 "只读上限必须明确报告 capability_unavailable",
src/policy_api/**               0 命中
```

**P2 的原始代码（客户端判定，逐行抄）**：`app.js:198` 一行完整表达式为
`severity=' + payload.severity + ' → ' + ((payload.severity === 'error' || payload.severity === 'critical') ? 'block' : 'allow_with_warnings')`，
它旁边的 `:177-194` 还在客户端判"checker 有无验证器供证、规则体必填字段、未知字段、codes 是否大写"。

**一致但未被点名的两处交叉验证**：layouts V9 的 `documents=27 chunks=535 generation=2` 与我 R1 实测逐字相同；layouts V13 的 9 个工具与我 R1 的 `registry --list` 输出相同。两份独立测量一致，可信度上升。

## 2. 逐条判定

### 2.1 对 `r1-layouts.md`

| 条目 | 判定 | 理由 |
| --- | --- | --- |
| V20 + U8（哈希/计数是活数据，必须带取数时刻） | **同意（最强的一条）** | 我复跑时规则集已是 **`rules: 44`**（`sha256:a90e64ac…`），既不是 layouts 的 45 也不是我 R1 的 26；双方的数字都在漂移，只有"带时刻"这条纪律站得住 |
| V24 + U6 + §9 风险 3 | **同意** | §1 P1/P7 独立复现；"跨层公共词汇 ≠ 可用错误码"这个提法准确 |
| V2/V3（health 免令牌；进程内 `handle` 要令牌） | **同意前半，后半未复核** | `app.py:295-320` 的两个 GET 是直连函数、不经过认证路径【复核读码】；"进程内 `runtime.handle` 要令牌"我只读到 `handle_route` 的存在，未构造调用 → **要求补一条实测或降级标注** |
| V8（检索 503） | **同意** | §1 P8 |
| V22（原型烘死哈希与「6 规则」KPI） | **同意** | `sha256:ed331a8d…` 实测出现在 `index.html:23`、`activation.html:23`、`assets/data.js:5778`（3 处，比 V22 说的 2 处多一处生成物） |
| V23（a11y 全 0） | **同意** | grep `tabindex / aria- / noscript / <form` 在 `console/` 下 **0 命中**【复核实测】 |
| §1 页面树用六层名当"板块" | **要求收敛（见 §3 矛盾 2）** | 层是架构分层，板块是权力边界；页面可以借层名，但"板块"一词会与 F2/口径 §1 撞车 |
| §5 既有 6 页的处置（authoring 整页【提案】、activation 废弃、system 拆分） | **同意** | 处置依据（N2/N4/F8）成立；尤其"静态清单不得冒充实测探针"与我的板块划分同源 |
| §8 无 JS 降级页 | **同意，要求补一条** | 降级页必须同样带"取数时刻 + 命令 + 退出码"，否则它就是 V22 那种过期快照的合法版本 |
| §7 对照表 13 行 | **同意，要求扩展到 4 个码** | 它只为 `evidence_unavailable` 写了"无文案"；同类的 `policy_unavailable` / `query_invalid` / `target_invalid` 也要同样处理（§1 P7） |

### 2.2 对 `r1-constraints.md`

| 条目 | 判定 | 理由 |
| --- | --- | --- |
| C1、C3、C9、C12、A1、A2、A13、A14 | **同意** | A2 我逐字复现（§1 P3/P4）；A1 的源码证据比结论更强（§1 P2） |
| A3（`orc.fs.write` 可无审批改写信任根数据） | **同意结论，反对分级** | 结论与 `path_scope: workspace` 一致；但"改写注册表会让所有工具立即未审核（自伤式 DoS）"我**未实测**，文档也没标级 → 要求标【推断】或补一次 `registry --verify` 前后对照 |
| C5 + V4（504/503/429 → "没有结论"，不存在通往"继续"的转移） | **反对措辞，同意意图** | `rule_set_unavailable` 是 `retryable=True`，"重试"与"继续"是两种转移；V4 若原样落成断言，实现方会不知道"重试按钮"算不算违规 → 要求像 layouts §7 那样显式区分"重试（换一次调用）"与"继续（带着未判定的状态往下走）" |
| V1/V2（`tool_id` 与 pre-check 退出口径） | **同意** | 我复现：`tool_id=orc.fs.write`、precheck 退 0；对照退 1 |
| V16（`innerHTML` 扫描进 `ci_local.py`） | **要求收敛** | `console/` 今天 **untracked**（F26）；把门禁指向未跟踪目录，会在它被删除后让 CI 永久红 → 门禁必须写成"路径存在才检查"，或等它入库后再加 |
| V20（引用漂移门禁） | **同意但需限定范围** | 全库 `path:line` 断言成本高；建议先只覆盖 `designs/os/meeting/**`（本会议产出），别一次覆盖 `docs/` 全量 |
| X15 与 layouts V24 并列 | **要求收敛（容易误读）** | 两条都对，但一个说"adapters 里有抛出点"、一个说"policy_api 里没有"，读者会读成冲突 → 终稿必须写成"按层归属"的表 |
| §0 证据产物 `.tmp/red-team/*.json` | **要求收敛** | 实测首字节：`out-a2.json` 与 `out-b2.json` = `255,254`（**UTF-16LE**），`one.json` 与 `one-real.json` = `239,187,191`（**UTF-8 带 BOM**），`req-multi.jsonl` / `audit-r.jsonl` 才是纯 UTF-8；前四个用 UTF-8 工具读会判为 binary 或带 BOM。本仓库文本规范是 UTF-8，证据产物应统一编码，否则"可复核"要附带编码说明 |

## 3. 与本提案 `r1-modules.md` 的矛盾（6 条，逐条判谁对）

| # | 矛盾 | 谁对 | 以什么为准 |
| --- | --- | --- | --- |
| 1 | 我在 §5 S6 把 `evidence_unavailable` / `policy_unavailable` 列为 API 的失败关闭状态；layouts §7 说 API 面不可达 | **layouts 对** | `src/policy_api/errors.py:59/:97`、`:64/:101` + 全包 grep 0 抛出点【复核读码】。终稿接口面必须加"今天有无抛出点"列 |
| 2 | 我用"层级"当被否决的板块拆分（V1）；layouts 直接用六层名当"板块 → 页面 → 标签页" | **我对，但要让一半** | 口径表 §1 冻结的是**分层**，而 Policy API 是 ②+④ 跨层、dsh 是 ①+② 跨层——把层当板块必然产生"一个东西两个板块"。以"层=架构分层、板块=权力边界、页面=导航分组"为准；layouts 的页面树本身成立，只需改称"导航分组" |
| 3 | 我 §5 S3 只写"任一 `FAILED` 即 block"；red-team C3/A2 强调 `approval` 的 `skipped/allow` 就是 B1 的签名 | **red-team 对，我不完整** | 我的复核输出：`"check":"approval","status":"skipped","reason_code":"allow","detail":"该工具不需要人工审批"`。同一个 `skipped` 既表示"不适用"（命令类检查对文件工具），也表示"该工具没声明门禁"——二者在接口面必须可分 |
| 4 | 我 §1 S1 写死 `rules: 26`；layouts V20 说它是活数据 | **layouts 对** | 复跑是 44【复核实测】。以"命令 + 取数时刻"为准，绝对值不进正文 |
| 5 | 我 §5 S6 只列 6 条路由，隐含"三个业务路由可用"；layouts V8 说 `retrieve` 对两租户 503 | **layouts 对，我漏了** | `api/policy-api.yaml:47-78` 两个租户都没有生效的 `retrieval` 配置【复核读码】。"路由存在 ≠ 能力可用" |
| 6 | 隐喻失败清单：我的 M7 谈"包与安装无依赖求解/无签名"；red-team 的 M1 谈"per-rule 启停 vs 整批原子替换" | **red-team 更锋利** | 我的 M7 是弱读法（没人真会去设计 SAT 求解）；red-team M1 直指最自然的错误界面控件（"启用/停用这条规则"），且 `services.py:80-94` 空集拒绝替换就是它的反证。采纳 red-team，我的 M7 降为附注 |

## 4. 对终稿的可执行修改建议

### 4.1 对 `01-板块拆分`

1. 总览表新增一列 **「今天可达性」**，取值只有三种写法：`可用` / `存在但今天产不出（0 抛出点）` / `不存在（【提案】）`；每格附一条复核命令或 `file:line`。
2. S1 行的规则规模一律写成 **「取数时刻 + 命令 + 值」**，例如：`2026-09-22 20:44 +08:00 · python -m policy.check --check-rules · rules: 44（sha256:a90e64ac…）`；**禁止**只写 `rules: 26` 这类裸数字。
3. S6 行补一句：**「6 条路由里 `/v1/knowledge/retrieve` 今天对 `local-dev` 与 `fixture-shop` 都返回 503 `knowledge_unavailable`（两租户均未配置检索），能力可用性不得由路由表推出。」**
4. 新增一小节 **「词汇表的层归属」**：一行 `capability_unavailable` → 只在 `src/adapters/`（拒绝语义，Phase 6）；一行 `evidence_unavailable` → 声明在 `src/policy_api/errors.py:59` 但今天 0 抛出点；并写明"同名不等于同层"。
5. §1 表格标题与正文把"板块"与"导航分组"分开：**「导航可以借层名，板块必须按权力边界切」**。

### 4.2 对 `02-操作流程`

1. 流程里每个"提交/生效"节点必须写成一句可断言的判据：**「pre-check 的 `approval` 项必须 `status=passed`；`skipped` 与 `failed` 都不等于通过」**，并附本文件 §1 P3/P4 的两条实测输出作为正反例。
2. 增加一个 **「B1 未修时的代理流程」** 分支（在修复前唯一诚实的画法）：**「新建规则文件当前落到 `orc.fs.write`（`approval: none`），因此本流程在此步显示『无人工门禁』，不得显示为『已审批』」**。依据 `src/orchestration/nodes.py:94-97` + `registry/tool-registry.yaml:293-315`。
3. 失败语义表加一行：**「pre-check 的 `skipped`：是『本项不适用』还是『该工具未声明门禁』必须由 `reason_code` 区分，界面不得把 `skipped` 渲染成通过」**。
4. 所有流程截图/线框里的哈希与计数一律加"取数时刻"角标（与 03 的 U8 同规则）。

### 4.3 对 `03-页面布局`

1. P4「规则」标签保留"工作树 / git 跟踪"两列，并把两列都加上取数时刻（我复跑：工作树 44、跟踪 6）。
2. P3「检索」标签的 503 文案补上根因：**「两个租户都未配置 `retrieval`（`api/policy-api.yaml:58-64` 被注释、`fixture-shop` 无该段），因此这不是索引坏了（索引 27 文档 / 535 chunk 正常）」**。
3. P6 增加一行差异说明：**「`/v1/health/*` 走 HTTP 面免令牌，而进程内 `handle` 路径要令牌——界面自检与浏览器结论可能不同，必须标注用的是哪条路径」**（依据 `src/policy_api/app.py:295-320`）。
4. §7 对照表把"无文案"从 1 个码扩展到 **4 个码**（`evidence_unavailable` / `policy_unavailable` / `query_invalid` / `target_invalid`），并统一写"不为它写 UI 分支"。
5. §8 无 JS 降级页增加一句硬要求：**「降级页每张表下方必须写『静态快照 · 取数时刻 T · 命令 C · 退出码 N』，缺任一项即视为过期页面」**。

## 5. 我承认自己 R1 文档里被推翻的地方

1. **§5 S6 的错误码可达性**：我把 `evidence_unavailable` / `policy_unavailable` 列进 API 的 503 失败状态，实际它们各只有"枚举 + 状态映射"两处、**0 抛出点**（§1 P7）。layouts §7 的"不为它写专门 UI"是对的。我的接口面缺"可达性"这一维。
2. **§1 S1 的 `rules: 26`**：这是我当时的实测，但写法错了——把它当事实写在表里；到本轮复跑时同一命令返回 44（`sha256:a90e64ac…`），layouts V20 还记录了同期 26 → 39 → 45 的三次跳变。layouts V20/U8 的"任何哈希/计数必须带取数时刻"推翻了这种写法。
3. **§5 S3 的失败面**：我写"任一 `FAILED` 即 block"是对的，但不完整——**B1 的签名恰恰是一个 `skipped`**（`approval: skipped/allow`）。把 `skipped` 一律读成"不适用"会漏掉最危险的那类放行。red-team C3/A2 与我的复核输出推翻了我的简化。
4. **§6 V1 的措辞过宽**：我否决的是"把六层当板块/权力边界"，却写成了"按六层拆成 6 个板块"，读起来像在否决 layouts 的导航分层。**layouts 的页面 IA 站得住**，我用词不准。
5. **§2 隐喻表的 M7**：我选了"包与安装"这个弱读法，漏掉 red-team M1 的强读法（"启用/停用单条规则"）。后者才是界面最可能长出来的错误控件，采纳 red-team。
6. **§7 Q1 问错了方向**：我问"工作树还是受跟踪，哪个是当前规则集"，预设了存在一个权威快照。V20 证明真正要定的是**展示纪律**：任何规则集数字必须带取数时刻与命令，而不是先裁决一个"当前值"。

## 6. 未复核 / 存疑（诚实标注）

- layouts V3 后半句（进程内 `handle` 要令牌）：未构造调用，仅读码到 `app.py:295-320` 的直连函数【未知，需核验】。
- red-team A3 的"自伤式 DoS"：未实测改写后的 `registry --verify` 状态。
- 我未跑全量 `pytest`、未构造 504、未做浏览器 DOM 实验——凡这类结论我都沿用对方的实测或标注未核验。
- red-team 的证据产物编码不统一：`out-a2.json` / `out-b2.json` 是 UTF-16LE（首字节 `255,254`），我的 UTF-8 读取工具直接判为 binary，需 `Get-Content -Encoding Unicode` 才可读；`one.json` / `one-real.json` 是 UTF-8 带 BOM。**建议后续证据产物统一为无 BOM 的 UTF-8**，否则"可复核"要附带编码说明。
- 本文件未修改任何源码、数据、`AGENTS.md`、既有 `designs` 文档或他人 R1 文件。
