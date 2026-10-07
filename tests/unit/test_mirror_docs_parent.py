"""mirror_docs.parent_of：父路径不能等于自身（自引用会把层级链变成环）。

来源：`docs/mirrors/google-eng-practices/manifest.json` 的 `review/index.md` 记录曾把
`parent` 写成它自己——`review/index.md` 既是共享层的父，自己也属于共享层，"照直写"就成环：
沿 parent 走面包屑 / 导航树的消费方要么死循环、要么放不下这个节点。该镜像自己的 STRUCTURE.md
写的是 `index.md` → `review/` → `review/index.md`，所以自引用时回落到站点根，链以 `""` 结束。

这一组用例同时守**生成器**与**已发布数据**：生成器改了却没重生成（或反过来有人手改了数据）
都会在这里红。
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIRRORS_DIR = REPO_ROOT / "docs" / "mirrors"


def _stub(name: str, **attributes: Any) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _load_mirror_docs(monkeypatch: pytest.MonkeyPatch) -> Any:
    """按路径加载 tools/mirror_docs.py：crawl4ai / bs4 是可选依赖，导入期只需要它们有名字。"""

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
        "mirror_docs_parent_under_test", REPO_ROOT / "tools" / "mirror_docs.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _shipped_pages(dataset: str) -> list[dict[str, Any]]:
    document = json.loads((MIRRORS_DIR / dataset / "manifest.json").read_text(encoding="utf-8"))
    return [page for page in document["pages"] if page.get("saved")]


def test_parent_chain_of_the_section_index_ends_at_the_site_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`review/index.md` 的父是站点根，不是它自己；根自己没有父。"""

    module = _load_mirror_docs(monkeypatch)
    site = module.SITES["eng-practices"]

    assert module.parent_of("index.md", site, "shared") == ""
    assert module.parent_of("review/index.md", site, "shared") == "index.md"
    # 反向对照：共享层其它页与两组文档的父节点语义不变（修的是自引用，不是重新定义层级）。
    assert module.parent_of("review/emergencies.md", site, "shared") == "review/index.md"
    assert module.parent_of("review/reviewer/index.md", site, "reviewer") == "review/index.md"
    assert (
        module.parent_of("review/reviewer/standard.md", site, "reviewer")
        == "review/reviewer/index.md"
    )
    assert module.parent_of("review/developer/small-cls.md", site, "author") == "review/developer/index.md"


def test_the_shipped_manifest_equals_the_generator_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """已发布的 manifest 必须逐条等于生成器现在的输出：防止"改了生成器忘了重生成"。"""

    module = _load_mirror_docs(monkeypatch)
    site = module.SITES["eng-practices"]
    pages = _shipped_pages("google-eng-practices")
    assert len(pages) >= 10, f"没读到 google-eng-practices 的页面：这条检查会变成空转（{len(pages)}）"

    recomputed = {
        page["local_path"]: module.parent_of(page["local_path"], site, page["guide"])
        for page in pages
    }
    recorded = {page["local_path"]: page["parent"] for page in pages}
    assert recomputed == recorded


def test_no_mirror_page_is_its_own_parent() -> None:
    """跨镜像的不变量：任何一页的 parent 都不许指回自己（数据层的成环检查）。"""

    manifests = sorted(MIRRORS_DIR.glob("*/manifest.json"))
    assert len(manifests) == 6, f"镜像套数变了，这条检查覆盖的集合要重新确认：{len(manifests)}"

    offenders = {
        f"{path.parent.name}:{page['local_path']}"
        for path in manifests
        for page in json.loads(path.read_text(encoding="utf-8"))["pages"]
        if page.get("parent") and page.get("local_path") == page.get("parent")
    }
    assert offenders == set(), f"这些页面的 parent 指向自己（层级链成环）：{sorted(offenders)}"
