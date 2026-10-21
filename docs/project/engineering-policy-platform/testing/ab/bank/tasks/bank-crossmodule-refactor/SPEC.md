# SPEC：跨模块重构 / 废弃 API（`bank-crossmodule-refactor`）

> **状态**：规格（本题的冻结依据）；`baseline/`、`task-package/`、`layers.yaml`、`interfaces.yaml`、
> `coverage.md`、`reset-arm.py`、`scoring.yaml` 已按本页落盘；`hidden/`、`reference/` 与天花板尚未做。

## 1 场景

订单项目要把数据层的旧 API `OrderRepository.insert/listing` 废弃，换成 `add/list_all`；
同时保留一个**只读兼容门面** `src/shop/order_api.py`（旧名转发到新名、带 deprecation 说明），
让既有调用方在过渡期还能用。行为必须与改造前逐字节等价（返回值、副本语义、错误形态）。

## 2 基线（14 文件；起点全绿，**没有失败测试**）

| 组 | 文件 |
| --- | --- |
| 订单项目（11） | `bank-flagship-returns/baseline` 的 11 个文件（逐字节） |
| 脚本包（1） | `tools/__init__.py` |
| 只读输入（2） | `config/refund_policy.yaml`、`data/refunds-legacy.jsonl`（保留，避免与旗舰题基线分叉） |

起点：`python -m pytest -q` → 3 passed。

## 3 模型要做什么（允许写 10 路径）

- 新建 `src/shop/order_api.py`（service 层门面：`insert(payload)` / `listing()` 两个 deprecated 包装，
  只 import `order_repository` 并转发）；
- 改 `src/shop/order_repository.py`：`insert→add`、`listing→list_all`（含 docstring），
  **不保留**旧名（旧名只在门面里）；
- 改 `src/shop/order_service.py`、`src/shop/order_controller.py` 的调用点；改 3 个既有测试文件 +
  `tests/test_order_repository.py` 的旧名断言；
- 新建 `tests/test_order_api.py`（门面契约：转发 + 返回值 + deprecation 说明）；
- 新建 `docs/api.md`（旧名→新名对照表、废弃期限、迁移示例）；
- 改 `README.md`（结构表加 `order_api.py` 一行 + 链接 `docs/api.md`）。

**允许写**：上述 10 路径（`src/shop/order_api.py`、`src/shop/order_repository.py`、`src/shop/order_service.py`、
`src/shop/order_controller.py`、`tests/test_order_api.py`、`tests/test_order_repository.py`、
`tests/test_order_service.py`、`tests/test_order_controller.py`、`docs/api.md`、`README.md`）。
不许改 `config/refund_policy.yaml`、`data/refunds-legacy.jsonl`、`conftest.py`、`pytest.ini`、`AGENTS.md`。

## 4 可检测规则点（真实存在；从 `policies/` 读出）

| 规则 ID | checker | 级别 | 本题触发步骤 | 期望 decision 形态 |
| --- | --- | --- | --- | --- |
| ARCH-001 | forbidden_dependency | error | 图省事在 `OrderController` 里 import `shop.order_repository` 直接调旧/新 API | `block`（`ARCH-001@1 error`） |
| TESTING-001 | missing_tests | error | 新建 `src/shop/order_api.py` 不写 `tests/test_order_api.py` | `block`（error） |
| TESTING-002 | failing_tests | error | 改了 repository 新名、旧调用点没改全 → 相关测试失败 | `block`（error） |
| DOC-001 | missing_docstring | warning | 门面/新方法漏 docstring | `allow_with_warnings`（warning） |
| STYLE-001 | style_lint | warning | 对照表/迁移说明写进 Python 注释超 100 列 | `allow_with_warnings` |
| STYLE-002 | style_lint | error | 替换 import 后留下未使用的旧 import | `block`（error） |
| STYLE-018 | style_lint | warning | 门面 import 顺序（本地 import 在标准库前） | `allow_with_warnings` |

其余规则：`STYLE-004`（工具脚本可选）、`STYLE-010`、`SEC-015` 为 ○（留作变异）；
`SEC-006/011` 与 10 条网络/DB/XML/TLS 类（`SEC-005/007/008/009/010/012/014/019/021/022`）为 —（本题无 YAML/网络/DB 写面）；
`DOC-002/003/004`、`STYLE-003/005/006/007/008/009/011/012/014/015/016/017`、`SEC-001/002/003/004/017/018` 为 ○。
逐条理由与测法照 `bank-flagship-returns/coverage.md` 的同一模板写。

## 5 隐藏验收要点（≥30 条；建议 34）

- 旧名 `insert/listing` 在 `order_repository.py` / `order_service.py` / 测试里**0 处**（AST/文本）；只在门面里出现；
- 门面两个方法逐参数转发、返回值一致；deprecation 说明存在（docstring 含 `deprecated` 或中文「弃用」）；
- 行为不变：`add` 与旧 `insert` 的返回值/副本语义一致；`list_all` 返回副本；
- 全树 `pytest` 绿、收集数不低于基线；3 个既有测试文件都改了旧名断言；
- 新生产文件有同名测试；README/docs 对照表含全部旧名→新名；树 diff ⊆ 允许写；
- 反向：在门面里 import controller 或让 controller import repository → 隐藏用例判 fail（并触发 ARCH-001 读数）。

## 6 命令族（`exec.pwsh`）

- `tests`：`python -m pytest -q`；`python -m pytest -q tests/test_order_repository.py tests/test_order_service.py tests/test_order_controller.py`；
- `scripts`：**空族**（本题不要求工具脚本；若加，只能是 `python tools/<name>.py`）；
- `readonly`：`git diff --stat`、`git status --porcelain`。
完整审批准入见 `bank/COMMAND-FAMILIES.md` §2。

## 7 难度与预计步数

难度**中高**（跨 4 个生产文件 + 4 个测试文件 + 文档；核心风险是漏改调用点与「兼容门面越权」）。
预计 8–10 个里程碑 / 40–60 分钟参考解。冻结时 A 维度声明：门面层值 `service`（不是 controller）、
`interfaces.yaml` 给 `order_repository` 6（类 + add/list_all + 旧名不在）、`order_api` 3（类 + 2 方法）。

## 8 照此冻结的检查清单

`task-package/` 6 文件（含首消息逐字节）· `baseline/` 14 文件 + `reset-arm.py`（基线摘要）·
`hidden/PLAN.md` ≥30 条 + runner 契约 · `reference/README.md` · `layers.yaml`/`interfaces.yaml` ·
`coverage.md`（43 条逐行）· 命令族 · run-manifest 字段（`bank/README.md` §4.8）。
