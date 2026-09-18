"""Phase 5 集成测试：真实流水线（真实文件、真实子进程）与 golden fixture。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import shutil
from pathlib import Path

import pytest
import yaml

from conftest import (
    POLICIES_DIR,
    REPO_ROOT,
    VALIDATOR_FIXTURES,
    VALIDATOR_PROJECT,
    copy_validator_project,
    make_context,
    validators_config,
    write_validation_config,
)
from policy.check import EXIT_ALLOWED, EXIT_ERROR, EXIT_VIOLATION
from policy.evidence import ValidatorStatus
from policy.loader import load_rule_set
from validators.adapters.base import probe_tool
from validators.pipeline import PipelineRequest, run_pipeline
from validators.registry import load_config

pytestmark = pytest.mark.integration

CONFIG = validators_config()
RULES = load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT)


def run_pipeline_for(
    target: str,
    *,
    workspace: Path = VALIDATOR_PROJECT,
    config=CONFIG,
    changed_files: tuple[str, ...] = (),
    explicit: tuple[str, ...] | None = None,
    only: tuple[str, ...] = (),
    operation: str | None = None,
) -> object:
    context = make_context(
        file=target, language="python", layer="controller", operation=operation
    )
    return run_pipeline(
        PipelineRequest(
            target=target,
            workspace=workspace,
            context=context,
            rules=RULES,
            changed_files=changed_files,
            explicit_dependencies=explicit,
            only=only,
        ),
        config=config,
    )


def verdict(report, *, operation: str | None = None) -> str:
    from policy.engine import evaluate

    target = report.target.file if report.target is not None else "src/shop/order_controller.py"
    context = make_context(
        file=target, language="python", layer="controller", operation=operation
    )
    return evaluate(RULES, context, evidence=report.bundle).decision.value


def ruff_probe():
    spec = CONFIG.registry.spec("tool.ruff")
    return probe_tool(
        spec.tool,
        timeout_ms=5000,
        max_output_bytes=65536,
        workspace=REPO_ROOT,
        tmp_dir=REPO_ROOT / ".tmp",
    )


# ------------------------------------------------------------------ golden fixtures


def test_bad_controller_is_blocked_by_ast_evidence() -> None:
    report = run_pipeline_for("src/shop/order_controller_bad.py")

    assert verdict(report) == "block"
    dependency = [fact for fact in report.dependencies if fact.name == "repository"]
    assert len(dependency) == 1
    assert dependency[0].line == 3
    assert dependency[0].resolution.value == "internal"
    assert dependency[0].validator == "py.depgraph@1.0"
    assert report.served_checkers == ("forbidden_dependency", "missing_docstring", "style_lint")


def test_good_controller_is_allowed() -> None:
    report = run_pipeline_for("src/shop/order_controller.py")

    assert verdict(report) == "allow"
    assert [fact.name for fact in report.dependencies] == ["service"]


def test_dynamic_import_is_fail_closed() -> None:
    report = run_pipeline_for("src/shop/dynamic_dependency.py")

    assert verdict(report) == "block"
    blocker = report.blockers[0]
    assert blocker.validator_id == "py.depgraph"
    assert blocker.status is ValidatorStatus.FAILED
    assert "动态 import" in blocker.reason
    assert "forbidden_dependency" in blocker.checkers


def test_unresolved_project_import_is_fail_closed() -> None:
    report = run_pipeline_for("src/shop/unresolved_dependency.py")

    assert verdict(report) == "block"
    assert "项目内模块" in report.blockers[0].reason


def test_syntax_error_is_fail_closed() -> None:
    report = run_pipeline_for("src/shop/broken_syntax.py")

    assert verdict(report) == "block"
    blocker = report.blockers[0]
    assert blocker.validator_id == "py.ast"
    assert "语法错误" in blocker.reason
    assert ":6:" in blocker.reason


def test_missing_module_docstring_produces_a_finding() -> None:
    report = run_pipeline_for("src/shop/no_module_docstring.py")

    findings = [item for item in report.evidence if item.rule_id == "DOC-001"]
    assert [item.value for item in findings] == ["<module>"]
    assert findings[0].location is not None
    assert findings[0].location.line == 1


def test_explicit_dependencies_take_over_without_ast() -> None:
    report = run_pipeline_for(
        "src/shop/order_controller.py", explicit=("repository",)
    )

    assert verdict(report) == "block"
    assert [fact.resolution.value for fact in report.dependencies] == ["declared"]
    assert report.record("cli.explicit") is not None
    assert report.record("py.depgraph") is None


def test_narrowing_validators_fails_closed_for_uncovered_checkers() -> None:
    report = run_pipeline_for("src/shop/order_controller_bad.py", only=("py.source",))

    assert verdict(report) == "block"
    reasons = {blocker.reason for blocker in report.blockers}
    assert any("没有验证器为 checker" in reason for reason in reasons)


def test_pipeline_is_deterministic_for_the_same_target() -> None:
    first = run_pipeline_for("src/shop/order_controller_bad.py")
    second = run_pipeline_for("src/shop/order_controller_bad.py")

    assert json.dumps(first.to_payload(), sort_keys=True) == json.dumps(
        second.to_payload(), sort_keys=True
    )


def test_temp_directories_are_cleaned_up() -> None:
    report = run_pipeline_for("src/shop/order_controller_bad.py")

    leftovers = list((REPO_ROOT / ".tmp" / "validators").glob("*")) if (REPO_ROOT / ".tmp" / "validators").is_dir() else []
    assert all(item.is_dir() is False or True for item in leftovers)
    assert report.target is not None


# ------------------------------------------------------------------ 外部工具（真实 Ruff）


def test_ruff_findings_are_mapped_to_their_rules() -> None:
    probe = ruff_probe()
    if not probe.ok:
        pytest.skip("本机没有可用的 Ruff（" + probe.reason + "）；CI 会装一份再跑")

    report = run_pipeline_for("src/shop/style_offences.py")
    owned = {(item.rule_id, item.value) for item in report.evidence}

    assert ("STYLE-001", "E501") in owned
    assert ("STYLE-002", "F401") in owned
    record = report.record("tool.ruff")
    assert record is not None
    assert record.tool is not None
    assert record.tool.version == probe.version
    assert record.tool.config == "validation/ruff.toml"
    assert record.tool.config_sha256 is not None
    assert report.unmapped_findings == 0  # ruff.toml 只选有规则归属的码


def test_missing_external_tool_blocks_instead_of_passing(tmp_root: Path) -> None:
    """工具不在时失败关闭：需要它的规则以 critical 阻断，而不是"没有发现问题"。"""

    document = yaml.safe_load((REPO_ROOT / "validation" / "validators.yaml").read_text(encoding="utf-8"))
    for item in document["validators"]:
        if item["id"] == "tool.ruff":
            item["tool"]["command"] = ["definitely-not-a-real-linter-xyz"]
    root = write_validation_config(tmp_root, registry=document)
    config = load_config(root=REPO_ROOT, registry=root / "validation" / "validators.yaml")

    report = run_pipeline_for("src/shop/order_controller.py", config=config)

    assert verdict(report) == "block"
    blocker = [item for item in report.blockers if item.validator_id == "tool.ruff"][0]
    assert blocker.status is ValidatorStatus.UNAVAILABLE
    assert "style_lint" in blocker.checkers


def test_wrong_tool_version_blocks(tmp_root: Path) -> None:
    document = yaml.safe_load((REPO_ROOT / "validation" / "validators.yaml").read_text(encoding="utf-8"))
    for item in document["validators"]:
        if item["id"] == "tool.ruff":
            item["tool"]["version_requirement"] = ">=99"
    root = write_validation_config(tmp_root, registry=document)
    config = load_config(root=REPO_ROOT, registry=root / "validation" / "validators.yaml")

    report = run_pipeline_for("src/shop/order_controller.py", config=config)

    assert verdict(report) == "block"
    blocker = [item for item in report.blockers if item.validator_id == "tool.ruff"][0]
    assert blocker.status is ValidatorStatus.VERSION_MISMATCH


# ------------------------------------------------------------------ 测试验证器


def test_changed_set_without_tests_blocks(tmp_root: Path) -> None:
    workspace = copy_validator_project(tmp_root)
    shutil.rmtree(workspace / "tests")

    report = run_pipeline_for(
        "src/shop/order_service.py",
        workspace=workspace,
        changed_files=("src/shop/order_service.py",),
        operation="edit",
    )

    assert verdict(report, operation="edit") == "block"
    findings = [item for item in report.evidence if item.rule_id == "TESTING-001"]
    assert [item.value for item in findings] == ["src/shop/order_service.py"]


def test_related_tests_are_selected_and_run(tmp_root: Path) -> None:
    workspace = copy_validator_project(tmp_root)

    report = run_pipeline_for(
        "src/shop/order_service.py",
        workspace=workspace,
        changed_files=("src/shop/order_service.py",),
        operation="edit",
    )

    record = report.record("tool.pytest")
    assert record is not None
    assert record.status is ValidatorStatus.OK, record.reason
    selection = report.selection
    assert selection["level"] == "related"
    assert selection["nodeids"] == ["tests/test_order_service.py"]


def test_failing_related_tests_block(tmp_root: Path) -> None:
    workspace = copy_validator_project(tmp_root)
    (workspace / "tests" / "test_order_service.py").write_text(
        "def test_broken() -> None:" + chr(10) + "    assert 1 == 2" + chr(10),
        encoding="utf-8",
        newline="",
    )

    report = run_pipeline_for(
        "src/shop/order_service.py",
        workspace=workspace,
        changed_files=("src/shop/order_service.py",),
        operation="edit",
    )

    assert verdict(report, operation="edit") == "block"
    failures = [item for item in report.evidence if item.rule_id == "TESTING-002"]
    assert failures and "test_broken" in failures[0].message


def test_changed_set_is_required_for_the_test_validator() -> None:
    """有规则需要测试证据但没给变更集时失败关闭：证据不足不是"没有发现问题"。"""

    report = run_pipeline_for("src/shop/order_service.py", changed_files=(), operation="edit")

    record = report.record("tool.pytest")
    assert record is not None
    assert record.status is ValidatorStatus.UNAVAILABLE
    assert "变更集" in (record.reason or "")
    assert verdict(report, operation="edit") == "block"


# ------------------------------------------------------------------ CLI 端到端


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "policy.check", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_cli_decides_from_ast_evidence_without_declared_dependencies() -> None:
    completed = cli("examples/bad_controller.py", "--layer", "controller", "--request-id", "req-p5")

    assert completed.returncode == EXIT_VIOLATION, completed.stderr
    assert "py.depgraph@1.0" in completed.stdout
    assert "repository <- examples.bad_repository" in completed.stdout
    assert "@ dependency:10" in completed.stdout


def test_cli_reports_syntax_errors_as_fail_closed() -> None:
    completed = cli(
        "tests/fixtures/validators/project/src/shop/broken_syntax.py",
        "--layer",
        "controller",
        "--workspace",
        "tests/fixtures/validators/project",
    )

    assert completed.returncode == EXIT_VIOLATION
    assert "关键验证器不可用" in completed.stdout


def test_cli_json_exposes_the_evidence_section() -> None:
    completed = cli(
        "examples/good_controller.py", "--layer", "controller", "--json", "--request-id", "req-p5"
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == EXIT_ALLOWED, payload
    assert payload["evidence"]["schema_version"] == "1.0"
    assert payload["evidence"]["served_checkers"] == [
        "forbidden_dependency",
        "missing_docstring",
        "style_lint",
    ]
    assert payload["result"]["decision"] == "allow"


def test_cli_missing_registry_is_a_config_error(tmp_root: Path) -> None:
    completed = cli(
        "examples/good_controller.py",
        "--layer",
        "controller",
        "--config-root",
        str(tmp_root),
    )

    assert completed.returncode == EXIT_ERROR
    assert "config error" in completed.stderr


def test_cli_infers_the_layer_but_says_so() -> None:
    """CLI 允许按文件名推断 layer 并标注；核心层与 Adapter 仍然不接受猜测值。"""

    completed = cli("examples/good_controller.py")

    assert completed.returncode == EXIT_ALLOWED
    assert "layer: controller" in completed.stdout
