# 27 · 台阶 5 · 控制面事实表与跨源互证设计稿（**只报告部分**，只写文档）

- **执行**：2026-10-03（本机）；控制面重构会话（**唯一写者**）。
- **树**：分支 `refactor/control-plane`；本文写就时的 HEAD = `6ed3ca8`（`git status --porcelain -uall` 为空）。
  本文里的**全部读数**都在这一棵树上实跑，复现命令见 §10（§1 逐条写出处）。
- **依据**：方案 **§3.2**（facts + checks 合表与连接键）/ **§3.3**（状态代数）/ **§4 台阶 5**（只报告 → 合并谓词 → 跨源互证 + L5 上线闸）/
  **§5.1 J5**（新检查自证）/ **§7.1**（×2.5 上调与 1.5 倍复核线）；17 号 **§3.2 / §3.3 / §3.4**（台阶 5 的两份整数清单与逐条结论）；
  23 号 §19（R-h 落地：登记表 64 行、四格红条件）与 **§20**（2026-10-03 评审五条裁定）；
  24 号 §8.3（声明文件 schema 兼容与"**不许新增加载期 FATAL**"的裁定先例）；25 号（只报告期的表达与升格路径）；
  26 号（CI 线交接的形状与"同一提交"纪律）；AGENTS 第 19（证据不带绝对路径）/ 45（仪器要能失败）/ 48（读数属于哪棵树）/
  49（"查了多少"要能答出来）/ 50（口径诚实、同名两义一律改名）/ 55（加键就是改协议）/ 56（账本不存在 = 不适用）条。
- **本文件是什么**：台阶 5 **只报告部分**的设计稿——两张表与它们的关系、连接键、三组跨源读数（C1/C2/C3）、
  逐项要加的键与版本轴、消费方、R-d 预注册形状、需要 CI 线配合的事项、预算与"可以缩小到什么范围"。
- **本文件不是什么**：不是开工单，也不是排期。**本文没有改任何代码、任何载荷、任何数据文件**：
  `validation/control-plane-facts.yaml` 没有建、`validation/instrument-checks.yaml` 一个字没动、
  合并谓词没有做、任何新的加载期 FATAL 没有加。

---

## 0 一句话

台阶 5 的只报告部分 = **一张新的 facts 表（只放指针）** + **在既有检查登记表上扩一个可选字段** +
**一个双向必查的连接键** + **三组跨源读数**（C1 两份测试路径声明的差集、C2 工具表覆盖关系、C3 预算不等式两套结论），
**全部只报告**（退出码恒 0、`enforced: false` + `would_exit_code: 1` 只是预注册）：
它把「平台对自己的声明说了什么、这些声明互相咬不咬得住」变成**可读的红**，而在解冻之前**一条判定都不改、一条退出码都不接**。

---

## 1 本轮实跑读数（不照抄 17 号）

> 口径：本文所有"今天"= 分支 `refactor/control-plane` @ `6ed3ca8`。**每条读数都给复现命令**（§10），
> 不引用 17 号当时的数——17 号的读数采于 `e235626c`（台阶 −1 的检查点），树已经长大。

### 1.1 C1 · 测试路径的两份声明

| 项 | 今天（`6ed3ca8`） | 17 号 / 归档 03 号 | 说明 |
| --- | --- | --- | --- |
| 平台级声明 | `validation/test-layout.yaml:21-23` 的 `test_patterns` **2** 条：`tests/**/test_*.py`、`tests/**/*_test.py` | 同 | 唯一权威口径（AGENTS 第 49 条） |
| Adapter 级声明 | `examples/dsh/dsh-adapter.yaml:22-24` 的 `test_paths` **1** 条：`tests/**/*.py`（`test_layer: test`） | 同 | 发给受治理项目的示例模板 |
| `tests/**/*.py` 文件数 | **202**（`git ls-files` 与工作树 `rglob` **都是 202**） | 184 | 检查点之后新增 **18** 个 .py，**18 个全是 `test_*` 形态**（所以差集没动） |
| 判定不一致 | **101**（`platform=False / adapter=True` **101**，反向 **0**） | 101 | 与 17 号**逐数相同** |
| 层级不一致 | **100** | ——（17 号只给了 101） | 差的 1 条是 `tests/conftest.py`：平台 `is_test=False`，但 `infer_layer` 按**子串**匹配把 `conftest` 判成 `test` |
| 口径变体「`**/` = 至少一段目录」 | **97** | 97 | 97 = 101 − **4**：4 个直接躺在 `tests/` 下的非测试文件（`api_support.py` / `conftest.py` / `enforcement_support.py` / `orchestration_support.py`）；这 4 个文件在检查点树里也是同一批 |
| 层见证（一条） | `tests/fixtures/validators/project/src/shop/order_controller.py` → adapter **test**（命中 `tests/**/*.py`）/ 平台 **controller**（`filename_guess`） | 同 | 这就是 AGENTS 第 49 条禁止的形态 |
| 未声明 `test_paths` 的 Adapter 配置 | `adapters/dsh/adapter.yaml` / `adapters/generic-json/adapter.yaml` / `adapters/legacy-post-only/adapter.yaml` **3 个全都没有** | 同 | 只有**示例**声明了它（M1 判据因此只覆盖示例） |

**一个必须写下来的观察**：101 这个数今天**恰好没变**，原因是新增的 18 个 .py 全部命中两条 pattern
（两边都判"是测试"），落不进差集。**"今天还是 101"不等于"这份声明没问题"**——
它是同一批辅助/夹具文件的旧账（归档 03 号 §4 的 101 条清单）。

### 1.2 C2 · 工具表三处声明（今天的实数）

| 来源 | 读数 | 细节 |
| --- | --- | --- |
| `registry/tool-registry.yaml` 的 `tools` | **10** | `agent=dsh` **6**（`edit` / `write` / `read` / `pwsh` / `bash` / `run_code`）+ `agent=orchestrator` **4**（id：`orc.fs.edit` / `orc.fs.write` / `orc.policy.write` / `orc.policy.edit`） |
| `adapters/*/manifest.yaml` 的 `tools` | **38 / 6 / 1** | dsh **38** / generic-json **6** / legacy-post-only **1** |
| 代码工具表 `src/adapters/dsh/adapter.py` 的 `TOOL_TABLE`（**dict comprehension**，38 个 `_spec(...)` 调用） | **38** | 与 manifest 的 dsh 名字集合**逐项相等**（差集两个方向都是 0）——由契约测试守住 |
| `registry/tool-registry.approved.json` | **10** 个工具的已审核 blob | 与注册表行数同数 |
| `adapters/approved.json` | **3** 个 adapter（dsh / generic-json / legacy-post-only） | `schema_version: "1.0"` |

**覆盖关系（这才是 C2 的新内容，今天没有一处检查它）**：

| 关系 | 今天读数 |
| --- | --- |
| 注册表里 `agent=dsh` 的 `tool_name` 6 个 ⊆ manifest 的 38 个名字 | **0 缺失**（6 个全在） |
| manifest 的 38 个名字里没有注册表条目的 | **32**（只读与未受治理的工具；**是设计**——受治理那 6 个才进注册表） |
| manifest(dsh) 名字 ↔ 代码 `TOOL_TABLE` 键 | **两个方向都是 0** |
| 注册表的 orchestrator 4 条 | 代码侧的引用在 `src/orchestration/nodes.py:69-72` 的四个常量（`EDIT_TOOL` / `WRITE_TOOL` / `PROTECTED_EDIT_TOOL` / `PROTECTED_WRITE_TOOL`）上；注册表里的 `tool_name`（`edit_file` / `write_file` / `edit_policy` / `write_policy`）**在 `src/orchestration/tools.py` 里 grep 不到**（**未核实**它在哪里解析，见 §9 第 1 条） |

### 1.3 C3 · 预算不等式两套结论（今天）

**先看仓库内那一套**（`examples/dsh/`，tracked，随时可复核）：

| 项 | 读数 |
| --- | --- |
| `examples/dsh/hooks.json` 的策略 Hook `timeout` | **30**（秒） |
| `examples/dsh/dsh-adapter.yaml` 的 `timeout_ms` | **5000**（毫秒） |
| `pre_evidence` | **没有声明** ⇒ 三段不等式（`pre_evidence.timeout_ms + timeout_ms < dsh 侧`）**不适用**，不是 0、也不是"通过" |
| 两段不等式 | 5000 < 30000 → **成立**；`hooks.check_wiring(...)` 返回**空串**（通过） |

**第二套结论**（有 `pre_evidence` 的实例，只在 `.tmp` 里；本机今天的读数）：

| 项 | 读数 |
| --- | --- |
| `.tmp/step3c/round/projectA/.policy/dsh-adapter.yaml` | `timeout_ms` **5000** + `pre_evidence.timeout_ms` **60000**（`enabled: true`） |
| 同目录 `hooks.json` 的 `timeout` | **120**（秒） |
| 三段之和 | **65000 < 120000** → 成立；`check_wiring` 返回**空串**（通过） |

**同一个问题今天有两份实现（不是本轮造的，是既有事实）**：

| 实现 | 判据 | dsh 侧上限取什么 | 看得到 `pre_evidence` 吗 |
| --- | --- | --- | --- |
| `src/adapters/dsh/hooks.py` 的 `check_wiring`（两段 + 声明并启用 `pre_evidence` 时的三段） | `timeout_ms < hooks.json 的 timeout`；声明了 `pre_evidence` 时再加 `pre_evidence.timeout_ms` | **只看 `hooks.json`**；没写 timeout 时按 `DEFAULT_HOOK_TIMEOUT_MS = 600000` 计 | **看得到** |
| `src/adapters/wiring.py` 的通道事实 `timeout_budget`（覆盖账里的 `ok`） | `dsh_side_timeout_ms > internal_budget_ms` | `min(进程内插件的 timeoutMs, hooks.json 的 timeout)` | **看不到**（只读 adapter 配置的 `timeout_ms`） |

**这条差异必须进报告**：`wiring` 的 `timeout_budget.ok = true` **不能**读成"三段不等式成立"。
今天 7 条被发现的通道**都没有声明 `pre_evidence`**，所以这个盲点**今天没有现实受害者**，
但它就是一个"读的人会读错"的口子（AGENTS 第 50 条）。

### 1.4 既有的两张"表"今天长什么样

| 项 | 读数 |
| --- | --- |
| `validation/control-plane.yaml`（方案 §3.2 的合表） | **不存在** |
| `validation/instrument-checks.yaml`（R-h 的检查登记表） | `schema_version: "1"`、**64 行**、8 字段；命名空间：`gate-step` **44** / `gap-probe` **13** / `seal-scenario` **5** / `report-only` **2**；owner：`ci-line` 46 / `control-plane` 18；`evidence_level`：`exit_code` 44 / `report` 15 / `seal` 5；`severity`：`blocking` 44 / `advisory` 20 |
| `covers` 字段的形态 | **64 行全是人读的句子**（probe 行逐字取该检查的 title、seal 行逐字取该场景的 what），**0 行**像键 |
| R-h 今天的读数 | 对象 **64**、登记表 64 行、四格红条件 **0 / 0 / 0 / 0**、`HITS: 0`、退出码 0 |
| `tools/exemption_expiry.py` 今天 | `HITS: 0 / declared=7 due=0 expired=0 unprovable=0` |
| `readings.declarations` 的词汇表 | 7 个名字（`adapter_config` / `instrument_checks` / `obligations_ledger` / `registry` / `report_only_steps` / `test_layout` / `wiring_scope`）——**没有 facts 表的位置** |

---

## 2 两张表与它们的关系

### 2.1 为什么 checks 表**不另起第二份**

方案 §3.2 要的是"一张检查登记表（facts + checks 合表）"。**checks 那一半已经存在**：
`validation/instrument-checks.yaml` 的 8 个字段（`check_id` / `owner` / `command` / `covers` /
`evidence_level` / `mutation_id` / `gap_note` / `severity`）与方案 §3.2 的原文**逐字相同**，
"只放指针"的加载期规则（出现 `last_run` / `status` / `passed` / `observed_*` 即报错）也已经实现（23 号 §19.3）。

再建一份"台阶 5 自己的 checks 表"会得到**同一个 `check_id` 两处真相**——AGENTS 第 50 条的"同名两义"，
而且 R-h 的四格红条件与新的连接键会各读一份，谁真谁假读不出来。因此：

> **台阶 5 只在 `validation/instrument-checks.yaml` 上扩字段，一个新表都不建。**

### 2.2 facts 表是新文件，而且**不叫** `control-plane.yaml`

| 决策 | 理由 |
| --- | --- |
| facts 表落 `validation/control-plane-facts.yaml`（新文件，自己的 `schema_version: "1"`） | checks 那一半已经在别的文件里；再建一个叫 `control-plane.yaml` 的文件、里面只有 facts，就是**同名两义**（方案名 vs 实际内容） |
| 不建方案字面意义上的"合表" | 方案 §3.2 **自己给了退路**："连接键……**给不出这条就拆回两张表**"。我们**给出**连接键（§2.3），只是它跨两个文件——这正是方案允许的形态 |
| 两张表的关系 | **facts 行 = 声明的事实（指针）**；**checks 行 = 检查（指针）**；连接键 = "这条检查覆盖哪些事实"。三者的**权威各自一份**，谁也不复制谁的值 |

### 2.3 连接键：`facts.key` ↔ checks 行的引用（双向必查）

**今天不能直接用 `checks.covers` 当连接键**：那 64 行的 `covers` 是**人读的句子**，而且它的来源纪律是
"能取自对象自己声明的文字就不另写一套"（表头注释）。要把它变成键，就得改写 64 行、丢掉这条来源纪律，
并且让同一个字段同时承担"给人看的说明"和"给机器查的键"——又一条同名两义。

**落地形态**（**偏离登记，请评审**）：新增**一个可选字段** `covers_facts`（字符串列表，每项是 `facts.key` 的形态）：

```yaml
  - check_id: "report-only:Control plane facts (report only)"
    owner: control-plane
    command: "python tools/control_plane_facts.py"
    covers: "控制面事实表 × 跨源互证（连接键双向必查 + C1/C2/C3 读数；只报告）"
    covers_facts:                       # ← 新增的可选字段（缺省 = 空列表 = 这一行不声明覆盖任何 fact）
      - "test_paths.platform_patterns"
      - "tool_tables.registry"
    evidence_level: report
    mutation_id: null
    gap_note: "存量检查，未做变异自证"
    severity: advisory
```

| 方向 | 判据（结构化，不解析文本） | 红条件键 |
| --- | --- | --- |
| 一 | `facts.key` 没有被**任何** checks 行的 `covers_facts` 引用 | `fact_without_check` |
| 二 | checks 行的 `covers_facts` 里有 `facts` 表里**不存在**的 key | `check_covers_unknown_fact` |

**两格都必须有**（否则"表里少写几行"就能把方向一凑成 0）；**第三条不是红、但必须可见**：
checks 行**没有** `covers_facts` 的条数（`checks_without_fact_link`）——不给这个计数，
"这张表今天什么都没连"就一个字都读不出来。

**备选 B（不推荐，列出来供评审比较）**：把 `covers` 本身改成 key 列表。代价：改写 64 行；
丢掉"逐字取自对象自己的声明"这条来源纪律；R-h 的表头注释、用例 6 与 7 都要跟着改；
"给人看的说明"得另找一个字段放。**收益只是省掉一个字段**。

**连接力的已知上限（照实写）**：方向一今天只能由**台阶 5 自己的报告行**满足——
三组事实真正的判定者（layer 契约测试、manifest↔代码契约测试、`hooks.check_wiring`）**都不在 R-h 的四族里**
（四族 = workflow 步骤 / 探针检查 / 封条场景 / 只报告步骤）。要更强的连接，就得把"pytest 检查"扩成第五族——
那是**另一次设计**（改 R-h 的对象枚举、第 55 条版本轴、以及一整套新登记），**不在本轮**，登记为剩余缺口（§9 第 4 条）。

---

## 3 逐项设计

> 每一项都按同一张表写：**要加的键 / 版本轴 / 消费方 / R-d 预注册 / CI 线配合**。

### 3.1 facts 表（新文件 + 新加载器）

**要加的键**：文件顶层 `schema_version` + `facts`（列表）；每行 9 字段（逐字取方案 §3.2）：

| 字段 | 取值域 / 形态 | 设计口径 |
| --- | --- | --- |
| `key` | 点分两段以上（`^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$`） | **不是** `check_id` 那种 `<namespace>:<name>` 形态：两张表用两套词汇，谁也冒充不了谁 |
| `authority` | `canonical` \| `observed` | `canonical` = 有唯一权威声明；`observed` = 某次读数观到的（**必须**在 `canonical_ref` 写清"谁观测"） |
| `canonical_ref` | `"<仓库相对路径>#<锚点>"` | 锚点是**给人看的指针**（如 `validation/test-layout.yaml#/test_patterns`），加载器**不解析**它 |
| `consumers` | 非空字符串列表 | 消费方的**名字**（模块 / 命令 / 用例），取自代码里真实存在的字面量 |
| `predicate` | 字符串（源码里的名字） | "这个事实成不成立"由**哪一处**判定——**不许**在表里再写一个判据式（那是第二套实现） |
| `severity` | `blocking` \| `advisory` | **本轮登记的行全部 `advisory`**：只报告期它们不阻断任何人，升格时才改 |
| `remedy` | 非空字符串 | 证明不了时"**改成什么形态就能过**"（AGENTS 第 50 条） |
| `on_unprovable` | `unavailable` \| `not_applicable` | **闭集**；不许写 `ignore` / `pass`——"读不到"既不是通过，也不是 0（第 56 条） |
| `expires` | `YYYY-MM-DD` \| `null` | 到期**只报告**（与 `exemption_expiry` 同族），本轮**不接退出码** |

**"不放值"的边界（写清楚，免得被读成"什么都不许写"）**：禁止的是**事实的取值**——
`last_run` / `status` / `passed` / `observed_*`（与 checks 表同一条禁键纪律）；
`expires` / `severity` / `authority` 是**声明**，不是取值，可以写。

**行清单（草案，落地前评审；最小集 = A + B + C 共 13 行）**：

| # | 组 | `key` | `authority` | `canonical_ref`（指针） | `predicate`（判据在哪） |
| --- | --- | --- | --- | --- | --- |
| 1 | A 测试路径 | `test_paths.platform_patterns` | canonical | `validation/test-layout.yaml#/test_patterns` | `validators.globs.glob_match` |
| 2 | A | `test_paths.adapter_example` | canonical | `examples/dsh/dsh-adapter.yaml#/test_paths+/test_layer` | `adapters.dsh.adapter.load_config` |
| 3 | B 工具表 | `tool_tables.registry` | canonical | `registry/tool-registry.yaml#/tools` | `enforcement.registry`（加载期校验） |
| 4 | B | `tool_tables.manifest.dsh` | canonical | `adapters/dsh/manifest.yaml#/tools` | `adapters.base`（manifest 校验） |
| 5 | B | `tool_tables.manifest.generic_json` | canonical | `adapters/generic-json/manifest.yaml#/tools` | 同上 |
| 6 | B | `tool_tables.manifest.legacy_post_only` | canonical | `adapters/legacy-post-only/manifest.yaml#/tools` | 同上 |
| 7 | B | `tool_tables.code.dsh` | canonical | `src/adapters/dsh/adapter.py#TOOL_TABLE` | `adapters.dsh.adapter` |
| 8 | B | `tool_tables.approved.registry` | canonical | `registry/tool-registry.approved.json` | `enforcement.registry` |
| 9 | B | `tool_tables.approved.adapters` | canonical | `adapters/approved.json` | `adapters.base` |
| 10 | C 预算 | `budget.hooks_timeout.example` | canonical | `examples/dsh/hooks.json#/hooks/PreToolUse` | `adapters.wiring._hook_timeout` |
| 11 | C | `budget.internal_budget.example` | canonical | `examples/dsh/dsh-adapter.yaml#/timeout_ms` | `adapters.dsh.adapter.load_config` |
| 12 | C | `budget.pre_evidence.example` | canonical | `examples/dsh/dsh-adapter.yaml#/pre_evidence` | 同上；**今天这一行不存在** ⇒ 读数是"未声明" |
| 13 | C | `budget.dsh_side_limit` | canonical | `src/adapters/dsh/hooks.py#check_wiring` + `src/adapters/wiring.py#timeout_budget` | **两处**：这一行存在的理由就是"两个口径并列、不许互相代替"（§1.3） |
| 14–16 | D 版本轴（**候选，可整组删**） | `axes.checks_table` / `axes.instrument_self_proof` / `axes.control_plane_facts` | canonical | 各自的常量所在文件#常量名 | 第 55 条那张表的落地指针；**值不进表**（值在代码里） |

**要加的键（YAML 形状示例，前两行）**：

```yaml
schema_version: "1"
facts:
  - key: "test_paths.platform_patterns"
    authority: canonical
    canonical_ref: "validation/test-layout.yaml#/test_patterns"
    consumers: ["policy.check.resolve_layer", "validators.selection.list_test_files"]
    predicate: "validators.globs.glob_match"
    severity: advisory
    remedy: "改这两条 pattern 之后必须同批跑 tests/contract/test_dsh_layer_declaration.py 与 tests/contract/test_validator_protocol.py"
    on_unprovable: unavailable
    expires: null
```

- **版本轴**：`validation/control-plane-facts.yaml` 自己的 `schema_version: "1"`（新文件**第一次出现就带轴**）。
  加载器只接受它认识的版本；读到别的版本、未知字段、未知枚举、重复 `key`、空 `consumers`、`observed` 却没写清谁观测——
  **一律降级为 `unavailable` + reason**（在**只报告工具内部**），**不抛给任何判定路径**（见 §5 第 2 条）。
- **消费方**：① 台阶 5 的报告工具（连接键 + 三组读数）；② 评审（人读指针）；③ **将来**的门禁（升格之后只读 `red_conditions` 的计数）；
  ④ Hook / Policy Engine / API / 编排：**什么都不读**——facts 表**不是**判定输入，它不许改变任何 allow / block。
- **R-d 预注册**：见 §6 的 R1–R7（既有载荷一个键都不加）+ R8（新载荷自证）。
- **CI 线配合**：无（表与加载器都是控制面会话的文件）。

### 3.2 checks 表扩字段（**一个**可选字段 + 版本轴 `"1"` → `"2"`）

| 项 | 内容 |
| --- | --- |
| 要加的字段 | `covers_facts`（可选；字符串列表；缺省 = 空列表 = 这一行不声明覆盖任何 fact）。**只加这一个**——不加 `kind`、不加 `family`、不加任何"运行结果"类键 |
| 加载期校验的分工 | **形态**在加载期查（每项必须匹配 `facts.key` 的形态，畸形即报错）；**存在性**在**读数**里查（那是连接键那一格的 `check_covers_unknown_fact`，不是加载错误）。这条分工要写进加载器 docstring，否则"表里写错的 key"会被读成"表坏了"而不是"连接悬空了" |
| 版本轴（第 55 条） | `tools/instrument_self_proof.py` 的 `CHECKS_SCHEMA_VERSION` `"1"` → **`"2"`**；**加载器接受 `"1"` 与 `"2"`**（与 `wiring-scope` 的声明文件同型：加的是**可选**字段，旧表仍然合法）；`validation/instrument-checks.yaml` 本体写成 `"2"` |
| 同批必须改的引用点（**这就是"加键就是改协议"的落地清单**） | ① 加载器常量与 `ROW_FIELDS`（`tools/instrument_self_proof.py`）；② 表头注释里"字段取值域"与"版本轴"两段（`validation/instrument-checks.yaml`）；③ `tests/unit/test_instrument_self_proof.py` 里两处写死的版本号：`assert document["schema_version"] == "1"` 与"坏版本"用例用的 `"2"`（要改成 `"3"`，否则这条用例会因为"2 现在是合法的"而**静默失效**）；④ `AGENTS.md` 第 55 条那张表——把 `CHECKS_SCHEMA_VERSION` 登记进去（它今天**不在**表里，这是一次补登记） |
| 兼容窗口 | 旧工具读新表 → `unavailable`（只报告，不阻断）；新工具读旧表 → 接受 `"1"`。**两者都在同一个提交里**，所以窗口是 0 |
| 消费方 | R-h 的仪器（四格读数**不变**：新字段不参与四格）+ 台阶 5 的报告工具（用 `covers_facts` 做连接键） |
| R-d 预注册 | R-h 的 `--json` **不加键**；`objects.table.schema_version` 由 `"1"` → `"2"`（**预注册的"会变"**，不是 0 条）；四格仍 `0/0/0/0`；`objects` 仍 64（CI 线还没接 R-h 的只报告步骤，见 §1.4 与 26 号） |
| CI 线配合 | 无（表与加载器都是控制面会话的文件） |

### 3.3 连接键双向必查（只报告）

- **要加的键**：报告载荷里 `links.fact_without_check` / `links.check_covers_unknown_fact`（两格红条件）+
  `links.checks_without_fact_link`（计数，**不是红**）；另外 `checks_table.counts.with_covers_facts` / `without_covers_facts`。
- **每格形状**（与 `adapters.cli wiring` 的 `red_conditions` **逐字同形**，不新造一套"红"）：
  `status` / `count` / `items[]` / `is_red` / `red_when` / `enforced: false` / `would_exit_code: 1` / `promote_when` / `note`。
- **版本轴**：新载荷第一次建轴 `CONTROL_PLANE_FACTS_SCHEMA_VERSION = "1.0"`（见 §3.6 的载荷总表）。
- **消费方**：评审（人）读两格 + `headline.machine_line`；**将来**的门禁只读两格的 `count`；判定路径什么都不读。
- **R-d 预注册**：既有载荷 0 键（§6 R1–R7）+ 硬约束 A（影子表变异自证，§6）。
- **落地当天的读数（照实算，别用"表里少写几行"凑 0）**：facts 表登记 **13** 行、`covers_facts` 只出现在
  "台阶 5 自己的报告行"上（那一行引用它读的全部 13 个 key）⇒ `fact_without_check = 0`、
  `check_covers_unknown_fact = 0`、`checks_without_fact_link = 64`（今天的 64 行一行都没声明覆盖事实）。
  **这三个数就是"初始状态"的读数**，不是"绿"。
- **CI 线配合**：无。

### 3.4 C1 · 测试路径互证（只报告那 101 个不一致，**不合并谓词**）

| 项 | 设计 |
| --- | --- |
| 要加的键 | `cross_source.test_paths`：`{scanned, disagreement_count, directions{platform_false_adapter_true, platform_true_adapter_false}, items[], enumeration, semantics_note, layer_disagreement{count, items[], note}}`；`red_conditions.test_path_declaration` |
| 判据从哪来 | **两侧各用它们现在的实现**：平台侧 `validators.registry.load_test_layout(root=...).is_test(path)`；Adapter 侧 `adapters.dsh.adapter.load_config(...).layer_resolution(path)`。报告只做**集合差**，**不新写一个大一统谓词**，也不改任何一处的判定 |
| 口径必须写进载荷 | `semantics_note` 逐字写明"`**/` = 零个或多个目录"；本机读数 `101`，把它解释成"至少一段"会读 `97`（差 = 4 个直接躺在 `tests/` 下的非测试文件，逐条列在 `note` 里）。**同一个数换个语义就变**，所以语义与数必须同框出现（AGENTS 第 48 条的同一条纪律） |
| 枚举口径 | 工作树 `tests/**/*.py`（`rglob`，与 `tests/contract/test_dsh_layer_declaration.py` 同口径）；今天 `git ls-files` 与它**同数（202）**。载荷同时给 `scanned`，读者不必猜扫了多少（第 49 条） |
| 层级读数 | `layer_disagreement.count = 100`（**不是 101**）；`items` 带 `{path, adapter, platform, source}`；`tests/conftest.py` 那一条单独在 `note` 里解释（平台的 `infer_layer` 按子串把 `conftest` 判成 `test`，**不是靠声明**） |
| 红条件与升格 | `red_conditions.test_path_declaration`：`count = 101`、`enforced: false`、`would_exit_code: 1`；`promote_when` = "跑过 N≥1 次且 0 命中"，并**写明降到 0 只有两条路**（合并谓词 / 改声明），**两条都不在本轮** |
| 不做 | **合并谓词**（一份实现、两个调用点）——见 §5 第 1 条 |
| R-d 预注册 | 决策载荷 0 条 / `policy.check --json` 0 条 / 图层与 `layer_source` 0 条（证明"只报告"没有碰判定） |
| CI 线配合 | 无（只读 `src/`、`validation/`、`examples/`） |

### 3.5 C2 · 工具表覆盖关系（只报告）

| 项 | 设计 |
| --- | --- |
| 要加的键 | `cross_source.tool_tables`：`{sources{registry, manifests[], code_tool_table, approved[]}, relations[{name, left, right, left_only[], right_only[], both_count}], notes[]}` |
| 读数（今天） | registry 10（dsh 6 / orchestrator 4）；manifests 38/6/1；`TOOL_TABLE` 38 = manifest dsh（两向 0）；registry 的 dsh `tool_name` 6 ⊆ manifest 38（0 缺失）；manifest 里没有注册表条目的 **32**（**设计**：只读与未受治理）；orchestrator 的 4 条由 `src/orchestration/nodes.py:69-72` 的常量引用 |
| **红条件：本轮不给** | 理由写在明处：今天**没有**一条可评审的判据能说"哪一组差异是缺口"——32 条 `not_governed` 是设计、orchestrator 的 `tool_name` ↔ 代码名关系**未核实**、`approved` 与注册表的对应由既有审核流程守。按 AGENTS 第 50 条，**没有依据的判定不许造**：这一组**只给读数**，判据留给评审裁定（§9 第 1 条把未核实的那一项列出来） |
| 依赖的既有检查（不重复造） | manifest ↔ 代码 `TOOL_TABLE` 已由契约测试守住；已审核哈希的比对已由 `adapters.cli matrix` 与运行期加载守住。C2 只报"覆盖关系"，**不重跑**它们的判据 |
| R-d 预注册 | 既有载荷 0 键（§6 R1–R7） |
| CI 线配合 | 无 |

### 3.6 C3 · 预算不等式两套结论（只报告）

**第一条纪律：不允许第三份实现。** 同一个不等式今天已有两份实现（§1.3），本轮**只准**在
"把其中一份变成可结构读的"和"复用现成读数"之间选，**不许**在报告工具里再写一遍判据式。

| 方案 | 做什么 | src | 代价 / 风险 | 结论 |
| --- | --- | --- | --- | --- |
| **A（推荐）** | 在 `src/adapters/dsh/hooks.py` 里把 `check_wiring` 的两段/三段判据抽成**一个结构化函数**（如 `budget_inequality_facts(config, hooks_config_path=...)` → `{two_term: {...}, three_term: {...}}`，状态闭集 `ok` / `violated` / `not_applicable` / `unavailable`），`check_wiring` **由它格式化**（返回的字符串**逐字节不变**）；报告工具与 `check_wiring` 成为**一份实现的两个调用点** | 约 110–170 | 动了**失败关闭**路径：refactor 必须用"等价性用例"证明错误消息逐字节相同 | **推荐**：它同时消掉"两处口径"的一半（`check_wiring` 侧），且不改变任何 allow / block |
| B | 不动 `hooks.py`：报告工具用"同一个配置 + 一个剥掉 `pre_evidence` 的副本"各调一次 `check_wiring`，按"空串 / 非空串"与早退顺序**推断**两段与三段各自的结论 | 0 | 依赖"空串 = 通过"与"两段先判"这两条**今天成立**的内部契约；一旦 `check_wiring` 的内部顺序变了，报告会**静默错**（要用例钉住顺序） | 备选：若评审不愿动 `hooks.py` |
| C | 只报**已经结构化**的那一套（`wiring` 的 `timeout_budget`，两段），三段标 `unavailable`（"没有结构化读数"） | 0 | **不满足范围**：C3 要的是"两套结论" | 不推荐（除非评审缩小范围） |

**要加的键**：`cross_source.budget.instances[]`（每实例：`{instance, declared{internal_budget_ms, hooks_timeout_ms, pre_evidence{declared, enabled, timeout_ms}}, two_term{status, limit_ms, source, reason}, three_term{status, sum_ms, limit_ms, source, reason}}`）+
`cross_source.budget.inventory_fact`（`wiring` 的 `timeout_budget`：`{dsh_side_timeout_ms, source, ok}`，**并列**，不合并）+
`red_conditions.budget_inequality`（只报"声明的那个不等式"被违反；`enforced: false`，因为真正的执行在 `check_wiring` 自己的调用点）。

- **三态语义（写死）**：`not_applicable` = 没声明 `pre_evidence`（**不是** 0、**不是**通过）；`unavailable` = 读不到（hooks.json 缺、timeout 是表达式、配置读不出来）；
  `violated` = 不等式不成立；`ok` = 成立且**本次真的读过**。
- **实例从哪来（显式，不扫目录）**：仓库内实例 `examples/dsh/` **恒读**；其他实例只由**显式参数** `--instance <config>@<hooks>` 给
  （今天那条 `.tmp/step3c/round/projectA` 的读数就是用它复现的）。**不扫 `.tmp`**：扫目录会把环境残渣读成事实，
  而且 `cleanup.py` 之后它们就不存在了（AGENTS 核心约束 6：不得根据目录推断上下文）。
- **两个 dsh 侧上限必须并列**（§1.3）：报告里 `inventory_fact` 与 `instances[].two_term` 各出一份，
  `note` 写明"`wiring` 的 `ok=true` 看不见 `pre_evidence`，**不许**当三段结论用"。
- **版本轴**：并进 §3.6 的新载荷（首次建轴 `CONTROL_PLANE_FACTS_SCHEMA_VERSION = "1.0"`）。
- **R-d 预注册**：R1–R7 全 0 条未预注册；**硬约束 B**（若选 A）：`check_wiring` 的返回值在等价性用例覆盖的 N 个配置上**逐字节相同**。
- **CI 线配合**：无。

### 3.7 新载荷（一份，承载上面全部读数）

| 键 | 内容 |
| --- | --- |
| `schema_version` | `CONTROL_PLANE_FACTS_SCHEMA_VERSION = "1.0"`（**新载荷第一次出现就带轴**；同批登记进 AGENTS 第 55 条那张表） |
| `mode` / `note` | 与 `exemption_expiry` 的只报告载荷同族（"只报告、退出码恒 0"必须自己说出来） |
| `reading_context` | 树 / 环境 / **两处声明**（新常量 `DECLARATION_CONTROL_PLANE_FACTS = "control_plane_facts"` + 既有的 `DECLARATION_INSTRUMENT_CHECKS`）——归属读数，第 48 条 |
| `facts` | `{table{status, path, schema_version, rows, reason}, rows[], counts}`（`path` 用**仓库相对**写法，第 19 条） |
| `checks_table` | `{table{...}, counts{rows, with_covers_facts, without_covers_facts}, namespaces, rows_with_facts[]}` |
| `links` | §3.3 的三项 |
| `cross_source` | §3.4 / §3.5 / §3.6 的三组读数 |
| `red_conditions` | `fact_without_check` / `check_covers_unknown_fact` / `test_path_declaration` / `budget_inequality`（四格；同形） |
| `headline` | `{machine_line, text}`；机器行 `CONTROL_PLANE_FACTS: ...` + 跨文件契约的 `HITS: <四格合计> / ...` |

**刻意不并进既有载荷**：R-h 的载荷（`INSTRUMENT_SELF_PROOF_SCHEMA_VERSION`）**一个键都不加**——
它的 `HITS:` 行已经是 26 号交接给 CI 线的**跨文件契约**，动它等于让正在接线的 CI 线返工（26 号 §1 第 1 件事）。
本载荷自带轴、自带 `HITS:` 行，`ci_local.report_only_reading()` **不用改**。

---

## 4 只报告期的表达与升格路径（与 25 号 §3 同形）

| 层 | 形态 | 为什么 |
| --- | --- | --- |
| 载荷键 | 四格 `red_conditions`（每格带 `count` / `items`）+ 一行机器行 + 一个 `headline` | 复用 `wiring` / `instrument_self_proof` 的既有形状，不新造一套"红" |
| 每格 | `enforced: false` + `would_exit_code: 1` + `promote_when` | "这是一条红条件"由**块本身的存在**表达；"此刻真的红着"由 `count > 0` 表达（23 号 §14.2③ 的同一口径） |
| 文本 | `CONTROL_PLANE_FACTS: <四格计数> / facts=<n> checks=<n>` + `HITS: <合计> / <逐格>` | 机器行是**跨文件契约**；人读的句子不进判据（AGENTS 第 49 条：不解析文本） |
| 退出码 | **恒 0**（只报告）；只有用法错误退 2 | 本轮总原则：不新增阻断步骤 |
| "未评" | `unavailable` + `reason`；`count` 写 `null` **不是 0** | 第 56 条：不适用 ≠ 0 命中 ≠ 通过 |
| 升格路径（预注册，不是承诺） | 与 L5 同型：**跑过 N≥1 次且四格合计 0 命中，且 0 命中来自至少一次真实读数** → 才允许把某格接进退出码；届时**必须**先有一轮 `warn + 非零退出` | 与 R-h / `obligations_gate` 同一条纪律 |

---

## 5 不做（逐条给理由）

| # | 不做 | 理由 |
| --- | --- | --- |
| 1 | **合并谓词**（一份实现、两个调用点，用在 C1 的两份测试路径声明上） | **它会改变判定**：layer 是判据输入（`policy.check` 的 `layer_source`、ARCH-001 那条规则按层生效）。合并之前先要知道"合并到哪一侧"（平台的 `test_patterns` 还是 Adapter 的 `test_paths` 语义？），那是一次**改判定的**变更，必须走 R-d 字段级差集 + 快照重记。本轮只把 101 **读出来**，判定路径**一个字节都不动** |
| 2 | **任何新的加载期 FATAL** | 新表 / 新字段的加载错误**一律降级**为只报告工具里的 `unavailable` + reason；`policy.check` / Hook / API / 门禁的退出码与判定**一个都不动**。依据是 24 号 §8.3 的裁定先例（声明 schema `"2"` 兼容 `"1"`、**不许新增加载期 FATAL**）。这里把"FATAL"的判据写明：**让某条既有命令以非零退出或阻断收场**（`check` 退 2、Hook exit 2、门禁步骤红）——新工具的用法错误退 2 不算（它不在任何既有链路里） |
| 3 | **L5 上线闸** | 它是"任何**新的加载期 FATAL** 先以 warn + 非零退出跑满一个轮次"的纪律（方案 §4 台阶 5）。本轮**不新增 FATAL**（第 2 条），所以它**没有服务对象**；等真出现新 FATAL 的那一轮（合并谓词 / 新闸门）再执行。**注意区分**：本轮的新工具**本身**是"只报告步骤"，与 L5 的 warn 期不是同一件事——它的升格判据在 §4 |
| 4 | **C4（host-version 声明 vs 观测记录）只写声明** | 17 号 §3.3 第 7 条把它的处置判成"**写声明**"；而本轮的范围是"建机制（先只报告）"与"只报告"两类，"写声明"这类收缩动作**不在其中**。它今天已经有 AGENTS 第 54 条的四形态与 CI 上的 `--record-check` 门禁，**不重复建**；事实表这一轮也**不**给它登记指针（登记指针要连带把"谁比对"写清，那是 C4 自己那一轮的事） |

---

## 6 R-d 预注册（落地后逐条核对）

| # | 尺子 | 预期 |
| --- | --- | --- |
| R1 | 决策载荷（10 个场景，`.tmp/step3b/probe_decisions.py`） | **逐字节相同**（本轮不碰判定路径） |
| R2' | `VERDICT` 判定行（144 行 + 插件字面量） | **逐字节相同**；`VERDICT_SCHEMA_VERSION` 仍 `"1.0"` |
| R2 | `policy.check --json` 三个入口 | 各 **1** 条归属读数（`run.id` / `run.started_at`）；**0 条未预注册** |
| R5 | `adapters.cli wiring --json` 三个入口 | **0 条未预注册**；硬约束 15/15 OK；顶层**不加键** |
| R6 | `provenance.cli wiring-scope --check --json` | **逐字节相同** |
| R7 | 门禁各步骤退出码（含两条只报告步骤） | **一个都不变**；新工具**不**接退出码 |
| R8 | **新载荷**自证 | 同一棵树上两次运行，剥掉归属读数（`run.id` / `run.started_at` / `tree.digest` / `tree.revision`）后**逐字节相同**（剥离项写出来） |
| R9 | **表格载荷**（这一条是预注册的"**会变**"） | R-h 的 `--json`：`objects.table.schema_version` `"1"` → `"2"`；四格仍 `0/0/0/0`；`objects` 仍 **64**（CI 线接 R-h 的步骤之后是 65，那时按 23 号 §20.1 第 4 条**同一提交**登记那一行） |
| 硬约束 A | 连接键的**变异自证**（AGENTS 第 45 条） | 在**影子表**上：删一行 facts → `fact_without_check` 从 0 变 1；给一行 checks 写一个不存在的 key → `check_covers_unknown_fact` 从 0 变 1；**撤回 → 都回 0** |
| 硬约束 B | C3 选 A 时的**等价性** | `check_wiring` 在一组合取配置上的返回字符串与 refactor 前**逐字节相同**（含"hooks.json 没写 timeout 按 600000 计"那一支） |
| 硬约束 C | 跨文件契约 | 新工具默认输出的 `HITS:` 行能被**真的** `ci_local.report_only_reading()` 读出（`0` / `N` / `unavailable` 三种；读取器一个字不改） |

---

## 7 需要 CI 线配合的事项（单独列出）

> **文件归属**：`tools/ci_local.py`、`tests/unit/test_ci_local*.py`、`tools/phase_evidence.py`、
> `.github/workflows/*` 属 **CI 线**；控制面会话**一个字都不动**。
> 但 `validation/instrument-checks.yaml` 属**控制面会话**——那**一行数据**按 23 号 **§20.1 第 4 条**的裁定，
> **授权 CI 会话在同一提交里加**（跨文件改一次，不拆两次）。

| # | 要 CI 线做什么 | 期望读数 | 为什么必须 CI 线做 |
| --- | --- | --- | --- |
| 1 | `tools/ci_local.py` 的 `REPORT_ONLY_STEPS` 加一条 `Control plane facts (report only)`（`args=("tools/control_plane_facts.py",)`，**不带 `--json`**；六个字段必填） | 默认输出的 `HITS: <四格合计> / ...` 行；非零退出**不计入门禁失败** | 只报告步骤表是 CI 线的数据；改它要同步 `tools/exemption_expiry.py` 的读数（`declared` 今天 **7** → 加 R-h 那条 **8** → 再加这条 **9**） |
| 2 | 同一提交里给 `validation/instrument-checks.yaml` 加那一行（`check_id: "report-only:Control plane facts (report only)"`、`covers_facts` 引用它读的全部 key） | 仪器自证 `objects` 64 → **65**、`no_check_id` 仍 **0** | 不加这一行，R-h 会把新步骤报成 `no_check_id = 1`（**只报告、不阻断**，但那就是"新步骤没被登记"）；**授权已在 23 号 §20.1 第 4 条** |
| 3 | `tests/unit/test_ci_local*.py`：一条"登记 + 读数"用例（这一步在 `REPORT_ONLY_STEPS` 里、`args` 不含 `--json`、六个字段非空、`report_only_reading()` 从**真实默认输出**读出整数） | 用例绿 | 那几个用例文件是 CI 线的；跨侧读数契约已由控制面会话的用例钉住，不必重复造 |
| 4 | **不需要**做的（写下来免得去找） | —— | ① 不进 workflow 分组（只报告步骤不在 `.github/workflows/*.yml` 里，`unregistered_steps()` 看不到它）；② 不动 `tools/phase_evidence.py`（加指针是**升格之后**的事）；③ 不接退出码（只报告期 `enforced: false`） |
| 5 | 若在 Windows 上跑 `--full`：按 23 号 **§20.1 第 6 条**——用了 `PYTEST_XDIST_AUTO_NUM_WORKERS=0`（xdist 在本会话形态下必然 INTERNALERROR）就**必须在读数处逐次声明**它、理由与代价 | 读数里带这一句 | 没有声明的门禁读数按"环境前提不明"处理 |

**交接的验收办法**（与 25 号 §6 / 26 号 §3 同一条纪律）：改完跑
`python tools/ci_local.py --full --python .venv/Scripts/python.exe`，把 `--timings` 与**只报告那一行的读数**
一起贴进 23 号的新一节；**不要只贴退出码**。

---

## 8 预算

**先对齐口径**（方案 §7 / §7.1，2026-09-29 裁定）：台阶 5 的原估算 **src 0.5k–1.5k / tests 0.6k–1.8k**；
**硬上限 = 原估上限 × 2.5** → **src 3.75k / tests 4.5k**；**复核线 = 原估上限 × 1.5** → **src 2.25k / tests 2.7k**；
超过复核线就**停下复核**（"为什么超、估的是什么口径"），不等于停工。

**台阶 5 已经花了多少**：**src 0 / tests 0**。`validation/instrument-checks.yaml` 的 618 行是**台阶 4**
（R-h）的数据，不重复计入台阶 5；本轮（设计稿）只写文档。

**本设计的估计**（口径 = 新增行；依据是同类机制的已花行数：R-h 的 `tools/instrument_self_proof.py` 980 行、
`tools/provenance_loop.py` 302 行、`src/provenance/wiring_scope.py` 175 行、`tools/exemption_expiry.py` 的载荷）：

| 件 | src | tests | tools | 数据 |
| --- | --- | --- | --- | --- |
| facts 表加载 + 连接键 + 三组读数（**一个**新工具） | 0 | 0 | **350–600** | **95–150**（13 行 × 9 字段） |
| checks 表扩字段（加载器 + 表头 + 两处写死版本号的用例） | 0–5 | 40–70 | 0 | 0 |
| 连接键双向必查（含影子表变异自证） | 0 | 60–110 | （含在上面的工具里） | 0 |
| C1 只报告 | 0 | 30–60 | （含） | 0 |
| C2 只报告 | 0 | 30–60 | （含） | 0 |
| C3 · **方案 A**（谓词收敛 + 等价性用例） | 110–170 | 50–90 | （含） | 0 |
| C3 · 方案 B（不动 `hooks.py`） | 0 | 30–60 | （含） | 0 |
| 声明键 + AGENTS 第 55 条登记 + `tools/README.md` 一行 | 5 | 0 | 2 | 0 |
| **合计（A）** | **115–175** | **210–390** | **350–600** | **95–150** |
| **合计（B）** | **5** | **190–360** | **390–640** | **95–150** |

**结论**：

- **src 115–175**：复核线 2.25k 的 **5%–8%**，硬上限 3.75k 的 3%–5%；**不越线**；
- **tests 210–390**：复核线 2.7k 的 8%–14%；**不越线**；
- 因此**不需要**为了预算缩小范围。**照实说明为什么这次这么低**：台阶 5 的只报告部分**不建新的判定机制**
  （不合并谓词、不加 FATAL、不接退出码），主体是一张数据表 + 一个单消费方的读数工具，
  与 25 号 §7 估 R-h（src 260–440 / tests 180–300）**同量级**——而 R-h 的实测是 src **+4** / tests **+352** / tools **+981**
  （23 号 §19.6）。所以真正要盯的是 **tools 桶**：方案 §7 的原估里**没有**这一项（§7.1 自己写过"原估计里没有这一项"），
  本设计把它**单独列出来**，不藏进 src。
- **可以缩小到什么范围**（若评审仍要收缩，按代价从小到大）：

| 方案 | 做什么 | 不做什么 | src | tests | tools | 数据 |
| --- | --- | --- | --- | --- | --- | --- |
| **A′** | facts 表 + checks 扩字段 + 连接键 | **不做** C1/C2/C3 三组读数 | 0–5 | 100–180 | 180–300 | 95–150 |
| **B′** | A′ + C1 + C3（方案 B：不动 `hooks.py`） | C2（它今天连判据都没有） | 0–5 | 160–300 | 300–480 | 95–150 |
| **C′** | 全做，但 C3 只报已有结构化的那一套（方案 C） | 第二套结论 | 0–5 | 180–330 | 330–560 | 95–150 |
| **全做（推荐）** | 上面全部 + C3 方案 A | 无 | 115–175 | 210–390 | 350–600 | 95–150 |

**一个诚实的提醒**：若评审要求把"pytest 检查"扩成第五族（§2.3 的连接力上限），或把 C3 的两个 dsh 侧上限也收敛成一份实现
（那要动 `wiring.py` 的通道事实），src/tests 都会往上走一档；两者都**不属于**本设计，另开一轮。

---

## 9 未核实（逐条）

1. **orchestrator 注册表条目的代码侧对应关系**：`tool_name`（`edit_file` / `write_file` / `edit_policy` / `write_policy`）
   在 `src/orchestration/tools.py` 里 **grep 不到**；代码侧能读到的只有 `nodes.py:69-72` 的四个 `orc.*` 常量。
   它在哪里解析**未核实**——C2 因此**不给红条件**（§3.5）。
2. **C2 的"哪一组差异算缺口"没有判据**：32 条 `not_governed` 是不是全部"按设计"，我只核对了注册表与 manifest 的**条目**，
   没有逐条去问"这个只读工具是不是真的只读"。
3. **`wiring` 的 `timeout_budget` 盲点没有实测**：今天 7 条通道**都没有**声明 `pre_evidence`，
   所以"通道声明了 `pre_evidence` 时 `ok` 会不会误报 true"**没有实测过**——它是从代码读出来的结论（§1.3）。
4. **连接键的连接力上限**只做了 grep 级别的核对：我确认了四族的枚举处（`.github/workflows/*.yml` / `CHECKS` / `SCENARIOS` / `REPORT_ONLY_STEPS`）
   里没有 pytest 检查，但**没有**把全仓的 pytest 用例逐条映射到 facts（那是"第五族"那一轮的事）。
5. **`.tmp` 实例不可复核**：C3 的第二套结论（`pre_evidence` 那一支）今天只有 `.tmp/step3c/round/projectA` 这一个载体，
   `python tools/cleanup.py` 之后它就没了；仓库内**没有**第二处声明 `pre_evidence` 的配置（这也是事实表只登记仓库内那一套的原因）。
6. **本设计的估计是估计**，不是 `numstat` 读数（本稿只写文档）。
7. **`97` 那个口径变体是我自己实现的翻译器**（把 `**/` 解成"至少一段目录"），与归档 03 号的参考实现**互相独立**，
   两边得到同一个数（97）；但"**/` 的语义在平台侧只有一份解释权"这件事我**没有**再验证一次（`validators/globs.py` 的 docstring 与
   `glob_to_regex` 的实现在同一条路径上，我没有跑跨实现对照）。
8. **C1 的 101 与检查点树的 101 相同**这件事我只核到了"新增 18 个 .py 全是 `test_*` 形态"这一层；
   没有逐条比对两份 101 的清单是否**同一批文件**（归档 03 号 §4 有旧清单，逐条比对是可选动作）。

---

## 10 复现命令（只读）

> 下面每条都在 `6ed3ca8` 上实跑过；需要解释器的用仓库自己的 `.venv`。
> 我这一轮的探针脚本落在 `.tmp/step30/`（**不提交**，`cleanup.py` 之后不可复核），
> 因此下面给的是**不依赖 `.tmp` 的一行命令**。

```powershell
# C1：文件数 / 直接躺在 tests/ 下的 4 个 / 判定不一致的方向
.venv\Scripts\python.exe -c "import subprocess;F=[p for p in subprocess.run(['git','ls-files','tests'],capture_output=True,text=True).stdout.splitlines() if p.endswith('.py')];print(len(F),[p for p in F if p.count('/')==1])"
.venv\Scripts\python.exe -c "import sys,subprocess;sys.path.insert(0,'src');from validators.globs import glob_match;from validators.registry import load_test_layout;import yaml;L=load_test_layout(root='.');A=yaml.safe_load(open('examples/dsh/dsh-adapter.yaml',encoding='utf-8'))['test_paths'];F=[p for p in subprocess.run(['git','ls-files','tests'],capture_output=True,text=True).stdout.splitlines() if p.endswith('.py')];D=[p for p in F if L.is_test(p)!=any(glob_match(x,p) for x in A)];print('files',len(F),'disagree',len(D))"

# C1：层见证（同一文件两条路径两层）
.venv\Scripts\python.exe -c "import sys,argparse,pathlib;sys.path.insert(0,'src');from adapters.dsh.adapter import load_config;from policy.check import resolve_layer;C=load_config('examples/dsh/dsh-adapter.yaml');W='tests/fixtures/validators/project/src/shop/order_controller.py';a=argparse.Namespace(layer=None,config_root=None,workspace='.',file=W);print('adapter',C.layer_resolution(W).layer,'platform',resolve_layer(a,anchor=pathlib.Path('.').resolve(),root=pathlib.Path('.').resolve(),file_path=pathlib.Path(W))[0])"

# C1：检查点树与今天的文件数（184 -> 202；新增 18 个全是 test_ 形态）
.venv\Scripts\python.exe -c "import subprocess;old=[p for p in subprocess.run(['git','ls-tree','-r','e235626c','--name-only','--','tests'],capture_output=True,text=True).stdout.splitlines() if p.endswith('.py')];new=[p for p in subprocess.run(['git','ls-files','tests'],capture_output=True,text=True).stdout.splitlines() if p.endswith('.py')];print(len(old),len(new),len([p for p in new if p not in set(old)]))"

# C2：工具表三处 + manifest↔代码相等
.venv\Scripts\python.exe -c "import sys,yaml;sys.path.insert(0,'src');from adapters.dsh.adapter import TOOL_TABLE;R=yaml.safe_load(open('registry/tool-registry.yaml',encoding='utf-8'))['tools'];M={p.split('/')[1]:yaml.safe_load(open(p,encoding='utf-8'))['tools'] for p in ['adapters/dsh/manifest.yaml','adapters/generic-json/manifest.yaml','adapters/legacy-post-only/manifest.yaml']};print('registry',len(R),{a:sum(1 for t in R if t.get('agent')==a) for a in sorted({t.get('agent') for t in R})});print('manifests',{k:len(v) for k,v in M.items()},'code',len(TOOL_TABLE),'equal',{t['name'] for t in M['dsh']}==set(TOOL_TABLE))"

# C3：两套结论（仓库实例 = 两段；.tmp 实例 = 三段）
.venv\Scripts\python.exe -c "import sys;sys.path.insert(0,'src');from adapters.dsh.adapter import load_config;from adapters.dsh.hooks import DEFAULT_HOOK_TIMEOUT_MS,check_wiring;C=load_config('examples/dsh/dsh-adapter.yaml');print('example pre_evidence',C.pre_evidence,'timeout_ms',C.timeout_ms,'check_wiring',repr(check_wiring(C,hooks_config_path='examples/dsh/hooks.json')),'default_limit',DEFAULT_HOOK_TIMEOUT_MS)"
.venv\Scripts\python.exe -c "import sys,os;sys.path.insert(0,'src');from adapters.dsh.adapter import load_config;from adapters.dsh.hooks import check_wiring;p='.tmp/step3c/round/projectA/.policy/dsh-adapter.yaml';C=load_config(p);print('tmp pre_evidence',C.pre_evidence.timeout_ms,'sum',C.pre_evidence.timeout_ms+C.timeout_ms,'check_wiring',repr(check_wiring(C,hooks_config_path=os.path.join(os.path.dirname(p),'hooks.json'))))"

# 两张表的现状：R-h 的读数与豁免到期读数
.venv\Scripts\python.exe tools\instrument_self_proof.py
.venv\Scripts\python.exe tools\exemption_expiry.py

# 登记表的命名空间分布（64 行怎么分的）
.venv\Scripts\python.exe -c "import collections,yaml;d=yaml.safe_load(open('validation/instrument-checks.yaml',encoding='utf-8'));print(d['schema_version'],len(d['checks']),dict(collections.Counter(r['check_id'].split(':')[0] for r in d['checks'])))"
```

---

**本文件是本轮的第 3 个提交**（第 1 个是 23 号 §20 的裁定登记与两处文档更正，第 2 个是 26 号第 2 件事的授权更正）；
索引见同目录 `README.md`。
