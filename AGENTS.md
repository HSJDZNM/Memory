# AGENTS.md

面向 AI 编码代理的仓库约定。人类贡献者同样可参考。

## 仓库现状

仓库已绑定 Python 技术栈（见下文），完成 Engineering Policy Platform 的 **Phase 0 至 Phase 8**；Phase 6 的第二真实 Agent 产品验证仍待外部环境，Phase 8 的真实模型作者（`ChangeAuthor` 端口的模型实现）同样未接入：

- 可运行：根 `README.md` 中的安装、测试、CLI、Hook 自检、沙箱闭环、性能基线、检索索引与评测命令均已实际验证；
- 有规则目录 `policies/`（**43 条规则**：5 条项目自订 + 38 条由 `docs/mirrors/<mirror>/**` 的镜像原文提炼，
  每条 `standard` 规则都带正反例夹具与 chunk 级溯源）、核心源码 `src/policy/`（models / context / scope / engine / loader / check）、
  dsh 适配器 `src/adapters/dsh/`（adapter / hooks / 进程内转发插件）、
  多 Agent 适配层 `src/adapters/`（models / base / runtime / conformance / loader / cli / json_adapter / event_adapter / dsh_adapter）、
  能力声明是数据 `adapters/`（每个 Agent 一份 manifest + adapter 配置 + 事件样本 + `approved.json` 已审核哈希）、
  检索层 `src/retrieval/`、语料清单 `knowledge/corpus.yaml`、
  受控执行层 `src/enforcement/`、工具注册表 `registry/`、
  测试 `tests/{unit,contract,integration,security}` 与 CI `.github/workflows/phase-8.yml`；
- 决策协议为 `SCHEMA_VERSION = "1.1"`（台阶 3b 起；**1.0 的载荷一律拒收**），
  世代名 `POLICY_VERSION = "decision-1.1"`（世代名常量在 `src/policy/models.py`，只与
  `schema_version` 同进同退、不跟随平台阶段），快照在 `tests/fixtures/decisions/`；
- Phase 2 的 Hook 契约、脱敏事件 fixture 与失败关闭设计分别在 `src/adapters/dsh/README.md`、
  `tests/fixtures/agent_events/dsh/` 与 `docs/project/engineering-policy-platform/phases/phase-2-dsh-adapter.md` 的实施记录里；
  `tools/dsh_sandbox_loop.py` 在 dsh 缺失**或**沙箱禁止管道 stdio（Hook spawn EPERM）时按环境跳过
  （退出码 0 + 写明 reason/reproduce，见 README 第 7.1 节）；它绝不把"跑不了"记成 pass；
- Phase 3 的摄取清单 `knowledge/corpus.yaml`、检索层 `src/retrieval/`（chunker / corpus / store / indexer /
  query / retriever / vector / context / cli）、固定评测集 `tests/fixtures/retrieval_eval/queries.yaml`、
  基线脚本 `tools/retrieval_eval.py` 与实施记录见 `docs/project/engineering-policy-platform/phases/phase-3-retrieval.md`；
  索引库是构建产物，落在 `.tmp/retrieval/`，可随时重建；
- Phase 4 的受控执行层 `src/enforcement/`（models / registry / action / approvals / audit / ledger /
  precheck / executor / drivers / postcheck / trace / cli）、数据化工具注册表
  `registry/tool-registry.yaml` 与已审核哈希 `registry/tool-registry.approved.json`、
  dsh 侧桥接 `src/adapters/dsh/enforcement.py`、受控执行闭环 `tools/enforcement_loop.py`；
  实施记录见 `docs/project/engineering-policy-platform/phases/phase-4-tool-enforcement.md`；
- Phase 5 的验证器层 `src/validators/`（python_ast / depgraph / docstrings / selection / adapters /
  pipeline / cli）、证据协议 `src/policy/evidence.py` 与 checker 分派 `src/policy/checkers.py`、
  数据化的验证器注册表与项目档案 `validation/`（validators / project / test-layout / ruff.toml / mypy.ini / pytest.ini）、
  语言专项规则包 `policies/coding/` 与 `policies/testing/`、夹具项目与假工具
  `tests/fixtures/validators/`、验证器闭环 `tools/validator_loop.py`；
  实施记录见 `docs/project/engineering-policy-platform/phases/phase-5-code-validators.md`；
- Phase 6 的规范事件 Schema 与能力声明模型 `src/adapters/models.py`、
  适配器协议与支持矩阵 `src/adapters/base.py`、
  多 Agent 运行时 `src/adapters/runtime.py`（命名空间隔离 / trace 来源校验 / 窗口熔断）、
  一致性套件 `src/adapters/conformance.py`、CLI `src/adapters/cli.py`、
  探针夹具 `tests/fixtures/agent_events/workspace/`、多 Agent 闭环 `tools/agent_loop.py`；
  当前只有 dsh 是真实产品接入，`generic-json` / `legacy-post-only` 是合成协议消费者；
  实施记录见 `docs/project/engineering-policy-platform/phases/phase-6-multi-agent-adapters.md`；
- Phase 7 的服务化层 `src/policy_api/`（models / errors / config / auth / services / runtime /
  timeout / idempotency / observability / ops / app / contract / cli / testing / probe）、
  部署数据与契约快照 `api/`（policy-api.yaml + openapi.json，说明见 `api/README.md`）、
  API 闭环 `tools/api_loop.py`、测试夹具 `tests/fixtures/api/`；
  **核心层不依赖 Web 框架**，只有 `policy_api` 的 HTTP 应用依赖 fastapi/uvicorn；
  实施记录见 `docs/project/engineering-policy-platform/phases/phase-7-policy-api.md`；
- Phase 8 的编排层 `src/orchestration/`（models / errors / limits / checkpoint / approvals / client /
  tools / nodes / graph / engines / langgraph_engine / runtime / cli）、编排闭环
  `tools/orchestration_loop.py`、工具注册表新增的 `orchestrator` 段（含"改规则需人工审批"的
  `orc.policy.edit`）、学习手册 `docs/project/learning/phase-8/`；
  **它是仓库里唯一导入工作流框架的地方**（只有 `langgraph_engine.py`，且构造引擎时才导入），
  核心层从不导入它；实施记录见 `docs/project/engineering-policy-platform/phases/phase-8-langgraph-orchestration.md`。

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
   若仓库 `.venv` 存在但在当前受限环境不可加载（缺依赖且装不进去），可用
   `python tools/ci_local.py --full --python <已验证解释器>` 显式覆盖；
   要让 **pre-push 钩子**也用上同一条逃生通道，设环境变量 `CI_LOCAL_PYTHON`（钩子与
   `ci_local.py` 都认它，`--python` 优先级更高）。不得为让门禁变绿而删除用户的 `.venv`。
   **同一工作树同时只允许一个 `ci_local.py`（含 pre-push 钩子那一次）真正执行**：它和它调起的
   编排闭环共用 `.tmp/` 下固定路径的状态（`.tmp/phase-8-orchestration/`、`.tmp/artifacts/`、
   `.tmp/retrieval/`），并发会互相拆台、跑出"假红"（实测出现过编排闭环 5/8 场景 FAIL 而单独跑
   全通过）。所以启动时取 `.tmp/ci-local.lock` 排他锁，抢不到的那个报出**持锁者 pid** 后
   **直接失败退出（1）**——不等待、不设绕过开关：并发的正确处置是显式拒绝，不是静默出错。
   锁由操作系统持有，进程一死自动释放，不留陈旧锁；`--list` 不取锁（它不写 `.tmp/`）。
   `tools/cleanup.py` **认同一把锁**：真要删之前非阻塞取锁，抢不到就报出持锁者 pid 后退出 1、
   一项都不删（`--dry-run` 不取锁；`.tmp/` 不存在时不取锁、也不把它建出来）。它删 `.tmp/` 下的子项时
   **显式跳过 `ci-local.lock`**，锁文件永不删除——否则 Windows 上 `rmtree` 会在被锁字节区间上失败
   （WinError 32），POSIX 上"删了再建"会换 inode，让两个进程各持一把锁、排他保证直接失效。
   **耗时可见**：门禁是串行的，墙钟时间就是各步之和。执行路径总会在最后打印按耗时降序的汇总表，
   `--timings` 另把每步耗时（含退出码）写成 `.tmp/ci-local-timings.json`——"为什么跑了二十分钟"
   应该是可直接读出来的事实，不是猜出来的印象。
   **同一批测试只跑一次**：`pytest` 步骤写 junit 报告，最后的"阶段验收证据"步骤引用它（`--suite-reports`），
   不再把四个套件重跑一遍；报告缺失 / 缺套件 / 早于最新源码改动时证据步骤退回真跑，并写明原因。
   两者的选组必须同属 `CODE_STEPS`：要么都跑、要么都不跑，引用的报告才必然来自本次门禁。
   **学习手册同步推迟到 `--full`**：默认与 pre-push（`--hook`）下它即使被改动选中也不执行，
   而是点名列为"未执行"并写明原因（`FULL_ONLY_STEPS`）；GitHub CI 照跑。改了 `src/` 或手册内容的
   分支，**合并前跑一次 `python tools/ci_local.py --full`**——否则手册漂移要到 CI 上才会红。
   pytest 步骤按文件并行（`-n auto --dist loadfile`，pytest-xdist 已锁定）：用例之间不得依赖
   `.tmp/` 下共享目录的"前后集合差"或"排序最后一个"，要定位本次运行的产物就记下它自己的 id。

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
| 依赖清单 | pydantic 2、PyYAML 6、FastAPI 0.1x + uvicorn（Phase 7 传输层）、langgraph 1.2（Phase 8 编排层，仅 `langgraph_engine.py` 导入）；dev: pytest 8+ | `pyproject.toml` |
| 依赖锁定 | `requirements.in`（声明）+ `requirements.lock`（固定直接依赖版本，CI 从它安装）；仓库不提交 `uv.lock` | 仓库根目录 |
| 测试 | pytest：`tests/unit`、`tests/contract`、`tests/integration`、`tests/security` | `pytest.ini`、`tests/conftest.py` |
| 检索 | SQLite FTS5（标准库 sqlite3；向量检索是可替换端口，本阶段未采纳） | `src/retrieval/`、`knowledge/corpus.yaml` |
| CI | GitHub Actions | `.github/workflows/phase-8.yml`（含 Phase 0–4 的重放用例、dsh 接线自检、检索基线、注册表审核、受控执行闭环、AST 证据重放、验证器注册表/探针/闭环、多 Agent 一致性套件/支持矩阵/闭环、Policy API 自检/OpenAPI 快照/ASGI 契约测试/API 闭环、编排自检/编排闭环/阶段证据） |
| 受控执行 | 标准库 + pydantic；注册表是 YAML 数据，台账与审计链是追加写 JSONL | `src/enforcement/`、`registry/` |
| 代码验证器 | 标准库 `ast` + 外部工具探针（Ruff / mypy / pytest 不进核心依赖） | `src/validators/`、`validation/` |
| 脚本 | 锁文件生成、阶段证据、性能基线、检索评测、dsh 沙箱闭环、受控执行闭环、多 Agent 闭环、API 闭环、编排闭环、notebook 生成与校验、临时文件清理 | `tools/*.py`（见 `tools/README.md`） |

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
   `policy_version` 是协议**世代名**（§"决策载荷的两个版本字段"），只与 `schema_version` 同进同退，
   **不跟随平台阶段**：载荷、快照与阶段证据都从 `policy.models.POLICY_VERSION` 取值，
   谁都不许自己算一个（曾经因此出现过"证据说 phase-5、载荷说 phase-1"）；
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
    结果在 `tests/fixtures/retrieval_eval/baseline-v3.json`（`tools/retrieval_eval.BASELINE_PATH` 指向当前版本，
    旧版基线留在同一目录作为历史），代码里不写"脱离数据的常数"；
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
    并写明"需要验证器证据"；Phase 6 Runtime 的写类动作更严格：没有 Phase 5 evidence provider
    直接 `evidence_unavailable` 阻断——绝不把 skipped 当成通过。
24. 多 Agent 适配层只做协议转换，且**能力上限由声明推出**：事件名、字段名、工具名、
    阻断与审批能力都写在 `adapters/<agent_id>/manifest.yaml` 里，
    并与 `adapters/approved.json` 的已审核哈希比对——改声明必须重新审核
    （`python -m adapters.cli approve --reviewer <name>`），
    未审核或哈希漂移一律拒绝接入。**拦不住写类动作的 Agent 不得被标成完整 enforcement**：
    只有事后钩子（`blocking=post_only`）或未声明 pre-hook 的协议消费者，
    上限是 `read_only`，受治理动作得到 `capability_unavailable`，
    绝不"跳过治理"；
25. 规范事件（`AgentEvent`，`src/adapters/models.py`）是唯一交换协议：
    未知版本、未知字段、未知事件类型、未知操作一律拒绝；`agent_id` 由装配处钉死，
    载荷自称无效；`payload` 只承载受控字段（`path` / `params` / `text` / `cwd`），其余原始输入只留摘要；
    路径解析的基准是**本次判定的工作区**（钩子类 Agent 用会话 cwd），
    绝对路径越界、含 `..` 的相对路径、空路径一律拒绝——
    `to_policy_event(..., workspace=...)` 的 `workspace` 参数不得被忽略；
26. 多 Agent 运行时（`src/adapters/runtime.py`）的四条隔离硬规则：
    审计与幂等键是 `<adapter.namespace>:<event_id>`，namespace 默认 agent id；同一部署跑多份同型号
    Agent 时必须用 `ledger_alias` 区分且运行时必须真正采用该 alias；主体只认 Adapter 的显式声明，
    载荷自称即拒绝；trace 登记表按 `owner_agent` 校验来源，同一 trace 的所有权与父链不可覆盖，
    伪造父 trace 一律 `trace_forged`；
    同一 Agent 在 `window_seconds` 窗口内的受治理事件数到上限即熔断
    （按 request_id 计数的旧口径数不到互相触发的循环，别再改回去）；
27. 一致性套件（`src/adapters/conformance.py`）的场景是**语义**描述，
    Adapter 用自己的事件名与工具名渲染（`render_event`）：
    新增一个 Agent 只增加渲染分支，不得让核心测试期望长出 Agent 专用分支；
    Adapter 不支持某个事件时必须显式失败（`AdapterEventError`），
    不允许静默跳过——"这个场景没测到"本身就是一个必须被写下来的结论；
28. Adapter 能力声明与代码工具表必须一致：`dsh` 的 manifest 与 Phase 2 的
    `TOOL_TABLE` 由契约测试逐项比对（名字、操作、路径字段、变更文本字段），
    改一处必须改另一处；升级 Agent 后先重跑 `python -m adapters.cli events` 与
    `python tools/agent_loop.py`，再更新支持矩阵与已审核哈希。
29. manifest 的 `full` 是能力上限，不是运行时自动接线：写类动作必须同时有 Phase 5
    `EvidenceBundle`、Policy allow 与 Phase 4 enforcer/pre-check，缺任一项都失败关闭；callback 只能在
    原子 claim + policy + pre-check 之后调用一次，callback 异常必须 block；PostToolUse 只做 post-check，
    绝不能再次调用 callback；runtime / trace / enforcement 台账损坏、未知版本或不可读写都不得忽略。
30. **API 是传输边界，不是第二份业务逻辑**：`src/policy_api/` 只做"协议 → 领域模型 → 协议"，
    判定仍只有 `policy.engine.evaluate` 一条路径（本地与经 API 的决定必须整份相等——
    决策载荷 JSON 值相等，字段顺序不属于契约）；`tools/api_loop.py` 会比对；
    `src/policy/` 与其余核心层**禁止导入 Web 框架**
    （`python -m policy_api.cli self-check` 与契约测试都会查）。
31. API 的 DTO 与领域模型分开，且两套版本各自演进：`API_SCHEMA_VERSION`（传输协议）与
    `policy.models.SCHEMA_VERSION` / `POLICY_VERSION`（决策协议与世代）**无关**；
    后者只能从核心取值，`policy_api` 不许自己算一个；删字段、**新增键**或改语义 = 新 API 版本
    （统一规则见第 55 条——"只增不改"同样是一次协议变更），
    改完必须 `python -m policy_api.cli openapi --write` 显式更新契约快照（`--check` 是 CI 门禁）。
32. API 的三条信任规则：**租户只来自令牌**（请求体里的 tenant 只是提示，越权即拒绝）、
    **客户端不能自带证据或决策**（证据只由服务端验证器流水线产出，检索的 `decision_ref`
    只能指向本服务算过的 `request_id`）、**服务身份不替用户扩权**（认证成功 ≠ 允许某个工具，
    业务动作仍由 Policy Engine 判定）。
33. API 失败关闭没有例外：未知 `api_version`、未知字段、未知操作枚举、未认证、跨租户、
    超预算、限流、依赖不可用（规则集 / 索引 / 验证器）、观测日志不可写，全部返回结构化错误码；
    **超时与"服务不可达"绝不等于 allow**（504 / 503，错误码由 `errors.STATUS_BY_CODE` 推导，
    调用方不能自定义 HTTP 状态）；错误响应不得泄露某个资源是否存在。
34. API 的观测与锚定：请求级 JSONL 只记摘要（request_id / trace / 主体 / 租户 / 规则集哈希 /
    索引版本 / Decision / 耗时 / 错误分类），密钥、绝对路径与控制字符在写入前脱敏，
    单条超限即失败关闭；指标端点只对运维角色或 `metrics_clients` 开放。
    `python -m policy_api.cli seal --out <锚>` 把摘要链末值发布到日志之外，
    `--verify` 能发现删尾或改写——**锚必须与日志分离存放**，它仍然不是防篡改日志。
35. **编排层是消费者，不是平台的一部分**：`src/orchestration/` 只回答"下一步做什么"，
    判定仍然只有平台一条路径；它是仓库里**唯一**导入工作流框架的地方
    （只有 `langgraph_engine.py`，构造引擎时才延迟导入 + 主版本校验，不可用即
    `EngineUnavailableError`，不静默回落），核心层从不导入它——删掉整个包，平台照常独立运行
    （`tests/contract/test_orchestration_engine.py` 检查两个方向）。`engine="auto"` 的回落
    必须如实写进 `RunReport.engine`，不许把参考引擎报成 LangGraph。
36. **图状态里不放正文**：需求原文、文件内容、工具输出与凭据都只以摘要/引用存在；
    checkpoint 是"单文件 + 原子替换"，带自己的版本（`STATE_SCHEMA_VERSION`，
    **不跟随平台阶段**）与状态摘要；相同输入必须得到逐字节相同的状态（状态里没有墙钟字段）。
    恢复时与**当前平台**的凭据（`rule_set_hash` / `index_version` / `tool_schema_hash` /
    协议世代）比对：规则集或索引变了就清掉旧 trace 与旧验证结果、回到检索节点重评
    （**不沿用旧 allow**）；工具 schema 变了旧审批作废；协议世代变了直接拒绝恢复；
    拿不到凭据按"变了"处理。恢复还会清掉上一轮的失败码与终态——失败不是工作流的进度。
37. **分支只由结构化 Decision 决定，终态只由失败码决定**（`errors.STATUS_BY_CODE`：
    平台不可用 / trace 断裂 / 证据缺失 → `blocked`；上限击穿 / 审批不合法 /
    副作用状态未知 → `needs_human`；编排自身损坏 → `failed`）。节点与引擎都不许自己发明状态，
    也没有任何一条"默认放行"的路径；未知路由标签、未知节点、非 `NodeOutcome` 的返回值一律失败关闭。
38. **人工审批绑的是平台口径的 `action_hash`**（`ToolRunner.binding()` 算出，覆盖工具 schema、
    规范化参数、主体、权限、上下文摘要**与 trace**），不是编排层自己的幂等键；找到的审批**文件**
    原样交给 Phase 4 的 pre-check 复验。"图到达了审批节点"永远不等于用户批准；
    恢复会重新校验审批，参数一变旧审批自动作废。
39. **编排层的写入仍然走 Phase 4 的受控执行链**（API 没有 enforce 路由）：工具表按 Agent 分段
    （`orchestrator` 段），改注册表必须重新审核；副作用之前先写"意图"并**立刻刷盘**
    （`NodeContext.commit`），恢复时发现"开工未结算"即 `side_effect_unknown` 交给人，
    既不重放也不假装成功；同一个幂等键重试不得产生第二次副作用（幂等跳过 + 平台台账两道闸）。
40. **规范文档不会"自动"变成规则**：`docs/mirrors/<mirror>/**` 首先是只读的追溯与检索语料，
    转化是一次**显式、可评审的提炼**。一条规则要上线必须同时满足：`source.kind ∈ {project-policy, standard}`
    且 `source.path` 指向**真实存在**的本地文件；`enforcement.checker` 是已实现的 6 个之一，
    且 `validation/validators.yaml` 里有验证器为它声明产证据；适用范围能用 6 个维度表达；
    `severity` 落在四值枚举里。不满足时**正确的做法是停在 Curated Guidance**（进 `knowledge/corpus.yaml`、供检索），
    而不是写一条"看起来在管这件事、实际什么都没查"的规则。
    由镜像文档提炼的规则（`source.kind: standard`）**必须**带正反例：
    `tests/fixtures/rules/<ID>/bad.py` 必须命中、`good.py` 必须不命中（且不能被 `skipped_rules` 吞掉），
    由 `tests/integration/test_rule_corpus.py` 走**真实验证器流水线**守住；
    并在 `knowledge/corpus.yaml` 的 `rule_sources` 登记
    `{rule_id, rule_version, dataset, source_path, heading_path}`（登记后解析不到 chunk 会让索引 run 失败）。
    **Ruff 码的归属必须双向一致**：规则声明的码要被 `validation/ruff.toml` 的 `select` 选中，
    `select` 的码要有规则归属——`tests/contract/test_validator_protocol.py` 的
    `test_ruff_codes_are_declared_and_selected_in_both_directions` 守住这条；**单向不一致都等于"规则静默失效"**。
    `type_check` 规则在装好 mypy 之前一律不启用（工具缺失 = 失败关闭，会让所有 Python 文件一次性判红）。
    逐篇的转化判定与理由见 `docs/project/architecture/规则转化覆盖报告.md`，方法与七个台阶见 `规则文档转化为规则.md`。
41. **分层声明必须自证测试路径**（M1）：`layers` 按声明顺序取第一个命中的 glob，因此一条生产层通配符
    可以悄悄罩住测试文件（实测：`tests/test_shipment_controller.py` 命中 `**/*_controller.py` 被判成
    入口层，ARCH-001 把一份"真实装配对象图"的测试挤成了"手写替身"）。声明了 `test_paths` 与
    `test_layer` 的配置，**加载期**必须能证明每条测试路径先命中测试层；证明不了（规则顺序不对、
    缺 `test_layer`、落到默认层）一律拒绝启动——配置自相矛盾时 Hook 报 `startup_error` 并退出 2，
    既不判 allow 也不判 block。检查用「见证路径」法（可能漏、不误报：报出来的每条都有真实路径支撑），
    实现在 `AdapterConfig.layer_test_conflicts()`；没声明 `test_paths` 的配置行为不变。
42. **动手前取证是可声明、可关闭、失败关闭的**（G3 的正面回答）：`dsh-adapter.yaml` 的 `pre_evidence` 段
    声明是否在 pre-execute 路径上跑 Phase 5 流水线取证（`registry_root` / `workspace` / `shadow_root` /
    `exclude` / `validators` / `timeout_ms`）。声明并启用后：在**影子工作区**（副本，用完必删）上应用
    "提议的新内容"，跑真实验证器，把 `EvidenceBundle` 交给 `policy.engine.evaluate`——证据类 checker 于是
    从 `skipped_rules` 变成**参与判定**。取证失败 / 超时 / 提议内容重建不了（例如 `edit` 的 `old_string`
    不唯一）一律失败关闭（`evidence_unavailable`，退出码 2），**绝不回落到"没证据就当跳过"**；
    没有声明这一段时保持 Phase 2 契约（只做上下文类 checker，其余显式记进 `skipped_rules`）。
    启用时还要满足预算不等式：`pre_evidence.timeout_ms + timeout_ms < hooks.json 的 timeout`。
43. **账本要说得出规则的严重级别分布**（M3）：`rule_count` 与"会拦人的规则数"是两回事
    （43 条里 24 条 error、19 条 warning；实测 DOC-001 命中只产生 `allow_with_warnings`）。
    pre-execute 的审计记录必须同时给出规则集与本次判定的按级别分布
    （`rules_by_severity` / `evaluated_by_severity` / `skipped_by_severity` /
    `blocking_capable_rule_count` / `advisory_rule_count`）；引用"有多少条规则在管"时必须带级别，
    不得把 warning 级规则算成阻断力。
44. **依赖类规则必须声明 language 维度**（N14）：`forbidden_dependency` 的依赖集来自语言解析；
    `language` 缺失时依赖集是空元组，「查了没问题」其实是**没有查**，而且这个 allow 的
    理由不写在任何地方（与「确实没有禁用依赖」逐字相同）。因此**加载期**拒绝「checker 属依赖类但
    scope 不含 `language` 维度、或把它写成不限制（`*`）」的规则——
    把「规则作者的纪律」变成会失败的检查（实现：`policy.loader.assert_language_declared`）。
    声明了具体语言而语言不匹配时，规则会显式进 `skipped_rules`（那不是静默），不在本检查范围内。
45. **自己的仪器也要能失败**（N13）：`tools/governance_gap_probe.py` 的 G06 曾经只驱动 Phase 2 的 Hook，
    从不走 Phase 6，于是对「两条路径依赖提取口径不一致」这类缺陷**永远是绿的**。探针的每条检查都必须
    写清它驱动的是哪条路径、**仍不覆盖什么**，并给出「修复前会红」的证明：在 `git archive HEAD` 的副本上
    做一次显式变异 → 检查变红 → 撤回变异 → 变绿。做不到就写下「这条检查覆盖不到」，
    不许把「跑了、是绿的」当成覆盖。
46. **账本要说得出「哪几条规则报了违规」**（P1）：`matched_rules` 是本次**参与过判定**的规则，
    `violations` 是本次**真的报了违规**的规则——43 条全开之后，只有前者的账本等于"全而糊"，
    读的人会按 matched 数违规。判定记录因此必须同时给出 `violations`（rule_id 带版本 + severity +
    message + 证据摘要，排序稳定、字符串脱敏）与 `violations_by_severity` / `violations_note`；
    `allow_with_warnings` 尤其需要（warning 是"看着过了、其实被提醒过"的那一类）。
    **没有算出 decision 的记录不许伪造这份清单**：`context_error` / `evidence_unavailable` /
    `event_replay` 这些记录里没有 `violations` 键，这件事本身就是一个必须能被读出来的结论。
47. **语言覆盖是数据，不是默认**（P2）：`validation/validators.yaml` 的 `uncovered_languages`
    是"哪些语言按设计不取证"的**唯一**声明处（每项必须带可评审的 `reason`；未知字段、重复语言、
    空理由、与既有 rule pack 自相矛盾一律加载期报错）。命中时**不是静默放行**：流水线产出显式判定
    `PipelineReport.language_coverage = {language, status: not_covered_by_design, reason, declared_in}`，
    `served_checkers` 保持为空——"平台对这类目标什么都没查"必须能从审计读到，而不是靠读者从 allow 反推。
    既没有 rule pack、也没有被声明 → **仍然失败关闭**；声明了不取证但本次有规则需要某个 checker 的证据
    → 同样是 Blocker。打开 `pre_evidence` 因此不再等于"文档类目标结构性不可写"。
48. **证据的含义取决于取证时那棵树的形状**（P3）：动手前取证跑在"当前磁盘树 + 本次提议内容"上，
    而"先写测试"这种正确写法会让兄弟模块还不在树里（实测：Ruff 的 isort 判成第三方 → I001 →
    STYLE-018 warning）。所以摘要必须写清**这条证据属于哪棵树**：`tree.scope`（含提议的当前树）、
    `target_existed_before`、`tree_digest`（覆盖「相对路径 + 文件哈希」的稳定摘要）、
    适用范围 note，以及"可能漏、不误报"的缺口标注（`tree_gaps` 只在顶层包已存在、模块找不到时报）。
    **同一份载荷在两棵树上得到两个结论不是缺陷，没写清是哪棵树才是**；批次语义（把同一批已提议的
    文件也放进树里）属于一次显式设计，不在本条的承诺里。
49. **测试路径与"查了多少"都只有一份声明**（P4/P5）："哪些路径算测试"是平台级数据
    （`validation/test-layout.yaml` 的 `test_patterns`，值 `test`），Adapter 的
    `test_paths` / `test_layer` 与 `policy.check` 的层推断**都**必须以它为准并写出来源
    （`layer_source ∈ {declared, platform_test_layout, filename_guess}`）——同一个测试文件不许在
    Hook 路径与验证器路径上得到两个层。CLI 还必须答得出"这次到底查了多少"：`check_volume`
    （`complete` / `missing_dimensions` / `blocking_capable_skipped` / `skipped_by_reason`，
    缺维度按 `rule.scope` 与 context 的结构化比对算出，**不解析 reasons 文本**），
    缺维度时文本输出一行 `INCOMPLETE:`。"缺关键维度"的失败关闭只落在**自相矛盾**的调用上
    （给了 `--changed` 却没给 `--operation` → 退出码 2）；把"完全没声明 `--operation`"一律变成
    配置错误会让 README 与文档里必须可执行的 allow 例子变成 block，那不是失败关闭而是破坏可用性。
50. **口径诚实：存什么、叫什么、拒绝时说清怎么改**（P6/P7/P8）：台账存参数原文与绝对
    `request.workspace` 是 PostToolUse 重建 `ActionRequest` 与 `action_hash` 的必要条件，
    所以**不许**为了自述好看而扣掉它——要改的是自述（`ledger.py` / `action.py` /
    `docs/project/architecture/术语与口径.md` 三处同一口径，并有测试钉住行为）；
    **同名两义一律改名**：验证器的 `declared_checkers` 是"声明负责"、顶层 `served_checkers`
    是"真的服务过"，改载荷键必须按协议自己的规则显式递增版本号（`EVIDENCE_SCHEMA_VERSION` /
    `PIPELINE_SCHEMA_VERSION`）；
    **拒绝理由必须给出"改成什么形态就能过"**：写类越界（`policy.context.repo_relative_path`）
    与读类、Phase 4 pre-check、Phase 6 `normalize_event_path` 用同一句话，范围校验一个字不放宽。
51. **「待实现」是显式状态：既不是失败，也不是通过**（Q7）：选中的测试**在收集期**就失败、
    而原因是「它 import 的**项目内**模块/名字在本次取证树里还不存在」时，取证侧必须给出
    `ValidatorStatus.PENDING_IMPLEMENTATION`（中文「待实现」）这条**显式状态**：
    不产生 Blocker、`failing_tests` **不进** `served_checkers`（没查成的不能记成查过了），
    报告与审计里带上 `pending_implementation` 清单（测试模块 + 缺失目标 + 修复动作），
    判定侧**不**把它记成 violation，而是产出 **warning 级**的**独立发现**
    （`ValidationResult.pending_findings`，审计记录里同名的键），
    decision 仍是 `allow_with_warnings`——「先写测试、再写实现」因此不再被自己的平台拦死，
    而绕法（把测试先写成不测任何东西的占位）也不再是唯一出路。
    **为什么必须独立成通道**（2026-09-29 裁定 D-1(b)，台阶 3b 落地）：第 46 条把
    `violations` 的定义钉死为"本次**真的报了违规**的规则"，而 pending 不是违规——
    混在同一个键里就是同名两义（第 50 条）。移出之后 `violations` 一个条目都不多、
    四种 decision 与改动前**逐个相等**（判据 J1(b)：`violations` 里没有 pending 条目），
    pending 的可见性改由新通道承接：`pending_findings` 在决策载荷、审计记录与给模型看的
    stderr 里都出现，**空通道是一个明确的空列表，不是一个缺失的键**。
    `expected_decision` 的空判定因此要求"两个通道都空"，阻断判定**一字不动**且只读
    `violations`（pending 的 severity 在**构造期**被强制为 warning，进不了阻断级）。
    **反例一条都不许放宽**：第三方包缺失、语法错误、conftest 出错、
    断言失败、退出码不是收集失败形态、目标解析不出来——全部保持真违规（规则自己的 severity）
    或原来的失败关闭（crashed/unavailable critical）。这条路**不证明测试最终会通过**：
    它只说明这次的树还在构建中，测试是否通过由后续动作的取证与 PostToolUse 事后核对重新算。
    新增状态值 = 载荷变更：`EVIDENCE_SCHEMA_VERSION` / `PIPELINE_SCHEMA_VERSION` 必须按协议
    自己的规则**显式递增**（1.1 → 1.2），并把写死版本号的断言按新版本号显式更新——
    包括 `docs/project/architecture/tech-detail/` 的生成物（改内容源后重新生成，`--check` 是门禁）。
52. **失败关闭不等于理由正确**（Q6）：拦住一次工具调用只完成了一半，另一半是**告诉人一个对的原因**。
    把「Hook 起不来」翻译成理由时，必须把「要启动什么」与「在哪个目录启动」**分开写**，并按
    工作目录的真实状态归因——Node 的 spawn 在 **cwd 不存在**时把 ENOENT 归给**可执行文件**，
    照抄它会把模型带偏到「运行时没装」。实现上 spawn **之前**用 `node:fs` 预检工作目录，
    异常路径再复查一次（覆盖竞态），两条路都失败关闭。插件侧的理由措辞是**跨侧契约**：
    `tools/dsh_sandbox_loop.py` 的分类器按它分流，改措辞必须同步两侧，并由
    `tests/contract/test_policy_hook_chain.py` 的跨侧用例（真插件产出 → 真分类器）守住。
53. **归因的合取必须落在同一条记录内**（D4）：在**整篇日志**上分别判定两组事实再合取，会把
    「真失败」洗成「环境跳过」——`tools/dsh_sandbox_loop.py` 里「启动崩溃原文」与「被拒路径」
    必须在**同一个崩溃块**内（崩溃原文行 + 紧随的缩进续行）、「`Hook 无法执行`」与「`spawn EPERM`」
    必须在**同一行**内，合不起来就归不了因：**宁可让真失败保持红**，也不产生环境跳过。
    同一纪律适用于诊断字段：从日志里推出来的根必须**先是合法的路径/URL**（`file:///C:/x` → `C:/x`），
    畸形候选按写明理由的规则丢弃，真根不许因为解析口径而消失。
54. **`host-version` 的四种形态互不代替，改声明必须重录观测**（Q8 尾巴）：报告（默认）/ 活体
    `--check` / CI `--record-check`（**不探测宿主**，比对提交进仓库的 `adapters/host-versions.observed.json`）
    / 写入 `--record`（唯一写入口）。CI 上必须跑 `--record-check`——活体形态在没装宿主的机器上
    退 0，它既不是通过也不是失败，不能当门禁；记录缺失/不完整/哈希对不上/声明≠记录一律退出 1
    （有门禁就必须有数据）。**维护纪律**：改 `adapters/<agent>/manifest.yaml` 之后先
    `python -m adapters.cli approve --reviewer <name>`，**再**在装着真实宿主的机器上跑
    `host-version --record`，把记录的 diff 送评审；版本不一致**不改变任何 allow/block**。
55. **加键就是改协议**（台阶 3b 的统一规则，2026-09-29 裁定）：任何协议载荷**新增键**或
    改语义，都必须按**该协议自己的**版本号显式递增，并把写死版本号的引用点（协议快照、
    契约快照、断言、生成物、跨语言/跨包的副本）在**同一个提交**里改完。
    **"只增不改、旧消费方还能读"不是跳过升版的理由**：加了键却不升版，会让同一个版本号
    底下存在两种载荷形状——那是第 50 条"同名两义"在协议层的形态，比一次显式的拒收更难发现。
    本仓库现有的版本轴（**列举，不是穷尽**——判据是"这个载荷的键集合或语义变没变"，
    不是这张表在不在；各自独立演进，谁也不跟随平台阶段）：
    - 判定与证据：`policy.models.SCHEMA_VERSION`（决策载荷）与世代名 `POLICY_VERSION`（只与它同进同退）；
      `policy.evidence.EVIDENCE_SCHEMA_VERSION` / `validators.pipeline.PIPELINE_SCHEMA_VERSION`；
      `policy.check.OUTPUT_SCHEMA_VERSION`（`--json` 的**外层包装**，不是决策载荷：1.0 是**追认**的
      ——台阶 3c 之前的形状（那时 `check_volume` 还没有 `obligations_open` / `obligations_note`），
      1.1 = 现形状；2026-09-30 裁定见 `src/policy/check.py` 的常量注释）；
    - 多 Agent 协议：`adapters.models.CANONICAL_EVENT_SCHEMA_VERSION`（规范事件）与
      `ADAPTER_MANIFEST_SCHEMA_VERSION`（manifest）；`adapters.base.ADAPTER_CONFIG_SCHEMA_VERSION`
      （adapter 配置）与 `APPROVED_SCHEMA_VERSION`（已审核哈希）；`adapters.runtime.AGENT_RUNTIME_SCHEMA_VERSION`；
      `adapters.wiring.WIRING_SCHEMA_VERSION`（接线报告）；`adapters.conformance.CONFORMANCE_SCHEMA_VERSION`
      （一致性套件报告）；`adapters.host_version.HOST_VERSION_SCHEMA_VERSION`（报告载荷）与
      `HOST_VERSION_RECORD_SCHEMA_VERSION`（提交进仓库的观测记录）；
    - dsh Hook：`adapters.dsh.hooks.AUDIT_SCHEMA_VERSION`（判定记录）；`VERDICT_SCHEMA_VERSION`
      （阻断判定行——**跨语言**：Python 与 `policy-hook.plugin.mjs` 必须同批改，插件按精确版本号读，
      不认识就回到"未知状态"）；
    - 受控执行与编排：`enforcement.models.ENFORCEMENT_SCHEMA_VERSION` / `REGISTRY_SCHEMA_VERSION`、
      `enforcement.registry.APPROVED_SCHEMA_VERSION`、`enforcement.ledger.LEDGER_SCHEMA_VERSION`、
      `enforcement.approvals.APPROVAL_SCHEMA_VERSION`、`orchestration.checkpoint.CHECKPOINT_SCHEMA_VERSION`；
    - API 与服务：`policy_api.models.API_SCHEMA_VERSION`、`policy_api.observability.REQUEST_LOG_SCHEMA_VERSION`、
      `policy_api.config.API_CONFIG_SCHEMA_VERSION`、`policy_api.idempotency.IDEMPOTENCY_SCHEMA_VERSION`、
      `policy_api.contract.SNAPSHOT_SCHEMA_VERSION`；
    - 检索与针脚：`retrieval.models.INDEX_SCHEMA_VERSION` 与 `CHUNKER_VERSION`（分块语义）、
      `provenance.cli.RECEIPT_SCHEMA_VERSION`、`provenance.wiring_scope.SCHEMA_VERSION`；
    - 本机门禁与仪器：`tools.obligations_gate.REPORT_SCHEMA_VERSION`（义务账门禁的报告载荷——
      账本不存在时从"没有依据的命中"改成"不适用"那一档，1.0 → 1.1）。
    **不是版本轴的同名字段**（别照这张表改）：`orchestration.langgraph_engine.MIN_LANGGRAPH_VERSION`
    是依赖下界；`adapters/<id>/manifest.yaml` 的 `agent_version` / `protocol_version` 是产品与协议
    **声明**（改了要重新审核并重录宿主观测，见第 54 条），不是载荷版本。
    **新增一条轴时，把它登记进这张表**：表里没有的载荷不等于可以不加版本号。
    **历史先例只登记、不回改**：P1（审计记录新增 `violations` / `violations_by_severity` /
    `violations_note`）与台阶 2（新增 `origin` 一族键）都**加了键而没有递增**
    `AUDIT_SCHEMA_VERSION`——它们是本规则生效前的既成事实，登记在这里是为了让后来者知道
    "当时没升版"，**不是可以再犯的先例**；从台阶 3a（`decision_reason` → 审计 1.0→1.1）起
    已按本规则执行，台阶 3b（`pending_findings` → 审计 1.1→1.2、决策 1.0→1.1）同。
56. **义务账只记账、不判罚，解除只认一次真实测试运行**（台阶 3c / 方案 §3.3）：判定载荷里的
    「待实现」（第 51 条）必须能被**跨会话**读到，否则一个拼错的 import 可以永久待实现下去，
    而每一次判定都是 `allow_with_warnings`。实现是 `src/policy/obligations.py`（追加写 JSONL，
    折叠出未结义务），三条口径写死在那里：键是 `(rule_id, target, missing_target)`、**不含
    `session_id`**（带上它，新会话就把义务清零）；**会话内只记账**（dsh 侧 `dsh-adapter.yaml` 的
    `obligations_ledger`，可选；写不了只打一行 `OBLIGATIONS LEDGER UNAVAILABLE`，**不改判定、
    不阻断**）；**判罚与读数只在 `tools/obligations_gate.py`**（**L5 试用期：warn + 非零退出**；
    2026-09-30 起它作为 `ci_local.py` 的**只报告步骤**（`REPORT_ONLY_STEPS`，带到期日）被本机门禁
    执行——**非零退出只打印命中数、不计入门禁失败**；升格判据是「跑过 N≥1 次且 0 命中」，
    且 0 命中必须来自至少一次真实读数）。两条会被判据读的后果：`obligations_open > 0` 时
    `check_volume.complete = false`（J1(c)）；**解除只由一次真实 pytest 运行判定**（J1(d)）——
    "真实"是**结构化**的三条事实（`tool.pytest` 状态 ∈ `{ok, findings}`、`failing_tests` 在
    `served_checkers` 里、选中的测试非空），不解析 reasons 文本，也不许由账本推断；
    `obligations_open == 0` 却给不出「最近一次真实测试运行」= **没有依据**，门禁按命中处理。
    没给 `--obligations` = **没有账本可读**（不是"0 条义务"）：账本摘要的键按"有没有给账本"
    出现或缺失，两个读法必须能分开（第 46/50 条）。**门禁这一侧同一条纪律**：账本**文件不存在**
    = **不适用**（`applicable=false`，不算命中，也**不算一次真实读数** —— 它凑不了升格判据里的
    "0 命中"）；账本**存在**（哪怕是个空文件）却拿不出最近一次真实运行，仍按命中处理（见上句）。
    账本协议自己的版本轴是 `policy.obligations.LEDGER_SCHEMA_VERSION`（第 55 条：加键就要动它），
    门禁**报告**自己的版本轴是 `tools.obligations_gate.REPORT_SCHEMA_VERSION`。

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
- Phase 8 的编排闭环在 `.tmp/phase-8-orchestration/` 下运行（受控工作区、checkpoint、审计与台账），
  学习手册的产物在 `.tmp/learning-phase-8/` 下：它只动这些目录，不得指向仓库真实文件；
- `.tmp/` 用完即删：`python tools/cleanup.py --dry-run` 预览，`python tools/cleanup.py` 执行；
- 该脚本只删白名单路径：`.tmp/`、`.pytest_cache/`、`.uv-cache/`、`__pycache__/`、`*.pyc`；
- 不要提交 `.tmp/` 内容；阶段证据可由 `python tools/phase_evidence.py` 随时重建。

## 学习手册（每个阶段一个目录）

每个阶段完成后在 `docs/project/learning/<phase>/` 下补齐四个文件：

```text
note.md            # 任务内容、对象清单与对象关系（手写）
walkthrough.ipynb  # 带注解的可执行讲解（由脚本生成，不要手改）
walkthrough.py     # 同一份内容的纯 Python 版本（由脚本生成）
README.md          # 怎么用、怎么维护、常见问题（手写）
```

- 改 notebook 内容 = 改它的**内容源**，然后运行 `python tools/build_learning_notebook.py` 重新生成。
  内容源分两处，别改错：Phase 0–5 的单元格内联在 `tools/build_learning_notebook.py`（`PHASE_N_CELLS`，
  并在 `PHASES` 注册）；**Phase 6–8 已拆到 `tools/phase6_cells.py` / `tools/phase7_cells.py` /
  `tools/phase8_cells.py`**，由生成器在文件头导入——生成器里没有它们的副本；
- 生成器会从两个工作目录各跑一遍全部代码单元，并断言示例退出码与文档里写过的 JSON 键名，
  任何不一致都会让生成失败，因此手册里的代码始终可运行、说明始终与输出一致；
- 新增阶段时同步更新索引 `docs/project/learning/README.md`；
- **手册里打印表格一律用生成器注入的 `pad()`**（按显示宽度补位）：`f"{文本:<10}"` 数的是字符个数，
  中文在等宽字体里占 2 列，中英混排的列会被挤歪；自由文本（原因、许可、细节）放最后一列；
- 提交前运行 `python tools/check_notebook.py docs/project/learning/*/walkthrough.ipynb` 校验结构。

## 引入新技术栈时需要同步更新

选定语言/框架后，请一次性补齐并在本文件登记：

- 依赖清单与锁文件（提交锁文件）；
- `README.md` 中的安装、构建、测试、运行命令（必须是**实际可执行**的命令，不要写占位符）；
- CI 配置；
- 相应的 `.gitignore` 条目（若 `.gitignore` 中已有 Node/Python 段，直接沿用）。
