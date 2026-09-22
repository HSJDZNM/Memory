# R2 交叉评审（操作流程分析师 · task-8）

> 评审对象：[`r1-modules.md`](r1-modules.md)（264 行，S1–S9）与 [`r1-constraints.md`](r1-constraints.md)（401 行，C1–C15 / A1–A14 / V1–V22）。
> 方法：**先自己跑、再读文档**；本轮只写本文件。引用一律给 `file:line` 或实测输出。
> 标记：【实测】= 本作者真跑过并贴退出码/输出；【读码】= 读了源码；【采信】= 引用对方证据但本轮未独立复核；【未知，需核验】。
> 环境：Windows + `pwsh`、Python 3.13.11、`$env:PYTHONPATH="src"`；**实测时刻 2026-09-22 20:33–20:52（+08:00）**。
>
> **⚠️ 评审期间工作区仍在变，这直接影响本次评审的结论**：规则集 26 → **44** 条（20:43，`sha256:a90e64ac…`）；
> 语料条目 27 → **42**（`retrieval.cli verify` → `datasets=6 entries=42`）；`rule_sources` 0 → **39** 条；
> `AGENTS.md` 在评审期间被改成"44 条规则 + 第 40 条约束"。因此对方文档里"今天"的实测值是**瞬时快照**：
> 例如 `r1-constraints.md:307` 的"六门禁全绿"与 `r1-modules.md:192` 的"phase_evidence 本轮未跑"现在都已不成立。
> 本评审对每条断言区分**当时为真 / 现在为真 / 现在为假**。

## 0. 结论速览

1. 两份文档的**事实骨架我复核后成立**：B1（新建规则文件绕过审批）、原型在浏览器里算判定、"门禁绿不等于规则集未变"三条我都能独立复现或读码确认（§1）。
2. 两份文档都缺一条**运维事实**：门禁的绿与规则集身份无关；而它在会议期间已经**由绿转红**（`phase_evidence` exit 1 / 9 个失败，`orchestration_loop` exit 1 / 3 个场景失败）——见 §1.3 与 §3 冲突 4。
3. 逐条裁定：**C1–C15 方向全部同意**（其中 C5 / C8 / C10 / C13 / C15 要求收窄措辞）；**A1–A14 同意 10 条、收窄 3 条、补强 1 条**；**V1–V22 同意 15 条、改口径 4 条、标"今天不可验收"3 条**（§2）。
4. 与我的 [`r1-flows.md`](r1-flows.md) 有 **5 处冲突**（§3），其中两处请 Lead 裁决：**审批发生在哪一步**、以及**"提交节点"的判据到底是哪一个字段**。
5. Lead 指定的写死条款我给出可直接进终稿的判据与正反例实测输出（§4）：**`pre.checks[check=="approval"].status` 必须是 `passed`；`skipped` 与 `failed` 都不等于通过**。

## 1. 引用抽查（全部本轮亲自复核）

### 1.1 B1：precheck 对 `orc.fs.write` 放行（对方 `r1-constraints.md:15-18` X1–X4、`:155-167` A2、`:288` V2）

| 我跑的命令 | 输出 | 结论 |
| --- | --- | --- |
| `python -c "from orchestration.nodes import Change; print(Change(path='policies/coding/NEW-001.yaml', content='x').tool_id)"` | `tool_id = orc.fs.write` | X1 **成立** |
| `python -m enforcement.cli precheck --request .tmp/r1-flows/req-orc-write.json --workspace .tmp/r1-flows/ws` | **exit 0**，`pre-decision: allow`；`[skipped] approval allow 该工具不需要人工审批`；registry/action_window/principal/permissions/rate_limit/circuit_breaker/ledger/audit 全 passed | X2、A2、V2 **成立** |
| 同上换成 `orc.policy.edit`（同 target、同主体） | **exit 1**，`pre-decision: block (approval_required)`；`[failed ] approval approval_required…` | X3 **成立**，且证明差异来自**工具选择**而非路径 |

**要求收敛一句**：`orc.fs.write` 仍是 `path_scope: workspace`（`registry/tool-registry.yaml:310`）；它放行的不是"任意路径"，而是"**受控工作区内的任意路径**"。
终稿若要写"整个工作区"，必须同时写清"工作区可能是仓库根"（我方实测 `--workspace .tmp/r1-flows/ws`，A3 用的是真实仓库根）。

### 1.2 原型在浏览器内算判定（对方 `r1-constraints.md:20` X6、`:145-152` A1、`:42-49` C1）

【读码】`designs/console/assets/app.js:170-199`：`validate()` 产出 `checker_covered` / `rule_body_incomplete` / `unknown_checker` / `severity_unknown`，并在
`:198` 直接写 `severity=... → block | allow_with_warnings`；`:340` 写死文案 `加载成功：N 条规则通过`；`:365` 点"预演"后写 `预演通过`，**全程没有网络请求**。
**补充（比 X9 更严重一档）**：`:365` 的"预演通过"连"浏览器内模拟"的标注都没有；F30 的约定只落在 `?` 提示里。

### 1.3 门禁绿 ≠ 规则集未变（对方 `r1-constraints.md:19` X5、`:307` V21；对照 `r0-facts.md` F13）

- CI 的规则集步骤就是 `python -m policy.check --check-rules`（`.github/workflows/phase-8.yml:50`）；`tools/ci_local.py:55` 的 "Rule set self-check" 同类。
- **任意可加载规则集都退 0**：我在 26 条（`sha256:a6c9655a…`，20:33）与 44 条（`sha256:a90e64ac…`，20:43）两个状态各跑一次，均 **exit 0**【实测】。
- 全仓**没有一步**把 `rule_set_hash` 钉在记录值上：grep `rule_set_hash|RuleSet.identity` 的命中都在 tools / learning 生成器的**输出**里，不是断言；最接近的是 `tools/check_arch_canon.py:31` 的 `NUMBERS = ["44","535","1109","1111"]`，它钉的是**文档数字**（其中 44 是 CI 步数，不是规则条数）。
- 反方向也有证据：规则 26 → 44 后 `tests/integration/test_cli.py::test_json_output_matches_policy_decision_contract` **红了**（`At index 2 diff: 'DOC-002@1' != 'STYLE-001@1'`、`Left contains 38 more items`），因为它硬编码了 6 条规则的期望。

**裁定：同意，但终稿必须写成不对称的两句**——
①"门禁全绿**不证明**规则集未变"（没有任何一步钉哈希）；
②"规则集变化**也不保证**门禁会红"（只有命中固定夹具的那部分规则才会让快照/契约测试变红）。
只写 ① 会被读成"改了规则门禁一定红"，那只在今天这条硬编码测试上偶然成立。

### 1.4 附加抽查：审批的三态（我方 R1 §E 实测，作为 §4 正反例来源）

| 态 | 实测输出 | 退出码 |
| --- | --- | --- |
| `passed` | `[passed ] approval allow approval_id=approval-e776d1ff39f9 granted_by=alice` | 0 |
| `skipped` | `[skipped] approval allow 该工具不需要人工审批`（`orc.fs.write`） | 0 |
| `failed` | `[failed ] approval approval_required 该动作需要人工审批，但没有提供与当前 action_hash 绑定的审批记录` | 1 |
| `failed`（同族） | `[failed ] approval approval_invalid 审批已过期（2026-09-22T12:41:03.126211Z）`——同一审批约 10 分钟后复用 | 1 |

JSON 字段路径实测（`precheck --json`）：`pre.decision`、`pre.checks[] = {check, status, reason_code, detail}`；
approval 条目形如 `{"check":"approval","status":"passed","reason_code":"allow","detail":"approval_id=… granted_by=alice"}`；
本机观测到的 status 取值集合为 `['passed','skipped']`（`failed` 出现在失败路径）。

## 2. 逐条裁定

### 2.1 C1–C15（【OS 宪法】）

| # | 裁定 | 依据 / 要求 |
| --- | --- | --- |
| C1 | 同意 | 我独立读码确认 `app.js:170-199`。**要求收敛**：C1 的"命中集合==白名单"门禁还要覆盖 `build_site.py` **生成的 HTML**（复制文案会绕过只扫 `app.js` 的扫描） |
| C2 | 同意 | 补一条：`:365`"预演通过"缺"模拟"标注（§1.2） |
| C3 | 同意 | 我独立复现 exit 0 / exit 1（§1.1） |
| C4 | 同意 | 补：审批**单次使用 + 短时效**，过期实测 `approval_invalid`（§1.4） |
| C5 | 同意但**收窄** | 今天无前端（N1）→ 只能写成纯函数断言；"服务端挡住 504/503"是**读码**级证据（我也未能构造 504） |
| C6 | 同意 | 可升级为请求要求：界面必须带 `include_evidence=true`，否则拿不到 `reasons` |
| C7 | 同意（采信） | `conformance.py:624-625` 本轮未独立复核 |
| C8 | 同意但**收窄** | A3 的 `registry/tool-registry.approved.json` 目标我未复现；我复现的是 `policies/` 目标。收口方式（正向白名单 / 负向清单）请 Lead 二选一（对方 O3） |
| C9 | 同意 | 我未独立造漂移镜像；但我实测到"检索不可用"是显式 503（`smoke` 的 `retrieve: 503`） |
| C10 | 同意 | 措辞要求：界面只写"摘要链"，禁止"防篡改 / 防修改" |
| C11 | 同意 | 我读到 `app.js` 用 `textContent` / `esc()`；未重跑 `innerHTML` grep（采信 X13） |
| C12 | 同意 | 与 V18 合并落地：核心导入失败必须显式报错，不得回退硬编码清单（采信 X8） |
| C13 | 同意 | 我方 A–H 全流程的演示产物都写 `.tmp/r1-flows/`，未触碰仓库数据 |
| C14 | 同意 | —— |
| C15 | 同意 | **要求限定**：门禁只能断言"该行包含锚文本"；跨文件行号漂移无法自动判定 → 标【未知，需核验】 |

### 2.2 A1–A14（攻击设计）

| # | 裁定 | 一句话理由 |
| --- | --- | --- |
| A1 | 同意 | 独立读码确认（§1.2）；这是我方 R1 §9 第 2 条（B2）的同一件事 |
| A2 | 同意 | 独立复现（§1.1） |
| A3 | 同意但收窄 | 只复现了 `policies/` 目标；`registry/` 等目标按"采信"处理 |
| A4 | 同意 | 与 C6 同源：缺省请求拿不到 `reasons` |
| A5 | 同意但收窄 | 服务端证据是读码；界面今天不存在 → **今天不可验收** |
| A6 | 同意 | 摘要链边界已在 `功能清单.md` 自述 |
| A7 | 同意（采信） | X11/X12 本轮未独立复核 |
| A8 | 同意 | 采信其自身的收窄（"租户存在性泄露"而非业务数据泄露） |
| A9 | 同意 | 与 A3 同源；`policies/` 不在哈希保护范围内这点关键 |
| A10 | 同意 | 拒绝语义必须进界面错误映射表 |
| A11 | 同意但收窄 | 演示值已登记（`api/README.md`）；风险在"令牌编译进静态产物"这个模式 |
| A12 | 同意（采信） | 挂载实验本轮未复现；但后果（404/405 语义变化）与 C15/V19 一致 |
| A13 | 同意 | 我自己的 R1 也按"引用必须可复核"执行 |
| A14 | 同意（采信） | X8 未独立复核 |

### 2.3 V1–V22（可断言验收）

| # | 裁定 | 要求 |
| --- | --- | --- |
| V1 / V2 / V3 | 同意（目标态） | 今天实测 V1 得 `orc.fs.write`、V2 得 exit 0 —— **它们描述的是"应然"，必须在终稿里标明今天为红** |
| V4 | 同意但**今天不可验收** | 无前端；落点只能是纯函数 + 契约测试 |
| V5 | 同意 | 与 C6/A4 同源 |
| V6 | 同意 | `tools/api_loop.py` 已存在 |
| V7 | 同意 | 与 `services.py:73-97` 一致 |
| V8 | 同意 | 我实测到"租赁未配检索 → retrieve 503"，与 V8 同族的失败关闭 |
| V9 | 同意 | **口径要更新**：评测基线现在是 `baseline-v3.json`（`AGENTS.md` 约束 18 已改） |
| V10 / V11 / V12 | 同意 | —— |
| V13 | 同意 + **补一条** | 见 §3 冲突 5：`evaluate` 幂等重放返回 `{}` 时不得当作"已判定" |
| V14 | 同意 | 我实测到同族证据（`approval_invalid`） |
| V15 / V16 / V17 / V18 | 同意 | —— |
| V19 | 同意 | 与 A12 同源 |
| V20 | 同意（限定范围） | 见 C15：只查"行包含锚文本" |
| V21 | **改口径** | 不能写"六个门禁全绿"：要写"六个命令 + `rule_set_hash` 记账 + `phase_evidence.result`"（§3 冲突 4） |
| V22 | 同意 | 与我的"每一步由谁判定"列同构 |

## 3. 与 `r1-flows.md` 的冲突（5 条，请 Lead 裁决前两条）

1. **谁在判定（写入链上到底有没有规则判定）**：`r1-modules.md:124` 把 S3 的 `policy` 项写成"只作为输入项"。我的实测是：
   请求不带 `policy_context` 时该项是 **`[skipped] policy allow 请求没有声明 policy_context：该动作没有文件维度，Phase 1 规则引擎不适用（显式跳过）`**——
   即写入链在缺上下文时**没有**任何规则判定。终稿必须写：**判定由调用方在进 pre-check 之前取得**，pre-check 只复验带进来的上下文；"缺上下文"是显式跳过，**不是通过**。
2. **审批在哪一步**：`r1-constraints.md:57` C3 要求"凡写 `policies/**` 一律人工审批"；实现上审批是**工具表属性（`approval: required|none`）+ precheck 的第 8 个检查项**，
   `approval: none` 的工具整项 `skipped`。终稿必须把"提交节点"定义成 `pre.checks[check=="approval"].status == "passed"`，并把**工具选择**（`Change.tool_id`）写成前置条件。
3. **B1 未修时 E 流程是否成立**：`r1-constraints.md:378-383` O10 说"不修 B1 就没有可用的提交链"。我的 E 流程实测表明：`fs.edit` / `exec.*` 链**今天完全可用**
   （precheck→execute→post-check→trace→verify 全 exit 0，重放 exit 1），只有"**新建规则文件**"这条链缺门禁。终稿要拆成两条链分别写。
4. **失败语义与显式状态**：`r1-constraints.md:19` X5 / `:307` V21 记录"六门禁全绿"（我 20:33 复跑也全绿）；但 20:46 复跑：`python tools/phase_evidence.py` **exit 1 / `result: fail` / 9 个失败**
   （contract 184 例 1 失败、integration 345 例 7 失败、security 84 例 1 失败），`python tools/orchestration_loop.py` **exit 1 / 8 场景 3 失败**。
   终稿的验收基线不得引用瞬时快照。
5. **幂等响应上限（对方两份文档都没有）**：44 条规则下 `evaluate` 响应 10762 字节、带 `include_evidence` 20245 字节，越过 `src/policy_api/idempotency.py:33` 的 `_MAX_RESPONSE_BYTES = 8192` 后，
   同一幂等键重放返回 **200 + 2 字节 `{}` + `Idempotency-Replayed: true`**；编排层读不到 `decision` → `policy_unavailable` → `blocked`（与 `orchestration_loop` 失败场景逐字对上）。
   V13/V6 只覆盖"不执行第二次"与"本地=API"，**没有覆盖"重放退化成空体"**。

## 4. Lead 指定写死条款：提交节点的唯一通过判据（可直接抄进终稿）

> **每个提交节点必须写成：`pre-check` 的 `approval` 检查项 `status` 必须等于 `passed`；
> `skipped` 与 `failed` 都不等于通过。** 通过判据不是退出码，也不是页面上有没有"批准"字样。

**机器可判的判据**（字段路径本轮实测）：`pre.decision == "allow"` **且** `pre.checks` 里 `check == "approval"` 的条目 `status == "passed"`。

**正例（批准有效，exit 0）**：

```text
pre-decision: allow (allow) tool=exec.pwsh
  [passed ] approval           allow approval_id=approval-e776d1ff39f9 granted_by=alice
JSON: {"check":"approval","status":"passed","reason_code":"allow","detail":"approval_id=approval-e776d1ff39f9 granted_by=alice"}
```

**反例一（`skipped`：工具声明不需要审批 —— 提交节点不得据此放行）**：

```text
pre-decision: allow (allow) tool=orc.fs.write
  [skipped] approval           allow 该工具不需要人工审批
说明：证明该动作"走错了工具"。目标在 policies/** 时，工具选择必须先是 orc.policy.edit；
      "跳过审批"是流程缺陷的信号，不是通过。
```

**反例二（`failed`：审批缺失 / 过期，exit 1）**：

```text
pre-decision: block (approval_required) tool=orc.policy.edit
  [failed ] approval           approval_required 该动作需要人工审批，但没有提供与当前 action_hash 绑定的审批记录

pre-decision: block (approval_invalid) tool=exec.pwsh
  [failed ] approval           approval_invalid 审批已过期（2026-09-22T12:41:03.126211Z）
```

**配套两条**（否则判据会被绕过）：
① **工具选择先于审批**：终稿要写"目标在 `policies/**` ⇒ 工具必须是 `orc.policy.edit`"，并配 `Change(path="policies/…", content=…).tool_id` 的断言（今天返回 `orc.fs.write`）；
② **审批单次使用 + 短时效**：同一审批复用会得到 `approval_invalid`，参数变一个字符 `action_hash` 即不符——审批是"一次动作一次批准"，不是"一次批准一段会话"。

## 5. 对终稿 `02-操作流程.md` 的可执行修改清单

1. **每个提交节点加一行判据**：照抄 §4 的黑体句 + JSON 字段路径；正反例各留一个（可用 §4 的实测输出原文）。
2. **流程图里给"判定"和"授权"分两个泳道**：判定（`policy.engine.evaluate`）在调用方一侧；授权（pre-check 的 14 项）在执行侧。缺 `policy_context` 时 `policy` 项 `skipped`，必须画成"虚线 + 显式跳过"，不得画成实线通过。
3. **"生效"一节改写为三条命令的证据链**：`policy.check --check-rules`（含 `sha256`）+ `retrieval.cli verify`（含 `datasets/entries`）+ `validators.cli probe`（缺工具的显式结论），并写明"**这三条全绿只证明可加载，不证明规则集没变**"。
4. **加"规则集身份记账"一节**：每次改 `policies/**` 记录 `--check-rules` 输出的 `sha256`；恢复/复核时比对它（补 V21 的口径）。
5. **加"检索不可用与无结果分开"的显式状态表**：`empty (no_results)`（CLI exit 1）/ `knowledge_unavailable`（API 503）。
6. **加"幂等键使用限制"一节**：判定调用不带幂等键；若带，必须识别 `Idempotency-Replayed: true` 并把 `{}` 当"未取到判定"（§3 冲突 5）。
7. **失败语义表用三套编号分开**：CLI 退出码 0/1/2（`src/policy/check.py:71-73`）、API 错误码→HTTP（`src/policy_api/errors.py:73-107`）、编排终态（`src/orchestration/errors.py:127-158`）；界面只显示后两套，且"未知码原样显示"。
8. **溯源一节按实测写**：`rule_sources` 现有 **39 条**；`retrieval.cli rules --rule DOC-001` / `STYLE-003` exit 0，`ARCH-001` / `STYLE-013` exit 1 —— 界面必须区分"已登记"与"未登记"，未登记不得渲染成"无来源"。
9. **每条流程加"谁负责判定"列**（照抄 R1 的写法），并在开头写死红线：界面与脚本不得复算、不得用退出码代替载荷、不得把 `skipped` 当通过。
10. **把"门禁快照"写成带时刻的引用**：`phase_evidence` 与 `orchestration_loop` 的当前实测结论（红）与原因（规则集增长 + 幂等上限）各留一句，避免终稿被读成"平台当前全绿"。

## 6. 交回 Lead 的开放问题

1. **裁决 §3 冲突 1 与 2**：写入链上"判定"的责任边界怎么写？（我的立场：判定在调用方，pre-check 只复验；提交节点判据只看 `approval.status`。）
2. **B1 的修法是否进入终稿的落地步骤**：若进，请指定"工具选择硬约束"还是"路径 pattern 排除"（两者都要改注册表 → 重新审核）。
3. **瞬时快照怎么写**：终稿的"当前状态"一节是否接受"带时刻 + 带 `sha256` 的引用"这种写法？（否则每次规则增长都会让终稿过期。）
4. **幂等上限的归属**：这是 `policy_api` 的实现缺陷（8192 上限对判定响应太小）还是使用纪律（判定不带幂等键）？我倾向两者都写，但要 Lead 定优先级。
5. **我的 R1 需要同步更正的条目**：§C 台阶 7 与 §9 第 9 行（溯源）已加 20:49 更正说明；§A 的 `entries=27` 现为 42。是否需要我在 R3 出一次"R1 全量刷新"？

---

**本文件未做的事（如实标注）**：未复现 A3 的 `registry/` 等目标 precheck、未复现 A12 的静态挂载实验、未复现 X8/X11/X12/X13 的 grep、未构造 504、未跑全量 `pytest`（只跑了 `phase_evidence` 与两个隔离用例）。
