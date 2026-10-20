# 2026-10-21 C3 第三件 v1：控制面（`.policy`）写面阻断 + 三路径验证套件

> 性质：**读数**（子会话 `c3-control-plane`，task-4）。依据 05 §4 C3 的门
> 「删除/执行/控制面写被前置阻断」、`readings/2026-10-21-C1C2C4-adjudication-draft.md` §4/§5
> 定下的 v1 范围，以及使用者 2026-10-20 会话的授权。
>
> 边界遵守：不改判定路径、不新增 reason code、不改 `precheck.py` / `action.py` / `drivers.py`；
> 不提交、不跑 `tools/ci_local.py`、不改 04/05/06/AGENTS/tools/README；没有删 `.tmp` 下任何目录。

## 0 一句话

C3 第三件的真实缺口是**数据缺口**：写类工具的 `blocked_prefixes` 不含 `.policy`，而读面从 B3
（注册表 1.2 的 `read_guard`）起已经封住它——同一条信任根两条路，读挡着、写敞着。本轮把
`.policy` 补进四个自动放行写工具的受保护前缀（注册表 `1.2 → 1.3`，重新审核），并用 17 条
固定请求的前后矩阵与两个测试套件把「只有 `.policy` 写面翻面、其余逐条相等」交成可复核读数。
**判定路径与 reason code 一个字没改。**

## 1 问题与改前读数

### 1.1 缺口证据（数据与代码位置）

| 事实 | 证据 |
| --- | --- |
| 四个自动放行写工具的 `blocked_prefixes` 是 `[policies, registry, adapters, api, validation]`，**不含 `.policy`** | `git show HEAD:registry/tool-registry.yaml`（1.2）的 `fs.edit` / `fs.write` / `orc.fs.edit` / `orc.fs.write` 段 |
| 同一份信任根的**读面**早已封住 | `exec.pwsh` / `exec.bash` 的 `read_guard.forbidden_path_prefixes: [".policy"]`（1.2，B3） |
| 写面的闸只认数据 | `src/enforcement/action.py#L299` `blocked_path_prefix`：casefold + 去尾斜杠 + **路径分段边界**（`.policyx/` 不命中）；`precheck.py#L401` 第 4a 项 → `path_out_of_scope`；`drivers.py#L258` 驱动层再查一遍 |
| 后果 | 受控项目里的审批条子（`approval.json`）、审计账本（`audit.jsonl`）、受控执行台账（`enforcement-ledger.jsonl`）都能被 `approval: none` 的写工具直接覆盖——"审计链是追加写"只对不经过这条路的写者成立 |

### 1.2 改前读数（HEAD 副本，真实 CLI，dry_run）

`git archive HEAD src registry policies` 的副本 + 当前 `.venv` 解释器，逐条
`python -m enforcement.cli precheck --request … --json`（`dry_run`：不认领 action_id、不写限流台账）。
固定请求集见 §3，这里只摘结论：

- `.policy` 写面 **8/8 `allow`**（`fs.edit` / `fs.write` / `orc.fs.edit` / `orc.fs.write`，
  含 `.POLICY`、`./.policy`、`.policy` 三种写法）；
- 近似前缀 `.policyx/audit.jsonl` `allow`（精度对照，不应翻面）；
- `policies/`、`registry/` 写 → `block / path_out_of_scope`（既有拦截面）；
- 受控项目内普通文件 → `allow`；
- 删除路径：`exec.pwsh` 的 `Remove-Item -Recurse .` 与 `exec.bash` 的 `rm -rf .policy` →
  `block / command_not_allowlisted`；
- 执行路径：`exec.run_code` 含 `import os` → `block / code_blocked`（`code_check` FAILED）；
- 命令对照：`git status --short` → `allow`；无害 `run_code` → `allow_with_warnings`。

## 2 改动面

| 文件 | 改动 | 为什么 |
| --- | --- | --- |
| `registry/tool-registry.yaml` | `registry_schema_version: "1.2" → "1.3"`；四个写类工具的 `file_path` 参数 `blocked_prefixes` 追加 `".policy"`（并在 `fs.edit` / `orc.fs.edit` 处写清理由） | 补数据缺口；键集合没变，变的是**这一列受保护前缀的取值** |
| `src/enforcement/models.py` | `REGISTRY_SCHEMA_VERSION = "1.3"`；`SUPPORTED_REGISTRY_SCHEMA_VERSIONS = {1.0, 1.1, 1.2, 1.3}`（+ 注释与一处陈旧的版本类比句） | AGENTS 第 55 条：取值语义变了就必须显式升版；旧注册表照常加载 |
| `registry/tool-registry.approved.json` | 重新审核（`--reviewer dshznm`） | 数据改动必须重审，否则 pre-check 以 `schema_not_approved` 拒绝整个工具 |
| `tests/contract/test_registry_control_plane_guard.py` | `CONTROL_PLANE_PREFIXES` 加 `.policy`；反真空断言扩到四个写工具；新增 8 条信任根写入用例 + `.policyx` 精度 + `policies/` 回归 | 与文件既有两条断言（数据面 / 行为面）同形，不新造套件风格 |
| `tests/contract/test_enforcement_protocol.py` | orc 写工具的 `blocked_prefixes` **精确集合**断言加 `.policy` | 该断言原本钉死五个前缀；数据改了它必须同批改（否则编排层边界与 dsh 侧漂开没人发现） |
| `tests/security/test_control_plane_write_guard.py`（新增） | 三路径验证套件：写（3 条信任根 + 精度 + 回归）/ 删除（`Remove-Item`、`rm -rf`）/ 执行（`import os` 与无害代码对照）+ 重审不变式 + 6 条坏 `blocked_prefixes` 声明的加载期拒绝 | 05 §4 C3 的三条路径要有同一份可复核读数 |
| `tests/unit/test_enforcement_approvals.py` | 注册表轴版本断言 1.2 → 1.3、`SUPPORTED` 断言加 1.3、旧文档加载循环加 `"1.2"`、测试名与 docstring 同步 | **Lead 在 task-4 rev 3 显式授权**（2026-10-21）；B3 升 1.1→1.2 时同样改过这处 |
| `docs/.../readings/2026-10-21-C3-control-plane-write-guard.md` | 本读数 | — |

### 2.1 硬编码 `"1.2"` 的全仓清点（Lead 要求逐行列）

只针对 **注册表轴**语义（不是所有字面量 1.2）。`git grep` 的全部命中与处置：

| 位置 | 处置 | 理由 |
| --- | --- | --- |
| `tests/unit/test_enforcement_approvals.py:436-441` | **改**（1.2→1.3；SUPPORTED 加 1.3；旧文档循环加 1.2） | 断言"当前注册表轴"，不升版它就必红 |
| `tests/contract/test_enforcement_protocol.py:401-407` | **改**（精确集合加 `.policy`） | 数据面断言：编排层与 dsh 侧必须同一组前缀 |
| `tests/contract/test_registry_control_plane_guard.py:34` | **改**（`CONTROL_PLANE_PREFIXES` 加 `.policy`） | 同上，自动放行写工具的数据面 |
| `tests/unit/test_precheck_read_guard.py:108` | **不改** | 它在**构造**一份 1.2 文档来测 read_guard；1.2 仍是受支持版本，构造旧形状是设计 |
| `tests/enforcement_support.py:208`、`tests/fixtures/approval_audit/registry*.yaml`、`examples/dsh/b-plan/tool-registry.local.yaml` | **不改** | 分别是测试注册表 / 旧形状夹具 / 示例本地注册表，都是 1.0；1.0 照常加载 |
| `src/enforcement/models.py:106`（ENFORCEMENT 轴的注释里的版本类比） | **改**（1.0/1.1/1.2 → 1.0/1.1/1.2/1.3） | 注释与常量保持一致；纯注释，不改语义 |
| `tools/phase_evidence.py:361` | **不改**（不在写区） | 既有残项（04 5.83③）：阶段证据里硬编码 `registry_schema_version: "1.0"`，与常量 1.3 不一致。**这条会让阶段证据说错版本**，应尽快单开一次修 |
| `docs/**`（含 B1/B3 读数、06 记录） | **不改** | 历史读数只登记当时值；06 的新行由 Lead 写 |

**别的轴**：`ENFORCEMENT_SCHEMA_VERSION` 仍是 `1.1`（本轮没有新 reason code，不动它）。
`evaluation/results` / dgate2 等载荷里的 1.2 与注册表轴无关。

### 2.2 版本轴判决（AGENTS 第 55 条）

`blocked_prefixes` 的**键**没变，但**取值列**多了一项受保护前缀、且这一列进 `schema_hash`
（授权面数据）。与 B2 的 `selection.level` 多出取值 "support"（PIPELINE 1.3→1.4）同型：
取值语义变了就是协议变化。因此 `REGISTRY_SCHEMA_VERSION` 1.2→1.3，`SUPPORTED` 显式列出
1.0/1.1/1.2/1.3（旧文档照常加载，不制造兼容窗口）。

## 3 前后矩阵（17 条，同一份用例表；改前 = `git archive HEAD` 副本，改后 = 工作树）

两条都是**真实 CLI**：`python -m enforcement.cli precheck --request … --json`（`dry_run`）；
同一份 `run_matrix.py`、同一批请求文档，`.tmp/c3-control-plane/merge_matrix.py` 机械合并并检查
两条不变式——**只有 `control_plane_write` 组允许翻面，且翻面后的 reason code 必须是
`path_out_of_scope`；其余逐条 decision/reason_code 相等**。合并结果：`violations: none`。

| # | 工具 | 目标 | 组 | 改前 decision / reason_code | 改后 decision / reason_code | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | fs.edit | .policy/approval.json | control_plane_write | allow / allow | block / path_out_of_scope | **新拦** |
| 2 | fs.write | .policy/audit.jsonl | control_plane_write | allow / allow | block / path_out_of_scope | **新拦** |
| 3 | fs.write | .policy/enforcement-ledger.jsonl | control_plane_write | allow / allow | block / path_out_of_scope | **新拦** |
| 4 | fs.edit | .POLICY/approval.json | control_plane_write | allow / allow | block / path_out_of_scope | **新拦** |
| 5 | fs.write | ./.policy/audit.jsonl | control_plane_write | allow / allow | block / path_out_of_scope | **新拦** |
| 6 | fs.write | .policy | control_plane_write | allow / allow | block / path_out_of_scope | **新拦** |
| 7 | orc.fs.edit | .policy/approval.json | control_plane_write | allow / allow | block / path_out_of_scope | **新拦** |
| 8 | orc.fs.write | .policy/audit.jsonl | control_plane_write | allow / allow | block / path_out_of_scope | **新拦** |
| 9 | fs.write | .policyx/audit.jsonl | precision | allow / allow | allow / allow | 不变（精度） |
| 10 | fs.write | policies/security/SEC-001.yaml | precision | block / path_out_of_scope | block / path_out_of_scope | 不变（回归） |
| 11 | fs.edit | registry/tool-registry.yaml | precision | block / path_out_of_scope | block / path_out_of_scope | 不变（回归） |
| 12 | fs.write | src/shop/cart_service.py | precision | allow / allow | allow / allow | 不变（对照） |
| 13 | exec.pwsh | Remove-Item -Recurse . | delete_execute | block / command_not_allowlisted | block / command_not_allowlisted | 不变 |
| 14 | exec.bash | rm -rf .policy | delete_execute | block / command_not_allowlisted | block / command_not_allowlisted | 不变 |
| 15 | exec.run_code | code: import os | delete_execute | block / code_blocked | block / code_blocked | 不变 |
| 16 | exec.pwsh | git status --short | delete_execute | allow / allow | allow / allow | 不变（对照） |
| 17 | exec.run_code | code: print('ok') | delete_execute | allow_with_warnings / allow_with_warnings | allow_with_warnings / allow_with_warnings | 不变（对照） |

读法：

- **1–8（控制面写）**：8/8 改前 `allow`、改后 `block / path_out_of_scope`。其中 4、5、6 是同一目标
  的拼写归一化（`.POLICY`、`./.policy`、前缀本身）——`blocked_path_prefix` 的口径是
  casefold + 去尾斜杠 + **分段边界**，漏掉任何一种都是真实可用的绕过；7、8 是编排层，
  两个 Agent 的信任根边界必须一致。
- **9–12（精度与回归）**：`.policyx/` **不误伤**（分段边界，不是字符串前缀）；`policies/` 与
  `registry/` 仍 `path_out_of_scope`；普通文件仍 `allow`。这 4 条前后**逐条相等**。
- **13–17（删除 / 执行）**：删除路径仍是 `command_not_allowlisted`（dsh 工具表没有 delete 操作，
  `Remove-Item` / `rm -rf` 连白名单都进不去），执行路径仍是 `code_blocked`（`code_check` FAILED）。
  两条路径的 reason code **一个字没变**。
- 矩阵的机器可读副本：`.tmp/c3-control-plane/matrix-{before,after}.json`、
  `matrix-invariants.json`（不提交；重建命令见 §8）。

## 4 测试

| 命令 | 结果 |
| --- | --- |
| `python -m pytest tests/security/test_control_plane_write_guard.py -n0 -q` | **18 passed**，exit 0 |
| `python -m pytest tests/contract/test_registry_control_plane_guard.py -n0 -q` | **13 passed**，exit 0 |
| `python -m pytest tests/contract/test_enforcement_protocol.py -n0 -q` | **14 passed**，exit 0 |
| `python -m pytest tests/unit/test_enforcement_approvals.py -n0 -q` | **44 passed**，exit 0 |
| `python -m pytest tests/unit tests/contract -n0 -q` | **2417 passed, 6 skipped**，exit 0 |
| `python -m pytest tests/integration tests/security -n0 -q` | **828 passed**，exit 0（B3 同年同日读数是 810；+18 = 本轮新增的 security 套件条数） |
| `python -c "import enforcement.approvals; import enforcement.precheck; import enforcement.models; import adapters.dsh.hooks; print('ok')"` | ok，exit 0（每次写 `models.py` 后立刻跑，见 §8 纪律） |

用例覆盖：

`tests/security/test_control_plane_write_guard.py`（三路径 + 数据面，18 条）：

- **写**：`fs.write` 写 `.policy/audit.jsonl` → block/`path_out_of_scope`；`fs.edit` 改
  `.policy/approval.json` 的 `granted_by` → block；`orc.fs.write` 写台账 → block（两个 Agent 同界）；
- **精度**：`.policyx/audit.jsonl` 的 `path_prefixes` 必须 PASSED（不误伤）；
- **回归**：`policies/` 仍 block/`path_out_of_scope`；
- **删除**：`Remove-Item`、`rm -rf` → `command_not_allowlisted`，且 `path_prefixes` 显式 SKIPPED
  （命令类工具没有 path 参数，不假装查过）；
- **执行**：`import os` → `code_blocked` + `code_check` FAILED；无害代码 → `code_check` PASSED
  但止步于 `approval_required`（"代码不安全"与"没有审批"是两件事）；
- **重审不变式**：四个写工具的当前描述必须与已审核哈希一致（`is_approved`）——改数据忘了重审时，
  pre-check 会以 `schema_not_approved` 拒绝整个工具；
- **加载期拒绝**：6 条坏 `blocked_prefixes` 声明（`/etc`、`..`、空串、`a//b`、忽略大小写重复、
  反斜杠绝对路径）在**注册表加载期**报 `RegistryError`；另有一条"声明在非 path 参数上"被拒
  （会被静默忽略的声明直接拒绝）。**此前 `blocked_prefixes` 没有这类加载期用例**（`read_guard`
  有 15 条），本轮补上。

`tests/contract/test_registry_control_plane_guard.py`（13 条）：数据面（四个自动放行写工具都必须
声明 `.policy` + 反真空断言覆盖 `fs.*` 与 `orc.fs.*`）+ 8 条信任根写入 block 用例 + `.policyx`
精度 + `policies/` 回归 + 对照组。

## 5 注册表重审与 verify

```
$env:PYTHONPATH="src"
python -m enforcement.cli registry --approve --reviewer dshznm   # exit 0
python -m enforcement.cli registry --verify                      # exit 0，10/10 ok
python tools/approval_allowlist_audit.py --check --registry registry/tool-registry.yaml \
    --approved registry/tool-registry.approved.json               # HITS 0 / drift 0 / exit 0
```

`registry/tool-registry.approved.json` 的 diff 要点：

- `reviewed_by`: `dshznm`；`approved_at`: `2026-10-20T18:41:34.147952Z`（本机时钟）；
- `governance_digest`: `sha256:47fa192d…` → **`sha256:290b5086…`**（治理表覆盖
  `registry_schema_version`，1.2→1.3 必然变）；
- `registry_digest`: `sha256:33e330b8…` → **`sha256:cc8d184d…`**；
- **只有 4/10 工具的 `schema_hash` 变了**：`fs.edit` / `fs.write` / `orc.fs.edit` / `orc.fs.write`
  （B1 加 `command_families`、B3 加 `read_guard` 时是 10/10 全变，因为那两次是**给每个工具加字段**；
  本轮是给四个已有字段改取值，所以其余六个逐字不变——这条差异本身可以当作"改的是数据不是形状"的旁证）；
- `approval_allowlist_audit --check` 的 `registry_hash_drift` 从 B3 读数时的 10 变成 **0**
  （B3 之后重审过一次；本轮重审后仓库侧仍是 0。受治侧副本的 drift 不在本读数范围内，见 §6）。

## 6 未核实项与残余

1. **受治侧副本没有同步**（与 B3 §7.1 同型）：受治项目里的 `.policy/tool-registry.local.yaml` 仍是
   旧形状（无 `read_guard`、更没有 `.policy` 前缀）。**本次改动只在仓库这一侧生效**；要让受治
   会话真的挡住 `.policy` 写入，受治侧必须同样改数据并重审（`registry --approve --reviewer <name>`）。
   仓库侧证据：`tests/contract/test_approval_allowlist_audit.py` 的 live 比对仍接受
   `registry_hash_drift ∈ {0, 10}`，本轮仓库侧是 0。
2. **控制面之外的写面没有封（本轮范围外，需要一次数据裁定）**：`.policy` 只是"信任根"的一个位置。
   以下目标当前都还能被自动放行的写工具改写，我没有扩大范围（扩大范围 = 改数据 + 重审，属于裁定）：
   - `.git/`：**实测仍是 `allow`**（`fs.write .git/hooks/pre-commit`、`fs.edit .git/config`
     在改前/改后两份树上都是 `allow`，探针 `.tmp/c3-control-plane/probe_git_surface.py`）。
     写 git hook 等于间接获得执行能力——"执行路径被前置阻断"挡的是 `run_code`/`pwsh` 那两条路，
     挡不住"先写 hook、等下一次 git 命令"。
   - 冻结的评测件与门槛：`dgate2/scorer/**`（含 `manifest.sha256`）、`evaluation/thresholds.yaml`、
     `evaluation/results/**`——它们定义"怎么打分"，改了读数就不可比。
   - 检索与溯源数据：`knowledge/corpus.yaml`（规则溯源与语料清单）。
   - 治理文档与 CI：`AGENTS.md`、`docs/project/**`、`.github/workflows/**`、`tools/**`（仪器本身）、
     `pyproject.toml` / `pytest.ini` / `requirements.*`。
   判据是"改了就改变治理或读数"；要不要进 `blocked_prefixes` 是**一次数据决策**（会同时改变
   `schema_hash` 与重审范围），不在本轮夹带。
3. **符号链接不在承诺范围内**：`blocked_path_prefix` 只看参数里的**路径字符串**，不解析 symlink /
   junction。受控项目里若存在指向 `.policy` 的链接，经链接路径写入仍会放行。这是"结构性检查不是
   沙箱"的同型边界（AGENTS 第 17 条末句），要封必须靠运行时的文件系统沙箱，不是再加一列前缀。
4. **`.policy` 只在工作区根成立**：前缀匹配吃的是**工作区相对路径**。把工具的工作区指到子目录
   （例如 `src/`）时不构成这条前缀——但那时工作区里也没有 `.policy`，属于另一个受治边界。
5. **审计 / 台账路径可以被搬走**：dsh 桥与 hooks 都允许显式指定 `--audit` / `--ledger`（例：
   `ledger_path_overridden` 留痕）。写面闸只挡 `.policy` 这一处；"账本被配置到别处"不在本闸承诺内。
6. **删除路径的现状码依赖命令白名单**：若将来把 `Remove-Item` / `rm` 加进白名单，删除路径就只剩
   读面 / 片段检查，届时必须重新评估（这是数据变更带来的语义迁移，不是本闸的漏洞）。
7. **未跑 `tools/ci_local.py`**（任务边界要求）：门禁里的步骤级检查（注册表审核步骤、受控执行闭环、
   编排闭环、阶段证据）未在本轮验证。已跑 §4 的四个 pytest 组合与三条 CLI 读数；它们覆盖这些闭环的
   **代码路径**，不等于门禁本身通过。
8. **`tools/phase_evidence.py:361` 硬编码 `"1.0"`**（04 5.83③ 既有残项）：阶段证据里的
   `registry_schema_version` 会与常量 1.3 不一致。不在本会话写区。
9. **`docs/project/architecture/tech-detail/04-受控执行/` 的生成物**仍只讲两层命令检查，
   未提 `read_guard`（B3 残项）也未提 `.policy` 写面——属于 Lead 的文档更新点（§7）。

## 7 留给 Lead 的更新点（本子会话按边界**没有**动这些文件）

| 文件 | 要写什么 |
| --- | --- |
| `04-open-work.md` 5.84 | 状态：C3 第三件 **v1 已落地**（2026-10-21）：`.policy` 写面数据 + 注册表 1.3 + 重审 + 17 条前后矩阵 + 两个套件；**残留**=§6 的 1/2/3（受治侧同步、`.git` 等控制面之外、symlink）；"整树 43 条读数"仍差 |
| `04-open-work.md` 5.86 | 关联：B3 的读面闸与本次写面闸是**同一份信任根的两面**；B3 的"受治侧未同步"同时命中本轮的写面数据 |
| `05-implementation-plan.md` §4 C3 行 | 门列补实测：删除（命令白名单）/ 执行（code_check）/ 控制面写（`.policy` 8 条翻面、`.policyx` 0 误伤）；C3 第三件 v1 状态 |
| `06-plan-progress.md` | 新增一行进度/决策：C3 第三件 v1，含两条口径决定（① 升版理由是"取值语义变"而非"加键"；② 写面闸与读面闸共用同一份"受控项目相对路径"规范化，**不新增 reason code**）与"受治侧未同步" |
| `AGENTS.md` 第 13 条 | 受保护前缀清单补 `.policy`（信任根：审批条子 / 审计账本 / 台账），并写清它进 `schema_hash`、改数据必须重审 |
| `AGENTS.md` 第 55 条版本轴表 | `enforcement.models.REGISTRY_SCHEMA_VERSION` **1.2 → 1.3**（`blocked_prefixes` 取值列 + `.policy`；SUPPORTED 保留 1.0/1.1/1.2/1.3）。注意 `ENFORCEMENT_SCHEMA_VERSION` **不动**（没有新 reason code） |
| `tools/README.md` | 本轮**没有**新增工具；若要把 §3 的矩阵变成常驻仪器（例如 `tools/control_plane_write_probe.py`），在那里登记 |
| 受治侧 `tool-registry.local.yaml`（不在本仓库） | 同步 `.policy` 前缀并重新审核（§6.1） |

## 8 复现命令与改动面

```powershell
# 1) 改前读数：HEAD 副本 + 真实 CLI
New-Item -ItemType Directory -Force .tmp/c3-control-plane/head-tree | Out-Null
git archive --format=tar HEAD src registry policies -o .tmp/c3-control-plane/head.tar
tar -xf .tmp/c3-control-plane/head.tar -C .tmp/c3-control-plane/head-tree
$env:PYTHONPATH="$PWD/.tmp/c3-control-plane/head-tree/src"
.venv\Scripts\python.exe .tmp/c3-control-plane/run_matrix.py --tag before     --repo .tmp/c3-control-plane/head-tree

# 2) 改后读数：当前工作树
$env:PYTHONPATH="$PWD/src"
.venv\Scripts\python.exe .tmp/c3-control-plane/run_matrix.py --tag after --repo .

# 3) 前后矩阵合并 + 不变式检查（只翻 .policy 写面 / 其余逐条相等）
.venv\Scripts\python.exe .tmp/c3-control-plane/merge_matrix.py

# 4) 控制面之外的探针（.git 写面；前后都是 allow，登记为残余）
.venv\Scripts\python.exe .tmp/c3-control-plane/probe_git_surface.py after .

# 5) 注册表重审 + verify + 族/白名单审计
$env:PYTHONPATH="src"
.venv\Scripts\python.exe -m enforcement.cli registry --approve --reviewer dshznm
.venv\Scripts\python.exe -m enforcement.cli registry --verify
.venv\Scripts\python.exe tools/approval_allowlist_audit.py --check     --registry registry/tool-registry.yaml --approved registry/tool-registry.approved.json

# 6) 测试
.venv\Scripts\python.exe -m pytest tests/security/test_control_plane_write_guard.py -n0 -q
.venv\Scripts\python.exe -m pytest tests/contract/test_registry_control_plane_guard.py -n0 -q
.venv\Scripts\python.exe -m pytest tests/unit tests/contract -n0 -q
.venv\Scripts\python.exe -m pytest tests/integration tests/security -n0 -q

# 7) Hook 导入链自检（每次写 src/enforcement/models.py 后立刻跑；本会话每次 exit 0）
.venv\Scripts\python.exe -c "import enforcement.approvals; import enforcement.precheck; import enforcement.models; import adapters.dsh.hooks; print('ok')"
```

改动的文件（本子会话）：

```
 M registry/tool-registry.yaml                       # 1.2→1.3 + 四个写类工具补 .policy
 M registry/tool-registry.approved.json              # 重新审核（--reviewer dshznm）
 M src/enforcement/models.py                         # REGISTRY 1.2→1.3 / SUPPORTED 保留 1.0-1.3
 M tests/contract/test_registry_control_plane_guard.py   # 数据面加 .policy + 12 条行为面
 M tests/contract/test_enforcement_protocol.py       # orc 写工具精确前缀集合加 .policy
 M tests/unit/test_enforcement_approvals.py          # 注册表轴版本断言（Lead 授权）
 ?? tests/security/test_control_plane_write_guard.py # 新增 18 条三路径套件
 ?? docs/project/engineering-policy-platform/readings/2026-10-21-C3-control-plane-write-guard.md
```

**纪律**（AGENTS / 04 第 5.85 条）：`models.py` 在 dsh Hook 的导入链上，**每次写入后立刻**跑
`import enforcement.approvals; import enforcement.precheck; import enforcement.models; import adapters.dsh.hooks`；
本子会话每次都是 exit 0 才做下一步。
