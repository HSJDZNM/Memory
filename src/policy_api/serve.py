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


def endpoint(config: Any) -> tuple[str, int]:
    """从 base_url 解析监听地址（配置即数据，不写死端口）。"""

    url = str(config.base_url)
    if "://" in url:
        url = url.split("://", 1)[1]
    url = url.split("/", 1)[0]
    if url.startswith("["):  # IPv6 字面量
        host, _, rest = url[1:].partition("]")
        port = int(rest.lstrip(":") or 8088)
        return host, port
    host, _, port_text = url.partition(":")
    return host or "127.0.0.1", int(port_text or 8088)


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
    host, port = endpoint(config)
    uvicorn.run(
        create_app(instance),
        host=host,
        port=port,
        log_level=log_level,
    )
    return 0
