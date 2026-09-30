"""台阶 3c：义务账门禁的读数与退出码（L5 试用期：warn + 非零退出，不阻断）。

门禁的价值全在"它会不会红"：一条永远绿的读数等于没有读数（AGENTS 第 45 条）。
因此这里逐条驱动**会命中**的形态（未结义务 / 账本存在却没有真实运行 / 账本读不懂 /
账本根本不存在但位置给错了），再给两条**不该命中**的形态（义务已由真实运行解除；
账本不存在 = 不适用）。

**"账本不存在"与"账本存在但空"必须分开**（2026-09-30 小修）：前者是**没有账本可读** →
不适用、不算命中；后者是**没有依据** → 仍然按命中处理（AGENTS 第 56 条）。
`test_a_ledger_with_no_real_run_cannot_claim_zero` 曾经把这两种情形混在一起
（用例名说"空账本"，传的却是一个从来没被创建的路径），于是"什么都没读到"也能占住
升格判据里的"0 命中"名额。
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
    assert payload["report_schema_version"] == "1.2"
    assert payload["mode"] == "warn"
    assert payload["hits"] == 1
    assert payload["exit_code"] == 1
    assert payload["applicable_ledgers"] == 1
    assert payload["not_applicable_ledgers"] == 0
    [report] = payload["ledgers"]
    assert report["applicable"] is True
    assert report["obligations_open"] == 1
    assert report["claim_supported"] is False
    assert report["hit"] is True
    # 读数必须说得出"属于哪棵树"（L5）；读不到也得写 unprovable，不许少算。
    assert report["tree_digest"].startswith(("sha256:", "unprovable:"))
    assert payload["tree_digest"] == report["tree_digest"]


def test_a_missing_ledger_is_not_applicable_and_not_a_hit(tmp_root: Path) -> None:
    """账本文件**不存在** = 没有账本可读 → **不适用**：不算命中，也不许冒充"0 条义务"。"""

    completed = run_gate("--ledger", str(tmp_root / "never-written.jsonl"), "--json")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["hits"] == 0
    assert payload["exit_code"] == 0
    assert payload["ledger_count"] == 1
    assert payload["applicable_ledgers"] == 0
    assert payload["not_applicable_ledgers"] == 1
    [report] = payload["ledgers"]
    assert report["applicable"] is False
    assert report["hit"] is False
    # 不适用不是一个读数：没有账本就没有这些键（第 46/50 条，两个读法必须能分开）。
    assert "obligations_open" not in report
    assert "claim_supported" not in report
    assert "last_real_test_run" not in report
    assert "tree_digest" not in report
    assert "没有账本可读" in report["note"]


def test_a_missing_ledger_is_labelled_in_the_text_reading(tmp_root: Path) -> None:
    """文本读数也要报"不适用"：读的人不许把它读成"跑过了、0 命中"。"""

    completed = run_gate("--ledger", str(tmp_root / "never-written.jsonl"))

    assert completed.returncode == 0, completed.stderr
    assert "不适用" in completed.stdout
    assert "HITS: 0 / 1 个账本（0 命中）；不适用 1 个" in completed.stdout


def test_a_present_but_empty_ledger_still_cannot_claim_zero(tmp_root: Path) -> None:
    """账本**存在**（空文件）= 0 条义务，但**没有依据** → 仍然按命中处理（AGENTS 第 56 条）。"""

    ledger = tmp_root / "empty.jsonl"
    ledger.write_text("", encoding="utf-8")

    completed = run_gate("--ledger", str(ledger))

    assert completed.returncode == 1, completed.stdout + completed.stderr
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
    assert report["applicable"] is True
    assert report["obligations_open"] == 0
    assert report["obligations_closed"] == 1
    assert report["claim_supported"] is True
    assert report["last_real_test_run"]["at"] == "2026-09-29T01:00:00Z"


def test_an_unreadable_ledger_is_a_usage_error(tmp_root: Path) -> None:
    """协议不认识的账本一律不读（退出码 2）—— 不许把它当成"没有义务"。"""

    ledger = tmp_root / "broken.jsonl"
    record = {"kind": "pending", "schema_version": "9.9"}
    ledger.write_text(json.dumps(record) + chr(10), encoding="utf-8")

    completed = run_gate("--ledger", str(ledger))

    assert completed.returncode == 2
    assert "读不懂" in completed.stderr


def test_a_ledger_path_that_is_a_directory_is_a_usage_error(tmp_root: Path) -> None:
    """路径存在但不是文件：这是用法错误（2），不许被读成"不适用"而滑过去。"""

    completed = run_gate("--ledger", str(tmp_root))

    assert completed.returncode == 2
    assert "不是一个文件" in completed.stderr


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
    assert payload["applicable_ledgers"] == 2
    assert payload["hits"] == 1
    assert [item["hit"] for item in payload["ledgers"]] == [True, False]


def test_a_not_applicable_ledger_does_not_hide_another_ledgers_hit(tmp_root: Path) -> None:
    """不适用与命中各数各的：一条不适用 + 一条有未结义务 → 命中 1，退出码仍然是 1。"""

    ledger = open_ledger(tmp_root / "open.jsonl")

    completed = run_gate(
        "--ledger", str(tmp_root / "never-written.jsonl"), "--ledger", str(ledger), "--json"
    )

    assert completed.returncode == 1, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ledger_count"] == 2
    assert payload["applicable_ledgers"] == 1
    assert payload["not_applicable_ledgers"] == 1
    assert payload["hits"] == 1
    assert [item["applicable"] for item in payload["ledgers"]] == [False, True]


def test_the_payload_says_which_tree_and_which_ledger_it_read(tmp_root: Path) -> None:
    """台阶 4：读数必须说得出"属于哪棵树、读的是哪个账本"（21 号 §2.3 第 a 行）。

    它只是旁注：hits / applicable / exit_code 一个都不由它决定——升格判据要读的
    "这次算不算一次真实读数"靠它说清归属（第 56 条）。
    """

    ledger = open_ledger(tmp_root / "open.jsonl")

    completed = run_gate("--ledger", str(ledger), "--json")

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    context = payload["reading_context"]
    assert context["source"] == "gate"
    assert context["tree"]["status"] == "available"
    assert context["tree"]["scope"] == "workspace"
    assert context["tree"]["digest"] == payload["tree_digest"], "与报告里的树摘要同一个值，不另算一遍"
    assert len(context["tree"]["revision"]) == 40
    assert context["host"]["sandbox"] == "unknown", "不探测沙箱：探测要有副作用，取不到事实就写 unknown"
    declaration = context["declarations"]["obligations_ledger"]
    assert declaration["status"] == "available"
    assert declaration["path"].endswith("open.jsonl")
    assert not Path(declaration["path"]).is_absolute(), "读数里不放绝对路径"
    assert declaration["digest"].startswith("sha256:")


def test_a_missing_ledger_is_not_applicable_inside_the_reading_context(tmp_root: Path) -> None:
    """账本不存在 = **不适用**（与报告里 applicable=false 同一口径），不是"读不到"。"""

    completed = run_gate("--ledger", str(tmp_root / "never-written.jsonl"), "--json")

    payload = json.loads(completed.stdout)
    assert payload["hits"] == 0 and payload["exit_code"] == 0
    assert payload["reading_context"]["declarations"]["obligations_ledger"] == {
        "status": "not_applicable"
    }


def test_two_ledgers_are_both_named_in_the_reading_context(tmp_root: Path) -> None:
    first = open_ledger(tmp_root / "repo.jsonl")
    second = tmp_root / "tmp-instance.jsonl"
    record_test_run(
        second,
        target="src/shop/order_service.py",
        selected_tests=("tests/test_order_service.py",),
        python_tests_executed=True,
        source="test",
        at="2026-09-29T02:00:00Z",
    )

    completed = run_gate("--ledger", str(first), "--ledger", str(second), "--json")

    payload = json.loads(completed.stdout)
    declarations = payload["reading_context"]["declarations"]
    assert sorted(declarations) == ["obligations_ledger", "obligations_ledger_2"], (
        "两个账本各自留一块：读的人要知道这份读数读的是哪几份输入"
    )
    assert all(item["status"] == "available" for item in declarations.values())
