"""通道清点（adapters.wiring）的状态机：每一种"没接线"都必须是显式状态。

为什么这些断言值得存在（R2 / G13 / G1）：如果配置缺失或损坏时清点仍然通过，
这个模块就只是给"零治理"盖了一个章——比没有检查更危险。
"""

from __future__ import annotations

import datetime as clock
import json
import re
from pathlib import Path
from typing import Any, Optional

import pytest
from conftest import POLICIES_DIR, REPO_ROOT, write_dsh_config

from adapters.wiring import (
    DEFAULT_INTERNAL_BUDGET_MS,
    FAILURE_STATUSES,
    IN_PROCESS_DEFAULT_TIMEOUT_MS,
    ChannelStatus,
    ToolObservationStatus,
    WiringError,
    declared_tool_table,
    probe_wiring,
)

NOW = clock.datetime(2026, 9, 25, 12, 0, tzinfo=clock.timezone.utc)

POLICY_COMMAND = (
    "python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml "
    "--hooks-config .policy/hooks.json --audit .policy/audit.jsonl"
)
# 故意不带 --audit 的变体：用来测"没声明审计目标"与"从 adapter 配置读 audit_log"两条路径。
POLICY_COMMAND_WITHOUT_AUDIT = (
    "python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml "
    "--hooks-config .policy/hooks.json"
)
ADAPTER_CONFIG = "project: demo\ntimeout_ms: 5000\naudit_log: .policy/audit.jsonl\n"
# 不带 audit_log 的变体：用来测"接线成立且预算可证，但没有声明审计目标"。
ADAPTER_CONFIG_WITHOUT_AUDIT = "project: demo\ntimeout_ms: 5000\n"

# 需求要求"状态至少包含"的七种：少一种就说明有一类失效没法被说出来。
REQUIRED_STATUSES = (
    ChannelStatus.WIRED,
    ChannelStatus.NOT_WIRED,
    ChannelStatus.HOOKS_CONFIG_MISSING,
    ChannelStatus.HOOKS_CONFIG_UNPARSABLE,
    ChannelStatus.NO_AUDIT_TARGET,
    ChannelStatus.AUDIT_NEVER_WRITTEN,
    ChannelStatus.STALE,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def make_home(tmp_root: Path) -> Path:
    home = tmp_root / "dsh-home"
    (home / "profiles").mkdir(parents=True, exist_ok=True)
    return home


def make_profile(home: Path, name: str, *, root: bool = True) -> Path:
    profile = home / "profiles" / name
    profile.mkdir(parents=True, exist_ok=True)
    if root:
        _write(profile / "cordis.yml", "[]\n")
    return profile


def in_process_patch(
    project_dir: Path, command: str = POLICY_COMMAND, dsh_timeout_ms: Any = 30000
) -> str:
    """dsh_timeout_ms=None 表示**不写** timeoutMs（插件会用它的 DEFAULT_TIMEOUT_MS）。"""

    timeout_line = (
        "" if dsh_timeout_ms is None else "        timeoutMs: " + repr(dsh_timeout_ms) + "\n"
    )
    return (
        "- insert:\n"
        "    - id: policy-hook\n"
        "      name: '<repo>/src/adapters/dsh/policy-hook.plugin.mjs'\n"
        "      config:\n"
        "        command: '" + command + "'\n"
        + timeout_line
        + "        projectDir: '" + project_dir.as_posix() + "'\n"
    )


def dialect_patch(project_dir: Path) -> str:
    return (
        "- insert:\n"
        "    - id: hooks-claude-code\n"
        "      name: '@deepseek-ai/dsh-hooks-claude-code'\n"
        "      config:\n"
        "        configPath: .policy/hooks.json\n"
        "        projectDir: '" + project_dir.as_posix() + "'\n"
    )


def policy_hooks(command: str = POLICY_COMMAND, timeout: Any = 30) -> dict[str, Any]:
    """timeout=None 表示**不写** timeout（用来构造"dsh 侧超时没有可读声明"的情形）。"""

    entry: dict[str, Any] = {"type": "command", "command": command}
    if timeout is not None:
        entry["timeout"] = timeout
    return {"hooks": {"PreToolUse": [{"matcher": "", "hooks": [entry]}]}}


def audit_line(timestamp: str) -> str:
    return json.dumps({"timestamp": timestamp, "reason_code": "allow"}, sort_keys=True) + "\n"


def wired_profile(
    home: Path,
    name: str = "desktop",
    *,
    audit: Optional[str] = "2026-09-25T11:59:00Z",
    command: str = POLICY_COMMAND,
    timeout: float = 30,
    bundles: Optional[list[str]] = None,
) -> Path:
    """一个"接好了"的通道：桥挂上了、hooks 配置指向策略 Hook、审计有新鲜留痕。"""

    profile = make_profile(home, name)
    _write(profile / "cordis.patch.yml", in_process_patch(profile))
    _write(profile / ".policy" / "hooks.json", json.dumps(policy_hooks(command, timeout)))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    if audit is not None:
        _write(profile / ".policy" / "audit.jsonl", audit_line(audit))
    if bundles is not None:
        _write(
            profile / "package.json",
            json.dumps({"dsh": {"profile": {"bundles": bundles}}}),
        )
    return profile


def probe(home: Path, **overrides: Any):
    """默认关掉会话观察：单元测试只测它自己构造的事实。"""

    overrides.setdefault("now", NOW)
    overrides.setdefault("observed_sessions", 0)
    return probe_wiring(dsh_home=home, **overrides)


def status_of(home: Path, name: str = "desktop", **overrides: Any) -> ChannelStatus:
    report = probe(home, **overrides)
    channels = {channel.channel_id: channel for channel in report.channels}
    assert "dsh:" + name in channels, sorted(channels)
    return channels["dsh:" + name].status


# --------------------------------------------------------------------- 正例


def test_wired_profile_passes_and_carries_the_facts(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    wired_profile(home, bundles=["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app"])

    report = probe(home)

    assert report.result == "pass", report.failures
    assert report.skipped is False
    channel = report.channels[0]
    assert channel.status is ChannelStatus.WIRED
    assert channel.hooks_config_exists is True
    assert channel.audit_records == 1
    assert channel.last_record_at == "2026-09-25T11:59:00Z"
    assert channel.age_seconds == 60
    assert channel.bundles == ("@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app")
    assert channel.hook_flags["--config"] == ".policy/dsh-adapter.yaml"
    # 命令原文可能带凭据：报告里只有摘要，没有原文。
    assert POLICY_COMMAND not in json.dumps(report.to_dict(), ensure_ascii=False)
    assert channel.hook_command_digest and len(channel.hook_command_digest) == 16


def test_dialect_bridge_is_recognised_as_wired(tmp_root: Path) -> None:
    """dsh 自带的 Claude Code 方言桥也是合法接线（configPath 指向 hooks.json）。"""

    home = make_home(tmp_root)
    profile = make_profile(home, "web")
    _write(profile / "cordis.patch.yml", dialect_patch(profile))
    _write(profile / ".policy" / "hooks.json", json.dumps(policy_hooks()))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(profile / ".policy" / "audit.jsonl", audit_line("2026-09-25T11:59:30Z"))

    report = probe(home)

    assert report.ok, report.failures
    assert report.channels[0].status is ChannelStatus.WIRED


def test_profile_patch_with_js_tag_is_not_a_parse_failure(tmp_root: Path) -> None:
    """dsh 的 patch 允许 !!js 表达式：裸 safe_load 会把它判成"不可解析"（假红）。

    真机上 desktop profile 就带 !!js；把它报成配置损坏会让这条检查失去可信度。
    这里把表达式放在不影响接线判定的字段上（projectDir），断言仍然 wired。
    """

    home = make_home(tmp_root)
    profile = make_profile(home, "desktop")
    patch = in_process_patch(profile).replace(
        "projectDir: '" + profile.as_posix() + "'", "projectDir: !!js process.cwd()"
    )
    _write(profile / "cordis.patch.yml", patch)
    _write(profile / ".policy" / "hooks.json", json.dumps(policy_hooks()))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(profile / ".policy" / "audit.jsonl", audit_line("2026-09-25T11:59:00Z"))

    report = probe(home)

    channel = report.channels[0]
    assert channel.status is ChannelStatus.WIRED, channel.detail
    assert any("js" in warning for warning in channel.warnings), channel.warnings


def test_js_expression_in_timeout_ms_makes_the_budget_unprovable(tmp_root: Path) -> None:
    """表达式形式的 dsh 侧超时读不出数值：不是"配置损坏"，但也不等于不等式成立。

    这正是本轮的口径：值读不出来 -> 证明不了 -> 失败态（不是 wired，也不是 unparsable）。
    """

    home = make_home(tmp_root)
    profile = make_profile(home, "desktop")
    patch = in_process_patch(profile).replace(
        "        timeoutMs: 30000\n",
        "        timeoutMs: !!js 1000 * 30\n",
    )
    _write(profile / "cordis.patch.yml", patch)
    _write(profile / ".policy" / "hooks.json", json.dumps(policy_hooks(timeout=None)))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(profile / ".policy" / "audit.jsonl", audit_line("2026-09-25T11:59:00Z"))

    report = probe(home)

    channel = report.channels[0]
    assert channel.status is ChannelStatus.TIMEOUT_BUDGET_UNKNOWN
    assert channel.status is not ChannelStatus.HOOKS_CONFIG_UNPARSABLE
    assert channel.detail.startswith("证明不了")


# --------------------------------------------------------------------- 反例


def test_empty_patch_layer_is_not_wired(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    _write(make_profile(home, "headless") / "cordis.patch.yml", "[]\n")

    report = probe(home)

    assert not report.ok
    assert report.channels[0].status is ChannelStatus.NOT_WIRED
    assert report.channels[0].detail


def test_missing_patch_layer_is_explicit_failure_not_pass(tmp_root: Path) -> None:
    """配置读不到 = 显式失败态。这条断言就是"配置读不到不等于通过"。"""

    home = make_home(tmp_root)
    make_profile(home, "desktop")

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.HOOKS_CONFIG_MISSING
    assert report.ok is False
    assert "patch 层不存在" in report.channels[0].detail


def test_patch_layer_that_is_a_directory_is_unreadable(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    profile = make_profile(home, "desktop")
    (profile / "cordis.patch.yml").mkdir()

    assert status_of(home) is ChannelStatus.PROFILE_UNREADABLE


def test_unparsable_patch_layer_is_explicit_failure(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    _write(make_profile(home, "desktop") / "cordis.patch.yml", "- id: [unclosed\n")

    assert status_of(home) is ChannelStatus.HOOKS_CONFIG_UNPARSABLE


def test_patch_layer_with_non_list_structure_is_unparsable(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    _write(make_profile(home, "desktop") / "cordis.patch.yml", "just-a-string\n")

    assert status_of(home) is ChannelStatus.HOOKS_CONFIG_UNPARSABLE


def test_bridge_without_hooks_config_reference_is_failure(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    profile = make_profile(home, "desktop")
    _write(
        profile / "cordis.patch.yml",
        "- insert:\n    - id: policy-hook\n"
        "      name: '<repo>/src/adapters/dsh/policy-hook.plugin.mjs'\n"
        "      config:\n        timeoutMs: 30000\n",
    )

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.HOOKS_CONFIG_MISSING
    assert "运行期接线自检会被关掉" in report.channels[0].detail


def test_missing_hooks_config_file_is_failure(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    profile = make_profile(home, "desktop")
    _write(profile / "cordis.patch.yml", dialect_patch(profile))

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.HOOKS_CONFIG_MISSING
    assert report.channels[0].hooks_config_exists is False


def test_hooks_config_that_is_a_directory_is_unreadable(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    profile = make_profile(home, "desktop")
    _write(profile / "cordis.patch.yml", dialect_patch(profile))
    (profile / ".policy" / "hooks.json").mkdir(parents=True)

    assert status_of(home) is ChannelStatus.HOOKS_CONFIG_UNREADABLE


def test_unparsable_hooks_config_is_failure(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    profile = make_profile(home, "desktop")
    _write(profile / "cordis.patch.yml", dialect_patch(profile))
    _write(profile / ".policy" / "hooks.json", "{not json")

    assert status_of(home) is ChannelStatus.HOOKS_CONFIG_UNPARSABLE


def test_hooks_config_without_policy_command_is_not_wired(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    profile = make_profile(home, "desktop")
    _write(profile / "cordis.patch.yml", dialect_patch(profile))
    _write(
        profile / ".policy" / "hooks.json",
        json.dumps(policy_hooks(command="python -m other.thing")),
    )
    _write(profile / ".policy" / "audit.jsonl", audit_line("2026-09-25T11:59:00Z"))

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.NOT_WIRED
    assert "adapters.dsh.hooks" in report.channels[0].detail


def test_bridge_mounted_but_never_calling_the_hook_is_not_wired(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    # 桥挂了、hooks 配置也在，但命令调用的是别的模块：这不是"配置缺失"，是"没接上"。
    other = (
        "python -m other.thing --config .policy/dsh-adapter.yaml "
        "--hooks-config .policy/hooks.json"
    )
    profile = make_profile(home, "desktop")
    _write(profile / "cordis.patch.yml", in_process_patch(profile, command=other))
    _write(profile / ".policy" / "hooks.json", json.dumps(policy_hooks(command=other)))

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.NOT_WIRED
    assert "adapters.dsh.hooks" in report.channels[0].detail


def test_hooks_config_without_policy_command_breaks_the_runtime_self_check(
    tmp_root: Path,
) -> None:
    """桥命令是对的，但它带的 --hooks-config 里没有策略命令：运行期自检会判 wiring_error。

    这种组合既不是"零治理"也不是"已治理"：Hook 每次都被自己的自检拦下来。
    两套实现必须给出同一个结论——运行期 hooks.check_wiring 会说"没有接入策略 Hook"。
    """

    home = make_home(tmp_root)
    profile = make_profile(home, "desktop")
    _write(profile / "cordis.patch.yml", in_process_patch(profile))
    _write(
        profile / ".policy" / "hooks.json",
        json.dumps(policy_hooks(command="python -m other.thing")),
    )
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(profile / ".policy" / "audit.jsonl", audit_line("2026-09-25T11:59:00Z"))

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.NOT_WIRED
    assert "wiring_error" in report.channels[0].detail


def test_audit_target_not_declared_is_no_audit_target(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    command = POLICY_COMMAND_WITHOUT_AUDIT
    profile = make_profile(home, "desktop")
    _write(profile / "cordis.patch.yml", in_process_patch(profile, command=command))
    _write(profile / ".policy" / "hooks.json", json.dumps(policy_hooks(command)))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG_WITHOUT_AUDIT)

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.NO_AUDIT_TARGET
    assert report.channels[0].audit_path is None


def test_audit_log_from_adapter_config_is_used(tmp_root: Path) -> None:
    """命令没写 --audit 时，adapter 配置里的 audit_log 也算声明（但它必须真的存在）。"""

    home = make_home(tmp_root)
    command = POLICY_COMMAND_WITHOUT_AUDIT
    profile = make_profile(home, "desktop")
    _write(profile / "cordis.patch.yml", in_process_patch(profile, command=command))
    _write(profile / ".policy" / "hooks.json", json.dumps(policy_hooks(command)))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)

    report = probe(home)

    # 声明了目标但文件不存在：这正是 audit_never_written（而不是"没有目标"）。
    assert report.channels[0].status is ChannelStatus.AUDIT_NEVER_WRITTEN
    assert report.channels[0].audit_path == "profiles/desktop/.policy/audit.jsonl"


def test_audit_never_written_when_file_is_missing(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    wired_profile(home, audit=None)

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.AUDIT_NEVER_WRITTEN
    assert report.channels[0].audit_records == 0


def test_audit_never_written_when_file_is_empty(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    profile = wired_profile(home, audit=None)
    _write(profile / ".policy" / "audit.jsonl", "")

    assert status_of(home) is ChannelStatus.AUDIT_NEVER_WRITTEN


def test_audit_without_any_parsable_record_is_unparsable(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    profile = wired_profile(home, audit=None)
    _write(profile / ".policy" / "audit.jsonl", "{not json\n" + "garbage\n")

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.AUDIT_UNPARSABLE
    assert report.channels[0].audit_bad_lines == 2


def test_audit_path_that_is_a_directory_is_unreadable(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    profile = wired_profile(home, audit=None)
    (profile / ".policy" / "audit.jsonl").mkdir()

    assert status_of(home) is ChannelStatus.AUDIT_UNREADABLE


def test_stale_audit_fails(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    wired_profile(home, audit="2026-09-01T00:00:00Z")

    report = probe(home, stale_after_seconds=3600)

    channel = report.channels[0]
    assert channel.status is ChannelStatus.STALE
    assert channel.age_seconds is not None and channel.age_seconds > 3600


def test_fresh_audit_within_threshold_passes(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    wired_profile(home, audit="2026-09-25T11:30:00Z")

    assert status_of(home, stale_after_seconds=3600) is ChannelStatus.WIRED


def test_future_audit_timestamp_is_clamped_with_warning(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    wired_profile(home, audit="2026-09-25T13:00:00Z")

    report = probe(home, stale_after_seconds=3600)

    assert report.channels[0].status is ChannelStatus.WIRED
    assert report.channels[0].age_seconds == 0
    assert any("时钟偏移" in warning for warning in report.channels[0].warnings)


def test_partially_corrupt_audit_keeps_the_verdict_but_warns(tmp_root: Path) -> None:
    """AuditLedger 只容忍被截断的最后一行：结论不变，但必须说出来。"""

    home = make_home(tmp_root)
    profile = wired_profile(home, audit=None)
    _write(
        profile / ".policy" / "audit.jsonl",
        audit_line("2026-09-25T11:59:00Z") + '{"timestamp": "2026-09-25T11:59',
    )

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.WIRED
    assert report.channels[0].audit_bad_lines == 1
    assert any("不可解析" in warning for warning in report.channels[0].warnings)


# --------------------------------------------------------------------- 阈值与判定


@pytest.mark.parametrize(
    "status", [item for item in ChannelStatus if item is not ChannelStatus.WIRED]
)
def test_every_non_wired_status_is_a_failure(status: ChannelStatus) -> None:
    assert status in FAILURE_STATUSES
    assert status.is_wired is False


def test_required_statuses_exist_in_the_enum() -> None:
    """需求点名要有的状态一个都不能少（少了就等于有一类失效没法被说出来）。"""

    for status in REQUIRED_STATUSES:
        assert status in ChannelStatus


def test_status_matrix_covers_the_required_states(tmp_root: Path) -> None:
    """用真实 fixture 把"每种状态都做得出来"钉住（不是只断言枚举里有这个名字）。"""

    cases: dict[ChannelStatus, Any] = {}

    home = make_home(tmp_root / "a")
    wired_profile(home)
    cases[ChannelStatus.WIRED] = home

    home = make_home(tmp_root / "b")
    _write(make_profile(home, "desktop") / "cordis.patch.yml", "[]\n")
    cases[ChannelStatus.NOT_WIRED] = home

    home = make_home(tmp_root / "c")
    make_profile(home, "desktop")
    cases[ChannelStatus.HOOKS_CONFIG_MISSING] = home

    home = make_home(tmp_root / "d")
    _write(make_profile(home, "desktop") / "cordis.patch.yml", "- id: [unclosed\n")
    cases[ChannelStatus.HOOKS_CONFIG_UNPARSABLE] = home

    home = make_home(tmp_root / "e")
    command = POLICY_COMMAND_WITHOUT_AUDIT
    profile = make_profile(home, "desktop")
    _write(profile / "cordis.patch.yml", in_process_patch(profile, command=command))
    _write(profile / ".policy" / "hooks.json", json.dumps(policy_hooks(command)))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG_WITHOUT_AUDIT)
    cases[ChannelStatus.NO_AUDIT_TARGET] = home

    home = make_home(tmp_root / "f")
    wired_profile(home, audit=None)
    cases[ChannelStatus.AUDIT_NEVER_WRITTEN] = home

    home = make_home(tmp_root / "g")
    wired_profile(home, audit="2026-09-01T00:00:00Z")
    cases[ChannelStatus.STALE] = home

    home = make_home(tmp_root / "h")
    profile = make_profile(home, "desktop")
    _write(profile / "cordis.patch.yml", in_process_patch(profile, dsh_timeout_ms=3000))
    _write(profile / ".policy" / "hooks.json", json.dumps(policy_hooks()))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(profile / ".policy" / "audit.jsonl", audit_line("2026-09-25T11:59:00Z"))
    cases[ChannelStatus.TIMEOUT_BUDGET_VIOLATED] = home

    home = make_home(tmp_root / "i")
    profile = wired_profile(home)
    (profile / ".policy" / "dsh-adapter.yaml").unlink()  # 预算事实读不到
    cases[ChannelStatus.TIMEOUT_BUDGET_UNKNOWN] = home

    # 需求点名的 7 种 + 预算的两种失败态：每种都必须做得出来，且只有 wired 通过。
    assert set(cases) == set(REQUIRED_STATUSES) | {
        ChannelStatus.TIMEOUT_BUDGET_VIOLATED,
        ChannelStatus.TIMEOUT_BUDGET_UNKNOWN,
    }
    for expected, case_home in cases.items():
        report = probe(case_home, stale_after_seconds=3600)
        assert report.channels[0].status is expected, expected
        assert report.ok is (expected is ChannelStatus.WIRED)
        # 只有 wired 通过；其余一律能让 --check 变红（ok 就是 --check 的判据）。
        assert report.ok is (expected is ChannelStatus.WIRED)


def test_unknown_entries_in_the_patch_do_not_crash_and_are_not_guessed(tmp_root: Path) -> None:
    """未知的 patch 条目照原样忽略（dsh 的配置格式不是本模块能穷举的），但不猜它是接线。"""

    home = make_home(tmp_root)
    profile = make_profile(home, "desktop")
    _write(
        profile / "cordis.patch.yml",
        "- insert:\n    - id: something-else\n      name: '@deepseek-ai/dsh-tool-web'\n"
        "      config:\n        futureField: 1\n",
    )

    assert status_of(home) is ChannelStatus.NOT_WIRED


def test_multiple_bridges_are_reported_not_silently_ignored(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    profile = wired_profile(home)
    _write(
        profile / "cordis.patch.yml",
        in_process_patch(profile)
        + "- insert:\n    - id: hooks-claude-code\n"
        "      name: '@deepseek-ai/dsh-hooks-claude-code'\n"
        "      config:\n        configPath: .policy/hooks.json\n",
    )

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.WIRED
    assert len(report.channels[0].bridge["detected"]) == 2
    assert any("多个策略桥" in warning for warning in report.channels[0].warnings)


# --------------------------------------------------------------------- 探测本身


def test_explicit_missing_dsh_home_is_a_failure_not_a_pass_nor_a_skip(
    tmp_root: Path,
) -> None:
    """显式指定 --dsh-home 却不存在 = 失败：那是"你声称有运行时"，不是环境没有。"""

    report = probe_wiring(dsh_home=tmp_root / "nope", now=NOW, observed_sessions=0)

    assert report.probe_status == "dsh_home_missing"
    assert report.channels == ()
    assert report.ok is False
    assert report.result == "fail"
    assert report.skipped is False
    assert report.failures == ()


def test_no_discoverable_runtime_is_skipped_not_passed(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """探遍了候选根、本机根本没有运行时 -> skipped（**不是 pass**，也不是 fail）。

    报成 fail 会让没有 Agent 的机器上这条命令永远红着，最终被当成噪声；
    报成 pass 就是造假。所以要有第三个显式终态，并且必须写明原因与复现方式。
    """

    monkeypatch.setattr(
        "adapters.wiring._dsh_home_candidates",
        lambda: [("test:no-runtime", tmp_root / "no-runtime")],
    )

    report = probe_wiring(observed_sessions=0, now=NOW)

    assert report.result == "skipped"
    assert report.ok is False
    assert report.channels == ()
    assert report.skipped is True
    assert report.skip_reason is not None and "环境跳过" in report.skip_reason
    assert report.reproduce is not None
    payload = report.to_dict()
    assert payload["result"] == "skipped"
    assert payload["environment_skipped"] is True
    assert payload["skip_reason"] == report.skip_reason


def test_missing_profiles_dir_is_a_failure_not_a_pass(tmp_root: Path) -> None:
    home = tmp_root / "dsh-home"
    home.mkdir()

    report = probe(home)

    assert report.probe_status == "profiles_dir_missing"
    assert report.ok is False


def test_directories_that_are_not_profiles_are_skipped_and_named(tmp_root: Path) -> None:
    """profiles 目录里只有非 profile 目录：运行时在、但没有通道 -> fail（不是 skipped）。"""

    home = make_home(tmp_root)
    (home / "profiles" / "node_modules").mkdir()

    report = probe(home)

    assert report.channels == ()
    assert report.ok is False
    assert report.result == "fail"
    assert report.skipped is False
    assert any("node_modules" in note for note in report.notes)


def test_a_skipped_directory_never_turns_the_whole_report_into_skipped(
    tmp_root: Path,
) -> None:
    """回归：真机上 profiles/ 里有个 node_modules。

    它必须只进 notes（"这个目录不是 profile"），**不能**把整份报告的 result 变成 skipped——
    那会让"发现了运行时但没接线"被读成"这台机器没有运行时"。
    """

    home = make_home(tmp_root)
    (home / "profiles" / "node_modules").mkdir()
    _write(make_profile(home, "desktop") / "cordis.patch.yml", "[]\n")

    report = probe(home)

    assert report.result == "fail"
    assert report.skipped is False
    assert report.to_dict()["environment_skipped"] is False
    assert [channel.channel_id for channel in report.channels] == ["dsh:desktop"]
    assert report.channels[0].status is ChannelStatus.NOT_WIRED


def test_channels_are_sorted_by_channel_id_and_output_is_deterministic(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    # 故意按倒序创建：排序不能依赖创建时间 / mtime。
    wired_profile(home, "web")
    wired_profile(home, "headless")
    wired_profile(home, "desktop")

    first = probe(home)
    second = probe(home)

    assert [channel.channel_id for channel in first.channels] == [
        "dsh:desktop",
        "dsh:headless",
        "dsh:web",
    ]
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(
        second.to_dict(), sort_keys=True
    )


def test_report_contains_no_absolute_paths(tmp_root: Path) -> None:
    """AGENTS.md 第 19 条：证据里不得出现绝对路径。"""

    home = make_home(tmp_root)
    project = tmp_root / "governed-project"
    project.mkdir()
    profile = make_profile(home, "desktop")
    _write(profile / "cordis.patch.yml", in_process_patch(project))
    _write(project / ".policy" / "hooks.json", json.dumps(policy_hooks()))
    _write(project / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(project / ".policy" / "audit.jsonl", audit_line("2026-09-25T11:59:00Z"))

    report = probe(home, project_root=project)
    payload = json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True)

    assert report.ok, report.failures
    assert str(tmp_root) not in payload
    assert tmp_root.as_posix() not in payload
    assert "<external>/hooks.json" in payload


def test_tool_declaration_is_read_from_the_adapter_tool_table(tmp_root: Path) -> None:
    """工具表只有一份声明源：只读导入 TOOL_TABLE，不复制。"""

    home = make_home(tmp_root)
    wired_profile(home)

    report = probe(home)
    table = declared_tool_table()

    assert report.tools.declaration_source.endswith("adapter.py:TOOL_TABLE")
    assert report.tools.declaration_error is None
    assert report.tools.declared == tuple(sorted(table))
    assert report.tools.report_only is True


def test_observed_runtime_tools_are_reported_but_never_block(tmp_root: Path) -> None:
    """漂移只报告：即便运行期出现了表里没有的工具，--check 的判据（ok）不受影响。"""

    home = make_home(tmp_root)
    wired_profile(home)
    sessions = home / "sessions" / "--ws--"
    sessions.mkdir(parents=True)
    # 一个 MCP 工具名：dsh 的默认拒绝白名单永远不该认识它（mcp__ 前缀是外部工具）。
    unknown_tool = "mcp__github__create_issue"
    _write(
        sessions / "session.jsonl",
        json.dumps({"data": {"header": {"tools": [{"name": "edit"}, {"name": unknown_tool}]}}})
        + "\n"
        + json.dumps(
            {"data": {"message": {"content": [{"type": "tool_use", "name": "team_task_create"}]}}}
        )
        + "\n",
    )

    report = probe(home, observed_sessions=4)

    assert report.ok, report.failures
    assert report.tools.observation_status is ToolObservationStatus.OBSERVED
    assert report.tools.sessions_scanned == 1
    assert report.tools.runtime_declared == ("edit", unknown_tool)
    assert report.tools.runtime_called == ("team_task_create",)
    # 漂移口径 = 观察到的集合减去声明表；表里有的（edit / team_task_create）不算漂移。
    observed = {"edit", unknown_tool, "team_task_create"}
    assert set(report.tools.observed_not_in_table) == observed - set(declared_tool_table())
    assert unknown_tool in report.tools.observed_not_in_table


def test_unavailable_observation_is_explicit_not_a_clean_bill(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    wired_profile(home)

    report = probe(home, observed_sessions=4)

    assert report.tools.observation_status is ToolObservationStatus.OBSERVATION_UNAVAILABLE
    assert report.tools.observed_not_in_table == ()
    assert report.tools.observation_detail


def test_disabled_observation_says_so(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    wired_profile(home)

    report = probe(home, observed_sessions=0)

    assert report.tools.observation_status is ToolObservationStatus.DISABLED


def test_zstd_session_records_are_read(tmp_root: Path) -> None:
    zstandard = pytest.importorskip("zstandard")
    home = make_home(tmp_root)
    wired_profile(home)
    sessions = home / "sessions" / "--ws--"
    sessions.mkdir(parents=True)
    body = (
        json.dumps({"data": {"header": {"tools": [{"name": "spawn_teammate"}]}}}) + "\n"
    ).encode("utf-8")
    (sessions / "session.v4.jsonl.zstd").write_bytes(
        zstandard.ZstdCompressor().compress(body)
    )

    report = probe(home, observed_sessions=2)

    assert report.tools.observation_status is ToolObservationStatus.OBSERVED
    assert report.tools.runtime_declared == ("spawn_teammate",)


def test_timeout_budget_violation_blocks(tmp_root: Path) -> None:
    """内部预算必须小于 dsh 侧 timeout；违反时**阻断**。

    理由不是"看着更严"，而是仓库自己的口径（AGENTS.md 第 10 条 + hooks.check_wiring）：
    dsh 侧超时一到就杀 Hook，而被杀在 dsh 协议里等于放行。运行期判错、清点判过 = 两套口径。
    """

    home = make_home(tmp_root)
    # 进程内插件的 dsh 侧超时是 patch 里的 timeoutMs；它必须大于内部预算 5000ms。
    profile = make_profile(home, "desktop")
    _write(profile / "cordis.patch.yml", in_process_patch(profile, dsh_timeout_ms=3000))
    _write(profile / ".policy" / "hooks.json", json.dumps(policy_hooks()))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(profile / ".policy" / "audit.jsonl", audit_line("2026-09-25T11:59:00Z"))

    report = probe(home)

    channel = report.channels[0]
    assert channel.status is ChannelStatus.TIMEOUT_BUDGET_VIOLATED
    assert channel.ok is False
    assert report.ok is False
    assert channel.timeout_budget["ok"] is False
    assert "被杀等于放行" in channel.detail
    # 留痕事实不能被吞掉：状态优先报预算不等式，但审计事实仍然要在报告里读得到。
    assert channel.audit_records == 1
    assert channel.last_record_at == "2026-09-25T11:59:00Z"


def test_hooks_timeout_over_budget_also_blocks(tmp_root: Path) -> None:
    """方言桥的情况：hooks.json 的 timeout 就是 dsh 侧超时，同样必须大于内部预算。"""

    home = make_home(tmp_root)
    profile = make_profile(home, "web")
    _write(profile / "cordis.patch.yml", dialect_patch(profile))
    _write(profile / ".policy" / "hooks.json", json.dumps(policy_hooks(timeout=3)))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(profile / ".policy" / "audit.jsonl", audit_line("2026-09-25T11:59:00Z"))

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.TIMEOUT_BUDGET_VIOLATED
    assert report.channels[0].timeout_budget["hooks_config_timeout_ms"] == 3000.0


def test_timeout_budget_ok_is_recorded(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    wired_profile(home, timeout=30)

    report = probe(home)

    assert report.channels[0].timeout_budget["ok"] is True
    assert report.channels[0].timeout_budget["internal_budget_ms"] == 5000


@pytest.mark.parametrize(
    "overrides",
    [
        {"stale_after_seconds": 0},
        {"stale_after_seconds": -1},
        {"observed_sessions": -1},
    ],
)
def test_invalid_arguments_raise_wiring_error(tmp_root: Path, overrides: dict[str, Any]) -> None:
    home = make_home(tmp_root)
    wired_profile(home)

    with pytest.raises(WiringError):
        probe(home, **overrides)


def test_naive_now_is_rejected(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    wired_profile(home)

    with pytest.raises(WiringError):
        probe_wiring(
            dsh_home=home,
            now=clock.datetime(2026, 9, 25, 12, 0),
            observed_sessions=0,
        )


def test_missing_project_root_is_rejected(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    wired_profile(home)

    with pytest.raises(WiringError):
        probe(home, project_root=tmp_root / "nowhere")


# --------------------------------------------------------------- 预算事实读不到 -> 失败态


def test_adapter_config_missing_makes_the_budget_unprovable(tmp_root: Path) -> None:
    """读不到预算 = 证明不了不等式 = 失败态（Lead 裁决：不许默默放行）。"""

    home = make_home(tmp_root)
    profile = wired_profile(home)
    (profile / ".policy" / "dsh-adapter.yaml").unlink()

    report = probe(home)

    channel = report.channels[0]
    assert channel.status is ChannelStatus.TIMEOUT_BUDGET_UNKNOWN
    assert channel.ok is False
    assert report.result == "fail"
    assert "证明不了" in channel.detail
    assert channel.timeout_budget["input_error"] is not None
    # 留痕事实仍然要读得到（状态只说明"先卡在哪"）。
    assert channel.audit_records == 1


def test_unparsable_adapter_config_makes_the_budget_unprovable(tmp_root: Path) -> None:
    home = make_home(tmp_root)
    profile = wired_profile(home)
    _write(profile / ".policy" / "dsh-adapter.yaml", "{not yaml")

    assert status_of(home) is ChannelStatus.TIMEOUT_BUDGET_UNKNOWN


def test_invalid_timeout_ms_in_adapter_config_is_unprovable(tmp_root: Path) -> None:
    """timeout_ms: 0 是运行期 load_config 会拒绝的值：Hook 起不来，清点也不能算通过。"""

    home = make_home(tmp_root)
    profile = wired_profile(home)
    _write(profile / ".policy" / "dsh-adapter.yaml", "project: demo\ntimeout_ms: 0\n")

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.TIMEOUT_BUDGET_UNKNOWN
    assert "timeout_ms 非法" in report.channels[0].detail


def test_adapter_config_without_timeout_ms_uses_the_runtime_default(tmp_root: Path) -> None:
    """缺省不是"读不到"：运行期 load_config 有默认值 5000ms，清点必须用同一个数。"""

    home = make_home(tmp_root)
    profile = wired_profile(home)
    _write(
        profile / ".policy" / "dsh-adapter.yaml",
        "project: demo\naudit_log: .policy/audit.jsonl\n",
    )

    report = probe(home)

    channel = report.channels[0]
    assert channel.status is ChannelStatus.WIRED
    assert channel.timeout_budget["internal_budget_ms"] == DEFAULT_INTERNAL_BUDGET_MS
    assert channel.timeout_budget["internal_budget_source"] == "runtime-default"


def test_command_without_config_flag_is_not_wired(tmp_root: Path) -> None:
    """没有 --config，Hook 进程根本起不来：这不是"预算读不到"，是接线不成立。"""

    home = make_home(tmp_root)
    command = (
        "python -m adapters.dsh.hooks --hooks-config .policy/hooks.json "
        "--audit .policy/audit.jsonl"
    )
    profile = make_profile(home, "desktop")
    _write(profile / "cordis.patch.yml", in_process_patch(profile, command=command))
    _write(profile / ".policy" / "hooks.json", json.dumps(policy_hooks(command)))
    _write(profile / ".policy" / "audit.jsonl", audit_line("2026-09-25T11:59:00Z"))

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.NOT_WIRED
    assert "--config" in report.channels[0].detail


def test_plugin_default_timeout_is_used_when_timeout_ms_is_absent(tmp_root: Path) -> None:
    """没写 timeoutMs 不是"读不到"：插件自己有 DEFAULT_TIMEOUT_MS（由下面那条用例盯着）。"""

    home = make_home(tmp_root)
    profile = make_profile(home, "desktop")
    _write(profile / "cordis.patch.yml", in_process_patch(profile, dsh_timeout_ms=None))
    _write(profile / ".policy" / "hooks.json", json.dumps(policy_hooks()))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(profile / ".policy" / "audit.jsonl", audit_line("2026-09-25T11:59:00Z"))

    report = probe(home)

    channel = report.channels[0]
    assert channel.status is ChannelStatus.WIRED
    assert channel.timeout_budget["in_process_timeout_ms"] == IN_PROCESS_DEFAULT_TIMEOUT_MS
    assert channel.timeout_budget["dsh_side_timeout_source"] == "plugin-default"


def test_invalid_timeout_ms_declaration_is_not_wired(tmp_root: Path) -> None:
    """timeoutMs: 0 会让插件在装配时抛错：该通道起不来，不能算 wired。"""

    home = make_home(tmp_root)
    profile = wired_profile(home)
    _write(profile / "cordis.patch.yml", in_process_patch(profile, dsh_timeout_ms=0))

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.NOT_WIRED
    assert "timeoutMs 非法" in report.channels[0].detail


def test_dialect_bridge_without_any_declared_timeout_is_unprovable(tmp_root: Path) -> None:
    """方言桥既没声明 defaultTimeoutMs、hooks 里也没写 timeout：不等式证明不了 -> 失败。"""

    home = make_home(tmp_root)
    profile = make_profile(home, "web")
    _write(profile / "cordis.patch.yml", dialect_patch(profile))
    _write(profile / ".policy" / "hooks.json", json.dumps(policy_hooks(timeout=None)))
    _write(profile / ".policy" / "dsh-adapter.yaml", ADAPTER_CONFIG)
    _write(profile / ".policy" / "audit.jsonl", audit_line("2026-09-25T11:59:00Z"))

    report = probe(home)

    assert report.channels[0].status is ChannelStatus.TIMEOUT_BUDGET_UNKNOWN
    assert report.channels[0].timeout_budget["dsh_side_timeout_ms"] is None


def test_internal_budget_default_matches_the_runtime_loader(tmp_root: Path) -> None:
    """DEFAULT_INTERNAL_BUDGET_MS 必须是运行期 load_config 的真实缺省值，不是我们自己定的。"""

    from adapters.dsh.adapter import load_config

    project = tmp_root / "demo"
    project.mkdir()
    document = write_dsh_config(
        tmp_root / "cfg" / "dsh-adapter.yaml", project_root=project, rules=POLICIES_DIR
    )
    kept = [
        line
        for line in document.read_text(encoding="utf-8").splitlines()
        if not line.startswith("timeout_ms:")
    ]
    _write(document, "\n".join(kept) + "\n")

    assert load_config(document).timeout_ms == DEFAULT_INTERNAL_BUDGET_MS


def test_in_process_default_timeout_matches_the_plugin_source() -> None:
    """插件的 DEFAULT_TIMEOUT_MS 是 dsh 侧超时的缺省值：改一边不改另一边必须变红。"""

    plugin = (REPO_ROOT / "src" / "adapters" / "dsh" / "policy-hook.plugin.mjs").read_text(
        encoding="utf-8"
    )
    match = re.search(r"const DEFAULT_TIMEOUT_MS = (\d+);", plugin)

    assert match is not None, "插件源码里找不到 DEFAULT_TIMEOUT_MS"
    assert int(match.group(1)) == IN_PROCESS_DEFAULT_TIMEOUT_MS
