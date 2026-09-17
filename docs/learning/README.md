# 学习手册

面向人的可执行讲解。**每个阶段一个文件夹**；阶段完成后在这里补一份能自己重跑的手册。

| 阶段 | 目录 | 内容 |
| --- | --- | --- |
| Phase 0 最小规则系统 | [phase-0/](phase-0/) | 一条规则从 YAML 到 PASS/FAIL 的完整链路 |
| Phase 1 Policy Engine | [phase-1/](phase-1/) | 上下文规范化、范围匹配、严重级别与可解释决策 |
| Phase 2 dsh Adapter | [phase-2/](phase-2/) | dsh 事件映射、显式上下文、Hook 的 allow / block 与失败关闭 |
| Phase 3 规范检索 | [phase-3/](phase-3/) | 分块、FTS5 检索、来源与哈希、Context 预算与"知识不可用" |
| Phase 4 受控执行 | [phase-4/](phase-4/) | Tool Registry、Action Request 与 action_hash 绑定、pre-check、受控执行、事后验证与审计链 |

后续阶段按同一约定新增：`phase-5/`、`phase-6/` …

## 每个阶段目录的固定结构

```text
docs/learning/<phase>/
├── note.md            # 任务内容、对象清单、对象之间的关系（本阶段的"是什么"）
├── walkthrough.ipynb # 带注解的可执行讲解（由脚本生成，不要手改）
├── walkthrough.py    # 同一份内容的纯 Python 版本（同一脚本生成）
└── README.md         # 怎么用、怎么维护、常见问题
```

其中两个 walkthrough 文件由 `tools/build_learning_notebook.py` 生成；
`note.md` 与 `README.md` 是手写文档。

## 怎么用

1. 先跑一次测试确认环境：`python -m pytest -q`；
2. 打开该阶段的 `walkthrough.ipynb` 从上到下执行。每个代码单元都有三段配套内容：
   **这一段代码要做什么**（读之前）→ 带逐行注释的代码 → **小结**（读之后，说明输出意味着什么）；
3. 完全没写过 Python 也没关系：notebook 开头有「预备知识」，讲清函数、类、模型、YAML 缩进与术语；
4. 想验证某个判断，直接改单元里的输入重跑——手册里的所有结论都来自真实模块，不是复述文档；
5. 想先看设计意图再动手，读同目录的 `note.md`。

## 怎么维护（新增阶段时照做）

1. 新建 `docs/learning/<phase>/` 目录，放齐上面四个文件；
2. 改 `tools/build_learning_notebook.py`：新增 `PHASE_N_CELLS` 并在 `PHASES` 里注册，然后运行
   `python tools/build_learning_notebook.py`（它会生成两个 walkthrough 文件并逐单元执行校验）；
3. 在本文件顶部的表格里加一行；
4. 提交前运行 `python tools/check_notebook.py docs/learning/*/walkthrough.ipynb`。

## 与其他文档的分工

| 文档 | 读者 | 回答什么 |
| --- | --- | --- |
| `docs/engineering-policy-platform/` | 设计与实施者 | 每个阶段要做什么、如何验收 |
| `docs/learning/<phase>/note.md` | 想搞懂结构的人 | 本阶段有哪些对象、关系如何、边界在哪 |
| `docs/learning/<phase>/walkthrough.*` | 想动手的人 | 这一步实际跑起来是什么样、为什么这么设计 |
| 根 `README.md` | 使用者 | 怎么装、怎么跑 |
