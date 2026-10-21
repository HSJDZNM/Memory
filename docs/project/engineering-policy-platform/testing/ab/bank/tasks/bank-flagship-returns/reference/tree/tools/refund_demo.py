"""退货演示：内存仓储 + 控制器创建两笔退货。"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from shop.order_repository import OrderRepository  # noqa: E402
from shop.refund_controller import RefundController  # noqa: E402
from shop.refund_policy import load_policy  # noqa: E402
from shop.refund_repository import RefundRepository  # noqa: E402
from shop.refund_service import RefundService  # noqa: E402

_POLICY_PATH = _ROOT / "config" / "refund_policy.yaml"


def main(policy_path: Path | None = None) -> list[dict]:
    """跑两笔退货并返回列表；策略默认按 __file__ 定位，不靠 cwd。"""
    policy = load_policy(_POLICY_PATH if policy_path is None else Path(policy_path))
    orders = OrderRepository()
    orders.insert({"id": 1, "total_cents": 1000})
    orders.insert({"id": 2, "total_cents": 500})
    service = RefundService(
        orders=orders,
        refunds=RefundRepository(),
        policy=policy,
    )
    controller = RefundController(service)
    controller.create_refund(1, 1000, "damaged", "demo-1")
    controller.create_refund(2, 500, "late", "demo-2")
    return controller.list_refunds()


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, sort_keys=True))
