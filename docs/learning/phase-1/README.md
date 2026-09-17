# Phase 1 学习手册：Policy Engine

本目录讲解 Phase 1：**把 Phase 0 的单规则判断升级为可解释、可扩展、仍然确定的 Policy Engine**。
设计文档见 [../../engineering-policy-platform/phases/phase-1-policy-engine.md](../../engineering-policy-platform/phases/phase-1-policy-engine.md)。

| 文件 | 内容 | 怎么用 |
| --- | --- | --- |
| [note.md](note.md) | 任务内容、对象清单、对象关系、边界与取舍 | 先读这个建立整体印象 |
| [walkthrough.ipynb](walkthrough.ipynb) | 65 个单元的可执行讲解（上下文规范化 -> 范围匹配 -> 决策 -> 协议），每个代码单元都有"要做什么 / 代码 / 小结"三段 | Jupyter / VS Code 打开，从上到下执行 |
| [walkthrough.py](walkthrough.py) | 同一份内容的纯 Python 版本 | `python docs/learning/phase-1/walkthrough.py` |

## 读之前先知道三件事

1. **Phase 0 的手册仍然是前置**：函数、类、模型、YAML 缩进这些基础在
   [../phase-0/walkthrough.ipynb](../phase-0/walkthrough.ipynb) 里讲过了，本手册只补新概念；
2. **Phase 1 的核心变化是"分出两件事"**：规则是否相关（matched / skipped）与是否违规（violations）。
   手册里所有结论都围绕这条线展开；
3. **规则文件没有变**：本阶段验证用的是测试内联与合成规则，仓库里仍然只有 ARCH-001 一条真实规则。

## 怎么用

1. 先跑一次测试确认环境是对的：`python -m pytest -q`；
2. 打开 notebook 从上到下执行。每个代码单元都有三段配套内容：
   **这一段代码要做什么**（读之前）→ 带逐行注释的代码 → **小结**（读之后，说明输出意味着什么）；
3. 想验证某个判断，直接改单元里的输入重跑——手册里的所有结论都来自真实模块，不是复述文档；
4. 想先看设计意图再动手，读同目录的 [note.md](note.md)。

## 单元卡住不返回怎么办

手册里的代码没有网络、没有大文件；最重的单元是性能基线（1000 条规则，数秒）。
如果第一个单元就一直没有输出，问题在内核启动而不是代码：

已知触发条件：在受限沙箱（文件系统只允许写工作区）里运行 Jupyter，
内核启动时给连接文件设置 ACL 会被拒绝，Jupyter 只等待而不会报错：

```text
ipykernel: error (5, 'SetFileSecurity', 'Access is denied.')
```

三种可用的替代方式：

1. 在普通 Jupyter / VS Code 中打开本 notebook；
2. 运行同内容的纯 Python 版本：`python docs/learning/phase-1/walkthrough.py`；
3. 直接用根 README 里的 CLI 命令做最小验证。

三条路径使用同一套模块，结论一致。

## 常见问题

**为什么"层写成 service"时正例文件仍然返回 0？**
因为 ARCH-001 的 scope 只声明了 controller，规则不参与判断。手册第 6 节会打印
"skipped ... layer service != controller"，这就是"规则不相关"与"规则通过"的区别。

**为什么上下文里没有"审批状态"字段？**
审批不能由文件名、目录或用户消息推断。规则用 `enforcement.requires_approval` 声明门禁，
决策用 `required_action=approval` 表达结果，两者都不经过上下文。

**规则里把 language 拼成 langauge 会怎样？**
加载阶段直接报错。Phase 0 允许显式 `extra_policy: skip` 忽略未知维度，Phase 1 把默认改成拒绝，
因为"拼错维度名"会让规则悄悄放大适用范围。

**CLI 的 `--module` 为什么不按目录推断？**
猜错模块会让规则在错误的范围上生效。真正的模块信息由 Phase 2 的 Adapter 提供。

## 怎么维护

notebook 由 `tools/build_learning_notebook.py` 生成，**不要手改 .ipynb**：

```powershell
python tools/build_learning_notebook.py --phase phase-1   # 重新生成并逐单元执行校验
python tools/build_learning_notebook.py --check           # 只校验是否与生成器一致
python tools/check_notebook.py docs/learning/phase-1/walkthrough.ipynb
```

生成器会从**两个工作目录**各跑一遍全部代码单元，断言每个示例的退出码（反例 1、正例 0、配置错误 2），
并核对文档里写过的决策协议字段名，因此"说明与示例不一致"会在生成阶段失败。

新增阶段时：把单元内容加到 `tools/build_learning_notebook.py` 的 `PHASE_N_CELLS`，
在 `PHASES` 里注册，然后运行上面的命令。

## 与其他文档的分工

| 文档 | 读者 | 回答什么 |
| --- | --- | --- |
| `../../engineering-policy-platform/phases/phase-1-policy-engine.md` | 实施者 | 本阶段要做什么、如何验收 |
| `note.md`（本目录） | 想搞懂结构的人 | 有哪些对象、关系如何、边界在哪 |
| `walkthrough.*`（本目录） | 想动手的人 | 实际跑起来是什么样、为什么这么设计 |
| 根 `README.md` | 使用者 | 怎么装、怎么跑 |
