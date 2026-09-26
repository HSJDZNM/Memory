"""通道清点的对外契约：CLI 退出码、JSON 形状、与运行期自检的一致性。

这组断言守的是"假安全感"：如果配置缺失或损坏时 wiring --check 仍然退出 0，
这条命令就只是在给零治理盖章（R2 / G13 / G1）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import POLICIES_DIR, REPO_ROOT, write_dsh_config

from adapters.cli import build_parser, main
from adapters.wiring import (
    FAILURE_STATUSES,
    WIRING_SCHEMA_VERSION,
    ChannelStatus,
    probe_wiring,
)

pytestmark = pytest.mark.contract

POLICY_COMMAND = (
    "python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml "
    "--hooks-config .policy/hooks.json --audit .policy/audit.jsonl"
)
ADAPTER_CONFIG = "project: demo\ntimeout_ms: 5000\naudit_log: .policy/audit.jsonl\n"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def make_home(tmp_root: Path) -> Path:
    home = tmp_root / "dsh-home"
    (home / "profiles").mkdir(parents=True, exist_ok=True)
    return home


def profile_patch(project_dir: Path, command: str = POLICY_COMMAND) -> str:
    return (
        "- insert:\n"
        "    - id: policy-hook\n"
        "      name: '<repo>/src/adapters/dsh/policy-hook.plugin.mjs'\n"
        "      config:\n"
        "        command: '" + command + "'\n"
        "        timeoutMs: 30000\n"
        "        projectDir: '" + project_dir.as_posix() + "'\n"
    )


def hooks_document(command: str = POLICY_COMMAND, timeout: float = 30) -> dict[str, Any]:
    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "",
                    "hooks": [{"type": "command", "command": command, "timeout": timeout}],
                }
            ]
        }
    }


def add_profile(home: Path, name: str, patch: str, *, hooks: Any = "good") -> Path:
    profile = home / "profiles" / name
    profile.mkdir(parents=True, exist_ok=True)
    _write(profile / "cordis.yml", "[]\n")
    _write(profile / "cordis.patch.yml", patch)
    if hooks is not None:
        _write(
            profile / ".policy" / "hooks.json",
            hooks if isinstance(hooks, str) else json.dumps(hooks),
        )
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(
        profile / ".policy" / "audit.jsonl",
        json.dumps({"timestamp": "2026-09-25T11:59:00Z"}) + "\n",
    )
    return profile


def wired_home(tmp_root: Path) -> Path:
    home = make_home(tmp_root)
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True, exist_ok=True)
    _write(profile / "cordis.yml", "[]\n")
    _write(profile / "cordis.patch.yml", profile_patch(profile))
    _write(profile / ".policy" / "hooks.json", json.dumps(hooks_document()))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(
        profile / ".policy" / "audit.jsonl",
        json.dumps({"timestamp": "2026-09-25T11:59:00Z"}) + "\n",
    )
    return home


def run_cli(argv: list[str], capsys: Any) -> tuple[int, str, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --------------------------------------------------------------------------- CLI


def test_wiring_check_exits_zero_only_for_a_wired_channel(tmp_root: Path, capsys: Any) -> None:
    home = wired_home(tmp_root)

    code, out, _ = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home), "--check"], capsys
    )

    assert code == 0, out
    assert "result" not in out or "pass" in out


def test_wiring_check_exits_non_zero_and_names_the_unwired_channel(
    tmp_root: Path, capsys: Any
) -> None:
    """完成判据：对"未接线"必须退出非 0，并在输出里指名道姓说哪个通道没接。"""

    home = make_home(tmp_root)
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True, exist_ok=True)
    _write(profile / "cordis.yml", "[]\n")
    _write(profile / "cordis.patch.yml", "[]\n")

    code, out, err = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home), "--check"], capsys
    )

    assert code == 1
    assert "dsh:desktop" in err
    assert "not_wired" in err


def test_wiring_without_check_is_a_report_not_a_gate(tmp_root: Path, capsys: Any) -> None:
    home = make_home(tmp_root)
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True, exist_ok=True)
    _write(profile / "cordis.patch.yml", "[]\n")

    code, out, err = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home)], capsys
    )

    assert code == 0
    assert "not_wired" in out
    assert "fail" in err


def test_unreadable_configuration_never_passes(tmp_root: Path, capsys: Any) -> None:
    """配置"读不到"必须是显式失败态：这条断言就是"读不到不等于通过"。"""

    home = make_home(tmp_root)
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True, exist_ok=True)
    # 有 profile 目录、没有 patch 层：dsh 会照常启动且不报错。
    _write(profile / "cordis.yml", "[]\n")

    code, out, err = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home), "--check", "--json"],
        capsys,
    )

    assert code == 1
    payload = json.loads(out)
    channel = payload["channels"][0]
    assert channel["status"] == ChannelStatus.HOOKS_CONFIG_MISSING.value
    assert channel["wired"] is False
    assert payload["result"] == "fail"


def test_unprovable_budget_fails_the_check(tmp_root: Path, capsys: Any) -> None:
    """预算事实读不到 -> --check 非 0。

    "读不到"不等于"不等式成立"：读不到就证明不了，按失败处理（不许默默放行）。
    两种读法失败都要覆盖：文件不在、文件在但不是合法 YAML。
    """

    home = wired_home(tmp_root)
    adapter_config = home / "profiles" / "desktop" / ".policy" / "dsh-adapter.yaml"

    adapter_config.unlink()
    code, out, _ = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home), "--check", "--json"],
        capsys,
    )

    assert code == 1
    payload = json.loads(out)
    channel = payload["channels"][0]
    assert payload["result"] == "fail"
    assert channel["status"] == ChannelStatus.TIMEOUT_BUDGET_UNKNOWN.value
    assert channel["wired"] is False
    assert channel["timeout_budget"]["input_error"]
    assert channel["detail"].startswith("证明不了")

    adapter_config.write_text("{not yaml", encoding="utf-8", newline="\n")
    second_code, second_out, _ = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home), "--check", "--json"],
        capsys,
    )

    assert second_code == 1
    second = json.loads(second_out)
    assert second["channels"][0]["status"] == ChannelStatus.TIMEOUT_BUDGET_UNKNOWN.value
    assert "不可读或不可解析" in second["channels"][0]["detail"]


def test_wiring_json_contract(tmp_root: Path, capsys: Any) -> None:
    home = wired_home(tmp_root)

    code, out, _ = run_cli(
        ["--root", str(REPO_ROOT), "--json", "wiring", "--dsh-home", str(home), "--check"],
        capsys,
    )

    assert code == 0
    payload = json.loads(out)
    assert payload["wiring_schema_version"] == WIRING_SCHEMA_VERSION
    assert set(payload) >= {
        "wiring_schema_version",
        "probe",
        "channels",
        "counts",
        "failures",
        "tools",
        "result",
    }
    assert set(payload["probe"]) >= {
        "dsh_home",
        "dsh_home_source",
        "candidates",
        "status",
        "profiles_dir",
        "project_root",
        "stale_after_seconds",
        "notes",
    }
    assert payload["counts"] == {"total": 1, "wired": 1, "failed": 0}
    assert payload["failures"] == []
    assert payload["result"] == "pass"
    assert payload["tools"]["report_only"] is True
    assert payload["channels"][0]["status"] == ChannelStatus.WIRED.value


def test_wiring_json_exposes_required_channel_statuses() -> None:
    """枚举值是协议：删一个、改一个名字都必须是一次显式的契约变更。"""

    assert {status.value for status in ChannelStatus} == {
        "wired",
        "not_wired",
        "hooks_config_missing",
        "hooks_config_unparsable",
        "no_audit_target",
        "audit_never_written",
        "stale",
        "profile_unreadable",
        "hooks_config_unreadable",
        "audit_unreadable",
        "audit_unparsable",
        "timeout_budget_violated",
        "timeout_budget_unknown",
    }
    assert set(FAILURE_STATUSES) == set(ChannelStatus) - {ChannelStatus.WIRED}


def test_missing_dsh_home_fails_the_check_and_says_so(tmp_root: Path, capsys: Any) -> None:
    code, out, err = run_cli(
        [
            "--root",
            str(REPO_ROOT),
            "wiring",
            "--dsh-home",
            str(tmp_root / "nowhere"),
            "--check",
            "--json",
        ],
        capsys,
    )

    assert code == 1
    payload = json.loads(out)
    assert payload["probe"]["status"] == "dsh_home_missing"
    assert payload["channels"] == []
    assert payload["result"] == "fail"
    assert "没有任何通道可以证明已接线" in " ".join(payload["probe"]["notes"])


def test_wiring_usage_errors_exit_two(tmp_root: Path, capsys: Any) -> None:
    home = wired_home(tmp_root)

    bad_now, _, err_now = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home), "--now", "not-a-time"],
        capsys,
    )
    bad_stale, _, err_stale = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--dsh-home", str(home), "--stale-after", "0"],
        capsys,
    )
    bad_root, _, err_root = run_cli(
        [
            "--root",
            str(REPO_ROOT),
            "wiring",
            "--dsh-home",
            str(home),
            "--project-root",
            str(tmp_root / "nowhere"),
        ],
        capsys,
    )

    assert (bad_now, bad_stale, bad_root) == (2, 2, 2)
    assert "--now" in err_now
    assert "stale_after_seconds" in err_stale
    assert "project-root" in err_root


def test_wiring_subcommand_is_registered_and_documented() -> None:
    import adapters.cli as cli_module

    parser = build_parser()
    subparsers = [
        action for action in parser._actions if getattr(action, "choices", None)  # noqa: SLF001
    ]
    commands = set(subparsers[0].choices)
    assert {"matrix", "approve", "check", "inspect", "events", "wiring"} <= commands
    assert "python -m adapters.cli wiring" in cli_module.__doc__


def test_wiring_output_contains_no_absolute_paths(tmp_root: Path, capsys: Any) -> None:
    """AGENTS.md 第 19 条：证据里不得出现绝对路径（夹具根也不行）。"""

    home = wired_home(tmp_root)

    _, out, err = run_cli(
        ["--root", str(REPO_ROOT), "--json", "wiring", "--dsh-home", str(home)], capsys
    )

    combined = out + err
    assert str(tmp_root) not in combined
    assert tmp_root.as_posix() not in combined


# --------------------------------------------------------------------------- 与运行期自检互相验证


def test_wiring_verdict_agrees_with_the_hook_self_check(tmp_root: Path, dsh_project: Path) -> None:
    """两套独立实现（运行期 hooks.check_wiring 与本模块的遍历）必须得到同一个结论。

    它们要是漂移了，"清点说接好了、运行期却判 wiring_error" 这种矛盾就没有任何检查能发现。
    """

    from adapters.dsh.hooks import check_wiring, load_config

    config_path = write_dsh_config(
        tmp_root / "cfg" / "dsh-adapter.yaml", project_root=dsh_project, rules=POLICIES_DIR
    )
    config = load_config(config_path)
    home = make_home(tmp_root)
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True, exist_ok=True)
    _write(profile / "cordis.yml", "[]\n")
    _write(profile / "cordis.patch.yml", profile_patch(profile))

    good = _write(profile / ".policy" / "hooks.json", json.dumps(hooks_document()))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(
        profile / ".policy" / "audit.jsonl",
        json.dumps({"timestamp": "2026-09-25T11:59:00Z"}) + "\n",
    )
    assert check_wiring(config, hooks_config_path=good) == ""
    good_status = probe_wiring(dsh_home=home, observed_sessions=0).channels[0].status
    assert good_status is ChannelStatus.WIRED, good_status

    bad = _write(
        profile / ".policy" / "hooks.json",
        json.dumps(hooks_document(command="python -m other.thing")),
    )
    report = check_wiring(config, hooks_config_path=bad)
    assert report != ""
    bad_status = probe_wiring(dsh_home=home, observed_sessions=0).channels[0].status
    assert bad_status is ChannelStatus.NOT_WIRED, bad_status


def test_missing_hooks_config_agrees_with_the_hook_self_check(
    tmp_root: Path, dsh_project: Path
) -> None:
    from adapters.dsh.hooks import check_wiring, load_config

    config_path = write_dsh_config(
        tmp_root / "cfg" / "dsh-adapter.yaml", project_root=dsh_project, rules=POLICIES_DIR
    )
    config = load_config(config_path)
    home = make_home(tmp_root)
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True, exist_ok=True)
    _write(profile / "cordis.yml", "[]\n")
    _write(profile / "cordis.patch.yml", profile_patch(profile))

    missing = profile / ".policy" / "hooks.json"
    assert check_wiring(config, hooks_config_path=missing) != ""
    status = probe_wiring(dsh_home=home, observed_sessions=0).channels[0].status
    assert status is ChannelStatus.HOOKS_CONFIG_MISSING, status


def test_timeout_budget_check_agrees_with_the_hook_self_check(
    tmp_root: Path, dsh_project: Path
) -> None:
    """超时不等式：运行期判 wiring_error 的情形，清点必须把预算事实标出来。"""

    from adapters.dsh.hooks import check_wiring, load_config

    config_path = write_dsh_config(
        tmp_root / "cfg" / "dsh-adapter.yaml", project_root=dsh_project, rules=POLICIES_DIR
    )
    config = load_config(config_path)
    home = make_home(tmp_root)
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True, exist_ok=True)
    _write(profile / "cordis.yml", "[]\n")
    _write(profile / "cordis.patch.yml", profile_patch(profile))
    hooks_path = _write(profile / ".policy" / "hooks.json", json.dumps(hooks_document(timeout=3)))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(
        profile / ".policy" / "audit.jsonl",
        json.dumps({"timestamp": "2026-09-25T11:59:00Z"}) + "\n",
    )

    # 运行期判错 -> 清点必须也是失败态（不是"只记一条 warning"）。
    assert check_wiring(config, hooks_config_path=hooks_path) != ""
    channel = probe_wiring(dsh_home=home, observed_sessions=0).channels[0]
    assert channel.timeout_budget["ok"] is False
    assert channel.status is ChannelStatus.TIMEOUT_BUDGET_VIOLATED
    assert channel.ok is False


# --------------------------------------------------------------------------- 默认探测


def test_default_probe_never_reports_a_vacuous_pass() -> None:
    """用默认位置（$DSH_HOME / ~/.dsh）探测：不许炸，也不许在探不到通道时说 pass。"""

    report = probe_wiring(observed_sessions=0)

    assert report.result in {"pass", "fail", "skipped"}
    assert [channel.channel_id for channel in report.channels] == sorted(
        channel.channel_id for channel in report.channels
    )
    if not report.channels:
        assert report.ok is False
        assert report.result != "pass"


def test_no_runtime_is_skipped_in_the_cli_and_require_runtime_turns_it_red(
    tmp_root: Path, monkeypatch: Any, capsys: Any
) -> None:
    """环境跳过：--check 退出 0 但 result=skipped（并写明原因），--require-runtime 让它变红。"""

    monkeypatch.setattr(
        "adapters.wiring._dsh_home_candidates",
        lambda: [("test:no-runtime", tmp_root / "no-runtime")],
    )

    code, out, _ = run_cli(
        ["--root", str(REPO_ROOT), "--json", "wiring", "--check"], capsys
    )

    assert code == 0
    payload = json.loads(out)
    assert payload["result"] == "skipped"
    assert payload["environment_skipped"] is True
    assert payload["skip_reason"] and "环境跳过" in payload["skip_reason"]
    assert payload["reproduce"]
    assert payload["channels"] == []
    assert payload["result"] != "pass"

    strict, out_strict, err_strict = run_cli(
        ["--root", str(REPO_ROOT), "wiring", "--check", "--require-runtime"], capsys
    )

    assert strict == 1
    assert "skipped" in err_strict
    assert "复现" in err_strict
