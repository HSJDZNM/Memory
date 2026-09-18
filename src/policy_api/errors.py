"""API 错误分类：固定枚举 + 固定状态码，错误响应不泄露资源是否存在。

设计要点：

- 错误码是**受控枚举**（`ErrorCode`），不是随手写的字符串：客户端可以据此编程，
  而我们不会因为某个分支随手 new 一个字符串就把错误空间变成无界的；
- 状态码由错误码**推导**（`STATUS_BY_CODE`），调用方不能自定义 HTTP 状态：
  "认证失败"永远是 401，"跨租户/不存在"永远是 404（两者刻意同码，避免用错误码探测
  某个规则集或索引是否存在）；
- 消息一律由服务端生成，不透传异常的 str()：异常文本里可能带绝对路径或内部配置名。
  `detail` 只允许写"调用方需要知道才能改请求"的内容。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

__all__ = [
    "STATUS_BY_CODE",
    "ApiError",
    "ErrorCode",
    "error_payload",
    "redact_detail",
]


class ErrorCode(str, Enum):
    """受控错误码。新增一个码就要同时给它一个状态码（见 STATUS_BY_CODE）。"""

    # --- 请求协议 ---
    SCHEMA_VERSION_MISSING = "schema_version_missing"
    SCHEMA_VERSION_UNKNOWN = "schema_version_unknown"
    BODY_INVALID = "body_invalid"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    BODY_TOO_LARGE = "body_too_large"
    CONTEXT_INVALID = "context_invalid"
    QUERY_INVALID = "query_invalid"
    TARGET_INVALID = "target_invalid"
    # --- 认证与授权 ---
    UNAUTHENTICATED = "unauthenticated"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_SCOPE_MISMATCH = "token_scope_mismatch"
    FORBIDDEN = "forbidden"
    TENANT_NOT_FOUND = "tenant_not_found"
    PROJECT_NOT_ALLOWED = "project_not_allowed"
    # --- 幂等与限流 ---
    IDEMPOTENCY_KEY_MISSING = "idempotency_key_missing"
    IDEMPOTENCY_KEY_CONFLICT = "idempotency_key_conflict"
    IDEMPOTENCY_UNAVAILABLE = "idempotency_unavailable"
    RATE_LIMITED = "rate_limited"
    REQUEST_BUDGET_EXCEEDED = "request_budget_exceeded"
    # --- 下游 / 依赖 ---
    EVALUATE_TIMEOUT = "evaluate_timeout"
    RETRIEVE_TIMEOUT = "retrieve_timeout"
    VALIDATE_TIMEOUT = "validate_timeout"
    KNOWLEDGE_UNAVAILABLE = "knowledge_unavailable"
    EVIDENCE_UNAVAILABLE = "evidence_unavailable"
    VALIDATOR_UNAVAILABLE = "validator_unavailable"
    RULE_SET_UNAVAILABLE = "rule_set_unavailable"
    POLICY_BUSY = "policy_busy"
    # --- 服务自身 ---
    POLICY_UNAVAILABLE = "policy_unavailable"
    AUDIT_UNAVAILABLE = "audit_unavailable"
    METRICS_FORBIDDEN = "metrics_forbidden"
    INTERNAL_ERROR = "internal_error"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"


# 错误码 → HTTP 状态。跨租户与"不存在"共用 404：错误码本身不能成为存在的探针。
STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.SCHEMA_VERSION_MISSING: 400,
    ErrorCode.SCHEMA_VERSION_UNKNOWN: 400,
    ErrorCode.BODY_INVALID: 400,
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: 415,
    ErrorCode.BODY_TOO_LARGE: 413,
    ErrorCode.CONTEXT_INVALID: 400,
    ErrorCode.QUERY_INVALID: 400,
    ErrorCode.TARGET_INVALID: 400,
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.TOKEN_EXPIRED: 401,
    ErrorCode.TOKEN_SCOPE_MISMATCH: 403,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.TENANT_NOT_FOUND: 404,
    ErrorCode.PROJECT_NOT_ALLOWED: 403,
    ErrorCode.IDEMPOTENCY_KEY_MISSING: 400,
    ErrorCode.IDEMPOTENCY_KEY_CONFLICT: 409,
    ErrorCode.IDEMPOTENCY_UNAVAILABLE: 503,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.REQUEST_BUDGET_EXCEEDED: 503,
    ErrorCode.EVALUATE_TIMEOUT: 504,
    ErrorCode.RETRIEVE_TIMEOUT: 504,
    ErrorCode.VALIDATE_TIMEOUT: 504,
    ErrorCode.KNOWLEDGE_UNAVAILABLE: 503,
    ErrorCode.EVIDENCE_UNAVAILABLE: 503,
    ErrorCode.VALIDATOR_UNAVAILABLE: 503,
    ErrorCode.RULE_SET_UNAVAILABLE: 503,
    ErrorCode.POLICY_BUSY: 503,
    ErrorCode.POLICY_UNAVAILABLE: 503,
    ErrorCode.AUDIT_UNAVAILABLE: 503,
    ErrorCode.METRICS_FORBIDDEN: 403,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.METHOD_NOT_ALLOWED: 405,
}

_MAX_DETAIL_CHARS = 240


def redact_detail(text: str) -> str:
    """错误细节只保留单行、限量、无控制字符的文本（不透传异常原文）。"""

    cleaned = " ".join(str(text).split())
    if len(cleaned) > _MAX_DETAIL_CHARS:
        cleaned = cleaned[: _MAX_DETAIL_CHARS - 1] + "…"
    return cleaned


@dataclass(eq=False)
class ApiError(Exception):
    """API 层的显式失败。绝不用于"默认放行"路径：构造它就意味着请求被拒绝。

    刻意**不是 frozen**：CPython 在抛出异常时会往实例上写 `__traceback__`，
    frozen dataclass 会因此抛 `FrozenInstanceError`，把"一个结构化 409"变成
    "一个 500"——错误分类被数据类装饰器吃掉，是最难查的一类退化。
    `eq=False` 保留异常的身份语义（按对象比较，避免 value-equality 干扰 except 分支）。
    """

    code: ErrorCode
    detail: str = ""
    retryable: bool = False
    # 仅供**本地诊断**：CLI / 闭环工具打印用，绝不进 HTTP 响应体（error_payload 只取
    # code/detail/retryable）。把它带在异常上，是为了让"内部错误"能被查清楚，
    # 而不是只留下一句"internal_error"。
    debug: str = ""

    def __post_init__(self) -> None:
        # Exception 的 __init__ 不参与 dataclass 生成，这里显式补上一次，日志里才有可读文本。
        Exception.__init__(self, f"{self.code.value}: {self.detail}" if self.detail else self.code.value)

    @property
    def status(self) -> int:
        return STATUS_BY_CODE[self.code]

    @property
    def kind(self) -> str:
        return self.code.value


def error_payload(
    error: ApiError, *, request_id: Optional[str] = None, trace_id: Optional[str] = None
) -> dict[str, object]:
    """错误响应的唯一形状：固定字段 + 受控错误码 + 受控细节。"""

    return {
        "error": {
            "code": error.kind,
            "detail": redact_detail(error.detail),
            "retryable": error.retryable,
            "request_id": request_id,
            "trace_id": trace_id,
        }
    }
