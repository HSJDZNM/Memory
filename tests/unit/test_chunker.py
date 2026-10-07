"""Phase 3 分块器单元测试：front matter、标题路径、代码块原子、预算与截断、稳定性。"""

from __future__ import annotations

import pytest

from retrieval import chunker
from retrieval.chunker import (
    ANCHOR_PREAMBLE,
    blocks_are_preserved,
    chunk_document,
    compact_text,
    fence_match,
    find_sections,
    iter_blocks,
    search_text,
    split_front_matter,
)
from retrieval.models import ChunkKind, document_id_for, sha256_text

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


def test_bom_does_not_shift_front_matter_coordinates() -> None:
    """BOM 只是被跳过的前缀，不得让 front matter 的边界错位（复核发现的坐标空间缺陷）。"""

    text = "\ufeff---" + chr(10) + "title: x" + chr(10) + "---" + chr(10) + "# H" + chr(10) + chr(10) + "body" + chr(10)
    front, body = split_front_matter(text)
    assert front.kind == "yaml"
    # 边界错位时 raw 会少掉最后一个 "-"，YAML 于是"解析失败"；错位修好后没有警告。
    assert front.warning is None
    assert front.raw == "---" + chr(10) + "title: x" + chr(10) + "---"
    assert front.metadata["title"] == "x"
    assert body == "# H" + chr(10) + chr(10) + "body" + chr(10)
    # 带不带 BOM 必须得到同一份正文（body 里不许残留分隔符残字）。
    assert split_front_matter(text.lstrip("\ufeff"))[1] == body


def test_bom_before_a_heading_is_not_swallowed_into_the_preamble() -> None:
    """没有 front matter 时，BOM 也不得留在正文里，否则首行标题会被吞进前言。"""

    text = "\ufeff# Title" + chr(10) + chr(10) + "body text" + chr(10)
    front, body = split_front_matter(text)
    assert front.kind == ""
    assert body == "# Title" + chr(10) + chr(10) + "body text" + chr(10)
    assert [section.anchor for section in find_sections(body)] == ["title"]


def test_bom_html_comment_front_matter_keeps_coordinates() -> None:
    text = "\ufeff<!--" + chr(10) + "title: y" + chr(10) + "-->" + chr(10) + "# H2" + chr(10) + chr(10) + "body" + chr(10)
    front, body = split_front_matter(text)
    assert front.kind == "html-comment"
    assert front.raw == "<!--" + chr(10) + "title: y" + chr(10) + "-->"
    assert front.metadata["title"] == "y"
    assert body == "# H2" + chr(10) + chr(10) + "body" + chr(10)


def test_yaml_values_json_cannot_serialize_do_not_break_chunking() -> None:
    """YAML 的日期 / 二进制 / 集合不得让整份文档分块失败（复核发现的 TypeError 逃逸）。"""

    nl = chr(10)
    text = (
        "---" + nl
        + "title: x" + nl
        + "date: 2024-01-01" + nl
        + "blob: !!binary aGk=" + nl
        + "tags: !!set {beta: null, alpha: null, gamma: null}" + nl
        + "2024-01-02: 键本身也是日期" + nl
        + "nested: {2024-01-03: y}" + nl
        + "---" + nl
        + "# H" + nl + nl + "body" + nl
    )
    front, body = split_front_matter(text)
    assert front.kind == "yaml"
    # 元数据转换失败会退化成"解析失败"警告，这里必须是真解析成功、没有警告。
    assert front.warning is None
    assert front.metadata["date"] == "2024-01-01"
    assert front.metadata["blob"] == "hi"
    # 集合没有固有顺序：退化文本必须排序后才拼接，否则同一输入会得到两种结果。
    assert front.metadata["tags"] == "{alpha, beta, gamma}"
    assert front.metadata["2024-01-02"] == "键本身也是日期"
    assert front.metadata["nested"] == '{"2024-01-03": "y"}'
    assert body == "# H" + nl + nl + "body" + nl
    # 同一输入两次得到同一份元数据（确定性是模块的硬约定）。
    again, _ = split_front_matter(text)
    assert dict(again.metadata) == dict(front.metadata)
    # 真正要保证的事：一个元数据字段不能让整个分块步骤失败。
    _, chunks = chunk_document(text, document_id="doc_meta", max_chars=200, hard_max_chars=400)
    assert [(item.heading_anchor, item.text) for item in chunks] == [("h", "body")]


def test_fence_info_string_may_contain_spaces() -> None:
    """带参数的围栏（```python title="x.py" 这类）必须被认成围栏（复核发现）。

    旧正则的 info 组不许出现空白，于是 ```jsx live / ```bash copy 整行被
    当成正文，块里的 # 注释被 find_sections 当成标题——代码被切碎，正是本模块要防的事。
    """

    cases = (
        ('```python title="x.py"', FENCE, 'python title="x.py"'),
        ("```jsx live", FENCE, "jsx live"),
        ("```bash copy", FENCE, "bash copy"),
        ("~~~text with spaces", "~~~", "text with spaces"),
    )
    for opening, closing, expected_info in cases:
        text = (
            "# Title" + chr(10) + chr(10)
            + opening + chr(10) + "# NOT-A-HEADING" + chr(10) + "print(1)" + chr(10)
            + closing + chr(10) + chr(10) + "## After" + chr(10) + chr(10) + "tail" + chr(10)
        )
        sections = find_sections(text)
        assert [section.anchor for section in sections] == ["title", "title/after"], opening
        code = [
            block
            for section in sections
            for block in section.blocks
            if block.kind is ChunkKind.CODE
        ]
        assert len(code) == 1, opening
        assert "# NOT-A-HEADING" in code[0].text, opening
        assert code[0].info == expected_info, opening


def test_backtick_fence_info_string_may_not_contain_a_backtick() -> None:
    """CommonMark：反引号围栏的 info string 含反引号 -> 这行不是围栏；波浪线围栏允许。"""

    assert fence_match(FENCE + "py" + chr(96) + "thon") is None
    tilde = fence_match("~~~info " + chr(96) + " backtick")
    assert tilde is not None
    assert tilde.group(1) == "~~~"
    # 普通围栏与带空格的 info string 都要认得出来。
    assert fence_match(FENCE + "python").group(2) == "python"
    assert fence_match("   " + FENCE + "   ").group(2) == ""
    assert fence_match("not a fence") is None


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


def test_long_line_over_budget_is_split_at_sentence_boundaries_without_loss() -> None:
    """一行 > max_chunk_chars 但 ≤ hard_max：按句读拆成多片，全部无损（不再静默截断）。"""

    line = " ".join(
        "Rule {} requires the reviewer to record a decision before merging.".format(index)
        for index in range(12)
    )
    assert len(line) > 400
    text = "# Title" + chr(10) + chr(10) + line + chr(10)
    _, chunks = chunk(text, max_chars=400, hard_max_chars=4000)
    assert len(chunks) > 1
    assert all(item.truncated is False for item in chunks)
    assert all(item.original_chars is None for item in chunks)
    assert all(item.oversized is False for item in chunks)
    assert all(item.char_count == len(item.text) <= 400 for item in chunks)
    assert all(item.text_hash == sha256_text(item.text) for item in chunks)
    section = next(item for item in find_sections(text) if item.anchor == "title")
    assert blocks_are_preserved(section.body, [item.text for item in chunks])
    assert compact_text(section.body) == compact_text("".join(item.text for item in chunks))
    # 无损是**逐字**的：片段首尾相接就是原行，既不丢字也不插字。
    assert "".join(item.text for item in chunks) == line
    # 切点落在句读上：除最后一片外，每片都以句末标点收尾（切点后的空白留在左片）。
    assert all(item.text.rstrip().endswith(".") for item in chunks[:-1])
    # 同一输入必须得到同一输出：片数、文本与哈希都不许随调用漂移。
    _, again = chunk(text, max_chars=400, hard_max_chars=4000)
    assert [(item.text, item.text_hash) for item in again] == [
        (item.text, item.text_hash) for item in chunks
    ]


def test_unbreakable_unit_over_hard_limit_is_truncated_and_counted() -> None:
    """没有断点可用的单元超过硬上限：恰好一片，截到硬上限并如实记账（original_chars 精确）。"""

    payload = "z" * 9000
    text = "# Title" + chr(10) + chr(10) + payload + chr(10)
    _, chunks = chunk(text, max_chars=400, hard_max_chars=1000)
    assert len(chunks) == 1
    assert chunks[0].truncated is True
    assert chunks[0].original_chars == 9000
    assert chunks[0].char_count == 1000 == len(chunks[0].text)
    assert chunks[0].oversized is True


def test_cjk_long_line_is_split_at_cjk_punctuation_without_loss() -> None:
    """中文长行（整段无换行）按 。！？； 切分：不切开汉字，也不丢字符。"""

    endings = ("。", "！", "？", "；")
    line = "".join(
        "第{}条：评审必须记录结论{}".format(index, endings[index % len(endings)])
        for index in range(60)
    )
    assert len(line) > 400
    text = "# 标题" + chr(10) + chr(10) + line + chr(10)
    _, chunks = chunk(text, max_chars=200, hard_max_chars=4000)
    assert len(chunks) > 1
    assert all(item.truncated is False for item in chunks)
    assert all(item.char_count == len(item.text) <= 200 for item in chunks)
    assert compact_text(line) == compact_text("".join(item.text for item in chunks))
    assert "".join(item.text for item in chunks) == line
    assert all(item.text.rstrip().endswith(endings) for item in chunks[:-1])
    # 中文句读本身是断点，不需要后面的空白：每片都必须是原来的连续子串（不切开任何汉字）。
    for item in chunks:
        assert item.text in line


def test_over_budget_line_inside_multi_line_paragraph_keeps_every_character() -> None:
    """真实语料形态：多行段落里只有一行超预算——该行按句读拆开，段落整体无损。"""

    long_line = " ".join(
        "Step {} describes what the pipeline must check before release.".format(index)
        for index in range(10)
    )
    text = (
        "# Title" + chr(10) + chr(10)
        + chr(10).join(["Short intro line.", long_line, "Short trailing line."]) + chr(10)
    )
    _, chunks = chunk(text, max_chars=200, hard_max_chars=4000)
    assert len(chunks) > 1
    assert all(item.truncated is False for item in chunks)
    section = next(item for item in find_sections(text) if item.anchor == "title")
    assert blocks_are_preserved(section.body, [item.text for item in chunks])
    assert compact_text("".join(item.text for item in chunks)) == compact_text(section.body)
    assert compact_text(long_line) in compact_text("".join(item.text for item in chunks))
    # 每片都是原段的**连续子串**：不丢字、不插字、不改字（打包只在片与片之间重排空白）。
    assert all(item.text in section.body for item in chunks)


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
