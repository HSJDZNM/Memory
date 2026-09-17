"""不可变核心模型。

本模块只负责类型、枚举与结构校验，不读取文件、不做规则匹配、不调用 LLM。
Phase 1 在 Phase 0 的基础上补齐 Context、Scope、Severity 与 Decision：
新增 critical 严重级别、scope 的多值与通配选择器、决策协议版本、命中/跳过解释字段。

约定：

- 所有模型 extra="forbid"，未知字段报错而不是静默忽略；
- 所有模型 frozen=True，实例创建后不可修改；
- 路径统一为仓库相对路径，分隔符统一为 "/"；
- 标识符比较使用 canonical_identifier（去空白 + 小写），
  刻意不做 "-" / "_" 互转，避免把 order_repository 误判为 order-repository；
- 决策协议由 schema_version 标记，未知版本在消费侧直接拒绝（ProtocolError）。
"""

from __future__ import annotations

import re
from enum import Enum
from hashlib import sha256
from typing import Any, FrozenSet, Mapping, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

__all__ = [
    "ALLOWING_SEVERITIES",
    "BLOCKING_SEVERITIES",
    "KNOWN_SCOPE_DIMENSIONS",
    "SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "WILDCARD",
    "Decision",
    "Enforcement",
    "EnforcementType",
    "Evidence",
    "ForbiddenDependencyRule",
    "LenientStrictModel",
    "Operation",
    "PolicyContext",
    "PolicyContextError",
    "Principal",
    "ProtocolError",
    "RequiredAction",
    "Rule",
    "RuleScope",
    "RuleSet",
    "RuleValidationError",
    "ScopeExtraPolicy",
    "ScopeValue",
    "Severity",
    "SkippedRule",
    "SourceRef",
    "ValidationResult",
    "Violation",
    "canonical_identifier",
    "expected_decision",
    "normalize_repo_path",
    "normalize_scope_value",
    "parse_decision",
]

_REPO_PATH_RE = re.compile(r"^[A-Za-z0-9._@+/-]+$")
_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SOURCE_KINDS = ("project-policy", "standard")
_RULE_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+$")

# 决策协议版本。任何字段增删或语义变化都必须显式改这里，
# 消费方（Phase 2 Adapter / Phase 7 API）只接受 SUPPORTED_SCHEMA_VERSIONS 中的版本。
SCHEMA_VERSION = "1.0"
SUPPORTED_SCHEMA_VERSIONS: FrozenSet[str] = frozenset({SCHEMA_VERSION})

# scope 中表示"该维度不限制"的显式通配值。没有声明该维度同样表示不限制。
WILDCARD = "*"

# 规则可以为这些上下文维度声明范围；其他键按 RuleScope.extra_policy 处理。
KNOWN_SCOPE_DIMENSIONS = ("language", "layer", "module", "operation", "project", "agent")


def canonical_identifier(value: str) -> str:
    """把依赖/模块标识符规范化为可比较形式：去首尾空白 + 小写。

    只做大小写折叠。"-" 与 "_" 保持原样，因此 Repository 与 repository 等价，
    而 order_repository 与 order-repository 不等价。
    """

    if not isinstance(value, str):
        raise TypeError(f"标识符必须是字符串，得到 {type(value).__name__}")
    return value.strip().lower()


def normalize_repo_path(value: str) -> str:
    """把路径规范化为仓库相对形式：反斜杠转 "/"，去掉 "./" 前缀与尾部 "/"。

    拒绝绝对路径与 ".." 逃逸。这属于 PolicyContextError（配置/执行错误），
    而不是模型校验错误，便于 CLI 用退出码 2 区分。
    """

    if not isinstance(value, str):
        raise PolicyContextError(f"路径必须是字符串，得到 {type(value).__name__}")

    raw = value.strip()
    if not raw:
        raise PolicyContextError("路径不能为空")

    candidate = raw.replace("\\", "/")
    if candidate.startswith("/") or _DRIVE_PREFIX_RE.match(candidate):
        raise PolicyContextError(f"路径必须是仓库相对路径，绝对路径需要 repo_root 归一: {raw!r}")

    segments: list[str] = []
    for segment in candidate.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            raise PolicyContextError(f"路径逃出仓库根目录，拒绝处理: {raw!r}")
        segments.append(segment)

    if not segments:
        raise PolicyContextError(f"路径必须指向仓库内的文件: {raw!r}")

    normalized = "/".join(segments)
    if not _REPO_PATH_RE.match(normalized):
        raise PolicyContextError(f"路径包含不支持的字符: {raw!r}")
    return normalized


class PolicyContextError(ValueError):
    """策略上下文缺失或不合法（失败策略：安全关键上下文缺失 → block / 退出码 2）。"""


class ProtocolError(ValueError):
    """决策协议无法消费：未知 schema_version、未知决策值或字段不合法。

    消费方必须把它当作硬错误，不能降级成默认 allow。
    """


class Severity(str, Enum):
    """违规严重级别。数值顺序即阻断能力顺序，供决策聚合使用。"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# 决策表：无 violation → allow；info/warning → allow_with_warnings；error/critical → block。
ALLOWING_SEVERITIES: FrozenSet[Severity] = frozenset({Severity.INFO, Severity.WARNING})
BLOCKING_SEVERITIES: FrozenSet[Severity] = frozenset({Severity.ERROR, Severity.CRITICAL})


class EnforcementType(str, Enum):
    """规则执行方式。Phase 0 只支持确定性执行。"""

    DETERMINISTIC = "deterministic"


class ScopeExtraPolicy(str, Enum):
    """scope 中未声明键的处理策略。"""

    SKIP = "skip"
    REJECT = "reject"


class Operation(str, Enum):
    """被治理的操作类型（受控枚举：未知操作必须报错，不得降级为"无操作"）。"""

    READ = "read"
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"
    EXECUTE = "execute"


# scope 维度的取值：单个精确值，或多个值（同字段多值 = OR）。"*" 表示该维度不限制。
ScopeValue = Union[str, Tuple[str, ...]]


def normalize_scope_value(value: Any, *, dimension: str) -> Optional[ScopeValue]:
    """规范化 scope 的某个维度：去空白 + 小写 + 去重，保留标量/列表形状。

    - 标量保持标量，列表保持元组，便于规则文件往返序列化时形状不变；
    - 出现 "*" 即整体视为通配（不限制该维度），避免"通配 + 条件"这种歧义写法；
    - operation 维度按受控枚举校验，未知操作在加载阶段就失败，而不是永远不命中。
    """

    if value is None:
        return None

    if isinstance(value, str):
        items: Tuple[Any, ...] = (value,)
        scalar = True
    elif isinstance(value, (list, tuple)):
        items = tuple(value)
        scalar = False
    else:
        raise ValueError(
            f"scope.{dimension} 必须是字符串或字符串列表，得到 {type(value).__name__}"
        )

    normalized: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise ValueError(
                f"scope.{dimension} 的值必须是字符串，得到 {type(item).__name__}"
            )
        token = item.strip()
        if not token:
            raise ValueError(f"scope.{dimension} 不能包含空值")
        if token == WILDCARD:
            return WILDCARD
        normalized.append(canonical_identifier(token))

    if not normalized:
        raise ValueError(f"scope.{dimension} 不能是空列表；不限制该维度时请省略该键")

    if dimension == "operation":
        known = {item.value for item in Operation}
        unknown = sorted({item for item in normalized if item not in known})
        if unknown:
            raise ValueError(
                f"scope.operation 只接受受控操作 {sorted(known)}，得到 {unknown}"
            )

    if scalar:
        return normalized[0]
    return tuple(normalized)


class Decision(str, Enum):
    """决策枚举固定为三种；未识别值按协议错误处理，绝不默认为 ALLOW。"""

    ALLOW = "allow"
    ALLOW_WITH_WARNINGS = "allow_with_warnings"
    BLOCK = "block"


class RequiredAction(str, Enum):
    """决策要求调用方完成的前置动作。审批必须以 block 表达，不能用 warning 代替。"""

    APPROVAL = "approval"


class StrictModel(BaseModel):
    """所有核心模型的基类：拒绝未知字段、禁止创建后修改。"""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=False)


class LenientStrictModel(StrictModel):
    """允许携带未知字段的严格模型；由子类自行决定如何处理这些字段。"""

    model_config = ConfigDict(
        extra="allow", frozen=True, validate_assignment=False, validate_default=True
    )


class SourceRef(StrictModel):
    """规则的本地来源。共享对话或外部文档不能作为可执行来源。"""

    kind: str = Field(min_length=1, description="来源类型：project-policy 或 standard")
    path: Optional[str] = Field(default=None, description="仓库相对路径")
    url: Optional[str] = Field(default=None, description="外部参考链接（仅供参考，非强制规范）")
    note: Optional[str] = Field(default=None, description="补充说明")

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SOURCE_KINDS:
            raise ValueError(
                f"source.kind 必须是本地来源 {list(SOURCE_KINDS)} 之一，得到 {value!r}；"
                "共享对话或外部文档不能作为可执行规则来源"
            )
        return normalized

    @field_validator("path")
    @classmethod
    def _check_path(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_repo_path(value)


class RuleScope(LenientStrictModel):
    """规则的适用范围：每个维度可选，缺省表示“不限制”（而不是匹配空值）。

    - 同维度多值 = OR，跨维度 = AND；
    - "*" 表示该维度显式不限制；
    - 未知维度按 extra_policy 处理：默认 reject。拼错维度名会让规则悄悄放大适用范围，
      必须在加载阶段报错；确需忽略时显式写 scope.extra_policy=skip 并记入 ignored_dimensions。
    """

    language: Optional[ScopeValue] = Field(default=None, description="目标语言，例如 python")
    layer: Optional[ScopeValue] = Field(default=None, description="目标架构层，例如 controller")
    module: Optional[ScopeValue] = Field(default=None, description="目标模块，例如 order")
    operation: Optional[ScopeValue] = Field(
        default=None, description="被治理的操作，取值必须是受控枚举"
    )
    project: Optional[ScopeValue] = Field(default=None, description="目标项目")
    agent: Optional[ScopeValue] = Field(default=None, description="产生请求的 Agent 标识")
    extra_policy: ScopeExtraPolicy = Field(
        default=ScopeExtraPolicy.REJECT,
        exclude=True,
        description="遇到未声明的 scope 键时：reject 让规则集加载失败，skip 记录并忽略该键",
    )

    @field_validator(*KNOWN_SCOPE_DIMENSIONS, mode="before")
    @classmethod
    def _normalize_dimension(cls, value: Any, info: Any) -> Optional[ScopeValue]:
        return normalize_scope_value(value, dimension=str(info.field_name))

    @property
    def declared_dimensions(self) -> Mapping[str, ScopeValue]:
        """已声明的维度 → 选择器；未声明的维度不在这里，也不会参与匹配。"""

        declared: dict[str, ScopeValue] = {}
        for name in KNOWN_SCOPE_DIMENSIONS:
            value = getattr(self, name)
            if value is not None:
                declared[name] = value
        return declared

    @property
    def ignored_dimensions(self) -> tuple[str, ...]:
        """未知 scope 键；显式 skip 时保留在这里，供决策解释而不是静默丢弃。"""

        return tuple(sorted(self.model_extra or {}))

    @model_validator(mode="after")
    def _handle_unknown_dimensions(self) -> "RuleScope":
        ignored = self.ignored_dimensions
        if ignored and self.extra_policy is ScopeExtraPolicy.REJECT:
            raise ValueError(
                "scope 中出现未知维度，拒绝加载（拼错维度名会让规则悄悄放大适用范围）："
                + ", ".join(repr(name) for name in ignored)
                + "；确需忽略请显式写 scope.extra_policy=skip"
            )
        return self


class Enforcement(StrictModel):
    """规则执行方式。除 deterministic 以外一律拒绝。"""

    type: EnforcementType
    checker: Optional[str] = Field(
        default=None, description="确定性检查器标识，例如 forbidden_dependency"
    )
    requires_approval: bool = Field(
        default=False,
        description=(
            "该规则是一道授权门禁：范围命中即表示当前操作需要人工审批，"
            "决策以 block + required_action=approval 表达"
        ),
    )

    @field_validator("checker")
    @classmethod
    def _check_checker(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("enforcement.checker 不能是空字符串")
        return normalized

    @model_validator(mode="after")
    def _deterministic_requires_checker(self) -> "Enforcement":
        if self.type is EnforcementType.DETERMINISTIC and not self.checker:
            raise ValueError("enforcement.type=deterministic 必须声明 enforcement.checker")
        return self


class ForbiddenDependencyRule(StrictModel):
    """Phase 0 唯一的规则体：禁止某一层直接依赖某些模块。"""

    forbidden_dependency: Tuple[str, ...] = Field(min_length=1)

    @field_validator("forbidden_dependency")
    @classmethod
    def _normalize_forbidden(cls, values: Tuple[str, ...]) -> Tuple[str, ...]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in values:
            canonical = canonical_identifier(raw)
            if not canonical:
                raise ValueError("rule.forbidden_dependency 不能包含空标识符")
            if canonical in seen:
                continue
            seen.add(canonical)
            normalized.append(canonical)
        return tuple(normalized)


class Rule(StrictModel):
    """一条机器可执行规则。id 与 version 共同决定审计身份。"""

    id: str = Field(min_length=1)
    version: int = Field(ge=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    scope: RuleScope
    severity: Severity
    enforcement: Enforcement
    rule: ForbiddenDependencyRule
    message: str = Field(min_length=1)
    source: SourceRef

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not _RULE_ID_RE.match(normalized):
            raise ValueError(
                "规则 id 必须形如 ARCH-001（大写字母/数字，短横线分段，以数字序号结尾），"
                f"得到 {value!r}"
            )
        return normalized

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        normalized = value.strip()
        if not _SAFE_NAME_RE.match(normalized):
            raise ValueError(f"规则 name 必须是稳定标识符（字母/数字/._-），得到 {value!r}")
        return normalized

    @property
    def canonical_id(self) -> str:
        """审计身份，形如 ARCH-001@1。"""

        return f"{self.id}@{self.version}"


class RuleSet(StrictModel):
    """一次加载的完整规则集合。空规则集是合法结果。"""

    rules: Tuple[Rule, ...] = ()
    source_paths: Tuple[str, ...] = ()

    def __len__(self) -> int:
        return len(self.rules)

    @property
    def ids(self) -> Tuple[str, ...]:
        return tuple(rule.canonical_id for rule in self.rules)

    @property
    def identity(self) -> str:
        """规则集身份，用于阶段验收证据中的 rule_set_hash。"""

        # 规则集身份只取决于规则内容，与加载顺序无关：
        #   1) exclude_none：未声明的 scope 维度不进载荷；
        #   2) 排序：同一组规则无论从哪个目录顺序读进来，哈希都一样。
        payload = chr(10).join(
            sorted(rule.model_dump_json(exclude_none=True) for rule in self.rules)
        )
        return "sha256:" + sha256(payload.encode("utf-8")).hexdigest()


class Principal(StrictModel):
    """请求主体。角色用于后续阶段鉴权，Phase 0 只保留结构。"""

    subject: str = Field(min_length=1)
    roles: FrozenSet[str] = Field(default_factory=frozenset)

    @field_validator("subject")
    @classmethod
    def _check_subject(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("principal.subject 不能为空")
        return normalized

    @field_validator("roles", mode="before")
    @classmethod
    def _normalize_roles(cls, value: Any) -> Any:
        if value is None:
            return frozenset()
        if isinstance(value, (list, tuple, set, frozenset)):
            return frozenset(
                canonical_identifier(str(item)) for item in value if str(item).strip()
            )
        return value


class PolicyContext(StrictModel):
    """规则匹配与决策所需的固定上下文。

    必需（没有默认值，Adapter 不得猜测，缺失即失败）：
    request_id、file、layer。

    可选（None 表示"上下文没有提供该信息"）：
    project、agent、operation、language、module、task、dependencies、git_diff、
    principal、trace_id。

    注意 language 刻意没有默认值：默认成 python 会让非 Python 文件被 Python 规则
    静默命中（或漏判），因此"不知道语言"必须显式表达为 None，并在 skipped_rules 里
    说明该规则因缺少维度值而没有参与判断。
    """

    request_id: str = Field(min_length=1)
    project: Optional[str] = None
    agent: Optional[str] = None
    operation: Optional[Operation] = None
    file: str
    language: Optional[str] = None
    module: Optional[str] = None
    layer: str
    task: Optional[str] = None
    dependencies: Tuple[str, ...] = ()
    git_diff: Optional[str] = None
    principal: Optional[Principal] = None
    trace_id: Optional[str] = None

    @field_validator("request_id")
    @classmethod
    def _check_request_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("request_id 不能为空")
        return normalized

    @field_validator("file")
    @classmethod
    def _check_file(cls, value: str) -> str:
        return normalize_repo_path(value)

    @field_validator("layer")
    @classmethod
    def _check_layer(cls, value: str) -> str:
        normalized = canonical_identifier(value)
        if not normalized:
            raise ValueError("layer 不能为空；安全关键字段缺失时不得猜测")
        return normalized

    @field_validator("language")
    @classmethod
    def _check_language(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = canonical_identifier(value)
        if not normalized:
            raise ValueError("language 不能是空字符串")
        return normalized

    @field_validator("project", "module", "agent")
    @classmethod
    def _check_canonical_dimension(cls, value: Optional[str]) -> Optional[str]:
        """维度值统一成 canonical_identifier，与 scope 的比较口径一致。"""

        if value is None:
            return None
        normalized = canonical_identifier(value)
        if not normalized:
            raise ValueError("上下文维度不能是空字符串；不知道就写 null，不要写空串")
        return normalized

    @field_validator("task")
    @classmethod
    def _check_task(cls, value: Optional[str]) -> Optional[str]:
        """task 是给人看的任务描述，只去首尾空白，不做大小写折叠。"""

        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("task 不能是空字符串；没有任务描述就写 null")
        return normalized

    @field_validator("trace_id")
    @classmethod
    def _check_trace_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("trace_id 不能是空字符串；没有 trace 就写 null")
        return normalized

    @field_validator("dependencies", mode="before")
    @classmethod
    def _normalize_dependencies(cls, value: Any) -> Any:
        if value is None:
            return ()
        if isinstance(value, str):
            raise TypeError("dependencies 必须是序列，不能是字符串")
        if isinstance(value, (list, tuple, set, frozenset)):
            normalized: list[str] = []
            seen: set[str] = set()
            for item in value:
                canonical = canonical_identifier(str(item))
                if not canonical or canonical in seen:
                    continue
                seen.add(canonical)
                normalized.append(canonical)
            return tuple(sorted(normalized))
        return value


class Evidence(StrictModel):
    """违规的结构化证据。禁止写入密钥、完整 Prompt 或敏感数据。"""

    kind: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    value: str
    file: Optional[str] = None
    line: Optional[int] = Field(default=None, ge=1)
    detail: Optional[str] = None


class Violation(StrictModel):
    """一条确定性违规。"""

    rule_id: str = Field(min_length=1)
    rule_version: int = Field(ge=1)
    severity: Severity
    message: str = Field(min_length=1)
    evidence: Evidence

    @property
    def canonical_id(self) -> str:
        return f"{self.rule_id}@{self.rule_version}"

    @property
    def sort_key(self) -> Tuple[str, str, str]:
        """稳定排序键：规则身份 → 证据值 → 证据主体。"""

        return (self.canonical_id, self.evidence.value, self.evidence.subject)


class SkippedRule(StrictModel):
    """一条范围不匹配的规则及其原因摘要（"规则是否相关"必须可解释）。"""

    rule_id: str = Field(min_length=1, description="审计身份，形如 ARCH-001@1")
    reasons: Tuple[str, ...] = Field(default=(), description="未命中的维度说明")

    @property
    def sort_key(self) -> str:
        return self.rule_id


class ValidationResult(StrictModel):
    """一次 evaluate 的完整结果，可直接序列化为审计证据（Phase 1 决策协议）。"""

    schema_version: str = SCHEMA_VERSION
    decision: Decision
    request_id: str
    trace_id: Optional[str] = None
    rule_set_hash: Optional[str] = None
    matched_rules: Tuple[str, ...] = ()
    skipped_rules: Tuple[SkippedRule, ...] = ()
    violations: Tuple[Violation, ...] = ()
    required_action: Optional[RequiredAction] = None
    policy_version: str = "phase-1"

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"未知决策协议版本 {value!r}；本实现只接受 "
                f"{sorted(SUPPORTED_SCHEMA_VERSIONS)}，拒绝默认放行"
            )
        return normalized

    @model_validator(mode="after")
    def _decision_matches_findings(self) -> "ValidationResult":
        expected = expected_decision(self.violations, required_action=self.required_action)
        if self.decision is not expected:
            raise ValueError(
                f"decision 与 violations/required_action 不一致：decision={self.decision.value}，"
                f"按当前发现应为 {expected.value}"
            )
        return self

    @property
    def passed(self) -> bool:
        return self.decision is Decision.ALLOW

    @property
    def severity_counts(self) -> Mapping[str, int]:
        counts: dict[str, int] = {}
        for violation in self.violations:
            counts[violation.severity.value] = counts.get(violation.severity.value, 0) + 1
        return counts

    @property
    def requires_approval(self) -> bool:
        return self.required_action is RequiredAction.APPROVAL

    def to_decision_dict(self) -> dict[str, Any]:
        """决策协议载荷（PolicyDecision），与 from_decision_dict 严格互逆。"""

        return {
            "schema_version": self.schema_version,
            "decision": self.decision.value,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "rule_set_hash": self.rule_set_hash,
            "matched_rules": list(self.matched_rules),
            "skipped_rules": [
                {"rule_id": item.rule_id, "reasons": list(item.reasons)}
                for item in self.skipped_rules
            ],
            "violations": [
                {
                    "rule_id": violation.rule_id,
                    "rule_version": violation.rule_version,
                    "severity": violation.severity.value,
                    "message": violation.message,
                    "evidence": _evidence_payload(violation.evidence),
                }
                for violation in self.violations
            ],
            "required_action": None if self.required_action is None else self.required_action.value,
            "policy_version": self.policy_version,
        }

    @classmethod
    def from_decision_dict(cls, payload: Mapping[str, Any]) -> "ValidationResult":
        """按协议解析决策载荷；版本不符或字段非法一律抛 ProtocolError。"""

        return parse_decision(payload)


def _evidence_payload(evidence: Evidence) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": evidence.kind,
        "subject": evidence.subject,
        "value": evidence.value,
    }
    if evidence.file is not None:
        payload["file"] = evidence.file
    if evidence.line is not None:
        payload["line"] = evidence.line
    if evidence.detail is not None:
        payload["detail"] = evidence.detail
    return payload


def expected_decision(
    violations: Tuple[Violation, ...], *, required_action: Optional[RequiredAction] = None
) -> Decision:
    """决策表：无违规 → allow；info/warning → allow_with_warnings；error/critical → block。

    需要人工审批时先以 block 表达：授权是前置条件，不能用模糊的 warning 代替。
    """

    if required_action is RequiredAction.APPROVAL:
        return Decision.BLOCK
    return _expected_decision(violations)


def _expected_decision(violations: Tuple[Violation, ...]) -> Decision:
    if not violations:
        return Decision.ALLOW
    if any(violation.severity in BLOCKING_SEVERITIES for violation in violations):
        return Decision.BLOCK
    return Decision.ALLOW_WITH_WARNINGS


def parse_decision(payload: Mapping[str, Any]) -> ValidationResult:
    """消费一份决策载荷：未知版本、未知决策值、字段错误一律拒绝。"""

    if not isinstance(payload, Mapping):
        raise ProtocolError(f"决策载荷必须是映射，得到 {type(payload).__name__}")

    version = payload.get("schema_version")
    if version is None:
        raise ProtocolError("决策载荷缺少 schema_version，拒绝消费")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ProtocolError(
            f"未知决策协议版本 {version!r}；本实现只接受 "
            f"{sorted(SUPPORTED_SCHEMA_VERSIONS)}，拒绝消费"
        )

    try:
        return ValidationResult.model_validate(dict(payload))
    except ValidationError as error:
        failure = RuleValidationError.from_pydantic(error, model_name="决策载荷")
        raise ProtocolError(str(failure)) from error


class RuleValidationError(ValueError):
    """把 pydantic 的校验失败包装成带字段位置的可读错误。"""

    def __init__(self, message: str, *, errors: Optional[list[dict[str, Any]]] = None) -> None:
        super().__init__(message)
        self.errors = errors or []

    @classmethod
    def from_pydantic(cls, error: ValidationError, *, model_name: str) -> "RuleValidationError":
        details = []
        for item in error.errors():
            location = ".".join(str(part) for part in item.get("loc", ()))
            details.append(f"{location or '<root>'}: {item.get('msg')}")
        message = f"{model_name} 校验失败 -> " + "; ".join(details)
        return cls(message, errors=[dict(item) for item in error.errors()])
