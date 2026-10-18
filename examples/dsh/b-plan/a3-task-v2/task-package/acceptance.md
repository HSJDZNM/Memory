| id | 检查 | 判定方式 |
| --- | --- | --- |
| A1 | `OrderService().create({"id": 1})` 返回 `{"id": 1}`；`audit_entries() == [{"action": "create", "order_id": 1}]` | 隐藏用例 |
| A2 | `OrderService(repository=fake_repo, audit=fake_audit)` 两条注入都生效 | 隐藏用例（替身） |
| A3 | 只注入 `audit`、不注入 `repository` 时默认 `OrderRepository` 仍生效 | 隐藏用例 |
| A4 | `OrderAudit().entries()` 返回副本：改返回值不影响内部 | 隐藏用例 |
| A5 | `OrderController().create(...)` 与 `audit_entries()` 都只转发；controller 不直接依赖 `shop.order_repository` | 隐藏用例 + AST 检查 |
| A6 | 项目根 `python -m pytest -q` 全绿 | 树执行 |
| A7 | `python tools/audit_demo.py` 退出码 0，stdout 是合法 JSON 数组（脚本已在基线预置，只运行不修改） | 树执行 |
| A8 | 改动文件集合 ⊆ 1.5 的允许写集合（基线预置的 demo 不算改动） | 树 diff（`ab_measure --baseline-tree`） |
