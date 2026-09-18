"""Phase 7 Policy API 的单元契约：错误码、配置、预算、限流、幂等与观测。

这一层刻意**不经过 HTTP**：FastAPI 只是 `ApiRuntime` 的一个调用方，真正被依赖的契约
（错误码 → 状态码的推导、配置即边界、预算与超时、幂等台账、脱敏观测）都在普通 Python 对象上。
把契约测试写成"起个服务再断言"，失败原因就永远指向传输层，而不是契约本身；
本文件因此可以在毫秒级、无端口、无网络的前提下把失败语义钉死。

每条用例都在证明一件**具体**的事：它为什么必须这样，写在用例自己的 docstring 里。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest

from conftest import REPO_ROOT

from policy_api.config import (
    ConfigError,
    RateLimitConfig,
    hash_token,
    load_api_config,
)
from policy_api.errors import ApiError, ErrorCode, STATUS_BY_CODE, error_payload, redact_detail
from policy_api.idempotency import IdempotencyLedger
from policy_api.observability import Latency, Metrics, RequestLog, RequestLogEntry
from policy_api.runtime import ApiRuntime, RateLimiter, budget_for
from policy_api.services import signature_of
from policy_api.timeout import Budget, BudgetExceeded, run_with_budget

from api_support import TOKEN_SHA

# --------------------------------------------------------------------------- 工具

# 一份"最小合法配置"：只有 schema_version 与一个租户。
# 它不指向真实目录也没关系——`load_api_config` 只做**配置层**校验，
# "目录存不存在"是装配层（TenantStore）的事，两者的失败必须能被分开测试。
BASE_CONFIG = """schema_version: "1.0"
tenants:
  - tenant_id: alpha
    project_root: project
    rules: [rules]
"""


def write_config(tmp_root: Path, text: str, *, name: str = "policy-api.yaml") -> Path:
    """把 YAML 文本写成配置文件（UTF-8 / LF，与仓库其它文本一致）。"""

    path = tmp_root / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def repo_config():
    """仓库自己的部署配置：需要真预算/真限流数值的用例用它，避免测试里另抄一份常量。"""

    return load_api_config(REPO_ROOT / "api" / "policy-api.yaml", root=REPO_ROOT)


def make_entry(**overrides) -> RequestLogEntry:
    """一条请求日志记录：只覆盖本次用例关心的字段。"""

    payload = {
        "route": "evaluate",
        "outcome": "ok",
        "status": 200,
        "request_id": "req-1",
        "tenant": "alpha",
        "client_id": "alpha-client",
        "subject": "alice",
        "token_ref": TOKEN_SHA[:12],
        "decision": "allow",
        "elapsed_ms": 3,
        "rule_set_hash": "sha256:" + "0" * 64,
        "violations": 0,
    }
    payload.update(overrides)
    return RequestLogEntry(**payload)


# --------------------------------------------------------------------------- 错误码


def test_every_error_code_has_a_status_and_api_error_derives_it() -> None:
    """错误码是**受控枚举**，状态码只能由它推导。

    证明两件事：(1) 枚举里每新增一个码都必须同时给出状态码（少一个 = `ApiError.status` 会 KeyError）；
    (2) 调用方拿到的状态码不是自己写的字段，而是 `STATUS_BY_CODE` 的值——"认证失败永远 401"
    这类不变量因此不可能被某个分支随手改掉。
    """

    declared = {item for item in ErrorCode}
    assert declared == set(STATUS_BY_CODE), "错误码与状态码映射必须一一对应"
    for code in ErrorCode:
        error = ApiError(code, "detail")
        assert error.status == STATUS_BY_CODE[code]
        assert error.kind == code.value
        assert isinstance(error.status, int) and 400 <= error.status <= 599
    # 客户端会按这些字面量编程：它们是被公开的线上协议的一部分。
    assert ErrorCode.SCHEMA_VERSION_MISSING.value == "schema_version_missing"
    assert ErrorCode.RATE_LIMITED.value == "rate_limited"
    assert ErrorCode.IDEMPOTENCY_KEY_CONFLICT.value == "idempotency_key_conflict"
    assert ErrorCode.METRICS_FORBIDDEN.value == "metrics_forbidden"
    assert ErrorCode.AUDIT_UNAVAILABLE.value == "audit_unavailable"
    # 失败关闭的语义：错误响应永远带 4xx/5xx，没有"默认放行"那一档。
    assert {code for code, status in STATUS_BY_CODE.items() if status < 400} == set()


def test_error_payload_shape_is_fixed_and_hides_debug() -> None:
    """错误响应只有一个形状：`{"error": {code, detail, retryable, request_id, trace_id}}`。

    形状固定 = 客户端可以只写一个解析器；`debug` 只留给本地诊断，
    绝不能出现在响应里（它可能带 traceback 与内部路径）。
    """

    payload = error_payload(
        ApiError(ErrorCode.FORBIDDEN, "该凭据没有被授权", retryable=False),
        request_id="req-1",
        trace_id="trace-1",
    )
    assert set(payload) == {"error"}
    assert set(payload["error"]) == {"code", "detail", "retryable", "request_id", "trace_id"}
    assert payload["error"] == {
        "code": "forbidden",
        "detail": "该凭据没有被授权",
        "retryable": False,
        "request_id": "req-1",
        "trace_id": "trace-1",
    }
    # 默认值也是契约的一部分：没有 request_id 就写 null，不编造一个。
    minimal = error_payload(ApiError(ErrorCode.INTERNAL_ERROR, "内部错误", debug="Traceback: boom"))
    assert minimal["error"]["request_id"] is None and minimal["error"]["trace_id"] is None
    assert "Traceback" not in json.dumps(minimal, ensure_ascii=False)


def test_redact_detail_collapses_lines_and_caps_length() -> None:
    """错误细节是**服务端生成的一行文本**：换行会被压平、超长会被截断。

    否则调用方拿到的 `detail` 可以是一条多行文本，日志注入与"响应体被撑爆"都会从这里进来。
    """

    assert redact_detail("first\nsecond\tthird   fourth") == "first second third fourth"
    assert redact_detail("   ") == ""
    assert redact_detail("x" * 240) == "x" * 240  # 正好到上限：不截断
    clipped = redact_detail("x" * 241)
    assert len(clipped) == 240 and clipped.endswith("…")
    assert clipped[:-1] == "x" * 239


# --------------------------------------------------------------------------- 配置


def test_load_api_config_rejects_unknown_schema_version(tmp_root: Path) -> None:
    """未知配置版本必须拒绝加载：看不懂的配置不允许"按默认语义"跑。"""

    path = write_config(tmp_root, BASE_CONFIG.replace('"1.0"', '"9.9"'))
    with pytest.raises(ConfigError) as info:
        load_api_config(path, root=REPO_ROOT)
    assert "未知部署配置版本" in str(info.value) and "9.9" in str(info.value)


def test_load_api_config_rejects_plaintext_token(tmp_root: Path) -> None:
    """令牌只允许以 sha256 出现：写明文就等于把凭据散进配置与备份。

    错误信息必须**直说**"明文"，否则维护者只会看到"格式不对"，然后把令牌加长再试一次。
    """

    text = BASE_CONFIG + (
        "clients:\n"
        "  - client_id: leaky\n"
        "    token_sha256: alpha-secret-token\n"
        "    tenants: [alpha]\n"
    )
    with pytest.raises(ConfigError) as info:
        load_api_config(write_config(tmp_root, text), root=REPO_ROOT)
    assert "明文" in str(info.value)
    assert "leaky" in str(info.value)


def test_load_api_config_rejects_token_that_is_neither_hash_nor_plaintext(tmp_root: Path) -> None:
    """"不是 64 位十六进制"与"看起来是明文"是两种错误，都要给出来。"""

    text = BASE_CONFIG + (
        "clients:\n"
        "  - client_id: shorty\n"
        "    token_sha256: zz\n"
        "    tenants: [alpha]\n"
    )
    with pytest.raises(ConfigError) as info:
        load_api_config(write_config(tmp_root, text), root=REPO_ROOT)
    assert "不是 64 位十六进制摘要" in str(info.value)


def test_load_api_config_rejects_empty_tenants(tmp_root: Path) -> None:
    """没有租户就没有可服务的边界：空租户列表不是"不限租户"。"""

    with pytest.raises(ConfigError) as info:
        load_api_config(
            write_config(tmp_root, 'schema_version: "1.0"\ntenants: []\n'), root=REPO_ROOT
        )
    assert "至少要声明一个租户" in str(info.value)


def test_load_api_config_rejects_client_with_undefined_tenant(tmp_root: Path) -> None:
    """客户端引用了未定义的租户 = 配置错误，必须在加载阶段炸，而不是等到认证时才 404。"""

    text = BASE_CONFIG + (
        "clients:\n"
        "  - client_id: c1\n"
        f"    token_sha256: {'a' * 64}\n"
        "    tenants: [gamma]\n"
    )
    with pytest.raises(ConfigError) as info:
        load_api_config(write_config(tmp_root, text), root=REPO_ROOT)
    assert "未定义的租户" in str(info.value) and "gamma" in str(info.value)


@pytest.mark.parametrize("tenant_id", ["Alpha", "alpha!", "-alpha", "alpha beta"])
def test_load_api_config_rejects_illegal_tenant_id(tmp_root: Path, tenant_id: str) -> None:
    """租户名是要出现在日志、指标与台账键里的标识符：非法字符不许通过。"""

    text = BASE_CONFIG.replace("alpha", tenant_id)
    with pytest.raises(ConfigError) as info:
        load_api_config(write_config(tmp_root, text), root=REPO_ROOT)
    assert "tenant_id" in str(info.value)


def test_load_api_config_rejects_duplicate_tenant_ids(tmp_root: Path) -> None:
    """重复租户名会让"哪个边界生效"变成未定义行为，加载即拒绝。"""

    text = BASE_CONFIG + "  - tenant_id: alpha\n    project_root: project\n    rules: [rules]\n"
    with pytest.raises(ConfigError) as info:
        load_api_config(write_config(tmp_root, text), root=REPO_ROOT)
    assert "tenant_id 必须唯一" in str(info.value)


def test_load_api_config_reports_missing_and_unreadable_files(tmp_root: Path) -> None:
    """配置读不到也是显式失败：文件不存在与非映射顶层各给一条明确错误。"""

    with pytest.raises(ConfigError) as missing:
        load_api_config(tmp_root / "nope.yaml", root=REPO_ROOT)
    assert "不存在" in str(missing.value) and "nope.yaml" in str(missing.value)

    with pytest.raises(ConfigError) as empty:
        load_api_config(write_config(tmp_root, ""), root=REPO_ROOT)
    assert "顶层必须是映射" in str(empty.value)


def test_hash_token_is_a_stable_sha256_hex_digest() -> None:
    """令牌只以摘要形式参与比较与落盘：这里钉死它的确切算法与形状。"""

    digest = hash_token("alpha-secret-token")
    assert digest == hashlib.sha256(b"alpha-secret-token").hexdigest()
    assert hash_token("alpha-secret-token") == digest
    assert digest != hash_token("alpha-secret-token ")
    assert len(digest) == 64 and digest == digest.lower()
    assert all(char in "0123456789abcdef" for char in digest)


# --------------------------------------------------------------------------- 预算


def test_budget_counts_down_and_fails_closed_when_exhausted() -> None:
    """预算耗尽必须抛异常（`BudgetExceeded`），没有"还剩 0ms 就继续"的分支。"""

    budget = Budget(total_ms=100, used_ms=30)
    assert budget.remaining_ms == 70
    spent = budget.spend(20)
    assert spent.remaining_ms == 50
    assert budget.remaining_ms == 70, "spend 返回新对象，不修改原件"
    assert budget.spend(-5).used_ms == 30, "负耗时不算回血"
    assert Budget(total_ms=10, used_ms=99).remaining_ms == 0, "剩余时间不出现负数"

    Budget(total_ms=10, used_ms=9).require(stage="evaluate")  # 还剩 1ms 就不抛
    with pytest.raises(BudgetExceeded) as info:
        Budget(total_ms=10, used_ms=10).require(stage="evaluate")
    assert "evaluate" in str(info.value)
    with pytest.raises(ValueError):
        Budget(total_ms=0)


def test_budget_for_caps_client_requested_budget() -> None:
    """调用方只能**要更小的**预算：要更大的一律 503，不能拖住服务端线程。"""

    config = repo_config()
    assert budget_for("evaluate", config, None) == config.budgets.evaluate_ms
    assert budget_for("evaluate", config, 10) == 10
    with pytest.raises(ApiError) as info:
        budget_for("evaluate", config, config.budgets.evaluate_ms + 1)
    assert info.value.code is ErrorCode.REQUEST_BUDGET_EXCEEDED
    assert info.value.status == 503
    # 非预算路由（metrics / health）回落到 evaluate 预算，而不是"没有上限"。
    assert budget_for("metrics", config, None) == config.budgets.evaluate_ms


def test_run_with_budget_returns_value_and_reports_timeout() -> None:
    """预算内正常返回；超预算返回 `(None, timed_out=True)`——调用方据此返回 504，绝不伪造结论。"""

    value, elapsed = run_with_budget(lambda: "ok", budget_ms=1000)
    assert value == "ok"
    assert elapsed.timed_out is False
    assert elapsed.milliseconds >= 0.0

    value, elapsed = run_with_budget(lambda: time.sleep(0.2), budget_ms=20)
    assert value is None
    assert elapsed.timed_out is True
    assert elapsed.milliseconds >= 20.0


def test_run_with_budget_propagates_operation_errors() -> None:
    """预算器只负责计时：被调用函数抛的异常原样抛出，由调用方决定翻成哪个错误码。"""

    def boom() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run_with_budget(boom, budget_ms=1000)
    with pytest.raises(ValueError):
        run_with_budget(lambda: None, budget_ms=0)


# --------------------------------------------------------------------------- 限流


def test_rate_limiter_exhausts_bucket_and_refills_with_injected_clock() -> None:
    """令牌桶按 (客户端, 租户) 计数：用假时钟证明"耗尽 → 429""推进时间 → 恢复"两件事。"""

    now = [1000.0]
    limiter = RateLimiter(RateLimitConfig(capacity=2, refill_per_second=1.0), clock=lambda: now[0])
    limiter.check("alpha-client:alpha")
    limiter.check("alpha-client:alpha")
    with pytest.raises(ApiError) as info:
        limiter.check("alpha-client:alpha")
    assert info.value.code is ErrorCode.RATE_LIMITED
    assert info.value.status == 429 and info.value.retryable is True

    limiter.check("both-client:alpha")  # 另一个桶：别人的请求不被这次耗尽影响
    now[0] += 1.0
    limiter.check("alpha-client:alpha")  # 1 秒补 1 个
    with pytest.raises(ApiError):
        limiter.check("alpha-client:alpha")
    assert limiter.snapshot()["buckets"] == 2


def test_rate_limiter_without_config_does_not_limit() -> None:
    """`config=None` 表示"这个部署显式不限流"，而不是"默认放行"：快照里也要能看出来。"""

    limiter = RateLimiter(None)
    for _ in range(50):
        limiter.check("alpha-client:alpha")
    snapshot = limiter.snapshot()
    assert snapshot["capacity"] is None and snapshot["refill_per_second"] is None


# --------------------------------------------------------------------------- 幂等


def test_idempotency_ledger_replays_and_conflicts_in_memory() -> None:
    """同一个 key + 同一个摘要 = 原结论；换了请求体 = 409。

    "换请求体也复用旧结论"是最危险的幂等实现：它会把 A 的判定结果发给 B。
    """

    ledger = IdempotencyLedger(None)
    lookup = dict(client_id="alpha-client", api_version="1.0", route="evaluate", key="k1")
    assert ledger.lookup(**lookup, digest="d1") is None

    body = {"decision": {"decision": "allow"}, "tenant": "alpha"}
    ledger.record(**lookup, digest="d1", status=200, body=body)
    hit = ledger.lookup(**lookup, digest="d1")
    assert hit is not None
    assert (hit.status, hit.body, hit.digest) == (200, body, "d1")

    with pytest.raises(ApiError) as info:
        ledger.lookup(**lookup, digest="d2")
    assert info.value.code is ErrorCode.IDEMPOTENCY_KEY_CONFLICT
    assert info.value.status == 409

    # 台账的键包含 client 与路由：换了调用者或路由就不是"同一个请求"。
    assert ledger.lookup(client_id="other", api_version="1.0", route="evaluate", key="k1", digest="d1") is None
    assert ledger.lookup(client_id="alpha-client", api_version="1.0", route="retrieve", key="k1", digest="d1") is None


def test_idempotency_ledger_persists_to_file_and_survives_restart(tmp_root: Path) -> None:
    """落盘台账要能被**另一个进程**读到：否则重启后同一个 key 会被重算（甚至给出不同结论）。"""

    path = tmp_root / "ledger" / "alpha.jsonl.idempotency"
    ledger = IdempotencyLedger(path, ttl_seconds=900)
    lookup = dict(client_id="alpha-client", api_version="1.0", route="evaluate", key="k1")
    ledger.record(**lookup, digest="d1", status=200, body={"decision": "allow"})
    assert path.is_file()

    reopened = IdempotencyLedger(path, ttl_seconds=900)
    hit = reopened.lookup(**lookup, digest="d1")
    assert hit is not None and hit.body == {"decision": "allow"}

    # 响应体超限时只记状态码：台账不能变成第二份数据仓库（结论仍然可重放）。
    oversized = {"blob": "x" * 9000}
    second = {**lookup, "key": "k2"}
    reopened.record(**second, digest="d2", status=200, body=oversized)
    big = reopened.lookup(**second, digest="d2")
    assert big is not None and big.status == 200 and big.body == {}


def test_idempotency_ledger_with_zero_ttl_never_expires(tmp_root: Path) -> None:
    """`ttl_seconds=0` 是"永不过期"的显式声明，不是"立刻过期"。

    证明方式：手工把过期时间写到过去——ttl=0 仍然命中，ttl=900 则必须重新判定（不能复用旧结论）。
    """

    path = tmp_root / "ledger.jsonl"
    ledger = IdempotencyLedger(path, ttl_seconds=0)
    lookup = dict(client_id="alpha-client", api_version="1.0", route="evaluate", key="k1")
    ledger.record(**lookup, digest="d1", status=200, body={"decision": "allow"})

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    rows[0]["expires_at"] = "2000-01-01T00:00:00.000000Z"
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )

    hit = ledger.lookup(**lookup, digest="d1")
    assert hit is not None and hit.body == {"decision": "allow"}
    assert IdempotencyLedger(path, ttl_seconds=900).lookup(**lookup, digest="d1") is None


def test_idempotency_ledger_fails_closed_on_corrupted_file(tmp_root: Path) -> None:
    """台账损坏 / 协议版本未知时宁可 503，也不按不确定的语义去重。"""

    lookup = dict(client_id="alpha-client", api_version="1.0", route="evaluate", key="k1", digest="d1")

    broken = tmp_root / "broken.jsonl"
    broken.write_text("这不是 JSON\n", encoding="utf-8", newline="\n")
    with pytest.raises(ApiError) as info:
        IdempotencyLedger(broken).lookup(**lookup)
    assert info.value.code is ErrorCode.IDEMPOTENCY_UNAVAILABLE
    assert info.value.status == 503 and info.value.retryable is True

    wrong_version = tmp_root / "wrong-version.jsonl"
    wrong_version.write_text(
        json.dumps({"ledger_schema_version": "2.0", "entry_key": "x"}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(ApiError) as info:
        IdempotencyLedger(wrong_version).lookup(**lookup)
    assert info.value.code is ErrorCode.IDEMPOTENCY_UNAVAILABLE
    assert "协议版本" in info.value.detail


# --------------------------------------------------------------------------- 指标


def test_metrics_observe_produces_self_consistent_payload() -> None:
    """指标是运维判断"服务是否健康"的输入：计数、错误数与延迟分位必须自洽。"""

    metrics = Metrics(clock=lambda: 100.0)
    metrics.observe(route="evaluate", outcome="ok", status=200, elapsed_ms=10.0, decision="allow")
    metrics.observe(route="evaluate", outcome="blocked", status=403, elapsed_ms=30.0, decision="block")
    metrics.observe(route="retrieve", outcome="ok", status=200, elapsed_ms=5.0)
    metrics.count_replay()
    metrics.count_rate_limited()
    metrics.count_timeout()
    metrics.count_budget_exceeded()

    payload = metrics.to_payload()
    bucket = payload["routes"]["evaluate"]
    assert bucket["requests"] == 2 and bucket["errors"] == 1 and bucket["count"] == 2
    assert bucket["mean_ms"] == 20.0 and bucket["max_ms"] == 30.0
    assert 10.0 <= bucket["p50_ms"] <= 30.0
    assert bucket["p50_ms"] <= bucket["p95_ms"] <= bucket["p99_ms"] <= bucket["max_ms"]
    assert payload["routes"]["retrieve"]["errors"] == 0
    assert payload["status_classes"] == {"2xx": 2, "4xx": 1}
    assert payload["decisions"] == {"allow": 1, "block": 1}
    assert payload["outcomes"] == {"ok": 2, "blocked": 1}
    assert (payload["replays"], payload["rate_limited"], payload["timeouts"]) == (1, 1, 1)
    assert payload["budget_exceeded"] == 1
    assert payload["uptime_seconds"] == 0.0


def test_latency_percentile_handles_empty_single_and_capped_samples() -> None:
    """空样本返回 None（"没有数据"不等于 0ms）；单样本返回它自己；样本上限只丢最旧的。"""

    latency = Latency()
    assert latency.count == 0
    assert latency.percentile(50) is None and latency.mean() is None
    assert latency.to_payload()["p50_ms"] is None and latency.to_payload()["max_ms"] is None

    latency.observe(7.5)
    assert latency.percentile(50) == 7.5 and latency.percentile(1) == 7.5

    for value in (1.0, 2.0, 3.0, 4.0):
        latency.observe(value)
    assert latency.count == 5
    assert latency.percentile(0) == 1.0
    assert latency.percentile(100) == 7.5

    capped = Latency(max_samples=2)
    for value in (1.0, 2.0, 3.0):
        capped.observe(value)
    assert capped.samples == [2.0, 3.0]


# --------------------------------------------------------------------------- 装配指纹


def test_signature_of_tracks_mtime_size_and_missing_paths(tmp_root: Path) -> None:
    """规则目录的指纹决定"要不要重载"：内容、mtime、大小任一变化都必须换指纹。

    不存在的路径也要给**稳定**指纹——规则目录被删掉时，指纹必须能自己变，
    而不是靠一个异常来触发重载（那种实现会让"目录还在但文件被删空"漏过去）。
    """

    first = tmp_root / "rules" / "ARCH-001.yaml"
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_text("id: ARCH-001\n", encoding="utf-8", newline="\n")

    baseline = signature_of((first,))
    assert baseline == signature_of((first,))

    first.write_text("id: ARCH-001\nversion: 2\n", encoding="utf-8", newline="\n")
    grown = signature_of((first,))
    assert grown != baseline

    stat = first.stat()
    os.utime(first, ns=(stat.st_atime_ns + 10**9, stat.st_mtime_ns + 10**9))
    assert signature_of((first,)) != grown

    missing = tmp_root / "gone" / "ARCH-001.yaml"
    assert signature_of((missing,)) == signature_of((missing,))
    assert signature_of((missing,)) != signature_of((first,))
    assert signature_of(()) == signature_of(())

    second = tmp_root / "rules" / "ARCH-002.yaml"
    second.write_text("id: ARCH-002\n", encoding="utf-8", newline="\n")
    assert signature_of((first, second)) == signature_of((second, first)), "指纹与文件顺序无关"


# --------------------------------------------------------------------------- 装配锚点


def test_tenant_validators_path_is_anchored_not_process_cwd(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """部署配置里的相对路径必须锚定到**仓库根**，不能锚定到进程 CWD（回归用例）。

    这里曾经是配置里唯一相对 CWD 的路径：`LoadedTenant.validators()` 把 `spec.validators`
    原样交给 `load_config(registry=...)`，而后者用 `Path(...)` 直接读。后果很隐蔽：
    同一个租户从仓库根启动 → validate 200，从任意别的目录启动 → 503 validator_unavailable
    ——"启动目录"改变了服务能力，也与 `api/README.md` 写明的
    "仓库根优先、配置目录兜底"不一致。现在 `TenantStore._assemble` 先把它解析成绝对路径
    （base = validation_root，其次 service_root），本用例因此把两种 CWD 各跑一遍，
    断言拿到的是**同一份**注册表与同一条路径。
    """

    config = load_api_config(REPO_ROOT / "api" / "policy-api.yaml", root=REPO_ROOT)
    runtime = ApiRuntime(config, root=REPO_ROOT, readiness_ttl_seconds=0.0)
    tenant = runtime.store.get("fixture-shop")
    assert tenant.validation_root == REPO_ROOT.resolve()
    assert tenant.spec.validators == "validation/validators.yaml"
    assert tenant.validators_path == REPO_ROOT / "validation" / "validators.yaml"

    anchored = tenant.validators()
    assert anchored.registry_path == REPO_ROOT / "validation" / "validators.yaml"

    monkeypatch.chdir(tmp_root)
    after_chdir = tenant.validators()
    assert after_chdir.registry_path == anchored.registry_path
    assert [item.id for item in after_chdir.registry.validators] == [
        item.id for item in anchored.registry.validators
    ]


# --------------------------------------------------------------------------- 观测


def test_request_log_disabled_fails_closed(tmp_root: Path) -> None:
    """"决定记不下来"就不返回决定：显式禁用观测时 append 必须抛 503。

    而"只关掉落盘"（path=None 但 enabled=True）是 --dry-run 的显式用法：留在内存里、不抛。
    """

    disabled = RequestLog(tmp_root / "unused.jsonl", enabled=False)
    with pytest.raises(ApiError) as info:
        disabled.append(make_entry())
    assert info.value.code is ErrorCode.AUDIT_UNAVAILABLE
    assert info.value.status == 503

    memory_only = RequestLog(None)
    memory_only.append(make_entry(request_id="req-memory"))
    assert memory_only.entries()[0]["request_id"] == "req-memory"
    assert memory_only.read_back() == ()


def test_request_log_appends_redacted_records(tmp_root: Path) -> None:
    """落盘记录必须可读回、可追溯，且**不含令牌明文与绝对路径**。"""

    path = tmp_root / "audit" / "service.jsonl"
    log = RequestLog(path, workspace=REPO_ROOT)
    log.append(
        make_entry(
            request_id="req-redact",
            subject=str(REPO_ROOT / "src" / "policy"),
            error="C:/Users/Public/secret.txt",
        )
    )

    rows = log.read_back()
    assert len(rows) == 1
    assert rows[0]["request_id"] == "req-redact"
    assert rows[0]["token_ref"] == TOKEN_SHA[:12]
    assert rows[0]["log_schema_version"] == "1.0"

    text = path.read_text(encoding="utf-8")
    assert "alpha-secret-token" not in text
    assert str(REPO_ROOT) not in text
    # 工作区内的绝对路径替换成 <workspace>（只留相对部分），工作区外的整体抹成 <abs>：
    # 观测日志里出现绝对路径等于把部署环境信息写进了日志。
    assert rows[0]["subject"].startswith("<workspace>")
    assert rows[0]["subject"].replace("\\", "/").endswith("src/policy")
    assert rows[0]["error"] == "<abs>"
