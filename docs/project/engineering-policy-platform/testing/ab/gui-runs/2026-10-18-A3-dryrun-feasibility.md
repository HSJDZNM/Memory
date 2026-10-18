> 来源：`.tmp/a3/A3-REPORT.md`（正文保持原报告；§10 是归档时补入的 R-1 复核结论）。
> 归档时间：2026-10-18。
> 本文件是 06 P-A3-001 / D-20261018-01 的证据落点（`.tmp` 产物会被 `tools/cleanup.py` 删除，不能长期复核）。
# A3 干跑四数 · 可行性侦察报告（task-3）

> 执行者：a3-dryrun-recon（本会话 DSH session `98ecab06-1a3a-4bcd-849a-dbb094fc03db`）
> 读取时刻：2026-10-18T08:33–09:10 +08:00（00:33–01:10Z）；起点 HEAD `6167fad`（读取时工作树已被并行 A1 改动，见 §6）
> 写区：仅 `.tmp/a3/`；未改任何仓库文件、未动 allow/block、未跑 `tools/ci_local.py`。

## 1. 三态总判定

**跑不成（A3 干跑今天不能产出四数）** —— 不是通过，也不是「不符合」。

- A3 要求「受治臂跑一遍任务」；今天**没有可跑的构造**：无 A3 任务包（B-3）、当前会话不受治（B-1）、
  受治项目审批 3/3 已过期（B-2）、受治树不是已知基线且不可完整枚举（B-4）。
- 四数的**仪器**并非全不可用：③（layer 表）与 ④（会话日志）可以直接复算；① 有计算函数但缺输入装配与口径；
  ② 无计算函数、缺命令族定义。在**旧受治会话**（`session-0ec9c5e0…`，2026-10-11T18:52Z 批次）上，
  四数都能用自写只读脚本复算出**代理读数**（§3）；它们**不是 A3 读数**，不占绿也不占红。
- 因此更精确的表述：**A3 跑不成；四数的仪器部分可用**。A3 门（05 §4 A3 行、§5.6 的 4/4）**未达成**。

## 2. 输入核实（命令 + 退出码 + 文件证据）

### a) 受治臂是否存在 / 当前会话是否受治

命令（在 `C:\Users\ZNM\Downloads\Memory`，`$env:PYTHONPATH='src'`）：

    .\.venv\Scripts\python.exe -m adapters.cli wiring            # exit 0
    .\.venv\Scripts\python.exe -m adapters.cli wiring --check    # exit 1

读数（2026-10-18T08:33Z 与 08:59Z 两次，声明被 A1 并行改动过，见 §6）：

- 全局：接线成立 **5/7**；留痕新鲜 **0/7**；`result=fail`（--check → exit 1）。
- `dsh:desktop`：`wiring_status=wired` / `freshness_status=never_written` / `status=audit_never_written`；
  它解析出的审计目标是 `<external>/audit.jsonl`（`audit_records=0`），**与真实受治账本不是同一个文件**
  （存量 datapack D7 已登记这条差异）。
- `dsh:governed`：`wired` / `stale`：`audit_records=168`，最后一条 `2026-09-26T12:27:10.904188Z`，
  距当时 1,857,972s > 604,800s。`dsh:governed-grade*` / `wmsvc` 同为 stale。

**真实受治账本**：`C:\Users\ZNM\Downloads\Comparison-test\Governance\.policy\audit.jsonl`
（2026-10-18 仍在增长；本报告读取期间 15,014 → 15,421 条）。其中：
`governed=true` 共 **127** 条，最后一条 **2026-10-11T18:53:33.511993Z**；
`session_scope=outside_project` 共 **14,515** 条，最后一条 **2026-10-18T00:57:20.679289Z**。
⇒ 2026-10-12 起**没有**任何受治动作，只有范围外留痕（「没管」不是「判定通过」）。

**当前会话是否受治**——依据三条，不靠猜：

1. `Test-Path .policy` → `False`（本会话工作区 Memory 没有 `.policy/`；受治配置在 Governance 工作区）。
2. 桌面 profile 的桥配置：`$DSH_HOME/profiles/desktop/cordis.patch.yml:300-307`，
   `policy-hook.plugin.mjs` 的命令带 `--config .policy/dsh-adapter.yaml --hooks-config .policy/hooks.json`，
   `projectDir: 'C:/Users/ZNM/Downloads/Comparison-test/Governance'`；Hook 按**会话 cwd**判定范围
   （`src/adapters/dsh/hooks.py:687-708`）⇒ cwd=Memory 必然 `session_out_of_scope`。
3. 审计里有本会话记录：`session_id=98ecab06-…`、`action_id=…:call_00_CtM4w1e4m4DH9bYq4tCL8438:ptc:3`、
   `timestamp=2026-10-18T00:36:21.461224Z`、`reason_code=session_out_of_scope`、
   `session_scope=outside_project`、`governed=false`、`session_cwd=<outside-workspace>`；
   同一 call 组可由本会话 session 记录的 `job/registered.owner=98ecab06-…` 对上。

⇒ **当前会话不受治**：桥在跑（每次工具调用都被 Hook 看到），但这次调用**没被判定**。

### b) 审批

`Comparison-test/Governance/.policy/approval.json`：`schema_version=1.2`，**records=3**；
覆盖 `exec.run_code`（code/description 两模式）+ `exec.pwsh` pytest 族 + `exec.pwsh` git 只读族。

| approval_id | tool_id | expires_at | 现在（2026-10-18T01:06Z） |
| --- | --- | --- | --- |
| approval-run-code | exec.run_code | 2026-10-17T23:38:27.513467Z | **已过期** |
| approval-pwsh-tests | exec.pwsh | 2026-10-17T23:59:00Z | **已过期** |
| approval-pwsh-readonly | exec.pwsh | 2026-10-17T23:59:00Z | **已过期** |

命令：`.\.venv\Scripts\python.exe .tmp\a3\final_evidence.py` → exit 0，逐条给出 `expired True`。
05 §3.6 的「今天到期」与文件一致；**今天（10-18）已全部过期**，任何受治命令都会先撞审批层
（`src/enforcement/approvals.py:519-520` 的「审批已过期」；L4/L5 旧读数亦为 `approval_invalid`）。

仪器旁证：`python tools\approval_allowlist_audit.py --approval … --registry … --approved …` → exit 0，
`HITS: 13 / allowlisted_prefix_without_a_ticket=13 / tools=2 patterns=2`。
**但这条读数有仪器缺陷**：它按「每条记录 × 白名单」比对，1.2 多记录下会把已被另一条记录覆盖的
`^python -m pytest` 也算成缺口（见 §7 风险 R-2）；单记录副本实测 12 命中，两记录副本 13 命中。

### c) 任务包 / 预注册

- 仓库内**没有** A3（或阶段 D）形状的任务包。`git ls-files` 计数：`examples/dsh/b-plan` 18 个、
  `docs/.../testing/ab` 16 个。最接近的两个候选都不是：
  - `examples/dsh/b-plan/comparison-task.md`（278 行）：**12 条探针消息**的发送包，M1 只改 3 个文件、
    明确「不要动 tests/、不要执行命令」，无 §5.2 的「既有+新增测试」「岔口」「参考解」；
  - `testing/ab/task-sets.md`（外部 SWE-bench 任务集）：9 个受测实例里**只有 2 个**通过全判据
    （`sympy__sympy-22456`、`sympy__sympy-22714`），且面向三臂矩阵、需额外依赖/钉死 venv；
    其树在 `.tmp/ab-tasks/`（gitignored、cleanup 会删，不能当预注册）。
- 全仓 grep「任务包」只命中 `05-implementation-plan.md` 的 A3 行本身。⇒ A3 的「需要一份任务包」仍是空。
- 05 §5.2 的任务形状（≥3 层、≥6 文件、≥2 个既有文件被改、既有+新增测试、岔口、无网络/随机/时钟、
  参考解 ≤90 分钟、固定首条消息/接口签名/验收表/允许写路径集合/里程碑顺序）没有任何一份已写死的实例。

### d) 四数的可计算输入

**目标任务的文件变化与写动作：没有。** 审计里最后的受治 write/edit 判定记录在
`2026-10-11T18:52:54.949802Z`（27 条记录 / 7 个文件）；`governed=true` 的最后一条在
`2026-10-11T18:53:33.511993Z`，2026-10-12 起**没有新增任何受治记录**（新增的全部落在
`outside_project`）。没有任何目标任务的文件变化或写动作记录。Governance 树现有的
`NOTES.md` 与 `tests/test_order_service.py` 差异来自 10-11/10-12 的旧 run，不是 A3 任务。

- **审计**：`write`/`edit` 带结构化 `file`/`layer`/`decision` 的记录共 **27 条 / 18 个 action_id**
  （每个动作 2 条 PreToolUse + 1 条 PostToolUse；去重必须按 action_id）；decision 分布
  block 9 / allow 10 / allow_with_warnings 8；涉及 7 个文件。`PostToolUse` **没有** `file` 键；
  被 `context_error` 拒收的写（如 `config/bad.yaml`）**没有结构化 file**，路径只在 `detail` 文本里。
- **命令族**：审计记录**没有命令原文**；`reason_code` 只能还原每次尝试的结果，不能还原「属于哪个族」。
  可用 `session` 记录的 `tool/ptc-dispatch*.arguments.command` 与 audit `action_id` 的 `:ptc:N` 对齐
  （本报告已用旧会话验证：11 次 `pwsh` PreToolUse 全部对上命令原文）。**因此「reason_code 单独还原首次通过率」
  不成立；正确的读法是 session args（命令原文）+ audit reason_code（每次尝试结果）按 action_id join，
  且「族」与「首次」必须预注册。** `enforcement-ledger.jsonl`
  的 `pre_state.request` 只在进入 Phase 4 的记录里有命令（552 条中 pwsh 部分覆盖，前面几层拒绝的没有）。
- **路径族 layer 表**：受治项目的 `.policy/dsh-adapter.yaml:16-32` 是**唯一**表：
  6 条 glob（tests/**、*_controller.py、*_service.py、*_repository.py、*.py、*.md），
  `test_paths` / `test_layer` 声明，**无 default_layer**；平台级「哪些路径算测试」在
  `validation/test-layout.yaml:21-23`（test_patterns），两者必须解得通（AGENTS 41/49）。
  它不是 A1 的 `validation/channel-coverage.yaml`（那是 channel × tool × mode 的覆盖账，不是 layer 表）。
- **上下文触顶**：从 DSH session 日志读：`request/context.contextWindow`（旧会话 1,000,000；
  本会话 1,048,576）、`request/header.config.maxTokens`（256,000）、`assistant/message.usage`
  （inputTokens/cacheReadTokens/cacheWriteTokens）、以及只进日志的压缩事件
  `compaction/start|end|summary`（`dsh-compaction` 包文档；桌面 profile 已挂
  `compaction-basic` + `command-compact` + `tool-result-pruner`，patch:166-178）。
  默认自动压缩阈值 = `floor(min(W*0.8, W−O−B))`，B=65,536 ⇒ W=1e6 时 **678,464 tokens（67.85%）**；
  旧会话峰值 47,019（4.70%）与 113,775（11.38%），本会话 234,665（22.38%），**均无 compaction 事件**。

## 3. 四数逐条：现在能不能产出

| 数 | 现在（A3 任务）能否产出 | 缺什么 | 旧会话代理读数（非 A3 读数） |
| --- | --- | --- | --- |
| ① 写动作治理覆盖率 | 不能 | 受治 run + 装配器 + 「实际文件变化」口径裁定；`ab_measure.automation_from` 只吃 `--actions` / `--runs.counts`，仓库无 audit→actions 装配器 | 1/1 = 100%（树变化只有 NOTES.md，有 PreToolUse allow+executed 记录）；pycache / pytest-cache 等命令副作用未计入 → 记 unmeasured 的一部分 |
| ② 命令族成功率 | 不能 | 受治 run + 命令族预注册 + 装配器；`reason_code` 单独还原不了族（需 session args 对齐） | 首次通过 **0/7 族**（各 0/1 或 0/2）；尝试级 2/11 = 18.2%；失败 7 次 `approval_invalid` + 1 组合阻断 + 1 白名单外 ⇒ 两个门槛同时不过 |
| ③ 路径族声明 | 能（真读数，作用于当前表） | 需要 A3 任务「写路径集合」才能给 A3 值 | 旧会话触碰 2 个族，只有 1 个有 layer（NOTES.md→docs；config/bad.yaml→无）= **50%**；样例项目 11 文件 10/11（pytest.ini 无映射），限定 src+tests+md 则 4/4 |
| ④ 上下文触顶 | 能（真读数，作用于已有会话） | 需要 A3 自己的 session 日志才能给 A3 值 | 未触发：compaction 事件 0，峰值 4.70% / 11.38% / 22.38% ≪ 67.85% 阈值 |

- ① 在 `ab_measure.py` 里的计算函数是 `automation_from`（L1913-2027），输入形状为
  `--actions`（`operation=write`、`governed=true`、`governance_status`）或 `--runs`
  （`counts.write_actions` / `governed_write_actions`）；没有输入时显式 `unavailable`。
  `.tmp/ab-arms/*/measurement_input.json` 是现有唯一真实输入：enforced 被阻断的 5 次 run 里
  `write_actions=0` 而 `governed_write_actions=1` ⇒ 覆盖率为 `None`（0 分母），与 A3 的
  「写动作 / 实际文件变化」不是一个口径。
- ② 的「首次通过」还缺粒度定义：一次调用内多次 `ptc:N` 算不算重试、跨消息同一命令算不算同族、
  「族」按 approval 记录还是 registry allowlist 前缀——都必须预注册，否则读数不可复算（06 A5 型要求）。

## 4. 阻断条件（每条带触发条件编号与复现）

- **B-1 当前会话不在受治范围（构造失败）**
  复现：`Test-Path .policy` → `False`；审计含本会话 `session_out_of_scope` 记录（见 §2a 的 action_id）。
  含义：A3 的受治臂必须在 workspace=Governance 的 GUI 会话里跑；本会话只能做范围外观测。
- **B-2 审批 3/3 已过期**
  复现：读 `approval.json` + 当前 UTC 比较（`.tmp/a3/final_evidence.py`，exit 0）；受治命令必得
  `approval_invalid`。⇒ ② 的「失败原因不全是 approval_invalid」也不可能满足。
- **B-3 无 A3 任务包 / 预注册**
  复现：`git ls-files`（18 / 16 个文件）与 `comparison-task.md` / `task-sets.md` 逐条比对 §5.2；无匹配文件。
  触发 05 §4 A3 行「需要一份任务包」的缺口；没有它，「任务路径」「命令族」「触碰路径」都无定义。
- **B-4 受治树不是已知基线、且不可完整枚举**
  复现：`Get-FileHash` 对比 sample-project → `ONLY_GOV: NOTES.md`、`DIFF: tests\test_order_service.py`；
  `Get-ChildItem …\Governance -Recurse` → 4 个 `pytest-cache-files-*` 目录 `UnauthorizedAccessException`
  （另有 `__pycache__`）。⇒ 起点 sha256 作废条件与 ① 的分母都不成立；R0 重置 + ACL 清理需要人。
- **B-5 ① 的输入装配与口径缺失**
  复现：`grep governance_status` 只命中 `tools/ab_measure.py`（无生产者）；审计写记录 27/18 去重问题、
  `context_error` 写无结构化 file；`ab_arms` 被阻断 run 的 `write_actions=0`。
- **B-6 ② 的定义/仪器缺口**
  复现：`grep command_famil` 在受治 `tool-registry.local.yaml` 无命中（B1 才新增 `command_families`）；
  `approval_allowlist_audit.py` 在多记录 1.2 下 per-record 误报（见 §7 R-2）。

## 5. 最小解冻清单（按依赖顺序，含人裁定项）

0. **人裁**：选定 A3 任务包并按 §5.2 写死（首条消息、接口签名、验收表、允许写路径集合、里程碑顺序、
   参考解）；同时预注册四数口径：① 分子/分母与排除清单、② 命令族来源与「首次」粒度、③「触碰=被写」
   且用 `.policy/dsh-adapter.yaml:layers` + `validation/test-layout.yaml`、④「触顶=compaction 事件或
   达到 threshold」及 W/O 取值来源。**没有这一步，后三步的读数不可复算。**
1. 在 Governance 工作区开一个 GUI 会话（受治臂）。当前 Memory 会话不可用（B-1）；
   即使 A1 把 `dsh:desktop` 声明改判 in_scope，Hook 仍按 session cwd 判定范围，改为声明不改变本会话的
   `session_out_of_scope`（声明≠运行时行为）。
2. R0 树重置：把 Governance 恢复为 sample-project（删 NOTES.md、还原 `tests/test_order_service.py`），
   清理 4 个 ACL 拒绝的 pytest-cache 目录与 `__pycache__`（**人**在普通 shell/修 ACL 后执行），
   记录起点 sha256 manifest、HEAD、`rule_set_hash`、账本起始偏移与三个 schema 版本（06 §2 起点锁）。
3. 重签 approval.json：按任务实际命令族与参数格签、7 天 TTL、记哈希。若不先做 B1，必须预注册
   「形状漂移属摩擦」；② 的 ≥90% 在 B1 之前大概率过不了 —— **需人裁定 A3 是否以 B1 为前置**
   （阶段 A 的冻结令不因「A3 只读」而降低 05 §5.6 的通过线）。
4. 只读装配器（不改 allow/block、不改退出码）：audit + 树 manifest + session args → 四数；
   放 `tools/` 属 A3 写区外（由 Lead 决定落点/是否豁免），或仅作 `.tmp` runbook 复算。
   同时决定是否修 `approval_allowlist_audit.py` 的 per-record 语义（B1 写区已含此文件）。
5. 执行 A3 干跑：受治臂跑一遍任务，前后各拍树快照，记录 audit/ledger 起止偏移与 session id；
   算四数；4/4 才进阶段 D，任一不过先修构造（05 §4 A3 门）。
6. 记录：按 §8 建议值写 06（P-A3-001 / D-20261018-01 / 可选 R-A-A3-01..04）。

## 6. 设计决定与偏差

- 全程只读；脚本与产物都在 `.tmp/a3/`；未改仓库文件、未动 allow/block、未改退出码、未跑 ci_local。
- 用**旧受治会话**做四数仪器代理读数，严格标注「非 A3 读数」，避免把「跑不成」写成「通过」。
- 为测 `approval_allowlist_audit.py` 的多记录语义，只在 `.tmp/a3/` 下复制 approval 记录（未改真实条子）。
- 侦察期间工作区被并行 A1 改动：`git status --porcelain` 显示
  `M adapters/wiring-scope.yaml; M tests/unit/test_control_plane_facts.py; M tests/unit/test_provenance_wiring_scope.py;
  M tools/control_plane_facts.py; M validation/control-plane-facts.yaml; M validation/instrument-checks.yaml;
  ?? validation/channel-coverage.yaml`。wiring 的 desktop `governs.decision` 在 08:33 仍是 `out_of_scope`，
  08:59 已随 A1 改成 `in_scope`；两次读数都保留在 `.tmp/a3/wiring.json` / `wiring-2.json`。
- 偏差：A3 原定「受治臂跑一遍」；因构造不成立，本次只交付可行性判定与仪器验证，不交付 A3 四数。

## 7. 未解风险

- **R-1（wiring 审计路径解析与运行时不一致）**：`audit_log: audit.jsonl` 运行时按 `.policy/` 基准解析，
  wiring 按 projectDir 解析 ⇒ `dsh:desktop` 报 `never_written`（0 条），真实账本却有 15,000+ 条。
  这不是「没留痕」，是**读错文件**；A1 的 coverage 声明文本（「记录 0 条」）需要同批更正。
  修复属 A1/平台，不在 A3 写区。
- **R-2（approval_allowlist_audit 多记录误报）**：1.2 一个 tool 多条记录时，工具对每条记录都要求
  覆盖整张白名单，B1 的「0 命中」门槛可能永远达不到（实测 13 vs 单记录副本 12）。修它属于 B1 的写区。
- **R-3（ACL 拒绝目录）**：Governance 下 4 个 `pytest-cache-files-*` 与 `.tmp/ab-pilot/poison2/...` 目录
  无法枚举（`Get-ChildItem -Recurse` / glob 报 UnauthorizedAccess），任何「全树哈希/差异」读数必须先
  显式排除或修复 ACL；naive 脚本会直接失败或漏文件。
- **R-4（共享账本）**：audit 是跨会话追加写，探测期间 15,014→15,421；A3 必须记起止偏移 + session_id，
  并按 action_id 折叠 pre/post/链侧三类记录（06 §4 的口径）。
- **R-5（`run_code` 旁路）**：`run_code` 的内部文件写入不经 Hook（gui-ladder §10 已登记「声明为不可结构化
  治理」）；若任务里模型用 run_code 写文件，① 的分母必须把这类变化记 unmeasured，不能当 100%。
- **R-6（上下文阈值随路由变）**：W 有 1,000,000 与 1,048,576 两种、O=256,000；阈值公式要按 session 读，
  不能写死 678,464。压缩是「按压力自动触发」还是「溢出后重试」两条路径，读数时要区分事件来源。

## 8. 建议 06 台账记录值（只给值，不写文件）

### 8.1 进度记录 P-A3-001

| 字段 | 建议值 |
| --- | --- |
| id | P-A3-001 |
| 时间 | 2026-10-18T09:10:00+08:00 |
| 阶段/任务 | A3 |
| 执行者 | a3-dryrun-recon（DSH session `98ecab06-1a3a-4bcd-849a-dbb094fc03db`） |
| 起点锁 | HEAD 6167fad；rule_set_hash sha256:73845ef515236940266b682631c02dec84c06886fa27a1e99f57e66284fae7d4；audit 1.3 / ledger 1.0 / approval 1.2；audit 起始 15,014 条（2026-10-18T00:37Z 读取），探测末 15,421 条 |
| 做了什么 | A3 干跑可行性侦察：受治臂、审批、任务包、四数输入；旧会话上复算四数仪器代理读数 |
| 结果 | 跑不成 |
| 证据指针 | `05-implementation-plan.md#L153`、`#L223-L230`；`examples/dsh/b-plan/comparison-task.md`；`docs/project/engineering-policy-platform/testing/ab/task-sets.md#L92-L104`；`Comparison-test/Governance/.policy/approval.json#L16-L17 / L37-L38 / L58-L59`；`…/audit.jsonl + 98ecab06-…:call_00_CtM4w1e4m4DH9bYq4tCL8438:ptc:3 + PreToolUse`；`python -m adapters.cli wiring` → exit 0（--check → exit 1） |
| 判据 | 05 §5.6（四数通过线）+ 05 §4 A3 行 |
| 偏差 | 无任务包，未跑受治臂；代理读数不等于 A3 读数 |
| 下一步 | 完成 §5 的最小解冻清单第 0 项（任务包与四数口径人裁） |

### 8.2 偏离/作废记录 D-20261018-01

| 字段 | 建议值 |
| --- | --- |
| id | D-20261018-01 |
| 时间 | 2026-10-18T09:10:00+08:00 |
| 事件 | A3 干跑构造失败，四数不产出 |
| 命中条件 | 构造失败 B-1..B-6（本报告 §4；对应 05 §5.6「开跑前」门） |
| 影响范围 | A3 四数不成立 ⇒ 05 §4 阶段 A 退出条件第三项未满足 ⇒ 阶段 D 不开跑 |
| 处置 | 改构造（补任务包、受治会话、R0 树、重签审批、只读装配器），不改判据、不改 allow/block |
| 证据指针 | 本报告 §2/§4（`05…md#L153`、`…audit.jsonl` action_id 上、`approval.json#L16-L17 / L37-L38 / L58-L59`、`…Governance/.policy/dsh-adapter.yaml#L16-L32`、`python -m adapters.cli wiring` exit 0/1） |

### 8.3（可选）读数记录 R-A-A3-01..04 —— **旧会话仪器代理，不构成 A3 四数**

| id | 读数名称 | 分母/口径 | 值 | 三态 | 备注 |
| --- | --- | --- | --- | --- | --- |
| R-A-A3-01 | 写动作治理覆盖率（代理） | L5-L8 旧受治会话树实际变化 1 个文件 / 有 PreToolUse 记录 1 次 | 1/1 = 100% | 符合（口径窄） | 不含命令副作用/pycache；非 A3 |
| R-A-A3-02 | 命令族首次通过率（代理） | 7 个族各取首尝试 / 11 次尝试 | 0/7 族；2/11 次尝试 | 不符合 | 7×approval_invalid；非 A3 |
| R-A-A3-03 | 路径族 layer 声明（代理） | L5-L8 写路径 2 族 | 1/2 = 50% | 不符合 | config/bad.yaml 无 layer；非 A3 |
| R-A-A3-04 | 上下文触顶（代理） | session `0ec9c5e0` 峰值 47,019 / 窗口 1,000,000 | 未触发（compaction 事件 0；阈值 678,464） | 符合 | 非 A3 |

## 9. 复现清单（本次实际跑过的命令）

    git status --porcelain                                         # exit 0
    Get-Date                                                       # 2026-10-18T08:33:40+08:00
    $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m adapters.cli wiring          # exit 0, result=fail
    $env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m adapters.cli wiring --check  # exit 1
    Test-Path .policy                                              # False
    .\.venv\Scripts\python.exe .tmp\a3\final_evidence.py           # exit 0, 3/3 expired
    .\.venv\Scripts\python.exe .tmp\a3\audit_time.py               # exit 0, 15,421 records / governed 127
    .\.venv\Scripts\python.exe .tmp\a3\write_records.py            # exit 0, 27 write records / 18 action_id
    .\.venv\Scripts\python.exe .tmp\a3\write_match_probe.py        # exit 0, NOTES.md 2 Pre + 1 Post
    .\.venv\Scripts\python.exe .tmp\a3\layer_and_context.py        # exit 0, 10/11, 1/2, 4/4; 47,019/113,775
    .\.venv\Scripts\python.exe .tmp\a3\cmd_join.py                 # exit 0, 11 attempts / 0-of-7 families first-pass
    .\.venv\Scripts\python.exe .tmp\a3\write_paths.py              # exit 0, 2 families / 1 mapped
    .\.venv\Scripts\python.exe tools\approval_allowlist_audit.py … # exit 0, HITS 13 (multi-record over-report)
    .\.venv\Scripts\python.exe .tmp\a3\wiring_summary.py           # exit 0, desktop wired/never_written, governed stale

所有 `.tmp/a3/*` 产物仅为复算证据，不提交、不是 06 §4 认可的「读数文件」落点；若要把本报告升级为
仓库读数，需由 Lead 决定写到已跟踪的 `docs/.../testing/ab/gui-runs/`（本任务写区外）。


## 10. 归档补充 · R-1 复核结论（2026-10-18）

**结论：同一份目标账本；wiring 的解析基准错了——不是两份账本，也不是「从没留痕」。**

- 运行时解析链（真实落盘）：`src/adapters/dsh/adapter.py:1004-1026` 用 `base_dir=config_path.parent` 载入配置；
  `_as_path`（`adapter.py:754-759`）把相对路径接到 `base_dir`；`audit_log` 在 `adapter.py:959-961` 走这条规则。
  配置 `Comparison-test/Governance/.policy/dsh-adapter.yaml` 的 `audit_log: audit.jsonl` ⇒ 运行时写
  `Comparison-test/Governance/.policy/audit.jsonl`（存在；核对时 15,421 条，含 `governed=true` 127 条；
  本会话的 pwsh 调用也以 `reason_code=session_out_of_scope` 记在这份文件里）。
- wiring 解析链（读错文件）：`src/adapters/wiring.py:1574-1581` 把 `bridge.projectDir` 放在候选基准第一位；
  `:1753-1758` 在钩子命令没有 `--audit` 时改用配置里的 `audit_log`；`:1406-1425` 的 `_resolve_ref`
  取第一个**存在**的候选，都不存在时返回第一个候选。桌面 profile 的两个候选
  `Governance/audit.jsonl` 与 `$DSH_HOME/profiles/desktop/audit.jsonl` **都不存在** ⇒ 返回
  `Governance/audit.jsonl`、`audit_records=0` ⇒ `freshness_status=never_written`。
- 只读复算（2026-10-18；Test-Path 与 wiring 报告均 exit 0，--check 见下）：`Test-Path C:/Users/ZNM/Downloads/Comparison-test/Governance/audit.jsonl`
  → `False`；`Test-Path C:/Users/ZNM/Downloads/Comparison-test/Governance/.policy/audit.jsonl` → `True`；
  `python -m adapters.cli wiring` → exit 0（dsh:desktop `audit_records=0` / `never_written`），
  `python -m adapters.cli wiring --check` → exit 1。直接调用两侧的解析函数：
  `adapters.dsh.adapter.load_config(<config>).audit_log` → `.../.policy/audit.jsonl`，而
  `adapters.wiring._resolve_ref("audit.jsonl", (projectDir, profile 目录), …)` → `.../Governance/audit.jsonl`
  （代码路径见上，两行都只读）。
- 影响：wiring 的留痕事实对「in-process 插件 + 配置里写 `audit_log`」这一种形状**系统性低估**；
  04-open-work §5.72 已登记。A1 的 `validation/channel-coverage.yaml` desktop 行的 reason 不能写「记录 0 条」，
  应写成「审计存在（15,421 条）、但 wiring 解析不到；见 04 §5.72」。
- 处置：**本轮只登记不修**。下一轮修 `wiring`（配置内的 `audit_log` 按配置文件目录解析，或把配置内引用统一交给
  `adapter.load_config` 解析）并同批改 coverage 文本；修之前，wiring 的 `never_written` 只能当「读不到」，
  不能当「没发生」。
- 边界：`dsh:governed` 的 `stale` 是另一件事（该 profile 自 `2026-09-26T12:27:10.904188Z` 起真的没有新记录），
  不要与 R-1 混读。
