"""retrieval.models 的取值校验：非法取值一律拒绝（失败关闭）。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from retrieval.models import CorpusQuarantine


def test_quarantine_text_hash_must_be_hex_and_is_lowercased() -> None:
    """隔离登记的 text_hash 必须是 64 位十六进制，且归一成小写（复核发现）。

    旧实现只查前缀与总长度："sha256:" + 64 个非十六进制字符也能登记，而它永远不可能
    等于任何真实 chunk 的 sha256_text（小写十六进制）——这条隔离于是静默失效。
    """

    good = "sha256:" + "a" * 64
    assert CorpusQuarantine(chunk_id="c", text_hash=good, reason="r").text_hash == good

    upper = "sha256:" + "A" * 64
    assert CorpusQuarantine(chunk_id="c", text_hash=upper, reason="r").text_hash == good

    # 与 ResolvedEntry._check_manifest_hash 同一口径：前缀可省，归一时补上。
    bare = "b" * 64
    assert CorpusQuarantine(chunk_id="c", text_hash=bare, reason="r").text_hash == "sha256:" + bare

    for bad in (
        "sha256:" + "g" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "a" * 65,
        "sha256:abc",
        "",
    ):
        with pytest.raises(ValidationError):
            CorpusQuarantine(chunk_id="c", text_hash=bad, reason="r")
