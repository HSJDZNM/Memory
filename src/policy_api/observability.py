"""可观测性：请求级 JSONL 与进程内指标。默认**不记录**原文。

记录什么：request_id / trace_id / 主体 / 租户 / 客户端 / 规则集哈希 / 索引版本 /
Decision / 耗时 / 错误分类 / 状态码。
不记录什么：完整 Prompt、文档正文、原始工具参数、令牌、绝对路径、控制字符。

落盘复用 Phase 4 已经验证过的脱敏实现（`enforcement.audit.redact_text` /
`sanitize_payload`）：密钥样式、绝对路径、控制字符、超长文本在那里都处理过，
Phase 7 再写一份"看起来差不多"的正则只会多一个漂移点。

**失败关闭**：日志不可写时请求以 `audit_unavailable`（503）失败——"决定记不下来"
就不返回决定。这与 Phase 4 的 "受治理动作在审计不可写时不执行" 是同一条纪律。
"""

from __future__ import annotations

import hashlib
import json
import statistics
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

from enforcement.audit import redact_text, sanitize_payload

from .errors import ApiError, ErrorCode

__all__ = [
    "REQUEST_LOG_SCHEMA_VERSION",
    "Latency",
    "Metrics",
    "RequestLog",
    "RequestLogEntry",
    "seal_audit",
    "verify_seal",
]

REQUEST_LOG_SCHEMA_VERSION = "1.0"
_MAX_RECORD_BYTES = 16384


def _utc_now() -> str:
    import datetime as clock

    return clock.datetime.now(clock.timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class RequestLogEntry:
    """一条请求记录（已脱敏）。字段是固定的：新增字段要一起改测试与文档。"""

    route: str
    outcome: str
    status: int
    request_id: str = ""
    tenant: str = ""
    project: str = ""
    client_id: str = ""
    subject: str = ""
    token_ref: str = ""
    decision: str = ""
    error: str = ""
    elapsed_ms: int = 0
    rule_set_hash: Optional[str] = None
    index_version: Optional[str] = None
    violations: int = 0
    trace_id: Optional[str] = None
    replayed: bool = False

    def to_payload(
        self, *, workspace: Optional[Path] = None, secrets: Sequence[str] = ()
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "log_schema_version": REQUEST_LOG_SCHEMA_VERSION,
            "timestamp": _utc_now(),
            "route": self.route,
            "outcome": self.outcome,
            "status": self.status,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "tenant": self.tenant,
            "project": self.project,
            "client_id": self.client_id,
            "subject": self.subject,
            "token_ref": self.token_ref,
            "decision": self.decision,
            "violations": self.violations,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "rule_set_hash": self.rule_set_hash,
            "index_version": self.index_version,
            "replayed": self.replayed,
        }
        clean = sanitize_payload(payload, workspace=workspace)
        if secrets:
            clean = _scrub_secrets(clean, secrets)
        return clean  # type: ignore[return-value]


def _scrub_secrets(value: Any, secrets: Sequence[str]) -> Any:
    """把**已知凭据的原文**从任意字段里抹掉。

    为什么需要它（独立验证者发现的真实缺陷）：`redact_text` 认的是"凭据长什么样"
    （`token=…` / `Bearer …` / `sk-…`），而自由文本字段是**客户端可控**的——
    调用方把令牌回显进 `request_id` 或 `principal.subject`，原文就会原样落盘。
    这里改成按值精确替换：只要某段文本等于我们认识的凭据，它就永远不进日志。
    凭据本身只在内存里传递（配置里存的是 sha256），不写盘、不进响应。
    """

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        cleaned = value
        for secret in secrets:
            if secret and secret in cleaned:
                cleaned = cleaned.replace(secret, "<redacted-token>")
        return cleaned
    if isinstance(value, Mapping):
        return {key: _scrub_secrets(item, secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_scrub_secrets(item, secrets) for item in value]
    return value


class RequestLog:
    """追加写的请求日志。写入失败即失败关闭（调用方翻译成 503）。"""

    def __init__(
        self,
        path: Optional[Path | str],
        *,
        enabled: bool = True,
        workspace: Optional[Path | str] = None,
    ) -> None:
        self.path = None if path is None else Path(path)
        self.enabled = bool(enabled)
        self.workspace = None if workspace is None else Path(workspace)
        # 已知凭据的原文：调用方每加一个就登记一次（`register_secret`）。
        self._secrets: set[str] = set()
        self._lock = threading.RLock()
        self._written: list[dict[str, Any]] = []

    def register_secret(self, value: Optional[str]) -> None:
        """登记一个"绝不允许出现在日志里"的字符串（令牌原文）。只留在内存。"""

        if value:
            with self._lock:
                self._secrets.add(value)

    @property
    def secrets(self) -> Tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._secrets))

    @property
    def active(self) -> bool:
        return self.enabled and self.path is not None

    def append(self, entry: RequestLogEntry) -> None:
        payload = entry.to_payload(workspace=self.workspace, secrets=self.secrets)
        try:
            line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as error:
            raise ApiError(
                ErrorCode.AUDIT_UNAVAILABLE,
                f"请求日志记录无法序列化（{type(error).__name__}）",
            ) from error
        if len(line.encode("utf-8")) > _MAX_RECORD_BYTES:
            raise ApiError(
                ErrorCode.AUDIT_UNAVAILABLE,
                "请求日志记录超过单条上限；拒绝写入半截证据",
            )
        with self._lock:
            self._written.append(payload)
            if not self.active:
                if not self.enabled:
                    raise ApiError(
                        ErrorCode.AUDIT_UNAVAILABLE,
                        "请求日志被显式禁用；按失败策略拒绝返回决定",
                    )
                return  # 只保留在内存里：仅用于测试与 --dry-run
            assert self.path is not None
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(line + "\n")
                    handle.flush()
            except OSError as error:
                raise ApiError(
                    ErrorCode.AUDIT_UNAVAILABLE,
                    f"请求日志不可写（{type(error).__name__}）",
                    retryable=True,
                ) from error

    def entries(self) -> Tuple[Mapping[str, Any], ...]:
        with self._lock:
            return tuple(dict(item) for item in self._written)

    def read_back(self) -> Tuple[Mapping[str, Any], ...]:
        """把落盘内容读回来（CI 与闭环用它证明"决定确实被记下来了"）。"""

        if self.path is None or not self.path.is_file():
            return ()
        rows: list[Mapping[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, Mapping):
                rows.append(item)
        return tuple(rows)

    # ------------------------------------------------------------------ 外部锚定

    def chain_digest(self) -> Optional[str]:
        """从第一条记录开始的**摘要链**末值；没有记录时返回 None。

        每条记录的摘要覆盖上一条的摘要，因此：
        - 改动任何一条中间记录 / 删除尾部记录 → 末值与已发布的锚不一致；
        - 重写整条链 → 末值同样变（除非攻击者能改锚本身）。

        它仍然**不是**防篡改日志：锚一旦和日志放在同一个可写位置就失去意义。
        Phase 7 提供的正是"把末值发布到外部"这件事所需的那一个值。
        """

        rows = self.read_back()
        if not rows:
            return None
        digest = ""
        for index, row in enumerate(rows, start=1):
            payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            digest = hashlib.sha256(
                f"p7:{index}:{digest}:{payload}".encode("utf-8")
            ).hexdigest()
        return "sha256:" + digest

    def summary(self) -> Mapping[str, Any]:
        rows = self.read_back()
        return {
            "records": len(rows),
            "chain_digest": self.chain_digest(),
            "first_request_id": str(rows[0].get("request_id") or "") if rows else "",
            "last_request_id": str(rows[-1].get("request_id") or "") if rows else "",
        }


@dataclass
class Latency:
    """延迟分布：只保留原始毫秒样本（上限内），p50/p95/p99 由样本算出。"""

    max_samples: int = 4096
    samples: list[float] = field(default_factory=list)

    def observe(self, milliseconds: float) -> None:
        self.samples.append(float(milliseconds))
        if len(self.samples) > self.max_samples:
            del self.samples[: len(self.samples) - self.max_samples]

    @property
    def count(self) -> int:
        return len(self.samples)

    def percentile(self, value: float) -> Optional[float]:
        if not self.samples:
            return None
        ordered = sorted(self.samples)
        if len(ordered) == 1:
            return round(ordered[0], 3)
        index = min(len(ordered) - 1, max(0, int(round((value / 100.0) * (len(ordered) - 1)))))
        return round(ordered[index], 3)

    def mean(self) -> Optional[float]:
        return round(statistics.fmean(self.samples), 3) if self.samples else None

    def to_payload(self) -> Mapping[str, Any]:
        return {
            "count": self.count,
            "mean_ms": self.mean(),
            "p50_ms": self.percentile(50),
            "p95_ms": self.percentile(95),
            "p99_ms": self.percentile(99),
            "max_ms": round(max(self.samples), 3) if self.samples else None,
        }


class Metrics:
    """进程内指标：计数、延迟分位、限流与超时分类。没有外部后端也不假装有。"""

    def __init__(self, *, clock: Any = time.monotonic) -> None:
        self.clock = clock
        self.started = clock()
        self._lock = threading.RLock()
        self._by_route: dict[str, dict[str, Any]] = {}
        self._decisions: dict[str, int] = {}
        self._code_classes: dict[str, int] = {}
        self._outcomes: dict[str, int] = {}
        self.rate_limited = 0
        self.budget_exceeded = 0
        self.timeouts = 0
        self.replays = 0

    def observe(
        self,
        *,
        route: str,
        outcome: str,
        status: int,
        elapsed_ms: float,
        decision: Optional[str] = None,
    ) -> None:
        with self._lock:
            bucket = self._by_route.setdefault(
                route, {"requests": 0, "errors": 0, "latency": Latency()}
            )
            bucket["requests"] += 1
            if status >= 400:
                bucket["errors"] += 1
            bucket["latency"].observe(elapsed_ms)
            self._code_classes[f"{status // 100}xx"] = self._code_classes.get(f"{status // 100}xx", 0) + 1
            self._outcomes[outcome] = self._outcomes.get(outcome, 0) + 1
            if decision:
                self._decisions[decision] = self._decisions.get(decision, 0) + 1

    def count_rate_limited(self) -> None:
        with self._lock:
            self.rate_limited += 1

    def count_budget_exceeded(self) -> None:
        with self._lock:
            self.budget_exceeded += 1

    def count_timeout(self) -> None:
        with self._lock:
            self.timeouts += 1

    def count_replay(self) -> None:
        with self._lock:
            self.replays += 1

    def to_payload(self) -> Mapping[str, Any]:
        with self._lock:
            return {
                "uptime_seconds": round(self.clock() - self.started, 3),
                "routes": {
                    route: {
                        "requests": bucket["requests"],
                        "errors": bucket["errors"],
                        **bucket["latency"].to_payload(),
                    }
                    for route, bucket in sorted(self._by_route.items())
                },
                "decisions": dict(sorted(self._decisions.items())),
                "status_classes": dict(sorted(self._code_classes.items())),
                "outcomes": dict(sorted(self._outcomes.items())),
                "rate_limited": self.rate_limited,
                "budget_exceeded": self.budget_exceeded,
                "timeouts": self.timeouts,
                "replays": self.replays,
            }


def redacted(value: Any, *, limit: int = 240) -> str:
    """把任意文本压成可安全落盘的一行（日志字段用）。"""

    return redact_text(str(value), limit=limit)


def seal_audit(log: RequestLog) -> Mapping[str, Any]:
    """把观测日志的链末值封成一份可对外发布的锚（JSON）。

    用法：`python -m policy_api.cli seal --out anchor.json`，然后把这个文件放到
    日志写不到的地方（对象存储、工单、另一台主机）。之后用
    `python -m policy_api.cli seal --verify anchor.json` 检查日志是否被动过。
    """

    payload = {
        "seal_schema_version": "1.0",
        "sealed_at": _utc_now(),
        **log.summary(),
        "log_path": None if log.path is None else log.path.name,
    }
    return payload


def verify_seal(log: RequestLog, seal: Mapping[str, Any]) -> Tuple[str, ...]:
    """校验锚与当前日志是否一致；返回问题列表（空 = 一致）。"""

    issues: list[str] = []
    if seal.get("seal_schema_version") != "1.0":
        issues.append("锚的协议版本未知；拒绝按不确定的语义校验")
    current = log.summary()
    if int(seal.get("records", -1)) != current["records"]:
        issues.append(
            f"记录数不一致：锚 {seal.get('records')} / 当前 {current['records']}"
            "（尾部被删或被追加）"
        )
    if seal.get("chain_digest") != current["chain_digest"]:
        issues.append("链末值与锚不一致（日志被改动或整链被重写）")
    return tuple(issues)
