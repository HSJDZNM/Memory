"""摄取编排：幂等重建、单文档原子替换、删除失效与可审计的 run 台账。

不变式：

1. **幂等**：同一输入连续摄取两次，document/chunk 数量不变，chunk_id 与 text_hash 完全一致；
   内容没变的文档连分块都不会重跑（content_hash + chunker_version 短路）。
2. **只动相关 chunk**：文档内容变化时按 chunk_id + text_hash 比对，未变的 chunk 保持
   revision 不变（可被测试直接观察），只有真正变化的 chunk 被替换。
3. **删除失效**：清单里没有的入口（源文件被删除/被移出清单）对应文档及其 chunk 会被删除，
   并且不再可检索。
4. **失败不冒充成功**：进程中断留下的 running 会在下一次 run 开始时标成 interrupted；
   运行期异常把 run 标成 failed 并把原因写进 note，绝不写成 completed。
5. **不许静默**：截断、超长、空章节、front matter 警告与哈希漂移全部计数并进报告。
"""

from __future__ import annotations

import datetime as clock
import uuid
from pathlib import Path
from typing import Callable, Optional, Tuple

from .chunker import CHUNKER_VERSION, chunk_document
from .corpus import EntryIssue, LoadedCorpus
from .models import (
    CorpusError,
    DocumentRecord,
    IndexRunStatus,
    IndexingError,
    ResolvedEntry,
    StrictModel,
    document_id_for,
    sha256_text,
)
from .store import ChunkStore

__all__ = [
    "DEFAULT_CORPUS_PATH",
    "DocumentOutcome",
    "IndexReport",
    "ingest",
    "needs_reindex",
]

DEFAULT_CORPUS_PATH = "knowledge/corpus.yaml"


class DocumentOutcome(StrictModel):
    """单个文档的摄取结果：状态与计数都可直接进报告。"""

    dataset: str
    source_path: str
    document_id: str
    status: str
    chunks: int = 0
    changed_chunks: int = 0
    truncated_chunks: int = 0
    oversized_chunks: int = 0
    empty_sections: int = 0
    front_matter_warning: Optional[str] = None
    hash_drift: bool = False


class IndexReport(StrictModel):
    """一次索引 run 的完整结论（阶段证据与 CLI 都读它）。"""

    run_id: str
    corpus: str
    status: IndexRunStatus
    input_hash: str
    index_version: str
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: int = 0
    documents: Tuple[DocumentOutcome, ...] = ()
    documents_indexed: int = 0
    chunks_created: int = 0
    chunks_updated: int = 0
    chunks_unchanged: int = 0
    chunks_removed: int = 0
    documents_removed: int = 0
    truncated_chunks: int = 0
    oversized_chunks: int = 0
    empty_sections: int = 0
    quarantined_chunks: int = 0
    released_quarantine: Tuple[str, ...] = ()
    rule_sources: Tuple[Tuple[str, int, str], ...] = ()
    drift: Tuple[EntryIssue, ...] = ()
    note: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status is IndexRunStatus.COMPLETED


def _now(now: Optional[clock.datetime]) -> clock.datetime:
    if now is None:
        return clock.datetime.now(clock.timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=clock.timezone.utc)
    return now


def _stamp(value: clock.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def needs_reindex(loaded: LoadedCorpus, store: ChunkStore) -> bool:
    """是否需要重建：输入指纹变化、没有成功过的 run，或库被标记成别的输入。"""

    last = store.last_completed_run()
    if last is None:
        return True
    if last.input_hash != loaded.input_hash:
        return True
    return store.corpus_input_hash != loaded.input_hash


def _read_entry(entry: ResolvedEntry, *, repo_root: Path, mirror: str) -> Tuple[str, str]:
    path = repo_root / mirror / entry.source_path
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise IndexingError(f"{entry.dataset}:{entry.source_path} 无法读取 ({error})") from error
    return text, sha256_text(text)


def _document_record(
    entry: ResolvedEntry,
    *,
    content_hash: str,
    byte_size: int,
    ingested_at: str,
) -> DocumentRecord:
    return DocumentRecord(
        document_id=entry.document_id,
        dataset=entry.dataset,
        source_path=entry.source_path,
        source_url=entry.source_url,
        title=entry.title,
        license=entry.license,
        license_source=entry.license_source,
        tier=entry.tier,
        visibility=entry.visibility,
        language=entry.language,
        content_hash=content_hash,
        manifest_hash=entry.manifest_sha256,
        byte_size=byte_size,
        mirror_revision=entry.mirror_revision,
        chunker_version=CHUNKER_VERSION,
        ingested_at=ingested_at,
    )


def _empty_sections(text: str) -> int:
    from .chunker import find_sections, split_front_matter

    _, body = split_front_matter(text)
    return sum(1 for section in find_sections(body) if section.is_empty)


def ingest(
    loaded: LoadedCorpus,
    store: ChunkStore,
    *,
    repo_root: Path | str,
    now: Optional[clock.datetime] = None,
    after_document: Optional[Callable[[ResolvedEntry], None]] = None,
    run_id: Optional[str] = None,
) -> IndexReport:
    """把清单里的全部入口摄取进索引库；失败时把 run 标成 failed 并抛 IndexingError。"""

    if not isinstance(loaded, LoadedCorpus):
        raise IndexingError(f"ingest 只接受 LoadedCorpus，得到 {type(loaded).__name__}")
    root = Path(repo_root).resolve()
    started = _now(now)
    stamp = _stamp(started)
    identifier = run_id or "run_" + uuid.uuid4().hex[:16]
    mirrors = {dataset.name: dataset.mirror for dataset in loaded.manifest.datasets}
    policy = loaded.manifest.policy

    store.start_run(loaded.input_hash, started_at=stamp, run_id=identifier)
    outcomes: list[DocumentOutcome] = []
    counters = {
        "documents_indexed": 0,
        "chunks_created": 0,
        "chunks_updated": 0,
        "chunks_unchanged": 0,
        "chunks_removed": 0,
        "documents_removed": 0,
        "truncated_chunks": 0,
        "oversized_chunks": 0,
        "empty_sections": 0,
        "quarantined_chunks": 0,
    }

    try:
        for dataset in loaded.manifest.datasets:
            entries = [item for item in loaded.entries if item.dataset == dataset.name]
            keep: list[str] = []
            for entry in entries:
                keep.append(entry.source_path)
                text, content_hash = _read_entry(
                    entry, repo_root=root, mirror=mirrors[entry.dataset]
                )
                existing = store.document(entry.document_id)
                byte_size = len(text.encode("utf-8"))
                if (
                    existing is not None
                    and existing.content_hash == content_hash
                    and existing.chunker_version == CHUNKER_VERSION
                ):
                    untouched = len(store.chunks(entry.document_id))
                    outcomes.append(
                        DocumentOutcome(
                            dataset=entry.dataset,
                            source_path=entry.source_path,
                            document_id=entry.document_id,
                            status="unchanged",
                            chunks=untouched,
                            hash_drift=existing.hash_drift,
                        )
                    )
                    counters["documents_indexed"] += 1
                    # 未变的文档连分块都不重跑：它的 chunk 全部计入 unchanged（没有一行被重写）。
                    counters["chunks_unchanged"] += untouched
                    if after_document is not None:
                        after_document(entry)
                    continue

                front, drafts = chunk_document(
                    text,
                    document_id=entry.document_id,
                    max_chars=policy.max_chunk_chars,
                    hard_max_chars=policy.hard_max_chunk_chars,
                )
                record = _document_record(
                    entry, content_hash=content_hash, byte_size=byte_size, ingested_at=stamp
                )
                with store.transaction():
                    store.upsert_document(record, front_matter=tuple(front.metadata.items()))
                    change = store.replace_chunks(entry.document_id, drafts)

                truncated = sum(1 for item in drafts if item.truncated)
                oversized = sum(1 for item in drafts if item.oversized)
                empty = _empty_sections(text)
                counters["documents_indexed"] += 1
                counters["chunks_created"] += len(change.created)
                counters["chunks_updated"] += len(change.updated)
                counters["chunks_unchanged"] += len(change.unchanged)
                counters["chunks_removed"] += len(change.removed)
                counters["truncated_chunks"] += truncated
                counters["oversized_chunks"] += oversized
                counters["empty_sections"] += empty
                outcomes.append(
                    DocumentOutcome(
                        dataset=entry.dataset,
                        source_path=entry.source_path,
                        document_id=entry.document_id,
                        status="created" if existing is None else "updated",
                        chunks=len(drafts),
                        changed_chunks=len(change.changed),
                        truncated_chunks=truncated,
                        oversized_chunks=oversized,
                        empty_sections=empty,
                        front_matter_warning=front.warning,
                        hash_drift=record.hash_drift,
                    )
                )
                if after_document is not None:
                    after_document(entry)

            removed = store.prune_dataset(dataset.name, keep=keep)
            counters["documents_removed"] += len(removed)

        quarantined, released = _apply_quarantine(loaded, store, stamp=stamp)
        counters["quarantined_chunks"] = len(quarantined)
        rule_sources = _resolve_rule_sources(loaded, store, repo_root=root, mirrors=mirrors)

        store.set_corpus_input_hash(loaded.input_hash)
        store.bump_generation()
        index_version = store.index_version
        completed = _now(now)
        store.finish_run(
            identifier,
            status=IndexRunStatus.COMPLETED,
            completed_at=_stamp(completed),
            note=None,
            **counters,
        )
    except BaseException as error:
        failed_at = _stamp(_now(now))
        # 失败的 run 也可能已经提交过部分文档：generation 必须递增，
        # 否则常驻进程里"键里带 index_version"的结果缓存会继续返回旧内容。
        store.bump_generation()
        store.finish_run(
            identifier,
            status=IndexRunStatus.FAILED,
            completed_at=failed_at,
            note=f"{type(error).__name__}: {error}"[:500],
        )
        if isinstance(error, (IndexingError, CorpusError)):
            raise
        raise IndexingError(f"索引中断（run {identifier} 已标记为 failed）: {error}") from error

    duration = int((_now(now) - started).total_seconds() * 1000)
    return IndexReport(
        run_id=identifier,
        corpus=loaded.corpus_path,
        status=IndexRunStatus.COMPLETED,
        input_hash=loaded.input_hash,
        index_version=index_version,
        started_at=stamp,
        completed_at=_stamp(_now(now)),
        duration_ms=duration,
        documents=tuple(outcomes),
        documents_removed=counters["documents_removed"],
        quarantined_chunks=counters["quarantined_chunks"],
        released_quarantine=released,
        rule_sources=rule_sources,
        drift=tuple(loaded.verification.drift),
        **{
            key: value
            for key, value in counters.items()
            if key not in ("quarantined_chunks", "documents_removed")
        },
    )


def _apply_quarantine(
    loaded: LoadedCorpus, store: ChunkStore, *, stamp: str
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """应用清单里的隔离条目；源文变化的旧隔离自动释放（并记进报告）。"""

    quarantined: list[str] = []
    for item in loaded.manifest.quarantine:
        chunk = store.chunk(item.chunk_id)
        if chunk is None:
            raise IndexingError(
                f"隔离清单引用了不存在的 chunk: {item.chunk_id}（先建索引，再登记隔离）"
            )
        if chunk.text_hash != item.text_hash:
            raise IndexingError(
                f"隔离清单的 text_hash 与当前 chunk 不一致: {item.chunk_id}；"
                "内容已变化，请重新确认后再登记"
            )
        store.quarantine(
            item.chunk_id,
            reason=item.reason,
            text_hash=item.text_hash,
            quarantined_at=stamp,
            document_id=chunk.document_id,
        )
        quarantined.append(item.chunk_id)

    # 清单是隔离状态的唯一事实来源：清单里没有的记录一律释放（chunk 被删除或文本已变化同理）。
    wanted = {item.chunk_id: item.text_hash for item in loaded.manifest.quarantine}
    released: list[str] = []
    for record in store.quarantined():
        chunk = store.chunk(record.chunk_id)
        stale = (
            record.chunk_id not in wanted
            or chunk is None
            or chunk.text_hash != record.text_hash
        )
        if stale:
            store.release_quarantine(record.chunk_id)
            released.append(record.chunk_id)
    return tuple(sorted(quarantined)), tuple(sorted(released))


def _resolve_rule_sources(
    loaded: LoadedCorpus,
    store: ChunkStore,
    *,
    repo_root: Path,
    mirrors: dict[str, str],
) -> Tuple[Tuple[str, int, str], ...]:
    """把清单里的规则溯源解析成稳定的 chunk_id 并写入 rule_sources 表。"""

    registered: list[Tuple[str, int, str]] = []
    for item in loaded.manifest.rule_sources:
        document_id = document_id_for(item.dataset, item.source_path)
        chunks = store.chunks(document_id)
        if not chunks:
            raise IndexingError(
                f"规则 {item.rule_id}@{item.rule_version} 的溯源指向未索引的文档: "
                f"{item.dataset}:{item.source_path}"
            )
        wanted = tuple(item.heading_path)
        matches = [
            chunk
            for chunk in chunks
            if not wanted or tuple(chunk.heading_path[: len(wanted)]) == wanted
        ]
        if not matches:
            raise IndexingError(
                f"规则 {item.rule_id}@{item.rule_version} 的标题路径在文档中不存在: "
                f"{' > '.join(wanted) or '<root>'} @ {item.source_path}"
            )
        for chunk in matches:
            store.register_rule_source(
                rule_id=item.rule_id, rule_version=item.rule_version, chunk_id=chunk.chunk_id
            )
            registered.append((item.rule_id, item.rule_version, chunk.chunk_id))
    return tuple(sorted(registered))


def quarantine_chunk(
    store: ChunkStore,
    *,
    chunk_id: str,
    reason: str,
    quarantined_at: str,
) -> str:
    """运行期隔离一个 chunk（供 CLI 与运维使用）：保留审计记录并立即从索引移除。"""

    chunk = store.chunk(chunk_id)
    if chunk is None:
        raise IndexingError(f"chunk 不存在: {chunk_id}")
    store.quarantine(
        chunk_id,
        reason=reason,
        text_hash=chunk.text_hash,
        quarantined_at=quarantined_at,
        document_id=chunk.document_id,
    )
    store.bump_generation()
    return chunk.text_hash
