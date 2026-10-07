"""OWASP 01_analyze：抓取失败 / 正文取不到 / links 为 None 都不许被读成"没有内容"。

为什么需要：失败的 crawl 给空正文，`str(r.markdown)` 还会把它变成字符串 "None"；旧流程照样写出
一份 indexes 全空、UNMAPPED 一长串的 taxonomy.json（退出码 0），而 `r.links` 为 None 时直接
AttributeError 中断整个运行。这里用假 crawler 驱动**真的 main()**：断言失败会显式报错、且不写
出那份误导性的 taxonomy.json。

01_analyze.py 依赖 crawl4ai（可选依赖，本机没装），因此只替换导入期需要的名字。
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = "https://cheatsheetseries.owasp.org/"
INDEXES = [
    "index.html",
    "IndexASVS.html",
    "IndexProactiveControls.html",
    "IndexTopTen.html",
    "IndexMASVS.html",
    "Glossary.html",
]
SEED = BASE + "cheatsheets/Secure_Code_Review_Cheat_Sheet.html"
SHEET = BASE + "cheatsheets/Authentication_Cheat_Sheet.html"


def _result(*, body: str = "# 标题" + chr(10), links: Any = None, ok: bool = True, error: str = "") -> Any:
    return SimpleNamespace(
        success=ok,
        error_message=error,
        markdown=SimpleNamespace(raw_markdown=body) if body is not None else None,
        links=links,
    )


class _Crawler:
    """假 crawler：按 URL 返回预先写好的 crawl 结果，并记下被请求的 URL。"""

    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    async def arun(self, url: str, config: Any = None) -> Any:
        self.calls.append(url)
        return self.responses[url]

    async def __aenter__(self) -> "_Crawler":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


def _stub(name: str, **attributes: Any) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _load(monkeypatch: pytest.MonkeyPatch, crawler: _Crawler, tmp_root: Path) -> Any:
    class AsyncWebCrawler:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _Crawler:
            return crawler

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    monkeypatch.setitem(
        sys.modules,
        "crawl4ai",
        _stub(
            "crawl4ai",
            AsyncWebCrawler=AsyncWebCrawler,
            BrowserConfig=lambda **kwargs: None,
            CrawlerRunConfig=lambda **kwargs: None,
            CacheMode=SimpleNamespace(BYPASS="bypass"),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "crawl4ai.async_crawler_strategy",
        _stub("crawl4ai.async_crawler_strategy", AsyncHTTPCrawlerStrategy=lambda **kwargs: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "crawl4ai.async_configs",
        _stub("crawl4ai.async_configs", HTTPCrawlerConfig=lambda **kwargs: None),
    )
    # 产物落在 CWD 下的 _work/：换到临时目录，别写到仓库里
    monkeypatch.chdir(tmp_root)
    spec = importlib.util.spec_from_file_location(
        "owasp_analyze_under_test", REPO_ROOT / "tools" / "owasp_cheatsheets" / "01_analyze.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _successful_responses(seed_links: Any, index_links: Any) -> dict[str, Any]:
    responses = {BASE + name: _result() for name in INDEXES}
    responses[BASE + "index.html"] = _result(links=index_links)
    responses[SEED] = _result(links=seed_links)
    return responses


def test_failed_crawl_raises_and_writes_no_taxonomy(
    monkeypatch: pytest.MonkeyPatch, tmp_root: Path
) -> None:
    """一页抓取失败：显式报错，且**不**写出 indexes 全空的 taxonomy.json。"""

    responses = _successful_responses({"internal": []}, {"internal": []})
    responses[BASE + "IndexTopTen.html"] = _result(ok=False, error="ECONNRESET")
    module = _load(monkeypatch, _Crawler(responses), tmp_root)

    with pytest.raises(RuntimeError) as error:
        asyncio.run(module.main())

    assert "IndexTopTen.html" in str(error.value)
    assert "ECONNRESET" in str(error.value)
    assert not (tmp_root / "_work" / "owasp-cheatsheets" / "taxonomy.json").exists()


def test_successful_crawl_but_empty_markdown_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_root: Path
) -> None:
    """抓取自称成功却没有正文：同样显式报错，不写成"这个索引没有 section"。"""

    responses = _successful_responses({"internal": []}, {"internal": []})
    responses[BASE + "IndexASVS.html"] = _result(body=None)
    module = _load(monkeypatch, _Crawler(responses), tmp_root)

    with pytest.raises(RuntimeError) as error:
        asyncio.run(module.main())

    assert "正文为空" in str(error.value)
    assert not (tmp_root / "_work" / "owasp-cheatsheets" / "taxonomy.json").exists()


def test_links_none_is_not_an_attribute_error(
    monkeypatch: pytest.MonkeyPatch, tmp_root: Path
) -> None:
    """crawl 成功但 `links` 为 None（crawl4ai 的失败形态之一）：按"没有链接"读，不崩。"""

    responses = _successful_responses(None, {"internal": [{"href": SHEET}]})
    module = _load(monkeypatch, _Crawler(responses), tmp_root)

    asyncio.run(module.main())

    payload = json.loads(
        (tmp_root / "_work" / "owasp-cheatsheets" / "taxonomy.json").read_text(encoding="utf-8")
    )
    assert payload["all_sheets"] == [SHEET]
