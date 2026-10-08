"""mirror_docs.fetch_plain_file：非 200 / 超时 / 网络错误都要变成读数，且有超时。

为什么需要：旧实现没有 timeout（一次挂起就拖死整轮镜像），且非 200 返回空串——调用方
`if extra.get(dest)` 直接跳过，而 README/STRUCTURE 照旧宣称这份文件已保存：镜像少了一页，
没有任何人看得见。
"""

from __future__ import annotations

import asyncio
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
        "mirror_docs_plain_under_test", REPO_ROOT / "tools" / "mirror_docs.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _install_aiohttp(
    monkeypatch: pytest.MonkeyPatch,
    * ,
    status: int | None = None,
    text: str = "",
    error: Exception | None = None,
    calls: list | None = None,
) -> None:
    """最小 aiohttp 替身：只实现 fetch_plain_file 用到的那几个形状。"""

    class _Timeout:
        def __init__(self, total: float | None = None) -> None:
            self.total = total

    class _Response:
        def __init__(self) -> None:
            self.status = status

        async def text(self) -> str:
            return text

        async def __aenter__(self) -> "_Response":
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    class _Session:
        def get(self, url: str, timeout: Any = None) -> _Response:
            if calls is not None:
                calls.append({"url": url, "timeout": getattr(timeout, "total", None)})
            if error is not None:
                raise error
            return _Response()

        async def __aenter__(self) -> "_Session":
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    class _ClientSession:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _Session:
            return _Session()

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    monkeypatch.setitem(
        sys.modules,
        "aiohttp",
        _stub("aiohttp", ClientSession=_ClientSession, ClientTimeout=_Timeout),
    )


def test_non_200_is_a_reading_with_a_reason(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """404 必须是读数（status/reason），不是空串。"""

    module = _load_mirror_docs(monkeypatch)
    calls: list = []
    _install_aiohttp(monkeypatch, status=404, calls=calls)

    reading = asyncio.run(module.fetch_plain_file("https://example.com/LICENSE"))

    assert reading["status"] == 404
    assert reading["text"] == ""
    assert reading["reason"] == "HTTP 404"
    assert calls[0]["timeout"] == 180, "请求必须带超时（旧实现没有，会挂死整轮镜像）"


def test_network_error_is_a_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    """连不上 / 超时：reason 里要有异常类型原文，不是空串。"""

    module = _load_mirror_docs(monkeypatch)
    _install_aiohttp(monkeypatch, error=TimeoutError("connect timeout"))

    reading = asyncio.run(module.fetch_plain_file("https://example.com/LICENSE"))

    assert reading["status"] is None
    assert reading["text"] == ""
    assert "TimeoutError" in reading["reason"]
    assert "connect timeout" in reading["reason"]


def test_ok_fetch_returns_stripped_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """200 时照旧给出正文（strip 之后），reason 为空。"""

    module = _load_mirror_docs(monkeypatch)
    _install_aiohttp(monkeypatch, status=200, text="  CC BY-SA 4.0  " + chr(10))

    reading = asyncio.run(module.fetch_plain_file("https://example.com/LICENSE"))

    assert reading["status"] == 200
    assert reading["text"] == "CC BY-SA 4.0"
    assert reading["reason"] == ""