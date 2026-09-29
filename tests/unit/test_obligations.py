"""台阶 3c：义务账的代数（记账 / 折叠 / 解除 / 读数）与它的三条口径。

临时目录用仓库自己的 `tmp_root` fixture（不是 pytest 的 `tmp_path`）：受限沙箱里
`tmp_path` 会退化成 PermissionError，让用例红在与被测行为无关的地方（tests/conftest.py 的说明）。

这里钉的是**数据层**的行为：键是什么、什么时候解除、读不出来的账本怎么办。真流水线那一侧
（"义务会不会在正确的时刻解除"）在 tests/integration/test_obligations_round.py 里。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from policy.obligations import (
    KIND_PENDING,
    KIND_TEST_RUN,
    LEDGER_SCHEMA_VERSION,
    OBLIGATIONS_KEYS,
    ObligationsError,
    book_pending_findings,
    describe,
    load,
    real_pytest_run,
    record_pending,
    record_test_run,
    summarize,
)


def pending(path: Path, *, rule: str = "TESTING-002", target: str = "src/shop/order_service.py",
            missing: str = "shop.order_service:cancel_order",
            module: str = "tests/test_order_service.py", at: str = "2026-09-29T00:00:00Z") -> None:
    record_pending(
        path,
        rule_id=rule,
        rule_version=1,
        target=target,
        missing_target=missing,
        test_module=module,
        checker="failing_tests",
        missing_targets=(missing,),
        at=at,
    )


def real_run(path: Path, *, target: str = "src/shop/order_service.py",
             selected=("tests/test_order_service.py",), at: str = "2026-09-29T01:00:00Z") -> None:
    record_test_run(
        path,
        target=target,
        selected_tests=selected,
        python_tests_executed=True,
        source="test",
        at=at,
    )


# --------------------------------------------------------------------------- 记账 / 折叠


def test_the_key_is_rule_target_missing_target_and_carries_no_session(tmp_root: Path) -> None:
    """键 = `(rule_id, target, missing_target)`，**不含 session_id**（方案 §3.3）。

    带上会话标识，新会话就会把义务清零 —— 那正是评审 §2.1 否掉的旧设计。
    """

    ledger = tmp_root / "o.jsonl"
    pending(ledger)
    record = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])

    assert set(record) == set(OBLIGATIONS_KEYS[KIND_PENDING])
    assert "session" not in json.dumps(record)

    state = load(ledger)
    [item] = state.open
    assert item.key.rule_id == "TESTING-002"
    assert item.key.target == "src/shop/order_service.py"
    assert item.key.missing_target == "shop.order_service:cancel_order"
    assert item.count == 1


def test_the_same_key_counts_up_and_keeps_its_age(tmp_root: Path) -> None:
    """同一把键再记一次 = 计数 +1、年龄不被重置（"这个目标多久没人覆盖"要读得出来）。"""

    ledger = tmp_root / "o.jsonl"
    pending(ledger, at="2026-09-29T00:00:00Z")
    pending(ledger, at="2026-09-29T03:00:00Z")

    [item] = load(ledger).open
    assert item.count == 2
    assert item.first_seen == "2026-09-29T00:00:00Z"
    assert item.last_seen == "2026-09-29T03:00:00Z"


def test_a_different_missing_target_is_a_different_obligation(tmp_root: Path) -> None:
    """缺失目标不同的两条义务不许被合并成一条 —— 它们要等的东西不一样。"""

    ledger = tmp_root / "o.jsonl"
    pending(ledger, missing="shop.order_service:cancel_order")
    pending(ledger, missing="shop.order_service:refund")

    assert len(load(ledger).open) == 2


# --------------------------------------------------------------------------- 解除


def test_only_a_real_run_discharges_and_only_by_target_or_selected_test(tmp_root: Path) -> None:
    """解除的两条结构化通道：**同 target**，或**那次跑不起来的测试模块这次被选中**。

    只按 target 匹配是不够的：Q7 的真实次序是「先写测试（target = 测试文件）→ 再写实现
    （target = 实现文件）」，跨 target 的那一步只有靠"覆盖它的测试这次真的跑了"才解除。
    """

    by_target = tmp_root / "by-target.jsonl"
    pending(by_target)
    real_run(by_target, target="src/shop/order_service.py", selected=("tests/other.py",))
    assert load(by_target).open == ()

    by_test_module = tmp_root / "by-module.jsonl"
    pending(by_test_module)
    real_run(by_test_module, target="src/shop/other.py", selected=("tests/test_order_service.py",))
    assert load(by_test_module).open == ()

    unrelated = tmp_root / "unrelated.jsonl"
    pending(unrelated)
    real_run(unrelated, target="src/shop/other.py", selected=("tests/other.py",))
    [still_open] = load(unrelated).open
    assert still_open.key.missing_target == "shop.order_service:cancel_order"


def test_a_run_without_execution_does_not_discharge(tmp_root: Path) -> None:
    """`python_tests_executed=false`（零收集 / 没选中 / 待实现）不解除，只留读数。"""

    ledger = tmp_root / "o.jsonl"
    pending(ledger)
    record_test_run(
        ledger,
        target="src/shop/order_service.py",
        selected_tests=("tests/test_order_service.py",),
        python_tests_executed=False,
        source="test",
        at="2026-09-29T01:00:00Z",
    )

    state = load(ledger)
    assert len(state.open) == 1
    assert state.last_real_test_run is None


def test_real_pytest_run_needs_all_three_structural_facts() -> None:
    """三条结构化事实缺一不可（不解析 reasons 文本，AGENTS 第 49 条同一纪律）。"""

    assert real_pytest_run(
        pytest_status="ok", served_checkers=["failing_tests"], selected_tests=["tests/t.py"]
    )
    assert real_pytest_run(
        pytest_status="findings", served_checkers=["failing_tests"], selected_tests=["tests/t.py"]
    )
    # 状态是 pending_implementation / crashed：不算跑成
    assert not real_pytest_run(
        pytest_status="pending_implementation",
        served_checkers=["missing_tests"],
        selected_tests=["tests/t.py"],
    )
    # 退出码 5（选中了、一个都没收集到）：failing_tests 不进 served
    assert not real_pytest_run(
        pytest_status="ok", served_checkers=["missing_tests"], selected_tests=["tests/t.py"]
    )
    # 没有选中任何测试：没有执行证据
    assert not real_pytest_run(
        pytest_status="ok", served_checkers=["failing_tests"], selected_tests=[]
    )


def test_the_two_status_names_match_the_validator_enum() -> None:
    """`PYTEST_EXECUTED_STATUSES` 与验证器层的取值不许漂移（两份声明一份事实）。"""

    from policy.evidence import ValidatorStatus

    from policy.obligations import PYTEST_EXECUTED_STATUSES

    assert {status.value for status in ValidatorStatus} >= set(PYTEST_EXECUTED_STATUSES)


# --------------------------------------------------------------------------- 读数


def test_an_empty_ledger_cannot_claim_zero(tmp_root: Path) -> None:
    """`obligations_open == 0` 但没有一次真实运行 = **没有依据**，不许被读成干净。"""

    ledger = tmp_root / "o.jsonl"
    summary = summarize(ledger)
    assert summary["obligations_open"] == 0
    assert summary["claim_supported"] is False
    assert "没有依据" in summary["note"]
    assert "没有依据" in describe(summary)

    pending(ledger)
    assert summarize(ledger)["claim_supported"] is False
    assert "1 条未结义务" in describe(summarize(ledger))

    real_run(ledger)
    closed = summarize(ledger)
    assert closed["obligations_open"] == 0
    assert closed["obligations_closed"] == 1
    assert closed["claim_supported"] is True
    assert closed["last_real_test_run"]["at"] == "2026-09-29T01:00:00Z"


def test_summary_reports_integers_only_and_names_no_ratio(tmp_root: Path) -> None:
    """方案 §3.5：只报整数，禁比例 —— 摘要里不许出现 ratio / percent / coverage 这类键。"""

    ledger = tmp_root / "o.jsonl"
    pending(ledger)
    summary = summarize(ledger)

    assert all(
        isinstance(value, int)
        for key, value in summary.items()
        if key in {"records", "pending_records", "test_run_records", "obligations_open", "obligations_closed"}
    )
    assert not [key for key in summary if any(word in key for word in ("ratio", "percent", "coverage"))]


# --------------------------------------------------------------------------- 失败关闭


def test_a_ledger_with_an_unknown_version_is_refused(tmp_root: Path) -> None:
    ledger = tmp_root / "o.jsonl"
    ledger.write_text(
        json.dumps({"kind": KIND_PENDING, "schema_version": "9.9"}) + chr(10), encoding="utf-8"
    )
    with pytest.raises(ObligationsError) as error:
        load(ledger)
    assert "schema_version" in str(error.value)


def test_an_unknown_key_set_is_refused(tmp_root: Path) -> None:
    """键集合是协议：多一个键就是另一种载荷，必须报错而不是当没看见（AGENTS 第 55 条）。"""

    ledger = tmp_root / "o.jsonl"
    record = {
        "kind": KIND_TEST_RUN,
        "schema_version": LEDGER_SCHEMA_VERSION,
        "at": "2026-09-29T00:00:00Z",
        "target": "src/shop/order_service.py",
        "selected_tests": [],
        "python_tests_executed": False,
        "source": "test",
        "extra": 1,
    }
    ledger.write_text(json.dumps(record) + chr(10), encoding="utf-8")
    with pytest.raises(ObligationsError) as error:
        load(ledger)
    assert "键集合" in str(error.value)


def test_appending_to_a_broken_ledger_is_refused(tmp_root: Path) -> None:
    """坏账本上不许续写：那会把"读不懂"变成"越写越读不懂"。"""

    ledger = tmp_root / "o.jsonl"
    ledger.write_text("not json" + chr(10), encoding="utf-8")
    with pytest.raises(ObligationsError):
        pending(ledger)


def test_a_missing_file_is_an_empty_ledger_not_an_error(tmp_root: Path) -> None:
    """文件不存在 = 空账本（还没记过），不是错误；但它的 0 **不可声称**（见上）。"""

    state = load(tmp_root / "absent.jsonl")
    assert state.records == 0 and state.open == ()


# --------------------------------------------------------------------------- 从判定记账


def test_book_pending_findings_expands_every_missing_target(tmp_root: Path) -> None:
    """一条 finding + 验证器侧的快照 → 每个缺失目标各记一条（键说的是单个 missing_target）。"""

    from policy.models import Evidence, Severity, Violation

    finding = Violation(
        rule_id="TESTING-002",
        rule_version=1,
        severity=Severity.WARNING,
        message="待实现",
        evidence=Evidence(
            kind="failing_tests",
            subject="tests/test_order_service.py",
            value="shop.order_service:cancel_order",
        ),
    )
    ledger = tmp_root / "o.jsonl"
    written = book_pending_findings(
        ledger,
        findings=(finding,),
        target="src/shop/order_service.py",
        pending_snapshot=(
            {
                "test_modules": ["tests/test_order_service.py"],
                "missing_targets": ["shop.order_service:cancel_order", "shop.order_service:refund"],
            },
        ),
        at="2026-09-29T00:00:00Z",
    )

    assert written == 2
    missing = sorted(item.key.missing_target for item in load(ledger).open)
    assert missing == ["shop.order_service:cancel_order", "shop.order_service:refund"]
    # 快照是完整的（两条都带两个目标），不是只留第一条。
    assert all(len(item.missing_targets) == 2 for item in load(ledger).open)
