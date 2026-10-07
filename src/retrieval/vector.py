"""可替换的向量检索端口与确定性本地 embedding（对照评测用，默认不启用）。

Phase 3 的立场：**先有可解释的 FTS5 基线，再有向量**。这里提供的是端口与一个
确定性、无依赖、无网络的本地实现，用来回答"向量检索在固定评测集上是否有稳定收益"，
而不是先引入框架再找理由（Qdrant / LlamaIndex 都不在本阶段）。

为什么不用内置 hash()：它带进程随机种子，"相同输入相同结果"这条核心约定会失效；
这里用 blake2b 做稳定哈希。embedding 只用于排序，永远不作为授权信号。
"""

from __future__ import annotations

import array
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
    """Embedding 端口：任何实现都必须给出稳定的向量维度与可复现的向量。

    **归一化不是必须的**：评分侧（_cosine）自己算真余弦，未归一化的实现不会被模长放大
    分数、也不会悄悄越过后面的 vector_min_similarity；返回全零向量的实现按相似度 0 计
    （不会得到 NaN）。内置 HashingEmbedding 本来就是 L2 归一化的，因此结果一字不变。
    """

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
    """真正的余弦相似度：点积 / 两个模长之积（任一模长为 0 时按 0 计）。

    端口契约不要求实现返回 L2 归一化的向量，所以归一必须在这里做：点积会在未归一的向量上
    被模长放大——一个正交但"很长"的候选能靠模长越过 vector_min_similarity，分数区间与排序
    也随之失去意义（复核发现：函数名叫 cosine，算的却是点积）。
    """

    if len(left) != len(right):
        raise ValueError("向量维度不一致")
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / math.sqrt(left_norm * right_norm)


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
        # 只有"维度与当前 embedding 一致"的行才算已存在：同模型名下的旧维度行
        # （换过 dim 的自定义实现）必须重算，否则它们永远不会被修好。
        # 只需要 (id, dim)：整表解码向量在这条路径上是纯浪费（O(corpus) 次解码只为拿 id）。
        existing = {
            chunk_id
            for chunk_id, dim in self.store.embedding_index(model=self.model_name)
            if dim == self.embedder.dim
        }
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

        # "有没有这个模型的向量"用 id 清单判（不解码整表）；真正要用的向量在候选集确定后
        # 再按 id 取（见下）——与整表读取逐值一致，只是不再读与本次权限/过滤无关的行。
        if not self.store.embedding_index(model=self.model_name):
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

        # 只取候选集的向量：整表解码会把与本次权限 / 过滤无关的向量也读出来。
        stored = self.store.embeddings_for(
            [hit.chunk_id for hit in candidates], model=self.model_name
        )

        query_vector = self.embedder.embed((" ".join(plan.terms),))[0]
        if len(query_vector) != self.embedder.dim:
            # embedding 端口违背了自己的声明：这是实现/配置错误，不能退化成"没有结果"。
            raise QueryError(
                f"embedding 实现返回的维度与声明不一致：{len(query_vector)} != {self.embedder.dim}"
            )
        scored: list[Tuple[float, SearchHit]] = []
        stale: list[str] = []
        for hit in candidates:
            vector = stored.get(hit.chunk_id)
            if vector is None:
                continue
            if len(vector) != len(query_vector):
                # 同一模型名下的旧维度向量（换过 dim 的自定义 embedding，
                # 或旧库遗留行）：跳过并显式报告，绝不拿它算余弦
                # （_cosine 会抛裸 ValueError，调用方只把它当"进程崩了"）。
                stale.append(hit.chunk_id)
                continue
            scored.append((_cosine(query_vector, vector), hit))
        if stale:
            # 静默丢掉这些行等于悄悄缩小候选集：索引对当前 embedding 已经不自洽，
            # 按"检索不可用"失败关闭，并给出可执行的修复动作。
            return RetrievalResult(
                status=RetrievalStatus.UNAVAILABLE,
                query=plan.text,
                plan=plan,
                method=self.method,
                index_version=index_version,
                reason=UnavailableReason.RETRIEVAL_FAILED,
                detail=(
                    f"索引里有 {len(stale)} 条 {self.model_name} 向量与当前 embedding 维度"
                    f"不一致（期望 {len(query_vector)}）：向量已过期；"
                    "先运行 python -m retrieval.cli vector --build 重建向量"
                ),
                request_id=query.request_id,
                trace_id=query.trace_id,
            )
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
