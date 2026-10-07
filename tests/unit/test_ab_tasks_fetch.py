"""ab_tasks 的取用失败必须带 reason，不许把网络异常当栈回溯抛出去。

为什么需要：`_get` 只用 urllib 取远端，而 main 只捕获 (AbTaskError, KeyError)。
URLError / HTTPError / socket.timeout / IncompleteRead 全都逃出去变成裸 traceback——
“网不通 / 上游 5xx / 传到一半断了”是本模块最常见的失败形态，它们必须和“本地没有语料”
一样逐条写出来。
"""

from __future__ import annotations

import json
import socket
import urllib.error
from pathlib import Path
from typing import Any

import pytest

import ab_tasks


def test_network_error_becomes_ab_task_error(tmp_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """URLError → AbTaskError（带原因），不是裸 traceback。"""

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise urllib.error.URLError("名字解析失败")

    monkeypatch.setattr(ab_tasks.urllib.request, "urlopen", boom)

    with pytest.raises(ab_tasks.AbTaskError) as error:
        ab_tasks._get("https://example.invalid/rows")

    assert "URLError" in str(error.value)
    assert "名字解析失败" in str(error.value)


def test_timeout_and_http_error_become_ab_task_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """socket.timeout（OSError 子类）与 HTTPException（传输中断）同样被翻译。"""

    for exception in (socket.timeout("timed out"), ab_tasks.http.client.IncompleteRead(b"x", 10)):
        def boom(*args: Any, _exception: BaseException = exception, **kwargs: Any) -> Any:
            raise _exception

        monkeypatch.setattr(ab_tasks.urllib.request, "urlopen", boom)
        with pytest.raises(ab_tasks.AbTaskError) as error:
            ab_tasks._get("https://example.invalid/rows")
        assert type(exception).__name__ in str(error.value)


def test_main_reports_the_reason_instead_of_crashing(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """CLI 层：--fetch 遇到网络失败 → 退出码 2 + 一行 ab_tasks: 理由。"""

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise urllib.error.HTTPError("https://example.invalid/rows", 503, "Service Unavailable", {}, None)

    monkeypatch.setattr(ab_tasks.urllib.request, "urlopen", boom)

    code = ab_tasks.main(["--fetch", "swe-bench-verified", "--root", str(tmp_root / "tasks")])

    captured = capsys.readouterr()
    assert code == 2
    assert captured.err.startswith("ab_tasks: ")
    assert "HTTPError" in captured.err
    assert "Traceback" not in captured.err
