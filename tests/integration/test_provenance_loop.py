"""台阶 0 的闭环读数：R-e 的五个场景（方案 §5.2 R-e、§4 台阶 0）。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import REPO_ROOT

pytestmark = pytest.mark.integration


def test_provenance_loop_reads_r_e(tmp_root: Path) -> None:
    out = tmp_root / "provenance-loop.json"

    completed = subprocess.run(
        [sys.executable, "tools/provenance_loop.py", "--out", str(out)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    scenarios = {item["id"]: item for item in report["scenarios"]}

    assert report["result"] == "pass"
    assert scenarios["pass-sealed-check"]["observed_state"] == "pass"
    assert scenarios["pass-sealed-check"]["observed_exit"] == 0

    # R-e 的另一半：对不上就是 external_write + 退出码 3，而不是 pass。
    assert scenarios["external-write"]["observed_state"] == "external_write"
    assert scenarios["external-write"]["observed_exit"] == 3
    assert scenarios["external-write"]["differences"]["modified"] == ["declared/a.txt"]

    # 证明不了（声明命中不到 / 声明是空壳）一律不给 pass，且空壳声明没有判据级封条。
    assert scenarios["unprovable-decl"]["observed_state"] == "unprovable"
    assert scenarios["unprovable-decl"]["observed_exit"] == 3
    assert scenarios["no-declaration"]["observed_state"] == "unprovable"
    assert scenarios["no-declaration"]["digest_absent"] is True

    # 仪器自证：把比对换成恒 pass 的替身，同一个场景就不再报红。
    assert scenarios["self-check-comparator"]["comparator_state"] == "external_write"
    assert scenarios["self-check-comparator"]["stub_state"] == "pass"
