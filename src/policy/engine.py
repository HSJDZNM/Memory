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
  进入 skipped_rules 并写明"需要验证器证据"，这是显式记录，不是静默放行；
- 第三种状态（Q7）：「工具跑成了、但这次的树还在构建中」（pending_implementation）——
  它不是"证据到手"（不进 served_checkers），也不是"证据没拿到"（不产生 Blocker），
  判定侧产出 warning 级 violation，decision=allow_with_warnings。
"""

from __future__ import annotations

from typing import Optional

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

    # 两个发现通道分开收（台阶 3b / D-1(b)）：violations 是"真的报了违规"，
    # pending_findings 是"这次没能查成（待实现）"。分流点在 handler 的返回值里，
    # 引擎不按 message 文本或 severity 去猜某一条属于哪个通道。
    violations: list[Violation] = []
    pending_findings: list[Violation] = []
    for rule in evaluated:
        checker = rule.enforcement.checker or ""
        if bundle is not None:
            blocker = bundle.blocker_for(checker)
            if blocker is not None:
                violations.append(blocker_violation(rule, blocker))
                continue
            # 三种状态必须分开（Q7）：证据到手（serves）/ 这次还查不了（pending_implementation）/
            # 证据没拿到（两者都不是 → 失败关闭）。中间那一种**不进** served_checkers，
            # 也**不产生** Blocker；判定函数会为它产出一条 pending_findings（severity 恒为 warning），
            # decision 因此是 allow_with_warnings，而不是普通 allow。
            pending = bundle.pending_for(checker)
            if not pending and not bundle.serves(checker):
                violations.append(uncovered_checker_violation(rule, checker))
                continue
        findings = checker_handler(checker)(rule, canonical, bundle)
        violations.extend(findings.violations)
        pending_findings.extend(findings.pending_findings)
    # 两个通道各排各的（同一把键 Violation.sort_key）：混排会让"这条属于哪个通道"
    # 变成读者要重新猜的事，而这两个通道的语义恰好是本次要分开的东西。
    violations.sort(key=lambda item: item.sort_key)
    pending_findings.sort(key=lambda item: item.sort_key)

    # 审批门禁由**范围命中**决定，与"这次有没有带证据包"无关：只给上下文的调用路径会把
    # 证据类 checker 的规则挪进 extra_skipped，如果门禁从 evaluated 派生，同一条规则就会
    # "带证据包 → block + approval"、"不带 → 普通 allow" —— 同一份规则两套结论，而文档承诺的是
    # "一旦范围命中，审批标记就转成 block + approval，与 violations 无关"（tech-detail 01 章）。
    # 用 matched（scope 命中）而不是 evaluated（本次真的判了）：门禁是前置条件，不是发现。
    approval_rules = sorted(
        rule.canonical_id for rule in matched if rule.enforcement.requires_approval
    )
    required_action = RequiredAction.APPROVAL if approval_rules else None

    return ValidationResult(
        decision=expected_decision(
            tuple(violations),
            required_action=required_action,
            pending=tuple(pending_findings),
        ),
        request_id=canonical.request_id,
        trace_id=canonical.trace_id,
        rule_set_hash=rules.identity,
        matched_rules=tuple(sorted(rule.canonical_id for rule in evaluated)),
        skipped_rules=tuple(sorted([*skipped, *extra_skipped], key=lambda item: item.sort_key)),
        violations=tuple(violations),
        pending_findings=tuple(pending_findings),
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
