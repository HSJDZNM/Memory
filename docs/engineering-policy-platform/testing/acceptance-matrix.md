# 阶段验收矩阵

| 阶段 | 必需产物 | 必需测试 | 可观察证据 | 进入下一阶段的条件 |
| --- | --- | --- | --- | --- |
| 0 | Rule、Loader、最小 Engine、CLI | 解析、重复 ID、正反例、退出码 | 相同输入稳定产生 PASS/FAIL | CLI 与单元测试均可重放 |
| 1 | Context、Scope、Severity、Decision | 路径规范化、范围矩阵、冲突与排序 | 每个决定列出命中/跳过规则原因 | 决策协议稳定且无 Agent 类型 |
| 2 | dsh Adapter、Hook、假执行器 | 映射契约、block 不执行、allow 一次 | 原始事件与标准上下文可关联 | 一个真实 dsh 流程在沙箱通过 |
| 3 | 文档摄取、FTS5、Context Builder | 幂等索引、固定查询集、删除、注入、失败关闭 | 查询 → chunk → 来源完整链路 | 基线指标固定且无无依据回退 |
| 4 | Pre/Post Enforcement、审计 | 参数绑定、重放、超时、Post 失败、工具返回注入 | 决策 → 执行 → 验证同一 trace | 高风险写操作无法绕过策略 |
| 5 | Validator Pipeline | golden fixture、工具缺失、超时、结果归一化 | 违规定位到文件/行/规则 | 确定性违规无需 LLM 判断 |
| 6 | 多 Agent Adapter、统一事件 | 全 Adapter 一致性、隔离、重复事件 | 等价事件产生等价决定 | 新增 Adapter 不修改核心层 |
| 7 | 版本化 Policy API | Schema、鉴权、租户隔离、并发、超时 | 请求、主体、规则版本、决定可追踪 | 两个不同 Adapter 通过 API 使用 |
| 8 | LangGraph 消费者 | 分支、循环上限、checkpoint、恢复、审批 | 每个节点与 Policy trace 关联 | 编排可替换且平台仍独立运行 |

## Phase 0 的硬限制

Phase 0 不引入 LangGraph、Qdrant、Neo4j、Kafka、FastAPI、MCP、多 Agent 或复杂 RAG。它只证明：

```text
YAML Rule → Rule Loader → Policy Engine → PASS / FAIL → Test Evidence
```

## Phase 3 的硬限制

Phase 3 只证明"找到什么值得告诉 Agent"，不证明任何执行能力：

```text
离线镜像 + 摄取清单 → 章节分块 → SQLite FTS5 → 带来源与哈希的片段 → 受控预算的 Engineering Context
```

检索层没有工具执行权限：它不调用工具、不产生 allow/block、不改变策略；相似度分数只用于内部排序。
"没有结果""没有权限""检索不可用"是三个显式状态，任何一条都不能被当作"没有规范"而放行。

## Phase 4 的硬限制

Phase 4 只证明“受控工具的执行被授权与验证”，不证明“代码质量”：

```text
Tool Registry（数据） → Action Request（action_hash） → Pre-check（权限 / 白名单 / 审批 / 规则 / 限流 / 审计）
→ 短时效 grant → 受控执行器（一次）→ Post-check（哈希 / diff / 退出码 / 语法）→ 审计链终态
```

本阶段**不**引入：Lint / 类型检查 / 测试执行等代码验证器（Phase 5）、多 Agent 适配器（Phase 6）、
版本化 API 与租户隔离（Phase 7）、上层编排（Phase 8）；
执行器的“回滚”只覆盖声明了 `file_snapshot` 且由平台自己执行的文件动作，
委托给 Agent 运行时执行的动作只能给出 `unsupported`，绝不假装可撤销。

## 发布级总门禁

平台进入实际 Agent 写操作链路前，还必须满足：

1. 对抗测试覆盖 prompt override、越权、审批绕过和工具滥用；
2. 密钥扫描确认规则、fixture、日志和报告无真实敏感数据；
3. Policy、Validator 或 API 故障不会静默放行高风险动作；
4. 所有 Adapter 通过同一契约套件；
5. 决策、规则版本、检索来源和执行结果可审计；
6. 回滚或禁用新规则不会破坏既有规则集；
7. 文档中的安装、测试和运行命令已在干净环境验证。
