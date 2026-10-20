# 2026-10-20 B1 审批「参数域」：读数

- 任务：05 §4 B1 / 04 5.69「审批按参数形状两向严格，GUI 里无法稳定预放行」
- 执行者：子会话 b1-approval（Lead 派发，task-1）
- 基线：干净树 `30d10ae`（修前读数在**改动前**采集，见 §5）
- 授权来源：**使用者 2026-10-20 在本会话中显式授权解冻并执行改判定的工作**（05 §2.3 冻结令的授权来源）
- 审核口径：`registry --approve --reviewer dshznm` 是**单人仓库的自审**（AGENTS 第 38 条），
  不假装第三方复核；"dshznm 这一次审核由使用者 2026-10-20 会话授权"这句同时写在这里与 §7。
- 三态口径：**有读数** / **无读数**（写清缺什么）/ **不适用**（不是 0）。本文件的每个数字都标了来源命令与退出码。

## 1 结论（先读这一节）

1. 审批协议 **1.2 → 1.3**：`param_patterns` 的覆盖口径新增「参数域」——注册表声明为
   **可选且有默认值**的参数，条子可以不逐格声明；匹配前按注册表默认值补齐**两侧**再比对。
   补出来的是一条**精确等于默认值**的模式（不是通配）。
2. 注册表 **1.0 → 1.1**：逐工具新增可选 `command_families`（命令族数据），逐参数新增可选
   `default`。两者都进逐工具 `schema_hash`（被审核数据），旧注册表（1.0）照常加载。
3. `python -m enforcement.cli approve --family TOOL:FAMILY`：按注册表的族签发**一条**条子；
   命令参数由族并成一条精确 union 模式（单模式族原样返回），签完**自检**它覆盖自己的样例请求。
4. `tools/approval_allowlist_audit.py --check`：族 × 白名单**双向**比对（精确成员），
   真实读数 **0 命中 / exit 0**；三处变异 + 一处"读不出来"证明仪器会红也会说"没有读数"（见 §8）。
5. **负例一条没放宽**：未知参数（构造期拒）、run_in_background=true（审批层按默认 false 拒；
   条子显式放行时在**驱动层**拒）、白名单外命令（命令检查拒）——修前修后逐条相同。
6. **1.1 / 1.2 记录行为与修前逐字相同**：18 行 1.2 矩阵 before/after 的
   `decision + reason_code + failed_check` **逐条相等**（§5）。
7. 决策载荷未变：4 份 `tests/fixtures/decisions/*.json` 的 sha256 前后**完全相同**，
   `git diff -- src/policy` 为空（`policy.engine.evaluate` 未改）。

## 2 改了什么（文件 + 版本号 + 数据字段）

| 文件 | 改动 | 版本/字段 |
| --- | --- | --- |
| `src/enforcement/approvals.py` | 协议 1.3「参数域」：`approval_param_domain()` / `union_pattern()`；`verify_approval(param_defaults=...)`；`select_approval` 的形状档改成三档（0 完全对得上 / 1 1.3 记录"声明的那几格对得上" / 2 对不上） | `APPROVAL_SCHEMA_VERSION 1.2→1.3`；`SUPPORTED={1.1,1.2,1.3}`；`APPROVAL_SET_SCHEMA_VERSIONS={1.2,1.3}`；新增 `APPROVAL_PARAM_DOMAIN_VERSION="1.3"`。**没有新增键**（改的是覆盖口径） |
| `src/enforcement/models.py` | `ParamSpec.default`（可选，仅用于审批匹配；类型/长度/pattern/enum/路径规范逐项校验）；`CommandFamily` + `ToolSpec.command_families`（唯一 id、可编译、非空、仅 shell_command）；`ToolSpec.param_defaults()` / `command_family()` | `REGISTRY_SCHEMA_VERSION 1.0→1.1`；`SUPPORTED_REGISTRY_SCHEMA_VERSIONS={1.0,1.1}`（加可选字段不制造兼容窗口，与 test-layout v1→v2 同型） |
| `registry/tool-registry.yaml` | `registry_schema_version: "1.1"`；`exec.pwsh` / `exec.bash` 的 `timeoutMs=60000` / `workdir="."` / `run_in_background=false` 默认值；两工具的 `command_families`（pwsh: tests 2 + readonly 3 + scripts 2；bash: tests 2 + readonly 2 + scripts 1，与 `allowed_commands` 逐字相同） | 数据字段：`default`、`command_families[].{id,title,patterns}`。**sandbox_permissions / justification 故意没有默认值**（平台从不把"缺席"当作 workspace-write 或空理由，给默认值会在审批域里写一句不真实的话） |
| `registry/tool-registry.approved.json` | `dshznm` 重新审核：10 个工具的 `schema_hash` 全变（新增字段进 approved_payload），reviewed_by / approved_at / 两个 digest 同批更新 | `approved_schema_version` 不变（清单的**键集合**没变，只是哈希值与审核人变了） |
| `src/enforcement/precheck.py` | 审批检查把 `spec.param_defaults()` 交给 `verify_approval`；拒绝理由补一条"本条审批自述 1.3，未声明的可选参数按默认值参与匹配"；判定详情加 `param_domain=defaults:[...]`（审计里读得出"补了哪些格"） | 只动审批这一段（Lead 条件 4：不新增 reason code、不碰 read_guard / forbidden_command_fragments） |
| `src/enforcement/cli.py` | `approve --family TOOL:FAMILY`（只适用于 `--binding pattern`；族模式必须逐字在白名单里；签完自检）；`registry --list --json` 的 `registry_schema_version` 改成从常量取（原来硬编码 "1.0"）；CLI 的 `select_approval` 调用点补传默认值 | 无新协议 |
| `tools/approval_allowlist_audit.py` | 新增 `--check` 模式：族 × 白名单双向比对；四格红条件 + `registry_hash_drift`；`mode: "families"`；`FAMILY-CHECK:` 机器行 | `APPROVAL_AUDIT_SCHEMA_VERSION 1.0→1.1`（加键/加模式即升版） |
| `tests/unit/test_enforcement_approvals.py`（新） | 44 条：协议版本、参数域六种组合、选择档、族数据契约、模型校验、precheck 集成、`approve --family`（真跑 CLI）、自检失败拒绝落盘 | — |
| `tests/contract/test_approval_binding_modes.py` | +122 行：1.3 协议轴、1.3 省略=默认值、1.2 逐字不变、拿不到默认值失败关闭、选择按生效域 | — |
| `tests/contract/test_approval_allowlist_audit.py` | +144 行：真实注册表 0 命中、三处变异必红、不可读=unavailable、`--check` 与 `--approval` 混用=用法错误 | — |
| `examples/dsh/b-plan/README.md` | 补一段 1.3 参数域 + `--family` 的用法与边界（本地副本 `tool-registry.local.yaml` **不动**，且已写明它没有默认值/族数据，旧纪律在它上面仍逐字成立） | — |

### 2.1 版本轴递增清单（Lead 条件 2）

| 轴 | 动作 | 依据 |
| --- | --- | --- |
| `enforcement.models.REGISTRY_SCHEMA_VERSION` | **1.0 → 1.1** | 注册表数据文件新增可选字段（加键=改协议）；加载器同时接受 1.0 与 1.1 |
| `enforcement.approvals.APPROVAL_SCHEMA_VERSION` | **1.2 → 1.3** | 覆盖口径变化（无新键）；`SUPPORTED` 保留 1.1/1.2/1.3 |
| `tools.approval_allowlist_audit.APPROVAL_AUDIT_SCHEMA_VERSION` | **1.0 → 1.1** | 新增 `--check` 模式与四条族相关红条件 |
| `enforcement.models.ENFORCEMENT_SCHEMA_VERSION` | 不动 | 运行时载荷（ActionRequest / PreDecision / …）键集合与语义未变；`tool_schema_hash` 是**值**变，不是形状变 |
| `enforcement.registry.APPROVED_SCHEMA_VERSION` | 不动 | 已审核清单的键集合未变（`tools.<id>.schema_hash` 的值按设计随改动而变） |

**同批改过的写死版本号引用点**：`src/enforcement/cli.py`（`registry --list --json` 里
硬编码的 "1.0" → 常量；OCR 评审 2026-10-07 已点名这一处）、`registry/tool-registry.yaml`（1.1）、
`registry/tool-registry.approved.json`（重新生成）。

**故意保留、且写清理由的引用点**（不是遗漏）：
- `tests/enforcement_support.py` 与 `tests/fixtures/approval_audit/registry*.yaml` 仍写
  `registry_schema_version: "1.0"`：它们是**旧形状注册表**的常驻用例（证明 1.0 照常加载是设计，
  不是兼容窗口）。它们不带新字段，因此不存在"同一版本号底下两种形状"。
- `examples/dsh/b-plan/tool-registry.local.yaml` 仍是 1.0：**按边界不改**（受治项目自己的数据）。
- `tools/phase_evidence.py:361` 仍硬编码 `"registry_schema_version": "1.0"`：
  **不在本次写区**，列为残留（§10 第 3 条），建议 Lead 同一批改成 `enforcement.models.REGISTRY_SCHEMA_VERSION`。

## 3 「参数域」的确切语义（实现口径，逐条可验）

设记录 R（binding=pattern）与本次请求参数 P，注册表默认值 D（仅对"可选且有默认值"的参数）：

1. **版本门**：只有 R 自述 ≥1.3 **且**调用方给了 D 才进入参数域；否则与修前逐字相同。
2. **请求侧补齐**：对每个默认值条目，若参数不在 P 里则补上默认值（记录声明过的那几格也补——
   否则"声明 ^30000$"的条子会意外接受"不传"）。
3. **记录侧补齐**：对每个**没被逐格声明**的默认值，补一条
   `^ + re.escape(渲染后的默认值) + $` 的模式（**精确**，例如 `workdir="."` → `^\.$`）。
4. 然后仍走 1.1 起的两向严格：声明的模式全要匹配；**补齐后仍未被声明的参数仍拒**
   （即"请求里出现未声明且无默认值的参数仍然拒"）。
5. 缺默认值的参数（`sandbox_permissions` / `justification`；以及任何没写 `default` 的参数）
   **不补**：条子必须逐格声明，否则请求里出现它就拒。

三条不可让步的性质各有专门用例：`test_1_3_omission_is_not_a_wildcard`、
`test_undeclared_parameters_without_a_default_are_still_refused`、
`test_old_records_do_not_get_the_parameter_domain`。
**只有记录自己自述 ≥1.3 时才补**；调用方不传默认值时 1.3 记录也按旧口径（失败关闭）。

## 4 命令族的数据与签发口径

- 族是**注册表数据**（`command_families`），模式与 `allowed_commands` **逐字相同**；
  `tools/approval_allowlist_audit.py --check` 做双向精确比对。
- **加载期不强制族与白名单一致**：强制会让那台仪器永远绿（AGENTS 第 45 条）；
  一致性由仪器判、由 `approve --family` 签发口再挡一次（族模式不在白名单里 → exit 2）。
- 签发出的条子：`command` 一格的模式是族内所有模式的精确并集
  （`(?:(?:p1)|(?:p2))`，`re.fullmatch` 语义等价于"任一分支整串匹配"；单模式族原样返回），
  其余参数仍须显式覆盖；签完**自检**一次 `verify_approval`（用样例请求，带注册表默认值）。
- `approval_id` 默认是 `approval-<tool>-<family>`（重签同一族 = 取代同一张条子），`note` 里写明族与模式。
- 用法（可复核）：见 `examples/dsh/b-plan/README.md` 与 `src/enforcement/cli.py` 的模块 docstring。

### 4.1 真实注册表上的签发 smoke（用例之外的第二次证明）

```text
$ $env:PYTHONPATH="src"; python -m enforcement.cli approve --request examples/dsh/b-plan/shell-request.json \
    --out .tmp/b1-matrix/family-approval.json --granted-by dshznm --roles reviewer \
    --binding pattern --max-uses 3 --family exec.pwsh:tests --param-pattern "description=.*"
  "approval_id": "approval-exec.pwsh-tests",
  "schema_version": "1.3",
  "command": "(?:(?:^python -m pytest( .*)?$)|(?:^uv run python -m pytest( .*)?$))",
  "note": "命令族 exec.pwsh:tests（注册表 command_families 生成；族模式 [...])"
approve_family_exit=0
```

（这条条子只落在 `.tmp/`，是 smoke 产物、不是签发出去的凭据；真实受治会话的条子仍必须由使用者亲手签。）

## 5 前后对比矩阵（固定语料，修前修后各跑一次 precheck）

- 修前：干净树 `30d10ae`（**改动前**采集；`.tmp/b1-matrix/before.json`）。
- 修后：`.tmp/b1-matrix/after.json`（同一 HEAD + 未提交改动）。
- 语料：`exec.pwsh`，真实注册表；3 个命令族（tests / readonly / scripts）×
  4 种参数格（2 格 / +timeoutMs=60000 / +workdir="." / +run_in_background=false），
  外加 5 类负例。每行用**同一个** ticket 模式，只把记录的 `schema_version` 从 1.2 换成 1.3。
- 入口：`pre_execute(..., dry_run=True)`（只回答"现在执行会被允许吗"：不认领 action_id、不写限流台账），
  每次跑在独立目录（台账/审计互不干扰）。

```text
| 用例（族 × 参数格） | 修前（1.2 条子） | 修后（1.2 条子） | 修后（1.3 条子） |
| --- | --- | --- | --- |
| 测试族 × 2 格（command+description） | allow / allow | allow / allow | allow / allow |
| 测试族 × 3 格（+timeoutMs=60000） | block / approval_invalid | block / approval_invalid | allow / allow |
| 测试族 × 4 格（+workdir=.) | block / approval_invalid | block / approval_invalid | allow / allow |
| 测试族 × 5 参（+run_in_background=false） | block / approval_invalid | block / approval_invalid | allow / allow |
| 只读族 × 2 格 | allow / allow | allow / allow | allow / allow |
| 只读族 × 3 格（+timeoutMs=60000） | block / approval_invalid | block / approval_invalid | allow / allow |
| 只读族 × 4 格（+workdir=.) | block / approval_invalid | block / approval_invalid | allow / allow |
| 只读族 × 5 参（+run_in_background=false） | block / approval_invalid | block / approval_invalid | allow / allow |
| 脚本族 × 2 格 | allow / allow | allow / allow | allow / allow |
| 脚本族 × 3 格（+timeoutMs=60000） | block / approval_invalid | block / approval_invalid | allow / allow |
| 脚本族 × 4 格（+workdir=.) | block / approval_invalid | block / approval_invalid | allow / allow |
| 脚本族 × 5 参（+run_in_background=false） | block / approval_invalid | block / approval_invalid | allow / allow |
| 负例：run_in_background=true（条子未声明） | block / approval_invalid | block / approval_invalid | block / approval_invalid |
| 负例：run_in_background=true（条子显式 ^true$） | allow / allow | allow / allow | allow / allow |
| 负例：timeoutMs=30000（非默认值） | block / approval_invalid | block / approval_invalid | block / approval_invalid |
| 负例：workdir=src（非默认值） | block / approval_invalid | block / approval_invalid | block / approval_invalid |
| 负例：未知参数 sandbox_permission | 构造期拒（param_unknown） | 构造期拒（param_unknown） | 构造期拒（param_unknown） |
| 负例：白名单外命令 rm -rf src | block / command_not_allowlisted | block / command_not_allowlisted | block / command_not_allowlisted |
```

**读数怎么读（三条）**：

1. **放宽的只有一处**：1.3 条子对"默认值参数"的省略（上表 1.3 列 12 行的 allow）。
   1.2 列与修前列**逐条相等**（18 行全部 same=True，比对脚本 `.tmp/b1-matrix/compare.py`）。
2. **负例一条没放宽**：
   - `run_in_background=true`：条子**未声明**它时，审批层按默认 `false` 拒
     （理由原文："参数 'run_in_background' 的取值 'true' 不等于注册表声明的默认值 False（审批协议 1.3 的参数域）…"）；
     条子**显式** `^true$` 时 precheck 放行（与修前相同），但**驱动层**拒绝
     （`.tmp/b1-matrix/after.json` 的 `driver` 栏：`REJECTED_AT_DRIVER`，
     原文"后台进程没有退出码，exit_code_zero 事后核对必然退化成 repair_required…"）。
     两处都是"拒"，只是闸门不同——**没有任何一条路能真的后台执行**。
   - `timeoutMs=30000` / `workdir="src"`：审批层拒，理由指向"注册表默认值"并给出
     `--param-pattern <name>=<正则>` 的改法（AGENTS 第 50 条）。
   - 未知参数：**构造期**就拒（`param_unknown`，`ActionRequest` 的参数 allowlist），两个版本一致。
   - 白名单外命令：`command_allowlist` 拒（`command_not_allowlisted`），与审批版本无关。
3. **1.2 记录遇到可选参数缺失时行为与修前一致**：上表 1.2 列 18 行与修前逐条相等（含
   "请求多一格就拒"、"记录声明了而请求没带就拒"两种）；另有单测
   `test_old_records_do_not_get_the_parameter_domain` 与契约用例
   `test_1_2_records_keep_the_strict_two_way_rule_even_when_defaults_exist` 钉住。

### 5.1 夹具矩阵 9/9（**不是**真实受治会话读数）

9 条常用命令 × 三个命令族的 1.3 条子（每条只声明 `command` + `description`）：

| 族 | 命令 | 结果 |
| --- | --- | --- |
| tests | `python -m pytest -q` | allow |
| tests | `uv run python -m pytest -q` | allow |
| readonly | `git status` | allow |
| readonly | `git diff` | allow |
| readonly | `Write-Output ok` | allow |
| readonly | `Get-ChildItem` | allow |
| scripts | `python tools/cleanup.py --dry-run` | allow |
| scripts | `python -m policy.check` | allow |
| scripts | `python -m enforcement.cli registry --verify` | allow |

**真实受治会话的 9/9：无读数**——还没有使用者签发的 1.3 条子，夹具矩阵不能代替它（07-status-brief 里
"9 条常用命令通过"必须等真实条子落地后才敢写成已完成）。

## 6 决策载荷未变的证明

| 项 | 修前（`30d10ae`） | 修后 | 结论 |
| --- | --- | --- | --- |
| `tests/fixtures/decisions/allow.json` | `sha256 5bdf5317…eec691` | 同 | 逐字节相同 |
| `tests/fixtures/decisions/approval.json` | `sha256 ddba160a…f2dc9d` | 同 | 逐字节相同 |
| `tests/fixtures/decisions/block.json` | `sha256 bd7cbfd0…157a90` | 同 | 逐字节相同 |
| `tests/fixtures/decisions/warning.json` | `sha256 364e6665…e55a41` | 同 | 逐字节相同 |
| `git diff -- src/policy` | — | 空 | `policy.engine.evaluate` 未改；`approvals` 不参与它 |

修前 sha256 清单另存 `.tmp/b1-matrix/before-env.txt`（含 git head、python 版本、采集时间）。

## 7 审核与注册表门禁（原文 + 退出码）

```text
$ $env:PYTHONPATH="src"; python -m enforcement.cli registry --approve --reviewer dshznm
{
  "approved": "registry/tool-registry.approved.json",
  "approved_at": "2026-10-20T12:35:46.768873Z",
  "registry_digest": "sha256:84ddc2dc74bacd10cda23e208c9c0ed24884acc7289f022cd0d80eb95d1687c7",
  "reviewed_by": "dshznm",
  "tools": 10
}
approve_exit=0

$ $env:PYTHONPATH="src"; python -m enforcement.cli registry --verify
registry: registry/tool-registry.yaml（version=1，10 个工具）
  ok exec.bash / exec.pwsh / exec.run_code / fs.edit / fs.read / fs.write /
     orc.fs.edit / orc.fs.write / orc.policy.edit / orc.policy.write
verify_exit=0
```

**审核口径**：dshznm 的这次审核由使用者 2026-10-20 会话授权；依据 AGENTS 第 38 条，这是
**单人仓库的自审**（审核人与使用者是同一身份的所有者路径），**不假装第三方复核**。

`registry/tool-registry.approved.json` 的 diff（要点）：

- `reviewed_by: enforcement-availability → dshznm`；`approved_at` 更新；
- `governance_digest` / `registry_digest` 变化（注册表协议版本进了治理表摘要）；
- **10 个工具的 `schema_hash` 全部变化**：新增的 `command_families` 与参数 `default` 进
  `approved_payload`，这是"族/默认值是被审核数据"的直接证据；
- `approved_schema_version` 仍是 1.1（清单键集合未变）。

## 8 族 × 白名单双向比对（原文 + 退出码 + 变异证明）

```text
$ python tools/approval_allowlist_audit.py --check --registry registry/tool-registry.yaml --approved registry/tool-registry.approved.json
APPROVAL_ALLOWLIST_AUDIT: family-check 0 hits / tools=2 families=6
FAMILY-CHECK: 0 / family_pattern_outside_the_allowlist=0 / allowlisted_pattern_without_a_family=0 / pattern_in_multiple_families=0 / command_tool_without_families=0 / registry_hash_drift=0 / tools=2 families=6
HITS: 0 / ...（同上）/ tools=2 families=6
exit=0
```

变异证明（`tests/contract/test_approval_allowlist_audit.py` 真跑工具、读 `--json`）：

| 变异 | 期望红格 | 读数 |
| --- | --- | --- |
| 给 `exec.pwsh:tests` 加一条 `^rm -rf( .*)?$` | `family_pattern_outside_the_allowlist` | 1 |
| 删掉 `exec.bash:scripts` 族（留一条没人认领的白名单） | `allowlisted_pattern_without_a_family` | 1 |
| 删掉 `exec.bash.command_families` | `command_tool_without_families` | 1（该工具的白名单**不**再逐条计入反向格：一个缺口不许数两遍） |

## 9 测试命令、退出码与通过数（全部 `-n0` 单进程）

| 命令 | 退出码 | 结果 |
| --- | --- | --- |
| `pytest tests/contract/test_approval_binding_modes.py tests/contract/test_approval_allowlist_audit.py -n0 -q`（**修前**，干净树） | 0 | 34 passed |
| `pytest tests/unit/test_enforcement_approvals.py -n0 -q` | 0 | 44 passed |
| `pytest tests/contract/test_approval_binding_modes.py tests/contract/test_approval_allowlist_audit.py tests/unit/test_enforcement_approvals.py -n0 -q` | 0 | 89 passed |
| `pytest tests/unit/test_tool_registry.py tests/unit/test_precheck.py tests/unit/test_enforcement_models.py tests/unit/test_action_request.py tests/contract/test_enforcement_protocol.py tests/integration/test_enforcement_cli.py tests/integration/test_enforcement_executor.py -n0 -q` | 0 | 191 passed |
| `pytest tests/contract/test_registry_control_plane_guard.py tests/contract/test_path_scope_boundaries.py tests/contract/test_run_code_static_check.py tests/security/test_enforcement_adversarial.py tests/integration/test_dsh_enforcement.py tests/unit/test_enforcement_drivers.py -n0 -q` | 0 | 88 passed |
| `pytest tests/unit tests/contract -n0 -q` | 1 | 2323 passed, 6 skipped, **31 errors**——**全部**是 pytest `tmp_path` 工厂在 `.tmp/tmp/pytest-of-ZNM/*/.lock` 上的 `PermissionError`（受限沙箱的已知限制；全部发生在 setup 阶段，涉及 api_contract / build_notebooks / check_arch_style / check_repo_consistency / dgate2_run_record / orchestration_loop_guards / validator_adapters / validator_registry，**与本次改动文件无关**）。B1 相关批次（用仓库 `tmp_root`）在同一环境全部通过 |
| `.venv\Scripts\python.exe .tmp\b1-matrix\run_matrix.py --label before` / `--label after` | 0 / 0 | 36 行 × 3 列 + gate9 18 行 |
| `enforcement.cli registry --approve --reviewer dshznm` | 0 | 10 tools |
| `enforcement.cli registry --verify` | 0 | 10/10 ok |
| `approval_allowlist_audit.py --check --registry ... --approved ...` | 0 | 0 hits |
| `enforcement.cli self-check` | 0 | registry=… tools=10 approved=10；只余本机找不到 pwsh 的**警告**（不静默通过） |
| `enforcement.cli approve --family exec.pwsh:tests`（真实注册表 + 示例请求，产物落 .tmp） | 0 | 1.3 条子，command 为族 union，approval_id=approval-exec.pwsh-tests |
| 导入链自检 `python -c "import enforcement.approvals; import enforcement.precheck; import enforcement.cli; import adapters.dsh.hooks"` | 0 | 每次改完 Hook 导入链上的文件都跑过 |

> 2026-10-20 事故记录（代价换来的硬规则）：本次会话在改 `approvals.py` 时漏了一行
> `from dataclasses import dataclass`，而它在 dsh Hook 的导入链上
> （`src/adapters/dsh/hooks.py:82 → adapters.dsh.enforcement → enforcement.approvals`），
> Hook 启动即崩、宿主按"未知状态=失败关闭"拒绝**全部**工具调用，整台受治会话被锁死，
> 最后靠使用者手工补那一行才恢复。之后的纪律：**每次写完 Hook 导入链上的文件立刻跑一次导入自检，
> 退出码 0 才做下一步**（本表最后一行）。

## 10 已知残留 / 下一步 / 无读数项

**残留（有读数，写清是什么）**：

1. **dsh 桥的选择器还没读注册表默认值**：`src/adapters/dsh/enforcement.py` 的
   `select_approval(...)` 调用点不在本次写区，没有传 `param_defaults`。
   影响只在**出示顺序**（1.3 条子省略格时可能不是最贴合的那张），判定不受影响
   （`pre_execute → verify_approval` 用的是注册表数据）。修复 = 那一处多传一个参数。
2. **外部受治副本的已审核哈希是旧格式产物**：`C:/Users/ZNM/Downloads/Comparison-test/Governance/.policy`
   的 `tool-registry.approved.json` 由旧 schema 生成，`registry_hash_drift` 实测 **10**（全部工具）。
   真实读数、不是测试坏了：受治侧必须按新格式重新 `registry --approve` 才回 0。
   契约用例把该读数钉成 `{0, 10}` 两种状态（0=已重审，10=还没重审），其它数字才算问题。
3. **`tools/phase_evidence.py:361` 仍硬编码 `"registry_schema_version": "1.0"`**：
   不在本次写区；阶段证据会与 `REGISTRY_SCHEMA_VERSION="1.1"` 不一致（与 OCR 评审 2026-10-07 点名同一处）。
4. **多模式族签出的 union 模式对"条子 × 白名单"审计不可读**：`_literal_prefixes` 对
   `(?:(?:p1)|(?:p2))` 取不出字面前缀 → 那一条按 `unavailable`（"没有读数"）记，
   不折叠成 0 命中。**族层面的 `--check` 是权威口径**；单模式族与手写单模式条子仍可读。
5. **5.11 仍未修**：`default` 只用于审批匹配，**不改驱动读参行为**（Lead 条件 1）；
   注册表里"声明了却没被驱动消费的参数"这条缺口保持原样。
6. 未跑 `python tools/ci_local.py`、未 `git commit` / `git push`（按任务边界，门禁由 Lead 串行跑）。

**无读数（缺什么写清楚）**：

- **真实受治会话的 9/9 常用命令**：缺使用者签发的 1.3 条子；当前只有夹具矩阵 9/9。
- **受治侧重审后的 drift=0**：缺受治侧重新审核；当前读数是 10（未重审），两种状态已写进契约用例。

**不适用**：

- 400 份真实会话回放的"0 误伤"读数：那是 B3（只读命令族读面闸门）的门，不是 B1 的。
- `run_in_background=true` 的"执行期证据"：平台显式不支持后台执行，只有"拒绝"这一种读数。

## 11 留给 Lead 的文档更新点（我不会改这些文件）

- **04-open-work.md**：5.69 的"残余（未修）"应改为已修并引用本读数；新增一条"B1 落地后的两处新残留"
  （§10 的 1 与 4）；§10 的 2/3 记成待办（受治侧重审、phase_evidence 常量）。
- **05-implementation-plan.md**：§4 B1 的"状态"从"已定（需解冻）"改为落地 + 读数路径；
  §3.2 的"参数域改法"补一句"默认值只声明 `timeoutMs/workdir/run_in_background`，提权参数不给默认值"。
- **06-plan-progress.md**：新增 B1 条目（日期、改动面、读数、门禁读数、结论）。
- **AGENTS.md**：第 14/17/55 条附近补一句"审批协议 1.3 的参数域：省略的可选参数按注册表默认值补齐，
  1.1/1.2 记录不受影响"；把 `REGISTRY_SCHEMA_VERSION` 1.0→1.1 与
  `APPROVAL_SCHEMA_VERSION` 1.2→1.3、`APPROVAL_AUDIT_SCHEMA_VERSION` 1.0→1.1 登记进第 55 条的表；
  另建议加一条"改 Hook 导入链上的模块后必须立刻导入自检"（这次锁死会话的教训）。
- **tools/README.md**：`approval_allowlist_audit.py` 那一行补 `--check` 模式与
  载荷版本 1.1、新增的两行机器行（`FAMILY-CHECK:` / `HITS:` 的 families 段）。
