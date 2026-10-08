"""load_corpus 的错误通道：镜像 manifest 的坏字段必须变成 CorpusError，而不是裸 ValidationError。

对应 L4 结论 src/retrieval/corpus.py:199（ResolvedEntry 构造是唯一没包 CorpusError 的校验点）：
调用方（cli.py 的 config error 分支）只接 CorpusError，未捕获的 ValidationError 会变成 traceback。
"""

from __future__ import annotations

import json

import pytest
from conftest import load_fixture_corpus, write_fixture_corpus

from retrieval.corpus import CorpusError, load_corpus


def _corrupt_first_manifest_hash(root) -> None:
    manifests = sorted(root.rglob("manifest.json"))
    assert manifests, "夹具没有生成 manifest.json"
    document = json.loads(manifests[0].read_text(encoding="utf-8"))
    document["pages"][0]["sha256"] = "sha256:abc"  # 形态不合法：models 会拒
    manifests[0].write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )


def test_a_malformed_manifest_hash_is_a_corpus_error(tmp_root):
    """坏 sha256 → CorpusError（config error 退出），不是逃逸的 ValidationError。"""

    path = write_fixture_corpus(tmp_root)
    _corrupt_first_manifest_hash(tmp_root)

    with pytest.raises(CorpusError) as error:
        load_corpus(path, repo_root=tmp_root)

    assert "镜像 manifest 记录校验失败" in str(error.value)


def test_the_fixture_corpus_still_loads(tmp_root):
    """反真空：同一份夹具在哈希没被改坏时照常加载。"""

    loaded = load_fixture_corpus(tmp_root)

    assert loaded.entries
