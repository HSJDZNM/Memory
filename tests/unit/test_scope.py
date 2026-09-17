"""Phase 1 Scope Matcher 表驱动测试：AND / OR / 通配 / 缺值 / 解释原因。"""

from __future__ import annotations

import pytest

from policy.engine import skipped_rule_id
from policy.models import PolicyContext, RuleScope
from policy.scope import (
    DIMENSION_ACCESSORS,
    compare_dimension,
    dimension_value,
    match_scope,
)

from conftest import make_context, make_rule


def scope_of(**dimensions: object) -> RuleScope:
    return RuleScope.model_validate(dimensions)


@pytest.mark.parametrize(
    ("dimensions", "context_overrides", "expected_matched", "expected_failures"),
    [
        # 单字段：精确命中 / 精确未命中
        ({"layer": "controller"}, {}, True, ()),
        ({"layer": "service"}, {}, False, ("layer controller != service",)),
        # 单字段：值列表 = OR
        ({"layer": ["controller", "service"]}, {}, True, ()),
        ({"layer": ["service", "repository"]}, {}, False, ("layer controller not in [service, repository]",)),
        # 通配：显式不限制，连缺失值也算命中
        ({"layer": "*"}, {}, True, ()),
        ({"module": "*"}, {}, True, ()),
        ({"layer": ["controller", "*"]}, {}, True, ()),
        # 多字段 = AND：一个命中一个未命中 → 整体不命中
        ({"layer": "controller", "language": "python"}, {}, True, ()),
        ({"layer": "controller", "language": "go"}, {}, False, ("language python != go",)),
        (
            {"layer": "controller", "module": "order"},
            {"module": "billing"},
            False,
            ("module billing != order",),
        ),
        # 声明了维度但上下文没有该值 → 不命中，并说明缺失
        ({"module": "order"}, {}, False, ("module <missing> != order",)),
        ({"operation": "edit"}, {}, False, ("operation <missing> != edit",)),
        # 上下文的 operation 是受控枚举，比较用其字符串值
        ({"operation": ["edit", "create"]}, {"operation": "edit"}, True, ()),
        ({"operation": "execute"}, {"operation": "edit"}, False, ("operation edit != execute",)),
        # 没有声明任何维度 = 不限制
        ({}, {"layer": "service"}, True, ()),
        # 未声明模块 ≠ 匹配空值：声明了 module 就必须有值
        ({"layer": "controller"}, {"module": None}, True, ()),
    ],
)
def test_scope_matrix(
    dimensions: dict[str, object],
    context_overrides: dict[str, object],
    expected_matched: bool,
    expected_failures: tuple[str, ...],
) -> None:
    result = match_scope(scope_of(**dimensions), make_context(**context_overrides))

    assert result.matched is expected_matched
    assert result.failures == expected_failures


@pytest.mark.parametrize(
    ("dimensions", "context_overrides", "expected_specificity"),
    [
        ({}, {}, 0),
        ({"layer": "*"}, {}, 0),
        ({"layer": "controller"}, {}, 1),
        ({"layer": "controller", "language": "python"}, {}, 2),
        ({"layer": ["controller", "service"], "language": "python"}, {}, 2),
        # 未命中的规则也能给出"命中了几个维度"，便于解释而不是二元结论
        ({"layer": "controller", "language": "go"}, {}, 1),
        ({"layer": "service", "language": "go"}, {}, 0),
    ],
)
def test_specificity_counts_matched_non_wildcard_dimensions(
    dimensions: dict[str, object], context_overrides: dict[str, object], expected_specificity: int
) -> None:
    result = match_scope(scope_of(**dimensions), make_context(**context_overrides))

    assert result.specificity == expected_specificity


def test_reasons_cover_every_declared_dimension() -> None:
    result = match_scope(
        scope_of(language="python", layer="controller", module="order"), make_context()
    )

    assert result.reasons == (
        "language python == python",
        "layer controller == controller",
        "module <missing> != order",
    )
    assert result.failures == ("module <missing> != order",)
    assert [(item.dimension, item.matched, item.wildcard) for item in result.comparisons] == [
        ("language", True, False),
        ("layer", True, False),
        ("module", False, False),
    ]


def test_wildcard_is_reported_as_no_restriction() -> None:
    result = match_scope(scope_of(layer="*"), make_context())

    assert result.comparisons[0].wildcard is True
    assert result.comparisons[0].reason == "layer * (no restriction)"


def test_ignored_dimensions_are_recorded_when_skip_is_explicit() -> None:
    scope = scope_of(layer="controller", tenant="acme", extra_policy="skip")

    result = match_scope(scope, make_context())

    assert result.matched is True
    assert result.ignored_dimensions == ("tenant",)
    assert "tenant (unknown dimension ignored by extra_policy=skip)" in result.reasons


def test_unknown_dimension_cannot_be_silently_ignored_by_default() -> None:
    with pytest.raises(Exception):
        scope_of(layer="controller", tenant="acme")


@pytest.mark.parametrize(
    ("dimension", "expected"),
    [
        ("language", "python"),
        ("layer", "controller"),
        ("module", None),
        ("operation", None),
        ("project", None),
        ("agent", None),
        ("unknown-dimension", None),
    ],
)
def test_dimension_value_reads_context(dimension: str, expected: object) -> None:
    assert dimension_value(make_context(), dimension) == expected


def test_dimension_accessors_cover_every_declared_dimension() -> None:
    from policy.models import KNOWN_SCOPE_DIMENSIONS

    assert set(DIMENSION_ACCESSORS) == set(KNOWN_SCOPE_DIMENSIONS)


def test_operation_dimension_uses_enum_value() -> None:
    context = make_context(operation="execute")

    assert dimension_value(context, "operation") == "execute"
    assert match_scope(scope_of(operation="execute"), context).matched is True


def test_compare_dimension_reports_missing_value_distinctly() -> None:
    comparison = compare_dimension("layer", "controller", None)

    assert comparison.matched is False
    assert comparison.actual is None
    assert comparison.reason == "layer <missing> != controller"


def test_matcher_does_not_mutate_inputs() -> None:
    scope = scope_of(layer=["controller", "service"])
    context = make_context()
    before_scope = scope.model_dump()
    before_context = context.model_dump()

    match_scope(scope, context)

    assert scope.model_dump() == before_scope
    assert context.model_dump() == before_context


def test_phase_0_skip_reason_string_is_preserved() -> None:
    """Phase 0 的可读原因格式保持不变，便于既有审计记录对比。"""

    rule = make_rule()

    assert skipped_rule_id(rule, make_context(layer="service")) == (
        "ARCH-001@1: layer service != controller"
    )
    assert skipped_rule_id(rule, make_context(language="go")) == (
        "ARCH-001@1: language go != python"
    )
    # 原因按 KNOWN_SCOPE_DIMENSIONS 的维度顺序输出，顺序稳定可比较
    assert skipped_rule_id(rule, make_context(layer="service", language="go")) == (
        "ARCH-001@1: language go != python; layer service != controller"
    )
    assert skipped_rule_id(rule, make_context()) is None


def test_list_scope_matches_every_listed_value() -> None:
    scope = scope_of(project=["shop", "crm"])

    assert match_scope(scope, make_context(project="shop")).matched is True
    assert match_scope(scope, make_context(project="crm")).matched is True
    assert match_scope(scope, make_context(project="blog")).matched is False
    assert match_scope(scope, make_context(project=None)).matched is False


def test_scope_result_is_serializable_for_audit() -> None:
    result = match_scope(scope_of(layer="controller"), make_context())
    payload = result.model_dump()

    assert payload["matched"] is True
    assert payload["comparisons"][0]["dimension"] == "layer"
    assert isinstance(PolicyContext.model_validate(make_context().model_dump()), PolicyContext)
