# AGENTS.md

面向 AI 编码代理的仓库约定。人类贡献者同样可参考。

## 仓库现状

仓库已绑定 Python 技术栈（见下文），并完成 Engineering Policy Platform 的 **Phase 0 / Phase 1 / Phase 2 / Phase 3 / Phase 4 / Phase 5**：

- 可运行：根 `README.md` 中的安装、测试、CLI、Hook 自检、沙箱闭环、性能基线、检索索引与评测命令均已实际验证；
- 有规则目录 `policies/`、核心源码 `src/policy/`（models / context / scope / engine / loader / check）、
  dsh 适配器 `src/adapters/dsh/`（adapter / hooks / 进程内转发插件）、
  检索层 `src/retrieval/`、语料清单 `knowledge/corpus.yaml`、
  受控执行层 `src/enforcement/`、工具注册表 `registry/`、
  测试 `tests/{unit,contract,integration,security}` 与 CI `.github/workflows/phase-5.yml`；
- Phase 1 的决策协议为 `SCHEMA_VERSION = "1.0"`，快照在 `tests/fixtures/decisions/`；
- Phase 2 的 Hook 契约、脱敏事件 fixture 与失败关闭设计分别在 `src/adapters/dsh/README.md`、
  `tests/fixtures/agent_events/dsh/` 与 `docs/engineering-policy-platform/phases/phase-2-dsh-adapter.md` 的实施记录里；
- Phase 3 的摄取清单 `knowledge/corpus.yaml`、检索层 `src/retrieval/`（chunker / corpus / store / indexer /
  query / retriever / vector / context / cli）、固定评测集 `tests/fixtures/retrieval_eval/queries.yaml`、
  基线脚本 `tools/retrieval_eval.py` 与实施记录见 `docs/engineering-policy-platform/phases/phase-3-retrieval.md`；
  索引库是构建产物，落在 `.tmp/retrieval/`，可随时重建；
- Phase 4 的受控执行层 `src/enforcement/`（models / registry / action / approvals / audit / ledger /
  precheck / executor / drivers / postcheck / trace / cli）、数据化工具注册表
  `registry/tool-registry.yaml` 与已审核哈希 `registry/tool-registry.approved.json`、
  dsh 侧桥接 `src/adapters/dsh/enforcement.py`、受控执行闭环 `tools/enforcement_loop.py`；
  实施记录见 `docs/engineering-policy-platform/phases/phase-4-tool-enforcement.md`；
- Phase 5 的验证器层 `src/validators/`（python_ast / depgraph / docstrings / selection / adapters /
  pipeline / cli）、证据协议 `src/policy/evidence.py` 与 checker 分派 `src/policy/checkers.py`、
  数据化的验证器注册表与项目档案 `validation/`（validators / project / test-layout / ruff.toml / mypy.ini / pytest.ini）、
  语言专项规则包 `policies/coding/` 与 `policies/testing/`、夹具项目与假工具
  `tests/fixtures/validators/`、验证器闭环 `tools/validator_loop.py`；
  实施记录见 `docs/engineering-policy-platform/phases/phase-5-code-validators.md`；
- 下一阶段计划见 `docs/engineering-policy-platform/phases/`（下一步是 Phase 6 Multi-Agent Adapters）。

**改动前先读 `README.md` 与实际的 `git ls-files`，不要假设未登记的目录或框架存在。**

## 工作方式

1. **先勘察再改动**：列出目录、读取相关文件，确认事实后再写代码。
2. **保持改动聚焦**：一个提交只做一件事，不顺手重构无关代码。
3. **不要提交密钥**：`.env`、`*.key`、`*.pem`、`secrets/` 已在 `.gitignore` 中忽略。若确实需要示例配置，提交 `.env.example` 且只放占位值。
4. **不要绕过忽略规则**：禁止使用 `git add -f` 强加被忽略的文件。
5. **推送前跑本机门禁**：`python tools/ci_local.py`（按改动范围自动选检查），装了钩子后
   `git push` 会自己跑 `--hook` 并在失败时阻断。**GitHub 侧故意不启用规则集/分支保护**：
   单人仓库里它的边际价值低于"把检查前移到本机"，而一旦启用就会禁止直接推 main。
   这条决定与理由记在这里，不留成"看起来有保护"的中间态。

## 文本文件规范

- 编码 UTF-8，换行 LF（`.gitattributes` 已强制 `eol=lf`，勿手动改回 CRLF）。
- 文件以单个换行符结尾，不留行尾空白。
- 缩进遵循 `.editorconfig`：默认 2 空格，Python 用 4 空格，Makefile 用 Tab。

## 提交信息

采用 Conventional Commits 格式：

```
<type>(<scope>): <subject>
```

`type` 取 `feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `perf` / `build` / `ci`。
主题行祈使语气、不超过 72 字符。破坏性变更在正文写明 `BREAKING CHANGE:`。

示例：`chore: initialize repository`

## 已选定的技术栈（Phase 0 起）

| 项 | 选择 | 位置 |
| --- | --- | --- |
| 语言 | Python ≥ 3.11 | `src/policy/`（src 布局） |
| 依赖清单 | pydantic 2、PyYAML 6；dev: pytest 8+ | `pyproject.toml` |
| 依赖锁定 | `requirements.in`（声明）+ `requirements.lock`（固定直接依赖版本，CI 从它安装）；仓库不提交 `uv.lock` | 仓库根目录 |
| 测试 | pytest：`tests/unit`、`tests/contract`、`tests/integration`、`tests/security` | `pytest.ini`、`tests/conftest.py` |
| 检索 | SQLite FTS5（标准库 sqlite3；向量检索是可替换端口，本阶段未采纳） | `src/retrieval/`、`knowledge/corpus.yaml` |
| CI | GitHub Actions | `.github/workflows/phase-5.yml`（含 Phase 0–4 的重放用例、dsh 接线自检、检索基线、注册表审核、受控执行闭环、AST 证据重放、验证器注册表/探针/闭环） |
| 受控执行 | 标准库 + pydantic；注册表是 YAML 数据，台账与审计链是追加写 JSONL | `src/enforcement/`、`registry/` |
| 代码验证器 | 标准库 `ast` + 外部工具探针（Ruff / mypy / pytest 不进核心依赖） | `src/validators/`、`validation/` |
| 脚本 | 锁文件生成、阶段证据、性能基线、检索评测、dsh 沙箱闭环、受控执行闭环、notebook 生成与校验、临时文件清理 | `tools/*.py`（见 `tools/README.md`） |

安装、测试、运行命令以根 `README.md` 为准，且必须保持可执行。

### 核心层约束（不要破坏）

1. `src/policy/` 只能依赖标准库、pydantic、PyYAML；禁止导入 Agent SDK、Web 框架、向量库或工作流框架；
2. 规则与语料都是数据：新增规则写进 `policies/<domain>/<ID>.yaml`，新增检索语料改
   `knowledge/corpus.yaml`（数据集、许可、tier、可见性、预算），不要在代码里硬编码判断或路径；
3. 未知字段、未知枚举、未知 scope 维度、未知操作、未知 checker、未知协议版本一律报错，
   不得静默忽略或默认放行；
4. 规则集加载是原子的：任一文件失败都不能替换现有规则集；
5. 相同输入必须得到相同结论：violation 按 `rule_id` 稳定排序，`matched_rules`/`skipped_rules` 有序，
   `RuleSet.identity` 与加载顺序无关；
6. 上下文只接受显式字段：不得根据文件名、目录或用户消息推断主体、权限或审批状态；
7. 决策协议带 `schema_version`，消费方看不懂必须拒绝；`tests/fixtures/decisions/` 的协议快照
   只能显式更新（`POLICY_UPDATE_SNAPSHOTS=1`），不能在断言里放宽；
8. Adapter 只做协议转换：不导入 Agent SDK 类型、不猜 layer/language/principal，
   声明不出来就失败关闭；未知事件、未知工具、缺失路径一律拒绝；
   **只读工具降级的只是授权链路，不是范围校验**：注册表声明了 `path_scope: workspace`，
   目标必须归一化后落在受控项目内（范围等于项目根记为 `.`），越界或证明不了就拒绝；
   工具表是白名单，升级 Agent 版本必须先更新工具表并补契约测试；
9. 进入下一阶段前必须更新本文件的依赖与命令，并运行 `tools/phase_evidence.py` 生成证据；
10. 外部命令 Hook 的阻断语义由 Agent 侧决定：`exit 0` 放行、`exit 2` 阻断；
    "超时 / 崩溃 / 配置读不到"在 dsh 侧等于放行，因此失败关闭必须由 Hook 自己保证
    （内部预算小于 Agent 侧超时 + 异常全部转成退出码 2 + 运行期接线自检）。
    改动退出码语义前先读 `src/adapters/dsh/README.md`；
11. 检索层同样是失败关闭：原始查询文本永不拼进 SQL / FTS 表达式，先规范化成受控词项；
    权限只来自显式 `AccessScope`（查询文本不能扩权），返回项必须带来源路径、URL、许可与文本哈希；
    无结果 / 无权限 / 检索不可用是三个不同的显式状态，检索不可用时只输出 `knowledge_unavailable`，
    绝不回退到"模型记忆里的规范"；相似度分数只用于内部排序，不作为授权信号；
12. 检索语料的哈希漂移不许静默：镜像 manifest 的 sha256 与本地文件不一致时写进 document 行、
    run 报告，并让 `python -m retrieval.cli verify` 退出 1（CI 里是硬门禁）；
13. 受控工具的授权只认结构化记录：风险级别、参数白名单、权限、审批门禁与事后验证器都在
    `registry/tool-registry.yaml`（数据），模型不能自行声明动作类别；运行时描述与
    `registry/tool-registry.approved.json` 的已审核哈希不一致时**该工具不可使用**
    （改注册表后必须重新审核：`python -m enforcement.cli registry --approve --reviewer <name>`）；
14. `action_hash` 覆盖工具 schema 哈希、规范化参数、主体、权限与上下文摘要：参数变一个字符旧授权即失效；
    授权短时效、单次使用，执行器不解析自然语言批准，重复 `action_id` 绝不执行第二次
    （台账 + 审计链两处都拦）；高风险动作（destructive / external / privileged）必须人工审批；
15. 事后验证必须交证据：文件前后哈希与 diff 摘要、退出码、超时、工具返回值只作不可信数据
    （只留摘要）；证据不足按 `repair_required` / `inconsistent` 处理，回滚能力按工具声明，
    声明不了就写 `unsupported`——绝不假装所有副作用都可撤销；
16. 审计链是追加写的摘要链（`sequence` + `prev_digest`）：密钥（含 `Authorization: Bearer` 后的 token）、
    绝对路径（Windows 与 POSIX）、控制字符与超长载荷一律脱敏或转义，单条记录超过上限直接失败关闭；
    受治理动作在审计 / 台账不可写时不执行（只有 `risk=read_only` 的工具允许声明 `audit_failure: degrade` 并记警告）。
    它是**摘要链不是防篡改日志**：删尾部或整链重写发现不了，外部锚定/签名属于 Phase 7；
17. 命令类工具的最小权限：白名单只做完整匹配，且命令里出现 `;` `|` `&` 反引号 `$(` `${` `>` `<` 或换行时
    一律结构性阻断（`command_composition_blocked`，pre-check 与驱动各查一遍）——
    `( .*)?` 形态的白名单会被“分号 + 第二条语句”绕过；
    同样地，命令里出现被禁片段 `../` `..\` `--output` `--ext-diff` `--no-index` 时结构性阻断
    （`command_fragment_blocked`）：白名单正则只描述“命令长什么样”，描述不了“这个选项会干什么”
    （`git diff --output=<文件>` 完整匹配却会写任意路径）。**白名单不是沙箱**：会读仓库内配置的
    命令仍可能被改写成执行外部命令，真正的隔离属于运行时的文件系统与进程沙箱，不在本阶段；
    需要组合命令或被禁片段时必须改注册表并重新审核，说明为什么安全；
18. 评测门槛与结果都随版本记录：门槛在 `tests/fixtures/retrieval_eval/queries.yaml`，
    结果在 `tests/fixtures/retrieval_eval/baseline-v2.json`，代码里不写"脱离数据的常数"；
    换 embedding、改术语表或改语料都必须重跑 `python tools/retrieval_eval.py --method both`，
    行为有意变化时用 `--record` 显式重记基线并递增评测集版本（`pytest` 也会比对这份基线）；
19. 验证器只产证据、不判定：allow / block 仍由 Policy Engine 决定；每条证据必须带
    验证器 ID 与版本、规则 ID、文件与行列、消息、严重级别、工具退出码与配置文件哈希，
    可选修复建议；证据里不得出现绝对路径、耗时或凭据（相同输入必须得到逐字节相同的证据）；
20. 关键验证器不可用一律失败关闭：缺失 / 版本不符 / 超时 / 崩溃 / 配置错误 / 输出非法，
    以及"没有任何验证器为某个 checker 提供证据"，都要让需要它的规则以 critical 阻断——
    同一批里的其他 PASS 抵消不了它；**"解析失败"不等于"没有依赖"**：语法错误、
    动态 import 目标不是常量、项目内模块解析失败都必须阻断；
21. 验证器注册表与项目档案是数据（`validation/`）：谁能产生证据、在哪个阶段、超时多久、
    工具版本区间与配置文件都写在 YAML 里；规则体必须与 `enforcement.checker` 一致，
    未知 checker、未实现的验证器 id、未声明的工具配置一律在加载阶段报错；
22. 外部工具只能按声明模板调用：参数 allowlist（路径必须是工作区内的仓库相对路径、不能以 "-" 开头）、
    白名单环境变量、显式工作目录、超时终止**整棵进程树**、输出必须脱敏（密钥 / 绝对路径 /
    控制字符 / 换行）并限量；工具输出与工具返回值只作不可信数据，不能改变规则集或造出新规则，
    没有规则归属的诊断只计数、不判定；
23. 验证器的临时目录只写在 `.tmp/validators/<run>/<validator>` 下（各验证器互不覆盖），用完即删；
    真实 Agent 链路与验证器共用的判定入口是 `policy.engine.evaluate(..., evidence=...)`，
    只提供上下文的调用路径（Phase 2 的 Hook）会把证据类 checker 的规则记进 `skipped_rules`
    并写明"需要验证器证据"——绝不静默放行。

## 临时文件与产物

- 会话产生的临时文件统一写在 `.tmp/`（已在 `.gitignore` 中），不要在仓库根目录散落临时文件；
  真实 Agent 沙箱闭环（`tools/dsh_sandbox_loop.py`）的受控项目与日志都在 `.tmp/phase-2-sandbox/` 下，
  不得把它指向真实仓库或真实凭据；
- Phase 4 的受控执行闭环在 `.tmp/phase-4-demo/` 下运行（受控工作区、审计、台账），
  它只动这个目录，不得指向仓库真实文件；
- Phase 3 的索引库、评测基线与阶段证据同样在 `.tmp/`（`.tmp/retrieval/`、`.tmp/artifacts/`）下，
  它们是构建产物，不提交；重建命令见根 `README.md`；
- Phase 5 的验证器闭环在 `.tmp/phase-5-demo/` 下运行（每个场景一个从夹具项目复制的工作区），
  验证器的运行期临时目录在 `.tmp/validators/` 下，二者都不触碰仓库真实文件；
- `.tmp/` 用完即删：`python tools/cleanup.py --dry-run` 预览，`python tools/cleanup.py` 执行；
- 该脚本只删白名单路径：`.tmp/`、`.pytest_cache/`、`.uv-cache/`、`__pycache__/`、`*.pyc`；
- 不要提交 `.tmp/` 内容；阶段证据可由 `python tools/phase_evidence.py` 随时重建。

## 学习手册（每个阶段一个目录）

每个阶段完成后在 `docs/learning/<phase>/` 下补齐四个文件：

```text
note.md            # 任务内容、对象清单与对象关系（手写）
walkthrough.ipynb  # 带注解的可执行讲解（由脚本生成，不要手改）
walkthrough.py     # 同一份内容的纯 Python 版本（由脚本生成）
README.md          # 怎么用、怎么维护、常见问题（手写）
```

- 改 notebook 内容 = 改 `tools/build_learning_notebook.py`（新增 `PHASE_N_CELLS` 并在 `PHASES` 注册），
  然后运行 `python tools/build_learning_notebook.py` 重新生成；
- 生成器会从两个工作目录各跑一遍全部代码单元，并断言示例退出码与文档里写过的 JSON 键名，
  任何不一致都会让生成失败，因此手册里的代码始终可运行、说明始终与输出一致；
- 新增阶段时同步更新索引 `docs/learning/README.md`；
- **手册里打印表格一律用生成器注入的 `pad()`**（按显示宽度补位）：`f"{文本:<10}"` 数的是字符个数，
  中文在等宽字体里占 2 列，中英混排的列会被挤歪；自由文本（原因、许可、细节）放最后一列；
- 提交前运行 `python tools/check_notebook.py docs/learning/*/walkthrough.ipynb` 校验结构。

## 引入新技术栈时需要同步更新

选定语言/框架后，请一次性补齐并在本文件登记：

- 依赖清单与锁文件（提交锁文件）；
- `README.md` 中的安装、构建、测试、运行命令（必须是**实际可执行**的命令，不要写占位符）；
- CI 配置；
- 相应的 `.gitignore` 条目（若 `.gitignore` 中已有 Node/Python 段，直接沿用）。
