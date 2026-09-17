"""查询规范化与受控 FTS 表达式构造。

安全前提（对应 Phase 3 文档的"查询安全测试"）：

1. 原始用户输入**永远**不进入 SQL 字符串，也不进入 FTS 表达式的语法位置：
   先做 Unicode NFKC 规范化、控制字符剔除、空白折叠与长度截断，再切成受控词项；
2. 词项只允许字母/数字/下划线/中日韩文字；引号、括号、NEAR、*、^、:、" 等 FTS 操作符
   在分词阶段就被丢弃，因此表达式里只剩"被双引号包裹的词项"与 OR；
3. 结构化过滤条件（数据集、层级、语言）来自调用方声明的受控字段，不来自文本；
4. 超长查询按字符上限截断并显式记 truncated，超量词项按词项上限丢弃并记 truncated。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional, Sequence, Tuple

from .chunker import CJK_RE, cjk_split
from .corpus import ExpansionLexicon
from .models import (
    AccessScope,
    CorpusPolicy,
    QueryError,
    QueryFilters,
    QueryPlan,
    RetrievalQuery,
)

__all__ = [
    "MAX_TOKEN_CHARS",
    "build_plan",
    "fts_expression",
    "fts_phrase",
    "normalize_query_text",
    "tokenize",
]

# 单个词项的字符上限：超长"词"通常是粘贴的 payload，直接丢弃而不是送去匹配。
MAX_TOKEN_CHARS = 48
_TOKEN_RE = re.compile(r"[0-9A-Za-z_]+|[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]+")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_query_text(raw: Optional[str], *, max_chars: int) -> Tuple[str, bool]:
    """规范化自由文本：NFKC、去控制字符、折叠空白、按字符上限截断。"""

    if raw is None:
        return "", False
    if not isinstance(raw, str):
        raise QueryError(f"查询文本必须是字符串或 null，得到 {type(raw).__name__}")

    text = unicodedata.normalize("NFKC", raw)
    text = _CONTROL_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text, False

    clipped = text[:max_chars]
    # 尽量在词边界截断，避免把一个词切成一半（切了也没关系，词项仍受控）。
    cut = clipped.rfind(" ")
    if cut > max_chars // 2:
        clipped = clipped[:cut]
    return clipped.strip(), True


def tokenize(text: str) -> Tuple[str, ...]:
    """把文本切成受控词项：ASCII 词 + 中日韩词组（词组按整段保留，索引侧逐字切分）。"""

    terms: list[str] = []
    for match in _TOKEN_RE.finditer(text):
        token = match.group(0)
        if len(token) > MAX_TOKEN_CHARS:
            continue
        if token.isascii():
            token = token.lower()
            if len(token) < 2 or token.isdigit():
                # 单字符英文词与纯数字噪声大，且对规范检索没有信息量。
                continue
        if token not in terms:
            terms.append(token)
    return tuple(terms)


def fts_phrase(term: str) -> str:
    """把一个词项变成 FTS5 字符串字面量：始终加双引号，内部引号再加倍转义。

    中日韩词组额外做逐字切分（与索引侧 search_text 用同一套切分）。
    """

    value = term
    if CJK_RE.search(value):
        value = cjk_split(value)
    return '"' + value.replace('"', '""') + '"'


def fts_expression(terms: Sequence[str]) -> str:
    """受控表达式：只由 OR 连接的双引号词项组成，没有任何其它 FTS 语法。"""

    return " OR ".join(fts_phrase(term) for term in terms if term)


def _structural_terms(query: RetrievalQuery) -> Tuple[str, ...]:
    """结构化字段作为**软词项**：它们提高排序相关性，但从不单独构成过滤条件。"""

    terms: list[str] = []
    if query.language:
        terms.append(query.language)
    if query.module:
        terms.append(query.module)
    if query.file:
        stem = query.file.rsplit("/", 1)[-1]
        if "." in stem:
            stem = stem.rsplit(".", 1)[0]
        for token in tokenize(stem):
            terms.append(token)
    return tuple(dict.fromkeys(terms))


def build_plan(
    query: RetrievalQuery,
    *,
    scope: AccessScope,
    policy: CorpusPolicy,
    lexicon: Optional[ExpansionLexicon] = None,
    text: Optional[str] = None,
) -> QueryPlan:
    """构造查询计划：文本 → 词项（含扩展与结构化软词项）→ 过滤条件 → 表达式。"""

    if not isinstance(query, RetrievalQuery):
        raise QueryError(f"build_plan 只接受 RetrievalQuery，得到 {type(query).__name__}")
    if not isinstance(scope, AccessScope):
        raise QueryError(f"build_plan 只接受 AccessScope，得到 {type(scope).__name__}")

    raw_text = query.text if text is None else text
    normalized, text_truncated = normalize_query_text(raw_text, max_chars=policy.max_query_chars)

    text_terms = tokenize(normalized)
    expanded = lexicon.expand(normalized) if lexicon is not None else ()
    structural = _structural_terms(query)

    ordered: list[str] = []
    for term in (*text_terms, *expanded, *structural):
        if term and term not in ordered:
            ordered.append(term)
    truncated = text_truncated
    if len(ordered) > policy.max_query_terms:
        ordered = ordered[: policy.max_query_terms]
        truncated = True

    filters = QueryFilters(
        datasets=query.datasets,
        tiers=tuple(item.value for item in query.tiers),
        languages=query.languages,
        scope_datasets=tuple(sorted(scope.datasets)),
    )
    limit = query.limit if query.limit is not None else policy.top_k
    return QueryPlan(
        text=normalized,
        terms=tuple(ordered),
        expanded_terms=tuple(expanded),
        structural_terms=structural,
        filters=filters,
        fts_expression=fts_expression(ordered),
        limit=limit,
        truncated=truncated,
    )
