"""mirror_docs：改写链接 / 互引 / 外链三处都只该看**围栏之外**的正文。

为什么需要：三处都跑在整份 Markdown 上，于是代码样例里指向镜像内页面的 URL 被改写成相对路径
（镜像里的代码与原文不一致）、被收进互引与外链台账（把代码当成引用关系）；而 headings_outline
与 verify_mirror 本来就跳过围栏——同一份工具里两套口径，且改写后的代码块链接 --verify 也看不见。
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NL = chr(10)
FENCE = chr(96) * 3

SPEC = {
    "host": "example.com",
    "prefix": "/docs/",
    "base": "https://example.com/docs/",
    "out": "docs/mirrors/example",
    "groups": [],
}


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
        "mirror_docs_fences_under_test", REPO_ROOT / "tools" / "mirror_docs.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_rewrite_links_leaves_fenced_code_untouched(tmp_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """围栏里的 URL 保持绝对；围栏外的改写为相对路径。"""

    module = _load_mirror_docs(monkeypatch)
    out = tmp_root / "mirror"
    (out / "a").mkdir(parents=True)
    urlmap = {
        "https://example.com/docs/a/": "a/index.md",
        "https://example.com/docs/b/": "b/index.md",
    }
    md = NL.join([
        "# 标题",
        "",
        "正文：https://example.com/docs/b/",
        "",
        FENCE + "text",
        "代码样例：https://example.com/docs/b/ 不该被改写",
        FENCE,
        "",
        "结尾：https://example.com/docs/b/",
        "",
    ])

    result = module.rewrite_links(md, "https://example.com/docs/a/", urlmap, out)

    assert "正文：../b/index.md" in result
    assert "结尾：../b/index.md" in result
    assert "代码样例：https://example.com/docs/b/ 不该被改写" in result


def test_compute_edges_ignores_fenced_code(tmp_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """互引只算围栏外的链接：围栏内的另一条链接不许进台账。"""

    module = _load_mirror_docs(monkeypatch)
    out = tmp_root / "mirror"
    (out / "a").mkdir(parents=True)
    (out / "b").mkdir(parents=True)
    (out / "c").mkdir(parents=True)
    (out / "b" / "index.md").write_text("# B" + NL, encoding="utf-8", newline=NL)
    (out / "c" / "index.md").write_text("# C" + NL, encoding="utf-8", newline=NL)
    (out / "a" / "index.md").write_text(
        NL.join([
            "# A",
            "",
            "[真实链接](../b/index.md)",
            "",
            FENCE,
            "[代码里的链接](../c/index.md)",
            FENCE,
            "",
        ]),
        encoding="utf-8",
        newline=NL,
    )

    edges = module.compute_edges(out)

    assert edges["a/index.md"] == ["b/index.md"]


def test_collect_outbound_ignores_fenced_code(tmp_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """外链登记同样只算围栏外：代码样例里的站内 URL 不是"正文外链"。"""

    module = _load_mirror_docs(monkeypatch)
    out = tmp_root / "mirror"
    (out / "a").mkdir(parents=True)
    (out / "a" / "index.md").write_text(
        NL.join([
            "# A",
            "",
            "正文外链：https://example.com/other/x",
            "",
            FENCE,
            "代码里的：https://example.com/secret/y",
            FENCE,
            "",
        ]),
        encoding="utf-8",
        newline=NL,
    )

    counts = module.collect_outbound(out, SPEC)

    assert counts == {"/other/x": 1}