"""KnowledgeRetriever 端口与 FTS5 实现。

端口返回值固定包含：chunk_id、document_id、来源（路径/URL/许可）、标题路径、排名、
检索方式与原文。相似度分数只用于**内部排序**：它不参与授权，也不改变决策，
Policy Engine 永远看不到它。

失败语义（失败策略：检索不可用不得回退到"模型记忆里的规范"）：

- 空查询 / 无结果 → status=empty + 显式原因；
- 索引库缺失、执行失败 → status=unavailable + 显式原因，绝不编造来源；
- 调用方没有授予任何数据集 → status=empty + access_denied（不是"没有结果"）。
"""

from __future__ import annotations

from hashlib import sha256
from typing import Optional, Protocol, Tuple

from .corpus import ExpansionLexicon
from .models import (
    AccessScope,
    CorpusPolicy,
    QueryError,
    RetrievalMethod,
    RetrievalQuery,
    RetrievalResult,
    RetrievalStatus,
    RetrievedChunk,
    StoreError,
    UnavailableReason,
)
from .query import build_plan
from .store import ChunkStore, SearchHit

__all__ = ["FtsRetriever", "KnowledgeRetriever", "ResultCache", "hits_to_chunks"]


class KnowledgeRetriever(Protocol):
    """检索端口：任何实现都必须返回同一形状的结果（来源完整、排名稳定）。"""

    method: RetrievalMethod

    def retrieve(self, query: RetrievalQuery, scope: AccessScope) -> RetrievalResult: ...


class ResultCache:
    """检索结果缓存。

    键里同时包含**主体、数据集权限、索引版本、查询计划与方法**：
    权限撤销换主体/集合键，文档删除或重建换索引版本键，因此旧缓存不可能被复用。
    """

    def __init__(self, *, max_entries: int = 128) -> None:
        self.max_entries = max_entries
        self._entries: dict[str, RetrievalResult] = {}
        self.hits = 0
        self.misses = 0

    def key(
        self, *, scope: AccessScope, index_version: str, method: RetrievalMethod, plan_key: str
    ) -> str:
        payload = "|".join(
            [scope.identity, index_version, method.value, plan_key]
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[RetrievalResult]:
        result = self._entries.get(key)
        if result is None:
            self.misses += 1
            return None
        self.hits += 1
        return result

    def put(self, key: str, result: RetrievalResult) -> None:
        if len(self._entries) >= self.max_entries:
            oldest = next(iter(self._entries))
            self._entries.pop(oldest, None)
        self._entries[key] = result

    def clear(self) -> None:
        self._entries.clear()

    @property
    def size(self) -> int:
        return len(self._entries)


def hits_to_chunks(
    hits: Tuple[SearchHit, ...], *, method: RetrievalMethod
) -> Tuple[RetrievedChunk, ...]:
    """把存储层命中转成检索结果：分数换成"越大越好"，排名从 1 开始。"""

    chunks: list[RetrievedChunk] = []
    for rank, hit in enumerate(hits, start=1):
        chunks.append(
            RetrievedChunk(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                dataset=hit.dataset,
                source_path=hit.source_path,
                source_url=hit.source_url,
                license=hit.license,
                tier=hit.tier,
                visibility=hit.visibility,
                title=hit.title,
                heading_path=hit.heading_path,
                heading_anchor=hit.heading_anchor,
                ordinal=hit.ordinal,
                rank=rank,
                score=-float(hit.score),
                method=method,
                text=hit.text,
                text_hash=hit.text_hash,
                char_count=hit.char_count,
                truncated=hit.truncated,
                oversized=hit.oversized,
            )
        )
    return tuple(chunks)


class FtsRetriever:
    """SQLite FTS5 基线检索：关键词、字段过滤与稳定排序。"""

    method = RetrievalMethod.FTS5

    def __init__(
        self,
        store: ChunkStore,
        *,
        policy: CorpusPolicy,
        lexicon: Optional[ExpansionLexicon] = None,
        cache: Optional[ResultCache] = None,
    ) -> None:
        self.store = store
        self.policy = policy
        self.lexicon = lexicon
        self.cache = cache

    def retrieve(self, query: RetrievalQuery, scope: AccessScope) -> RetrievalResult:
        if not isinstance(query, RetrievalQuery):
            raise QueryError(f"retrieve 只接受 RetrievalQuery，得到 {type(query).__name__}")
        if not isinstance(scope, AccessScope):
            raise QueryError(f"retrieve 只接受 AccessScope，得到 {type(scope).__name__}")

        plan = build_plan(query, scope=scope, policy=self.policy, lexicon=self.lexicon)
        try:
            index_version = self.store.index_version
        except StoreError as error:
            return RetrievalResult(
                status=RetrievalStatus.UNAVAILABLE,
                query=plan.text,
                plan=plan,
                method=self.method,
                reason=UnavailableReason.INDEX_MISSING,
                detail=str(error),
                request_id=query.request_id,
                trace_id=query.trace_id,
            )

        if plan.is_empty:
            return RetrievalResult(
                status=RetrievalStatus.EMPTY,
                query=plan.text,
                plan=plan,
                method=self.method,
                index_version=index_version,
                reason=UnavailableReason.EMPTY_QUERY,
                detail="查询规范化后没有可用词项",
                request_id=query.request_id,
                trace_id=query.trace_id,
            )
        if not scope.datasets:
            return RetrievalResult(
                status=RetrievalStatus.EMPTY,
                query=plan.text,
                plan=plan,
                method=self.method,
                index_version=index_version,
                reason=UnavailableReason.ACCESS_DENIED,
                detail="AccessScope 没有授予任何数据集；授权只来自显式声明",
                request_id=query.request_id,
                trace_id=query.trace_id,
            )

        cache_key = None
        if self.cache is not None:
            cache_key = self.cache.key(
                scope=scope,
                index_version=index_version,
                method=self.method,
                plan_key=plan.model_dump_json(),
            )
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached.model_copy(
                    update={"request_id": query.request_id, "trace_id": query.trace_id}
                )

        try:
            hits = self.store.search(
                expression=plan.fts_expression,
                scope=scope,
                limit=plan.limit,
                datasets=plan.filters.datasets,
                tiers=plan.filters.tiers,
                languages=plan.filters.languages,
            )
        except StoreError as error:
            return RetrievalResult(
                status=RetrievalStatus.UNAVAILABLE,
                query=plan.text,
                plan=plan,
                method=self.method,
                index_version=index_version,
                reason=UnavailableReason.RETRIEVAL_FAILED,
                detail=str(error),
                request_id=query.request_id,
                trace_id=query.trace_id,
            )

        if not hits:
            result = RetrievalResult(
                status=RetrievalStatus.EMPTY,
                query=plan.text,
                plan=plan,
                method=self.method,
                index_version=index_version,
                reason=UnavailableReason.NO_RESULTS,
                detail="查询合法但没有命中任何 chunk",
                request_id=query.request_id,
                trace_id=query.trace_id,
            )
        else:
            result = RetrievalResult(
                status=RetrievalStatus.OK,
                query=plan.text,
                plan=plan,
                method=self.method,
                index_version=index_version,
                results=hits_to_chunks(hits, method=self.method),
                request_id=query.request_id,
                trace_id=query.trace_id,
            )
        if cache_key is not None and self.cache is not None:
            self.cache.put(cache_key, result)
        return result
