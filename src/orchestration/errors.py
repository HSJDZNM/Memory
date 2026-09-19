"""编排层的失败分类与运行状态映射。

编排层是平台消费者，所以"失败"必须是一等公民：

1. 未知状态版本、未知节点、未知路由标签、未知字段一律报错（沿用核心层的严格解析纪律）；
2. 平台不可用、证据缺失、trace 断裂、审批不合法一律转成显式失败码，
   绝不"继续往下走"，也绝不退回默认放行；
3. **失败码决定终态**（`STATUS_BY_CODE`），节点与引擎都不许自己发明一个状态；
4. 失败详情是脱敏后的短文本：不带正文、凭据与绝对路径。
"""

from __future__ import annotations

from typing import Any, Final, Mapping, Optional

from .models import FailureCode, NodeId, RunStatus

__all__ = [
    "STATUS_BY_CODE",
    "ApprovalError",
    "CheckpointError",
    "CircuitOpenError",
    "EngineUnavailableError",
    "LimitExceeded",
    "NodeContractError",
    "OrchestrationError",
    "PlatformUnavailableError",
    "ResumeError",
    "StateError",
    "TraceError",
]


class OrchestrationError(Exception):
    """编排层所有显式失败的基类：带稳定失败码，调用方按码分支。"""

    code: FailureCode = FailureCode.STATE_INVALID

    def __init__(self, detail: str, *, node: Optional[NodeId] = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.node = node

    def failure_payload(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "node": None if self.node is None else self.node.value,
            "detail": self.detail,
        }


class StateError(OrchestrationError):
    """状态本身不合法（版本未知、字段缺失、不可序列化）。"""

    code = FailureCode.STATE_INVALID


class NodeContractError(OrchestrationError):
    """节点输出或图定义违反契约（未知节点、未知路由标签、缺字段）。"""

    code = FailureCode.NODE_CONTRACT_INVALID


class PlatformUnavailableError(OrchestrationError):
    """平台依赖不可用：策略服务、检索、验证器、工具或 trace。

    计划步骤 §平台故障：这类失败一律让高风险路径**停下**，不是"跳过"。
    """

    def __init__(
        self,
        detail: str,
        *,
        code: FailureCode = FailureCode.POLICY_UNAVAILABLE,
        node: Optional[NodeId] = None,
        status: Optional[int] = None,
    ) -> None:
        super().__init__(detail, node=node)
        self.code = code
        self.status = status


class TraceError(OrchestrationError):
    """trace 传播中断或来源不可信。"""

    code = FailureCode.TRACE_MISSING


class ApprovalError(OrchestrationError):
    """审批引用缺失、过期、主体不符、参数漂移或已被用完。"""

    code = FailureCode.APPROVAL_MISSING


class LimitExceeded(OrchestrationError):
    """硬上限被击穿：进入 needs_human，绝不无限自调用。"""

    code = FailureCode.LIMIT_REPAIR_ROUNDS


class CircuitOpenError(OrchestrationError):
    """反复失败后熔断打开：停止调用平台。"""

    code = FailureCode.CIRCUIT_OPEN


class EngineUnavailableError(OrchestrationError):
    """声明的图引擎不可用（例如要求 LangGraph 但当前环境版本不符）。"""

    code = FailureCode.ENGINE_UNAVAILABLE


class CheckpointError(OrchestrationError):
    """checkpoint 缺失、损坏或版本不兼容。"""

    code = FailureCode.CHECKPOINT_CORRUPT


class ResumeError(CheckpointError):
    """恢复路径上的显式失败（不允许用旧 allow 接着跑）。"""

    code = FailureCode.CHECKPOINT_INCOMPATIBLE


# 失败码 → 运行终态。BLOCKED 表示"平台侧说不清楚，禁止继续"，
# NEEDS_HUMAN 表示"上限或审批要求人来做决定"，FAILED 表示"编排自己坏了"。
STATUS_BY_CODE: Final[Mapping[FailureCode, RunStatus]] = {
    FailureCode.STATE_INVALID: RunStatus.FAILED,
    FailureCode.STATE_VERSION_UNKNOWN: RunStatus.FAILED,
    FailureCode.NODE_UNKNOWN: RunStatus.FAILED,
    FailureCode.NODE_CONTRACT_INVALID: RunStatus.FAILED,
    FailureCode.CHECKPOINT_MISSING: RunStatus.FAILED,
    FailureCode.CHECKPOINT_CORRUPT: RunStatus.FAILED,
    FailureCode.CHECKPOINT_INCOMPATIBLE: RunStatus.FAILED,
    FailureCode.ENGINE_UNAVAILABLE: RunStatus.FAILED,
    FailureCode.POLICY_UNAVAILABLE: RunStatus.BLOCKED,
    FailureCode.POLICY_BLOCKED: RunStatus.BLOCKED,
    FailureCode.KNOWLEDGE_UNAVAILABLE: RunStatus.BLOCKED,
    FailureCode.VALIDATOR_UNAVAILABLE: RunStatus.BLOCKED,
    FailureCode.EVIDENCE_UNAVAILABLE: RunStatus.BLOCKED,
    FailureCode.TOOL_UNAVAILABLE: RunStatus.BLOCKED,
    FailureCode.TOOL_DENIED: RunStatus.BLOCKED,
    FailureCode.TRACE_MISSING: RunStatus.BLOCKED,
    FailureCode.TRACE_FORGED: RunStatus.BLOCKED,
    FailureCode.CIRCUIT_OPEN: RunStatus.BLOCKED,
    FailureCode.SIDE_EFFECT_UNKNOWN: RunStatus.NEEDS_HUMAN,
    FailureCode.APPROVAL_MISSING: RunStatus.NEEDS_HUMAN,
    FailureCode.APPROVAL_EXPIRED: RunStatus.NEEDS_HUMAN,
    FailureCode.APPROVAL_SUBJECT_MISMATCH: RunStatus.NEEDS_HUMAN,
    FailureCode.APPROVAL_PARAM_MISMATCH: RunStatus.NEEDS_HUMAN,
    FailureCode.APPROVAL_CONSUMED: RunStatus.NEEDS_HUMAN,
    FailureCode.LIMIT_REPAIR_ROUNDS: RunStatus.NEEDS_HUMAN,
    FailureCode.LIMIT_TOOL_CALLS: RunStatus.NEEDS_HUMAN,
    FailureCode.LIMIT_NODE_RUNS: RunStatus.NEEDS_HUMAN,
    FailureCode.LIMIT_TOKENS: RunStatus.NEEDS_HUMAN,
    FailureCode.LIMIT_WALL_CLOCK: RunStatus.NEEDS_HUMAN,
    FailureCode.LIMIT_COST: RunStatus.NEEDS_HUMAN,
}


def status_for(error: OrchestrationError) -> RunStatus:
    """失败码 → 终态；未登记的失败码一律按 FAILED 处理（不猜、不放行）。"""

    return STATUS_BY_CODE.get(error.code, RunStatus.FAILED)
