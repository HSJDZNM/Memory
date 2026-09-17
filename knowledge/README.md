# knowledge/：检索语料清单与查询词表

这两个文件是 Phase 3 检索层的**数据**（不是代码）：改语料、改预算、改隔离、改术语都只动这里。

| 文件 | 作用 | 谁在用 |
| --- | --- | --- |
| corpus.yaml | 摄取清单：数据集、镜像目录、许可、tier、可见性、检索预算、隔离登记、规则溯源登记 | `src/retrieval/corpus.py` 加载，`src/retrieval/indexer.py` 摄取，`tools/retrieval_eval.py` 与阶段证据引用 |
| query_expansion.yaml | 受控中英术语表：把中文任务术语桥接到上游英文文档实际使用的术语 | `src/retrieval/query.py` 构造查询计划时使用；扩展结果记进 QueryPlan，可审计 |

## 维护流程

```powershell
python -m retrieval.cli verify                 # 数据集 / 许可 / 镜像 manifest / 本地哈希是否一致
python -m retrieval.cli index                  # 幂等重建索引（产物在 .tmp/retrieval/ 下）
python tools/retrieval_eval.py --method both   # 固定评测集基线是否仍然达标（FTS5 门槛决定退出码）
# 术语表或语料有意改动后，结果基线要显式重记（会同时更新版本化结果文件）：
python tools/retrieval_eval.py --method both --rebuild --record tests/fixtures/retrieval_eval/baseline-v2.json
python tools/phase_evidence.py                 # 把语料事实写进阶段证据
```

## 规则（有测试强制）

1. **只登记镜像里真实存在的页面**：条目必须能在该镜像的 manifest.json 中找到，缺失即加载失败；
2. **许可必填**：每个数据集都要写许可与许可声明所在文件，`verify` 会检查该文件是否存在；
3. **tier 与 visibility 分开**：tier（policy / guidance / reference）只决定 Context 中的优先级；
   visibility=restricted 的数据集必须由调用方显式授权（`AccessScope.allow_restricted`）才可检索；
4. **预算是数据**：分块预算、Context 预算、查询长度与词项上限都写在这里，代码里不写常数；
5. **隔离条目必须带 text_hash**：源文变化后旧隔离自动失效（清单是隔离状态的唯一事实来源）；
6. **术语表只登记术语**：中文 ≤10 字、最多两段、不含标点；英文 ≤4 个词；
   条目与具体评测查询无关，测试会拒绝"把评测集答案抄进术语表"的写法。

## 新增数据集

1. 在 `docs/<mirror>/` 下准备镜像与 manifest.json（上游 URL、标题、sha256、字节数、抓取时间）；
2. 在 `corpus.yaml` 里加一个 dataset：`name / title / mirror / license / license_source / tier / visibility / entries`；
3. 跑 `verify`（哈希、许可、条目）→ `index`（幂等重建）→ `retrieval_eval.py`（门槛是否仍达标）；
4. 若新数据集进入固定评测集的期望文档，必须同时递增评测集 version 并更新阶段记录里的基线数字。
