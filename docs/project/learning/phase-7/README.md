# Phase 7 学习手册 · Policy API

这份手册用**实际运行的代码**走一遍 Phase 7：把已经稳定的规则判定服务化，同时证明
"服务化之后语义没有变"。它**不起端口、不联网**——第 7 节用进程内调用助手
`policy_api.testing.build_runtime` + `call` 走**同一条判定路径**
（HTTP 层只是它的一个调用方），因此跑完一遍只需要几秒。

## 怎么用

```powershell
$env:PYTHONPATH = 'src'
jupyter lab docs/project/learning/phase-7/walkthrough.ipynb     # 交互式阅读
python docs/project/learning/phase-7/walkthrough.py             # 纯 Python 版，直接看输出
python tools/run_notebook_in_kernel.py docs/project/learning/phase-7/walkthrough.ipynb
```

## 手册里有什么

| 小节 | 内容 |
| --- | --- |
| 0 | 前提：怎么跑、需要什么、临时产物写在哪 |
| 1 | DTO 与领域模型分开：两套版本、信封形态、未知字段 400 |
| 2 | 错误码 → 状态码：受控枚举、跨租户与不存在同码 |
| 3 | 配置即数据：租户 / 客户端 / 预算，明文令牌拒绝加载 |
| 4 | 认证与隔离：四条失败路径与 `token_ref` |
| 5 | 预算与超时：调用方只能要更小的预算，超时是 `(None, timed_out=True)` |
| 6 | 幂等台账：同键同摘要返回原响应，同键换请求体 409 |
| 7 | 进程内完整链路：本地引擎与 API 的决定**整份相等** |
| 8 | readiness 与观测：逐项检查、记录字段、摘要链锚定 |
| 9 | 失败关闭对照表（14 条路径，每一行都是本次运行真实发生的调用） |

**整份手册最重要的一个断言**在第 7 节：`policy.engine.evaluate` 在进程内算出的决策
载荷，与 API 返回的 `body["decision"]` 必须**整份字典相等**。

## 怎么维护

手册内容**不在 notebook 里手改**。改 `tools/phase7_cells.py`（单元内容与结构断言），
然后运行：

```powershell
python tools/build_learning_notebook.py --phase phase-7
```

生成器会做四件事：

1. 写出 `walkthrough.ipynb` 与 `walkthrough.py`（纯 Python 版）；
2. 从仓库根与 `docs/project/learning/phase-7/` **各跑一遍全部代码单元**；
3. 执行 `tools/phase7_cells.check_phase_7_structure`：核对部署配置里的租户与客户端、
   `STATUS_BY_CODE` 的关键映射、认证失败路径、预算与超时、幂等结果、
   本地/API 决策一致、readiness 与逐项检查一致、观测日志不含凭据与绝对路径、
   锚定校验通过、失败关闭对照表——任何一条不成立都让生成失败；
4. 版本检查模式下（`--check`）比对 notebook 与生成器是否一致。

提交前跑 `python tools/check_notebook.py docs/project/learning/phase-7/walkthrough.ipynb`。

## 常见问题

**手册会起服务、会联网吗？**
不会。第 7 节用的是进程内调用（`build_runtime` + `call`），和 HTTP 层调的是
同一个 `ApiRuntime.handle`。要验证真实 HTTP 语义（请求头、状态码、405/404 的形状）
时看 `tools/api_loop.py`：它会在 127.0.0.1 上起一个真实端口，逐场景比对本地与
经 API 的决定。

**手册会动我的仓库吗？**
不会。所有产物都在 `.tmp/learning-phase-7/` 下，而且每个代码单元开始前先删再建：
坏配置、幂等台账、观测日志、被删尾的日志副本都在那里。跑完用
`python tools/cleanup.py` 清理。

**为什么第 8 节的 readiness 有时是 `degraded`？**
那是**真实缺陷的照实显示**，不是手册的偶发问题：租户的 `validators` 是配置里的
相对路径，加载方按进程工作目录解析它。细节见同目录 `note.md` 的最后一节。

**为什么第 9 节要临时替换 `policy_api.runtime.evaluate`？**
为了确定性地演示"预算到点返回 504"。替换发生在一个 `try / finally` 里，用完立刻
还原；被拖慢的那次判定仍然会跑完，只是结果被丢弃——这正是手册反复强调的
"超时 = 调用方不再等待"。

**手册里的令牌是真的吗？**
不是。`local-dev-token` / `dsh-agent-token` / `ops-monitor-token` 是仓库
公开的**演示值**，同时写在 `tests/fixtures/api/README.md` 里；配置里存的只有它们的
sha256。真实部署请用 `python -m policy_api.cli clients --hash` 生成自己的摘要。

**想自己跑一次真实 HTTP 闭环？**

```powershell
$env:PYTHONPATH = 'src'
python -m policy_api.cli self-check      # 装配 / readiness / 传输契约自检
python -m policy_api.cli openapi --check # 契约快照是否漂移（CI 门禁）
python tools/api_loop.py                 # 八个场景的闭环（真端口）
```
