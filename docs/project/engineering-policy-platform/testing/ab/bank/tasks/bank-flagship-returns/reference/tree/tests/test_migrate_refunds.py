"""migrate_refunds 的用例：无损、原子与失败关闭。"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.migrate_refunds import main  # noqa: E402

LEGACY = PROJECT_ROOT / "data" / "refunds-legacy.jsonl"


def _scratch(name: str) -> Path:
    """一个干净的临时目录（不依赖 pytest 的 tmp_path）。"""
    path = Path(tempfile.gettempdir()) / "demo-shop-tests" / name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path


def test_migrates_three_records() -> None:
    """按 refund_id 升序写出 3 条 v2 记录。"""
    out = _scratch("migrate-records") / "v2.jsonl"
    assert main(["--in", str(LEGACY), "--out", str(out)]) == 0
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [row["refund_id"] for row in rows] == [1, 2, 3]
    assert [row["status"] for row in rows] == ["migrated", "migrated", "migrated"]
    assert [row["fee_cents"] for row in rows] == [0, 0, 0]
    assert rows[0]["amount_cents"] == 1000
    assert rows[0]["reason"] == "damaged"


def test_output_is_stable_and_lf_only() -> None:
    """文件是 LF、末尾一个换行、键有序、两次运行逐字节相同。"""
    directory = _scratch("migrate-stable")
    first = directory / "first.jsonl"
    second = directory / "second.jsonl"
    assert main(["--in", str(LEGACY), "--out", str(first)]) == 0
    assert main(["--in", str(LEGACY), "--out", str(second)]) == 0
    raw = first.read_bytes()
    assert raw == second.read_bytes()
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\n\n")
    for line in raw.decode("utf-8").splitlines():
        payload = json.loads(line)
        assert list(payload) == sorted(payload)


def test_bad_input_returns_one_and_keeps_the_output() -> None:
    """坏输入返回 1，且不替换已有输出文件。"""
    directory = _scratch("migrate-bad")
    source = directory / "legacy.jsonl"
    source.write_text('{"id": 1, "order": 1, "cents": -1, "why": "x"}\n', encoding="utf-8")
    out = directory / "v2.jsonl"
    out.write_bytes(b"SENTINEL\n")
    assert main(["--in", str(source), "--out", str(out)]) == 1
    assert out.read_bytes() == b"SENTINEL\n"
