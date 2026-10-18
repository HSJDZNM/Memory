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

# tools/audit_demo.py（基线预置，只运行不修改）
# 运行：python tools/audit_demo.py
# stdout = json.dumps(service.audit_entries(), ensure_ascii=False, sort_keys=True)
