"""mirror_docs.norm：`<dir>/index.html` 与 `<dir>/` 归一成同一个 URL 键。

为什么需要：`url_to_relpath` 把两者都映射到 `<dir>/index.md`，而 `norm` 故意保留 `.html`
（只有无扩展名的目录式路径补尾斜杠）——于是 BFS 同时发现两种写法时，两页写进同一个文件
（后写覆盖先写）、manifest 出现两条同 local_path 的 saved 条目，而 README 还写着
"已知等价 URL … 已按尾斜杠形式归一，不重复保存"。
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

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
        "mirror_docs_norm_under_test", REPO_ROOT / "tools" / "mirror_docs.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_index_html_and_directory_form_are_one_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """两种写法归一成同一个 URL，且都落到同一个本地文件。"""

    module = _load_mirror_docs(monkeypatch)

    directory_form = module.norm("https://example.com/docs/guide/", SPEC)
    html_form = module.norm("https://example.com/docs/guide/index.html", SPEC)

    assert html_form == directory_form == "https://example.com/docs/guide/"
    assert module.url_to_relpath(html_form, SPEC) == "guide/index.md"
    assert module.url_to_relpath(directory_form, SPEC) == "guide/index.md"


def test_site_root_index_html_also_collapses(monkeypatch: pytest.MonkeyPatch) -> None:
    """站点根的 index.html 同样归一（否则根页会与 "/" 抢同一个 index.md）。"""

    module = _load_mirror_docs(monkeypatch)
    spec = dict(SPEC, prefix="/", exact=["/"])

    assert module.norm("https://example.com/index.html", spec) == "https://example.com/"


def test_other_html_files_keep_their_own_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """只有 index.html 归一：普通 .html 页仍然是各自的键（不能被这次修复顺手改掉）。"""

    module = _load_mirror_docs(monkeypatch)

    assert module.norm("https://example.com/docs/a.html", SPEC) == "https://example.com/docs/a.html"
    assert module.url_to_relpath("https://example.com/docs/a.html", SPEC) == "a.md"