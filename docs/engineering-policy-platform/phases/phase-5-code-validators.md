# Phase 5：代码验证器

## 目标

用 AST、依赖图、现有 Linter、类型检查和测试产生确定性证据，让 Policy Engine 不依赖 LLM 猜测代码是否合规。

## Validator 契约

```text
validate(target, context, config) → ValidationEvidence[]
```

每条 evidence 至少包含 validator ID/版本、规则 ID、文件、行列、消息、严重级别、工具退出码和可选修复建议。Validator 只产生证据，最终 allow/block 仍由 Policy Engine 决定。

## 渐进开发步骤

### 1. Python AST 最小实现

首个目标仍是 `ARCH-001`。对 Python 可先使用标准库 `ast` 提取 import 与调用依赖，避免在单语言原型阶段过早引入 tree-sitter。需要跨语言或标准库 AST 无法覆盖时，再加入 tree-sitter Adapter。

### 2. 依赖图

把文件、模块和层作为节点，把 import 或解析后的依赖作为边。依赖图必须区分无法解析、外部包和项目内部模块，不能把“解析失败”当作“没有依赖”。

### 3. 外部工具 Adapter

复用 Ruff、类型检查器和 pytest，不重复实现它们。每个 Adapter 固定：

- 工具版本和配置文件；
- 参数 allowlist；
- 工作目录与超时；
- stdout/stderr 大小上限；
- 原始输出到统一 evidence 的映射；
- 工具缺失、崩溃和配置错误的区别。

### 4. 多语言扩展点

Python 规则可参考仓库 PEP 8/257；.NET API 规则可参考本地 .NET Design Guidelines。语言专项规则进入独立 rule pack，核心 Pipeline 不包含语言分支。

### 5. Test Validator

根据 git diff 找到生产文件与测试文件，运行最小相关测试；相关性不足时升级到更大测试集。测试进程必须隔离、限时，并限制网络和写入范围。

### 6. Pipeline 聚合

```text
Code → AST → Dependency → Lint → Type → Tests → Evidence → Policy
```

支持按规则选择 Validator，并明确哪些可并行。一个关键 Validator 缺失或超时不能被其他 PASS 抵消。

## 测试步骤

### Golden fixtures

为每条规则提供最小 good/bad 源文件，断言规则 ID、文件和行列。首批至少包含：

- Controller → Repository（bad）；
- Controller → Service（good）；
- 动态 import 或别名 import；
- 语法错误；
- 无法解析的项目依赖；
- PEP 8 可由 Ruff 检出的风格错误；
- 缺失或错误的 docstring（如果项目采纳 PEP 257）；
- 生产变更缺少对应测试。

### Adapter 失效测试

- 工具不存在；
- 工具版本与锁定版本不符；
- 超时、崩溃、非零退出码；
- 输出为空、乱码或超长；
- 工作目录错误；
- 恶意文件名或输出尝试注入日志。

### 结果归一化

- Windows/POSIX 路径映射一致；
- 同一问题的排序稳定；
- 外部工具版本差异不会静默改变协议；
- 重复 evidence 去重但保留来源；
- 多 Validator 同时失败时最高严重级别正确。

### 测试有效性

每个 good/bad fixture 必须证明：移除违规代码后 bad 测试转为通过，重新引入违规后失败。对于行为测试，至少做一次最小变异或手工破坏，确认测试真的能抓到错误。

### 性能与隔离

- 固定小、中、大 fixture 记录耗时基线；
- 超时能终止子进程及其后代；
- 测试不能访问真实密钥或生产网络；
- 并行 Validator 不互相覆盖临时文件；
- 资源限制触发时产生明确 evidence。

## 观察点

观察 LLM 解释、Policy 决策和 Validator 证据的边界：解释可以变化，规则证据和最终决定必须稳定、可重放。

## 退出条件

- `ARCH-001` 完全由 AST/依赖证据判定；
- 外部工具版本、配置与错误分类可追溯；
- 关键 Validator 超时和缺失均失败关闭；
- good/bad/边界/失效 fixture 完整；
- 新增语言只需新增 Adapter 和 rule pack，不修改核心协议。

通过后进入 [Phase 6](phase-6-multi-agent-adapters.md)。

---

## 实施记录（2026-09，Phase 5 已完成）

本节记录实际落地的接口、数据结构、命令与偏差，避免文档与代码漂移。原始计划保留在上文。

### 前置调查：先把"证据从哪来"这件事钉死

| 调查项 | 结论（本机实测） |
| --- | --- |
| 单语言原型用什么解析 | 标准库 `ast` 足够：import（含别名与相对导入）、动态 import、调用链、定义与 docstring 一次解析全部拿到；tree-sitter 只会在出现多语言需求时再引入 |
| 外部工具怎么接 | Ruff / mypy / pytest 都是**外部工具**而不是本项目的 Python 依赖：放进 `requirements.lock` 会让"规则数据"和"工具安装"耦合，因此改为"探针发现 + 版本区间声明 + 缺失即失败关闭" |
| Ruff 在本机存在吗 | 有（0.14.13，PATH 上）——所以 lint 路径在本机是真实跑通的；CI 里用 `uv pip install "ruff>=0.6,<1"` 装一份 |
| mypy / pyright 有吗 | 都没有。因此 `tool.mypy` 的适配器与失败语义已实现并测试，但**没有启用类型规则**：启用它会让所有 Python 文件在缺工具时一次性判红，这是数据决定的事 |
| 超时能不能杀掉后代进程 | Windows 上 `taskkill /F /T` 在受限环境里直接 Access denied（实测），改用 `ctypes` 调 job object（`TerminateJobObject` + `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`）后整棵进程树确实被终止；POSIX 走 `start_new_session` + `killpg` |
| 判定放在哪 | 证据是端口、判定是核心：新增 `policy.evidence`（证据协议）与 `policy.checkers`（checker 分派），`policy.engine.evaluate` 增加可选的 `evidence` 入参而**决策协议仍是 1.0** |
| dsh 侧怎么办 | Phase 2 的 Hook 仍然只提供上下文：证据类 checker 的规则会进入 `skipped_rules` 并写明"需要验证器证据"（显式记录，不是静默放行）；把验证器接进 Hook 属于 Phase 6 |

### 实际新增与变化

| 位置 | 内容 |
| --- | --- |
| `src/policy/evidence.py` | 新增：证据协议（`ValidationEvidence` / `DependencyFact` / `ValidatorRecord` / `Blocker` / `EvidenceBundle` / `SourceDigest` / `ToolInvocation`），版本 `1.0`，规范化排序与去重 |
| `src/policy/checkers.py` | 新增：checker 分派（`CONTEXT_CHECKERS` = forbidden_dependency；`EVIDENCE_CHECKERS` = missing_docstring / style_lint / type_check / missing_tests / failing_tests）+ 阻断类 violation 的构造 |
| `src/policy/models.py` | 变化：`Rule.rule` 从单一规则体变为**按 checker 区分的规则体 union**（forbidden_dependency / missing_docstring / style_lint / type_check / missing_tests / failing_tests），并加入"规则体必须与 checker 一致、未知 checker 直接报错"的校验；错误位置去掉 union 成员类名 |
| `src/policy/engine.py` | 变化：`evaluate(rules, context, *, evidence=None)`；判定改为按 checker 查表；证据类 checker 在没有证据的调用路径上进 `skipped_rules` 并写明原因；新增 `matching_rules` 供流水线选验证器 |
| `src/policy/check.py` | 变化：默认走验证器流水线（目标路径先按 `--workspace` 解析、再按仓库根）；新增 `--workspace` / `--config-root` / `--changed` / `--validators` / `--keep-temp`；`--json` 增加 `evidence` 段；`--dependencies` 语义变成"显式声明依赖、覆盖 AST 证据" |
| `src/validators/models.py`、`registry.py` | 新增：注册表 / 项目档案 / 测试布局的数据模型与加载器（原子、拒绝未知字段、拒绝重复 ID、`requires` 必须更早执行、工具配置必须存在、checker 必须有验证器负责） |
| `src/validators/source.py` | 新增：源码身份（哈希、语言、规模），拒绝越界路径、符号链接逃逸、超大文件、非 UTF-8、NUL |
| `src/validators/python_ast.py` | 新增：标准库 ast 事实（import / 别名 / 相对导入 / 动态 import 的常量性 / 调用链 / 定义与 docstring / 语法错误） |
| `src/validators/depgraph.py` | 新增：模块索引与依赖解析（internal / stdlib / external / unresolved），组件归类，节点与边，"解析失败不等于没有依赖" |
| `src/validators/docstrings.py` | 新增：PEP 257 证据（模块 / 类 / 函数 / 方法，是否含私有对象由规则数据决定） |
| `src/validators/selection.py` | 新增：测试选择（related → package → suite）与"改了生产代码却没有测试"的识别 |
| `src/validators/adapters/base.py` | 新增：外部工具公共机制（探针、版本区间、argv allowlist、白名单环境、超时终止进程树、输出脱敏限量、六类失败分类） |
| `src/validators/adapters/ruff.py`、`mypy.py`、`pytest_runner.py` | 新增：三个外部工具适配器（诊断码归属由规则数据决定；没有规则归属的诊断只计数） |
| `src/validators/pipeline.py` | 新增：按规则选验证器 → 按依赖分波执行（同波并行）→ 聚合证据与阻断点；显式依赖时让位给 `cli.explicit`；临时目录 `.tmp/validators/<run>/<validator>` 用完即删 |
| `src/validators/cli.py、__main__.py` | 新增：`registry` / `probe` / `check`（只产证据）/ `pipeline`（证据 + 判定）四条子命令 |
| `validation/validators.yaml`、`project.yaml`、`test-layout.yaml`、`ruff.toml`、`mypy.ini`、`pytest.ini` | 新增：验证器注册表、项目档案（语言 / python_roots / 组件）、测试布局、三个外部工具的固定配置 |
| `policies/coding/DOC-001.yaml`、`STYLE-001.yaml`、`STYLE-002.yaml`、`policies/testing/TESTING-001.yaml`、`TESTING-002.yaml` | 新增：语言专项与测试规则包（PEP 257 / Ruff E501 / Ruff F401 / 缺测试 / 相关测试失败） |
| `tests/fixtures/validators/` | 新增：夹具项目（正例、反例、动态 import、无法解析依赖、语法错误、风格问题、缺 docstring、测试文件）+ 假工具（失效与边界行为）+ README |
| `tests/unit/test_validator_{registry,facts,checkers,adapters}.py` | 新增：21 + 26 + 20 + 24 个用例（注册表不变量、AST 与依赖图、docstring 与测试选择、引擎 × 证据、适配器失效分类） |
| `tests/contract/test_validator_protocol.py` | 新增：20 个用例（证据协议版本、checker 词表跨层一致、注册表 ↔ 实现对齐、核心层不导入 Adapter、载荷无绝对路径与耗时、两次运行逐字节一致） |
| `tests/integration/test_validator_{pipeline,cli}.py` | 新增：22 + 11 个用例（真实夹具项目、真实 Ruff、失败关闭、测试选择与失败、CLI 退出码与 JSON 契约） |
| `tests/security/test_validator_adversarial.py` | 新增：12 个对抗用例（路径逃逸与符号链接、选项注入、超大源码、工具输出注入与凭据、未实现验证器、临时目录隔离） |
| `tools/validator_loop.py` | 新增：验证器闭环（10 个场景，结论写给阶段证据） |
| `tools/phase_evidence.py` | 变化：`CURRENT_PHASE=5`，新增 `validators` 段（注册表 / 项目档案 / 配置摘要 / checker 归属 / 规则覆盖 / 闭环结论） |
| `.github/workflows/phase-5.yml` | 替换 `phase-4.yml`：保留 Phase 0–4 的重放，追加 Ruff 安装、AST 证据重放、注册表与实现对齐、工具探针、失败关闭重放、验证器闭环 |

### 决策链的形状（一次验证的六个位置）

    (1) 规则集：哪条规则的 checker 由谁提供证据（规则 × 注册表 × 项目档案）
        → scope 命中后才需要证据；未知 checker 或没有人负责的 checker 直接失败关闭
    (2) 源码身份：内容 sha256 + 语言 + 规模（读不到 / 超大 / 非 UTF-8 / 含 NUL → 阻断）
    (3) 事实层：AST（import / 调用 / 定义 / 语法错误）与依赖图（解析结果 + 组件名 + 未解析项）
        → 语法错误、动态 import 目标不是常量、项目内模块解析失败 → 阻断
    (4) 外部工具：探针（可用性 + 版本区间）→ 按声明模板执行 → 输出脱敏限量 → 诊断映射到规则
        → 缺失 / 版本不符 / 超时 / 崩溃 / 配置错误 / 输出非法 → 阻断
    (5) 证据聚合：ValidationEvidence / DependencyFact / ValidatorRecord / Blocker
        → 排序稳定、去重保留来源、不含绝对路径与耗时
    (6) 判定：policy.engine.evaluate(rules, context, evidence=bundle)
        → allow / allow_with_warnings / block（critical 阻断的严重级别由证据缺失决定，不由规则配置决定）

### 与原始计划的偏差（都需要知道）

1. **外部工具不进 `requirements.lock`。** 计划书把 Ruff / mypy / pytest 列为 Phase 5 的技术，
   这里把它们实现为**外部工具**：版本区间与配置文件写在 `validation/validators.yaml`（数据），
   探针负责发现，缺失即失败关闭。理由：把 linter 变成核心依赖会让"规则数据"与"工具安装"耦合，
   而锁文件只能锁 Python 包；CI 另外装一份 Ruff（`uv pip install "ruff>=0.6,<1"`）。
2. **没有启用类型检查规则。** mypy 适配器、失败语义与假工具测试都已就位，但 `policies/` 里没有
   `type_check` 规则：本机与 CI 都没有 mypy，启用它会让所有 Python 文件在缺工具时一次性判红。
   `validation/validators.yaml` 仍然声明了 `tool.mypy`（端口与版本区间可见、`probe` 会如实报 unavailable）。
3. **调用链不产生依赖事实。** `self._repository.save()` 这种实例字段需要类型推断，本阶段不做：
   调用只在根名字能静态绑定到某条 import 时进入依赖图的边（报告用），判定只依据 import 事实。
   模块级 import 总是存在的，所以"Controller 直接依赖 Repository"不会漏判。
4. **`--dependencies` 保留但语义收窄。** 它现在表示"显式声明依赖、覆盖 AST 证据"，证据里记成
   `cli.explicit@1.0`，并且让位给它的依赖类验证器不再参与；文档里的历史示例仍然可重放。
5. **未知 checker 从引擎阶段前移到加载阶段。** 规则体是按 checker 区分的 union，未知 checker 与
   "规则体对不上 checker"都在加载时就报错（更早失败）；引擎里仍保留第二道防线（`SUPPORTED_CHECKERS`），
   并有用 `model_construct` 绕过模型构造的回归用例。
6. **只提供上下文的调用路径不改语义，但记录更明确。** dsh Hook 仍然只提供上下文；证据类 checker 的规则
   进入 `skipped_rules` 并写明"需要验证器证据"，ARCH-001 这类上下文类 checker 照旧判定。
   把验证器接进 Hook（对编辑后的内容做 AST 解析）属于 Phase 6 的适配器一致性工作。
7. **新增语言只加数据与 Adapter。** `rule_packs` 按语言分组、`project.yaml` 声明语言识别与解析根；
   核心流水线里没有 `if language == "python"`，未知语言在选择验证器时就失败关闭。
8. **证据不进决策协议。** 决策协议仍是 `1.0`（`tests/fixtures/decisions/` 未变），证据在 CLI 的
   `evidence` 段与 `validators.cli` 里；这样"决策可重放"与"证据可追溯"两件事各自演进。

### 失败关闭是怎么实现的

1. **规则需要的 checker 没有验证器** → 流水线给阻断点（`not_selected`）→ critical 阻断；
2. **验证器没跑成**（缺失 / 版本不符 / 超时 / 崩溃 / 配置错误 / 输出非法）→ 阻断，
   并且它的下游验证器不再执行（避免同一根因产出多条阻断点）；
3. **源码读不到 / 超大 / 非 UTF-8 / 含 NUL / 路径越界 / 符号链接逃逸** → 阻断；
4. **语法错误** → 阻断（解析不了的文件不能被判定为"没有依赖问题"）；
5. **动态 import 目标不是常量、项目内模块解析失败、相对导入无法展开** → 阻断；
6. **测试验证器缺少变更集** → 阻断（"没有变更集"不是"没有改动"）；
7. **工具输出非法**（非 UTF-8 / 空 JSON / 超大）→ 阻断；工具输出里的指令性文本、
   绝对路径与凭据只作数据，绝不改变规则集或造出新规则。

### 一处环境观察（与本阶段实现无关，但会影响证据解读）

Windows 上 `taskkill /F /T` 在受限环境里返回 Access denied，因此"超时终止整棵进程树"改由
job object（`ctypes` + `TerminateJobObject`）实现。`tests/unit/test_validator_adapters.py` 里的
超时用例让假工具同时启动一个心跳子进程，终止后核对心跳文件不再增长——这条用例证明的是
"后代进程也被终止"，而不是"主进程退出了"。

### 三处由实现过程暴露并已修复的问题

| # | 问题 | 修复 | 回归用例 |
| --- | --- | --- | --- |
| P1 | `run_tool` 在非 OK 状态返回了内部的 `_ProcessResult`，适配器调用 `payload()` 直接 AttributeError，表现为"验证器崩溃 → 失败关闭" | 统一为 `ToolRun`（`_run_process` 与 `run_tool` 同一返回类型） | 对抗测试里的 garbage / crash 场景（状态必须是 output_invalid / crashed，而不是 failed） |
| P2 | 前置验证器失败时，下游验证器各自再报一次 blocker，同一个根因产出四条阻断点 | 前置未成功时下游记 `not_selected` 并写明原因；阻断点只在根因处产生，checker 覆盖仍然传递 | `test_oversized_source_is_fail_closed`（只应有一条根因阻断点） |
| P3 | CLI 的相对路径参数（`--workspace` / `--config-root`）只按当前工作目录解析，从 `docs/learning/phase-5/` 启动手册时同一命令行为不同 | 统一成"先按 cwd、再按仓库根"的解析规则（`policy.check.resolve_directory`，`validators.cli` 复用） | 手册生成器从两个工作目录各跑一遍（`build_learning_notebook.py`） |

### 落地命令

    python -m validators.cli registry                      # 验证器注册表事实（JSON）
    python -m validators.cli registry --show tool.ruff      # 单个验证器的声明
    python -m validators.cli probe                          # 外部工具可用性与版本
    python -m validators.cli check examples/bad_controller.py --layer controller   # 只产证据
    python -m validators.cli pipeline examples/bad_controller.py --layer controller # 证据 + 判定
    python -m policy.check examples/bad_controller.py --layer controller  # 默认走验证器流水线
    python -m policy.check examples/good_controller.py --layer controller
    python -m policy.check <file> --operation edit --changed <file> --workspace <project>  # 测试验证器
    python tools/validator_loop.py                          # 验证器闭环（结论进阶段证据）
    python -m pytest tests/unit -q                          # 482 用例
    python -m pytest tests/contract -q                      # 110 用例
    python -m pytest tests/integration -q                   # 180 用例
    python -m pytest tests/security -q                      # 34 用例
    python tools/phase_evidence.py                          # .tmp/artifacts/phase-5-evidence.json

### 验收证据

`python tools/phase_evidence.py` 生成的 `.tmp/artifacts/phase-5-evidence.json` 记录：
实现版本、规则集哈希、决策协议版本、Agent 适配器契约事实、检索与受控执行事实、
**验证器事实**（注册表 / 项目档案 / 测试布局的路径与 sha256 摘要、阶段顺序、rule pack、
checker → 验证器归属、每个验证器的阶段 / critical / 工具版本区间 / 配置、每条规则由谁提供证据、
组件清单、测试层级）、**验证器闭环结论**（10 个场景的通过情况与关键事实）、
每个套件的命令 / 用例数 / 失败数、性能基线、JUnit 报告路径与时间戳。
证据里不含任何被验证文件的内容、工具输出原文或凭据。

### 本机门禁里的一条已知噪音

在**被沙箱化的会话**里跑 `python tools/ci_local.py --full` 时，`Real dsh sandbox loop` 这一步会失败：
嵌套 dsh 会话在到达 Hook 之前就被拒绝，审计文件为空，脚本据此写出
`diagnosis: "Hook 从未被调用"`（Phase 2/4 已记录这条环境边界）。它不是策略判定结果，
也不是本阶段的回归——CI 上没有 dsh 时该脚本输出 `skipped` 并退出 0。Phase 5 自己的闭环
（`python tools/validator_loop.py`）不依赖 dsh，在本机与 CI 都稳定通过。
