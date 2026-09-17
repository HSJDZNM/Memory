# Phase 0 学习手册：最小规则系统

本目录讲解 Phase 0：**一个程序读取机器可执行规则，对固定上下文稳定产生 PASS/FAIL**。
设计文档见 [../../engineering-policy-platform/phases/phase-0-minimum-rule-system.md](../../engineering-policy-platform/phases/phase-0-minimum-rule-system.md)。

| 文件 | 内容 | 怎么用 |
| --- | --- | --- |
| [note.md](note.md) | 任务内容、对象清单、对象关系、边界 | 先读这个建立整体印象 |
| [walkthrough.ipynb](walkthrough.ipynb) | 48 个单元的可执行讲解（含预备知识与逐行注释），每个代码单元都有"要做什么 / 代码 / 小结"三段 | Jupyter / VS Code 打开，从上到下执行 |
| [walkthrough.py](walkthrough.py) | 同一份内容的纯 Python 版本 | `python docs/learning/phase-0/walkthrough.py` |

## 单元卡住不返回怎么办

手册里没有耗时操作（无循环、无网络、无大文件），正常情况下**全部单元数秒跑完**。
如果第一个单元就一直没有输出，问题在内核启动而不是代码：

已知触发条件：在受限沙箱（文件系统只允许写工作区）里运行 Jupyter，
内核启动时给连接文件设置 ACL 会被拒绝，Jupyter 只等待而不会报错：

```text
ipykernel: error (5, 'SetFileSecurity', 'Access is denied.')
```

三种可用的替代方式：

1. 在普通 Jupyter / VS Code 中打开本 notebook；
2. 运行同内容的纯 Python 版本：`python docs/learning/phase-0/walkthrough.py`；
3. 直接用根 `README.md` 里的 CLI 命令做最小验证。

三条路径使用同一套模块，结论一致。

## 怎么用

1. 先跑一次测试确认环境是对的：`python -m pytest -q`；
2. 打开 notebook 从上到下执行。每个代码单元都有三段配套内容：
   **这一段代码要做什么**（读之前）→ 带逐行注释的代码 → **小结**（读之后，说明输出意味着什么）；
3. 完全没写过 Python 也没关系：开头的「预备知识」用五小节讲清函数、类、模型、YAML 缩进与术语；
4. 想验证某个判断，直接改单元里的输入重跑——手册里的所有结论都来自真实模块，不是复述文档。

## 怎么维护

notebook 由 `tools/build_learning_notebook.py` 生成，**不要手改 .ipynb**：

```powershell
python tools/build_learning_notebook.py          # 重新生成，并逐单元执行校验
python tools/check_notebook.py docs/learning/phase-0/walkthrough.ipynb
```

生成器会从**两个工作目录**各跑一遍全部代码单元，并断言每个示例的退出码（反例 1、正例 0、配置错误 2），
还会核对文档里写过的 JSON 键名与 `PolicyDecision` 字段，因此"说明与示例不一致"会在生成阶段失败。

想确认"在真实内核里也能跑"（需要 ipykernel）：

```powershell
python tools/run_notebook_in_kernel.py docs/learning/phase-0/walkthrough.ipynb
```

## 与其他文档的分工

| 文档 | 读者 | 回答什么 |
| --- | --- | --- |
| `../../engineering-policy-platform/phases/phase-0-minimum-rule-system.md` | 实施者 | 本阶段要做什么、如何验收 |
| `note.md`（本目录） | 想搞懂结构的人 | 有哪些对象、关系如何、边界在哪 |
| `walkthrough.*`（本目录） | 想动手的人 | 实际跑起来是什么样、为什么这么设计 |
