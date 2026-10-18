"""订单审计台账的演示脚本。

在项目根目录运行：python tools/audit_demo.py
stdout：OrderService 审计条目的 JSON 数组（ensure_ascii=False、sort_keys=True）。
"""

import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shop.order_service import OrderService  # noqa: E402


def main() -> int:
    """创建两笔订单并打印审计条目。"""
    service = OrderService()
    service.create({"id": 1})
    service.create({"id": 2})
    entries = service.audit_entries()
    print(json.dumps(entries, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
