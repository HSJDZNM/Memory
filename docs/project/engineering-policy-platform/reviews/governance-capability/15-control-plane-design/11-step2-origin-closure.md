# 11 · 台阶 2：归因闭集与核验前置（R-g）的读数与字段级差集

- **执行**：2026-09-29（本机）；控制面重构会话（唯一写者）+ 一个并行的执行者（JS 侧，写域互斥）。
- **树**：`C:\Users\ZNM\Downloads\Memory-rf` = 分支 `refactor/control-plane`，本台阶的提交见文末。
- **依据**：方案 §3.4（一个归因闭集 + 核验前置）与 §4 台阶 2；判据 **R-g**（归因不得指错对象）；
  差集纪律 **R-d**（任何改变 decision 的步骤必须交出**字段级**差集）。
- **本文件是什么**：台阶 2 的设计口径、R-d 差集读数、R-g 的红→绿读数，以及**没有做**的事。

## 1 这一步要解决什么（一句话）

失败关闭只完成了一半：另一半是**告诉人一个对的原因**。实测过的错法是把「Hook 起不来」翻译成
「Node 没装」——Node 的 spawn 在 **cwd 不存在**时把 ENOENT 归给**可执行文件**，而那个可执行文件
存在且可执行（14 号文档 §5 Q6）。台阶 2 把「指着谁」从**文本**升格成**数据**，并且规定：
写这条理由之前，先执行它的**证伪判据**。

## 2 R-d：字段级差集（改判定才要差集；本台阶**没有**改判定）

**口径**：11 个 `tests/fixtures/agent_events/dsh` 事件 fixture，各跑一次**生产入口**
（`python -m adapters.dsh.hooks`，真 stdin、过 `--hooks-config` 接线自检），把「退出码 +
VERDICT 判定行 + 那份审计的全部记录」整份收下来（时间戳字段 `timestamp` / `recorded_at` /
`elapsed_ms` 剔除），再对**基线树**（同一棵树 `git stash` 回退到本台阶之前）跑同一批，逐字段递归比对。
仪器：`.tmp\ctl-staging\rd_probe.py` + `rd_compare.py`；读数 `.tmp/rd-diff/decisions-{before,after}.json`
与 `.tmp/rd-diff/rd-field-diff.json`。

| # | 字段路径 | before | after | 说明 |
| --- | --- | --- | --- | --- |
| 1 | 11 个 fixture 的 `exit_code` | 逐个相同 | 逐个相同 | **判定完全没动** |
| 2 | 11 个 fixture 的 `VERDICT` 行 | 逐个相同（值相等） | 逐个相同 | 判定行**一个字都没改** |
| 3 | `pre-tool-use-edit-allow` / `-edit-block` / `-extra-fields` 的审计记录 | 无 `origin` 键 | **新增 `origin`**（`platform.evidence_unavailable`、`causal_link=proven`） | 本台阶的唯一新增字段 |
| 4 | `post-tool-use-edit` / `pre-tool-use-pwsh-execute` 的 `digest` / `recorded_at` | 各自一个值 | 各自**不同**的值 | **墙钟漂移，不是本步骤引入**：`recorded_at=utc_now()` 进摘要（`src/enforcement/audit.py:203,329`），同一棵树上重跑也会不同 |

**差集条数 = 7；其中 3 条是本台阶新增的 `origin` 键，4 条是墙钟漂移，0 条是判定变化。**

**为什么本台阶"不改变 decision"也要出差集**：因为它在审计里**新增了字段**。R-d 的原话是
"任何改变 decision 的步骤必须交出字段级差集"——本步骤没有改变 decision，但"没有"这个结论
本身必须由读数支撑，不能由"我觉得没改"支撑。

### 2.1 一条被撤回的改动（写下来，免得下次又有人这么改）

实现过程中曾经在 `run_hook` 里加过一层 `try/except`，把配置加载失败从
`reason_code=startup_error` 改写成 `config_error`（理由是"这个错误码更准确"）。
**已撤回**：那是**改变判定载荷**（`reason_code` 是判定行与审计的字段），不属于台阶 2 的授权范围；
现在配置加载失败在库里**原样抛出**，归因由生产入口 `main()` 用同一个 `origin_from_failure` 计算。
撤回前后的读数都在 `.tmp/rd-diff/` 里。

## 3 归因闭集（方案 §3.4 的前半）

**落点**：`src/provenance/origin.py`（形状）+ `src/provenance/origin_runtime.py`（核验）。
放 `src/provenance/` 的理由与 §3.1 的针脚相同：内核目录里改一行必须变红，归因实现自己坐在内核
目录会造成自干扰。

**闭集**（`origin` 只能取这五族）：

| 族 | 本次实现过的取值 | 什么时候用 |
| --- | --- | --- |
| `platform.*` | `platform.config_unreadable`、`platform.evidence_unavailable` | 平台自己读不到输入 / 拿不到证据 |
| `agent_runtime.*` | `agent_runtime.spawn_denied`、`agent_runtime.spawn_failed` | Agent 运行时起不了钩子命令 |
| `host.*` | `host.workdir_unreadable` | 宿主这一侧的路径不可读 |
| `project.*` | `project.workdir_missing` | 被治理项目自己的目录声明错了 |
| `unknown_origin` | `unknown_origin` | **核验证伪了自己人**，或这条理由没有可执行的判据 |

**每个 origin 必须携带**：`owner` / `object{kind,value,source}` /
`observation{method,result,verified,verified_at,run_scoped}` / `fix` / `causal_link`。
**写不出 `fix` 的 origin 不许存在**——空串、空白、缺键一律 `OriginError`；未知取值、未知
`object.kind`、未知 `method`、未知 `causal_link` 同样报错（与平台其他"未知一律拒绝"同一条纪律）。

**跨语言契约**：`payload_is_well_formed()` 断言载荷**恰好**是这些键（多一个键也算违约）。
JS 侧（插件）逐字实现同一份形状——两侧各自演化时，最先坏掉的就是这种没有检查的自由度。

## 4 核验前置（方案 §3.4 的后半）

**四条硬规则**（`origin_runtime.py` 的实现与注释逐条对应）：

1. **核验前置**：说"配置读不到"之前先真的去读它——`stat` → 是不是文件 → 能不能按 UTF-8 读；
2. **核验允许证伪自己人**：判据不成立时**只能**落 `unknown_origin`，`causal_link=unproven`，
   **不许**把对象换成"配置里的某个字段"继续指控；
3. **失败关闭不因为归因变松**：归因是**诊断**，不是第二份判定——它既不进 `decision` 也不进
   `violations`，消费者不得据它 allow/block；
4. **总能给出一条**：给不出对象时就是 `unknown_origin`（写明"没有对象可核验"），而不是缺席——
   缺席会让读者把"这次没归因"读成"这次归因没问题"。

**配置族的原因码闭集**（`ORIGIN_BY_REASON_CODE`）：`startup_error` / `config_error` →
`platform.config_unreadable`；`wiring_error` → `platform.config_unreadable`（对象是
`hooks.json`，**不是** adapter 配置，所以调用方必须把**那一个**路径交进来）；
`evidence_unavailable` → `platform.evidence_unavailable`。**表外的原因码一律 `unknown_origin`**
并写明"本台阶只覆盖配置族与 spawn 输入族"。

## 5 R-g 的红→绿（判据）

判据 R-g 的原话：**工作目录存在而 spawn 抛 ENOENT 时，理由不得说"工作目录不存在"，
必须说"问题不在目录这一侧"。**

本台阶把这条判据从**文本**升格成**数据**：

| 输入 | 核验动作 | 归因（读数） |
| --- | --- | --- |
| 配置路径不存在 | `stat` | `platform.config_unreadable`、`causal_link=proven`、`observation.method=stat`、结果里带 `ENOENT` |
| 路径是目录 | `stat` | `platform.config_unreadable`、`object.kind=path`、结果说"它是一个目录" |
| 文件在、不是 UTF-8 | `read` | `platform.config_unreadable`、结果说"在，但读不出来"（与"不存在"分开） |
| 文件在、可读、是 UTF-8 | `load` | **`unknown_origin`**（核验证伪了自己人）、`causal_link=unproven`、结果里带"证伪" |
| 理由没有指名任何输入 | — | `unknown_origin`、`method=none`、结果说"没有对象可核验" |
| `event_replay` 等表外原因码 | — | `unknown_origin`、结果说"没有可执行的证伪判据" |

**红→绿怎么读**：不是"理由的措辞变了"，而是**同一个输入下，归因的对象与核验观测对得上**。
第 4 行是这条判据的**正面控制**：报"配置读不到"而配置其实好好的时候，结论必须变成
"这条理由不是配置那一侧的问题"，而不是换一个对象继续指控。

## 6 证据（改动的文件与哈希）

| 文件 | 行数 | sha256[:16] |
| --- | --- | --- |
| `src/provenance/origin.py`（新增） | 297 | `43d301bd547f1428` |
| `src/provenance/origin_runtime.py`（新增） | 202 | `4bd867cf875cbb81` |
| `src/provenance/__init__.py` | 75 | `f78b205f4722dd57` |
| `src/adapters/dsh/hooks.py` | 2071 | `75a0f52e7ac2bf83` |
| `tests/unit/test_provenance_origin.py`（新增） | 289 | `903163a785952273` |
| `tests/integration/test_dsh_origin_attribution.py`（新增） | 201 | `dc0bb36d1ff20a55` |

**读数**（`Memory-rf\.venv` 3.13.11 / pytest 9.1.1，`PYTHONPATH=<repo>/src`）：

| 命令 | 读数 |
| --- | --- |
| `pytest -q tests/unit/test_provenance_origin.py tests/integration/test_dsh_origin_attribution.py` | **21 passed** |
| `pytest -q tests/unit/test_dsh_pre_evidence.py tests/integration/test_dsh_pre_evidence_hook.py tests/contract/test_policy_hook_chain.py tests/unit/test_provenance_worktree.py tests/unit/test_provenance_wiring_scope.py tests/integration/test_provenance_loop.py` | **88 passed**（台阶 0 与 Phase 5 口径**没有回归**） |

## 7 JS 侧（spawn 输入族）：插件的 origin 闭集与核验前置

**执行者**：本会话的第二个执行者（写域与 Python 侧互斥：只有 `policy-hook.plugin.mjs` 与
`tests/contract/test_policy_hook_chain.py` 两个文件）。**落树通道与 Python 侧相同**（`patch.py` 清单，
每条替换恰好命中一次）；**未提交**，与 Python 侧同批提交。

### 7.1 改了什么

| 文件 | 行数 | sha256[:16] | 说明 |
| --- | --- | --- | --- |
| `src/adapters/dsh/policy-hook.plugin.mjs` | 399 → 514 | `A7BE5BDB17EEAAD5` → `26ABA823F6DD9949` | 新增 `buildOrigin` / `workdirFailureOrigin` / `createRunHook`；`inspectWorkdir` 五个分支各带 `origin` |
| `tests/contract/test_policy_hook_chain.py` | 1234 → 1566 | `93F25EC641616B6C` → `1AC992EFDBE11336` | **纯追加**：独立探针 `HARNESS_ORIGIN` + 11 条新用例 |

**两种形状一个字未改**：`tools/pre-execute` 仍然返回 `{kind:'deny', reason}`、
`tools/post-execute` 仍然返回 `{kind:'block', feedback}`；`origin` **不塞进**这两种形状，
只挂在 `runHook` 的返回值上（探针用同一个假 ctx 再装配一次来读它——为此把装配提成
`export function createRunHook(ctx, config)`，`apply` 的返回值与注册行为不变）。

### 7.2 七个场景的**实际**读数（真 node 驱动真插件，不是期望值）

| 场景 | `origin` | `method` | `verified` | `causal_link` | `object.kind` / `value` / `source` |
| --- | --- | --- | --- | --- | --- |
| `projectDir` 不存在 | `project.workdir_missing` | `stat` | true | proven | `workdir` / `missing-workdir` / `config.projectDir` |
| `projectDir` 是个文件 | `project.workdir_missing` | `stat` | true | proven | `workdir` / `not-a-dir.txt` / `config.projectDir` |
| 未给 `projectDir`、会话 cwd 不存在 | `project.workdir_missing` | `stat` | true | proven | `workdir` / `missing-workdir` / `会话 cwd（config.projectDir 未声明）` |
| 目录正常 + spawn ENOENT（**R-g 的原场景**） | `agent_runtime.spawn_failed` | `spawn` | true | proven | `command` / 命令前缀 / `config.command`（**不再指目录**） |
| 竞态（预检通过后目录被删） | `project.workdir_missing` | `stat` | true | proven | `workdir` / `vanishing-workdir` / `config.projectDir` |
| 目录正常 + spawn EPERM | `agent_runtime.spawn_denied` | `spawn` | true | proven | `command` / 命令前缀 / `config.command` |
| `projectDir` 存在（**放行**） | **不存在 `origin` 键** | — | — | — | — |

**R-g 那一行的读数原文**：`observation.result = 'spawn 报错原文：spawn C:\Program Files\nodejs\node.exe ENOENT'`——
真机那句**误导原文照留**（定位要看得见原文），但 `object.kind=command`、归因落 `agent_runtime`，
理由因此不再指向目录。`stat` 那几条的 `result` 是 `'stat 观测：该路径不存在（ENOENT）'`——
**核验真的执行过**，不是照抄错误原文。

### 7.3 跨语言契约（由 Python 侧补上一条 JS 执行者点名的缺口）

JS 执行者明确写了一条缺口：他没有把 `payload_is_well_formed` 写进自己的用例（不想让他的文件依赖
当时还未提交的 `provenance` 模块）。本文件因此在 Python 侧补两条用例（`tests/integration/test_dsh_origin_attribution.py`）：

1. **闭集一致性**：从插件源码里取 `ORIGIN_VALUES` / `OBSERVATION_METHODS` / `OBJECT_KINDS` /
   `ORIGIN_OBJECT_KIND` 的字面量，与 Python 常量逐项比对。**JS 是 Python 的**子集**，不是等集**：
   插件只实现 spawn 输入族那一半，配置族的核验在 Python 侧做。实测 JS 侧五个取值
   （`project.workdir_missing` / `host.workdir_unreadable` / `agent_runtime.spawn_denied` /
   `agent_runtime.spawn_failed` / `unknown_origin`）全部落在 Python 的七值闭集内；
   `OBSERVATION_METHODS` 与 `OBJECT_KINDS` 两侧**完全相等**（各 5 项 / 6 项）。
2. **形状可判**：按插件那六个拒绝场景的形状造载荷，逐条过 `payload_is_well_formed`（6/6）。

**另记一条**：插件**不读** Python 写的那行 `[policy] ORIGIN`——它自己算 spawn 族的归因。
两侧因此没有"共用一行文本"的耦合，也**不许**加：插件对 Hook 失败的解释一字不改，
Python 的 ORIGIN 行只进审计与诊断。（这条以注释形式留在用例里，免得下一轮有人误加断言。）

### 7.4 JS 侧的读数

| 命令 | 读数 |
| --- | --- |
| `node --check src/adapters/dsh/policy-hook.plugin.mjs` | `exit 0` |
| `pytest -q tests/contract/test_policy_hook_chain.py` | **31 passed**（改前基线 20 passed；既有 Q6 用例全绿） |
| `pytest -q tests/unit/test_dsh_pre_evidence.py tests/integration/test_dsh_pre_evidence_hook.py` | **42 passed**（Phase 5 口径无回归） |
| `pytest -q tests/unit/test_wiring.py` | **92 passed** |
| `pytest -q tests/integration/test_dsh_sandbox_loop.py` | **67 passed** |
| `pytest -q tests/integration/test_governance_gap_probe.py` | **21 passed** |
| **自证会红**：把 `assert origin["origin"] == "agent_runtime.spawn_denied"` 改反 | **1 failed**（原文 `AssertionError: assert 'agent_runtime.spawn_denied' == 'agent_runtime.spawn_failed'`）；改回 → `1 passed`。变异只在临时副本上做，仓库源码未动 |
| `ruff check`（`.py`；`.mjs` 不认，报 invalid-syntax） | `Found 1 error`：`E501 line 854`（**既有**：`git show HEAD:` 的原版单独喂 ruff 读数逐字相同）；新增行 E501 = 0 |

### 7.5 JS 侧的"没有做"（照抄执行者的自述，不替他背书）

- **未跑真实 dsh 会话的端到端闭环**（`tools/dsh_sandbox_loop.py` 那一层只跑了集成用例）：
  探针的假 ctx **照搬**了真机 Node 的 `cwd 不存在 → ENOENT 归给可执行文件` 行为，
  因此"真机会不会这样归因"仍是**未核实**。
- `verified_at` 的"来自真实调用"只有两条间接证据：源码里就是 `new Date().toISOString()` +
  断言它能解析成带时区的 ISO-8601 且落在测试时刻 ±600s 内；**没有**独立手段证明时钟来自那次调用。
- `.mjs` 除 `node --check` 外**没有任何** JS lint / 类型检查读数（本机 ruff 不认 JS）。
- **待裁定（记在这里，不在本台阶内改）**：spawn 族的 `observation.result` 保留报错原文，
  真机原文里含绝对路径（`C:\Program Files\nodejs\node.exe`）。它目前**不进审计链**；
  若将来要进，AGENTS 第 16 条的绝对路径脱敏需要一个明确口径（Python 侧同类字面量走 `sanitize`，
  JS 侧目前没有对应函数）。


## 9 本机门禁（原文命令，2026-09-29，树 = 本台阶的提交前状态）

| 项 | 读数 |
| --- | --- |
| 命令 | `python tools/ci_local.py --full --python .venv/Scripts/python.exe`（cwd = `C:\Users\ZNM\Downloads\Memory-rf`） |
| 步骤 | `改动文件 773 个；执行 33 步（本机跳过 11 步，登记豁免 2 步）`；**33/33 `rc=0`**，非 0 计数 **0** |
| 结论行 | `本机检查全部通过（33 步）`；进程 exit **0** |
| 墙钟 | 表内**合计 7m 59.0s**；最贵 pytest 5m 06.4s（64.0%）、Learning notebooks 1m 02.0s、Orchestration closed loop 1m 01.5s |
| 测试 | `1934 passed, 1 skipped, 3 warnings in 304.90s (0:05:04)`（本台阶之前是 1932 passed：新增 2 条跨语言/形状用例） |
| 证据 | `.tmp/ci-full-step2-run2.log`（168678 B，sha256[:16] `78b6efd444156f69`）；`.tmp/artifacts/tests-all-report.xml`（258326 B，`5d8bbb41086ff037`）、`phase-8-evidence.json`（47942 B，`4c5470d256933cd2`） |

**第一次跑是红的，红因在文本规范**（不是本次改动本身）：`Text conventions` `rc=1`，报
`tests/contract/test_policy_hook_chain.py: 文件以多个空行结尾` 与
`tests/unit/test_provenance_origin.py: 文件未以单个换行符结尾`。修掉之后复跑才有上表的 33/33——
**把这次红记在这里**：门禁第一次挡住了新增文件的两个格式问题，这正是它该做的事。
（第一次的读数：`.tmp/ci-full-step2.log`，失败 1 处 = 文本规范。）

**这一步证明什么**：原文命令在本树跑绿，33 步里包含本台阶新增的两个测试文件与改动过的契约用例。
**不证明**：CI（Linux / UTF-8）侧同样绿；也不证明归因接进了门禁——**它没有**：本台阶没有把
`origin` 接进 `ci_local.py` 的任何一步，R-g 目前只由本文 §5 / §7 的用例守住。

## 8 不证明什么 / 未核实

- **不证明「理由一定对」**：本台阶只保证"归因**可核验**、且核验结论与理由一致"。
  核验判据本身是有限的（配置族只覆盖"读得到 / 读不到"这一层，`spawn` 输入族只覆盖
  "目录在不在 / 命令起没起得来"），覆盖不到的对象一律 `unknown_origin`。
- **不证明门禁会拦住它**：本台阶**没有**把归因接进 `tools/ci_local.py` 的任何一步；
  R-g 目前由 §5 的用例与 JS 侧的契约用例守住。
- **不证明 CI（Linux / UTF-8）侧同样绿**：本节读数全部来自本机。
- **未核实**：本机沙箱的强制点实现（与 6 号 / 8.2 节同一条）。
