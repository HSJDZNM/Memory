"""Policy API 的运行时：认证、隔离、预算、幂等、限流、观测。

```text
HTTP 层（FastAPI：只解析 DTO 与 Authorization）
  → ApiRuntime.handle(route, payload, authorization, headers)
      → 认证（令牌 → 客户端 → 租户/项目边界）
      → 并发闸门（覆盖认证后的完整请求处理）
      → 幂等（key + 请求摘要 → 原响应）+ 预算（超时 → 显式错误，不伪造 allow）
      → 操作：policy.engine.evaluate / retrieval / validators.pipeline
      → 观测（脱敏 JSONL + 指标）
```

三条"不"：

- **不**在运行时里复制业务逻辑：判定只有 `policy.engine.evaluate` 一条路径，
  API 与本地 SDK 因此必然给出同一结论（tests/integration 用两条路径对比来证明）；
- **不**让调用方自带证据或自带决策：证据由服务端流水线产出，
  检索授权来自"服务端算过的决策"，客户端无法用载荷给自己扩权；
- **不**回落：任何一步失败都返回显式错误码，"策略不可用"绝不等价于"策略说可以"。
"""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence, Tuple

from policy.check import infer_layer
from policy.context import build_context
from policy.engine import EngineError, evaluate
from pydantic import ValidationError

from policy.models import (
    POLICY_VERSION,
    Decision,
    Operation,
    PolicyContext,
    PolicyContextError,
    ValidationResult,
    canonical_identifier,
)

from .auth import AuthContext, authorize, parse_authorization
from .config import ApiConfig, ConfigError, RateLimitConfig, load_api_config
from .errors import ApiError, ErrorCode, error_payload
from .idempotency import IdempotencyLedger, request_digest
from .models import (
    API_SCHEMA_VERSION,
    ContextDTO,
    EvaluateRequest,
    RetrieveRequest,
    ValidationRequest,
)
from .observability import Metrics, RequestLog, RequestLogEntry
from .services import LoadedTenant, TenantStore
from .timeout import run_with_budget

__all__ = [
    "ROUTES",
    "ApiRuntime",
    "RateLimiter",
    "RuntimeResponse",
    "budget_for",
    "build_runtime",
    "load_runtime_config",
]

# 路由名：指标、日志、幂等与错误的键都用它（不是 URL，改 URL 不该改台账语义）。
ROUTES = ("evaluate", "retrieve", "validate", "health", "readiness", "metrics")


@dataclass(frozen=True)
class RuntimeResponse:
    """一次调用的完整结果：状态码 + 正文 + 响应头。"""

    status: int
    body: Mapping[str, Any]
    headers: Mapping[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class RateLimiter:
    """按 (客户端, 租户) 的令牌桶。`config=None` 表示不限流（显式声明，不是默认放行）。"""

    def __init__(self, config: Optional[RateLimitConfig], *, clock: Callable[[], float] = time.monotonic) -> None:
        self.config = config
        self.clock = clock
        self._lock = threading.RLock()
        self._buckets: dict[str, list[float]] = {}

    def _bucket(self, key: str) -> list[float]:
        bucket = self._buckets.get(key)
        if bucket is None:
            capacity = float(self.config.capacity) if self.config else 0.0
            bucket = [capacity, self.clock()]
            self._buckets[key] = bucket
        return bucket

    def check(self, key: str) -> None:
        if self.config is None:
            return
        with self._lock:
            bucket = self._bucket(key)
            now = self.clock()
            elapsed = max(0.0, now - bucket[1])
            bucket[0] = min(
                float(self.config.capacity), bucket[0] + elapsed * self.config.refill_per_second
            )
            bucket[1] = now
            if bucket[0] < 1.0:
                raise ApiError(
                    ErrorCode.RATE_LIMITED,
                    "请求速率超过该凭据的上限；稍后重试",
                    retryable=True,
                )
            bucket[0] -= 1.0

    def snapshot(self) -> Mapping[str, Any]:
        with self._lock:
            return {
                "buckets": len(self._buckets),
                "capacity": None if self.config is None else self.config.capacity,
                "refill_per_second": None if self.config is None else self.config.refill_per_second,
            }


def budget_for(route: str, config: ApiConfig, requested: Optional[int]) -> int:
    """本次请求的预算：路由默认值，调用方可以要更小的（要更大的一律拒绝）。"""

    default = {
        "evaluate": config.budgets.evaluate_ms,
        "retrieve": config.budgets.retrieve_ms,
        "validate": config.budgets.validate_ms,
    }.get(route, config.budgets.evaluate_ms)
    if requested is None:
        return default
    if requested > default:
        raise ApiError(
            ErrorCode.REQUEST_BUDGET_EXCEEDED,
            f"调用方请求的预算 {requested}ms 超过本路由的上限 {default}ms",
        )
    return requested


def _decision_payload(result: ValidationResult) -> dict[str, Any]:
    """决策载荷原样透出：API **不改写**核心协议（它只是传输）。"""

    return result.to_decision_dict()


def _check_context_limits(payload: Mapping[str, Any], *, config: ApiConfig) -> None:
    """逐字段检查上下文规模。

    规则"请求体不超过 X"只描述了一次传输的大小；真正的风险是**单个字段**被撑爆
    （例如 10MB 的 `git_diff`），它会被写进判定、证据与日志。这里按字段量，超限即失败关闭。
    """

    for field in ("file", "module", "task", "git_diff"):
        value = payload.get(field)
        if not isinstance(value, str):
            continue
        size = len(value.encode("utf-8"))
        if size > config.limits.max_context_bytes:
            raise ApiError(
                ErrorCode.BODY_TOO_LARGE,
                f"context.{field} 超过上限 {config.limits.max_context_bytes} 字节",
            )
    task = payload.get("task")
    if isinstance(task, str) and len(task) > config.limits.max_prompt_chars:
        raise ApiError(
            ErrorCode.BODY_TOO_LARGE,
            f"context.task 超过上限 {config.limits.max_prompt_chars} 字符",
        )


def _context_from_dto(
    context: ContextDTO,
    auth: AuthContext,
    tenant: LoadedTenant,
    *,
    request_id: str,
    trace_id: Optional[str],
    runtime_config: ApiConfig,
) -> PolicyContext:
    payload = dict(context.to_context_payload(request_id=request_id, trace_id=trace_id))
    if payload.get("project") is None and tenant.spec.project:
        # 项目边界来自**租户声明**（配置即数据），不从请求推断；请求显式声明时以请求为准，
        # 但已经被 authorize 校验过"该凭据被授权这个项目"。
        payload["project"] = canonical_identifier(tenant.spec.project)
    if payload.get("agent") is None:
        payload["agent"] = canonical_identifier(f"api:{auth.client_id}")
    layer = str(payload.get("layer") or "").strip()
    if not layer:
        inferred = infer_layer(str(payload["file"]))
        if inferred:
            payload["layer"] = inferred
    _check_context_limits(payload, config=runtime_config)
    try:
        return build_context(payload, repo_root=tenant.project_root)
    except PolicyContextError as error:
        raise ApiError(ErrorCode.CONTEXT_INVALID, str(error)) from error


class ApiRuntime:
    """服务端的核心：一个进程一份，线程安全（多 worker 部署时每个 worker 各一份）。"""

    def __init__(
        self,
        config: ApiConfig,
        *,
        root: Optional[Path | str] = None,
        store: Optional[TenantStore] = None,
        request_log: Optional[RequestLog] = None,
        metrics: Optional[Metrics] = None,
        clock: Callable[[], float] = time.monotonic,
        readiness_ttl_seconds: float = 1.0,
    ) -> None:
        self.config = config
        anchor = Path(root) if root is not None else Path(config.service_root or Path.cwd())
        self.store = store if store is not None else TenantStore(config, root=anchor).load()
        self.metrics = metrics if metrics is not None else Metrics()
        self.clock = clock
        self.request_log = request_log or RequestLog(
            None if config.audit.path is None else (anchor / config.audit.path),
            enabled=config.audit.enabled,
            workspace=anchor,
        )
        self.rate_limiter = RateLimiter(config.rate_limit, clock=clock)
        self._idempotency: dict[str, IdempotencyLedger] = {}
        self._idempotency_lock = threading.Lock()
        self._decisions: dict[str, ValidationResult] = {}
        self._decisions_lock = threading.RLock()
        self._semaphore = threading.BoundedSemaphore(config.limits.max_concurrency)
        self._readiness: Optional[Tuple[float, Mapping[str, Any], int]] = None
        self._readiness_lock = threading.RLock()
        # 最近一次未预期异常的 traceback（只给 CLI / 闭环工具看，不进响应、不进日志）。
        self.last_error: str = ""
        self.readiness_ttl_seconds = readiness_ttl_seconds

    # ------------------------------------------------------------------ 装配

    @classmethod
    def from_path(
        cls, path: Path | str, *, root: Optional[Path | str] = None, **kwargs: Any
    ) -> "ApiRuntime":
        config = load_api_config(path, root=root)
        return cls(config, root=root, **kwargs)

    def ledger_for(self, tenant_id: str) -> IdempotencyLedger:
        """每个租户一份幂等台账：A 的 key 永远不会命中 B 的台账。"""

        with self._idempotency_lock:
            ledger = self._idempotency.get(tenant_id)
            if ledger is None:
                tenant = self.store.get(tenant_id)
                base = tenant.audit_path
                if base is not None:
                    path: Optional[Path] = base.with_name(base.name + ".idempotency")
                else:
                    path = None
                ledger = IdempotencyLedger(path, ttl_seconds=self.config.idempotency_ttl_seconds)
                self._idempotency[tenant_id] = ledger
            return ledger

    # ------------------------------------------------------------------ 入口

    def handle(
        self,
        route: str,
        payload: Mapping[str, Any],
        *,
        authorization: Optional[str] = None,
    ) -> RuntimeResponse:
        """处理一次调用。任何异常路径都以结构化错误结束，绝不抛给调用方。"""

        started = self.clock()
        request_id = ""
        tenant_id = ""
        project = ""
        trace_id = str(payload.get("trace_id") or "") or None
        # request_id 必须在**认证之前**解析好：限流与并发闸门是 _authenticate 内部抛的，
        # 若等它返回再赋值，503/429 的错误响应里 request_id 就是 null——客户端拿不到
        # 能用来对日志的关联标识，观测契约（请求级可追溯）在这两条路径上落空。
        request_id = str(payload.get("request_id") or "").strip()
        if not request_id and route == "metrics":
            # 运维路由没有请求体：request_id 由服务端生成（日志里仍可串联）。
            request_id = f"{route}:{int(self.clock() * 1000)}"
        auth: Optional[AuthContext] = None
        decision_value: Optional[str] = None
        rule_set_hash: Optional[str] = None
        index_version: Optional[str] = None
        violations = 0
        replayed = False
        outcome = "unknown"
        status = 500
        body: Mapping[str, Any] = {}
        headers: dict[str, str] = {}
        try:
            auth, project = self._authenticate(route, payload, authorization, request_id)
            tenant_id = auth.tenant
            with self._concurrency_slot():
                key = self._idempotency_key(payload)
                digest = ""
                if key is not None:
                    digest = request_digest(
                        {
                            "payload": self._payload_for(payload),
                            "subject": auth.subject,
                            "route": route,
                        }
                    )
                    replay = self.ledger_for(tenant_id).lookup(
                        client_id=auth.client_id,
                        api_version=API_SCHEMA_VERSION,
                        route=route,
                        key=key,
                        digest=digest,
                    )
                    if replay is not None:
                        self.metrics.count_replay()
                        replayed = True
                        status = replay.status
                        body = dict(replay.body)
                        headers["Idempotency-Replayed"] = "true"
                        decision_value = str(
                            body.get("decision") or body.get("summary", {}).get("decision") or ""
                        )
                        outcome = "replayed"
                        elapsed = int((self.clock() - started) * 1000)
                        self._record(
                            route=route,
                            outcome=outcome,
                            status=status,
                            started=started,
                            auth=auth,
                            request_id=request_id,
                            trace_id=trace_id,
                            project=project,
                            decision=decision_value,
                            error="",
                            replayed=True,
                            rule_set_hash=None,
                            index_version=None,
                            violations=0,
                        )
                        return RuntimeResponse(
                            status=status,
                            body=body,
                            headers={**headers, "X-Elapsed-Ms": str(elapsed)},
                        )
                status, body, facts = self._dispatch(route, payload, auth)
                decision_value = facts.get("decision") or ""
                rule_set_hash = facts.get("rule_set_hash")
                index_version = facts.get("index_version")
                violations = int(facts.get("violations") or 0)
                outcome = "ok" if status < 400 else str(facts.get("error") or "error")
                if key is not None and digest and _recordable(status, facts):
                    # 台账里存的是**键序规范化后的那一份**，并把同一份作为本次响应返回：
                    # 于是"重放"是逐字节相同，而不是"解析后相等"。代价是响应字段按字母序排列
                    # （JSON 对象本来就无序，契约里也没有"字段顺序"这一条）。
                    canonical = _canonical_body(body)
                    self.ledger_for(tenant_id).record(
                        client_id=auth.client_id,
                        api_version=API_SCHEMA_VERSION,
                        route=route,
                        key=key,
                        digest=digest,
                        status=status,
                        body=body,
                        canonical_body=canonical,
                    )
                    body = canonical
        except ApiError as error:
            status = error.status
            body = error_payload(
                error,
                request_id=request_id or None,
                trace_id=trace_id,
            )
            outcome = error.kind
            if error.code is ErrorCode.RATE_LIMITED:
                self.metrics.count_rate_limited()
            if error.code in (
                ErrorCode.EVALUATE_TIMEOUT,
                ErrorCode.RETRIEVE_TIMEOUT,
                ErrorCode.VALIDATE_TIMEOUT,
            ):
                self.metrics.count_timeout()
            if error.code is ErrorCode.REQUEST_BUDGET_EXCEEDED:
                self.metrics.count_budget_exceeded()
        except ValidationError as error:
            # DTO 的未知字段 / 未知枚举在这里被拒：契约由服务端说了算，不静默忽略。
            status = 400
            outcome = ErrorCode.BODY_INVALID.value
            body = error_payload(
                ApiError(ErrorCode.BODY_INVALID, _describe_validation(error)),
                request_id=request_id or None,
            )
        except Exception as error:  # noqa: BLE001 - 未知异常也必须收敛成结构化错误
            import traceback

            status = 500
            outcome = ErrorCode.INTERNAL_ERROR.value
            body = error_payload(
                ApiError(
                    ErrorCode.INTERNAL_ERROR,
                    f"{type(error).__name__}",
                    debug=traceback.format_exc(limit=6),
                ),
                request_id=request_id or None,
            )
            self.last_error = traceback.format_exc(limit=6)
        elapsed = int((self.clock() - started) * 1000)
        headers["X-Elapsed-Ms"] = str(elapsed)
        self._record(
            route=route,
            outcome=outcome,
            status=status,
            started=started,
            auth=auth,
            request_id=request_id,
            trace_id=trace_id,
            project=project,
            decision=decision_value or "",
            error="" if outcome in ("ok", "replayed") else outcome,
            replayed=replayed,
            rule_set_hash=rule_set_hash,
            index_version=index_version,
            violations=violations,
        )
        return RuntimeResponse(status=status, body=body, headers=headers)

    # ------------------------------------------------------------------ 认证

    def _authenticate(
        self,
        route: str,
        payload: Mapping[str, Any],
        authorization: Optional[str],
        request_id: str,
    ) -> Tuple[AuthContext, str]:
        """认证 + 限流。

        `request_id` 由调用方解析后传入（见 `handle`）：本函数在限流时会抛错，
        随后的并发闸门同样会抛错；这些响应必须带 request_id 才能追溯。
        """

        if not request_id:
            raise ApiError(ErrorCode.BODY_INVALID, "缺少 request_id")
        # 凭据来源：优先请求头（HTTP 的常规形态）；进程内调用可以直接放进信封。
        # 顺序很重要——先解析请求头会在"只有信封凭据"时直接 401，把一种合法调用方式变成失败。
        credentials = payload.get("credentials")
        if isinstance(credentials, Mapping) and "token" in credentials:
            token = str(credentials["token"])
        else:
            token = parse_authorization(authorization)
        # 令牌原文只在这里出现一次：登记给观测层，保证它不会因为被回显进
        # request_id / subject 之类的自由文本字段而落进日志。
        self.request_log.register_secret(token)
        context = payload.get("context")
        project = None
        if isinstance(context, Mapping):
            project = context.get("project")
        auth = authorize(
            self.config,
            token=token,
            subject=str(_principal_field(payload, "subject") or ""),
            tenant=self._tenant_hint(payload),
            project=canonical_identifier(str(project)) if project else None,
            route=route,
        )
        self.rate_limiter.check(f"{auth.client_id}:{auth.tenant}")
        return auth, str(project or "")

    @contextmanager
    def _concurrency_slot(self) -> Iterator[None]:
        """限制完整的认证后请求处理，而不是只探测信号量是否可取。"""

        if not self._semaphore.acquire(timeout=0.5):
            raise ApiError(
                ErrorCode.POLICY_BUSY,
                "服务当前并发已满；请稍后重试",
                retryable=True,
            )
        try:
            yield
        finally:
            self._semaphore.release()

    def _tenant_hint(self, payload: Mapping[str, Any]) -> Optional[str]:
        """租户只能由**令牌**决定：载荷里的 tenant 字段只作为"客户端想用哪个"的提示，

        且必须落在该令牌被授权的集合内（`authorize` 会拒绝越权的提示）。
        """

        value = payload.get("tenant")
        return None if value is None else str(value).strip()

    # ------------------------------------------------------------------ 分派

    def _dispatch(
        self, route: str, payload: Mapping[str, Any], auth: AuthContext
    ) -> Tuple[int, Mapping[str, Any], Mapping[str, Any]]:
        if route == "evaluate":
            return self._evaluate(payload, auth)
        if route == "retrieve":
            return self._retrieve(payload, auth)
        if route == "validate":
            return self._validate(payload, auth)
        if route == "metrics":
            return self._metrics(auth)
        raise ApiError(ErrorCode.NOT_FOUND, "未知路由")

    # ------------------------------------------------------------------ evaluate

    def _evaluate(
        self, payload: Mapping[str, Any], auth: AuthContext
    ) -> Tuple[int, Mapping[str, Any], Mapping[str, Any]]:
        request = EvaluateRequest.model_validate(dict(payload))
        tenant = self.store.get(auth.tenant)
        budget_ms = budget_for("evaluate", self.config, request.budget_ms)
        context = _context_from_dto(
            request.context,
            auth,
            tenant,
            request_id=request.request_id,
            trace_id=request.trace_id,
            runtime_config=self.config,
        )
        rules = tenant.rules()

        def work() -> ValidationResult:
            return evaluate(rules, context)

        result, elapsed = run_with_budget(work, budget_ms=budget_ms, clock=self.clock)
        if result is None:
            self.metrics.count_timeout()
            raise ApiError(
                ErrorCode.EVALUATE_TIMEOUT,
                f"策略判定超出预算 {budget_ms}ms；未给出结论（不伪造 allow）",
                retryable=True,
            )
        with self._decisions_lock:
            self._decisions[_decision_key(auth.tenant, request.request_id)] = result
        body: dict[str, Any] = {
            "api_version": API_SCHEMA_VERSION,
            "tenant": auth.tenant,
            "decision": _decision_payload(result),
            "summary": {
                "decision": result.decision.value,
                "violations": len(result.violations),
                "matched": len(result.matched_rules),
                "skipped": len(result.skipped_rules),
                "required_action": None if result.required_action is None else result.required_action.value,
            },
            "rule_set": {
                "hash": result.rule_set_hash,
                "rules": len(rules),
                "identity": list(rules.ids),
            },
            "policy_version": result.policy_version,
            "generation": POLICY_VERSION,
            "timing": {"budget_ms": budget_ms, "elapsed_ms": int(elapsed.milliseconds)},
        }
        if request.include_evidence:
            body["skipped_rules"] = [item.model_dump(mode="json") for item in result.skipped_rules]
        facts = {
            "decision": result.decision.value,
            "rule_set_hash": result.rule_set_hash,
            "violations": len(result.violations),
        }
        return 200, body, facts

    # ------------------------------------------------------------------ retrieve

    def _retrieve(
        self, payload: Mapping[str, Any], auth: AuthContext
    ) -> Tuple[int, Mapping[str, Any], Mapping[str, Any]]:
        request = RetrieveRequest.model_validate(dict(payload))
        tenant = self.store.get(auth.tenant)
        budget_ms = budget_for("retrieve", self.config, request.budget_ms)
        # **授权先于可用性**：先回答"这次请求有没有资格用那份决策"，
        # 再去问"语料/索引在不在"。反过来会让"跨租户引用"被伪装成
        # "知识不可用"，把授权结论和可用性结论混成一个错误码。
        policy_facts = self._policy_facts(tenant, auth, request.decision_ref)
        loaded = tenant.corpus()
        if tenant.store_path is None:
            raise ApiError(
                ErrorCode.KNOWLEDGE_UNAVAILABLE,
                "该租户没有配置检索索引；检索能力不可用",
            )
        # 上下文是**必需**的：文件/层级这些维度必须由调用方显式声明，服务端不推断，
        # 也不允许"没有上下文就按租户默认集合检索"（那等于把边界交给服务端猜）。
        context = _context_from_dto(
            request.context,
            auth,
            tenant,
            request_id=request.request_id,
            trace_id=request.trace_id,
            runtime_config=self.config,
        )

        from retrieval.context import ContextBuilder
        from retrieval.models import AccessScope, RetrievalQuery
        from retrieval.retriever import FtsRetriever

        corpus_policy = loaded.policy  # LoadedCorpus.policy 是属性，不是方法
        scope = AccessScope(
            subject=auth.subject,
            datasets=frozenset(item.name for item in loaded.manifest.datasets),
            allow_restricted=False,
        )
        # query 可以缺省：那时用上下文里的 task 作为查询文本（`from_context` 的默认行为）。
        query = RetrievalQuery.from_context(context, text=request.query, limit=request.limit)

        def work() -> Tuple[Any, Any, Any]:
            from retrieval.store import ChunkStore, StoreError

            # `create=False` 是**失败关闭**的一部分：默认的 create=True 会把"索引文件不见了"
            # 悄悄重建成一个空库，检索于是返回 empty/no_results——那会被读成
            # "查过了，规范里没有"，而事实是"索引没了"。索引是构建产物，服务只读它。
            try:
                store = ChunkStore(tenant.store_path, create=False)  # type: ignore[arg-type]
            except StoreError as error:
                raise ApiError(
                    ErrorCode.KNOWLEDGE_UNAVAILABLE,
                    f"租户 {auth.tenant} 的检索索引不存在；请先运行 "
                    f"python -m retrieval.cli index（检索不可用时不得回退到模型记忆）",
                    retryable=True,
                ) from error
            with store:
                retriever = FtsRetriever(
                    store, policy=corpus_policy, lexicon=tenant.lexicon()
                )
                retrieval = retriever.retrieve(query, scope)
                builder = ContextBuilder.from_policy(corpus_policy)
                engineering = builder.build(
                    retrieval=retrieval,
                    policy_facts=policy_facts,
                    query=query.text or "",
                    request_id=request.request_id,
                    trace_id=request.trace_id,
                )
                return retrieval, engineering, store.stats()

        outcome, elapsed = run_with_budget(work, budget_ms=budget_ms, clock=self.clock)
        if outcome is None:
            self.metrics.count_timeout()
            raise ApiError(
                ErrorCode.RETRIEVE_TIMEOUT,
                f"检索超出预算 {budget_ms}ms；未返回片段（不回退到模型记忆）",
                retryable=True,
            )
        retrieval, engineering, stats = outcome
        body: dict[str, Any] = {
            "api_version": API_SCHEMA_VERSION,
            "tenant": auth.tenant,
            "status": retrieval.status.value,
            "reason": None if retrieval.reason is None else retrieval.reason.value,
            "detail": retrieval.detail,
            "query": retrieval.query,
            "plan": None if retrieval.plan is None else retrieval.plan.model_dump(mode="json"),
            "method": retrieval.method.value,
            "hits": [_chunk_payload(item) for item in retrieval.results],
            "context": _context_payload(engineering),
            "policy_facts": [item.model_dump(mode="json") for item in policy_facts],
            "index": {
                "database": tenant.store_path.name,
                "index_version": retrieval.index_version,
                "generation": int(getattr(stats, "generation", 0) or 0),
                "corpus_input_hash": getattr(stats, "corpus_input_hash", None),
                "hash_drift": sorted(
                    f"{issue.dataset}:{issue.source_path}"
                    for issue in loaded.verification.drift
                ),
                "documents": int(getattr(stats, "documents", 0) or 0),
                "chunks": int(getattr(stats, "chunks", 0) or 0),
                "quarantined": int(getattr(stats, "quarantined", 0) or 0),
            },
            "timing": {"budget_ms": budget_ms, "elapsed_ms": int(elapsed.milliseconds)},
            "available": bool(engineering.is_available),
        }
        # 三个显式状态各有自己的 HTTP 语义（AGENTS 约束 11）：
        #   ok       → 200（有命中）
        #   empty    → 200 + status/reason（查询合法但确实没有命中，客户端看 reason）
        #   unavailable → 503 knowledge_unavailable（索引/语料/检索本身不可用，绝不降级成"没有结果"）
        if retrieval.status.value == "unavailable":
            raise ApiError(
                ErrorCode.KNOWLEDGE_UNAVAILABLE,
                f"{retrieval.reason.value if retrieval.reason else 'unavailable'}："
                f"{retrieval.detail or '检索不可用'}",
                retryable=True,
            )
        facts = {"index_version": retrieval.index_version, "decision": "", "violations": 0}
        return 200, body, facts

    def _policy_facts(
        self, tenant: LoadedTenant, auth: AuthContext, decision_ref: Optional[str]
    ) -> Tuple[Any, ...]:
        """检索的授权事实只来自**本服务算过的决策**，客户端不能自带决策载荷。"""

        if not decision_ref:
            return ()
        with self._decisions_lock:
            result = self._decisions.get(_decision_key(auth.tenant, decision_ref))
        if result is None:  # noqa: SIM108 - 保持显式分支，便于阅读状态机
            raise ApiError(
                ErrorCode.FORBIDDEN,
                "decision_ref 指向的决策不在本服务上；拒绝用未经验证的决策扩权",
            )
        current = tenant.rule_set_hash()
        if result.rule_set_hash and current and result.rule_set_hash != current:
            raise ApiError(
                ErrorCode.FORBIDDEN,
                "规则集在两次调用之间发生了变化；请重新 evaluate 后再检索",
            )
        from retrieval.models import PolicyFact

        facts: dict[str, Any] = {}
        for violation in result.violations:
            identity = violation.canonical_id
            facts[identity] = PolicyFact(
                rule_id=identity,
                severity=violation.severity.value,
                message=violation.message,
                source_path=violation.evidence.file,
            )
        return tuple(facts[key] for key in sorted(facts))

    # ------------------------------------------------------------------ validate

    def _validate(
        self, payload: Mapping[str, Any], auth: AuthContext
    ) -> Tuple[int, Mapping[str, Any], Mapping[str, Any]]:
        request = ValidationRequest.model_validate(dict(payload))
        tenant = self.store.get(auth.tenant)
        budget_ms = budget_for("validate", self.config, request.budget_ms)
        context = _context_from_dto(
            request.context,
            auth,
            tenant,
            request_id=request.request_id,
            trace_id=request.trace_id,
            runtime_config=self.config,
        )
        rules = tenant.rules()
        config = tenant.validators()
        target = request.target or context.file

        from validators.pipeline import PipelineRequest, run_pipeline

        pipeline_request = PipelineRequest(
            target=target,
            workspace=tenant.project_root,
            context=context,
            rules=rules,
            changed_files=tuple(request.changed),
            only=tuple(request.only),
        )

        def work() -> Any:
            return run_pipeline(pipeline_request, config=config)

        report, elapsed = run_with_budget(work, budget_ms=budget_ms, clock=self.clock)
        if report is None:
            self.metrics.count_timeout()
            raise ApiError(
                ErrorCode.VALIDATE_TIMEOUT,
                f"验证器流水线超出预算 {budget_ms}ms；未产出证据（不把缺失当通过）",
                retryable=True,
            )
        result = evaluate(rules, context, evidence=report.bundle) if request.include_decision else None
        report_payload = dict(report.to_payload())
        truncated = 0
        evidence_items = list(report_payload.get("evidence") or [])
        limit = _evidence_limit(self.config)
        if len(evidence_items) > limit:
            truncated = len(evidence_items) - limit
            report_payload["evidence"] = evidence_items[:limit]
        body: dict[str, Any] = {
            "api_version": API_SCHEMA_VERSION,
            "tenant": auth.tenant,
            "report": report_payload,
            "blockers": [item.model_dump(mode="json") for item in report.blockers],
            "truncated_evidence": truncated,
            "timing": {"budget_ms": budget_ms, "elapsed_ms": int(elapsed.milliseconds)},
        }
        facts: dict[str, Any] = {}
        if result is not None:
            body["decision"] = _decision_payload(result)
            body["summary"] = {
                "decision": result.decision.value,
                "violations": len(result.violations),
                "matched": len(result.matched_rules),
                "skipped": len(result.skipped_rules),
            }
            facts = {
                "decision": result.decision.value,
                "rule_set_hash": result.rule_set_hash,
                "violations": len(result.violations),
            }
        return 200, body, facts

    # ------------------------------------------------------------------ 运维

    def _metrics(self, auth: AuthContext) -> Tuple[int, Mapping[str, Any], Mapping[str, Any]]:
        from .ops import metrics_token_ok

        if not metrics_token_ok(self.config, auth):
            # 不透露"是否存在指标"以外的任何信息，也没有第二个错误形状。
            raise ApiError(ErrorCode.METRICS_FORBIDDEN, "该凭据没有读取指标的权限")
        body = {
            "api_version": API_SCHEMA_VERSION,
            "service": self.config.service_name,
            "deployment": self.config.deployment,
            "metrics": self.metrics.to_payload(),
            "rate_limit": self.rate_limiter.snapshot(),
            "tenants": list(self.store.ids),
            "readiness": self.readiness(),
        }
        return 200, body, {}

    # ------------------------------------------------------------------ readiness

    def readiness(self, *, force: bool = False) -> Mapping[str, Any]:
        """缓存 readiness 结论（TTL 内复用），避免每个探针都重新加载规则集。"""

        now = self.clock()
        with self._readiness_lock:
            if (
                not force
                and self._readiness is not None
                and now - self._readiness[0] < self.readiness_ttl_seconds
            ):
                return dict(self._readiness[1])
        report = self._readiness_report()
        with self._readiness_lock:
            self._readiness = (now, dict(report), 0)
        return report

    def _readiness_report(self) -> Mapping[str, Any]:
        from .ops import readiness_report

        return readiness_report(self)

    # ------------------------------------------------------------------ 记录

    def _record(
        self,
        *,
        route: str,
        outcome: str,
        status: int,
        started: float,
        auth: Optional[AuthContext],
        request_id: str,
        trace_id: Optional[str],
        project: str,
        decision: str,
        error: str,
        replayed: bool,
        rule_set_hash: Optional[str],
        index_version: Optional[str],
        violations: int,
    ) -> None:
        elapsed_ms = int((self.clock() - started) * 1000)
        self.metrics.observe(
            route=route,
            outcome=outcome,
            status=status,
            elapsed_ms=float(elapsed_ms),
            decision=decision or None,
        )
        entry = RequestLogEntry(
            route=route,
            outcome=outcome,
            status=status,
            request_id=request_id,
            trace_id=trace_id,
            tenant="" if auth is None else auth.tenant,
            project=project,
            client_id="" if auth is None else auth.client_id,
            subject="" if auth is None else auth.subject,
            token_ref="" if auth is None else auth.token_ref,
            decision=decision,
            error=error,
            elapsed_ms=elapsed_ms,
            rule_set_hash=rule_set_hash,
            index_version=index_version,
            violations=violations,
            replayed=replayed,
        )
        self.request_log.append(entry)

    @staticmethod
    def _idempotency_key(payload: Mapping[str, Any]) -> Optional[str]:
        value = payload.get("idempotency_key")
        return None if value is None else str(value)

    @staticmethod
    def _payload_for(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """台账与摘要里保存的载荷：**去掉凭据**（令牌永不落盘）。"""

        return {key: value for key, value in payload.items() if key not in ("credentials",)}


def _principal_field(payload: Mapping[str, Any], name: str) -> Any:
    principal = payload.get("principal")
    if isinstance(principal, Mapping):
        return principal.get(name)
    return None


def _canonical_body(body: Mapping[str, Any]) -> Mapping[str, Any]:
    """把响应体规范化成"可以直接当字节比较"的一份（键序稳定）。

    只用于**幂等键的响应**：第一次与重放会返回同一份字节。没有幂等键的请求保持原有键序
    （响应形状本来就是受控 JSON，键序不属于契约）。
    """

    return json.loads(json.dumps(dict(body), ensure_ascii=False, sort_keys=True))


def _decision_key(tenant: str, request_id: str) -> str:
    return f"{tenant}:{request_id}"


def _recordable(status: int, facts: Mapping[str, Any]) -> bool:
    """可重放的结论才落台账：超时 / 忙碌 / 内部错误不落，"重试看的还是同一个失败"没有意义。"""

    if status in (429, 500, 503, 504):
        return False
    return True


def _chunk_payload(chunk: Any) -> dict[str, Any]:
    """检索命中：字段原样 + `citation` / `citation_source`（它们是属性，不在 model_dump 里）。

    引用必须**开箱可用**：否则每个消费方都要自己拼一次引用格式，而"拼错了"
    就等于把来源标注做成了形式上存在、实际上不可追溯的东西。
    """

    payload = dict(chunk.model_dump(mode="json"))
    payload["citation"] = f"[{payload.get('chunk_id')}]"
    payload["citation_source"] = str(getattr(chunk, "citation_source", payload.get("source_path", "")))
    return payload


def _context_payload(context: Any) -> dict[str, Any]:
    """Engineering Context：显式给出检索状态与引用列表（模型属性不会进 model_dump）。"""

    payload = dict(context.model_dump(mode="json"))
    payload["available"] = bool(getattr(context, "is_available", False))
    payload["citations"] = list(getattr(context, "citations", ()))
    payload["citation_count"] = len(payload["citations"])
    return payload


def _describe_validation(error: ValidationError) -> str:
    """把 pydantic 校验失败压成一行：字段位置 + 原因（不吐内部结构）。"""

    parts: list[str] = []
    for item in error.errors()[:5]:
        location = ".".join(str(part) for part in item.get("loc", ()))
        parts.append(f"{location or 'body'}: {item.get('msg')}")
    if len(error.errors()) > 5:
        parts.append(f"另有 {len(error.errors()) - 5} 处错误")
    return "; ".join(parts) or "请求体不合法"


def _evidence_limit(config: ApiConfig) -> int:
    return max(1, config.limits.max_response_bytes // 512)


def load_runtime_config(path: Path | str, *, root: Optional[Path | str] = None) -> ApiConfig:
    """便捷函数：加载配置并把 `ConfigError` 原样抛出（CLI 负责翻译成退出码）。"""

    try:
        return load_api_config(path, root=root)
    except ConfigError:
        raise
