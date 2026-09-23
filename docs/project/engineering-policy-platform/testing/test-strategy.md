# 测试策略

## 目标

测试不是最终阶段，而是每个阶段的交付物。所有 Policy Decision 都应由可重放输入和结构化证据支持。

## 测试层级

| 层级 | 验证内容 | 外部依赖 |
| --- | --- | --- |
| 单元测试 | 模型、解析、匹配、严重级别、规范化 | 无 |
| 契约测试 | Adapter、Validator、API 是否遵循核心协议 | 使用固定 fixture 或 fake |
| 集成测试 | SQLite、FTS5、真实 CLI、Hook、HTTP 边界 | 仅阶段内必要依赖 |
| 端到端测试 | Agent 事件到 allow/block/repair 的完整闭环 | 使用受控沙箱和假执行器优先 |
| 对抗测试 | 注入、越权、跨租户、审批绕过、工具滥用 | 无真实密钥和生产数据 |
| 非功能测试 | 性能、并发、超时、日志失败、资源耗尽 | 可重复的固定负载 |

## 固定测试资产

未来实现时建议建立：

```text
tests/
├── fixtures/
│   ├── policies/
│   ├── contexts/
│   ├── agent_events/
│   ├── source_files/
│   ├── retrieval_corpus/
│   └── adversarial/
├── unit/
├── contract/
├── integration/
├── e2e/
└── security/
```

每个 fixture 必须说明：用途、预期结果、关联规则、是否包含模拟敏感数据。禁止加入真实凭据、用户数据或生产日志。

## 每条规则的最小测试集

1. 正例：合规输入得到允许；
2. 反例：明确违规输入得到预期严重级别；
3. 边界：缺失字段、大小写、路径分隔符、空集合和多规则冲突；
4. 范围：规则只影响声明的语言、模块、层或操作；
5. 稳定性：相同输入得到相同排序、消息和证据；
6. 失效：执行器、检索或验证器不可用时符合失败策略；
7. 回归：每个已修复缺陷先加入能复现它的 fixture。

## Adapter 一致性套件

所有 Agent Adapter 必须复用同一组契约用例：

- 能把等价事件映射成等价 `PolicyContext`；
- 不猜测安全关键字段；
- 保留 `request_id`、`trace_id` 和主体信息；
- block 时不调用真实执行器；
- allow 时执行器只调用一次；
- 重复事件不重复执行；
- 未知协议版本和未知决策值拒绝处理；
- 工具返回中的指令性内容不会变成系统指令。

## 检索评测

使用 [仓库数据源](../02-repository-data-sources.md) 中的固定查询集，保存：

- `precision@k` 与 `recall@k`；
- 首个正确文档排名；
- 返回片段的来源和哈希；
- 无结果、删除文档和权限变化场景；
- prompt injection、跨租户和缓存泄漏结果。

最初以 FTS5 为基线。只有当向量检索在固定评测集上提供可重复收益，才加入 Embedding 或 Qdrant。

## 安全与对抗测试

参考仓库内 OWASP Agent、RAG 和 MCP 文档，至少覆盖：

- 用户或检索内容尝试覆盖系统策略；
- 未授权工具调用和参数扩权；
- 低权限会话访问高权限工具；
- 恶意内容进入长期记忆或索引；
- 日志、引用、工具参数和最终输出泄露敏感字段；
- 递归工具链、无限重试和成本失控；
- 审批过期、参数变化和审批重放；
- 一个 Agent 诱导另一个 Agent 越过信任边界；
- 检索失败、Validator 超时和 Policy API 不可用时的 fail-closed 行为。

## 审计证据

每次阶段验收至少保存：

```json
{
  "phase": 0,
  "implementation_version": "git-sha-or-local-revision",
  "rule_set_hash": "sha256:...",
  "test_suite": "tests/unit",
  "result": "pass",
  "cases": 12,
  "failures": 0,
  "artifacts": ["test-report.xml"],
  "timestamp": "RFC3339"
}
```

报告中不得记录密钥、完整 Prompt、隐私数据或未经脱敏的工具参数。

## 未来命令约定

正式进入 Python 实现后，命令应由 `pyproject.toml` 和根 README 定义并保证可执行。推荐最终收敛为：

```powershell
python -m pytest tests/unit -q
python -m pytest tests/contract -q
python -m pytest tests/integration -q
python -m pytest tests/security -q
python -m pytest
```

这些命令目前只是目标接口；在依赖清单、锁文件和 CI 尚未创建前，不作为当前仓库的可运行命令。

## 阶段门禁

只有同时满足以下条件才能进入下一阶段：

- 本阶段所有必需测试通过；
- 失败路径已被测试而不是仅靠代码阅读；
- 接口、规则和证据格式有文档；
- 新增依赖有必要性说明并已锁定版本；
- README 与实际命令同步；
- 没有被跳过或静默放宽的安全测试；
- 阶段验收证据可被另一位开发者重放。
