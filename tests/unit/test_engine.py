"""Phase 0 Engine 表驱动测试：范围匹配、依赖判定、稳定排序。"""

from __future__ import annotations

import pytest

from policy.engine import (
    EngineError,
    evaluate,
    insufficient_context_violation,
    rule_matches_context,
    skipped_rule_id,
)
from policy.models import (
    Decision,
    Enforcement,
    EnforcementType,
    ForbiddenDependencyRule,
    Rule,
    RuleScope,
    RuleSet,
    Severity,
    SourceRef,
)

from conftest import make_context, rule_document

def _rule(
    rule_id: str,
    *,
    forbidden: tuple[str, ...],
    severity: Severity = Severity.ERROR,
    checker: str | None = "forbidden_dependency",
) -> Rule:
    return Rule(
        id=rule_id,
        version=1,
        name="controller-service-boundary",
        description="测试规则",
        scope=RuleScope(language="python", layer="controller"),
        severity=severity,
        enforcement=Enforcement(type=EnforcementType.DETERMINISTIC, checker=checker),
        rule=ForbiddenDependencyRule(forbidden_dependency=forbidden),
        message="Controller 必须通过 Service 访问 Repository。",
        source=SourceRef(kind="project-policy", path="tests/unit/test_engine.py"),
    )


@pytest.mark.parametrize(
    ("layer", "dependencies", "expected_decision", "expected_rule_ids"),
    [
        ("controller", ["repository"], Decision.BLOCK, ("ARCH-001@1",)),
        ("controller", ["service"], Decision.ALLOW, ()),
        ("service", ["repository"], Decision.ALLOW, ()),
        ("controller", ["Repository"], Decision.BLOCK, ("ARCH-001@1",)),
        ("controller", [], Decision.ALLOW, ()),
    ],
)
def test_arch_001_truth_table(
    arch_rules: RuleSet,
    layer: str,
    dependencies: list[str],
    expected_decision: Decision,
    expected_rule_ids: tuple[str, ...],
) -> None:
    context = make_context(layer=layer, dependencies=dependencies)

    result = evaluate(arch_rules, context)

    assert result.decision is expected_decision
    assert tuple(violation.canonical_id for violation in result.violations) == expected_rule_ids
    assert result.request_id == "req-123"


def test_violation_payload_is_structured(arch_rules: RuleSet) -> None:
    result = evaluate(arch_rules, make_context(layer="controller", dependencies=["repository"]))

    violation = result.violations[0]
    assert violation.rule_id == "ARCH-001"
    assert violation.rule_version == 1
    assert violation.severity is Severity.ERROR
    assert violation.message == "Controller 必须通过 Service 访问 Repository。"
    assert violation.evidence.kind == "dependency"
    assert violation.evidence.subject == "src/order/controller.py"
    assert violation.evidence.value == "repository"
    assert violation.evidence.file == "src/order/controller.py"
    assert result.matched_rules == ("ARCH-001@1",)


def test_matched_rules_lists_scope_hits_only(arch_rules: RuleSet) -> None:
    assert evaluate(arch_rules, make_context(layer="service", dependencies=["repository"])).matched_rules == ()
    assert evaluate(arch_rules, make_context(layer="controller")).matched_rules == ("ARCH-001@1",)


def test_scope_mismatch_reason_is_reported(arch_rule: Rule) -> None:
    service = make_context(layer="service")
    python_controller = make_context(layer="controller")
    other_language = make_context(language="go")

    assert rule_matches_context(arch_rule, python_controller)
    assert not rule_matches_context(arch_rule, service)
    assert skipped_rule_id(arch_rule, service) == "ARCH-001@1: layer service != controller"
    assert skipped_rule_id(arch_rule, other_language) == "ARCH-001@1: language go != python"
    assert skipped_rule_id(arch_rule, python_controller) is None


def test_undeclared_scope_dimension_means_any_value() -> None:
    rule = Rule.model_validate(rule_document(scope={"layer": "controller"}))

    # scope.language 缺省 = 不限制：任何语言都匹配，但 layer 仍然生效
    assert rule_matches_context(rule, make_context(language=None, layer="controller"))
    assert rule_matches_context(rule, make_context(language="go", layer="controller"))
    assert not rule_matches_context(rule, make_context(language="go", layer="service"))


def test_missing_context_layer_cannot_be_matched_by_declared_layer() -> None:
    rule = Rule.model_validate(rule_document(scope={"layer": "controller"}))

    assert not rule_matches_context(rule, make_context(layer="unknown"))
    assert skipped_rule_id(rule, make_context(layer="unknown")) == (
        "ARCH-001@1: layer unknown != controller"
    )


def test_multiple_rules_are_sorted_by_rule_id() -> None:
    rules = RuleSet(
        rules=(
            _rule("ARCH-010", forbidden=("repository", "orm")),
            _rule("ARCH-002", forbidden=("repository",)),
        )
    )

    result = evaluate(rules, make_context(layer="controller", dependencies=["orm", "repository"]))

    assert [violation.canonical_id for violation in result.violations] == [
        "ARCH-002@1",
        "ARCH-010@1",
        "ARCH-010@1",
    ]
    assert [violation.evidence.value for violation in result.violations] == [
        "repository",
        "orm",
        "repository",
    ]


def test_repeated_evaluation_is_identical(arch_rules: RuleSet) -> None:
    context = make_context(layer="controller", dependencies=["repository"])

    first = evaluate(arch_rules, context)
    second = evaluate(arch_rules, context)

    assert first.model_dump() == second.model_dump()
    assert first.to_decision_dict() == second.to_decision_dict()


def test_warning_severity_yields_allow_with_warnings() -> None:
    rules = RuleSet(
        rules=(
            _rule("ARCH-003", forbidden=("repository",), severity=Severity.WARNING),
        )
    )

    result = evaluate(rules, make_context(layer="controller", dependencies=["repository"]))

    assert result.decision is Decision.ALLOW_WITH_WARNINGS
    assert result.passed is False
    assert result.severity_counts == {"warning": 1}


def test_empty_rule_set_allows_and_reports_nothing(arch_rules: RuleSet) -> None:
    result = evaluate(RuleSet(), make_context(layer="controller", dependencies=["repository"]))

    assert result.decision is Decision.ALLOW
    assert result.matched_rules == ()
    assert result.violations == ()


def test_unsupported_enforcement_never_passes_silently() -> None:
    """模型层已经拒绝未知 checker；这里验证引擎的第二道防线（绕过模型构造的规则）。"""

    base = _rule("ARCH-004", forbidden=("repository",))

    # model_construct 刻意跳过校验，模拟"有规则绕过了模型层"的情形
    forged = Rule.model_construct(
        id=base.id,
        version=base.version,
        name=base.name,
        description=base.description,
        scope=base.scope,
        severity=base.severity,
        enforcement=Enforcement(type=EnforcementType.DETERMINISTIC, checker="llm_judgement"),
        rule=base.rule,
        message=base.message,
        source=base.source,
    )

    # RuleSet 同样是严格模型：这里也要 model_construct 才能装进这条"伪造"规则
    forged_set = RuleSet.model_construct(rules=(forged,), source_paths=("tests/unit/test_engine.py",))

    with pytest.raises(EngineError) as error:
        evaluate(forged_set, make_context(layer="controller", dependencies=["repository"]))

    assert "llm_judgement" in str(error.value)


def test_engine_does_not_mutate_context_or_rules(arch_rules: RuleSet) -> None:
    context = make_context(layer="controller", dependencies=["repository"])
    before = context.model_dump()

    evaluate(arch_rules, context)

    assert context.model_dump() == before
    assert arch_rules.ids == ("ARCH-001@1",)


def test_insufficient_context_violation_blocks(arch_rule: Rule) -> None:
    result = insufficient_context_violation(arch_rule, request_id="req-9", detail="layer 缺失")

    assert result.decision is Decision.BLOCK
    assert result.request_id == "req-9"
    assert result.violations[0].evidence.kind == "context"
