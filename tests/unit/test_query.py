"""Phase 3 查询规范化与 FTS 表达式测试：注入安全、长度限制、扩展词与确定性。"""

from __future__ import annotations

import re

import pytest

from retrieval.corpus import ExpansionLexicon, ExpansionTerm
from retrieval.models import AccessScope, CorpusPolicy, Operation, QueryError, RetrievalQuery, Tier
from retrieval.query import build_plan, fts_expression, fts_phrase, normalize_query_text, tokenize

LEXICON = ExpansionLexicon(
    version=1,
    terms=(
        ExpansionTerm(zh=("代码评审",), en=("code review",)),
        ExpansionTerm(zh=("评审",), en=("review",)),
        ExpansionTerm(zh=("检索",), en=("retrieval", "rag")),
    ),
)

SCOPE = AccessScope(subject="local-user", datasets=frozenset({"guides", "adversarial"}))
QUOTED_TERM = re.compile(r'^"(?:[^"]|"")*"$')


def plan(text: str | None, **overrides):
    query = RetrievalQuery(text=text, **overrides)
    return build_plan(query, scope=SCOPE, policy=CorpusPolicy(), lexicon=LEXICON)


def test_normalize_applies_nfkc_and_collapses_whitespace() -> None:
    text, truncated = normalize_query_text("  ＡＢＣ   code \t review \n\n ", max_chars=100)
    assert text == "ABC code review"
    assert truncated is False


def test_normalize_drops_control_characters() -> None:
    text, _ = normalize_query_text("review\x00\x1fcode", max_chars=100)
    assert text == "review code"


def test_normalize_truncates_at_character_budget() -> None:
    raw = " ".join(["token"] * 100)
    text, truncated = normalize_query_text(raw, max_chars=40)
    assert truncated is True
    assert len(text) <= 40
    assert not text.endswith(" ")


def test_normalize_rejects_non_string() -> None:
    with pytest.raises(QueryError):
        normalize_query_text(123, max_chars=10)


def test_tokenize_drops_short_and_numeric_tokens_but_keeps_cjk() -> None:
    assert tokenize("a go 42 review 代码评审") == ("go", "review", "代码评审")


def test_fts_phrase_is_always_a_quoted_literal() -> None:
    assert fts_phrase("code review") == '"code review"'
    assert fts_phrase('x"y') == '"x""y"'


def test_cjk_terms_become_character_split_phrases() -> None:
    # 索引侧把中日韩文字逐字切开，查询侧必须用同一口径，否则永远匹配不上。
    assert fts_phrase("代码评审") == '"代 码 评 审"'


HOSTILE_INPUTS = (
    'review" OR "secret',
    "review AND (policy OR rule)",
    "NEAR(review policy, 5)",
    "review* ^policy tag:secret",
    "'; DROP TABLE chunks_fts; --",
    "review)) UNION SELECT 1 --",
    "documents MATCH 'x'",
    "\u4ee3\u7801\u8bc4\u5ba1" * 40,
)


@pytest.mark.parametrize("hostile", HOSTILE_INPUTS)
def test_hostile_input_cannot_change_the_expression_structure(hostile: str) -> None:
    plan_value = plan(hostile)
    expressions = [plan_value.fts_expression]
    assert expressions[0] == fts_expression(plan_value.terms)
    for expression in expressions:
        if not expression:
            continue
        for piece in expression.split(" OR "):
            assert QUOTED_TERM.match(piece), f"表达式里出现了非受控片段: {piece!r}"
        # FTS 语法字符只能出现在引号内部（作为被匹配的文本），不能作为操作符生效。
        for operator in ("*", "^", "(", ")", ":"):
            assert operator not in expression


def test_plain_query_keeps_expected_terms() -> None:
    value = plan("code review checklist")
    assert value.terms == ("code", "review", "checklist")
    assert value.fts_expression == '"code" OR "review" OR "checklist"'
    assert value.expanded_terms == ()


def test_expansion_matches_longest_term_only() -> None:
    value = plan("代码评审需要检查哪些方面")
    assert "code review" in value.expanded_terms
    assert "review" not in value.expanded_terms
    # 原查询文本作为一个中文词组保留，供索引侧逐字匹配（项目内的中文文档）。
    assert "代码评审需要检查哪些方面" in value.terms


def test_expansion_is_reusable_for_other_languages() -> None:
    value = plan("检索失败")
    assert "retrieval" in value.expanded_terms
    assert "rag" in value.expanded_terms


def test_structural_fields_add_soft_terms_and_filters() -> None:
    value = plan(
        "checklist",
        file="src/order/controller.py",
        module="order",
        language="Python",
        operation=Operation.EDIT,
        datasets=("guides",),
        tiers=(Tier.GUIDANCE,),
    )
    assert value.structural_terms == ("python", "order", "controller")
    assert value.terms[:3] == ("checklist", "python", "order")
    assert value.filters.datasets == ("guides",)
    assert value.filters.tiers == ("guidance",)
    assert value.filters.scope_datasets == ("adversarial", "guides")


def test_term_cap_truncates_and_flags() -> None:
    policy = CorpusPolicy(max_query_terms=4)
    value = build_plan(
        RetrievalQuery(text="alpha beta gamma delta epsilon zeta"),
        scope=SCOPE,
        policy=policy,
        lexicon=None,
    )
    assert value.terms == ("alpha", "beta", "gamma", "delta")
    assert value.truncated is True
    assert value.fts_expression == '"alpha" OR "beta" OR "gamma" OR "delta"'


def test_empty_text_produces_empty_plan() -> None:
    value = plan("   ")
    assert value.is_empty is True
    assert value.terms == ()
    assert value.fts_expression == ""


def test_limit_defaults_to_policy_top_k_and_can_be_overridden() -> None:
    assert plan("review").limit == CorpusPolicy().top_k
    assert plan("review", limit=2).limit == 2


def test_plan_is_deterministic() -> None:
    first = plan("代码评审 code review")
    second = plan("代码评审 code review")
    assert first.model_dump_json() == second.model_dump_json()


def test_build_plan_rejects_wrong_types() -> None:
    with pytest.raises(QueryError):
        build_plan("not a query", scope=SCOPE, policy=CorpusPolicy())  # type: ignore[arg-type]
    with pytest.raises(QueryError):
        build_plan(RetrievalQuery(text="x"), scope="not a scope", policy=CorpusPolicy())  # type: ignore[arg-type]
