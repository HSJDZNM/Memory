"""Phase 5 判定层测试：docstring 证据、测试选择，以及"证据 → 违规"的引擎语义。"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import (
    VALIDATOR_PROJECT,
    make_checker_rule,
    make_context,
    validators_config,
)
from policy.engine import evaluate
from policy.evidence import (
    Blocker,
    DependencyFact,
    DependencyKind,
    DependencyResolution,
    EvidenceBundle,
    EvidenceLocation,
    SourceDigest,
    ValidationEvidence,
    ValidatorKind,
    ValidatorRecord,
    ValidatorStatus,
)
from policy.models import Decision, RuleSet, Severity
from validators.docstrings import missing_docstring_evidence
from validators.python_ast import parse_module
from validators.selection import list_test_files, select_tests

CONFIG = validators_config()
VALIDATOR = "py.docstring@1.0"


def bundle(**overrides: object) -> EvidenceBundle:
    payload: dict[str, object] = {"target": None}
    payload.update(overrides)
    return EvidenceBundle(**payload)  # type: ignore[arg-type]


def finding(rule_id: str, *, message: str = "缺少 docstring", line: int = 3) -> ValidationEvidence:
    return ValidationEvidence(
        validator_id="py.docstring",
        validator_version="1.0",
        checker="missing_docstring",
        rule_id=rule_id,
        rule_version=1,
        severity=Severity.WARNING,
        message=message,
        value="<module>",
        location=EvidenceLocation(file="src/shop/no_module_docstring.py", line=line, column=0),
    )


def record(
    validator_id: str = "py.docstring",
    *,
    status: ValidatorStatus = ValidatorStatus.OK,
    checkers: tuple[str, ...] = ("missing_docstring",),
    critical: bool = True,
) -> ValidatorRecord:
    return ValidatorRecord(
        validator_id=validator_id,
        validator_version="1.0",
        kind=ValidatorKind.BUILTIN,
        stage="docstring",
        status=status,
        critical=critical,
        served_checkers=checkers,
    )


# ------------------------------------------------------------------ docstring 验证器


def test_docstring_validator_reports_the_module_and_public_definitions() -> None:
    rule = make_checker_rule("DOC-001")
    facts = parse_module(
        "def public() -> None:" + chr(10) + "    pass" + chr(10)
    )

    evidence = missing_docstring_evidence(
        facts, target_path="src/shop/example.py", rules=(rule,), validator=VALIDATOR
    )

    values = {item.value for item in evidence}
    assert values == {"<module>", "public"}
    assert all(item.rule_id == "DOC-001" for item in evidence)
    assert all(item.checker == "missing_docstring" for item in evidence)
    assert evidence[1].location == EvidenceLocation(file="src/shop/example.py", line=1, column=0)


def test_docstring_validator_respects_targets_and_private_switch() -> None:
    methods_only = make_checker_rule(
        "DOC-002", body={"missing_docstring": {"targets": ["method"], "include_private": True}}
    )
    facts = parse_module(
        "class Holder:" + chr(10)
        + "    def _hidden(self) -> None:" + chr(10)
        + "        pass" + chr(10)
    )

    evidence = missing_docstring_evidence(
        facts, target_path="src/shop/example.py", rules=(methods_only,), validator=VALIDATOR
    )

    assert [item.value for item in evidence] == ["Holder._hidden"]


def test_docstring_validator_is_silent_when_everything_is_documented() -> None:
    rule = make_checker_rule("DOC-001")
    facts = parse_module(
        '"""模块。"""' + chr(10) + "def public() -> None:" + chr(10) + '    """有。"""' + chr(10)
    )

    assert (
        missing_docstring_evidence(
            facts, target_path="a.py", rules=(rule,), validator=VALIDATOR
        )
        == ()
    )


def test_docstring_evidence_is_sorted_and_deduplicated() -> None:
    rule = make_checker_rule("DOC-001")
    other = make_checker_rule("DOC-009", body={"missing_docstring": {"targets": ["module"]}})
    facts = parse_module("x = 1" + chr(10))

    evidence = missing_docstring_evidence(
        facts, target_path="a.py", rules=(rule, other), validator=VALIDATOR
    )

    assert [item.rule_id for item in evidence] == ["DOC-001", "DOC-009"]


# ------------------------------------------------------------------ 测试选择


def test_selection_prefers_the_related_test_file() -> None:
    selection = select_tests(
        target_path="src/shop/order_service.py",
        changed_files=("src/shop/order_service.py",),
        layout=CONFIG.layout,
        workspace=VALIDATOR_PROJECT,
        max_nodeids=10,
    )

    assert selection.level == "related"
    assert selection.nodeids == ("tests/test_order_service.py",)
    assert selection.missing == ()


def test_selection_escalates_to_the_suite_when_nothing_is_related() -> None:
    selection = select_tests(
        target_path="src/shop/order_repository.py",
        changed_files=("src/shop/order_repository.py",),
        layout=CONFIG.layout,
        workspace=VALIDATOR_PROJECT,
        max_nodeids=10,
    )

    assert selection.level == "suite"
    assert selection.nodeids == ("tests/test_order_service.py",)


def test_selection_reports_changed_production_files_without_tests(tmp_root: Path) -> None:
    workspace = tmp_root / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "lonely.py").write_text("x = 1" + chr(10), encoding="utf-8", newline="")

    selection = select_tests(
        target_path="src/lonely.py",
        changed_files=("src/lonely.py",),
        layout=CONFIG.layout,
        workspace=workspace,
        max_nodeids=10,
    )

    assert selection.level == "none"
    assert selection.missing == ("src/lonely.py",)


def test_selection_is_not_applicable_without_production_changes() -> None:
    selection = select_tests(
        target_path="docs/readme.md",
        changed_files=("docs/readme.md",),
        layout=CONFIG.layout,
        workspace=VALIDATOR_PROJECT,
        max_nodeids=10,
    )

    assert selection.level == "none"
    assert "没有生产文件" in selection.reason


def test_selection_caps_node_ids() -> None:
    selection = select_tests(
        target_path="src/shop/order_repository.py",
        changed_files=(),
        layout=CONFIG.layout,
        workspace=VALIDATOR_PROJECT,
        max_nodeids=0,
    )

    assert selection.nodeids == ()


def test_list_test_files_uses_the_declared_patterns() -> None:
    files = list_test_files(VALIDATOR_PROJECT, CONFIG.layout)

    assert files == ("tests/test_order_service.py",)


# ------------------------------------------------------------------ 引擎 × 证据


def test_finding_becomes_a_violation_with_location_and_rule_severity() -> None:
    rule = make_checker_rule("DOC-001", severity="error")
    rules = RuleSet(rules=(rule,), source_paths=("policies/coding/DOC-001.yaml",))
    evidence = bundle(
        evidence=(finding("DOC-001"),),
        validators=(record(),),
        served_checkers=("missing_docstring",),
    )

    result = evaluate(rules, make_context(), evidence=evidence)

    assert result.decision is Decision.BLOCK
    violation = result.violations[0]
    assert violation.severity is Severity.ERROR  # 严重级别来自规则，不来自证据
    assert violation.evidence.file == "src/shop/no_module_docstring.py"
    assert violation.evidence.line == 3
    assert "py.docstring@1.0" in (violation.evidence.detail or "")


def test_findings_for_other_rules_are_ignored() -> None:
    rule = make_checker_rule("DOC-001")
    rules = RuleSet(rules=(rule,), source_paths=())
    evidence = bundle(
        evidence=(finding("DOC-999"),),
        validators=(record(),),
        served_checkers=("missing_docstring",),
    )

    result = evaluate(rules, make_context(), evidence=evidence)

    assert result.decision is Decision.ALLOW


def test_critical_validator_failure_blocks_even_without_findings() -> None:
    rule = make_checker_rule("DOC-001")
    rules = RuleSet(rules=(rule,), source_paths=())
    evidence = bundle(
        validators=(record(status=ValidatorStatus.TIMEOUT),),
        blockers=(
            Blocker(
                validator_id="py.docstring",
                validator_version="1.0",
                status=ValidatorStatus.TIMEOUT,
                reason="超过超时 1000ms",
                checkers=("missing_docstring",),
            ),
        ),
    )

    result = evaluate(rules, make_context(), evidence=evidence)

    assert result.decision is Decision.BLOCK
    assert result.violations[0].severity is Severity.CRITICAL
    assert "关键验证器不可用" in result.violations[0].message


def test_checker_without_any_evidence_is_fail_closed() -> None:
    rule = make_checker_rule("DOC-001")
    rules = RuleSet(rules=(rule,), source_paths=())

    result = evaluate(rules, make_context(), evidence=bundle())

    assert result.decision is Decision.BLOCK
    assert "没有验证器为 checker missing_docstring 提供证据" in result.violations[0].message


def test_context_only_paths_record_evidence_checkers_as_skipped() -> None:
    rule = make_checker_rule("DOC-001")
    rules = RuleSet(rules=(rule,), source_paths=())

    result = evaluate(rules, make_context())

    assert result.decision is Decision.ALLOW
    assert result.matched_rules == ()
    assert [item.rule_id for item in result.skipped_rules] == ["DOC-001@1"]
    assert "验证器证据" in result.skipped_rules[0].reasons[0]


def test_forbidden_dependency_uses_evidence_facts_with_lines() -> None:
    rule = make_checker_rule("ARCH-001", checker="forbidden_dependency")
    rules = RuleSet(rules=(rule,), source_paths=())
    evidence = bundle(
        dependencies=(
            DependencyFact(
                name="repository",
                module="shop.order_repository",
                kind=DependencyKind.FROM_IMPORT,
                resolution=DependencyResolution.INTERNAL,
                file="src/shop/order_controller_bad.py",
                line=3,
                column=0,
                validator="py.depgraph@1.0",
            ),
        ),
        validators=(record("py.depgraph", checkers=("forbidden_dependency",)),),
        served_checkers=("forbidden_dependency",),
    )

    result = evaluate(rules, make_context(), evidence=evidence)

    assert result.decision is Decision.BLOCK
    violation = result.violations[0]
    assert violation.evidence.line == 3
    assert violation.evidence.value == "repository"
    assert "py.depgraph@1.0" in (violation.evidence.detail or "")


def test_explicit_dependency_facts_keep_the_phase_zero_message() -> None:
    rule = make_checker_rule("ARCH-001", checker="forbidden_dependency")
    rules = RuleSet(rules=(rule,), source_paths=())
    evidence = bundle(
        dependencies=(
            DependencyFact(
                name="repository",
                kind=DependencyKind.DECLARED,
                resolution=DependencyResolution.DECLARED,
                file="src/shop/order_controller_bad.py",
                validator="cli.explicit@1.0",
            ),
        ),
        served_checkers=("forbidden_dependency",),
    )

    result = evaluate(rules, make_context(), evidence=evidence)

    assert result.violations[0].evidence.detail == "layer=controller 直接依赖 repository"
    assert result.violations[0].evidence.line is None


def test_violations_are_sorted_stably_regardless_of_evidence_order() -> None:
    rule = make_checker_rule("DOC-001")
    rules = RuleSet(rules=(rule,), source_paths=())
    first = finding("DOC-001", message="A", line=9)
    second = finding("DOC-001", message="B", line=2)

    forward = evaluate(
        rules,
        make_context(),
        evidence=bundle(
            evidence=(first, second),
            validators=(record(),),
            served_checkers=("missing_docstring",),
        ),
    )
    backward = evaluate(
        rules,
        make_context(),
        evidence=bundle(
            evidence=(second, first),
            validators=(record(),),
            served_checkers=("missing_docstring",),
        ),
    )

    assert forward.to_decision_dict() == backward.to_decision_dict()
    assert [item.evidence.line for item in forward.violations] == [2, 9]


def test_bundle_normalisation_deduplicates_and_sorts() -> None:
    duplicated = ValidationEvidence(
        validator_id="py.ast",
        validator_version="1.0",
        checker="style_lint",
        rule_id="STYLE-001",
        severity=Severity.WARNING,
        message="重复的诊断",
        value="E501",
    )
    raw = EvidenceBundle(
        evidence=(duplicated, duplicated),
        validators=(record("z.validator"), record("a.validator")),
        dependencies=(
            DependencyFact(
                name="service",
                kind=DependencyKind.IMPORT,
                resolution=DependencyResolution.INTERNAL,
                validator="py.depgraph@1.0",
            ),
            DependencyFact(
                name="os",
                kind=DependencyKind.IMPORT,
                resolution=DependencyResolution.STDLIB,
                validator="py.depgraph@1.0",
            ),
        ),
    )

    normalised = raw.normalize()

    assert len(normalised.evidence) == 1
    assert [item.validator for item in normalised.validators] == ["a.validator@1.0", "z.validator@1.0"]
    assert [fact.name for fact in normalised.dependencies] == ["service", "os"]
    assert normalised == raw.normalize()


def test_source_digest_and_unknown_schema_are_rejected() -> None:
    digest = SourceDigest(file="a.py", language="python", sha256="sha256:" + "0" * 64, bytes=1, lines=1)
    assert digest.file == "a.py"

    with pytest.raises(Exception) as error:
        EvidenceBundle(schema_version="9.9")
    assert "未知证据协议版本" in str(error.value)
