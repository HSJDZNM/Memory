"""Phase 7 Policy API 的 HTTP 集成测试：真实 ASGI、真实规则集、真实索引、真实验证器流水线。

为什么是这一层：单元测试证明"契约对象的行为"，契约测试证明"文档与边界"，
但**只有把请求真的发进 ASGI 栈**才能证明"经 API 的判定与本地 SDK 是同一个结论"。
这里用 `policy_api.testing.make_client`（httpx 的 ASGI 传输，进程内、无端口、无 uvicorn），
因此"真实"与"快"不冲突。

每个用例都在验证一条具体的安全/正确性主张，注释写的是"为什么必须这样"。
"""

from __future__ import annotations

import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping

import pytest

from conftest import REPO_ROOT, write_fixture_corpus

from policy.context import build_context
from policy.engine import evaluate
from policy import models as policy_models
from policy.loader import load_rule_set
from policy_api.config import LoadConfig, RateLimitConfig, load_api_config
from policy_api.runtime import ApiRuntime
from policy_api.testing import make_client
from retrieval.corpus import load_corpus
from retrieval.indexer import ingest
from retrieval.store import ChunkStore

from api_support import OPS_TOKEN, TOKEN, TOKEN2, TOKEN_SHA, isolated_api

pytestmark = pytest.mark.integration

API_RULES = REPO_ROOT / "tests" / "fixtures" / "api" / "rules"

# 请求上下文原型：文件对应租户项目里的 src/shop/order_controller.py。
# 两个变体只差 dependencies：一个好的 controller 与一个直连 repository 的 controller。
GOOD_CONTEXT: dict[str, Any] = {
    "file": "src/shop/order_controller.py",
    "layer": "controller",
    "language": "python",
    "dependencies": ["service"],
}
BAD_CONTEXT: dict[str, Any] = {**GOOD_CONTEXT, "dependencies": ["repository"]}


# --------------------------------------------------------------------------- 夹具


def build_api(
    tmp_root: Path,
    *,
    relaxed_rate_limit: bool = True,
    limit_overrides: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> tuple[ApiRuntime, Any, Path]:
    """装配一套隔离的 API，返回 `(runtime, ASGI 客户端, 配置文件)`。

    `readiness_ttl_seconds=0`：readiness 有 1s 缓存，而"规则目录被删掉后必须立刻变成
    not_ready"的用例不能靠 sleep 去等缓存过期——探针路由本身也要被测。

    `relaxed_rate_limit=True`：模板里的桶是 5 个请求（限流本身由
    `test_rate_limit_exhausts_bucket` 单独验证）。本文件多数用例要发十几个请求来区分
    错误码，被 429 掩盖的 400 会让断言说谎——那是"测试环境没摆对"，不是被测行为。

    `limit_overrides`：逐字段覆盖模板里的 `limits`（例如把 `max_concurrency` 压到 1）。
    覆盖值用 `LoadConfig(...)` **重新构造**而不是 `model_copy`：配置即边界，越界的覆盖值
    （如 0 / 257）必须在装配处就被 pydantic 拒绝，否则用例会拿着一份"看起来生效、
    其实非法"的配置去断言。默认 None = 一个字段都不动。
    """

    config_path, anchor = isolated_api(tmp_root, **kwargs)
    config = load_api_config(config_path, root=anchor)
    if relaxed_rate_limit:
        config = config.model_copy(
            update={"rate_limit": RateLimitConfig(capacity=1000, refill_per_second=1000.0)}
        )
    if limit_overrides:
        # 逐字段覆盖 + 重新校验（见 docstring）：LoadConfig 的 ge/le 在构造时就生效。
        limits = LoadConfig(**{**config.limits.model_dump(), **limit_overrides})
        config = config.model_copy(update={"limits": limits})
    runtime = ApiRuntime(config, root=anchor, readiness_ttl_seconds=0.0)
    return runtime, make_client(runtime), config_path


def auth(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def envelope(request_id: str, *, tenant: str = "alpha", context: Mapping[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    """请求信封：所有 POST 路由共用的形状（api_version / request_id / 主体 / 上下文）。"""

    body: dict[str, Any] = {
        "api_version": "1.0",
        "request_id": request_id,
        "tenant": tenant,
        "principal": {"subject": "alice", "roles": ["developer"]},
        "context": dict(GOOD_CONTEXT if context is None else context),
    }
    body.update(extra)
    return body


def error_code(response: Any) -> str:
    return response.json()["error"]["code"]


def index_fixture(tmp_root: Path) -> tuple[Path, Path]:
    """为检索用例建一份**真实索引**，返回 `(语料根, 索引库)`。

    用 Phase 3 的夹具语料与真实摄取流水线（`load_corpus` + `ingest`），
    因为"检索命中"这件事只有真索引才能证明：空索引、假命中都会让用例看起来是绿的。
    """

    corpus_root = tmp_root / "corpus"
    db = tmp_root / "index" / "retrieval.sqlite3"
    loaded = load_corpus(write_fixture_corpus(corpus_root), repo_root=corpus_root)
    with ChunkStore(db) as store:
        report = ingest(loaded, store, repo_root=corpus_root)
    assert report.documents_indexed == len(loaded.entries)
    assert report.chunks_created > 0
    return corpus_root, db


# --------------------------------------------------------------------------- 判定


def test_evaluate_decision_payload_equals_the_core_engine_result(tmp_root: Path) -> None:
    """**同一个上下文 + 同一份规则**：经 API 的决策载荷与本地 `policy.engine.evaluate` **整份相等**。

    比的是 JSON **值**，不是两侧各自序列化出来的字节：本地是领域对象 `to_decision_dict()`、
    线上是响应载荷，两者的序列化入口不同，字段顺序不属于契约（带 idempotency_key 的请求
    还会被 `_canonical_body` 规范化成字母序）。

    这是"API 是传输边界，不是第二份业务逻辑"（AGENTS 核心约束 30）唯一的硬证据：
    如果 API 层自己拼了一份决策、或漏传/改写了上下文字段，这里就会出现差异。
    """

    runtime, client, _ = build_api(tmp_root)
    request_id, trace_id = "it-evaluate-1", "trace-1"
    response = client.post(
        "/v1/policy/evaluate",
        headers=auth(),
        json=envelope(request_id, context=BAD_CONTEXT, trace_id=trace_id),
    )
    assert response.status_code == 200
    body = response.json()
    decision = body["decision"]

    assert set(decision) == {
        "schema_version",
        "decision",
        "request_id",
        "trace_id",
        "rule_set_hash",
        "matched_rules",
        "skipped_rules",
        "violations",
        "required_action",
        "policy_version",
    }
    assert decision["schema_version"] == "1.0"
    assert decision["request_id"] == request_id and decision["trace_id"] == trace_id
    assert decision["decision"] == "block"
    assert body["tenant"] == "alpha"
    assert body["summary"]["decision"] == decision["decision"]
    assert body["summary"]["violations"] == len(decision["violations"]) == 1
    assert body["rule_set"]["hash"] == decision["rule_set_hash"]
    assert body["rule_set"]["hash"].startswith("sha256:")
    assert body["rule_set"]["identity"] == ["ARCH-001@1"]
    # 传输层**不改写**决策协议：世代名同样来自核心。
    assert body["policy_version"] == policy_models.POLICY_VERSION
    assert body["generation"] == policy_models.POLICY_VERSION
    assert body["timing"]["budget_ms"] == 2000

    project = tmp_root / "project"
    local_rules = load_rule_set([project / "rules"], repo_root=project)
    local_context = build_context(
        {
            "request_id": request_id,
            "trace_id": trace_id,
            "file": GOOD_CONTEXT["file"],
            "layer": "controller",
            "language": "python",
            "dependencies": ["repository"],
        },
        repo_root=project,
    )
    local = evaluate(local_rules, local_context)
    assert local_rules.identity == body["rule_set"]["hash"]
    assert local.to_decision_dict() == decision
    # 再比一次两侧**规范化序列化**后的字符串：它与上面的 == 等价，额外钉住"载荷必须可 JSON 序列化"。
    assert json.dumps(local.to_decision_dict(), sort_keys=True) == json.dumps(decision, sort_keys=True)


def test_two_clients_get_the_same_decision_for_the_same_context(tmp_root: Path) -> None:
    """不同客户端/令牌对**同一个上下文**得到同一个决策。

    判定只取决于"规则集 + 上下文"：客户端身份进入的是审计与授权，
    绝不能成为决策的输入（否则"同一份规则"就有了两个版本）。
    """

    runtime, client, _ = build_api(tmp_root)
    request_id = "it-agree"
    first = client.post("/v1/policy/evaluate", headers=auth(TOKEN), json=envelope(request_id, context=BAD_CONTEXT))
    second = client.post(
        "/v1/policy/evaluate",
        headers=auth(TOKEN2),
        json=envelope(request_id, context=BAD_CONTEXT),
    )
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["tenant"] == second.json()["tenant"] == "alpha"
    assert first.json()["decision"] == second.json()["decision"]
    assert first.json()["rule_set"]["hash"] == second.json()["rule_set"]["hash"]
    # 两个请求确实来自不同客户端（不是"同一个客户端发了两次"）。
    assert first.json()["decision"]["request_id"] == second.json()["decision"]["request_id"] == request_id


def test_extra_rule_pack_is_loaded_and_evidence_rules_are_skipped_not_passed(tmp_root: Path) -> None:
    """额外规则包真的进了规则集；而"需要验证器证据"的规则在只有上下文的调用路径上**显式记进 skipped_rules**。

    这是"API 路径不得把 skipped 当成通过"（AGENTS 核心约束 23）的接口级证据：
    结论是 allow，但 `matched == 0`、skipped 里写明原因，客户端与审计都能看出"这条规则没被判"。
    """

    runtime, client, _ = build_api(tmp_root, extra_rules=(API_RULES,))
    assert dict(runtime.store.errors) == {}
    response = client.post(
        "/v1/policy/evaluate",
        headers=auth(),
        json=envelope(
            "it-extra-rules",
            context={"file": "src/shop/order_service.py", "layer": "service", "language": "python"},
            include_evidence=True,
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["rule_set"]["identity"] == ["API-001@1", "ARCH-001@1"]
    assert body["summary"]["decision"] == "allow"
    assert body["summary"]["matched"] == 0
    assert body["summary"]["skipped"] == 2
    skipped = {item["rule_id"]: item["reasons"] for item in body["skipped_rules"]}
    assert "需要验证器证据" in " ".join(skipped["API-001@1"])
    assert "layer service != controller" in " ".join(skipped["ARCH-001@1"])


# --------------------------------------------------------------------------- 协议错误


def test_unknown_field_is_rejected(tmp_root: Path) -> None:
    """未知字段报错而不是忽略：客户端拼错字段名必须能被发现（否则会静默用默认值判定）。"""

    runtime, client, _ = build_api(tmp_root)
    response = client.post(
        "/v1/policy/evaluate", headers=auth(), json={**envelope("it-unknown"), "evil": 1}
    )
    assert response.status_code == 400
    assert error_code(response) == "body_invalid"
    assert "evil" in response.json()["error"]["detail"]


def test_api_version_must_be_present_and_known(tmp_root: Path) -> None:
    """版本字段必须显式出现，且未知版本拒绝：`缺失` 与 `不支持` 是两个可区分的错误。"""

    runtime, client, _ = build_api(tmp_root)
    payload = envelope("it-version")
    payload.pop("api_version")
    missing = client.post("/v1/policy/evaluate", headers=auth(), json=payload)
    assert missing.status_code == 400
    assert error_code(missing) == "schema_version_missing"

    unknown = client.post(
        "/v1/policy/evaluate", headers=auth(), json={**envelope("it-version"), "api_version": "9.9"}
    )
    assert unknown.status_code == 400
    assert error_code(unknown) == "schema_version_unknown"
    assert "9.9" in unknown.json()["error"]["detail"]


def test_malformed_json_is_rejected(tmp_root: Path) -> None:
    """坏 JSON 是 400 body_invalid，不是 500：解析失败也要落在受控错误码里。"""

    runtime, client, _ = build_api(tmp_root)
    response = client.post(
        "/v1/policy/evaluate",
        headers={**auth(), "Content-Type": "application/json"},
        content=b"{not json",
    )
    assert response.status_code == 400
    assert error_code(response) == "body_invalid"


def test_non_json_content_type_is_rejected_with_415(tmp_root: Path) -> None:
    """非 JSON 的 Content-Type 必须被拒成 415 unsupported_media_type（不是 body_invalid）。

    "请求体不是 JSON 媒体类型"与"请求体内容不合法"是两类失败：前者该由传输层在**解析之前**
    回答，后者才轮到 DTO。`app._body_guard` 依赖因此在框架解析请求体之前就把字节读出来，
    否则这段检查会被框架的校验抢先，415（以及 413）这类传输层错误永远没有机会出现
    ——这条曾经真实发生过：三个 POST 路由的 handler 声明了请求体模型，
    于是 `Content-Type: text/plain` 得到的是框架的 400 body_invalid。
    """

    runtime, client, _ = build_api(tmp_root)
    posted = client.post(
        "/v1/knowledge/retrieve",
        headers={**auth(), "Content-Type": "text/plain"},
        content=json.dumps(envelope("it-content-type")).encode("utf-8"),
    )
    assert posted.status_code == 415
    assert error_code(posted) == "unsupported_media_type"

    # 运维路由（GET，没有请求体模型）走的是同一个检查：媒体类型不是 JSON 一样被拒。
    ops = client.get(
        "/v1/ops/metrics",
        headers={"Authorization": f"Bearer {OPS_TOKEN}", "Content-Type": "text/plain"},
    )
    assert ops.status_code == 415
    assert error_code(ops) == "unsupported_media_type"


def test_oversized_body_is_rejected_with_413(tmp_root: Path) -> None:
    """请求体上限是**真的上限**：贴着上限的请求要能过，超过一个字节就 413。

    注意两层上限是**独立**的：这里测的是整个请求体的字节数（由依赖在框架解析之前读，
    见 `_body_guard`）；单个上下文字段的上限是另一条检查（下一个用例）。
    """

    runtime, client, _ = build_api(tmp_root)
    limit = runtime.config.limits.max_request_bytes
    context_limit = runtime.config.limits.max_context_bytes

    # 规模可观但仍在两层上限之内：判定照常进行（上限不是"稍大就拒"）。
    # 夹具里字段上限（32KB）天然小于请求体上限（64KB），因此"贴着请求体上限"只能靠
    # 大体量字段，而它会先撞字段上限——两条检查的先后关系由下一个用例钉住。
    padding = context_limit - 64  # 字段本身留一点余量（"x" 长度就是字段字节数）
    padded = envelope("it-size-ok", context={**GOOD_CONTEXT, "git_diff": "x" * padding})
    size = len(json.dumps(padded).encode("utf-8"))
    assert limit > size > context_limit - 1024
    accepted = client.post("/v1/policy/evaluate", headers=auth(), json=padded)
    assert accepted.status_code == 200

    # 超一个字节：裸请求体把总长度顶过上限（字段都小，走的是请求体这条检查）。
    oversized = client.post(
        "/v1/policy/evaluate",
        headers={**auth(), "Content-Type": "application/json"},
        content=b'{"pad":"' + b"x" * limit + b'"}',
    )
    assert oversized.status_code == 413
    assert error_code(oversized) == "body_too_large"


def test_oversized_context_field_is_rejected_with_413(tmp_root: Path) -> None:
    """单个上下文维度也有自己的上限：请求体不超，字段超了同样 413。

    "请求体不超过 X"只描述了一次传输；真正的风险是**单个字段**被撑爆
    （10MB 的 git_diff 会写进判定、证据与日志）。逐字段的检查因此也必须存在，
    而且必须是失败关闭，不是"截断成看起来完整的证据"。
    """

    runtime, client, _ = build_api(tmp_root)
    context_limit = runtime.config.limits.max_context_bytes
    payload = envelope(
        "it-context-size", context={**GOOD_CONTEXT, "git_diff": "x" * (context_limit + 16)}
    )
    assert len(json.dumps(payload).encode("utf-8")) < runtime.config.limits.max_request_bytes
    response = client.post("/v1/policy/evaluate", headers=auth(), json=payload)
    assert response.status_code == 413
    assert error_code(response) == "body_too_large"
    assert "git_diff" in response.json()["error"]["detail"]
def test_missing_layer_is_rejected(tmp_root: Path) -> None:
    """缺少 layer（安全关键维度）必须被拒，绝不能"推不出来就当作无限制"。

    实测（真实行为）：缺少 `context.layer` 得到的是 **400 body_invalid**，而不是任务书里
    期望的 context_invalid——`ContextDTO.layer` 是必填字段，DTO 校验（唯一校验点）先于
    `build_context` 失败。两者都是 400 且都失败关闭，但错误码指向的修复动作不同：
    body_invalid 是"请求体字段不合法"，context_invalid 才是"上下文语义不合法"。
    这条偏差记录进测试报告，而不在断言里放宽：缺失安全关键维度必须失败，这一点没有分歧。
    """

    runtime, client, _ = build_api(tmp_root)
    payload = envelope("it-layer", context={"file": "src/shop/order_controller.py", "language": "python"})
    response = client.post("/v1/policy/evaluate", headers=auth(), json=payload)
    assert response.status_code == 400
    assert error_code(response) == "body_invalid"  # 偏差：任务书期望 context_invalid
    assert "layer" in response.json()["error"]["detail"]


def test_unknown_route_and_method_have_explicit_codes(tmp_root: Path) -> None:
    """未知路径 404 not_found、方法不对 405 method_not_allowed：都由错误码枚举给出。"""

    runtime, client, _ = build_api(tmp_root)
    missing = client.get("/v1/does-not-exist")
    assert missing.status_code == 404
    assert error_code(missing) == "not_found"

    wrong_method = client.get("/v1/policy/evaluate")
    assert wrong_method.status_code == 405
    assert error_code(wrong_method) == "method_not_allowed"


# --------------------------------------------------------------------------- 限流与幂等


def test_rate_limit_exhausts_bucket_and_returns_429(tmp_root: Path) -> None:
    """配额（capacity=5, refill=0.001/s）耗尽后返回 429 rate_limited。

    用**模板原样的配置**（不放松限流）：这条用例证明的正是"调用方不能无限压服务"。
    """

    runtime, client, _ = build_api(tmp_root, relaxed_rate_limit=False)
    statuses = []
    for index in range(6):
        response = client.post(
            "/v1/policy/evaluate",
            headers=auth(),
            json=envelope(f"it-rate-{index}", context=BAD_CONTEXT),
        )
        statuses.append(response.status_code)
    assert statuses == [200, 200, 200, 200, 200, 429]
    assert error_code(response) == "rate_limited"
    assert response.json()["error"]["retryable"] is True
    # 与 503 同一路径：限流也是在 _authenticate 内部抛的，错误响应同样必须带 request_id。
    assert response.json()["error"]["request_id"] == "it-rate-5"
    assert runtime.metrics.to_payload()["rate_limited"] == 1


def test_idempotency_replays_the_stored_response_and_conflicts_on_other_bodies(tmp_root: Path) -> None:
    """同一个 `idempotency_key`：同请求体 → 原响应 + `Idempotency-Replayed`；不同请求体 → 409。

    重试是客户端的天性：没有这条约束，"重试一次判定"就会变成"重算一次"，
    而两次判定之间的规则集可能已经变了。
    """

    runtime, client, _ = build_api(tmp_root)
    payload = envelope("it-idempotent", context=BAD_CONTEXT)
    first = client.post(
        "/v1/policy/evaluate", headers=auth(), json={**payload, "idempotency_key": "key-1"}
    )
    assert first.status_code == 200
    assert "Idempotency-Replayed" not in first.headers

    replayed = client.post(
        "/v1/policy/evaluate", headers=auth(), json={**payload, "idempotency_key": "key-1"}
    )
    assert replayed.status_code == 200
    assert replayed.headers["Idempotency-Replayed"] == "true"
    assert replayed.json() == first.json()
    # **逐字节**相同：独立验证者曾发现"重放只是语义相同、字节不同"（台账写入时按
    # sort_keys 规范化，回读后键序变了）。现在带幂等键的响应统一按规范化键序返回，
    # 于是"这次响应和上次一样吗"可以用字节回答。
    assert replayed.content == first.content

    conflict = client.post(
        "/v1/policy/evaluate",
        headers=auth(),
        json={**envelope("it-idempotent", context=GOOD_CONTEXT), "idempotency_key": "key-1"},
    )
    assert conflict.status_code == 409
    assert error_code(conflict) == "idempotency_key_conflict"

    assert [row["replayed"] for row in runtime.request_log.read_back()] == [False, True, False]


# --------------------------------------------------------------------------- readiness


def test_readiness_goes_not_ready_when_the_rule_directory_disappears(tmp_root: Path) -> None:
    """规则目录被删掉：readiness 立刻 503 not_ready，evaluate 得到 503 rule_set_unavailable。

    这是"没有规则 = 全部放行"的反例：`ApiRuntime` 拒绝用空规则集继续服务，
    而 readiness 把"某个租户装不上"当成必须被看见的事实（而不是启动日志里的一行警告）。
    """

    runtime, client, _ = build_api(tmp_root)
    ready = client.get("/v1/health/ready")
    assert ready.status_code == 200
    assert ready.json()["state"] == "ready"

    shutil.rmtree(tmp_root / "project" / "rules")

    degraded = client.get("/v1/health/ready")
    assert degraded.status_code == 503
    report = degraded.json()
    assert report["state"] == "not_ready"
    assert report["ready"] is False
    # 租户**装配**是成功的（目录当时还在），失败发生在"加载规则集"这一步：
    # 两个错误必须能被分开看，否则运维分不清"配置写错了"还是"文件被删了"。
    assert report["assembly_errors"] == {}
    checks = {item["tenant"]: item for item in report["tenants"]}
    assert checks["alpha"]["ok"] is False and checks["beta"]["ok"] is False
    alpha_checks = {check["check"]: check for check in checks["alpha"]["checks"]}
    assert alpha_checks["rule_set"]["ok"] is False
    assert alpha_checks["rule_set"]["detail"] == "rule_set_unavailable"

    blocked = client.post("/v1/policy/evaluate", headers=auth(), json=envelope("it-no-rules"))
    assert blocked.status_code == 503
    assert error_code(blocked) == "rule_set_unavailable"


# --------------------------------------------------------------------------- 观测


def test_request_log_records_the_decision_without_any_token(tmp_root: Path) -> None:
    """判定被记进 JSONL：request_id / 租户 / 客户端 / 决策 / 规则集哈希都在，令牌明文不在。

    "决定记不下来就不返回决定"是失败关闭；这条用例证明**记下来了**，并且记的是摘要而不是凭据。
    """

    runtime, client, _ = build_api(tmp_root)
    response = client.post(
        "/v1/policy/evaluate", headers=auth(), json=envelope("it-log-1", context=BAD_CONTEXT)
    )
    assert response.status_code == 200

    rows = runtime.request_log.read_back()
    assert len(rows) == 1
    row = rows[0]
    assert row["request_id"] == "it-log-1"
    assert row["route"] == "evaluate" and row["status"] == 200 and row["outcome"] == "ok"
    assert row["tenant"] == "alpha" and row["client_id"] == "alpha-client"
    assert row["decision"] == "block" and row["violations"] == 1
    assert row["rule_set_hash"] == response.json()["rule_set"]["hash"]
    assert row["token_ref"] == TOKEN_SHA[:12]
    assert row["replayed"] is False

    text = runtime.request_log.path.read_text(encoding="utf-8")
    assert "alpha-secret-token" not in text
    assert str(REPO_ROOT) not in text


# --------------------------------------------------------------------------- 检索


def test_retrieve_returns_cited_hits_from_a_real_index(tmp_root: Path) -> None:
    """真实索引上的检索：命中带来源路径 / 许可 / 文本哈希，Context 里带引用列表。

    "命中"这件事只有真索引能证明；引用字段是**授权与追溯的最小集**——
    没有来源与哈希的片段等于让模型凭记忆说话（AGENTS 核心约束 11）。
    """

    corpus_root, db = index_fixture(tmp_root)
    runtime, client, _ = build_api(tmp_root, corpus_root=corpus_root, db=db)
    response = client.post(
        "/v1/knowledge/retrieve",
        headers=auth(),
        json={
            "api_version": "1.0",
            "request_id": "it-retrieve-1",
            "tenant": "alpha",
            "principal": {"subject": "alice"},
            # 检索同样必须显式声明上下文：文件/层级不是服务端能猜的东西，
            # 而查询计划正是从这些显式字段（外加自由文本）构造出来的。
            "context": dict(GOOD_CONTEXT),
            "query": "guide",
            "limit": 3,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["method"] == "fts5"
    assert body["available"] is True

    hits = body["hits"]
    assert len(hits) >= 1
    assert any(hit["dataset"] == "guides" for hit in hits)
    for hit in hits:
        assert hit["text_hash"].startswith("sha256:")
        assert hit["license"]
        assert hit["source_path"] and hit["source_url"]
        assert hit["citation"] == f"[{hit['chunk_id']}]"
        assert hit["citation_source"].startswith(hit["source_path"])

    context = body["context"]
    assert context["citations"], "Context 必须给出引用列表"
    assert context["citation_count"] == len(context["citations"])
    assert body["index"]["index_version"]
    # 夹具语料是 4 篇文档；limit=3 只是把这 13 个片段里的前 3 条还给调用方，
    # 因此"索引里有多少片段"必须比"这次返回了几条"大——否则 limit 根本没生效。
    assert body["index"]["documents"] == 4
    assert body["index"]["chunks"] > len(hits) == 3


def test_retrieve_rejects_a_decision_ref_the_service_never_computed(tmp_root: Path) -> None:
    """`decision_ref` 只能指向**本服务算过的** request_id：客户端不能自带决策给自己扩权。"""

    corpus_root, db = index_fixture(tmp_root)
    runtime, client, _ = build_api(tmp_root, corpus_root=corpus_root, db=db)
    response = client.post(
        "/v1/knowledge/retrieve",
        headers=auth(),
        json={
            "api_version": "1.0",
            "request_id": "it-retrieve-forged",
            "tenant": "alpha",
            "principal": {"subject": "alice"},
            "context": dict(GOOD_CONTEXT),
            "query": "guide",
            "decision_ref": "never-computed-by-this-service",
        },
    )
    assert response.status_code == 403
    assert error_code(response) == "forbidden"


def test_retrieve_fails_closed_when_the_index_file_disappears(tmp_root: Path) -> None:
    """索引文件被删掉后必须失败关闭：503 `knowledge_unavailable`。

    这条曾经是**真实缺陷**（独立验证者发现）：`ChunkStore(path)` 默认 `create=True`，
    文件缺失会被重新建成一个空库，于是返回 200 + `status=empty / reason=no_results`
    ——"索引没了"被报成"查询没有命中"，客户端会以为自己真查过一遍。
    现在打开索引用 `create=False`（索引是构建产物，服务只读它），缺失即 503。
    """

    corpus_root, db = index_fixture(tmp_root)
    runtime, client, _ = build_api(tmp_root, corpus_root=corpus_root, db=db)
    payload = {
        "api_version": "1.0",
        "request_id": "it-retrieve-missing-index",
        "tenant": "alpha",
        "principal": {"subject": "alice"},
        "context": dict(GOOD_CONTEXT),
        "query": "guide",
        "limit": 3,
    }
    assert client.post("/v1/knowledge/retrieve", headers=auth(), json=payload).json()["status"] == "ok"

    db.unlink()
    response = client.post("/v1/knowledge/retrieve", headers=auth(), json=payload)
    assert response.status_code == 503
    assert error_code(response) == "knowledge_unavailable"
    assert response.json()["error"]["retryable"] is True
    # 重建命令写在 detail 里：这是调用方唯一能做的修复动作。
    assert "retrieval.cli index" in response.json()["error"]["detail"]


# --------------------------------------------------------------------------- 验证器


def test_validate_runs_the_real_pipeline_and_returns_a_decision(tmp_root: Path) -> None:
    """验证路由跑**真流水线**：报告带 schema_version、依赖事实与 served_checkers，判定一并给出。

    验证器只产证据、不判定：allow 仍然由 `policy.engine.evaluate(..., evidence=...)` 给出，
    因此这里同时断言"报告有证据"与"决策有结论"。
    """

    runtime, client, _ = build_api(tmp_root)
    response = client.post(
        "/v1/validation/evaluate", headers=auth(), json=envelope("it-validate-1")
    )
    assert response.status_code == 200
    body = response.json()
    report = body["report"]
    assert report["schema_version"] == "1.0"
    assert report["target"]["file"] == "src/shop/order_controller.py"
    assert report["served_checkers"] == ["forbidden_dependency"]
    # 记录里的身份字段是 `validator`（形如 py.depgraph@1.0）：证据必须能追到"谁产的"。
    assert [item["validator"] for item in report["validators"]] == [
        "py.ast@1.0",
        "py.depgraph@1.0",
        "py.source@1.0",
    ]
    assert all(item["status"] == "ok" for item in report["validators"])
    assert all(item["critical"] is True for item in report["validators"])
    assert {fact["name"] for fact in report["dependencies"]} == {"service"}
    assert body["blockers"] == []
    assert body["truncated_evidence"] == 0
    assert body["decision"]["decision"] == "allow"
    assert body["summary"]["decision"] == "allow"
    assert body["decision"]["request_id"] == "it-validate-1"


def test_validate_fails_closed_for_a_tenant_without_validators(tmp_root: Path) -> None:
    """没有声明 validation_root 的租户：validate 得到 503 validator_unavailable，不是 allow。"""

    runtime, client, _ = build_api(tmp_root)
    response = client.post(
        "/v1/validation/evaluate",
        headers=auth(TOKEN2),
        json=envelope("it-validate-beta", tenant="beta"),
    )
    assert response.status_code == 503
    assert error_code(response) == "validator_unavailable"
    assert "beta" in response.json()["error"]["detail"]


# --------------------------------------------------------------------------- 并发闸门


def test_concurrency_gate_limits_in_flight_requests(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """一个真实请求仍在处理时，后到请求拿到 **503 policy_busy**。

    为什么必须这样：`max_concurrency`（`config.LoadConfig`）约束的是"同时在处理中的请求数"。
    慢调用方把许可占满时服务必须失败关闭——排队会让所有调用方一起变慢，把墙钟预算变成
    空头承诺；而"照样处理"更糟：调用方会把失败读成一次结论（AGENTS 核心约束 33）。
    因此 `policy_busy` + `retryable=True` 是协议的一部分，状态码由 `STATUS_BY_CODE` 推导
    （503），调用方据此知道"这次没有结论、可以重试"。

    首个请求进入真实策略评估后由事件闸门暂停；第二个请求从同一个 ASGI 入口进入，必须在
    首个请求完成前被并发上限拒绝。事件只控制策略调用的完成时机，不接触运行时内部信号量，
    因而这条用例验证的是调用方可观察的行为，而不是实现细节。
    """

    runtime, client, _ = build_api(tmp_root, limit_overrides={"max_concurrency": 1})
    assert runtime.config.limits.max_concurrency == 1, "闸门大小必须真的来自配置"

    evaluation_started = threading.Event()
    release_evaluation = threading.Event()

    def blocking_evaluate(rules, context):
        evaluation_started.set()
        if not release_evaluation.wait(timeout=5):
            raise AssertionError("首个请求等待释放超时")
        return evaluate(rules, context)

    monkeypatch.setattr("policy_api.runtime.evaluate", blocking_evaluate)
    second_client = make_client(runtime)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first_future = pool.submit(
            client.post,
            "/v1/policy/evaluate",
            headers=auth(),
            json=envelope("it-busy-first", context=BAD_CONTEXT),
        )
        try:
            assert evaluation_started.wait(timeout=2), "首个请求没有进入策略评估"
            busy = second_client.post(
                "/v1/policy/evaluate",
                headers=auth(),
                json=envelope("it-busy-blocked", context=BAD_CONTEXT),
            )
        finally:
            release_evaluation.set()
        first = first_future.result(timeout=5)

    assert busy.status_code == 503
    assert error_code(busy) == "policy_busy"
    assert busy.json()["error"]["retryable"] is True
    # 失败响应里绝不能出现决策：503 必须读起来像"没有结论"，而不是"结论是允许"。
    assert "decision" not in busy.json()
    # request_id 必须在认证与并发闸门之前解析好，否则 503 没有关联标识，
    # "请求级可观测"对这条路径就是空头承诺。
    assert busy.json()["error"]["request_id"] == "it-busy-blocked"
    assert first.status_code == 200
    assert first.json()["decision"]["decision"] == "block"

    # 释放之后闸门必须恢复可用：一次占满不能把服务永久打死。
    recovered = client.post(
        "/v1/policy/evaluate",
        headers=auth(),
        json=envelope("it-busy-recovered", context=BAD_CONTEXT),
    )
    assert recovered.status_code == 200
