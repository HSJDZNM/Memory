"""Phase 7 Policy API 的传输契约：OpenAPI 快照、版本钉死、路由表与核心层边界。

契约测试与单元测试的区别：它守的是**跨进程、跨版本**的承诺。

- OpenAPI 快照是 Adapter 作者看到的全部真相，改它必须显式评审（`--write`），
  因此这里的断言是"零差异"，而不是"看起来差不多"；
- 传输协议版本（`API_SCHEMA_VERSION`）与决策协议版本（`policy.models.SCHEMA_VERSION`）
  是两套独立演进的东西，但后者只能**从核心取值**——API 层自己算一个版本，
  就等于让"同一份规则"有了两个名字（AGENTS 核心约束 7 与 31）；
- "核心层不依赖 Web 框架"必须是可执行的断言：它决定了`src/policy` 能否在没有
  FastAPI 的环境里独立运行，也是"API 只是传输边界"的唯一硬证据。

这里只用 ASGI 进程内调用（`make_client`），不起端口、不跑 uvicorn。
"""

from __future__ import annotations

import json
import re

import pytest

from conftest import REPO_ROOT

from policy import models as policy_models
from policy_api.config import ApiConfig, load_api_config
from policy_api.contract import (
    BUDGET_ROUTES,
    ENDPOINTS,
    openapi_document,
    self_check,
    snapshot_diff,
)
from policy_api.models import (
    API_SCHEMA_VERSION,
    DECISION_PAYLOAD_SCHEMA_VERSION,
    POLICY_GENERATION,
    SUPPORTED_API_SCHEMA_VERSIONS,
    ApiEnvelope,
    ContextDTO,
    EvaluateRequest,
    PrincipalDTO,
    RetrieveRequest,
    ValidationRequest,
)
from policy_api.runtime import ROUTES, ApiRuntime
from policy_api.testing import make_client

pytestmark = pytest.mark.contract

REPO_CONFIG = REPO_ROOT / "api" / "policy-api.yaml"
OPENAPI_SNAPSHOT = REPO_ROOT / "api" / "openapi.json"

# 核心层禁止出现的依赖：任何一条都会把"能独立运行的核心"变成"必须先装 Web 栈"。
FORBIDDEN_IMPORTS = ("fastapi", "starlette", "uvicorn", "httpx", "requests", "flask")
CORE_LAYERS = ("policy", "retrieval", "validators", "enforcement")
_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(" + "|".join(FORBIDDEN_IMPORTS) + r")\b", re.MULTILINE
)


@pytest.fixture(scope="module")
def runtime() -> ApiRuntime:
    """按仓库自己的部署配置装配运行时（与 CI 里的 `policy_api.cli` 走同一条路）。"""

    config = load_api_config(REPO_CONFIG, root=REPO_ROOT)
    return ApiRuntime(config, root=REPO_ROOT)


def test_openapi_snapshot_matches_the_application(runtime: ApiRuntime) -> None:
    """OpenAPI 快照与当前应用**零差异**：这是 CI 门禁，不是提示。

    快照是 Adapter 作者与客户端唯一的协议来源；允许它悄悄漂移，就等于允许线上协议悄悄变。
    差异必须由人显式更新：`python -m policy_api.cli openapi --write`。
    """

    assert OPENAPI_SNAPSHOT.is_file(), "契约快照必须被提交"
    diff = snapshot_diff(OPENAPI_SNAPSHOT, openapi_document(runtime))
    assert diff == (), (
        "OpenAPI 快照与当前应用不一致（改协议后用 python -m policy_api.cli openapi --write 显式更新）："
        + json.dumps(list(diff), ensure_ascii=False)
    )


def test_self_check_passes_on_the_repo_config(runtime: ApiRuntime) -> None:
    """自检必须绿：它同时覆盖配置、租户装配、readiness 与传输契约。

    任何一项失败都意味着"这份配置在今天不能安全提供服务"，而不是"少个可选字段"。
    """

    report = self_check(runtime)
    failed = [item for item in report["checks"] if not item["ok"]]
    assert report["ok"] is True, json.dumps(failed, ensure_ascii=False)
    assert report["tenants"] == ["fixture-shop", "local-dev"]
    assert report["readiness"]["state"] == "ready"


def test_transport_version_is_pinned_on_the_envelope_only() -> None:
    """`api_version` 只出现在信封上，且默认就是当前版本。

    ContextDTO / PrincipalDTO 是**载荷** DTO：它们多一个版本字段就会多一个"到底以谁为准"的歧义。
    """

    assert API_SCHEMA_VERSION == "1.0"
    assert SUPPORTED_API_SCHEMA_VERSIONS == frozenset({"1.0"})

    envelopes = (ApiEnvelope, EvaluateRequest, RetrieveRequest, ValidationRequest)
    for model in envelopes:
        assert model.model_fields["api_version"].default == "1.0"
    for model in (ContextDTO, PrincipalDTO):
        assert "api_version" not in model.model_fields
        assert "schema_version" not in model.model_fields
    # 三个具体请求类必须都是信封的子类：横切关注点（认证/幂等/预算）在每条路由上同形。
    for model in (EvaluateRequest, RetrieveRequest, ValidationRequest):
        assert issubclass(model, ApiEnvelope)
    # 两套名字刻意不同，这里把差异钉死（不是"差不多就行"）：
    # ENDPOINTS 的 (URL, name) 里，name 是**应用路由名**（也是 operationId 的来源），
    # 健康检查因此叫 live / ready；而运行时把这两条探针归到 health / readiness 两个概念下，
    # 因为它们是"不经过 handle()"的运维探针，不参与台账与指标键。
    # 真正共享同一套键的是四条**受治理**路由：它们决定幂等台账、指标与错误分类。
    governed = {"evaluate", "retrieve", "validate", "metrics"}
    assert governed <= {name for _, name in ENDPOINTS}
    assert governed <= set(ROUTES)
    assert {name for _, name in ENDPOINTS} - governed == {"live", "ready"}
    assert set(ROUTES) - governed == {"health", "readiness"}


def test_decision_payload_versions_come_from_the_core() -> None:
    """决策协议版本与世代名只能来自核心：API 不许自己算一个。

    这条断言是"曾经出现过证据说 phase-5、载荷说 phase-1"那类事故的回归测试。
    """

    assert DECISION_PAYLOAD_SCHEMA_VERSION == policy_models.SCHEMA_VERSION
    assert POLICY_GENERATION == policy_models.POLICY_VERSION


def test_openapi_info_pins_the_three_versions(runtime: ApiRuntime) -> None:
    """文档里必须能一眼看出这份 API 说的是哪套协议、跑的是哪一代策略。"""

    info = openapi_document(runtime)["info"]
    assert info["x-api-schema-version"] == API_SCHEMA_VERSION
    assert info["x-decision-schema-version"] == policy_models.SCHEMA_VERSION
    assert info["x-policy-generation"] == policy_models.POLICY_VERSION


@pytest.mark.parametrize("layer", CORE_LAYERS)
def test_core_layers_do_not_import_web_frameworks(layer: str) -> None:
    """核心层（规则 / 检索 / 验证器 / 受控执行）不得依赖 Web 框架。

    用源码文本而不是导入图：这条边界要能被"读代码的人"直接看到，
    也必须能在没有安装 FastAPI 的环境里成立。
    """

    root = REPO_ROOT / "src" / layer
    assert root.is_dir()
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        match = _IMPORT_RE.search(path.read_text(encoding="utf-8"))
        if match:
            offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {match.group(1)}")
    assert offenders == [], "核心层出现了 Web 框架依赖：" + ", ".join(offenders)


def test_app_routes_match_contract_endpoints(runtime: ApiRuntime) -> None:
    """`create_app` 暴露的路由与 `contract.ENDPOINTS` 一一对应（6 条，不多不少）。

    路由表是幂等键、指标键与错误分类的共同基础：多一条未登记的路由 =
    多一条没人测过、也没进指标口径的入口。
    """

    app = make_client(runtime).app
    declared = dict(ENDPOINTS)
    served = {
        route.path: route.name
        for route in app.routes
        if getattr(route, "name", None) in set(declared.values())
    }
    assert served == declared
    assert len(served) == 6

    methods = {
        route.path: set(route.methods)
        for route in app.routes
        if getattr(route, "name", None) in set(declared.values())
    }
    for path in ("/v1/policy/evaluate", "/v1/knowledge/retrieve", "/v1/validation/evaluate"):
        assert methods[path] == {"POST"}
    for path in ("/v1/health/live", "/v1/health/ready", "/v1/ops/metrics"):
        assert methods[path] == {"GET"}


def test_health_live_payload_has_fixed_top_level_keys(runtime: ApiRuntime) -> None:
    """存活探针的形状固定：编排系统与监控都按这几个键写表达式。

    它**不碰**规则集、索引与日志——"没有规则可服务"的进程仍然是活着的进程，
    那是 readiness 要回答的问题。
    """

    response = make_client(runtime).get("/v1/health/live")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"api_version", "status", "service", "deployment"}
    assert payload["api_version"] == API_SCHEMA_VERSION
    assert payload["status"] == "live"
    assert payload["service"] == runtime.config.service_name
    assert payload["deployment"] == runtime.config.deployment


def test_every_budget_route_is_a_declared_route_with_a_configured_budget() -> None:
    """"有预算的路由"必须是真实路由，并且配置里真的有对应预算字段。

    否则要么出现"没有上限的路由"，要么出现"配了却没人用"的预算——
    两种都会让超时语义在运维眼里变得不可信。
    """

    config: ApiConfig = load_api_config(REPO_CONFIG, root=REPO_ROOT)
    assert set(BUDGET_ROUTES) <= set(ROUTES)
    for route in BUDGET_ROUTES:
        assert f"{route}_ms" in ApiConfig.model_fields["budgets"].annotation.model_fields
        assert getattr(config.budgets, f"{route}_ms") > 0
