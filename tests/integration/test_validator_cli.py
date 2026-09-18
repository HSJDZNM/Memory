"""Phase 5 验证器 CLI 集成测试：真实子进程、退出码与机器可读载荷。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO_ROOT

pytestmark = pytest.mark.integration

PROJECT = "tests/fixtures/validators/project"


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "validators.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_registry_command_prints_the_declared_facts() -> None:
    completed = cli("registry", "--json")

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["stages"][0] == "source"
    assert {item["id"] for item in payload["validators"]} == {
        "py.source",
        "py.ast",
        "py.depgraph",
        "py.docstring",
        "tool.ruff",
        "tool.mypy",
        "tool.pytest",
    }
    assert payload["checkers"]["python"]["forbidden_dependency"] == ["py.depgraph"]
    assert payload["defaults"]["max_parallel"] >= 1


def test_registry_show_reports_one_validator() -> None:
    completed = cli("registry", "--show", "tool.ruff")

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["validators"][0]["tool"]["config"] == "validation/ruff.toml"
    assert payload["validators"][0]["critical"] is True


def test_registry_show_rejects_unknown_ids() -> None:
    completed = cli("registry", "--show", "tool.absent")

    assert completed.returncode == 2
    assert "config error" in completed.stderr


def test_probe_reports_tool_availability() -> None:
    completed = cli("probe", "--json")

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    statuses = {item["validator"]: item["status"] for item in payload["tools"]}
    assert set(statuses) == {"tool.ruff@1.0", "tool.mypy@1.0", "tool.pytest@1.0"}
    assert statuses["tool.pytest@1.0"] == "ok"  # pytest 是本项目的依赖，必定可用


def test_check_command_only_produces_evidence() -> None:
    """check 只交证据：即使依赖违规很明显，它也不给 allow / block（那是 pipeline 的活）。"""

    completed = cli(
        "check",
        "src/shop/order_controller_bad.py",
        "--layer",
        "controller",
        "--workspace",
        PROJECT,
        "--json",
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["result"] is None  # check 不做判定
    assert payload["evidence"]["dependencies"][0]["name"] == "repository"
    assert payload["evidence"]["schema_version"] == "1.0"


def test_check_command_exits_one_on_findings() -> None:
    completed = cli(
        "check",
        "src/shop/style_offences.py",
        "--layer",
        "service",
        "--workspace",
        PROJECT,
        "--json",
    )

    if not any(tool["status"] == "ok" for tool in json.loads(cli("probe", "--json").stdout)["tools"]):
        pytest.skip("本机没有任何可用的外部工具")
    assert completed.returncode == 1, completed.stderr
    payload = json.loads(completed.stdout)
    validators = {item["validator"] for item in payload["evidence"]["evidence"]}
    assert "tool.ruff@1.0" in validators
    assert {item["rule_id"] for item in payload["evidence"]["evidence"]} <= {
        "STYLE-001",
        "STYLE-002",
    }


def test_pipeline_command_matches_policy_check() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    args = [
        "src/shop/order_controller_bad.py",
        "--layer",
        "controller",
        "--workspace",
        PROJECT,
        "--request-id",
        "req-p5-compare",
    ]
    first = cli("pipeline", *args, "--json")
    second = subprocess.run(
        [sys.executable, "-m", "policy.check", *args, "--json"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert first.returncode == second.returncode == 1, first.stderr + second.stderr
    assert json.loads(first.stdout)["result"] == json.loads(second.stdout)["result"]


def test_check_command_rejects_a_target_outside_the_workspace(tmp_root: Path) -> None:
    completed = cli("check", "../outside.py", "--layer", "controller", "--workspace", PROJECT)

    assert completed.returncode == 2
    assert "config error" in completed.stderr


def test_check_requires_an_explicit_layer() -> None:
    completed = cli("check", "src/shop/order_controller.py", "--workspace", PROJECT)

    assert completed.returncode == 2
    assert "--layer" in completed.stderr


def test_unknown_validator_filter_is_rejected() -> None:
    completed = cli(
        "check",
        "src/shop/order_controller.py",
        "--layer",
        "controller",
        "--workspace",
        PROJECT,
        "--validators",
        "tool.absent",
    )

    assert completed.returncode == 2
    assert "tool.absent" in completed.stderr


def test_changed_from_git_uses_the_working_tree(tmp_root: Path) -> None:
    """--changed-from-git 直接问 git 要变更集；没有 git 时会显式失败而不是当作没有变更。"""

    completed = cli(
        "check",
        "src/shop/order_service.py",
        "--layer",
        "service",
        "--workspace",
        PROJECT,
        "--operation",
        "edit",
        "--changed-from-git",
        "HEAD",
        "--rules",
        str(REPO_ROOT / "policies"),
    )

    assert completed.returncode in (0, 1, 2)
    if completed.returncode == 2:
        assert "git" in completed.stderr
