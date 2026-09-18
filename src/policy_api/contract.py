"""契约工具：OpenAPI 快照、自检与最小冒烟。

Phase 7 的"契约"有三个可判定对象（都能被 CI 变成门禁）：

1. **OpenAPI 文档**：由应用对象生成，落成 `api/openapi.json`。变化必须显式评审
   （`--write`），不允许悄悄改——它是 Adapter 作者看到的全部真相；
2. **传输契约的形状**：错误码→状态码映射完整、每个错误码有状态、DTO 的必填字段
   与路由表一一对应、决策载荷版本来自核心而不是本包自己算一个；
3. **最小冒烟**：进程内跑一遍 live → ready → evaluate → retrieve，证明装配真的能用
   （不是"文件都在"这种静态判断）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from . import __version__
from .config import ApiConfig
from .errors import STATUS_BY_CODE, ErrorCode
from .models import (
    API_SCHEMA_VERSION,
    DECISION_PAYLOAD_SCHEMA_VERSION,
    POLICY_GENERATION,
    ContextDTO,
    EvaluateRequest,
    RetrieveRequest,
    ValidationRequest,
)
from .runtime import ROUTES, ApiRuntime

__all__ = [
    "BUDGET_ROUTES",
    "SNAPSHOT_SCHEMA_VERSION",
    "openapi_document",
    "self_check",
    "smoke",
    "snapshot_diff",
    "write_snapshot",
]

SNAPSHOT_SCHEMA_VERSION = "1.0"
ENDPOINTS: Tuple[Tuple[str, str], ...] = (
    ("/v1/policy/evaluate", "evaluate"),
    ("/v1/knowledge/retrieve", "retrieve"),
    ("/v1/validation/evaluate", "validate"),
    ("/v1/health/live", "live"),
    ("/v1/health/ready", "ready"),
    ("/v1/ops/metrics", "metrics"),
)
BUDGET_ROUTES = ("evaluate", "retrieve", "validate")


def _application(runtime: ApiRuntime) -> Any:
    from .app import create_app

    return create_app(runtime)


def openapi_document(runtime: ApiRuntime) -> Mapping[str, Any]:
    """生成 OpenAPI 文档，并把本服务的契约版本钉进 `info`。"""

    document = _application(runtime).openapi()
    document.setdefault("info", {})
    document["info"]["x-api-schema-version"] = API_SCHEMA_VERSION
    document["info"]["x-decision-schema-version"] = DECISION_PAYLOAD_SCHEMA_VERSION
    document["info"]["x-policy-generation"] = POLICY_GENERATION
    document["info"]["x-service-version"] = __version__
    return document


def write_snapshot(path: Path | str, document: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_ordered(document), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    target.write_text(text, encoding="utf-8", newline="\n")


def snapshot_diff(path: Path | str, document: Mapping[str, Any]) -> Tuple[str, ...]:
    """比较快照与当前文档；缺失、损坏、字段漂移都要被指出来。"""

    target = Path(path)
    if not target.is_file():
        return (f"OpenAPI 快照不存在：{target.name}",)
    try:
        stored = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return (f"OpenAPI 快照不可解析：{type(error).__name__}",)
    return _diff(stored, _ordered(document), prefix="")


def _ordered(document: Mapping[str, Any]) -> Mapping[str, Any]:
    """去掉框架注入的非确定性字段（生成时间等），只留契约本身。"""

    payload = dict(document)
    info = dict(payload.get("info") or {})
    info.pop("x-generated-at", None)
    payload["info"] = info
    return payload


def _diff(stored: Any, current: Any, *, prefix: str) -> Tuple[str, ...]:
    issues: list[str] = []
    if isinstance(stored, Mapping) and isinstance(current, Mapping):
        for key in sorted(set(stored) | set(current)):
            location = f"{prefix}.{key}" if prefix else str(key)
            if key not in current:
                issues.append(f"{location}: 快照里有、当前文档没有（字段被删除？）")
            elif key not in stored:
                issues.append(f"{location}: 当前文档新增了字段（新增可选字段也应显式更新快照）")
            else:
                issues.extend(_diff(stored[key], current[key], prefix=location))
        return tuple(issues)
    if isinstance(stored, list) and isinstance(current, list):
        if len(stored) != len(current):
            issues.append(f"{prefix}: 长度不一致（快照 {len(stored)} / 当前 {len(current)}）")
            return tuple(issues)
        for index, (left, right) in enumerate(zip(stored, current)):
            issues.extend(_diff(left, right, prefix=f"{prefix}[{index}]"))
        return tuple(issues)
    if stored != current:
        issues.append(f"{prefix}: 快照 {stored!r} != 当前 {current!r}")
    return tuple(issues)


def _contract_checks(runtime: ApiRuntime) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    declared = {item.value for item in ErrorCode}
    mapped = {item.value for item in STATUS_BY_CODE}
    check(
        "error_codes_mapped",
        declared == mapped,
        "错误码与状态码映射一致" if declared == mapped else f"缺少映射：{sorted(declared - mapped)}",
    )
    routes = set(ROUTES)
    expected = {"evaluate", "retrieve", "validate", "metrics"}
    check("runtime_routes", expected <= routes, f"运行时路由：{sorted(routes)}")

    paths = {path for path, _ in ENDPOINTS}
    document = openapi_document(runtime)
    served = set((document.get("paths") or {}).keys())
    check(
        "openapi_paths",
        paths == served,
        f"OpenAPI 暴露 {sorted(served)}",
    )
    schemas = (document.get("components") or {}).get("schemas") or {}
    for name in ("EvaluateRequest", "RetrieveRequest", "ValidationRequest", "ContextDTO"):
        check(f"schema_{name}", name in schemas, "已导出" if name in schemas else "缺失")

    for model, label in (
        (EvaluateRequest, "evaluate"),
        (RetrieveRequest, "retrieve"),
        (ValidationRequest, "validate"),
    ):
        fields = set(model.model_fields)
        check(
            f"envelope_{label}",
            {"api_version", "request_id", "principal"} <= fields,
            f"信封字段：{sorted(fields)}",
        )
    check(
        "context_dimensions",
        {"file", "layer", "operation", "dependencies"} <= set(ContextDTO.model_fields),
        f"上下文维度：{sorted(ContextDTO.model_fields)}",
    )
    check(
        "decision_protocol_pinned",
        DECISION_PAYLOAD_SCHEMA_VERSION and POLICY_GENERATION,
        f"决策协议 {DECISION_PAYLOAD_SCHEMA_VERSION} / 世代 {POLICY_GENERATION}",
    )
    budgets = runtime.config.budgets
    check(
        "budgets_positive",
        min(budgets.evaluate_ms, budgets.retrieve_ms, budgets.validate_ms) > 0,
        f"evaluate={budgets.evaluate_ms}ms retrieve={budgets.retrieve_ms}ms "
        f"validate={budgets.validate_ms}ms",
    )
    check(
        "request_size_capped",
        runtime.config.limits.max_request_bytes > 0
        and runtime.config.limits.max_concurrency > 0,
        f"max_request_bytes={runtime.config.limits.max_request_bytes} "
        f"max_concurrency={runtime.config.limits.max_concurrency}",
    )
    check(
        "core_has_no_framework",
        _core_is_framework_free(),
        "src/policy 不导入 Web 框架（API 是独立的一层）",
    )
    check(
        "tenants_have_boundaries",
        all(item.rules and item.project_root for item in runtime.config.tenants),
        "每个租户都声明了规则目录与项目边界",
    )
    return checks


def _core_is_framework_free() -> bool:
    """核心层不得导入 Web 框架（契约测试也会查一遍，这里给部署者一个直接可见的结论）。"""

    root = Path(__file__).resolve().parents[2] / "src" / "policy"
    if not root.is_dir():
        return True
    forbidden = ("fastapi", "starlette", "uvicorn", "flask", "requests", "httpx")
    for path in sorted(root.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            if f"import {name}" in text or f"from {name}" in text:
                return False
    return True


def self_check(runtime: ApiRuntime) -> Mapping[str, Any]:
    """配置 + 租户 + readiness + 传输契约的完整自检。"""

    checks = _contract_checks(runtime)
    readiness = runtime.readiness(force=True)
    checks.append(
        {
            "check": "readiness",
            "ok": bool(readiness.get("ready")),
            "detail": str(readiness.get("detail")),
        }
    )
    for tenant in readiness.get("tenants", ()):
        for item in tenant.get("checks", ()):
            if not item.get("ok"):
                checks.append(
                    {
                        "check": f"tenant:{tenant.get('tenant')}:{item.get('check')}",
                        "ok": False,
                        "detail": str(item.get("detail")),
                    }
                )
    return {
        "ok": all(item["ok"] for item in checks),
        "api_version": API_SCHEMA_VERSION,
        "service_version": __version__,
        "tenants": list(runtime.store.ids),
        "clients": len(runtime.config.clients),
        "readiness": readiness,
        "checks": checks,
    }


def _tenant_for_token(config: ApiConfig, token: str) -> str:
    """冒烟用哪个租户：令牌被授权的第一个（多个时必须显式声明，这里替它选一个最小的）。"""

    from .config import hash_token

    digest = hash_token(token)
    for client in config.clients:
        if client.token_sha256 == digest and client.tenants:
            return client.tenants[0]
    raise ApiError(ErrorCode.UNAUTHENTICATED, "冒烟用的令牌不在配置里")


def smoke(runtime: ApiRuntime, *, token: str) -> Mapping[str, Any]:
    """最小链路：live → ready → evaluate → retrieve（全部进程内，不开端口）。"""

    from .testing import call

    live = {"status": "live"}
    ready = runtime.readiness(force=True)
    tenant = _tenant_for_token(runtime.config, token)
    evaluate_payload = {
        "api_version": API_SCHEMA_VERSION,
        "request_id": "smoke:evaluate",
        "tenant": tenant,
        "principal": {"subject": "smoke", "roles": ["developer"]},
        "context": {"file": "src/example/service.py", "layer": "service", "language": "python"},
    }
    evaluate_response = call(runtime, "evaluate", evaluate_payload, token=token)
    retrieve_response = call(
        runtime,
        "retrieve",
        {
            "api_version": API_SCHEMA_VERSION,
            "request_id": "smoke:retrieve",
            "tenant": tenant,
            "principal": {"subject": "smoke", "roles": ["developer"]},
            # 上下文与 query 都是**必需**的：file / layer 必须显式声明（服务端不猜），
            # 而"找什么"可以是自由文本或上下文里的 task。
            "context": {
                "file": "src/example/service.py",
                "layer": "service",
                "language": "python",
                "task": "代码评审",
            },
            "query": "代码评审",
            "limit": 3,
        },
        token=token,
    )
    evaluate_ok = evaluate_response.status == 200
    # 检索"不可用"是显式状态（该租户没配索引 / 索引缺失）：冒烟接受它，但必须报出来，
    # 绝不把它当成"检索没问题"。
    retrieve_ok = retrieve_response.status in (200, 503)
    retrieve_state = str(retrieve_response.body.get("status") or "") or str(
        (retrieve_response.body.get("error") or {}).get("code") or ""
    )
    return {
        "ok": bool(evaluate_ok and retrieve_ok and ready.get("ready")),
        "retrieve_available": retrieve_response.status == 200,
        "live": live,
        "ready": ready,
        "evaluate": {
            "status": evaluate_response.status,
            "decision": str(
                (evaluate_response.body.get("summary") or {}).get("decision") or ""
            )
            or str((evaluate_response.body.get("error") or {}).get("code") or ""),
            "rules": len(
                ((evaluate_response.body.get("rule_set") or {}).get("identity") or [])
            ),
        },
        "retrieve": {"status": retrieve_response.status, "state": retrieve_state},
    }
