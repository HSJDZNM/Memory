"""Policy Engine：范围匹配、决策聚合与解释信息。

引擎只读取传入的 PolicyContext 与（可选的）证据包：不访问全局状态、不调用 LLM、
不读文件系统、不执行外部工具。证据由 Validator 端口生产，引擎只负责判定，
因此相同上下文 + 相同规则集 + 相同证据必然得到相同结果。

Phase 5 相对 Phase 1–4 的变化：

- 判定按 enforcement.checker 分派（policy.checkers），引擎里不再内联某一条规则怎么判；
- 可选的 evidence（EvidenceBundle）作为判定输入：ARCH-001 的依赖完全来自
  AST / 依赖图证据，证据里的文件与行列会写进 violation；
- 失败关闭：关键验证器不可用（缺失 / 超时 / 崩溃 / 版本不符 / 输出非法）时，
  需要它的规则以 critical 违规阻断，不被同批的其他 PASS 抵消；
- 仅有上下文的调用路径（Phase 2 的 Hook）拿不到代码证据时，证据类 checker 的规则
  进入 skipped_rules 并写明"需要验证器证据"，这是显式记录，不是静默放行。
"""

from __future__ import annotations

from typing import Iterator, Optional, Sequence

from .checkers import (
    CONTEXT_CHECKERS,
    SUPPORTED_CHECKERS,
    blocker_violation,
    checker_handler,
    uncovered_checker_violation,
)
from .context import normalize_context
from .evidence import EvidenceBundle
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
    "matching_rules",
    "rule_matches_context",
    "skipped_rule_id",
]


# 证据类 checker 在"没有验证器流水线"的调用路径上的跳过原因（写进 skipped_rules）。
EVIDENCE_NOT_COLLECTED = (
    "checker {checker} 需要验证器证据；本次调用只提供上下文，没有验证器流水线"
)


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


def matching_rules(rules: RuleSet, context: PolicyContext) -> tuple[tuple[Rule, ...], tuple[SkippedRule, ...]]:
    """按 scope 分出"参与判断"与"未参与判断"的规则，并校验 checker 受支持。

    这是流水线选择验证器的输入：只有 scope 命中的规则才需要证据。
    """

    canonical = normalize_context(context)
    matched: list[Rule] = []
    skipped: list[SkippedRule] = []
    for rule in rules.rules:
        result = match_scope(rule.scope, canonical)
        if result.matched:
            _assert_executable(rule)
            matched.append(rule)
        else:
            skipped.append(SkippedRule(rule_id=rule.canonical_id, reasons=result.failures))
    return tuple(matched), tuple(sorted(skipped, key=lambda item: item.sort_key))


def evaluate(
    rules: RuleSet,
    context: PolicyContext,
    *,
    evidence: Optional[EvidenceBundle] = None,
) -> ValidationResult:
    """对固定上下文稳定地产生 allow / allow_with_warnings / block。

    evidence=None 表示调用方只提供上下文（Phase 0–4 的契约）；此时证据类 checker
    的规则不会被判定，而是记进 skipped_rules 并写明原因。
    """

    canonical = normalize_context(context)
    bundle = None if evidence is None else evidence.normalize()

    matched, skipped = matching_rules(rules, canonical)
    evaluated: list[Rule] = []
    extra_skipped: list[SkippedRule] = []
    for rule in matched:
        checker = rule.enforcement.checker or ""
        if bundle is None and checker not in CONTEXT_CHECKERS:
            extra_skipped.append(
                SkippedRule(
                    rule_id=rule.canonical_id,
                    reasons=(EVIDENCE_NOT_COLLECTED.format(checker=checker),),
                )
            )
            continue
        evaluated.append(rule)

    violations: list[Violation] = []
    for rule in evaluated:
        checker = rule.enforcement.checker or ""
        if bundle is not None:
            blocker = bundle.blocker_for(checker)
            if blocker is not None:
                violations.append(blocker_violation(rule, blocker))
                continue
            if not bundle.serves(checker):
                violations.append(uncovered_checker_violation(rule, checker))
                continue
        violations.extend(checker_handler(checker)(rule, canonical, bundle))
    violations.sort(key=lambda item: item.sort_key)

    approval_rules = sorted(
        rule.canonical_id for rule in evaluated if rule.enforcement.requires_approval
    )
    required_action = RequiredAction.APPROVAL if approval_rules else None

    return ValidationResult(
        decision=expected_decision(tuple(violations), required_action=required_action),
        request_id=canonical.request_id,
        trace_id=canonical.trace_id,
        rule_set_hash=rules.identity,
        matched_rules=tuple(sorted(rule.canonical_id for rule in evaluated)),
        skipped_rules=tuple(sorted([*skipped, *extra_skipped], key=lambda item: item.sort_key)),
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
