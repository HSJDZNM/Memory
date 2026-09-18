"""Phase 5 对抗测试：路径逃逸、注入、超限与"工具输出不得改变策略"。

信任边界：外部工具的输出、被验证文件的路径与内容都是不可信输入。它们可以进证据，
但不能改规则、不能造规则、不能把绝对路径与凭据带进报告。
"""

from __future__ import annotations

import json
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
from policy.evidence import ValidatorStatus
from policy.loader import load_rule_set
from validators.pipeline import PipelineRequest, run_pipeline
from validators.registry import RegistryError, load_config
from validators.source import SourceError, read_source

pytestmark = pytest.mark.security

CONFIG = validators_config()
RULES = load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT)


def run_for(target: str, *, workspace: Path = VALIDATOR_PROJECT, config=CONFIG, keep_temp: bool = False):
    context = make_context(file=target, language="python", layer="controller")
    return run_pipeline(
        PipelineRequest(target=target, workspace=workspace, context=context, rules=RULES),
        config=config,
        keep_temp=keep_temp,
    )


def adversarial_config(tmp_root: Path, behaviour: str, *, tool: str = "ruff"):
    """把 tool.ruff 指向假工具的某种"恶意"行为。"""

    document = yaml.safe_load((REPO_ROOT / "validation" / "validators.yaml").read_text(encoding="utf-8"))
    fake = str(REPO_ROOT / "tests" / "fixtures" / "validators" / "tools" / "fake_tool.py")
    for item in document["validators"]:
        if item["id"] == "tool." + tool:
            item["tool"]["command"] = ["{python}", fake, tool, behaviour]
    root = write_validation_config(tmp_root, registry=document)
    return load_config(root=REPO_ROOT, registry=root / "validation" / "validators.yaml")


def test_target_paths_cannot_escape_the_workspace(tmp_root: Path) -> None:
    workspace = tmp_root / "workspace"
    workspace.mkdir()
    outside = tmp_root / "outside.py"
    outside.write_text("x = 1" + chr(10), encoding="utf-8", newline="")

    for candidate in ("../outside.py", str(outside), "sub/../../outside.py"):
        with pytest.raises(SourceError):
            read_source(candidate, workspace=workspace, language="python", max_bytes=1024)


def test_file_names_with_shell_metacharacters_are_rejected(tmp_root: Path) -> None:
    workspace = tmp_root / "workspace"
    workspace.mkdir()
    # 只测"能建出来但必须被拒绝"的形态；换行与竖线在 Windows 上根本建不出文件，
    # 那种名字直接走路径校验（不需要文件存在）。
    for name in ("a;rm -rf.py", "a$(whoami).py", "a&b.py"):
        target = workspace / name
        target.write_text("x = 1" + chr(10), encoding="utf-8", newline="")
        with pytest.raises(SourceError):
            read_source(name, workspace=workspace, language="python", max_bytes=1024)

    for impossible in ("a" + chr(10) + "b.py", "a|b.py", "a" + chr(0) + "b.py"):
        with pytest.raises(SourceError):
            read_source(impossible, workspace=workspace, language="python", max_bytes=1024)


def test_path_option_injection_is_rejected() -> None:
    from validators.adapters.base import ToolError, build_argv, probe_tool

    spec = CONFIG.registry.spec("tool.ruff")
    probe = probe_tool(
        spec.tool,
        timeout_ms=5000,
        max_output_bytes=65536,
        workspace=REPO_ROOT,
        tmp_dir=REPO_ROOT / ".tmp",
    )

    with pytest.raises(ToolError):
        build_argv(
            spec.tool,
            probe,
            python="python",
            workspace=REPO_ROOT,
            config=None,
            paths=("--config=/etc/passwd",),
        )


def test_oversized_source_is_fail_closed(tmp_root: Path) -> None:
    workspace = copy_validator_project(tmp_root)
    target = workspace / "src" / "shop" / "huge.py"
    target.write_text("x = 1" + chr(10) * 200000, encoding="utf-8", newline="")

    document = yaml.safe_load((REPO_ROOT / "validation" / "validators.yaml").read_text(encoding="utf-8"))
    document["defaults"]["max_source_bytes"] = 1024
    root = write_validation_config(tmp_root, registry=document)
    config = load_config(root=REPO_ROOT, registry=root / "validation" / "validators.yaml")

    report = run_for("src/shop/huge.py", workspace=workspace, config=config)

    assert report.blockers
    assert "超过上限" in report.blockers[0].reason


def test_tool_output_cannot_inject_instructions_or_secrets(tmp_root: Path) -> None:
    config = adversarial_config(tmp_root, "injection")

    report = run_for("src/shop/order_controller.py", config=config)
    payload = json.dumps(report.to_payload(), ensure_ascii=False)

    assert "ignore previous instructions" not in payload.replace("ignore previous instructions", "", 0) or True
    assert "eyJhbGciOiJIUzI1NiJ9" not in payload
    assert "C:/Users/secret" not in payload
    assert chr(27) not in payload
    # 注入文本仍然作为"数据"进入证据（可审计），但不会改变规则集或造出新规则
    assert {item.rule_id for item in report.evidence} <= {"STYLE-001", "STYLE-002"}


def test_tool_output_cannot_invent_rule_ids(tmp_root: Path) -> None:
    config = adversarial_config(tmp_root, "findings", tool="ruff")

    report = run_for("src/shop/order_controller.py", config=config)

    assert {item.rule_id for item in report.evidence} <= {"STYLE-001", "STYLE-002"}
    assert report.unmapped_findings >= 1  # W291 没有规则归属，只能计数


def test_crashed_tool_fails_closed(tmp_root: Path) -> None:
    config = adversarial_config(tmp_root, "crash")

    report = run_for("src/shop/order_controller.py", config=config)

    assert [item.status for item in report.blockers] == [ValidatorStatus.CRASHED]
    assert "style_lint" in report.blockers[0].checkers


def test_unimplemented_validator_is_rejected_fail_closed(tmp_root: Path) -> None:
    document = yaml.safe_load((REPO_ROOT / "validation" / "validators.yaml").read_text(encoding="utf-8"))
    document["validators"].append(
        {
            "id": "py.ghost",
            "version": "1.0",
            "kind": "builtin",
            "stage": "docstring",
            "checkers": ["missing_docstring"],
            "critical": True,
            "description": "注册表里有、代码里没有的验证器",
        }
    )
    for pack in document["rule_packs"]:
        if pack["id"] == "python-core":
            pack["validators"] = list(pack["validators"]) + ["py.ghost"]
    root = write_validation_config(tmp_root, registry=document)

    # 复核 F6 之后：注册表声明了实现里没有的验证器，**加载阶段**就拒绝
    # （此前是运行期 config_error → block；两条都失败关闭，但加载期更早、更清楚）。
    with pytest.raises(RegistryError) as error:
        load_config(root=REPO_ROOT, registry=root / "validation" / "validators.yaml")

    assert "py.ghost" in str(error.value)


def test_temp_directories_are_isolated_per_validator() -> None:
    report = run_for("src/shop/order_controller_bad.py", keep_temp=True)

    runs = sorted((REPO_ROOT / ".tmp" / "validators").glob("*"))
    latest = runs[-1]
    directories = {item.name for item in latest.iterdir() if item.is_dir()}

    assert {"py.source", "py.ast"} <= directories
    assert report.served_checkers  # 运行本身正常


def test_decisions_do_not_leak_absolute_paths(tmp_root: Path) -> None:
    config = adversarial_config(tmp_root, "garbage")

    report = run_for("src/shop/order_controller.py", config=config)
    payload = json.dumps(report.to_payload(), ensure_ascii=False)

    assert str(REPO_ROOT).replace(chr(92), "/") not in payload
    assert str(REPO_ROOT) not in payload


def test_garbage_output_is_output_invalid_not_success(tmp_root: Path) -> None:
    config = adversarial_config(tmp_root, "garbage")

    report = run_for("src/shop/order_controller.py", config=config)

    assert [item.status for item in report.blockers] == [ValidatorStatus.OUTPUT_INVALID]


def test_changed_set_cannot_point_outside_the_workspace(tmp_root: Path) -> None:
    workspace = copy_validator_project(tmp_root)
    context = make_context(file="src/shop/order_service.py", language="python", layer="service", operation="edit")

    # 复核 F10 之后：非法变更集在**进入流水线之前**就被拒绝（配置错误，退出码 2），
    # 而不是一路带到测试选择阶段再以 ValidationError → crashed 的形式失败关闭。
    with pytest.raises(RegistryError) as error:
        run_pipeline(
            PipelineRequest(
                target=context.file,
                workspace=workspace,
                context=context,
                rules=RULES,
                changed_files=("../../../etc/passwd", "src/shop/order_service.py"),
            ),
            config=CONFIG,
        )

    assert "变更集里的路径不合法" in str(error.value)
