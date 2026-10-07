"""mirror_docs.write_structure：一页都没保存时也要写出读数，不许让 max() 崩掉。

为什么需要：`width = max(len(r[0]) for r in rows) + 2` 在 rows 为空时抛 ValueError——
发现为空（sitemap 没给范围）或全部抓取失败时，整个 run 在写 STRUCTURE.md 这一步中止，
读者既看不到"没有页面"这个事实，也拿不到已抓到的 manifest。
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _stub(name: str, **attributes: Any) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _load_mirror_docs(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setitem(
        sys.modules,
        "crawl4ai",
        _stub("crawl4ai", AsyncWebCrawler=object, CacheMode=object, CrawlerRunConfig=object),
    )
    monkeypatch.setitem(
        sys.modules,
        "crawl4ai.async_crawler_strategy",
        _stub("crawl4ai.async_crawler_strategy", AsyncHTTPCrawlerStrategy=object),
    )
    monkeypatch.setitem(
        sys.modules,
        "crawl4ai.markdown_generation_strategy",
        _stub("crawl4ai.markdown_generation_strategy", CustomHTML2Text=object),
    )
    monkeypatch.setitem(sys.modules, "bs4", _stub("bs4", BeautifulSoup=object))
    spec = importlib.util.spec_from_file_location(
        "mirror_docs_structure_under_test", REPO_ROOT / "tools" / "mirror_docs.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_structure_is_written_when_no_page_was_saved(tmp_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """空 manifest：STRUCTURE.md 仍然写出"没有任何页面被保存"这个读数。"""

    module = _load_mirror_docs(monkeypatch)
    out = tmp_root / "mirror"
    out.mkdir(parents=True, exist_ok=True)
    spec = {
        "structure_mode": "outline",
        "structure_findings": ["发现为空：sitemap 没有给出范围内的页面"],
        "license": "CC BY-SA 4.0",
    }

    module.write_structure(out, spec, [], {})

    text = (out / "STRUCTURE.md").read_text(encoding="utf-8")
    assert "没有任何页面被保存" in text
    assert "发现为空" in text