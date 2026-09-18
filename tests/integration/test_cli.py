"""Phase 0 CLI 集成测试：真实子进程、输出内容、退出码与可重放性。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from policy.check import (
    EXIT_ALLOWED,
    EXIT_ERROR,
    EXIT_VIOLATION,
    default_rule_dirs,
    exit_code_for,
    infer_layer,
    parse_dependencies,
    python_imports,
    run,
)
from policy.loader import load_rule_set
from policy.models import (
    SCHEMA_VERSION,
    Decision,
    Evidence,
    ProtocolError,
    Severity,
    ValidationResult,
    Violation,
    parse_decision,
)

from conftest import REPO_ROOT, rule_document, write_rule

pytestmark = pytest.mark.integration

BAD_EXAMPLE = "examples/bad_controller.py"
GOOD_EXAMPLE = "examples/good_controller.py"


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def workspace_path(path: Path) -> str:
    """把临时目录转换成相对仓库根目录的路径，便于子进程与错误信息断言。"""

    if path.is_relative_to(REPO_ROOT):
        return path.relative_to(REPO_ROOT).as_posix()
    return str(path)


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """在仓库根目录以子进程方式运行 python -m policy.check。"""

    return subprocess.run(
        [sys.executable, "-m", "policy.check", *args],
        cwd=REPO_ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_bad_fixture_reports_rule_and_exits_1() -> None:
    completed = run_cli(BAD_EXAMPLE, "--dependencies", "repository", "--request-id", "req-bad")

    assert completed.returncode == EXIT_VIOLATION, completed.stderr
    stdout = completed.stdout
    assert "ARCH-001" + "@" + "1" in stdout
    assert "Controller 必须通过 Service 访问 Repository。" in stdout
    assert "controller -> service -> repository" in stdout
    assert "evidence: dependency=repository" in stdout
    assert "FAIL" in stdout


def test_good_fixture_exits_0() -> None:
    completed = run_cli(GOOD_EXAMPLE, "--dependencies", "service", "--request-id", "req-good")

    assert completed.returncode == EXIT_ALLOWED, completed.stderr
    assert "PASS" in completed.stdout
    # 决策必须说清哪些规则参与了判断、哪些被跳过
    assert "matched: ARCH-001" + "@" + "1" in completed.stdout
    # Phase 5 起 TESTING-* 需要变更上下文：没有 --operation 时按范围跳过并写明原因
    assert "TESTING-001" + "@" + "1: operation <missing> != [create, edit]" in completed.stdout


def test_scope_mismatch_is_reported_as_skip_reason() -> None:
    """layer=service 时 ARCH-001 不参与判断，CLI 要给出原因，而不是只报 PASS。"""

    completed = run_cli(GOOD_EXAMPLE, "--dependencies", "repository", "--layer", "service")

    assert completed.returncode == EXIT_ALLOWED, completed.stderr
    assert "skipped (规则范围不匹配，未参与判断):" in completed.stdout
    assert "- ARCH-001" + "@" + "1: layer service != controller" in completed.stdout
    matched_line = next(
        line for line in completed.stdout.splitlines() if line.startswith("matched: ")
    )
    assert "ARCH-001" + "@" + "1" not in matched_line, matched_line


def test_cli_is_reproducible() -> None:
    args = (BAD_EXAMPLE, "--dependencies", "repository", "--request-id", "req-fixed")

    first = run_cli(*args)
    second = run_cli(*args)

    assert first.returncode == second.returncode == EXIT_VIOLATION
    assert first.stdout == second.stdout
    assert first.stderr == second.stderr


def test_missing_rule_directory_exits_2(tmp_root: Path) -> None:
    completed = run_cli(GOOD_EXAMPLE, "--rules", workspace_path(tmp_root / "absent"))

    assert completed.returncode == EXIT_ERROR
    assert "config error" in completed.stderr
    assert "规则目录不存在" in completed.stderr
    assert completed.stdout == ""


def test_corrupted_rule_file_exits_2(tmp_root: Path) -> None:
    root = tmp_root / "policies"
    root.mkdir()
    (root / "ARCH-001.yaml").write_text("id: ARCH-001\nversion: [1, 2\n", encoding="utf-8")

    completed = run_cli(GOOD_EXAMPLE, "--rules", workspace_path(root))

    assert completed.returncode == EXIT_ERROR
    assert "ARCH-001.yaml" in completed.stderr


def test_unknown_checker_exits_2(tmp_root: Path) -> None:
    """未知 checker 在**加载阶段**就被拒绝（Phase 5 起比引擎阶段更早失败）。"""

    root = tmp_root / "policies"
    document = rule_document()
    document["enforcement"]["checker"] = "llm_judgement"
    write_rule(root / "ARCH-001.yaml", document, yaml_module=yaml)

    completed = run_cli(GOOD_EXAMPLE, "--rules", workspace_path(root))

    assert completed.returncode == EXIT_ERROR
    assert "config error" in completed.stderr
    assert "llm_judgement" in completed.stderr
    assert completed.stdout == ""


def test_missing_file_exits_2() -> None:
    completed = run_cli("examples/does_not_exist.py", "--rules", "policies")

    assert completed.returncode == EXIT_ERROR
    assert "config error" in completed.stderr


def test_directory_instead_of_file_exits_2() -> None:
    """路径不是文件时属于配置错误，不允许静默通过。"""

    completed = run_cli("examples", "--rules", "policies")

    assert completed.returncode == EXIT_ERROR
    assert "config error" in completed.stderr



def test_check_rules_mode_validates_without_file() -> None:
    completed = run_cli("--check-rules")

    assert completed.returncode == EXIT_ALLOWED, completed.stderr
    # Phase 0 的 1 条 -> Phase 5 的 6 条：ARCH-001 与各阶段的规则包都在同一份规则集里
    assert "规则集校验通过，共 6 条规则" in completed.stdout


def test_check_rules_mode_fails_on_corrupted_rules(tmp_root: Path) -> None:
    root = tmp_root / "policies"
    root.mkdir()
    (root / "ARCH-001.yaml").write_text("id: ARCH-001\nseverity: fatal\n", encoding="utf-8")

    completed = run_cli("--check-rules", "--rules", workspace_path(root))

    assert completed.returncode == EXIT_ERROR
    assert "severity" in completed.stderr


def test_json_output_matches_policy_decision_contract() -> None:
    completed = run_cli(BAD_EXAMPLE, "--dependencies", "repository", "--json", "--request-id", "req-json")

    assert completed.returncode == EXIT_VIOLATION
    payload = json.loads(completed.stdout)

    assert set(payload) == {
        "context",
        "evidence",
        "exit_code",
        "reported_imports",
        "result",
        "rule_set",
    }
    # Phase 5：--json 里带完整证据（依赖来自显式声明，因为本次传了 --dependencies）
    assert payload["evidence"]["dependencies"][0]["name"] == "repository"
    assert payload["evidence"]["dependencies"][0]["resolution"] == "declared"
    assert payload["evidence"]["served_checkers"] == [
        "forbidden_dependency",
        "missing_docstring",
        "style_lint",
    ]
    assert payload["exit_code"] == EXIT_VIOLATION
    result = payload["result"]
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["decision"] == "block"
    assert result["request_id"] == "req-json"
    assert result["trace_id"] is None
    assert result["required_action"] is None
    assert result["matched_rules"] == [
        "ARCH-001" + "@" + "1",
        "DOC-001" + "@" + "1",
        "STYLE-001" + "@" + "1",
        "STYLE-002" + "@" + "1",
    ]
    assert [item["rule_id"] for item in result["skipped_rules"]] == [
        "TESTING-001" + "@" + "1",
        "TESTING-002" + "@" + "1",
    ]
    assert result["policy_version"] == "phase-1"
    assert result["rule_set_hash"] == payload["rule_set"]["identity"]
    violation = result["violations"][0]
    assert violation["rule_id"] == "ARCH-001"
    assert violation["rule_version"] == 1
    assert violation["severity"] == "error"
    assert violation["evidence"] == {
        "kind": "dependency",
        "subject": BAD_EXAMPLE,
        "value": "repository",
        "file": BAD_EXAMPLE,
        "detail": "layer=controller 直接依赖 repository",
    }
    assert payload["rule_set"]["ids"] == [
        "ARCH-001" + "@" + "1",
        "DOC-001" + "@" + "1",
        "STYLE-001" + "@" + "1",
        "STYLE-002" + "@" + "1",
        "TESTING-001" + "@" + "1",
        "TESTING-002" + "@" + "1",
    ]
    assert payload["rule_set"]["schema_version"] == SCHEMA_VERSION
    assert payload["rule_set"]["identity"].startswith("sha256:")
    assert payload["context"]["file"] == BAD_EXAMPLE
    assert payload["context"]["layer"] == "controller"


def test_json_result_is_a_consumable_protocol_payload() -> None:
    """result 必须能被 parse_decision 原样消费，未知版本则拒绝。"""

    allowed = json.loads(run_cli(GOOD_EXAMPLE, "--dependencies", "service", "--json").stdout)
    blocked = json.loads(run_cli(BAD_EXAMPLE, "--dependencies", "repository", "--json").stdout)

    parsed_allowed = parse_decision(allowed["result"])
    parsed_blocked = parse_decision(blocked["result"])

    assert parsed_allowed.decision is Decision.ALLOW
    assert "ARCH-001" + "@" + "1" in parsed_allowed.matched_rules
    assert parsed_blocked.decision is Decision.BLOCK
    assert parsed_blocked.to_decision_dict() == blocked["result"]

    with pytest.raises(ProtocolError):
        parse_decision({**blocked["result"], "schema_version": "9.9"})


def test_trace_id_is_recorded_and_not_invented() -> None:
    without = json.loads(run_cli(BAD_EXAMPLE, "--dependencies", "repository", "--json").stdout)
    with_trace = json.loads(
        run_cli(
            BAD_EXAMPLE,
            "--dependencies",
            "repository",
            "--json",
            "--trace-id",
            "trace-456",
            "--task",
            "add order creation API",
        ).stdout
    )

    assert without["result"]["trace_id"] is None
    assert with_trace["result"]["trace_id"] == "trace-456"
    assert with_trace["context"]["task"] == "add order creation API"


def test_python_module_entry_points_agree() -> None:
    """python -m policy 与 python -m policy.check 必须给出同一条结论。"""

    env = _env()
    args = [BAD_EXAMPLE, "--dependencies", "repository", "--json", "--request-id", "req-entry"]
    first = subprocess.run(
        [sys.executable, "-m", "policy", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    second = run_cli(*args)

    assert first.returncode == second.returncode == EXIT_VIOLATION, first.stderr
    assert first.stdout == second.stdout


def test_run_function_is_reentrant(capsys: pytest.CaptureFixture[str]) -> None:
    code = run([BAD_EXAMPLE, "--dependencies", "repository", "--request-id", "req-run"])
    first = capsys.readouterr().out
    code_again = run([BAD_EXAMPLE, "--dependencies", "repository", "--request-id", "req-run"])
    second = capsys.readouterr().out

    assert code == code_again == EXIT_VIOLATION
    assert first == second


def test_default_rule_dirs_point_at_repository_policies() -> None:
    directories = default_rule_dirs(REPO_ROOT)

    assert directories == (REPO_ROOT / "policies",)
    rules = load_rule_set(directories, repo_root=REPO_ROOT)
    assert "ARCH-001" + "@" + "1" in rules.ids
    assert rules.source_paths == (
        "policies/architecture/ARCH-001.yaml",
        "policies/coding/DOC-001.yaml",
        "policies/coding/STYLE-001.yaml",
        "policies/coding/STYLE-002.yaml",
        "policies/testing/TESTING-001.yaml",
        "policies/testing/TESTING-002.yaml",
    )


def test_repository_example_dependencies_are_declared() -> None:
    """示例文件必须自带可重放的依赖声明，避免 CLI 示例与规则漂移。"""

    bad = (REPO_ROOT / BAD_EXAMPLE).read_text(encoding="utf-8")
    good = (REPO_ROOT / GOOD_EXAMPLE).read_text(encoding="utf-8")

    assert "--dependencies repository" in bad
    assert "--dependencies service" in good


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("examples/bad_controller.py", "controller"),
        ("src/order/order_service.py", "service"),
        ("src/order/order_repository.py", "repository"),
        ("src/order/models.py", "model"),
        ("src/order/registry.py", "unknown"),
        (None, "unknown"),
    ],
)
def test_infer_layer(name: str | None, expected: str) -> None:
    assert infer_layer(name) == expected


def test_parse_dependencies_is_canonical() -> None:
    assert parse_dependencies(None) == ()
    assert parse_dependencies("") == ()
    assert parse_dependencies(" Repository , service ,, ") == ("repository", "service")


def test_python_imports_reports_top_level_modules() -> None:
    source = "import os\nfrom examples import service\nfrom . import local\nimport a.b.c\n"

    assert python_imports(source) == ("a", "examples", "os")
    assert python_imports("def broken(:\n") == ()


def test_exit_code_for_maps_decision_to_code() -> None:
    violation = Violation(
        rule_id="ARCH-001",
        rule_version=1,
        severity=Severity.ERROR,
        message="Controller 必须通过 Service 访问 Repository。",
        evidence=Evidence(kind="dependency", subject="a.py", value="repository"),
    )
    blocked = ValidationResult(
        decision=Decision.BLOCK, request_id="req-1", violations=(violation,)
    )
    allowed = ValidationResult(decision=Decision.ALLOW, request_id="req-1")

    assert exit_code_for(allowed) == EXIT_ALLOWED
    assert exit_code_for(blocked) == EXIT_VIOLATION
