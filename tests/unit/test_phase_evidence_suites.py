"""阶段验收证据的测试结果来源：复用 junit 报告，还是真跑一遍。

为什么值得单独测：门禁里的 pytest 步骤与证据步骤跑的是**同一批测试**，而证据步骤过去会把
四个套件再跑一遍（全量门禁里约 5 分钟）——只为数用例数。改成“引用 pytest 刚写出的 junit
报告”之后，判据必须仍然完整：报告缺套件、有归属不出去的用例、读不出、或者早于最新源码改动，
都要退回真跑一遍，绝不允许拿半份报告拼出一个“通过”。这里全部用合成 XML 钉住，不跑真测试。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tools import phase_evidence as pe

COMBINED = """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests">
<testsuite name="pytest" tests="5" failures="1" errors="0" skipped="1">
<testcase classname="tests.unit.test_a" file="tests/unit/test_a.py" name="t1"/>
<testcase classname="tests.unit.test_a" file="tests/unit/test_a.py" name="t2">
<skipped message="本机不允许创建符号链接"/></testcase>
<testcase classname="tests.contract.test_b" file="tests/contract/test_b.py" name="t3"/>
<testcase classname="tests.integration.test_c"
          file="tests/integration/test_c.py" name="t4"/>
<testcase classname="tests.security.test_d" file="tests/security/test_d.py" name="t5">
<failure message="boom">trace</failure></testcase>
</testsuite></testsuites>"""


def _report(tmp_root: Path, text: str = COMBINED, name: str = "tests-all-report.xml") -> Path:
    path = tmp_root / name
    path.write_text(text, encoding="utf-8")
    return path


def _stub_run_suite(ran: list[str]):
    """替身：记录被真跑的套件名，返回一份最小结果（用来证明“退回了真跑”）。"""

    def run(name: str) -> dict:
        ran.append(name)
        return {"cases": 1, "failures": 0}

    return run


def test_report_paths_takes_explicit_files_only(tmp_root: Path) -> None:
    first = _report(tmp_root, COMBINED, "a.xml")
    second = _report(tmp_root, COMBINED, "b.xml")

    assert pe.report_paths([str(first)]) == [first]
    assert pe.report_paths([str(first), str(second)]) == [first, second]
    assert pe.report_paths([str(tmp_root)]) == []  # 目录不是报告：不猜、不展开
    assert pe.report_paths([str(tmp_root / 'missing.xml')]) == []
    assert pe.report_paths(None) == []


def test_combined_report_is_split_back_into_the_four_suites(tmp_root: Path) -> None:
    suites = pe.suites_from_reports([_report(tmp_root)])

    assert sorted(suites) == sorted(pe.SUITES)
    assert suites["tests/unit"]["cases"] == 2
    assert suites["tests/unit"]["skipped"] == 1
    assert suites["tests/unit"]["failures"] == 0
    assert suites["tests/unit"]["result"] == "pass"
    assert suites["tests/security"]["failures"] == 1
    assert suites["tests/security"]["result"] == "fail"
    # 有失败就是 1：报告的结论与“真跑一遍”的退出码同义
    assert suites["tests/security"]["exit_code"] == 1
    assert suites["tests/integration"]["source"] == "junit-report"
    assert sum(int(item["cases"]) for item in suites.values()) == 5


def test_case_outside_the_four_suites_is_refused(tmp_root: Path) -> None:
    """归属不出去的用例：不猜它属于哪一套，整份报告作废（"缺套件"那条由下一条用例覆盖）。"""

    text = COMBINED.replace("tests/integration/test_c.py", "tests/something/test_c.py")

    with pytest.raises(pe.SuiteReportError, match="不属于"):
        pe.suites_from_reports([_report(tmp_root, text)])


def test_report_without_cases_of_a_suite_is_refused(tmp_root: Path) -> None:
    text = COMBINED.replace('file="tests/security/test_d.py"', 'file="tests/unit/test_d.py"')

    with pytest.raises(pe.SuiteReportError, match="没有这些套件"):
        pe.suites_from_reports([_report(tmp_root, text)])


def test_unreadable_report_is_refused(tmp_root: Path) -> None:
    broken = _report(tmp_root, "<testsuites>", "broken.xml")

    with pytest.raises(pe.SuiteReportError, match="读不出"):
        pe.suites_from_reports([broken])


def test_stale_report_falls_back_to_running_the_suites(tmp_root, monkeypatch) -> None:
    report = _report(tmp_root)
    ran: list[str] = []
    future = (time.time() + 3600, "src/policy/engine.py")
    monkeypatch.setattr(pe, "newest_test_input", lambda: future)
    monkeypatch.setattr(pe, "run_suite", _stub_run_suite(ran))

    suites, source, reports = pe.resolve_suites([str(report)])

    assert source == "pytest"  # 陈旧 -> 真跑，绝不引用
    assert ran == list(pe.SUITES)
    assert reports == []
    assert pe.stale_reason([report]) is not None


def test_fresh_report_is_reused_without_running_anything(tmp_root, monkeypatch) -> None:
    report = _report(tmp_root)
    monkeypatch.setattr(pe, "newest_test_input", lambda: (0.0, "src/policy/engine.py"))

    def explode(name: str) -> dict:  # pragma: no cover - 走到这里就是复用逻辑失效
        raise AssertionError("新鲜报告不该再跑测试：%s" % name)

    monkeypatch.setattr(pe, "run_suite", explode)

    suites, source, reports = pe.resolve_suites([str(report)])

    assert source == "junit-report"
    assert reports == [report.resolve().relative_to(pe.REPO_ROOT).as_posix()]
    assert suites["tests/unit"]["cases"] == 2
    assert pe.stale_reason([report]) is None


def test_no_reports_means_run_the_suites(tmp_root, monkeypatch) -> None:
    ran: list[str] = []
    monkeypatch.setattr(pe, "run_suite", _stub_run_suite(ran))

    _suites, source, reports = pe.resolve_suites([str(tmp_root / "missing.xml")])

    assert source == "pytest"
    assert ran == list(pe.SUITES)
    assert reports == []
