# Phase 7：Policy API

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

通过后进入 [Phase 8](phase-8-langgraph-orchestration.md)。
