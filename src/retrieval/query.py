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
# 词项 = 一段连续的"词字符"（字母/数字/下划线，含中日韩文字）。用 Unicode 词类而不是
# [0-9A-Za-z_]：后者会把带变音符的拉丁词切成碎片——tokenize("café") 得到 ("caf",)、
# tokenize("naïve") 得到 ("na","ve")（"ï" 整个丢掉），而这些碎片照样进 OR 表达式、
# 照样能匹配到无关文本（复核发现 L4 query.py:41）。索引侧本来就把整篇原文交给 FTS5 的
# unicode61（按 Unicode 字母切词），两端口径一致才谈得上"命中"。
_TOKEN_RE = re.compile(r"\w+")
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

    return _tokenize_with_stats(text)[0]


def _tokenize_with_stats(text: str) -> Tuple[Tuple[str, ...], bool]:
    """分词并报告有没有丢东西：有超长词项被丢弃时返回 dropped=True。

    这个信号必须能传到 QueryPlan.truncated：一段没有空格的中文粘贴在 FTS 侧就是一个
    超长 token，整条查询可能因此**一个词都不剩**；此时 truncated=False 会让调用方以为
    "这条查询被完整地搜过了"，而实际上它什么都没搜。
    """

    terms: list[str] = []
    dropped = False
    for match in _TOKEN_RE.finditer(text):
        token = match.group(0)
        if len(token) > MAX_TOKEN_CHARS:
            dropped = True
            continue
        if token.isascii():
            token = token.lower()
            if len(token) < 2 or token.isdigit():
                # 单字符英文词与纯数字噪声大，且对规范检索没有信息量。
                continue
        if token not in terms:
            terms.append(token)
    return tuple(terms), dropped


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


def _controlled_term(value: str, *, max_chars: int) -> bool:
    """**扩展短语**在进 FTS 表达式之前必须满足的字符类与长度约束。

    允许字母 / 数字 / 下划线 / 连字符 / 中日韩文字，以及短语内部的空格。连字符是有意的：
    声明里的术语本来就有 human-in-the-loop / multi-tenant 这类写法，而 fts_phrase 会把整条
    短语加引号——连字符在 FTS 侧只是分词符，不是语法。长度上界用 policy.max_query_chars：
    比整个查询预算还长的"词"没有意义。控制字符、标点与超长串一律拒绝。
    """

    if not value or len(value) > max_chars:
        return False
    return all(
        char in " _-"
        or (char.isascii() and char.isalnum())
        or bool(CJK_RE.fullmatch(char))
        for char in value
    )


def _structural_terms(
    query: RetrievalQuery, *, max_chars: int
) -> Tuple[Tuple[str, ...], bool]:
    """结构化字段作为**软词项**：它们提高排序相关性，但从不单独构成过滤条件。

    这些值必须过与文本同一套受控分词：它们最终会进 fts_expression，而本模块的安全前提是
    "词项只允许字母/数字/下划线/中日韩文字、且受长度上限约束"——上游只做 strip/lower，
    含空格的值会变成多词短语、超长值绕过词项上限、控制字符也一路带到表达式里。
    """

    terms: list[str] = []
    dropped = False
    for value in (query.language, query.module):
        if not value:
            continue
        found, lost = _tokenize_with_stats(value)
        terms.extend(found)
        dropped = dropped or lost
    if query.file:
        stem = query.file.rsplit("/", 1)[-1]
        if "." in stem:
            stem = stem.rsplit(".", 1)[0]
        found, lost = _tokenize_with_stats(stem)
        terms.extend(found)
        dropped = dropped or lost
    return tuple(dict.fromkeys(terms)), dropped


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

    text_terms, text_dropped = _tokenize_with_stats(normalized)

    # 扩展词项同样要过受控词项检查（load_expansion 只守声明文件；本模块允许直接构造
    # ExpansionLexicon，那条路径不该能把句子 / 超长串 / 控制字符带进表达式）。
    expanded_terms: list[str] = []
    expanded_dropped = False
    for term in lexicon.expand(normalized) if lexicon is not None else ():
        if term in expanded_terms:
            continue
        if _controlled_term(term, max_chars=policy.max_query_chars):
            expanded_terms.append(term)
        else:
            expanded_dropped = True
    expanded = tuple(expanded_terms)
    structural, structural_dropped = _structural_terms(
        query, max_chars=policy.max_query_chars
    )

    ordered: list[str] = []
    for term in (*text_terms, *expanded, *structural):
        if term and term not in ordered:
            ordered.append(term)
    # 字符截断、超长词项被丢弃、词项数超上限——三种"这次搜索比原始请求窄"都要记 truncated。
    truncated = text_truncated or text_dropped or expanded_dropped or structural_dropped
    if len(ordered) > policy.max_query_terms:
        ordered = ordered[: policy.max_query_terms]
        truncated = True
    # 截断之后，expanded_terms / structural_terms 必须与**生效的**词项一致：它们是计划的一部分
    # （消费者用它们做加权、高亮与"为什么搜到这个"，而 fts_expression 只由 ordered 构造）。
    # 不裁的话计划会广告一批不在 terms / 表达式里的词——读了它的人会以为这些词生效了。
    effective = set(ordered)
    expanded = tuple(term for term in expanded if term in effective)
    structural = tuple(term for term in structural if term in effective)

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
        expanded_terms=expanded,
        structural_terms=structural,
        filters=filters,
        fts_expression=fts_expression(ordered),
        limit=limit,
        truncated=truncated,
    )
