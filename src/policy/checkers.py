"""checker 分派：把确定性证据转成 Violation（Phase 5）。

引擎不再内联"某条规则怎么判"，而是按 enforcement.checker 查表：

- 上下文类 checker（CONTEXT_CHECKERS）：Phase 0–4 的契约，仅凭 PolicyContext 就能判；
- 证据类 checker（EVIDENCE_CHECKERS）：必须由验证器流水线给出证据，没有证据就不能判。

新增 checker 必须同时出现在这里与 validation/validators.yaml 的验证器声明里：
前者决定"引擎会不会用"，后者决定"谁来产生证据"。未知 checker 一律 EngineError，
绝不静默忽略或默认放行。
"""

from __future__ import annotations

from typing import Callable, List, Mapping, Optional

from .evidence import Blocker, DependencyFact, EvidenceBundle, ValidationEvidence
from .models import Evidence, PolicyContext, Rule, Severity, Violation

__all__ = [
    "CONTEXT_CHECKERS",
    "EVIDENCE_CHECKERS",
    "SUPPORTED_CHECKERS",
    "blocker_violation",
    "checker_handler",
    "uncovered_checker_violation",
]

# 仅凭上下文即可判定的 checker（Phase 0–4 的契约；Phase 5 起默认证据来自 AST / 依赖图）。
CONTEXT_CHECKERS = frozenset({"forbidden_dependency"})

# 必须有验证器证据的 checker；没有证据时代码把规则记进 skipped_rules 并写明原因。
EVIDENCE_CHECKERS = frozenset(
    {"missing_docstring", "style_lint", "type_check", "missing_tests", "failing_tests"}
)

SUPPORTED_CHECKERS = CONTEXT_CHECKERS | EVIDENCE_CHECKERS

Handler = Callable[[Rule, PolicyContext, Optional[EvidenceBundle]], List[Violation]]


def _finding_violations(
    rule: Rule, context: PolicyContext, evidence: Optional[EvidenceBundle]
) -> List[Violation]:
    """证据类 checker 的统一映射：只认绑定到本规则的证据。"""

    if evidence is None:
        return []

    violations: List[Violation] = []
    for item in evidence.evidence:
        if item.rule_id != rule.id:
            continue
        violations.append(_violation_from_finding(rule, context, item))
    return violations


def _violation_from_finding(
    rule: Rule, context: PolicyContext, item: ValidationEvidence
) -> Violation:
    location = item.location
    detail = item.detail or item.message
    if item.tool is not None:
        tool_version = item.tool.tool
        if item.tool.version:
            tool_version += "=" + item.tool.version
        detail = item.validator + " / " + tool_version + "（退出码 " + str(item.tool.exit_code) + "）: " + detail
    else:
        detail = item.validator + ": " + detail
    if item.fix:
        detail = detail + "；建议修复：" + item.fix
    return Violation(
        rule_id=rule.id,
        rule_version=rule.version,
        severity=rule.severity,
        message=rule.message,
        evidence=Evidence(
            kind=rule.enforcement.checker or "validator",
            subject=context.file if location is None else location.file,
            value=item.value or item.checker,
            file=None if location is None else location.file,
            line=None if location is None else location.line,
            detail=detail,
        ),
    )


def _forbidden_dependency(
    rule: Rule, context: PolicyContext, evidence: Optional[EvidenceBundle]
) -> List[Violation]:
    """ARCH-001 形态：证据里的依赖名命中 forbidden_dependency 即违规。

    没有证据时退回 Phase 0–4 的契约：依赖来自上下文里显式声明的 dependencies。
    """

    forbidden = set(rule.rule.forbidden_dependency)
    if not forbidden:
        return []

    if evidence is None:
        hits = [name for name in context.dependencies if name in forbidden]
        return [
            Violation(
                rule_id=rule.id,
                rule_version=rule.version,
                severity=rule.severity,
                message=rule.message,
                evidence=Evidence(
                    kind="dependency",
                    subject=context.file,
                    value=name,
                    file=context.file,
                    detail=f"layer={context.layer} 直接依赖 {name}",
                ),
            )
            for name in hits
        ]

    violations: List[Violation] = []
    for fact in evidence.dependencies:
        if fact.name not in forbidden:
            continue
        violations.append(
            Violation(
                rule_id=rule.id,
                rule_version=rule.version,
                severity=rule.severity,
                message=rule.message,
                evidence=Evidence(
                    kind="dependency",
                    subject=fact.file or context.file,
                    value=fact.name,
                    file=fact.file or context.file,
                    line=fact.line,
                    detail=_dependency_detail(context, fact),
                ),
            )
        )
    return violations


def _dependency_detail(context: PolicyContext, fact: DependencyFact) -> str:
    """依赖证据的可读说明：显式声明的依赖保持 Phase 0–4 的原文，其余附上来源。"""

    if fact.resolution.value == "declared":
        return f"layer={context.layer} 直接依赖 {fact.name}"
    parts = [f"layer={context.layer} 直接依赖 {fact.name}", fact.kind.value, fact.resolution.value]
    if fact.module:
        parts.append(fact.module)
    parts.append(fact.validator)
    return " · ".join(parts)


def checker_handler(checker: str) -> Handler:
    """按 checker 取判定函数；未知 checker 由引擎报错，这里只负责查表。"""

    return _HANDLERS[checker]


_HANDLERS: Mapping[str, Handler] = {
    "forbidden_dependency": _forbidden_dependency,
    "missing_docstring": _finding_violations,
    "style_lint": _finding_violations,
    "type_check": _finding_violations,
    "missing_tests": _finding_violations,
    "failing_tests": _finding_violations,
}


def blocker_violation(rule: Rule, blocker: Blocker) -> Violation:
    """关键验证器不可用时失败关闭：以 critical 表达，保证任何严重级别配置都阻断。"""

    return Violation(
        rule_id=rule.id,
        rule_version=rule.version,
        severity=Severity.CRITICAL,
        message=(
            "关键验证器不可用，按失败策略阻断：" + blocker.validator
            + " 状态 " + blocker.status.value + "（" + blocker.reason + "）"
        ),
        evidence=Evidence(
            kind="validator",
            subject=blocker.validator,
            value=blocker.status.value,
            detail=blocker.reason,
        ),
    )


def uncovered_checker_violation(rule: Rule, checker: str) -> Violation:
    """有规则要用某个 checker，却没有任何验证器为它产出证据——同样失败关闭。"""

    return Violation(
        rule_id=rule.id,
        rule_version=rule.version,
        severity=Severity.CRITICAL,
        message="没有验证器为 checker " + checker + " 提供证据，拒绝在没有证据的情况下判定通过",
        evidence=Evidence(
            kind="validator", subject=rule.canonical_id, value=checker, detail="uncovered_checker"
        ),
    )
