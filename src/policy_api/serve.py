"""把应用交给 ASGI 服务器（uvicorn）。

启动不是"能跑就行"：装配失败、配置不合法、租户装不上时**拒绝启动**，
并且把 `readiness` 的结论打在启动日志里——一个"起来了但没有规则可服务"的进程
比启动失败更危险。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .config import ConfigError, load_api_config
from .runtime import ApiRuntime

__all__ = ["endpoint", "serve"]


def _port(text: str, *, source: Any) -> int:
    """端口必须是 1-65535 的整数；否则抛 ConfigError（配置错误，不是运行时错误）。"""

    try:
        port = int(text)
    except ValueError as error:
        raise ConfigError(f"base_url 端口非法：{source!r}") from error
    if not 1 <= port <= 65535:
        raise ConfigError(f"base_url 端口越界（1-65535）：{source!r}")
    return port


def endpoint(config: Any) -> tuple[str, int]:
    """从 base_url 解析监听地址（配置即数据，不写死端口）。

    解析失败一律 **ConfigError**：监听地址是部署边界，拼错一个字符必须变成
    "配置不可用，拒绝启动 = 2"。以前 `int(port_text)` 的 ValueError 会从 `endpoint()`
    直接冒出去（`serve()` 只把 ConfigError 翻译成退出码 2），部署者看到的是一段
    traceback 而不是可判断的退出码；未闭合的 `[` 还会静默产出 `('::1', 8088)`
    这种捏造出来的地址。
    """

    source = str(config.base_url)
    url = source
    if "://" in url:
        url = url.split("://", 1)[1]
    url = url.split("/", 1)[0]
    if url.startswith("["):  # IPv6 字面量
        host, closing, rest = url[1:].partition("]")
        if not closing:
            raise ConfigError(f"base_url 的 IPv6 字面量缺少闭合的 ']'：{source!r}")
        if not host:
            raise ConfigError(f"base_url 的 IPv6 字面量为空：{source!r}")
        return host, _port(rest.lstrip(":") or "8088", source=source)
    host, _, port_text = url.partition(":")
    return host or "127.0.0.1", _port(port_text or "8088", source=source)


def serve(
    config_path: Path | str,
    *,
    root: Optional[Path | str] = None,
    log_level: str = "info",
    runtime: Optional[ApiRuntime] = None,
) -> int:
    """启动 ASGI 服务。返回进程退出码（配置错误 = 2，装配失败 = 3）。"""

    import uvicorn

    from .app import create_app

    try:
        config = load_api_config(config_path, root=root)
    except ConfigError as error:
        print(f"policy-api: 配置不可用，拒绝启动：{error}")
        return 2
    instance = runtime or ApiRuntime(config, root=root)
    report = instance.readiness(force=True)
    if not report.get("ready"):
        print(f"policy-api: readiness 未通过，拒绝启动：{report.get('detail')}")
        for tenant in report.get("tenants", ()):
            for item in tenant.get("checks", ()):
                if not item.get("ok"):
                    print(f"  - {tenant.get('tenant')} / {item.get('check')}: {item.get('detail')}")
        return 3
    try:
        # 用 **instance 自己的 config**：注入了 runtime 时，真正在服务的是它，
        # 而 `config` 是刚刚从 `config_path` 重新读进来的那一份——两者可以不是同一份配置，
        # 拿后者的地址监听等于让"服务听在哪个地址"与"服务按哪份配置判定"分家。
        host, port = endpoint(instance.config)
    except ConfigError as error:
        # 与 load_api_config 同一条出口：配置读不懂 / 写错了都是"拒绝启动 = 2"，
        # 绝不把部署配置的错误变成一段 traceback（那既没有退出码语义，也掩盖了原因）。
        print(f"policy-api: 配置不可用，拒绝启动：{error}")
        return 2
    uvicorn.run(
        create_app(instance),
        host=host,
        port=port,
        log_level=log_level,
    )
    return 0
