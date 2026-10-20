# 2026-10-20 B3：只读命令族读面闸门（registry `read_guard`）

任务：共享任务 **task-3**（05 §4 B3 / 04 号 5.70；使用者已在 2026-10-20 会话授权解冻并执行改判定）。
执行者：子会话 b3-readguard。**未提交、未跑 `tools/ci_local.py`、未改 04/05/06/AGENTS/tools/README**。

## 0. 一句话

只读命令族的**读面**（命令文本里的路径操作数）此前不受任何范围校验：改前实测
`git show HEAD:.policy/approval.json` 与 `git log -p -- .policy/audit.jsonl` 在**真实 precheck CLI** 上
退出码 0、reason_code `allow`。本次把这条边界写成注册表数据（`read_guard`，注册表 1.1 → 1.2）并加一条
结构性检查（`read_guard`，新原因码 `read_guard_blocked`）。改后 8 条越界形态全部阻断、8 条合法只读命令
0 误伤、白名单外命令与被禁片段命令的 reason_code **一个字没变**。

## 1. 问题与改前读数

04 号 5.70：写类参数的路径走 `policy.context.repo_relative_path` 的范围校验，**命令文本里的路径操作数
不走那一层**。于是同一个文件有两条路——写被拦、读不被拦。

**改前实测**（不引用旧结论，现场重跑）：用 `git archive HEAD` 的副本（`registry_schema_version: "1.1"`、
无 `read_guard`）+ 真实 `enforcement.cli precheck`（dry_run，带一张 `exec.pwsh:readonly` 族级条子）逐条跑：

| 命令原文 | 退出码 | decision | reason_code |
| --- | --- | --- | --- |
| `git show HEAD:.policy/approval.json` | 0 | allow | `allow` |
| `git log -p -- .policy/audit.jsonl` | 0 | allow | `allow` |
| `git log -p -- ./.policy/audit.jsonl` | 0 | allow | `allow` |
| `git show HEAD:.POLICY/approval.json` | 0 | allow | `allow` |
| `git log -p -- ..` | 0 | allow | `allow` |
| `git show HEAD:..` | 0 | allow | `allow` |
| `git log -p -- C:/Users/ZNM/.ssh/id_rsa` | 0 | allow | `allow` |
| `git show HEAD:../Free/README.md` | 1 | block | `command_fragment_blocked` |

两条关键事实（与 04 5.70 的措辞对齐，也把落地差异写清）：

1. **信任根读取在改前完全放行**：`HEAD:.policy/...`、`-- .policy/...`、`./` 拼写、大小写变体、
   只写 `..` 的越界、宿主绝对路径——七种形态全部 `allow`。
2. **`HEAD:../Free/README.md` 改前就被拦，但不是被"范围校验"拦的**：它含 `../` 子串，命中的是
   `forbidden_command_fragments`（`command_fragment_blocked`）。片段清单只是**顺带**挡住了这一例，它描述不了
   "这次读取的目标是什么"。同层证据：`git show HEAD:..`（没有 `../` 子串）改前是 `allow`。

## 2. 设计

### 2.1 数据形状（`registry/tool-registry.yaml`，逐工具可选）

```yaml
read_guard:
  families: [readonly]                              # 适用命令族：必须是本工具 command_families 里已声明的 ID
  path_forms: [positional, revision_path]           # 命令文本里认哪些「路径操作数」形态（闭集）
  forbidden_path_prefixes: [".policy"]              # 受保护前缀（信任根：审批条子 / 审计账本）
  forbidden_forms: [parent_escape, absolute_path]   # 读面越界形态（闭集）
```

- **数据与代码的分界**：*规则*（禁哪些前缀、开哪几条形态、对哪几族生效）全在数据里；*语法*（怎么切 token、
  怎么判越界）在代码里。两张闭集（`READ_PATH_FORMS` / `READ_FORBIDDEN_FORMS`）在 `models.py`，与
  `SUPPORTED_CODE_CHECKS` 同型：注册表能选"用哪几种"，不能发明一种没人实现的形态。
- **加载期校验（失败关闭）**：未知字段拒绝（`StrictModel`）、**四字段都必填且不得为空集合**、`families` 必须是
  本工具已声明的族、前缀必须是规范的工作区相对路径（`..` / 前导 `/` / 空段 / 重复一律报错）、形态必须在闭集内、
  `read_guard` 只适用于 `shell_command` 驱动。
- **进 `schema_hash`**：`read_guard` 是 `ToolSpec` 的字段，天然进 `approved_payload()` ⇒ 改读面边界必须重新
  `registry --approve`（用例 `test_read_guard_enters_the_reviewed_schema_hash` 钉住）。
- **不把命令文本拼进正则**：检查只对命令文本做**结构化切分**（token → 声明形态 → 归一化路径），不构造任何
  来自命令文本的正则，也不改写命令。

### 2.2 谓词（只对声明的形态生效）

| 谓词 | 判据 | 说明 |
| --- | --- | --- |
| `absolute_path` | `/x`、反斜杠绝对路径、`C:/x` | **`revision_path` 形态除外**：git 的 `HEAD:/x` 是「仓库根下的 x」，拦它是误伤（用例 `git show HEAD:/README.md` 必须 PASSED） |
| `parent_escape` | `posixpath.normpath` 后是 `..` 或 `../...` | `a/../../x` 同样命中；只写 `..` 时没有 `../` 子串，片段层看不见 |
| `forbidden_path_prefix` | 归一化后 = 前缀 或 前缀 + 斜杠 | 大小写不敏感（Windows 文件系统不区分）、按路径分段边界（`.policyx/` 不命中） |

形态提取（`read_guard_operands`）：

- `positional`：不以 `-` 开头的独立 token，**每个都当路径候选**（不做"像不像路径"的启发式——`git log -p -- registry`
  那种裸目录名没有斜杠，启发式会漏；而谓词足够具体，`git status` 的两个 token 不会被误伤）。
- `revision_path`：`<rev>:<path>` 冒号右侧。`C:/...` 按**宿主绝对路径**解释（`_WINDOWS_ABS_RE`），否则
  `git log -p -- C:/Users/...` 会被当成 rev=`C` 的树内路径而放行。
- 选项取值不算操作数（`--output=` 后面那一段仍归 `forbidden_command_fragments`）；引号会剥掉。

### 2.3 位置：片段检查**之后**（4e）

检查顺序变成 permissions → path_prefixes → command_allowlist → command_composition → command_fragments
→ **read_guard** → code_check → approval → …。理由：**先命中者定码**，把读面闸门放在片段检查之后，所有含
被禁片段 / 组合片段的命令 reason_code 一个字不改（这是"不扩大其它命令的拦截面"的最强形式）。读面闸门负责片段
清单**描述不了**的那一类——`.policy/approval.json` 里没有任何被禁片段。

代价（写进残余）：同时含 `../` 的越界形态（如 `git show HEAD:../Free/README.md`）报告的是
`command_fragment_blocked`。用例 `test_the_documented_crossings_are_blocked_with_the_read_guard_code` 用一份
**去掉 `../` 的片段清单**证明读面闸门自己就能拦住它——它是一道独立闸门，不是片段清单的复述。

### 2.4 三种结论状态（不假装查过）

| 状态 | 何时 |
| --- | --- |
| `PASSED` | 命令命中了 `read_guard.families` 里的族，且每个路径操作数都在读面内 |
| `SKIPPED` + "该工具未声明 read_guard 数据" | 工具没有这条数据（旧注册表 1.0 / 1.1 照常加载） |
| `SKIPPED` + "该命令不在 read_guard 声明的只读族 [...] 内" | 只读族以外的命令（pytest / 脚本族）——拦截面不变 |
| `FAILED` → `read_guard_blocked` | 命中任一谓词 |

### 2.5 新增原因码与协议轴（AGENTS 第 55 条）

| 轴 | 改动 | 理由 |
| --- | --- | --- |
| `enforcement.models.ENFORCEMENT_SCHEMA_VERSION` | **1.0 → 1.1**，`SUPPORTED` = {1.0, 1.1} | `ReasonCode` **多出一个取值** `read_guard_blocked`。键集合没变、取值集合变了——与 B2 的 `selection.level` 多出 `support`（PIPELINE 1.3→1.4）同型。1.0 保留：已落盘的审计 / 台账 / 决策记录是 1.0 载荷，键集合与 1.1 逐字相同，拒收只会让历史证据读不出来 |
| `enforcement.models.REGISTRY_SCHEMA_VERSION` | **1.1 → 1.2**，`SUPPORTED` = {1.0, 1.1, 1.2} | 逐工具新增可选字段 `read_guard`（加键就是改协议）；1.0 / 1.1 文档照常加载 |

`read_guard_blocked` 出现在 `PreDecision` 的 `checks[].reason_code`（受控执行协议载荷），因此走
`ENFORCEMENT_SCHEMA_VERSION` 这一条轴；它不进 dsh 侧 `AUDIT_SCHEMA_VERSION` 的键集合。

### 2.6 已知缺口（结构性检查不是沙箱，照 AGENTS 第 17 条末句）

- 选项取值（`--output` 的取值、`--ext-diff`）仍由 `forbidden_command_fragments` 管，本闸门不看。
- 被引号包裹且**含空格**的路径会被空白切成两段 ⇒ 可能漏判（不误报）。
- git 的配置 / 别名 / 短名展开、pathspec magic、Windows 短名不在视野里。
- `git cat-file` 等读取通道不在命令白名单里，因此本闸门对它们没有承诺；一旦白名单放开这类命令，必须同时
  评估 `path_forms`。

## 3. 前后矩阵（18 条，同一份用例表；改前 = `git archive HEAD` 副本，改后 = 当前工作树）

两条都是**真实 CLI**：`python -m enforcement.cli precheck --request … --approval <族级条子> --json`，
`dry_run` 语义（不占 action_id、不写限流台账）。下表由 `.tmp/b3-read-guard/matrix-{before,after}.json`
机械合并（`merge_matrix.py`），未手抄。

| # | 命令原文 | 组 | 改前 退出码 / reason_code | 改后 退出码 / reason_code | 结论 |
| --- | --- | --- | --- | --- | --- |
| 1 | `git show HEAD:.policy/approval.json` | crossing | 0 / `allow` | 1 / `read_guard_blocked` | **新拦** |
| 2 | `git log -p -- .policy/audit.jsonl` | crossing | 0 / `allow` | 1 / `read_guard_blocked` | **新拦** |
| 3 | `git show HEAD:../Free/README.md` | crossing | 1 / `command_fragment_blocked` | 1 / `command_fragment_blocked` | 不变 |
| 4 | `git log -p -- ./.policy/audit.jsonl` | crossing | 0 / `allow` | 1 / `read_guard_blocked` | **新拦** |
| 5 | `git show HEAD:.POLICY/approval.json` | crossing | 0 / `allow` | 1 / `read_guard_blocked` | **新拦** |
| 6 | `git log -p -- ..` | crossing | 0 / `allow` | 1 / `read_guard_blocked` | **新拦** |
| 7 | `git show HEAD:..` | crossing | 0 / `allow` | 1 / `read_guard_blocked` | **新拦** |
| 8 | `git log -p -- C:/Users/ZNM/.ssh/id_rsa` | crossing | 0 / `allow` | 1 / `read_guard_blocked` | **新拦** |
| 9 | `git status` | legal | 0 / `allow` | 0 / `allow` | 不变（合法） |
| 10 | `git diff` | legal | 0 / `allow` | 0 / `allow` | 不变（合法） |
| 11 | `git log --oneline -5` | legal | 0 / `allow` | 0 / `allow` | 不变（合法） |
| 12 | `git log -p -- src/enforcement/precheck.py` | legal | 0 / `allow` | 0 / `allow` | 不变（合法） |
| 13 | `git show HEAD:src/enforcement/models.py` | legal | 0 / `allow` | 0 / `allow` | 不变（合法） |
| 14 | `git diff -- src/enforcement/models.py` | legal | 0 / `allow` | 0 / `allow` | 不变（合法） |
| 15 | `git show HEAD:/README.md` | legal | 0 / `allow` | 0 / `allow` | 不变（合法） |
| 16 | `git log -p -- .policyx/audit.jsonl` | legal | 0 / `allow` | 0 / `allow` | 不变（合法） |
| 17 | `Remove-Item -Recurse .` | other | 1 / `command_not_allowlisted` | 1 / `command_not_allowlisted` | 不变 |
| 18 | `git diff --output=x.txt` | other | 1 / `command_fragment_blocked` | 1 / `command_fragment_blocked` | 不变 |

读法：

- **1–8 组（越界）**：7 条改前 `allow`、改后 `read_guard_blocked`（**新拦**）；第 3 条改前就被片段层挡住，
  改后仍是 `command_fragment_blocked`（口径不变，见 §2.3）。
- **9–16 组（合法）**：改前改后**都是 `allow`**，8/8 无误伤。其中 13、15 是两条误伤探针：
  `git show HEAD:src/enforcement/models.py`（合法 `<rev>:<path>` 读）与 `git show HEAD:/README.md`
  （git 语义下的树内根路径；若把 `revision_path` 也当绝对路径判，这条会被误伤）——两条都通过。16 是近似前缀
  `.policyx/`，不被前缀闸误伤。
- **17–18 组（对照）**：白名单外命令仍 `command_not_allowlisted`，被禁片段仍 `command_fragment_blocked`；
  **`read_guard` 与 `command_fragment_blocked` 是两个码，没有混用**。

## 4. 测试

| 命令 | 结果 |
| --- | --- |
| `python -m pytest tests/unit/test_precheck_read_guard.py -n0 -q` | **42 passed**，exit 0 |
| `python -m pytest tests/contract/test_registry_read_face_guard.py -n0 -q` | **11 passed**，exit 0 |
| `python -m pytest tests/unit tests/contract -n0 -q` | **2407 passed, 6 skipped**，exit 0（6 条是既有的 Windows 平台跳过） |
| `python -m pytest tests/integration tests/security -n0 -q` | **810 passed**，exit 0（dsh Hook / 受控执行闭环 / API / 编排的端到端路径全跑一遍：协议版本升版没有打断任何链路） |
| `python -c "import enforcement.approvals; import enforcement.precheck; import enforcement.models; import adapters.dsh.hooks; print('ok')"` | ok，exit 0（每次写入后都跑，见 §9 纪律） |

用例覆盖（`tests/unit/test_precheck_read_guard.py`）：

- 三条门 + 同型：`HEAD:.policy/...`、`-- .policy/...`、`HEAD:..`（**片段清单里去掉 `../`** 时仍被拦 ⇒ 独立闸门）；
- 码不混用：含片段的两种形态报 `command_fragment_blocked`，读面越界报 `read_guard_blocked`（两条检查各留痕）；
- 拼写归一化：`./.policy`、`.POLICY`、无尾斜杠的 `.policy`、`git diff -- .policy` 都命中；`.policyx/` 不命中；
- 0 误伤：10 条合法命令 `read_guard` 必须 PASSED（含 `HEAD:/README.md` 与 `HEAD:src/...` 两条探针）；
- 不扩大拦截面：只读族以外的命令（`print('ok')` 形态）与白名单外命令（`Remove-Item`）读面闸门显式 `SKIPPED`；
- 数据面：`read_guard` 进 `schema_hash`；15 条半截/非法声明在加载期被拒（空集合 ×4、未知形态 ×2、未知字段、
  未声明的族、缺 `command_families`、非命令类驱动、`..` 前缀、`/etc` 前缀、重复前缀 / 族 / 形态）；
- 原因码只加值、不复用既有值。

契约用例（`tests/contract/test_registry_read_face_guard.py`，与 `test_registry_control_plane_guard.py` 同形）：

- **数据面**：每个 `shell_command` 工具都必须为它的只读族声明 `read_guard`，且受保护前缀含 `.policy`、
  `path_forms` 含 `revision_path`（反真空：必须覆盖 `exec.pwsh` / `exec.bash`）；
- **行为面**：真注册表 + 真 pre-check，4 条信任根读取必须 block 且 `command_fragments` 同时是 PASSED，
  `git show HEAD:..` 必须 block；对照组 5 条合法只读命令 `read_guard` PASSED。

**测试侧的一处必要修正**（记录在案）：`tests/contract/test_approval_allowlist_audit.py` 的变异③原本只摘
`command_families`；注册表 1.2 起 `read_guard` 依赖族数据，整份注册表会加载失败、仪器只能报 `unavailable`。
该变异已改成同时摘掉 `read_guard`（并写明理由），被测的仍然是"命令类工具没有族数据"这一格。

## 5. 注册表重审与 verify

```
python -m enforcement.cli registry --approve --reviewer dshznm   # exit 0
python -m enforcement.cli registry --verify                      # exit 0，10/10 ok
python tools/approval_allowlist_audit.py --check \
    --registry registry/tool-registry.yaml --approved registry/tool-registry.approved.json   # 0 hits / exit 0
```

`registry/tool-registry.approved.json` 的 diff 要点：

- `reviewed_by`: `dshznm`；`approved_at`: `2026-10-20T14:04:07.997107Z`；
- `governance_digest`: `sha256:826b9d9a…` → **`sha256:47fa192d…`**（治理表覆盖 `registry_schema_version`，1.1→1.2 必然变）；
- `registry_digest`: `sha256:84ddc2dc…` → **`sha256:33e330b8…`**；
- **10/10 工具的 `schema_hash` 全变**——不是因为都改了读面，而是因为 `read_guard: null` 出现在每一条
  `approved_payload()` 里（B1 加 `command_families` 时同样 10/10 全变）。真正带读面数据的是 `exec.pwsh` /
  `exec.bash` 两条：`0f675188…` → `59176129…`、`436183de…` → `b6dd2b29…`。

副作用读数（未修，留给 Lead 判断）：重审前 `registry --verify` 对 10 个工具给的理由都是"角色 / 权限 / 默认值 /
审批角色表与已审核摘要不一致"——而实际变的是 `registry_schema_version`。那句枚举没覆盖"注册表协议版本"这一项，
属于 `registry.py` 的措辞精度问题（不在本次写区）。

## 6. 「400 份真实会话回放」：**未取得**

05 §4 B3 的门要求"合法命令 0 误伤（400 份真实会话回放）"。**这一读数本次未取得**，不许写成 0 误伤。上面 §3 的
0 误伤读数是**夹具级 + 契约级**（18 条矩阵、10 条合法单元用例、5 条契约对照组），不是会话回放。

为取得它，实际试了两条来源，都不成立（这两条"取不到"本身是可核实的读数）：

1. **受治项目的审计链**（`<受治>/.policy/audit.jsonl`，34 830 条记录）：按设计只留摘要（redact + digest），
   **没有命令原文**——实测 34 628 条 dsh Hook 记录只有 `tool` / `reason_code` / `exit_code` 等字段，
   `payload.checks` 里有检查项但**没有 command 值**。
2. **受治项目的受控执行台账**（`<受治>/.policy/enforcement-ledger.jsonl`，552 行；109 条 `claim`）：
   按 AGENTS 第 50 条它**应当**存 `request.params` 原文，但实测 **0/109 条带参数**（`request` 为 `null`，
   台账是更早版本写的）。可用命令原文条数 = 0。

结论：**未取得**。取得它需要一份"带命令原文的真实会话记录"（例如下一轮直接从受治侧 `claim` 记录里读，
或在真实会话上重跑一轮 GUI 阶梯），这不在本子会话可用的数据里。

## 7. 未核实项与残余

1. **受治侧副本没有同步**：`<受治>/.policy/tool-registry.local.yaml` 仍是旧内容（无 `read_guard`、注册表 1.1），
   其 `approved.json` 也还是旧格式产物。**本次改动只在仓库这一侧生效**；要让受治会话真的挡住信任根读取，受治侧
   必须同样改数据 + 重新审核（`registry --approve --reviewer <name>`）。相关契约用例
   `tests/contract/test_approval_allowlist_audit.py::test_the_live_comparison_approval_matches_its_registry_shape`
   仍接受 `registry_hash_drift ∈ {0, 10}`，本次读数是 10。
2. **`Get-ChildItem` / `Write-Output` 也在 `readonly` 族里**：它们带宿主绝对路径参数时现在会被
   `read_guard_blocked` 拦（例如 `Get-ChildItem C:/Users/...`）。这与"读面只接受受控项目内的相对路径"一致，
   但确实是这两个命令的一次**行为收紧**；若认为它们不该受读面约束，正确做法是**新增一个只含 `git` 的族**并改
   `read_guard.families`（改数据 + 重新审核），不是在代码里加特判。
3. **注册表版本与字段没有交叉校验**：1.0 / 1.1 文档里写 `read_guard` 不会被拒（B1 对 `command_families` /
   `default` 同样没有）。两条轴在这一点上口径一致，但与 `validation/test-layout.yaml` 的
   "v1 里写 v2 字段是配置错误"**不一致**。要不要补留 Lead 决定（补就要三处一起补）。
4. **`git show HEAD:../Free/README.md` 的报告码是 `command_fragment_blocked`**（§2.3 的有意取舍）。若 Lead
   认为读面理由更该被看见，正确改法是调换两条检查的顺序并**接受**既有 reason_code 变化——那是一次独立的判定变更，
   不在本次夹带。
5. **未跑 `tools/ci_local.py`**（任务边界要求）；门禁里的**步骤级**检查（注册表审核步骤、受控执行闭环、编排闭环、
   阶段证据）因此未在本轮验证。已跑 §4 的四个 pytest 套件（unit / contract / integration / security，共 3217 条通过）
   与三条 CLI 读数：它们覆盖这些闭环的**代码路径**，但不等于门禁本身通过。
6. **`docs/project/architecture/tech-detail/04-受控执行/` 的生成物**仍只讲两层命令检查
   （`command_composition_blocked` / `command_fragment_blocked`），未提 `read_guard`——属于 Lead 的文档更新点（§8）。

## 8. 留给 Lead 的更新点（本子会话按边界**没有**动这些文件）

| 文件 | 要写什么 |
| --- | --- |
| `AGENTS.md` 第 17 条 | 在"白名单不是沙箱"那段的命令类最小权限里补一句：只读命令族另有**读面闸门**（注册表 `read_guard`，1.2）——受保护前缀（`.policy`）与越界形态（`parent_escape` / `absolute_path`）结构性阻断，原因码 `read_guard_blocked`；它按**命令族**生效、其它命令拦截面不变；并声明它同样**不是沙箱** |
| `AGENTS.md` 第 55 条版本轴表 | `enforcement.models.ENFORCEMENT_SCHEMA_VERSION` **1.0 → 1.1**（新增原因码取值 `read_guard_blocked`）；`REGISTRY_SCHEMA_VERSION` **1.1 → 1.2**（新增可选字段 `read_guard`，SUPPORTED 保留 1.0 / 1.1 / 1.2） |
| `04-open-work.md` 5.70 | 状态改为 ② 已落地（2026-10-20，B3）：数据 + 检查 + 新原因码 + 18 条前后矩阵 + 两个测试套件；**残留**见本读数 §7（受治侧副本未同步 / `Get-ChildItem` 行为收紧 / 400 份回放未取得）。建议把 §7 的 1–4 另立一条残项 |
| `04-open-work.md` 5.12 | 关联更新：只读工具的 `path_scope` 仍是"只声明不执行"（Adapter 侧），本次补的是**命令类工具**的读面，二者不是同一件事，别读成同一处已修 |
| `05-implementation-plan.md` §4 B3 行 | 期望列填实测：3 条越界形态被拦（矩阵 1–3，同型 6–8）+ 合法命令 0 误伤（矩阵 9–16、10 条单元、5 条契约），**400 份真实会话回放未取得**（§6）；判据列不变 |
| `06-plan-progress.md` | 新增一条进度/决策行：B3 落地，含两条口径决定（读面闸门**按族生效**、**先命中者定码**）与"400 份回放未取得" |
| `tools/README.md` | 若要把"读面读数"做成常驻仪器（例如把 §3 的矩阵跑成 `tools/read_face_probe.py`），在此登记；本次**没有**新增工具 |
| `registry/tool-registry.local.yaml`（受治侧，不在本仓库） | 同步 `read_guard` 数据并重新审核（§7.1） |

## 9. 复现命令与改动面

```powershell
# 1) 改前读数：HEAD 副本 + 真实 CLI
git archive --format=tar HEAD src registry policies -o .tmp/b3-read-guard/head3.tar
tar -xf .tmp/b3-read-guard/head3.tar -C .tmp/b3-read-guard/head-tree
$env:PYTHONPATH="$PWD/.tmp/b3-read-guard/head-tree/src"
.venv\Scripts\python.exe .tmp/b3-read-guard/run_matrix.py --tag before --repo .tmp/b3-read-guard/head-tree --python .venv/Scripts/python.exe

# 2) 改后读数：当前工作树
$env:PYTHONPATH="$PWD/src"
.venv\Scripts\python.exe .tmp/b3-read-guard/run_matrix.py --tag after --repo . --python .venv/Scripts/python.exe

# 3) 前后矩阵合并成表
.venv\Scripts\python.exe .tmp/b3-read-guard/merge_matrix.py

# 4) 测试
$env:PYTHONPATH="src"
.venv\Scripts\python.exe -m pytest tests/unit/test_precheck_read_guard.py -n0 -q
.venv\Scripts\python.exe -m pytest tests/contract/test_registry_read_face_guard.py -n0 -q
.venv\Scripts\python.exe -m pytest tests/unit tests/contract -n0 -q
```

改动的文件（本子会话）：

```
 M registry/tool-registry.yaml                    # 1.1→1.2 + exec.pwsh / exec.bash 的 read_guard 数据
 M registry/tool-registry.approved.json           # 重新审核（--reviewer dshznm）
 M src/enforcement/models.py                      # ENFORCEMENT 1.0→1.1 / REGISTRY 1.1→1.2 / ReadGuardSpec / 新原因码 / 闭集
 M src/enforcement/precheck.py                    # 4e) read_guard 检查 + 操作数提取 + 三条谓词
 M tests/unit/test_enforcement_approvals.py              # 版本断言 1.1→1.2（并加 1.1 文档照常加载）
 M tests/contract/test_approval_allowlist_audit.py       # 变异③同时摘 read_guard（§4 末段说明）
 ?? tests/unit/test_precheck_read_guard.py               # 42 条
 ?? tests/contract/test_registry_read_face_guard.py      # 11 条
```

纪律（AGENTS / 04 第 5.85 条）：`precheck.py` / `models.py` 在 dsh Hook 的导入链上，**每次写入后立刻**跑
`import enforcement.approvals; import enforcement.precheck; import enforcement.models; import adapters.dsh.hooks`，
本子会话每次都是 exit 0 才做下一步（最后一次读数见 §4）。
