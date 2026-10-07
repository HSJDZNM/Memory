"""Phase 8 编排层的状态与节点契约（框架中立、可序列化）。

这一层不拥有任何治理语义：规则、权限、证据与判定都在 Policy Platform 里。
这里只定义"工作流怎么走"——最小状态、节点输出、循环上限、checkpoint 与审批引用。

三条持久化纪律（阶段计划 §1 / §5 / 退出条件）：

1. 长期 checkpoint 只保存**引用**：task ID、阶段、artifact ID 与哈希、Policy trace ID、
   验证摘要、重试计数、审批引用；
2. 需求正文、文件内容、工具完整输出、凭据一律不进状态——状态里只有摘要与短结论；
3. 相同输入必须得到逐字节相同的状态：没有墙钟时间，只有自增序号；
   最终报告里的时间由调用方注入的时钟产生，不进状态。

版本纪律与 Phase 7 一致：编排协议有自己的 `STATE_SCHEMA_VERSION`，
而 `policy_version` / 决策协议版本只从核心取值，本包不许自己算一个。
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Final, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from policy.models import POLICY_VERSION, SCHEMA_VERSION, Decision, Severity

__all__ = [
    "STATE_SCHEMA_VERSION",
    "SUPPORTED_STATE_SCHEMA_VERSIONS",
    "ApprovalUse",
    "ArtifactKind",
    "ArtifactRef",
    "ContextRef",
    "Counters",
    "FailureCode",
    "FailureRef",
    "GraphState",
    "NodeId",
    "NodeRun",
    "PlatformSnapshot",
    "PlanStep",
    "RunLimits",
    "RunStatus",
    "StageStatus",
    "ValidationSummary",
    "ViolationRef",
    "canonical_digest",
    "is_relative_state_path",
    "empty_state",
]

# 编排状态协议版本。改字段语义 = 新版本；读不懂的状态必须拒绝（见 checkpoint 层）。
# 1.1（台阶 3a / H1+H10）：ValidationSummary 增受控 `reason_code`、ViolationRef 增证据通道
# `evidence_kind` / `evidence_value`。两者都进 checkpoint 状态，因此旧版状态显式拒绝恢复
# （协议自己的规则：改状态载荷就递增自己的版本号，不去改动决策协议）。
STATE_SCHEMA_VERSION: Final[str] = "1.1"
SUPPORTED_STATE_SCHEMA_VERSIONS: Final[frozenset[str]] = frozenset({STATE_SCHEMA_VERSION})

_MAX_ID = 128
_MAX_TEXT = 400
# 自由文本（验收条目、结论行）比结构化字段更短：它们是"短结论"，不是正文。
_MAX_NOTE = 200
_MAX_PATH = 512


class StrictModel(BaseModel):
    """未知字段一律报错：编排状态与平台载荷之间不许有"悄悄多出来"的字段。"""

    model_config = ConfigDict(extra="forbid")


def canonical_digest(value: Any) -> str:
    """规范化 JSON 的 sha256（带 sha256: 前缀）。相同输入必须得到相同摘要。"""

    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _relative_path(value: str) -> str:
    """状态里的路径只能是仓库相对路径：绝对路径、反斜杠与 `..` 一律拒绝。"""

    if not value or len(value) > _MAX_PATH:
        raise ValueError("路径必须是长度 1..512 的仓库相对路径")
    if value.startswith("/") or value.startswith("~") or ":" in value.split("/")[0]:
        raise ValueError("状态里不许出现绝对路径")
    if "\\" in value:
        raise ValueError("状态里的路径统一用 / 分隔")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("路径不得包含空段、. 或 ..")
    return value


def is_relative_state_path(value: Any) -> bool:
    """这个值能不能作为**状态里的**仓库相对路径（与 _relative_path 逐条同口径）。

    给"过滤外部载荷"的地方用（例如编排客户端从平台响应里挑 source_path）：
    它们需要的是"能不能进状态"这一个判断，而不是自己再写一套更松的规则——
    两套口径必然漂移（实测过：松的那套放 Windows 形态与百分号编码进状态，
    而同一个值交给状态模型就会被拒）。
    """

    try:
        _relative_path(value)
    except (TypeError, ValueError):
        return False
    return True


def _short_text(value: str, *, limit: int = _MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise ValueError("必须是文本")
    if len(value) > limit:
        raise ValueError(f"文本超过 {limit} 字符：状态里只放短结论，不放正文")
    if "\x00" in value:
        raise ValueError("文本不得包含控制字符")
    return value


def _safe_text(value: str, *, limit: int = _MAX_NOTE) -> str:
    """状态里的自由文本：必须是**短结论**，而且不得出现凭据形态的取值。

    "状态里不放正文"如果只是约定，调用方随手把需求原文塞进验收条目就破功了
    （独立验证探针 P1/P1b 就是这样证伪的）。因此这里把它变成**拒绝**：
    超长、或含 `sk-` / `Bearer x` / 私钥块这类确定形态的凭据 → 直接报错，
    既不落盘也不"先收下再说"。
    """

    from enforcement.audit import contains_secret_value

    text = _short_text(value, limit=limit)
    if contains_secret_value(text):
        raise ValueError("状态里的文本不得包含凭据形态的取值：拒绝把凭据写进长期状态")
    return text


def _safe_state_text(value: str) -> str:
    """进长期状态的自由文本统一过一遍：短、无控制字符、无**凭据形态**的取值。

    为什么不是"只给 requirements/notes 用"：状态是**长期**的（checkpoint 落盘，还可能进审计与
    报告），凭据一旦写进去就没有回收路径；而这几处（ArtifactRef.note / PolicyTraceRef.reason /
    ViolationRef.message / NodeRun.detail / FailureRef.detail）装的都是上游或外部文本，
    不能靠"调用方自觉"。长度沿用各字段自己的上限（400）——这次只加凭据探针，不顺手改长度。
    """

    return _safe_text(value, limit=_MAX_TEXT)


class NodeId(str, Enum):
    """工作流的节点。名字就是图里的节点名（CLI 与 checkpoint 都用它）。"""

    REQUIREMENT_ANALYSIS = "requirement_analysis"
    POLICY_RETRIEVAL = "policy_retrieval"
    ARCHITECTURE_PLANNING = "architecture_planning"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    REPAIR = "repair"
    TESTING = "testing"
    REVIEW = "review"


class StageStatus(str, Enum):
    PENDING = "pending"
    OK = "ok"
    FAILED = "failed"
    BLOCKED = "blocked"
    NEEDS_HUMAN = "needs_human"
    SKIPPED = "skipped"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    NEEDS_HUMAN = "needs_human"
    BLOCKED = "blocked"
    FAILED = "failed"


class FailureCode(str, Enum):
    """显式失败码。新增码必须同时登记 `errors.STATUS_BY_CODE`。"""

    STATE_INVALID = "state_invalid"
    STATE_VERSION_UNKNOWN = "state_version_unknown"
    NODE_UNKNOWN = "node_unknown"
    NODE_CONTRACT_INVALID = "node_contract_invalid"
    POLICY_UNAVAILABLE = "policy_unavailable"
    POLICY_BLOCKED = "policy_blocked"
    KNOWLEDGE_UNAVAILABLE = "knowledge_unavailable"
    VALIDATOR_UNAVAILABLE = "validator_unavailable"
    EVIDENCE_UNAVAILABLE = "evidence_unavailable"
    TOOL_UNAVAILABLE = "tool_unavailable"
    TOOL_DENIED = "tool_denied"
    TRACE_MISSING = "trace_missing"
    TRACE_FORGED = "trace_forged"
    CIRCUIT_OPEN = "circuit_open"
    SIDE_EFFECT_UNKNOWN = "side_effect_unknown"
    APPROVAL_MISSING = "approval_missing"
    APPROVAL_EXPIRED = "approval_expired"
    APPROVAL_SUBJECT_MISMATCH = "approval_subject_mismatch"
    APPROVAL_PARAM_MISMATCH = "approval_param_mismatch"
    APPROVAL_CONSUMED = "approval_consumed"
    CHECKPOINT_MISSING = "checkpoint_missing"
    CHECKPOINT_CORRUPT = "checkpoint_corrupt"
    CHECKPOINT_INCOMPATIBLE = "checkpoint_incompatible"
    LIMIT_REPAIR_ROUNDS = "limit_repair_rounds"
    LIMIT_TOOL_CALLS = "limit_tool_calls"
    LIMIT_NODE_RUNS = "limit_node_runs"
    LIMIT_TOKENS = "limit_tokens"
    LIMIT_WALL_CLOCK = "limit_wall_clock"
    LIMIT_COST = "limit_cost"
    ENGINE_UNAVAILABLE = "engine_unavailable"


class ArtifactKind(str, Enum):
    REQUIREMENT = "requirement"
    PLAN = "plan"
    CHANGE = "change"
    REPORT = "report"


class ArtifactRef(StrictModel):
    """artifact 只留引用与摘要：正文在受控工作区里，不进状态。"""

    artifact_id: str = Field(min_length=1, max_length=_MAX_ID)
    kind: ArtifactKind
    path: Optional[str] = None
    digest: str = Field(min_length=1, max_length=80)
    bytes: int = Field(default=0, ge=0)
    note: str = Field(default="", max_length=_MAX_TEXT)

    _check_path = field_validator("path")(
        lambda value: None if value is None else _relative_path(value)
    )
    _check_note = field_validator("note")(_safe_state_text)


class ContextRef(StrictModel):
    """检索到的片段引用：来源、哈希与许可，**不含正文**。"""

    chunk_id: str = Field(min_length=1, max_length=_MAX_ID)
    source_path: str = Field(min_length=1, max_length=_MAX_PATH)
    digest: str = Field(min_length=1, max_length=80)
    license: str = Field(default="", max_length=120)
    tier: str = Field(default="", max_length=40)

    _check_source = field_validator("source_path")(_relative_path)


class PolicyTraceRef(StrictModel):
    """一次平台判定的引用：request_id / 决定 / 规则集哈希 / trace。"""

    node: NodeId
    request_id: str = Field(min_length=1, max_length=_MAX_ID)
    decision: Decision
    trace_id: Optional[str] = Field(default=None, max_length=_MAX_ID)
    rule_set_hash: Optional[str] = Field(default=None, max_length=80)
    reason: str = Field(default="", max_length=_MAX_TEXT)

    _check_reason = field_validator("reason")(_safe_state_text)


# H1：一次 block 属于哪一类——**受控闭集**（不留自由文本）。
#
# 为什么需要它：`block` + `violations=[]` 在判定层是**合法**形态（审批门禁就是这一种），
# 而消费方修复节点把它读成「没有依据」，于是抛契约错误、整轮变 FAILED——一条「需要人批准」
# 被翻译成了「编排自己坏了」。这里把「属于哪一类」算出来，让消费方有受控的东西可读。
#
# 为什么是**派生**而不是决策协议的新字段：判定协议（policy SCHEMA_VERSION）本轮不动——
# 这些结论都能从已有的 required_action 与 violations 的证据通道算出来；多一个载荷字段
# 等于多一条可能与判定矛盾的通道。
REASON_APPROVAL_REQUIRED: Final[str] = "approval_required"
REASON_POLICY_VIOLATION: Final[str] = "policy_violation"
REASON_EVIDENCE_UNAVAILABLE: Final[str] = "evidence_unavailable"
REASON_CODES: Final[frozenset[str]] = frozenset(
    {REASON_APPROVAL_REQUIRED, REASON_POLICY_VIOLATION, REASON_EVIDENCE_UNAVAILABLE}
)

# 判定侧用 `evidence.kind` 表达「平台没能查」（不是代码缺陷）。**真实产出**只有两条：
#   checkers.blocker_violation          → kind="validator"、value=验证器状态、detail=自由文本原因；
#   checkers.uncovered_checker_violation → kind="validator"、value=checker 名、detail="uncovered_checker"。
# 真正的规则违规写的是 checker 名（style_lint / failing_tests …）、"dependency"（含「依赖无法证明」）
# 或 "context"。因此 kind 是"平台没能查"与"规则报了违规"之间**唯一稳定的结构化区别**。
#
# 为什么不是 detail：blocker 的 detail 是自由文本原因（checkers.py:399），拿它比受控取值永远比不中；
# 而且 detail 根本没进 ViolationRef（client 只搬 kind/value）。老实现比的是 evidence_value ∈
# {"uncovered_checker","blocker"}——两个取值平台都不会写进 value，于是真实载荷恒判 policy_violation：
# 平台明明说"我没能查"，修复节点却按"规则报了违规"去改文件（H1 要防的正是这件事）。
UNREPAIRABLE_EVIDENCE_KINDS: Final[frozenset[str]] = frozenset({"validator"})


def decision_reason(
    decision: Decision,
    *,
    required_action: Optional[str],
    violations: Tuple["ViolationRef", ...],
) -> Optional[str]:
    """按**受控规则**给一次 block 归类；说不出来就返回 None（消费方失败关闭）。

    规则（顺序即优先级，未知一律 None）：

    1. required_action == "approval" → approval_required（授权是前置条件，不是发现）；
    2. 有 violation 且**每一条**都是「平台没能查」→ evidence_unavailable；
    3. 有 violation 且至少一条是规则报的违规 → policy_violation；
    4. 其余（含 block + 空 violations 却说不出为什么）→ None。
    """

    if decision is not Decision.BLOCK:
        return None
    if required_action == "approval":
        return REASON_APPROVAL_REQUIRED
    if not violations:
        return None
    if all(item.evidence_kind in UNREPAIRABLE_EVIDENCE_KINDS for item in violations):
        return REASON_EVIDENCE_UNAVAILABLE
    return REASON_POLICY_VIOLATION


class ViolationRef(StrictModel):
    """结构化 violation：修复节点只能基于它规划，不读自然语言。

    `evidence_kind` / `evidence_value` 是**证据通道**（H10）：判定侧的 violation 靠
    `evidence.kind` 区分"某条规则报了违规"与"关键验证器撤了证据"（`uncovered_checker` /
    `blocker`），而"过桥"这一层原先只取 evidence 的 file/line，把 kind/value/detail
    整段丢掉——于是修复节点只能靠中文 message 猜这条 violation 属于哪一类，而"靠文本猜"
    正是平台一直在治的那件事。这里只搬引用，不搬正文。
    """

    rule_id: str = Field(min_length=1, max_length=_MAX_ID)
    rule_version: int = Field(ge=1)
    severity: Severity
    file: str = Field(default="", max_length=_MAX_PATH)
    line: Optional[int] = Field(default=None, ge=1)
    message: str = Field(default="", max_length=_MAX_TEXT)
    evidence_kind: str = Field(default="", max_length=_MAX_ID)
    evidence_value: str = Field(default="", max_length=_MAX_TEXT)

    _check_message = field_validator("message")(_safe_state_text)

    @field_validator("file")
    @classmethod
    def _check_file(cls, value: str) -> str:
        return "" if not value else _relative_path(value)


class ValidationSummary(StrictModel):
    """验证结果摘要：决定 + 证据摘要 + 验证器 + violation 列表（都是引用）。

    `required_action` 来自决策协议（目前只有 `approval`）：需要人工审批时**不是**
    FAIL，但也绝不是"可以继续动手"——引擎必须把它路由到审批门禁。
    """

    decision: Decision
    status: StageStatus = StageStatus.OK
    request_id: str = Field(min_length=1, max_length=_MAX_ID)
    trace_id: Optional[str] = Field(default=None, max_length=_MAX_ID)
    rule_set_hash: Optional[str] = Field(default=None, max_length=80)
    evidence_digest: Optional[str] = Field(default=None, max_length=80)
    required_action: Optional[str] = Field(default=None, max_length=40)
    validators: Tuple[str, ...] = ()
    violations: Tuple[ViolationRef, ...] = ()
    # H1：受控 reason。**派生字段，不进决策载荷**（决策协议仍是 1.0）——它回答的是
    # "这次 block 属于哪一类"，由 `client.decision_reason` 从 required_action +
    # violations 的 evidence 通道**算出来**，不是第二份判定。`None` = 说不出来，
    # 消费方（repair）必须按失败关闭处理，不许猜。
    reason_code: Optional[str] = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def _reason_matches_findings(self) -> "ValidationSummary":
        """没给就按同一套受控规则**派生**；给了就必须与发现一致（不许第二份判定）。

        为什么要在这里做：摘要有两个来源（`DecisionOutcome.summary` / `ValidationOutcome.summary`）
        与若干直接构造点（测试、恢复路径）。只在其中一处派生，别处就会出现"字段为空但其实是
        审批门禁"的摘要——消费方于是又回到"读不出理由"的老问题上。
        """

        derived = decision_reason(
            self.decision,
            required_action=self.required_action,
            violations=self.violations,
        )
        if self.reason_code is None:
            # 模型是 frozen 的：派生值用 object.__setattr__ 落进去（pydantic 2 的
            # after-validator 不接受"返回另一个实例"，见它的 UserWarning）。
            object.__setattr__(self, "reason_code", derived)
            return self
        if self.reason_code not in REASON_CODES:
            raise ValueError(
                f"未知的 reason_code {self.reason_code!r}；只接受 {sorted(REASON_CODES)}，"
                "拒绝在未知理由下继续"
            )
        if derived != self.reason_code:
            # **无条件**比：只在"派生出东西"时才比，会让 allow（或 block + 空 violations +
            # 无审批要求）的摘要带上任意受控 reason——这个字段就变成了第二个判定通道，
            # 而消费方（修复节点）会按一个发现并不支持的理由分流。派生不出理由时只能是 None。
            raise ValueError(
                f"reason_code 与发现不一致：{self.reason_code!r} != {derived!r}"
                "（受控 reason 是从发现派生的，不许成为第二个判定通道）"
            )
        return self

    @property
    def reason(self) -> Optional[str]:
        """受控 reason 的只读视图；说不出来时返回 None，**绝不返回一个默认值**。"""

        return self.reason_code

    @property
    def failing(self) -> bool:
        """PASS / FAIL 只由结构化 Decision 决定，不由文本或异常决定。"""

        return self.decision is Decision.BLOCK

    @property
    def needs_approval(self) -> bool:
        return self.required_action == "approval"


class PlanStep(StrictModel):
    step_id: str = Field(min_length=1, max_length=_MAX_ID)
    node: NodeId
    target: Optional[str] = None
    summary: str = Field(default="", max_length=_MAX_TEXT)

    _check_target = field_validator("target")(
        lambda value: None if value is None else _relative_path(value)
    )


class Counters(StrictModel):
    """循环与预算计数。上限击穿即进入 needs_human。"""

    repair_rounds: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    node_runs: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    cost_units: int = Field(default=0, ge=0)
    elapsed_ms: int = Field(default=0, ge=0)


class RunLimits(StrictModel):
    """硬上限。默认值刻意保守：宁可早点交给人，也不无限自调用。"""

    max_repair_rounds: int = Field(default=2, ge=0, le=50)
    max_tool_calls: int = Field(default=4, ge=0, le=200)
    max_node_runs: int = Field(default=32, ge=1, le=500)
    max_tokens: int = Field(default=20000, ge=0)
    max_cost_units: int = Field(default=1000, ge=0)
    max_elapsed_ms: int = Field(default=120000, ge=0)
    max_approval_uses: int = Field(default=1, ge=1, le=50)


class ApprovalUse(StrictModel):
    """审批引用的使用记录：绑定 action 摘要，限期，可复用次数由上限决定。"""

    node: NodeId
    approval_id: str = Field(min_length=1, max_length=_MAX_ID)
    action_hash: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=_MAX_ID)
    issued_at: str = Field(min_length=1, max_length=40)
    expires_at: str = Field(min_length=1, max_length=40)
    uses: int = Field(default=1, ge=1)


class NodeRun(StrictModel):
    """一个节点的一次执行记录：状态 + 幂等键 + 输出摘要（不含正文）。"""

    node: NodeId
    attempt: int = Field(default=1, ge=1)
    status: StageStatus
    idempotency_key: str = Field(min_length=1, max_length=_MAX_ID)
    outcome_digest: str = Field(min_length=1, max_length=80)
    label: str = Field(default="", max_length=64)
    failure_code: Optional[FailureCode] = None
    detail: str = Field(default="", max_length=_MAX_TEXT)

    _check_detail = field_validator("detail")(_safe_state_text)


class FailureRef(StrictModel):
    code: FailureCode
    node: Optional[NodeId] = None
    detail: str = Field(default="", max_length=_MAX_TEXT)

    _check_detail = field_validator("detail")(_safe_state_text)


class PlatformSnapshot(StrictModel):
    """恢复时的兼容性凭据：规则集 / 索引 / 工具 schema / 协议版本。

    任何一项变了，旧 allow 就不能沿用——见 `checkpoint.verify_compatibility`。
    """

    policy_version: str = POLICY_VERSION
    decision_schema_version: str = SCHEMA_VERSION
    state_schema_version: str = STATE_SCHEMA_VERSION
    rule_set_hash: Optional[str] = Field(default=None, max_length=80)
    index_version: Optional[str] = Field(default=None, max_length=80)
    tool_schema_hash: Optional[str] = Field(default=None, max_length=80)

    def incompatible_with(self, other: "PlatformSnapshot") -> Tuple[str, ...]:
        """返回不兼容的维度名（有序、去重），供恢复时报告与重新评估。"""

        changed: list[str] = []
        for name in (
            "policy_version",
            "decision_schema_version",
            "rule_set_hash",
            "index_version",
            "tool_schema_hash",
        ):
            before = getattr(self, name)
            after = getattr(other, name)
            if before != after and (before is not None or after is not None):
                changed.append(name)
        return tuple(changed)


class GraphState(StrictModel):
    """最小图状态：只有推进工作流需要的引用。

    它是**不可变**的：节点返回新实例，引擎负责替换。这样 checkpoint 里存的
    每一版都是完整、可校验的快照，不存在"半套状态"。
    """

    state_schema_version: str = STATE_SCHEMA_VERSION
    task_id: str = Field(min_length=1, max_length=_MAX_ID)
    revision: int = Field(default=0, ge=0)
    stage: NodeId = NodeId.REQUIREMENT_ANALYSIS
    status: RunStatus = RunStatus.RUNNING
    request_id: str = Field(default="", max_length=_MAX_ID)
    trace_id: Optional[str] = Field(default=None, max_length=_MAX_ID)
    requirements: Tuple[str, ...] = ()
    plan: Tuple[PlanStep, ...] = ()
    artifacts: Tuple[ArtifactRef, ...] = ()
    contexts: Tuple[ContextRef, ...] = ()
    traces: Tuple[PolicyTraceRef, ...] = ()
    validation: Optional[ValidationSummary] = None
    test_validation: Optional[ValidationSummary] = None
    counters: Counters = Field(default_factory=Counters)
    limits: RunLimits = Field(default_factory=RunLimits)
    approvals: Tuple[ApprovalUse, ...] = ()
    runs: Tuple[NodeRun, ...] = ()
    failure: Optional[FailureRef] = None
    snapshot: Optional[PlatformSnapshot] = None
    notes: Tuple[str, ...] = ()

    @field_validator("state_schema_version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        if value not in SUPPORTED_STATE_SCHEMA_VERSIONS:
            raise ValueError(f"未知的编排状态版本：{value}")
        return value

    @field_validator("requirements", "notes")
    @classmethod
    def _check_texts(cls, value: Tuple[str, ...]) -> Tuple[str, ...]:
        return tuple(_safe_text(item) for item in value)

    # ---- 便捷访问（都返回新实例，绝不原地改） --------------------------------

    def payload(self) -> dict[str, Any]:
        """规范化 JSON 载荷：checkpoint、幂等键与报告共用同一种序列化。"""

        return json.loads(self.model_dump_json())

    def digest(self) -> str:
        return canonical_digest(self.payload())

    def replace(self, **updates: Any) -> "GraphState":
        data = self.payload()
        data.update(updates)
        data["revision"] = self.revision + 1
        return GraphState.model_validate(data)

    def last_run(self, node: NodeId) -> Optional[NodeRun]:
        for run in reversed(self.runs):
            if run.node is node:
                return run
        return None

    def completed(self, node: NodeId, idempotency_key: str) -> bool:
        """该节点是否已经用**同一个幂等键**成功跑过（重试不重复副作用）。"""

        return any(
            run.node is node
            and run.status in (StageStatus.OK, StageStatus.SKIPPED)
            and run.idempotency_key == idempotency_key
            for run in self.runs
        )

    def trace_for(self, node: NodeId) -> Optional[PolicyTraceRef]:
        for trace in reversed(self.traces):
            if trace.node is node:
                return trace
        return None

    def approval_for(self, action_hash: str) -> Optional[ApprovalUse]:
        for approval in reversed(self.approvals):
            if approval.action_hash == action_hash:
                return approval
        return None


def empty_state(
    task_id: str,
    *,
    limits: Optional[RunLimits] = None,
    request_id: str = "",
    trace_id: Optional[str] = None,
    requirements: Tuple[str, ...] = (),
) -> GraphState:
    """新建一个 RUNNING 状态。调用方必须显式给出 task_id。"""

    return GraphState(
        task_id=task_id,
        request_id=request_id,
        trace_id=trace_id,
        requirements=requirements,
        limits=limits or RunLimits(),
    )
