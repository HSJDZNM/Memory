# Phase 2 学习手册：dsh Adapter

本目录讲解 Phase 2：**把 dsh 的工具调用事件翻译成核心策略协议，并在工具执行之前决定放行还是阻断**。
设计文档见 [../../engineering-policy-platform/phases/phase-2-dsh-adapter.md](../../engineering-policy-platform/phases/phase-2-dsh-adapter.md)，
前置调查与实测证据见 [../../../src/adapters/dsh/README.md](../../../../src/adapters/dsh/README.md)。

| 文件 | 内容 | 怎么用 |
| --- | --- | --- |
| [note.md](note.md) | 任务内容、对象清单、对象关系、边界与取舍 | 先读这个建立整体印象 |
| [walkthrough.ipynb](walkthrough.ipynb) | 49 个单元的可执行讲解（事件 -> 映射 -> 配置 -> Hook 出口 -> PostToolUse 事后验证 -> 失败关闭 -> CLI -> 审计），每个代码单元都有"要做什么 / 代码 / 小结"三段 | Jupyter / VS Code 打开，从上到下执行 |
| [walkthrough.py](walkthrough.py) | 同一份内容的纯 Python 版本 | `python docs/project/learning/phase-2/walkthrough.py` |

## 读之前先知道三件事

1. **Phase 0 / Phase 1 的手册仍然是前置**：函数、类、模型、YAML 缩进与决策协议在
   [../phase-0/walkthrough.ipynb](../phase-0/walkthrough.ipynb) 与
   [../phase-1/walkthrough.ipynb](../phase-1/walkthrough.ipynb) 里讲过，本手册只补新概念；
2. **Phase 2 的核心变化是"策略从建议变成控制"**：block 路径下执行器**一次都不会被调用**，
   allow 路径下**恰好一次**。手册里所有断言都围绕这条线展开；
3. **手册不调用 dsh**：它用 11 个脱敏 fixture 和假执行器验证 Python 侧契约（不联网、不跑 LLM）。
   真实沙箱闭环在 [../../../tools/dsh_sandbox_loop.py](../../../../tools/dsh_sandbox_loop.py)，
   它的证据在 Adapter README 的"实测偏差"一节与阶段文档的实施记录里。

## 怎么用

1. 先跑一次测试确认环境是对的：`python -m pytest -q`；
2. 打开 notebook 从上到下执行。每个代码单元都有三段配套内容：
   **这一段代码要做什么**（读之前）→ 带逐行注释的代码 → **小结**（读之后，说明输出意味着什么）；
3. 想验证某个判断，直接改单元里的输入重跑——手册里的所有结论都来自真实模块；
4. 想先看设计意图再动手，读同目录的 [note.md](note.md)；
5. 手册把临时文件写在仓库的 `.tmp/learning/<uuid>/` 下（受治理的临时项目、
   adapter 配置、审计 JSONL 都在那里），看完可以 `python tools/cleanup.py` 清理。

## 单元卡住不返回怎么办

手册里的代码没有网络、没有大文件；最慢的单元是"判定超时"，它故意睡 300ms。
如果第一个单元就一直没有输出，问题在内核启动而不是代码：

已知触发条件：在受限沙箱（文件系统只允许写工作区）里运行 Jupyter，
内核启动时给连接文件设置 ACL 会被拒绝，Jupyter 只等待而不会报错：

    ipykernel: error (5, 'SetFileSecurity', 'Access is denied.')

三种可用的替代方式：

1. 在普通 Jupyter / VS Code 中打开本 notebook；
2. 运行同内容的纯 Python 版本：`python docs/project/learning/phase-2/walkthrough.py`；
3. 直接用根 README 里的 Hook 自检命令做最小验证。

三条路径使用同一套模块，结论一致。

## 常见问题

**为什么说"block 路径执行器调用 0 次"就是行为控制，而不是建议？**
因为执行器是 Hook 自己去调的：判定为 block 时它根本不会走到 `executor.execute`。
单元 7 用假执行器把这件事变成可断言的数字（`{"block": 0, "allow": 1}`），
测试 `tests/integration/test_dsh_hook.py` 用的是同一套断言。

**layer 没声明就阻断，为什么不能默认成 module？**
猜错 layer 会让规则在错误的范围上生效——本该管住 controller 的规则可能一次都不参与判断。
所以 Adapter 只接受"配置里声明过"的值；唯一允许的放宽方式是显式写 `default_layer`，
它出现在配置里、可以被评审与 diff，而猜测不会留下任何痕迹。

**为什么 `write` 映射成 `operation=create`，而不是 `edit`？**
dsh 的 write 是 create-or-overwrite，一个字符串表达不了两种语义，映射表只能选一个。
代价是"只为 edit 声明 operation 的规则不会命中 write"；需要同时覆盖时把 operation 写成
`[create, edit]`（同维度多值 = OR）。这种不命中不会静默：skipped_rules 会写出原因。

**为什么放行时 stdout 必须为空？**
dsh 在退出码为 0 且 stdout 以 `{` 开头时，会把它当作结构化输出解析。
Hook 提前打一行日志，就可能被当成"结构化结果"读走；因此所有诊断只写 stderr，
stdout 留给真正的结构化输出（单元 10 用真实子进程验证了这一点）。

**手册为什么不真的启动 dsh？**
因为手册要验证的是"事件 -> 决策 -> 执行/阻断"这条**确定性**链路，它不需要 Agent 参与。
dsh 的真实闭环是不可复现的（模型行为、网络、凭据），属于沙箱脚本与阶段证据，
不属于每个读者都能重跑的手册。

**官方 Hook 桥不是能阻断吗？为什么还要一个进程内插件？**
本机实测（dsh CLI 0.1.5-rc.1 + Hook 包 0.1.5-rc.2）：官方桥**确实调用了** Hook 命令、
审计里也有 `exit_code=2` 的 block 记录，但工具仍然执行了——deny 没有传递到工具管线。
最小复现与结论写在 `src/adapters/dsh/README.md` 第 7 节。
`policy-hook.plugin.mjs` 用同一条线协议补上这一步：stdin JSON、exit 0 放行、exit 2 阻断、
stderr 即理由，另外把"起不来/被杀"和"0/2 之外的退出码"也判为阻断。

**PostToolUse 现在是什么角色？**
Phase 4 之后它是**事后验证入口**：PreToolUse 授权时会把执行前基线（路径 + 哈希 + 字节数）
写进台账，PostToolUse 取回基线、收集文件哈希与 diff、跑注册表声明的验证器，再写终态。
验证失败时 exit 2 的含义是"结果需要修复"（`post_repair_required` / `post_inconsistent`）——
副作用已经发生，它不会声称回滚成功。手册单元 8 用三种情形（结果对得上 / 语法坏了 /
目标没变）演示这条链路。

**为什么 pwsh 这类工具在单元 5 里说"不受治理"，在单元 7 里又被拦住了？**
两处说的是两件事：Adapter 层不对执行类工具做策略判定（它的 `kind=execute`，没有文件上下文），
但 Hook 会把它们交给 Phase 4 的 Tool Registry——主体没有 `shell.exec` 就 `permission_denied`，
命令不在白名单就 `command_not_allowlisted`，命令里带分号等组合片段就
`command_composition_blocked`。只有只读工具（`read` / `glob` / `grep`）是真正的"显式降级"：
放行，但审计里记 `not_governed`。

**配置里少了 `registry` 会怎样？**
受控工具一律阻断（`enforcement_unavailable`）。这是有意为之："忘记接线"不能退化成
"没有治理"。单元 9 的失败关闭表里有这一条。

**单元输出里的时间戳每次都变，正常吗？**
正常。审计记录里的 `timestamp` 与 `elapsed_ms` 每次都不同；
但 fixture 的 `payload_digest`、规则集哈希 `rule_set_hash` 与所有退出码必须每次一致——
生成器从两个工作目录各跑一遍全部单元并断言退出码，任何不一致都会让生成失败。

**为什么临时目录用 `mkdir + uuid`，不用 `tempfile.mkdtemp`？**
受限沙箱会拒绝 `mkdtemp/chmod`，报出的权限错误与规则加载本身无关，很容易误导排查。
仓库测试（`tests/conftest.py`）与手册因此统一用"固定根目录 + uuid 子目录"。

## 怎么维护

notebook 由 `tools/build_learning_notebook.py` 生成，**不要手改 .ipynb**：

    python tools/build_learning_notebook.py --phase phase-2   # 重新生成并逐单元执行校验
    python tools/build_learning_notebook.py --check           # 只校验是否与生成器一致
    python tools/check_notebook.py docs/project/learning/phase-2/walkthrough.ipynb

生成器会从**两个工作目录**（仓库根、`docs/project/learning/phase-2/`）各跑一遍全部代码单元，
断言三个单元的退出码序列（单元 27 block/allow、单元 31 四类失败关闭、单元 35 CLI 三态），
并核对文档里写过的对象字段名（PolicyEvent 16 个、PolicyContext 13 个、审计记录 23 个），
因此"说明与示例不一致"会在生成阶段失败。

改内容时注意两条约定：

- 单元里只写 `.tmp/` 下的路径，不碰仓库其它文件；
- 退出码断言靠"打印文本里出现 `退出码 <数字>`"定位：新增打印时要么有意纳入断言，
  要么换一个说法，否则生成会失败（这正是它的作用）。

新增阶段时：把单元内容加到 `tools/build_learning_notebook.py` 的 `PHASE_N_CELLS`，
在 `PHASES` 里注册，然后运行上面的命令。

## 与其他文档的分工

| 文档 | 读者 | 回答什么 |
| --- | --- | --- |
| `../../engineering-policy-platform/phases/phase-2-dsh-adapter.md` | 实施者 | 本阶段要做什么、如何验收 |
| `../../../src/adapters/dsh/README.md` | 接线的人 | dsh 的 Hook 契约、工具参数、失败语义与实测偏差 |
| `../../../tests/fixtures/agent_events/dsh/README.md` | 写测试的人 | 每个 fixture 的场景、预期与脱敏方式 |
| [note.md](note.md)（本目录） | 想搞懂结构的人 | 有哪些对象、关系如何、边界在哪 |
| [walkthrough.ipynb](walkthrough.ipynb)（本目录） | 想动手的人 | 实际跑起来是什么样、为什么这么设计 |
| 根 `README.md` | 使用者 | 怎么装、怎么跑 |
