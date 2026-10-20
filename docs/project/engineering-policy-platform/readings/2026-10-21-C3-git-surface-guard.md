# 2026-10-21 C3 前置阻断补齐：受保护前缀补 `.git` 与 `.github/workflows`

> 性质：**读数**（子会话 `c3-git-surface`，task-5）。依据 04 5.87 的缺口与建议、05 §4 C3 的门
> 「删除/执行/控制面写被前置阻断」、`readings/2026-10-21-C1C2C4-adjudication-draft.md` §4 的残留，
> 以及使用者 2026-10-20 会话的授权与本轮「继续任务」的口径。
>
> 边界遵守：只改 `registry/`、`tests/` 与本读数；**不改判定路径、不新增 reason code、不改
> `precheck.py` / `action.py` / `drivers.py`**；不提交、不跑 `tools/ci_local.py`、
> 不改 04/05/06/AGENTS/tools/README；没有删 `.tmp` 下任何目录。

## 0 一句话

C3 第三件 v1 封住的是 `.policy`（受控项目里的**信任根**），但**执行面**仍敞着：写
`.git/hooks/pre-commit` 等于下一次 `git commit` 时拿到执行权，改 `.github/workflows/*`
等于让所有门禁不再跑。本轮把 `.git` 与 `.github/workflows` 补进四个自动放行写工具的
`blocked_prefixes`（注册表 **1.3 → 1.4**，重新审核），用 27 条固定请求的前后矩阵与扩展后的
两套用例交成可复核读数：**只有新增的执行面组 7/7 翻面（`allow` → `block` /
`path_out_of_scope`），其余 20 条逐条相等**。判定路径与 reason code 一个字没改。

## 1 问题与改前读数

### 1.1 缺口证据（数据与代码位置）

| 事实 | 证据 |
| --- | --- |
| 1.3 的四个自动放行写工具 `blocked_prefixes` 是 `[policies, registry, adapters, api, validation, ".policy"]`，**不含 `.git` / `.github/workflows`** | `git show HEAD:registry/tool-registry.yaml`（HEAD `c827653`）的 `fs.edit` / `fs.write` / `orc.fs.edit` / `orc.fs.write` 段 |
| 上一轮读数已实测它们可写 | `readings/2026-10-21-C3-control-plane-write-guard.md` §6②：探针 `.tmp/c3-control-plane/probe_git_surface.py` 显示 `.git/hooks/pre-commit` 与 `.git/config` 改前/改后都 `allow` |
| 为什么它们是"执行面"而不是"数据" | `.git/hooks/*` 在下一次 git 命令时由 git 执行（`pre-commit` / `post-checkout` 等）；`.git/config` 可改 `core.hooksPath` / alias，把执行面搬到任意路径（该路径甚至不在受保护前缀里）；`.github/workflows/*` 决定 CI 跑不跑——它是检查的执行面 |
| 闸的实现不变 | `src/enforcement/action.py#L299` `blocked_path_prefix`：casefold + 去首尾斜杠 + **路径分段边界**（`candidate == prefix` 或 `candidate.startswith(prefix + "/")`）；`precheck.py#L401` 第 4a 项 → `path_out_of_scope`；`drivers.py#L258` 驱动层再查一遍 |
| 判据（04 5.87 的数据裁定） | 只封"改了就改变执行面"的：`.git` 与 workflow。文档、语料（`knowledge/corpus.yaml`）、阈值（`evaluation/thresholds.yaml`）、`AGENTS.md`、`tools/**` 改的是**判定依据或读数**，按"规则 + 审批"处理，不做结构性阻断（本轮不扩到它们） |

### 1.2 改前读数（HEAD 副本 `c827653`，真实 CLI，dry_run）

`git archive HEAD src registry policies` 的副本 + 当前 `.venv` 解释器，逐条
`python -m enforcement.cli precheck --request … --json`；CLI 的 precheck 固定 `dry_run=True`
（`src/enforcement/cli.py#L531`：不认领 action_id、不签发可用授权、不写限流台账）。固定请求集见
§3，这里只摘结论：

- **执行面 7/7 都是 `allow / allow`**：`.git/hooks/pre-commit`（`fs.write`）、
  `.git/config`（`fs.edit`）、`.github/workflows/ci.yml`、`.github/workflows/phase-8.yml`、
  `./.github/workflows/ci.yml`、`orc.fs.write` 写 `.git/hooks/pre-commit`、`.GIT/hooks/pre-commit`；
- **精度对照都是 `allow`**：`.gitignore`、`.github/ISSUE_TEMPLATE/bug.md`、
  `.github/workflowsx/ci.yml`、`.policyx/audit.jsonl`、受控项目内普通文件；
- **既有拦截面没动**：`.policy` 写面 8/8 `block / path_out_of_scope`（1.3 已落地）；
  `policies/`、`registry/` 写 → `block / path_out_of_scope`；
- **删除路径**：`Remove-Item -Recurse .`、`rm -rf .policy` → `block / command_not_allowlisted`；
- **执行路径**：`run_code` 含 `import os` → `block / code_blocked`（`code_check` FAILED）；
- **命令对照**：`git status --short` → `allow`；无害 `run_code` → `allow_with_warnings`。

## 2 改动面

| 文件 | 改动 | 为什么 |
| --- | --- | --- |
| `registry/tool-registry.yaml` | `registry_schema_version: "1.3" → "1.4"`；四个写类工具的 `file_path.blocked_prefixes` 追加 `".git"` 与 `".github/workflows"`（并写清判据） | 补数据缺口；键集合没变，变的是**这一列受保护前缀的取值** |
| `src/enforcement/models.py` | `REGISTRY_SCHEMA_VERSION = "1.4"`；`SUPPORTED_REGISTRY_SCHEMA_VERSIONS` 显式列出 1.0/1.1/1.2/1.3/1.4；两处版本注释同步（1.4 的判据写进常量上方） | AGENTS 第 55 条：取值语义变了必须显式升版；旧注册表照常加载 |
| `registry/tool-registry.approved.json` | 重新审核（`--reviewer dshznm`） | 数据改动必须重审，否则 pre-check 以 `schema_not_approved` 拒绝整个工具 |
| `tests/security/test_control_plane_write_guard.py` | 三路径套件扩执行面（6 条写入 + 3 条精度 + `registry/` 回归），docstring 的修前矩阵补一行 | 05 §4 C3 的门要有同一份可复核读数；执行面与信任根同级 |
| `tests/contract/test_registry_control_plane_guard.py` | `CONTROL_PLANE_PREFIXES` 加 `.git` / `.github/workflows`（数据面 + 反真空断言自动覆盖四个写工具）；新增 6 条行为面 + 3 条精度 | 与文件既有两条断言（数据面 / 行为面）同形，不新造套件风格 |
| `tests/contract/test_enforcement_protocol.py` | orc 写工具的 `blocked_prefixes` **精确集合**断言加两项 | 该断言钉死整组前缀；数据改了它必须同批改，否则编排层与 dsh 侧漂开没人发现 |
| `tests/unit/test_enforcement_approvals.py` | 注册表轴版本断言 1.3 → 1.4、`SUPPORTED` 断言加 1.4、旧文档加载循环加 `1.3`、测试名与 docstring 同步 | 断言"当前注册表轴"；不升版它就必红。**Lead 在 task-5 显式授权**（2026-10-21） |
| `docs/project/engineering-policy-platform/readings/2026-10-21-C3-git-surface-guard.md` | 本读数 | — |

### 2.1 硬编码前缀与版本号的全仓清点（逐条处置）

只针对**注册表轴与受保护前缀**这两个语义（不是所有字面量 1.3）。全仓检索的命中与处置：

| 位置 | 处置 | 理由 |
| --- | --- | --- |
| `tests/unit/test_enforcement_approvals.py:436-455` | **改**（1.3→1.4；SUPPORTED 加 1.4；旧文档循环加 1.3；测试名改 `…_to_1_4_…`） | 断言"当前注册表轴"，不升版必红 |
| `tests/contract/test_enforcement_protocol.py:401-412` | **改**（精确集合加 `.git` / `.github/workflows`） | 数据面断言：编排层与 dsh 侧必须同一组前缀 |
| `tests/contract/test_registry_control_plane_guard.py:44` | **改**（`CONTROL_PLANE_PREFIXES` 加两项） | 自动放行写工具的数据面 + 反真空 |
| `tests/unit/test_precheck_read_guard.py:108` | **不改** | 它在**构造**一份 1.2 文档来测 `read_guard`；1.2 仍是受支持版本，构造旧形状是设计 |
| `tests/enforcement_support.py:208`、`tests/fixtures/approval_audit/registry*.yaml`、`examples/dsh/b-plan/tool-registry.local.yaml` | **不改** | 测试注册表 / 旧形状夹具 / 示例本地注册表，都是 1.0；1.0 照常加载 |
| `src/enforcement/models.py:106`（ENFORCEMENT 轴注释里的版本类比） | **改**（补 1.4） | 注释与常量保持一致；纯注释，不改语义 |
| `tools/phase_evidence.py:361` | **不改**（不在写区） | 既有残项（04 5.83③）：阶段证据里硬编码 `registry_schema_version: "1.0"`，与常量 1.4 不一致。**这条会让阶段证据说错版本**，应尽快单开一次修 |
| `docs/**`（含 B3/C3 v1 读数、06 记录） | **不改** | 历史读数只登记当时值；06 的新行由 Lead 写 |

**别的轴**：`ENFORCEMENT_SCHEMA_VERSION` 仍是 `1.1`（本轮没有新 reason code，不动它）。
`evaluation/results` / dgate2 等载荷里的版本与注册表轴无关。

### 2.2 版本轴判决（AGENTS 第 55 条）

`blocked_prefixes` 的**键**没变，但**取值列**多了两项受保护前缀，且这一列进工具的
`schema_hash`（授权面数据）。与 1.3 补 `.policy`、B2 的 `selection.level` 多出取值
"support" 同型：取值语义变了就是协议变化。因此 `REGISTRY_SCHEMA_VERSION` 1.3 → 1.4，
`SUPPORTED` 显式列出 1.0/1.1/1.2/1.3/1.4（旧文档照常加载，不制造兼容窗口）。
`ENFORCEMENT_SCHEMA_VERSION` 不动（没有新增 reason code，`path_out_of_scope` 是既有码）。

## 3 前后矩阵（27 条，同一份用例表；改前 = `git archive HEAD` 副本，改后 = 工作树）

两条都是**真实 CLI**：`python -m enforcement.cli precheck --request … --json`（`dry_run`）；
同一份 `.tmp/c3-git-surface/run_matrix.py`、同一批请求文档，`.tmp/c3-git-surface/merge_matrix.py`
机械合并并检查两条不变式——**只有 `git_surface_write` 组允许翻面，且翻面后的 reason code 必须是
`path_out_of_scope`；其余逐条 decision/reason_code 相等**。合并结果：`violations: none`。

| # | 工具 | 目标 | 组 | 改前 decision / reason_code | 改后 decision / reason_code | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | fs.edit | .policy/approval.json | control_plane_write | block / path_out_of_scope | block / path_out_of_scope | 不变（回归） |
| 2 | fs.write | .policy/audit.jsonl | control_plane_write | block / path_out_of_scope | block / path_out_of_scope | 不变（回归） |
| 3 | fs.write | .policy/enforcement-ledger.jsonl | control_plane_write | block / path_out_of_scope | block / path_out_of_scope | 不变（回归） |
| 4 | fs.edit | .POLICY/approval.json | control_plane_write | block / path_out_of_scope | block / path_out_of_scope | 不变（回归） |
| 5 | fs.write | ./.policy/audit.jsonl | control_plane_write | block / path_out_of_scope | block / path_out_of_scope | 不变（回归） |
| 6 | fs.write | .policy | control_plane_write | block / path_out_of_scope | block / path_out_of_scope | 不变（回归） |
| 7 | orc.fs.edit | .policy/approval.json | control_plane_write | block / path_out_of_scope | block / path_out_of_scope | 不变（回归） |
| 8 | orc.fs.write | .policy/audit.jsonl | control_plane_write | block / path_out_of_scope | block / path_out_of_scope | 不变（回归） |
| 9 | fs.write | .git/hooks/pre-commit | git_surface_write | allow / allow | block / path_out_of_scope | **新拦** |
| 10 | fs.edit | .git/config | git_surface_write | allow / allow | block / path_out_of_scope | **新拦** |
| 11 | fs.write | .github/workflows/ci.yml | git_surface_write | allow / allow | block / path_out_of_scope | **新拦** |
| 12 | fs.write | .github/workflows/phase-8.yml | git_surface_write | allow / allow | block / path_out_of_scope | **新拦**（仓库里真实存在的 workflow） |
| 13 | fs.write | ./.github/workflows/ci.yml | git_surface_write | allow / allow | block / path_out_of_scope | **新拦**（`./` 拼写） |
| 14 | orc.fs.write | .git/hooks/pre-commit | git_surface_write | allow / allow | block / path_out_of_scope | **新拦**（编排层同界） |
| 15 | fs.write | .GIT/hooks/pre-commit | git_surface_write | allow / allow | block / path_out_of_scope | **新拦**（大小写变体） |
| 16 | fs.write | .policyx/audit.jsonl | precision | allow / allow | allow / allow | 不变（精度） |
| 17 | fs.write | .gitignore | precision | allow / allow | allow / allow | 不变（分段边界，不误伤） |
| 18 | fs.write | .github/ISSUE_TEMPLATE/bug.md | precision | allow / allow | allow / allow | 不变（只封 workflows） |
| 19 | fs.write | .github/workflowsx/ci.yml | precision | allow / allow | allow / allow | 不变（近似前缀不误伤） |
| 20 | fs.write | policies/security/SEC-001.yaml | precision | block / path_out_of_scope | block / path_out_of_scope | 不变（回归） |
| 21 | fs.edit | registry/tool-registry.yaml | precision | block / path_out_of_scope | block / path_out_of_scope | 不变（回归） |
| 22 | fs.write | src/shop/cart_service.py | precision | allow / allow | allow / allow | 不变（对照） |
| 23 | exec.pwsh | Remove-Item -Recurse . | delete_execute | block / command_not_allowlisted | block / command_not_allowlisted | 不变 |
| 24 | exec.bash | rm -rf .policy | delete_execute | block / command_not_allowlisted | block / command_not_allowlisted | 不变 |
| 25 | exec.run_code | code: import os | delete_execute | block / code_blocked | block / code_blocked | 不变 |
| 26 | exec.pwsh | git status --short | delete_execute | allow / allow | allow / allow | 不变（对照） |
| 27 | exec.run_code | code: print('ok') | delete_execute | allow_with_warnings / allow_with_warnings | allow_with_warnings / allow_with_warnings | 不变（对照） |

读法：

- **9–15（执行面写）**：7/7 改前 `allow`、改后 `block / path_out_of_scope`。其中 13、15 是
  同一目标的拼写归一化（`./`、大写）——`blocked_path_prefix` 的口径是 casefold + 去尾斜杠 +
  **分段边界**，漏掉任何一种都是真实可用的绕过；14 是编排层，两个 Agent 的执行面边界必须一致；
  12 列的是仓库里**真实存在的** workflow，证明这不是只拦"想象中的 ci.yml"。
- **1–8（信任根写）**：上一轮已翻面的 8 条本轮**逐条相等**——补执行面前缀没有把信任根闸改宽或改窄。
- **16–22（精度与回归）**：`.gitignore` 不是 `.git` 之下、`.github/ISSUE_TEMPLATE/bug.md`
  不在 `.github/workflows` 之下、`.github/workflowsx/ci.yml` 不是 `workflows` 之下——
  路径分段边界保证"只封执行面、不误伤日常文档"；`policies/` 与 `registry/` 仍
  `path_out_of_scope`；普通文件仍 `allow`。这 7 条前后**逐条相等**。
- **23–27（删除 / 执行）**：删除路径仍是 `command_not_allowlisted`，执行路径仍是 `code_blocked`。
  两条路径的 reason code **一个字没变**（本轮不碰它们，列出来是为了证明"没碰"）。
- 矩阵的机器可读副本：`.tmp/c3-git-surface/matrix-{before,after}.json`、
  `matrix-invariants.json`、`matrix-table.md`（不提交；重建命令见 §8）。

## 4 测试

| 命令 | 结果 |
| --- | --- |
| `python -m pytest tests/security/test_control_plane_write_guard.py tests/contract/test_registry_control_plane_guard.py tests/contract/test_enforcement_protocol.py tests/unit/test_enforcement_approvals.py -n0 -q` | **108 passed**，exit 0 |
| `python -m pytest tests/unit tests/contract -n0 -q` | **2423 passed, 6 skipped, 3 failed**（exit 1）——3 条**全部**落在并发的 C1-a 改动上（audit 轴 `AUDIT_SCHEMA_VERSION` 1.3→1.4 与 batch 块：`test_hook_audit_reading_context.py` 2 条 + `test_hook_skip_visibility.py` 1 条）；对方把对应测试文件改完后复跑这两个文件 → **17 passed**，exit 0。**本轮 registry 轴的改动不产生这 3 条**（归属读法见 §6.10） |
| `python -m pytest tests/integration tests/security -n0 -q` | **859 passed**，exit 0（9 分 47 秒）——比上一轮读数的 828 多出的条数来自本轮 security 扩的 10 条与**并发 C1-a 子会话**新增的集成用例（`tests/integration/test_dsh_batch_ledger.py` 等），本轮没有改这些用例 |
| `python -m enforcement.cli registry --verify` | exit 0（10/10 ok） |
| `python -c "import enforcement.approvals; import enforcement.precheck; import enforcement.models; import adapters.dsh.hooks; print('ok')"` | ok，exit 0（每次写 `models.py` 后立刻跑，见 §8 纪律） |

用例覆盖：

`tests/security/test_control_plane_write_guard.py`（三路径 + 数据面，28 条）：

- **写（信任根）**：`.policy/audit.jsonl` → block/`path_out_of_scope`；改 `approval.json` → block；
  `orc.fs.write` 写台账 → block；
- **写（执行面）**：`.git/hooks/pre-commit`、`.git/config`、`.github/workflows/ci.yml`、
  `orc.fs.write` 写 `.git/hooks/pre-commit`、`.GIT/…`、`./.github/workflows/ci.yml`
  → block/`path_out_of_scope` 且 `path_prefixes` FAILED、detail 含命中的前缀；
- **精度**：`.gitignore`、`.github/ISSUE_TEMPLATE/bug.md`、`.github/workflowsx/ci.yml`、
  `.policyx/audit.jsonl` 的 `path_prefixes` 必须 PASSED（不误伤）；
- **回归**：`policies/` 与 `registry/` 仍 block/`path_out_of_scope`；
- **删除**：`Remove-Item`、`rm -rf` → `command_not_allowlisted`，且 `path_prefixes` 显式 SKIPPED；
- **执行**：`import os` → `code_blocked` + `code_check` FAILED；无害代码 → `code_check` PASSED
  但止步于 `approval_required`；
- **重审不变式**：四个写工具的当前描述必须与已审核哈希一致（`is_approved`）；
- **加载期拒绝**：6 条坏 `blocked_prefixes` 声明 + 1 条"声明在非 path 参数上"在注册表加载期报
  `RegistryError`（`.git` / `.github/workflows` 也必须走同一条规范化口径：不带前导斜杠、
  不含 `..` 与空段、忽略大小写不重复）。

`tests/contract/test_registry_control_plane_guard.py`（数据面 + 行为面，22 条）：数据面
（四个自动放行写工具都必须声明整组前缀 + 反真空断言覆盖 `fs.*` 与 `orc.fs.*`）+ 8 条信任根写入
block + 6 条执行面写入 block + 3 条执行面精度 + `.policyx` 精度 + `policies/` 回归 + 对照组。

## 5 注册表重审与 verify

```
$env:PYTHONPATH="src"
python -m enforcement.cli registry --approve --reviewer dshznm   # exit 0，10 个工具
python -m enforcement.cli registry --verify                      # exit 0，10/10 ok
python tools/approval_allowlist_audit.py --check --registry registry/tool-registry.yaml \
    --approved registry/tool-registry.approved.json               # HITS 0 / drift 0 / exit 0
```

`registry/tool-registry.approved.json` 的 diff 要点：

- `reviewed_by`: `dshznm`；`approved_at`: `2026-10-20T23:06:01.152041Z`（本机时钟，UTC；
  本地为 2026-10-21 07:06）；
- `governance_digest`: `sha256:290b5086…` → **`sha256:cb0ab0e6…`**（治理表覆盖
  `registry_schema_version`，1.3 → 1.4 必然变）；
- `registry_digest`: `sha256:cc8d184d…` → **`sha256:e7aaefdb…`**；
- **只有 4/10 工具的 `schema_hash` 变了**：`fs.edit`（`5fabf01c…` → `211a87d0…`）、
  `fs.write`（`a8e9faa3…` → `3dc792fb…`）、`orc.fs.edit`（`a9036ef1…` → `edf554aa…`）、
  `orc.fs.write`（`683a873e…` → `dd31a646…`）；其余六个（`exec.bash` / `exec.pwsh` /
  `exec.run_code` / `fs.read` / `orc.policy.edit` / `orc.policy.write`）**逐字不变**——
  这本身是"改的是取值不是形状"的旁证（B1/B3 是给每个工具加字段，那两次 10/10 全变）；
- `tools/approval_allowlist_audit.py --check`：`registry_hash_drift=0`、`HITS: 0`（改前也是 0；
  重审后仓库侧仍是 0。受治侧副本的 drift 不在本读数范围内，见 §6）。

## 6 未核实项与残余

1. **受治侧副本没有同步**（与 B3 §7.1、C3 v1 §6.1 同型）：受治项目里的
   `.policy/tool-registry.local.yaml` 仍是旧形状。**本次改动只在仓库这一侧生效**；要让受治会话
   真的挡住 `.git` / workflow 写入，受治侧必须同样改数据并重审。仓库侧证据是
   `tests/contract/test_approval_allowlist_audit.py` 的 live 比对（`drift ∈ {0, 10}`，本轮是 0）。
2. **符号链接不在承诺范围内**（同 C3 v1 §6.3）：`blocked_path_prefix` 只看参数里的**路径字符串**，
   不解析 symlink / junction。受控项目里若存在指向 `.git`（或 `.policy`）的链接，经链接路径写入
   仍会放行。这是"结构性检查不是沙箱"的同型边界（AGENTS 第 17 条末句）。
3. **`.github/workflows` 被挡住不等于"CI 不再可被改写"**：workflow 会调用仓库里的文件
   （本仓库是 `tools/ci_local.py` 与 pytest 配置），那些文件仍可被自动放行的写工具改写——
   本轮封的是"直接改 workflow 或 hook"这条**执行面**，不是"改被 CI 调用的脚本"这条**间接执行面**。
   后者属于 04 5.87 点名的 `tools/**` / `pyproject.toml` / `requirements.*`，本轮按裁定
   **不扩**（改它们 = 改规则或读数，走审批）。这是本轮最大的残余，必须写在明处。
4. **`.git` 之外的控制面没有封**（04 5.87 原文）：`dgate2/scorer/**`（含 `manifest.sha256`）、
   `evaluation/thresholds.yaml`、`evaluation/results/**`、`knowledge/corpus.yaml`、
   `AGENTS.md`、`docs/project/**`、`tools/**`、`pyproject.toml` / `pytest.ini` /
   `requirements.*`。它们是"改判定依据或读数"的那一类，建议按"规则 + 审批"处理，不是结构性阻断。
5. **`.gitattributes` 仍可写**（不在 `.git` 之下）：它不能定义执行命令（filter 的定义在
   `.git/config`，已封），但可以把文件标成 binary 让 diff 不显示内容——属于"证据面"而不是"执行面"，
   本轮不封；若将来要求"diff 必须可见"，这是一条要单独立项的读面。
6. **前缀只在工作区根成立**（同 C3 v1 §6.4）：前缀匹配吃的是**工作区相对路径**。把工具的工作区指到
   子目录（例如 `src/`）时不构成 `.git` / `.policy` 前缀——但那时工作区里也没有这些目录，
   属于另一个受治边界。
7. **大小写口径**：`.GIT` 在 POSIX 上是另一个目录，但 `blocked_path_prefix` 用 casefold 匹配，
   因此它在 Linux 上也会被拦（宁可多拦一个不存在的目标，也不留 Windows 上的绕过）。
8. **未跑 `tools/ci_local.py`**（任务边界要求）：门禁里的步骤级检查（注册表审核步骤、受控执行闭环、
   编排闭环、阶段证据）未在本轮验证。已跑 §4 的 pytest 组合与三条 CLI 读数；它们覆盖这些闭环的
   **代码路径**，不等于门禁本身通过。
9. **`tools/phase_evidence.py:361` 硬编码 `registry_schema_version: "1.0"`**（04 5.83③ 既有残项）：
   阶段证据里的版本会与常量 1.4 不一致。不在本会话写区。
10. **本轮的树是共享工作树**：跑 §4 时 `git status --short` 里还有别的子会话对
    `src/adapters/dsh/adapter.py` / `hooks.py` 的改动与新增文件 `src/adapters/dsh/batch_ledger.py`
   （C1-a 等）。**归属判据（不靠猜）**：那 3 条失败全在 **audit 轴**上——C1-a 把
   `AUDIT_SCHEMA_VERSION` 1.3→1.4 并加 `batch_ref` / batch 块，失败时那两份测试还没改完；
   它们不读 `REGISTRY_SCHEMA_VERSION`，只读 hook 审计记录，**与本轮的 registry 轴是两个轴**。对方改完后
   单独复跑那两个文件：**17 passed / exit 0**。本轮的四个套件与矩阵只依赖 `registry/`、
   `src/enforcement/` 与本轮改的文件，全绿。**教训**：共享工作树上的全量红必须先按 `git status`
   与轴归属，不能直接记成"这次改动引入的回归"。

## 7 留给 Lead 的更新点（本子会话按边界**没有**动这些文件）

| 文件 | 要写什么 |
| --- | --- |
| `04-open-work.md` 5.87 | 状态：**部分已落地**（2026-10-21）：`.git` 与 `.github/workflows` 进四个写类工具的受保护前缀（注册表 1.4 + 重审 + 27 条矩阵 + 两套用例）；**残留**=§6 的 1/2/3/4/5（受治侧同步、symlink、经 CI 调用的脚本仍是间接执行面、其余治理面、`.gitattributes`） |
| `04-open-work.md` 5.84 | 关联：C3 的"前置阻断"从信任根（`.policy`）扩到执行面（`.git` / CI），两轮读数各自独立 |
| `AGENTS.md` 第 13 条 | 受保护前缀清单补 `.git` 与 `.github/workflows`，写清判据是"改了就改变执行面"（hook 会执行、config 能改 hook 路径、workflow 决定 CI 跑不跑），并写清它们进 `schema_hash`、改数据必须重审 |
| `AGENTS.md` 第 55 条版本轴表 | `enforcement.models.REGISTRY_SCHEMA_VERSION` **1.3 → 1.4**（`blocked_prefixes` 取值列 + `.git` / `.github/workflows`；SUPPORTED 保留 1.0–1.4）。`ENFORCEMENT_SCHEMA_VERSION` **不动**（没有新 reason code） |
| `05-implementation-plan.md` §4 C3 行 | 门列补实测：执行面写（`.git` / workflow）7 条翻面、`.gitignore` / 模板 0 误伤 |
| `06-plan-progress.md` | 新增一行进度/决策：C3 前置阻断补齐（注册表 1.4），含两条口径决定（① 只封执行面，文档/语料/阈值按规则 + 审批；② 不新增 reason code，复用 `path_out_of_scope`）与"受治侧未同步""经 CI 调用的脚本仍是间接执行面" |
| `tools/README.md` | 本轮**没有**新增工具；矩阵是 `.tmp` 下的**一次性仪器**（不入库）。若要把 §3 的矩阵变成常驻仪器，在那里登记 |
| 受治侧 `tool-registry.local.yaml`（不在本仓库） | 同步 `.git` / `.github/workflows` 前缀并重新审核（§6.1） |
| `docs/project/architecture/tech-detail/04-受控执行/` | 生成物目前只讲两层命令检查（B3 与 C3 v1 的残项同型）：补"受保护前缀 = 信任根（`.policy`）+ 执行面（`.git` / workflow）"这一层，改内容源后重新生成（`--check` 是门禁） |

## 8 复现命令与改动面

```powershell
# 1) 改前读数：HEAD 副本 + 真实 CLI
New-Item -ItemType Directory -Force .tmp/c3-git-surface/head-tree | Out-Null
git archive --format=tar HEAD src registry policies -o .tmp/c3-git-surface/head.tar
tar -xf .tmp/c3-git-surface/head.tar -C .tmp/c3-git-surface/head-tree
$env:PYTHONPATH="$PWD/.tmp/c3-git-surface/head-tree/src"
.venv\Scripts\python.exe .tmp/c3-git-surface/run_matrix.py --tag before --repo .tmp/c3-git-surface/head-tree

# 2) 改后读数：当前工作树（先在 1) 之后改数据并重审，见 §5）
$env:PYTHONPATH="$PWD/src"
.venv\Scripts\python.exe .tmp/c3-git-surface/run_matrix.py --tag after --repo .

# 3) 前后矩阵合并 + 不变式检查（只翻 git_surface_write / 其余逐条相等）
.venv\Scripts\python.exe .tmp/c3-git-surface/merge_matrix.py

# 4) 注册表重审 + verify + 族/白名单审计
$env:PYTHONPATH="src"
.venv\Scripts\python.exe -m enforcement.cli registry --approve --reviewer dshznm
.venv\Scripts\python.exe -m enforcement.cli registry --verify
.venv\Scripts\python.exe tools/approval_allowlist_audit.py --check --registry registry/tool-registry.yaml --approved registry/tool-registry.approved.json

# 5) 测试（-n0）
.venv\Scripts\python.exe -m pytest tests/security/test_control_plane_write_guard.py tests/contract/test_registry_control_plane_guard.py tests/contract/test_enforcement_protocol.py tests/unit/test_enforcement_approvals.py -n0 -q
.venv\Scripts\python.exe -m pytest tests/unit tests/contract -n0 -q
.venv\Scripts\python.exe -m pytest tests/integration tests/security -n0 -q

# 6) Hook 导入链自检（每次写 src/enforcement/models.py 后立刻跑；本会话每次 exit 0）
$env:PYTHONPATH="src"
.venv\Scripts\python.exe -c "import enforcement.approvals; import enforcement.precheck; import enforcement.models; import adapters.dsh.hooks; print('ok')"
```

改动的文件（本子会话）：

```
 M registry/tool-registry.yaml                          # 1.3→1.4 + 四个写类工具补 .git / .github/workflows
 M registry/tool-registry.approved.json                 # 重新审核（--reviewer dshznm）
 M src/enforcement/models.py                            # REGISTRY 1.3→1.4 / SUPPORTED 保留 1.0–1.4
 M tests/security/test_control_plane_write_guard.py     # 三路径套件扩执行面（+10 条）
 M tests/contract/test_registry_control_plane_guard.py  # 数据面加两项 + 9 条行为面
 M tests/contract/test_enforcement_protocol.py          # orc 写工具精确前缀集合加两项
 M tests/unit/test_enforcement_approvals.py             # 注册表轴版本断言（task-5 授权）
 ?? docs/project/engineering-policy-platform/readings/2026-10-21-C3-git-surface-guard.md
```

**纪律**（AGENTS / 04 第 5.85 条）：`models.py` 在 dsh Hook 的导入链上，**每次写入后立刻**跑
`import enforcement.approvals; import enforcement.precheck; import enforcement.models; import adapters.dsh.hooks`；
本子会话每次都是 exit 0 才做下一步。
