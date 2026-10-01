"""`ApiPolicyClient` 的传输选择：回环地址不读代理环境（2026-10-01 第 0.5 条）。

背景（23 号 §15.2）：本机 pre-push 门禁第 29 步报过 `Policy API 502 unknown`（响应体为空），
而平台自身不产生 502（`policy_api.errors.STATUS_BY_CODE` 里没有这一档）——推断是回环请求
被系统代理接走了（**未核实**）。这条行为因此被钉住：**回环地址**用不读代理的 opener，
**非回环地址保持原样**（部署场景可能需要代理），注入的 `opener` 参数优先级不变。

**修复前会红**：把 `orchestration.client._default_transport_opener` 换回
`urllib.request.urlopen`，第 2 条断言立即失败（实测读数见 23 号 §16.0）。
为什么用"读 opener 的代理表"而不是起一个真服务器：这条用例要证明的是**代理不会被咨询**，
而 `ProxyHandler.proxies == {}` 正是 urllib 判定"不走代理"的唯一依据；
"opener 真的被用上"由既有的 `FakeOpener` 一族用例（`tests/integration/` 与 `tests/security/`）覆盖。
"""

from __future__ import annotations

import urllib.request
from typing import Any

from orchestration.client import ApiPolicyClient

# 一个注定连不上的地址：它只需要"被读到"，不需要可用。
FORGED_PROXY = "http://127.0.0.1:9"


def _configured_proxy_tables(opener: Any) -> Any:
    """opener 上**实际挂着**的代理表（列表）。

    `urllib.request.urlopen`（函数形态）与"不读代理"的 opener 都返回空列表——差别不在
    "表是不是空的"，而在**有没有代理处理器**：`ProxyHandler({})` 一个 `<scheme>_open` 方法
    都不装，`add_handler` 于是根本不登记它（`urllib/request.py:766-775`、`:408-453`），
    所以"不读代理"的 opener 与"读过代理但表为空"的 opener 在这里长得一样——
    这也正是断言要写成"没有非空代理表"的原因。
    """

    target = getattr(opener, "__self__", opener)
    return [
        dict(handler.proxies)
        for handler in getattr(target, "handlers", ())
        if isinstance(handler, urllib.request.ProxyHandler)
    ]


def _forge_proxy(monkeypatch: Any) -> None:
    monkeypatch.setenv("HTTP_PROXY", FORGED_PROXY)
    monkeypatch.setenv("HTTPS_PROXY", FORGED_PROXY)
    monkeypatch.setenv("ALL_PROXY", FORGED_PROXY)
    # no_proxy 会把"没走代理"变成环境变量的功劳：这里明确排掉它。
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)


def test_the_forged_proxy_environment_reaches_the_default_opener(monkeypatch) -> None:
    """对照：先证明"伪造的代理变量会被默认 opener 读走"，后面的断言才有意义。"""

    _forge_proxy(monkeypatch)
    tables = _configured_proxy_tables(urllib.request.build_opener())
    assert any(tables), "伪造的代理环境变量没有被默认 opener 读到：这组用例失效了"
    assert FORGED_PROXY in "".join(str(key) for table in tables for key in table.values())


def test_loopback_base_url_gets_an_opener_with_an_empty_proxy_table(monkeypatch) -> None:
    """回环地址的三种写法（大小写不敏感）都必须拿到"代理表为空"的 opener。"""

    _forge_proxy(monkeypatch)
    for url in (
        "http://127.0.0.1:8000",
        "http://[::1]:8000",
        "http://localhost:8000",
        "http://LocalHost:8000",
    ):
        client = ApiPolicyClient(url, token="test-token")
        # 第一句是**可证伪**的那一句：修复前这里就是 `urllib.request.urlopen`。
        assert client._opener is not urllib.request.urlopen, url
        # 第二句验效果：回环 opener 上不存在任何非空代理表。
        assert all(not table for table in _configured_proxy_tables(client._opener)), url


def test_non_loopback_base_url_keeps_the_default_urlopen(monkeypatch) -> None:
    """非回环地址**保持原样**：仍是 `urllib.request.urlopen`（它会读代理设置）。

    `127.0.0.2` 也在这条路上——口径写死三个写法，别的回环写法不猜（注释在常量旁）。
    """

    _forge_proxy(monkeypatch)
    for url in ("http://api.example.com:8000", "https://policy.internal", "http://127.0.0.2:8000"):
        assert ApiPolicyClient(url, token="test-token")._opener is urllib.request.urlopen, url


def test_an_injected_opener_still_wins(monkeypatch) -> None:
    """注入的 `opener` 优先级不变：回环与否都不影响它。"""

    _forge_proxy(monkeypatch)

    def opener(request: Any, timeout: Any = None) -> Any:  # pragma: no cover - 不该被调用
        raise AssertionError("注入的 opener 必须优先")

    for url in ("http://127.0.0.1:8000", "http://api.example.com:8000"):
        client = ApiPolicyClient(url, token="test-token", opener=opener)
        assert client._opener is opener, url
