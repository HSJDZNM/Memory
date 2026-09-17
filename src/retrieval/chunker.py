"""章节分块器：把一份 Markdown 镜像切成可检索、可追溯的 chunk。

规则（对应 Phase 3 文档第 3 步）：

1. 去掉 front matter（YAML 的 --- 块，或 OWASP 镜像用的 <!-- --> 注释块），
   元数据交给调用方写进 documents，不进正文；未闭合的 front matter 不删正文、只记警告；
2. 标题路径随 chunk 保存（heading_path 是原文标题，heading_anchor 是稳定锚点）；
3. 代码块是**原子单元**：不在中间切断，也不与其它块合并；
4. 有明确的字符预算：段落按行边界打包，超预算的原子单元单独成 chunk 并记 oversized；
   单个原子单元超过硬上限时截断，记 truncated + original_chars（丢了多少必须能算出来）；
5. 空章节被跳过并计数；重复标题用出现序号区分（锚点稳定且互不相同）；
6. chunk 文本是原文，不解释、不改写、不加摘要。

标题识别只在代码块之外生效：PEP 8 这类文档的代码块里就有以 "#" 开头的注释行，
把它们当标题会把代码切碎（这是本模块存在的主要理由之一）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Tuple

import yaml

from .models import (
    CHUNKER_VERSION,
    ChunkDraft,
    ChunkKind,
    RetrievalError,
    chunk_id_for,
    sha256_text,
)

__all__ = [
    "ANCHOR_PREAMBLE",
    "Block",
    "ChunkerError",
    "FrontMatter",
    "Section",
    "blocks_are_preserved",
    "chunk_document",
    "cjk_split",
    "compact_text",
    "find_sections",
    "front_matter_bounds",
    "heading_anchor",
    "iter_blocks",
    "search_text",
    "split_front_matter",
]

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
# 围栏用 \x60（反引号）的十六进制写法，避免源码里出现难以阅读的连续反引号。
FENCE_RE = re.compile(r"^\s{0,3}(\x60{3,}|~{3,})\s*([^\s\x60]*)\s*$")
SLUG_RE = re.compile(r"[^0-9a-z\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]+")
# 中日韩文字区间：这些语言没有空格分词，FTS5 的 unicode61 会把整段当成一个词，
# 因此索引与查询两侧都按"逐字切分"生成检索文本（同一套切分，避免两侧不一致）。
CJK_RE = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]+"
)

ANCHOR_PREAMBLE = "preamble"


class ChunkerError(RetrievalError):
    """分块失败：内容不可解析或预算参数自相矛盾。"""


@dataclass(frozen=True)
class FrontMatter:
    """front matter 的解析结果。

    kind 取值：yaml / html-comment / yaml-unterminated / html-comment-unterminated。
    未闭合时正文原样保留（不删任何字符），只记录警告。
    """

    kind: str
    raw: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)
    warning: Optional[str] = None

    @property
    def removed(self) -> bool:
        return self.kind in ("yaml", "html-comment")


@dataclass(frozen=True)
class Block:
    """分块器的最小单元：一段连续正文，或一个完整的代码块。"""

    kind: ChunkKind
    text: str
    line_start: int
    info: str = ""


@dataclass(frozen=True)
class Section:
    """一个章节：标题路径 + 该章节下的原文块。"""

    heading_path: Tuple[str, ...]
    anchor: str
    blocks: Tuple[Block, ...]
    line_start: int

    @property
    def body(self) -> str:
        return "\n\n".join(block.text for block in self.blocks)

    @property
    def is_empty(self) -> bool:
        return not self.blocks


def cjk_split(text: str, *, separator: str = " ") -> str:
    """把连续的中日韩文字逐字切开，其余内容保持不变。

    索引与查询共用这一个函数：只要两侧口径一致，"代码评审" 与 "代 码 评 审" 就能互相命中。
    """

    return CJK_RE.sub(lambda match: separator.join(match.group(0)), text)


def search_text(text: str) -> str:
    """FTS 检索列的内容：原文 + 中日韩逐字切分。展示用的原文另存一列，永不改写。"""

    return cjk_split(text)


def _slug(value: str) -> str:
    lowered = value.strip().lower()
    slug = SLUG_RE.sub("-", lowered).strip("-")
    return slug or "section"


def heading_anchor(heading_path: Sequence[str], occurrences: Mapping[str, int]) -> str:
    """把标题路径转成稳定锚点；同一路径第 n 次出现时追加 #n。

    没有标题的"前言"也用同一套计数：否则一篇文档里恰好出现标题 "Preamble" 时，
    它会与前言抢同一个锚点，两个 chunk 的 ID 相同、后写入的会把先写入的覆盖掉。
    """

    parts = [_slug(item) for item in heading_path] if heading_path else [ANCHOR_PREAMBLE]
    key = "/".join(parts)
    count = occurrences.get(key, 0) + 1
    if count > 1:
        parts[-1] = parts[-1] + "#" + str(count)
    return "/".join(parts)


def front_matter_bounds(text: str) -> Tuple[int, int, str, Optional[str]]:
    """定位 front matter：返回 (start, end, kind, warning)；end 之前的字符属于 front matter。"""

    stripped = text.lstrip("\ufeff")
    offset = len(text) - len(stripped)
    if stripped.startswith("---"):
        end = _find_closing_line(stripped, start=3, tokens=("---", "..."))
        if end is None:
            return offset, offset, "yaml-unterminated", "YAML front matter 未闭合，正文原样保留"
        return offset, end, "yaml", None
    if stripped.startswith("<!--"):
        closing = stripped.find("-->")
        if closing == -1:
            return (
                offset,
                offset,
                "html-comment-unterminated",
                "HTML 注释 front matter 未闭合，正文原样保留",
            )
        return offset, closing + 3, "html-comment", None
    return 0, 0, "", None


def _find_closing_line(text: str, *, start: int, tokens: Sequence[str]) -> Optional[int]:
    position = start
    while position < len(text):
        line_end = text.find(chr(10), position)
        if line_end == -1:
            line_end = len(text)
        line = text[position:line_end].strip()
        if line in tokens:
            return line_end
        position = line_end + 1
    return None


def split_front_matter(text: str) -> Tuple[FrontMatter, str]:
    """切出 front matter 与正文；结果只取决于文本本身（同一输入永远同一结果）。"""

    start, end, kind, warning = front_matter_bounds(text)
    if end <= start:
        return FrontMatter(kind=kind, raw="", metadata={}, warning=warning), text

    raw = text[start:end]
    body = text[end:].lstrip(chr(10))
    metadata: dict[str, str] = {}
    if kind == "yaml":
        inner = raw
        if inner.startswith("---"):
            inner = inner[3:]
        if inner.endswith("---") or inner.endswith("..."):
            inner = inner[:-3]
        try:
            parsed = yaml.safe_load(inner)
        except yaml.YAMLError as error:
            message = "front matter YAML 解析失败：" + str(error)
            return FrontMatter(kind=kind, raw=raw, metadata={}, warning=message), body
        if parsed is None:
            parsed = {}
        if not isinstance(parsed, Mapping):
            message = "front matter 不是映射，得到 " + type(parsed).__name__
            return FrontMatter(kind=kind, raw=raw, metadata={}, warning=message), body
        metadata = {str(key): _scalar(value) for key, value in parsed.items()}
    elif kind == "html-comment":
        inner = raw[4:]
        if inner.endswith("-->"):
            inner = inner[:-3]
        for line in inner.split(chr(10)):
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            if key:
                metadata[key] = value.strip()

    return FrontMatter(kind=kind, raw=raw, metadata=metadata, warning=warning), body


def _scalar(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def iter_blocks(body: str, *, line_start: int = 1) -> Tuple[Block, ...]:
    """把一段 Markdown 正文切成块：连续正文 vs 完整代码块（含围栏行）。"""

    lines = body.split(chr(10))
    blocks: list[Block] = []
    buffer: list[str] = []
    buffer_start = line_start
    fence: Optional[str] = None
    fence_info = ""
    fence_lines: list[str] = []
    fence_start = line_start

    def flush_prose() -> None:
        nonlocal buffer, buffer_start
        text = chr(10).join(buffer).strip(chr(10))
        if text.strip():
            blocks.append(Block(kind=ChunkKind.PROSE, text=text, line_start=buffer_start))
        buffer = []

    for index, line in enumerate(lines):
        number = line_start + index
        if fence is not None:
            fence_lines.append(line)
            if _closes_fence(line, fence):
                blocks.append(
                    Block(
                        kind=ChunkKind.CODE,
                        text=chr(10).join(fence_lines),
                        line_start=fence_start,
                        info=fence_info,
                    )
                )
                fence = None
                fence_lines = []
                fence_info = ""
            continue

        match = FENCE_RE.match(line)
        if match:
            flush_prose()
            fence = match.group(1)[0] * 3
            fence_info = match.group(2)
            fence_start = number
            fence_lines = [line]
            continue

        if not line.strip():
            flush_prose()
            buffer_start = number + 1
            continue
        if not buffer:
            buffer_start = number
        buffer.append(line)

    if fence is not None:
        # 破损 Markdown：围栏没闭合时把剩余内容整体当作代码块，不猜、不丢。
        blocks.append(
            Block(
                kind=ChunkKind.CODE,
                text=chr(10).join(fence_lines),
                line_start=fence_start,
                info=fence_info + " (unterminated)",
            )
        )
    else:
        flush_prose()
    return tuple(blocks)


def _closes_fence(line: str, fence: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    marker = stripped[0]
    if marker not in (chr(96), "~"):
        return False
    return len(stripped) >= 3 and set(stripped) == {marker}


def find_sections(body: str, *, line_start: int = 1) -> Tuple[Section, ...]:
    """按标题切章节；标题只在代码块之外生效，重复标题用出现序号区分。"""

    lines = body.split(chr(10))
    sections: list[Section] = []
    occurrences: dict[str, int] = {}
    stack: list[Tuple[int, str]] = []
    current_path: Tuple[str, ...] = ()
    current_start = line_start
    buffer: list[str] = []
    fence: Optional[str] = None
    newline = chr(10)

    def flush() -> None:
        nonlocal buffer
        text = newline.join(buffer)
        buffer = []
        blocks = iter_blocks(text, line_start=current_start)
        if not blocks and not current_path:
            # 正文之前没有任何内容：不需要为空白占一个"章节"。
            return
        # 锚点在"章节结束"时分配：空章节同样占用序号，保证同一路径的编号与文档顺序一致。
        anchor = heading_anchor(current_path, occurrences)
        key = "/".join(_slug(item) for item in current_path) if current_path else ANCHOR_PREAMBLE
        occurrences[key] = occurrences.get(key, 0) + 1
        sections.append(
            Section(
                heading_path=current_path,
                anchor=anchor,
                blocks=blocks,
                line_start=current_start,
            )
        )

    for index, line in enumerate(lines):
        number = line_start + index
        if fence is not None:
            buffer.append(line)
            if _closes_fence(line, fence):
                fence = None
            continue
        fence_match = FENCE_RE.match(line)
        if fence_match:
            fence = fence_match.group(1)[0] * 3
            buffer.append(line)
            continue
        heading = HEADING_RE.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            current_path = tuple(item[1] for item in stack)
            current_start = number
            continue
        buffer.append(line)

    flush()
    return tuple(sections)


def chunk_document(
    text: str,
    *,
    document_id: str,
    max_chars: int,
    hard_max_chars: int,
    chunker_version: str = CHUNKER_VERSION,
) -> Tuple[FrontMatter, Tuple[ChunkDraft, ...]]:
    """把一份文档切成 chunk：先分章节，再按预算打包，最后给每个 chunk 一个稳定 ID。"""

    if max_chars <= 0 or hard_max_chars <= 0:
        raise ChunkerError("max_chars 与 hard_max_chars 必须是正数")
    if max_chars > hard_max_chars:
        raise ChunkerError("max_chars 不能大于 hard_max_chars")
    if not document_id:
        raise ChunkerError("document_id 不能为空")

    front, body = split_front_matter(text)
    drafts: list[ChunkDraft] = []
    ordinal = 0
    for section in find_sections(body):
        if section.is_empty:
            continue
        for part_index, piece in enumerate(
            _pack(section.blocks, max_chars=max_chars, hard_max_chars=hard_max_chars), start=1
        ):
            payload, kind, truncated, original_chars, oversized = piece
            drafts.append(
                ChunkDraft(
                    chunk_id=chunk_id_for(document_id, section.anchor, part_index),
                    document_id=document_id,
                    ordinal=ordinal,
                    heading_path=section.heading_path,
                    heading_anchor=section.anchor,
                    text=payload,
                    text_hash=sha256_text(payload),
                    char_count=len(payload),
                    kind=kind,
                    part_index=part_index,
                    truncated=truncated,
                    original_chars=original_chars,
                    oversized=oversized,
                )
            )
            ordinal += 1
    return front, tuple(drafts)


_Piece = Tuple[str, ChunkKind, bool, Optional[int], bool]


def _pack(
    blocks: Sequence[Block], *, max_chars: int, hard_max_chars: int
) -> Tuple[_Piece, ...]:
    """把章节内的块打包成若干 chunk 载荷。"""

    pieces: list[_Piece] = []
    current: list[Block] = []
    current_len = 0
    newline = chr(10)

    def emit(selected: Sequence[Block], kind: ChunkKind, *, truncated: bool,
             original: Optional[int], oversized: bool) -> None:
        payload = (newline + newline).join(block.text for block in selected)
        pieces.append((payload, kind, truncated, original, oversized or len(payload) > max_chars))

    def flush() -> None:
        nonlocal current, current_len
        if not current:
            return
        kinds = {block.kind for block in current}
        kind = ChunkKind.MIXED if len(kinds) > 1 else next(iter(kinds))
        emit(current, kind, truncated=False, original=None, oversized=False)
        current = []
        current_len = 0

    for block in blocks:
        # 1) 超硬上限：代码块是原子单元，只能截断并记录丢弃量；段落按行边界拆开，不丢字符。
        if len(block.text) > hard_max_chars and block.kind is ChunkKind.CODE:
            flush()
            emit(
                (Block(kind=block.kind, text=block.text[:hard_max_chars], line_start=block.line_start,
                        info=block.info),),
                block.kind,
                truncated=True,
                original=len(block.text),
                oversized=True,
            )
            continue
        if len(block.text) > hard_max_chars:
            flush()
            for text, truncated, original in _split_prose(
                block.text, max_chars=max_chars, hard_max_chars=hard_max_chars
            ):
                emit(
                    (Block(kind=block.kind, text=text, line_start=block.line_start, info=block.info),),
                    block.kind,
                    truncated=truncated,
                    original=original,
                    oversized=len(text) > max_chars,
                )
            continue

        # 2) 塞得下就继续装。
        joined = current_len + len(block.text) + (2 if current_len else 0)
        if joined <= max_chars:
            current.append(block)
            current_len = joined
            continue

        # 3) 塞不下：先结掉当前 chunk，再决定新块怎么放。
        flush()
        if len(block.text) <= max_chars:
            current.append(block)
            current_len = len(block.text)
            continue

        # 4) 单块超预算：代码块整体成一块（记 oversized）；段落按行边界拆开，不丢文本。
        if block.kind is ChunkKind.CODE:
            emit((block,), block.kind, truncated=False, original=None, oversized=True)
            continue
        for text in _prose_pieces(block.text, max_chars=max_chars):
            emit(
                (Block(kind=block.kind, text=text, line_start=block.line_start, info=block.info),),
                block.kind,
                truncated=False,
                original=None,
                oversized=False,
            )
    flush()
    return tuple(pieces)


def _split_prose(
    text: str, *, max_chars: int, hard_max_chars: Optional[int] = None
) -> Tuple[Tuple[str, bool, Optional[int]], ...]:
    """段落按行边界拆成不超过预算的片段：不切断行，也不丢内容。

    唯一会丢字符的情况是**单行**本身就超过硬上限（没有任何断点可用）：
    这时截断并返回 (文本, True, 原始长度)，让调用方把丢弃量记清楚。
    """

    limit = hard_max_chars if hard_max_chars is not None else max_chars
    pieces: list[Tuple[str, bool, Optional[int]]] = []
    buffer: list[str] = []
    length = 0

    def flush() -> None:
        nonlocal buffer, length
        if buffer:
            pieces.append((chr(10).join(buffer), False, None))
        buffer = []
        length = 0

    for line in text.split(chr(10)):
        if len(line) > limit:
            # 单行超硬上限：先结掉已攒的内容，再把这一行截断（丢多少写进 original）。
            flush()
            pieces.append((line[:limit], True, len(line)))
            continue
        addition = len(line) + (1 if buffer else 0)
        if buffer and length + addition > max_chars:
            flush()
        buffer.append(line)
        length += len(line) + (1 if len(buffer) > 1 else 0)
    flush()
    return tuple(pieces)


def _prose_pieces(text: str, *, max_chars: int) -> Tuple[str, ...]:
    """只要文本的便捷包装（不带截断信息）。"""

    return tuple(piece for piece, _, _ in _split_prose(text, max_chars=max_chars))


def compact_text(value: str) -> str:
    """去掉全部空白字符，用于比较"有没有丢字、有没有多出字"。"""

    return re.sub(r"\s+", "", value)


def blocks_are_preserved(body: str, chunk_texts: Sequence[str]) -> bool:
    """校验不变式：正文的字符全部落进 chunk，且 chunk 没有多出字符。

    允许打包时在行边界插入换行与空行（预算打包的必然结果），但不允许丢字、改字或加解释。
    截断（truncated=True）是本不变式的**显式例外**：那部分丢失量由 original_chars 单独记录，
    并计入索引 run 报告，不允许静默发生。
    """

    return compact_text(body) == compact_text("".join(chunk_texts))
