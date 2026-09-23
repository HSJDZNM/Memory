# Phase 3 规范检索：对象与关系

面向人的"这一阶段到底有什么"。讲三件事：**要解决什么问题**、**有哪些对象**、**它们之间是什么关系**。
想看代码跑起来什么样，读同目录的 `walkthrough.ipynb`；想知道为什么这么设计，读
`docs/project/engineering-policy-platform/phases/phase-3-retrieval.md`。

## 1. 这一阶段解决什么问题

Phase 0-2 之后，系统已经能在工具执行之前说"不行"。但"不行"之外，Agent 还需要知道"该怎么做"：
代码评审要看什么、写到什么程度算小变更、"检索失败该怎么办"这种专业判断写在哪份官方文档里。

这些答案已经在仓库里了（Google / GitLab / OWASP / PEP / .NET 的离线镜像），
Phase 3 的任务是**把它们变成可检索、可追溯、长度可控的参考资料**，交给 Agent。
它明确**不**做授权、不执行工具、不调用 LLM。

一句话边界：**检索回答"找到什么值得告诉 Agent"，授权与执行仍然是别人的事。**

## 2. 对象清单

### 2.1 语料侧（数据）

| 对象 | 是什么 | 关键字段 |
| --- | --- | --- |
| 数据集 CorpusDataset | 一组同源、同许可的镜像文档 | `name`、`mirror`、`license`、`tier`、`visibility`、`entries` |
| 摄取清单 CorpusManifest | `knowledge/corpus.yaml` 的内存形态 | `version`、`policy`、`datasets`、`quarantine`、`rule_sources` |
| 入口 ResolvedEntry | 一个已解析的文档：与镜像 manifest 对齐后的元数据 | `source_path`、`source_url`、`manifest_sha256`、`tier`、`visibility` |
| 检索策略 CorpusPolicy | 预算与门槛（分块、查询、Context） | `max_chunk_chars`、`context_budget_chars`、`vector_min_similarity` |
| 术语表 ExpansionLexicon | 受控中英术语映射（跨语言词法桥接） | `terms[].zh` / `terms[].en` |

### 2.2 存储侧（可重建的产物）

| 对象 | 是什么 | 关键字段 |
| --- | --- | --- |
| 文档 DocumentRecord | 一份被摄取的文档 | `document_id`、`content_hash`、`manifest_hash`、`tier`、`license` |
| 片段 ChunkDraft / ChunkRecord | 一段**原文**及其结构信息 | `chunk_id`、`heading_path`、`heading_anchor`、`text_hash`、`revision` |
| 索引 run IndexRunRecord | 一次摄取的台账 | `run_id`、`status`、`input_hash`、各项计数 |
| 隔离 QuarantinedChunk | 已知恶意片段 | `chunk_id`、`text_hash`、`reason` |
| 规则溯源 RuleSourceRow | 规则版本 ← 来源 chunk | `rule_id`、`rule_version`、`chunk_id` |

### 2.3 检索侧（一次查询的生命周期）

| 对象 | 是什么 | 关键字段 |
| --- | --- | --- |
| 检索请求 RetrievalQuery | 自由文本 + 受控字段 | `text`、`file`、`language`、`module`、`datasets`、`limit` |
| 查询计划 QueryPlan | 规范化结果：词项、过滤条件、可重放的 FTS 表达式 | `terms`、`expanded_terms`、`fts_expression` |
| 权限范围 AccessScope | 主体 + 允许的数据集（+ 是否允许受限数据集） | `subject`、`datasets`、`allow_restricted` |
| 命中 RetrievedChunk | 一条结果：来源、位置、排名、方式、原文 | `rank`、`score`、`method`、`text_hash` |
| 检索结果 RetrievalResult | 一次检索的完整结论 | `status`、`reason`、`index_version`、`results` |

### 2.4 上下文侧（交给 Agent 的东西）

| 对象 | 是什么 | 关键字段 |
| --- | --- | --- |
| 策略事实 PolicyFact | 来自 Policy Engine 的权威片段（不是检索结果） | `rule_id`、`severity`、`message` |
| 参考片段 ContextSnippet | Context 里的一段参考，带引用 ID | `citation_id`、`source_path`、`text_hash` |
| Engineering Context | 最终文本块 | `status`、`budget_chars`、`used_chars`、`citations` |

## 3. 对象之间的关系

### 3.1 主链路

```text
knowledge/corpus.yaml
   │  load_corpus（与镜像 manifest 对齐：URL / 标题 / sha256 / 许可）
   ▼
ResolvedEntry ──chunk_document──▶ ChunkDraft ──ingest──▶ documents + chunks + chunks_fts
   （front matter / 标题路径 / 代码块原子 / 预算与截断）        （index_runs 记台账，generation 递增）
                                                              │
RetrievalQuery ──build_plan──▶ QueryPlan ──FtsRetriever──▶ RetrievalResult（来源 + 哈希 + 排名）
   （文本 → 受控词项 + 术语扩展）        ▲                     │
                                       │                     ▼
                             AccessScope（权限只来自这里）  ContextBuilder
                                                              │
PolicyFact（来自 Policy Engine）───────────────────────────────▶ EngineeringContext
                                                              （策略事实在前，参考在后，总长 ≤ 预算）
```

### 3.2 三条容易混淆的边界

1. **tier ≠ 权限**：`tier`（policy / guidance / reference）只决定 Context 里的排序优先级；
   `visibility` 才决定谁能检索，而且必须由调用方在 `AccessScope` 里显式授予。
2. **"没有结果" ≠ "检索不可用"**：`empty / no_results` 是"知识库里确实没有"，
   `empty / access_denied` 是"你没权限"，`unavailable` 是"检索本身坏了"。
   只有第三种意味着"不能答"，但它同样不能变成"用模型记忆答"。
3. **分数不是授权信号**：`score` 只用于排序，Policy Engine 看不到它；
   命中一条高分片段不代表这个动作被允许。

### 3.3 稳定性关系（为什么可以重建索引）

```text
document_id = f(dataset, source_path)          # 重爬不换 ID，换数据集就是另一份文档
chunk_id    = f(document_id, 锚点, 片段序号)     # 同一段原文重建后仍是同一个 ID
text_hash   = sha256(chunk 原文)               # 内容变化只影响它自己
revision    = 该行被改写的次数                  # 没变的 chunk 保持 revision 不变
index_version = f(schema, generation, 输入指纹)  # 一变则缓存失效
```

## 4. 本阶段明确不做什么

- 不执行工具、不产生 allow / block、不改变任何策略；
- 不调用 LLM、不联网、不引入向量数据库：embedding 只是**可替换端口**，
  确定性本地实现用于对照评测，且评测显示它没有跑赢 FTS5，因此没有进入默认链路；
- 不把检索结果当作系统指令：参考区有明确边界，片段里的指令性文本只是数据；
- 不提交索引库：`.tmp/retrieval/index.sqlite3` 是构建产物，随时可以重建。

## 5. 想继续往下读

| 想知道 | 去哪 |
| --- | --- |
| 每步跑起来是什么样 | `walkthrough.ipynb`（或 `walkthrough.py`） |
| 为什么这样设计、偏差在哪 | `docs/project/engineering-policy-platform/phases/phase-3-retrieval.md` 的实施记录 |
| 语料与词表怎么维护 | `knowledge/README.md` |
| 基线数字怎么复现 | `python tools/retrieval_eval.py --method both` |
