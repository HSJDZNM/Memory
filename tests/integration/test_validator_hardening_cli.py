"""Phase 5 复核回归（集成层）：真实 CLI 与真实夹具项目上的修复验证。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from conftest import (
    POLICIES_DIR,
    REPO_ROOT,
    VALIDATOR_PROJECT,
    copy_validator_project,
    make_context,
    validators_config,
    write_validation_config,
)
from policy.check import EXIT_ALLOWED, EXIT_ERROR, EXIT_VIOLATION
from policy.loader import load_rule_set
from validators.pipeline import PipelineRequest, run_pipeline
from validators.registry import load_config

pytestmark = pytest.mark.integration

CONFIG = validators_config()
RULES = load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT)


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


def run_for(target: str, *, workspace: Path = VALIDATOR_PROJECT, config=CONFIG, operation=None,
            changed=()):
    context = make_context(
        file=target, language="python", layer="controller", operation=operation
    )
    return run_pipeline(
        PipelineRequest(
            target=target,
            workspace=workspace,
            context=context,
            rules=RULES,
            changed_files=tuple(changed),
        ),
        config=config,
    )


def verdict(report) -> str:
    from policy.engine import evaluate

    target = report.target.file if report.target is not None else "src/shop/order_controller_bad.py"
    return evaluate(
        RULES, make_context(file=target, language="python", layer="controller"), evidence=report.bundle
    ).decision.value


# ---------------------------------------------------------------- F2：from pkg import submodule


def test_submodule_import_fixture_is_blocked() -> None:
    """from shop import order_repository 是常见的依赖写法，不能漏判。"""

    report = run_for("src/shop/submodule_controller_bad.py")

    assert verdict(report) == "block"
    edge = [fact for fact in report.dependencies if fact.name == "repository"]
    assert edge and edge[0].module == "shop.order_repository"


# ---------------------------------------------------------------- F8：未知语言失败关闭


def test_unknown_language_is_a_config_error() -> None:
    completed = cli("examples/bad_controller.py", "--layer", "controller", "--language", "go")

    assert completed.returncode == EXIT_ERROR
    assert "rule pack" in completed.stderr
    assert completed.stdout == ""


def test_declared_language_still_works() -> None:
    completed = cli("examples/good_controller.py", "--layer", "controller", "--language", "python")

    assert completed.returncode == EXIT_ALLOWED, completed.stderr


# ---------------------------------------------------------------- F3：别名动态 import


def test_aliased_dynamic_import_fixture_is_blocked(tmp_root: Path) -> None:
    workspace = copy_validator_project(tmp_root)
    (workspace / "src" / "shop" / "alias_dynamic.py").write_text(
        '"""动态 import 的别名形式。"""' + chr(10) + chr(10)
        + "from importlib import import_module as im" + chr(10) + chr(10)
        + "def load(name: str) -> object:" + chr(10) + '    """按名字加载。"""' + chr(10)
        + "    return im(name)" + chr(10),
        encoding="utf-8",
        newline="",
    )

    report = run_for("src/shop/alias_dynamic.py", workspace=workspace)

    assert verdict(report) == "block"
    assert any("动态 import" in blocker.reason for blocker in report.blockers)


# ---------------------------------------------------------------- F10：变更集校验


def test_invalid_changed_path_is_a_config_error() -> None:
    completed = cli(
        "src/shop/order_service.py",
        "--layer",
        "service",
        "--workspace",
        "tests/fixtures/validators/project",
        "--operation",
        "edit",
        "--changed",
        "src/../../outside.py",
    )

    assert completed.returncode == EXIT_ERROR
    assert "变更集里的路径不合法" in completed.stderr


# ---------------------------------------------------------------- F5：证据条数上限要被执行


def test_evidence_cap_is_enforced_and_recorded(tmp_root: Path) -> None:
    document = yaml.safe_load(
        (REPO_ROOT / "validation" / "validators.yaml").read_text(encoding="utf-8")
    )
    document["defaults"]["max_evidence"] = 1
    root = write_validation_config(tmp_root, registry=document)
    config = load_config(root=REPO_ROOT, registry=root / "validation" / "validators.yaml")

    report = run_for("src/shop/style_offences.py", config=config)

    record = report.record("tool.ruff")
    if record is None or record.status.value != "findings":
        pytest.skip("本机没有可用的 Ruff；上限逻辑由 test_validator_pipeline 的假工具用例覆盖")
    assert report.truncated_evidence >= 1
    assert "已截断" in (record.reason or "")
    assert len([item for item in report.evidence if item.validator_id == "tool.ruff"]) == 1


# ---------------------------------------------------------------- F4：缺测试在真实夹具上报出来


def test_production_change_without_related_test_blocks() -> None:
    report = run_for(
        "src/shop/order_repository.py",
        operation="edit",
        changed=("src/shop/order_repository.py",),
    )
    from policy.engine import evaluate

    context = make_context(
        file="src/shop/order_repository.py",
        language="python",
        layer="repository",
        operation="edit",
    )
    result = evaluate(RULES, context, evidence=report.bundle)

    assert result.decision.value == "block"
    assert "TESTING-001" in {item.rule_id for item in result.violations}
    assert report.selection.get("missing") == ["src/shop/order_repository.py"]


# ---------------------------------------------------------------- B-F3：layer 推断要标明


def test_inferred_layer_is_marked_in_text_output() -> None:
    completed = cli("examples/good_controller.py")

    assert completed.returncode == EXIT_ALLOWED, completed.stderr
    assert "由文件名推断" in completed.stdout


def test_explicit_layer_is_not_marked_as_inferred() -> None:
    completed = cli("examples/good_controller.py", "--layer", "controller")

    assert completed.returncode == EXIT_ALLOWED
    assert "由文件名推断" not in completed.stdout
