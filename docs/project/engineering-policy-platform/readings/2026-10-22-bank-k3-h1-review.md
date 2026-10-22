# 2026-10-22 题库 k≥3 · H1 第三方逐条可追溯性复核

> **性质**：H1 降级裁定后的第三方逐条复核（只读），复核者不是各题 hidden 的作者；不改 hidden/任务包/判据。
> 起点 HEAD `3ed9529`（工作树干净）；本读数只落结论与证据指针。
> **判据**：`readings/2026-10-22-bank-k3-deliberations.md` §3.2；`readings/2026-10-21-c1b-treatment-adjudication.md`
> 的 H1 口径；bank/README §4.3。「可追溯 = 指到 first-message 句子或 acceptance 的 A#；SPEC 只作辅助」。
> **阈值（预注册）**：单题 flag >2 或涉及核心语义 → 停/重出该题 hidden；≤2 且可定点修 → keep + 定点修。

## 0 一句话

async **1 flag（I5）**、docs **2 flag（I5/I7）**、crossmodule **3 flag（T21/T20/T26）**；
三题核心语义 flag 均为 **0**。按预注册阈值：async/docs 在阈值内（keep + 定点修），
**crossmodule 3 > 2 → 命中「停/重出该题 hidden」的失败关闭条件**。
**因此「可开跑」不签、27 run 不开**；等使用者裁定（重出 vs 经书面改判的定点修）。

## 1 逐题结论

| 题 | 总条数 | keep | flag | 核心语义 flag | 建议 |
| --- | --- | --- | --- | --- | --- |
| bank-async-concurrency | 38 | 37 | **1（I5）** | 0 | keep + 定点修（I5 代理） |
| bank-docs-config | 40 | 38 | **2（I5/I7）** | 0 | keep + 定点修（I5/I7） |
| bank-crossmodule-refactor | 34 | 31 | **3（T21/T20/T26）** | 0 | **按预注册：停/重出该题 hidden**（复核者建议定点修，但阈值字面为 3 > 2） |

### 1.1 async 的 flag

- **I5**：判定代理要求测试里某条 assert 的 `ast.unparse` 同时含 `已弃用` 与 `__doc__`；会误伤
  `doc = module.__doc__ or ""; assert "已弃用" in doc` 或 `inspect.getdoc(...)` 这两种满足首消息 L39 的写法。
  建议放宽为「含 已弃用 且含 `__doc__`/`getdoc`」或收窄为「原用例保留 + 无 skip + 有 assert 提及 已弃用」。
- 反向缺口 7 条（质量缺口，不记 flag）：start 重复幂等、新测试 assert/skip、main() 返回值、注入队列 maxsize、
  运行中 processed()、A6 的 AST 部分、README「其它行不动」；另 1 条次要（noqa E402 / 第三方依赖）。

### 1.2 docs 的 flag

- **I5**：`test_config` / `test_check_config` 的「测试函数」计数只扫模块顶层 FunctionDef，参数化/类内写法会被误伤；
  首消息只要求「至少 5 / 2 个测试函数」，没有限定必须顶层。
- **I7**：`src/shop/config.py` 不 import 任何 shop 模块——首消息只有「（model 层）」标签，A1–A10 无对应项；
  合法解复用 shop 常量会被误伤（概率低但无出处）。建议删除该条或补进首消息/验收表。
- 非阻断附注：T18 的 no eval/exec/compile/importlib 三条无字面出处；EN3/EN4 的输出通道隐含约定；
  T22 的标题「恰 1 次且有序」比 A7 严；I4 的 sys.path 断言等。

### 1.3 crossmodule 的 flag（命中阈值）

- **T21**：要求 `pytest tests/test_order_api.py` 单独 exit 0；首消息 A6 与【命令约束】都没有这条，
  PLAN §6.3 自述是相对 coverage 骨架的收窄。
- **T20**：controller 的 import 集合被限定为恰好 `{shop.order_service}`，而首消息只给负列表
  （不许 import repository）；`from __future__ import annotations` 等字面合规写法会被误伤。
- **T26**：迁移示例要求恰三反引号围栏，首消息只要求「代码块」；波浪线围栏（CommonMark 合法）会被误伤。
- 复核者建议：三处均为 hidden 比契约严、参考解不受影响，可定点修；**但按预注册阈值字面 flag=3 > 2，
  机械结论是停/重出**，是否按严重度重解释留 Lead/使用者裁定。本读数按预注册**不自行放宽**。

## 2 失败关闭与当前状态

- 命中 `readings/2026-10-22-bank-k3-deliberations.md` §3.2 与 05 §8 第 11 条的
  「单题 flag >2 → 停/重出该题 hidden」；也命中交接提示 §10 的「H1 复核 flag 超阈值」。
- **「可开跑」不签、27 run 不开**；1 臂 re-smoke 已完成的读数（`readings/2026-10-22-bank-k3-resmoke.md`）
  仍然有效，但它不替代 H1 门。
- 已就绪且不受影响：3 份 freeze、臂配置、run-record、审批（TTL 到 2026-10-29T12:38Z）。
- 现场：`.tmp/k3/h1/{bank-async-concurrency,bank-docs-config,bank-crossmodule-refactor}.md`（一次性）。

## 3 需要使用者裁定（二选一，均须写进读数）

1. **按预注册重出 crossmodule hidden**：另起未参与实施的子会话重写 PLAN+runner（或至少重写三条 flag 用例），
   重跑基线红/参考树天花板、重算 hidden 摘要、重冻结、重跑 H1 复核；成本较高，结论可写「独立重出」。
2. **书面改判：定点修 + 重冻结 + 重测 + 三条复核**：把 T21/T20/T26 改为「补进首消息/验收表」或「放宽断言」，
   同批修 async I5、docs I5/I7；重算 hidden/scoring/README 摘要、重冻结、重跑参考树天花板与三条复核。
   这偏离「>2 → 重出」的预注册，必须在读数写「用户改判 + 日期 + 影响面」，不能静默做。
3. 其他处置（例如换题）需同时说明 Gate 0 的替换规则是否满足（当前 docs 激活、migration 无激活，
   按预注册不允许用 migration 换 docs）。

## 4 证据指针

- 逐条表：`.tmp/k3/h1/bank-async-concurrency.md`（38 条）、`.../bank-docs-config.md`（40 条）、
  `.../bank-crossmodule-refactor.md`（34 条）。
- 输入：各题 `task-package/first-message.md` 与 `acceptance.md`、`hidden/PLAN.md`、`hidden/runner.py`。
- 预注册：`readings/2026-10-22-bank-k3-deliberations.md` §3.2；05 §8 第 11 条。
