# 2026-10-21 实验冻结项裁决：宿主版本 / 沙箱形态 / 5.90 / 5.88② / 部署复制

> **性质**：裁决读数（共享任务 task-6）。范围 = 只读分析 + 三条只读命令 + 两次版本探测；**不改代码、不改注册表、不 commit、不 push、不跑真机会话、不跑 `ci_local`**。
> **起点**：HEAD `0f580f8`（工作树干净；同目录下未跟踪的 `2026-10-21-c1b-treatment-adjudication.md` 是 task-7 的读数，不在本文范围）。
> **依据**：AGENTS 第 10/13/14/17/38/45/50/52/54/55 条；05 §5.4 / §5.5 / §5.6 与 §8；06 的 R-A-GATE-07 / R-C1b-01 / R-SYNC-01；04 5.61 / 5.78 / 5.81 / 5.82 / 5.86 / 5.88 / 5.90。
> **与 task-7 的关系**：task-7 已裁「C1-b = 平台代际基线（T3）」并指出 17 字段不足。本文**不另立第二个字段**：宿主与沙箱两格并入它的 `platform_generation`，一次升版；两处若各加一个字段，就是同一份载荷的两次协议变更。
> **纪律**：不写均值/百分比/显著性；不出现绝对路径与凭据。路径一律 token：`<workspace>`（本仓库）、`<install>`（桌面端安装目录）、`<npm-global>`（npm 全局 bin）、`<governed>`（受治项目根）、`<DSH_HOME>`、`<temp>`。

## 0 一句话

五项各自冻结在**一个可复核的形态**上：宿主 = app 自带 **dsh 0.2.1-rc.2**（PATH 上的 0.2.1-alpha.2 只作案例宿主）；控制器/测量进程 = **danger-full-access**；5.90 = **接受为实验的已知边界**、实验后修；批次并发 = **串行 run** 而不加锁；每个实验臂/受治项目 = **自己的** registry 1.4 本地副本 + 自己的已审核 + 使用者签的条子。

五项里只有记录字段要动协议：不新增第二个顶层字段，宿主/沙箱/配置/审批/模型并入 task-7 的 `platform_generation`，`RUN_MANIFEST_SCHEMA_VERSION` 1.0→1.1 与评分器冻结块 version 2→3 一次做完。

## 1 结论表（每项一行）

| # | 项 | 裁决 | 一句话理由 |
| --- | --- | --- | --- |
| 1 | 宿主版本 | 冻结 **app 自带 dsh 0.2.1-rc.2**（`<install>/resources/runtime/cli/bin/dsh.cmd`；桌面端外壳同版本）；**PATH 上的 0.2.1-alpha.2 只作历史案例的宿主**，不进本轮 k≥3 | 目标是 dsh 桌面 GUI 的开发任务（05 §1）；10-21 三份真机读数都在 rc.2；05 §5.4 禁的是**臂与臂之间**不同，不要求保留旧宿主 |
| 2 | 沙箱形态 | 控制器/测量进程一律 **danger-full-access**；dsh 会话沙箱每轮固定并记录；`reading_context.host.sandbox` **只写三态**，模式另记两个字段；run 与 `ci_local`、与第二个会话**互斥** | workspace-write 下 Hook spawn EPERM 已实测（跑不成）；三态与环境模式是两根轴，混写会绕过枚举校验 |
| 3 | 04 5.90 | 冻结窗口内**接受为已知边界**（不修）；实验关闭后按 (b) 回放 pre 理由修；(c) 不采纳 | 修 = 改模型可见反馈 = 改 treatment 的反馈通道（05 §5.4/§5.5）；审计里的 `reason_code` 本来就是对的 |
| 4 | 04 5.88② | 实验期**串行 run**（一次一臂一 run、不共用受治项目）；**不加锁/不加 fsync**；批次计数不干净即记 degraded | T3 下批次进判定；并发让批次成员变少 → 偏严；加锁改的是每次受治理写的热路径 |
| 5 | 部署复制与重审 | 每臂/受治项目各一份 `tool-registry.local.yaml`（1.4 + governed-dev）+ **自己那份** `tool-registry.approved.json`（`--reviewer dshznm` 自审，写清不是第三方）；条子只由使用者签；仓库 `registry/**` 一个字节不动 | 04 5.82：仓库版没有 governed-dev，用它会让每个写/执行 `permission_denied`（A 首跑作废）；AGENTS 13 禁改仓库已审核哈希 |

## 2 逐项裁决

### 2.1 宿主版本

**核实（本轮实测）**

| 事实 | 读数 | 证据 |
| --- | --- | --- |
| PATH 上的 dsh | **0.2.1-alpha.2**（`<npm-global>/dsh.ps1`） | 本轮 `dsh --version`、`Get-Command dsh` |
| app 自带 CLI | **0.2.1-rc.2** | 本轮 `& '<install>/resources/runtime/cli/bin/dsh.cmd' --version` |
| 桌面端外壳 | **0.2.1-rc.2** | 本轮 `DeepSeek Harness.exe` 的 FileVersion；与 `readings/2026-10-21-C4-steer-probe.md:121` 同号 |
| manifest 声明 | `agent_version: 0.2.1-alpha.2`；`host_version` 探 `dsh --version` | `adapters/dsh/manifest.yaml:24`、`:72-75`；`:19-21` 自述「桌面端是另一条版本线」 |
| 观测记录 | `observed_version: 0.2.1-alpha.2`，`manifest_digest: sha256:2c5e1b92…` | `adapters/host-versions.observed.json:3-13` |
| CI 形态 `--record-check` | **exit 0**；match 1 / drift 0 / recording_stale 0 / unavailable 0 / not_declared 2 | 本轮实测（不探测宿主，只比「声明 vs 记录」） |
| 活体 `--check` | **exit 0**；声明 = 宿主 = 记录 | 本轮实测 |
| 10-20 三臂 run 的宿主 | **0.2.1-alpha.2** | `readings/2026-10-20-D-gate2-ab-c-runs.md:17`；`06-plan-progress.md:305`（P-D-006） |
| run-manifest 是否记宿主 | **不记**：17 字段里没有宿主/模型；`arms` 只抽 `tree_digest / session_id / launch.patch / launcher_sandbox` 四类 | `testing/ab/dgate2/run-manifest/README.md:18-36`、`:61-78` |
| 10-21 三份真机读数的宿主 | **0.2.1-rc.2**（app 自带） | `readings/2026-10-21-registry-1.4-registry-sync.md:74`、`:180`；`readings/2026-10-21-C1-b-batch-into-decision.md:21`、`:62`；`2026-10-21-C4-steer-probe.md:121-123` |
| 10-20 轮的臂注册表 | 读数记 `e8bc569b…`；当前 1.4 副本是 **`120474c8…`** | `readings/2026-10-20-D-gate2-ab-c-runs.md:16`；本轮 `Get-FileHash` |

**裁决：冻结 rc.2（app 自带 CLI + 桌面端外壳），不冻结 alpha.2。**

1. **目标对齐**：本计划的目标原文是「在 dsh 桌面 GUI 的代码开发任务中」（05 §1）；桌面端跑的就是 rc.2。alpha.2 是 PATH 上的 npm CLI，不是交付入口——把实验冻结在它上面，等于在一条不是产品的宿主线上回答产品问题。
2. **与已取得的真机证据同线**：10-21 的三份真机读数（C4 能力、R-SYNC-01 四例、R-C1b-01 三次 edit）全部在 rc.2。若冻结 alpha.2，「平台能力已在 rc.2 真机成立」与「实验在 alpha.2 上跑」会永远分居两条版本线，每次跨读数引用都要再写一次限定。
3. **05 §5.4 的口径**：它禁的是**臂与臂之间**宿主不同；三份 10-20 run 本身同宿主（alpha.2），该轮内部**不命中** §5.4。但它与 rc.2 轮**不能合并**——这一点与 task-7 的「旧 n=1 作废为新对照」同向。

**记录方式（三层，各回答一个问题）**

| 层 | 记什么 | 回答什么 | 为什么不能省 |
| --- | --- | --- | --- |
| `platform_generation.host`（任务-7 的新字段；与本文合并一次升版） | `entry`（headless/desktop）、`dsh_runtime`、`dsh_source`（app_bundled/path_cli）、`dsh_entry`（token）、`profile`、`session_sandbox`、`file_policy`、`sandbox`（三态） | 「这次 run 用的是哪条 dsh 线、什么形态」 | 现在的 manifest 与 arm-facts 都不记它；这是 §5.4 在本轮**唯一可复核**的载体 |
| `arms` 的输入文件（C 臂形状的 arm-facts，`arms.source_sha256` 钉住） | 同上 + `dsh.version` + `launch.patch` + `adapter_config.sha256` + `registry_digest` + `approval.sha256` | 「这份 manifest 取自哪次启动记录」 | `--arm-facts` 已能接受 C 臂完整 manifest（`run-manifest/README.md:61-78`）；A/B 臂 facts 比 C 臂**少**记了 `dsh.version` 与 `session_sandbox`（`c-arm/README.md:235-238`、`:207-209` 的推荐 vs `runs/2026-10-20/A/arm-facts.json:7-8` 被 manifest 只抽 launcher） |
| run 报告 `reading_context.host` | `dsh_runtime`、`dsh_source`、`file_policy`、`session_sandbox`、`sandbox`（三态） | 「这份读数属于哪个环境」 | 写进报告才能被引用；但**不是**版本轴（`src/provenance/reading_context.py:51-53`），别给它编号 |
| `adapters/host-versions.observed.json` | **保持 alpha.2 不动** | 「PATH 上的 dsh 是否等于 manifest 声明」 | 它探的是 PATH、单值、`executable` 写 `dsh`（`manifest.yaml:72-75`）；把 app 路径塞进去需要改声明 + `--probe-binary`，记录会变成「executable=dsh 却探了另一条路径」的不真实陈述，且 PATH-only 机器上 `--check` 永远 drift |

**代价与未核实**

- 10-20 n=1 只作 alpha.2 案例，不计入 k≥3；D 校准门（P+/P−/canary，无模型）与 C1-b 门 2/4/5 必须在 rc.2 重跑一次（成本低；task-7 §6 也已要求重跑）。
- 每臂 `.policy/dsh-adapter.yaml` 的 `agent_version` 必须写 **rc.2**：它是 `action_hash` 的参与字段（`src/enforcement/models.py:1236-1255`），写错会让审计与真宿主说两句话。仓库侧 manifest 仍写 alpha.2（`tests/contract/test_dsh_layer_declaration.py:47-60` 只钉 `examples/dsh/dsh-adapter.yaml`，**b-plan 那份副本没有契约钉住**）→ 必须把它的 sha256 与取值记进 `platform_generation`。
- **未核实**：alpha.2 与 rc.2 的**行为差异没有对照读数**。10-20 A 臂的 post 分布里没有 `post_error`（`2026-10-20-D-gate2-ab-c-runs.md:45-46`），但现场审计已被清空、无法复核「被拒调用是否也拿到 post」；而 A3（alpha.2，`readings/2026-10-18-A3-single-action-probe.md:44`）与 R-SYNC-01（rc.2，`:190`）都记录过这条回声。换代前不能假定两版本在这条上一致。
- **未核实**：app 是否会自动更新。run 窗口内宿主变号 = 05 §5.4 的「外部改动」→ 该 run 作废；需要使用者关自动更新，或在 run 前后各核对一次 `--version` 并写进起点清单。

**旧读数标注（不改旧文件，只登记映射）**

| 既有读数/产物 | 宿主 | 标注与用法 |
| --- | --- | --- |
| A3 单动作探针 / U2b / 干跑 v1·v2 | alpha.2 | 构造与能力读数；引用时带「宿主 0.2.1-alpha.2（PATH CLI）」；**不参与**本轮 k≥3 |
| `readings/2026-10-20-D-gate2-ab-c-runs.md` + `runs/2026-10-20/{A,B,C}/` | alpha.2 | **案例读数（alpha.2 轮）**；轮内三臂同宿主、不命中 §5.4；**不与 rc.2 轮合并**；按 task-7 已裁「作废为新对照」 |
| C4 / R-SYNC-01 / R-C1b-01 | rc.2（app 自带） | 保留为平台能力/受治侧真机读数；引用时写 `host.dsh_source=app_bundled`；它们**不是**对比臂读数 |
| C3 三件 / C1-a / final_tree_gate / C1-b 的离线门 | 无宿主（离线） | 不标宿主；**不得**由它们推断宿主行为 |
| `adapters/host-versions.observed.json` | alpha.2（CLI 线） | 保持有效（`--record-check` exit 0）；**不得**读成「run 宿主已冻结」 |

### 2.2 沙箱形态

**事实**

- `workspace-write` 下 Hook 需要管道 stdio，实测 `spawn EPERM`：三例全部失败关闭、`.policy/` 0 条审计（`readings/2026-10-21-registry-1.4-registry-sync.md:98-108`、`:83-93`）。这不是策略判定，是**跑不成**。
- 同一套配置在 `danger-full-access` 下四例全部取得（同上 `:110-131`）；本机门禁也只在 `danger-full-access` 下跑得了（`06-plan-progress.md:231`；`2026-10-21-new-session-prompt.md:18`）。
- 10-20 三臂：**launcher 沙箱 `danger-full-access`、会话沙箱 `workspace-write`**（`2026-10-20-D-gate2-ab-c-runs.md:17`；`runs/2026-10-20/A/arm-facts.json:7-8`）；run-manifest 只抽了 launcher（`runs/2026-10-20/A/run-manifest.json:20-25`），`session_sandbox` 留在未受跟踪的输入文件里。
- T 维度 runner 对**文件沙箱**敏感：同一命令在 workspace-write 下 10 条子进程用例 PermissionError（T 30/40），danger-full-access 下 40/40（04 5.81②）。c-arm 的推荐是 launcher 与 session **分开记**（`testing/ab/dgate2/c-arm/README.md:207-209`、`:238`）。
- `.policy` 的审计/台账是**活账本**：c-arm 冒烟窗内账本 +53 条全部来自其他并发会话（`c-arm/README.md:209`）。同一受治项目两个会话同时跑，读数会被别人的记录染色。

**裁决**

1. **控制器/测量进程一律 danger-full-access**（唯一形态）。这是 Hook 能起来、门禁能跑、T 维度能读的前提；任何 workspace-write 下得到的「拒绝」都不是策略读数。
2. **dsh 会话沙箱每轮固定并记录**。建议保持 10-20 轮的 `workspace-write`（产品默认；评分只读最终树、runner 在会话外跑）；若改用 `danger-full-access` 也接受，但**同一轮三臂必须同值**，且写进 `platform_generation.host.session_sandbox`。
3. **`reading_context.host.sandbox` 只写三态**（`restricted` / `unrestricted` / `unknown`，`src/provenance/reading_context.py:147-154`），**不能**写 `danger-full-access`——那不是合法取值（`host_block` 会 raise，`:405-408`）。模式另记 `host.file_policy` / `host.session_sandbox`（`host_block(extra=…)` 允许宿主事实，但不得覆盖 platform/python/sandbox，`:390-424`）。
4. **三态的判据**：本轮出现了「工作区之外操作被拒」的证据 → `restricted`（R-SYNC-01 的 EPERM 轮就是这一格，`:181`）；真的做完了且没有拒绝证据 → `unrestricted`（`:110-131` 的四例）；没做过 → `unknown`。Hook 审计里的 `host.sandbox` 恒为 `unknown`（`src/adapters/dsh/hooks.py:1201`），**不得**读成 run 形态。
5. **互斥**：run 与 `ci_local` 不并跑——两者都要 danger-full-access，共享同一工作树与 `.tmp` 固定路径，而 `ci_local` 的 `.tmp/ci-local.lock` 只对它自己生效、run 侧没有锁（`2026-10-21-new-session-prompt.md:20`）。操作口径：run 前查锁是否被占（**不删锁文件**），`ci_local` 期间不启动 run；同一受治项目一次只一个会话。
6. 违反上述任何一条 → 该 run 记 **跑不成** + reason/reproduce，不记通过（AGENTS 10/45）。

### 2.3 04 5.90：被拒调用仍收到 PostToolUse，模型侧理由是 `post_error`

**先核实「是不是宿主行为」**：是。三处独立证据：

- R-SYNC-01 b 例（rc.2）：PreToolUse `decision=allow` + `reason_code=path_out_of_scope`、`probe.txt` 未落地，宿主仍派发 PostToolUse，Hook 的 post 路径「找不到对应的 pre-check 记录」→ `post_error`（`readings/2026-10-21-registry-1.4-registry-sync.md:122-123`、`:190`）。
- A3 D6（alpha.2）：blocked PreToolUse 之后**仍会**收到 PostToolUse，得到 `post_error`（`readings/2026-10-18-A3-single-action-probe.md:44`）；04 5.60 的旧真机也是 7 次 pre 拦截各跟一条 `post_error`（`04-open-work.md:287`）。
- 反证（最关键）：宿主**自己**拒绝的调用（`file has not been read`）也收到了 PostToolUse，记为 `post_inconsistent`（`registry-sync.md:124`）→ 这不是插件装配问题，而是宿主对「未执行的调用」也派发事后事件。

**机制（决定能不能便宜地修）**：post 在台账里找不到 `pre_state` 时一律抛 `DshEventError`（`src/adapters/dsh/enforcement.py:388-410`）；`_post_decision_outcome` 的 `except Exception` 把它统一映射成 `post_error`（`src/adapters/dsh/hooks.py:2546-2557`）。而 pre 只在**不 block** 时写 `pre_state`（`enforcement.py:295-301`、`:303-340`），所以「被 pre 拒」与「根本没走 pre」在 post 侧**不可分**。范围：只有声明了 `post_checks` 的工具会走到这一步；`post_checks: []` 的工具 post 返回 None → `post_not_required`（`enforcement.py:385-386`；`hooks.py:2559-2564`）。写/执行类会得到这条回声，纯读类不会。

**三选一**

| 选项 | 内容 | 代价 | 对多步任务读数的影响 | 结论 |
| --- | --- | --- | --- | --- |
| (a) 接受边界 | 写进实验的接受边界：审计为准、模型自述不作为读数 | 0 代码；但每次引用都要带限定 | block 越多，A 臂的 `post_error` 回声越多；模型可能按错误理由继续（10-20 A 的 M5b→M5c→熔断即例） | **本轮采纳** |
| (b) 修 post 路径 | pre 已 block 时回放 pre 的 reason_code | 审计协议升版（新 `stage_note` + 新键 → `AUDIT_SCHEMA_VERSION` 1.5→1.6）；新异常/映射/用例；**改模型可见反馈 = 改 treatment** | 修后模型看到真理由；与已跑轮**不可比**（反馈通道变了） | **实验后做**（最小改动面见下） |
| (c) 插件抑制 | 插件记住自己 deny 过的 call id，post 直接 `next()` | 少一条审计占位；**删掉**「被拒调用是否被执行」的探测器；对宿主自己拒绝的调用无效 | 模型只看到 host 的拒绝文本；若宿主某版本真的执行了被 deny 的调用，不再有 post 核对 | **不采纳** |

**若做 (b)：最小改动面（只给文字，不落代码）**

1. `src/adapters/dsh/enforcement.py::EnforcementBridge.post`：`state_for()` 为 None 时，先用现有 `sink.chain_records()`（`src/enforcement/audit.py:203`、`:374`）找该 `action_id` 的最新 `PRE_DECISION`；`decision == block` → 追加一条 `POST_EVIDENCE`（`stage_note=post_skipped_blocked`、`pre_reason_code`、`pre_sequence`、`untrusted_result_digest`），再抛一个**专用**异常（携带 pre 的 reason_code 与失败 check 的 detail）；找不到 pre 记录才保持现状。
2. `src/adapters/dsh/hooks.py::_post_decision_outcome`：在通用 `except Exception` **之前**捕获该异常，返回 `exit 2`、`reason_code=post_skipped_blocked`、stderr 回放 pre 的 detail（不再出现「找不到对应的 pre-check 记录」）。
3. `src/adapters/dsh/policy-hook.plugin.mjs`：不改（它已把 stderr 原样交给模型，`blockFeedback` 只包一层，`:703-708`）。
4. `src/enforcement/trace.py`：确认新 `stage_note` 不构成链缺陷（现有 `post_without_pre` / `post_without_request` 的先例在 `tests/unit/test_enforcement_audit.py:380-390`）。
5. 生成物：`docs/project/architecture/tech-detail/02-dsh-Hook-内部流程/` 提到 `post_without_pre`（`:673`、`:680`），按生成管线重生成，`--check` 是门禁。

**要补的用例（若做 (b)）**

- `tests/contract/test_policy_hook_chain.py`：① pre block（write `<governed>/.policy/x`）→ post 走新路径，`reason_code` **不是** `post_error`、模型侧文本含 pre 的理由；② 真旁路（无 pre 记录、工具真的执行）**仍** `post_error`、仍写 `post_without_pre`；③ 宿主拒绝未执行（pre allow）→ 现有 `post_inconsistent` 不变。
- `tests/integration/test_dsh_enforcement.py`：blocked write 的 post 记录 + 台账无 `pre_state` + 审计新键；现有两条 `post_error` 用例（`:397`、`:718`）是「无 pre 记录」的正例，逐条保留。
- `tests/unit/test_enforcement_audit.py`：`post_skipped_blocked` 不算链缺陷；旧 `post_without_pre` 记录照常读。
- 协议：新键 = 升 `AUDIT_SCHEMA_VERSION`（AGENTS 55），写死版本号的断言同批改。

**一处与任务书假设不同、按事实写**：AGENTS 52 要求同步的是**插件侧 spawn 失败措辞**（`Hook 无法执行（…）`）与 `tools/dsh_sandbox_loop.py` 的归因（`tools/dsh_sandbox_loop.py:318`、`:1100-1112`）。本方案不改那句措辞，因此**不需要**动那个分类器；被牵动的是 post 理由的跨侧契约用例与审计 `stage_note` 词汇。若将来把新文案写成「Hook 无法执行」形态，则必须同步两侧。

**对多步任务读数的影响（本轮按 (a) 读）**

- 任何把 `post_error` 计成「事后失败 / 证据不足」的读数**不可用**，改读为「被拒调用的事后回声」；post 分布必须**按 pre decision 分列**（allow 的 post / block 的 post），不要把 block 的回声混进 post_validated 的分母。
- 10-20 A 的 `post_repair_required 3` 是**执行后**失败（预期红 pytest 的 exit 1），与 block 回声是两回事（`2026-10-20-D-gate2-ab-c-runs.md:45-46`），引用时不要合并。
- 这条缺陷对两臂同类存在、频次随 block 数变化：它**是 treatment 反馈的一部分**，不是随机噪声；但因此 A/B 的 block 数差异会带出「模型收到的理由质量」差异——05 §5.5 的「不能证明」里必须加一条。

### 2.4 04 5.88②：同会话批次并发追加无锁/无 fsync

**事实**

- `_write_line` 只做 open-append-write-close：**无跨进程锁、无 `flush`/`fsync`**（`src/adapters/dsh/batch_ledger.py:317-325`）；`append_target` 是**先读后写**（`:342-382`），两个并发进程会各自少看对方刚追加的目标；读侧把坏行计 `skipped`、不当成员（`:285-304`）；账本按会话分文件（模块 docstring 第 1 条，`:11-13`），因此跨会话并发不会互相污染，风险在**同会话并发**与「同项目两个会话共享 audit/ledger」。
- 04 5.88② 原文（`04-open-work.md:315`）；C1-b 读数把「并发锁/fsync」列为残项（`readings/2026-10-21-C1-b-batch-into-decision.md` §6）。
- **T3 之后两臂 `into_decision=true`**（task-7 §1）→ 批次**进判定**，不再只是只报告；这条残项因此从「可观测性」变成「构造正确性」。

**裁决：实验期规定串行 run；不加锁、不加 fsync。**

- 一次一臂一 run；同一受治项目一次只一个会话；run 期间不跑 `ci_local`、不跑探针、不让第二个会话写同一 `.policy`。
- 每 run 记 `pre_evidence.batch` 的 10 键计数与 `batch.settlement`（键集见 `2026-10-21-c1b-treatment-adjudication.md` §3.2）；`status ∈ {partial, unreadable}` 或 `skipped_lines>0` / `invalid_lines>0` / `truncated>0` → 该 run 记 **instrumentation-degraded**，不并入 k≥3（与 task-7 §8.2 同口径）。
- 不加锁的理由：`append_target` 在每个写类 pre 之后调一次，属于热路径；加锁要新的性能基线（现有预算是 `pre_evidence.timeout_ms + timeout_ms < hooks timeout`，批次读取已在其中），Windows 上跨进程锁还会引入锁序/权限问题；而它只影响可观测性，不改变 allow/block 的安全性质。
- 触发升级：任一次真机出现同会话并发追加的现场（`skipped_lines>0` 或 `partial`/`unreadable`），或 k≥3 轮里同题两次 run 的批次读数不稳定 → 单开一轮做锁 + fsync + 性能基线。

**会不会影响 k≥3 的批次读数：会，方向是偏严。** 并发导致成员**变少** → `changed_files` 收窄 → 更容易 `TESTING-002` 失败关闭/更容易 block；它不会把 block 洗成 allow。所以污染的是「治理强度/任务能否完成」的过程读数，不是「越权放行」的安全读数。评分（T/C/A）只读最终树（05 §5.3），批次并发不直接进分数；但它让模型多被拦一次 → 多耗步数/可能熔断 → 通过 T 间接影响分数，因此必须按上面的 degraded 标记处理。

### 2.5 部署复制与重审

**裁决**：每个实验臂/受治项目各自持有一份**带 governed-dev 的 registry 1.4 本地副本** + **自己那份**已审核哈希；仓库 `registry/**` 与 `adapters/**` 一个字节不动。

| 项 | 取值 | 依据 |
| --- | --- | --- |
| 用哪份注册表 | `examples/dsh/b-plan/tool-registry.local.yaml`（`registry_schema_version: 1.4`；`governed-dev: [repo.read, repo.write, shell.exec]`；`read_guard` / 三个受保护前缀 / 三族 / 三个默认值与仓库 1.4 逐字相同） | 04 5.82 的结论：仓库版没有 governed-dev，用它会让每个写/执行 `permission_denied`（A 首跑作废，D-20261020-01）；同步与复核读数见 `readings/2026-10-21-registry-1.4-registry-sync.md` §1 |
| 不动的 | 仓库 `registry/tool-registry.yaml`、`registry/tool-registry.approved.json` | AGENTS 13。本轮实测仓库 `registry --verify` **exit 0、10 工具 ok**（作为「没被我们动过」的对照读数） |
| 审核人 | `--reviewer dshznm`（单人自审）；`approved.json` 的 `reviewed_by` 就是它（`registry/tool-registry.approved.json:7`） | 04 5.38：记在案、不假装第三方；读数必须写「单人自审，不是第三方复核」；`2026-10-21-new-session-prompt.md:82` 同口径 |
| 条子 | **只能使用者签**；代理不得自签（AGENTS 14；交接提示词 §4 第 4 条） | 每项目一份 `approval.json`，不跨臂复制；sha256 进冻结记录（05 §3.6；10-20 轮 A `d53f0d99…` / B `346f35c2…`，`2026-10-20-D-gate2-ab-c-runs.md:5`） |

**步骤与命令模板（占位符写清；`<reviewer>` 本机为 `dshznm`）**

```powershell
# T0 装配 + 注册表重审（自审记录；不签条子）
Copy-Item <workspace>/examples/dsh/b-plan/tool-registry.local.yaml <governed>/.policy/
Copy-Item <workspace>/examples/dsh/b-plan/dsh-adapter.yaml <governed>/.policy/   # 改 project_root / rules / rules_root / agent_version / pre_evidence / batch_ledger
Copy-Item <workspace>/examples/dsh/b-plan/hooks.json <governed>/.policy/
python -m enforcement.cli registry --registry <governed>/.policy/tool-registry.local.yaml --approved <governed>/.policy/tool-registry.approved.json --approve --reviewer <reviewer>
python -m enforcement.cli registry --registry <governed>/.policy/tool-registry.local.yaml --approved <governed>/.policy/tool-registry.approved.json --verify
python tools/approval_allowlist_audit.py --check --registry <governed>/.policy/tool-registry.local.yaml --approved <governed>/.policy/tool-registry.approved.json

# T1 命令类条子（按族；由使用者执行）
python -m enforcement.cli approve --registry <governed>/.policy/tool-registry.local.yaml --approved <governed>/.policy/tool-registry.approved.json --request <workspace>/examples/dsh/b-plan/shell-request.json --out <governed>/.policy/approval.json --granted-by <reviewer> --roles reviewer --binding pattern --family exec.pwsh:tests --param-pattern "description=.*" --max-uses <N> --ttl <seconds> --approval-id <approval-id>

# T2 PTC 传输工具（桌面端会话才需要；与 T1 并入同一个 approval.json，互不挤占）
python -m enforcement.cli approve --registry <governed>/.policy/tool-registry.local.yaml --approved <governed>/.policy/tool-registry.approved.json --request <workspace>/examples/dsh/b-plan/run-code-request.json --out <governed>/.policy/approval.json --granted-by <reviewer> --roles reviewer --binding pattern --param-pattern "code=(?s).*" --param-pattern "description=.*" --max-uses <N> --ttl <seconds> --approval-id <approval-id>
```

- 占位符：`<governed>` = 受治项目根；`<workspace>` = 本仓库；`<reviewer>` = 自审人（本机 `dshznm`）；`<N>` / `<seconds>` / `<approval-id>` 由使用者定。
- `--family` 只认注册表声明过的族（`exec.pwsh:tests` / `readonly` / `scripts`）；族级 `--check` 是权威口径（04 5.83④）。
- `code=(?s).*` 必须带 DOTALL（`examples/dsh/b-plan/README.md:85-86`）；1.3 参数域下省略 `timeoutMs` / `workdir` / `run_in_background` 仍覆盖「不传或恰好等于默认值」，非默认值照样拒（同文件 `:105-119`）。
- 到期必须显式重签，不静默续期（05 §3.6）。

**记录**：每臂 `adapter_config.sha256` + `registry_digest` + `approved.reviewed_by`/`approved_at` + `approval.sha256` 进 `platform_generation`。**旧案例不可重建**：10-20 轮的臂注册表 `e8bc569b…` 在当前树已不存在（现 1.4 副本 `120474c8…`），只能读 digest、不能重放。

## 3 冻结清单（必须进 run 产物的字段）

**落点**：全部并入 task-7 的 `platform_generation` 一个顶层字段（一次升版）；`arms` 的输入文件与 run 报告的 `reading_context` 只做**同一事实的副本**，不另立格式。

| 字段 | 取值来源 | 为什么必须记 | 缺了会怎样 |
| --- | --- | --- | --- |
| `host.entry` | 启动 argv / profile（headless / desktop） | 「哪条入口」决定是不是产品真实形态 | 与 05 §1 的目标无法对齐 |
| `host.dsh_runtime` | `<install>/resources/runtime/cli/bin/dsh.cmd --version` | 05 §5.4 的宿主同一性 | 宿主跨臂不同无法被检验 |
| `host.dsh_source` + `host.dsh_entry`（token） | 启动 argv | 同名两版本（PATH 与 app 自带）必须分得开 | 两条线被读成同一条 |
| `host.profile` + `launch.patch` | 启动 argv（C 臂必须 null） | 治理是否挂上 | C 臂「不治理」无法自证 |
| `host.file_policy` | 控制器会话（本机 danger-full-access） | Hook 能否 spawn | 把跑不成读成通过 |
| `host.session_sandbox` | dsh session log 的 `sandbox/mode` | 会话内工具行为 | 会话形态不可复核 |
| `reading_context.host.sandbox` | 证据（见 §2.2 第 4 条） | 三态口径 | 与模式混写成非法值/假值 |
| `declarations.adapter_config.digest`（+ `agent_version` 取值） | 受治项目 `.policy/dsh-adapter.yaml` 单文件 sha256 | 它覆盖 `into_decision` / `max_targets` / `registry_root` / `pre_evidence`，且 `agent_version` 进 `action_hash` | 审计与真宿主可能说两句话；旧记录完全没有 |
| `declarations.registry.digest`（+ `registry_schema_version`） | 受治项目 `.policy/tool-registry.local.yaml` | 注册表是判定数据 | 旧案例的 `e8bc569b…` 已不可重建 |
| `approval.sha256` | 受治项目 `.policy/approval.json` | 条子是构造的一部分 | 「这次为什么能跑」不可复核 |
| `batch_ledger.enabled` / `into_decision` / `max_targets` / `ttl_hours` + `BATCH_LEDGER_SCHEMA_VERSION` | adapter 配置 + 常量 | T3 的代际证据 | 旧案例的批次行为不可复现 |
| `AUDIT_SCHEMA_VERSION`（观测值） | 审计记录 | 1.5 是 T3 的协议证据 | 旧记录 1.4 与 1.5 混读 |
| `pre_evidence.enabled` / `pre_evidence.timeout_ms` / `timeout_ms` / `hooks_timeout_ms` | 配置 + `hooks.json` | 预算不等式 | 批次/取证是否在预算内不可证 |
| `model.id` + 参数（+ 首消息 sha） | 会话 header / 启动参数 | **05 §5.4 同时点名单变量是「宿主**或**模型」** | 现在没有任何产物记它 → 「同一模型」只能靠人记得 |
| `start.head` + `start.worktree_clean` | **run 之前**生成一份起点清单 | 旧 manifest 的 `head` 是**生成时点**（三份都是 `34b153c`，而案例读数写 run 起点 `889c97c`） | 起点锁被误读成 run 起点 |
| `run.serial`（`ci_local_lock_held=false`、`concurrent_sessions=1`） | 开跑前检查 | §2.4 的串行约束 | 并发污染无法识别 |
| 观测的批次计数 | 每条判定的 `pre_evidence.batch` + `batch.settlement` | degraded 判据 | 进程读数被当成干净 run |
| `test_layout_sha256` | 每臂实际 `validation/test-layout.yaml` | A/B 的唯一实质差异（task-7 §4.1） | treatment 对照不可证 |

**升版口径**：以上字段集体进 `platform_generation` → `RUN_MANIFEST_SCHEMA_VERSION` 1.0→1.1（AGENTS 55），同批评分器冻结块 version 2→3、重生成 `scorer/manifest.sha256` 并重冻；旧 manifest 内嵌的旧组合摘要因此全部失效（task-7 §4.2 已给同一口径）。**不**另加第二个顶层字段。若 Lead 选择「只写 arm-facts」，必须在 05 §8 显式写「manifest 不自足、消费方要信任一个未进 17 字段契约的旁文件」——这是 task-7 已判为不推荐的形态。

## 4 作废面（这项决定让哪些既有读数不再可引用）

| 既有读数/产物 | 为什么不引用 | 处置 |
| --- | --- | --- |
| `runs/2026-10-20/{A,B,C}/run-manifest.json` + `readings/2026-10-20-D-gate2-ab-c-runs.md` | alpha.2、AUDIT 1.4 / 账本 1.0、无 batch 字段、无 adapter/registry/approval digest、`head` 是生成时点 | 作废为**新冻结的对照**；A/B 重跑；C 若题库/宿主变也重跑（task-7 §5.1 同） |
| 旧 M5b activation（`readings/2026-10-19-D-gate2-treatment.md` §2.3.5；`examples/dsh/b-plan/a3-task-v3/README.md` §3） | 单文件判定口径的产物；T3 下批次会把测试带进 changed | 机制保留，**end-to-end activation 作废**，须在冻结配置 + 新题库上重证 |
| 10-20 A 的 post 分布 | 只对「执行过的动作」可用；block 的回声无法从旧读数里分离 | 新报告按 pre decision 分列 post 计数 |
| R-SYNC-01 §2.2/§2.3 的 workspace-write 三例 | Hook spawn EPERM，`.policy/` 0 条审计 | 保持**跑不成**（原文已写明），不得读成「平台没拦住」 |
| `adapters/host-versions.observed.json` 的 alpha.2 | 它是 CLI 线，不是 run 宿主 | 保持有效；**不得**当 run 宿主冻结 |
| 10-20 臂注册表 digest `e8bc569b…` | 当前树只有 1.4 副本（`120474c8…`） | 旧案例只可读 digest、不可重放 |
| R-SYNC-01 §4 的 `host.sandbox=restricted` | 那是 EPERM 轮的形态读数 | 四例复跑的 run 应记 `unrestricted`；两者不可混 |
| 任何把 `post_error` 当「事后失败」的计数 | 见 §2.3 | 重读为「被拒调用的事后回声」 |

## 5 需要使用者 / Lead 立刻做的事

| # | 谁 | 动作 |
| --- | --- | --- |
| 1 | 使用者 | 确认冻结 **rc.2**（app 自带），并在 run 窗口内**关闭 app 自动更新**（或在每次 run 前后核对 `--version`）。只有你能保证窗口内宿主不变。 |
| 2 | 使用者 | 按 §2.5 的 T1/T2 模板给每个受治项目**签条子**；T0 的注册表自审命令也应由你执行或明确授权——代理不得自签（AGENTS 14）。 |
| 3 | Lead | 在 05 §8 新增一条冻结记录（本文五项 + task-7 的 T3），并在 04 更新 5.81 / 5.82 / 5.88 / 5.90 的状态列（只改状态与指针，不改历史读数）。 |
| 4 | Lead | 把 task-7 的 `platform_generation` 与本文 §3 的宿主/沙箱字段合并成**一次**升版（RUN_MANIFEST 1.0→1.1、评分器冻结块 version 2→3、重生成 manifest），并在任何 k≥3 run **之前**完成。 |
| 5 | Lead | 在 D 开跑前清单里加三条：run 前查 `.tmp/ci-local.lock`（不删）；一次一臂一 run、同一受治项目一次一会话；run 报告按 pre decision 分列 post 计数并写 `host.sandbox` 三态 + `file_policy` / `session_sandbox`。 |
| 6 | Lead | 决定 5.90 的时机：**推荐实验后修**；若决定现在修，必须在任何 k≥3 run 之前落地并重跑门——轮中换反馈通道 = 05 §5.4 的作废。 |

## 6 三个最大风险（给评审）

1. **冻结不可自证**：17 字段里没有宿主、模型、adapter 配置、注册表、审批——本轮的「同一宿主/同一模型」只能由旁文件与散文支撑。若不在 run 前完成一次显式升版，§5.4 的两个单变量（宿主、模型）**都不可证**。
2. **换代与 5.90 是同一件事的两面**：从 alpha.2 换到 rc.2 本身就要重跑校准门；而 `post_error` 回声在 10-20 A 的 post 分布里读不到、现场审计又被清空 → 「换代是否改变反馈」没有对照。若在轮中修 5.90，反馈通道变化会让前后轮不可比；若不修，必须在读数里把它写成 treatment 反馈的一部分。
3. **T3 + 串行约束的执行纪律**：批次进判定后，并发追加会让 `changed_files` 收窄（偏严），而这种偏严在两次同题 run 之间不可归因给 treatment；只要有一次 run 与 `ci_local` 或第二个会话重叠，k≥3 的批次读数就不能合并。

## 7 复审条件与触发

- **宿主**：app 或 PATH `dsh` 任一升级/降级 → 冻结失效（新轮）；run 窗口内自动更新 = 「外部改动」→ 该 run 作废。
- **沙箱**：任一次 run 出现 spawn EPERM / 工作区外被拒的证据 → 该 run 记跑不成；连续两次 → 冻结形态需重裁。
- **5.90**：k≥3 轮关闭后的下一轮立项（不早于本轮读数冻结）；若轮取消，可提前修。修时按 `AUDIT_SCHEMA_VERSION` 升版并补 §2.3 的用例。
- **5.88②**：任一 run 出现 `skipped_lines>0` / `partial` / `unreadable`，或同题两次批次读数不稳定 → 单开一轮做锁 + fsync + 性能基线。
- **部署**：registry 再变 → 重审 + 重签；出现第二评审人 → 按 AGENTS 38 重跑 review；2026-12-31 统一复审并入。
- **模型**：k≥3 开跑前仍没有模型身份字段 → 该轮不得写「同一模型」（05 §5.2/§5.4），只能写「未记录」。

## 8 证据指针与复现命令

**本轮实测命令（只读；路径已 token 化）**

```powershell
# 1) PATH 上的 dsh（命名要写清，不然会被读成「本机只有一条线」）
Get-Command dsh            # => <npm-global>/dsh.ps1
dsh --version              # => 0.2.1-alpha.2
# 2) app 自带 CLI 与桌面端外壳
& '<install>/resources/runtime/cli/bin/dsh.cmd' --version   # => 0.2.1-rc.2
(Get-Item '<install>/DeepSeek Harness.exe').VersionInfo.FileVersion   # => 0.2.1-rc.2
# 3) host-version 的两种非写形态（AGENTS 54：四种形态互不代替）
$env:PYTHONPATH='src'; python -m adapters.cli host-version --record-check   # exit 0，match 1/3
$env:PYTHONPATH='src'; python -m adapters.cli host-version                  # exit 0，声明=宿主=记录
# 4) 仓库注册表未被改动（对照用；不是本轮改动）
$env:PYTHONPATH='src'; python -m enforcement.cli registry --verify          # exit 0，10 工具 ok
# 5) 两处配置的当前摘要（证明 10-20 轮的臂配置不可重建）
Get-FileHash -Algorithm SHA256 examples/dsh/b-plan/tool-registry.local.yaml # => 120474c8…
Get-FileHash -Algorithm SHA256 examples/dsh/b-plan/dsh-adapter.yaml         # => 66bc586e…
```

**文件指针**

- 宿主声明与读法：`adapters/dsh/manifest.yaml:19-21`、`:24`、`:72-75`；`adapters/host-versions.observed.json:3-13`；`src/adapters/cli.py:18-28`、`:746-875`（四种形态与退出码）。
- run 产物缺宿主：`testing/ab/dgate2/run-manifest/README.md:18-36`、`:61-78`；`runs/2026-10-20/A/arm-facts.json:7-9`；`runs/2026-10-20/A/run-manifest.json:20-25`；`c-arm/README.md:207-209`、`:235-238`。
- 沙箱：`readings/2026-10-21-registry-1.4-registry-sync.md:83-93`、`:98-108`、`:110-131`、`:180-181`；`06-plan-progress.md:231`；`2026-10-21-new-session-prompt.md:18`、`:20`；`src/provenance/reading_context.py:147-154`、`:390-424`；`src/adapters/dsh/hooks.py:1201`。
- 5.90：`src/adapters/dsh/enforcement.py:295-301`、`:303-340`、`:388-410`；`src/adapters/dsh/hooks.py:2546-2557`、`:2559-2564`；`src/enforcement/precheck.py:1331-1345`、`:1412-1427`；`src/enforcement/audit.py:203`、`:374`；`04-open-work.md:287`、`:317`；`readings/2026-10-21-registry-1.4-registry-sync.md:122-124`、`:190`。
- 5.88②：`src/adapters/dsh/batch_ledger.py:11-23`、`:70-71`、`:285-304`、`:317-325`、`:342-382`；`04-open-work.md:315`；`readings/2026-10-21-c1b-treatment-adjudication.md` §3.2、§4.1、§8.2。
- 部署：`examples/dsh/b-plan/tool-registry.local.yaml:49`、`:69`；`examples/dsh/b-plan/dsh-adapter.yaml:9`、`:43-46`、`:51-55`；`examples/dsh/b-plan/README.md:74-76`、`:85-86`、`:105-119`、`:135-143`；`registry/tool-registry.approved.json:7`；`04-open-work.md:264`、`:309`；`2026-10-21-new-session-prompt.md:82`。
- 两版本副本的契约缺口：`tests/contract/test_dsh_layer_declaration.py:25`、`:47-60`（只钉 `examples/dsh/dsh-adapter.yaml`）。

## 9 给 Lead 可直接抄进 04/06 的短句

**04 5.81（一行，追加）**：实验冻结的宿主是 **app 自带 dsh 0.2.1-rc.2**（`<install>/resources/runtime/cli/bin/dsh.cmd`，桌面端外壳同版本）；PATH 上的 0.2.1-alpha.2 只作 A3 干跑与 10-20 n=1 的**案例宿主**，两者不得合并；`host-version` 记录仍是 CLI 线（alpha.2），**不回答** run 宿主——run 宿主由 `platform_generation.host` 记。

**04 5.88（一行，追加）**：批次并发按**串行 run** 处置（一次一臂一 run、同一受治项目不共用、与 `ci_local` 互斥）；账本仍无锁/无 fsync，`partial`/`unreadable`/`skipped_lines>0` 的 run 记 **instrumentation-degraded**、不并入 k≥3；要锁/fsync 单开一轮并给性能基线。

**04 5.90（一行，追加）**：5.90 在冻结窗口内**接受为已知边界**（审计 `reason_code` 为读数依据，模型侧 `post_error` 回声不作为读数）；实验后按 (b) 修（回放 pre 理由、`AUDIT_SCHEMA_VERSION` 1.5→1.6、新 `stage_note`），(c) 插件抑制不采纳。

**05 §8（新增一条）**：D 门 2 冻结五项——宿主 = app 自带 dsh 0.2.1-rc.2；控制器/测量进程 = danger-full-access 且会话沙箱每轮固定并记录；5.90 接受为边界；批次并发串行处置；每臂 registry 1.4 本地副本 + `dshznm` 自审 + 使用者签条子；仓库 `registry/**` 与 `adapters/**` 不动。旧 alpha.2 n=1 作废为新对照；宿主/沙箱/配置/审批/模型字段并入 task-7 的 `platform_generation` **一次**升版（RUN_MANIFEST 1.0→1.1、评分器冻结块 version 2→3）。

**06（一条，可拆两行）**：D 门 2 冻结项已裁决（task-6）：宿主 rc.2 / 控制器 danger-full-access / 5.90 接受边界 / 批次串行 / 部署副本+自审；**旧 alpha.2 n=1 不并入 k≥3**；改版前先完成 `platform_generation` 升版与 D 校准门在 rc.2 的重跑。
