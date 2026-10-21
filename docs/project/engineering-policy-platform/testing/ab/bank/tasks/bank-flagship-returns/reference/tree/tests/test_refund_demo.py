"""refund_demo 的用例：两条记录与脚本入口。"""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.refund_demo import main  # noqa: E402


def test_main_returns_two_records() -> None:
    """演示返回两条记录，fee 分别是 25 与 12。"""
    records = main()
    assert [record["refund_id"] for record in records] == [1, 2]
    assert [record["fee_cents"] for record in records] == [25, 12]
    assert [record["status"] for record in records] == ["recorded", "recorded"]


def test_script_prints_a_json_array() -> None:
    """在项目根跑脚本：退出码 0，stdout 是 2 条 JSON。"""
    result = subprocess.run(
        [sys.executable, "tools/refund_demo.py"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 2
    assert payload[0]["idempotency_key"] == "demo-1"
