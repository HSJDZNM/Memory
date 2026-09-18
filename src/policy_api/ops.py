"""运维面：liveness、readiness 与指标鉴权。

**liveness 与 readiness 的区别**（Phase 7 文档第 6 步）：

- `/v1/health/live`：进程还在、事件循环还在。它**不碰**规则集、索引和验证器——
  一个"没有规则可服务"的进程仍然是活着的进程；
- `/v1/health/ready`：能**安全地提供策略服务**。它逐个租户检查规则集可加载、
  验证器注册表可用、索引存在且可读、观测日志可写；任何一项失败就返回 503。

`ready` 载荷只报告**本服务自己**的健康状况（租户名、检查项、原因），这些东西的可见范围
本来就等于"能访问这个服务的人"，而不是某个具体资源是否存在——资源存在性从不进入响应。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Optional

from .errors import ApiError, ErrorCode

if TYPE_CHECKING:  # pragma: no cover - 仅为类型检查
    from .auth import AuthContext
    from .runtime import ApiRuntime

__all__ = ["metrics_token_ok", "readiness_report"]

# 允许读取指标的角色：集群运维的凭据用角色声明，而不是"所有已认证客户端都能看"。
METRICS_ROLES = ("ops", "service-admin")


def _utc_now() -> str:
    import datetime as clock

    return clock.datetime.now(clock.timezone.utc).isoformat().replace("+00:00", "Z")


def metrics_token_ok(config: Any, auth: "AuthContext") -> bool:
    """指标可见性：声明了运维角色的凭据，或配置里显式授权的客户端。"""

    if set(auth.roles) & set(METRICS_ROLES):
        return True
    allowed = getattr(config, "metrics_clients", ()) or ()
    return auth.client_id in tuple(allowed)


def _check_tenant(runtime: "ApiRuntime", tenant_id: str) -> Mapping[str, Any]:
    """单个租户的可服务性。任何一步失败都记原因，绝不"跳过检查当作通过"。"""

    checks: list[dict[str, Any]] = []
    tenant = runtime.store.get(tenant_id)

    try:
        rules = tenant.rules()
        checks.append(
            {
                "check": "rule_set",
                "ok": bool(rules.rules),
                "detail": f"{len(rules.rules)} 条规则",
                "rule_set_hash": rules.identity,
            }
        )
    except ApiError as error:
        checks.append({"check": "rule_set", "ok": False, "detail": error.kind})

    if tenant.spec.retrieval is not None and tenant.spec.retrieval.enabled:
        if tenant.store_path is None or not tenant.store_path.is_file():
            checks.append(
                {"check": "index", "ok": False, "detail": "索引库不存在（需要离线重建）"}
            )
        else:
            try:
                from retrieval.store import ChunkStore

                # create=False：readiness 只**探测**已有索引，不建库、不改任何东西。
                # initialize=False：连 DDL 都不跑；缺表会让 assert_integrity 抛错并如实报告。
                with ChunkStore(tenant.store_path, create=False, initialize=False) as store:
                    store.assert_integrity()
                    stats = store.stats()
                checks.append(
                    {
                        "check": "index",
                        "ok": True,
                        "detail": f"{stats.documents} 文档 / {stats.chunks} 片段",
                        "index_version": stats.index_version,
                    }
                )
            except Exception as error:  # noqa: BLE001 - 索引不可读就是不可服务
                checks.append(
                    {"check": "index", "ok": False, "detail": type(error).__name__}
                )
    else:
        checks.append({"check": "index", "ok": True, "detail": "该租户未启用检索"})

    if tenant.validation_root is not None:
        try:
            config = tenant.validators()
            checks.append(
                {
                    "check": "validators",
                    "ok": bool(config.registry.validators),
                    "detail": f"{len(config.registry.validators)} 个验证器声明",
                }
            )
        except ApiError as error:
            checks.append({"check": "validators", "ok": False, "detail": error.kind})
    else:
        # 没有声明验证器 = 该租户不提供"证据 + 判定"这一能力。这是**部署方的显式选择**：
        # 只要部署配置声明了 validators_available，readiness 就接受它；
        # 真正的失败关闭发生在调用时（validate 得到 validator_unavailable，不是 allow）。
        checks.append(
            {
                "check": "validators",
                "ok": bool(runtime.config.validators_available),
                "detail": "该租户未配置验证器；validate 会显式失败关闭（validator_unavailable）",
            }
        )

    if runtime.request_log.active:
        path = Path(runtime.request_log.path)  # type: ignore[arg-type]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            probe = path.with_name(path.name + ".probe")
            probe.write_text("", encoding="utf-8")
            probe.unlink()
            checks.append({"check": "audit_log", "ok": True, "detail": "可写"})
        except OSError:
            checks.append({"check": "audit_log", "ok": False, "detail": "观测日志不可写"})
    else:
        checks.append({"check": "audit_log", "ok": False, "detail": "观测日志未启用"})

    return {
        "tenant": tenant_id,
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }


def readiness_report(runtime: "ApiRuntime") -> Mapping[str, Any]:
    """全部租户的 readiness 汇总。"""

    tenants = [_check_tenant(runtime, tenant_id) for tenant_id in runtime.store.ids]
    errors = dict(runtime.store.errors)
    failed = [item["tenant"] for item in tenants if not item["ok"]]
    missing = sorted(errors)
    ready = not failed and not missing and bool(tenants)
    if ready:
        state = "ready"
        detail = f"{len(tenants)} 个租户可服务"
    elif tenants and len(failed) < len(tenants):
        state = "degraded"
        detail = "部分租户不可服务：" + ", ".join([*failed, *missing])
    else:
        state = "not_ready"
        detail = "没有可服务的租户：" + ", ".join([*failed, *missing]) or "未装配任何租户"
    return {
        "state": state,
        "ready": ready,
        "checked_at": _utc_now(),
        "tenants": tenants,
        "assembly_errors": errors,
        "detail": detail,
    }
