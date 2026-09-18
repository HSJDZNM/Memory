"""验证器证据协议：Phase 5 的核心端口。

职责边界：

- 本模块只定义"验证器交出来的证据长什么样"，不解析代码、不调用外部工具、不读文件；
- 证据**不改变决策协议**：PolicyDecision 仍是 schema_version 1.0，引擎消费证据后
  按规则产出 Violation，证据本身通过 CLI 的 evidence 段与 validators.cli 对外暴露；
- 未知字段、未知状态一律报错，不允许"看不懂就当通过"；
- 排序稳定：同样的验证器输出必然得到同样的证据顺序（evidence 在进引擎前先规范化）。

为什么把协议放在核心层：Validator 是总体架构里列出的端口之一，实现（ast / Ruff / pytest）
属于基础设施 Adapter。核心定义"证据的形状"，Adapter 负责生产，核心负责判定。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, FrozenSet, Mapping, Optional, Tuple

from pydantic import Field, field_validator

from .models import Severity, StrictModel, canonical_identifier, normalize_repo_path

__all__ = [
    "EVIDENCE_SCHEMA",
    "EVIDENCE_SCHEMA_VERSION",
    "FAIL_CLOSED_STATUSES",
    "SUCCESS_STATUSES",
    "SUPPORTED_EVIDENCE_SCHEMA_VERSIONS",
    "Blocker",
    "DependencyFact",
    "DependencyKind",
    "DependencyResolution",
    "EvidenceBundle",
    "EvidenceLocation",
    "SourceDigest",
    "ToolInvocation",
    "ValidationEvidence",
    "ValidatorKind",
    "ValidatorRecord",
    "ValidatorStatus",
]

# 证据协议版本。字段增删或语义变化都要显式改这里；消费方只接受列出的版本。
EVIDENCE_SCHEMA = "validation-evidence"
EVIDENCE_SCHEMA_VERSION = "1.0"
SUPPORTED_EVIDENCE_SCHEMA_VERSIONS: FrozenSet[str] = frozenset({EVIDENCE_SCHEMA_VERSION})


class ValidatorKind(str, Enum):
    """验证器来源：内置（本仓库代码）或外部工具（Ruff / mypy / pytest 等）。"""

    BUILTIN = "builtin"
    EXTERNAL = "external"


class ValidatorStatus(str, Enum):
    """一次验证器运行的结果状态。

    失败关闭的状态（FAIL_CLOSED_STATUSES）必须让"需要该验证器的门禁"block，
    绝不能被同一批里的其他 PASS 抵消。
    """

    OK = "ok"
    FINDINGS = "findings"
    UNAVAILABLE = "unavailable"
    VERSION_MISMATCH = "version_mismatch"
    TIMEOUT = "timeout"
    CRASHED = "crashed"
    CONFIG_ERROR = "config_error"
    OUTPUT_INVALID = "output_invalid"
    FAILED = "failed"
    NOT_SELECTED = "not_selected"


# 成功：验证器真的跑完了（有没有发现是另一回事）。
SUCCESS_STATUSES: FrozenSet[ValidatorStatus] = frozenset(
    {ValidatorStatus.OK, ValidatorStatus.FINDINGS}
)

# 失败关闭：这些状态说明"证据没拿到"，不是"没有发现问题"。
FAIL_CLOSED_STATUSES: FrozenSet[ValidatorStatus] = frozenset(
    {
        ValidatorStatus.UNAVAILABLE,
        ValidatorStatus.VERSION_MISMATCH,
        ValidatorStatus.TIMEOUT,
        ValidatorStatus.CRASHED,
        ValidatorStatus.CONFIG_ERROR,
        ValidatorStatus.OUTPUT_INVALID,
        ValidatorStatus.FAILED,
    }
)


class DependencyKind(str, Enum):
    """目标文件依赖另一个模块的形态。动态 import 也要留痕，不能当作"没有依赖"。"""

    IMPORT = "import"
    FROM_IMPORT = "from_import"
    DYNAMIC = "dynamic"
    CALL = "call"
    DECLARED = "declared"


class DependencyResolution(str, Enum):
    """依赖解析结果。"解析失败"必须与"外部包"分开，不能都当成"没有依赖"。"""

    INTERNAL = "internal"
    EXTERNAL = "external"
    STDLIB = "stdlib"
    UNRESOLVED = "unresolved"
    DECLARED = "declared"


class SourceDigest(StrictModel):
    """被验证文件的身份：内容哈希 + 语言 + 规模。证据必须能绑定到具体一份内容。"""

    file: str
    language: str
    sha256: str = Field(min_length=8)
    bytes: int = Field(ge=0)
    lines: int = Field(ge=0)

    @field_validator("file")
    @classmethod
    def _check_file(cls, value: str) -> str:
        return normalize_repo_path(value)

    @field_validator("language")
    @classmethod
    def _check_language(cls, value: str) -> str:
        normalized = canonical_identifier(value)
        if not normalized:
            raise ValueError("language 不能为空；语言未知时应在验证之前失败关闭")
        return normalized


class EvidenceLocation(StrictModel):
    """证据位置：文件 + 行 + 列（列可缺省，行对"定位到行"的门禁是必需的）。"""

    file: str
    line: Optional[int] = Field(default=None, ge=1)
    column: Optional[int] = Field(default=None, ge=0)

    @field_validator("file")
    @classmethod
    def _check_file(cls, value: str) -> str:
        return normalize_repo_path(value)


class ToolInvocation(StrictModel):
    """外部工具的一次调用事实：版本、配置、退出码、输出规模。

    版本与配置哈希都要留痕：同一个规则的诊断结果会随工具版本与配置变化，
    没有这两项就无法回答"这个结论是用哪套工具、哪份配置得出的"。

    duration_ms 只用于性能观察，**不写进可比较的载荷**：相同输入的两次运行
    必须得到逐字节相同的证据（否则"可重放"就只是口号）。
    """

    tool: str = Field(min_length=1)
    version: Optional[str] = None
    config: Optional[str] = None
    config_sha256: Optional[str] = None
    exit_code: Optional[int] = None
    duration_ms: int = Field(default=0, ge=0)
    output_bytes: int = Field(default=0, ge=0)
    truncated: bool = False
    status: ValidatorStatus = ValidatorStatus.OK


class ValidationEvidence(StrictModel):
    """一条验证器证据。

    契约（Phase 5 计划书）：至少包含 validator ID/版本、规则 ID、文件、行列、
    消息、严重级别、工具退出码与可选修复建议。
    """

    validator_id: str = Field(min_length=1)
    validator_version: str = Field(min_length=1)
    checker: str = Field(min_length=1)
    rule_id: Optional[str] = None
    rule_version: Optional[int] = Field(default=None, ge=1)
    severity: Severity = Severity.ERROR
    message: str = Field(min_length=1)
    value: str = ""
    location: Optional[EvidenceLocation] = None
    tool: Optional[ToolInvocation] = None
    fix: Optional[str] = None
    detail: Optional[str] = None

    @property
    def sort_key(self) -> Tuple[str, str, str, int, int, str]:
        """稳定排序键：验证器 → 规则 → 文件 → 行列 → 消息。"""

        location = self.location
        return (
            self.validator_id,
            self.rule_id or "",
            "" if location is None else location.file,
            0 if location is None or location.line is None else location.line,
            0 if location is None or location.column is None else location.column,
            self.message,
        )

    @property
    def validator(self) -> str:
        return f"{self.validator_id}@{self.validator_version}"

    def to_payload(self) -> Mapping[str, Any]:
        payload: dict[str, Any] = {
            "validator": self.validator,
            "checker": self.checker,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "severity": self.severity.value,
            "message": self.message,
            "value": self.value,
            "location": None
            if self.location is None
            else {
                "file": self.location.file,
                "line": self.location.line,
                "column": self.location.column,
            },
            "tool": None if self.tool is None else _tool_payload(self.tool),
            "fix": self.fix,
            "detail": self.detail,
        }
        return payload


class DependencyFact(StrictModel):
    """一条"目标文件依赖某个模块"的事实。name 是参与规则匹配的名字。"""

    name: str = Field(min_length=1)
    module: Optional[str] = None
    kind: DependencyKind
    resolution: DependencyResolution
    file: Optional[str] = None
    line: Optional[int] = Field(default=None, ge=1)
    column: Optional[int] = Field(default=None, ge=0)
    validator: str = Field(min_length=1)
    detail: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        normalized = canonical_identifier(value)
        if not normalized:
            raise ValueError("依赖名不能为空")
        return normalized

    @field_validator("file")
    @classmethod
    def _check_file(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else normalize_repo_path(value)

    @property
    def sort_key(self) -> Tuple[str, str, str, str, int, int]:
        return (
            self.resolution.value,
            self.name,
            self.kind.value,
            self.file or "",
            0 if self.line is None else self.line,
            0 if self.column is None else self.column,
        )

    def to_payload(self) -> Mapping[str, Any]:
        return {
            "name": self.name,
            "module": self.module,
            "kind": self.kind.value,
            "resolution": self.resolution.value,
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "validator": self.validator,
            "detail": self.detail,
        }


class ValidatorRecord(StrictModel):
    """一次验证器运行的可追溯记录：状态、耗时、工具版本与原因。"""

    validator_id: str = Field(min_length=1)
    validator_version: str = Field(min_length=1)
    kind: ValidatorKind
    stage: str = Field(min_length=1)
    status: ValidatorStatus
    critical: bool = True
    duration_ms: int = Field(default=0, ge=0)
    reason: Optional[str] = None
    tool: Optional[ToolInvocation] = None
    evidence_count: int = Field(default=0, ge=0)
    served_checkers: Tuple[str, ...] = ()

    @property
    def validator(self) -> str:
        return f"{self.validator_id}@{self.validator_version}"

    def to_payload(self) -> Mapping[str, Any]:
        return {
            "validator": self.validator,
            "kind": self.kind.value,
            "stage": self.stage,
            "status": self.status.value,
            "critical": self.critical,
            "reason": self.reason,
            "tool": None if self.tool is None else _tool_payload(self.tool),
            "evidence_count": self.evidence_count,
            "served_checkers": list(self.served_checkers),
        }


class Blocker(StrictModel):
    """一个"证据没拿到"的失败关闭点，以及它让哪些 checker 无法判定。"""

    validator_id: str = Field(min_length=1)
    validator_version: str = Field(min_length=1)
    status: ValidatorStatus
    reason: str = Field(min_length=1)
    checkers: Tuple[str, ...] = ()

    @property
    def validator(self) -> str:
        return f"{self.validator_id}@{self.validator_version}"

    def to_payload(self) -> Mapping[str, Any]:
        return {
            "validator": self.validator,
            "status": self.status.value,
            "reason": self.reason,
            "checkers": list(self.checkers),
        }


class EvidenceBundle(StrictModel):
    """一次代码验证的全部证据。引擎只读这个对象，不关心它是怎么来的。"""

    schema_version: str = EVIDENCE_SCHEMA_VERSION
    target: Optional[SourceDigest] = None
    dependencies: Tuple[DependencyFact, ...] = ()
    evidence: Tuple[ValidationEvidence, ...] = ()
    validators: Tuple[ValidatorRecord, ...] = ()
    blockers: Tuple[Blocker, ...] = ()
    served_checkers: Tuple[str, ...] = ()
    unmapped_findings: int = Field(default=0, ge=0)

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in SUPPORTED_EVIDENCE_SCHEMA_VERSIONS:
            raise ValueError(
                f"未知证据协议版本 {value!r}；本实现只接受 "
                f"{sorted(SUPPORTED_EVIDENCE_SCHEMA_VERSIONS)}，拒绝当通过处理"
            )
        return normalized

    @classmethod
    def empty(cls) -> "EvidenceBundle":
        return cls()

    @property
    def blocked(self) -> bool:
        return bool(self.blockers)

    def serves(self, checker: str) -> bool:
        """是否有验证器为这个 checker 成功产出过证据。"""

        return checker in self.served_checkers

    def blocker_for(self, checker: str) -> Optional[Blocker]:
        """返回让该 checker 无法判定的第一个 blocker（按稳定顺序）。"""

        for blocker in self.blockers:
            if checker in blocker.checkers:
                return blocker
        return None

    def dependency_names(self) -> Tuple[str, ...]:
        return tuple(sorted({fact.name for fact in self.dependencies}))

    def normalize(self) -> "EvidenceBundle":
        """稳定化：证据、依赖、记录、阻断点全部按确定顺序排列并去重。"""

        return self.model_copy(
            update={
                "dependencies": tuple(
                    sorted(_unique(self.dependencies, key=_dependency_key), key=lambda item: item.sort_key)
                ),
                "evidence": tuple(
                    sorted(_unique(self.evidence, key=_evidence_key), key=lambda item: item.sort_key)
                ),
                "validators": tuple(sorted(self.validators, key=lambda item: item.validator)),
                "blockers": tuple(sorted(self.blockers, key=lambda item: (item.validator, item.reason))),
                "served_checkers": tuple(sorted(set(self.served_checkers))),
            }
        )

    def to_payload(self) -> Mapping[str, Any]:
        return {
            "schema_version": self.schema_version,
            "schema": EVIDENCE_SCHEMA,
            "target": None
            if self.target is None
            else {
                "file": self.target.file,
                "language": self.target.language,
                "sha256": self.target.sha256,
                "bytes": self.target.bytes,
                "lines": self.target.lines,
            },
            "dependencies": [fact.to_payload() for fact in self.dependencies],
            "evidence": [item.to_payload() for item in self.evidence],
            "validators": [record.to_payload() for record in self.validators],
            "blockers": [blocker.to_payload() for blocker in self.blockers],
            "served_checkers": list(self.served_checkers),
            "unmapped_findings": self.unmapped_findings,
        }


def _tool_payload(tool: ToolInvocation) -> Mapping[str, Any]:
    return {
        "tool": tool.tool,
        "version": tool.version,
        "config": tool.config,
        "config_sha256": tool.config_sha256,
        "exit_code": tool.exit_code,
        "output_bytes": tool.output_bytes,
        "truncated": tool.truncated,
        "status": tool.status.value,
    }


def _dependency_key(fact: DependencyFact) -> Tuple[str, str, str, str, int]:
    return (
        fact.name,
        fact.kind.value,
        fact.resolution.value,
        fact.file or "",
        0 if fact.line is None else fact.line,
    )


def _evidence_key(item: ValidationEvidence) -> Tuple[str, str, str, int, int, str]:
    return item.sort_key


def _unique(items: Any, *, key: Any) -> list:
    """按 key 去重但保留来源：同一 key 的多条记录只留第一条（其余已在记录里可见）。"""

    seen: set = set()
    result: list = []
    for item in items:
        marker = key(item)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result
