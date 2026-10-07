"""Phase 5 判定层测试：docstring 证据、测试选择，以及"证据 → 违规"的引擎语义。"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from conftest import (
    VALIDATOR_PROJECT,
    make_checker_rule,
    make_context,
    validators_config,
)
from policy.check import render_text
from policy.engine import evaluate
from policy.evidence import (
    Blocker,
    DependencyFact,
    DependencyKind,
    DependencyResolution,
    EvidenceBundle,
    EvidenceLocation,
    PendingImplementation,
    SourceDigest,
    ValidationEvidence,
    ValidatorKind,
    ValidatorRecord,
    ValidatorStatus,
)
from policy.models import Decision, Evidence, RuleSet, Severity, ValidationResult, Violation
from validators.docstrings import missing_docstring_evidence
from validators.python_ast import parse_module
from validators.selection import list_test_files, select_tests

CONFIG = validators_config()
VALIDATOR = "py.docstring@1.0"


def bundle(**overrides: object) -> EvidenceBundle:
    payload: dict[str, object] = {"target": None}
    payload.update(overrides)
    return EvidenceBundle(**payload)  # type: ignore[arg-type]


def finding(rule_id: str, *, message: str = "缺少 docstring", line: int = 3) -> ValidationEvidence:
    return ValidationEvidence(
        validator_id="py.docstring",
        validator_version="1.0",
        checker="missing_docstring",
        rule_id=rule_id,
        rule_version=1,
        severity=Severity.WARNING,
        message=message,
        value="<module>",
        location=EvidenceLocation(file="src/shop/no_module_docstring.py", line=line, column=0),
    )


def record(
    validator_id: str = "py.docstring",
    *,
    status: ValidatorStatus = ValidatorStatus.OK,
    declared: tuple[str, ...] = ("missing_docstring",),
    critical: bool = True,
) -> ValidatorRecord:
    """ValidatorRecord 上的 `declared_checkers` 是"这个验证器声明负责哪些 checker"。

    它与 `EvidenceBundle.served_checkers`（**真的**服务过）是两个字段、两个含义（P7）：
    证据包里两个都叫 served_checkers 时，这里最容易把它们混着读。
    """

    return ValidatorRecord(
        validator_id=validator_id,
        validator_version="1.0",
        kind=ValidatorKind.BUILTIN,
        stage="docstring",
        status=status,
        critical=critical,
        declared_checkers=declared,
    )


# ------------------------------------------------------------------ docstring 验证器


def test_docstring_validator_reports_the_module_and_public_definitions() -> None:
    rule = make_checker_rule("DOC-001")
    facts = parse_module(
        "def public() -> None:" + chr(10) + "    pass" + chr(10)
    )

    evidence = missing_docstring_evidence(
        facts, target_path="src/shop/example.py", rules=(rule,), validator=VALIDATOR
    )

    values = {item.value for item in evidence}
    assert values == {"<module>", "public"}
    assert all(item.rule_id == "DOC-001" for item in evidence)
    assert all(item.checker == "missing_docstring" for item in evidence)
    assert evidence[1].location == EvidenceLocation(file="src/shop/example.py", line=1, column=0)


def test_docstring_validator_respects_targets_and_private_switch() -> None:
    methods_only = make_checker_rule(
        "DOC-002", body={"missing_docstring": {"targets": ["method"], "include_private": True}}
    )
    facts = parse_module(
        "class Holder:" + chr(10)
        + "    def _hidden(self) -> None:" + chr(10)
        + "        pass" + chr(10)
    )

    evidence = missing_docstring_evidence(
        facts, target_path="src/shop/example.py", rules=(methods_only,), validator=VALIDATOR
    )

    assert [item.value for item in evidence] == ["Holder._hidden"]


def test_docstring_validator_is_silent_when_everything_is_documented() -> None:
    rule = make_checker_rule("DOC-001")
    facts = parse_module(
        '"""模块。"""' + chr(10) + "def public() -> None:" + chr(10) + '    """有。"""' + chr(10)
    )

    assert (
        missing_docstring_evidence(
            facts, target_path="a.py", rules=(rule,), validator=VALIDATOR
        )
        == ()
    )


def test_docstring_evidence_is_sorted_and_deduplicated() -> None:
    rule = make_checker_rule("DOC-001")
    other = make_checker_rule("DOC-009", body={"missing_docstring": {"targets": ["module"]}})
    facts = parse_module("x = 1" + chr(10))

    evidence = missing_docstring_evidence(
        facts, target_path="a.py", rules=(rule, other), validator=VALIDATOR
    )

    assert [item.rule_id for item in evidence] == ["DOC-001", "DOC-009"]


# ------------------------------------------------------------------ 测试选择


def test_selection_prefers_the_related_test_file() -> None:
    selection = select_tests(
        target_path="src/shop/order_service.py",
        changed_files=("src/shop/order_service.py",),
        layout=CONFIG.layout,
        workspace=VALIDATOR_PROJECT,
        max_nodeids=10,
    )

    assert selection.level == "related"
    assert selection.nodeids == ("tests/test_order_service.py",)
    assert selection.missing == ()


def test_selection_escalates_to_the_suite_when_nothing_is_related() -> None:
    selection = select_tests(
        target_path="src/shop/order_repository.py",
        changed_files=("src/shop/order_repository.py",),
        layout=CONFIG.layout,
        workspace=VALIDATOR_PROJECT,
        max_nodeids=10,
    )

    assert selection.level == "suite"
    assert selection.nodeids == ("tests/test_order_service.py",)


def test_selection_reports_changed_production_files_without_tests(tmp_root: Path) -> None:
    workspace = tmp_root / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "lonely.py").write_text("x = 1" + chr(10), encoding="utf-8", newline="")

    selection = select_tests(
        target_path="src/lonely.py",
        changed_files=("src/lonely.py",),
        layout=CONFIG.layout,
        workspace=workspace,
        max_nodeids=10,
    )

    assert selection.level == "none"
    assert selection.missing == ("src/lonely.py",)


def test_selection_is_not_applicable_without_production_changes() -> None:
    selection = select_tests(
        target_path="docs/readme.md",
        changed_files=("docs/readme.md",),
        layout=CONFIG.layout,
        workspace=VALIDATOR_PROJECT,
        max_nodeids=10,
    )

    assert selection.level == "none"
    assert "没有生产文件" in selection.reason


def test_selection_caps_node_ids() -> None:
    selection = select_tests(
        target_path="src/shop/order_repository.py",
        changed_files=(),
        layout=CONFIG.layout,
        workspace=VALIDATOR_PROJECT,
        max_nodeids=0,
    )

    assert selection.nodeids == ()


def test_list_test_files_uses_the_declared_patterns() -> None:
    files = list_test_files(VALIDATOR_PROJECT, CONFIG.layout)

    assert files == ("tests/test_order_service.py",)


# ------------------------------------------------------------------ 引擎 × 证据


def test_finding_becomes_a_violation_with_location_and_rule_severity() -> None:
    rule = make_checker_rule("DOC-001", severity="error")
    rules = RuleSet(rules=(rule,), source_paths=("policies/coding/DOC-001.yaml",))
    evidence = bundle(
        evidence=(finding("DOC-001"),),
        validators=(record(),),
        served_checkers=("missing_docstring",),
    )

    result = evaluate(rules, make_context(), evidence=evidence)

    assert result.decision is Decision.BLOCK
    violation = result.violations[0]
    assert violation.severity is Severity.ERROR  # 严重级别来自规则，不来自证据
    assert violation.evidence.file == "src/shop/no_module_docstring.py"
    assert violation.evidence.line == 3
    assert "py.docstring@1.0" in (violation.evidence.detail or "")


def test_findings_for_other_rules_are_ignored() -> None:
    rule = make_checker_rule("DOC-001")
    rules = RuleSet(rules=(rule,), source_paths=())
    evidence = bundle(
        evidence=(finding("DOC-999"),),
        validators=(record(),),
        served_checkers=("missing_docstring",),
    )

    result = evaluate(rules, make_context(), evidence=evidence)

    assert result.decision is Decision.ALLOW


def test_critical_validator_failure_blocks_even_without_findings() -> None:
    rule = make_checker_rule("DOC-001")
    rules = RuleSet(rules=(rule,), source_paths=())
    evidence = bundle(
        validators=(record(status=ValidatorStatus.TIMEOUT),),
        blockers=(
            Blocker(
                validator_id="py.docstring",
                validator_version="1.0",
                status=ValidatorStatus.TIMEOUT,
                reason="超过超时 1000ms",
                checkers=("missing_docstring",),
            ),
        ),
    )

    result = evaluate(rules, make_context(), evidence=evidence)

    assert result.decision is Decision.BLOCK
    assert result.violations[0].severity is Severity.CRITICAL
    assert "关键验证器不可用" in result.violations[0].message


def test_a_blocker_without_checkers_is_unrepresentable() -> None:
    """没有 checker 的 blocker 直接不可表示。

    引擎只按 checker 查 blocker（EvidenceBundle.blocker_for），所以那种形态会让
    blocked=True 而永远命不中任何规则——载荷宣称有一个失败关闭点，实际谁都不会被它挡住，
    正是"看不懂就当通过"的变体。与 PendingImplementation 同口径：checkers 必须非空。
    """

    with pytest.raises(ValidationError):
        Blocker(
            validator_id="py.docstring",
            validator_version="1.0",
            status=ValidatorStatus.TIMEOUT,
            reason="超过超时 1000ms",
        )


def test_every_blocker_is_reachable_by_the_checkers_it_declares() -> None:
    """反向不变量：bundle 里的每个 blocker 都能被它声明的 checker 找回来。"""

    evidence = bundle(
        validators=(record(status=ValidatorStatus.TIMEOUT),),
        blockers=(
            Blocker(
                validator_id="py.docstring",
                validator_version="1.0",
                status=ValidatorStatus.TIMEOUT,
                reason="超过超时 1000ms",
                checkers=("missing_docstring",),
            ),
        ),
    )

    assert evidence.blocked is True
    assert evidence.blocker_for("missing_docstring") is not None


def test_checker_without_any_evidence_is_fail_closed() -> None:
    rule = make_checker_rule("DOC-001")
    rules = RuleSet(rules=(rule,), source_paths=())

    result = evaluate(rules, make_context(), evidence=bundle())

    assert result.decision is Decision.BLOCK
    assert "没有验证器为 checker missing_docstring 提供证据" in result.violations[0].message


def test_context_only_paths_record_evidence_checkers_as_skipped() -> None:
    rule = make_checker_rule("DOC-001")
    rules = RuleSet(rules=(rule,), source_paths=())

    result = evaluate(rules, make_context())

    assert result.decision is Decision.ALLOW
    assert result.matched_rules == ()
    assert [item.rule_id for item in result.skipped_rules] == ["DOC-001@1"]
    assert "验证器证据" in result.skipped_rules[0].reasons[0]


def test_forbidden_dependency_uses_evidence_facts_with_lines() -> None:
    rule = make_checker_rule("ARCH-001", checker="forbidden_dependency")
    rules = RuleSet(rules=(rule,), source_paths=())
    evidence = bundle(
        dependencies=(
            DependencyFact(
                name="repository",
                module="shop.order_repository",
                kind=DependencyKind.FROM_IMPORT,
                resolution=DependencyResolution.INTERNAL,
                file="src/shop/order_controller_bad.py",
                line=3,
                column=0,
                validator="py.depgraph@1.0",
            ),
        ),
        validators=(record("py.depgraph", declared=("forbidden_dependency",)),),
        served_checkers=("forbidden_dependency",),
    )

    result = evaluate(rules, make_context(), evidence=evidence)

    assert result.decision is Decision.BLOCK
    violation = result.violations[0]
    assert violation.evidence.line == 3
    assert violation.evidence.value == "repository"
    assert "py.depgraph@1.0" in (violation.evidence.detail or "")


def test_explicit_dependency_facts_keep_the_phase_zero_message() -> None:
    rule = make_checker_rule("ARCH-001", checker="forbidden_dependency")
    rules = RuleSet(rules=(rule,), source_paths=())
    evidence = bundle(
        dependencies=(
            DependencyFact(
                name="repository",
                kind=DependencyKind.DECLARED,
                resolution=DependencyResolution.DECLARED,
                file="src/shop/order_controller_bad.py",
                validator="cli.explicit@1.0",
            ),
        ),
        served_checkers=("forbidden_dependency",),
    )

    result = evaluate(rules, make_context(), evidence=evidence)

    assert result.violations[0].evidence.detail == "layer=controller 直接依赖 repository"
    assert result.violations[0].evidence.line is None


def test_violations_are_sorted_stably_regardless_of_evidence_order() -> None:
    rule = make_checker_rule("DOC-001")
    rules = RuleSet(rules=(rule,), source_paths=())
    first = finding("DOC-001", message="A", line=9)
    second = finding("DOC-001", message="B", line=2)

    forward = evaluate(
        rules,
        make_context(),
        evidence=bundle(
            evidence=(first, second),
            validators=(record(),),
            served_checkers=("missing_docstring",),
        ),
    )
    backward = evaluate(
        rules,
        make_context(),
        evidence=bundle(
            evidence=(second, first),
            validators=(record(),),
            served_checkers=("missing_docstring",),
        ),
    )

    assert forward.to_decision_dict() == backward.to_decision_dict()
    assert [item.evidence.line for item in forward.violations] == [2, 9]


def test_bundle_normalisation_deduplicates_and_sorts() -> None:
    duplicated = ValidationEvidence(
        validator_id="py.ast",
        validator_version="1.0",
        checker="style_lint",
        rule_id="STYLE-001",
        severity=Severity.WARNING,
        message="重复的诊断",
        value="E501",
    )
    raw = EvidenceBundle(
        evidence=(duplicated, duplicated),
        validators=(record("z.validator"), record("a.validator")),
        dependencies=(
            DependencyFact(
                name="service",
                kind=DependencyKind.IMPORT,
                resolution=DependencyResolution.INTERNAL,
                validator="py.depgraph@1.0",
            ),
            DependencyFact(
                name="os",
                kind=DependencyKind.IMPORT,
                resolution=DependencyResolution.STDLIB,
                validator="py.depgraph@1.0",
            ),
        ),
    )

    normalised = raw.normalize()

    assert len(normalised.evidence) == 1
    assert [item.validator for item in normalised.validators] == ["a.validator@1.0", "z.validator@1.0"]
    assert [fact.name for fact in normalised.dependencies] == ["service", "os"]
    assert normalised == raw.normalize()


def test_dedup_keys_cover_the_whole_payload_not_just_the_sort_key() -> None:
    """去重只许合并**逐字段相同**的记录。

    sort_key 是排序键、故意粗：DependencyFact 不看 module/column/validator/detail，
    ValidationEvidence 不看 severity/value/fix/detail/tool，PendingImplementation 不看 checkers。
    用它去重会把这些"只差一个载荷字段"的事实静默吞掉，而幸存的那一条还取决于适配器输出顺序——
    "同一份验证器输出 ⇒ 逐字节相同的证据"于是并不成立。
    """

    shared = dict(
        validator_id="py.docstring",
        validator_version="1.0",
        checker="missing_docstring",
        rule_id="DOC-001",
        rule_version=1,
        message="缺少 docstring",
    )
    raw = EvidenceBundle(
        target=None,
        dependencies=(
            DependencyFact(
                name="os",
                kind=DependencyKind.IMPORT,
                resolution=DependencyResolution.STDLIB,
                file="src/a.py",
                line=1,
                column=0,
                validator="py.depgraph@1.0",
            ),
            DependencyFact(
                name="os",
                kind=DependencyKind.IMPORT,
                resolution=DependencyResolution.STDLIB,
                file="src/a.py",
                line=1,
                column=12,
                validator="py.depgraph@1.0",
            ),
        ),
        evidence=(
            ValidationEvidence(**shared, severity=Severity.ERROR, value="a"),
            ValidationEvidence(**shared, severity=Severity.WARNING, value="a"),
        ),
        pending_implementation=(
            PendingImplementation(
                validator_id="tool.pytest",
                validator_version="1.0",
                checkers=("failing_tests",),
                test_modules=("tests/test_a.py",),
                missing_targets=("shop.order_service",),
                reason="收集期缺目标",
                fix="补上实现",
            ),
            PendingImplementation(
                validator_id="tool.pytest",
                validator_version="1.0",
                checkers=("missing_tests",),
                test_modules=("tests/test_a.py",),
                missing_targets=("shop.order_service",),
                reason="收集期缺目标",
                fix="补上实现",
            ),
        ),
    )

    normalised = raw.normalize()

    assert len(normalised.dependencies) == 2, "只差 column 的两条依赖事实不是同一条"
    assert len(normalised.evidence) == 2, "只差 severity 的两条证据不是同一条"
    assert len(normalised.pending_implementation) == 2, "只差 checkers 的两条待实现不是同一条"


def test_byte_identical_records_still_collapse() -> None:
    """真正逐字段相同的记录仍然合并——不然 normalize() 就不叫稳定化了。"""

    fact = DependencyFact(
        name="os",
        kind=DependencyKind.IMPORT,
        resolution=DependencyResolution.STDLIB,
        file="src/a.py",
        line=1,
        validator="py.depgraph@1.0",
    )

    assert len(EvidenceBundle(target=None, dependencies=(fact, fact)).normalize().dependencies) == 1


def test_source_digest_and_unknown_schema_are_rejected() -> None:
    digest = SourceDigest(file="a.py", language="python", sha256="sha256:" + "0" * 64, bytes=1, lines=1)
    assert digest.file == "a.py"

    with pytest.raises(Exception) as error:
        EvidenceBundle(schema_version="9.9")
    assert "未知证据协议版本" in str(error.value)


# ------------------------------------------------------------------ Q7：待实现 ≠ 失败

def pending(
    *,
    checkers: tuple[str, ...] = ("failing_tests",),
    test_modules: tuple[str, ...] = ("tests/test_audit_repository.py",),
    missing_targets: tuple[str, ...] = ("shop.audit_repository:AuditEntry",),
) -> PendingImplementation:
    """一条「待实现」记录：工具跑成了，但覆盖它的测试还跑不了。"""

    return PendingImplementation(
        validator_id="tool.pytest",
        validator_version="1.0",
        checkers=checkers,
        test_modules=test_modules,
        missing_targets=missing_targets,
        reason=(
            "选中的测试在收集期失败：项目内的 shop.audit_repository:AuditEntry "
            "在本次取证树里还不存在"
        ),
        fix="先把 AuditEntry 落地，再重跑取证",
    )


def test_pending_implementation_warns_instead_of_blocking() -> None:
    """Q7 的正面：规则自己是 error，但「待实现」的判定只能是 warning。

    P1：allow_with_warnings 尤其要能读出"被提醒过"——折叠成普通 allow 就等于把
    "覆盖它的测试还没能运行"这件事从账本上删掉。
    """

    rule = make_checker_rule("TESTING-002", checker="failing_tests", severity="error")
    rules = RuleSet(rules=(rule,), source_paths=())
    evidence = bundle(
        validators=(
            record("tool.pytest", declared=("failing_tests", "missing_tests")),
        ),
        # 没查成的 checker 不能记成查过了：missing_tests 由 selection 服务过，failing_tests 没有
        served_checkers=("missing_tests",),
        pending_implementation=(pending(),),
    )

    result = evaluate(rules, make_context(), evidence=evidence)

    assert result.decision is Decision.ALLOW_WITH_WARNINGS
    # J1(b)：pending **不是违规**——violations 里一条 pending 都没有。
    # 只断言这一半会被"把 pending 整条删掉"满足，所以下一行必须同时钉住"它还在"。
    assert result.violations == ()
    assert [item.canonical_id for item in result.pending_findings] == ["TESTING-002@1"]
    finding = result.pending_findings[0]
    assert finding.severity is Severity.WARNING  # 「待实现」不是违规，用 warning 表达
    assert "待实现" in finding.message
    assert "tests/test_audit_repository.py" in finding.message
    assert "shop.audit_repository:AuditEntry" in finding.message
    assert "本次写入被放行" in finding.message
    assert result.matched_rules == ("TESTING-002@1",)
    # severity_counts 是"违规"的分布：pending-only 因此是空的——这是对的口径，
    # 不是漏统计（文本输出另有一段 pending，见 test_pending_only_prints_a_reason_line）。
    assert result.severity_counts == {}


def test_pending_implementation_is_readable_from_the_decision_payload() -> None:
    rule = make_checker_rule("TESTING-002", checker="failing_tests", severity="error")
    rules = RuleSet(rules=(rule,), source_paths=())
    evidence = bundle(
        validators=(record("tool.pytest", declared=("failing_tests",)),),
        pending_implementation=(pending(),),
    )

    payload = evaluate(rules, make_context(), evidence=evidence).to_decision_dict()
    entry = payload["pending_findings"][0]

    assert payload["decision"] == "allow_with_warnings"
    # 两个通道在载荷里各占一个键，且**不是**同一份清单：violations 空、新通道非空。
    assert payload["violations"] == []
    assert entry["severity"] == "warning"
    assert "待实现" in entry["message"]
    assert entry["evidence"]["value"] == "shop.audit_repository:AuditEntry"


def test_the_pending_channel_refuses_a_blocking_severity() -> None:
    """构造期不变量：`pending_findings` 只承载 warning。

    为什么钉在**构造期**而不是靠调用方自觉：阻断判定只读 `violations`；如果 pending 能带
    error/critical，"从 violations 搬到 pending"就成了一次静默放宽（D-1(b) 要避免的正是这个）。
    构造期拒绝让它变成一个硬失败，而不是一个要靠人读出来才发现的口径缺失。
    """

    blocking = Violation(
        rule_id="TESTING-002",
        rule_version=1,
        severity=Severity.ERROR,
        message="待实现（这条不该能进 pending 通道）",
        evidence=Evidence(kind="failing_tests", subject="tests/t.py", value="shop.x:y"),
    )

    with pytest.raises(ValidationError) as error:
        ValidationResult(
            decision=Decision.BLOCK,
            request_id="req-1",
            pending_findings=(blocking,),
        )

    assert "pending_findings" in str(error.value)
    assert "error" in str(error.value)


def test_pending_only_prints_a_reason_line_instead_of_an_empty_one() -> None:
    """B5（台阶 3b）：pending-only 的决策在文本输出里必须**读得出理由**。

    改动前这里打出的是 `FAIL: decision=allow_with_warnings（required_action=None）`——
    括号里既不是级别分布、也不是审批门禁，读者从中读不出"为什么不是普通 allow"，
    而这一行本来正是给人看的那一行。这条断言只钉"读得出"，措辞可以变。
    """

    rule = make_checker_rule("TESTING-002", checker="failing_tests", severity="error")
    rules = RuleSet(rules=(rule,), source_paths=())
    evidence = bundle(
        validators=(record("tool.pytest", declared=("failing_tests",)),),
        pending_implementation=(pending(),),
    )
    context = make_context()

    text = render_text(context, rules, evaluate(rules, context, evidence=evidence))

    assert "decision=allow_with_warnings" in text
    # 空理由行必须消失：这一条是 B5 的全部要点。
    assert "required_action=None" not in text
    assert "pending_findings" in text
    assert "TESTING-002@1" in text
    assert "待实现" in text


def test_pending_implementation_does_not_silence_other_checkers() -> None:
    """待实现只覆盖它自己声明的那几个 checker：别的 checker 照旧失败关闭。"""

    rule = make_checker_rule("DOC-001")
    rules = RuleSet(rules=(rule,), source_paths=())
    evidence = bundle(
        validators=(record("tool.pytest", declared=("failing_tests",)),),
        pending_implementation=(pending(),),
    )

    result = evaluate(rules, make_context(), evidence=evidence)

    assert result.decision is Decision.BLOCK
    assert "没有验证器为 checker missing_docstring 提供证据" in result.violations[0].message


def test_a_blocker_still_wins_over_a_pending_note() -> None:
    """失败关闭优先：同一条 checker 上既有点阻断点又有一句"待实现"时，阻断必须赢。"""

    rule = make_checker_rule("TESTING-002", checker="failing_tests", severity="error")
    rules = RuleSet(rules=(rule,), source_paths=())
    evidence = bundle(
        validators=(record("tool.pytest", declared=("failing_tests",)),),
        blockers=(
            Blocker(
                validator_id="tool.pytest",
                validator_version="1.0",
                status=ValidatorStatus.TIMEOUT,
                reason="超过超时 120000ms，已终止进程树",
                checkers=("failing_tests",),
            ),
        ),
        pending_implementation=(pending(),),
    )

    result = evaluate(rules, make_context(), evidence=evidence)

    assert result.decision is Decision.BLOCK
    assert result.violations[0].severity is Severity.CRITICAL
    assert "关键验证器不可用" in result.violations[0].message


def test_pending_implementation_records_are_normalised_and_carried_in_the_payload() -> None:
    duplicated = pending()
    raw = EvidenceBundle(pending_implementation=(duplicated, duplicated))

    normalised = raw.normalize()

    assert len(normalised.pending_implementation) == 1
    assert normalised.pending_for("failing_tests") == (duplicated,)
    assert normalised.pending_for("missing_tests") == ()
    assert normalised.serves("failing_tests") is False
    assert raw.to_payload()["pending_implementation"][0]["test_modules"] == [
        "tests/test_audit_repository.py"
    ]
