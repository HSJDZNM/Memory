"""可替换的向量检索端口与确定性本地 embedding（对照评测用，默认不启用）。

Phase 3 的立场：**先有可解释的 FTS5 基线，再有向量**。这里提供的是端口与一个
确定性、无依赖、无网络的本地实现，用来回答"向量检索在固定评测集上是否有稳定收益"，
而不是先引入框架再找理由（Qdrant / LlamaIndex 都不在本阶段）。

为什么不用内置 hash()：它带进程随机种子，"相同输入相同结果"这条核心约定会失效；
这里用 blake2b 做稳定哈希。embedding 只用于排序，永远不作为授权信号。
"""

from __future__ import annotations

import datetime as clock
import math
import re
from hashlib import blake2b
from typing import Optional, Protocol, Sequence, Tuple

from .corpus import ExpansionLexicon
from .models import (
    AccessScope,
    CorpusPolicy,
    QueryError,
    RetrievalMethod,
    RetrievalQuery,
    RetrievalResult,
    RetrievalStatus,
    StoreError,
    UnavailableReason,
)
from .query import build_plan
from .retriever import ResultCache, hits_to_chunks
from .store import ChunkStore, SearchHit

__all__ = ["EmbeddingPort", "HashingEmbedding", "VectorRetriever"]

_WORD_RE = re.compile(r"[0-9A-Za-z_\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]+")


class EmbeddingPort(Protocol):
    """Embedding 端口：任何实现都必须给出稳定的向量维度与可复现的向量。"""

    name: str
    dim: int

    def embed(self, texts: Sequence[str]) -> Tuple[Tuple[float, ...], ...]: ...


class HashingEmbedding:
    """确定性本地 embedding：词项 + 字符 3-gram 的带符号哈希，L2 归一化。"""

    def __init__(self, *, dim: int = 256, ngram: int = 3) -> None:
        if dim <= 0:
            raise ValueError("dim 必须是正数")
        if ngram < 1:
            raise ValueError("ngram 必须是正数")
        self.dim = dim
        self.ngram = ngram

    @property
    def name(self) -> str:
        return f"hashing-char{self.ngram}gram-{self.dim}"

    def _features(self, text: str) -> Tuple[str, ...]:
        lowered = text.lower()
        features: list[str] = list(_WORD_RE.findall(lowered))
        compact = re.sub(r"\s+", "", lowered)
        for index in range(max(len(compact) - self.ngram + 1, 0)):
            features.append("g:" + compact[index : index + self.ngram])
        return tuple(features)

    def embed_one(self, text: str) -> Tuple[float, ...]:
        vector = [0.0] * self.dim
        for feature in self._features(text):
            digest = blake2b(feature.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big")
            sign = 1.0 if value & 1 else -1.0
            vector[(value >> 1) % self.dim] += sign
        norm = math.sqrt(sum(item * item for item in vector))
        if norm == 0.0:
            return tuple(vector)
        return tuple(item / norm for item in vector)

    def embed(self, texts: Sequence[str]) -> Tuple[Tuple[float, ...], ...]:
        return tuple(self.embed_one(text) for text in texts)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("向量维度不一致")
    return sum(a * b for a, b in zip(left, right))


class VectorRetriever:
    """向量检索实现：与 FTS5 走同一套权限过滤与同一套结果形状。"""

    method = RetrievalMethod.VECTOR

    def __init__(
        self,
        store: ChunkStore,
        *,
        policy: CorpusPolicy,
        lexicon: Optional[ExpansionLexicon] = None,
        embedder: Optional[EmbeddingPort] = None,
        cache: Optional[ResultCache] = None,
    ) -> None:
        self.store = store
        self.policy = policy
        self.lexicon = lexicon
        self.embedder: EmbeddingPort = embedder or HashingEmbedding()
        self.cache = cache

    @property
    def model_name(self) -> str:
        return self.embedder.name

    def build(self, *, now: Optional[clock.datetime] = None) -> int:
        """为所有 chunk 建立（或补齐）向量；已存在的不重算，因此可反复运行。"""

        datasets = tuple(name for name, _ in self.store.stats().datasets)
        scope = AccessScope(subject="indexer", datasets=frozenset(datasets), allow_restricted=True)
        existing = {chunk_id for chunk_id, _ in self.store.embeddings(model=self.model_name)}
        pending = [hit for hit in self.store.candidates(scope=scope) if hit.chunk_id not in existing]
        if not pending:
            return 0
        stamp = (now or clock.datetime.now(clock.timezone.utc)).isoformat().replace("+00:00", "Z")
        vectors = self.embedder.embed([hit.text for hit in pending])
        if len(vectors) != len(pending):
            raise QueryError("embedding 实现的返回数量与输入不一致")
        for hit, vector in zip(pending, vectors):
            if len(vector) != self.embedder.dim:
                raise QueryError(
                    f"embedding 维度与声明不一致：{len(vector)} != {self.embedder.dim}"
                )
            import array

            payload = array.array("f", vector)
            self.store.store_embedding(
                chunk_id=hit.chunk_id,
                model=self.model_name,
                vector=payload.tobytes(),
                dim=self.embedder.dim,
                embedded_at=stamp,
            )
        return len(pending)

    def retrieve(self, query: RetrievalQuery, scope: AccessScope) -> RetrievalResult:
        if not isinstance(query, RetrievalQuery):
            raise QueryError(f"retrieve 只接受 RetrievalQuery，得到 {type(query).__name__}")
        if not isinstance(scope, AccessScope):
            raise QueryError(f"retrieve 只接受 AccessScope，得到 {type(scope).__name__}")

        plan = build_plan(query, scope=scope, policy=self.policy, lexicon=self.lexicon)
        index_version = self.store.index_version
        if plan.is_empty:
            return RetrievalResult(
                status=RetrievalStatus.EMPTY,
                query=plan.text,
                plan=plan,
                method=self.method,
                index_version=index_version,
                reason=UnavailableReason.EMPTY_QUERY,
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
                request_id=query.request_id,
                trace_id=query.trace_id,
            )

        cache_key = None
        if self.cache is not None:
            cache_key = self.cache.key(
                scope=scope,
                index_version=index_version,
                method=self.method,
                plan_key=plan.model_dump_json() + "|" + self.model_name,
            )
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached.model_copy(
                    update={"request_id": query.request_id, "trace_id": query.trace_id}
                )

        stored = dict(self.store.embeddings(model=self.model_name))
        if not stored:
            return RetrievalResult(
                status=RetrievalStatus.UNAVAILABLE,
                query=plan.text,
                plan=plan,
                method=self.method,
                index_version=index_version,
                reason=UnavailableReason.INDEX_MISSING,
                detail=f"索引里没有 {self.model_name} 的向量；先运行 retrieval.cli vector --build",
                request_id=query.request_id,
                trace_id=query.trace_id,
            )

        try:
            candidates = self.store.candidates(
                scope=scope,
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

        query_vector = self.embedder.embed((" ".join(plan.terms),))[0]
        scored: list[Tuple[float, SearchHit]] = []
        for hit in candidates:
            vector = stored.get(hit.chunk_id)
            if vector is None:
                continue
            scored.append((_cosine(query_vector, vector), hit))
        scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
        floor = self.policy.vector_min_similarity
        relevant = [item for item in scored if item[0] >= floor]
        top = relevant[: plan.limit]
        if not top:
            result = RetrievalResult(
                status=RetrievalStatus.EMPTY,
                query=plan.text,
                plan=plan,
                method=self.method,
                index_version=index_version,
                reason=UnavailableReason.NO_RESULTS,
                detail=(
                    "向量检索没有达到相关性下限的候选"
                    f"（min_similarity={floor}；候选 {len(scored)} 条）"
                ),
                request_id=query.request_id,
                trace_id=query.trace_id,
            )
        else:
            hits = tuple(hit.model_copy(update={"score": -score}) for score, hit in top)
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
