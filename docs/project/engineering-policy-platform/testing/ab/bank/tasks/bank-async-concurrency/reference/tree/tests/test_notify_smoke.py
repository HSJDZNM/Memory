"""notify_smoke 的用例：脚本返回去重后的 2 条记录。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.notify_smoke import main  # noqa: E402


def test_smoke_returns_two_records() -> None:
    """main() 返回去重后的 2 条记录：smoke-1 在前、smoke-2 在后。"""
    records = main()
    assert [record["key"] for record in records] == ["smoke-1", "smoke-2"]
    assert records[0]["order_id"] == 1
    assert records[1]["kind"] == "sms"
