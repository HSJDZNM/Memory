"""Phase 3 摄取与索引集成测试：幂等、增量替换、删除失效、中断、隔离与溯源。"""

from __future__ import annotations

from pathlib import Path

import pytest

from retrieval.corpus import load_corpus, verify_corpus
from retrieval.indexer import IndexingError, ingest, needs_reindex
from retrieval.models import (
    AccessScope,
    IndexRunStatus,
    RetrievalQuery,
    RetrievalStatus,
)
from retrieval.retriever import FtsRetriever
from retrieval.store import ChunkStore, StoreError

from conftest import (
    REPO_ROOT,
    RETRIEVAL_FIXTURES,
    load_fixture_corpus,
    write_fixture_corpus,
)

pytestmark = pytest.mark.integration

GUIDE_MIRROR = "mirror/guides"
INDEX_DOCUMENT = "index.md"


def open_store(tmp_root: Path) -> ChunkStore:
    return ChunkStore(tmp_root / "index.sqlite3")


def scope_of(loaded) -> AccessScope:
    return AccessScope(subject="integration-user", datasets=frozenset(loaded.manifest.dataset_names))


def test_real_corpus_is_verified_and_idempotent(tmp_root) -> None:
    loaded = load_corpus(REPO_ROOT / "knowledge" / "corpus.yaml", repo_root=REPO_ROOT)
    assert loaded.verification.ok, [issue.detail for issue in loaded.verification.issues]
    assert len(loaded.entries) >= 10

    store = open_store(tmp_root)
    try:
        first = ingest(loaded, store, repo_root=REPO_ROOT)
        assert first.status is IndexRunStatus.COMPLETED
        assert first.documents_indexed == len(loaded.entries)
        assert first.chunks_created > 0
        stats_after_first = store.stats()

        second = ingest(loaded, store, repo_root=REPO_ROOT)
        assert second.status is IndexRunStatus.COMPLETED
        assert second.chunks_created == 0
        assert second.chunks_updated == 0
        assert second.chunks_removed == 0
        assert second.documents_removed == 0
        assert all(outcome.status == "unchanged" for outcome in second.documents)
        stats_after_second = store.stats()
        assert stats_after_second.chunks == stats_after_first.chunks
        assert stats_after_second.documents == stats_after_first.documents

        # 未变化的 chunk 不得被重写：revision 停留在 1，FTS 行数也不变。
        for document in store.documents():
            assert all(chunk.revision == 1 for chunk in store.chunks(document.document_id))
        assert store.fts_row_count() == stats_after_first.chunks
        assert not needs_reindex(loaded, store)
    finally:
        store.close()


def test_real_corpus_records_license_source_and_metadata(tmp_root) -> None:
    loaded = load_corpus(REPO_ROOT / "knowledge" / "corpus.yaml", repo_root=REPO_ROOT)
    store = open_store(tmp_root)
    try:
        ingest(loaded, store, repo_root=REPO_ROOT)
        documents = {f"{item.dataset}:{item.source_path}": item for item in store.documents()}
        owasp = documents[
            "owasp-cheatsheets:14_AI与LLM应用安全/RAG_Security_Cheat_Sheet.md"
        ]
        assert owasp.license == "CC BY-SA 4.0"
        assert owasp.source_url == "https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html"
        assert owasp.content_hash.startswith("sha256:")
        assert owasp.manifest_hash == owasp.content_hash
        assert owasp.hash_drift is False
        assert owasp.byte_size > 0
        pep = documents["python-pep-code-style:pep-8-python-code/index.md"]
        front = dict(store.front_matter(pep.document_id))
        assert front.get("title") == "Style Guide for Python Code"
        assert front.get("copyright", "").lower().startswith("this document has been placed")
    finally:
        store.close()


def test_single_file_change_replaces_only_related_chunks(tmp_root) -> None:
    loaded = load_fixture_corpus(tmp_root)
    store = open_store(tmp_root)
    try:
        ingest(loaded, store, repo_root=tmp_root)
        document_id = loaded.entry("guides", INDEX_DOCUMENT).document_id
        topics_id = loaded.entry("guides", "topics.md").document_id
        before = {chunk.chunk_id: chunk for chunk in store.chunks(document_id)}
        topics_before = {chunk.chunk_id: chunk for chunk in store.chunks(topics_id)}

        original_text = (RETRIEVAL_FIXTURES / "guides" / INDEX_DOCUMENT).read_text(encoding="utf-8")
        corrected_text = original_text.replace(
            "First notes section.", "First notes section, now corrected."
        )
        assert corrected_text != original_text
        (tmp_root / GUIDE_MIRROR / INDEX_DOCUMENT).write_text(
            corrected_text, encoding="utf-8", newline=""
        )
        reloaded = load_fixture_corpus(tmp_root, overrides={"guides/index.md": corrected_text})
        report = ingest(reloaded, store, repo_root=tmp_root)

        assert report.chunks_removed == 0
        after = {chunk.chunk_id: chunk for chunk in store.chunks(document_id)}
        assert set(before) == set(after)
        changed = [
            chunk_id
            for chunk_id, chunk in after.items()
            if chunk.revision > before[chunk_id].revision
        ]
        assert len(changed) == 1
        assert before[changed[0]].text_hash != after[changed[0]].text_hash
        # 变化只落在被改动的章节；其它文档完全没被触碰。
        for chunk_id, chunk in after.items():
            if chunk_id not in changed:
                assert chunk.revision == before[chunk_id].revision == 1
        assert {chunk.chunk_id: chunk.revision for chunk in store.chunks(topics_id)} == {
            chunk_id: chunk.revision for chunk_id, chunk in topics_before.items()
        }
    finally:
        store.close()


def test_removed_entry_invalidates_its_chunks(tmp_root) -> None:
    loaded = load_fixture_corpus(tmp_root)
    store = open_store(tmp_root)
    lexicon = None
    try:
        ingest(loaded, store, repo_root=tmp_root)
        topics_id = loaded.entry("guides", "topics.md").document_id
        retriever = FtsRetriever(store, policy=loaded.policy, lexicon=lexicon)
        before = retriever.retrieve(
            RetrievalQuery(text="production code and its tests", limit=5), scope_of(loaded)
        )
        assert any(item.document_id == topics_id for item in before.results)

        # 清单里去掉该入口（等价于源文件被删除/移出语料）。
        (tmp_root / GUIDE_MIRROR / "topics.md").unlink()
        reloaded = load_fixture_corpus(tmp_root, drop_files=("guides/topics.md",))
        report = ingest(reloaded, store, repo_root=tmp_root)
        assert report.documents_removed == 1
        assert store.document(topics_id) is None
        assert store.chunks(topics_id) == ()

        after = retriever.retrieve(
            RetrievalQuery(text="production code and its tests", limit=5), scope_of(reloaded)
        )
        assert all(item.document_id != topics_id for item in after.results)
    finally:
        store.close()


def test_interrupted_run_is_marked_failed_and_does_not_claim_success(tmp_root) -> None:
    loaded = load_fixture_corpus(tmp_root)
    store = open_store(tmp_root)
    try:
        def explode(entry) -> None:
            if entry.source_path == "topics.md":
                raise RuntimeError("simulated crash")

        with pytest.raises(IndexingError):
            ingest(loaded, store, repo_root=tmp_root, after_document=explode, run_id="run_crash")

        run = store.run("run_crash")
        assert run is not None
        assert run.status is IndexRunStatus.FAILED
        assert run.completed_at is not None
        assert run.note and "simulated crash" in run.note
        # 输入指纹没有提交：下一次仍认为需要重建（不会把半套数据当成最新）。
        assert store.corpus_input_hash is None
        assert needs_reindex(loaded, store)
    finally:
        store.close()


def test_stale_running_run_is_marked_interrupted(tmp_root) -> None:
    loaded = load_fixture_corpus(tmp_root)
    store = open_store(tmp_root)
    try:
        store.start_run("sha256:stale", started_at="2026-09-16T00:00:00Z", run_id="run_stale")
        assert store.run("run_stale").status is IndexRunStatus.RUNNING

        ingest(loaded, store, repo_root=tmp_root, run_id="run_fresh")
        stale = store.run("run_stale")
        assert stale.status is IndexRunStatus.INTERRUPTED
        assert stale.completed_at is not None
        assert store.run("run_fresh").status is IndexRunStatus.COMPLETED
    finally:
        store.close()


def test_quarantine_removes_chunk_and_manifest_release_restores_it(tmp_root) -> None:
    loaded = load_fixture_corpus(tmp_root)
    store = open_store(tmp_root)
    try:
        ingest(loaded, store, repo_root=tmp_root)
        document_id = loaded.entry("adversarial", "poisoned.md").document_id
        target = next(
            chunk for chunk in store.chunks(document_id) if "IGNORE ALL PREVIOUS INSTRUCTIONS" in chunk.text
        )

        quarantined = load_fixture_corpus(
            tmp_root,
            quarantine=[
                {
                    "chunk_id": target.chunk_id,
                    "text_hash": target.text_hash,
                    "reason": "语料内指令注入样本",
                }
            ],
        )
        report = ingest(quarantined, store, repo_root=tmp_root)
        assert report.quarantined_chunks == 1
        assert store.stats().quarantined == 1
        stored = store.chunk(target.chunk_id)
        assert stored is not None and stored.quarantined is True
        assert store.fts_row_count() == store.stats().chunks - 1

        retriever = FtsRetriever(store, policy=quarantined.policy)
        hits = retriever.retrieve(
            RetrievalQuery(text="IGNORE ALL PREVIOUS INSTRUCTIONS shell tool", limit=5),
            scope_of(quarantined),
        )
        assert all(item.chunk_id != target.chunk_id for item in hits.results)

        # 清单里删掉隔离条目 -> 旧隔离自动释放，chunk 重新可检索。
        released = load_fixture_corpus(tmp_root)
        second = ingest(released, store, repo_root=tmp_root)
        assert target.chunk_id in second.released_quarantine
        assert store.stats().quarantined == 0
        assert store.chunk(target.chunk_id).quarantined is False
    finally:
        store.close()


def test_quarantine_with_stale_hash_fails_closed(tmp_root) -> None:
    loaded = load_fixture_corpus(tmp_root)
    store = open_store(tmp_root)
    try:
        ingest(loaded, store, repo_root=tmp_root)
        document_id = loaded.entry("adversarial", "poisoned.md").document_id
        target = store.chunks(document_id)[0]
        stale = load_fixture_corpus(
            tmp_root,
            quarantine=[
                {"chunk_id": target.chunk_id, "text_hash": "sha256:" + "1" * 64, "reason": "旧哈希"}
            ],
        )
        with pytest.raises(IndexingError):
            ingest(stale, store, repo_root=tmp_root)
        assert store.run(store.runs(limit=1)[0].run_id).status is IndexRunStatus.FAILED
    finally:
        store.close()


def test_rule_source_registration_and_cascade_delete(tmp_root) -> None:
    loaded = load_fixture_corpus(
        tmp_root,
        rule_sources=[
            {
                "rule_id": "REVIEW-900",
                "rule_version": 1,
                "dataset": "guides",
                "source_path": "topics.md",
                "heading_path": ["Review Topics", "Tests"],
            }
        ],
    )
    store = open_store(tmp_root)
    try:
        report = ingest(loaded, store, repo_root=tmp_root)
        assert report.rule_sources
        rows = store.rule_sources(rule_id="REVIEW-900")
        assert len(rows) == 1
        row = rows[0]
        assert row.heading_path == ("Review Topics", "Tests")
        assert "same change" in store.chunk(row.chunk_id).text
        assert store.rules_for_chunk(row.chunk_id) == (("REVIEW-900", 1),)

        # 入口被移除后，溯源行随之消失（不允许指向已删除的 chunk）。
        (tmp_root / GUIDE_MIRROR / "topics.md").unlink()
        reloaded = load_fixture_corpus(
            tmp_root,
            drop_files=("guides/topics.md",),
            rule_sources=[],
        )
        ingest(reloaded, store, repo_root=tmp_root)
        assert store.rule_sources(rule_id="REVIEW-900") == ()
    finally:
        store.close()


def test_rule_source_with_unknown_heading_fails(tmp_root) -> None:
    loaded = load_fixture_corpus(
        tmp_root,
        rule_sources=[
            {
                "rule_id": "REVIEW-901",
                "rule_version": 1,
                "dataset": "guides",
                "source_path": "topics.md",
                "heading_path": ["Review Topics", "No Such Heading"],
            }
        ],
    )
    store = open_store(tmp_root)
    try:
        with pytest.raises(IndexingError):
            ingest(loaded, store, repo_root=tmp_root)
    finally:
        store.close()


def test_hash_drift_is_recorded_instead_of_silently_ignored(tmp_root) -> None:
    loaded = load_fixture_corpus(tmp_root, drift=("guides/index.md",))
    assert not loaded.verification.ok
    assert [issue.kind for issue in loaded.verification.drift] == ["hash_mismatch"]

    store = open_store(tmp_root)
    try:
        report = ingest(loaded, store, repo_root=tmp_root)
        assert report.status is IndexRunStatus.COMPLETED
        assert report.drift and report.drift[0].kind == "hash_mismatch"
        drifted = [item for item in store.documents() if item.hash_drift]
        assert [item.source_path for item in drifted] == [INDEX_DOCUMENT]

        # 修正哈希后漂移消失。
        fixed = load_fixture_corpus(tmp_root)
        assert fixed.verification.ok
        second = verify_corpus(fixed, repo_root=tmp_root)
        assert second.ok
    finally:
        store.close()


def test_deleting_a_document_invalidates_cached_results(tmp_root) -> None:
    loaded = load_fixture_corpus(tmp_root)
    store = open_store(tmp_root)
    try:
        ingest(loaded, store, repo_root=tmp_root)
        document_id = loaded.entry("guides", INDEX_DOCUMENT).document_id
        version_before = store.index_version
        removed = store.delete_document(document_id)
        assert removed > 0
        store.bump_generation()
        assert store.index_version != version_before
        assert store.document(document_id) is None
    finally:
        store.close()


def test_corpus_manifest_rejects_unknown_dataset_and_bad_paths(tmp_root) -> None:
    path = write_fixture_corpus(tmp_root)
    from retrieval.corpus import CorpusError

    loaded = load_corpus(path, repo_root=tmp_root)
    with pytest.raises(CorpusError):
        loaded.dataset("does-not-exist")
    assert loaded.manifest.dataset_names == ("adversarial", "guides", "restricted-docs")


# ---------------------------------------------------------------- 复核发现的回归用例

def test_section_displacement_reindex_does_not_conflict(tmp_root) -> None:
    """在文档中间插入/删除章节不得触发 ordinal 冲突（复核发现的阻断级缺陷）。

    旧实现先 INSERT/UPDATE 后 DELETE，位移期间新序号会撞上尚未挪走的旧行，
    导致唯一约束失败、整份文档回滚，并且**重试也永远失败**（只能删库重建）。
    """

    base = (
        "# Title" + chr(10) + chr(10)
        + "intro text" + chr(10) + chr(10)
        + "## Alpha" + chr(10) + chr(10) + "alpha body" + chr(10) + chr(10)
        + "## Beta" + chr(10) + chr(10) + "beta body" + chr(10) + chr(10)
        + "## Gamma" + chr(10) + chr(10) + "gamma body" + chr(10)
    )
    shifted = (
        "# Title" + chr(10) + chr(10)
        + "intro text" + chr(10) + chr(10)
        + "## Inserted" + chr(10) + chr(10) + "new body" + chr(10) + chr(10)  # 最前面插入一节
        + "## Alpha" + chr(10) + chr(10) + "alpha body" + chr(10) + chr(10)
        + "## Gamma" + chr(10) + chr(10) + "gamma body" + chr(10) + chr(10)   # 删掉中间一节
        + "## Delta" + chr(10) + chr(10) + "delta body" + chr(10)             # 末尾新增一节
    )
    loaded = load_fixture_corpus(tmp_root, overrides={"guides/index.md": base})
    store = open_store(tmp_root)
    try:
        ingest(loaded, store, repo_root=tmp_root)
        document_id = loaded.entry("guides", INDEX_DOCUMENT).document_id
        before = {chunk.chunk_id: chunk for chunk in store.chunks(document_id)}

        ingest(
            load_fixture_corpus(tmp_root, overrides={"guides/index.md": shifted}),
            store,
            repo_root=tmp_root,
        )

        after = {chunk.chunk_id: chunk for chunk in store.chunks(document_id)}
        anchors = {chunk.heading_anchor for chunk in after.values()}
        assert any(item.endswith("inserted") for item in anchors)
        assert any(item.endswith("delta") for item in anchors)
        assert not any(item.endswith("beta") for item in anchors)
        # 序号连续、不重复（负序号没有被写回库里）。
        assert sorted(chunk.ordinal for chunk in after.values()) == list(range(len(after)))
        # 未变的 chunk 只换了位置，revision 不变；内容变化的才递增。
        alpha_before = next(
            chunk for chunk in before.values() if chunk.heading_anchor.endswith("alpha")
        )
        alpha_after = next(
            chunk for chunk in after.values() if chunk.heading_anchor.endswith("alpha")
        )
        assert alpha_after.chunk_id == alpha_before.chunk_id
        assert alpha_after.revision == alpha_before.revision == 1
        integrity = store.integrity()
        assert integrity["missing_fts_rows"] == 0 and integrity["orphan_fts_rows"] == 0
    finally:
        store.close()


def test_section_gaining_a_part_does_not_conflict(tmp_root) -> None:
    """一个章节变长、多出一个 part 时同样要能增量重建。"""

    short = "# Title" + chr(10) + chr(10) + "## Long" + chr(10) + chr(10) + "one line" + chr(10)
    long_lines = [f"line {index} of a long section" for index in range(40)]
    long_text = (
        "# Title" + chr(10) + chr(10) + "## Long" + chr(10) + chr(10)
        + chr(10).join(long_lines) + chr(10)
    )
    store = open_store(tmp_root)
    try:
        ingest(
            load_fixture_corpus(tmp_root, overrides={"guides/index.md": short}),
            store,
            repo_root=tmp_root,
        )
        document_id = load_fixture_corpus(tmp_root).entry("guides", INDEX_DOCUMENT).document_id
        ingest(
            load_fixture_corpus(tmp_root, overrides={"guides/index.md": long_text}),
            store,
            repo_root=tmp_root,
        )
        chunks = store.chunks(document_id)
        assert len(chunks) > 1
        assert sorted(chunk.ordinal for chunk in chunks) == list(range(len(chunks)))
        integrity = store.integrity()
        assert integrity["missing_fts_rows"] == 0 and integrity["orphan_fts_rows"] == 0
    finally:
        store.close()


def test_missing_file_fails_closed_and_needs_manifest_removal(tmp_root) -> None:
    """源文件被删除但清单仍引用它：摄取失败关闭，旧 chunk 不会假装还在。"""

    loaded = load_fixture_corpus(tmp_root)
    store = open_store(tmp_root)
    try:
        ingest(loaded, store, repo_root=tmp_root)
        document_id = loaded.entry("guides", "topics.md").document_id
        (tmp_root / GUIDE_MIRROR / "topics.md").unlink()

        # 注意：不能重新 load_fixture_corpus（它会把镜像文件再写回来）；
        # 这里直接用已经解析好的清单再摄取一次，模拟"文件没了但条目还在"。
        with pytest.raises(IndexingError):
            ingest(loaded, store, repo_root=tmp_root)
        run = store.runs(limit=1)[0]
        assert run.status is IndexRunStatus.FAILED
        assert store.document(document_id) is not None  # 旧数据仍在，但 run 是 failed
        assert verify_corpus(loaded, repo_root=tmp_root).ok is False

        # 正确做法：文件删除必须同时从清单移除条目。
        removed = load_fixture_corpus(tmp_root, drop_files=("guides/topics.md",))
        report = ingest(removed, store, repo_root=tmp_root)
        assert report.documents_removed == 1
        assert store.document(document_id) is None
    finally:
        store.close()


def test_failed_run_bumps_generation_so_caches_are_dropped(tmp_root) -> None:
    """失败的 run 也可能改过可检索内容：generation 必须递增，缓存不能继续命中。"""

    original = (RETRIEVAL_FIXTURES / "guides" / INDEX_DOCUMENT).read_text(encoding="utf-8")
    corrected = original.replace("First notes section.", "First notes section, now corrected.")
    loaded = load_fixture_corpus(tmp_root)
    store = open_store(tmp_root)
    try:
        ingest(loaded, store, repo_root=tmp_root)
        version_before = store.index_version

        def explode(entry) -> None:
            if entry.source_path == "topics.md":
                raise RuntimeError("simulated crash after a committed document")

        changed = load_fixture_corpus(tmp_root, overrides={"guides/index.md": corrected})
        with pytest.raises(IndexingError):
            ingest(changed, store, repo_root=tmp_root, after_document=explode)
        assert store.index_version != version_before
    finally:
        store.close()


def test_fts_damage_is_reported_instead_of_looking_empty(tmp_root) -> None:
    """FTS 表被删掉后重建为空表：必须报结构不一致，而不是退化成"没有结果"。"""

    loaded = load_fixture_corpus(tmp_root)
    store = open_store(tmp_root)
    try:
        ingest(loaded, store, repo_root=tmp_root)
        store.close()
        import sqlite3

        connection = sqlite3.connect(tmp_root / "index.sqlite3")
        connection.execute("DROP TABLE chunks_fts")
        connection.commit()
        connection.close()

        with pytest.raises(StoreError):
            ChunkStore(tmp_root / "index.sqlite3", create=False)
    finally:
        pass


def test_run_history_records_every_run(tmp_root) -> None:
    loaded = load_fixture_corpus(tmp_root)
    store = open_store(tmp_root)
    try:
        ingest(loaded, store, repo_root=tmp_root, run_id="run_one")
        ingest(loaded, store, repo_root=tmp_root, run_id="run_two")
        runs = {run.run_id: run for run in store.runs(limit=10)}
        assert set(runs) == {"run_one", "run_two"}
        assert all(run.status is IndexRunStatus.COMPLETED for run in runs.values())
        assert runs["run_one"].input_hash == runs["run_two"].input_hash
        assert store.last_completed_run().run_id in runs
    finally:
        store.close()
