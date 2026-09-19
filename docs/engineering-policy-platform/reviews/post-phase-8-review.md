# Post-Phase-8 独立验收与修复记录

> 本文记录 2026-09-19 对 Engineering Policy Platform Phase 0–8 收尾改动的独立验收。
> 验收基线是 `7f96039^`，范围为 `7f96039` 至 `123d177` 的 8 个提交，以及验收后针对
> 两项 Spec 缺陷补上的修复。本文区分“自动化门禁通过”“行为已被证伪验证”和
> “受外部环境限制、尚未验证”，不把三者混写。

## 1. 验收范围与方法

本轮核对以下主张：

1. D1：熔断阈值遵循“显式参数 > Adapter 声明（全体一致）> 模块常数”；
2. D2：本地引擎与 API 比较的是完整 JSON 值，不虚构字段顺序或字节契约；
3. D3 v1：环境跳过与“已验证通过”可区分，同时不改变既有 `result` 值域与门禁行为；
4. W1：seal/锚定、并发闸门、状态防正文与引擎回落分支有非空转回归；
5. W2：Phase 0 scope 语义与阶段证据路径不再陈旧；
6. 工作树、提交范围、本机门禁与阶段证据是否符合自述。

方法分三层：

- 静态审阅 `git diff 7f96039^...HEAD`，追踪配置、运行时与测试之间的真实数据流；
- 定向执行受影响测试，并检查新增断言是否能在旧实现上变红；
- 在修复与本文进入工作树后执行 `python tools/ci_local.py --full`，让文档、一致性、测试、
  闭环与阶段证据一起接受最终门禁。

## 2. 首轮验收结论

首轮门禁全部退出 0，但 Spec 审阅发现两项自动化测试没有揭示的实现缺陷，因此当时结论为
**不通过**。这说明“门禁全绿”只能证明已编码的断言成立，不能替代对断言是否覆盖真实行为的复核。

| # | 级别 | 缺陷 | 为什么原测试没有发现 |
| --- | --- | --- | --- |
| S1 | 阻断 | `max_concurrency` 的许可在 `_authenticate()` 内取得后立即释放，真正的 `_dispatch()` 尚未开始；慢请求之间不受在途上限约束 | 测试直接获取私有 `_semaphore` 制造“已满”，只证明手工占满后会返回 503，没有发出两个真实并发请求 |
| S2 | 重要 | `_resolve_thresholds()` 宣称三级优先，但 `DEFAULT_BREAKER_LIMIT` / `DEFAULT_WINDOW_SECONDS` 没有读取点；配置缺失时抛错，模块常数回退不可达 | Adapter 配置模型自己复制了 50/60 默认值，与模块常数碰巧相同，测试只比较数值，无法证明默认值来源 |

同时确认首轮测试总数的准确表述应是“收集 1110 例，`1109 passed, 1 skipped`”，不是
“1110 例全过”。跳过项是 Windows 未启用开发者模式时不能创建符号链接的安全用例；Linux CI
会实际执行该分支。

## 3. S1 修复：并发许可覆盖真实请求处理

修复位于 `src/policy_api/runtime.py`：

- `_authenticate()` 只负责认证与限流，不再取得后立即释放并发许可；
- `_concurrency_slot()` 在认证成功后进入，覆盖幂等查询/记录、业务分派和预算等待；
- `finally` 无条件释放许可，正常响应、幂等重放和异常路径都不会泄漏容量；
- `request_id` 仍在认证与并发闸门之前解析，429/503 的关联标识不回退。

回归用例 `test_concurrency_gate_limits_in_flight_requests` 只从 ASGI 入口观察行为：首个真实
`/v1/policy/evaluate` 请求进入策略评估后暂停，第二个请求在首个请求结束前必须得到
`503 policy_busy`，释放后首个请求与恢复请求都必须得到 200。测试不再读写运行时的私有信号量。

红灯证据（旧实现）：第二个请求进入业务处理并最终得到 `504 evaluate_timeout`，断言期望 503，失败。
绿灯证据（新实现）：并发用例与 429 request_id 回归共同通过。

## 4. S2 修复：三级阈值来源真实可达

修复位于 `src/adapters/base.py` 与 `src/adapters/runtime.py`：

- `AdapterConfig.max_events_per_window` / `window_seconds` 改为可选声明；省略时保留 `None`，
  不在配置模型里复制运行时默认值；
- `_resolve_thresholds()` 对每个维度分别应用显式参数、声明值、模块常数；
- 多 Adapter 一致性比较的是各自的最终有效值：省略值按模块常数参与比较，声明分歧仍失败关闭；
- `gt=0` 继续约束任何显式声明，运行时也继续拒绝非正的显式构造参数。

新增用例删除一份真实 `adapter.yaml` 中的两个阈值字段，先断言声明保持缺失，再通过公共
`AgentRuntime(...)` 构造器观察模块常数生效。旧实现会在“声明保持缺失”的断言处变红；新实现下，
声明值、显式覆盖、冲突拒绝、非正窗口拒绝和模块默认五条用例全部通过。

## 5. 其余主张的验收结果

| 项 | 结论 | 证据摘要 |
| --- | --- | --- |
| D2 JSON 值相等 | 通过 | 本地领域载荷与 API `decision` 比完整字典；幂等响应对响应的字节一致主张仍保留，没有混淆两种契约 |
| D3 v1 环境跳过 | 按声明通过 | dsh 缺失时产物写 `result: skipped`、`environment_skipped: true`；阶段证据的文件变化字段为 `null` |
| 503/429 request_id | 通过 | request_id 在认证前解析；真实并发 503 与限流 429 都断言关联标识 |
| seal/锚定 | 通过 | 未改动基线、追加条数、等长改写、未知版本四个分支均有独立断言 |
| 状态防正文 | 通过 | 超长正文与凭据形态分别按明确原因拒绝，合法短结论可进入状态 |
| 引擎回落 | 通过 | `auto` 在 LangGraph 不可用时如实报告 `reference`，显式 `langgraph` 仍失败关闭 |
| W2 文档修正 | 通过 | Phase 0 默认 scope 语义与当前模型一致；阶段证据路径跟随 `CURRENT_PHASE` |

## 6. 已知 v2 边界

以下事项没有被本轮两个 Spec 修复暗中扩大，继续作为后续工作显式保留：

1. 阶段证据顶层 `result` 仍可为 `pass`，即使 Phase 2 真实 dsh 闭环因环境而 `skipped`；
2. spawn 失败路径中的 `block_passed` / `allow_passed` 仍可能用 `false` 表示“没跑”，不是三态；
3. `hook_could_not_spawn()` 仍解析 Agent 自然语言日志；可靠判据应改为 Hook 启动见证文件；
4. `--require-dsh` 尚无负向自动化用例，常规 CI 也不要求真实 dsh 环境；
5. `adapter.yaml` 的阈值不在 `adapters/approved.json` 审核哈希范围内；
6. 一个 `AgentRuntime` 仍使用一组全局阈值，不支持 per-adapter 阈值；
7. dsh `LOGS/*.txt` 不自动清理，环境限制与接线损坏仍未由结构化见证完全区分。

此外，Phase 6 的第二真实 Agent 产品验证与 Phase 8 的真实 `ChangeAuthor` 模型实现仍是外部环境项，
不能由本仓库的合成协议消费者或替代端口宣称完成。

## 7. 过程与历史问题

- 8 个历史提交并非都满足“一个提交只做一件事”：`8a5a168` 同时覆盖 seal 与并发，
  `39995c0` 同时覆盖状态正文与引擎回落，`123d177` 同时修 scope 文档与证据路径；
- Phase 7 notebook 的实际内容源已拆到 `tools/phase7_cells.py`，但 `AGENTS.md` 仍写成只能修改
  `tools/build_learning_notebook.py`。当前生成器明确导入前者，两份仓库说明需要在后续文档维护中统一；
- `.tmp/.pytest_cache` 的 ACL 仍会产生 `PytestCacheWarning`，不影响测试结果，但会妨碍缓存写入与清理。

这些问题不改变 S1/S2 的运行时结论，但应保留在审计记录中，避免把“代码行为通过”扩写成
“提交历史与仓库说明完全合规”。

## 8. 验证证据

TDD 红灯命令：

```powershell
python -m pytest -q `
  tests/integration/test_api_http.py::test_concurrency_gate_limits_in_flight_requests `
  tests/integration/test_multi_agent_runtime.py::test_module_defaults_apply_when_thresholds_are_not_declared
```

旧实现结果：`2 failed`；分别观察到 `504 != 503` 与省略声明后仍得到 `50 != None`。

定向绿灯：

```powershell
python -m pytest -q tests/integration/test_api_http.py tests/integration/test_multi_agent_runtime.py
```

结果：`62 passed`。

最终全量门禁：

```powershell
python tools/ci_local.py --full
```

结果：30 步全部通过；主测试集 `1110 passed, 1 skipped`，跳过原因仍是 Windows 环境不能创建
符号链接。阶段证据收集 1111 例、0 failure，顶层 `result: pass`；dsh 真实闭环明确记录
`result: skipped`、`environment_skipped: true`、`block_file_unchanged: null`、
`allow_changed_once: null`。因此本轮仓库内验收通过，但不把真实 dsh 产品闭环写成已验证。

## 9. 最终结论

S1 与 S2 均已通过“旧实现变红、新实现转绿”的回归验证，完整本机门禁也通过。基于仓库内可执行
范围，Phase 0–8 的本轮收尾改动可以验收；第 6 节列出的 v2 与外部产品环境事项仍是明确缺口，
不得从本结论推导为已经完成。
