"""Phase 5 集成测试：真实流水线（真实文件、真实子进程）与 golden fixture。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from conftest import (
    POLICIES_DIR,
    REPO_ROOT,
    VALIDATOR_FIXTURES,
    VALIDATOR_PROJECT,
    copy_validator_project,
    make_checker_rule,
    make_context,
    validators_config,
    write_validation_config,
)
from policy.check import EXIT_ALLOWED, EXIT_ERROR, EXIT_VIOLATION
from policy.engine import evaluate
from policy.evidence import EVIDENCE_SCHEMA_VERSION, ValidatorStatus
from policy.loader import load_rule_set
from policy.models import RuleSet
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
    keep_temp: bool = False,
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
        keep_temp=keep_temp,
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


def test_temp_directories_are_cleaned_up(monkeypatch) -> None:
    """用完即删：默认运行不得在 .tmp/validators 下留下本次运行的目录。

    先用 keep_temp=True 证明"这次运行确实建了临时目录、且目录按验证器分开"，
    再用默认参数跑一次，确认**那一次运行自己的**目录已经不在——否则"没有残留"可能只是
    "从来没建过"：把 pipeline 里的 finally 去掉，这条用例照样是绿的。

    本次运行的目录靠记下 pipeline 自己生成的 run_id 来定位，而不是比对 .tmp/validators 前后的
    目录集合：门禁的 pytest 按文件并行时，别的进程也在同一目录下建 / 删运行目录，集合差会把
    别人的目录算进来（假红）。只看自己的 run_id，结论与并行无关，判定强度不变。
    """

    import validators.pipeline as pipeline

    runs_root = CONFIG.root / ".tmp" / "validators"
    issued: list[str] = []
    real_uuid4 = pipeline.uuid.uuid4

    def recording_uuid4():
        value = real_uuid4()
        issued.append(value.hex[:12])
        return value

    monkeypatch.setattr(pipeline, "uuid", SimpleNamespace(uuid4=recording_uuid4))

    kept = run_pipeline_for("src/shop/order_controller_bad.py", keep_temp=True)
    assert len(issued) == 1, "一次流水线运行应当恰好生成一个 run_id"
    run_root = runs_root / issued[0]
    assert run_root.is_dir(), "keep_temp=True 必须留下本次运行的临时目录"
    assert {item.name for item in run_root.iterdir() if item.is_dir()} >= {"py.ast", "py.source"}
    assert kept.target is not None

    try:
        report = run_pipeline_for("src/shop/order_controller_bad.py")
        assert len(issued) == 2, "第二次运行应当生成自己的 run_id"
        assert issued[1] != issued[0]
        leftover = runs_root / issued[1]
        assert not leftover.exists(), "默认运行结束后不得留下本次运行的临时目录：" + leftover.name
        assert report.target is not None
    finally:
        shutil.rmtree(run_root, ignore_errors=True)


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


def test_declared_checkers_are_not_served_checkers() -> None:
    """P7 的可执行反例：`validators[].declared_checkers`（声明负责）≠ 顶层 `served_checkers`（真的服务过）。

    修复前这个字段叫 `served_checkers`，与顶层同名。一个 `not_selected` 的验证器照样把它
    列出来——按名字读会把"没跑"读成"跑了"，正是本仓库反复强调的那类静默。
    """

    report = run_pipeline_for("src/shop/broken_syntax.py")

    record = report.record("py.depgraph")
    assert record is not None
    # 语法错误让 py.ast 失败关闭，依赖它的 py.depgraph 于是没被选中
    assert record.status is ValidatorStatus.NOT_SELECTED
    # 声明负责：即使一条证据都没产
    assert record.declared_checkers == ("forbidden_dependency",)
    # 真的服务过：顶层口径里没有它
    assert "forbidden_dependency" not in report.served_checkers

    payload = report.to_payload()
    entry = next(
        item for item in payload["validators"] if item["validator"] == "py.depgraph@1.0"
    )
    assert entry["declared_checkers"] == ["forbidden_dependency"]
    assert "served_checkers" not in entry
    # 顶层 served_checkers 不改名、不改语义：它仍然是"真的服务过"
    assert payload["served_checkers"] == list(report.served_checkers)


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
    # P7：没跑成的验证器只"声明负责"，不"服务过"——两个字段必须分开读
    record = report.record("tool.ruff")
    assert record is not None
    assert record.declared_checkers == ("style_lint",)
    assert "style_lint" not in report.served_checkers


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


# ------------------------------------- 分析不成立（N17）与"无归属诊断"的区别


BROKEN_SYNTAX = "src/shop/broken_syntax.py"
UNOWNED_LINT = "src/shop/unowned_lint_code.py"


def require_ruff() -> None:
    probe = ruff_probe()
    if not probe.ok:
        pytest.skip("本机没有可用的 Ruff（" + probe.reason + "）；CI 会装一份再跑")


def style_lint_rules() -> tuple[str, ...]:
    return tuple(
        sorted(rule.id for rule in RULES.rules if rule.enforcement.checker == "style_lint")
    )


def test_syntax_error_keeps_ruff_out_of_the_ledger() -> None:
    """N17：ruff 没能分析这个文件时，账本不许声称它查过了。

    修复前的实测：`served_checkers == ("style_lint",)`、`tool.ruff` 记成 ok —— 39 条
    style_lint 因而被记成"已判定 / 未发现"，而真正拦住文件的是 py.ast 的失败关闭。
    """

    require_ruff()
    report = run_pipeline_for(BROKEN_SYNTAX)

    record = report.record("tool.ruff")
    assert record is not None
    assert record.status is ValidatorStatus.FAILED
    assert "未能分析" in (record.reason or "")
    assert record.evidence_count == 0

    # (a) 那 39 条 style_lint 不再被记成已判定；这个文件上没有任何 checker 被判定过
    assert "style_lint" not in report.served_checkers
    assert report.served_checkers == ()

    # (b) 显式状态：分析不成立（而不是"判定过、未发现"）
    notes = [item for item in report.judgements if item.checker == "style_lint"]
    assert [(item.outcome, item.validators) for item in notes] == [
        ("unanalyzed", ("tool.ruff@1.0",))
    ]
    assert "未能分析" in notes[0].detail

    # 诊断仍然计数（不静默），只是不参与判定
    assert report.unmapped_findings >= 1

    # 失败关闭传到规则层：39 条 style_lint 规则全部以 critical 记失败关闭
    context = make_context(file=BROKEN_SYNTAX, language="python", layer="controller")
    result = evaluate(RULES, context, evidence=report.bundle)
    assert result.decision.value == "block"
    blocked = {
        item.rule_id
        for item in result.violations
        if item.severity.value == "critical" and "关键验证器不可用" in item.message
    }
    assert len(style_lint_rules()) == 39
    assert set(style_lint_rules()) <= blocked

    # 相同输入两次运行的载荷逐字节一致：新字段也必须是确定的
    again = run_pipeline_for(BROKEN_SYNTAX)
    assert json.dumps(report.to_payload(), sort_keys=True) == json.dumps(
        again.to_payload(), sort_keys=True
    )


def test_unowned_lint_codes_are_counted_and_do_not_block() -> None:
    """真正的无归属 lint 码（F841）仍只计数、不判定：不得被误升级成失败关闭。"""

    require_ruff()
    report = run_pipeline_for(UNOWNED_LINT)

    record = report.record("tool.ruff")
    assert record is not None
    assert record.status is ValidatorStatus.OK, record.reason
    assert report.unmapped_findings == 1
    assert "style_lint" in report.served_checkers
    assert report.blockers == ()
    assert verdict(report) == "allow"

    # 跑过但一条都没归上：显式口径，别让它长得像"判定过、未发现"
    notes = [item for item in report.judgements if item.checker == "style_lint"]
    assert [(item.outcome, item.validators) for item in notes] == [("empty", ("tool.ruff@1.0",))]
    assert "没有规则归属" in notes[0].detail


def test_every_needed_checker_is_served_or_explained() -> None:
    """账本里没有第三种含糊说法：需要判定的 checker 要么被判定，要么被显式解释。"""

    require_ruff()
    report = run_pipeline_for(BROKEN_SYNTAX)

    blocked = {checker for blocker in report.blockers for checker in blocker.checkers}
    explained = set(report.served_checkers) | blocked

    assert set(report.checks) <= explained
    assert not (set(report.served_checkers) & blocked)


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


def test_conftest_above_the_workspace_is_not_part_of_the_run(tmp_root: Path) -> None:
    """被测项目的收集范围只由它自己决定：工作区**之上**的 conftest 不得被加载。

    validation/pytest.ini 的约定是"被测项目的收集范围只由它自己与命令行参数决定"。但 `-c` 指向
    validation/ 时，pytest 把 confcutdir 定在 validation/，被测工作区之上的每一层目录都会被当成
    收集起点、其中的 conftest 会被加载——取证结论于是依赖"工作区碰巧放在哪"。Windows 上还会对
    这些上层目录里的兄弟项逐个 lstat：门禁并行时别的进程正在删它们，嵌套 pytest 随之报
    FileNotFoundError，三条流水线用例在本机 -n auto 下假红。

    反例构造：在工作区的父目录放一个一导入就失败的 conftest。修前它会被加载 -> 收集失败；
    修后（argv 带 --confcutdir {workspace}）它不在范围内，相关测试照常通过。
    """

    workspace = copy_validator_project(tmp_root)
    (tmp_root / "conftest.py").write_text(
        "raise RuntimeError('ancestor conftest must not be loaded')" + chr(10),
        encoding="utf-8",
        newline="",
    )

    report = run_pipeline_for(
        "src/shop/order_service.py",
        workspace=workspace,
        changed_files=("src/shop/order_service.py",),
        operation="edit",
    )

    record = report.record("tool.pytest")
    assert record is not None
    assert record.status is ValidatorStatus.OK, record.reason


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


# ------------------------------------------------------------------ Q7：待实现

# 先写测试、再写实现：测试 import 的名字还没落地（真机收据的形状见 14 号报告 §5 Q7）。
PENDING_TARGET = "src/shop/audit_repository.py"
PENDING_TEST_MODULE = "tests/test_audit_repository.py"
PENDING_TEST_SOURCE = (
    '"""审计仓储的测试：先写测试，实现还没落地。"""' + chr(10) + chr(10)
    + "from shop.audit_repository import AuditEntry" + chr(10) + chr(10) + chr(10)
    + "def test_entry_keeps_the_sequence() -> None:" + chr(10)
    + '    """序号原样保留。"""' + chr(10) + chr(10)
    + "    assert AuditEntry(sequence=1).sequence == 1" + chr(10)
)
# 模块落地了，但 AuditEntry 这个名字还没写进去 → 收集期 ImportError（退出码 2）
PENDING_PROPOSAL = (
    '"""审计仓储。"""' + chr(10) + chr(10) + chr(10)
    + "class AuditRepository:" + chr(10)
    + '    """审计仓储的实现（AuditEntry 还没落地）。"""' + chr(10)
)
PENDING_LANDED = (
    '"""审计仓储。"""' + chr(10) + chr(10) + chr(10)
    + "class AuditEntry:" + chr(10)
    + '    """一条审计记录。"""' + chr(10) + chr(10)
    + "    def __init__(self, sequence: int) -> None:" + chr(10)
    + '        """记录序号。"""' + chr(10) + chr(10)
    + "        self.sequence = sequence" + chr(10)
)


def pending_project(tmp_root: Path) -> Path:
    workspace = copy_validator_project(tmp_root)
    (workspace / PENDING_TEST_MODULE).write_text(
        PENDING_TEST_SOURCE, encoding="utf-8", newline=""
    )
    (workspace / PENDING_TARGET).write_text(PENDING_PROPOSAL, encoding="utf-8", newline="")
    return workspace


# 这五条只关心"测试证据"这一条链路：规则集收窄到 missing_tests + failing_tests，
# 流水线就只选 py.source + tool.pytest。**这不是降低真实性**：跑的是同一条真流水线、
# 真的 pytest 子进程、同一套证据协议；收窄掉的只是与 Q7 无关的外部工具（ruff），
# 否则"本机 PATH 里有没有 ruff"会决定这条用例的红绿——那是环境的性质，不是被测行为的性质。
Q7_RULES = RuleSet(
    rules=(
        make_checker_rule("TESTING-001", checker="missing_tests"),
        make_checker_rule("TESTING-002", checker="failing_tests"),
    ),
    source_paths=(),
)


def run_q7(workspace: Path) -> object:
    return run_pipeline(
        PipelineRequest(
            target=PENDING_TARGET,
            workspace=workspace,
            context=make_context(
                file=PENDING_TARGET, language="python", layer="repository", operation="create"
            ),
            rules=Q7_RULES,
            changed_files=(PENDING_TARGET,),
        ),
        config=CONFIG,
    )


def q7_verdict(report) -> str:
    return evaluate(
        Q7_RULES,
        make_context(
            file=PENDING_TARGET, language="python", layer="repository", operation="create"
        ),
        evidence=report.bundle,
    ).decision.value


def test_pending_implementation_is_a_warning_not_a_validator_crash(tmp_root: Path) -> None:
    """真流水线：状态是 pending_implementation、没有 blocker、failing_tests 不进 served。"""

    workspace = pending_project(tmp_root)

    report = run_q7(workspace)

    record = report.record("tool.pytest")
    assert record is not None
    assert record.status is ValidatorStatus.PENDING_IMPLEMENTATION, record.reason
    assert "待实现" in (record.reason or "")
    assert report.blockers == ()
    [pending] = report.pending_implementation
    assert pending.test_modules == (PENDING_TEST_MODULE,)
    assert pending.missing_targets == ("shop.audit_repository:AuditEntry",)
    assert pending.checkers == ("failing_tests",)
    # 没查成的不能记成查过了；查成的（missing_tests 来自 selection）照样记账
    assert "failing_tests" not in report.served_checkers
    assert "missing_tests" in report.served_checkers
    assert [item for item in report.evidence if item.checker == "failing_tests"] == []
    assert "pending_implementation" in report.to_payload()
    assert q7_verdict(report) == "allow_with_warnings"


def test_pending_implementation_clears_once_the_name_lands(tmp_root: Path) -> None:
    """补上 AuditEntry 之后：状态回到 ok、待实现清单为空、测试真的跑了。"""

    workspace = pending_project(tmp_root)
    (workspace / PENDING_TARGET).write_text(PENDING_LANDED, encoding="utf-8", newline="")

    report = run_q7(workspace)

    record = report.record("tool.pytest")
    assert record is not None
    assert record.status is ValidatorStatus.OK, record.reason
    assert report.pending_implementation == ()
    assert "failing_tests" in report.served_checkers
    assert q7_verdict(report) == "allow"


def test_a_third_party_import_failure_is_still_a_real_finding(tmp_root: Path) -> None:
    """反例：第三方包缺失不是"待实现"——它是真违规，仍然阻断。"""

    workspace = copy_validator_project(tmp_root)
    (workspace / PENDING_TARGET).write_text(PENDING_LANDED, encoding="utf-8", newline="")
    (workspace / PENDING_TEST_MODULE).write_text(
        '"""第三方包缺失。"""' + chr(10) + chr(10)
        + "import requests_absent_package" + chr(10) + chr(10) + chr(10)
        + "def test_noop() -> None:" + chr(10)
        + '    """占位。"""' + chr(10) + chr(10)
        + "    assert requests_absent_package" + chr(10),
        encoding="utf-8",
        newline="",
    )

    report = run_q7(workspace)

    record = report.record("tool.pytest")
    assert record is not None
    assert record.status is ValidatorStatus.FINDINGS, record.reason
    assert report.pending_implementation == ()
    assert "failing_tests" in report.served_checkers
    assert not [item for item in report.blockers if "failing_tests" in item.checkers]
    assert q7_verdict(report) == "block"
    failures = [item for item in report.evidence if item.checker == "failing_tests"]
    assert failures and "requests_absent_package" in failures[0].message
    assert "验证器不可用" not in failures[0].message


def test_a_syntax_error_in_the_test_module_is_still_a_real_finding(tmp_root: Path) -> None:
    """反例：测试模块自己语法错误 → 真违规（不是"验证器被搞崩了"）。"""

    workspace = copy_validator_project(tmp_root)
    (workspace / PENDING_TARGET).write_text(PENDING_LANDED, encoding="utf-8", newline="")
    (workspace / PENDING_TEST_MODULE).write_text(
        "def broken(:" + chr(10), encoding="utf-8", newline=""
    )

    report = run_q7(workspace)

    record = report.record("tool.pytest")
    assert record is not None
    assert record.status is ValidatorStatus.FINDINGS, record.reason
    assert report.pending_implementation == ()
    assert not [item for item in report.blockers if "failing_tests" in item.checkers]
    assert q7_verdict(report) == "block"
    failures = [item for item in report.evidence if item.checker == "failing_tests"]
    assert failures and "SyntaxError" in failures[0].message


def test_a_broken_conftest_is_a_real_finding_not_a_crashed_validator(tmp_root: Path) -> None:
    """反例：conftest 出错（退出码 4、stdout 全空）也要有显式证据，且理由不说成"验证器不可用"。"""

    workspace = copy_validator_project(tmp_root)
    (workspace / PENDING_TARGET).write_text(PENDING_LANDED, encoding="utf-8", newline="")
    (workspace / PENDING_TEST_MODULE).write_text(
        PENDING_TEST_SOURCE, encoding="utf-8", newline=""
    )
    (workspace / "tests" / "conftest.py").write_text(
        "import requests_absent_package" + chr(10), encoding="utf-8", newline=""
    )

    report = run_q7(workspace)

    record = report.record("tool.pytest")
    assert record is not None
    assert record.status is ValidatorStatus.FINDINGS, record.reason
    assert report.pending_implementation == ()
    assert not [item for item in report.blockers if "failing_tests" in item.checkers]
    assert q7_verdict(report) == "block"
    failures = [item for item in report.evidence if item.checker == "failing_tests"]
    assert failures and "requests_absent_package" in failures[0].message
    assert "收集失败" in failures[0].message
    assert "验证器不可用" not in failures[0].message


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
    # 协议版本由契约测试逐字钉住（tests/contract/test_validator_protocol.py），这里跟随常量
    assert payload["evidence"]["schema_version"] == EVIDENCE_SCHEMA_VERSION
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
