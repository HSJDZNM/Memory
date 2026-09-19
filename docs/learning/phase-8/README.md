# Phase 8 学习手册 · LangGraph 编排

这是**手工文档**：怎么用、怎么维护、遇到问题怎么办。可执行的讲解在
`walkthrough.ipynb`（与同内容的 `walkthrough.py`），由
`tools/build_learning_notebook.py` 生成，不要手改。

## 怎么用

```powershell
# 交互式阅读（需要 jupyter）
jupyter lab docs/learning/phase-8/walkthrough.ipynb

# 纯 Python 版：逐段打印同样的输出
python docs/learning/phase-8/walkthrough.py
```

notebook 里的代码单元**不联网、不起端口、不调用模型**：它用脚本化的假客户端
（`ScriptedPolicyClient`）与只记录不落盘的执行端口（`RecordingToolRunner`）跑完整状态机，
再在"两个引擎等价"那一节真的构造 LangGraph 引擎（本机已安装 langgraph 1.2.11）。
真实平台链路（真端口、真受控执行、真 checkpoint 与恢复）由
`python tools/orchestration_loop.py` 证明。

所有演示产物写在 `.tmp/learning-phase-8/` 下，可以随时删：
`python tools/cleanup.py`。

## 手册里有什么

| 小节 | 回答的问题 |
| --- | --- |
| 1 | 图状态长什么样，为什么它拒绝正文、绝对路径与未知字段 |
| 2 | 硬上限怎么记账，失败码怎么决定终态 |
| 3 | 图为什么是数据：节点、静态边与条件分支 |
| 4 | 假客户端下的完整 happy path：每一步的判定都能追溯 |
| 5 | 验证失败 → 修复 → 通过：PASS/FAIL 只由结构化 Decision 决定 |
| 6 | 两个引擎跑同一份 spec，报告逐字节一致（"编排可替换"） |
| 7 | checkpoint 与恢复：中断、续跑、以及 checkpoint 里没有正文 |
| 8 | 人工审批：参数绑定、限期、单次使用、恢复不绕过 |
| 9 | 一张失败关闭表：每个失败码对应的终态 |

## 怎么维护

1. 改内容 = 改 `tools/phase8_cells.py`（**不要**直接改 notebook），然后运行
   `python tools/build_learning_notebook.py --phase phase-8`；
   生成器会从两个工作目录（仓库根与 `docs/learning/phase-8/`）各跑一遍全部代码单元，
   并核对 `check_phase_8_structure` 里的结构断言；
2. 提交前运行 `python tools/check_notebook.py docs/learning/phase-8/walkthrough.ipynb`
   与 `python tools/build_learning_notebook.py --check`；
3. 表格一律用生成器注入的 `pad()` 补位（中文占两列，`f"{x:<10}"` 会把表挤歪）；
4. 新增阶段时同步更新 `docs/learning/README.md` 的索引。

## 常见问题

**Q：为什么手册里跑的是参考引擎，而不是 LangGraph？**
A：因为手册要证明的两件事不同。第 4/5/7/8 节证明的是**语义**（状态机、循环、恢复、审批），
这些与框架无关，用参考引擎跑得又快又稳；第 6 节专门证明**可替换性**——
同一份 spec 交给两个引擎，报告逐字节一致。真正的 LangGraph 链路在
`tools/orchestration_loop.py` 里与真实平台一起跑。

**Q：为什么 checkpoint 不直接交给 LangGraph 的 checkpointer？**
A：阶段计划要求 checkpoint 里带"规则集 / 索引 / 工具 schema 的兼容性"，
那是**领域信息**，通用 checkpointer 不提供；恢复时"不兼容就不沿用旧 allow"
必须有地方判断与记录。LangGraph 仍然负责图执行（递归、分支、状态通道）。

**Q：手册跑完 `.tmp/` 里多了一堆文件，要提交吗？**
A：不要。`.tmp/` 已在 `.gitignore` 中；删除用 `python tools/cleanup.py`。

**Q：notebook 被 Jupyter 写脏了怎么办？**
A：`git checkout -- docs/learning/phase-8/walkthrough.ipynb`，或重新生成
`python tools/build_learning_notebook.py --phase phase-8`。
