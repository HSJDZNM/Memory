"""P5：CLI 的检查量摘要（check_volume）必须从数据算出来，而不是解析原因字符串。

07 号报告 P5 的现象：缺 `--operation` 时 TESTING-001/002 只是进 `skipped_rules`，
判定照样 allow、退出码不变——两个 allow 在读数上长得一模一样。
`build_check_volume` 把"这次到底查了多少"变成结构化读数：

- 参与 / 跳过 / 跳过原因 / 跳过级别 / 有阻断力的跳过，全部从规则集、scope 与上下文算出来；
- `missing_dimensions` 回答"规则要、上下文没有"的维度（例如 `operation`），`complete` 由它决定；
- 真的服务过的 checker 只认证据报告（`EvidenceBundle.served_checkers`），不认声明。

模型与引擎都是真实的（`policy.models` / `policy.engine`），只有规则集与上下文是本地构造的。
"""

from __future__ import annotations

from conftest import make_checker_rule, make_context, make_rule
from policy.check import (
    CHECK_VOLUME_NOTE,
    SKIP_REASON_EVIDENCE_NOT_COLLECTED,
    SKIP_REASON_MISSING_DIMENSION,
    SKIP_REASON_SCOPE_MISMATCH,
    build_check_volume,
)
from policy.engine import evaluate
from policy.evidence import EvidenceBundle
from policy.models import Decision, RuleSet

TESTING_SCOPE = {"language": "python", "operation": ["create", "edit"]}


def testing_rules() -> RuleSet:
    """两条 error 级的测试规则（声明了 operation 维度）+ 一条不受层限制的入口规则。"""

    return RuleSet(
        rules=(
            make_checker_rule("TESTING-001", checker="missing_tests", scope=TESTING_SCOPE),
            make_checker_rule("TESTING-002", checker="failing_tests", scope=TESTING_SCOPE),
            make_rule("ARCH-001", scope={"language": "python", "layer": "controller"}),
        )
    )


def test_missing_operation_makes_the_check_incomplete() -> None:
    """缺 operation：判定照样 allow，但 check_volume 必须说清有两条规则根本没被查。"""

    rules = testing_rules()
    context = make_context()
    result = evaluate(rules, context)
    volume = build_check_volume(rules, context, result)

    assert result.decision is Decision.ALLOW
    assert volume["rule_count"] == 3
    assert volume["effective_rule_count"] == 1
    assert volume["skipped_rule_count"] == 2
    assert volume["effective_rule_count"] < volume["rule_count"]
    assert volume["skipped_by_reason"][SKIP_REASON_MISSING_DIMENSION] == 2
    assert volume["skipped_by_reason"][SKIP_REASON_SCOPE_MISMATCH] == 0
    assert volume["skipped_by_reason"][SKIP_REASON_EVIDENCE_NOT_COLLECTED] == 0
    assert volume["skipped_by_severity"] == {"error": 2}
    assert volume["blocking_capable_skipped"] == 2
    assert volume["missing_dimensions"] == ["operation"]
    assert volume["complete"] is False
    assert volume["note"] == CHECK_VOLUME_NOTE
    assert "skipped" in volume["note"] and "passed" in volume["note"]


def test_declaring_the_operation_makes_the_check_complete() -> None:
    """给了 operation：不再缺维度，`complete` 为真——即使规则因为没证据而进 skipped。

    `complete` 只回答"调用方声明得够不够全"；缺证据是另一条轴（`evidence_not_collected`），
    两者的区分正是"跳过 ≠ 通过"与"缺维度 ≠ 缺证据"两句话的落点。
    """

    rules = testing_rules()
    context = make_context(operation="edit")
    result = evaluate(rules, context)
    volume = build_check_volume(rules, context, result)

    assert volume["missing_dimensions"] == []
    assert volume["complete"] is True
    assert volume["skipped_rule_count"] == 2
    assert volume["skipped_by_reason"][SKIP_REASON_EVIDENCE_NOT_COLLECTED] == 2
    assert volume["skipped_by_reason"][SKIP_REASON_MISSING_DIMENSION] == 0


def test_scope_mismatch_is_not_reported_as_a_missing_dimension() -> None:
    """层不匹配是"规则不相关"，不是"调用方没声明"：不许混成一个桶。"""

    rules = RuleSet(
        rules=(make_rule("ARCH-001", scope={"language": "python", "layer": "controller"}),)
    )
    context = make_context(layer="service", operation="edit")
    result = evaluate(rules, context)
    volume = build_check_volume(rules, context, result)

    assert volume["skipped_by_reason"][SKIP_REASON_SCOPE_MISMATCH] == 1
    assert volume["skipped_by_reason"][SKIP_REASON_MISSING_DIMENSION] == 0
    assert volume["missing_dimensions"] == []
    assert volume["complete"] is True
    assert volume["blocking_capable_skipped"] == 1


def test_the_classification_does_not_read_the_reason_text() -> None:
    """把 reasons 换成"看起来匹配"的文本，分类与 missing_dimensions 必须不变。

    这条挡的是"解析 skipped reason 字符串来归类"的实现：那种实现会相信原因文本写了什么，
    而"为什么跳过"是 scope 与上下文的**结构化比较**产物，文本只是给人看的渲染。
    """

    rules = testing_rules()
    context = make_context()
    result = evaluate(rules, context)
    forged = result.model_copy(
        update={
            "skipped_rules": tuple(
                item.model_copy(update={"reasons": ("operation edit in [create, edit]",)})
                for item in result.skipped_rules
            )
        }
    )
    volume = build_check_volume(rules, context, forged)

    assert volume["missing_dimensions"] == ["operation"]
    assert volume["complete"] is False
    assert volume["skipped_by_reason"][SKIP_REASON_MISSING_DIMENSION] == 2


def test_served_checkers_come_from_the_evidence_report() -> None:
    """真的服务过的 checker 只认证据报告：声明过不等于跑过（P7 的同一口径）。"""

    rules = testing_rules()
    context = make_context(operation="edit")
    bundle = EvidenceBundle(served_checkers=("failing_tests", "missing_tests"))
    result = evaluate(rules, context, evidence=bundle)
    volume = build_check_volume(rules, context, result, evidence=bundle)

    assert volume["served_checkers"] == ["failing_tests", "missing_tests"]
    assert volume["skipped_rule_count"] == 0
    assert volume["effective_rule_count"] == 3
    assert volume["complete"] is True
    assert volume["blocking_capable_skipped"] == 0
