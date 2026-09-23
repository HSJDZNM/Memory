# R0 事实基线（Lead 勘察，全体会议成员必须引用）

> 目的：把「本仓库今天实际是什么」变成可引用的编号事实（F = 已存在，N = 尚不存在）。
> 纪律：本文件只写**当前代码与数据实际做到的事**，不写计划；与代码冲突时以代码为准。
> 任何人新增事实，写进自己 R1 文档的「事实引用」小节，并附 `file:line`。
> 标记约定：【实测】= 本轮真的跑过命令；【读码】= 读了源码/数据；【提案】= 尚未存在。

## 1. 定位与架构口径

- **F1** 定位：独立于具体 Coding Agent 的软件工程治理层；把规范变成机器可执行规则，对固定上下文稳定给出 allow / allow_with_warnings / block，并留下可重放证据。（README.md:1-21）
- **F2** 六层架构（架构图文口径的唯一真相源）：① 消费方/入口、② 接入与协议转换、③ 判定核心、④ 能力层、⑤ 数据与契约、⑥ 证据与门禁。（docs/project/architecture/README.md:8）
- **F3** 12 项能力清单与主要入口。（docs/project/architecture/功能清单.md:45-60）
- **F4** 九阶段 Phase 0–8 全部实现完成；未完成项只有两个：第二个真实 Agent 产品验证（Phase 6）、真实模型作者 ChangeAuthor（Phase 8）。（docs/project/engineering-policy-platform/README.md:45-59、功能清单.md:33-43）
- **F5** 三条「唯一」：判定路径唯一（本地/dsh/API/编排都只经过 policy.engine.evaluate）；工作流框架导入点唯一（只有 src/orchestration/langgraph_engine.py，构造引擎时延迟导入）；凭据与正文唯一口径（图状态/审计/台账只放摘要与引用）。（功能清单.md:25-29）
- **F6** 台阶 1–7（规则文档 → 可执行规则）与 Phase 0–8 是三套独立编号，对照见 docs/project/architecture/术语与口径.md §2；图上标 ①②③。

## 2. 运行时边界（进程、入口、路由）

- **F7** Policy API 只有 6 条路由（传输契约快照 api/openapi.json 的真相源）：
  - POST /v1/policy/evaluate（判定）
  - POST /v1/knowledge/retrieve（检索）
  - POST /v1/validation/evaluate（验证器证据）
  - GET /v1/health/live、GET /v1/health/ready（存活/就绪）
  - GET /v1/ops/metrics（仅运维角色或 metrics_clients）
  （src/policy_api/contract.py:45-50；app.py:44-48、295-310；ROUTES 元组见 runtime.py:73）
- **F8** **没有 enforce 路由**：API 不执行受控工具，写入只能走 Phase 4 的受控执行链（AGENTS.md 约束 39）。
- **F9** CLI 入口包（`python -m <pkg>`）：policy.check、retrieval.cli、enforcement.cli、validators.cli、adapters.cli、policy_api.cli、orchestration.cli。（git ls-files src/*/__main__.py；子命令表见 tools/README.md、各包 cli.py）
- **F10** 脚本入口 tools/*.py；其中 6 个 *_loop.py 是闭环证据脚本：dsh_sandbox_loop、enforcement_loop、validator_loop、agent_loop、api_loop、orchestration_loop。（tools/README.md:12-17）
- **F11** 核心层禁止导入 Web 框架与工作流框架；只有 policy_api 依赖 fastapi/uvicorn，只有 langgraph_engine.py 导入 langgraph。（AGENTS.md 约束 1、30、35）
- **F12** API 启动即自检：serve 先跑 readiness，不通过就拒绝启动。（api/README.md:55-56）

## 3. 数据（相当于「文件系统」）

- **F13** 规则是数据：policies/<domain>/<ID>.yaml，现 6 份（architecture/ARCH-001、coding/DOC-001、coding/STYLE-001、coding/STYLE-002、testing/TESTING-001、testing/TESTING-002）。规则集加载是原子的。（git ls-files policies；AGENTS.md 约束 2、4）
- **F14** 检索语料清单 knowledge/corpus.yaml + 术语映射 knowledge/query_expansion.yaml；索引是构建产物，落在 .tmp/retrieval/，可随时重建。（AGENTS.md 约束 11、12、18）
- **F15** 受控工具注册表 registry/tool-registry.yaml + 已审核哈希 registry/tool-registry.approved.json（按 Agent 分段，含 orchestrator 段）；哈希不一致该工具不可用。（AGENTS.md 约束 13、39）
- **F16** 验证器注册表与项目档案 validation/（validators.yaml、project.yaml、test-layout.yaml、ruff.toml、mypy.ini、pytest.ini）。（AGENTS.md 约束 21）
- **F17** Agent 能力声明是数据：adapters/<agent_id>/manifest.yaml + adapters/approved.json；当前 3 个消费者，只有 dsh 是真实产品，generic-json 与 legacy-post-only 是合成协议夹具。（AGENTS.md 约束 24；README.md 进度段）
- **F18** API 部署数据 api/policy-api.yaml：limits / budgets / rate_limit / tenants / clients（只存 token 的 sha256）/ audit 六段。（api/README.md:9-19）
- **F19** 临时产物统一在 .tmp/ 下（检索索引、各阶段闭环结果、阶段证据），用完即删：`python tools/cleanup.py`。（AGENTS.md「临时文件与产物」）

## 4. 证据与门禁

- **F20** 阶段证据：`python tools/phase_evidence.py` 生成规则集哈希 / 协议版本 / 适配器契约 / 各阶段闭环结论 / 测试结果 / 性能基线。（tools/README.md:9）
- **F21** CI：.github/workflows/phase-8.yml（Phase 0–4 重放、dsh 接线自检、检索基线、注册表审核、受控执行闭环、AST 证据重放、验证器闭环、多 Agent 一致性、API 自检/OpenAPI 快照/契约/闭环、编排自检/闭环/阶段证据）。
- **F22** 本机同序门禁：`python tools/ci_local.py`（--full / --list / --hook / --python）。GitHub 侧故意不启用分支保护。（AGENTS.md「工作方式」5）
- **F23** 文本与仓库门禁：check_text_conventions.py、check_repo_consistency.py、check_notebook.py、check_arch_canon.py、check_arch_style.py、secret_scan.py。（tools/README.md:7、23-30）
- **F24** 测试四层：tests/{unit,contract,integration,security} + tests/fixtures/。（pytest.ini、git ls-files tests）
- **F25** 审计链是追加写摘要链（sequence + prev_digest），是**摘要链不是防篡改日志**；对外锚定由 `python -m policy_api.cli seal --out <锚>` 完成。（AGENTS.md 约束 16、34）

## 5. 已有前端资产（必须续接，不要重复造）

- **F26** 已有一份尚未提交（untracked）的操作台提案：docs/project/engineering-policy-platform/designs/ 下 5 份文档（可行性评估、前端交互逻辑、后端契约与连接证据、评审意见、分块策略对比），以及可点开的静态原型 designs/console/（6 个 HTML + assets/app.js + assets/style.css + 由 build_site.py 生成的 assets/data.js）。（git status 显示 `?? docs/project/engineering-policy-platform/designs/`）
- **F27** 原型 6 页与覆盖范围：index（总览）、data（镜像/语料/索引与分块）、authoring（提炼/规则文件）、gates（验证器覆盖）、activation（审批·生效·溯源）、system（连接自检/路由表/缺口/红线）。（designs/console/README.md:15-24）
- **F28** 原型的数据来源是真实数据：规则集来自 policy.loader.load_rule_set、语料来自 corpus.yaml、镜像清单来自 docs/*/manifest.json、验证器覆盖来自 validation/validators.yaml + policy.checkers.SUPPORTED_CHECKERS、chunk 列表来自 .tmp/retrieval/index.sqlite3、路由来自 policy_api.runtime.ROUTES。（designs/console/README.md:40-49）
- **F29** 原型的既有边界：无写路径（提交必须走 Phase 4 受控执行链 orc.policy.edit + action_hash）；预演是浏览器内模拟，真实实现必须调用后端同一套代码；提交前须先修 B1（新建规则文件绕过审批）与 B2（HTTP 面漂移静默）。（designs/console/README.md:61-64）
- **F30** 原型交互约定：所有解释放在 ? 悬停提示；灰按钮 = 该操作今天没有对应路由（悬停给出缺口与替代命令）；勾选与候选存在 localStorage（键 console.state）。（designs/console/README.md:33-39）

## 6. AGENTS.md 中与「操作系统」设计直接相关的硬约束（原文编号）

- **F31** 约束 30：API 是传输边界，不是第二份业务逻辑；判定只有 policy.engine.evaluate 一条路径，本地与经 API 的决定必须整份相等。
- **F32** 约束 31/32/33：两套版本各自演进；租户只来自令牌；客户端不能自带证据或决策；服务身份不替用户扩权；超时与服务不可达绝不等于 allow。
- **F33** 约束 13/14/15/16：授权只认结构化记录；action_hash 覆盖工具 schema + 规范化参数 + 主体 + 权限 + 上下文摘要；短时效单次使用；高风险必须人工审批；事后验证必须交证据；审计不可写则受治理动作不执行。
- **F34** 约束 17/22：命令白名单只做完整匹配且结构性阻断组合命令与被禁片段；外部工具只能按声明模板调用，超时终止整棵进程树，输出脱敏限量。
- **F35** 约束 24/25：能力上限由声明推出；拦不住写类动作的 Agent 上限是 read_only，受治理动作得到 capability_unavailable，绝不跳过治理。
- **F36** 约束 35–39：编排层是消费者不是平台；图状态不放正文；分支只由结构化 Decision 决定；人工审批绑平台口径的 action_hash；编排层写入仍走 Phase 4 链；恢复时发现「开工未结算」即 side_effect_unknown 交给人。
- **F37** 约束 2/19/21/27：规则、语料、工具表、验证器档案、能力声明都是**数据**；验证器只产证据不判定；一致性套件的场景是语义描述，不得让核心测试长出 Agent 专用分支。
- **F38** 约束 5/6：相同输入必须得到相同结论；上下文只接受显式字段，不得根据文件名、目录或用户消息推断主体、权限或审批状态。
- **F39** 约束 3/20/33：未知字段、未知枚举、未知 scope、未知操作、未知 checker、未知版本一律报错；关键验证器不可用一律失败关闭；「解析失败」不等于「没有依赖」。

## 7. 今天**不存在**的东西（设计不得假装它存在）

- **N1** 没有前端工程：仓库无 package.json、无前端构建链；原型是零构建静态页 + 一个 Python 生成器。（git ls-files 无 package.json）
- **N2** 没有草稿规则存储：草稿规则生命周期状态机在既有设计里是【提案】。（designs/文档转规则操作平台-前端交互逻辑.md:73）
- **N3** 没有写路由、没有 CORS：前端与 API 只能同源（既有设计的实测结论：无 CORS、只能同源）。（docs/project/engineering-policy-platform/README.md:38-40）
- **N4** 没有审批中心：人工审批今天以文件/结构化记录形态交给 Phase 4 pre-check 复验，没有可查询的「待审批列表」服务。（AGENTS.md 约束 38；F15）
- **N5** 没有多用户会话、没有前端身份：真实身份只有 api/policy-api.yaml 里的 clients 与角色。（designs/文档转规则操作平台-前端交互逻辑.md:21-33）
- **N6** 没有第二个真实 Agent 产品、没有真实 ChangeAuthor 模型。（F4）

## 8. 会议纪律（对所有成员生效）

1. 一切结论必须能追到 F 编号、file:line 或实测输出；找不到证据就写【未知，需核验】，**不许猜**。
2. 「界面/脚本层不得出现第二份判定」是本设计的最高红线，任何板块、流程、页面若违反，必须显式写成风险并给出替代方案。
3. 写入范围只限自己被分配的 meeting 文件；不得改源码、不得改 AGENTS.md、不得改既有 designs 文档。
4. 文本规范：UTF-8、LF、行尾无空白、文件结尾一个换行。
