"""Phase 1 决策聚合测试：严重级别决策表、审批门禁、顺序稳定性。"""

from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from policy.engine import evaluate
from policy.models import (
    Decision,
    Evidence,
    RequiredAction,
    RuleSet,
    Severity,
    SkippedRule,
    ValidationResult,
    Violation,
    expected_decision,
)

from conftest import make_context, make_rule


def rules(*items: object) -> RuleSet:
    return RuleSet(rules=tuple(items))  # type: ignore[arg-type]


def violation(severity: Severity, *, rule_id: str = "ARCH-001", value: str = "repository") -> Violation:
    return Violation(
        rule_id=rule_id,
        rule_version=1,
        severity=severity,
        message="测试违规",
        evidence=Evidence(kind="dependency", subject="src/order/controller.py", value=value),
    )


@pytest.mark.parametrize(
    ("severities", "required_action", "expected"),
    [
        ((), None, Decision.ALLOW),
        ((Severity.INFO,), None, Decision.ALLOW_WITH_WARNINGS),
        ((Severity.WARNING,), None, Decision.ALLOW_WITH_WARNINGS),
        ((Severity.ERROR,), None, Decision.BLOCK),
        ((Severity.CRITICAL,), None, Decision.BLOCK),
        ((Severity.INFO, Severity.WARNING), None, Decision.ALLOW_WITH_WARNINGS),
        ((Severity.INFO, Severity.ERROR), None, Decision.BLOCK),
        ((Severity.WARNING, Severity.ERROR), None, Decision.BLOCK),
        ((Severity.WARNING, Severity.CRITICAL), None, Decision.BLOCK),
        ((), RequiredAction.APPROVAL, Decision.BLOCK),
        ((Severity.INFO,), RequiredAction.APPROVAL, Decision.BLOCK),
        ((Severity.CRITICAL,), RequiredAction.APPROVAL, Decision.BLOCK),
    ],
)
def test_decision_table(
    severities: tuple[Severity, ...], required_action: RequiredAction | None, expected: Decision
) -> None:
    findings = tuple(violation(item) for item in severities)

    assert expected_decision(findings, required_action=required_action) is expected


def test_no_matching_rule_allows() -> None:
    rule_set = rules(make_rule(scope={"layer": "service"}))

    result = evaluate(rule_set, make_context(layer="controller", dependencies=["repository"]))

    assert result.decision is Decision.ALLOW
    assert result.violations == ()
    assert result.matched_rules == ()
    assert result.skipped_rules[0].rule_id == "ARCH-001@1"


def test_multiple_warnings_allow_with_warnings() -> None:
    rule_set = rules(
        make_rule("CODING-001", severity="warning", forbidden=("logging",)),
        make_rule("CODING-002", severity="warning", forbidden=("orm",)),
    )

    result = evaluate(rule_set, make_context(dependencies=["logging", "orm"]))

    assert result.decision is Decision.ALLOW_WITH_WARNINGS
    assert result.severity_counts == {"warning": 2}
    assert result.passed is False


def test_warning_plus_error_blocks() -> None:
    rule_set = rules(
        make_rule("ARCH-001", severity="warning", forbidden=("logging",)),
        make_rule("ARCH-002", severity="error", forbidden=("repository",)),
    )

    result = evaluate(rule_set, make_context(dependencies=["logging", "repository"]))

    assert result.decision is Decision.BLOCK
    assert result.severity_counts == {"error": 1, "warning": 1}


@pytest.mark.parametrize("severity", ["error", "critical"])
def test_critical_and_error_always_block(severity: str) -> None:
    rule_set = rules(make_rule("SEC-001", severity=severity))

    result = evaluate(rule_set, make_context(dependencies=["repository"]))

    assert result.decision is Decision.BLOCK
    assert result.violations[0].severity is Severity(severity)


def test_info_only_is_not_a_block() -> None:
    rule_set = rules(make_rule("STYLE-001", severity="info"))

    result = evaluate(rule_set, make_context(dependencies=["repository"]))

    assert result.decision is Decision.ALLOW_WITH_WARNINGS
    assert result.violations[0].severity is Severity.INFO


def test_rule_order_does_not_change_decision_or_sorting() -> None:
    items = [
        make_rule("ARCH-010", forbidden=("repository", "orm")),
        make_rule("ARCH-002", forbidden=("repository",)),
        make_rule("CODING-003", severity="warning", forbidden=("logging",)),
    ]
    context = make_context(dependencies=["orm", "repository", "logging"])

    baseline = evaluate(rules(*items), context).to_decision_dict()
    for seed in range(5):
        shuffled = list(items)
        random.Random(seed).shuffle(shuffled)
        assert evaluate(rules(*shuffled), context).to_decision_dict() == baseline

    assert [item["rule_id"] for item in baseline["violations"]] == [
        "ARCH-002",
        "ARCH-010",
        "ARCH-010",
        "CODING-003",
    ]
    assert baseline["matched_rules"] == ["ARCH-002@1", "ARCH-010@1", "CODING-003@1"]


def test_aggregation_never_overwrites_duplicate_rule_ids() -> None:
    """加载器拒绝重复 ID；即使直接构造出重复 ID，聚合也不能静默覆盖其中一条。"""

    rule_set = rules(make_rule("ARCH-001"), make_rule("ARCH-001", forbidden=("orm",)))

    result = evaluate(rule_set, make_context(dependencies=["repository", "orm"]))

    assert [item.rule_id for item in result.violations] == ["ARCH-001", "ARCH-001"]
    assert result.matched_rules == ("ARCH-001@1", "ARCH-001@1")


def test_skipped_rules_are_sorted_and_explained() -> None:
    rule_set = rules(
        make_rule("ARCH-002", scope={"layer": "service"}),
        make_rule("ARCH-001", scope={"layer": "repository"}),
    )

    result = evaluate(rule_set, make_context(layer="controller"))

    assert [item.rule_id for item in result.skipped_rules] == ["ARCH-001@1", "ARCH-002@1"]
    assert result.skipped_rules[0].reasons == ("layer controller != repository",)


def test_approval_gate_blocks_without_any_violation() -> None:
    """审批是前置门禁：范围命中就要求授权，与"是否违规"分开表达。"""

    rule_set = rules(make_rule(requires_approval=True))

    result = evaluate(rule_set, make_context(dependencies=["service"]))

    assert result.decision is Decision.BLOCK
    assert result.required_action is RequiredAction.APPROVAL
    assert result.violations == ()
    assert result.matched_rules == ("ARCH-001@1",)
    assert result.to_decision_dict()["required_action"] == "approval"


def test_approval_gate_keeps_violations_separate() -> None:
    rule_set = rules(make_rule(requires_approval=True))

    result = evaluate(rule_set, make_context(dependencies=["repository"]))

    assert result.decision is Decision.BLOCK
    assert result.required_action is RequiredAction.APPROVAL
    assert [item.rule_id for item in result.violations] == ["ARCH-001"]


def test_warning_rule_with_approval_is_not_downgraded_to_warning() -> None:
    rule_set = rules(make_rule(severity="warning", requires_approval=True))

    result = evaluate(rule_set, make_context(dependencies=["repository"]))

    assert result.decision is Decision.BLOCK
    assert result.required_action is RequiredAction.APPROVAL


def test_unmatched_approval_rule_does_not_block() -> None:
    rule_set = rules(make_rule(requires_approval=True, scope={"layer": "service"}))

    result = evaluate(rule_set, make_context(layer="controller"))

    assert result.decision is Decision.ALLOW
    assert result.required_action is None


def test_required_action_is_exclusive_to_approval() -> None:
    rule_set = rules(make_rule())

    result = evaluate(rule_set, make_context(dependencies=["repository"]))

    assert result.required_action is None
    assert result.requires_approval is False


@pytest.mark.parametrize(
    ("decision", "findings", "required_action"),
    [
        (Decision.ALLOW, (violation(Severity.ERROR),), None),
        (Decision.BLOCK, (), None),
        (Decision.ALLOW_WITH_WARNINGS, (), None),
        (Decision.ALLOW, (), RequiredAction.APPROVAL),
        (Decision.ALLOW_WITH_WARNINGS, (violation(Severity.CRITICAL),), None),
    ],
)
def test_inconsistent_decision_is_rejected(
    decision: Decision, findings: tuple[Violation, ...], required_action: RequiredAction | None
) -> None:
    with pytest.raises(ValidationError):
        ValidationResult(
            decision=decision,
            request_id="req-1",
            violations=findings,
            required_action=required_action,
        )


def test_repeated_evaluation_is_byte_identical() -> None:
    rule_set = rules(make_rule(), make_rule("CODING-002", severity="warning", forbidden=("logging",)))
    context = make_context(dependencies=["repository", "logging"], trace_id="trace-1")

    first = evaluate(rule_set, context)
    second = evaluate(rule_set, context)

    assert first.model_dump() == second.model_dump()
    assert first.to_decision_dict() == second.to_decision_dict()


def test_result_records_trace_hash_and_skipped_reasons() -> None:
    rule_set = rules(make_rule(), make_rule("ARCH-002", scope={"layer": "service"}))
    context = make_context(dependencies=["service"], trace_id="trace-42")

    result = evaluate(rule_set, context)

    assert result.trace_id == "trace-42"
    assert result.rule_set_hash == rule_set.identity
    assert result.request_id == "req-123"
    assert result.policy_version == "phase-1"
    assert result.skipped_rules == (
        SkippedRule(rule_id="ARCH-002@1", reasons=("layer controller != service",)),
    )
