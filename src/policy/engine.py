"""Policy Engine：范围匹配、决策聚合与解释信息。

引擎只读取传入的 PolicyContext：不访问全局状态、不调用 LLM、不读文件系统。
证据全部来自给定上下文，因此相同上下文与相同规则集必然得到相同结果。

Phase 1 相对 Phase 0 的变化：

- 匹配交给 scope.match_scope，支持多值与通配，并保留每个维度的比较原因；
- 决策表加入 critical 与 required_action=approval；
- 结果记录 skipped_rules（为什么没参与判断）、trace_id 与规则集哈希，
  让"规则是否相关"与"是否违规"两件事分开可解释；
- 违反规则集身份与输入顺序无关：matched/skipped/violations 都按稳定顺序输出。
"""

from __future__ import annotations

from typing import Iterator, Sequence

from .context import normalize_context
from .models import (
    Decision,
    EnforcementType,
    Evidence,
    PolicyContext,
    RequiredAction,
    Rule,
    RuleSet,
    Severity,
    SkippedRule,
    ValidationResult,
    Violation,
    expected_decision,
)
from .scope import ScopeMatchResult, match_scope

__all__ = [
    "SUPPORTED_CHECKERS",
    "EngineError",
    "evaluate",
    "explain",
    "insufficient_context_violation",
    "rule_matches_context",
    "skipped_rule_id",
]

SUPPORTED_CHECKERS = frozenset({"forbidden_dependency"})


class EngineError(Exception):
    """规则声明了本引擎无法执行的检查器（失败策略：未知执行方式不得放行）。"""


def rule_matches_context(rule: Rule, context: PolicyContext) -> bool:
    """判断规则的 scope 是否覆盖当前上下文。"""

    return match_scope(rule.scope, context).matched


def explain(rule: Rule, context: PolicyContext) -> ScopeMatchResult:
    """给出单条规则的匹配解释；供 CLI 与审计展示，不改变任何决策。"""

    return match_scope(rule.scope, normalize_context(context))


def skipped_rule_id(rule: Rule, context: PolicyContext) -> str | None:
    """规则未匹配时给出可读原因；匹配时返回 None。"""

    result = match_scope(rule.scope, context)
    if result.matched:
        return None
    return f"{rule.canonical_id}: " + "; ".join(result.failures)


def _iter_matching_rules(rules: RuleSet, context: PolicyContext) -> Iterator[Rule]:
    for rule in rules.rules:
        if rule_matches_context(rule, context):
            yield rule


def evaluate(rules: RuleSet, context: PolicyContext) -> ValidationResult:
    """对固定上下文稳定地产生 allow / allow_with_warnings / block。"""

    canonical = normalize_context(context)
    matched: list[Rule] = []
    skipped: list[SkippedRule] = []

    for rule in rules.rules:
        result = match_scope(rule.scope, canonical)
        if result.matched:
            matched.append(rule)
        else:
            skipped.append(SkippedRule(rule_id=rule.canonical_id, reasons=result.failures))

    for rule in matched:
        _assert_executable(rule)

    violations: list[Violation] = []
    for rule in matched:
        violations.extend(_violations_for(rule, canonical))
    violations.sort(key=lambda item: item.sort_key)

    approval_rules = sorted(
        rule.canonical_id for rule in matched if rule.enforcement.requires_approval
    )
    required_action = RequiredAction.APPROVAL if approval_rules else None

    return ValidationResult(
        decision=expected_decision(tuple(violations), required_action=required_action),
        request_id=canonical.request_id,
        trace_id=canonical.trace_id,
        rule_set_hash=rules.identity,
        matched_rules=tuple(sorted(rule.canonical_id for rule in matched)),
        skipped_rules=tuple(sorted(skipped, key=lambda item: item.sort_key)),
        violations=tuple(violations),
        required_action=required_action,
    )


def _assert_executable(rule: Rule) -> None:
    if rule.enforcement.type is not EnforcementType.DETERMINISTIC:
        raise EngineError(
            f"{rule.canonical_id}: 不支持的 enforcement {rule.enforcement.type.value!r}"
        )
    if rule.enforcement.checker not in SUPPORTED_CHECKERS:
        raise EngineError(
            f"{rule.canonical_id}: 未知 checker {rule.enforcement.checker!r}，"
            "拒绝在未知执行方式下放行"
        )


def _violations_for(rule: Rule, context: PolicyContext) -> list[Violation]:
    """ARCH-001 形态：上下文依赖命中 forbidden_dependency 时产生 violation。"""

    forbidden = set(rule.rule.forbidden_dependency)
    if not forbidden:
        return []

    hits = [dependency for dependency in context.dependencies if dependency in forbidden]
    return [
        Violation(
            rule_id=rule.id,
            rule_version=rule.version,
            severity=rule.severity,
            message=rule.message,
            evidence=Evidence(
                kind="dependency",
                subject=context.file,
                value=dependency,
                file=context.file,
                detail=f"layer={context.layer} 直接依赖 {dependency}",
            ),
        )
        for dependency in hits
    ]


def insufficient_context_violation(rule: Rule, *, request_id: str, detail: str) -> ValidationResult:
    """安全关键上下文缺失时的 fail-closed 结果（失败策略：block）。"""

    violation = Violation(
        rule_id=rule.id,
        rule_version=rule.version,
        severity=Severity.CRITICAL,
        message=f"安全关键上下文缺失，按失败策略阻断：{detail}",
        evidence=Evidence(
            kind="context", subject=rule.canonical_id, value="missing", detail=detail
        ),
    )
    return ValidationResult(
        decision=Decision.BLOCK,
        request_id=request_id,
        matched_rules=(rule.canonical_id,),
        violations=(violation,),
    )
