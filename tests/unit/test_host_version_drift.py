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
import datetime as clock
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from adapters.base import AdapterSpec, manifest_digest
from adapters.cli import main, run_approve
from adapters.host_version import (
    DEFAULT_PROBE_TIMEOUT_MS,
    HOST_VERSION_RECORD_SCHEMA_VERSION,
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


# --------------------------------------------------------------------------- 观测记录（CI 形态）
#
# 这一节对应修复轮 14 的尾巴（Q8）：检查修好了、也接进门禁了，但在**没有 dsh 的 CI 上**它读不到
# 宿主版本 → unavailable → 退出 0，等于"修了一条会红的检查，却没有任何地方会为它红"。
#
# 修法不是让 CI 也装 dsh（那只是把问题搬走），而是引入一份**提交进仓库的观测记录**：
#
#   adapters/host-versions.observed.json   只能由 host-version --record 写入
#   host-version --record-check            不探测宿主，只比对「声明 vs 记录 + 记录里的
#                                          manifest 哈希」
#
# 记录必须同时钉住三样东西，缺一条这条门禁就会被绕空：
#
#   1. 观测到的版本（observed_version）；
#   2. 探测读法（executable / args / version_pattern）——读法变了，记录描述的不是同一次观测；
#   3. 观测时 manifest 的哈希——声明改了却不重录，记录立刻过期（这是"改一处必须重新审核"的延伸）。
#
# 本机形态 `--check` 的四种状态语义一个字不放宽，只**新增**第五种 recording_stale：
# 活体探测与记录不一致时退出 1，理由是"记录过期，重跑 --record 并把 diff 送评审"。

RECORD_NAME = "host-versions.observed.json"


def _record_path(root: Path) -> Path:
    return root / "adapters" / RECORD_NAME


def _run(root: Path, capsys, *extra: str) -> tuple[int, dict]:
    code = main(["--root", str(root), "host-version", *extra, "--json"])
    return code, json.loads(capsys.readouterr().out)


def _record(root: Path, capsys, *, probe_binary: str | None = None) -> dict:
    extra = ["--record"]
    if probe_binary is not None:
        extra += ["--probe-binary", "demo-agent=" + probe_binary]
    code, payload = _run(root, capsys, *extra)
    assert code == 0, payload
    return payload


def _rewrite_record(root: Path, mutate) -> Path:
    """手改提交进仓库的记录（模拟"记录被改过 / 记录与声明脱节"）。"""

    path = _record_path(root)
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )
    return path


def _manifest_digest_of(root: Path, agent_id: str = "demo-agent") -> str:
    path = root / "adapters" / agent_id / "manifest.yaml"
    spec = AdapterSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    return manifest_digest(spec.to_manifest(path=path))


def _write_repo_without_probe(
    root: Path, *, declared: str, enforcement: str, capture=None
) -> None:
    """一份**没有** host_version 读法的声明：用它证明"记录一个条目都没有"是拒写，不是空转绿。"""

    directory = root / "adapters" / "demo-agent"
    directory.mkdir(parents=True, exist_ok=True)
    document = _manifest_document(agent_version=declared, requested_enforcement=enforcement)
    (directory / "manifest.yaml").write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
        newline=chr(10),
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


def test_no_command_but_record_ever_writes_the_record(tmp_root, capsys):
    """记录只能由显式 --record 写入：报告与 --check 都不许碰它。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)
    assert not _record_path(root).exists()

    _run(root, capsys, "--check", "--probe-binary", "demo-agent=" + sys.executable)
    assert not _record_path(root).exists()

    code, payload = _run(root, capsys, "--record-check")
    assert code == 1
    assert payload["result"] == "record_missing"
    assert not _record_path(root).exists()


def test_record_pins_the_observed_version_the_reading_and_the_manifest_hash(tmp_root, capsys):
    """一条记录必须同时说出：观测到什么版本、按什么读法观测、当时是哪一份声明。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)

    payload = _record(root, capsys, probe_binary=sys.executable)

    assert payload["result"] == "pass"
    document = json.loads(_record_path(root).read_text(encoding="utf-8"))
    assert document["schema_version"] == HOST_VERSION_RECORD_SCHEMA_VERSION
    entry = document["entries"][0]
    assert entry["agent_id"] == "demo-agent"
    assert entry["observed_version"] == "1.0.0"
    # 读法来自**声明**（不是这次探测用到的本机路径）。
    assert entry["executable"] == "demo-host"
    assert list(entry["args"]) == ["-c", "print('1.0.0')"]
    assert entry["version_pattern"] == VERSION_PATTERN
    assert entry["manifest_digest"] == _manifest_digest_of(root)
    assert clock.datetime.fromisoformat(
        entry["recorded_at"].replace("Z", "+00:00")
    ).tzinfo is not None
    # 记录里不许出现本机布局：探测用的解释器路径只存在于这一次运行里。
    text = _record_path(root).read_text(encoding="utf-8")
    assert str(Path(sys.executable)) not in text
    assert str(Path(sys.executable).parent) not in text


def test_record_refuses_to_write_when_the_declaration_drifts(tmp_root, capsys):
    """宿主比声明新：这时没有可提交的证据，记录一个字节都不许写。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('2.0.0')"], capture=capsys)

    code, payload = _run(
        root, capsys, "--record", "--probe-binary", "demo-agent=" + sys.executable
    )

    assert code == 1
    # 拒写是一个**可读的结论**，不是"exit 1 而载荷说 pass"。
    assert payload["result"] == "record_refused"
    assert not _record_path(root).exists()
    assert any("2.0.0" in item and "1.0.0" in item for item in payload["failures"])


def test_record_refuses_to_write_when_the_host_is_unreadable(tmp_root, capsys):
    """读不到宿主就没有"实测值"可记：拒写，并且说清是哪一条读不到。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)

    code, payload = _run(
        root, capsys, "--record", "--probe-binary", "demo-agent=does-not-exist-xyz"
    )

    assert code == 1
    assert payload["result"] == "record_refused"
    assert any("unavailable" in item for item in payload["failures"])
    assert not _record_path(root).exists()


@pytest.mark.parametrize("enforcement", ["full", "read_only"])
def test_record_refuses_to_write_a_record_with_no_entries(tmp_root, capsys, enforcement):
    """一个条目都没有的记录 = "有门禁、没数据"：拒写（full 无读法本就算失败，read_only 也一样）。"""

    root = tmp_root / "repo"
    _write_repo_without_probe(
        root, declared="third-party-0.9.0", enforcement=enforcement, capture=capsys
    )

    code, payload = _run(root, capsys, "--record")

    assert code == 1
    assert payload["failures"]
    assert not _record_path(root).exists()


def test_recorded_check_is_green_without_any_host(tmp_root, capsys):
    """CI 形态的全部意义：这台机器上没有宿主二进制，声明与记录照样能被核对。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)
    _record(root, capsys, probe_binary=sys.executable)

    # 连 --probe-binary 都不给：声明的 demo-host 不在 PATH 上（CI 就是这种机器）。
    code, payload = _run(root, capsys, "--record-check")

    assert code == 0
    assert payload["result"] == "pass"
    assert payload["mode"] == "record"
    assert payload["covered"] == 1
    assert payload["findings"][0]["status"] == "match"
    assert payload["findings"][0]["source"] == "record"


def test_recorded_check_fails_when_the_manifest_changed_without_recording(tmp_root, capsys):
    """改声明却不重录 = 记录钉住的 manifest 哈希与当前不一致 → 红。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)
    _record(root, capsys, probe_binary=sys.executable)
    # 改了版本并**重新审核**（不重新审核会被注册表哈希先挡住，那是另一条防线）。
    _write_temp_repo(root, declared="2.0.0", args=["-c", "print('1.0.0')"], capture=capsys)

    code, payload = _run(root, capsys, "--record-check")

    assert code == 1
    assert payload["result"] == "fail"
    assert payload["findings"][0]["status"] == "recording_stale"
    assert any("--record" in item for item in payload["failures"])


def test_recorded_check_fails_when_the_recorded_version_was_hand_edited(tmp_root, capsys):
    """manifest 哈希没动、记录里的版本被改过 → 声明 ≠ 记录，红，并点名两个版本。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)
    _record(root, capsys, probe_binary=sys.executable)
    _rewrite_record(root, lambda doc: doc["entries"][0].update({"observed_version": "0.9.0"}))

    code, payload = _run(root, capsys, "--record-check")

    assert code == 1
    assert payload["result"] == "fail"
    assert payload["findings"][0]["status"] == "drift"
    assert "1.0.0" in payload["failures"][0]
    assert "0.9.0" in payload["failures"][0]
    assert "--record" in payload["failures"][0]


def test_recorded_check_fails_when_the_record_is_missing(tmp_root, capsys):
    """有门禁就必须有数据：记录缺失退出 1，绝不退化成"没东西可查"。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)
    _record(root, capsys, probe_binary=sys.executable)
    _record_path(root).unlink()

    code, payload = _run(root, capsys, "--record-check")

    assert code == 1
    assert payload["result"] == "record_missing"
    assert any("--record" in item for item in payload["failures"])


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda doc: doc["entries"][0].pop("manifest_digest"), id="missing-field"
        ),
        pytest.param(
            lambda doc: doc["entries"][0].update({"note": "手写的解释"}), id="unknown-field"
        ),
        pytest.param(lambda doc: doc.update({"entries": []}), id="empty-entries"),
        pytest.param(
            lambda doc: doc["entries"].append(dict(doc["entries"][0])), id="duplicate-agent"
        ),
        pytest.param(
            lambda doc: doc["entries"][0].update({"manifest_digest": "sha256:not-a-digest"}),
            id="bad-digest",
        ),
        pytest.param(lambda doc: doc.update({"schema_version": "9.9"}), id="unknown-version"),
        pytest.param(
            lambda doc: doc["entries"][0].update({"recorded_at": "昨天"}), id="bad-timestamp"
        ),
    ],
)
def test_recorded_check_rejects_an_incomplete_or_unknown_record(tmp_root, capsys, mutate):
    """记录缺失 / 不完整 / 未知字段 / 未知协议版本一律退出 1——不许静默跳过。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)
    _record(root, capsys, probe_binary=sys.executable)
    _rewrite_record(root, mutate)

    code, payload = _run(root, capsys, "--record-check")

    assert code == 1
    assert payload["result"] == "record_invalid"
    assert payload["failures"]


def test_a_stray_record_entry_is_a_failure_not_silence(tmp_root, capsys):
    """记录里有当前注册表没有的 Agent：记录与声明已经不同步，不是"多一条无所谓"。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)
    _record(root, capsys, probe_binary=sys.executable)
    _rewrite_record(
        root,
        lambda doc: doc["entries"].append(
            {**doc["entries"][0], "agent_id": "ghost-agent"}
        ),
    )

    code, payload = _run(root, capsys, "--record-check")

    assert code == 1
    assert payload["result"] == "fail"
    assert any("ghost-agent" in item for item in payload["failures"])


def test_live_check_flags_a_stale_record(tmp_root, capsys):
    """活体一致但记录是旧的：这条记录不能当成"已核对"，退出 1 并说清怎么修。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)
    _record(root, capsys, probe_binary=sys.executable)
    _rewrite_record(root, lambda doc: doc["entries"][0].update({"observed_version": "0.9.0"}))

    code, payload = _run(
        root, capsys, "--check", "--probe-binary", "demo-agent=" + sys.executable
    )

    assert code == 1
    assert payload["result"] == "fail"
    finding = payload["findings"][0]
    assert finding["status"] == "recording_stale"
    # 活体读到的仍然是 1.0.0：新状态说的是"记录与活体不一致"，不是"声明漂移"。
    assert finding["observed_version"] == "1.0.0"
    assert any("记录过期" in item for item in payload["failures"])
    assert any("--record" in item for item in payload["failures"])
    # 账本要说得出口「这次覆盖了几个」：stale 的那条**参与过**比对（活体探测成功、版本一致），
    # 不能一边写「观测记录…参与了比对」一边写「本次没有任何 Adapter 真正参与比对」。
    assert payload["covered"] == 1
    assert not any("什么都没有覆盖" in note for note in payload["notes"])
    assert any("参与了比对" in note for note in payload["notes"])


def test_live_check_is_green_when_the_record_matches_the_host(tmp_root, capsys):
    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)
    _record(root, capsys, probe_binary=sys.executable)

    code, payload = _run(
        root, capsys, "--check", "--probe-binary", "demo-agent=" + sys.executable
    )

    assert code == 0
    assert payload["result"] == "pass"
    assert payload["findings"][0]["status"] == "match"
    # 记录确实参与了这次比对（不是被忽略掉之后"看起来绿"）。
    assert payload["findings"][0]["recorded_at"]


def test_live_check_does_not_compare_the_record_when_the_host_is_unreadable(tmp_root, capsys):
    """读不到宿主时记录不参与比对：状态仍是 unavailable，不是 match，也不是 recording_stale。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)
    _record(root, capsys, probe_binary=sys.executable)

    code, payload = _run(root, capsys, "--check", "--require-runtime")

    assert code == 1
    assert payload["result"] == "unavailable"
    assert payload["findings"][0]["status"] == "unavailable"
    assert any("记录" in note for note in payload["notes"])


def test_report_mode_never_gates_on_a_stale_record(tmp_root, capsys):
    """报告模式（不带 --check）不改退出码：记录过期照样打印出来，但退出 0。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)
    _record(root, capsys, probe_binary=sys.executable)
    _rewrite_record(root, lambda doc: doc["entries"][0].update({"observed_version": "0.9.0"}))

    code, payload = _run(root, capsys, "--probe-binary", "demo-agent=" + sys.executable)

    assert code == 0
    assert payload["result"] == "fail"
    assert payload["failures"]


def test_record_check_rejects_host_only_flags(tmp_root, capsys):
    """CI 形态不探测宿主：给了只对活体探测有意义的开关是用法错误，不许静默忽略。"""

    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)

    code = main(
        [
            "--root", str(root),
            "host-version", "--record-check", "--probe-binary", "demo-agent=" + sys.executable,
        ]
    )

    assert code == 2
    assert "--probe-binary" in capsys.readouterr().err


def test_record_and_record_check_are_mutually_exclusive(tmp_root, capsys):
    root = tmp_root / "repo"
    _write_temp_repo(root, declared="1.0.0", args=["-c", "print('1.0.0')"], capture=capsys)

    code = main(["--root", str(root), "host-version", "--record", "--record-check"])

    assert code == 2
    assert "--record" in capsys.readouterr().err
