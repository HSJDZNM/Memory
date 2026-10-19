# src/shop/order_audit.py（新建）
class OrderAudit:
    """记录订单动作的审计台账（内存实现）。"""
    def __init__(self) -> None: ...
    def record(self, action: str, order_id: int) -> dict: ...
    def entries(self) -> list[dict]: ...

# src/shop/order_service.py（改）
class OrderService:
    def __init__(self, repository: OrderRepository | None = None,
                 audit: OrderAudit | None = None) -> None: ...
    def create(self, payload: dict) -> dict: ...      # 签名不变，成功后记一条 ("create", id)
    def audit_entries(self) -> list[dict]: ...        # 新增

# src/shop/order_controller.py（改）
class OrderController:
    def audit_entries(self) -> list[dict]: ...        # 新增，只转发

# tools/audit_demo.py（新建，演示脚本）
def main() -> list[dict]: ...                        # 构造 OrderService、创建两笔订单、返回 audit_entries()
# 运行：python tools/audit_demo.py（项目根）
# __main__：print(json.dumps(main(), ensure_ascii=False, sort_keys=True))

# tests/test_audit_demo.py（新建，契约测试）
# 从 tools.audit_demo 导入 main，断言 main() == [{"action": "create", "order_id": 1},
#                                              {"action": "create", "order_id": 2}]
# 基线已有 tools/__init__.py：tools 因此是**项目内**包（缺的是 tools.audit_demo 这个模块，不是第三方包）
