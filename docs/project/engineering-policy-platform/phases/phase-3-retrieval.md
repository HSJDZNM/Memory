# Phase 3：规范检索

## 目标

从仓库已有离线文档中检索与任务相关的规范片段，并生成带来源、长度受控的 Engineering Context。RAG 只负责“找到什么值得告诉 Agent”，不负责授权或执行。

## 渐进实现顺序

### 1. 建立摄取清单

先只选择 [仓库数据源](../02-repository-data-sources.md) 中的少量权威入口：Google 评审、GitLab 评审、OWASP Agent/RAG/MCP、PEP 8/257 和 .NET 指南。记录数据集、许可、manifest 哈希和摄取时间。

### 2. 定义存储模型

```text
documents(id, dataset, source_path, source_url, content_hash, license)
chunks(id, document_id, heading_path, ordinal, text, text_hash)
rules(id, version, source_chunk_id)
index_runs(id, started_at, completed_at, input_hash, status)
```

文档与 chunk ID 必须稳定生成，使重建索引后仍可比较来源。

### 3. 实现章节分块器

- 去除 front matter，但元数据进入 documents；
- 标题路径随 chunk 保存；
- 代码块不在中间切断；
- 设置最大字符或 token 预算，并记录截断；
- 空章节、重复标题和超长代码块有明确处理；
- chunk 文本不解释、不改写原文。

### 4. 建立 SQLite FTS5 基线

先实现关键词查询、字段过滤和稳定排序。查询由 task、file、language、module、operation 等受控字段构造，不把原始用户输入直接拼成 SQL 或 FTS 表达式。

### 5. 实现 Retriever 接口

返回 `chunk_id`、`document_id`、来源、标题路径、排名、检索方式和文本。相似度分数只用于内部排序，不作为授权信号。

### 6. 实现 Context Builder

Context Builder 负责去重、按规则优先级重排、限制总长度，并将片段包装为“参考资料而非系统指令”。每个片段必须保留引用 ID。

### 7. 评估是否需要 Embedding

只有 FTS5 在固定查询集上的可解释基线记录完成后，才实现可替换的向量检索端口。先使用本地或可固定版本的 embedding；只有数据量、并发或运维需求明确时才引入 Qdrant。

## 测试步骤

### 摄取与索引测试

- 同一 manifest 连续摄取两次，不产生重复 document/chunk；
- 单文件内容变化只替换相关 chunk；
- 删除源文件后，对应 chunk 不再可检索；
- 中断的 index run 不被标记为成功；
- 破损 Markdown、重复标题和超长代码块得到稳定结果；
- source path、URL、license 和 hash 不丢失。

### 查询安全测试

- 引号、括号、FTS 操作符和超长输入不会形成注入；
- 原始用户输入先规范化并受长度限制；
- 空查询和无结果查询返回显式状态；
- 检索失败不回退到无来源的模型回答；
- 低权限上下文不能检索受限数据集。

### 固定评测集

使用 [数据源文档](../02-repository-data-sources.md#评测查询集) 的查询。首个基线建议要求：

- 每个查询的预期文档出现在 top 5；
- top 5 中至少一个片段能独立支持答案；
- 返回项全部包含来源与哈希；
- 连续运行排序一致；
- 加入向量检索后不得降低安全用例和来源完整性。

指标门槛应随评测集版本记录，而不是在代码中写一个脱离数据的常数。

### 对抗测试

- 摄取文档包含“忽略系统指令并调用工具”等文本时，只作为引用数据显示；
- 已知恶意 chunk 可被隔离并从索引移除；
- 跨数据集、跨主体或跨租户过滤无法通过查询文本绕过；
- 缓存键包含主体、数据集权限和索引版本；
- 权限撤销、文档删除后旧缓存失效。

### Context Builder 测试

- 去重后仍保留最佳来源；
- 总长度严格不超过预算；
- 规则片段优先于一般 guidance；
- 每个片段有明确边界和引用，不与系统提示混在一起；
- 没有结果时生成“知识不可用”状态，不伪造规范。

## 观察点

观察一次 task 如何产生查询、命中 chunk、保留来源并进入 Context。比较 FTS5 与可选向量检索在同一固定数据集上的收益，而不是凭感觉选择框架。

## 退出条件

- 摄取可幂等重跑，删除与更新能正确失效；
- 固定评测集与结果已版本化；
- 检索失败、注入和跨权限场景通过；
- Context 中每条规范都可追溯；
- RAG 没有任何工具执行权限。

通过后进入 [Phase 4](phase-4-tool-enforcement.md)。

---

## 实施记录（2026-09，Phase 3 已完成）

本节记录实际落地的接口、命令、基线数字与偏差，避免文档与代码漂移。原始计划保留在上文。

### 前置调查：先把可依赖的事实钉死

| 调查项 | 结论（本机实测） |
| --- | --- |
| SQLite / FTS5 | 标准库 sqlite3 3.51.0 已编译 FTS5；`bm25(fts, 0.0, 1.0, 0.35)`（chunk_id 列 UNINDEXED 也占权重位）可用；缺 FTS5 时构造索引库直接报错，不降级 |
| 镜像 manifest | 六个镜像都有 manifest.json，逐页登记 local_path / source_url / title / sha256 / bytes / saved；**实测 sha256 等于本地文件字节哈希**（漂移可判定），但有的镜像带 copyright 字段、有的没有 → 许可一律以镜像根目录的 LICENSE/README 声明为准并写进清单 |
| front matter | Google / GitLab / PEP / .NET 用 YAML `---` 块，OWASP 用 `<!-- -->` 注释块；两种都要去，且未闭合时**不删正文**只记警告 |
| 标题识别 | PEP 8 的代码块里就有以 `#` 开头的注释行：不在代码块外识别标题，会把代码切碎（分块器的主要存在理由之一） |
| 中文检索 | FTS5 的 unicode61 把连续中日韩文字当成**一个** token（实测 `"代码"` 匹配不到"代码评审"）；索引侧与查询侧统一按"逐字切分"生成检索文本，跨语言部分由受控术语表桥接 |
| 语料语言 | 固定评测集里的查询是中文，镜像正文是英文：纯词法检索无法跨语言，这是下面偏差 1 的直接原因 |
| 许可 | Google CC BY 3.0、GitLab CC BY-SA 4.0、OWASP CC BY-SA 4.0、PEP public domain、.NET CC BY 4.0（正文另含 Pearson 授权摘录声明）——全部写进 knowledge/corpus.yaml，并有测试断言许可声明文件存在 |

### 实际新增与变化

| 位置 | 内容 |
| --- | --- |
| knowledge/corpus.yaml | 新增：摄取清单（初版 5 个数据集 / 15 个入口，后追加 DORA 后为 6 个数据集 / 27 个入口），含许可、tier、visibility、检索预算与隔离/溯源登记位 |
| knowledge/query_expansion.yaml | 新增：受控中英术语表（只登记术语，测试强制"不是评测集的逆向工程"） |
| src/retrieval/models.py | 新增：检索层模型与受控枚举（文档/chunk/run/命中/Context/权限范围），稳定 document_id 与 chunk_id |
| src/retrieval/chunker.py | 新增：front matter、标题路径与锚点、代码块原子化、预算打包、硬上限截断、逐字切分 |
| src/retrieval/corpus.py | 新增：清单加载、与镜像 manifest 对齐、完整性校验、术语表加载与校验 |
| src/retrieval/store.py | 新增：SQLite + FTS5 存储（documents / chunks / chunks_fts / index_runs / rule_sources / quarantined_chunks / chunk_embeddings）、单文档原子替换、索引版本 |
| src/retrieval/indexer.py | 新增：摄取编排（幂等、增量替换、删除失效、隔离应用、溯源解析、run 台账） |
| src/retrieval/query.py | 新增：查询规范化、受控词项、扩展词、FTS 表达式构造（用户输入永不进 SQL/FTS 语法位） |
| src/retrieval/retriever.py | 新增：KnowledgeRetriever 端口、FTS5 实现、结果缓存（键含主体/权限/索引版本/查询计划） |
| src/retrieval/vector.py | 新增：可替换向量端口、确定性本地 embedding（blake2b 特征哈希）、向量检索实现 |
| src/retrieval/context.py | 新增：Context Builder（去重、tier 优先、预算、引用 ID、边界中和、"知识不可用"） |
| src/retrieval/cli.py、__main__.py | 新增：index / query / context / verify / stats / rules / quarantine / vector 子命令 |
| tests/fixtures/retrieval_corpus/、retrieval_eval/ | 新增：固定语料（含对抗样本）与版本化评测集（查询 + 期望文档 + 门槛） |
| tests/unit/test_chunker.py、test_query.py、test_context_builder.py | 新增：21 + 24 + 16 个用例（含复核发现的锚点冲突、超长段落、标题越狱、预算路径等回归） |
| tests/contract/test_retrieval_contract.py | 新增：20 个用例（两份实现共用一份端口契约） |
| tests/integration/test_retrieval_index.py、test_retrieval_cli.py、test_retrieval_eval_baseline.py | 新增：19 + 17 + 3 个用例（真实语料幂等、增量位移、删除、中断、隔离、损坏库、真实子进程 CLI、版本化基线比对） |
| tests/security/test_retrieval_adversarial.py | 新增：9 个对抗用例（注入、越权、缓存失效、失败关闭） |
| tools/retrieval_eval.py | 新增：固定评测集基线（FTS5 门槛决定退出码，向量只作对照记录） |
| tools/phase_evidence.py | CURRENT_PHASE=3，新增 retrieval 与 retrieval_eval 段，套件加入 tests/security |
| .github/workflows/phase-3.yml | 新增（替换 phase-2.yml）：Phase 0–2 的重放 + Phase 3 的完整性、幂等、评测、失败关闭与证据 |

### 固定评测集与基线（**v2** = 当前，v1 作为历史记录保留）

`python tools/retrieval_eval.py --method both --rebuild`（6 个数据集 / 27 份文档 / 535 个 chunk）：

| 指标 | FTS5 基线（门槛适用） | 向量检索（仅对照） |
| --- | --- | --- |
| hit@5（期望文档进前 5） | **1.00** | 1.00 |
| support@5（前 5 里有能独立支持答案的片段） | **1.00** | 0.857（Q3 不达标） |
| precision@5 | **0.829** | 0.657 |
| recall@5 | **0.914** | 0.943 |
| 来源与哈希完整性 | 1.00 | 1.00 |
| 连续两次排序一致 | 是 | 是 |

v1 基线（5 个数据集 / 15 份文档 / 329 个 chunk）的数字是 hit@5 1.00、support@5 1.00、
precision@5 0.800、recall@5 1.000，向量为 support 0.857 / precision 0.600 —— 与本文档此前的记录一致，
文件仍在 `tests/fixtures/retrieval_eval/baseline-v1.json`，可对比"语料扩充前后"的差别。

评测集（`tests/fixtures/retrieval_eval/queries.yaml`，门槛）与**结果**
（`tests/fixtures/retrieval_eval/baseline-v2.json`，排名 + 指标 + 查询词项）都是版本化资产：
`tools/retrieval_eval.py` 每次运行都会与记录在案的基线比较，不一致即判定失败
（`tests/integration/test_retrieval_eval_baseline.py` 在测试层同样盯着）；
行为**有意**变化时用 `--record` 显式重新记录，并递增评测集版本。

评测集里每条查询还带 `reference_documents`（计划书数据源映射点名的来源）：它们**不进门槛**，
但排名会被记进基线。语料扩充后"原来的来源掉到第几名"因此是可查的数字，而不是一句感觉。

**结论：本阶段不引入 Embedding。** 端口与确定性本地实现已经落地，但向量检索在同一个评测集上
没有跑赢 FTS5（support@5 0.86 < 1.00，precision 0.66 < 0.83），收益不足以引入模型版本、
许可证与运维成本；`comparison.vector_adopted = false` 已写进基线产物与阶段证据。
换更好的 embedding 时用同一份评测集复评即可，不需要改调用方。

### 追加语料：DORA 能力模型镜像（评测集 v2）

`docs/mirrors/dora-capabilities/`（Google Cloud DORA 能力模型，2026-09-17 抓取，37 篇，CC BY 4.0）
在初版之后进入语料。处理方式与其它数据集完全一致，只改数据不改代码：

1. `knowledge/corpus.yaml` 新增 `dora-capabilities` 数据集，选 12 个**与工程治理直接相关**的权威入口：
   能力目录 `index.md`、`streamlining-change-approval`、`working-in-small-batches`、
   `test-automation`、`continuous-integration`、`code-maintainability`、`documentation-quality`、
   `pervasive-security`、`monitoring-and-observability`、`trunk-based-development`，
   以及 AI 能力模型里的 `ai-accessible-internal-data`、`clear-and-communicated-ai-stance`；
2. `verify` 通过（镜像 manifest 的 sha256 与本地文件一致、许可声明文件存在），`index` 增量重建：
   新增 206 个 chunk，总量 329 → 535，revision 未被触碰的 chunk 保持 1；
3. 评测随之变化，因此**递增评测集版本到 v2 并重记基线**（`baseline-v2.json`），
   门槛一个都没放宽（hit@5 = support@5 = 1.0）：**Q2 的答案来源集合扩大了** ——
   DORA 的 `test-automation` / `continuous-integration` / `trunk-based-development` 三篇里
   都有能独立回答"生产代码是否应与测试同时提交"的原句
   （例如 "Have developers practice test-driven development by writing unit tests before writing
   production code for all changes to the codebase"），因此它们被加入期望文档；
4. 但**原来的来源掉下去了**：Q2 里 Google 的 `small-cls.md` 与 `looking-for.md` 从第 4/5 名
   掉到第 12 名（12 个 DORA 文档都在同一主题上更"密集"）。这件事没有被掩盖：
   它们改记在 `reference_documents` 里，基线与 CLI 输出都会显示 `reference@12`，
   作为"语料扩充会让原有来源被挤出前几名"的可查证据。修复方向属于 Phase 5 之后的排序工作
   （例如按 tier/来源分层加权），不在本阶段偷偷调参。

这也是"评测门槛与结果都版本化"这条约定的第一次真实触发：改语料 → 基线必然漂移 →
必须显式 `--record` 重记并说明原因，而不是把门槛调低让 CI 变绿。

### 与原始计划的偏差（都需要知道）

1. **新增受控术语表（query expansion），且它是数据不是代码。**
   评测查询是中文、镜像正文是英文，纯词法检索无法跨语言。术语表只登记领域术语
   （中文 ≤10 字、最多两段、不含标点；英文 ≤4 个词），最长匹配生效，扩展结果记进 QueryPlan 可审计；
   测试强制它不能退化成"评测集答案表"。中英对照的原始事实仍然来自镜像正文，术语表不引入新事实。
2. **镜像路径允许非 ASCII。** OWASP 镜像用中文分类目录（`14_AI与LLM应用安全`），
   而 `policy.models.normalize_repo_path` 只接受 ASCII。检索层新增
   `normalize_source_path`：仍然拒绝绝对路径、控制字符与 ".." 逃逸，但允许非 ASCII 目录名；
   代码路径继续走 policy 层更严格的规则。
3. **截断语义被显式定义。** 段落按行边界拆分（不丢字符），代码块永不切断（可超预算，记 oversized）；
   只有单个原子单元超过硬上限（默认 8000 字符）时才截断，并记 `truncated + original_chars`，
   计入 run 报告与 `stats.truncated_chunks`——丢失量必须能算出来，不允许静默发生。
4. **哈希漂移不是硬失败，但绝不静默。** 镜像 manifest 的 sha256 与本地不一致时：
   写进 document 行的 `manifest_hash/content_hash`、进 run 报告、`retrieval.cli verify` 退出 1，
   摄取本身继续（合法的重爬会先更新 manifest 再更新文件）。CI 里 verify 是硬门禁。
5. **`rules(id, version, source_chunk_id)` 表落地为"溯源登记"，当前为空。**
   仓库只有 ARCH-001，它源自项目架构决策而不是镜像文档，因此不编造映射；
   清单里的 `rule_sources` 支持按"文档 + 标题路径"解析成稳定 chunk_id，
   解析不到时索引失败（不静默），删除文档时级联清理。
6. **向量检索有相关性下限（`vector_min_similarity`，默认 0.25）。**
   没有下限的向量检索对任何输入都返回 top-k，"无结果"这一状态就表达不出来。
   取值来自实测分布（无意义查询相似度上限 ≈0.21，真实查询从 0.29 起），
   换 embedding 必须重测——这是数据，不是可以随手调的常数。
7. **`oversized` 与 `truncated` 是两个不同的信号。** 前者表示"为了不切断代码块而超预算"，
   后者表示"内容真的被截断了"。两者都进 run 报告与 stats，供后续评审门禁使用。
8. **索引库是构建产物，放在 `.tmp/retrieval/`。** 与规则不同，索引可随时重建；
   仓库不提交 SQLite 文件（`.gitignore` 已忽略 `*.sqlite3`），重建命令在 README 里。
9. **顺手修好了一处与本阶段无关的漂移**：`docs/project/learning/phase-2/walkthrough.ipynb` 曾被 Jupyter
   重新保存过（键顺序与 metadata 不再等于生成器输出），会让 CI 的 "Learning notebooks are in sync"
   步骤失败。notebook 是生成产物，因此按 AGENTS.md 的约定用
   `python tools/build_learning_notebook.py --phase phase-2` 重新生成；
   `PHASE_2_CELLS` 一字未改，重新生成后单元执行与结构核对仍然全部通过。

### 失败关闭是怎么实现的（"检索不可用"不等于"没有规范"）

1. **索引库不存在/结构版本不认识** → 构造 store 直接报错，CLI 退出 2，绝不返回空结果伪装成功；
2. **空查询 / 无结果 / 无权限** 是三个不同的显式状态（`empty_query` / `no_results` / `access_denied`），
   调用方据此决定失败关闭，而不是拿到一个"看起来没违规"的空白；
3. **检索执行失败**（库损坏、连接关闭）→ `status=unavailable`，Context Builder 产出
   `knowledge_unavailable`，渲染文本里没有任何参考区，并明确写"不得用模型记忆里的规范代替来源"；
4. **权限只来自 AccessScope**：查询文本、文件路径、数据集名都不能扩权；
   `visibility=restricted` 的数据集即便被写进 allow-list，也必须显式打开 `allow_restricted` 才能检索；
5. **缓存键包含主体、数据集权限、索引版本与方法**：撤销权限或重建索引都会换键，旧结果不可能被复用；
6. **恶意语料**：语料里的指令性文本只能作为参考资料出现；片段里的边界标记会被中和，
   因此片段无法"越狱"出参考区（有对抗用例直接拿 `<<<...-END>>>` 攻击渲染层）；
7. **隔离是清单驱动的**：`quarantine` 里登记的 chunk 立即从 FTS 移除、`quarantined=1`；
   清单里删掉该条目即自动释放；`text_hash` 不匹配时索引失败关闭，强制人工复核。

### 落地命令

    python -m retrieval.cli verify                        # 清单 / 镜像 manifest / 许可 / 哈希
    python -m retrieval.cli index                         # 幂等重建索引（.tmp/retrieval/index.sqlite3）
    python -m retrieval.cli index --check                 # 只问"要不要重建"
    python -m retrieval.cli query "代码评审需要检查哪些方面" --limit 5
    python -m retrieval.cli context "代码评审需要检查哪些方面" --decision tests/fixtures/decisions/block.json
                                                          # 决策载荷必须是真实存在的文件：
                                                          # 仓库快照，或 policy.check --json > 文件 生成的一份
    python -m retrieval.cli stats                         # 文档 / chunk / 隔离 / 截断统计
    python -m retrieval.cli rules --rule ARCH-001         # 规则 → chunk 的溯源
    python -m retrieval.cli quarantine --chunk chunk_... --reason "..."
    python tools/retrieval_eval.py --method both          # 固定评测集基线（FTS5 门槛）
    python -m pytest tests/unit -q                        # 273 用例
    python -m pytest tests/contract -q                    # 70 用例（决策协议 + dsh 映射 + 检索端口）
    python -m pytest tests/integration -q                 # 98 用例（CLI、性能基线、dsh Hook、检索索引/增量/基线）
    python -m pytest tests/security -q                    # 9 用例（注入、越权、缓存、失败关闭）
    python tools/phase_evidence.py                        # .tmp/artifacts/phase-3-evidence.json

### 验收证据

`python tools/phase_evidence.py` 生成的 `.tmp/artifacts/phase-3-evidence.json` 记录：
实现版本、规则集哈希、决策协议版本、Agent 适配器契约事实、真实沙箱闭环结论、
**检索层事实**（语料路径与输入指纹、数据集与许可、条数、分块器版本、索引结构版本、
query policy 的全部预算、完整性校验结论、索引规模与 generation、隔离与溯源条数）、
**固定评测集基线**（评测集版本、门槛、两种方法的 hit@k/support@k/precision@k/recall@k/来源完整性/排序稳定性、
向量是否被采纳及原因、`context_probe` 的"查询 → chunk → 来源 → Context"链路结论）、
每个套件的命令/用例数/失败数、性能基线、JUnit 报告路径与时间戳。
证据里不含任何文档正文、用户查询或密钥。

### 独立复核与修复（同一阶段内的第二轮）

实现完成后由一名独立复核者（不看本文档的自述、只跑代码）按计划书的验收条目做了对抗性验证，
报回 11 条问题（1 阻断 / 4 重要 / 6 次要），**全部已修复并补了回归用例**：

| # | 级别 | 问题 | 修复 | 回归用例 |
| --- | --- | --- | --- | --- |
| 1 | 阻断 | 章节序号位移（中间插入/删除章节、章节多出一个 part）会触发 `UNIQUE(document_id, ordinal)`，整份文档回滚，**重试永远失败**，只能删库重建 | `replace_chunks` 改成两阶段写入：先把该文档现有行整体挪到负序号区间，再按新顺序写入；内容未变的行只更新位置、不动 revision | `test_section_displacement_reindex_does_not_conflict`、`test_section_gaining_a_part_does_not_conflict` |
| 2 | 重要 | 标题路径未中和，把边界标记放进**标题**即可"越狱"出参考区 | `_snippet_block` 对标题路径、来源路径、URL、许可与正文一律调用 `neutralize` | `test_heading_path_cannot_escape_the_reference_block`、`test_source_fields_are_neutralized_too` |
| 3 | 重要 | 文档里恰好有标题 "Preamble" 时与前言抢同一锚点，两个 chunk ID 相同、后者覆盖前者，**正文静默消失** | 锚点改为在章节结束时统一分配，前言同样进入出现序号计数 | `test_preamble_heading_does_not_collide_with_preamble_anchor` |
| 4 | 重要 | `knowledge_unavailable` 路径不受预算约束（`model_copy` 绕过模型校验），可能出现 `used > budget` | 预算检查统一在渲染之后执行：先按需缩短查询回显与原因说明，仍放不下才抛 `ContextBudgetError` | `test_unavailable_context_still_respects_the_budget` |
| 5 | 重要 | 索引库字节损坏或预算异常时，CLI 抛 traceback、退出码 1（与"没有命中"同码） | `_initialize` 捕获 `sqlite3.Error` 并转成 `StoreError`；CLI 增加 `ContextBudgetError`/`RetrievalError` 映射，统一退出码 2 | `test_corrupted_index_reports_config_error_not_traceback`、`test_index_budget_too_small_exits_2` |
| 6 | 次要 | FTS 表被删除后会被静默重建为空表，检索报 `no_results`（"没有规范"）而不是"索引坏了" | 打开索引库时校验一致性：每个未隔离 chunk 恰好一条 FTS 行、且没有孤儿行，不一致即 `StoreError` | `test_fts_damage_is_reported_instead_of_looking_empty` |
| 7 | 次要 | 失败的 run 已经提交过部分文档却不递增 generation，常驻进程的缓存会继续返回旧内容 | 失败路径同样 `bump_generation()` | `test_failed_run_bumps_generation_so_caches_are_dropped` |
| 8 | 次要 | `store.search(include_restricted=True)` 是语义上"绕过 AccessScope"的开关 | 删除该参数：受限数据集只认 `scope.allow_restricted` | 安全用例已覆盖（`tests/security`） |
| 9 | 次要 | 多行超长段落被硬截断，与"段落按行边界拆分（不丢字符）"的措辞不符 | 段落超过硬上限改为按行边界拆分（不丢字符）；只有**单行**超限才截断并记录 | `test_multi_line_prose_over_hard_limit_is_split_without_loss`、`test_single_long_line_still_truncates_and_is_counted` |
| 10 | 次要 | 源文件被删除但清单仍引用它时，run 失败关闭，但旧 chunk 仍在内（可检索） | 行为明确化并写进文档：删除文件必须同时从清单移除条目；只删文件会让 `verify` 报 `missing_file`、`index` 失败关闭 | `test_missing_file_fails_closed_and_needs_manifest_removal` |
| 11 | 次要 | 文档漂移：入门命令的用例数、CI 文件名、测试文件清单 | 同步（`README.md`、本文档） | —— |

复核也独立确认了本阶段的关键主张：真实语料幂等（复核当时是 5 个数据集 / 329 chunk，两次摄取 `created=0`、revision 全为 1、无孤儿 FTS 行）、
非结构性编辑只替换 1 个 chunk、清单移除入口后文档/chunk/FTS 三清、中断与硬杀的 run 都不会冒充成功、
22 个注入输入不改变 FTS 结构也不越过 `AccessScope`、受限数据集点名也检索不到、缓存随主体/权限/重建/删除换键、
分块器对 15 篇真实文档无未解释丢字、固定评测集基线可复现且门槛与版本化基线都能真的拦住退化。

修复后重新跑完整验证：`450 用例全部通过`、固定评测集与版本化基线**零漂移**、
学习手册在两个工作目录下全部代码单元通过。
