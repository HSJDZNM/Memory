"""SQLite + FTS5 存储层：documents / chunks / index_runs / rules / 隔离 / 向量。

设计要点：

- **FTS5 是可解释基线**：检索列存"检索文本"（原文 + 中日韩逐字切分），chunk 表存展示用原文，
  两者分开，保证"检索口径"变化不会改写原文；
- **chunk_id 稳定**：重建索引后同一段原文仍是同一个 ID，内容变化只影响它自己的 text_hash；
- **单文档原子替换**：一个文档的 chunk 增删改在同一个事务里完成，中途失败整体回滚；
- **中断的 run 不冒充成功**：新 run 开始前把遗留的 running 标记为 interrupted，
  失败路径显式写成 failed；
- **权限在 SQL 里过滤**：数据集集合来自调用方的 AccessScope，永远不作为查询文本的一部分；
- **缓存失效靠 index_version**：它由 schema 版本、generation 计数与摄取输入指纹组成，
  任何重建、删除、隔离都会让旧键失效。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional, Sequence, Tuple

from .chunker import search_text
from .models import (
    INDEX_SCHEMA_VERSION,
    AccessScope,
    ChunkChange,
    ChunkDraft,
    ChunkKind,
    ChunkRecord,
    DocumentRecord,
    IndexRunRecord,
    IndexRunStatus,
    QuarantinedChunk,
    StrictModel,
    StoreError,
    Tier,
    Visibility,
    sha256_text,
)

__all__ = [
    "DEFAULT_DB_PATH",
    "SCHEMA_STATEMENTS",
    "ChunkStore",
    "IndexStats",
    "RuleSourceRow",
    "SearchHit",
    "default_db_path",
]

DEFAULT_DB_PATH = ".tmp/retrieval/index.sqlite3"

SCHEMA_STATEMENTS: Tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        document_id TEXT PRIMARY KEY,
        dataset TEXT NOT NULL,
        source_path TEXT NOT NULL,
        source_url TEXT NOT NULL,
        title TEXT NOT NULL,
        license TEXT NOT NULL,
        license_source TEXT,
        tier TEXT NOT NULL,
        visibility TEXT NOT NULL,
        language TEXT,
        content_hash TEXT NOT NULL,
        manifest_hash TEXT,
        byte_size INTEGER NOT NULL,
        mirror_revision TEXT,
        chunker_version TEXT NOT NULL,
        front_matter TEXT NOT NULL DEFAULT '[]',
        ingested_at TEXT NOT NULL,
        UNIQUE (dataset, source_path)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
        ordinal INTEGER NOT NULL,
        heading_path TEXT NOT NULL,
        heading_anchor TEXT NOT NULL,
        text TEXT NOT NULL,
        text_hash TEXT NOT NULL,
        char_count INTEGER NOT NULL,
        kind TEXT NOT NULL,
        part_index INTEGER NOT NULL,
        truncated INTEGER NOT NULL DEFAULT 0,
        original_chars INTEGER,
        oversized INTEGER NOT NULL DEFAULT 0,
        quarantined INTEGER NOT NULL DEFAULT 0,
        revision INTEGER NOT NULL DEFAULT 1,
        UNIQUE (document_id, ordinal)
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
        chunk_id UNINDEXED,
        text,
        heading_path,
        tokenize = 'unicode61 remove_diacritics 2'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS index_runs (
        run_id TEXT PRIMARY KEY,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        input_hash TEXT NOT NULL,
        status TEXT NOT NULL,
        documents_indexed INTEGER NOT NULL DEFAULT 0,
        chunks_created INTEGER NOT NULL DEFAULT 0,
        chunks_updated INTEGER NOT NULL DEFAULT 0,
        chunks_unchanged INTEGER NOT NULL DEFAULT 0,
        chunks_removed INTEGER NOT NULL DEFAULT 0,
        documents_removed INTEGER NOT NULL DEFAULT 0,
        truncated_chunks INTEGER NOT NULL DEFAULT 0,
        oversized_chunks INTEGER NOT NULL DEFAULT 0,
        empty_sections INTEGER NOT NULL DEFAULT 0,
        quarantined_chunks INTEGER NOT NULL DEFAULT 0,
        note TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rule_sources (
        rule_id TEXT NOT NULL,
        rule_version INTEGER NOT NULL,
        chunk_id TEXT NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
        PRIMARY KEY (rule_id, rule_version, chunk_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quarantined_chunks (
        chunk_id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        text_hash TEXT NOT NULL,
        reason TEXT NOT NULL,
        quarantined_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunk_embeddings (
        chunk_id TEXT PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
        model TEXT NOT NULL,
        dim INTEGER NOT NULL,
        vector BLOB NOT NULL,
        embedded_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_documents_dataset ON documents(dataset)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_runs_status ON index_runs(status)",
)

_SCHEMA_VERSION_KEY = "schema_version"
_GENERATION_KEY = "generation"
_CORPUS_INPUT_KEY = "corpus_input_hash"


class SearchHit(StrictModel):
    """一条 FTS 命中：chunk + document 的全部来源信息 + 内部排序分数。"""

    chunk_id: str
    document_id: str
    dataset: str
    source_path: str
    source_url: str
    license: str
    license_source: Optional[str] = None
    tier: Tier
    visibility: Visibility
    title: str
    heading_path: Tuple[str, ...] = ()
    heading_anchor: str = ""
    ordinal: int = 0
    part_index: int = 1
    text: str = ""
    text_hash: str = ""
    char_count: int = 0
    truncated: bool = False
    oversized: bool = False
    score: float = 0.0


class RuleSourceRow(StrictModel):
    """rules(id, version, source_chunk_id) 的一行，附带 chunk 的来源信息便于展示。"""

    rule_id: str
    rule_version: int
    chunk_id: str
    document_id: str
    source_path: str
    heading_path: Tuple[str, ...] = ()
    heading_anchor: str = ""
    text_hash: str = ""


class IndexStats(StrictModel):
    """索引库的规模统计，供 CLI 与阶段证据使用。"""

    documents: int = 0
    chunks: int = 0
    quarantined: int = 0
    truncated_chunks: int = 0
    oversized_chunks: int = 0
    embedded_chunks: int = 0
    datasets: Tuple[Tuple[str, int], ...] = ()
    schema_version: str = INDEX_SCHEMA_VERSION
    generation: int = 0
    index_version: str = ""
    corpus_input_hash: Optional[str] = None
    last_run: Optional[IndexRunRecord] = None


def default_db_path(repo_root: Path | str) -> Path:
    return Path(repo_root) / DEFAULT_DB_PATH


class ChunkStore:
    """索引库句柄。一个实例对应一个 SQLite 文件（或 :memory:）。"""

    def __init__(
        self,
        path: Path | str,
        *,
        create: bool = True,
        timeout: float = 30.0,
        initialize: bool = True,
    ) -> None:
        self.path = str(path)
        is_memory = self.path == ":memory:"
        self._is_memory = is_memory
        if not is_memory:
            target = Path(self.path)
            if not create and not target.is_file():
                raise StoreError(f"索引库不存在: {target}；先运行 python -m retrieval.cli index")
            target.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._raw = sqlite3.connect(self.path, isolation_level=None, timeout=timeout)
        except sqlite3.Error as error:
            raise StoreError(f"无法打开索引库 {self.path}: {error}") from error
        self._raw.row_factory = sqlite3.Row
        self._raw.execute("PRAGMA foreign_keys = ON")
        if not is_memory:
            try:
                self._raw.execute("PRAGMA journal_mode = WAL")
            except sqlite3.Error:
                # WAL 不是所有文件系统都支持；退化到默认日志模式不影响正确性。
                pass
        self._closed = False
        if initialize:
            self._initialize()

    # ------------------------------------------------------------------ 基础

    def __enter__(self) -> "ChunkStore":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._raw.close()
            self._closed = True

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """显式事务：一个文档的增删改要么全部生效，要么整体回滚。"""

        self._raw.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._raw.execute("ROLLBACK")
            raise
        else:
            self._raw.execute("COMMIT")

    def _execute(self, sql: str, parameters: Sequence[Any] = ()) -> sqlite3.Cursor:
        try:
            return self._raw.execute(sql, tuple(parameters))
        except sqlite3.Error as error:
            raise StoreError(f"索引库操作失败: {error} ({sql.strip().split()[0]})") from error

    def _initialize(self) -> None:
        try:
            for statement in SCHEMA_STATEMENTS:
                self._raw.execute(statement)
        except sqlite3.Error as error:
            message = str(error)
            if "fts5" in message.lower():
                raise StoreError(
                    "当前 Python 的 SQLite 未启用 FTS5，Phase 3 的检索基线无法建立："
                    f"{message}"
                ) from error
            # 库文件损坏也走这里：CLI 必须给出退出码 2，而不是抛出一个未捕获的 traceback。
            raise StoreError(f"初始化索引库失败（文件可能损坏）: {message}") from error
        self.assert_integrity()
        stored = self._meta(_SCHEMA_VERSION_KEY)
        if stored is None:
            self._raw.execute(
                "INSERT INTO schema_meta(key, value) VALUES (?, ?)",
                (_SCHEMA_VERSION_KEY, INDEX_SCHEMA_VERSION),
            )
            self._set_meta(_GENERATION_KEY, "0")
        elif stored != INDEX_SCHEMA_VERSION:
            raise StoreError(
                f"索引库结构版本 {stored!r} 与当前实现 {INDEX_SCHEMA_VERSION!r} 不一致；"
                "拒绝在未知结构上检索，请重建索引"
            )

    # ------------------------------------------------------------------ meta

    def _meta(self, key: str) -> Optional[str]:
        row = self._execute("SELECT value FROM schema_meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def _set_meta(self, key: str, value: str) -> None:
        self._execute(
            "INSERT INTO schema_meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    @property
    def schema_version(self) -> str:
        return self._meta(_SCHEMA_VERSION_KEY) or INDEX_SCHEMA_VERSION

    @property
    def generation(self) -> int:
        raw = self._meta(_GENERATION_KEY)
        return int(raw) if raw is not None else 0

    def bump_generation(self) -> int:
        """每次改变可检索内容（重建、删除、隔离）都递增：缓存键随之失效。"""

        current = self.generation + 1
        self._set_meta(_GENERATION_KEY, str(current))
        return current

    @property
    def corpus_input_hash(self) -> Optional[str]:
        return self._meta(_CORPUS_INPUT_KEY)

    def set_corpus_input_hash(self, value: str) -> None:
        self._set_meta(_CORPUS_INPUT_KEY, value)

    @property
    def index_version(self) -> str:
        """索引版本：结构 + generation + 摄取输入指纹；任何一个变化都会换键。"""

        payload = "|".join(
            [
                "schema:" + self.schema_version,
                "generation:" + str(self.generation),
                "input:" + (self.corpus_input_hash or "<none>"),
            ]
        )
        return sha256_text(payload)

    # ------------------------------------------------------------- documents

    def document(self, document_id: str) -> Optional[DocumentRecord]:
        row = self._execute("SELECT * FROM documents WHERE document_id = ?", (document_id,)).fetchone()
        return None if row is None else _document_from_row(row)

    def documents(self, *, dataset: Optional[str] = None) -> Tuple[DocumentRecord, ...]:
        if dataset is None:
            rows = self._execute("SELECT * FROM documents ORDER BY dataset, source_path").fetchall()
        else:
            rows = self._execute(
                "SELECT * FROM documents WHERE dataset = ? ORDER BY source_path", (dataset,)
            ).fetchall()
        return tuple(_document_from_row(row) for row in rows)

    def upsert_document(
        self,
        record: DocumentRecord,
        *,
        front_matter: Sequence[Tuple[str, str]] = (),
    ) -> None:
        self._execute(
            """
            INSERT INTO documents(
                document_id, dataset, source_path, source_url, title, license, license_source,
                tier, visibility, language, content_hash, manifest_hash, byte_size,
                mirror_revision, chunker_version, front_matter, ingested_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(document_id) DO UPDATE SET
                dataset=excluded.dataset, source_path=excluded.source_path,
                source_url=excluded.source_url, title=excluded.title, license=excluded.license,
                license_source=excluded.license_source, tier=excluded.tier,
                visibility=excluded.visibility, language=excluded.language,
                content_hash=excluded.content_hash, manifest_hash=excluded.manifest_hash,
                byte_size=excluded.byte_size, mirror_revision=excluded.mirror_revision,
                chunker_version=excluded.chunker_version, front_matter=excluded.front_matter,
                ingested_at=excluded.ingested_at
            """,
            (
                record.document_id,
                record.dataset,
                record.source_path,
                record.source_url,
                record.title,
                record.license,
                record.license_source,
                record.tier.value,
                record.visibility.value,
                record.language,
                record.content_hash,
                record.manifest_hash,
                record.byte_size,
                record.mirror_revision,
                record.chunker_version,
                json.dumps([list(item) for item in front_matter], ensure_ascii=False),
                record.ingested_at,
            ),
        )

    def front_matter(self, document_id: str) -> Tuple[Tuple[str, str], ...]:
        row = self._execute(
            "SELECT front_matter FROM documents WHERE document_id = ?", (document_id,)
        ).fetchone()
        if row is None:
            return ()
        try:
            payload = json.loads(row["front_matter"])
        except (TypeError, ValueError):
            return ()
        return tuple((str(item[0]), str(item[1])) for item in payload if len(item) == 2)

    def prune_dataset(self, dataset: str, *, keep: Sequence[str]) -> Tuple[str, ...]:
        """删除数据集里已经不在清单中的文档（源文件被删除时同样走这条路径）。"""

        keep_set = set(keep)
        rows = self._execute(
            "SELECT document_id, source_path FROM documents WHERE dataset = ?", (dataset,)
        ).fetchall()
        removed: list[str] = []
        for row in rows:
            if row["source_path"] in keep_set:
                continue
            document_id = str(row["document_id"])
            self._delete_document(document_id)
            removed.append(document_id)
        return tuple(sorted(removed))

    def delete_document(self, document_id: str) -> int:
        document = self.document(document_id)
        if document is None:
            return 0
        count = len(self.chunks(document_id))
        self._delete_document(document_id)
        return count

    def _delete_document(self, document_id: str) -> None:
        self._execute("DELETE FROM chunks_fts WHERE chunk_id IN "
                      "(SELECT chunk_id FROM chunks WHERE document_id = ?)", (document_id,))
        self._execute("DELETE FROM quarantined_chunks WHERE document_id = ?", (document_id,))
        self._execute("DELETE FROM documents WHERE document_id = ?", (document_id,))

    # ---------------------------------------------------------------- chunks

    def chunks(self, document_id: str) -> Tuple[ChunkRecord, ...]:
        rows = self._execute(
            "SELECT * FROM chunks WHERE document_id = ? ORDER BY ordinal", (document_id,)
        ).fetchall()
        return tuple(_chunk_from_row(row) for row in rows)

    def chunk(self, chunk_id: str) -> Optional[ChunkRecord]:
        row = self._execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()
        return None if row is None else _chunk_from_row(row)

    def replace_chunks(self, document_id: str, drafts: Sequence[ChunkDraft]) -> ChunkChange:
        """用新的分块结果替换一个文档的 chunk：只动真正变化的行，其余保留 revision。

        两阶段写入：先把该文档现有行的 ordinal 整体挪到负区间，再按新顺序写入。
        否则"在文档中间插入/删除章节"时，新 ordinal 会撞上尚未挪走的旧行，
        触发 UNIQUE(document_id, ordinal) —— 那会让一次增量更新永久失败（只能删库重建）。
        """

        existing = {item.chunk_id: item for item in self.chunks(document_id)}
        incoming = {item.chunk_id: item for item in drafts}
        created: list[str] = []
        updated: list[str] = []
        unchanged: list[str] = []
        removed: list[str] = []

        if existing:
            self._execute(
                "UPDATE chunks SET ordinal = -(ordinal + 1) WHERE document_id = ?",
                (document_id,),
            )

        for chunk_id, draft in incoming.items():
            previous = existing.get(chunk_id)
            if previous is None:
                self._insert_chunk(draft)
                created.append(chunk_id)
                continue
            same_content = (
                previous.text_hash == draft.text_hash
                and previous.heading_path == draft.heading_path
                and previous.heading_anchor == draft.heading_anchor
                and previous.part_index == draft.part_index
            )
            if same_content and previous.quarantined == self._is_quarantined(
                chunk_id, draft.text_hash
            ):
                # 内容没变：无条件写回正确序号（刚才被挪到负区间了），不动 revision。
                self._update_ordinal(chunk_id, draft.ordinal)
                unchanged.append(chunk_id)
                continue
            self._update_chunk(draft, previous.revision + 1)
            updated.append(chunk_id)

        for chunk_id in existing:
            if chunk_id not in incoming:
                self._delete_chunk(chunk_id)
                removed.append(chunk_id)

        return ChunkChange(
            created=tuple(sorted(created)),
            updated=tuple(sorted(updated)),
            unchanged=tuple(sorted(unchanged)),
            removed=tuple(sorted(removed)),
        )

    def _update_ordinal(self, chunk_id: str, ordinal: int) -> None:
        self._execute("UPDATE chunks SET ordinal = ? WHERE chunk_id = ?", (ordinal, chunk_id))

    def _insert_chunk(self, draft: ChunkDraft) -> None:
        quarantined = self._is_quarantined(draft.chunk_id, draft.text_hash)
        self._execute(
            """
            INSERT INTO chunks(
                chunk_id, document_id, ordinal, heading_path, heading_anchor, text, text_hash,
                char_count, kind, part_index, truncated, original_chars, oversized,
                quarantined, revision
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
            """,
            (
                draft.chunk_id,
                draft.document_id,
                draft.ordinal,
                json.dumps(list(draft.heading_path), ensure_ascii=False),
                draft.heading_anchor,
                draft.text,
                draft.text_hash,
                draft.char_count,
                draft.kind.value,
                draft.part_index,
                1 if draft.truncated else 0,
                draft.original_chars,
                1 if draft.oversized else 0,
                1 if quarantined else 0,
            ),
        )
        if not quarantined:
            self._index_chunk_fts(draft.chunk_id, draft.text, draft.heading_path)

    def _update_chunk(self, draft: ChunkDraft, revision: int) -> None:
        quarantined = self._is_quarantined(draft.chunk_id, draft.text_hash)
        self._execute(
            """
            UPDATE chunks SET ordinal=?, heading_path=?, heading_anchor=?, text=?, text_hash=?,
                char_count=?, kind=?, part_index=?, truncated=?, original_chars=?, oversized=?,
                quarantined=?, revision=?
            WHERE chunk_id=?
            """,
            (
                draft.ordinal,
                json.dumps(list(draft.heading_path), ensure_ascii=False),
                draft.heading_anchor,
                draft.text,
                draft.text_hash,
                draft.char_count,
                draft.kind.value,
                draft.part_index,
                1 if draft.truncated else 0,
                draft.original_chars,
                1 if draft.oversized else 0,
                1 if quarantined else 0,
                revision,
                draft.chunk_id,
            ),
        )
        self._execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (draft.chunk_id,))
        if not quarantined:
            self._index_chunk_fts(draft.chunk_id, draft.text, draft.heading_path)

    def _delete_chunk(self, chunk_id: str) -> None:
        self._execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
        self._execute("DELETE FROM chunks WHERE chunk_id = ?", (chunk_id,))

    def _index_chunk_fts(self, chunk_id: str, text: str, heading_path: Sequence[str]) -> None:
        self._execute(
            "INSERT INTO chunks_fts(chunk_id, text, heading_path) VALUES (?,?,?)",
            (chunk_id, search_text(text), search_text(" > ".join(heading_path))),
        )

    # ------------------------------------------------------------ index runs

    def start_run(self, input_hash: str, *, started_at: str, run_id: str) -> IndexRunRecord:
        """开一次 run：先把遗留的 running 标成 interrupted（崩溃现场不会被当成成功）。"""

        stale = self.stale_runs()
        if stale:
            self._execute(
                "UPDATE index_runs SET status = ?, completed_at = ?, "
                "note = COALESCE(note, '进程中断，未完成') WHERE status = ?",
                (IndexRunStatus.INTERRUPTED.value, started_at, IndexRunStatus.RUNNING.value),
            )
        self._execute(
            "INSERT INTO index_runs(run_id, started_at, input_hash, status) VALUES (?,?,?,?)",
            (run_id, started_at, input_hash, IndexRunStatus.RUNNING.value),
        )
        record = self.run(run_id)
        assert record is not None
        return record

    def finish_run(
        self,
        run_id: str,
        *,
        status: IndexRunStatus,
        completed_at: str,
        note: Optional[str] = None,
        **counters: int,
    ) -> IndexRunRecord:
        if status is IndexRunStatus.RUNNING:
            raise StoreError("finish_run 不接受 running：run 结束时必须给出终态")
        allowed = {
            "documents_indexed",
            "chunks_created",
            "chunks_updated",
            "chunks_unchanged",
            "chunks_removed",
            "documents_removed",
            "truncated_chunks",
            "oversized_chunks",
            "empty_sections",
            "quarantined_chunks",
        }
        unknown = sorted(set(counters) - allowed)
        if unknown:
            raise StoreError(f"未知的 run 计数字段: {unknown}")
        assignments = ", ".join(f"{name} = ?" for name in counters)
        parameters: list[Any] = [status.value, completed_at, note] + [counters[name] for name in counters]
        sql = "UPDATE index_runs SET status = ?, completed_at = ?, note = ?"
        if assignments:
            sql += ", " + assignments
        sql += " WHERE run_id = ?"
        parameters.append(run_id)
        self._execute(sql, parameters)
        record = self.run(run_id)
        if record is None:
            raise StoreError(f"索引 run 不存在: {run_id}")
        return record

    def run(self, run_id: str) -> Optional[IndexRunRecord]:
        row = self._execute("SELECT * FROM index_runs WHERE run_id = ?", (run_id,)).fetchone()
        return None if row is None else _run_from_row(row)

    def runs(self, *, limit: int = 10) -> Tuple[IndexRunRecord, ...]:
        rows = self._execute(
            "SELECT * FROM index_runs ORDER BY started_at DESC, run_id DESC LIMIT ?", (limit,)
        ).fetchall()
        return tuple(_run_from_row(row) for row in rows)

    def stale_runs(self) -> Tuple[IndexRunRecord, ...]:
        rows = self._execute(
            "SELECT * FROM index_runs WHERE status = ? ORDER BY started_at", (IndexRunStatus.RUNNING.value,)
        ).fetchall()
        return tuple(_run_from_row(row) for row in rows)

    def last_completed_run(self) -> Optional[IndexRunRecord]:
        row = self._execute(
            "SELECT * FROM index_runs WHERE status = ? ORDER BY completed_at DESC, run_id DESC LIMIT 1",
            (IndexRunStatus.COMPLETED.value,),
        ).fetchone()
        return None if row is None else _run_from_row(row)

    # ------------------------------------------------------------ quarantine

    def _is_quarantined(self, chunk_id: str, text_hash: str) -> bool:
        row = self._execute(
            "SELECT text_hash FROM quarantined_chunks WHERE chunk_id = ?", (chunk_id,)
        ).fetchone()
        # 源文一变，旧隔离自动失效（保留记录由 reconcile_quarantine 负责清理）。
        return row is not None and str(row["text_hash"]) == text_hash

    def quarantine(self, chunk_id: str, *, reason: str, text_hash: str, quarantined_at: str,
                   document_id: str) -> QuarantinedChunk:
        """隔离一个已知恶意 chunk：保留审计记录并从 FTS 索引移除。"""

        self._execute(
            """
            INSERT INTO quarantined_chunks(chunk_id, document_id, text_hash, reason, quarantined_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(chunk_id) DO UPDATE SET
                document_id=excluded.document_id, text_hash=excluded.text_hash,
                reason=excluded.reason, quarantined_at=excluded.quarantined_at
            """,
            (chunk_id, document_id, text_hash, reason, quarantined_at),
        )
        self._execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
        self._execute("UPDATE chunks SET quarantined = 1 WHERE chunk_id = ?", (chunk_id,))
        return QuarantinedChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            text_hash=text_hash,
            reason=reason,
            quarantined_at=quarantined_at,
        )

    def release_quarantine(self, chunk_id: str) -> bool:
        row = self._execute(
            "SELECT * FROM quarantined_chunks WHERE chunk_id = ?", (chunk_id,)
        ).fetchone()
        if row is None:
            return False
        self._execute("DELETE FROM quarantined_chunks WHERE chunk_id = ?", (chunk_id,))
        chunk = self.chunk(chunk_id)
        if chunk is not None:
            self._execute("UPDATE chunks SET quarantined = 0 WHERE chunk_id = ?", (chunk_id,))
            self._index_chunk_fts(chunk_id, chunk.text, chunk.heading_path)
        return True

    def quarantined(self) -> Tuple[QuarantinedChunk, ...]:
        rows = self._execute(
            "SELECT * FROM quarantined_chunks ORDER BY quarantined_at, chunk_id"
        ).fetchall()
        return tuple(
            QuarantinedChunk(
                chunk_id=str(row["chunk_id"]),
                document_id=str(row["document_id"]),
                text_hash=str(row["text_hash"]),
                reason=str(row["reason"]),
                quarantined_at=str(row["quarantined_at"]),
            )
            for row in rows
        )

    # ---------------------------------------------------------- rule sources

    def register_rule_source(self, *, rule_id: str, rule_version: int, chunk_id: str) -> None:
        chunk = self.chunk(chunk_id)
        if chunk is None:
            raise StoreError(f"规则溯源指向不存在的 chunk: {chunk_id}")
        self._execute(
            "INSERT INTO rule_sources(rule_id, rule_version, chunk_id) VALUES (?,?,?) "
            "ON CONFLICT(rule_id, rule_version, chunk_id) DO NOTHING",
            (rule_id, rule_version, chunk_id),
        )

    def rule_sources(
        self, *, rule_id: str, rule_version: Optional[int] = None
    ) -> Tuple[RuleSourceRow, ...]:
        if rule_version is None:
            rows = self._execute(
                "SELECT * FROM rule_sources WHERE rule_id = ? ORDER BY rule_version, chunk_id",
                (rule_id,),
            ).fetchall()
        else:
            rows = self._execute(
                "SELECT * FROM rule_sources WHERE rule_id = ? AND rule_version = ? ORDER BY chunk_id",
                (rule_id, rule_version),
            ).fetchall()
        return tuple(_rule_source_from_row(row, self) for row in rows)

    def rules_for_chunk(self, chunk_id: str) -> Tuple[Tuple[str, int], ...]:
        rows = self._execute(
            "SELECT rule_id, rule_version FROM rule_sources WHERE chunk_id = ? "
            "ORDER BY rule_id, rule_version",
            (chunk_id,),
        ).fetchall()
        return tuple((str(row["rule_id"]), int(row["rule_version"])) for row in rows)

    # ---------------------------------------------------------------- search

    def search(
        self,
        *,
        expression: str,
        scope: AccessScope,
        limit: int,
        datasets: Sequence[str] = (),
        tiers: Sequence[str] = (),
        languages: Sequence[str] = (),
    ) -> Tuple[SearchHit, ...]:
        """FTS5 查询：过滤条件全部走参数化 SQL，查询文本只出现在 MATCH 参数里。

        受限数据集只认 scope.allow_restricted：这里刻意不提供"绕过参数"，
        否则权限判断就多了一个可以被上层随手打开的开关。
        """

        if not expression.strip():
            return ()
        allowed = sorted(set(scope.datasets))
        if not allowed:
            return ()
        if datasets:
            requested = sorted(set(datasets))
            allowed = sorted(set(allowed) & set(requested))
            if not allowed:
                return ()
        allow_restricted = scope.allow_restricted
        conditions = [
            "c.quarantined = 0",
            "d.dataset IN (" + ",".join("?" for _ in allowed) + ")",
        ]
        parameters: list[Any] = [expression, *allowed]
        if not allow_restricted:
            conditions.append("d.visibility = ?")
            parameters.append(Visibility.PUBLIC.value)
        if tiers:
            conditions.append("d.tier IN (" + ",".join("?" for _ in tiers) + ")")
            parameters.extend(tiers)
        if languages:
            conditions.append("d.language IN (" + ",".join("?" for _ in languages) + ")")
            parameters.extend(languages)
        parameters.append(limit)

        sql = (
            "SELECT c.chunk_id, c.document_id, c.ordinal, c.heading_path, c.heading_anchor, "
            "c.text, c.text_hash, c.char_count, c.truncated, c.oversized, c.part_index, "
            "d.dataset, d.source_path, d.source_url, d.license, d.license_source, d.title, "
            "d.tier, d.visibility, bm25(chunks_fts, 0.0, 1.0, 0.35) AS score "
            "FROM chunks_fts f "
            "JOIN chunks c ON c.chunk_id = f.chunk_id "
            "JOIN documents d ON d.document_id = c.document_id "
            "WHERE chunks_fts MATCH ? AND " + " AND ".join(conditions) + " "
            "ORDER BY score ASC, c.chunk_id ASC LIMIT ?"
        )
        rows = self._execute(sql, parameters).fetchall()
        return tuple(_search_hit_from_row(row) for row in rows)

    # ----------------------------------------------------------------- stats

    def stats(self) -> IndexStats:
        documents = int(self._execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"])
        chunks = int(self._execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"])
        quarantined = int(
            self._execute("SELECT COUNT(*) AS n FROM quarantined_chunks").fetchone()["n"]
        )
        truncated = int(
            self._execute("SELECT COUNT(*) AS n FROM chunks WHERE truncated = 1").fetchone()["n"]
        )
        oversized = int(
            self._execute("SELECT COUNT(*) AS n FROM chunks WHERE oversized = 1").fetchone()["n"]
        )
        embedded = int(
            self._execute("SELECT COUNT(*) AS n FROM chunk_embeddings").fetchone()["n"]
        )
        dataset_rows = self._execute(
            "SELECT dataset, COUNT(*) AS n FROM documents GROUP BY dataset ORDER BY dataset"
        ).fetchall()
        return IndexStats(
            documents=documents,
            chunks=chunks,
            quarantined=quarantined,
            truncated_chunks=truncated,
            oversized_chunks=oversized,
            embedded_chunks=embedded,
            datasets=tuple((str(row["dataset"]), int(row["n"])) for row in dataset_rows),
            schema_version=self.schema_version,
            generation=self.generation,
            index_version=self.index_version,
            corpus_input_hash=self.corpus_input_hash,
            last_run=(self.runs(limit=1) or (None,))[0],
        )

    def fts_row_count(self) -> int:
        return int(self._execute("SELECT COUNT(*) AS n FROM chunks_fts").fetchone()["n"])

    def integrity(self) -> Mapping[str, int]:
        """索引一致性：每个未隔离的 chunk 有且只有一条 FTS 行，且没有孤儿 FTS 行。"""

        chunks = int(self._execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"])
        quarantined = int(
            self._execute("SELECT COUNT(*) AS n FROM chunks WHERE quarantined = 1").fetchone()["n"]
        )
        fts_rows = self.fts_row_count()
        missing = int(
            self._execute(
                "SELECT COUNT(*) AS n FROM chunks c LEFT JOIN chunks_fts f ON f.chunk_id = c.chunk_id "
                "WHERE c.quarantined = 0 AND f.chunk_id IS NULL"
            ).fetchone()["n"]
        )
        orphans = int(
            self._execute(
                "SELECT COUNT(*) AS n FROM chunks_fts f LEFT JOIN chunks c ON c.chunk_id = f.chunk_id "
                "WHERE c.chunk_id IS NULL"
            ).fetchone()["n"]
        )
        return {
            "chunks": chunks,
            "quarantined": quarantined,
            "fts_rows": fts_rows,
            "missing_fts_rows": missing,
            "orphan_fts_rows": orphans,
        }

    def assert_integrity(self) -> None:
        """结构损坏（例如 FTS 表被删掉重建为空表）必须报错，不能退化成"没有结果"。"""

        data = self.integrity()
        if data["missing_fts_rows"] or data["orphan_fts_rows"]:
            raise StoreError(
                "索引结构不一致："
                f"缺少 FTS 行的 chunk={data['missing_fts_rows']}，孤儿 FTS 行={data['orphan_fts_rows']}；"
                "拒绝在损坏的索引上检索，请重建索引（python -m retrieval.cli index）"
            )

    # ------------------------------------------------------------- embeddings

    def store_embedding(self, *, chunk_id: str, model: str, vector: bytes, dim: int,
                        embedded_at: str) -> None:
        self._execute(
            "INSERT INTO chunk_embeddings(chunk_id, model, dim, vector, embedded_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(chunk_id) DO UPDATE SET "
            "model=excluded.model, dim=excluded.dim, vector=excluded.vector, "
            "embedded_at=excluded.embedded_at",
            (chunk_id, model, dim, vector, embedded_at),
        )

    def embeddings(self, *, model: str) -> Tuple[Tuple[str, Tuple[float, ...]], ...]:
        stored = self._execute(
            "SELECT chunk_id, dim, vector FROM chunk_embeddings WHERE model = ? ORDER BY chunk_id",
            (model,),
        ).fetchall()
        import array

        result: list[Tuple[str, Tuple[float, ...]]] = []
        for row in stored:
            values = array.array("f")
            values.frombytes(row["vector"])
            result.append((str(row["chunk_id"]), tuple(float(item) for item in values)))
        return tuple(result)

    def embedding_metadata(self) -> Mapping[str, Any]:
        row = self._execute(
            "SELECT model, dim, COUNT(*) AS n FROM chunk_embeddings GROUP BY model, dim"
        ).fetchone()
        if row is None:
            return {}
        return {"model": str(row["model"]), "dim": int(row["dim"]), "chunks": int(row["n"])}

    def candidates(
        self,
        *,
        scope: AccessScope,
        datasets: Sequence[str] = (),
        tiers: Sequence[str] = (),
        languages: Sequence[str] = (),
    ) -> Tuple[SearchHit, ...]:
        """向量检索的候选集：与 FTS 走同一套权限过滤，只是不接 MATCH 表达式。"""

        allowed = sorted(set(scope.datasets))
        if not allowed:
            return ()
        if datasets:
            allowed = sorted(set(allowed) & set(datasets))
            if not allowed:
                return ()
        conditions = [
            "c.quarantined = 0",
            "d.dataset IN (" + ",".join("?" for _ in allowed) + ")",
        ]
        parameters: list[Any] = list(allowed)
        if not scope.allow_restricted:
            conditions.append("d.visibility = ?")
            parameters.append(Visibility.PUBLIC.value)
        if tiers:
            conditions.append("d.tier IN (" + ",".join("?" for _ in tiers) + ")")
            parameters.extend(tiers)
        if languages:
            conditions.append("d.language IN (" + ",".join("?" for _ in languages) + ")")
            parameters.extend(languages)
        sql = (
            "SELECT c.chunk_id, c.document_id, c.ordinal, c.heading_path, c.heading_anchor, "
            "c.text, c.text_hash, c.char_count, c.truncated, c.oversized, c.part_index, "
            "d.dataset, d.source_path, d.source_url, d.license, d.license_source, d.title, "
            "d.tier, d.visibility, 0.0 AS score "
            "FROM chunks c JOIN documents d ON d.document_id = c.document_id "
            "WHERE " + " AND ".join(conditions) + " ORDER BY c.chunk_id"
        )
        rows = self._execute(sql, parameters).fetchall()
        return tuple(_search_hit_from_row(row) for row in rows)


def _document_from_row(row: sqlite3.Row) -> DocumentRecord:
    return DocumentRecord(
        document_id=str(row["document_id"]),
        dataset=str(row["dataset"]),
        source_path=str(row["source_path"]),
        source_url=str(row["source_url"]),
        title=str(row["title"]),
        license=str(row["license"]),
        license_source=row["license_source"],
        tier=Tier(str(row["tier"])),
        visibility=Visibility(str(row["visibility"])),
        language=row["language"],
        content_hash=str(row["content_hash"]),
        manifest_hash=row["manifest_hash"],
        byte_size=int(row["byte_size"]),
        mirror_revision=row["mirror_revision"],
        chunker_version=str(row["chunker_version"]),
        ingested_at=str(row["ingested_at"]),
    )


def _chunk_from_row(row: sqlite3.Row) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=str(row["chunk_id"]),
        document_id=str(row["document_id"]),
        ordinal=int(row["ordinal"]),
        heading_path=tuple(json.loads(row["heading_path"])),
        heading_anchor=str(row["heading_anchor"]),
        text=str(row["text"]),
        text_hash=str(row["text_hash"]),
        char_count=int(row["char_count"]),
        kind=ChunkKind(str(row["kind"])),
        part_index=int(row["part_index"]),
        truncated=bool(row["truncated"]),
        original_chars=row["original_chars"],
        oversized=bool(row["oversized"]),
        revision=int(row["revision"]),
        quarantined=bool(row["quarantined"]),
    )


def _run_from_row(row: sqlite3.Row) -> IndexRunRecord:
    return IndexRunRecord(
        run_id=str(row["run_id"]),
        started_at=str(row["started_at"]),
        completed_at=row["completed_at"],
        input_hash=str(row["input_hash"]),
        status=IndexRunStatus(str(row["status"])),
        documents_indexed=int(row["documents_indexed"]),
        chunks_created=int(row["chunks_created"]),
        chunks_updated=int(row["chunks_updated"]),
        chunks_unchanged=int(row["chunks_unchanged"]),
        chunks_removed=int(row["chunks_removed"]),
        documents_removed=int(row["documents_removed"]),
        truncated_chunks=int(row["truncated_chunks"]),
        oversized_chunks=int(row["oversized_chunks"]),
        empty_sections=int(row["empty_sections"]),
        quarantined_chunks=int(row["quarantined_chunks"]),
        note=row["note"],
    )


def _search_hit_from_row(row: sqlite3.Row) -> SearchHit:
    return SearchHit(
        chunk_id=str(row["chunk_id"]),
        document_id=str(row["document_id"]),
        dataset=str(row["dataset"]),
        source_path=str(row["source_path"]),
        source_url=str(row["source_url"]),
        license=str(row["license"]),
        license_source=row["license_source"],
        tier=Tier(str(row["tier"])),
        visibility=Visibility(str(row["visibility"])),
        title=str(row["title"]),
        heading_path=tuple(json.loads(row["heading_path"])),
        heading_anchor=str(row["heading_anchor"]),
        ordinal=int(row["ordinal"]),
        part_index=int(row["part_index"]),
        text=str(row["text"]),
        text_hash=str(row["text_hash"]),
        char_count=int(row["char_count"]),
        truncated=bool(row["truncated"]),
        oversized=bool(row["oversized"]),
        score=float(row["score"]),
    )


def _rule_source_from_row(row: sqlite3.Row, store: ChunkStore) -> RuleSourceRow:
    chunk = store.chunk(str(row["chunk_id"]))
    document = None if chunk is None else store.document(chunk.document_id)
    return RuleSourceRow(
        rule_id=str(row["rule_id"]),
        rule_version=int(row["rule_version"]),
        chunk_id=str(row["chunk_id"]),
        document_id="" if chunk is None else chunk.document_id,
        source_path="" if document is None else document.source_path,
        heading_path=() if chunk is None else chunk.heading_path,
        heading_anchor="" if chunk is None else chunk.heading_anchor,
        text_hash="" if chunk is None else chunk.text_hash,
    )
