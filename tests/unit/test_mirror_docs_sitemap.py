"""mirror_docs 的 sitemap 索引解析：写法带空白的 <loc> 不许被静默丢掉。

为什么需要：`subs` 只要命中了**别的**条目，平铺回退就不会启用；正则里的空白类一旦写成字面量
`s`，`<loc> https://…</loc>` 这类条目就一条都匹配不上——整份子 sitemap 从镜像里消失，
而 --verify 只会看到「页面数变少」，看不出是谁丢的。

mirror_docs 依赖 crawl4ai / aiohttp / bs4（可选依赖，本机没装），因此这里只替换导入期需要的
那几个名字，被断言的是纯解析函数。
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

WHITESPACED_INDEX = "".join(
    [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "<sitemap>",
        "  <loc> https://docs.example.com/sitemap-en.xml</loc>",
        "</sitemap>",
        "<sitemap><loc>https://docs.example.com/sitemap-ja.xml</loc></sitemap>",
        "</sitemapindex>",
    ]
)

FLAT_URLSET = "".join(
    [
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "<url><loc>https://docs.example.com/a/</loc></url>",
        "<url><loc>  https://docs.example.com/b/  </loc></url>",
        "</urlset>",
    ]
)


def _stub(name: str, **attributes: Any) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _load_mirror_docs(monkeypatch: pytest.MonkeyPatch) -> Any:
    """按标准配方按路径加载工具模块；缺的第三方包用最小替身补齐。"""

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
        "mirror_docs_under_test", REPO_ROOT / "tools" / "mirror_docs.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_whitespace_prefixed_loc_is_not_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """`<loc> https://…</loc>`（标签后有空白）必须与紧凑写法一样被取到。"""

    module = _load_mirror_docs(monkeypatch)
    assert module.sitemap_index_entries(WHITESPACED_INDEX) == [
        "https://docs.example.com/sitemap-en.xml",
        "https://docs.example.com/sitemap-ja.xml",
    ]


def test_flat_urlset_still_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """平铺 urlset（没有 <sitemap> 包装）仍然按 <loc> 读，回退没有被这次修复弄坏。"""

    module = _load_mirror_docs(monkeypatch)
    assert module.sitemap_index_entries(FLAT_URLSET) == [
        "https://docs.example.com/a/",
        "https://docs.example.com/b/",
    ]
