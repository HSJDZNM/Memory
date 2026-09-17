"""Phase 3 契约测试：检索端口的返回形状、状态语义与确定性。

两份实现（FTS5 基线、向量端口）必须遵守同一份契约：调用方不需要知道用的是哪一种。
"""

from __future__ import annotations

from typing import Any, Callable

import pytest

from retrieval.corpus import load_expansion
from retrieval.indexer import ingest
from retrieval.models import (
    AccessScope,
    RetrievalMethod,
    RetrievalQuery,
    RetrievalResult,
    RetrievalStatus,
    UnavailableReason,
)
from retrieval.retriever import FtsRetriever, ResultCache
from retrieval.store import ChunkStore
from retrieval.vector import VectorRetriever

from conftest import REPO_ROOT, load_fixture_corpus

pytestmark = pytest.mark.contract

PAYLOAD_KEYS = {
    "status",
    "query",
    "plan",
    "method",
    "index_version",
    "results",
    "reason",
    "detail",
    "request_id",
    "trace_id",
}
RESULT_KEYS = {
    "chunk_id",
    "document_id",
    "dataset",
    "source_path",
    "source_url",
    "license",
    "tier",
    "visibility",
    "title",
    "heading_path",
    "heading_anchor",
    "ordinal",
    "rank",
    "score",
    "method",
    "text",
    "text_hash",
    "char_count",
    "truncated",
    "oversized",
}


@pytest.fixture()
def indexed(tmp_root):
    loaded = load_fixture_corpus(tmp_root)
    store = ChunkStore(tmp_root / "index.sqlite3")
    ingest(loaded, store, repo_root=tmp_root)
    lexicon = load_expansion(REPO_ROOT / "knowledge" / "query_expansion.yaml", repo_root=REPO_ROOT)
    scope = AccessScope(subject="contract-user", datasets=frozenset(loaded.manifest.dataset_names))
    yield loaded, store, lexicon, scope
    store.close()


def fts_factory(loaded, store, lexicon, scope):
    return FtsRetriever(store, policy=loaded.policy, lexicon=lexicon, cache=ResultCache())


def vector_factory(loaded, store, lexicon, scope):
    retriever = VectorRetriever(store, policy=loaded.policy, lexicon=lexicon, cache=ResultCache())
    retriever.build()
    return retriever


IMPLEMENTATIONS: tuple[tuple[RetrievalMethod, Callable[..., Any]], ...] = (
    (RetrievalMethod.FTS5, fts_factory),
    (RetrievalMethod.VECTOR, vector_factory),
)


@pytest.mark.parametrize(("method", "factory"), IMPLEMENTATIONS)
def test_payload_shape_is_stable(indexed, method, factory) -> None:
    loaded, store, lexicon, scope = indexed
    result = factory(loaded, store, lexicon, scope).retrieve(
        RetrievalQuery(text="review checklist", limit=3), scope
    )
    assert isinstance(result, RetrievalResult)
    assert set(result.model_dump()) == PAYLOAD_KEYS
    assert result.method is method
    assert result.status is RetrievalStatus.OK
    assert result.index_version == store.index_version
    for item in result.results:
        assert set(item.model_dump()) == RESULT_KEYS


@pytest.mark.parametrize(("method", "factory"), IMPLEMENTATIONS)
def test_ranks_are_sequential_sources_are_complete(indexed, method, factory) -> None:
    loaded, store, lexicon, scope = indexed
    result = factory(loaded, store, lexicon, scope).retrieve(
        RetrievalQuery(text="review checklist tests", limit=4), scope
    )
    assert [item.rank for item in result.results] == list(range(1, len(result.results) + 1))
    for item in result.results:
        assert item.chunk_id and item.document_id
        assert item.source_path and item.source_url and item.license and item.text_hash
        assert item.text and item.char_count == len(item.text)
        assert item.method is method


@pytest.mark.parametrize(("method", "factory"), IMPLEMENTATIONS)
def test_same_query_twice_returns_identical_ranking(indexed, method, factory) -> None:
    loaded, store, lexicon, scope = indexed
    retriever = factory(loaded, store, lexicon, scope)
    first = retriever.retrieve(RetrievalQuery(text="acceptance checklist", limit=5), scope)
    second = retriever.retrieve(RetrievalQuery(text="acceptance checklist", limit=5), scope)
    assert [(item.rank, item.chunk_id, item.score) for item in first.results] == [
        (item.rank, item.chunk_id, item.score) for item in second.results
    ]


@pytest.mark.parametrize(("method", "factory"), IMPLEMENTATIONS)
def test_empty_query_returns_explicit_status(indexed, method, factory) -> None:
    loaded, store, lexicon, scope = indexed
    result = factory(loaded, store, lexicon, scope).retrieve(RetrievalQuery(text="   "), scope)
    assert result.status is RetrievalStatus.EMPTY
    assert result.reason is UnavailableReason.EMPTY_QUERY
    assert result.results == ()


@pytest.mark.parametrize(("method", "factory"), IMPLEMENTATIONS)
def test_no_results_is_explicit_and_never_fabricated(indexed, method, factory) -> None:
    loaded, store, lexicon, scope = indexed
    result = factory(loaded, store, lexicon, scope).retrieve(
        RetrievalQuery(text="zzzzz-nonexistent-token"), scope
    )
    assert result.status is RetrievalStatus.EMPTY
    assert result.reason is UnavailableReason.NO_RESULTS
    assert result.results == ()


@pytest.mark.parametrize(("method", "factory"), IMPLEMENTATIONS)
def test_scope_without_datasets_is_access_denied(indexed, method, factory) -> None:
    loaded, store, lexicon, _ = indexed
    empty_scope = AccessScope(subject="nobody", datasets=frozenset())
    result = factory(loaded, store, lexicon, empty_scope).retrieve(
        RetrievalQuery(text="review checklist"), empty_scope
    )
    assert result.status is RetrievalStatus.EMPTY
    assert result.reason is UnavailableReason.ACCESS_DENIED
    assert result.results == ()


@pytest.mark.parametrize(("method", "factory"), IMPLEMENTATIONS)
def test_plan_is_echoed_with_filters(indexed, method, factory) -> None:
    loaded, store, lexicon, scope = indexed
    result = factory(loaded, store, lexicon, scope).retrieve(
        RetrievalQuery(text="checklist", datasets=("guides",), language="PYTHON"), scope
    )
    assert result.plan is not None
    assert result.plan.text == "checklist"
    assert result.plan.filters.datasets == ("guides",)
    assert result.plan.filters.scope_datasets == ("adversarial", "guides", "restricted-docs")
    assert "python" in result.plan.terms


@pytest.mark.parametrize(("method", "factory"), IMPLEMENTATIONS)
def test_request_and_trace_ids_are_preserved(indexed, method, factory) -> None:
    loaded, store, lexicon, scope = indexed
    result = factory(loaded, store, lexicon, scope).retrieve(
        RetrievalQuery(text="checklist", request_id="req-1", trace_id="trace-1"), scope
    )
    assert result.request_id == "req-1"
    assert result.trace_id == "trace-1"


@pytest.mark.parametrize(("method", "factory"), IMPLEMENTATIONS)
def test_retrieve_rejects_wrong_types(indexed, method, factory) -> None:
    loaded, store, lexicon, scope = indexed
    retriever = factory(loaded, store, lexicon, scope)
    with pytest.raises(Exception):
        retriever.retrieve("not a query", scope)  # type: ignore[arg-type]
    with pytest.raises(Exception):
        retriever.retrieve(RetrievalQuery(text="x"), "not a scope")  # type: ignore[arg-type]


def test_vector_retriever_without_embeddings_is_unavailable(tmp_root) -> None:
    loaded = load_fixture_corpus(tmp_root)
    store = ChunkStore(tmp_root / "index.sqlite3")
    try:
        ingest(loaded, store, repo_root=tmp_root)
        retriever = VectorRetriever(store, policy=loaded.policy)
        scope = AccessScope(subject="u", datasets=frozenset(loaded.manifest.dataset_names))
        result = retriever.retrieve(RetrievalQuery(text="checklist"), scope)
        assert result.status is RetrievalStatus.UNAVAILABLE
        assert result.reason is UnavailableReason.INDEX_MISSING
        assert result.results == ()
    finally:
        store.close()


def test_result_cache_key_covers_subject_permissions_index_and_plan(indexed) -> None:
    loaded, store, lexicon, scope = indexed
    cache = ResultCache()
    retriever = FtsRetriever(store, policy=loaded.policy, lexicon=lexicon, cache=cache)
    query = RetrievalQuery(text="review checklist")
    retriever.retrieve(query, scope)
    hits = cache.hits
    retriever.retrieve(query, scope)
    assert cache.hits == hits + 1  # 同一主体、同一权限、同一索引版本 -> 命中缓存

    other_scope = AccessScope(
        subject="other-user",
        datasets=scope.datasets,
    )
    retriever.retrieve(query, other_scope)
    assert cache.hits == hits + 1  # 换主体必然换键

    narrowed = AccessScope(subject=scope.subject, datasets=frozenset({"guides"}))
    retriever.retrieve(query, narrowed)
    assert cache.hits == hits + 1  # 换权限集合必然换键
