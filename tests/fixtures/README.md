# 测试夹具

每一项都说明用途、预期结果、关联规则，以及是否包含敏感数据。
根据[测试策略](../../docs/project/engineering-policy-platform/testing/test-strategy.md)，禁止加入真实凭据、用户数据或生产日志。

## 仓库内可执行示例（examples/）

| 文件 | 用途 | 预期结果 | 关联规则 | 敏感数据 |
| --- | --- | --- | --- | --- |
| examples/bad_controller.py | 反例：Controller 直接依赖 Repository | 退出码 1，ARCH-001@1 BLOCK | ARCH-001 | 无 |
| examples/good_controller.py | 正例：Controller 只依赖 Service | 退出码 0，ALLOW | ARCH-001 | 无 |
| examples/bad_repository.py | 反例的依赖目标（自身不违规） | 不参与判定 | 无 | 无 |
| examples/good_service.py | Service 依赖 Repository，说明范围边界 | 不参与判定（layer 不在 scope 内） | ARCH-001（范围不匹配） | 无 |

示例文件把直接依赖写在文件末尾的注释里，避免"文档写一套、命令跑另一套"。
CLI 判定只使用显式传入的 --dependencies，或文件的 import 顶层模块名；两者都不做语义猜测。

## 规则夹具（policies/ 与测试内联文档）

| 来源 | 用途 | 预期结果 |
| --- | --- | --- |
| policies/architecture/ARCH-001.yaml | 本项目唯一的真实规则 | 加载为 ARCH-001@1 |
| tests/conftest.py::RULE_DOCUMENT | 单元测试的规则原型 | 合法规则基线，可整体替换字段 |
| tests/conftest.py::make_rule | 按原型构造规则变体（severity / scope / 审批） | 只覆盖本次测试关心的字段 |
| tests/unit/test_loader.py 内联 YAML | 破损 YAML、错误类型、重复 ID、非映射文档 | 抛出 RuleFileError 并带路径/字段 |
| tools/policy_bench.py::generate_rules | 固定种子的合成规则（10 / 100 / 1000 条） | 同种子得到同规则集哈希 |

除协议快照与 Agent 事件外不引入独立 fixture 目录：其余变体都由 RULE_DOCUMENT 深拷贝生成，
避免"夹具与真实规则漂移"这一类静默失效。

## Agent 事件 fixture（agent_events/）

Phase 2 起引入：Agent Runtime 送来的事件是**外部事实**，不能由测试内联构造，
否则"接口变了测试还绿"这一类静默失效无法发现。每个 Adapter 一个目录，附版本说明：

| 目录 | 内容 | 说明 |
| --- | --- | --- |
| agent_events/dsh/ | dsh PreToolUse 载荷（allow / block / 拒绝路径） | 采集自真实 dsh，已脱敏；见该目录 README.md |

新增 Agent Adapter 时必须同时新增：最小真实事件 fixture、产品版本记录、
以及"未知事件/未知工具/缺失路径被拒绝"的用例。

## 决策协议快照（decisions/）

Phase 1 起决策载荷带 `schema_version`，这四份快照就是"协议不许悄悄变"的守门人：

| 文件 | 场景 | 关键点 | 敏感数据 |
| --- | --- | --- | --- |
| allow.json | controller 只依赖 service | 有命中规则、无违规，`required_action` 为 null | 无 |
| warning.json | 命中 warning 规则 | decision = allow_with_warnings | 无 |
| block.json | 命中 error 规则 | decision = block，evidence 带 file 与 detail | 无 |
| approval.json | 命中带审批门禁的规则 | decision = block 且 `required_action` = approval，无违规 | 无 |

快照由 `tests/contract/test_decision_protocol.py` 比对与校验，覆盖：

- 载荷与当前实现逐字段一致；
- `parse_decision` 能把快照解析回模型，并与重新计算的结果完全一致；
- 未知 `schema_version`、未知 `decision`、未知 `required_action` 一律被拒绝。

**更新方式**（只在确实要改协议时执行，并在提交信息里说明兼容性）：

```powershell
$env:POLICY_UPDATE_SNAPSHOTS = "1"; python -m pytest tests/contract -q
Remove-Item Env:POLICY_UPDATE_SNAPSHOTS
```

快照里的 `rule_set_hash` 由测试内联的规则集算出，不随仓库 `policies/` 变化而变化。

## 检索语料与评测集（retrieval_corpus/ 与 retrieval_eval/）

Phase 3 起引入：文档分块、索引幂等、查询安全与 Context 组装都需要**稳定的语料**，
但语料文件的哈希必须由运行时计算（手写哈希会随内容改动立刻漂移）。因此：

| 目录 | 内容 | 说明 |
| --- | --- | --- |
| retrieval_corpus/ | 夹具 Markdown（front matter、代码块内的 "#" 注释行、重复标题、空章节、受限样本、注入样本） | 镜像 manifest.json 与摄取清单由 tests/conftest.py 在临时目录里生成，sha256 运行时计算 |
| retrieval_eval/queries.yaml | 版本化固定评测集：中文查询、期望文档、supporting_terms 与门槛 | 门槛随评测集版本记录，代码里没有"脱离数据的常数"；改动必须递增 version 并重跑 tools/retrieval_eval.py |

详见 [retrieval_corpus/README.md](retrieval_corpus/README.md)。

## 验证器夹具（validators/）

Phase 5 起引入：代码验证器需要**能被破坏的样本**与**能被扮演的坏工具**，否则"失败关闭"
只能靠读代码相信。夹具全部是合成内容，不含真实凭据、用户数据或生产日志。

| 目录 | 内容 | 说明 |
| --- | --- | --- |
| validators/project/ | 最小受控项目：正例 / 反例 Controller、动态 import、无法解析的依赖、语法错误、风格问题、缺 docstring、同名测试 | 依赖图、docstring、外部工具与测试验证器都用它；`tests/conftest.py` 只在**仓库自己的收集路径**上屏蔽它的 tests/，夹具项目内部仍可被测试验证器真的收集 |
| validators/tools/fake_tool.py | 假工具：`ok / findings / empty / garbage / flood / config_error / crash / slow / old / injection` | 失效与边界分类的稳定复现；`slow` 会派生心跳子进程，用来证明超时终止的是整棵进程树 |

详见 [validators/README.md](validators/README.md)。

## 性能基线夹具

`tools/policy_bench.py` 用固定种子（默认 `20260101`）生成规则与上下文：
测试断言"同种子 → 同规则集哈希 → 同决定"，阶段证据记录耗时与内存峰值。
环境不同时耗时与内存会浮动，因此测试只断言数量级上限，不做精确比较。

## 临时目录

测试使用 conftest.py 提供的 tmp_root fixture（仓库内 .tmp/tests/<uuid>/），
刻意不使用 pytest 的 tmp_path：后者依赖 tempfile.mkdtemp，在受限沙箱里会被拒绝，
产生与规则加载本身无关的权限错误。tmp_root 在所有环境下行为一致，并在用例结束后清理。
