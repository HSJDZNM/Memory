"""R14 / 缺陷 2：声明版本 vs 宿主实际版本，必须能被比对，并且在漂移时变红。

为什么这组用例必须存在：adapters/<agent>/manifest.yaml 的 agent_version 字段说明是
「**已实测**的 Agent 产品版本」（src/adapters/models.py），但在本轮修复之前**全仓库没有
任何地方**把它与宿主实际版本比过——宿主升到 0.1.6-alpha.2 之后，一致性套件、事件 fixture
重放与支持矩阵**全部照常通过**。一条永远为绿的检查等于没有检查，因此这里的每个用例要么
钉住「漂移会被发现」，要么钉住「读不到时不许说成通过」。

两条口径写在前头（它们本身就是被测行为）：

1. **版本不一致不是拦截判定**：它只让显式调用的检查退出 1，不改变任何 allow / block
   （把版本号变成放行条件，会把「宿主升级」直接封成「平台不可用」）；
2. **四种状态互不折叠**：match / drift / not_declared / unavailable。
   「这台机器上读不到宿主版本」与「读到且一致」是两件事。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from adapters.cli import main, run_approve
from adapters.host_version import (
    DEFAULT_PROBE_TIMEOUT_MS,
    HostVersionStatus,
    check_declared_versions,
    probe_host_version,
)
from adapters.models import AdapterManifest, HostVersionProbe

VERSION_PATTERN = r"([0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.]+)?)"


# --------------------------------------------------------------------------- 夹具


def _manifest_document(**overrides) -> dict:
    """一份最小可用的 manifest 文档（字段形状与 adapters/dsh/manifest.yaml 同类）。"""

    document: dict = {
        "schema_version": "1.0",
        "agent_id": "demo-agent",
        "agent_version": "1.0.0",
        "display_name": "Demo Agent",
        "protocol": "hook-command",
        "protocol_version": "demo-hooks@1",
        "pre_hook": {"declared": True, "kind": "pre_hook", "response_kind": "exit_code"},
        "post_hook": {"declared": False, "kind": "request_gate", "response_kind": "exit_code"},
        "approval": "none",
        "blocking": "pre_execute",
        "response_kind": "exit_code",
        "event_types": ["tool.pre_execute"],
        "requested_enforcement": "full",
    }
    document.update(overrides)
    return document


def _probe(**overrides) -> dict:
    document = {
        "executable": "demo-host",
        "args": ["-c", "print('1.0.0')"],
        "version_pattern": VERSION_PATTERN,
    }
    document.update(overrides)
    return document


def _manifest(declared: str, *, probe: dict | None = None, **overrides) -> AdapterManifest:
    payload = _manifest_document(agent_version=declared, **overrides)
    if probe is not None:
        payload["host_version"] = probe
    return AdapterManifest.model_validate(payload)


def _check(
    manifest: AdapterManifest,
    *,
    enforcement: str = "full",
    override: Path | str | None = sys.executable,
    runner=None,
    timeout_ms: int = DEFAULT_PROBE_TIMEOUT_MS,
):
    """跑一次比对。默认用**真实子进程**（sys.executable），只是把可执行文件钉死。"""

    overrides = {} if override is None else {manifest.agent_id: override}
    return check_declared_versions(
        {manifest.agent_id: manifest},
        enforcement_by_agent={manifest.agent_id: enforcement},
        overrides=overrides,
        timeout_ms=timeout_ms,
        runner=runner,
    )


# --------------------------------------------------------------------------- 探测本身


def test_probe_reads_the_version_from_the_declared_command():
    probe = HostVersionProbe(**_probe(args=["-c", "print('0.1.6-alpha.2')"]))

    outcome = probe_host_version(probe, executable_override=sys.executable)

    assert outcome.ok is True
    assert outcome.version == "0.1.6-alpha.2"
    assert outcome.executable_name == Path(sys.executable).name


def test_probe_with_a_missing_executable_is_unavailable_not_a_match():
    probe = HostVersionProbe(**_probe(executable="definitely-not-installed-xyz"))

    outcome = probe_host_version(probe, executable_override=None)

    assert outcome.ok is False
    assert outcome.version is None
    assert "找不到" in outcome.detail


def test_probe_with_a_non_zero_exit_is_unavailable():
    probe = HostVersionProbe(**_probe(args=["-c", "raise SystemExit(7)"]))

    outcome = probe_host_version(probe, executable_override=sys.executable)

    assert outcome.ok is False
    assert "退出码 7" in outcome.detail


def test_probe_with_unparsable_output_is_unavailable():
    probe = HostVersionProbe(**_probe(args=["-c", "print('no version here')"]))

    outcome = probe_host_version(probe, executable_override=sys.executable)

    assert outcome.ok is False
    assert "解析不出" in outcome.detail


def test_probe_timeout_is_unavailable():
    def timeout_runner(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout", 0))

    probe = HostVersionProbe(**_probe())

    outcome = probe_host_version(
        probe, executable_override=sys.executable, runner=timeout_runner, timeout_ms=50
    )

    assert outcome.ok is False
    assert "超时" in outcome.detail


def test_probe_detail_does_not_leak_absolute_paths():
    """探测失败的理由里不许出现本机绝对路径（AGENTS.md 第 19 条同一口径）。"""

    probe = HostVersionProbe(
        **_probe(args=["-c", "raise SystemExit('C:/Users/someone/secret/project')"])
    )

    outcome = probe_host_version(probe, executable_override=sys.executable)

    assert outcome.ok is False
    assert "C:/Users/someone" not in outcome.detail
    assert "<path>" in outcome.detail


# --------------------------------------------------------------------------- 比对结论


def test_matching_declaration_passes():
    report = _check(_manifest("0.1.0", probe=_probe(args=["-c", "print('0.1.0')"])))

    assert report.result == "pass"
    assert report.failures == ()
    assert report.covered == 1
    assert report.findings[0].status is HostVersionStatus.MATCH
    assert report.findings[0].observed_version == "0.1.0"


def test_drift_is_a_failure_and_says_how_to_fix_it():
    """本轮缺陷的正面钉子：声明 0.1.5-rc.1、宿主 0.1.6-alpha.2 —— 必须红。"""

    report = _check(_manifest("0.1.5-rc.1", probe=_probe(args=["-c", "print('0.1.6-alpha.2')"])))

    finding = report.findings[0]
    assert finding.status is HostVersionStatus.DRIFT
    assert finding.declared_version == "0.1.5-rc.1"
    assert finding.observed_version == "0.1.6-alpha.2"
    assert report.result == "fail"
    assert len(report.failures) == 1
    # 拒绝理由必须给出「改成什么形态就能过」（AGENTS.md 第 50 条）。
    assert "approve --reviewer" in report.failures[0]
    assert "agent_version" in report.failures[0]


def test_a_full_adapter_without_a_probe_declaration_is_a_failure():
    """删掉 host_version 块可以让检查「什么都查不到」——因此它是失败，不是跳过。"""

    report = _check(_manifest("1.0.0", probe=None), enforcement="full")

    assert report.findings[0].status is HostVersionStatus.NOT_DECLARED
    assert report.result == "fail"
    assert report.covered == 0
    assert "host_version" in report.failures[0]


def test_a_read_only_adapter_without_a_probe_is_reported_but_not_a_failure():
    """合成协议消费者没有宿主二进制：它是显式状态，不是失败，也绝不计入「已比对」。"""

    report = _check(_manifest("third-party-0.9.0", probe=None), enforcement="read_only")

    assert report.findings[0].status is HostVersionStatus.NOT_DECLARED
    assert report.result == "pass"
    assert report.failures == ()
    assert report.covered == 0
    assert report.total == 1
    assert any("什么都没有覆盖" in note for note in report.to_dict()["notes"])


def test_unavailable_is_not_reported_as_a_match():
    manifest = _manifest("1.0.0", probe=_probe(executable="definitely-not-installed-xyz"))

    report = _check(manifest, override=None)

    assert report.findings[0].status is HostVersionStatus.UNAVAILABLE
    assert report.result == "unavailable"
    assert report.failures == ()
    # 它不是 pass：一个「读不到」绝不能长得像「核对过了」。
    assert report.result != "pass"


def test_report_is_deterministic_and_has_no_absolute_paths():
    manifest = _manifest("1.0.0", probe=_probe(args=["-c", "print('1.0.0')"]))

    first = _check(manifest).to_dict()
    second = _check(manifest).to_dict()

    assert first == second
    dumped = json.dumps(first, ensure_ascii=False, sort_keys=True)
    assert str(Path(sys.executable).parent) not in dumped
    assert str(Path(sys.executable)) not in dumped


# --------------------------------------------------------------------------- 声明本身


def test_probe_executable_must_be_a_bare_command_name():
    for bad in ("../../evil", "/bin/sh", "cmd.exe && calc", "C:\\tools\\dsh.exe"):
        with pytest.raises(ValidationError):
            HostVersionProbe(**_probe(executable=bad))


def test_probe_arguments_reject_shell_composition():
    """探测是 argv 直执（不经 shell）：声明里出现组合字符一律拒绝。"""

    for bad in ("a; rm -rf /", "a | b", "$(whoami)", "\x60id\x60", "a > out.txt", "line\nbreak"):
        with pytest.raises(ValidationError):
            HostVersionProbe(**_probe(args=[bad]))


def test_probe_pattern_must_capture_exactly_one_group():
    for bad in (r"[0-9]+\.[0-9]+", r"([0-9]+)\.([0-9]+)"):
        with pytest.raises(ValidationError):
            HostVersionProbe(**_probe(version_pattern=bad))


def test_probe_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        HostVersionProbe(**_probe(command="dsh --version"))


def test_manifest_rejects_a_malformed_probe():
    with pytest.raises(ValidationError):
        _manifest("1.0.0", probe=_probe(executable="/usr/bin/env"))


def test_manifest_without_a_probe_still_validates():
    """合成协议消费者不必声明探测：这个字段是可选的。"""

    assert _manifest("third-party-0.9.0", probe=None).host_version is None


# --------------------------------------------------------------------------- CLI 入口


def _write_temp_repo(
    root: Path, *, declared: str, args: list, enforcement: str = "full", capture=None
) -> None:
    directory = root / "adapters" / "demo-agent"
    directory.mkdir(parents=True, exist_ok=True)
    document = _manifest_document(
        agent_version=declared, requested_enforcement=enforcement, host_version=_probe(args=args)
    )
    (directory / "manifest.yaml").write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
    approved = run_approve(
        argparse.Namespace(
            root=str(root), approved=None, reviewer="unit-test", allow_unsupported=False
        )
    )
    assert approved == 0
    if capture is not None:
        # run_approve 自己也会打印一份 JSON：先清掉，别让它混进被测命令的输出。
        capture.readouterr()


def test_cli_drift_is_red_and_match_is_green(tmp_root, capsys):
    """同一条命令：声明与宿主一致 → 0；不一致 → 1。检查因此「现在通过、以后能失败」。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)

    code = main(
        [
            "--root", str(root),
            "host-version", "--check", "--json",
            "--probe-binary", "demo-agent=" + sys.executable,
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["result"] == "pass"
    assert payload["findings"][0]["status"] == "match"

    # 宿主「升级」了：同一条声明立刻变红。
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('2.0.0')"], capture=capsys)
    code = main(
        [
            "--root", str(root),
            "host-version", "--check", "--json",
            "--probe-binary", "demo-agent=" + sys.executable,
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["result"] == "fail"
    assert payload["findings"][0]["status"] == "drift"
    assert payload["findings"][0]["observed_version"] == "2.0.0"


def test_cli_reports_without_check_and_exits_zero(tmp_root, capsys):
    """不带 --check 时它是一份报告：漂移照样打出来，但不改退出码。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('2.0.0')"], capture=capsys)

    code = main(
        [
            "--root", str(root),
            "host-version", "--json",
            "--probe-binary", "demo-agent=" + sys.executable,
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["result"] == "fail"
    assert payload["failures"]


def test_cli_unavailable_needs_the_explicit_require_runtime_flag(tmp_root, capsys):
    """读不到宿主版本：--check 不红，--require-runtime 红——环境跳过必须能被显式要求成红灯。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)

    code = main(
        ["--root", str(root), "host-version", "--check", "--json",
         "--probe-binary", "demo-agent=does-not-exist-xyz"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["result"] == "unavailable"

    code = main(
        ["--root", str(root), "host-version", "--check", "--require-runtime", "--json",
         "--probe-binary", "demo-agent=does-not-exist-xyz"]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["result"] == "unavailable"


def test_cli_report_does_not_leak_absolute_paths(tmp_root, capsys):
    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)

    main(
        [
            "--root", str(root),
            "host-version", "--json",
            "--probe-binary", "demo-agent=" + sys.executable,
        ]
    )
    printed = capsys.readouterr().out

    assert str(root) not in printed
    assert str(Path(sys.executable).parent) not in printed
    # 解析到的可执行文件只以文件名出现。
    assert Path(sys.executable).name in printed


def test_cli_rejects_a_probe_binary_for_an_unknown_agent(tmp_root, capsys):
    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)

    code = main(["--root", str(root), "host-version", "--probe-binary", "nobody=/bin/sh"])

    assert code == 2
    assert "nobody" in capsys.readouterr().err
