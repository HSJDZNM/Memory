# Phase 3 学习手册：怎么用、怎么维护

## 这是什么

Phase 3（规范检索）的可执行讲解。回答四个问题：

| 小节 | 问题 |
| --- | --- |
| 1-2 | 哪些文档进了检索，一份 Markdown 怎么变成 chunk |
| 3-4 | 一次索引做了什么，为什么可以反复重跑 |
| 5-7 | 查询为什么安全，检索结果与 Context 里到底有什么 |
| 8-10 | 检索不可用时怎么办，基线门槛写在哪，命令行退出码怎么读 |

## 怎么跑

```powershell
# 方式一：Jupyter（需要本机有 Jupyter）
jupyter lab docs/project/learning/phase-3/walkthrough.ipynb

# 方式二：纯 Python（同内容，逐段打印）
python docs/project/learning/phase-3/walkthrough.py

# 方式三：不想装 Jupyter，只想确认它没坏
python tools/run_notebook_in_kernel.py docs/project/learning/phase-3/walkthrough.ipynb
```

前置条件只有一个：仓库里能读到 `knowledge/corpus.yaml` 与 `docs/` 下的离线镜像。
notebook 自己会建立临时索引（写在 `.tmp/learning/phase-3-<uuid>/`），
**不需要预先跑过 `retrieval.cli index`**，跑完可以用 `python tools/cleanup.py` 清理。

## 它实际验证了什么

生成器会在两个工作目录（仓库根目录、手册目录）各执行一遍全部代码单元，并核对：

- 语料：6 个数据集、27 个入口、许可齐全、完整性校验通过；
- 分块：重复标题锚点互不相同、代码块内的 `#` 不被当作标题、空章节被跳过；
- 索引：第一次 run 覆盖 27 份文档，第二次 run 新建/更新/删除都是 0，`revision` 全为 1；
- 查询安全：恶意输入产生的 FTS 表达式只由双引号词项与 `OR` 组成，且命中范围不越过授权数据集；
- 检索：命中都带来源路径、URL、许可与文本哈希；
- Context：`used_chars == len(渲染结果) <= 预算`，`[P1]` 在 `[K1]` 之前，参考区标注为不可信数据；
- 失败关闭：检索不可用时只输出 `knowledge_unavailable`，不渲染参考区；
- 评测：固定评测集（v2）在当前代码上仍然通过门槛（hit@k / support@k 都是 1.0）；
- CLI 退出码：`verify` 0、有命中 0、无结果 1、缺索引库 2。

任何一条对不上，`python tools/build_learning_notebook.py` 就会失败——手册里的结论不会悄悄过期。

## 怎么维护

手册内容**不是手写的 notebook**，而是 `tools/build_learning_notebook.py` 里的
`PHASE_3_CELLS` 与 `check_phase_3_structure`：

```powershell
# 改内容 -> 重新生成（会写 walkthrough.ipynb / walkthrough.py 并逐单元执行校验）
python tools/build_learning_notebook.py --phase phase-3

# 只校验当前文件与生成器是否一致（CI 用这条）
python tools/build_learning_notebook.py --check

# 结构校验（不依赖 nbformat）
python tools/check_notebook.py docs/project/learning/phase-3/walkthrough.ipynb
```

不要直接编辑 `.ipynb`：下一次生成会覆盖它，而且 JSON diff 无法评审。

## 常见问题

**Q：跑的时候报"摄取清单不存在"？**
A：notebook 是从 `knowledge/corpus.yaml` 反推仓库根目录的，请确认你在仓库里跑，
或者让当前工作目录位于仓库之内（它自己会向上找）。

**Q：为什么手册里的数字（27 份文档、535 个 chunk）和我跑出来的不一样？**
A：先把语料加回去。`python -m retrieval.cli verify` 会告诉你缺哪些入口；
如果语料确实变了，更新 `knowledge/corpus.yaml`、重跑评测并同步阶段记录，
生成器里的断言也要一起改——这条规则是"手册与实现不许漂移"的具体执行方式。

**Q：能改成检索别的文档吗？**
A：能，但要在 `knowledge/corpus.yaml` 里登记数据集与许可，然后重跑
`verify` → `index` → `retrieval_eval.py`。评测门槛是版本化数据，改语料就要重新记录基线。

**Q：为什么手册里没有向量检索的完整演示？**
A：向量检索在本阶段是"对照实验"：端口与实现都在代码里（`src/retrieval/vector.py`），
但固定评测集显示它没有跑赢 FTS5，因此没有进入默认链路。想看数字就运行
`python tools/retrieval_eval.py --method both`，或读阶段实施记录里的对照表。
