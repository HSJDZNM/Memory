# Phase 7：Policy API

> 状态：仓库实现已完成。API 只增加**部署与信任边界**，不改变规则语义；
> 核心库仍可不启动 API 独立运行（契约测试会守住这条）。

## 目标

把已经稳定的核心能力服务化，使多个 Adapter 通过版本化 API 使用统一规则、检索和验证能力。API 是传输边界，不应把业务逻辑从核心库复制一份。

## 最小 API

```http
POST /v1/policy/evaluate
POST /v1/knowledge/retrieve
POST /v1/validation/evaluate
GET  /v1/health/live
GET  /v1/health/ready
```

`evaluate` 只计算决定；真正执行工具仍在受控 Executor。除非有明确需求，不在首版 API 中提供任意 shell、文件或插件执行接口。

## 开发步骤

### 1. 固定 OpenAPI Schema

从核心模型生成或显式映射请求响应。API DTO 与领域模型分开，防止传输字段污染核心。请求必须携带 schema version、request ID、主体和项目边界。

### 2. 加入认证与授权

服务先验证调用者，再由 Policy Engine 判断业务动作。认证成功不等于允许某个工具；服务身份也不能替最终用户扩权。

### 3. 租户与项目隔离

规则、索引、缓存、日志和限流键都包含 tenant/project。任何未指定边界的查询不得跨默认集合搜索。

### 4. 超时、幂等与限流

- evaluate/retrieve/validate 分别设置预算；
- 写入型或可能重复触发的请求支持 idempotency key；
- 限制请求体、chunk 数、并发和返回大小；
- 下游超时时返回明确错误，不伪造 allow。

### 5. 可观测性

记录 request ID、trace ID、主体、规则集版本、索引版本、Decision、耗时和错误分类。默认不记录完整 Prompt、文档正文、密钥或未脱敏工具参数。

### 6. 部署前准备

只有在 API 契约稳定后才选择 FastAPI 等框架。依赖版本必须锁定；健康检查区分“进程活着”和“能安全提供策略服务”。

## 测试步骤

### Schema 与兼容性

- 合法请求与核心 Decision 一致；
- 缺失/未知字段、未知 schema version 和超大请求被拒绝；
- OpenAPI 快照变化需要显式评审；
- 新增可选字段保持向后兼容；
- 删除或改义字段需要新 API 版本。

### 认证与隔离

- 未认证、过期凭据和错误 audience 被拒绝；
- tenant A 无法读取 tenant B 的规则、chunk、缓存或 trace；
- 服务账户不能替用户调用未授权工具；
- 错误响应不泄露某个资源是否存在；
- 日志与指标按权限访问。

### 行为测试

- 两个不同 Adapter 通过 API 对等价上下文得到等价决定；
- Engine、Retriever、Validator 超时分别得到正确状态和失败策略；
- idempotency key 重试不重复产生副作用或审计记录；
- 并发规则更新与 evaluate 不产生半套规则；
- readiness 在规则或关键依赖不可用时失败。

### 非功能测试

- 固定规则集下记录 p50/p95/p99 基线；
- 请求体、并发和速率限制生效；
- 慢客户端不会耗尽工作线程；
- 日志后端故障、连接池耗尽和优雅关闭有测试；
- 模糊测试覆盖 JSON 边界、Unicode、控制字符和路径字段。

## 观察点

观察同一个 Policy Engine 被本地 SDK 和 HTTP Adapter 使用时是否产生完全相同的决定。API 只增加部署与信任边界，不改变规则语义。

## 退出条件

- OpenAPI、认证、隔离和版本策略有自动化测试；
- 至少两个 Adapter 通过 API 契约测试；
- 服务异常不会返回默认 allow；
- health/readiness、限流、超时和审计可观察；
- 核心库仍可不启动 API 独立运行。

## 实施记录

本记录对应 Phase 7 的六个开发步骤、四组测试与五个退出条件。**实际命令以根
`README.md` 为准**，这里只记录实现事实、踩到的坑与需要知道的偏差。

### 实际做了什么

| 计划步骤 | 落地物 |
| --- | --- |
| 1 固定 OpenAPI Schema | `src/policy_api/models.py`（DTO：`ApiEnvelope` / `ContextDTO` / 三个请求体）、`src/policy_api/contract.py`（`api/openapi.json` 快照 + 差异比较）、`python -m policy_api.cli openapi --check`（CI 门禁，漂移即退出 1） |
| 2 加入认证与授权 | `src/policy_api/auth.py`：`Authorization: Bearer` → 令牌 sha256（`hmac.compare_digest`）→ 客户端声明 → 租户/项目边界；`ClientSpec.expires_at` 过期即 401；服务身份不替用户扩权，授权仍由 Policy Engine 做 |
| 3 租户与项目隔离 | `src/policy_api/services.py`（`TenantStore` / `LoadedTenant`）：每个租户自带规则目录、项目根、检索索引、验证器配置与观测日志；请求体没有 tenant 字段，租户只能来自令牌；跨租户与"不存在"对外同为 404/401，不泄露存在性 |
| 4 超时、幂等与限流 | `src/policy_api/timeout.py`（墙钟预算，超时返回 504 而不是 allow）、`src/policy_api/idempotency.py`（每租户一份台账：同键同摘要返回原响应 + `Idempotency-Replayed`，同键不同摘要 409）、`src/policy_api/runtime.py`（每（客户端，租户）令牌桶、`max_request_bytes` / `max_concurrency` / `max_response_bytes`） |
| 5 可观测性 | `src/policy_api/observability.py`：请求级 JSONL（request_id / trace_id / 主体 / 租户 / 规则集哈希 / 索引版本 / Decision / 耗时 / 错误分类 / 状态码）+ 指标（路由计数、p50/p95/p99、限流与超时计数）；**摘要链 + 对外锚定**（`python -m policy_api.cli seal`）补上 Phase 4 "删尾部发现不了"的缺口 |
| 6 部署前准备 | `src/policy_api/app.py`（FastAPI 传输层：`create_app(runtime)`）、`src/policy_api/serve.py`（readiness 未过就**拒绝启动**）、依赖锁定 `requirements.lock`（fastapi / uvicorn）、`/v1/health/live` 与 `/v1/health/ready` 各答一个不同的问题 |
| （额外）| `src/policy_api/cli.py`（`serve` / `self-check` / `openapi` / `clients` / `smoke` / `seal`）、`src/policy_api/testing.py`（进程内调用与 ASGI 客户端）、`src/policy_api/probe.py`（HTTP Adapter：第二个协议消费者）、`tools/api_loop.py`（八个场景的闭环） |

### 实际新增与变化

| 位置 | 内容 |
| --- | --- |
| `src/policy_api/errors.py` | 新增：受控 `ErrorCode` 枚举 + `STATUS_BY_CODE`（状态码由错误码推导，调用方不能自定义 HTTP 状态）；`redact_detail` 保证错误细节单行限量 |
| `src/policy_api/models.py` | 新增：传输协议版本 `API_SCHEMA_VERSION = "1.0"`、`ContextDTO`（与 `PolicyContext` 一一对应但独立演进）、三个请求体、`ReadinessReport`；`DECISION_PAYLOAD_SCHEMA_VERSION` / `POLICY_GENERATION` 直接取自核心，**本包不许自己算一个版本** |
| `src/policy_api/config.py` | 新增：`ApiConfig`（服务身份 / 预算 / 限额 / 限流 / 租户 / 客户端 / 观测）；明文令牌一律拒绝加载 |
| `src/policy_api/services.py` | 新增：`TenantStore`（原子装配，单租户失败只记错误）、`LoadedTenant`（规则集按文件指纹热替换，永不出现半套规则）、`corpus_root`（语料清单的锚点独立解析） |
| `src/policy_api/runtime.py` | 新增：`ApiRuntime.handle`——认证 → 并发闸门 → 幂等 → 预算 → 分派 → 观测；闸门覆盖认证后的完整请求处理，所有失败路径收敛为结构化错误，没有任何"默认 allow"分支 |
| `src/policy_api/ops.py` | 新增：readiness 的逐租户检查（规则集 / 索引 / 验证器 / 观测日志）与指标鉴权（角色或 `metrics_clients`） |
| `src/policy_api/app.py` | 新增：FastAPI 应用；请求体校验只有一处（运行时的 DTO），路由上的"握手模型"只用于生成 OpenAPI |
| `api/policy-api.yaml`、`api/openapi.json` | 新增：部署配置（数据）与 OpenAPI 快照（改契约必须显式 `--write`） |
| `tests/fixtures/api/` | 新增：Phase 7 夹具（租户规则 `API-001.yaml`，说明见该目录 README） |
| `src/adapters/conformance.py` | 变化：`conformance_enforcer` 的判据从"它是不是 dsh"改成"它有没有声明工具注册表与已审核哈希"——任何接入 Phase 4 的 Adapter 都走同一条链路 |
| `tools/api_loop.py` | 新增：Phase 7 闭环（真端口 uvicorn；本地与 API 决定整份相等 / 两个协议消费者等价 / 超时 504 / 不可达阻断 / 幂等 / 跨租户 / readiness / 锚定） |
| `tools/phase_evidence.py` | 变化：`CURRENT_PHASE=7`，新增 `policy_api` 段（OpenAPI 版本、租户与客户端数量、自检结论、闭环结论） |
| `.github/workflows/phase-7.yml` | 替换 `phase-6.yml`：追加 API 自检、OpenAPI 快照、ASGI 契约测试与 API 闭环四步 |

### 请求处理链的形状（一次 HTTP 判定的十个位置）

    (1) 传输：FastAPI 读 Authorization、限制请求体、把 JSON 交给运行时
        → 非 JSON / 超大 / 坏 JSON → 400 / 413（不进入运行时）
    (2) 版本：api_version 必须出现且被支持
        → 缺失 → schema_version_missing；未知 → schema_version_unknown
    (3) 认证：Bearer 令牌 → sha256 → 客户端声明（常量时间比较）
        → 未知令牌 → 401；过期 → 401 token_expired
    (4) 边界：租户只来自令牌；项目来自上下文，必须落在令牌授权内
        → 越权租户 → 401；项目越权 → 403 project_not_allowed
    (5) 限流与并发：每（客户端，租户）令牌桶 + 在途上限
        → 429 rate_limited；在途满 → 503 policy_busy
    (6) 幂等：key + 请求摘要（不含凭据）与台账比对
        → 命中 → 原响应 + Idempotency-Replayed；同键换体 → 409
    (7) 预算：路由默认值，调用方只可要更小
        → 超时 → 504（evaluate_timeout / retrieve_timeout / validate_timeout）
    (8) 分派：policy.engine.evaluate / retrieval / validators.pipeline
        → 规则集不可加载 → 503 rule_set_unavailable；无索引 → 503 knowledge_unavailable；
          无验证器 → 503 validator_unavailable
    (9) 观测：脱敏 JSONL + 指标；写入失败 → 503 audit_unavailable（不返回决定）
    (10) 响应：决策载荷**原样透出**（API 不改写核心协议）+ 耗时头

### 与原始计划的偏差（都需要知道）

1. **首版索引是"离线构建、服务只读"的，不是"服务内建索引"。**
   计划允许"索引版本"出现在观测里，但没规定谁来建。实现选择：索引由
   `python -m retrieval.cli index` 离线构建，服务每次请求开一个只读句柄；
   readiness 会检查索引存在且完整。理由与 Phase 3 一致——索引是构建产物，
   `ChunkStore` 的连接不可跨线程共享，让服务在请求里重建索引既慢又把"读到半套索引"
   变成可能。
2. **客户端不能自带证据，也不能自带决策。**
   计划写"服务先验证调用者，再由 Policy Engine 判断业务动作"；实现把这条推到更远：
   `/v1/policy/evaluate` 的请求体里没有 evidence 字段（证据只能由服务端验证器流水线产出），
   `/v1/knowledge/retrieve` 的 `decision_ref` 只能指向**本服务算过的** `request_id`
   （且规则集世代必须一致），因此"自带一份 block/allow 载荷来给自己扩权"这条路不存在。
3. **指标端点不属于任何租户。**
   `/v1/ops/metrics` 是服务级事实，只要求认证 + 运维角色（`ops` / `service-admin` 或
   `metrics_clients`）。让它"必须有租户边界"会把服务级观测变成某个租户的私有物，
   而它本身不包含任何租户数据（只有计数、延迟分位与错误分类）。
4. **审计锚定是"发布链末值"，不是防篡改日志。**
   Phase 4 已写明：摘要链发现不了删尾部或整链重写。Phase 7 因此把
   `chain_digest`（覆盖序号与每条记录摘要）封成可对外发布的锚
   （`python -m policy_api.cli seal --out anchor.json`，`--verify` 校验）。
   锚一旦与日志放在同一个可写位置就失去意义——"放到哪里"是部署方的决定，
   不在本命令能力范围内，这一点写在这里以免被误读成"已经防篡改"。
5. **令牌是静态凭据，没有 OIDC / 签名与轮换。**
   计划要求"验证调用者、拒绝过期凭据"，实现用配置里声明的
   `token_sha256` + `expires_at` 满足这两条；真正的身份提供方、签名与轮换属于
   部署环境的事，本阶段不假装有（也因此没有 `audience` 字段可判——
   "错误 audience 被拒绝"这条以"令牌不属于该客户端/租户即 401"落地）。
6. **请求体只读一次，而且由服务端读。**
   路由**刻意不声明请求体参数**：FastAPI 会在运行依赖之前先把请求体解析成对象，
   于是"超大请求体"会先撞上框架的解析器（实测 200KB 的流式请求体会得到框架的 400，
   服务端的 413 永远没有机会执行）。现在请求体在**依赖**里读一次（按 `max_request_bytes`
   判断，声明型与流式都是 413 `body_too_large`），再自己解析 JSON——
   错误分类因此由服务端决定，而不是由框架版本决定。
7. **`/v1/knowledge/retrieve` 的 `context` 是必填、`query` 可选。**
   与 evaluate 一致：file / layer 必须显式声明，服务端不猜；查询来源是 `query` 或
   `context.task`，两者都没有就 400（不是"空结果"）。理由与检索层的三态一致——
   "没有结果"和"不知道该找什么"必须是两件事。
8. **框架的请求校验被刻意降到最低。**
   路由上的请求体模型是**按 DTO 程序化生成**的宽松握手模型（字段可选、未知字段忽略），
   它只用于生成 OpenAPI；真正的校验只有一处——运行时的 `EvaluateRequest` /
   `RetrieveRequest` / `ValidationRequest`（`extra="forbid"`）。
   否则"未知字段"会得到两种语义（框架的 422 与我们的 400），
   而错误分类是契约的一部分。
9. **`policy_version` 仍然不变。**
   Phase 7 没有改决策协议：`schema_version = "1.0"` / `policy_version = "phase-1"`，
   `tests/fixtures/decisions/` 原样未动。传输协议有自己的
   `API_SCHEMA_VERSION = "1.0"`，两者独立演进——"改一个字段"不等于"改规则语义"。
10. **HTTP Adapter 是第二个协议消费者，不是第二个 Agent 产品。**
   `src/policy_api/probe.py` 把规范事件经 **真实 HTTP** 送往 API，用来证明
   "同一套规则、两条路径、同一个决定"；它仍然声明 `read_only`：
   API 不执行工具，它只回答"允不允许"，受控执行仍在 Agent 侧。

### 独立交叉验证（Phase 7 收尾时做的，结论写在这里）

除了本仓库自己的测试，Phase 7 交付后做了一次**独立验证**：验证者只读仓库、自己写探针，
逐条试图证伪 14 个不变量（路由是否真的分开、两条路径的决定是否整份相等、
失败路径是否会给 allow、租户是否只来自令牌、客户端能否自带证据/决策、
请求体上限是否真的生效、令牌是否只以摘要存在、幂等语义、readiness 是否反映真实依赖、
契约快照是否真的是门禁、核心层是否不依赖框架、cwd 无关性、CLI 是否真的能跑、锚定能否发现删尾）。

结果：12 条通过；**2 条发现了真实缺陷**，都已修复并补了回归用例：

| 发现 | 现象 | 修复 |
| --- | --- | --- |
| 令牌明文可能落进观测日志 | 客户端把令牌回显进 `request_id` / `principal.subject` 时，脱敏只认"凭据长什么样"（`token=` / `Bearer ` / `sk-`），回显的原文被原样写入 JSONL | 认证处把令牌原文登记给观测层（`RequestLog.register_secret`），写日志前按**值**精确替换成 `<redacted-token>`；凭据只在内存里传递 |
| 幂等重放不是逐字节相同 | 台账写入时按 `sort_keys` 规范化，回读后键序变了，重放响应与首次响应"解析后相等、字节不同" | 带幂等键的响应统一按规范化键序返回（台账存同一份），"这次响应和上次一样吗"现在可以用字节回答 |

上表第二行（幂等重放）说的是**响应对响应**，与"本地引擎 vs 经 API"不是同一种主张：前者
两侧是同一份规范化序列化（`runtime._canonical_body`，`sort_keys=True` 只作用于带
`idempotency_key` 的请求），"字节相同"可达、也确实该用 `replayed.content == first.content`
断言；后者一侧是本地领域对象（`to_decision_dict()`）、另一侧是 HTTP 响应载荷里的
`decision`，两侧序列化入口不同、键序自然不同，能要求的只有**整份 JSON 值相等**——字段顺序
不属于契约（`api/README.md` 与 `api/openapi.json` 都没把它写成契约，`_canonical_body`
的注释也这么说），拿字节去比这两者只会得到一条永远失败的断言。`tools/api_loop.py`
比的就是整份相等。

同一轮验证还发现并修掉了三条实现缺口：

1. **索引文件缺失被重建成空库**：`ChunkStore(path)` 默认 `create=True`，索引不见了会被
   悄悄建成空库，检索于是返回 200 `empty/no_results`——"索引没了"被报成"没有命中"。
   现在用 `create=False`（索引是构建产物，服务只读它），缺失即 503 `knowledge_unavailable`。
   `runtime.py` 里那段 `if status == "unavailable": status = 200` 的死分支也一并删掉：
   三个检索状态（ok / empty / unavailable）现在各自对应 200 / 200 / 503。
2. **日志里 `trace_id` 恒为 null**：`_record` 从不接收 trace，与"观测记录 trace ID"不符；
   现在信封里的 `trace_id` 会一路传到请求日志。
3. **两条限额没生效**：`max_context_bytes` / `max_prompt_chars` 只在配置里定义过，
   运行时不读。现在逐字段检查（file / module / task / git_diff），超限 413 `body_too_large`
   ——"请求体不超过 X"描述不了"单个字段被撑爆"。另外文档里那三个 POST 路由不再声明 422：
   运行时把所有校验失败映射成 400，文档里留一个永远不会返回的状态码等于让调用方白写分支。

验证者提出的**已知边界**（不改，写在这里）：多选题性质的"猜边界"不在本阶段——
真实 uvicorn 监听端口的行为、多进程/多 worker 下的文件锁与限流、metrics 与并发竞态
都只做了单进程验证；没有 `Content-Type` 头的 JSON 请求会被接受（只拦"存在且非
application/json"），这是有意的宽松，不是遗漏。

### 已知边界（不假装做到）

- **没有 TLS、没有反向代理、没有连接池调优**：`uvicorn` 直接监听 127.0.0.1，
  这些属于部署环境；仓库内能证明的是"认证、隔离、预算、幂等、观测"的存在性与失败语义。
- **超时是"调用方不再等待"，不是"工作已经停止"**：Python 没有可移植的线程取消，
  超时后工作线程仍会把这一次判定跑完，其结果被丢弃。观测里记 `outcome=timeout`。
- **指标只存在于进程内**：没有外部后端、没有持久化，重启即归零；
  `/v1/ops/metrics` 是"当前进程的自述"，不是历史报表。
- **"慢客户端不会耗尽工作线程"是有限度的**：并发闸门用
  `BoundedSemaphore(max_concurrency)` + 0.5s 获取超时，超过就 503 `policy_busy`；
  它保证的是"不会无限排队"，不是"服务端一定有容量"。
- **规则集热替换是"整份替换 + 指纹检测"**：规则目录里新增文件、改内容或改时间戳
  都会被下一次请求发现；但不存在"跨请求事务"——两个请求可以合理地用不同世代的规则集，
  各自内部仍然是完整的一套（`rule_set_hash` 会如实反映出来）。

### 验收证据

```powershell
$env:PYTHONPATH = "src"
python -m policy_api.cli self-check                 # 装配 / readiness / 传输契约自检
python -m policy_api.cli openapi --check            # OpenAPI 快照未漂移（CI 门禁）
python tools/api_loop.py                            # 八个场景的 API 闭环
python tools/phase_evidence.py                      # 阶段证据（含 policy_api 段）
```

### 退出条件对照

| 退出条件 | 证据 |
| --- | --- |
| OpenAPI、认证、隔离和版本策略有自动化测试 | `tests/contract/test_api_protocol.py`（快照比对 + 版本钉死 + 核心层不依赖框架）、`tests/security/test_api_adversarial.py`（认证、越权、不泄露存在性） |
| 至少两个 Adapter 通过 API 契约测试 | `tools/api_loop.py` 的 "两个协议消费者等价"：`generic-json`（进程内）与 `http-api`（经 API）跑同一组语义场景，并逐场景比对决定 |
| 服务异常不会返回默认 allow | 超时 504 / 不可达阻断 / 规则集不可用 503 / 观测不可写 503，四个场景都断言"没有任何 allow" |
| health/readiness、限流、超时和审计可观察 | `/v1/health/live` 与 `/v1/health/ready`、`/v1/ops/metrics`（p50/p95/p99 + 限流计数）、请求级 JSONL、`seal --verify` |
| 核心库仍可不启动 API 独立运行 | `tests/contract/test_api_protocol.py` 断言 `src/policy`（以及 retrieval / validators / enforcement）不导入 fastapi/starlette；`python -m policy.check` 全链路不经过 API |
