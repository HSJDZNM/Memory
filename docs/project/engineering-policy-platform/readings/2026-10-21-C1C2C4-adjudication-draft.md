# 2026-10-21 C1/C2/C4 裁定草案 + C3 前置阻断范围

> 性质：**裁定草案**，不是读数。依据使用者 2026-10-20 会话的授权（"现在我都允许"）与 05 §4 C、§8 第 9 条。
> 草案只写"建议怎么做、门是什么、代价与到期日"；**未经使用者逐条确认前，C1/C2 的判定改动不落地**。
> C3 的第三件（危险动作前置阻断）在本文 §5 单独定范围，本轮即由子会话按该范围实现。

## 0 一句话

C1/C2 都属于"改判定语义 + 协议升版"，建议各分两个台阶：**先只报告，再进判定**；C4 先做**只读探针**验证宿主的
`agent.steer` 能力，不碰判定；C3 第三件的真实缺口是 **`.policy/` 写面**（读面已由 B3 封住，写面没有），本轮补数据 +
验证套件，不改判定路径。

## 1 C1 批次台账（04 5.46；05 §3.3）

**问题**：Hook 每次工具调用是新进程，批次状态跨不了进程；判定粒度是单次编辑，`(conftest.py,)` 与
`(conftest.py, order_service.py)` 两种批次会得到 block / allow 两个结论（04 5.68 的决定性读数）。后果是
"先写测试"这条正路会被自己的取证打成警告。

**建议分两台阶**：

| 台阶 | 内容 | 改判定吗 | 门 | 回退 |
| --- | --- | --- | --- | --- |
| C1-a 只报告 | Hook 把本 session 已提议的文件记进 `.policy/pre-evidence-batches/<session_id>.jsonl`（追加写、按 session 分文件、TTL 24h、显式 `settled` / `abandoned`），判定记录里带 `batch_ref` 摘要；批次**不进** evaluate | 否 | 真实 Hook：连续三次 edit 后账本可读、`batch_ref` 稳定；同一 session 的两条记录能按 batch 折叠；并发两个 session 文件互不覆盖；清理后不残留 | 删记录、判定不看它 |
| C1-b 进判定 | `pre_evidence` 把同批已提议文件也放进取证树，判定输入带批次集合；`PIPELINE_SCHEMA_VERSION` 1.4→1.5（或 `EVIDENCE_SCHEMA_VERSION` 1.2→1.3，按实际载荷变哪一份算） | **是** | 三步（实现→测试→conftest）逐步 decision 与合并判定**逐个相等**；批次能被显式 settle/abandon，未结算的批次不得当作通过；**预算不等式**重算（`pre_evidence.timeout_ms + timeout_ms < hooks.json timeout`） | 删批次输入、版本回退 |

**风险**：并发会话共用 `.policy/` 时批次文件互相污染（按 session 分文件 + TTL + 显式结算缓解）；批次的"同一批"定义
（时间窗？显式 API？）是一次**语义决策**，不许用"最近 N 分钟"这种隐式口径（AGENTS 第 6 条：不推断）。

**建议裁定**：先做 C1-a（约 2 人日，不改判定），拿到真实读数的"批次折叠正确率"后再决定 C1-b。C1-b 另行裁定。

## 2 C2 证据第三态「不适用」（04 5.68；05 §4 C2）

**问题**：证据只有"服务过 / 失败关闭"两态；一次验证器缺口被写成 41 条 critical violation（style_lint 扇入 39:1）。
"本次不适用"没有表达方式，只能走跳过或失败关闭两个极端。

**建议语义**（先写死，再实现）：

- `not_applicable` **不是**"跳过"：它要求给出**结构化依据**（哪个声明 / 哪条数据说"这类目标不需要该 checker"，
  例如 `validation/validators.yaml` 的 `uncovered_languages`），并带**到期日**（到期自动失效，回到失败关闭）。
- 与现有三态的关系：`available`（查过、有结果）/ `unavailable`（查不了，失败关闭）/ **`not_applicable`（按设计不查，
  有依据、有期限）**；`skipped_rules` 仍是"规则不适用"，不改名。

**协议与门**：

| 轴 | 变更 | 说明 |
| --- | --- | --- |
| `policy.evidence.EVIDENCE_SCHEMA_VERSION` | 1.2 → **1.3** | 证据载荷新增显式状态值（取值集合变即协议变化） |
| `validators.pipeline.PIPELINE_SCHEMA_VERSION` | 1.4 → **1.5** | 流水线报告新增 `not_applicable` 通道与依据字段 |

门：**"同一输入从 block 变 allow"的用例必须存在且通过**（这正是放宽的定义）；**反例一条不放宽**（第三方包缺失 /
语法错误 / conftest 出错 / 断言失败 / 目标解析不出来仍按原 severity 或失败关闭）；到期后自动回到失败关闭的用例；
`tool.pytest` 与 `tool.ruff` 各一条真实读数。回退：删状态值与依据字段、版本回退。

**到期日**：每个 `not_applicable` 依据必须带 `expires_at`（建议 ≤ 90 天），过期即失败关闭；读数的 `reading_context`
必须写清"这条证据属于哪棵树/哪套声明"（第 48 条）。

**建议裁定**：**不急于做**。04 5.75② 已用一行配置解掉当下最痛的 block；C2 的价值取决于"语言不覆盖"这类场景是否
反复出现。建议先跑一轮"哪些 checker 缺口最常见"的只报告读数，再决定是否升版。

## 3 C4 回合末 steer 门禁（05 §3.1）

**宿主事实（已查）**：dsh 在回合收尾前派发 `agent/turn-stopping`，约定是**监听器里调用 `agent.steer(...)` 注入新指令**，
没有 "decision: block" 返回值；仓库的插件当前只注册了 pre/post-execute，**没有订阅**该事件。

**先做验证明（不改判定）**：一个只读探针，在桌面 profile 的插件里订阅 `agent/turn-stopping`，检查 `agent.steer` 是否
真的存在、调用后宿主是否重读收件箱再跑一步；两种结果都要落读数（可用 / 不可用）。**不可用就停在验证**。

**若可用再做**：未结清清单（C1 的批次账）→ 有未结清文件时注入一条"先补齐取证再收尾"的指令；**没有未结清时不多跑一步**；
最大注入次数（例如 1 次/回合）防循环；steer 只由服务端判定结果触发，模型自述不作为触发条件。

门：真机两例（有未结清：多跑一步且第二次不再注入；没有：回合正常结束）；`steer` 文案与判定原因码一起落账。
**风险**：注入循环、把"只报告"变成事实上的阻断、桌面 profile 的插件 API 版本漂移（第 54 条同型）。
**建议裁定**：先做验证探针（1 天），可用再裁定是否立项。

## 4 C3 第三件的现状（本轮实测）

| 路径 | 现状 | 依据 |
| --- | --- | --- |
| 写类工具到 `policies/`、`registry/`、`adapters/`、`api/`、`validation/` | **已前置阻断**（数据 `blocked_prefixes`，precheck + drivers 两处） | `registry/tool-registry.yaml` 的 `fs.edit` / `fs.write` / `orc.*` 段 |
| 写类工具到 `<受控项目>/.policy/` | **没有阻断**——`blocked_prefixes` 不含 `.policy`；而读面已由 B3 的 `read_guard` 封住 ⇒ **同一目标两条路，写没封** | `registry/tool-registry.yaml` 的 `blocked_prefixes` 列表；B3 读数 §2.1 |
| 删除 | dsh 工具表无 delete 操作；`pwsh` 的 `Remove-Item` 不在白名单（`command_not_allowlisted`） | `src/adapters/dsh/adapter.py` 的工具表；`registry` 的 `allowed_commands` |
| 执行 | `run_code` 有结构化静态检查（禁 `os`/`shutil`/`subprocess`/`open`/`exec` 等，已知缺口写明）；`pwsh` 走白名单 + 片段 + 读面 | `registry` 的 `code_check` 段；`precheck` 的检查链 |

**结论**：C3 第三件不是"从零建一道闸"，而是**补一个数据缺口**（`.policy` 写面）+ **把已有三路径的阻断交成可复核的读数**。
v1 范围：注册表把 `.policy` 加进写类 `blocked_prefixes`（1.2→1.3、重审）+ 一套验证用例（写 `.policy` 被拦、
`policies` 仍被拦、`.policyx` 不误伤、删除/执行路径的既有码不变）+ 读数；**不改判定路径、不新增 reason code**。

## 5 建议顺序与到期

1. **本轮**：C3 第三件 v1（数据 + 验证套件）——范围小、可直接交子会话；C1/C2/C4 草案交使用者确认。
2. 下一轮：按使用者的确认，任选 C1-a 或 C4 验证探针（都不改判定）。
3. 到期日：C2 的"先做只报告读数"建议在 2026-12-31 前给一次结论（与 5.80 / 5.82 的复审同日）；C4 的验证探针
   若 2026-11-30 前没跑，"回合末门禁"按"当前宿主不支持阻断"收口，不再悬空。

## 6 证据指针

- 05 §3.1（宿主 Stop 语义）、§3.2（B1 参数域）、§3.3（批次状态）、§4 C（C1–C4）、§8 第 9 条。
- 04 5.46 / 5.68 / 5.70 / 5.86。
- `registry/tool-registry.yaml` 的 `blocked_prefixes`、`code_check`；`src/enforcement/action.py#L299`（`blocked_path_prefix`）；
  `src/enforcement/precheck.py#L401`（precheck 调用点）；B3 读数 `readings/2026-10-20-B3-read-guard.md` §2.1。
