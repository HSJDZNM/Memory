"""tools/verify_ledger.py 的 CLI 用例：合法产物 / 篡改行。"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.migrate_ledger import main as migrate  # noqa: E402
from tools.verify_ledger import main as verify  # noqa: E402

LEDGER = ROOT / "data" / "ledger-v1.jsonl"


def test_verify_accepts_the_product(tmp_path: Path, capsys) -> None:
    """合法产物 exit 0、stdout 恰一行 VERIFIED 4，且校验不改文件。"""
    target = tmp_path / "ledger-v2.jsonl"
    assert migrate(["--in", str(LEDGER), "--out", str(target)]) == 0
    capsys.readouterr()
    assert verify(["--path", str(target)]) == 0
    assert capsys.readouterr().out == "VERIFIED 4\n"
    before = target.read_bytes()
    assert verify(["--path", str(target)]) == 0
    assert target.read_bytes() == before


def test_verify_rejects_a_missing_key(tmp_path: Path, capsys) -> None:
    """缺一个键必须 exit 1 且 stderr 一行 VERIFY FAILED:。"""
    target = tmp_path / "ledger-v2.jsonl"
    assert migrate(["--in", str(LEDGER), "--out", str(target)]) == 0
    capsys.readouterr()
    lines = target.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    del record["reason"]
    lines[0] = json.dumps(record, ensure_ascii=False)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert verify(["--path", str(target)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("VERIFY FAILED:")


def test_verify_rejects_records_out_of_order(tmp_path: Path, capsys) -> None:
    """记录不按 entry_id 升序必须 exit 1。"""
    target = tmp_path / "ledger-v2.jsonl"
    assert migrate(["--in", str(LEDGER), "--out", str(target)]) == 0
    lines = target.read_text(encoding="utf-8").splitlines()
    lines[0], lines[1] = lines[1], lines[0]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert verify(["--path", str(target)]) == 1
    assert capsys.readouterr().err.startswith("VERIFY FAILED:")
