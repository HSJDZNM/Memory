"""Phase 3 分块器单元测试：front matter、标题路径、代码块原子、预算与截断、稳定性。"""

from __future__ import annotations

import pytest

from retrieval.chunker import (
    ANCHOR_PREAMBLE,
    blocks_are_preserved,
    chunk_document,
    compact_text,
    find_sections,
    iter_blocks,
    search_text,
    split_front_matter,
)
from retrieval.models import ChunkKind, document_id_for

from conftest import RETRIEVAL_FIXTURES

INDEX_FIXTURE = RETRIEVAL_FIXTURES / "guides" / "index.md"
# 反引号围栏在源码里写三次很吵，统一用它拼装，避免"文档写一套、代码跑一套"。
FENCE = chr(96) * 3


def chunk(
    text: str, *, max_chars: int = 200, hard_max_chars: int = 400, document_id: str = "doc_test"
):
    return chunk_document(
        text,
        document_id=document_id,
        max_chars=max_chars,
        hard_max_chars=hard_max_chars,
    )


def test_yaml_front_matter_is_removed_and_metadata_is_kept() -> None:
    front, body = split_front_matter(INDEX_FIXTURE.read_text(encoding="utf-8"))
    assert front.kind == "yaml"
    assert front.removed is True
    assert front.metadata["title"] == "Reviewer Guide"
    assert front.metadata["source_url"].startswith("https://example.invalid/")
    assert "title:" not in body
    assert body.startswith("# Reviewer Guide")


def test_html_comment_front_matter_is_removed() -> None:
    text = (RETRIEVAL_FIXTURES / "guides" / "topics.md").read_text(encoding="utf-8")
    front, body = split_front_matter(text)
    assert front.kind == "html-comment"
    assert front.metadata["title"] == "Review topics"
    assert body.lstrip().startswith("# Review Topics")


def test_unterminated_front_matter_keeps_every_character() -> None:
    text = "---\ntitle: broken\n\n# Real heading\n\nbody text\n"
    front, body = split_front_matter(text)
    assert front.kind == "yaml-unterminated"
    assert front.removed is False
    assert front.warning is not None
    # 不删正文：即便是破损 front matter，也必须逐字保留。
    assert body == text


def test_heading_inside_code_fence_is_not_a_heading() -> None:
    text = (
        "# Title\n\n"
        + FENCE
        + "python\n"
        "# NOT-A-HEADING\n"
        "def f():\n"
        "    return 1\n"
        + FENCE
        + "\n\n## After\n\ntail\n"
    )
    sections = find_sections(text)
    assert [section.anchor for section in sections] == ["title", "title/after"]
    code_chunks = [item for item in chunk(text)[1] if item.kind is ChunkKind.CODE]
    assert len(code_chunks) == 1
    assert "# NOT-A-HEADING" in code_chunks[0].text


def test_code_block_is_never_split_even_over_budget() -> None:
    body = "\n".join(f"line {index} of the sample" for index in range(12))
    text = f"# Title\n\nprose before\n\n{FENCE}text\n{body}\n{FENCE}\n\nprose after\n"
    _, chunks = chunk(text, max_chars=80, hard_max_chars=4000)
    code = [item for item in chunks if item.kind is ChunkKind.CODE]
    assert len(code) == 1
    assert body in code[0].text
    assert code[0].oversized is True
    assert code[0].truncated is False
    # 该章节的其它块仍然完整保留。
    section = next(item for item in find_sections(text) if item.anchor == "title")
    assert blocks_are_preserved(section.body, [item.text for item in chunks])


def test_prose_is_split_at_line_boundaries_without_losing_text() -> None:
    lines = [f"The reviewer explains point number {index} in detail." for index in range(20)]
    text = "# Title\n\n" + "\n".join(lines) + "\n"
    _, chunks = chunk(text, max_chars=120, hard_max_chars=4000)
    assert len(chunks) > 1
    assert all(item.truncated is False for item in chunks)
    section = next(item for item in find_sections(text) if item.anchor == "title")
    assert blocks_are_preserved(section.body, [item.text for item in chunks])


def test_single_line_over_hard_limit_is_truncated_and_recorded() -> None:
    payload = "x" * 900
    text = f"# Title\n\n{FENCE}text\n{payload}\n{FENCE}\n"
    _, chunks = chunk(text, max_chars=100, hard_max_chars=300)
    assert len(chunks) == 1
    assert chunks[0].truncated is True
    assert chunks[0].oversized is True
    assert chunks[0].original_chars == len(payload) + len("text") + 2 * len(FENCE) + 2
    assert chunks[0].char_count == 300


def test_duplicate_headings_get_distinct_stable_anchors() -> None:
    text = INDEX_FIXTURE.read_text(encoding="utf-8")
    _, chunks = chunk(text, max_chars=400, hard_max_chars=1200)
    anchors = [item.heading_anchor for item in chunks]
    assert len(anchors) == len(set(anchors))
    notes = [item for item in chunks if "notes" in item.heading_anchor]
    assert len(notes) == 2
    assert notes[0].heading_path == notes[1].heading_path == ("Reviewer Guide", "Notes")
    assert notes[0].heading_anchor.endswith("notes")
    assert notes[1].heading_anchor.endswith("notes#2")
    assert "DUP-MARKER" in notes[1].text


def test_empty_section_is_skipped_but_visible_in_sections() -> None:
    text = "# Title\n\nbody\n\n## Appendix\n\n## After Appendix\n\ntail\n"
    sections = find_sections(text)
    empty = [section for section in sections if section.is_empty]
    assert [section.anchor for section in empty] == ["title/appendix"]
    _, chunks = chunk(text)
    assert all(item.heading_anchor != "title/appendix" for item in chunks)


def test_chunk_ids_and_hashes_are_stable_and_content_bound() -> None:
    original = "# Title\n\nalpha text\n\n## First\n\nfirst body\n\n## Second\n\nsecond body\n"
    document_id = document_id_for("guides", "index.md")
    _, first = chunk(original, max_chars=400, hard_max_chars=1200, document_id=document_id)
    _, again = chunk(original, max_chars=400, hard_max_chars=1200, document_id=document_id)
    assert [(item.chunk_id, item.text_hash) for item in first] == [
        (item.chunk_id, item.text_hash) for item in again
    ]

    changed = original.replace("second body", "second body with a correction")
    _, after = chunk(changed, max_chars=400, hard_max_chars=1200, document_id=document_id)
    before_by_anchor = {item.heading_anchor: item for item in first}
    after_by_anchor = {item.heading_anchor: item for item in after}
    assert set(before_by_anchor) == set(after_by_anchor)
    for anchor, item in before_by_anchor.items():
        other = after_by_anchor[anchor]
        # 同一段原文重建后仍是同一个 ID。
        assert item.chunk_id == other.chunk_id
        if anchor.endswith("second"):
            assert item.text_hash != other.text_hash
        else:
            assert item.text_hash == other.text_hash


def test_unterminated_fence_is_stable_and_preserves_text() -> None:
    text = f"# Title\n\n{FENCE}python\nprint('no closing fence')\n\nmore code\n"
    _, chunks = chunk(text)
    assert len(chunks) == 1
    assert chunks[0].kind is ChunkKind.CODE
    assert "no closing fence" in chunks[0].text
    assert chunks[0].oversized is False


def test_ordinals_are_sequential_and_unique() -> None:
    text = INDEX_FIXTURE.read_text(encoding="utf-8")
    _, chunks = chunk(text, max_chars=200, hard_max_chars=1200)
    assert [item.ordinal for item in chunks] == list(range(len(chunks)))


def test_search_text_splits_cjk_but_keeps_ascii() -> None:
    assert search_text("代码评审 code review") == "代 码 评 审 code review"
    assert search_text("plain ascii") == "plain ascii"


def test_mixed_block_kind_is_reported() -> None:
    text = f"# Title\n\nprose line\n\n{FENCE}text\ncode line\n{FENCE}\n"
    _, chunks = chunk(text, max_chars=400, hard_max_chars=1200)
    assert chunks[0].kind is ChunkKind.MIXED


def test_preamble_without_heading_becomes_its_own_section() -> None:
    text = "intro line without any heading\n\n# Later\n\nbody\n"
    _, chunks = chunk(text)
    assert chunks[0].heading_anchor == ANCHOR_PREAMBLE
    assert chunks[0].heading_path == ()


def test_blocks_helper_reports_lossless_coverage() -> None:
    text = INDEX_FIXTURE.read_text(encoding="utf-8")
    _, chunks = chunk(text, max_chars=200, hard_max_chars=1200)
    for section in find_sections(split_front_matter(text)[1]):
        if section.is_empty:
            continue
        texts = [item.text for item in chunks if item.heading_anchor == section.anchor]
        assert blocks_are_preserved(section.body, texts)
        assert compact_text(section.body) == compact_text("".join(texts))


def test_preamble_heading_does_not_collide_with_preamble_anchor() -> None:
    """前言与标题 "Preamble" 不能抢同一个锚点（复核发现的静默丢正文缺陷）。"""

    text = "intro text before any heading" + chr(10) + chr(10) + "# Preamble" + chr(10) + chr(10) + "more text" + chr(10)
    _, chunks = chunk(text)
    identifiers = [item.chunk_id for item in chunks]
    assert len(identifiers) == len(set(identifiers))
    anchors = [item.heading_anchor for item in chunks]
    assert anchors[0] == ANCHOR_PREAMBLE
    assert anchors[1] == ANCHOR_PREAMBLE + "#2"
    assert any("intro text before any heading" in item.text for item in chunks)
    assert any("more text" in item.text for item in chunks)


def test_multi_line_prose_over_hard_limit_is_split_without_loss() -> None:
    """多行段落超过硬上限时按行边界拆分，不丢字符（只有单行超限才截断）。"""

    lines = ["x" * 100 for _ in range(100)]
    text = "# Title" + chr(10) + chr(10) + chr(10).join(lines) + chr(10)
    _, chunks = chunk(text, max_chars=400, hard_max_chars=1000)
    assert len(chunks) > 1
    assert all(item.truncated is False for item in chunks)
    section = next(item for item in find_sections(text) if item.anchor == "title")
    assert blocks_are_preserved(section.body, [item.text for item in chunks])
    assert all(item.char_count <= 1000 for item in chunks)


def test_single_long_line_still_truncates_and_is_counted() -> None:
    """单行没有断点可用：截断并记录，绝不静默丢弃。"""

    text = "# Title" + chr(10) + chr(10) + ("y" * 5000) + chr(10)
    _, chunks = chunk(text, max_chars=400, hard_max_chars=1000)
    assert len(chunks) >= 1
    assert chunks[0].truncated is True
    assert chunks[0].original_chars == 5000


def test_chunker_rejects_contradictory_budgets() -> None:
    with pytest.raises(Exception):
        chunk_document("# T\n\nbody\n", document_id="doc", max_chars=500, hard_max_chars=100)
    with pytest.raises(Exception):
        chunk_document("# T\n\nbody\n", document_id="", max_chars=10, hard_max_chars=100)


def test_iter_blocks_keeps_fence_lines() -> None:
    blocks = iter_blocks(f"before\n\n{FENCE}sh\necho hi\n{FENCE}\n\nafter\n")
    assert [block.kind for block in blocks] == [
        ChunkKind.PROSE,
        ChunkKind.CODE,
        ChunkKind.PROSE,
    ]
    assert blocks[1].info == "sh"
