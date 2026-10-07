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

import json
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
    "PendingImplementation",
    "SourceDigest",
    "ToolInvocation",
    "ValidationEvidence",
    "ValidatorKind",
    "ValidatorRecord",
    "ValidatorStatus",
]

# 证据协议版本。字段增删或语义变化都要显式改这里；消费方只接受列出的版本。
# 1.1：ValidatorRecord.served_checkers → declared_checkers（P7）。同一份载荷里曾有两个
#      served_checkers、含义不同——顶层是"真的服务过"，记录里是"声明负责"；按名字读会把
#      "没跑"读成"跑了"。1.0 的载荷在 validators[] 里用的是那个歧义键名，语义也不同，
#      因此 **不再接受**：看不懂就拒绝，不做"尽量理解"。
# 1.2：新增 ValidatorStatus.PENDING_IMPLEMENTATION 与 EvidenceBundle.pending_implementation
#      （Q7：「测试已落地、目标模块还不存在」是「待实现」，不是 validator crashed）。它既不是
#      "证据到手"（**不进** served_checkers），也不是"证据没拿到"（**不产生** Blocker），
#      判定侧据此产出 warning。1.1 的载荷里没有这一族字段，读到 pending 记录时会当成未知
#      状态，因此同样 **不再接受**。
EVIDENCE_SCHEMA = "validation-evidence"
EVIDENCE_SCHEMA_VERSION = "1.2"
SUPPORTED_EVIDENCE_SCHEMA_VERSIONS: FrozenSet[str] = frozenset({EVIDENCE_SCHEMA_VERSION})


class ValidatorKind(str, Enum):
    """验证器来源：内置（本仓库代码）或外部工具（Ruff / mypy / pytest 等）。"""

    BUILTIN = "builtin"
    EXTERNAL = "external"


class ValidatorStatus(str, Enum):
    """一次验证器运行的结果状态。

    失败关闭的状态（FAIL_CLOSED_STATUSES）必须让"需要该验证器的门禁"block，
    绝不能被同一批里的其他 PASS 抵消。

    三个集合必须覆盖全部取值：SUCCESS（证据到手）、FAIL_CLOSED（证据没拿到）、
    以及两种"都不是"的显式状态（NOT_SELECTED = 本次没选它；PENDING_IMPLEMENTATION =
    跑成了、但这次的树还在构建中）。**新增状态必须显式归入其中之一**：漏归类会被
    读成"没问题"，这条由 tests/contract/test_validator_protocol.py 钉住。
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
    # 「待实现」：工具**跑成了**，但选中的测试模块因为**项目内**某个模块/名字在本次树里
    # 还不存在而在收集期失败（Q7 / 08 号报告 §5 Q1 的三次复现）。它刻意不进上面两个集合：
    # 不是"证据到手"（没查成的不能记成查过了），也不是"证据没拿到"（那不是失败关闭，
    # 而是"先写测试、再写实现"这条正确顺序）。判定侧据此产出 warning 级 violation。
    PENDING_IMPLEMENTATION = "pending_implementation"


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
    """一次验证器运行的可追溯记录：状态、耗时、工具版本与原因。

    `declared_checkers` 的口径（写死，不要按名字猜）：它回答"这个验证器**声明负责**
    哪些 checker"，因此在 `not_selected` / `crashed` / `unavailable` 时**照样**列出来。
    **声明负责 ≠ 真的服务过**：真的服务过的是 `EvidenceBundle.served_checkers` /
    `PipelineReport.served_checkers`（只收 status ∈ SUCCESS_STATUSES、且没被 blocker 划掉的
    checker）。两个字段同名会把"没跑"读成"跑了"（07 号报告 P7），所以名字必须不同。
    """

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
    declared_checkers: Tuple[str, ...] = ()

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
            "declared_checkers": list(self.declared_checkers),
        }


class Blocker(StrictModel):
    """一个"证据没拿到"的失败关闭点，以及它让哪些 checker 无法判定。"""

    validator_id: str = Field(min_length=1)
    validator_version: str = Field(min_length=1)
    status: ValidatorStatus
    reason: str = Field(min_length=1)
    # **必须非空**（与 PendingImplementation 同口径）：引擎只按 checker 查 blocker
    # （EvidenceBundle.blocker_for），一个没有 checker 的 blocker 会让 blocked=True 而永远
    # 命不中任何规则——载荷宣称有一个失败关闭点，实际谁都不会被它挡住。那种形态在这里
    # 直接不可表示，于是"失败关闭点是不是真的生效"不再取决于每个构造点的自觉。
    checkers: Tuple[str, ...] = Field(min_length=1)

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


class PendingImplementation(StrictModel):
    """「待实现」：这次写入放行了，但覆盖它的测试**还跑不了**。

    现场（08 号报告 §5 Q1 / 14 号报告 §5 Q7，三次独立复现）：项目约定"先写测试"，平台又要求
    "写生产文件时对应的测试必须已经存在"。先落地的测试 import 还不存在的**项目内**模块/名字时，
    pytest 在收集期以退出码 2 结束；旧口径把它归成 validator crashed，再由 Blocker 机制升级成
    critical 覆盖 tool.pytest 声明的两个 checker——于是两条都正确的要求在同一次写盘上互相拆台，
    被惩罚的是正确的开发顺序，模型的绕法是"先把测试暂存成不测任何东西的占位"。

    这个对象把"待实现"变成一等事实：它**不是**"证据到手"（因此不进 served_checkers，
    AGENTS 第 50 条 / N17：没查成的不能记成查过了），**也不是**"证据没拿到"（因此不产生
    Blocker），而是一条可读的、会进判定载荷的 warning（decision=allow_with_warnings）。

    三个清单都**不许为空**：说不出"哪个测试模块、因为哪个项目内缺失的目标"就构不出这条记录——
    否则它会长成"没有理由的放行"。字段全部是仓库相对路径 / 模块名，不含绝对路径（AGENTS 第 19 条）。
    """

    validator_id: str = Field(min_length=1)
    validator_version: str = Field(min_length=1)
    checkers: Tuple[str, ...] = Field(min_length=1)
    test_modules: Tuple[str, ...] = Field(min_length=1)
    missing_targets: Tuple[str, ...] = Field(min_length=1)
    reason: str = Field(min_length=1)
    fix: str = Field(min_length=1)

    @property
    def validator(self) -> str:
        return f"{self.validator_id}@{self.validator_version}"

    @property
    def sort_key(self) -> Tuple[str, Tuple[str, ...], Tuple[str, ...]]:
        return (self.validator, self.test_modules, self.missing_targets)

    def to_payload(self) -> Mapping[str, Any]:
        return {
            "validator": self.validator,
            "checkers": list(self.checkers),
            "test_modules": list(self.test_modules),
            "missing_targets": list(self.missing_targets),
            "reason": self.reason,
            "fix": self.fix,
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
    # Q7：「待实现」是一个**独立**的通道——既不进 served_checkers，也不产生 blocker。
    # 把它塞进上面任一处都会让两件事重新混成一件（"查过了、没问题"）。
    pending_implementation: Tuple[PendingImplementation, ...] = ()
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

    def pending_for(self, checker: str) -> Tuple[PendingImplementation, ...]:
        """返回覆盖该 checker 的「待实现」记录（按稳定顺序）。

        它回答的是第三种问题：不是"这个 checker 查过了吗"，而是"它这次为什么没能查成，
        以及这个原因属于**本次的树还在构建中**吗"。没有它，引擎只能把"没服务过"一律
        当成失败关闭——那正是 Q7 要修的那件事。
        """

        return tuple(
            item
            for item in self.pending_implementation
            if checker in item.checkers
        )

    def dependency_names(self) -> Tuple[str, ...]:
        return tuple(sorted({fact.name for fact in self.dependencies}))

    def normalize(self) -> "EvidenceBundle":
        """稳定化：证据、依赖、记录、阻断点全部按确定顺序排列并去重。"""

        return self.model_copy(
            update={
                "dependencies": tuple(
                    sorted(_unique(self.dependencies, key=_payload_key), key=lambda item: item.sort_key)
                ),
                "evidence": tuple(
                    sorted(_unique(self.evidence, key=_payload_key), key=lambda item: item.sort_key)
                ),
                "validators": tuple(sorted(self.validators, key=lambda item: item.validator)),
                "blockers": tuple(sorted(self.blockers, key=lambda item: (item.validator, item.reason))),
                "served_checkers": tuple(sorted(set(self.served_checkers))),
                "pending_implementation": tuple(
                    sorted(
                        _unique(self.pending_implementation, key=_payload_key),
                        key=lambda item: item.sort_key,
                    )
                ),
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
            "pending_implementation": [
                item.to_payload() for item in self.pending_implementation
            ],
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


def _payload_key(item: Any) -> str:
    """去重键 = 这条记录的**完整载荷**（规范化 JSON），不是 sort_key。

    为什么不能用 sort_key：它是**排序**键，故意粗——ValidationEvidence 只取
    validator/rule/file/line/column/message，DependencyFact 连 module / column / validator /
    detail 都不取。用它去重会把"只差 severity / value / fix / detail / tool"或"只差 module /
    column"的两条记录当成同一条丢掉，而被留下的那一条还取决于适配器的输出顺序：于是
    "同一份验证器输出 ⇒ 逐字节相同的证据"这条承诺并不成立，事实被静默吞掉
    （同一行的第二个 import、同一位置不同 severity 的两条诊断都会消失）。

    用完整载荷当键：只有真正逐字段相同的记录才合并；将来给载荷加字段，去重判据自动跟上。
    """

    return json.dumps(item.to_payload(), ensure_ascii=False, sort_keys=True)


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
