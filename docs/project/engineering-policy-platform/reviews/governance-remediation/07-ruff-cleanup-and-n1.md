# 07 · ruff 清理与 N1（多 Agent 依赖口径统一）

状态：**执行中（Lead 计划 v1，2026-09-25）**
前置：[00-remediation-plan.md](00-remediation-plan.md) 的 §5 表格里的 **N1** 与 **N8**。

---

## 1. 本轮要收口的两件事

上一轮把两件事**登记未修**（理由都写了，不是沉默地漏掉）；本轮把它们收口：

| 编号 | 上一轮的处置 | 本轮 |
| --- | --- | --- |
| **N8** | 「**不清理**，登记」——依据 AGENTS.md 工作方式第 2 条（改动聚焦），说明写在 [02-channel-inventory.md](02-channel-inventory.md) §9.1 | 清干净，范围见 §2 |
| **N1** | 「**登记为待办**」——把提取逻辑抽成共享模块，让三条路径同一口径 | 修，设计与冻结接口见 §4、§5 |

---

## 2. ruff 清理：范围与实测（用户裁决 = A）

**口径**：对本改动集（`git status --porcelain` 的 44 个文件）里的每个 `.py`，
分别对 `HEAD:<path>` 与工作区版本跑
`ruff check --config validation/ruff.toml`。
对 HEAD 版本必须给 `--stdin-filename`，否则不会套用仓库配置（这是 02 号文档 §9.1 记下的坑）：

```powershell
git show HEAD:src/adapters/cli.py | python -m ruff check --config validation/ruff.toml --stdin-filename src/adapters/cli.py -
```

**实测结果**（Lead，2026-09-25）：

| 桶 | HEAD 既有 | 工作区现状 | 本轮 |
| --- | --- | --- | --- |
| `src/` + `tests/` + 手写 `tools/` | **83** | **148** | **清到 0** |
| `tools/build_learning_notebook.py` | 113 | 113 | **不动**（见下） |
| `docs/`（`nb_cells/nb02.py` 26 + 生成物 `walkthrough.py` 18） | 44 | 44 | **不动**（见下） |

**为什么工作区是 148 而不是 83**：本轮改动集**自己新引入了 65 条**——
主要落在上一轮新建的未跟踪测试文件里
（`test_approval_binding_modes.py` 17、`tools/governance_gap_probe.py` 17、
`test_run_code_static_check.py` 5、`test_dependency_path_consistency.py` 5 …），
其余是既有文件里新增行的 E501。**既然本轮要动这批文件，就一并清到 0**：
只清 83 条会留下「新引入的违规」，等于把 N8 换个方向重演一次。

**边界（明确排除，写在这里而不是留在沉默里）**：

- `tools/build_learning_notebook.py`（113）与 `docs/project/learning/phase-2/walkthrough.py`（18）：
  后者是**由前者生成**的产物（AGENTS.md：「不要手改」）。前者的 E501 绝大多数落在
  **内嵌的 notebook 单元格源码字符串**里——重排等于改学习手册的内容，
  属于另一条产品线（手册生成链，`ci_local` 的 "Learning notebooks are in sync" 守它），
  与治理缺口修复不是一件事。要清必须单开一轮，并重新生成手册。
- `docs/project/architecture/tech-detail/notebooks/nb_cells/nb02.py`（26）：
  同上，它是 tech-detail 讲义的**内容源**，E501 落在单元格代码字符串里。

**逐文件的验收清单**（HEAD 既有 → 工作区现状 → 目标 0）在共享任务板上按写域下发；
每条违规的判定一律以命令输出为准，不以「看起来没问题」为准。

---

## 3. 安全类码的处置（用户裁决：就地修）

范围里有 3 条 bandit 安全类码**没有「行为不变」的机械修法**，逐条处置：

| 码 | 坐标 | 性质 | 处置 |
| --- | --- | --- | --- |
| `S506` | `src/adapters/dsh/adapter.py` `yaml.load(stream, Loader=_StrictLoader)` | **误报**：`_StrictLoader` 是 `SafeLoader` 子类（拒绝未知字段），仓库文档与 `validation/ruff.toml` 的注释都写明这是 SEC-006 的已知误报 | 按**仓库既有 noqa 约定**加行内豁免并写明理由（与 `src/adapters/wiring.py:580` 的 `# noqa: PLC0415 - 理由` 同一写法） |
| `S105` | `src/adapters/dsh/adapter.py` `token == "*"`（**上一轮重构新引入**） | **误报**：bandit B105 对「字符串与疑似口令变量做比较」的判定；这里是比较通配符 | 首选**真修**（把字面量提成命名常量，比较里不再出现字符串字面量）；做不到再按同上约定豁免 |
| `S602` | `tools/ci_local.py` `subprocess(shell=True)` | 真实语义，但 `shell=True` 是 Windows 上跑门禁步骤的实现方式 | 首选**真修**（若能用列表参数表达就不加豁免）；确实不能改则按同上约定豁免并写明**为什么安全** |

**刻意不动 `validation/ruff.toml`**：它的 sha256 会写进每条验证器证据
（`src/validators/adapters/base.py:114` 的 `config_sha256`），
改它等于改证据口径；且该文件注释写明 `[lint.per-file-ignores]` 段「**当前刻意留空**」。
行内 `noqa` 是仓库已经用了 20+ 次的既有约定，可见、可评审、不改变证据口径。

---

## 4. N1：根因与目标设计

### 4.1 根因：同一个语义，两条路径各写一份，只修了一条

上一轮把 G6（「依赖规则只认行首字面写法，换个写法就绕过」）修在 **Phase 2 的 dsh 路径**上，
做法是 `src/adapters/dsh/adapter.py` 里的 `propose_dependencies`：识别相对导入
（`from . import repository`）、识别动态导入（`importlib.import_module("x")`），
并把**证明不了**的部分变成显式状态（`unproven_dynamic` / `parseable`），
再由 `_governed_dependencies` 登记成 `policy.checkers.UNPROVEN_DEPENDENCY_TOKENS` 里的保留标记，
让依赖类 checker **失败关闭**。

而 **Phase 6 的多 Agent 路径**仍用 `src/adapters/textfacts.py` 的**旧口径**：
行级正则、只认字面写法、没有「证明不了」这个状态。三条路径都在调它：

| 调用点 | 现状 |
| --- | --- |
| `src/adapters/json_adapter.py:101` | `payload["dependencies"] = list(proposed_dependencies(text))` |
| `src/adapters/event_adapter.py:203` | 同上 |
| `src/adapters/dsh_adapter.py:105` | 同上（Phase 6 的 dsh 桥，与 Phase 2 的 dsh 是两条路径） |

**后果**：同一段变更文本，走 dsh 路径会被拦，走多 Agent 路径放行——G6 在这条路径上仍然成立，
而且**放行是静默的**（账本上写的是 allow）。

**为什么上一轮没顺手修**：它需要跨模块重构（00 号文档 N1 行）。用户本轮明确要求修。

### 4.2 目标设计：一个引擎 + 一个接线点

两件事一起做，缺任何一件 G6 都还在：

1. **一个引擎**：把 `DependencyProposal` / `propose_dependencies` / `proposed_dependencies` /
   `governed_dependencies` 全部搬进**共享层** `src/adapters/textfacts.py`
   （它的 docstring 本来就写着「依赖是核心上下文的维度，不是某一家 Agent 的属性」——
   现在只是把这句话落实）。`src/adapters/dsh/adapter.py` 改为**薄再导出**，行为逐字节不变。
2. **一个接线点**：`language`（决定「这段文本能不能按 Python 的 import 语法解读」）
   在 Phase 6 路径上只有 `base.Adapter.to_policy_context` 里才算得出来——
   那里 `file` 已归一化（`canonical_path`）、`language` 已由配置解析（`language_for`）。
   所以**把提取挪到那里**，而不是让每个 Adapter 各自提前算：
   - 现在是「三个 Adapter 各自 `payload["dependencies"] = ...`」——**三份实现、三处漏判**；
   - 改成「payload 只带 `text`，`to_policy_context` 用 `language` 统一提取」——**一份实现，按构造一致**。

对照 Phase 2 的既有做法：`src/adapters/dsh/adapter.py:1195` 就是在算完 `language` 之后
`_governed_dependencies(text, language=language)`。Phase 6 只是把同一件事补上。

**向后兼容**：payload 里**显式声明**的 `dependencies` 仍然优先（第三方规范事件可以自带），
只有在「有 `text` 且没有显式 `dependencies`」时才派生。这条必须有测试。

### 4.3 不做的事（防止范围蔓延）

- **不碰** N3（词级匹配的过度近似）与 N4（预执行路径没有模块索引）：
  00 号文档已裁决保留，且 `tests/integration/test_dependency_path_consistency.py`
  把「两条路径不等价」写成了**已知差异的断言**。本轮只统一口径，**不改变**这条已知差异。
- **不动** `validation/ruff.toml`（§3）。
- **不动** notebook 生成链（§2）。

---

## 5. 冻结接口（T1 实现，T2 按它写测试）

```python
# src/adapters/textfacts.py —— 共享层，Agent 无关

class DependencyTextError(ValueError): ...
    # 共享层不得依赖 dsh 的 DshEventError（那是 Phase 2 适配器自己的错误类型）

@dataclass(frozen=True)
class DependencyProposal:
    names: Tuple[str, ...] = ()            # 能证明的依赖名（去重 + 稳定排序）
    unproven_dynamic: Tuple[str, ...] = () # 出现动态导入但目标不是字符串字面量
    parseable: bool = True                 # 变更文本能否作为模块（或整体缩进一级的块）解析

    @property
    def unproven(self) -> bool: ...        # bool(unproven_dynamic) or not parseable

def propose_dependencies(text: str) -> DependencyProposal: ...

def proposed_dependencies(text: str) -> Tuple[str, ...]: ...
    # 向后兼容的薄封装 = propose_dependencies(text).names
    # 语义必须与 HEAD 完全一致：tests/contract/test_dsh_adapter.py 的既有断言
    # **一个字都不许改**，它就是这次重构的回归证明

def governed_dependencies(text: str, *, language: Optional[str]) -> Tuple[str, ...]: ...
    # language != "python" -> ()
    # unproven_dynamic 非空 -> 登记 policy.checkers.UNPROVEN_DYNAMIC_IMPORT
    # not parseable     -> 登记 policy.checkers.UNPROVEN_CHANGED_TEXT
```

**语言只能来自声明**（AGENTS.md 核心约束 6）：`language` 由 adapter 配置的
`languages` 规则 / `default_language` 解析（`base.Adapter.language_for`），
**绝不从文件名或路径猜**。

---

## 6. 分工与写域（互斥，越界由 Lead 打回）

| 任务 | 写域 | 内容 |
| --- | --- | --- |
| T1 引擎 | `src/adapters/textfacts.py`、`src/adapters/dsh/adapter.py`、`src/adapters/base.py` | §4.2 的 1+2；含这三个文件的 ruff 清零 |
| T2 契约测试 | `tests/integration/test_dependency_path_consistency.py`、`tests/contract/test_dependency_extraction_parity.py`（新建） | 按 §5 冻结接口写测试：跨路径同口径、相对/动态导入、保留标记失败关闭、显式 `dependencies` 优先 |
| T3 src ruff | `src/**`（**除** T1 的三个文件） | §2 的 `src/` 桶清零 |
| T4 tests+tools ruff | `tests/**`、`tools/**`（**除** T2 的两个文件与 notebook 生成链） | §2 的 `tests/`+`tools/` 桶清零 |
| V1 独立验收 | `docs/project/engineering-policy-platform/reviews/governance-remediation/08-n1-independent-verification.md`、`.tmp/verifier-n1/**` | §7 |

**三条硬规矩**：

1. `tests/contract/test_dsh_adapter.py` 的**既有断言不许改**（T4 只清它的 ruff）。
   它变了，说明 T1 的重构改变了 Phase 2 的行为——那是回归，不是适配。
2. 任何文件都不得被两个任务同时写；发现需要跨写域改动，先报 Lead。
3. 不许为了让测试变绿而放宽断言（改成 `>=`、加 `try/except` 吞掉、删用例）。
   做不到就说做不到，写进报告。

---

## 7. 验收标准（V1 独立执行，Lead 复核）

1. **G6 在多 Agent 路径上不再可绕过**：构造同一段变更文本（`from . import repository` /
   `importlib.import_module("repository")` / 非字面量动态导入），走 **Phase 6 路径**，
   与走 **Phase 2 dsh 路径**得到**同一结论**；修复前必须是「放行」，修复后必须是「阻断」。
   **必须给出修复前的红**（回退那几行 → 探针再次变红），否则证明不了探针在测这件事。
2. **ruff**：§2 的 in-scope 文件集 **148 → 0**；`tools/build_learning_notebook.py` 与
   `docs/` 的计数**不变**（边界的证明，不是口头声明）。
   命令：`ruff check --config validation/ruff.toml <file>`。
3. **无回归**：`pytest` 全绿，且用例数 ≥ 基线；
   `tests/contract/test_dsh_adapter.py` 的断言在 diff 里**未变**（用 blob hash 证明）。
4. **不静默**：`governed_dependencies` 的 `language != "python"` 分支必须被测试覆盖——
   否则「不提取」会退化成新的静默放行。

---

## 8. 过程记录（Lead 追加）

格式对齐 00 号文档 §5：**执行期实测出来的、计划里没写的东西**记在这里。

| 编号 | 发现 | 坐标 | 处置 |
| --- | --- | --- | --- |
| R1 | **再导出被"清理"掉了，外部可见面被无声缩小**：T1 把依赖引擎搬进 `textfacts.py` 时去掉了 `src/adapters/dsh/adapter.py` 里 `from policy.checkers import UNPROVEN_CHANGED_TEXT, UNPROVEN_DYNAMIC_IMPORT` 那行。这两个名字**原先是被暴露过的模块属性**（`tests/contract/test_dsh_adapter.py:22-23` 就是从这里 import），于是 T3 的全量 `pytest` 在**收集期**就 `ImportError` 了——不是断言失败，是整个测试文件收不进来 | `src/adapters/dsh/adapter.py`；由 T3 在跑全量时撞到并如实上报 | **已修（T1）**：保留再导出并加进 `__all__`，并自查 `__all__` 里每个名字都能 import。教训：**`__all__`/模块属性是契约面**，重构时"删掉一个没人用的 import"可能就是在删接口——判断依据不是"本文件里还有人用吗"，而是"外面有没有人 import 过" |
| R2 | **"显式 dependencies 优先"的信任边界**：这条向后兼容分支**只能**用于 Adapter 内部注入。外部规范事件的 payload 白名单是 `{"path", "params", "text", "cwd"}`（`src/adapters/models.py:745-751`），`dependencies` **不在**白名单里；`tests/contract/test_agent_adapters.py:251-257` 专门把它当**伪造的内部字段**测。三条 Adapter 现在能设它，是因为它们在 `parse_canonical_event` **之后**用 `object.__setattr__` 注入 | `src/adapters/models.py`、`src/adapters/base.py` | **提前拦住**：明确要求 T1 **不得**把 `dependencies` 加进 `allowed_payload`——那等于让客户端自带依赖集，违反 AGENTS.md 约束 25/32（"客户端不能自带证据或决策"），是安全回归而不是兼容性改进。分支保留，但注释里要写明"外部事件到不了这里，白名单会先拒绝" |
| R3 | **并发跑测试会互相拆台**：4 个写者 + 1 个验收员都要跑 `pytest`，而仓库的闭环测试共用 `.tmp/` 下的固定路径（`.tmp/artifacts/`、`.tmp/phase-4-demo/`、`.tmp/phase-8-orchestration/`、`.tmp/retrieval/` …）。AGENTS.md 已经为 `ci_local.py` 记过这条（并发会跑出**假红**，实测出现过编排闭环 5/8 场景 FAIL 而单独跑全通过） | 全队 | **已处置**：本轮加了 `.tmp/runlock.py`（目录式互斥 + 45 分钟陈锁打破），**所有** pytest 调用一律走它。它是会话级工具，不进仓库（`.tmp/` 已在 .gitignore） |
| R6 | **缺口探针自己有缺口**：`tools/governance_gap_probe.py` 的 G06 只驱动 Phase 2 的 `python -m adapters.dsh.hooks`，**从不走 Phase 6**。V1 拿它对**修前快照**跑 `--phase after`，仍然 **13/13、exit 0** —— 它在 N1 还活着的那棵树上照样全绿 | `tools/governance_gap_probe.py` 的 `check_g06`（全文 grep `JsonAdapter` / `to_policy_context` **零命中**） | **已做**：在 `check_g06` 加**范围声明**（只覆盖 Phase 2 + 曾在 Phase 6 独立成立 + 不要把全绿当成"所有入口都生效"），指针**先列两个 git 跟踪的测试文件**、V1 探针只作附注并标明"构建产物可重建"（永久注释不挂在 `.tmp/` 上——`cleanup.py` 会删它）。证明：`ast_equal --baseline file --before <改动前副本>` → `AST identical: True`；同 `--root` 下新旧两份探针 → 都 exit 0 / 13/13、`逐项结论相同: True`、`facts（归一化后）相同: True`。**登记 N13**（给 G06 补 Phase 6 用例，验收判据"对修前快照必须变红"） |
| R7 | **规则作者的纪律被当成了代码保证**：`language` 声明不出来时为 `None`，依赖集是 `()`，依赖类 checker 于是 allow，而"为什么 allow"（语言未知）没有写进任何地方。今天没有洞，只是因为 43 条规则里唯一用 `forbidden_dependency` 的 ARCH-001 恰好在 scope 里声明了 `language=python` | `src/adapters/base.py` 的 language 解析 + `src/policy/checkers.py` 的 scope 匹配 | **登记 N14**（下一轮）：在**规则加载期**拒绝"用 `forbidden_dependency` 但 scope 不含 language 维度"的规则——把纪律变成会失败的检查。由 T2 在写跨路径测试时发现并如实上报 |
| R8 | **两个"看起来是绿其实是没跑/跑错"的陷阱**（都由 V1 实测发现）：(a) `-p no:cacheprovider` 会让本仓库 `pytest.ini` 的 `cache_dir` 报 "Unknown config option"，结果是 **"no tests ran"（exit 4）**——看起来像绿；(b) `ruff --output-format concise` 的 stdout 里除违规行还有一行汇总 `Found 8 errors.`，**数行数会把汇总也数进去**（实测 8 条被数成 10 条） | 全队 | **写进本记录**：判定"绿"必须看**末行统计与退出码**，不能只看"没有红色输出"；ruff 计数只认 `<path>:<line>:<col>: <CODE>` 形态的行。这两条与 R5 同源：**"检查没说话"与"检查通过了"是两件事** |
| R10 | **本机门禁的 pytest 步会偶发 `WinError 5` 假红，必须与真失败区分开**：第一次全量门禁跑出 `Text conventions` 失败（两处"文件以多个空行结尾"，已修）；修完再跑，`Text conventions` 转绿而 pytest 步出现 **1 条失败**——`tests/unit/test_api_contract.py::test_idempotency_ledger_with_zero_ttl_never_expires`，报 `PermissionError: [WinError 5] 拒绝访问` 于 `policy_api/idempotency.py:326` 的 `os.replace(...)`（写 `.tmp/tests/<uuid>/ledger.jsonl`） | `src/policy_api/idempotency.py` 的原子替换 + 本机文件沙箱 | **判定为环境问题，不是回归**，三条证据：(a) 同一条用例在**同一台机器**上此前已通过 5 次（T3/T4/V1/T2 各一次全量 + 门禁第 1 次的 pytest 步）；(b) 清掉 `.tmp/tests` 下 59 个残留目录后**第 3 次全量门禁 32 步全绿**；(c) 同一份日志里 `pytest` 自己的缓存写入也在报同类 `WinError 5`（`.tmp/.pytest_cache`，基线里就有）——说明这台机器对 `.tmp/` 的写入**间歇性被拒**，与改动无关。**教训**：门禁红了先看**错在哪一层**（`os.replace` 的 WinError 5 ≠ 断言失败），别把环境假红当成回归去改代码；反过来也一样——**清掉残留后必须重跑**，不能因为"上次是假红"就把下一次真红也当假红 |
| R9 | **"显式空 `dependencies: []` 会抑制派生"是一条刻意保留的语义边界**：T2 问能不能为它写断言；裁决是**不写**——冻结接口没说空声明的语义，为未冻结的语义造断言会把"我猜的"变成"契约"。同时确认它**不新增权力**：同一个进程内 Adapter 不设 `text` 就同样不派生；且外部规范事件根本到不了这个分支（`models.py:745-751` 的白名单先拒绝，`test_agent_adapters.py:251` 的伪造用例守着） | `src/adapters/base.py` 的"键存在即显式"分支 | **写进本记录**（文档级，不动已被 V1 验证过的代码） |
| R5 | **"为了绕 lint 而改名"改掉了运行时还在被按名查找的东西**：T4 为消 `F811`（形参遮蔽未使用的导入），把 3 个测试文件里刻意的 fixture 再导出改成了别名 `enforcement_paths as _enforcement_paths_fixture`。但 **pytest 注册 fixture 用的是导入模块里的属性名**（`_pytest/fixtures.py:2104-2113`：没有显式 `name=` 时按 `dir(holderobj)` 的名字注册），于是注册名变成别名，26 个用例在 **setup 期** `fixture 'enforcement_paths' not found` —— 别名恰好抵消了那条注释想保住的东西 | `tests/integration/test_enforcement_cli.py:24`、`tests/contract/test_approval_binding_modes.py:29`、`tests/contract/test_run_code_static_check.py:33`；由 **T3 跑全量时撞到**并给出源码级根因与算术归因（1348 + 56 + 26 = 1430 = 冻结基线） | **已修（T4）**：保留**原名** + `__all__ = ["enforcement_paths"]`（ruff 认为该名字被再导出 → F401/F811 都不再报，而模块属性名不变 → pytest 注册回原名）。**只加 `# noqa: F401` 不够**（实测仍报 F811），T3 用 `.tmp/ruff-probe/cand2.py` 实测过、Lead 复核过。教训：**任何为了绕 lint 而改掉的名字，都要先问一句"这个名字在运行时还被谁按它找"**——fixture、注册表键、反射、CLI 名、审计字段，都属于这一类 |
| R4 | **基线比上一轮记录高得多**：上一轮的验收记录写"964 passed"，本轮开工实测 **1430 passed, 1 skipped**（248s）。差额来自上一轮后半段新增的测试文件（未跟踪的那批） | — | **写进验收口径**：本轮一切"无回归"判定以 **1430** 为基线，不以 964 |
