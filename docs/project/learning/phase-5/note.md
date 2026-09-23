# Phase 5 笔记：代码验证器（Code Validators）

这一页回答三件事：**这一阶段的任务是什么**、**有哪些对象**、**对象之间是什么关系**。
想知道"实际跑起来是什么样"，看同目录的 `walkthrough.ipynb`（或 `walkthrough.py`）。

## 任务内容

Phase 0–4 解决了"规则能不能稳定判定"与"动作能不能被授权执行"，但规则判定依赖的
"这段代码依赖了什么"一直由调用方声明（`--dependencies`）。Phase 5 把这件事换成**确定性证据**：

    代码文件 → 源码身份（哈希）→ AST 事实 → 依赖图（组件 + 解析结果）
             → docstring / Lint / 类型 / 测试（内置 + 外部工具）
             → 证据（ValidationEvidence，带验证器 ID/版本、规则 ID、文件行列、工具退出码、配置哈希）
             → Policy Engine → allow / allow_with_warnings / block

四件必须成立的事：

1. **ARCH-001 完全由 AST / 依赖图证据判定**：默认不需要、也不接受调用方手写依赖；
2. **失败关闭**：关键验证器缺失 / 版本不符 / 超时 / 崩溃 / 配置错误 / 输出非法，
   以及"没有任何验证器为某个 checker 提供证据"，都要让需要它的规则以 critical 阻断；
   "解析失败"不等于"没有依赖"（语法错误、动态 import、项目内模块解析失败都阻断）；
3. **证据可重放**：相同输入两次运行得到逐字节相同的证据（不写耗时、不写绝对路径、不写临时目录）；
4. **扩展点是数据**：新增语言 = 新增 Adapter + rule pack，核心流水线里没有语言分支。

## 对象清单

| 对象 | 位置 | 职责（一句话） |
| --- | --- | --- |
| `ValidationEvidence` | `src/policy/evidence.py` | 一条证据：验证器、规则、位置、严重级别、工具事实、修复建议 |
| `DependencyFact` | 同上 | 一条"目标依赖某模块"的事实（名字、形态、解析结果、位置） |
| `ValidatorRecord` / `Blocker` | 同上 | 一次验证器运行的状态记录 / 失败关闭点（含它让哪些 checker 不可判定） |
| `EvidenceBundle` | 同上 | 一次验证的全部证据，规范化后交给引擎（排序稳定、去重保留来源） |
| checker 分派 | `src/policy/checkers.py` | 把证据变成 `Violation`：依赖类、发现类、阻断类三条路径 |
| `ValidatorSpec` / `RulePack` / `Registry` | `src/validators/models.py` | 验证器注册表的数据模型（阶段、checker、工具、超时、critical） |
| `ProjectProfile` | 同上 | 项目档案：语言识别、模块解析根、路径 → 组件映射 |
| `TestLayout` | 同上 | 生产文件 ↔ 测试文件的对应关系与测试进程上限 |
| `PythonModuleFacts` | `src/validators/python_ast.py` | 标准库 ast 的事实：import / 调用 / 定义 / 语法错误 |
| `DependencyResult` | `src/validators/depgraph.py` | 依赖事实 + 未解析项 + 图节点与边 |
| `AdapterResult` / `ToolRun` / `Probe` | `src/validators/adapters/base.py` | 外部工具的一次探测 / 运行归一结果 |
| `PipelineRequest` / `PipelineReport` | `src/validators/pipeline.py` | 一次验证的输入 / 输出（报告 + 证据包） |
| `ValidationConfig` | `src/validators/registry.py` | 三份数据文件（注册表 / 项目档案 / 测试布局）与它们的路径和摘要 |

数据（都在 `validation/` 下）：`validators.yaml`（谁能产生证据）、`project.yaml`（语言与组件）、
`test-layout.yaml`（测试对应关系与限额）、`ruff.toml` / `mypy.ini` / `pytest.ini`（工具配置）。

规则（`policies/` 下）：`architecture/ARCH-001.yaml`（依赖方向）、`coding/DOC-001.yaml`（PEP 257）、
`coding/STYLE-001.yaml` / `STYLE-002.yaml`（Ruff E501 / F401）、
`testing/TESTING-001.yaml` / `TESTING-002.yaml`（缺测试 / 相关测试失败）。

## 对象关系

    规则（数据）                      验证器注册表（数据）              项目档案（数据）
    enforcement.checker  ──────────►  checkers: [...]  ──────────►  languages / python_roots / components
        │                                   │                                  │
        │  scope 命中                        │ 阶段 + requires                  │ 组件名参与规则匹配
        ▼                                   ▼                                  ▼
   引擎匹配规则集合 ── 需要哪些 checker ──► 流水线选验证器 ── 分波执行 ──► 证据（bundle）
        │                                                                       │
        └───────────────── evaluate(rules, context, evidence=bundle) ◄──────────┘
                                    │
                                    ▼
                        allow / allow_with_warnings / block

三条判定路径（都在 `policy/checkers.py` 里，引擎不再内联任何一条规则的判定）：

- **依赖类**（`forbidden_dependency`）：证据里的依赖名命中规则声明的禁止清单 → violation（带行号）；
- **发现类**（`missing_docstring` / `style_lint` / `type_check` / `missing_tests` / `failing_tests`）：
  只认绑定到本规则的证据；严重级别来自规则，不来自证据；
- **阻断类**：验证器不可用或 checker 无人负责 → `critical` violation（保证任何配置下都阻断）。

## 边界（这一阶段明确不做）

- **不做判定**：验证器只产证据；证据不写进决策协议（协议仍是 `1.0`），它在 `--json` 的 `evidence` 段；
- **不做类型检查的默认启用**：mypy 端口与失败语义已就位，但仓库没有启用类型规则——
  本机与 CI 都没装 mypy，启用它会让所有 Python 文件在缺工具时一次性判红，这是数据决定的事；
- **不做多语言**：标准库 ast 只覆盖 Python；新增语言 = 新增 Adapter + rule pack；
- **不做真正的沙箱**：外部工具在本机进程里跑，隔离靠白名单环境变量、参数 allowlist、
  超时终止进程树与输出脱敏；文件系统 / 网络隔离属于运行时的沙箱；
- **不进 dsh Hook 的默认链路**：只提供上下文的调用路径把证据类 checker 的规则记进
  `skipped_rules` 并写明"需要验证器证据"——显式记录，不是静默放行（接进 Hook 属于 Phase 6）。
