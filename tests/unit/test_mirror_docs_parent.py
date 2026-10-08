"""mirror_docs.parent_of：父节点必须是镜像里真实存在的记录，或空串。

同一函数在 docs/mirrors/*/manifest.json 里落过两个缺陷：

1. **自引用**：`review/index.md` 既是共享层的父、自己也属于共享层，旧实现照直写就返回它自己，
   沿 parent 走面包屑 / 导航树的消费方要么死循环、要么放不下这个节点；
2. **悬空**：旧实现把"共享层"的父路径写死成 `review/index.md`——那是 google-eng-practices 的
   结构。gitlab-code-review（20 篇）与 python-pep-code-style（11 篇）根本没有这个文件，
   于是两套镜像的 parent **全部**指向不存在的记录，而这条引用既不报错、也没有任何读数为证。

新口径：父节点 = **同一镜像里最近的祖先索引页**，由本次清单（local_path 集合）推出；
多根镜像的每一根（专题入口）没有父页，记 `""`。返回值因此必然落在清单内或为空串。

这一组用例同时守**生成器**与**已发布数据**：改了生成器却没重生成、或反过来有人手改了数据，
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
# 这三套镜像的 manifest 由 tools/mirror_docs.py 生成，parent 由 parent_of 推出；
# dotnet / dora 的 parent 来自各自站点模块，owasp 走独立流水线（它们的 parent 由第 3 条用例守）。
MIRROR_DOCS_DATASETS = ("google-eng-practices", "gitlab-code-review", "python-pep-code-style")


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


def test_parent_is_the_nearest_ancestor_index_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """沿目录逐级向上取第一个存在的 index.md；站点根没有父，`review/index.md` 的父是它。"""

    module = _load_mirror_docs(monkeypatch)
    known = {
        "index.md",
        "review/index.md",
        "review/emergencies.md",
        "review/reviewer/index.md",
        "review/reviewer/standard.md",
    }

    assert module.parent_of("index.md", known) == ""
    assert module.parent_of("review/index.md", known) == "index.md"  # 旧实现返回它自己
    assert module.parent_of("review/emergencies.md", known) == "review/index.md"
    assert module.parent_of("review/reviewer/index.md", known) == "review/index.md"
    assert module.parent_of("review/reviewer/standard.md", known) == "review/reviewer/index.md"


def test_multi_root_mirror_rows_have_no_parent_and_no_dangling_guess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """多根镜像：专题入口没有父页（""），有祖先索引页的用真的，绝不猜一个不存在的路径。"""

    module = _load_mirror_docs(monkeypatch)
    known = {
        "development/code_review/index.md",
        "user/project/merge_requests/reviews/index.md",
        "user/project/merge_requests/reviews/suggestions/index.md",
    }

    assert module.parent_of("development/code_review/index.md", known) == ""
    assert module.parent_of("user/project/merge_requests/reviews/index.md", known) == ""
    assert (
        module.parent_of("user/project/merge_requests/reviews/suggestions/index.md", known)
        == "user/project/merge_requests/reviews/index.md"
    )
    # 中间层没有索引页：不许回落到站点根（镜像里没有 index.md），更不许编一个路径出来。
    assert module.parent_of("runner/development/reviewing-gitlab-runner/index.md", known) == ""


def test_every_shipped_parent_points_at_a_record_that_exists() -> None:
    """不变量：每条 parent 要么是空串，要么指向镜像目录里真实存在的文件。

    这是"下次重爬能自己发现"的那条检查：悬空引用（旧实现在 gitlab / python-pep 上各有
    20 / 11 条）会让这条用例红，而不是等到有人沿 parent 走导航树时才炸。
    owasp 的 parent 指向各分类的 README.md——它们不在 manifest 的 pages 里，但确实是镜像文件，
    因此判据用"文件存在"而不是"在 pages 里"。
    """

    manifests = sorted(MIRRORS_DIR.glob("*/manifest.json"))
    assert len(manifests) == 6, f"镜像套数变了，这条检查覆盖的集合要重新确认：{len(manifests)}"

    problems: list[str] = []
    checked = 0
    for path in manifests:
        document = json.loads(path.read_text(encoding="utf-8"))
        for page in document["pages"]:
            parent = page.get("parent")
            if not parent:
                continue
            checked += 1
            if (path.parent / parent).is_file():
                continue
            problems.append(f"{path.parent.name}:{page['local_path']} -> {parent}")

    assert checked > 100, f"没有读到几条 parent：这条检查会变成空转（{checked}）"
    assert problems == [], f"这些 parent 指向镜像里不存在的文件：{problems}"


@pytest.mark.parametrize("dataset", MIRROR_DOCS_DATASETS)
def test_generated_mirror_manifests_equal_the_generator_output(
    dataset: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """已发布的 manifest 必须逐条等于生成器现在的输出（防止改了生成器忘了重生成）。"""

    module = _load_mirror_docs(monkeypatch)
    pages = _shipped_pages(dataset)
    assert len(pages) >= 10, f"{dataset} 只读到 {len(pages)} 页：这条检查会变成空转"
    known = {page["local_path"] for page in pages}

    recomputed = {page["local_path"]: module.parent_of(page["local_path"], known) for page in pages}
    recorded = {page["local_path"]: page["parent"] for page in pages}
    assert recomputed == recorded


def test_no_mirror_page_is_its_own_parent() -> None:
    """自引用单独再钉一次：它是环，不只是"指向不存在的文件"。"""

    offenders = {
        f"{path.parent.name}:{page['local_path']}"
        for path in sorted(MIRRORS_DIR.glob("*/manifest.json"))
        for page in json.loads(path.read_text(encoding="utf-8"))["pages"]
        if page.get("parent") and page.get("local_path") == page.get("parent")
    }
    assert offenders == set(), f"这些页面的 parent 指向自己（层级链成环）：{sorted(offenders)}"
