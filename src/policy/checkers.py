"""checker 分派：把确定性证据转成 Violation（Phase 5）。

引擎不再内联"某条规则怎么判"，而是按 enforcement.checker 查表：

- 上下文类 checker（CONTEXT_CHECKERS）：Phase 0–4 的契约，仅凭 PolicyContext 就能判；
- 证据类 checker（EVIDENCE_CHECKERS）：必须由验证器流水线给出证据，没有证据就不能判。

新增 checker 必须同时出现在这里与 validation/validators.yaml 的验证器声明里：
前者决定"引擎会不会用"，后者决定"谁来产生证据"。未知 checker 一律 EngineError，
绝不静默忽略或默认放行。

依赖类 checker 的匹配语义只有一条（两条判定路径共用同一个函数，不许各写一套）：

- 规则的 forbidden 标识与依赖标识**整名相等**就命中；
- 否则按"词"比较：把依赖标识的点分路径逐段再按 "_" 切开，forbidden 的词序列
  连续出现即命中。理由：Python 模块名与文件名共用同一套词，项目档案里的组件模式
  正是按这条路走的（**/*_repository.py → 组件 repository），因此
  "forbidden: repository" 必须命中 shop.order_repository —— 只比整名会让最常见
  的那种写法漏判，而那正是"看起来在管、实际什么都没查"。
- "证明不了"必须显式拒绝：预执行路径（没有模块索引、变更片段不一定完整）
  用 UNPROVEN_DEPENDENCY_TOKENS 里的保留标记表达"依赖集无法证明"，
  依赖类 checker 见到标记即按失败策略阻断（critical），不与其他 PASS 相抵。
"""

from __future__ import annotations

from typing import Callable, List, Mapping, Optional, Tuple

from .evidence import Blocker, DependencyFact, EvidenceBundle, ValidationEvidence
from .models import (
    Evidence,
    PolicyContext,
    Rule,
    Severity,
    Violation,
    canonical_identifier,
)

__all__ = [
    "CONTEXT_CHECKERS",
    "EVIDENCE_CHECKERS",
    "SUPPORTED_CHECKERS",
    "UNPROVEN_CHANGED_TEXT",
    "UNPROVEN_DEPENDENCY_TOKENS",
    "UNPROVEN_DYNAMIC_IMPORT",
    "blocker_violation",
    "checker_handler",
    "dependency_forbidden",
    "dependency_words",
    "uncovered_checker_violation",
    "unproven_dependency_violation",
]

# 仅凭上下文即可判定的 checker（Phase 0–4 的契约；Phase 5 起默认证据来自 AST / 依赖图）。
CONTEXT_CHECKERS = frozenset({"forbidden_dependency"})

# 必须有验证器证据的 checker；没有证据时代码把规则记进 skipped_rules 并写明原因。
EVIDENCE_CHECKERS = frozenset(
    {"missing_docstring", "style_lint", "type_check", "missing_tests", "failing_tests"}
)

SUPPORTED_CHECKERS = CONTEXT_CHECKERS | EVIDENCE_CHECKERS

# 依赖无法证明时的保留标记：它们不是依赖名，而是"这一类依赖判定做不了"的显式信号。
# 由 Adapter（生产者）登记进 PolicyContext.dependencies，由依赖类 checker 消费。
# 为什么走 dependencies 维度而不是新增上下文字段：PolicyContext 是 Phase 1 冻结的协议，
# 而 dependencies 本来就是"这次变更引入了什么"的维度；标记在审计里可见
# （dsh Hook 把 dependencies 原样写进审计记录），因此它不是"静默跳过"。
UNPROVEN_DYNAMIC_IMPORT = "<unproven-dynamic-import>"
UNPROVEN_CHANGED_TEXT = "<unparseable-changed-text>"
UNPROVEN_DEPENDENCY_TOKENS = frozenset({UNPROVEN_DYNAMIC_IMPORT, UNPROVEN_CHANGED_TEXT})

# 每种"证明不了"的中文理由：写进 violation，人一眼能看出是哪一类。
UNPROVEN_REASONS: Mapping[str, str] = {
    UNPROVEN_DYNAMIC_IMPORT: "变更文本出现动态导入，但目标不是字符串字面量：依赖集无法静态确定",
    UNPROVEN_CHANGED_TEXT: (
        "变更片段无法作为模块或缩进块解析：依赖集无法证明（解析失败不等于没有依赖）"
    ),
}

Handler = Callable[[Rule, PolicyContext, Optional[EvidenceBundle]], List[Violation]]


def dependency_words(value: str) -> Tuple[str, ...]:
    """依赖标识 → 词序列：点分路径的每一段再按 "_" 切开。

    为什么按 "_" 切而不是只比整名：Python 模块名与文件名共用同一套词，项目档案里的
    组件模式也是按这条路走的（**/*_repository.py → 组件 repository）。因此
    shop.order_repository 与 AST 路径解析出的组件名 repository 落在同一个词上，
    两条判定路径对同一条规则才会给出同一个结论。
    """

    words: list[str] = []
    for segment in canonical_identifier(value).split("."):
        words.extend(part for part in segment.split("_") if part)
    return tuple(words)


def dependency_forbidden(forbidden: str, *values: Optional[str]) -> bool:
    """forbidden 标识是否命中这些依赖标识（整名相等，或词序列连续出现）。

    调用方必须把**同一个依赖的全部标识**传进来（证据路径是 name + module，
    上下文路径是依赖名本身），两条路径因此共用一套语义。
    """

    token = canonical_identifier(forbidden)
    if not token:
        return False
    token_words = dependency_words(token)
    for value in values:
        if value is None:
            continue
        canonical = canonical_identifier(value)
        if canonical == token:
            return True
        if not token_words:
            continue
        words = dependency_words(canonical)
        width = len(token_words)
        for start in range(len(words) - width + 1):
            if words[start : start + width] == token_words:
                return True
    return False


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
        detail = (
            item.validator
            + " / "
            + tool_version
            + "（退出码 "
            + str(item.tool.exit_code)
            + "）: "
            + detail
        )
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


def unproven_dependency_violation(
    rule: Rule, context: PolicyContext, markers: Tuple[str, ...]
) -> Violation:
    """依赖无法证明：按失败策略阻断（critical），并写明是哪一类"证明不了"。

    用 critical 而不是规则自己的 severity：这类结论说明**依赖集本身不成立**，
    不是"检查发现了问题"，同批里的其他 PASS 不允许把它抵消掉。
    """

    reasons = "；".join(UNPROVEN_REASONS.get(item, item) for item in markers)
    return Violation(
        rule_id=rule.id,
        rule_version=rule.version,
        severity=Severity.CRITICAL,
        message="依赖无法证明，拒绝在证明不了的情况下判定通过：" + reasons,
        evidence=Evidence(
            kind="dependency",
            subject=context.file,
            value=",".join(markers),
            file=context.file,
            detail=f"layer={context.layer}；标记 {list(markers)} 由依赖证据生产者登记",
        ),
    )


def _forbidden_dependency(
    rule: Rule, context: PolicyContext, evidence: Optional[EvidenceBundle]
) -> List[Violation]:
    """ARCH-001 形态：依赖标识命中 forbidden_dependency 即违规。

    三条路径共用同一套匹配语义（policy.checkers.dependency_forbidden）：

    - 证据路径：AST / 依赖图交出来的事实，name 与 module 都要参与比较；
    - 上下文路径（Phase 0–4 契约）：依赖来自上下文里显式声明的 dependencies；
    - "证明不了"：上下文带着 UNPROVEN_DEPENDENCY_TOKENS 里的标记时失败关闭 ——
      解析失败不等于没有依赖（AGENTS.md 第 20 条）。
    """

    forbidden = tuple(rule.rule.forbidden_dependency)
    if not forbidden:
        return []

    unproven = tuple(
        sorted(name for name in context.dependencies if name in UNPROVEN_DEPENDENCY_TOKENS)
    )
    if unproven:
        return [unproven_dependency_violation(rule, context, unproven)]

    if evidence is None:
        hits = [
            name
            for name in context.dependencies
            if any(dependency_forbidden(token, name) for token in forbidden)
        ]
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
        if not any(
            dependency_forbidden(token, fact.name, fact.module) for token in forbidden
        ):
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
