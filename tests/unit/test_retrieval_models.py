"""retrieval.models 的取值校验：非法取值一律拒绝（失败关闭）。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from retrieval.models import CorpusManifest, CorpusQuarantine


def test_public_models_are_exported() -> None:
    """被别的模块直接 import 的公开模型必须在 __all__ 里（复核发现：L4 models.py:41）。"""

    import retrieval.models as models

    assert "CorpusManifest" in models.__all__
    assert "DocumentRecord" in models.__all__
    # __all__ 是有序清单：两个名字都按字母序落位。
    assert models.__all__ == sorted(models.__all__)


def test_restricted_datasets_must_agree_with_visibility() -> None:
    """restricted_datasets 必须与 visibility 逐项一致（复核发现：security / fail-open）。

    这份名单在生产代码里没有第二个消费者：检索期真正生效的是 documents.visibility 与
    AccessScope.allow_restricted。登记成受限而 visibility 仍是 public，等于"按清单作者
    的意思该受限、实际任何人都能检索"。
    """

    dataset = {
        "name": "guides",
        "title": "Guides",
        "mirror": "mirror/guides",
        "license": "CC0-1.0",
        "tier": "guidance",
        "visibility": "public",
        "entries": ["index.md"],
    }
    public = {"version": 1, "datasets": [dataset], "restricted_datasets": []}
    assert CorpusManifest.model_validate(public).restricted_datasets == ()

    # fail-open 方向：登记为受限，但 visibility 允许所有人检索。
    with pytest.raises(ValidationError):
        CorpusManifest.model_validate({**public, "restricted_datasets": ["guides"]})

    restricted = {
        **public,
        "datasets": [{**dataset, "visibility": "restricted"}],
        "restricted_datasets": ["guides"],
    }
    assert CorpusManifest.model_validate(restricted).restricted_datasets == ("guides",)

    # 反向：visibility=restricted 却漏登记，这份名单就在骗读者。
    with pytest.raises(ValidationError):
        CorpusManifest.model_validate({**restricted, "restricted_datasets": []})

    # 真实语料与夹具都满足这条不变式（全 public + 空名单 / restricted + 登记）。
    from pathlib import Path

    import yaml

    from conftest import REPO_ROOT

    document = yaml.safe_load((REPO_ROOT / "knowledge" / "corpus.yaml").read_text(encoding="utf-8"))
    manifest = CorpusManifest.model_validate(document)
    assert manifest.restricted_datasets == ()


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
