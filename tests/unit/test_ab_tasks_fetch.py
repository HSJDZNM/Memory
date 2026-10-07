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
import urllib.parse
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

OTHER_SOURCE = ab_tasks.TaskSource(
    id="other-hf",
    kind="hf-rows",
    url="https://huggingface.co/datasets/other-org/other-dataset",
    revision="1" * 40,
    license="CC0-1.0 (fixture)",
    license_source="fixture",
    gated=False,
    expected_rows=0,
    note="夹具源：证明请求里的坐标来自声明而不是写死的 SWE-bench",
    hf_config="custom-config",
    hf_split="train",
)


def test_fetch_requests_the_coordinates_of_its_own_source(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """第二个 hf-rows 源按**它自己的** dataset/config/split 取，不沿用写死的 SWE-bench。"""

    monkeypatch.setitem(ab_tasks.SOURCES, "other-hf", OTHER_SOURCE)
    requested: list[str] = []

    def fake_get(url: str, timeout: int = 120) -> bytes:
        requested.append(url)
        return json.dumps({"rows": [], "num_rows_total": 0}).encode("utf-8")

    monkeypatch.setattr(ab_tasks, "_get", fake_get)

    reading = ab_tasks.fetch("other-hf", root=tmp_root / "tasks")

    assert requested, "至少要发一次请求"
    params = urllib.parse.parse_qs(urllib.parse.urlparse(requested[0]).query)
    assert params["dataset"] == ["other-org/other-dataset"]
    assert params["config"] == ["custom-config"]
    assert params["split"] == ["train"]
    assert "princeton-nlp" not in requested[0]
    assert reading["dataset"] == "other-hf"
    assert reading["rows"] == 0


def test_dataset_id_without_the_marker_is_an_explicit_error() -> None:
    """URL 里取不出 dataset 名时显式报错，不猜、不回落。"""

    broken = ab_tasks.TaskSource(
        id="broken",
        kind="hf-rows",
        url="https://example.invalid/no-marker",
        revision="2" * 40,
        license="",
        license_source="",
        gated=False,
        expected_rows=0,
        note="",
    )

    with pytest.raises(ab_tasks.AbTaskError) as error:
        ab_tasks._hf_dataset_id(broken)

    assert "dataset" in str(error.value)
