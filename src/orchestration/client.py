"""Policy Platform 客户端端口：编排层**只**通过它与平台对话。

三种实现，对应阶段计划的两步走（§2「先用 fake Policy Client，再连接 Phase 7 API」）：

- `ScriptedPolicyClient`：固定的 allow / block / error 响应。用它可以把"编排缺陷"
  和"平台缺陷"分开——状态机测试不该依赖真的规则集；
- `ApiPolicyClient`：真实 HTTP（标准库 `urllib`），只走 Phase 7 的公开路由，
  不导入 `policy.engine` 等内部实现；
- `ResilientPolicyClient`：在任何实现外面加熔断：反复失败就停止调用平台。

失败语义（与 Phase 7 的失败码一一对应，绝不"出错即放行"）：

- 传输失败 / 5xx / 504 / 429 → `PlatformUnavailableError`（终态 blocked）；
- 401 / 403（认证、租户、项目边界）→ 同样是 blocked：编排层不会用"降级"绕过边界；
- 4xx（400 / 413 / 415）→ 这是编排层自己发错了请求 → `NodeContractError`（终态 failed）；
- 200 但载荷缺字段 / 版本对不上 → `PlatformUnavailableError`（宁可停下，也不猜）。

trace 纪律：调用方给了 `trace_id` 就必须原样拿回来；拿不回来即 `TraceError`。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, Tuple, runtime_checkable

from policy.models import Decision, ValidationResult, parse_decision

from .errors import (
    CircuitOpenError,
    NodeContractError,
    PlatformUnavailableError,
    TraceError,
)
from .models import (
    ContextRef,
    FailureCode,
    StageStatus,
    ValidationSummary,
    ViolationRef,
)

__all__ = [
    "API_SCHEMA_VERSION",
    "EVALUATE_PATH",
    "RETRIEVE_PATH",
    "VALIDATE_PATH",
    "ApiPolicyClient",
    "CircuitBreaker",
    "DecisionOutcome",
    "EvaluateCall",
    "PlatformCall",
    "PlatformReadiness",
    "PolicyClient",
    "ResilientPolicyClient",
    "RetrievalOutcome",
    "RetrieveCall",
    "ScriptedPolicyClient",
    "ValidateCall",
    "ValidationOutcome",
    "failure_code_for",
]

API_SCHEMA_VERSION = "1.0"
EVALUATE_PATH = "/v1/policy/evaluate"
RETRIEVE_PATH = "/v1/knowledge/retrieve"
VALIDATE_PATH = "/v1/validation/evaluate"
READINESS_PATH = "/v1/health/ready"
DEFAULT_TIMEOUT_SECONDS = 30.0

# 平台错误码 → 编排层失败码。**没有默认放行**：未登记的码一律 blocked。
FAILURE_CODE_BY_API_ERROR: Mapping[str, FailureCode] = {
    "knowledge_unavailable": FailureCode.KNOWLEDGE_UNAVAILABLE,
    "validator_unavailable": FailureCode.VALIDATOR_UNAVAILABLE,
    "evidence_unavailable": FailureCode.EVIDENCE_UNAVAILABLE,
    "rule_set_unavailable": FailureCode.POLICY_UNAVAILABLE,
    "policy_unavailable": FailureCode.POLICY_UNAVAILABLE,
    "policy_busy": FailureCode.POLICY_UNAVAILABLE,
    "audit_unavailable": FailureCode.POLICY_UNAVAILABLE,
    "idempotency_unavailable": FailureCode.POLICY_UNAVAILABLE,
    "request_budget_exceeded": FailureCode.POLICY_UNAVAILABLE,
    "idempotency_key_conflict": FailureCode.POLICY_UNAVAILABLE,
    "internal_error": FailureCode.POLICY_UNAVAILABLE,
    "rate_limited": FailureCode.POLICY_UNAVAILABLE,
    "evaluate_timeout": FailureCode.POLICY_UNAVAILABLE,
    "retrieve_timeout": FailureCode.POLICY_UNAVAILABLE,
    "validate_timeout": FailureCode.POLICY_UNAVAILABLE,
    "unauthenticated": FailureCode.POLICY_UNAVAILABLE,
    "token_expired": FailureCode.POLICY_UNAVAILABLE,
    "token_scope_mismatch": FailureCode.POLICY_UNAVAILABLE,
    "forbidden": FailureCode.POLICY_UNAVAILABLE,
    "tenant_not_found": FailureCode.POLICY_UNAVAILABLE,
    "project_not_allowed": FailureCode.POLICY_UNAVAILABLE,
    "metrics_forbidden": FailureCode.POLICY_UNAVAILABLE,
    "not_found": FailureCode.POLICY_UNAVAILABLE,
    "method_not_allowed": FailureCode.POLICY_UNAVAILABLE,
    # 编排层自己发错了请求：这是编排缺陷，不是平台不可用。
    "schema_version_missing": FailureCode.NODE_CONTRACT_INVALID,
    "schema_version_unknown": FailureCode.NODE_CONTRACT_INVALID,
    "body_invalid": FailureCode.NODE_CONTRACT_INVALID,
    "unsupported_media_type": FailureCode.NODE_CONTRACT_INVALID,
    "body_too_large": FailureCode.NODE_CONTRACT_INVALID,
    "context_invalid": FailureCode.NODE_CONTRACT_INVALID,
    "query_invalid": FailureCode.NODE_CONTRACT_INVALID,
    "target_invalid": FailureCode.NODE_CONTRACT_INVALID,
    "idempotency_key_missing": FailureCode.NODE_CONTRACT_INVALID,
}

_REQUEST_FAULT_CODES = frozenset(
    {
        FailureCode.NODE_CONTRACT_INVALID,
    }
)


def failure_code_for(status: int, code: Optional[str]) -> FailureCode:
    """HTTP 状态 + 平台错误码 → 编排层失败码（保守：认不出来的一律 blocked）。"""

    if code is not None and code in FAILURE_CODE_BY_API_ERROR:
        return FAILURE_CODE_BY_API_ERROR[code]
    if status in (400, 404, 405, 409, 413, 415):
        return FailureCode.NODE_CONTRACT_INVALID
    return FailureCode.POLICY_UNAVAILABLE


# --------------------------------------------------------------------- 调用与结果


@dataclass(frozen=True)
class PlatformCall:
    """一次平台调用的信封。`context` / `principal` 是平台 DTO 形状的普通映射。"""

    request_id: str
    context: Mapping[str, Any]
    principal: Mapping[str, Any]
    tenant: Optional[str] = None
    trace_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    budget_ms: Optional[int] = None

    def envelope(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "api_version": API_SCHEMA_VERSION,
            "request_id": self.request_id,
            "principal": dict(self.principal),
            "context": dict(self.context),
        }
        for name in ("tenant", "trace_id", "idempotency_key", "budget_ms"):
            value = getattr(self, name)
            if value is not None:
                payload[name] = value
        return payload


@dataclass(frozen=True)
class EvaluateCall(PlatformCall):
    include_evidence: bool = True

    def envelope(self) -> dict[str, Any]:
        payload = super().envelope()
        payload["include_evidence"] = self.include_evidence
        return payload


@dataclass(frozen=True)
class RetrieveCall(PlatformCall):
    query: Optional[str] = None
    limit: Optional[int] = None
    decision_ref: Optional[str] = None

    def envelope(self) -> dict[str, Any]:
        payload = super().envelope()
        for name in ("query", "limit", "decision_ref"):
            value = getattr(self, name)
            if value is not None:
                payload[name] = value
        return payload


@dataclass(frozen=True)
class ValidateCall(PlatformCall):
    target: Optional[str] = None
    changed: Tuple[str, ...] = ()
    only: Tuple[str, ...] = ()
    include_decision: bool = True

    def envelope(self) -> dict[str, Any]:
        payload = super().envelope()
        payload["include_decision"] = self.include_decision
        if self.target is not None:
            payload["target"] = self.target
        if self.changed:
            payload["changed"] = list(self.changed)
        if self.only:
            payload["only"] = list(self.only)
        return payload


@dataclass(frozen=True)
class DecisionOutcome:
    """evaluate 的结果：结构化 Decision + 原始协议对象（供 Phase 4 复用）。"""

    decision: Decision
    request_id: str
    trace_id: Optional[str] = None
    rule_set_hash: Optional[str] = None
    required_action: Optional[str] = None
    matched_rules: Tuple[str, ...] = ()
    skipped_rules: Tuple[str, ...] = ()
    violations: Tuple[ViolationRef, ...] = ()
    validation: Optional[ValidationResult] = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        """只有 allow / allow_with_warnings 算"可以继续动手"。"""

        return self.decision in (Decision.ALLOW, Decision.ALLOW_WITH_WARNINGS)

    def summary(self, *, status: Any = None) -> ValidationSummary:
        return ValidationSummary(
            decision=self.decision,
            status=StageStatus.OK if status is None else status,
            request_id=self.request_id,
            trace_id=self.trace_id,
            rule_set_hash=self.rule_set_hash,
            required_action=self.required_action,
            violations=self.violations,
        )


@dataclass(frozen=True)
class RetrievalOutcome:
    """retrieve 的结果：三态（ok / empty / unavailable）必须分开。"""

    status: str
    request_id: str
    reason: Optional[str] = None
    detail: str = ""
    index_version: Optional[str] = None
    trace_id: Optional[str] = None
    contexts: Tuple[ContextRef, ...] = ()

    @property
    def usable(self) -> bool:
        """只有 `ok` 且真的带回片段才算"拿到了规范"；empty 不是"没有规范"。"""

        return self.status == "ok" and bool(self.contexts)


@dataclass(frozen=True)
class ValidationOutcome:
    """validate 的结果：决定 + 证据摘要 + 验证器状态（不落正文）。"""

    decision: Decision
    request_id: str
    trace_id: Optional[str] = None
    rule_set_hash: Optional[str] = None
    evidence_digest: Optional[str] = None
    required_action: Optional[str] = None
    validators: Tuple[str, ...] = ()
    blockers: Tuple[str, ...] = ()
    violations: Tuple[ViolationRef, ...] = ()
    validation: Optional[ValidationResult] = None
    status: str = "ok"

    @property
    def failing(self) -> bool:
        return self.decision is Decision.BLOCK

    def summary(self) -> ValidationSummary:
        return ValidationSummary(
            decision=self.decision,
            status=StageStatus.OK if not self.failing else StageStatus.FAILED,
            request_id=self.request_id,
            trace_id=self.trace_id,
            rule_set_hash=self.rule_set_hash,
            evidence_digest=self.evidence_digest,
            required_action=self.required_action,
            validators=self.validators,
            violations=self.violations,
        )


@dataclass(frozen=True)
class PlatformReadiness:
    """平台的版本凭据：恢复时用它与 checkpoint 比对。

    **拿不到就是拿不到**：字段为 None 表示"不知道"，调用方按"变了"处理（重新评估），
    绝不按"没变"处理——那会让旧 allow 被沿用。
    """

    state: str = "unknown"
    ready: bool = False
    rule_set_hash: Optional[str] = None
    index_version: Optional[str] = None


@runtime_checkable
class PolicyClient(Protocol):
    """编排层唯一允许的"问平台"入口。"""

    def evaluate(self, call: EvaluateCall) -> DecisionOutcome: ...

    def retrieve(self, call: RetrieveCall) -> RetrievalOutcome: ...

    def validate(self, call: ValidateCall) -> ValidationOutcome: ...

    def readiness(self) -> PlatformReadiness: ...


# --------------------------------------------------------------------- 载荷解析


def _violations_from(payload: Mapping[str, Any]) -> Tuple[ViolationRef, ...]:
    items: list[ViolationRef] = []
    raw = payload.get("violations")
    if not isinstance(raw, Sequence):
        return ()
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        evidence = item.get("evidence")
        file = ""
        line = None
        if isinstance(evidence, Mapping):
            candidate = evidence.get("file")
            if isinstance(candidate, str) and _is_relative(candidate):
                file = candidate
            if isinstance(evidence.get("line"), int):
                line = int(evidence["line"])
        items.append(
            ViolationRef(
                rule_id=str(item.get("rule_id", "unknown")),
                rule_version=int(item.get("rule_version", 1) or 1),
                severity=str(item.get("severity", "error")),
                file=file,
                line=line,
                message=str(item.get("message", ""))[:400],
            )
        )
    return tuple(items)


def _parse_validation(payload: Mapping[str, Any]) -> ValidationResult:
    try:
        return parse_decision(payload)
    except Exception as error:  # noqa: BLE001 - 解析不出来就是平台契约坏了
        raise PlatformUnavailableError(
            f"决策载荷无法解析（{type(error).__name__}）：拒绝按'看起来没问题'继续",
            code=FailureCode.POLICY_UNAVAILABLE,
        ) from error


def _is_relative(value: str) -> bool:
    """状态里只允许仓库相对路径：绝对路径、`~` 与 `..` 一律不进状态。"""

    return bool(value) and not value.startswith(("/", "~")) and ".." not in value.split("/")


def _check_trace(expected: Optional[str], received: Optional[str]) -> Optional[str]:
    if expected is not None and received != expected:
        raise TraceError(
            f"trace 传播中断：请求带 {expected!r}，响应回 {received!r}"
        )
    return received


# --------------------------------------------------------------------- HTTP 实现


class ApiPolicyClient:
    """Phase 7 Policy API 的 HTTP 客户端（标准库实现，走公开路由）。"""

    def __init__(
        self,
        base_url: str,
        *,
        token: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        opener: Optional[Callable[..., Any]] = None,
    ) -> None:
        if not base_url or not token:
            raise NodeContractError("ApiPolicyClient 需要 base_url 与 token")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._opener = opener or urllib.request.urlopen
        self.paths: list[str] = []

    # -- 传输 ---------------------------------------------------------------
    def _post(self, path: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        body = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        self.paths.append(path)
        try:
            with self._opener(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                status = int(response.status)
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            status = int(error.code)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise PlatformUnavailableError(
                f"Policy API 不可达（{type(error).__name__}）",
                code=FailureCode.POLICY_UNAVAILABLE,
            ) from error
        try:
            decoded = json.loads(raw) if raw else {}
        except json.JSONDecodeError as error:
            raise PlatformUnavailableError(
                "Policy API 返回了非 JSON 响应：按不可用处理",
                code=FailureCode.POLICY_UNAVAILABLE,
                status=status,
            ) from error
        if not isinstance(decoded, Mapping):
            raise PlatformUnavailableError(
                "Policy API 返回的顶层不是对象：按不可用处理",
                code=FailureCode.POLICY_UNAVAILABLE,
                status=status,
            )
        if status != 200:
            error_block = decoded.get("error")
            code = error_block.get("code") if isinstance(error_block, Mapping) else None
            failure = failure_code_for(status, code if isinstance(code, str) else None)
            detail = ""
            if isinstance(error_block, Mapping):
                detail = str(error_block.get("detail", ""))[:200]
            message = f"Policy API {status} {code or 'unknown'}: {detail}"
            if failure in _REQUEST_FAULT_CODES:
                raise NodeContractError(message)
            raise PlatformUnavailableError(message, code=failure, status=status)
        return decoded

    def _get(self, path: str) -> tuple[int, Mapping[str, Any]]:
        request = urllib.request.Request(
            self.base_url + path,
            method="GET",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.paths.append(path)
        try:
            with self._opener(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return int(response.status), json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            try:
                return int(error.code), json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return int(error.code), {}
        except (urllib.error.URLError, TimeoutError, OSError):
            # 版本凭据拿不到：如实说"不知道"，由调用方按"变了"处理。
            return 0, {}

    def readiness(self) -> PlatformReadiness:
        status, body = self._get(READINESS_PATH)
        if status == 0:
            return PlatformReadiness(state="unknown", ready=False)
        rule_set_hash = None
        index_version = None
        tenants = body.get("tenants")
        if isinstance(tenants, Sequence):
            for tenant in tenants:
                if not isinstance(tenant, Mapping):
                    continue
                checks = tenant.get("checks")
                if not isinstance(checks, Sequence):
                    continue
                for check in checks:
                    if not isinstance(check, Mapping):
                        continue
                    if check.get("check") == "rule_set" and check.get("rule_set_hash"):
                        rule_set_hash = str(check["rule_set_hash"])[:80]
                    if check.get("check") == "index" and check.get("index_version"):
                        index_version = str(check["index_version"])[:80]
        return PlatformReadiness(
            state=str(body.get("state", "unknown")),
            ready=bool(body.get("ready", False)),
            rule_set_hash=rule_set_hash,
            index_version=index_version,
        )

    # -- 三个路由 -----------------------------------------------------------
    def evaluate(self, call: EvaluateCall) -> DecisionOutcome:
        body = self._post(EVALUATE_PATH, call.envelope())
        decision_block = body.get("decision")
        if not isinstance(decision_block, Mapping):
            raise PlatformUnavailableError(
                "evaluate 响应缺少 decision 对象", code=FailureCode.POLICY_UNAVAILABLE
            )
        result = _parse_validation(decision_block)
        if result.request_id != call.request_id:
            raise PlatformUnavailableError(
                "evaluate 响应的 request_id 与请求不一致：拒绝把别人的决定当自己的",
                code=FailureCode.POLICY_UNAVAILABLE,
            )
        trace = _check_trace(call.trace_id, result.trace_id)
        return DecisionOutcome(
            decision=result.decision,
            request_id=result.request_id,
            trace_id=trace,
            rule_set_hash=result.rule_set_hash,
            required_action=(
                None if result.required_action is None else str(result.required_action.value)
            ),
            matched_rules=tuple(result.matched_rules),
            skipped_rules=tuple(item.rule_id for item in result.skipped_rules),
            violations=_violations_from(decision_block),
            validation=result,
            payload=decision_block,
        )

    def retrieve(self, call: RetrieveCall) -> RetrievalOutcome:
        body = self._post(RETRIEVE_PATH, call.envelope())
        status = str(body.get("status", "unavailable"))
        if status not in ("ok", "empty", "unavailable"):
            raise PlatformUnavailableError(
                f"retrieve 返回未知状态 {status!r}", code=FailureCode.KNOWLEDGE_UNAVAILABLE
            )
        if status == "unavailable":
            # 服务端通常已经用 503 回答；万一它以 200 表达，也照样失败关闭。
            raise PlatformUnavailableError(
                "检索不可用：" + str(body.get("detail", ""))[:200],
                code=FailureCode.KNOWLEDGE_UNAVAILABLE,
            )
        context_block = body.get("context")
        snippets = ()
        if isinstance(context_block, Mapping):
            raw = context_block.get("snippets")
            if isinstance(raw, Sequence):
                snippets = tuple(item for item in raw if isinstance(item, Mapping))
        contexts: list[ContextRef] = []
        for item in snippets:
            source = str(item.get("source_path", ""))
            if not source or source.startswith(("/", "~")) or ".." in source.split("/"):
                continue
            contexts.append(
                ContextRef(
                    chunk_id=str(item.get("chunk_id", ""))[:128] or "unknown",
                    source_path=source,
                    digest=str(item.get("text_hash", "sha256:unknown"))[:80],
                    license=str(item.get("license", ""))[:120],
                    tier=str(item.get("tier", ""))[:40],
                )
            )
        index = body.get("index")
        index_version = None
        if isinstance(index, Mapping) and index.get("index_version") is not None:
            index_version = str(index["index_version"])[:80]
        # trace 由上下文块回声；请求带了 trace 就必须原样拿回来。
        echoed = None
        if isinstance(context_block, Mapping) and context_block.get("trace_id") is not None:
            echoed = str(context_block["trace_id"])[:128]
        return RetrievalOutcome(
            status=status,
            request_id=call.request_id,
            reason=None if body.get("reason") is None else str(body["reason"]),
            detail=str(body.get("detail", ""))[:200],
            index_version=index_version,
            trace_id=_check_trace(call.trace_id, echoed),
            contexts=tuple(contexts),
        )

    def validate(self, call: ValidateCall) -> ValidationOutcome:
        body = self._post(VALIDATE_PATH, call.envelope())
        report = body.get("report")
        if not isinstance(report, Mapping):
            raise PlatformUnavailableError(
                "validate 响应缺少 report", code=FailureCode.VALIDATOR_UNAVAILABLE
            )
        validators = tuple(
            str(item.get("validator", ""))
            for item in report.get("validators", []) or []
            if isinstance(item, Mapping)
        )
        blockers = tuple(
            ":".join(
                [
                    str(item.get("validator", "")),
                    str(item.get("status", "")),
                    str(item.get("reason", "")),
                ]
            )
            for item in body.get("blockers", []) or []
            if isinstance(item, Mapping)
        )
        decision_block = body.get("decision")
        evidence = report.get("evidence")
        evidence_digest = None
        if isinstance(evidence, Sequence) and evidence:
            from .models import canonical_digest

            evidence_digest = canonical_digest(list(evidence))
        if not isinstance(decision_block, Mapping):
            # 没有决定就没有 PASS：验证器不可用必须是显式失败，不是"跳过"。
            raise PlatformUnavailableError(
                "validate 响应没有决策载荷（验证器不可用不等于通过）",
                code=FailureCode.VALIDATOR_UNAVAILABLE,
            )
        result = _parse_validation(decision_block)
        if result.request_id != call.request_id:
            raise PlatformUnavailableError(
                "validate 响应的 request_id 与请求不一致",
                code=FailureCode.POLICY_UNAVAILABLE,
            )
        trace = _check_trace(call.trace_id, result.trace_id)
        return ValidationOutcome(
            decision=result.decision,
            request_id=result.request_id,
            trace_id=trace,
            rule_set_hash=result.rule_set_hash,
            evidence_digest=evidence_digest,
            required_action=None
            if result.required_action is None
            else str(result.required_action.value),
            validators=validators,
            blockers=blockers,
            violations=_violations_from(decision_block),
            validation=result,
            status="blocked" if blockers else "ok",
        )


# --------------------------------------------------------------------- 熔断


@dataclass
class CircuitBreaker:
    """连续失败到阈值就打开；打开期间**不调用平台**，直接失败关闭。"""

    failure_threshold: int = 3
    opened: bool = False
    consecutive_failures: int = 0
    opened_after_calls: int = 0
    calls: int = 0

    def ensure_closed(self) -> None:
        if self.opened:
            raise CircuitOpenError(
                f"熔断已打开（连续 {self.consecutive_failures} 次失败）：停止调用平台"
            )

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= max(1, self.failure_threshold):
            self.opened = True
            self.opened_after_calls = self.calls

    def reset(self, *, authorised: bool = False) -> None:
        """只有显式的人工/运维动作才能复位——恢复不该由"再来一次"自动完成。"""

        if not authorised:
            raise CircuitOpenError("熔断复位需要显式授权")
        self.opened = False
        self.consecutive_failures = 0


class ResilientPolicyClient:
    """给任意 `PolicyClient` 加熔断：重复失败时停止调用平台。"""

    def __init__(self, inner: PolicyClient, *, failure_threshold: int = 3) -> None:
        self.inner = inner
        self.breaker = CircuitBreaker(failure_threshold=failure_threshold)

    def _call(self, name: str, call: PlatformCall) -> Any:
        self.breaker.ensure_closed()
        self.breaker.calls += 1
        try:
            outcome = getattr(self.inner, name)(call)
        except PlatformUnavailableError:
            self.breaker.record_failure()
            raise
        self.breaker.record_success()
        return outcome

    def evaluate(self, call: EvaluateCall) -> DecisionOutcome:
        return self._call("evaluate", call)

    def retrieve(self, call: RetrieveCall) -> RetrievalOutcome:
        return self._call("retrieve", call)

    def validate(self, call: ValidateCall) -> ValidationOutcome:
        return self._call("validate", call)

    def readiness(self) -> PlatformReadiness:
        """版本查询不参与熔断计数：它不是"业务调用"，失败也已经按最保守方向处理。"""

        return self.inner.readiness()


# --------------------------------------------------------------------- 假客户端


def allow_outcome(request_id: str, *, rule_set_hash: str = "sha256:" + "a" * 64) -> DecisionOutcome:
    return DecisionOutcome(
        decision=Decision.ALLOW,
        request_id=request_id,
        rule_set_hash=rule_set_hash,
        matched_rules=("ARCH-001@1",),
    )


def block_outcome(
    request_id: str,
    *,
    rule_id: str = "ARCH-001",
    rule_version: int = 1,
    file: str = "src/shop/order_controller.py",
    line: int = 1,
    message: str = "Controller 不得直接访问 Repository。",
    rule_set_hash: str = "sha256:" + "a" * 64,
) -> DecisionOutcome:
    return DecisionOutcome(
        decision=Decision.BLOCK,
        request_id=request_id,
        rule_set_hash=rule_set_hash,
        violations=(
            ViolationRef(
                rule_id=rule_id,
                rule_version=rule_version,
                severity="error",
                file=file,
                line=line,
                message=message,
            ),
        ),
    )


@dataclass
class ScriptedPolicyClient:
    """按脚本回答的假客户端：固定 allow / block / error。

    - 脚本用完之后的调用一律 `PlatformUnavailableError`——**没有隐式 allow**；
    - 每条脚本项可以是 outcome 对象，也可以是 `Exception` 实例（用来演平台故障）；
    - `calls` 记录每一次调用，测试用它断言"节点真的问了平台"。
    """

    evaluate_script: Sequence[Any] = ()
    retrieve_script: Sequence[Any] = ()
    validate_script: Sequence[Any] = ()
    readiness_value: PlatformReadiness = field(default_factory=PlatformReadiness)
    calls: list[Tuple[str, PlatformCall]] = field(default_factory=list)

    def readiness(self) -> PlatformReadiness:
        return self.readiness_value

    def _next(self, route: str, script: Sequence[Any], call: PlatformCall) -> Any:
        self.calls.append((route, call))
        taken = sum(1 for name, _ in self.calls if name == route) - 1
        if taken >= len(script):
            raise PlatformUnavailableError(
                f"{route} 的脚本已用尽（第 {taken + 1} 次调用）：失败关闭，不返回隐式 allow",
                code=FailureCode.POLICY_UNAVAILABLE,
            )
        item = script[taken]
        if isinstance(item, BaseException):
            raise item
        return item

    def evaluate(self, call: EvaluateCall) -> DecisionOutcome:
        outcome = self._next("evaluate", self.evaluate_script, call)
        return self._substitute(outcome, call)

    def retrieve(self, call: RetrieveCall) -> RetrievalOutcome:
        outcome = self._next("retrieve", self.retrieve_script, call)
        return self._substitute(outcome, call)

    def validate(self, call: ValidateCall) -> ValidationOutcome:
        outcome = self._next("validate", self.validate_script, call)
        return self._substitute(outcome, call)

    @staticmethod
    def _substitute(outcome: Any, call: PlatformCall) -> Any:
        """把脚本项里的 request_id 占位符换成真实调用 ID，并做类型检查。"""

        substituted = outcome
        if getattr(outcome, "request_id", None) == "<auto>":
            substituted = type(outcome)(**{**outcome.__dict__, "request_id": call.request_id})
        if call.trace_id is not None and getattr(substituted, "trace_id", None) is None:
            substituted = type(substituted)(
                **{**substituted.__dict__, "trace_id": call.trace_id}
            )
        return substituted
