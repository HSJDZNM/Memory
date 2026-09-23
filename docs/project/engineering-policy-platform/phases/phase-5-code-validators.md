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
| `tests/unit/test_validator_hardening.py`、`tests/integration/test_validator_hardening_cli.py` | 新增（复核第二轮 + CI 第二轮）：21 条回归用例，钉住复核与 CI 发现的每一个缺陷 |
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
| P3 | CLI 的相对路径参数（`--workspace` / `--config-root`）只按当前工作目录解析，从 `docs/project/learning/phase-5/` 启动手册时同一命令行为不同 | 统一成"先按 cwd、再按仓库根"的解析规则（`policy.check.resolve_directory`，`validators.cli` 复用） | 手册生成器从两个工作目录各跑一遍（`build_learning_notebook.py`） |

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
    python -m pytest tests/unit -q                          # 494 用例
    python -m pytest tests/contract -q                      # 112 用例
    python -m pytest tests/integration -q                   # 189 用例
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

### 一处长期漂移：决策载荷里的 policy_version（已定义并修复）

Phase 5 收尾核对阶段证据时发现：证据里的 `decision_protocol.policy_version` 写着 `phase-5`，
而任何真实决策载荷里这个字段是 `phase-1`。复现：

    git show a3b0e35:tools/phase_evidence.py | Select-String policy_version   # Phase 4 时写 phase-4
    git show a3b0e35:src/policy/models.py     | Select-String policy_version  # 载荷一直是 phase-1

也就是说，工具用"平台阶段"顶替了"协议字段值"，**从 Phase 4 起就是这样**（Phase 5 沿用了同一行）。
两种修法都摆出来比较过：

| 选项 | 改动面 | 结论 |
| --- | --- | --- |
| A：只让证据报真实值 | `tools/phase_evidence.py` 一处 + 守卫用例 | 必需：证据不许说假话 |
| B：把载荷里的值升到 `phase-5` | 模型默认值 + 4 份快照（`POLICY_UPDATE_SNAPSHOTS=1`）+ 3 处断言 | **不采纳**：那会给消费方引入第二条兼容轴，并把"显式更新快照"降级成每阶段的例行公事 |

最终做法是"A 加把 B 的问题定义清楚"：

1. `src/policy/models.py` 新增 `POLICY_VERSION` 常量（值仍是 `phase-1`，**快照不变**）：
   `schema_version` 是唯一兼容轴（字段增删或语义变化时递增），`POLICY_VERSION` 是协议**世代名**，
   只与 `schema_version` 同进同退、不跟随平台阶段；平台阶段看阶段证据的 `phase` 与 `implementation_version`；
2. 载荷、快照与阶段证据都从这一个常量取值，工具不再自己算（`tools/phase_evidence.py` 改为读模型）；
3. 契约守卫：`test_policy_version_is_the_protocol_generation_not_the_platform_phase`（常量 = 模型默认值 = 四份快照）
   与 `test_phase_evidence_reports_the_payload_value_verbatim`（证据报的值 = 载荷的值）；
4. 文档：总体架构新增"决策载荷的两个版本字段"（含义与何时变），AGENTS 核心约束 7 记下这条规则，
   学习手册里那句硬编码的 `当前阶段: phase-1` 改成读真实常量并解释两个字段的分工。

为什么不让它跟着阶段走：Phase 5 确实改变了 violation 的来源集合（新增 `kind="validator"` 的 critical 阻断），
但那是**值的集合**变化，不是协议形状变化——载荷形状仍是 1.0，消费方按 `violations[].evidence.kind` 处理即可；
需要"这一代引擎是谁"的场景（审计、阶段证据、复现）已经有 `rule_set_hash` 与 `implementation_version`，
比一个每阶段都要决策一次的常量精确得多。真正的协议变更点（Phase 7 的版本化 API）会让两个字段一起动。

### 独立复核与修复（同一阶段内的第二轮）

Phase 5 收尾时由**两个独立子会话**做了一次对抗复核（只看阶段计划书的上半部分，实施记录视为不可信；
只跑代码、不改被跟踪文件）。完整记录见
[Post-Phase-5 复核记录](../reviews/post-phase-5-review.md)。结论与处置：

**复核确认成立的**：决策协议未被改动（四份快照与代码产出逐字节一致）、checker 词表三层一致、
加载不变量全部成立、六类工具失败全部失败关闭（把注册表改成 `critical: false` 仍被二道防线拦住）、
超时真的终止整棵进程树、证据逐字节可重放、只提供上下文的调用路径没有静默放行。

**复核发现并已修复的**（每条都带回归用例，详见复核记录 §4）：

| 级别 | 问题 | 修复 |
| --- | --- | --- |
| 重要 | `from shop import order_repository` 不产生依赖边 → ARCH-001 漏判（"Controller 直接依赖 Repository"最常见的写法之一） | from-import 的每个名字再探一次 `<module>.<name>`，仅在本项目内解析成功时补边 |
| 重要 | `from importlib import import_module as im; im(name)` 绕过动态 import 门禁 | AST 事实新增 `bindings`（含别名），动态 import 按绑定识别；常量参数还能解析出真实模块边 |
| 重要 | 工作区只要有一个测试文件，`suite` 升级就永远命中 → `TESTING-001` 等价死规则 | 把"跑什么"与"有没有对应测试"分开：升级不再冒充"带了测试" |
| 重要 | 注册表声明 `max_evidence: 200` 却零消费者（500 条诊断全进证据） | 流水线按上限截断，并把截断条数写进验证器记录与报告 |
| 重要 | 文档命令 `retrieval.cli context --decision decision.json` 引用的文件不存在，且读不到时裸 traceback + 退出码 1 | 读不到 / 非 JSON 一律 config error（退出码 2）；README 与 phase-3 文档改成真实可跑的示例 |
| 次要 | `--language go` → 全部规则 scope 落空 → allow；未实现验证器 id 只在运行期报错；变更集越界到选择阶段才崩；非 UTF-8 目标分类不一致；node id 上限静默截断；工具输出的 `filename` 可伪造证据位置；失败原因为空；`{python}` 字面量进证据；`changed_only` 无读取点 | 逐条修复：语言无 rule pack 即配置错误、加载期拒绝幽灵验证器、进入流水线前校验变更集、分类统一、截断可见、位置只接受真实文件、原因带输出摘要、工具名解析、开关真正生效 |
| 文档 | 用例数过期、`--layer` 推断未标明、Ruff 前提缺失、手册索引缺 Phase 5、"向量未跑赢"措辞 | 逐条修正 |

复核同时把三条边界写清楚而不是"修成看起来有保护"：`--dependencies` 是显式旁路（历史契约，
证据来源记成 `cli.explicit@1.0`）、只提供上下文的调用路径按既有契约判 ARCH-001、
验证器临时目录跟随 `--config-root`。

### CI 第二轮：只有 Linux 能看见的漏判（CI-F1）

推送复核修复后 CI 的测试步变红，失败用例是
`tests/security/test_validator_adversarial.py::test_decisions_do_not_leak_absolute_paths`：
新增的 `tool_label` 把夹具工具声明的**绝对路径**原样写进了证据的 `tool` 字段
（`["{python}", "<绝对路径>/fake_tool.py", ...]` 这种声明形态），违反 AGENTS 19。

它同时暴露了**门禁自身的漏洞**：那条断言写的是
`str(REPO_ROOT).replace(chr(92), "/") not in payload`，而 Windows 上载荷里的路径是
`C:\\Users\\...` 形态——被 JSON 转义（`\\`）与分隔符两重差异挡住，断言**恒真**，
所以本机与两轮复核都是绿的。修复顺序刻意做成"先让本机红、再让本机绿"：

1. 断言改为同时比"JSON 转义后的形态"与"正斜杠形态" → 本机立刻复现 CI 的红；
2. `tool_label` 只保留最后一段并归一两种分隔符 → 本机转绿，并补
   `test_tool_label_never_returns_a_path` 钉住"证据里的工具名不带目录"。

Ruff 0.16.8（CI 上装的是最新版，本机是 0.14.13）无法在本机复现，已单独用 0.16 的 JSON
字段形态（`filename` / `location` / `fix.edits[].location` 为 `null`）验证适配器：
正常映射或回退到目标文件，不产生绝对路径。

### 本机门禁里的一条已知噪音

在**被沙箱化的会话**里跑 `python tools/ci_local.py --full` 时，`Real dsh sandbox loop` 这一步会失败：
嵌套 dsh 会话在到达 Hook 之前就被拒绝，审计文件为空，脚本据此写出
`diagnosis: "Hook 从未被调用"`（Phase 2/4 已记录这条环境边界）。它不是策略判定结果，
也不是本阶段的回归——CI 上没有 dsh 时该脚本输出 `skipped` 并退出 0。Phase 5 自己的闭环
（`python tools/validator_loop.py`）不依赖 dsh，在本机与 CI 都稳定通过。
