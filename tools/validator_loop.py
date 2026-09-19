"""Phase 5 验证器闭环：在受控工作区里重放"代码 → 证据 → 判定"。

    python tools/validator_loop.py            # 跑完整闭环，结论写到 .tmp/artifacts/
    python tools/validator_loop.py --json     # 只打印结论

它证明六件事（对应 Phase 5 的退出条件）：

1. ARCH-001 完全由 AST / 依赖图证据判定（不再需要调用方声明依赖），并给出行号；
2. 动态 import、无法解析的项目内依赖与语法错误都失败关闭，而不是"没有发现问题"；
3. 关键外部工具缺失（或版本不符）时，需要它的规则以 critical 阻断；
4. 生产变更缺少对应测试时阻断；有测试时按 related 层级选择并真的运行；
5. 相同输入两次运行得到逐字节相同的证据（可重放）；
6. 外部工具的版本与配置文件哈希可追溯。

所有产物都写在 .tmp/phase-5-demo/ 下，不触碰仓库真实文件。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DEMO_ROOT = REPO_ROOT / ".tmp" / "phase-5-demo"
FIXTURE_PROJECT = REPO_ROOT / "tests" / "fixtures" / "validators" / "project"
RESULT = REPO_ROOT / ".tmp" / "artifacts" / "phase-5-validators-result.json"

FAILING_TEST = """def test_broken() -> None:
    assert 1 == 2
"""


@dataclass
class Scenario:
    name: str
    passed: bool
    detail: str = ""
    facts: dict[str, Any] = field(default_factory=dict)
    # "通过"与"真的跑过"是两件事：工具不可用时场景仍然算 passed（否则闭环会在
    # 没装 Ruff 的机器上变红），但 verified=False 把"这条没验证到"如实写下来——
    # 以前这里写的是 passed=True + "skipped: ..."，等于把环境跳过记成通过。
    verified: bool = True


def prepare(name: str) -> Path:
    """准备一个只属于本次场景的工作区（从夹具项目复制）。"""

    workspace = DEMO_ROOT / name
    shutil.rmtree(workspace, ignore_errors=True)
    shutil.copytree(FIXTURE_PROJECT, workspace)
    return workspace


def services():
    from policy.loader import load_rule_set
    from validators.registry import load_config

    config = load_config(root=REPO_ROOT)
    rules = load_rule_set([REPO_ROOT / "policies"], repo_root=REPO_ROOT)
    return config, rules


def decide(
    workspace: Path,
    target: str,
    *,
    operation: str | None = None,
    changed=(),
    config=None,
    layer: str | None = None,
):
    """跑一次流水线并算出决策（与 CLI 用的是同一条链路）。"""

    from policy.context import build_context
    from policy.engine import evaluate
    from validators.pipeline import PipelineRequest, run_pipeline

    default_config, rules = services()
    config = default_config if config is None else config
    if layer is None:
        layer = "controller" if "controller" in target else "service"
    context = build_context(
        {
            "request_id": "phase-5-demo",
            "file": target,
            "layer": layer,
            "language": "python",
            "operation": operation,
        },
        repo_root=workspace,
    )
    report = run_pipeline(
        PipelineRequest(
            target=target,
            workspace=workspace,
            context=context,
            rules=rules,
            changed_files=tuple(changed),
        ),
        config=config,
    )
    result = evaluate(rules, context, evidence=report.bundle)
    return report, result


def scenario_ast_blocks_bad_controller() -> Scenario:
    workspace = prepare("bad-controller")
    report, result = decide(workspace, "src/shop/order_controller_bad.py")

    facts = {
        "decision": result.decision.value,
        "rules": list(result.matched_rules),
        "dependencies": [
            {"name": fact.name, "module": fact.module, "line": fact.line}
            for fact in report.dependencies
            if fact.name == "repository"
        ],
        "violations": [
            {
                "rule_id": item.rule_id,
                "file": item.evidence.file,
                "line": item.evidence.line,
                "detail": item.evidence.detail,
            }
            for item in result.violations
        ],
    }
    passed = (
        result.decision.value == "block"
        and any(item.rule_id == "ARCH-001" for item in result.violations)
        and any(item["line"] == 3 for item in facts["dependencies"])
    )
    return Scenario(
        "ARCH-001 由 AST / 依赖图证据阻断（不需要调用方声明依赖）",
        passed,
        "decision=" + result.decision.value,
        facts,
    )


def scenario_ast_allows_good_controller() -> Scenario:
    workspace = prepare("good-controller")
    report, result = decide(workspace, "src/shop/order_controller.py")

    names = sorted(fact.name for fact in report.dependencies)
    return Scenario(
        "合规的 Controller 放行（依赖是 service）",
        result.decision.value == "allow" and "repository" not in names,
        "decision=" + result.decision.value + " dependencies=" + ",".join(names),
        {"decision": result.decision.value, "dependencies": names},
    )


def scenario_dynamic_import_fails_closed() -> Scenario:
    workspace = prepare("dynamic")
    report, result = decide(
        workspace, "src/shop/dynamic_dependency.py", layer="controller"
    )

    blockers = [(item.validator, item.status.value, item.reason) for item in report.blockers]
    return Scenario(
        "动态 import 无法静态解析 → 失败关闭",
        result.decision.value == "block" and any(item[0] == "py.depgraph@1.0" for item in blockers),
        "blockers=" + str(len(blockers)),
        {"blockers": [{"validator": item[0], "status": item[1]} for item in blockers]},
    )


def scenario_syntax_error_fails_closed() -> Scenario:
    workspace = prepare("syntax")
    report, result = decide(workspace, "src/shop/broken_syntax.py", layer="controller")

    blockers = [(item.validator, item.reason) for item in report.blockers]
    return Scenario(
        "语法错误 → 失败关闭（解析不了的文件不能被判定为没有依赖问题）",
        result.decision.value == "block" and any(item[0] == "py.ast@1.0" for item in blockers),
        blockers[0][1] if blockers else "没有阻断点",
        {"blockers": [{"validator": item[0], "reason": item[1]} for item in blockers]},
    )


def scenario_missing_tool_fails_closed() -> Scenario:
    import yaml

    from validators.registry import load_config

    workspace = prepare("missing-tool")
    document = yaml.safe_load(
        (REPO_ROOT / "validation" / "validators.yaml").read_text(encoding="utf-8")
    )
    for item in document["validators"]:
        if item["id"] == "tool.ruff":
            item["tool"]["command"] = ["definitely-not-a-real-linter-xyz"]
    root = DEMO_ROOT / "missing-tool-config"
    (root / "validation").mkdir(parents=True, exist_ok=True)
    for name in ("project.yaml", "test-layout.yaml", "ruff.toml", "mypy.ini", "pytest.ini"):
        shutil.copyfile(REPO_ROOT / "validation" / name, root / "validation" / name)
    (root / "validation" / "validators.yaml").write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8", newline=""
    )
    config = load_config(root=REPO_ROOT, registry=root / "validation" / "validators.yaml")

    report, result = decide(workspace, "src/shop/order_controller.py", config=config)
    blockers = [(item.validator, item.status.value) for item in report.blockers]
    return Scenario(
        "关键外部工具缺失 → 需要它的规则失败关闭",
        result.decision.value == "block" and ("tool.ruff@1.0", "unavailable") in blockers,
        "blockers=" + str(blockers),
        {"blockers": [{"validator": item[0], "status": item[1]} for item in blockers]},
    )


def scenario_missing_tests_block() -> Scenario:
    workspace = prepare("no-tests")
    shutil.rmtree(workspace / "tests")

    report, result = decide(
        workspace,
        "src/shop/order_service.py",
        operation="edit",
        changed=("src/shop/order_service.py",),
    )
    findings = [item for item in report.evidence if item.rule_id == "TESTING-001"]
    return Scenario(
        "生产变更缺少对应测试 → 阻断",
        result.decision.value == "block" and bool(findings),
        "findings=" + str(len(findings)),
        {"findings": [item.value for item in findings]},
    )


def scenario_related_tests_run() -> Scenario:
    workspace = prepare("with-tests")
    report, result = decide(
        workspace,
        "src/shop/order_service.py",
        operation="edit",
        changed=("src/shop/order_service.py",),
    )
    record = report.record("tool.pytest")
    selection = report.selection
    return Scenario(
        "选中的相关测试真的跑起来并通过",
        result.decision.value == "allow"
        and record is not None
        and record.status.value == "ok"
        and selection.get("nodeids") == ["tests/test_order_service.py"],
        "selection=" + str(selection.get("level")),
        {"selection": selection, "status": None if record is None else record.status.value},
    )


def scenario_failing_tests_block() -> Scenario:
    workspace = prepare("failing-tests")
    (workspace / "tests" / "test_order_service.py").write_text(
        FAILING_TEST, encoding="utf-8", newline=""
    )

    report, result = decide(
        workspace,
        "src/shop/order_service.py",
        operation="edit",
        changed=("src/shop/order_service.py",),
    )
    findings = [item for item in report.evidence if item.rule_id == "TESTING-002"]
    return Scenario(
        "相关测试失败 → 阻断（逐条给出失败用例）",
        result.decision.value == "block" and bool(findings),
        "failures=" + str(len(findings)),
        {"failures": [item.value for item in findings]},
    )


def scenario_evidence_is_reproducible() -> Scenario:
    workspace = prepare("reproducible")
    first, _ = decide(workspace, "src/shop/style_offences.py")
    second, _ = decide(workspace, "src/shop/style_offences.py")

    same = json.dumps(first.to_payload(), sort_keys=True) == json.dumps(
        second.to_payload(), sort_keys=True
    )
    return Scenario(
        "相同输入两次运行得到逐字节相同的证据",
        same,
        "identical" if same else "两次运行的证据不一致",
        {"validators": [record.validator for record in first.validators]},
    )


def scenario_tool_facts_are_traceable() -> Scenario:
    workspace = prepare("traceable")
    report, _ = decide(workspace, "src/shop/style_offences.py")
    record = report.record("tool.ruff")

    if record is None or record.tool is None:
        return Scenario(
            "外部工具的版本与配置可追溯",
            True,
            "skipped: 本机没有可用的 Ruff（CI 会装一份再跑）",
            {"tool.ruff": "unavailable"},
            verified=False,
        )
    facts = {
        "version": record.tool.version,
        "config": record.tool.config,
        "config_sha256": record.tool.config_sha256,
        "exit_code": record.tool.exit_code,
    }
    traceable = bool(facts["version"] and facts["config"] and facts["config_sha256"])
    return Scenario(
        "外部工具的版本与配置可追溯",
        traceable,
        "ruff=" + str(facts["version"]),
        facts,
    )


SCENARIOS = (
    scenario_ast_blocks_bad_controller,
    scenario_ast_allows_good_controller,
    scenario_dynamic_import_fails_closed,
    scenario_syntax_error_fails_closed,
    scenario_missing_tool_fails_closed,
    scenario_missing_tests_block,
    scenario_related_tests_run,
    scenario_failing_tests_block,
    scenario_evidence_is_reproducible,
    scenario_tool_facts_are_traceable,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 5 验证器闭环")
    parser.add_argument("--json", action="store_true", help="只打印结论 JSON")
    args = parser.parse_args(argv)

    scenarios: list[Scenario] = []
    for scenario in SCENARIOS:
        try:
            scenarios.append(scenario())
        except Exception as error:  # 场景本身崩了也算失败，并把原因写出来
            scenarios.append(
                Scenario(scenario.__name__, False, type(error).__name__ + ": " + str(error))
            )

    payload = {
        "phase": 5,
        "workspace": DEMO_ROOT.relative_to(REPO_ROOT).as_posix(),
        "result": "pass" if all(item.passed for item in scenarios) else "fail",
        "scenarios": [
            {
                "name": item.name,
                "passed": item.passed,
                "verified": item.verified,
                "detail": item.detail,
                "facts": item.facts,
            }
            for item in scenarios
        ],
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for item in scenarios:
            # 没验证到的场景不能显示成 PASS：人读的就是这一行。
            mark = "SKIP" if not item.verified else ("PASS" if item.passed else "FAIL")
            print("[" + mark + "] " + item.name + ": " + item.detail)
        print("result: " + payload["result"] + "  (证据: " + RESULT.relative_to(REPO_ROOT).as_posix() + ")")
        if payload["result"] != "pass":
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
