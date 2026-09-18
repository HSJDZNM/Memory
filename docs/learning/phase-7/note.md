# Phase 7 学习手册 · 任务与对象关系

## 这一阶段要完成的三件事

1. **把核心能力服务化，而不是复制它**：API 只做"协议 → 领域模型 → 协议"，
   判定仍然只有 `policy.engine.evaluate` 一条路径——同一个上下文经本地 SDK 与经 API
   必须得到**逐字节相同**的决策载荷；`src/policy/` 与其余核心层禁止导入 Web 框架；
2. **把部署边界变成数据**：租户（项目根 / 规则目录 / 检索索引 / 验证器配置 / 观测日志）、
   客户端（令牌 sha256 + 可用租户/项目/角色/有效期）、预算、限流与幂等 TTL 全部写在
   `api/policy-api.yaml`；配置里出现明文令牌一律拒绝加载；
3. **失败关闭没有例外**：未知版本、未知字段、未认证、跨租户、超预算、限流、
   依赖不可用（规则集 / 索引 / 验证器）、观测日志不可写，全部返回结构化错误码；
   超时是 504、服务不可达是 503，**没有任何路径默认 allow**。

## 对象清单

| 对象 | 位置 | 职责 |
| --- | --- | --- |
| `API_SCHEMA_VERSION`、`ApiEnvelope`、`ContextDTO`、三个请求体 | `src/policy_api/models.py` | 传输协议（DTO）：信封 + 载荷，`extra="forbid"` |
| `ErrorCode`、`STATUS_BY_CODE`、`ApiError`、`error_payload` | `src/policy_api/errors.py` | 受控错误码 → 固定 HTTP 状态；错误细节单行限量 |
| `ApiConfig`、`TenantSpec`、`ClientSpec`、`load_api_config` | `src/policy_api/config.py` | 部署配置（数据）；明文令牌拒绝加载 |
| `authorize`、`AuthContext` | `src/policy_api/auth.py` | 令牌 → 客户端 → 租户/项目边界；`token_ref` 是 sha256 前 12 位 |
| `TenantStore`、`LoadedTenant` | `src/policy_api/services.py` | 原子装配租户；规则集按文件指纹整份热替换 |
| `ApiRuntime.handle` | `src/policy_api/runtime.py` | 认证 → 限流/并发 → 幂等 → 预算 → 分派 → 观测 |
| `budget_for`、`run_with_budget` | `runtime.py`、`timeout.py` | 墙钟预算；超时返回 `(None, timed_out=True)` |
| `IdempotencyLedger`、`request_digest` | `src/policy_api/idempotency.py` | 每租户一份台账：同键同摘要 → 原响应；同键换体 → 409 |
| `RequestLog`、`Metrics`、`seal_audit` / `verify_seal` | `src/policy_api/observability.py` | 脱敏 JSONL + 进程内指标 + 摘要链锚定 |
| `readiness_report`、`metrics_token_ok` | `src/policy_api/ops.py` | 逐租户可服务性检查；指标端点鉴权 |
| `create_app` | `src/policy_api/app.py` | FastAPI 传输层（本手册不起端口，只用进程内调用） |
| `build_runtime` / `call` | `src/policy_api/testing.py` | 进程内调用助手：不开端口走完整链路 |
| `api/policy-api.yaml`、`api/openapi.json` | `api/` | 部署配置与传输契约快照 |
| `tools/api_loop.py` | `tools/` | API 闭环（真端口）：本地/API 一致、幂等、跨租户、readiness、锚定 |

## 对象关系

```text
HTTP 请求（JSON + Authorization: Bearer）
      │
      ▼
policy_api.models.*（DTO：信封 + context / query / target）
      │  协议校验：api_version 必须显式出现且受支持；未知字段 400
      ▼
ApiRuntime.handle(route, payload, authorization)
      ├─ auth.authorize        令牌 sha256 → 客户端 → 租户/项目边界（401 / 403 / 404）
      ├─ RateLimiter           每（客户端，租户）令牌桶（429）；并发闸门（503 policy_busy）
      ├─ IdempotencyLedger     同键同摘要 → 原响应；同键换体 → 409；台账不可用 → 503
      ├─ budget_for / run_with_budget   超时 → 504（没有结论，不是 allow）
      ▼
policy.engine.evaluate / retrieval / validators.pipeline（**核心一行未改**）
      │  ValidationResult：决策载荷原样透出，API 不改写核心协议
      ▼
observability：脱敏 JSONL + 指标 + 摘要链（seal_audit / verify_seal）
      │
      ▼
响应（决策载荷 + X-Elapsed-Ms）／结构化错误（error_payload）
```

## 三条必须记住的判断

1. **API 是传输边界，不是第二份业务逻辑。** 判定只有 `policy.engine.evaluate` 一条
   路径，本地与经 API 的决定逐字节相同；`src/policy/` 禁止导入 Web 框架，
   核心仍然可以脱离 API 独立运行。
2. **信任只有三条。** 租户只来自令牌（请求体里的 `tenant` 只是提示）、客户端不能
   自带证据或决策（`decision_ref` 只能指向本服务算过的 `request_id`，
   且规则集世代必须一致）、服务身份不替用户扩权（认证成功 ≠ 允许某个工具，
   业务动作仍由 Policy Engine 判定）。
3. **两套版本各自演进。** `API_SCHEMA_VERSION`（传输协议）与
   `policy.models.SCHEMA_VERSION` / `POLICY_VERSION`（决策协议与世代名）
   无关；后者只能从核心取值，`policy_api` 不许自己算一个。

## 手册里照实写着的一个实现缺陷

租户的 `validators` 是配置里的**相对路径**，而
`policy_api.services.LoadedTenant.validators()` 把它原样交给
`validators.registry.load_config`，后者按**进程工作目录**解析它。租户的其余路径
（项目根 / 规则目录 / 检索索引 / 观测日志）都由 `TenantStore._resolve` 按
`--root` 锚定，只有这一处漏了。后果有两个：

- 从非仓库根目录启动时，声明了 `validators` 的租户会在 readiness 里被如实报成
  "验证器不可服务"，`validate` 路由得到 `validator_unavailable`；
- 如果进程工作目录下恰好存在同名的相对路径，加载到的会是**另一份**注册表——
  "配置里的路径必须锚定"这条纪律被破坏了一处。

手册把这个现象**显示出来**（第 8 节打印达标的检查项与未通过的检查），而不是改配置绕过。
可能的修法：让 `LoadedTenant.validators()` 也走一次
`TenantStore._resolve`，或让 `load_config` 把相对路径按 `root` 解析。
