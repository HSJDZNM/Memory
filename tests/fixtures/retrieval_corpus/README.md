# Phase 3 检索夹具

固定语料与评测集的说明。每一项都写明用途、预期结果与是否包含敏感数据；
按[测试策略](../../../docs/project/engineering-policy-platform/testing/test-strategy.md)，禁止真实凭据、
用户数据与生产日志。

## retrieval_corpus/（分块、索引、检索与对抗测试的语料）

语料文件放在这里，**镜像 manifest 与摄取清单由 tests/conftest.py 在临时目录里生成**：
manifest.json 里的 sha256 必须与被测文件一致，手写哈希会随文件改动立刻漂移，
因此哈希一律在运行时计算（同 tools/policy_bench.py"固定种子生成规则"的思路）。

| 文件 | 用途 | 预期结果 | 敏感数据 |
| --- | --- | --- | --- |
| guides/index.md | YAML front matter、代码块内的 "#" 注释行、重复标题 Notes、空章节 Appendix | 代码块不被切断；标题只在块外生效；重复标题锚点不同；空章节被跳过并计数 | 无 |
| guides/topics.md | HTML 注释 front matter、普通章节 | front matter 元数据进入 documents，正文不含元数据 | 无 |
| restricted/internal.md | 受限数据集样本（visibility=restricted） | 未显式授权时任何查询都检索不到，包括查询文本直接点名它的场景 | 无（占位 token） |
| adversarial/poisoned.md | 语料内指令注入（"IGNORE ALL PREVIOUS INSTRUCTIONS…"） | 只作为引用数据出现，边界标记被中和，不改变任何策略或执行 | 无 |

目录映射：夹具相对路径的第一段即镜像目录名，其余部分是镜像内的 local_path。
例如 guides/index.md → 镜像 mirror/guides，条目 index.md。

## retrieval_eval/（固定评测集）

| 文件 | 用途 |
| --- | --- |
| queries.yaml | 版本化评测集：查询、期望文档、supporting_terms 与门槛（hit@k / support@k / 来源完整性 / 排序稳定性） |
| baseline-v1.json / baseline-v2.json | 版本化**结果**：记录在案的每查询排名、指标、查询词项与 `reference_rank`（计划书点名的来源当前排第几，只记录不作门槛）；`tools/retrieval_eval.py` 与 `tests/integration/test_retrieval_eval_baseline.py` 都会与当前基线比较，不一致即失败（行为有意变化时用 `--record` 显式重记并递增评测集版本） |

评测集直接来自[仓库数据源](../../../docs/project/engineering-policy-platform/02-repository-data-sources.md#评测查询集)，
门槛随评测集版本记录，代码里不写"脱离数据的常数"。修改查询或门槛必须递增 version，
并重跑 python tools/retrieval_eval.py 更新 .tmp/artifacts/phase-3-retrieval-baseline.json。

## 临时目录

与 Phase 0–2 一致：所有临时产物写在 .tmp/ 下（通过 conftest 的 tmp_root fixture），
不用 pytest 的 tmp_path（受限沙箱里 mkdtemp 会被拒绝）。
