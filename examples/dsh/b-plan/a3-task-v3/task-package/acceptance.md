| id | 检查 | 判定方式 |
| --- | --- | --- |
| A1 | `OrderService().create({"id": 1})` 返回 `{"id": 1}`；`audit_entries() == [{"action": "create", "order_id": 1}]` | 隐藏用例 |
| A2 | `OrderService(repository=fake_repo, audit=fake_audit)` 两条注入都生效 | 隐藏用例（替身） |
| A3 | 只注入 `audit`、不注入 `repository` 时默认 `OrderRepository` 仍生效 | 隐藏用例 |
| A4 | `OrderAudit().entries()` 返回副本：改返回值不影响内部 | 隐藏用例 |
| A5 | `OrderController().create(...)` 与 `audit_entries()` 都只转发；controller 不直接依赖 `shop.order_repository` | 隐藏用例 + AST 检查 |
| A6 | 项目根 `python -m pytest -q` 全绿 | 树执行 |
| A7 | 新建并运行 `python tools/audit_demo.py`：退出码 0，stdout 是合法 JSON 数组（脚本由本任务创建，不在基线里） | 树执行 |
| A8 | 改动文件集合 ⊆ 允许写的 9 个路径（新建的 `tools/audit_demo.py` 与 `tests/test_audit_demo.py` 算改动） | 树 diff（`ab_measure --baseline-tree`） |
