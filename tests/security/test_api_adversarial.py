"""Phase 7 Policy API 的对抗测试：认证边界、跨租户隔离、自带证据、观测沉降与失败关闭。

与集成测试的区别：集成测试问"正常路径是否按契约工作"，这里问**"能不能被绕过"**。
每条用例都对应一条具体的攻击面，注释里写清楚攻击者想得到什么、以及为什么拿不到：

- 用错误码区分"租户不存在"与"你不能用这个租户" = 拿服务当租户探测器；
- 客户端自带 `evidence` / `decision` = 自己给自己发通行证；
- 载荷里声明 `principal.roles` = 用请求体给自己升权；
- 观测日志不可写却继续返回决定 = 事后查不清是谁批的；
- 控制字符与绝对路径进日志 = 日志注入与部署信息泄露。

全部用例都走真实 ASGI 栈（进程内、无端口），并在隔离的临时租户边界里跑。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Mapping

import pytest

from conftest import REPO_ROOT, write_fixture_corpus

from policy_api.config import RateLimitConfig, load_api_config
from policy_api.runtime import ApiRuntime
from policy_api.testing import make_client
from retrieval.corpus import load_corpus
from retrieval.indexer import ingest
from retrieval.store import ChunkStore

from api_support import OPS_TOKEN, TOKEN, TOKEN2, isolated_api

pytestmark = pytest.mark.security

GOOD_CONTEXT: dict[str, Any] = {
    "file": "src/shop/order_controller.py",
    "layer": "controller",
    "language": "python",
    "dependencies": ["service"],
}


# --------------------------------------------------------------------------- 夹具


def build_api(tmp_root: Path, **kwargs: Any) -> tuple[ApiRuntime, Any]:
    """隔离装配一套 API（与集成测试同一套夹具，这里只需要 runtime 与客户端）。

    限流桶被显式放大：本文件要用**大量**被拒请求来区分错误码，
    5 个请求的桶会把 401/403 全变成 429——那是环境噪声，不是被测行为。
    """

    config_path, anchor = isolated_api(tmp_root, **kwargs)
    config = load_api_config(config_path, root=anchor).model_copy(
        update={"rate_limit": RateLimitConfig(capacity=1000, refill_per_second=1000.0)}
    )
    runtime = ApiRuntime(config, root=anchor, readiness_ttl_seconds=0.0)
    return runtime, make_client(runtime)


def index_fixture(tmp_root: Path) -> tuple[Path, Path]:
    """真实索引（跨租户与 decision_ref 用例需要它，否则检索会先在"没有语料"处失败）。"""

    corpus_root = tmp_root / "corpus"
    db = tmp_root / "index" / "retrieval.sqlite3"
    loaded = load_corpus(write_fixture_corpus(corpus_root), repo_root=corpus_root)
    with ChunkStore(db) as store:
        ingest(loaded, store, repo_root=corpus_root)
    return corpus_root, db


def auth(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def envelope(request_id: str, *, tenant: str | None = "alpha", context: Mapping[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
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


def retrieve_payload(request_id: str, *, tenant: str = "alpha", **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "api_version": "1.0",
        "request_id": request_id,
        "tenant": tenant,
        "principal": {"subject": "alice"},
        # 检索必须显式声明上下文：文件/层级这些维度由调用方给出，服务端不推断。
        "context": dict(GOOD_CONTEXT),
        "query": "guide",
        "limit": 3,
    }
    body.update(extra)
    return body


# --------------------------------------------------------------------------- 认证


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Basic YWxpY2U6c2VjcmV0"},
        # 下面两行是**故意造出来的假凭据**（本项目测试夹具的演示令牌与乱码），
        # 不是真实凭据：它们存在的意义就是"不成形的凭据必须 401"。
        {"Authorization": "Bearer not-a-real-token"},  # secret-scan: allow（假凭据）
        {"Authorization": "bearer alpha-secret-token"},  # secret-scan: allow（方案名大小写不匹配也算未认证）
    ],
    ids=["no-header", "empty", "basic", "wrong-token", "lowercase-scheme"],
)
def test_authentication_failures_are_all_401(tmp_root: Path, headers: dict[str, str]) -> None:
    """任何"凭据不成形"的请求都只能得到 401 unauthenticated。

    刻意不接受 `bearer` 小写：认证方案是协议的一部分，"猜一个 fallback"就是放宽边界。
    """

    runtime, client = build_api(tmp_root)
    response = client.post("/v1/policy/evaluate", headers=headers, json=envelope("sec-auth"))
    assert response.status_code == 401
    assert error_code(response) == "unauthenticated"
    assert response.json()["error"]["retryable"] is False


def test_tenant_trespass_is_indistinguishable_from_a_bad_token(tmp_root: Path) -> None:
    """alpha 的令牌要求使用 beta 租户：必须是 401，且**与错误令牌的响应逐字节相同**。

    如果这里返回 403 `tenant_not_found` 或 "该租户不存在"，服务就变成了租户名的探测器：
    攻击者可以用错误码枚举部署里存在哪些租户（AGENTS 核心约束 33）。
    """

    runtime, client = build_api(tmp_root)
    trespass = client.post(
        "/v1/policy/evaluate", headers=auth(TOKEN), json=envelope("sec-trespass", tenant="beta")
    )
    bad_token = client.post(
        "/v1/policy/evaluate",
        headers={"Authorization": "Bearer definitely-not-a-token"},  # secret-scan: allow（假凭据）
        json=envelope("sec-trespass", tenant="beta"),
    )
    assert trespass.status_code == bad_token.status_code == 401
    assert error_code(trespass) == error_code(bad_token) == "unauthenticated"
    assert trespass.content == bad_token.content

    # 不存在的租户与"你不能用的租户"同样不可区分。
    undefined = client.post(
        "/v1/policy/evaluate", headers=auth(TOKEN), json=envelope("sec-trespass", tenant="gamma")
    )
    assert undefined.status_code == 401
    assert undefined.content == trespass.content


def test_client_authorized_for_two_tenants_must_declare_one(tmp_root: Path) -> None:
    """被授权多个租户的凭据必须显式声明 tenant：服务端**不替调用方选一个**。"""

    runtime, client = build_api(tmp_root)
    response = client.post(
        "/v1/policy/evaluate", headers=auth(TOKEN2), json=envelope("sec-scope", tenant=None)
    )
    assert response.status_code == 403
    assert error_code(response) == "token_scope_mismatch"
    assert "tenant" in response.json()["error"]["detail"]


# --------------------------------------------------------------------------- 信息泄露


def test_error_responses_never_leak_internal_information(tmp_root: Path) -> None:
    """错误响应只能包含"调用方需要知道才能改请求"的内容。

    逐条检查：没有规则目录名（`policies/`）、没有仓库绝对路径（两种分隔符写法）、没有 traceback。
    """

    runtime, client = build_api(tmp_root)
    url = "/v1/policy/evaluate"
    probes = [
        ("未认证", client.post(url, json=envelope("sec-leak-1"))),
        ("未知字段", client.post(url, headers=auth(), json={**envelope("sec-leak-2"), "evil": 1})),
        (
            "未知版本",
            client.post(url, headers=auth(), json={**envelope("sec-leak-3"), "api_version": "9.9"}),
        ),
        (
            "越界路径",
            client.post(
                url,
                headers=auth(),
                json=envelope(
                    "sec-leak-4",
                    context={"file": "C:/Windows/win.ini", "layer": "controller", "language": "python"},
                ),
            ),
        ),
        ("未知路径", client.get("/v1/policy/nowhere")),
        ("方法不对", client.get(url)),
    ]
    # 依赖不可用（规则目录被删）也必须只说"不可用"，不说"哪个文件在哪儿"。
    shutil.rmtree(tmp_root / "project" / "rules")
    probes.append(("规则集不可用", client.post(url, headers=auth(), json=envelope("sec-leak-5"))))

    for name, response in probes:
        assert response.status_code >= 400, name
        text = response.text
        assert "policies/" not in text, f"{name}: 泄露了规则目录名"
        assert str(REPO_ROOT) not in text, f"{name}: 泄露了仓库绝对路径"
        assert str(REPO_ROOT).replace("\\", "/") not in text, f"{name}: 泄露了仓库绝对路径（POSIX 写法）"
        assert "Traceback" not in text, f"{name}: 泄露了 traceback"
        assert set(response.json()) == {"error"}, name

    assert probes[-1][1].status_code == 503
    assert error_code(probes[-1][1]) == "rule_set_unavailable"


# --------------------------------------------------------------------------- 自带证据 / 自带决策


def test_client_supplied_evidence_or_decision_is_rejected(tmp_root: Path) -> None:
    """客户端不能在请求体里塞证据或决策：未知字段一律 400。

    证据只能由服务端验证器流水线产出；决策只能由策略引擎算出。
    "客户端说这条规则过了"如果被接受，整套治理就退化成了自证。
    """

    runtime, client = build_api(tmp_root)
    for field, value in (
        ("evidence", [{"rule_id": "ARCH-001", "status": "passed"}]),
        ("decision", {"decision": "allow", "schema_version": "1.0"}),
        ("skipped_rules", []),
    ):
        response = client.post(
            "/v1/knowledge/retrieve",
            headers=auth(),
            json=retrieve_payload("sec-self", **{field: value}),
        )
        assert response.status_code == 400, field
        assert error_code(response) == "body_invalid"
        assert field in response.json()["error"]["detail"]

    evaluated = client.post(
        "/v1/policy/evaluate", headers=auth(), json={**envelope("sec-self-2"), "evidence": []}
    )
    assert evaluated.status_code == 400
    assert error_code(evaluated) == "body_invalid"


def test_forged_decision_ref_is_rejected(tmp_root: Path) -> None:
    """`decision_ref` 只能指向本服务算过的 request_id：伪造引用得到 403，而不是"按它授权"。"""

    corpus_root, db = index_fixture(tmp_root)
    runtime, client = build_api(tmp_root, corpus_root=corpus_root, db=db)
    response = client.post(
        "/v1/knowledge/retrieve",
        headers=auth(),
        json=retrieve_payload("sec-forged", decision_ref="i-computed-this-myself"),
    )
    assert response.status_code == 403
    assert error_code(response) == "forbidden"


# --------------------------------------------------------------------------- 扩权


def test_client_cannot_widen_its_own_principal_or_roles(tmp_root: Path) -> None:
    """载荷里的 `principal` 只是"我声称我是谁"，它不能改变认证结论与授权角色。

    - 声称 `subject: root` + `roles: [admin]`：租户仍然是令牌给的 alpha，决策与 alice 完全一致；
    - 声称运维角色也拿不到指标：指标可见性只看**配置里该客户端声明的角色/白名单**。
    """

    runtime, client = build_api(tmp_root)
    baseline = client.post("/v1/policy/evaluate", headers=auth(), json=envelope("sec-widen"))
    assert baseline.status_code == 200

    widened = client.post(
        "/v1/policy/evaluate",
        headers=auth(),
        json=envelope("sec-widen", principal={"subject": "root", "roles": ["admin", "ops"]}),
    )
    assert widened.status_code == 200
    assert widened.json()["tenant"] == "alpha"
    assert widened.json()["decision"] == baseline.json()["decision"]
    assert widened.json()["rule_set"]["hash"] == baseline.json()["rule_set"]["hash"]

    metrics = client.post(
        "/v1/policy/evaluate",
        headers=auth(),
        json=envelope("sec-widen", principal={"subject": "root", "roles": ["ops"]}),
    )
    assert metrics.status_code == 200
    assert metrics.json()["tenant"] == "alpha"

    assert error_code(client.get("/v1/ops/metrics", headers=auth(TOKEN))) == "metrics_forbidden"


# --------------------------------------------------------------------------- 跨租户隔离


def test_cross_tenant_isolation_of_decisions_and_idempotency(tmp_root: Path) -> None:
    """两个租户之间：决策引用不可串用，幂等键互不影响。

    `both-client` 同时被授权 alpha 与 beta，因此它是最危险的调用方——
    如果 `decision_ref` 或幂等台账按"客户端"而不是"客户端 + 租户"分桶，这里就会串。
    """

    corpus_root, db = index_fixture(tmp_root)
    runtime, client = build_api(tmp_root, corpus_root=corpus_root, db=db)

    evaluated = client.post(
        "/v1/policy/evaluate", headers=auth(TOKEN2), json=envelope("sec-iso", tenant="alpha")
    )
    assert evaluated.status_code == 200

    # 同一个 request_id：在 alpha 里是有效引用，在 beta 里必须 403。
    inside = client.post(
        "/v1/knowledge/retrieve",
        headers=auth(TOKEN2),
        json=retrieve_payload("sec-iso-in", tenant="alpha", decision_ref="sec-iso"),
    )
    assert inside.status_code == 200
    across = client.post(
        "/v1/knowledge/retrieve",
        headers=auth(TOKEN2),
        json=retrieve_payload("sec-iso-out", tenant="beta", decision_ref="sec-iso"),
    )
    assert across.status_code == 403
    assert error_code(across) == "forbidden"

    # 幂等：同一个 key、同一个客户端，但 tenant 不同 → 两份台账，互不冲突。
    first = client.post(
        "/v1/policy/evaluate",
        headers=auth(TOKEN2),
        json=envelope("sec-idem-alpha", tenant="alpha", idempotency_key="shared-key"),
    )
    second = client.post(
        "/v1/policy/evaluate",
        headers=auth(TOKEN2),
        json=envelope("sec-idem-beta", tenant="beta", idempotency_key="shared-key"),
    )
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["tenant"] == "alpha" and second.json()["tenant"] == "beta"
    assert "Idempotency-Replayed" not in second.headers

    alpha_ledger = runtime.ledger_for("alpha").path
    beta_ledger = runtime.ledger_for("beta").path
    assert alpha_ledger != beta_ledger
    assert alpha_ledger.name == "alpha.jsonl.idempotency"
    assert beta_ledger.name == "beta.jsonl.idempotency"
    assert {row["tenant"] for row in runtime.request_log.read_back()} == {"alpha", "beta"}


# --------------------------------------------------------------------------- 运维面


def test_metrics_requires_ops_credentials(tmp_root: Path) -> None:
    """指标端点只对运维角色或 `metrics_clients` 白名单开放。

    指标里有租户名、错误分类与延迟分布：它对普通调用方开放等于把部署拓扑交出去。
    """

    runtime, client = build_api(tmp_root)
    assert client.post(
        "/v1/policy/evaluate", headers=auth(), json=envelope("sec-metrics-1")
    ).status_code == 200

    forbidden = client.get("/v1/ops/metrics", headers=auth(TOKEN))
    assert forbidden.status_code == 403
    assert error_code(forbidden) == "metrics_forbidden"
    assert error_code(client.get("/v1/ops/metrics", headers=auth(TOKEN2))) == "metrics_forbidden"
    assert client.get("/v1/ops/metrics").status_code == 401

    allowed = client.get("/v1/ops/metrics", headers=auth(OPS_TOKEN))
    assert allowed.status_code == 200
    body = allowed.json()
    assert "evaluate" in body["metrics"]["routes"]
    assert body["metrics"]["routes"]["evaluate"]["requests"] == 1
    assert body["tenants"] == ["alpha", "beta"]
    assert set(body) == {"api_version", "service", "deployment", "metrics", "rate_limit", "tenants", "readiness"}


# --------------------------------------------------------------------------- 失败关闭


def test_audit_log_failure_fails_closed(tmp_root: Path) -> None:
    """观测日志不可写时：请求得到 503 audit_unavailable，**且不返回决定**。

    "决定记不下来就不返回决定"是 Phase 4 就定下的纪律：否则一次无法追溯的 allow
    会变成事后审计里根本不存在的授权。
    """

    runtime, client = build_api(tmp_root)
    blocker = tmp_root / "blocker.txt"
    blocker.write_text("我不是目录", encoding="utf-8", newline="\n")
    runtime.request_log.path = blocker / "audit.jsonl"

    response = client.post("/v1/policy/evaluate", headers=auth(), json=envelope("sec-audit"))
    assert response.status_code == 503
    assert error_code(response) == "audit_unavailable"
    body = response.json()
    assert set(body) == {"error"}
    assert "decision" not in response.text and "allow" not in json.dumps(body)


def test_control_characters_are_neutralised_in_the_log(tmp_root: Path) -> None:
    """控制字符不许原样进日志（日志注入），超长查询直接被拒。

    两段式：超长查询（含 NUL/ESC + 5000 个汉字）命中 `max_length` → 400；
    而**被接受**的请求把控制字符放进 `request_id` 与 `subject`，
    日志里必须只剩转义形式（`\\x00` / `\\x1b`），不得出现真正的控制字节。
    """

    runtime, client = build_api(tmp_root)
    hostile_query = "\u0000\u001b" + "汉" * 5000
    rejected = client.post(
        "/v1/knowledge/retrieve",
        headers=auth(),
        json=retrieve_payload("sec-ctrl-1", query=hostile_query),
    )
    assert rejected.status_code == 400
    assert error_code(rejected) == "body_invalid"

    accepted = client.post(
        "/v1/policy/evaluate",
        headers=auth(),
        json=envelope("req-\u0000\u001b-1", principal={"subject": "ali\u0000ce"}),
    )
    assert accepted.status_code == 200
    assert accepted.json()["decision"]["request_id"] == "req-\u0000\u001b-1"

    text = runtime.request_log.path.read_text(encoding="utf-8")
    assert "\x00" not in text and "\x1b" not in text, "控制字符必须被转义，不能原样落盘"
    assert r"\x00" in text and r"\x1b" in text
    rows = runtime.request_log.read_back()
    # 被拒的请求也必须留痕；而 request_id 落盘时已经是**转义形式**，不是原字节。
    assert [row["request_id"] for row in rows] == ["sec-ctrl-1", r"req-\x00\x1b-1"]


# --------------------------------------------------------------------------- 未知枚举


def test_unknown_operation_enum_is_rejected_not_downgraded(tmp_root: Path) -> None:
    """未知操作不得被降级成"没有操作"。

    实测（真实行为）：`context.operation = "delete_everything"` 得到 **400 body_invalid**
    （DTO 的受控枚举先于上下文构建失败），而不是期望的 context_invalid；
    `file_operation`（自由字符串字段）走的是 `ContextDTO.to_context_payload`，
    因此那一条给出的才是 context_invalid——两条路径都必须在注释里说清楚。
    共同点是：没有任何一条路径把未知操作当成"无操作"放行。
    """

    runtime, client = build_api(tmp_root)
    unknown_operation = client.post(
        "/v1/policy/evaluate",
        headers=auth(),
        json=envelope(
            "sec-op-1",
            context={**GOOD_CONTEXT, "operation": "delete_everything"},
        ),
    )
    assert unknown_operation.status_code == 400
    assert error_code(unknown_operation) == "body_invalid"  # 偏差：任务书期望 context_invalid
    # DTO 校验只指出"哪个字段不合法"，不回显客户端给的值（错误细节由服务端生成）。
    assert "context.operation" in unknown_operation.json()["error"]["detail"]

    unknown_file_operation = client.post(
        "/v1/policy/evaluate",
        headers=auth(),
        json=envelope(
            "sec-op-2",
            context={**GOOD_CONTEXT, "file_operation": "delete_everything"},
        ),
    )
    assert unknown_file_operation.status_code == 400
    assert error_code(unknown_file_operation) == "context_invalid"

    # 对照：显式的 null 是合法值（"本次调用没有操作"必须显式声明，而不是靠猜）。
    explicit_null = client.post(
        "/v1/policy/evaluate",
        headers=auth(),
        json=envelope("sec-op-3", context={**GOOD_CONTEXT, "operation": None}),
    )
    assert explicit_null.status_code == 200
    assert explicit_null.json()["decision"]["decision"] == "allow"
