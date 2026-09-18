"""HTTP 传输层：FastAPI 应用。

这一层只做四件事：解析 Authorization、限制请求体、把 JSON 交给 `ApiRuntime`、
把 `ApiError` 翻译成结构化错误。**判定不在这一层发生**——把逻辑写进路由，
就等于给"同一套规则"长出第二个实现，本地 SDK 与 API 的结论迟早会分叉。

为什么现在才引入 Web 框架（Phase 7 文档第 6 步）：契约（DTO、版本、错误形状、幂等与
budget 语义）已经在 `policy_api.models` / `runtime` 里固定，并能脱离 HTTP 测试；
框架只是把它接到线上，换框架不需要改契约。

**唯一的校验者**：路由声明一个"握手模型"（结构由 `policy_api.models` 的 DTO 程序化生成，
并且 `extra='ignore'`），框架用它生成 OpenAPI 文档；真正的字段校验仍然只有一处——
`ApiRuntime` 里的 `EvaluateRequest` / `RetrieveRequest` / `ValidationRequest`
（`extra='forbid'`，未知字段报错）。于是"文档描述的"和"实际接受的"来自同一份定义，
而框架版本不会悄悄改变错误语义。
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ConfigDict, ValidationError, create_model
from starlette.exceptions import HTTPException as StarletteHTTPException

from .errors import ApiError, ErrorCode, error_payload
from .models import (
    API_SCHEMA_VERSION,
    ContextDTO,
    EvaluateRequest as EvaluateDTO,
    PrincipalDTO,
    RetrieveRequest as RetrieveDTO,
    ValidationRequest as ValidationDTO,
)
from .runtime import ApiRuntime

__all__ = ["create_app", "handshake_models", "route_table"]

# 路由表：URL → 运行时路由名（台账键、指标键与错误分类都用运行时名字，不用 URL）。
route_table = (
    ("/v1/policy/evaluate", "evaluate"),
    ("/v1/knowledge/retrieve", "retrieve"),
    ("/v1/validation/evaluate", "validate"),
)
_OPS_ROUTES = ("/v1/ops/metrics",)

_PERMISSIVE = ConfigDict(extra="ignore")

# 每个 POST 路由可能返回的状态码。**这是契约的一部分**：错误分类是服务端的选择，
# 不该在文档里写成框架默认的 422。这些都是显式 4xx/5xx——成功路径永远是 200。
_ROUTE_STATUS_CODES: Mapping[str, tuple[int, ...]] = {
    "evaluate": (400, 401, 403, 404, 409, 413, 415, 429, 500, 503, 504),
    "retrieve": (400, 401, 403, 404, 409, 413, 415, 429, 500, 503, 504),
    "validate": (400, 401, 403, 404, 409, 413, 415, 429, 500, 503, 504),
}
_READINESS_STATUS_CODES = (200, 503)
_METRICS_STATUS_CODES = (200, 403)

# 路由 → OpenAPI operationId / tag（URL 与运行时路由名分开：改 URL 不该改台账语义）。
_OPERATION_IDS = {
    "evaluate": "policyEvaluate",
    "retrieve": "knowledgeRetrieve",
    "validate": "validationEvaluate",
}
_TAGS = {"evaluate": "policy", "retrieve": "knowledge", "validate": "validation"}


def _handshake(name: str, source: Any) -> Any:
    """按 DTO 生成"只用于文档"的请求模型：字段可选、未知字段忽略。

    校验锚点只有一个（运行时的 DTO）。这里放宽是为了让框架的 pre-validation
    不会用"另一套错误形状"抢先回答，同时 OpenAPI 仍然如实描述协议。
    """

    fields = {
        key: (Optional[field.annotation], None) for key, field in source.model_fields.items()
    }
    return create_model(name, __config__=_PERMISSIVE, **fields)  # type: ignore[call-overload]


class EvaluateRequest(_handshake("EvaluateRequest", EvaluateDTO)):  # type: ignore[misc,valid-type]
    """POST /v1/policy/evaluate 的请求体（结构见 policy_api.models.EvaluateRequest）。"""


class RetrieveRequest(_handshake("RetrieveRequest", RetrieveDTO)):  # type: ignore[misc,valid-type]
    """POST /v1/knowledge/retrieve 的请求体。"""


class ValidationRequest(_handshake("ValidationRequest", ValidationDTO)):  # type: ignore[misc,valid-type]
    """POST /v1/validation/evaluate 的请求体。"""


class ContextEnvelope(_handshake("ContextDTO", ContextDTO)):  # type: ignore[misc,valid-type]
    """上下文维度（OpenAPI 组件；运行时仍由 ContextDTO 校验）。"""


class PrincipalEnvelope(_handshake("PrincipalDTO", PrincipalDTO)):  # type: ignore[misc,valid-type]
    """主体声明（OpenAPI 组件）。"""


def handshake_models() -> Mapping[str, Any]:
    return {
        "EvaluateRequest": EvaluateRequest,
        "RetrieveRequest": RetrieveRequest,
        "ValidationRequest": ValidationRequest,
        "ContextDTO": ContextEnvelope,
        "PrincipalDTO": PrincipalEnvelope,
    }


def _json(status: int, body: Mapping[str, Any], headers: Optional[Mapping[str, str]] = None) -> JSONResponse:
    return JSONResponse(status_code=status, content=dict(body), headers=dict(headers or {}))


def _error_response(error: ApiError, request: Request) -> JSONResponse:
    return _json(
        error.status,
        error_payload(
            error,
            request_id=request.headers.get("X-Request-Id") or None,
            trace_id=request.headers.get("X-Trace-Id") or None,
        ),
    )


def _too_large(headers: Mapping[str, str], limit: int) -> bool:
    declared = headers.get("content-length")
    if not declared:
        return False
    try:
        return int(declared) > limit
    except ValueError:
        return False


async def _read_body(request: Request, limit: int) -> bytes:
    """读到第一个超过上限的块就停下（不把超大请求体整个吃进内存）。"""

    if _too_large(request.headers, limit):
        raise ApiError(ErrorCode.BODY_TOO_LARGE, f"请求体超过上限 {limit} 字节")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise ApiError(ErrorCode.BODY_TOO_LARGE, f"请求体超过上限 {limit} 字节")
    return bytes(body)


def _body_guard(limit: int) -> Any:
    """把"只读一次、且先于框架解析"的请求体放进依赖里。

    ```
    async def guard(request: Request) -> None:
        request.state.raw_body = await _read_body(request, limit)
    ```

    为什么必须是依赖而不是"处理器函数的第一行"：FastAPI 在调用处理器**之前**就已经
    按签名把请求体解析成了对象，于是"超大请求体"会先撞上框架的解析器并报成
    400 body_invalid，我们的 413 永远没有机会执行。依赖在框架校验之前解析，
    判定权因此回到了服务端——错误分类是契约的一部分，不能由框架版本决定。
    """

    async def guard(request: Request) -> None:
        request.state.raw_body = await _read_body(request, limit)

    return Depends(guard)


def create_app(runtime: ApiRuntime) -> FastAPI:
    """按运行时装配 ASGI 应用。同一份契约可以用不同框架实现（Phase 7 第 6 步）。"""

    app = FastAPI(
        title="Engineering Policy Platform API",
        version=API_SCHEMA_VERSION,
        summary="把规则、检索与验证能力服务化；判定仍由核心 Policy Engine 做。",
        docs_url=None,  # 交互文档默认关闭：它会把全部 schema 暴露给未认证的访问者
        redoc_url=None,
        openapi_url="/v1/openapi.json",
    )
    app.state.runtime = runtime

    async def handle_route(route: str, request: Request) -> JSONResponse:
        limit = runtime.config.limits.max_request_bytes
        # 请求体由依赖读过一次（顺序见 _body_guard）：这里只消费结果，不再碰数据流。
        raw = getattr(request.state, "raw_body", None)
        if raw is None:  # 理论上不会发生；真发生了就是"没读到请求体"，按协议错误拒绝
            raw = b""
        content_type = (request.headers.get("content-type") or "").split(";")[0].strip()
        if content_type and content_type != "application/json":
            raise ApiError(
                ErrorCode.UNSUPPORTED_MEDIA_TYPE, "请求体必须是 application/json"
            )
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(ErrorCode.BODY_INVALID, "请求体不是合法的 UTF-8 JSON") from None
        if not isinstance(payload, Mapping):
            raise ApiError(ErrorCode.BODY_INVALID, "请求体顶层必须是对象")
        response = runtime.handle(
            route, payload, authorization=request.headers.get("authorization")
        )
        return _json(response.status, response.body, response.headers)

    guard = _body_guard(runtime.config.limits.max_request_bytes)
    for path, route, body_model, summary in (
        (
            "/v1/policy/evaluate",
            "evaluate",
            EvaluateRequest,
            "对固定上下文给出 allow / allow_with_warnings / block。",
        ),
        (
            "/v1/knowledge/retrieve",
            "retrieve",
            RetrieveRequest,
            "检索离线规范并组装带来源的 Engineering Context。",
        ),
        (
            "/v1/validation/evaluate",
            "validate",
            ValidationRequest,
            "产出验证器证据（可选顺带判定）。",
        ),
    ):
        # **刻意不声明请求体参数**：FastAPI 会在运行依赖之前先把请求体解析成对象，
        # 于是"超大请求体"会先撞上框架的解析器，我们的 413 永远没有机会执行
        # （实测：200KB 的流式请求体会得到框架的 400，而不是服务端的 413）。
        # 请求体因此只读一次——在依赖里读、按服务端上限拒绝、再自己解析 JSON。
        # OpenAPI 文档里的请求体形状来自"握手模型"，而真正的校验只有运行时一处。
        # 两个坑都在这一行签名里：
        # 1) `_guard` 的注解**不能写 None**：get_type_hints 会把它规范成 NoneType，
        #    而 FastAPI 跳过 NoneType 参数——依赖于是被静默丢弃，"先读一次请求体"也不再发生；
        # 2) `route` 必须**绑成默认值**：它是循环变量，闭包共享同一个 cell，循环结束后
        #    三条路由会全部变成最后一个值（实测：evaluate/retrieve 都被分派成 validate，
        #    HTTP 上它们等于不存在，而进程内调用仍然正确——所以只有"经 HTTP"的用例能发现它）。
        async def handler(
            request: Request, _guard: Any = guard, _route: str = route
        ) -> JSONResponse:
            return await handle_route(_route, request)

        handler.__name__ = f"handle_{route}"
        handler.__doc__ = summary
        # `openapi_extra` 必须**传给 add_api_route**：写成 `handler.__dict__["openapi_extra"]`
        # 不会生效（FastAPI 取的是 APIRoute 实例自己的属性），文档里于是既没有请求体
        # 也没有 4xx/5xx 响应——契约看起来"什么都没有"，而运行时其实什么都检查。
        openapi_extra = {
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{body_model.__name__}"}
                    }
                },
            },
            "responses": {
                str(code): _error_response_doc(code) for code in _ROUTE_STATUS_CODES[route]
            },
        }
        app.add_api_route(
            path,
            handler,
            methods=["POST"],
            name=route,
            response_class=JSONResponse,
            operation_id=_OPERATION_IDS[route],
            tags=[_TAGS[route]],
            # 不声明 response_model：那会让框架往文档里塞一个 422 与一个假的空 schema；
            # 响应形状（决策载荷 / 检索结果 / 验证报告）由核心协议与错误信封决定，
            # 文档里以 requestBody + 逐状态码说明为准。
            responses={200: {"description": "决策 / 检索结果 / 验证证据（载荷是受控 JSON）"}},
            openapi_extra=openapi_extra,
        )

    async def ops_metrics(request: Request) -> JSONResponse:
        return await handle_route("metrics", request)

    ops_metrics.__name__ = "handle_metrics"
    app.add_api_route(
        "/v1/ops/metrics",
        ops_metrics,
        methods=["GET"],
        name="metrics",
        response_class=JSONResponse,
        operation_id="opsMetrics",
        tags=["ops"],
        responses={200: {"description": "进程内指标（路由计数、延迟分位、限流与超时计数）"}},
        openapi_extra={
            "responses": {str(code): _error_response_doc(code) for code in _METRICS_STATUS_CODES}
        },
    )

    @app.get("/v1/health/live", name="live", operation_id="healthLive", tags=["ops"])
    async def live() -> JSONResponse:
        """进程活着：不加载规则、不碰索引、不读日志——那些是 readiness 的事。"""

        return _json(
            200,
            {
                "api_version": API_SCHEMA_VERSION,
                "status": "live",
                "service": runtime.config.service_name,
                "deployment": runtime.config.deployment,
            },
        )

    @app.get(
        "/v1/health/ready",
        name="ready",
        operation_id="healthReady",
        tags=["ops"],
        responses={code: {"description": "readiness 报告（state 是权威字段）"} for code in _READINESS_STATUS_CODES},
    )
    async def ready() -> JSONResponse:
        """能安全提供策略服务：规则 / 索引 / 验证器 / 观测日志逐项检查。"""

        report = runtime.readiness()
        return _json(200 if report.get("ready") else 503, report)

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, error: ApiError) -> JSONResponse:
        """结构化错误：**所有** ApiError 都从这里出去，状态码由错误码推导。

        没有这一条，`ApiError` 会落到下面的通用处理器，把"413 / 415 / 400"一律压成 500——
        错误分类是契约的一部分（见 `errors.STATUS_BY_CODE`），不能由"漏注册一个处理器"决定。
        """

        return _error_response(error, request)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return _error_response(
            ApiError(ErrorCode.BODY_INVALID, _describe_validation(error)), request
        )

    @app.exception_handler(ValidationError)
    async def _pydantic_error(request: Request, error: ValidationError) -> JSONResponse:
        return _error_response(
            ApiError(ErrorCode.BODY_INVALID, _describe_validation(error)), request
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        # 框架自己的 404 / 405 / 415 也要走同一个错误信封：调用方不该看到两种错误形状。
        code = {
            404: ErrorCode.NOT_FOUND,
            405: ErrorCode.METHOD_NOT_ALLOWED,
            415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
        }.get(error.status_code, ErrorCode.INTERNAL_ERROR)
        return _error_response(ApiError(code, str(error.detail or "")), request)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, error: Exception) -> JSONResponse:
        # 未预期异常也不泄露内部文本；细节由观测日志里的 outcome=internal_error 承载。
        return _error_response(ApiError(ErrorCode.INTERNAL_ERROR, type(error).__name__), request)

    # 契约组件必须在**所有**路由与处理器注册之后写进文档（OpenAPI 会被缓存，先写会丢内容）。
    _install_contract_schemas(app)
    return app


def _error_response_doc(code: int) -> Mapping[str, Any]:
    return {
        "description": f"{code}：结构化错误（见 ErrorResponse）",
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
        },
    }


def _install_contract_schemas(app: FastAPI) -> None:
    """把"握手模型"与错误信封写进 OpenAPI 组件。

    请求体的形状来自 `policy_api.models` 的 DTO（由 `handshake_models()` 程序化生成），
    错误信封来自 `errors.error_payload`。两者都必须**出现在文档里**：
    调用方是照着这份文档写 Adapter 的，"服务端实际接受的形状没写进契约"等于没契约。
    """

    document = app.openapi()
    # 框架会默认声明 422，但运行时把**所有**校验失败映射成 400（错误分类由服务端决定）。
    # 文档里留着一个永远不会返回的状态码，等于让调用方为不存在的情况写分支。
    for path_item in document.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                operation.get("responses", {}).pop("422", None)
    components = document.setdefault("components", {}).setdefault("schemas", {})
    for name, model in handshake_models().items():
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        definitions = schema.pop("$defs", {})
        for key, value in definitions.items():
            components.setdefault(key, value)
        components[name] = schema
    # 422 只在组件里也去掉（HTTPValidationError / ValidationError 是框架的产物）。
    for unused in ("HTTPValidationError", "ValidationError"):
        components.pop(unused, None)
    components["ErrorResponse"] = {
        "title": "ErrorResponse",
        "type": "object",
        "required": ["error"],
        "properties": {
            "error": {
                "type": "object",
                "required": ["code", "detail", "retryable"],
                "properties": {
                    "code": {
                        "type": "string",
                        "enum": sorted(item.value for item in ErrorCode),
                    },
                    "detail": {"type": "string"},
                    "retryable": {"type": "boolean"},
                    "request_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "trace_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
            }
        },
    }
    app.openapi_schema = document


def _describe_validation(error: Any) -> str:
    """把校验失败压成一行：只保留字段位置与原因，不吐内部结构。"""

    items = error.errors() if hasattr(error, "errors") else []
    parts: list[str] = []
    for item in items[:5]:
        location = ".".join(str(part) for part in item.get("loc", ()) if part != "body")
        parts.append(f"{location or 'body'}: {item.get('msg')}")
    if len(items) > 5:
        parts.append(f"另有 {len(items) - 5} 处错误")
    return "; ".join(parts) or "请求体不合法"
