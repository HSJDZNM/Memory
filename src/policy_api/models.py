"""API DTO：传输协议与领域模型之间的**显式**边界。

为什么要单独一份模型（而不是直接把 PolicyContext 暴露成请求体）：

1. **防止传输字段污染核心**：`trace_id`、`budget_ms`、`idempotency_key` 属于传输层，
   核心的 PolicyContext 不认识它们；核心改字段也不该自动变成线上协议的变化。
2. **两套版本各自演进**：`API_SCHEMA_VERSION` 是**传输协议**版本，
   `policy.models.SCHEMA_VERSION` 是**决策载荷**版本。改 API 的载荷（含**加键**）
   是新 API 版本，不是新决策协议；改规则语义是决策协议的事，与 API 版本无关。
   统一规则（AGENTS.md 第 31 条，"任何协议载荷加键或改语义都按该协议自己的版本号递增"）
   比本包原先只写"删字段或改语义"的口径更严：**加键也要升版**，所以"只增不改"的改动
   在这里同样是一次 API 协议变更，不是"顺手加一个字段"。
3. **未知字段一律报错**：`extra="forbid"` + 未知版本拒绝，与核心层同一条纪律。

请求体做成**信封**形态（`api_version` / `credentials` / `request_id` / `trace_id` /
`budget_ms` / `idempotency_key` / `payload`），于是认证、幂等、预算这些横切关注点
在每个路由上是同一种形状，而不是各自一套。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, Optional, Tuple

from pydantic import Field, field_validator, model_validator

from policy.models import (
    POLICY_VERSION,
    SCHEMA_VERSION,
    Operation,
    StrictModel,
    canonical_identifier,
    normalize_repo_path,
)

from .errors import ApiError, ErrorCode

__all__ = [
    "API_SCHEMA_VERSION",
    "CONTEXT_FIELDS",
    "DECISION_PAYLOAD_SCHEMA_VERSION",
    "READINESS_STATES",
    "SUPPORTED_API_SCHEMA_VERSIONS",
    "ApiEnvelope",
    "ContextDTO",
    "Credentials",
    "DecisionSummary",
    "EvaluateRequest",
    "IndexIdentity",
    "PrincipalDTO",
    "ReadinessReport",
    "ReadinessState",
    "RetrieveRequest",
    "ValidationRequest",
    "envelope_of",
    "principal_of",
]

# 传输协议版本。与决策协议（policy.models.SCHEMA_VERSION）**无关**，各自演进。
API_SCHEMA_VERSION = "1.0"
SUPPORTED_API_SCHEMA_VERSIONS = frozenset({API_SCHEMA_VERSION})

# 决策载荷的协议世代名：与 `policy.models.POLICY_VERSION` 同进同退（本包不自己算一个）。
DECISION_PAYLOAD_SCHEMA_VERSION = SCHEMA_VERSION
POLICY_GENERATION = POLICY_VERSION


class Credentials(StrictModel):
    """认证凭据。**绝不**写进日志：观测层只记 sha256 前 12 位。"""

    scheme: str = "bearer"
    # `repr=False`：这条承诺必须在**声明密钥的地方**成立，而不是只靠调用方自觉（落盘前剥离
    # `credentials` 是 `runtime._payload_for` 里的模型外补丁）。没有换成 SecretStr 是因为它
    # 要求每个使用点显式 `get_secret_value()`——改一个类型就得多改认证边界；而 repr=False
    # 已经关掉了最现实的那条路：`logger.info("%s", request)` / `repr(model)` / 捕获局部变量的
    # 错误上报 / traceback 里的模型表示。
    # 注：理由写在这里而不是类 docstring 里——docstring 会作为 description 进 OpenAPI 快照，
    # 一句注释不该造成一次"契约变化"。
    token: str = Field(min_length=8, max_length=512, repr=False)


class PrincipalDTO(StrictModel):
    """主体声明：只由调用方显式提供，服务端不从路径或载荷推断。

    声明出来的 subject 由 `runtime._authenticate` 交给 `authorize`（认证主体），roles 则**只**
    来自令牌（`ClientSpec.roles`）——载荷声明的 roles 不参与授权。

    以前这里还有一个 `to_domain()`：全仓没有任何调用点，而它会把载荷声明的 roles 变成核心的
    `Principal`——那正好是"客户端自带决策"的入口。删掉它，DTO 不再承诺一次从未发生的转换
    （`ContextDTO.to_context_payload()` 不产出 principal 键；API 路径上也没有消费
    `PolicyContext.principal` 的代码，多角色 Agent 路径的 principal 由 Adapter 的装配声明给出）。
    """

    subject: str = Field(min_length=1, max_length=200)
    roles: Tuple[str, ...] = ()

    @field_validator("subject")
    @classmethod
    def _subject_is_meaningful(cls, value: str) -> str:
        """空白不是主体：`" "` 满足 min_length=1，但它不是"谁在调用"——它会进日志与证据，
        却永远对不上任何一个真实调用者。去空白后仍为空即拒绝。
        """

        normalized = value.strip()
        if not normalized:
            raise ValueError("subject 不能是空白")
        return normalized

    @field_validator("roles", mode="before")
    @classmethod
    def _normalize_roles(cls, value: Any) -> Any:
        if value is None:
            return ()
        if isinstance(value, str):
            raise TypeError("roles 必须是序列，不能是字符串")
        if isinstance(value, (list, tuple, set, frozenset)):
            return tuple(sorted({canonical_identifier(str(item)) for item in value if str(item).strip()}))
        return value


class ContextDTO(StrictModel):
    """PolicyContext 的线上形态：字段与核心一一对应，但允许未来独立演进。"""

    file: str
    layer: str
    language: Optional[str] = None
    module: Optional[str] = None
    operation: Optional[Operation] = None
    file_operation: Optional[str] = None
    task: Optional[str] = None
    dependencies: Tuple[str, ...] = ()
    git_diff: Optional[str] = None
    project: Optional[str] = None
    agent: Optional[str] = None

    @model_validator(mode="after")
    def _one_operation_field(self) -> "ContextDTO":
        if self.operation is not None and self.file_operation is not None:
            raise ValueError("operation 与 file_operation 只能写一个（它们是同一个维度）")
        return self

    @field_validator("file")
    @classmethod
    def _check_file(cls, value: str) -> str:
        normalized = normalize_repo_path(value)
        if not normalized:
            raise ValueError("context.file 不能为空")
        return normalized

    @field_validator("layer")
    @classmethod
    def _check_layer(cls, value: str) -> str:
        normalized = canonical_identifier(value)
        if not normalized:
            raise ValueError("layer 不能为空；安全关键维度不允许猜测")
        return normalized

    @field_validator("task")
    @classmethod
    def _check_task(cls, value: Optional[str]) -> Optional[str]:
        """任务描述是检索的查询来源之一（RetrieveRequest 的守卫按它判"至少有一个来源"）：
        一片空白既不是"有查询"、也不是"没查询"。它会被当成有效查询传给检索层，返回一个
        empty 结果——那会被读成"查过了、没有规范"，正是那条守卫要挡的形态。
        """

        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("context.task 不能是空白；没有任务描述就写 null")
        return normalized

    @field_validator("dependencies", mode="before")
    @classmethod
    def _normalize_dependencies(cls, value: Any) -> Any:
        if value is None:
            return ()
        if isinstance(value, str):
            raise TypeError("dependencies 必须是序列，不能是字符串")
        if isinstance(value, (list, tuple, set, frozenset)):
            return tuple(sorted({canonical_identifier(str(item)) for item in value if str(item).strip()}))
        return value

    def to_context_payload(self, *, request_id: str, trace_id: Optional[str]) -> dict[str, Any]:
        """转成 `policy.context.build_context` 的输入。未知维度由核心层继续拒绝。"""

        payload: dict[str, Any] = {
            "request_id": request_id,
            "file": self.file,
            "layer": self.layer,
            "language": self.language,
            "module": self.module,
            "task": self.task,
            "dependencies": list(self.dependencies),
            "git_diff": self.git_diff,
        }
        operation = self.operation
        if operation is None and self.file_operation:
            try:
                operation = Operation(self.file_operation.strip().lower())
            except ValueError:
                raise ApiError(
                    ErrorCode.CONTEXT_INVALID,
                    f"未知操作 {self.file_operation!r}；受控枚举为 "
                    f"{sorted(item.value for item in Operation)}",
                ) from None
        payload["operation"] = None if operation is None else operation.value
        if trace_id:
            payload["trace_id"] = trace_id
        if self.agent:
            payload["agent"] = self.agent
        if self.project:
            payload["project"] = self.project
        return payload


CONTEXT_FIELDS: frozenset[str] = frozenset(ContextDTO.model_fields)


class ApiEnvelope(StrictModel):
    """所有 POST 路由共用的信封。"""

    api_version: str = API_SCHEMA_VERSION
    request_id: str = Field(min_length=1, max_length=200)
    # 租户边界只能来自**令牌**：这里的 tenant 是"我想用哪个"的提示，
    # 服务端会拿它与该令牌被授权的集合比对，越权即拒绝（不是"服务端替你选一个"）。
    tenant: Optional[str] = Field(default=None, max_length=64)
    trace_id: Optional[str] = Field(default=None, max_length=200)
    idempotency_key: Optional[str] = Field(default=None, max_length=200)
    budget_ms: Optional[int] = Field(default=None, ge=1, le=600_000)
    credentials: Optional[Credentials] = None

    @model_validator(mode="before")
    @classmethod
    def _version_present(cls, value: Any) -> Any:
        """版本字段**必须显式出现**：缺失与未知都要能被区分地拒绝。"""

        if isinstance(value, Mapping) and "api_version" not in value:
            raise ApiError(ErrorCode.SCHEMA_VERSION_MISSING, "请求缺少 api_version")
        return value

    @field_validator("api_version")
    @classmethod
    def _version_supported(cls, value: str) -> str:
        if value not in SUPPORTED_API_SCHEMA_VERSIONS:
            raise ApiError(
                ErrorCode.SCHEMA_VERSION_UNKNOWN,
                f"未知 API 版本 {value!r}；本服务只接受 "
                f"{sorted(SUPPORTED_API_SCHEMA_VERSIONS)}",
            )
        return value

    @field_validator("request_id")
    @classmethod
    def _check_request_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("request_id 不能为空")
        return normalized

    @field_validator("tenant", "trace_id", "idempotency_key")
    @classmethod
    def _optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("空字符串与 null 不是一个意思：没有值就写 null")
        return normalized


class EvaluateRequest(ApiEnvelope):
    """只计算决定：不执行任何工具，也不写任何业务状态。"""

    principal: PrincipalDTO
    context: ContextDTO
    include_evidence: bool = False


class RetrieveRequest(ApiEnvelope):
    """检索 + 组装 Engineering Context。

    授权只来自**本服务算出的决策**：`decision_ref` 指的是上次 evaluate 的 request_id
    （在同一租户、同一规则集世代内可重算），客户端不能自带一份决策载荷来给自己扩权。
    """

    principal: PrincipalDTO
    context: ContextDTO
    # 查询文本是**数据**：它只参与词法匹配，不参与过滤条件的构造，也不会被写进 SQL。
    # 规模上限由核心的检索策略再收紧一次（`max_query_chars`）。
    query: Optional[str] = Field(default=None, max_length=2000)
    limit: Optional[int] = Field(default=None, ge=1, le=50)
    decision_ref: Optional[str] = Field(default=None, max_length=200)
    workspace: bool = True

    @model_validator(mode="after")
    def _query_or_task(self) -> "RetrieveRequest":
        """至少要有一个查询来源：自由文本，或上下文里的 task。

        ```
        if not (self.query or self.context.task): raise ValueError(...)
        ```
        两者都没有时不是"空查询"，而是"不知道该找什么"——按协议错误拒绝，
        而不是让检索层返回一个 empty 结果（那会被读成"查过了，没有规范"）。
        """

        if not (self.query or self.context.task):
            raise ValueError("query 与 context.task 至少要有一个：不知道找什么就不是一次检索")
        return self

    @field_validator("query")
    @classmethod
    def _check_query(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("query 不能是空字符串；没有自由文本就写 null")
        return normalized


class ValidationRequest(ApiEnvelope):
    """产出证据（可选顺带判定）。证据只能由服务端的验证器流水线产生。"""

    principal: PrincipalDTO
    context: ContextDTO
    target: Optional[str] = None
    changed: Tuple[str, ...] = ()
    only: Tuple[str, ...] = ()
    include_decision: bool = True

    @field_validator("target")
    @classmethod
    def _check_target(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = normalize_repo_path(value)
        if not normalized:
            raise ValueError("target 不能为空")
        return normalized

    @field_validator("changed", "only", mode="before")
    @classmethod
    def _normalize_paths(cls, value: Any) -> Any:
        if value is None:
            return ()
        if isinstance(value, str):
            raise TypeError("必须是路径序列，不能是字符串")
        if isinstance(value, (list, tuple, set, frozenset)):
            return tuple(sorted({normalize_repo_path(str(item)) for item in value if str(item).strip()}))
        return value


class IndexIdentity(StrictModel):
    """本次请求用到的索引身份：租户 + 世代 + 版本，便于把"结论"钉到"哪一份数据"。"""

    tenant: str
    database: str
    generation: int = 0
    index_version: str = ""
    corpus_input_hash: Optional[str] = None
    hash_drift: Tuple[str, ...] = ()


class DecisionSummary(StrictModel):
    """决策的**可审计摘要**（完整载荷由 decision 字段给出）。"""

    decision: str
    request_id: str
    rule_set_hash: Optional[str] = None
    matched: int = 0
    skipped: int = 0
    violations: int = 0
    required_action: Optional[str] = None
    policy_version: str = DECISION_PAYLOAD_SCHEMA_VERSION
    generation: str = POLICY_GENERATION


class ReadinessState(str, Enum):
    """readiness 的三种状态：能服务 / 还在装配 / 已经不可用。"""

    READY = "ready"
    DEGRADED = "degraded"
    NOT_READY = "not_ready"


READINESS_STATES: frozenset[str] = frozenset(item.value for item in ReadinessState)


class ReadinessReport(StrictModel):
    """readiness 的显式报告：区分"进程活着"与"能安全提供策略服务"。"""

    state: ReadinessState
    checked_at: str
    tenants: Tuple[Mapping[str, Any], ...] = ()
    checks: Tuple[Mapping[str, Any], ...] = ()
    detail: str = ""


def envelope_of(model: ApiEnvelope) -> ApiEnvelope:
    """取信封字段（统一 HTTP 层与进程内调用的口径）。"""

    return model


def principal_of(model: Any) -> PrincipalDTO:
    return model.principal
