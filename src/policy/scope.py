"""Scope Matcher：判断规则的适用范围是否覆盖当前上下文。

首版匹配语义（对应 Phase 1 文档第 3 步）：

- 单维度取值：精确值、值列表、星号通配；
- 跨维度是 AND，同维度多值是 OR；
- 没有声明的维度表示"不限制"，而不是"匹配空值"；
- 声明了维度但上下文没有该值时不命中，并在 reasons 里说明 —— 宁可判"规则不相关"，
  也不猜一个值出来；
- 匹配结果附带每个维度的比较结果与 specificity（命中的非通配维度数）：
  specificity 只用于解释与排序，绝不参与决策。
"""

from __future__ import annotations

from typing import Callable, Mapping, Optional, Tuple

from .models import (
    KNOWN_SCOPE_DIMENSIONS,
    WILDCARD,
    PolicyContext,
    RuleScope,
    ScopeValue,
    StrictModel,
)

__all__ = [
    "DIMENSION_ACCESSORS",
    "DimensionComparison",
    "ScopeMatchResult",
    "compare_dimension",
    "dimension_value",
    "match_scope",
]

DIMENSION_ACCESSORS: Mapping[str, Callable[[PolicyContext], Optional[str]]] = {
    "language": lambda context: context.language,
    "layer": lambda context: context.layer,
    "module": lambda context: context.module,
    "operation": lambda context: None if context.operation is None else context.operation.value,
    "project": lambda context: context.project,
    "agent": lambda context: context.agent,
}


class DimensionComparison(StrictModel):
    """单个 scope 维度的比较结果：matched 决定规则是否相关，reason 说明为什么。"""

    dimension: str
    declared: ScopeValue
    actual: Optional[str] = None
    matched: bool
    wildcard: bool = False
    reason: str


class ScopeMatchResult(StrictModel):
    """一次 scope 匹配的完整解释。"""

    matched: bool
    reasons: Tuple[str, ...] = ()
    failures: Tuple[str, ...] = ()
    comparisons: Tuple[DimensionComparison, ...] = ()
    ignored_dimensions: Tuple[str, ...] = ()

    @property
    def specificity(self) -> int:
        """命中的非通配维度数；仅用于解释与排序，绝不参与决策。"""

        return sum(
            1
            for comparison in self.comparisons
            if comparison.matched and not comparison.wildcard
        )


def dimension_value(context: PolicyContext, dimension: str) -> Optional[str]:
    """读取上下文的某个维度值；没有该维度时返回 None（而不是空字符串）。"""

    accessor = DIMENSION_ACCESSORS.get(dimension)
    return None if accessor is None else accessor(context)


def _display(declared: ScopeValue) -> str:
    if declared == WILDCARD:
        return WILDCARD
    if isinstance(declared, tuple):
        return "[" + ", ".join(declared) + "]"
    return declared


def _is_wildcard(declared: ScopeValue) -> bool:
    return declared == WILDCARD or (isinstance(declared, tuple) and WILDCARD in declared)


def compare_dimension(
    dimension: str, declared: ScopeValue, actual: Optional[str]
) -> DimensionComparison:
    """比较一个维度：返回结构化结果与可读原因。"""

    if _is_wildcard(declared):
        return DimensionComparison(
            dimension=dimension,
            declared=declared,
            actual=actual,
            matched=True,
            wildcard=True,
            reason=f"{dimension} * (no restriction)",
        )

    if actual is None:
        return DimensionComparison(
            dimension=dimension,
            declared=declared,
            actual=None,
            matched=False,
            reason=f"{dimension} <missing> != {_display(declared)}",
        )

    if isinstance(declared, tuple):
        matched = actual in declared
        operator = "in" if matched else "not in"
        return DimensionComparison(
            dimension=dimension,
            declared=declared,
            actual=actual,
            matched=matched,
            reason=f"{dimension} {actual} {operator} {_display(declared)}",
        )

    matched = actual == declared
    return DimensionComparison(
        dimension=dimension,
        declared=declared,
        actual=actual,
        matched=matched,
        reason=f"{dimension} {actual} {'==' if matched else '!='} {declared}",
    )


def match_scope(scope: RuleScope, context: PolicyContext) -> ScopeMatchResult:
    """按维度顺序比较规则范围与上下文，返回可解释的匹配结果。"""

    declared_dimensions = scope.declared_dimensions
    comparisons: list[DimensionComparison] = []
    reasons: list[str] = []
    failures: list[str] = []

    for dimension in KNOWN_SCOPE_DIMENSIONS:
        if dimension not in declared_dimensions:
            continue
        comparison = compare_dimension(
            dimension, declared_dimensions[dimension], dimension_value(context, dimension)
        )
        comparisons.append(comparison)
        reasons.append(comparison.reason)
        if not comparison.matched:
            failures.append(comparison.reason)

    for dimension in scope.ignored_dimensions:
        reasons.append(f"{dimension} (unknown dimension ignored by extra_policy=skip)")

    return ScopeMatchResult(
        matched=not failures,
        reasons=tuple(reasons),
        failures=tuple(failures),
        comparisons=tuple(comparisons),
        ignored_dimensions=scope.ignored_dimensions,
    )
