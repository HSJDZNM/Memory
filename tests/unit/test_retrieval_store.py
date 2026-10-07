"""Phase 3 存储层单元测试：事务原子性、嵌套语义与 FTS 唯一性。

对应复核发现：多语句变更方法各自不带事务（store.py:499）与 FTS 行唯一性没有维护/校验
（store.py:736）。两条都要求"失败必须整体回滚、不许留下半套状态"。
"""

from __future__ import annotations

import sqlite3

import pytest

from retrieval.models import (
    AccessScope,
    ChunkDraft,
    DocumentRecord,
    QuarantineOrigin,
    StoreError,
    Tier,
    Visibility,
    sha256_text,
)
from retrieval.store import ChunkStore


def make_document(document_id: str = "doc_a", path: str = "guides/a.md") -> DocumentRecord:
    return DocumentRecord(
        document_id=document_id,
        dataset="guides",
        source_path=path,
        source_url="https://example.invalid/" + path,
        title="Fixture",
        license="CC0-1.0 (fixture)",
        tier=Tier.GUIDANCE,
        visibility=Visibility.PUBLIC,
        content_hash=sha256_text(path),
        byte_size=1,
        ingested_at="2026-01-01T00:00:00Z",
    )


def make_draft(
    chunk_id: str, text: str, *, document_id: str = "doc_a", ordinal: int = 0
) -> ChunkDraft:
    return ChunkDraft(
        chunk_id=chunk_id,
        document_id=document_id,
        ordinal=ordinal,
        heading_path=("Fixture",),
        heading_anchor="fixture",
        text=text,
        text_hash=sha256_text(text),
        char_count=len(text),
    )


def seeded_store() -> ChunkStore:
    store = ChunkStore(":memory:")
    store.upsert_document(make_document())
    store.replace_chunks(
        "doc_a",
        (
            make_draft("chunk_a", "alpha body", ordinal=0),
            make_draft("chunk_b", "beta body", ordinal=1),
        ),
    )
    return store


def test_transaction_control_statements_follow_the_store_error_contract(monkeypatch) -> None:
    """BEGIN / COMMIT / ROLLBACK 失败必须落 StoreError，且不许盖掉原始异常（复核发现）。"""

    store = ChunkStore(":memory:")
    try:
        # 没有活动事务时 COMMIT 会真的失败：sqlite3.OperationalError -> StoreError。
        assert not store._raw.in_transaction
        with pytest.raises(StoreError):
            store._run_control("COMMIT")

        # ROLLBACK 失败：原始异常原样抛出，回滚失败只作为 note 附上。
        real_control = store._run_control

        def flaky(sql: str) -> None:
            if sql.strip().upper().startswith("ROLLBACK"):
                raise StoreError("模拟 ROLLBACK 失败")
            real_control(sql)

        with monkeypatch.context() as patcher:
            patcher.setattr(store, "_run_control", flaky)
            with pytest.raises(RuntimeError) as failure:
                with store.transaction():
                    raise RuntimeError("原始失败")
        notes = getattr(failure.value, "__notes__", [])
        assert any("ROLLBACK" in note for note in notes), notes

        # 回滚失败这件事本身不可修复：连接会停在事务里——这是必须能被读出来的后果，
        # 不是"静默恢复"。只有真的回滚成功之后，句柄才回到可用的干净状态。
        assert store._raw.in_transaction is True
        store._raw.execute("ROLLBACK")
        assert store._raw.in_transaction is False
        store.upsert_document(make_document("doc_after"))
        assert store.document("doc_after") is not None
    finally:
        store.close()


def test_replace_chunks_rolls_back_when_a_write_fails(monkeypatch) -> None:
    """中途失败必须整体回滚：不许留下负序号或缺 FTS 行的半套状态。"""

    store = seeded_store()
    try:
        original = ChunkStore._index_chunk_fts
        calls = {"count": 0}

        def flaky(self, chunk_id, text, heading_path):
            calls["count"] += 1
            if calls["count"] == 2:
                raise StoreError("模拟写入中断")
            return original(self, chunk_id, text, heading_path)

        monkeypatch.setattr(ChunkStore, "_index_chunk_fts", flaky)
        with pytest.raises(StoreError):
            store.replace_chunks(
                "doc_a",
                (
                    make_draft("chunk_c", "gamma body", ordinal=0),
                    make_draft("chunk_d", "delta body", ordinal=1),
                ),
            )
        monkeypatch.undo()

        chunks = store.chunks("doc_a")
        assert [chunk.chunk_id for chunk in chunks] == ["chunk_a", "chunk_b"]
        assert sorted(chunk.ordinal for chunk in chunks) == [0, 1]
        assert store.fts_row_count() == 2
        store.assert_integrity()
    finally:
        store.close()


def test_nested_transaction_does_not_commit_the_outer_work() -> None:
    """内层事务不得提交外层未完成的改动：嵌套只记账，由最外层决定提交或回滚。"""

    store = ChunkStore(":memory:")
    try:
        with pytest.raises(RuntimeError):
            with store.transaction():
                store.upsert_document(make_document("doc_outer"))
                # 自带事务的多语句方法：它绝不能在这里 COMMIT（那会把外层一起提交）。
                store.replace_chunks(
                    "doc_outer",
                    (make_draft("chunk_outer", "outer body", document_id="doc_outer"),),
                )
                raise RuntimeError("外层失败")

        assert store.document("doc_outer") is None
        assert store.chunks("doc_outer") == ()
        assert store.fts_row_count() == 0
    finally:
        store.close()


def test_nested_transaction_commits_once_when_everything_succeeds() -> None:
    store = ChunkStore(":memory:")
    try:
        with store.transaction():
            store.upsert_document(make_document("doc_ok"))
            store.replace_chunks(
                "doc_ok", (make_draft("chunk_ok", "ok body", document_id="doc_ok"),)
            )
        assert store.document("doc_ok") is not None
        assert [chunk.chunk_id for chunk in store.chunks("doc_ok")] == ["chunk_ok"]
        store.assert_integrity()
    finally:
        store.close()


def test_release_quarantine_is_atomic(monkeypatch) -> None:
    """解除隔离是多语句操作：写 FTS 失败时不许留下"记录已删、标志已清"的半套状态。"""

    store = seeded_store()
    try:
        chunk = store.chunk("chunk_a")
        assert chunk is not None
        store.quarantine(
            "chunk_a",
            reason="测试隔离",
            text_hash=chunk.text_hash,
            quarantined_at="2026-01-01T00:00:00Z",
            document_id="doc_a",
            origin=QuarantineOrigin.RUNTIME,
        )

        def explode(self, chunk_id, text, heading_path):
            raise StoreError("模拟 FTS 写入失败")

        monkeypatch.setattr(ChunkStore, "_index_chunk_fts", explode)
        with pytest.raises(StoreError):
            store.release_quarantine("chunk_a")
        monkeypatch.undo()

        assert [item.chunk_id for item in store.quarantined()] == ["chunk_a"]
        assert store.chunk("chunk_a").quarantined is True
        store.assert_integrity()
    finally:
        store.close()


def test_prune_dataset_is_atomic(monkeypatch) -> None:
    """删除失效文档要么全成、要么全不动：中途失败不许删一半。"""

    store = ChunkStore(":memory:")
    try:
        store.upsert_document(make_document("doc_a", "guides/a.md"))
        store.upsert_document(make_document("doc_b", "guides/b.md"))
        store.replace_chunks("doc_a", (make_draft("chunk_a", "alpha", document_id="doc_a"),))
        store.replace_chunks("doc_b", (make_draft("chunk_b", "beta", document_id="doc_b"),))

        original = ChunkStore._delete_document
        calls = {"count": 0}

        def flaky(self, document_id):
            calls["count"] += 1
            if calls["count"] == 2:
                raise StoreError("模拟删除中断")
            return original(self, document_id)

        monkeypatch.setattr(ChunkStore, "_delete_document", flaky)
        with pytest.raises(StoreError):
            store.prune_dataset("guides", keep=())
        monkeypatch.undo()

        # 第一份文档已经被删过一次：回滚之后它必须原样还在。
        assert {item.document_id for item in store.documents()} == {"doc_a", "doc_b"}
        assert store.fts_row_count() == 2
        store.assert_integrity()
    finally:
        store.close()


def test_release_quarantine_keeps_exactly_one_fts_row() -> None:
    """解除隔离走"先删后插"：重复行会让同一个 chunk 在 search() 里出现两次（复核发现）。"""

    store = seeded_store()
    try:
        chunk = store.chunk("chunk_a")
        assert chunk is not None
        store.quarantine(
            "chunk_a",
            reason="测试隔离",
            text_hash=chunk.text_hash,
            quarantined_at="2026-01-01T00:00:00Z",
            document_id="doc_a",
            origin=QuarantineOrigin.RUNTIME,
        )
        # 模拟"隔离期间正文变了"：重切会按新哈希把它重新写回 FTS（旧隔离记录随之失效）。
        store.replace_chunks(
            "doc_a",
            (
                make_draft("chunk_a", "alpha body (revised)", ordinal=0),
                make_draft("chunk_b", "beta body", ordinal=1),
            ),
        )
        assert store.fts_row_count() == 2

        assert store.release_quarantine("chunk_a") is True
        scope = AccessScope(subject="unit-user", datasets=frozenset({"guides"}))
        hits = [hit.chunk_id for hit in store.search(expression="revised", scope=scope, limit=10)]
        assert hits == ["chunk_a"]
        assert store.fts_row_count() == 2
        store.assert_integrity()
    finally:
        store.close()


def test_duplicate_fts_row_is_reported_as_corruption(tmp_root) -> None:
    """FTS 行多出来同样是结构损坏：必须在打开时就拒绝，而不是 search() 返回两次。"""

    path = tmp_root / "duplicate.sqlite3"
    store = ChunkStore(path)
    store.upsert_document(make_document())
    store.replace_chunks("doc_a", (make_draft("chunk_a", "alpha body"),))
    store.close()

    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO chunks_fts(chunk_id, text, heading_path) VALUES (?,?,?)",
        ("chunk_a", "alpha body", "Fixture"),
    )
    connection.commit()
    connection.close()

    with pytest.raises(StoreError, match="FTS 行总数"):
        ChunkStore(path, create=False)
