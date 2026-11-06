# Memory

**Memory 是一个独立于具体 Coding Agent 的软件工程治理层。** 它把工程规范变成机器可执行的规则，
对显式上下文稳定地给出 `allow` / `allow_with_warnings` / `block`，并留下"命中了哪些规则、
跳过了哪些、依据什么证据"的可重放审计记录。

当前状态（截至 bank k≥3 收尾，2026-10-23）：

- **Phase 0–8 的仓库实现已完成**：规则与判定、Agent 适配、离线检索、受控执行、代码验证器、
  多 Agent 运行时、HTTP API、可恢复编排。
- **bank k≥3 pilot 已完成 27 次运行**（3 题 × 3 臂 × 3 block）：**21 份完整 run-record + 6 份 T-only**；
  独立验收审计 **A1–A12 全部 pass**，结论 **pass-with-open-items**（开放项见
  [审计读数](docs/project/engineering-policy-platform/readings/2026-10-24-bank-k3-audit.md) §4）。
- **43 条规则、6 类 checker**；单元 / 契约 / 集成 / 对抗四层测试；本机门禁与 GitHub Actions 双门禁。
- 当前只有 **dsh** 是真实产品接入；第二个真实 Agent 产品与 Phase 8 的真实模型作者仍是外部验收项。

> 一句话：它不替 Agent 写代码，也不替模型"感觉"对错；它把"什么算合规"变成可执行、可解释、
> 可审计的判定与执行边界。

## 治理原理

### 一条请求怎么走

```text
Agent / 工具请求
  → Adapter：只做协议转换，输出显式 PolicyEvent / PolicyContext（不猜 layer / language / principal）
  → Rule Set：YAML 数据，按 scope（语言 / 层 / 模块 / 操作 / Agent / 项目）选择相关规则
  → Engine：确定性判定 → allow / allow_with_warnings / block
      并给出 matched_rules / skipped_rules / violations / evidence
  → Executor：授权与具体动作绑定（action_hash），单次使用，先 pre-check 再执行
  → Post-check：文件前后哈希、diff、退出码、验证器证据
  → Audit：追加写摘要链；一次任务可回放到"为什么"
```

### 五条硬规则

1. **规则是数据，不是提示词。** `policies/**/*.yaml` 由 Loader 解析成不可变模型；规则有
   id、version、scope、severity、checker、source；改语义必须升 version。43 条规则 = 5 条项目自订
   + 38 条由镜像文档提炼；每条 `standard` 规则带正反例夹具与 chunk 级溯源。
2. **上下文只来自显式声明。** 主体、权限、layer、language、operation 都必须由调用方 / Adapter
   显式给出；不从文件名、目录或用户消息里推断。声明不出来就失败关闭。
3. **不确定就拒绝（fail-closed）。** 未知 `schema_version`、未知字段、未知 scope 维度、
   未知 checker、未知操作、缺失证据、验证器不可用——一律报错或 block，绝不"默认放行"；
   API 的超时 / 不可达也绝不等于 allow。
4. **证据先于判定。** 能确定性验证的规则不交给模型：依赖用 AST / 依赖图，风格 / 文档 / 类型 /
   测试由外部工具产证据；验证器只产证据，最终 allow / block 仍由 `policy.engine.evaluate`
   一条路径决定。没有证据的 checker 进 `skipped_rules` 并写明原因，绝不把"没查"当成"通过"。
5. **授权绑动作，审计可重放。** `action_hash` 覆盖工具 schema、规范化参数、主体、权限、
   上下文与 trace；参数改一个字符旧授权立即失效；授权短时效、单次使用。执行后必须交证据；
   审计链是追加写摘要链，删尾 / 整链重写发现不了，所以需要外部锚定——它不假装自己是防篡改日志。

### 两层边界

- **判定只有一条路径**：核心是 `policy.engine.evaluate`；CLI、dsh Hook、HTTP API、编排层
  都只是在它外面加入口 / 边界，不复制判定逻辑。
- **Adapter 只翻译，不治理**：dsh / 多 Agent 的能力声明是数据（`adapters/`），未审核或哈希漂移的
  工具不可用；适配层不把 Agent SDK 类型带进核心。
- **API 是传输边界**：租户只来自令牌，客户端不能自带证据 / 决策；本地与经 API 的决策载荷必须整份相等。
- **编排是消费者**：`src/orchestration/` 只回答"下一步做什么"，是仓库里唯一导入 LangGraph 的地方；
  删掉它平台照常独立运行。每次动手仍回平台要结构化 Decision，人工审批绑 `action_hash`，
  副作用前先写"意图"，恢复时"开工未结算"交给人（`side_effect_unknown`）。

### 它不是什么

- **不是沙箱**：白名单 / 规则不是进程与文件系统隔离；真正的隔离属于运行时。
- **不是 LLM 裁判**：确定性失败不能被模型解释覆盖。
- **不是"文档自动变规则"**：镜像文档先只读、可检索；转成规则是一次显式、可评审的提炼。
- **不是"审计链防篡改"**：它是摘要链；删尾部 / 整链重写发现不了，需要外部锚定 / 签名。

## 治理价值与效果

### 价值：把"规范"变成可验证的工程能力

| 问题 | 机制 | 可验证的落点 |
| --- | --- | --- |
| 规范散在提示词 / 文档里，靠模型自觉 | 规则是数据，带 version / scope / source；正反例夹具 | `policies/` 43 条；加载原子性；规则集哈希 |
| 判定不可解释，出了问题不知道哪条规则 | Decision 载荷：matched / skipped / violations / evidence / request_id | `policy.check --json`；审计；决策协议 1.1 |
| 不确定时默认放行 | fail-closed；未知输入 / 缺失证据 / 依赖不可用一律拒绝 | 对抗测试；API 超时≠allow；验证器缺失 critical |
| 治理只停留在"建议" | 授权与具体动作绑定、单次使用、执行后交证据 | `action_hash`；pre/post-check；audit / ledger |
| 多 Agent 各写一套 | Adapter 协议转换 + 能力声明 + 一致性套件 + 隔离 / 熔断 | `adapters/`；conformance；runtime namespace |
| 服务化后出现第二套判定 | API 只做"协议 → 领域模型 → 协议"，判定仍只有一条路径 | 本地 / API 决策整份相等；OpenAPI 快照 |
| 编排绕过治理 | 编排是消费者；每次动作回平台判定；图状态不放正文 | checkpoint 兼容性；审批绑 action_hash；失败关闭 |

### 效果：k≥3 pilot 读数（n=3，只作描述）

2026-10 的 bank k≥3 pilot：3 题 × 3 臂 × 3 block = 27 次运行，单一模型身份、单一宿主、headless。

| 任务 | A（旧口径） | B（新口径） | C（不治理对照） |
| --- | --- | --- | --- |
| crossmodule 重构（负对照） | 33/33 ×3 | 33/33 ×3 | 33/33 ×3 |
| async 并发 | 14/38、30/38、31/38 | 38/38 ×3 | 38/38 ×3 |
| docs 配置迁移 | 28/39 ×3 | 36/39 ×3 | 39/39 ×3 |

- **27/27 正常运行结束**（exit 0、无超时、`invalid=[]`）；**21 份完整 run-record + 6 份 T-only**。
- **方向计数 3/3**：async A<B；docs A<B 且 B<C；cross 三臂同值（负对照按构造不应有差异）。
- **守卫读数**：21 份完整记录、144 个文件检查；C 维度 134 `allow` + 10 `allow_with_warnings`、
  0 `block`；69 条 `DOC-001@1` warning（7 run / 10 文件）；A 结构谓词 191/210 pass、
  19 次失败（A5/A6/A7/A9），不改变 T 计数。
- **防作弊抽样（H2）**：抽 6/10 个测试路径、51 个版本；0 skip/xfail、0 空测试、0 `assert True`；
  但**抽样不盲**、只覆盖 60%。
- **独立审计**：A1–A12 全 pass、0 处数字不一致；结论 **pass-with-open-items**。

### 怎么读这些数（重要）

- 这是 **pilot 的描述性读数**，不是 treatment 效应结论：n=3、单模型、单宿主；
  **不能写"有效 / 显著 / 提升 / 优于"**，不能算均值 / 百分比 / 跨题总分，不能外推。
- 6 个 T-only（async / docs 的 A 臂）只作 T 原值来源，**不能**与 21 份完整记录混读成 C/A 对照。
- docs 的 B/C 差（36 vs 39）在读数里只记录为 B 的最终配置未迁移、C 已迁移；
  **不归因于某条规则**，n=3 也不足以区分原因。
- H2 的"未发现削弱"只代表 6/10 个路径的静态核对；**非盲、未跑测试、无变异自证**，
  不能外推成"全部测试都没被削弱"。
- 逐 run 证据与开放项见
  [27 run 读数](docs/project/engineering-policy-platform/readings/2026-10-23-bank-k3-27runs.md) /
  [H2](docs/project/engineering-policy-platform/readings/2026-10-23-bank-k3-h2.md) /
  [守卫](docs/project/engineering-policy-platform/readings/2026-10-23-bank-k3-guards.md) /
  [treatment](docs/project/engineering-policy-platform/readings/2026-10-23-bank-k3-treatment.md) /
  [独立审计](docs/project/engineering-policy-platform/readings/2026-10-24-bank-k3-audit.md)。

### 工程读数

- **43 条规则**（5 项目自订 + 38 由镜像提炼）、6 类 checker、正反例夹具与 chunk 级溯源。
- **当前收集 3430 个测试用例**（单元 2054 / 契约 505 / 集成 754 / 对抗 117；本机全量
  3424 passed、6 skipped——跳过项均为 Windows 环境限制）。
- **本机门禁 + GitHub Actions 双门禁**：本机 `tools/ci_local.py` 按改动选择步骤并持排他锁；
  CI 覆盖 30 步（含只有 bash 能跑的步骤）。
- **k≥3 现场**：27 个 run 目录、3 份 freeze、3 份 exp-set、审批 / TTL 与审计证据全部保留在
  `.tmp/k3/`（按约定不进 git）。

## 快速开始

环境要求：Python ≥ 3.11。以下命令均已在本仓库实际执行验证。

### 安装

依赖锁定以 [requirements.lock](requirements.lock) 为准。推荐用 [uv](https://docs.astral.sh/uv/)
建虚拟环境并从锁文件安装：

```powershell
uv venv
uv pip install -r requirements.lock
```

没有 uv 时，用现有解释器从同一份锁文件安装：

```powershell
python -m pip install -r requirements.lock
```

**核心可以独立运行**：`pyproject.toml` 的必装依赖只有 pydantic 与 PyYAML；HTTP 栈
（fastapi / uvicorn）与编排框架（langgraph）分别在 `[api]` 与 `[orchestration]` 两个 extra 里。
只想要治理核心时：

```powershell
pip install .                  # 核心：policy / retrieval / validators / enforcement / adapters
pip install ".[api]"           # 再加 HTTP 服务
pip install ".[orchestration]" # 再加编排层（需要 langgraph）
```

### 运行规则检查（CLI）

```powershell
# 反例：Controller 直接依赖 Repository，退出码 1
uv run python -m policy.check examples/bad_controller.py --layer controller

# 正例：Controller 只依赖 Service，退出码 0
uv run python -m policy.check examples/good_controller.py --layer controller

# 范围不匹配：layer=service 时 ARCH-001 不参与判断，输出会列出跳过原因，退出码 0
uv run python -m policy.check examples/good_controller.py --layer service

# 只校验规则集本身（配置损坏时退出码 2）
uv run python -m policy.check --check-rules
```

退出码：`0` 通过（allow）、`1` 发现违规（block / allow_with_warnings）、`2` 配置或执行错误。
`--json` 输出机器可读包装；其中的 `result` 是带 `schema_version` 的决策载荷，可被
`policy.parse_decision` 原样解析回来。更细的字段与版本轴见
[src/policy/models.py](src/policy/models.py) 与 [03 技术选型](docs/project/engineering-policy-platform/03-technology-and-layout.md)。

未使用 uv 时，先让解释器找到 `src/`：

```powershell
$env:PYTHONPATH = "src"
python -m policy.check examples/bad_controller.py --dependencies repository
```

### 测试

```powershell
uv run python -m pytest tests/unit -q
uv run python -m pytest tests/contract -q
uv run python -m pytest tests/integration -q
uv run python -m pytest tests/security -q
uv run python -m pytest -q
```

四层分别是：单元（模型、范围、聚合、分块、AST、API DTO、编排状态）、契约（决策协议快照、
Adapter 映射、检索端口、执行协议、验证器证据、API 传输、引擎等价）、集成（真实 CLI、
dsh Hook、检索索引、受控执行、验证器流水线、HTTP API、编排恢复）、对抗（注入、越权、
失败关闭、伪造审批、跨租户、平台不可达绝不返回 allow）。

### 本机门禁

```powershell
uv run python tools/ci_local.py          # 按改动范围选择步骤；持排他锁，失败退出 1
uv run python tools/ci_local.py --full   # 全量（CI 的 30 步）
```

装上钩子后 `git push` 会自己跑 `--hook`，失败即阻断推送。同一工作树同时只允许一个
`ci_local` 实例（它和编排闭环共用 `.tmp/` 下的固定状态）。

### 清理临时文件

所有会话产物都写在 `.tmp/`（已在 `.gitignore` 中）。用完即删：

```powershell
uv run python tools/cleanup.py --dry-run   # 先看会删什么
uv run python tools/cleanup.py             # 删除 .tmp/、__pycache__/、.pytest_cache/ 等
```

### 更多操作

本 README 只保留基础操作。各阶段怎么跑、参数与退出码，见下面的**能力地图**与各模块 README；
完整目录与文档分层见 [docs/README.md](docs/README.md)。

## 能力地图

| 能力（阶段） | 它回答的问题 | 入口 | 深入 |
| --- | --- | --- | --- |
| 规则与判定（0–1） | 这次变更为什么 allow / block？ | `python -m policy.check` | `src/policy/` |
| dsh Hook（2） | Agent 调工具前能不能执行？ | `src/adapters/dsh/`、`examples/dsh/` | [Adapter README](src/adapters/dsh/README.md) |
| 离线检索（3） | 当前任务该知道什么规范？ | `python -m retrieval.cli` | [knowledge/corpus.yaml](knowledge/corpus.yaml) |
| 受控执行（4） | 允许之后真的执行了吗？ | `python -m enforcement.cli` | [registry/tool-registry.yaml](registry/tool-registry.yaml) |
| 代码验证器（5） | 结果是否真的合规？ | `python -m validators.cli` | [validation/](validation/) |
| 多 Agent（6） | 换一个 Agent 还能否一致？ | `python -m adapters.cli` | [adapters/](adapters/) |
| Policy API（7） | 服务化后判定会不会分叉？ | `src/policy_api/` | [api/README.md](api/README.md) |
| 编排（8） | 下一步做什么、失败能否恢复？ | `src/orchestration/` | [src/orchestration/README.md](src/orchestration/README.md) |
| bank k≥3 | 治理改动在真实任务上表现如何？ | `testing/ab/bank/` | [bank README](docs/project/engineering-policy-platform/testing/ab/bank/README.md) |

详细命令不放在 README：每个阶段都有可执行的闭环脚本与读数；从
[Engineering Policy Platform 文档集](docs/project/engineering-policy-platform/README.md) 进入。

## 目录结构

```text
.
├── src/policy/                 # 核心：规则加载 / 上下文 / 范围 / 判定 / 决策协议
├── src/adapters/               # Agent 适配层（dsh、多 Agent 运行时、一致性套件）
├── src/retrieval/              # 离线规范检索（SQLite FTS5；向量是端口）
├── src/enforcement/            # 受控执行（注册表 / 授权 / 审计 / 台账 / 驱动 / 事后核对）
├── src/validators/             # 代码验证器（AST / 依赖图 / 文档 / 选择 / 流水线）
├── src/policy_api/             # HTTP 服务边界（DTO / 认证 / 租户 / 观测 / 契约）
├── src/orchestration/          # 编排消费者（唯一导入 LangGraph 的包）
├── policies/                   # 43 条规则（数据）+ 正反例夹具
├── adapters/                   # Agent 能力声明 + 已审核哈希
├── registry/                   # 工具授权表 + 已审核哈希
├── validation/                 # 验证器注册表 / 项目档案 / 测试布局
├── api/                        # Policy API 部署数据 + OpenAPI 快照
├── knowledge/                  # 检索清单与受控术语表
├── docs/                       # mirrors（只读镜像）+ project（本项目文档与读数）
├── tests/{unit,contract,integration,security}
├── tools/                      # 阶段证据 / 闭环脚本 / 评测 / 清理
├── .github/workflows/phase-8.yml
└── .tmp/                       # 会话临时产物（不进 git，用完可删）
```

## 技术栈

| 项 | 选择 | 说明 |
| --- | --- | --- |
| 语言 | Python ≥ 3.11（本机验证 3.13.11） | 文档选型 Phase 0–1 指定 |
| 依赖 | 必装：pydantic 2、PyYAML 6；extras：`[api]`、`[orchestration]` | 核心层不依赖 Web 框架，也不依赖工作流框架；只有 `policy_api.app` 与 `orchestration.langgraph_engine` 例外 |
| 检索 | SQLite FTS5（标准库 sqlite3） | 可解释的检索基线；向量检索是端口，本阶段未采纳 |
| 受控执行 | 标准库 + pydantic | 注册表是 YAML；授权 / 幂等 / 审计链落在追加写 JSONL 上 |
| 测试 | pytest 8+（本机验证 9.1.1） | 单元 + 契约 + 集成 + 对抗四层；API 用进程内 ASGI 客户端 |
| 包管理 | uv；锁文件是 `requirements.lock` | 仓库不提交 `uv.lock`；CI 从锁文件安装 |
| CI | GitHub Actions | `.github/workflows/phase-8.yml` |

## 架构不变量

1. 核心层（`src/policy/`）不导入 Agent 框架、Web 框架、向量库或工作流框架；
   只有 API 的 app 与编排的 LangGraph 引擎按声明例外。
2. 规则集加载是原子的；未知字段、未知枚举、未知 scope 维度、未知操作、未知 checker 一律报错，
   不静默忽略或默认放行。
3. 相同输入得到相同结论；violation 按 `rule_id` 稳定排序；规则集哈希与加载顺序无关。
4. 上下文只接受显式字段；不根据文件名、目录或用户消息推断主体、权限或审批状态。
5. 决策协议带 `schema_version`；未知版本拒绝消费，不降级为 allow。
6. Adapter 只做协议转换；未知事件 / 工具 / 缺失路径一律拒绝；能力声明未审核或哈希漂移的工具不可用。
7. 检索的原始查询不拼 SQL / FTS 表达式；权限只来自显式 `AccessScope`；不可用时只输出
   `knowledge_unavailable`，绝不回退到"模型记忆里的规范"。
8. 受控执行：`action_hash` 覆盖工具 schema、参数、主体、权限与上下文；授权短时效、单次使用；
   执行后必须交证据；审计 / 台账不可写时不执行受治理动作。
9. API 是传输边界：租户只来自令牌；客户端不能自带证据或决策；超时 / 不可达不是 allow。
10. 编排是消费者：图状态不放正文；恢复用当前凭据重评；审批绑 `action_hash`；
    "开工未结算"即 `side_effect_unknown` 交给人，不重放也不假装成功。

## 约定

### 提交信息

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```text
<type>(<scope>): <subject>
```

常用 type：`feat`、`fix`、`docs`、`refactor`、`test`、`chore`、`perf`、`build`、`ci`。
主题行使用祈使语气，不超过 72 字符；破坏性变更在正文写 `BREAKING CHANGE:`。

### 分支

主分支为 `main`。功能开发使用 `feat/<topic>`，修复使用 `fix/<topic>`。

### 文本文件

统一 UTF-8 编码与 LF 换行（由 `.gitattributes` 强制）；提交前删除行尾空白，
文件以单个换行符结尾（由 `.editorconfig` 提示）。

## 开放项与边界

- **Phase 6 的第二个真实 Agent 产品验证**仍待外部环境；当前只有 dsh 是真实接入，
  `generic-json` / `legacy-post-only` / `http-api` 是合成协议消费者。
- **Phase 8 的真实模型作者**（`ChangeAuthor` 端口）尚未接入；候选改动目前来自可替换端口。
- **bank k≥3 的开放项**（详见 [审计读数](docs/project/engineering-policy-platform/readings/2026-10-24-bank-k3-audit.md) §4）：
  H2 抽样不盲；H2 结果在 bank run-record 1.0 无 `bypass_sampling` 落点；6 个 T-only 的 C/A unavailable；
  `COMMAND-FAMILIES.md` 与 async / docs README 的两处预存 errata 未修；H2 只覆盖 6/10、未做运行验证。
- **能力边界**：白名单不是沙箱；审计链不是防篡改日志；n=3 的 pilot 不能外推成效果结论。
- 完整开放工作与复审时间见 [04-open-work.md](docs/project/engineering-policy-platform/04-open-work.md)；
  非技术读者看 [07 状态简报](docs/project/engineering-policy-platform/07-status-brief.md)。

## 延伸阅读

- [Engineering Policy Platform 文档集](docs/project/engineering-policy-platform/README.md)
- [愿景、边界与设计原则](docs/project/engineering-policy-platform/00-vision-and-principles.md) ·
  [总体架构与核心契约](docs/project/engineering-policy-platform/01-architecture-and-contracts.md)
- [技术详解（可执行 notebook）](docs/project/architecture/tech-detail/README.md) ·
  [术语与口径](docs/project/architecture/术语与口径.md)
- [bank 题库与 k≥3 读数](docs/project/engineering-policy-platform/testing/ab/bank/README.md)
- [AGENTS.md](AGENTS.md)：仓库约定、阶段纪律与实现约束
