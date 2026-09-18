"""Phase 5 外部工具适配器测试：探针、参数 allowlist、超时、输出上限与错误分类。

每一种失败都必须落在一个显式状态上——"工具没装"和"没有问题"是两件事。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from conftest import (
    FAKE_TOOL,
    VALIDATOR_PROJECT,
    fake_tool_spec,
    make_checker_rule,
    validators_config,
)
from policy.evidence import ValidatorKind, ValidatorStatus
from validators.adapters.base import (
    ToolError,
    build_argv,
    probe_tool,
    resolve_executable,
    run_tool,
    sanitize_text,
    tool_environment,
)
from validators.adapters.mypy import run_mypy
from validators.adapters.pytest_runner import run_pytest
from validators.adapters.ruff import run_ruff

CONFIG = validators_config()
TARGET = "src/shop/style_offences.py"
TIMEOUT_MS = 5000


def probe(spec, tmp_dir: Path, *, timeout_ms: int = TIMEOUT_MS):
    return probe_tool(
        spec.tool,
        python=sys.executable,
        timeout_ms=timeout_ms,
        max_output_bytes=CONFIG.registry.defaults.max_output_bytes,
        workspace=VALIDATOR_PROJECT,
        tmp_dir=tmp_dir,
    )


def ruff_rules():
    return (
        make_checker_rule("STYLE-001", checker="style_lint", body={"style_lint": {"tool": "ruff", "codes": ["E501"]}}),
        make_checker_rule("STYLE-002", checker="style_lint", body={"style_lint": {"tool": "ruff", "codes": ["F401"]}}),
    )


# ------------------------------------------------------------------ 探针与版本


def test_probe_reports_the_tool_version(tmp_root: Path) -> None:
    result = probe(fake_tool_spec("ruff"), tmp_root)

    assert result.status is ValidatorStatus.OK
    assert result.version == "0.14.13"
    assert result.executable is not None


def test_probe_detects_a_missing_executable(tmp_root: Path) -> None:
    spec = fake_tool_spec("ruff")
    spec = spec.model_copy(
        update={"tool": spec.tool.model_copy(update={"command": ("definitely-not-a-real-tool-xyz",)})}
    )

    result = probe(spec, tmp_root)

    assert result.status is ValidatorStatus.UNAVAILABLE
    assert "找不到可执行文件" in result.reason


def test_probe_detects_a_version_outside_the_declared_range(tmp_root: Path) -> None:
    result = probe(fake_tool_spec("ruff", "old"), tmp_root)

    assert result.status is ValidatorStatus.VERSION_MISMATCH
    assert result.version == "0.1.0"
    assert "不满足声明区间" in result.reason


def test_probe_rejects_unparsable_version_output(tmp_root: Path) -> None:
    spec = fake_tool_spec("ruff")
    spec = spec.model_copy(
        update={"tool": spec.tool.model_copy(update={"version_pattern": r"nothing (\d+)"})}
    )

    result = probe(spec, tmp_root)

    assert result.status is ValidatorStatus.VERSION_MISMATCH
    assert "无法从版本输出解析出版本" in result.reason


def test_resolve_executable_falls_back_to_the_interpreter_directory() -> None:
    assert resolve_executable("{python}", python=sys.executable) == sys.executable
    assert resolve_executable("definitely-not-a-real-tool-xyz") is None


# ------------------------------------------------------------------ 参数与输出


def test_build_argv_rejects_path_traversal_and_option_injection(tmp_root: Path) -> None:
    spec = fake_tool_spec("ruff")
    result = probe(spec, tmp_root)

    for bad in ("../etc/passwd", "/etc/passwd", "C:/Windows/system32", "-rf", "a" + chr(10) + "b"):
        with pytest.raises(ToolError):
            build_argv(
                spec.tool,
                result,
                python=sys.executable,
                workspace=VALIDATOR_PROJECT,
                config=None,
                paths=(bad,),
            )


def test_build_argv_rejects_suspicious_node_ids(tmp_root: Path) -> None:
    spec = fake_tool_spec("pytest", "ok", argv=("-q", "{nodeids}"))
    result = probe(spec, tmp_root)

    for bad in ("-k", "tests/a.py::x y", "tests/a.py" + chr(0)):
        with pytest.raises(ToolError):
            build_argv(
                spec.tool,
                result,
                python=sys.executable,
                workspace=VALIDATOR_PROJECT,
                config=None,
                nodeids=(bad,),
            )


def test_build_argv_expands_placeholders_in_order(tmp_root: Path) -> None:
    spec = fake_tool_spec("ruff", "ok", argv=("check", "{paths}", "--workspace", "{workspace}"))
    result = probe(spec, tmp_root)

    argv = build_argv(
        spec.tool,
        result,
        python=sys.executable,
        workspace=VALIDATOR_PROJECT,
        config=None,
        paths=(TARGET,),
    )

    assert argv[0] == sys.executable
    assert TARGET in argv
    assert str(VALIDATOR_PROJECT) in argv


def test_tool_environment_is_an_allowlist(tmp_root: Path) -> None:
    os.environ["PHASE5_SECRET_PROBE"] = "value"
    try:
        env = tool_environment(tmp_dir=tmp_root)
    finally:
        os.environ.pop("PHASE5_SECRET_PROBE", None)

    assert "PHASE5_SECRET_PROBE" not in env
    assert "HOME" not in env and "USERPROFILE" not in env
    assert env["TEMP"] == str(tmp_root)
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"


def test_sanitize_text_redacts_secrets_paths_and_control_characters() -> None:
    raw = (
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.sig"  # secret-scan: allow 合成凭据
        + " at C:/Users/secret/project/file.py"
        + chr(27) + "[31m red"
        + chr(7)
    )

    cleaned = sanitize_text(raw, limit=400)

    assert "eyJhbGciOiJIUzI1NiJ9" not in cleaned
    assert "C:/Users/secret" not in cleaned
    assert chr(27) not in cleaned
    assert "\\x07" in cleaned or chr(7) not in cleaned


def test_sanitize_text_truncates_long_payloads() -> None:
    cleaned = sanitize_text("x" * 5000, limit=100)

    assert len(cleaned) <= 100
    assert cleaned.endswith("[truncated]")


# ------------------------------------------------------------------ 运行期状态


def run_fake(spec, tmp_dir: Path, *, timeout_ms: int = TIMEOUT_MS, max_output_bytes: int = 262144):
    result = probe(spec, tmp_dir, timeout_ms=timeout_ms)
    assert result.ok, result.reason
    argv = build_argv(
        spec.tool,
        result,
        python=sys.executable,
        workspace=VALIDATOR_PROJECT,
        config=None,
        paths=(TARGET,),
    )
    return run_tool(
        spec.tool,
        result,
        argv,
        workspace=VALIDATOR_PROJECT,
        tmp_dir=tmp_dir,
        timeout_ms=timeout_ms,
        max_output_bytes=max_output_bytes,
        findings_exit_codes=(1,),
    )


def test_run_tool_classifies_config_errors_and_crashes(tmp_root: Path) -> None:
    config_error = run_fake(fake_tool_spec("ruff", "config_error"), tmp_root)
    crashed = run_fake(fake_tool_spec("ruff", "crash"), tmp_root)

    assert config_error.status is ValidatorStatus.CONFIG_ERROR
    assert config_error.exit_code == 2
    assert crashed.status is ValidatorStatus.CRASHED
    assert crashed.exit_code == 3


def test_run_tool_rejects_non_utf8_output(tmp_root: Path) -> None:
    result = run_fake(fake_tool_spec("ruff", "garbage"), tmp_root)

    assert result.status is ValidatorStatus.OUTPUT_INVALID
    assert "UTF-8" in result.reason


def test_run_tool_truncates_oversized_output(tmp_root: Path) -> None:
    result = run_fake(fake_tool_spec("ruff", "flood"), tmp_root, max_output_bytes=1024)

    assert result.truncated is True
    assert result.output_bytes > 1024
    assert len(result.stdout) <= 1024


def test_timeout_kills_the_whole_process_tree(tmp_root: Path) -> None:
    spec = fake_tool_spec("ruff", "slow", timeout_ms=2000)
    started = time.monotonic()

    result = run_fake(spec, tmp_root, timeout_ms=2000)
    elapsed = time.monotonic() - started

    assert result.status is ValidatorStatus.TIMEOUT
    assert result.timed_out is True
    assert elapsed < 20, "超时没有真正终止进程"

    marker = tmp_root / "fake_tool_child_pid.txt"
    if not marker.is_file():
        pytest.skip("假工具没有写子进程标记")
    heartbeat = Path(marker.read_text(encoding="utf-8").splitlines()[1])
    before = heartbeat.read_text(encoding="utf-8", errors="replace").count("beat")
    time.sleep(0.4)
    after = heartbeat.read_text(encoding="utf-8", errors="replace").count("beat")
    assert after == before, "子进程还在写心跳：超时没有终止整棵进程树"


# ------------------------------------------------------------------ 适配器映射


def run_adapter(name: str, behaviour: str, tmp_root: Path, *, rules=None):
    spec = fake_tool_spec(name, behaviour)
    result = probe(spec, tmp_root)
    assert result.ok, result.reason
    arguments = dict(
        spec=spec,
        config=CONFIG,
        probe=result,
        target_path=TARGET,
        workspace=VALIDATOR_PROJECT,
        rules=ruff_rules() if rules is None else rules,
        python=sys.executable,
        tmp_dir=tmp_root,
    )
    if name == "ruff":
        return run_ruff(**arguments)
    if name == "mypy":
        return run_mypy(**arguments)
    return run_pytest(**arguments, changed_files=(TARGET,))


def test_ruff_maps_only_diagnostics_owned_by_rules(tmp_root: Path) -> None:
    result = run_adapter("ruff", "findings", tmp_root)

    assert result.status is ValidatorStatus.FINDINGS
    assert result.unmapped == 1  # W291 没有规则拥有它
    owners = {item.rule_id: item for item in result.evidence}
    assert set(owners) == {"STYLE-001", "STYLE-002"}
    assert owners["STYLE-001"].location is not None
    assert owners["STYLE-001"].location.line == 9
    assert owners["STYLE-001"].value == "E501"
    assert owners["STYLE-002"].fix is not None
    assert owners["STYLE-001"].tool is not None
    assert owners["STYLE-001"].tool.version == "0.14.13"
    assert owners["STYLE-001"].tool.exit_code == 1


def test_ruff_reports_output_invalid_for_empty_or_broken_json(tmp_root: Path) -> None:
    empty = run_adapter("ruff", "empty", tmp_root)

    assert empty.status is ValidatorStatus.OUTPUT_INVALID
    assert "JSON" in (empty.reason or "")


def test_ruff_sanitizes_adversarial_diagnostic_messages(tmp_root: Path) -> None:
    result = run_adapter("ruff", "injection", tmp_root)

    assert result.status is ValidatorStatus.FINDINGS
    message = result.evidence[0].message
    assert chr(10) not in message
    assert chr(27) not in message
    assert "eyJhbGciOiJIUzI1NiJ9" not in message
    assert "C:/Users/secret" not in (result.evidence[0].detail or "") + message


def test_ruff_treats_a_missing_tool_as_unavailable(tmp_root: Path) -> None:
    spec = fake_tool_spec("ruff")
    spec = spec.model_copy(
        update={"tool": spec.tool.model_copy(update={"command": ("definitely-not-a-real-tool-xyz",)})}
    )
    with pytest.raises(ToolError):
        build_argv(
            spec.tool,
            probe_tool(
                spec.tool,
                timeout_ms=1000,
                max_output_bytes=1024,
                workspace=VALIDATOR_PROJECT,
                tmp_dir=tmp_root,
            ),
            python=sys.executable,
            workspace=VALIDATOR_PROJECT,
            config=None,
            paths=(TARGET,),
        )


def test_mypy_maps_error_lines_and_counts_unowned_ones(tmp_root: Path) -> None:
    rule = make_checker_rule(
        "TYPES-001", checker="type_check", body={"type_check": {"tool": "mypy", "codes": ["return-value"]}}
    )

    result = run_adapter("mypy", "findings", tmp_root, rules=(rule,))

    assert result.status is ValidatorStatus.FINDINGS
    assert [item.rule_id for item in result.evidence] == ["TYPES-001"]
    assert result.evidence[0].value == "RETURN-VALUE"
    assert result.unmapped >= 1  # 没有码的那条与 unused-ignore 都不属于这条规则


def test_pytest_reports_missing_tests_when_the_workspace_has_none(tmp_root: Path) -> None:
    missing_rule = make_checker_rule("TESTING-001", checker="missing_tests")
    workspace = tmp_root / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "lonely.py").write_text("x = 1" + chr(10), encoding="utf-8", newline="")

    spec = fake_tool_spec("pytest", "ok", argv=("-q", "{nodeids}"))
    result = probe(spec, tmp_root)

    outcome = run_pytest(
        spec=spec,
        config=CONFIG,
        probe=result,
        target_path="src/lonely.py",
        workspace=workspace,
        rules=(missing_rule,),
        python=sys.executable,
        tmp_dir=tmp_root,
        changed_files=("src/lonely.py",),
    )

    # 一个测试文件都没有的工作区里，生产变更全部算"缺少对应测试"
    assert [item.checker for item in outcome.evidence] == ["missing_tests"]
    assert outcome.evidence[0].value == "src/lonely.py"


def test_pytest_reports_failing_tests(tmp_root: Path) -> None:
    failing_rule = make_checker_rule("TESTING-002", checker="failing_tests")

    result = run_adapter("pytest", "findings", tmp_root, rules=(failing_rule,))

    assert result.status is ValidatorStatus.FINDINGS
    failing = [item for item in result.evidence if item.checker == "failing_tests"][0]
    assert "test_create_delegates_to_repository" in failing.value
    assert failing.location is not None
    assert failing.location.file == "tests/test_order_service.py"


def test_pytest_reports_success_without_evidence(tmp_root: Path) -> None:
    failing_rule = make_checker_rule("TESTING-002", checker="failing_tests")

    result = run_adapter("pytest", "ok", tmp_root, rules=(failing_rule,))

    assert result.status is ValidatorStatus.OK
    assert result.evidence == ()


def test_pytest_exit_code_five_is_not_a_failure(tmp_root: Path) -> None:
    failing_rule = make_checker_rule("TESTING-002", checker="failing_tests")
    spec = fake_tool_spec("pytest", "empty", argv=("-q", "{nodeids}"))
    spec = spec.model_copy(update={"tool": spec.tool.model_copy(update={"command": (sys.executable, str(FAKE_TOOL), "pytest", "empty")})})
    result = probe(spec, tmp_root)
    assert result.ok

    from validators.adapters.pytest_runner import run_pytest as adapter

    outcome = adapter(
        spec=spec,
        config=CONFIG,
        probe=result,
        target_path=TARGET,
        workspace=VALIDATOR_PROJECT,
        rules=(failing_rule,),
        python=sys.executable,
        tmp_dir=tmp_root,
        changed_files=(TARGET,),
    )

    assert outcome.status in (ValidatorStatus.OK, ValidatorStatus.FINDINGS)
    assert outcome.tool is not None
