# Policy API 的部署数据（`api/`）

```text
api/
├── policy-api.yaml   # 部署配置：服务身份、预算、限额、租户、客户端（数据，不是代码）
└── openapi.json      # 传输契约快照：由应用生成，改契约必须显式评审
```

## 这份配置决定什么

| 段落 | 决定 | 不知道就会怎样 |
| --- | --- | --- |
| `limits` | 请求体 / 响应 / 上下文上限、在途并发 | 超大请求体、慢客户端把工作线程占满 |
| `budgets` | 每条路由的墙钟预算（毫秒） | "下游卡住"会变成"请求一直挂着"，而不是显式 504 |
| `rate_limit` | 每个（客户端，租户）的令牌桶 | 单个凭据能把服务打满 |
| `tenants` | **边界**：项目根、规则目录、检索索引、验证器配置、观测日志 | 没有边界的租户不装配（readiness 会失败） |
| `clients` | 令牌 sha256、可用的租户/项目、角色、有效期 | 没有客户端就没人能调用；明文令牌一律拒绝加载 |
| `audit` | 观测日志落点 | 日志不可写时请求失败关闭（`audit_unavailable`） |

**相对路径的锚点**：先按 `--root`（默认仓库根）解析，解析结果不存在时再按
**配置文件所在目录**解析。于是"把配置和它引用的目录打成一个部署包"是可行的，
而"仓库根优先"这条安全边界没有被改。

## 令牌

配置里**只有 sha256**，没有明文：

```powershell
"my-real-token" | python -m policy_api.cli clients --hash
# 把输出的 64 位十六进制贴进 clients[].token_sha256
python -m policy_api.cli clients          # 列出客户端（只显示摘要前 12 位）
```

本仓库的 `policy-api.yaml` 里几条令牌（`local-dev-token` / `dsh-agent-token` /
`ops-monitor-token`）是**演示环境**的固定值，同时写在 `tests/fixtures/api/README.md` 里，
供测试与闭环复现；它们不是真实凭据，也不指向任何真实系统。

## 本地怎么跑

```powershell
$env:PYTHONPATH = "src"

python -m policy_api.cli self-check                 # 装配 / readiness / 传输契约自检
python -m policy_api.cli openapi --check            # 契约快照是否漂移（CI 门禁）
python -m policy_api.cli smoke --token local-dev-token
python -m policy_api.cli serve                      # 默认 http://127.0.0.1:8088

# 下面的令牌是仓库公开的**演示值**，sha256 见 tests/fixtures/api/README.md
curl.exe -s -X POST http://127.0.0.1:8088/v1/policy/evaluate ^
  -H "Authorization: Bearer local-dev-token" ^  # secret-scan: allow（仓库公开的演示令牌）
  -H "Content-Type: application/json" ^
  -d "{\"api_version\":\"1.0\",\"request_id\":\"demo-1\",\"tenant\":\"local-dev\",\"principal\":{\"subject\":\"alice\",\"roles\":[\"developer\"]},\"context\":{\"file\":\"examples/bad_controller.py\",\"layer\":\"controller\"}}"
```

**启动即自检**：`serve` 会先跑一次 readiness，没通过就**拒绝启动**并把原因打出来——
一个"起来了但没有规则可服务"的进程比启动失败更危险。

## 请求的形状

所有 `POST` 路由共用同一个信封：

```json
{
  "api_version": "1.0",
  "request_id": "req-1",
  "tenant": "local-dev",
  "trace_id": "trace-1",
  "idempotency_key": "optional-key",
  "budget_ms": 500,
  "principal": {"subject": "alice", "roles": ["developer"]},
  "context": {"file": "src/shop/order_service.py", "layer": "service", "language": "python"}
}
```

- `api_version` **必须显式出现**：缺失与未知是两个不同的错误码；
- `tenant` 是"我想用哪个"的提示，最终以**令牌授权的集合**为准（越权即拒绝）；
- `budget_ms` 只能**调小**路由默认值，调大一律 503 `request_budget_exceeded`；
- 未知字段一律 400（`extra="forbid"`），未知操作枚举同样 400；
- `context` 是**三个路由都必需**的：file / layer 这些安全关键维度必须由调用方显式声明，
  服务端不推断，也不允许"没有上下文就按默认集合检索"；
- `/v1/knowledge/retrieve` 的查询来源是 `query`（自由文本）**或** `context.task`，
  两者至少要有一个——都没有不是"空查询"，而是"不知道该找什么"，按 400 拒绝
  （返回一个 empty 结果会被读成"查过了，没有规范"）。

## 错误响应

固定形状，且**不泄露资源是否存在**：

```json
{"error": {"code": "evaluate_timeout", "detail": "…", "retryable": true,
           "request_id": "req-1", "trace_id": null}}
```

状态码由错误码推导（`src/policy_api/errors.py` 的 `STATUS_BY_CODE`）。
几条关键语义：

| 错误码 | HTTP | 含义 |
| --- | --- | --- |
| `unauthenticated` / `token_expired` | 401 | 令牌不认识或已过期；"租户不存在"、"越权租户"对外同样是 401 |
| `project_not_allowed` | 403 | 凭据没有被授权这个项目边界 |
| `rate_limited` | 429 | 令牌桶耗尽 |
| `idempotency_key_conflict` | 409 | 同一个 key 换了请求体 |
| `body_too_large` | 413 | 超过 `max_request_bytes` |
| `evaluate_timeout` / `retrieve_timeout` / `validate_timeout` | 504 | 预算耗尽：**没有结论**，不是 allow |
| `rule_set_unavailable` / `knowledge_unavailable` / `validator_unavailable` | 503 | 依赖不可用：失败关闭 |
| `audit_unavailable` | 503 | 观测日志不可写：决定不返回 |

## 观测与锚定

- 请求级 JSONL：`audit.path`（默认 `.tmp/phase-7-api/audit.jsonl`），字段见
  `src/policy_api/observability.py`；密钥样式、绝对路径、控制字符在写入前脱敏；
  单条超过上限直接失败关闭，不写半截证据；
- 指标：`GET /v1/ops/metrics`（需要 `ops` / `service-admin` 角色或 `metrics_clients`），
  给出按路由的请求数、错误数、p50/p95/p99、限流与超时计数；
- **对外锚定**（补 Phase 4 摘要链的缺口）：

  ```powershell
  python -m policy_api.cli seal --out anchor.json      # 封出链末值
  python -m policy_api.cli seal --verify anchor.json   # 日志被删尾/改写则退出 1
  ```

  锚必须放到**日志写不到的地方**才有意义；"放在哪"是部署方的决定。

## 改契约的流程

1. 改 `src/policy_api/models.py`（DTO）或 `app.py`（路由）；
2. `python -m policy_api.cli openapi --check` 会失败并逐条列出差异——
   这是**故意的**：契约变化必须被看见；
3. 确认无误后 `python -m policy_api.cli openapi --write` 更新 `api/openapi.json`，
   在同一个提交里说明"为什么变"；
4. 删字段或改语义 = 新的 `API_SCHEMA_VERSION`，不是"顺手改一下"。
