"""台阶 3c：义务账门禁的读数与退出码（L5 试用期：warn + 非零退出，不阻断）。

门禁的价值全在"它会不会红"：一条永远绿的读数等于没有读数（AGENTS 第 45 条）。
因此这里逐条驱动**会命中**的形态（未结义务 / 声称 0 却没有真实运行 / 账本读不懂），
再给一条**不该命中**的形态（义务已由真实运行解除）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

from policy.obligations import record_pending, record_test_run

pytestmark = pytest.mark.integration

GATE = REPO_ROOT / "tools" / "obligations_gate.py"


def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_gate(*args: str):
    return subprocess.run(
        [sys.executable, str(GATE), *args],
        cwd=REPO_ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def open_ledger(path: Path) -> Path:
    record_pending(
        path,
        rule_id="TESTING-002",
        rule_version=1,
        target="src/shop/order_service.py",
        missing_target="shop.order_service:cancel_order",
        test_module="tests/test_order_service.py",
        checker="failing_tests",
        missing_targets=("shop.order_service:cancel_order",),
        at="2026-09-29T00:00:00Z",
    )
    return path


def test_an_open_obligation_is_a_hit_with_a_nonzero_exit(tmp_root: Path) -> None:
    ledger = open_ledger(tmp_root / "open.jsonl")

    completed = run_gate("--ledger", str(ledger), "--json")

    assert completed.returncode == 1, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["mode"] == "warn"
    assert payload["hits"] == 1
    assert payload["exit_code"] == 1
    [report] = payload["ledgers"]
    assert report["obligations_open"] == 1
    assert report["claim_supported"] is False
    assert report["hit"] is True
    # 读数必须说得出"属于哪棵树"（L5）；读不到也得写 unprovable，不许少算。
    assert report["tree_digest"].startswith(("sha256:", "unprovable:"))
    assert payload["tree_digest"] == report["tree_digest"]


def test_a_ledger_with_no_real_run_cannot_claim_zero(tmp_root: Path) -> None:
    """空账本 = 0 条义务，但**没有依据**（没有一次真实 pytest 运行）→ 同样算命中。"""

    completed = run_gate("--ledger", str(tmp_root / "absent.jsonl"))

    assert completed.returncode == 1, completed.stderr
    assert "没有依据" in completed.stdout
    assert "HITS: 1 / 1" in completed.stdout


def test_a_real_run_clears_the_hit(tmp_root: Path) -> None:
    """正对照：义务被一次真实运行解除之后，门禁必须**变绿**（否则它永远是红的，等于没读数）。"""

    ledger = open_ledger(tmp_root / "closed.jsonl")
    record_test_run(
        ledger,
        target="src/shop/order_service.py",
        selected_tests=("tests/test_order_service.py",),
        python_tests_executed=True,
        source="test",
        at="2026-09-29T01:00:00Z",
    )

    completed = run_gate("--ledger", str(ledger), "--json")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["hits"] == 0
    [report] = payload["ledgers"]
    assert report["obligations_open"] == 0
    assert report["obligations_closed"] == 1
    assert report["claim_supported"] is True
    assert report["last_real_test_run"]["at"] == "2026-09-29T01:00:00Z"


def test_an_unreadable_ledger_is_a_usage_error(tmp_root: Path) -> None:
    """协议不认识的账本一律不读（退出码 2）—— 不许把它当成"没有义务"。"""

    ledger = tmp_root / "broken.jsonl"
    ledger.write_text(json.dumps({"kind": "pending", "schema_version": "9.9"}) + chr(10), encoding="utf-8")

    completed = run_gate("--ledger", str(ledger))

    assert completed.returncode == 2
    assert "读不懂" in completed.stderr


def test_two_instances_are_reported_side_by_side(tmp_root: Path) -> None:
    """L5 要求"读数同时给仓库内与 .tmp 实例"：多条 --ledger 各给一行，命中数分开数。"""

    repo_side = open_ledger(tmp_root / "repo.jsonl")
    tmp_side = tmp_root / "tmp-instance.jsonl"
    record_test_run(
        tmp_side,
        target="src/shop/order_service.py",
        selected_tests=("tests/test_order_service.py",),
        python_tests_executed=True,
        source="test",
        at="2026-09-29T02:00:00Z",
    )

    completed = run_gate("--ledger", str(repo_side), "--ledger", str(tmp_side), "--json")

    assert completed.returncode == 1, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ledger_count"] == 2
    assert payload["hits"] == 1
    assert [item["hit"] for item in payload["ledgers"]] == [True, False]
