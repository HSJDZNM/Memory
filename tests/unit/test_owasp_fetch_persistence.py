"""OWASP 02_fetch：一条页面的失败不许吞掉整轮结果，索引与正文必须同一轮。

为什么需要：旧版只把 crawl 本身放进 try，清洗 / 落盘 / 链接提取全在守护之外，
asyncio.gather 又不带 return_exceptions——任何一步抛异常都会在 json.dump(meta.json) 之前
中断整个 main()，于是**所有已抓页面的元数据一起丢掉**，而 content/ 里留着这一轮的 .md，
与上一轮的 meta.json 配成一对。CONTENT 跨轮不清空又让"新正文 + 旧索引"成为可能。

02_fetch.py 依赖 crawl4ai（可选依赖，本机没装），因此只替换导入期需要的名字，
被驱动的是真的 main()。
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
SEED = BASE + "cheatsheets/Secure_Code_Review_Cheat_Sheet.html"
SHEET = BASE + "cheatsheets/Authentication_Cheat_Sheet.html"
INDEXES = [
    "index.html",
    "IndexASVS.html",
    "IndexProactiveControls.html",
    "IndexTopTen.html",
    "IndexMASVS.html",
    "Glossary.html",
]
BODY = "# 标题" + chr(10) + chr(10) + ("正文内容。" * 80) + chr(10)


def _result(body: str, *, ok: bool = True, status: int = 200, links: Any = None) -> Any:
    return SimpleNamespace(
        success=ok,
        status_code=status,
        markdown=SimpleNamespace(raw_markdown=body),
        links=links if links is not None else {"internal": [{"href": BASE + "cheatsheets/a.html"}]},
    )


class _Crawler:
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
    monkeypatch.chdir(tmp_root)
    work = tmp_root / "_work" / "owasp-cheatsheets"
    work.mkdir(parents=True, exist_ok=True)
    (work / "taxonomy.json").write_text(
        json.dumps({"all_sheets": [SHEET]}), encoding="utf-8", newline=""
    )
    spec = importlib.util.spec_from_file_location(
        "owasp_fetch_under_test", REPO_ROOT / "tools" / "owasp_cheatsheets" / "02_fetch.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _responses() -> dict[str, Any]:
    responses = {BASE + name: _result(BODY) for name in INDEXES}
    responses[SEED] = _result(BODY)
    responses[SHEET] = _result(BODY)
    return responses


def test_post_processing_failure_keeps_the_rest_of_the_run(
    monkeypatch: pytest.MonkeyPatch, tmp_root: Path
) -> None:
    """一页的清洗失败只记这一页：meta.json 照样写出，其余页面照样 saved。"""

    # seed 页正文带上 BOOM：走"抓取成功、后处理失败"这一支
    responses = _responses()
    responses[SEED] = _result(BODY + "BOOM")
    module = _load(monkeypatch, _Crawler(responses), tmp_root)

    def boom(md: str) -> str:
        if "BOOM" in md:
            raise ValueError("describe 爆了")
        return "描述"

    monkeypatch.setattr(module, "describe", boom)
    asyncio.run(module.main())

    work = tmp_root / "_work" / "owasp-cheatsheets"
    meta = json.loads((work / "meta.json").read_text(encoding="utf-8"))
    assert set(meta) == set(responses), "每一页都必须有一条读数"
    assert meta[SEED]["saved"] is False
    assert meta[SEED]["error"] == "ValueError"
    assert meta[SHEET]["saved"] is True
    # 后处理失败的那一页不许留下正文（正文先算完再落盘）
    assert not (work / "content" / (module.slug_of(SEED) + ".md")).exists()
    assert (work / "content" / (module.slug_of(SHEET) + ".md")).is_file()


def test_stale_content_and_meta_from_a_previous_run_are_replaced(
    monkeypatch: pytest.MonkeyPatch, tmp_root: Path
) -> None:
    """上一轮留下的 content/*.md 与 meta.json 不许与这一轮混在一起。"""

    work = tmp_root / "_work" / "owasp-cheatsheets"
    (work / "content").mkdir(parents=True, exist_ok=True)
    (work / "content" / "stale.md").write_text("上一轮的正文" + chr(10), encoding="utf-8", newline="")
    (work / "meta.json").write_text(json.dumps({"old": {"saved": True}}), encoding="utf-8", newline="")

    module = _load(monkeypatch, _Crawler(_responses()), tmp_root)
    asyncio.run(module.main())

    assert not (work / "content" / "stale.md").exists()
    meta = json.loads((work / "meta.json").read_text(encoding="utf-8"))
    assert "old" not in meta
    assert meta[SEED]["saved"] is True
