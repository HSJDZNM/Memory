"""本机门禁「只报告」步骤的回归（L5 试用期口径：只读数、不判罚）。

为什么单独一个文件：这一族行为（非零退出不进 failures、读不出命中数也照实说、
--list 里豁免不许隐形）是"本轮不新增阻断步骤"这条裁定的可执行形态；
它与 tests/unit/test_ci_local.py 里的锁 / 解释器回归是两件事，混在一起会让两边都难读。
"""

from __future__ import annotations

import datetime as _datetime
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_ci_local():
    """按文件路径加载 ci_local（与 test_ci_local.py 同一套配方）。

    刻意不用 @dataclass 写 ReportOnlyStep：装饰期要求模块已登记进 sys.modules，
    而这种加载方式不登记它——实测会直接报 AttributeError。用 NamedTuple 就不受这条约束。
    """

    spec = importlib.util.spec_from_file_location(
        "ci_local_report_only_under_test",
        REPO_ROOT / "tools" / "ci_local.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepare(ci_local, monkeypatch, tmp_root):
    monkeypatch.setattr(ci_local, "ROOT", tmp_root)
    monkeypatch.setattr(
        ci_local,
        "_steps",
        lambda: [("Module import probe", '.venv/bin/python -c "print(1)"')],
    )
    monkeypatch.setattr(ci_local, "_selected_names", lambda full: [])
    monkeypatch.setattr(ci_local, "_changed_paths", lambda: [])
    monkeypatch.setattr(ci_local, "unregistered_steps", lambda: [])


def _probe(ci_local, body):
    return ci_local.ReportOnlyStep(
        name="Probe report only",
        args=("-c", body),
        reason="回归用例：只报告步骤的读数与退出码",
        expires_at="2026-10-31",
        adopted="2026-09-30",
        reads="HITS: 行",
    )


def test_report_only_step_reads_hits_without_failing_the_gate(monkeypatch, capsys, tmp_root):
    """非零退出只打印命中数：门禁仍然退出 0（几行读数不许拦住推送）。"""

    ci_local = _load_ci_local()
    _prepare(ci_local, monkeypatch, tmp_root)
    monkeypatch.setattr(
        ci_local,
        "REPORT_ONLY_STEPS",
        (_probe(ci_local, "import sys; print('HITS: 3 / 1 个账本（有命中）'); sys.exit(1)"),),
    )

    assert ci_local.main(["--full", "--python", sys.executable]) == 0
    out = capsys.readouterr().out
    assert "REPORT-ONLY" in out
    assert "HITS: 3 / 1" in out
    assert "不计入门禁失败" in out


def test_report_only_step_prefers_structured_hits(monkeypatch, capsys, tmp_root):
    """给了 --json 就走结构化字段（不解析文本），读数里带账本数。"""

    ci_local = _load_ci_local()
    _prepare(ci_local, monkeypatch, tmp_root)
    probe = _probe(
        ci_local,
        "import json; print(json.dumps({'hits': 2, 'ledger_count': 3})); raise SystemExit(1)",
    )
    monkeypatch.setattr(
        ci_local,
        "REPORT_ONLY_STEPS",
        (probe._replace(args=(*probe.args, "--json")),),
    )

    assert ci_local.main(["--full", "--python", sys.executable]) == 0
    assert "hits=2 / 3 个账本" in capsys.readouterr().out


def test_report_only_step_that_cannot_be_read_says_so(monkeypatch, capsys, tmp_root):
    """读不出命中数时照实说，且仍然不阻断（不把"读不到"变成门禁结论）。"""

    ci_local = _load_ci_local()
    _prepare(ci_local, monkeypatch, tmp_root)
    monkeypatch.setattr(
        ci_local,
        "REPORT_ONLY_STEPS",
        (_probe(ci_local, "import sys; print('nothing useful'); sys.exit(7)"),),
    )

    assert ci_local.main(["--full", "--python", sys.executable]) == 0
    out = capsys.readouterr().out
    assert "退出码 7" in out
    assert "读不出命中数" in out


def test_report_only_steps_are_listed_with_their_expiry(monkeypatch, capsys, tmp_root):
    """--list 里必须看得到只报告步骤、豁免到期日与理由（豁免不许隐形）。"""

    ci_local = _load_ci_local()
    monkeypatch.setattr(ci_local, "ROOT", tmp_root)
    monkeypatch.setattr(ci_local, "_steps", lambda: [])
    monkeypatch.setattr(ci_local, "_selected_names", lambda full: [])
    monkeypatch.setattr(ci_local, "_changed_paths", lambda: [])
    monkeypatch.setattr(ci_local, "unregistered_steps", lambda: [])

    assert ci_local.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "本机只报告" in out
    for step in ci_local.REPORT_ONLY_STEPS:
        assert step.name in out
        assert step.expires_at in out


def test_every_report_only_exemption_carries_reason_and_expiry():
    """登记表本身就是数据契约：缺理由 / 缺到期日 / 日期不合法一律算缺陷。"""

    ci_local = _load_ci_local()
    assert ci_local.REPORT_ONLY_STEPS
    for step in ci_local.REPORT_ONLY_STEPS:
        assert step.name.strip()
        assert step.args and all(part.strip() for part in step.args)
        assert step.reason.strip(), step.name
        assert step.reads.strip(), step.name
        _datetime.date.fromisoformat(step.expires_at)
        _datetime.date.fromisoformat(step.adopted)


def test_hook_mode_stays_quiet_even_when_a_report_only_reading_is_red(monkeypatch, capsys, tmp_root):
    """钩子成功时保持安静：只报告步骤**红也不出声**（它不改结论，读数留给常规运行）。"""

    ci_local = _load_ci_local()
    _prepare(ci_local, monkeypatch, tmp_root)
    monkeypatch.setattr(
        ci_local,
        "REPORT_ONLY_STEPS",
        (_probe(ci_local, "import sys; print('HITS: 1 / 1 个账本（有命中）'); sys.exit(1)"),),
    )

    assert ci_local.main(["--hook", "--python", sys.executable]) == 0
    captured = capsys.readouterr()
    assert "REPORT-ONLY" not in captured.out
    assert "REPORT-ONLY" not in captured.err

    # 同一个只报告步骤在常规运行里必须出声（安静只属于钩子模式）。
    assert ci_local.main(["--full", "--python", sys.executable]) == 0
    assert "REPORT-ONLY" in capsys.readouterr().out


def test_report_only_reading_parses_an_indented_json_payload(monkeypatch, capsys, tmp_root):
    """`--json` 的载荷是缩进过的多行 JSON（indent=2）：逐行 json.loads 读不到它。

    实测（第 17 轮门禁运行）：义务门禁这一步打的就是多行载荷，读数因此退化成
    "读不出命中数" —— 零命中的那次运行于是给不出任何可引用的读数。
    """

    ci_local = _load_ci_local()
    _prepare(ci_local, monkeypatch, tmp_root)
    probe = _probe(
        ci_local,
        "import json; print(json.dumps({'hits': 0, 'ledger_count': 1,"
        " 'not_applicable_ledgers': 1}, indent=2))",
    )
    monkeypatch.setattr(
        ci_local,
        "REPORT_ONLY_STEPS",
        (probe._replace(args=(*probe.args, "--json")),),
    )

    assert ci_local.main(["--full", "--python", sys.executable]) == 0
    out = capsys.readouterr().out
    assert "hits=0 / 1 个账本" in out
    assert "不适用 1" in out


def test_report_only_step_shows_when_a_ledger_was_not_applicable(monkeypatch, capsys, tmp_root):
    """账本不存在时读数里必须看得出"不适用"：0 命中不等于"读到过一次真实读数"。"""

    ci_local = _load_ci_local()
    _prepare(ci_local, monkeypatch, tmp_root)
    probe = _probe(
        ci_local,
        "import json; print(json.dumps({'hits': 0, 'ledger_count': 1,"
        " 'not_applicable_ledgers': 1}))",
    )
    monkeypatch.setattr(
        ci_local,
        "REPORT_ONLY_STEPS",
        (probe._replace(args=(*probe.args, "--json")),),
    )

    assert ci_local.main(["--full", "--python", sys.executable]) == 0
    out = capsys.readouterr().out
    assert "hits=0 / 1 个账本" in out
    assert "不适用 1" in out
