"""进程内调用助手：不开端口也能走完整链路。

两组工具：

- `build_runtime` / `call`：**进程内**直接调用 `ApiRuntime`。它是唯一的判定路径，
  HTTP 层只是它的一个调用方；用它可以在毫秒级跑大量边界用例；
- `make_client`：FastAPI 的 ASGI TestClient（httpx 传输，进程内，无网络）。
  需要验证 HTTP 语义（请求头、状态码、超大请求体、405/404 的形状）时用它。

两者都不需要真的起服务，也不写业务状态：所有产物（索引、观测日志、台账）都在调用方给的
临时目录里。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from .config import ApiConfig, load_api_config
from .runtime import ApiRuntime, RuntimeResponse

__all__ = ["build_runtime", "call", "make_client", "runtime_from_config"]


def build_runtime(
    config_path: Path | str, *, root: Optional[Path | str] = None, **kwargs: Any
) -> ApiRuntime:
    """从配置文件装配运行时（测试与 CLI 共用同一条装配路径）。"""

    config = load_api_config(config_path, root=root)
    return runtime_from_config(config, root=root, **kwargs)


def runtime_from_config(
    config: ApiConfig, *, root: Optional[Path | str] = None, **kwargs: Any
) -> ApiRuntime:
    return ApiRuntime(config, root=root, **kwargs)


def call(
    runtime: ApiRuntime,
    route: str,
    payload: Mapping[str, Any],
    *,
    token: Optional[str] = None,
) -> RuntimeResponse:
    """进程内调用一次；凭据既可以放信封里，也可以由调用方显式传入。"""

    body: dict[str, Any] = dict(payload)
    authorization = None
    if token is not None:
        authorization = f"Bearer {token}"
    return runtime.handle(route, body, authorization=authorization)


def make_client(runtime: ApiRuntime) -> Any:
    """ASGI 测试客户端（进程内）。需要 httpx；不需要 uvicorn、不需要端口。"""

    from fastapi.testclient import TestClient

    from .app import create_app

    return TestClient(create_app(runtime), raise_server_exceptions=False)
