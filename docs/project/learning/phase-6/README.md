# Phase 6 学习手册 · 多 Agent Adapter

这份手册用**实际运行的代码**走一遍 Phase 6：让真实 dsh、一个合成 JSON 消费者和一个
合成的“只有 PostToolUse”消费者通过同一套协议接受一致治理。后两者不是第二个真实产品接入。

## 怎么用

```powershell
jupyter lab docs/project/learning/phase-6/walkthrough.ipynb     # 交互式阅读
python docs/project/learning/phase-6/walkthrough.py             # 纯 Python 版，直接看输出
python tools/run_notebook_in_kernel.py docs/project/learning/phase-6/walkthrough.ipynb
```

## 手册里有什么

| 小节 | 内容 |
| --- | --- |
| 1 | 规范事件 Schema：受控字段、版本轴、未知事件被拒绝 |
| 2 | 支持矩阵：能力声明 → 上限（数据决定结论） |
| 3 | 同一语义场景渲染成三家线协议（差异留在 Adapter） |
| 4 | 一致性套件：12 个语义场景、逐 Adapter coverage；不支持项显式记为 inapplicable |
| 5 | 能力不足：只读上限与 `capability_unavailable` |
| 6 | 隔离与熔断：命名空间、伪造 trace、循环终止 |
| 7 | 事件 → 上下文 → 决策的完整链路与原生响应 |
| 8 | 漂移检测、路径越界、未知工具/事件、响应脱敏 |
| 9 | 多 Agent 闭环（`tools/agent_loop.py`）与结论 JSON |

手册中的 dsh 写动作显式装配确定性的 Phase 5 证据夹具和真实 Phase 4 pre-check；该证据夹具只用于
Adapter 一致性演示，不替代生产验证器流水线。

## 怎么维护

手册内容**不在 notebook 里手改**。改 `tools/phase6_cells.py`（单元内容），然后：

```powershell
python tools/build_learning_notebook.py --phase phase-6
```

生成器会做四件事：

1. 写出 `walkthrough.ipynb` 与 `walkthrough.py`（纯 Python 版）；
2. 从仓库根与 `docs/project/learning/phase-6/` **各跑一遍全部代码单元**；
3. 执行 `tools/phase6_cells.check_phase_6_structure`：核对套件结果、阻断是否真的发生、
   熔断是否出现、闭环是否通过——任何一条不成立都让生成失败；
4. 版本检查模式下（`--check`）比对 notebook 与生成器是否一致。

## 常见问题

**手册会动我的仓库吗？**
不会。临时产物都在 `.tmp/notebook-demo/phase-6/` 下，受控工作区是仓库内的只读探针
`tests/fixtures/agent_events/workspace/`；跑完用 `python tools/cleanup.py` 清理。

**为什么手册里每次都要删掉临时目录？**
台账是"本轮"的幂等记录。复用上一轮的文件会让本轮的事件立刻被判成重放或熔断，
失败原因就与被测行为无关了——这个坑在实现阶段真的踩过一次。

**为什么有些 Adapter 在渲染场景时会报错？**
那是**能力事实**，不是缺陷：`legacy-post-only` 声明的事件里没有 `tool.pre_execute`，
一致性套件因此无法为它渲染执行前场景，于是显式失败而不是静默跳过。

**想自己接一个 Agent？**
先写 `adapters/<id>/manifest.yaml`（事件名、工具表、能力），再写适配器类（通常继承
`EventAdapter` 或 `JsonAdapter`），然后在 `src/adapters/loader.py` 的 `ADAPTER_FACTORIES`
登记协议名，最后跑 `python -m adapters.cli approve --reviewer <name>` 审核能力声明。
完整流程见阶段文档的"Adapter 升级流程"。
