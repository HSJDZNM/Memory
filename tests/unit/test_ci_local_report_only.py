"""本机门禁「只报告」步骤的回归（L5 试用期口径：只读数、不判罚）。

为什么单独一个文件：这一族行为（非零退出不进 failures、读不出命中数也照实说、
--list 里豁免不许隐形）是"本轮不新增阻断步骤"这条裁定的可执行形态；
它与 tests/unit/test_ci_local.py 里的锁 / 解释器回归是两件事，混在一起会让两边都难读。
"""

from __future__ import annotations

import datetime as _datetime
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

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


def test_json_objects_survive_braces_inside_string_values() -> None:
    """字符串值里的 { } 是内容不是结构：数花括号会整段读不出（读数退化成"读不出命中数"）。"""

    ci_local = _load_ci_local()
    payload = json.dumps(
        {"hits": 3, "ledger_count": 1, "note": "半截 } 收尾"},
        ensure_ascii=False,
        indent=2,
    )
    found = ci_local.json_objects(payload + chr(10) + "后续输出：这一步的结论行" + chr(10))

    assert [item.get("hits") for item in found] == [3]


def test_json_objects_read_a_multi_line_payload() -> None:
    """阳性对照：普通多行载荷照旧读得出来（第一行只有一个 {）。"""

    ci_local = _load_ci_local()
    payload = json.dumps({"hits": 0, "ledger_count": 2}, ensure_ascii=False, indent=2)

    assert [item.get("hits") for item in ci_local.json_objects(payload)] == [0]


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


@pytest.mark.parametrize(
    "body, extra_args",
    [
        # 文本读数：exemption_expiry 的形态——退出码恒为 0，命中只在 HITS: 行里
        ("print('HITS: 2 / 8 条豁免（到期提醒 1，过期 1）')", ()),
        # 结构化读数：退出码 0 也不许把 hits 覆盖成 0
        ("import json; print(json.dumps({'hits': 2, 'ledger_count': 3}))", ("--json",)),
    ],
    ids=["hits-line", "json-hits"],
)
def test_exit_code_zero_with_hits_is_not_reported_as_zero_hits(
    monkeypatch, capsys, tmp_root, body, extra_args
):
    """退出码 0 ≠ 0 命中：结论里的命中数必须取自读数（第 13 轮发现）。

    过去结论写死"退出码 0 ⇒ 0 命中（退出码 0）"，而 exemption_expiry 的退出码永远是 0——
    有豁免到期 / 过期时，REPORT-ONLY 行会同时写着"0 命中"和一条 HITS>0 的读数。
    """

    ci_local = _load_ci_local()
    _prepare(ci_local, monkeypatch, tmp_root)
    probe = _probe(ci_local, body)
    monkeypatch.setattr(
        ci_local,
        "REPORT_ONLY_STEPS",
        (probe._replace(args=(*probe.args, *extra_args)),),
    )

    assert ci_local.main(["--full", "--python", sys.executable]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if "REPORT-ONLY" in line]
    assert len(lines) == 1, lines
    assert "—— 2 命中（退出码 0）" in lines[0]
    assert "—— 0 命中" not in lines[0]


def _run_report_only_step(step, *extra: str) -> "subprocess.CompletedProcess[str]":
    """按 REPORT_ONLY_STEPS 里**那一条真实步骤**的 args 起子进程（与门禁同一条命令）。"""

    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO_ROOT / "src")
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, *step.args, *extra],
        cwd=str(REPO_ROOT),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def test_real_exemption_expiry_output_yields_an_integer_hit_count():
    """真实输出喂给真实解析器：tools/exemption_expiry.py 的默认输出必须读出**整数**命中数。

    这条用例不复刻输出格式：子进程跑的就是 ci_local 登记的那条命令（仓库真实的豁免声明），
    再用同一天的 `--json` 载荷交叉核对——命中数 = 已过期条数（HITS 行的契约）。
    格式一旦漂移（HITS 行被删 / 改名 / 数字不再在冒号后面），这里就会红，
    而不是让门禁悄悄退回"命中数读不出"。
    """

    ci_local = _load_ci_local()
    step = next(
        item for item in ci_local.REPORT_ONLY_STEPS
        if any("exemption_expiry.py" in argument for argument in item.args)
    )
    assert "--json" not in step.args  # 这一步读的是默认文本输出
    today = _datetime.date.today().isoformat()  # 两次运行钉同一天，避免跨午夜读数不一致

    text = _run_report_only_step(step, "--today", today)
    assert text.returncode == 0, text.stdout + text.stderr
    count, reading = ci_local.report_only_reading(step, text.stdout + text.stderr)
    assert isinstance(count, int) and not isinstance(count, bool), reading
    assert reading.startswith("HITS: %d " % count), reading

    payload = _run_report_only_step(step, "--today", today, "--json")
    assert payload.returncode == 0, payload.stdout + payload.stderr
    expired = json.loads(payload.stdout)["counts"]["expired"]
    assert count == expired, (count, expired, reading)
    assert ci_local.report_only_verdict(text.returncode, count) == "%d 命中（退出码 0）" % count


INSTRUMENT_SELF_PROOF_STEP = "Instrument self-proof (report only)"


def test_instrument_self_proof_is_registered_as_a_report_only_step():
    """登记：仪器自证（R-h）是一条只报告步骤，六个字段齐全，且**不带 --json**。

    不带 --json 是读数契约的一部分：它的载荷没有 hits 键（不是账本），带了 --json
    读取器就只认载荷、永远读不到 HITS: 行（26 号交接第 1 节）。
    """

    ci_local = _load_ci_local()
    matches = [
        step for step in ci_local.REPORT_ONLY_STEPS if step.name == INSTRUMENT_SELF_PROOF_STEP
    ]
    assert len(matches) == 1, [step.name for step in ci_local.REPORT_ONLY_STEPS]
    step = matches[0]
    assert step.args == ("tools/instrument_self_proof.py",)
    assert "--json" not in step.args
    for field in ("reason", "expires_at", "adopted", "reads"):
        assert getattr(step, field).strip(), field
    _datetime.date.fromisoformat(step.expires_at)
    _datetime.date.fromisoformat(step.adopted)


def test_real_instrument_self_proof_output_reads_zero_hits():
    """真实默认输出喂给真实读取器：读出整数 0 命中，结论是「0 命中（退出码 0）」。

    0 命中同时说明登记表与对象清单对得上：这一步自己就是对象清单第 4 族的一员，
    加了步骤却没在 validation/instrument-checks.yaml 补 "report-only:<name>" 那一行，
    仪器自证会报 no_check_id=1 —— 这条用例就红在这里，而不是等门禁读数里悄悄多出一个命中。
    """

    ci_local = _load_ci_local()
    step = next(
        item for item in ci_local.REPORT_ONLY_STEPS if item.name == INSTRUMENT_SELF_PROOF_STEP
    )

    completed = _run_report_only_step(step)  # 按登记的 args 起子进程，仓库根为 cwd
    assert completed.returncode == 0, completed.stdout + completed.stderr
    count, reading = ci_local.report_only_reading(step, completed.stdout + completed.stderr)
    assert count == 0, reading
    assert reading.startswith("HITS: 0 / "), reading
    assert "no_check_id=0" in reading, reading
    assert ci_local.report_only_verdict(completed.returncode, count) == "0 命中（退出码 0）"


CONTROL_PLANE_FACTS_STEP = "Control plane facts (report only)"


def test_control_plane_facts_is_registered_as_a_report_only_step():
    """登记：控制面事实表（台阶 5）是一条只报告步骤，六个字段齐全，且**不带 --json**。

    形状与期望读数见 28 号交接第 1 节。
    """

    ci_local = _load_ci_local()
    matches = [
        step for step in ci_local.REPORT_ONLY_STEPS if step.name == CONTROL_PLANE_FACTS_STEP
    ]
    assert len(matches) == 1, [step.name for step in ci_local.REPORT_ONLY_STEPS]
    step = matches[0]
    assert step.args == ("tools/control_plane_facts.py",)
    assert "--json" not in step.args
    for field in ("reason", "expires_at", "adopted", "reads"):
        assert getattr(step, field).strip(), field
    _datetime.date.fromisoformat(step.expires_at)
    _datetime.date.fromisoformat(step.adopted)


def test_real_control_plane_facts_output_yields_an_integer_hit_count():
    """真实默认输出喂给真实读取器：读出**整数**命中数，结论里的数字就是这个整数。

    刻意**不**断言命中数是多少：这一步处在只报告期，今天的 101 是 C1 的存量不一致；
    pytest 是阻断步骤，在这里钉死命中数等于把只报告的读数偷偷升格成门禁。
    只钉读数契约：HITS: 行在、能读出整数、尾部的 checks= 与登记表行数一致。
    """

    ci_local = _load_ci_local()
    step = next(
        item for item in ci_local.REPORT_ONLY_STEPS if item.name == CONTROL_PLANE_FACTS_STEP
    )

    completed = _run_report_only_step(step)  # 按登记的 args 起子进程，仓库根为 cwd
    assert completed.returncode == 0, completed.stdout + completed.stderr
    count, reading = ci_local.report_only_reading(step, completed.stdout + completed.stderr)
    assert isinstance(count, int) and not isinstance(count, bool), reading
    assert reading.startswith("HITS: %d / " % count), reading
    assert ci_local.report_only_verdict(completed.returncode, count) == (
        "%d 命中（退出码 0）" % count
    )

    table = yaml.safe_load(
        (REPO_ROOT / "validation" / "instrument-checks.yaml").read_text(encoding="utf-8")
    )
    assert reading.endswith("checks=%d" % len(table["checks"])), reading


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


def test_quiet_default_still_parses_the_full_output_and_keeps_it_in_a_log(
    monkeypatch, capsys, tmp_root
):
    """默认的精简输出（步骤输出写日志、控制台每步一行）不能让读数变短。

    载荷故意做得比失败尾部（TAIL_LINES）长得多、`hits` 放在最前面：读数解析拿到的
    必须是子进程的**完整** stdout，而不是控制台上截出来的尾巴；完整输出另存一份日志。
    """

    ci_local = _load_ci_local()
    _prepare(ci_local, monkeypatch, tmp_root)
    body = (
        "import json; print(json.dumps({'hits': 4, 'ledger_count': 2,"
        " 'rows': list(range(%d))}, indent=2)); raise SystemExit(1)" % (ci_local.TAIL_LINES * 5)
    )
    probe = _probe(ci_local, body)
    monkeypatch.setattr(
        ci_local,
        "REPORT_ONLY_STEPS",
        (probe._replace(args=(*probe.args, "--json")),),
    )

    assert ci_local.main(["--full", "--python", sys.executable]) == 0
    out = capsys.readouterr().out
    assert "hits=4 / 2 个账本" in out
    assert "=== Probe report only（只报告） ===" not in out  # 精简模式不打标题块
    logs = sorted((tmp_root / ".tmp" / "ci-local-logs").glob("*probe-report-only.log"))
    assert [item.name for item in logs] == ["02-probe-report-only.log"]  # 序号接在 workflow 步骤后
    assert "ci-local-logs/02-probe-report-only.log" in out
    text = logs[0].read_text(encoding="utf-8")
    assert '"hits": 4' in text and text.startswith("$ ")


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
