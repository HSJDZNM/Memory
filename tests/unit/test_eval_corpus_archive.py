"""eval_corpus._archive_members：畸形归档要翻成 CorpusError，不许裸抛。

为什么需要：BadZipFile / tarfile.ReadError 都是普通 Exception 子类，逃出去就是 --fetch 上的
一段栈回溯——而"200 响应但内容是畸形/截断/恰好以 PK 开头的非 zip 体"正是上游/代理会给出的形状。
"""

from __future__ import annotations

import importlib.util
import io
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS = REPO_ROOT / "tools"
_MODULE = None


def _load_eval_corpus():
    global _MODULE
    if _MODULE is not None:
        return _MODULE
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location(
        "eval_corpus_archive_under_test", TOOLS / "eval_corpus.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _MODULE = module
    return module


def test_non_zip_body_starting_with_pk_is_a_corpus_error() -> None:
    """以 PK 开头但不是 zip：BadZipFile → CorpusError。"""

    module = _load_eval_corpus()
    spec = next(iter(module.SOURCES.values()))

    with pytest.raises(module.CorpusError) as error:
        module._archive_members(spec, b"PK\x03\x04 not a zip body at all")

    assert "不是合法 zip" in str(error.value)


def test_non_archive_body_is_a_corpus_error() -> None:
    """既不是 zip 也不是 tar：tarfile.ReadError → CorpusError。"""

    module = _load_eval_corpus()
    spec = next(iter(module.SOURCES.values()))

    with pytest.raises(module.CorpusError) as error:
        module._archive_members(spec, b"<html>200 OK but not an archive</html>")

    assert "不是合法 tar" in str(error.value)


def test_valid_archive_still_parses() -> None:
    """阳性对照：合法 zip 照旧读出来（这次收口不许把正常路径弄坏）。"""

    module = _load_eval_corpus()
    spec = next(iter(module.SOURCES.values()))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(spec.archive_root + "/a.py", "value = 1" + chr(10))

    members = module._archive_members(spec, buffer.getvalue())

    assert members == {"a.py": b"value = 1" + bytes([10])}

def test_truncated_transfer_becomes_a_corpus_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """IncompleteRead（传输被截断）→ CorpusError，不是裸 HTTPException。"""

    module = _load_eval_corpus()
    spec = next(iter(module.SOURCES.values()))

    def boom(*args: object, **kwargs: object) -> object:
        raise module.http.client.IncompleteRead(b"partial", 100)

    monkeypatch.setattr(module.urllib.request, "urlopen", boom)

    with pytest.raises(module.CorpusError) as error:
        module._download(spec)

    assert "IncompleteRead" in str(error.value)


def test_plain_network_error_still_becomes_a_corpus_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """阳性对照：URLError 照旧翻成 CorpusError。"""

    module = _load_eval_corpus()
    spec = next(iter(module.SOURCES.values()))

    def boom(*args: object, **kwargs: object) -> object:
        raise module.urllib.error.URLError("no route to host")

    monkeypatch.setattr(module.urllib.request, "urlopen", boom)

    with pytest.raises(module.CorpusError):
        module._download(spec)
