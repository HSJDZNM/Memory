# T3 rule-fidelity 实施记录（G6 / G7 / G8 / G10）

> 任务：共享任务板 `task-3`（根因 R3 / R4·glob / R5·工具表，见 `00-remediation-plan.md` 第 1 节）。
> 写域：`src/adapters/dsh/adapter.py`、`src/policy/checkers.py`、`adapters/dsh/manifest.yaml`、
> `adapters/approved.json`（只由审核命令重签）、`tests/{unit,contract,integration}` 下的相关测试、本文档。
> 所有命令用系统 python（3.13），未创建或改动 `.venv`，未运行 `tools/ci_local.py`。

## 0. 一句话

四个缺口都是"**说得出口、证不出来**"：依赖证据靠文字扫描、分层命中不落记录、
通配符少一层、工具表缺条目也没有漂移检测。修复的共同形状是**把"证不出来"变成显式状态**，
并给每一处配一条会失败的检查。

## 1. 交付摘要

| 缺口 | 根因 | 改了什么（坐标） | 会失败的检查（修前 → 修后） |
| --- | --- | --- | --- |
| G8 | R4（`**/` 少一层） | `src/adapters/dsh/adapter.py:612` `_glob_to_regex`：`**/` → `(?:.*/)?` | `glob_match("**/*.md","README.md")`：False → True |
| G7 | R3（分层靠文件名） | `adapter.py:679` `LayerResolution` + `:735` `AdapterConfig.layer_resolution()` | `hasattr(AdapterConfig,"layer_resolution")`：False → True |
| G6 | R3（文本扫描冒充依赖证据） | `adapter.py:434-608` 依赖提案 + `src/policy/checkers.py:69-118` 统一匹配、`:170-240` 失败关闭 | 见 §6：四种写法由"零命中"变"阻断" |
| G10 | R5（声明与运行期无漂移检测） | `adapter.py:185` TOOL_TABLE 补 7 项、`:311-384` 漂移检测；`adapters/dsh/manifest.yaml:186-215` 同步；`approved.json` 重签 | `spawn_teammate in TOOL_TABLE`：False → True |

新增测试：

- `tests/contract/test_dsh_adapter.py`：G6 依赖证据（含 5 种绕过写法参数化）、G7 分层命中、G8 通配符与跨模块对照、G10 工具表与 note 留痕；
- `tests/contract/test_tool_table_drift.py`（新）：漂移检测的观察来源、空观察集拒绝、新增项待评审；
- `tests/integration/test_dependency_path_consistency.py`（新）：AST/依赖图路径与预执行路径的**同结论**测试。

## 2. G8：`**/` 的零层匹配

### 2.1 语义

`_glob_to_regex` 现在与 `src/validators/globs.py:24-52` 逐条同义：

- `**/` = **零个或多个**目录（`(?:.*/)?`）—— 根目录文件与"前缀后的零层"（`src/**/*.py` vs `src/a.py`）都命中；
- 结尾 `**` = 任意剩余路径；`*` 不跨目录；`?` 单字符。

两处实现的等价性由 `tests/contract/test_dsh_adapter.py::test_dsh_glob_semantics_match_the_validator_matcher`
钉住：样本来自 `adapters/dsh/adapter.yaml` 的真实 pattern + 边界 pattern（含 `src/**/` 形态），
零层 / 一层 / 深层三种目录深度各取一例，逐对比对两份实现的布尔结果（不是比对名字集合）。

### 2.2 影响表（必做项：修好后新增的命中）

方法：对 `adapters/dsh/adapter.yaml` 的每一条 pattern，用 `git ls-files`（865 个跟踪文件）
分别跑修前（`git show HEAD:src/adapters/dsh/adapter.py` 的旧匹配器）与修后匹配，取差集。

| pattern | 映射 | 新增命中（真实跟踪文件） | 丢失命中 |
| --- | --- | --- | --- |
| `**/*_controller.py` | layer=controller | 0（本仓库没有根目录 `*_controller.py`） | 0 |
| `**/*_service.py` | layer=service | 0 | 0 |
| `**/*_repository.py` | layer=repository | 0 | 0 |
| `**/*.py` | layer=module | 0（本仓库没有根目录 `.py`） | 0 |
| `**/*.md` | layer=docs | **2：`AGENTS.md`、`README.md`** | 0 |
| `**/*.py` | language=python | 0 | 0 |

补充：V1 的 10 行 G08 验收（含 `**/*.py` vs `cli.py`、`src/**/*.py` vs `src/a.py`、
`src/**/*.py` vs `other/src/a.py`、`a.pyc` / `a.md.bak` 的**不放宽**反例）逐行实测全中，
见 §7 的 `g08-check.py`。任一条 pattern 的"放大"只有**零层**这一种形态：没有任何 pattern
丢失命中，也没有任何 pattern 命中到更深的目录。

**结论：放大可接受，不需要改数据（adapter.yaml）。** 理由：新增的两条命中恰恰是
"声明过 `**/*.md → docs`、却对根目录 README 静默失效"的那种配置缺陷；修好之后
根目录 `.md`/`.py` 从"没有 layer 映射 → 直接阻断"变成"按声明映射后正常判定"，
这正是声明本来就想要的行为。

`src/validators/globs.py:9-12` 原先把这份分歧写成"刻意不同"，已由 Lead 同步更新
（该文件不在我的写域，我发了消息请其修改；新措辞指向本文的 §2.2 与跨模块对照测试）。

## 3. G7：分层命中显式化

```python
@dataclass(frozen=True)
class LayerResolution:      # adapter.py:679
    layer: Optional[str]
    matched_pattern: Optional[str]
    defaulted: bool
```

- 命中某条 layers 规则 → `(rule.layer, rule.pattern, False)`；
- 未命中任何规则 → `(default_layer, None, True)`（`default_layer` 可能为 `None`）。

`layer_for()` 保留原签名与行为（现由 `layer_resolution().layer` 实现）。
「未命中任何分层规则」因此可与「命中某个层」区分：默认值不是一条规则。

审计字段名沿用计划冻结的三个：`layer` / `layer_matched_pattern` / `layer_defaulted`（由 T1 写进 hooks 审计）。
V1 的 G07 探针正是按这三个键读记录（`tools/governance_gap_probe.py:1366-1381`），本接口给出的
值可以满足它的两条断言（命中态 `defaulted is False` 且 pattern 等于命中的 pattern；默认态 `defaulted is True` 且 pattern 为 `None`）。

## 4. G6：依赖证据

### 4.1 曾经被结构性放行的写法（实测修前行为见 §6）

| 写法 | 修前 `proposed_dependencies` | 修后 |
| --- | --- | --- |
| `from . import repository` | `()` | `(".repository",)` → 命中 |
| `from pkg.repository import X` | `("pkg",)` | `("pkg.repository", …)` → 命中 |
| `from shop.order_repository import OrderRepository` | `("shop",)` | `("shop.order_repository", …)` → 命中 |
| `importlib.import_module("repository")` | `()` | `("repository",)` → 命中 |
| `__import__("repository")` | `()` | `("repository",)` → 命中 |
| `importlib.import_module(name)` | `()`（静默放行） | 证明不了 → 依赖类 checker 失败关闭（critical） |

提取规则（`adapter.py:434-608`）：

- `from X import a, b`：登记 `X` 与**每个被导入名字的候选子模块** `X.a` / `X.b`。
  候选必须一起登记，因为 `from <pkg> import <submodule>`（`submodule_controller_bad.py` 那种写法）
  在 AST 路径上会把依赖边落在子模块文件上，而预执行路径没有模块索引 —— 漏登记 = 结构性放行；
- 相对导入保留前导点（`.repository` / `..pkg.mod`）；
- 动态导入按 AST 路径同一识别口径（点分调用末段是 `import_module`，或 `__import__`），
  第一个实参是**单个字符串字面量**（只认 r/u 前缀）才算证明得了；变量 / 拼接 / f-string / 缺参数
  一律算"证明不了"；
- 整行注释不参与提取（行内注释仍是残余面，见 §9）。

### 4.2 匹配语义：两条路径共用同一个函数

`src/policy/checkers.py:82-118`（`dependency_words` / `dependency_forbidden`）：

- `dependency_words()`：点分路径逐段再按 `_` 切词；
- `dependency_forbidden(forbidden, *values)`：整名相等，或 forbidden 的词序列在依赖标识里**连续出现**。

为什么按 `_` 切词：Python 模块名与文件名共用同一套词，项目档案里的组件模式也是按这条路走的
（`validation/project.yaml` 的 `**/*_repository.py` → 组件 `repository`）。因此
`shop.order_repository` 与 AST 路径解析出的组件名 `repository` 落在同一个词上 ——
只比整名会让最常见的那种写法漏判，那正是"看起来在管、实际什么都没查"。

反例（防止退化成子串匹配，已写成测试）：
`dependency_forbidden("repository", "service.orderservice")` / `("repository","orderservice")` /
`("repository","repositories")` / `("shop.order_repository","repository")` 全部为假。

证据路径同时比较 `fact.name` 与 `fact.module`：AST 路径的外部包只留顶层名（`pkg`），
点分路径在 `module` 里（`pkg.repository`），只看 `name` 会漏掉 `from pkg.repository import X`。

### 4.3 "证明不了"是显式状态

`adapter.py:589` `_governed_dependencies()` 把两种"证明不了"登记成保留标记
（`checkers.py:69-80`）：

- `<unproven-dynamic-import>`：动态导入目标不是字面量；
- `<unparseable-changed-text>`：变更文本既不能作为模块、也不能作为整体缩进一级的块解析
  （只对声明为 python 的路径做：import 语法与 `ast.parse` 都是 Python 的事实）。

依赖类 checker 见到标记即以 **critical** 阻断（不被同批 PASS 抵消），且**只在规则 scope 命中时**生效 ——
这正是计划对"可能过度阻断"的约束：非 controller 层、或没有依赖规则命中时，标记只留在审计里。

### 4.4 跨路径一致性（Lead 要求的对照）

`tests/integration/test_dependency_path_consistency.py`：同一段代码、同一个 PolicyContext、
同一个只含 ARCH-001 的 RuleSet、同一个判定入口 `policy.engine.evaluate`，两条路径分别是

- AST / 依赖图：真实验证器流水线 `validators.pipeline.run_pipeline`（py.ast → py.depgraph）；
- 预执行：`to_policy_event` → `to_policy_context` → `evaluate`（无证据）。

| 输入 | 预执行路径 | AST/依赖图路径 | 一致 | 正确值 |
| --- | --- | --- | --- | --- |
| `from shop.order_service import OrderService`（正例） | allow | allow | ✅ | allow |
| `from shop.order_repository import OrderRepository` | block | block | ✅ | block |
| `from shop import order_repository` | block | block | ✅ | block |
| `from pkg.repository import X` | block | block | ✅ | block |
| `from . import repository` | block | block（unresolved → 失败关闭） | ✅ | block |
| `importlib.import_module("repository")` | block | block | ✅ | block |
| `importlib.import_module(name)` | block（保留标记） | block（unresolved dynamic） | ✅ | block |
| 语法错误 | block（保留标记） | block（py.ast 失败关闭） | ✅ | block |

**已知且被钉住的不等价情形**（`KNOWN_DIVERGENCES`，写成断言而不是文档里的一句话）：

| 输入 | 预执行 | AST | 原因 |
| --- | --- | --- | --- |
| `from shop.missing_service import MissingService`（模块不存在，但名字里没有组件词） | allow | block | 预执行路径不读文件系统、没有模块索引，"顶层包存在但模块不存在"只有 AST 路径能判 |

这条差距的兜底是：写完之后 Phase 5 仍然对真实文件失败关闭，所以系统整体没有放行；
弱的是**预执行这一道闸**。它变红意味着差距形态变了，需要重新评审。

## 5. G10：工具表补齐与漂移检测

### 5.1 补齐（`adapter.py:185-299`，`manifest.yaml:186-215`）

新增 7 项，全部 `ToolKind.NO_FILE` / `direction: inbound`：
`spawn_teammate`、`team_task_create`、`team_task_get`、`team_task_list`、`team_task_update`、
`wait_agent`、`load_workspace_dependencies`。工具表 31 → 38 项。

分类口径只有一条：**这个工具自己写不写仓库里的文件**。不写 → NO_FILE（记录但不治理）。
`spawn_teammate` 的 note 明确写"本检查站看不到子会话、只记录、不声称已治理"
（AGENTS.md 第 24 条），并且这句话会通过 `to_policy_event` 的 reason 进入 hooks 审计
（`adapter.py` 里 NO_FILE 分支优先使用 `spec.note`；这条由
`test_spawn_teammate_records_that_the_child_session_is_not_observable` 钉住）。

为什么不是 EXECUTE：`tests/contract/test_enforcement_protocol.py::test_every_governed_dsh_tool_is_registered`
要求所有 write/execute 类工具都在 `registry/tool-registry.yaml` 里登记（那是 T4 的写域）；
而且把"拉起会话"记成"已被受控链路治理"本身就是过度声称 —— 受控链路管的是这次调用，
管不到子会话之后的写类动作。

### 5.2 漂移检测（`adapter.py:311-384`）

```python
tool_table_drift(observed, *, source, table=TOOL_TABLE) -> ToolTableDrift
observed_tools_from_payloads(payloads) -> tuple[str, ...]
```

- `unreviewed`：观察到了、工具表没有 → **待评审**；`absent`：工具表有、本批没观察到 → 信息（白名单可以更宽）；
- 观察来源（`source` 必填，结论要能追到来源）：dsh 钩子审计 JSONL 的 `tool` 字段（运行期真实调用）、
  `tests/fixtures/agent_events/dsh/*.json`（committed 的真实采集载荷）、会话工具清单快照；
- **拿不到观察数据时报错，不跳过**：空观察集直接 `DshEventError`（"没观察到"≠"没有漂移"），
  形状不对的载荷同样报错。两种来源都有测试（`tests/contract/test_tool_table_drift.py`）。

观察快照（`SESSION_OBSERVED_TOOLS`，33 个）与白名单的**双向**差集都被钉住：
新增项会红（`test_a_new_tool_name_is_reported_for_review_instead_of_being_ignored`），
白名单条目消失也会红（`test_tool_table_entries_outside_the_session_are_the_documented_ones`）。
`tests/fixtures/agent_events/dsh/pre-tool-use-unknown-tool.json` 里刻意不在白名单的
`mcp__github__create_issue` 是唯一被允许出现在差集里的名字（它是"未知工具必须被拒绝"的反例夹具）。

### 5.3 manifest 与已审核哈希

`adapters/dsh/manifest.yaml` 与 `TOOL_TABLE` 逐项一致（`test_dsh_manifest_matches_the_phase_2_tool_table` 通过），
`adapters/approved.json` 由审核命令重签（**未手改哈希**）：

```
python -m adapters.cli approve --reviewer rule-fidelity
```

- dsh `manifest_digest`：`sha256:e3adea73…` → `sha256:5225c41a37a1383afb2ea5e636b5f154be5164d2d4a7d6c9fc0c637aac49dd90`；
- `reviewed_by`：`HSJDZNM` → `rule-fidelity`（审核动作是 T3 工作流做的，如实记录；Lead 要换成
  人工审核人只需重跑同一条命令）；
- 顺带刷新了三个 adapter 的 `ceiling_reasons`（旧值里残留着"未审核"字样，重签后与实际一致）。

## 6. 修前 / 修后对照（HEAD 源码实测）

把 HEAD 版本按包内子模块装载后直接调用（脚本：`.tmp/rule-fidelity/baseline-compare.py`）：

| 检查 | 修前 | 修后 |
| --- | --- | --- |
| `proposed_dependencies("from . import repository")` | `()` | `(".repository",)` |
| `proposed_dependencies("from pkg.repository import X")` | `("pkg",)` | `("pkg.repository", "pkg.repository.x")` |
| `proposed_dependencies("from shop.order_repository import …")` | `("shop",)` | `("shop.order_repository", …)` |
| `proposed_dependencies('importlib.import_module("repository")')` | `()` | `("repository",)` |
| `proposed_dependencies("importlib.import_module(name)")` | `()` | `("import_module",)`（证明不了） |
| `glob_match("**/*.md","README.md")` | False | True |
| `glob_match("src/**/*.py","src/a.py")` | False | True |
| `AdapterConfig.layer_resolution` | 不存在 | 存在 |
| `"spawn_teammate" in TOOL_TABLE` | False | True |
| `tool_table_drift` | 不存在 | 存在 |
| checker 上下文路径命中 `shop.order_repository` | 0 | 1 |
| checker 证据路径命中 `name=pkg, module=pkg.repository` | 0 | 1 |
| checker 对 `<unproven-dynamic-import>` | 0（静默放行） | 1（critical 阻断） |

## 7. 测试与真实结果

```
# 改动前的基线（必须绿才动手）
$ python -m pytest tests/integration/test_rule_corpus.py tests/contract -q
271 passed, 1 warning in 20.58s

# 新增/更新后的相关测试
$ python -m pytest tests/contract/test_dsh_adapter.py tests/contract/test_tool_table_drift.py \
    tests/integration/test_dependency_path_consistency.py tests/integration/test_dsh_hook.py -q
2 failed, 93 passed
  # 2 failed = test_dsh_hook.py 的两个 CLI 用例（T1 的接线严格化，Lead 明确由其统一修改，我未触碰）

$ python -m pytest tests/integration/test_dependency_path_consistency.py -q
9 passed, 1 warning in 0.91s

# 全量（unit + contract + integration）
$ python -m pytest tests/unit tests/contract tests/integration -q
13 failed, 1309 passed, 1 skipped in 209.38s
```

全量里那 13 条的归属（逐条复核过，不是"大概"）：

| 失败 | 归属 | 处置 |
| --- | --- | --- |
| `test_dsh_adapter.py` 2 条（我新写的断言过严 / `load_config(adapter.yaml)` 形状不符） | T3（我） | 已修：断言改为"命中集合 + 命中的依赖名"；配置改为从真实 pattern 构造 |
| `test_dsh_hook.py::test_allow_calls_…` | T3（我，Lead 指派） | 已改断言并写明理由（见 §7.1） |
| `test_dsh_hook.py` 2 条 CLI 用例 | T1 / Lead | 未触碰 |
| `test_enforcement_cli.py::test_pattern_approval_…` | T4 | 未触碰 |
| `test_governance_gap_probe.py` G02/G04/G07/G09/G13 | V1 + 各工作流 | 未触碰（G07 等 T1 写审计字段） |
| `test_validator_pipeline.py` 2 条 | 并发假红 | 单独重跑：3 passed（同一工作树里多个会话共用 `.tmp/`，AGENTS.md 已警告过） |

### 7.1 V1 探针 G06 的独立复现（隔离目录，不受探针历史状态影响）

V1 的探针在**当前工作树**上跑 G06 会红，但红的原因是 `reason=event_replay`：

```
[对照] controller_service_allowed: src/inventory_controller.py <- 'from inventory_service import …' -> exit=2 reason=event_replay
[对照] module_layer_allowed:      src/helpers.py           <- 'from repository import Repository'      -> exit=2 reason=event_replay
```

探针的受控工作目录 `.tmp/verifier/probe/baseline/audit/` 里留着上一次运行的台账，
同一个 `action_id`（`probe-session:probe-g06-controller_service_allowed`）第二次出现时被
幂等闸按设计拒绝 —— 这是 G04 要的行为，但它让 G06 的两条**对照**用例变成"blocked"。
G07 的 `probe-g07-defaulted` 是同一个原因（探针证据里同样写着 `event_replay`）。

为了不把"探针状态"误读成"我的修复"，我把 V1 的 11 条用例原样搬到隔离目录重跑了一遍
（`.tmp/rule-fidelity/g06-e2e.py`：全新项目目录、全新配置、`ledger=None`，直接走真实 Hook 链
`DshPreExecuteHook.handle`）：

```
$ python .tmp/rule-fidelity/g06-e2e.py
OK  literal_from               expected=blocked  observed=blocked  exit=2 reason=policy_block
OK  plain_import               expected=blocked  observed=blocked  exit=2 reason=policy_block
OK  importlib_module           expected=blocked  observed=blocked  exit=2 reason=policy_block
OK  dunder_import              expected=blocked  observed=blocked  exit=2 reason=policy_block
OK  relative_import            expected=blocked  observed=blocked  exit=2 reason=policy_block
OK  relative_named             expected=blocked  observed=blocked  exit=2 reason=policy_block
OK  submodule_import           expected=blocked  observed=blocked  exit=2 reason=policy_block
OK  dotted_import              expected=blocked  observed=blocked  exit=2 reason=policy_block
OK  alias_case                 expected=blocked  observed=blocked  exit=2 reason=policy_block
OK  controller_service_allowed expected=allowed  observed=allowed  exit=0 reason=allow
OK  module_layer_allowed       expected=allowed  observed=allowed  exit=0 reason=allow
G06 failures: []
```

9 条绕过写法全部**因策略判定**阻断（不是 replay / param_error），2 条对照全部保持放行。

### 7.2 关于 `test_dsh_hook.py` 里那条被指派的断言

```python
assert event.dependencies == ("service", "service.orderservice", "util", "util.clock")
```

输入是 fixture `pre-tool-use-edit-allow.json` 的
`"from service import OrderService\nfrom util import clock"`。新值是语义变更后的正确值，理由：

- `from` 的模块本身是依赖（`service` / `util`），完整点分路径必须保留 —— 旧实现只留顶层名字，
  等于放行 `from shop.order_repository import X` 这类写法；
- 被导入的名字**可能是子模块**（`from shop import order_repository` 是必须命中的写法之一），
  预执行路径没有模块索引，无法区分"子模块"与"类/函数"，因此候选一起登记；
- 多登记的方向是失败关闭：只可能让依赖规则更早阻断，不会放行。代价是这条断言里的两个
  `x.y` 候选名字（已在这里写明）。

## 8. 没做 / 做不到（含原因）

| 事项 | 原因 |
| --- | --- |
| 改 `src/validators/globs.py:9-12` 的 docstring | 不在我的写域；已发消息请 Lead 修改，Lead 已改并回执 |
| 补 `tests/fixtures/rules/ARCH-001/{good,bad}.py` | **任务书写的这两个文件在仓库里从来不存在**（`git ls-files` 无 ARCH 命中、`git cat-file -t HEAD:…` 报不存在）。且 ARCH-001 的 `source.kind` 是 `project-policy`（AGENTS.md 第 40 条只要求 `standard` 规则有正反例），而 `test_rule_corpus.py` 的夹具上下文是 `layer="fixture"`、ARCH-001 的 scope 是 `layer: controller` —— 补上夹具会直接把该集成测试弄红。Lead 裁决：不补，改由契约测试覆盖（`test_positive_example_is_not_blocked_and_not_skipped` + 5 种绕过写法参数化 + 跨路径一致性测试） |
| 改 `adapters/dsh/adapter.yaml` | G8 的放大（根目录文件）是声明本来就想要的行为，判为可接受；且该文件不在我的写域 |
| 改 `src/adapters/textfacts.py`（Phase 6 依赖提取） | 不在我的写域（只读确认）。它是另一条路径，**仍然有同样的两个缺口**：不识别相对导入（`from . import repository`）、不识别动态导入 —— 见 §9 |
| 把 Phase 5 验证器流水线接进 pre 路径 | 计划 §2「明确不做」：架构变更，不是本轮范围（本轮只做"证明不了就拒绝"的如实标注） |
| 修改 `test_dsh_hook.py` 的两个 CLI 用例 | Lead 明确划界，由 Lead 统一改 |

## 9. 遗留风险与需要 Review 的判断

1. **预执行路径仍然弱于 AST 路径的地方**（已写成断言钉住，不是"应该没事"）：
   (a) 模块存在性（`unresolved`）；(b) 组件映射依赖项目档案（`**/repositories/**` 这种复数/目录形态
   只有 AST 路径能解析到组件名）。兜底是写后 Phase 5 仍然失败关闭。
2. **Phase 6 的 `src/adapters/textfacts.py` 路径没有跟着改**：`json_adapter` / `event_adapter` /
   `dsh_adapter` 都用它，那两个缺口（相对导入、动态导入）在多 Agent 路径上原样存在。
   建议另开任务（写域：`src/adapters/textfacts.py`）把同一套语义搬过去，或直接复用
   `propose_dependencies`。
3. **词级匹配是过度近似**：`forbidden: repository` 会命中 `order_repository_helpers` 这类词序列
   相同的模块名；`repositories`（复数）不命中。方向是失败关闭，且只在规则 scope 命中时生效。
4. **行内注释 / 文档字符串里的 import 仍会被词法提取**（整行注释已排除）。残余面由
   "只在依赖类 checker + scope 命中时生效"约束。
5. **未命中任何分层规则**（`defaulted=True` 且 `layer=None`）仍按原行为在写类事件上阻断 ——
   审计字段由 T1 落地后，G07 才算闭环；V1 的 G07 探针在 T1 完成前会红。
6. `adapters/dsh/adapter.yaml` 是 Phase 6 形态的配置，Phase 2 的 `load_config` 会因
   `schema_version / ledger_alias / max_events_per_window / window_seconds` 四个字段按未知字段拒绝它。
   两份配置各服务一条路径，本轮**没有**合并（不在写域，也不是缺口）；测试里改为"搬真实声明"。
