"""tools/migrate_ledger.py 的 CLI 用例：成功 / 坏输入 / 幂等。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.migrate_ledger import main  # noqa: E402

LEDGER = ROOT / "data" / "ledger-v1.jsonl"


def test_main_migrates_the_ledger(tmp_path: Path, capsys) -> None:
    """成功时 exit 0、stdout 恰一行 MIGRATED 4、产物 4 行。"""
    target = tmp_path / "ledger-v2.jsonl"
    assert main(["--in", str(LEDGER), "--out", str(target)]) == 0
    assert capsys.readouterr().out == "MIGRATED 4\n"
    assert len(target.read_text(encoding="utf-8").splitlines()) == 4


def test_main_rejects_a_bad_row_and_keeps_the_target(tmp_path: Path, capsys) -> None:
    """坏输入 exit 1、stderr 一行 MIGRATE FAILED:、目标哨兵字节不变。"""
    bad = tmp_path / "bad.jsonl"
    bad.write_text("[1, 2]\n", encoding="utf-8")
    target = tmp_path / "out.jsonl"
    target.write_bytes(b"SENTINEL\n")
    assert main(["--in", str(bad), "--out", str(target)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("MIGRATE FAILED:")
    assert target.read_bytes() == b"SENTINEL\n"


def test_main_is_idempotent(tmp_path: Path, capsys) -> None:
    """同一输入跑两次，两个产物逐字节相同。"""
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    assert main(["--in", str(LEDGER), "--out", str(first)]) == 0
    assert main(["--in", str(LEDGER), "--out", str(second)]) == 0
    capsys.readouterr()
    assert first.read_bytes() == second.read_bytes()


def test_main_usage_error_exits_two() -> None:
    """缺 --out 是用法错误：argparse 退出 2，不进入迁移流程。"""
    with pytest.raises(SystemExit) as info:
        main(["--in", str(LEDGER)])
    assert info.value.code == 2
