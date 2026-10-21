# 验收表（bank-crossmodule-refactor）

> 判定方式三档：**隐藏用例**（另一子会话按 `hidden/PLAN.md` 实现，最终树只读）、
> **树执行**（在最终树的副本里跑命令，只看退出码/输出）、**树 diff**（最终树 vs 14 文件基线）。
> 本表与 first-message.md 的「验收表」逐字对应（本文件加了行内代码，去掉反引号即逐字相同）；改一处必须改另一处。
> 隐藏代码**尚未写**：本表是判据，不是读数；A1–A10 的实测状态见 `coverage.md` §6。

| id | 检查 | 判定方式 |
| --- | --- | --- |
| A1 | `OrderRepository.add` 与旧 `insert` 逐项等价：`add({"id": 1})` 返回 `{"id": 1}` 且是副本（改返回值不影响内部）；改入参不影响内部；`list_all()` 每次返回新的 list 与新的 dict | 隐藏用例 |
| A2 | 旧名 `insert`/`listing` 在 `src/shop/order_repository.py`、`order_service.py`、`order_controller.py` 与三个既有测试文件里 0 处（AST 与文本两种读法都查）；旧名只出现在 `src/shop/order_api.py` 与 `tests/test_order_api.py` | 隐藏用例 + AST |
| A3 | 调用链贯通：`OrderService.create` 调 `repository.add`、`OrderService.list_all` 调 `repository.list_all`（替身记录调用）；`OrderController.list_all` 调 `service.list_all` | 隐藏用例 |
| A4 | `OrderApi` 只转发：构造器恰一个必填位置参数 `repository`；`insert`/`listing` 逐参数转发并原样返回同一个对象；文件里不 import `order_service` / `order_controller`，也不出现 `OrderRepository(` 调用 | 隐藏用例 + AST |
| A5 | 门面弃用说明：模块、类、`insert`、`listing` 的 docstring 都存在，两个方法 docstring 各含「弃用」或 `deprecated` 且写出新名（`add` / `list_all`） | 隐藏用例 |
| A6 | 项目根 `python -m pytest -q` 全绿；`--collect-only` 收集数 ≥ 4；`tests/test_order_api.py` 至少 3 条用例、每个测试文件至少 1 条 assert、无 `skip`/`xfail` | 树执行 |
| A7 | `docs/api.md` 有 `## 对照表` / `## 废弃期限` / `## 迁移示例` 三个二级标题且正文非空；对照表含 `insert`、`listing`、`add`、`list_all`；废弃期限写明保留到 `v2.0` 发布为止；迁移示例含代码块与 `OrderApi`、`add(` / `list_all(` | 隐藏用例 |
| A8 | `README.md` 的结构表含 `src/shop/order_api.py` 一行，且文末链接 `docs/api.md` | 隐藏用例 |
| A9 | 行为不变：同一份输入（含不可映射的 payload）分别在原始基线与改造后的树上跑 `controller.create` / `controller.list_all`，返回值逐字节相等、异常类型相同 | 树执行 + 隐藏用例 |
| A10 | 改动文件集合 ⊆ 允许写的 10 条；基线 14 文件里不属于允许写集合的 7 个逐字节不变 | 树 diff |
