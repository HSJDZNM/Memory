"""PEP 257 缺失 docstring 检查（内置验证器，不调用外部工具）。

查哪些对象由规则数据决定（module / class / function / method 与是否包含私有对象）；
本模块只负责“哪些定义缺 docstring”，严重级别与最终判定仍由 Policy Engine 决定。
"""

from __future__ import annotations

from typing import Sequence, Tuple

from policy.evidence import EvidenceLocation, ValidationEvidence
from policy.models import MissingDocstringSpec, Rule, Severity

from .python_ast import DefinitionFact, ModuleFacts

__all__ = ["missing_docstring_evidence"]


def missing_docstring_evidence(
    facts: ModuleFacts,
    *,
    target_path: str,
    rules: Sequence[Rule],
    validator: str,
) -> Tuple[ValidationEvidence, ...]:
    """按规则声明的目标集合产出缺失 docstring 的证据（同一对象只报一次）。"""

    validator_id, _, validator_version = validator.partition("@")
    evidence: list[ValidationEvidence] = []
    seen: set[Tuple[str, str, int]] = set()

    for rule in rules:
        body = rule.rule
        spec: MissingDocstringSpec = body.missing_docstring
        targets = {item.value for item in spec.targets}

        if "module" in targets and not facts.module_docstring:
            marker = (rule.id, "<module>", 1)
            if marker not in seen:
                seen.add(marker)
                evidence.append(
                    ValidationEvidence(
                        validator_id=validator_id,
                        validator_version=validator_version,
                        checker="missing_docstring",
                        rule_id=rule.id,
                        rule_version=rule.version,
                        severity=Severity.WARNING,
                        message="模块缺少 docstring（PEP 257）",
                        value="<module>",
                        location=EvidenceLocation(file=target_path, line=1, column=0),
                        fix="在文件首行加一段说明模块用途的 docstring",
                    )
                )

        for definition in facts.definitions:
            if definition.kind not in targets:
                continue
            if definition.private and not spec.include_private:
                continue
            if definition.docstring:
                continue
            marker = (rule.id, definition.qualified, definition.line)
            if marker in seen:
                continue
            seen.add(marker)
            evidence.append(_finding(rule, definition, target_path, validator_id, validator_version))

    return tuple(sorted(evidence, key=lambda item: item.sort_key))


def _finding(
    rule: Rule,
    definition: DefinitionFact,
    target_path: str,
    validator_id: str,
    validator_version: str,
) -> ValidationEvidence:
    kind_label = {"class": "类", "function": "函数", "method": "方法"}.get(
        definition.kind, definition.kind
    )
    return ValidationEvidence(
        validator_id=validator_id,
        validator_version=validator_version,
        checker="missing_docstring",
        rule_id=rule.id,
        rule_version=rule.version,
        severity=Severity.WARNING,
        message=kind_label + " " + definition.qualified + " 缺少 docstring（PEP 257）",
        value=definition.qualified,
        location=EvidenceLocation(
            file=target_path, line=definition.line, column=definition.column
        ),
        fix="为 " + definition.qualified + " 补一段说明其职责与副作用的 docstring",
    )
