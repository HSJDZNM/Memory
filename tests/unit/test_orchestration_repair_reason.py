"""台阶 3a（H1/H10）：block 的受控 reason，与「修复节点不许凭感觉修」的接线。

为什么需要这组用例：block + violations=[] 在判定层是**合法**形态（审批门禁就是这一种），
但消费方修复节点把「没有 violations」一律读成「没有依据」，抛 NodeContractError——
于是一条「需要人批准」被翻译成「编排自己坏了」（终态 FAILED）。**缺陷在、定向套件全绿**，
所以这里的每一条都是新增的判据（AGENTS 第 45 条）。

三条边界同时钉住：

1. 审批门禁：不修、不放行 → NEEDS_HUMAN（AGENTS 第 38 条「到达审批节点 ≠ 用户批准」）；
2. 平台没能查：不产生任何 Change → BLOCKED；
3. 说不出理由的 block：**照旧**抛契约错误（失败关闭不许被这次改动打开）。
"""

from __future__ import annotations

import pytest

from orchestration.client import (
    REASON_EVIDENCE_UNAVAILABLE,
    REASON_POLICY_VIOLATION,
    decision_reason,
)
from orchestration.errors import NodeContractError
from orchestration.models import (
    Decision,
    FailureCode,
    GraphState,
    NodeId,
    RunLimits,
    RunStatus,
    StageStatus,
    ValidationSummary,
    ViolationRef,
    empty_state,
)
from orchestration.nodes import repair
from orchestration_support import node_context, task_spec

pytestmark = pytest.mark.contract

RULE_SET_HASH = "sha256:" + "a" * 64


def _summary(**overrides: object) -> ValidationSummary:
    payload: dict[str, object] = {
        "decision": Decision.BLOCK,
        "request_id": "task-1:validation:0",
        "rule_set_hash": RULE_SET_HASH,
    }
    payload.update(overrides)
    return ValidationSummary(**payload)


def _state_with(summary: ValidationSummary) -> GraphState:
    """一份「刚验证失败」的状态：validation 摘要在位，阶段停在 REPAIR。"""

    state = empty_state("task-1", limits=RunLimits(), trace_id="trace-1")
    return state.replace(stage=NodeId.REPAIR, validation=summary, status=StageStatus.FAILED)


# --------------------------------------------------------------- 受控 reason 的派生


def test_an_approval_gate_is_not_read_as_a_violation() -> None:
    """审批门禁：reason 是 approval_required，而且它是唯一合法的空 violations 形态。"""

    summary = _summary(required_action="approval")
    assert summary.violations == ()
    assert summary.reason_code == "approval_required"
    assert summary.reason == summary.reason_code


def test_evidence_channels_decide_between_policy_and_platform_failure() -> None:
    """H10：证据通道（kind/value）决定归类，**不解析中文 message**。"""

    policy = _summary(
        violations=(
            ViolationRef(
                rule_id="ARCH-001",
                rule_version=1,
                severity="error",
                message="Controller 不得直接访问 Repository。",
                evidence_kind="dependency",
                evidence_value="repository",
            ),
        )
    )
    assert policy.reason_code == REASON_POLICY_VIOLATION

    uncovered = _summary(
        violations=(
            ViolationRef(
                rule_id="TESTING-002",
                rule_version=1,
                severity="critical",
                message="没有验证器为 checker missing_tests 提供证据",
                evidence_kind="validator",
                evidence_value="uncovered_checker",
            ),
        )
    )
    assert uncovered.reason_code == REASON_EVIDENCE_UNAVAILABLE


def test_a_block_that_cannot_say_why_has_no_reason() -> None:
    """说不出来就是 None：**不许**把 None 读成某一种（那是发明依据）。"""

    assert _summary().reason_code is None
    assert _summary().reason is None
    assert decision_reason(Decision.ALLOW, required_action=None, violations=()) is None


# --------------------------------------------------------------- repair() 的动作


def test_repair_stops_at_the_approval_gate_instead_of_failing_the_run(tmp_root) -> None:
    """R2：审批门禁 → NEEDS_HUMAN，且**不产生任何 Change**。"""

    state = _state_with(_summary(required_action="approval"))
    context = node_context(tmp_root, task=task_spec("task-1"))

    outcome = repair(state, context)

    assert outcome.label == "needs_human"
    assert outcome.state.failure is not None
    assert outcome.state.failure.code is FailureCode.APPROVAL_MISSING
    # 终态由失败码决定（errors.STATUS_BY_CODE）：APPROVAL_MISSING → NEEDS_HUMAN，
    # 而不是"编排自己坏了"的 FAILED。
    assert outcome.state.status is RunStatus.NEEDS_HUMAN
    assert outcome.state.counters.repair_rounds == 0
    assert not any(
        run.node is NodeId.REPAIR and run.status is StageStatus.PENDING
        for run in outcome.state.runs
    )


def test_repair_stops_when_the_platform_could_not_check(tmp_root) -> None:
    """R3：平台没能查 → BLOCKED，不规划改动。"""

    state = _state_with(
        _summary(
            violations=(
                ViolationRef(
                    rule_id="TESTING-002",
                    rule_version=1,
                    severity="critical",
                    message="关键验证器不可用",
                    evidence_kind="validator",
                    evidence_value="blocker",
                ),
            ),
            reason_code=REASON_EVIDENCE_UNAVAILABLE,
        )
    )
    context = node_context(tmp_root, task=task_spec("task-1"))

    outcome = repair(state, context)

    assert outcome.label == "blocked"
    assert outcome.state.failure is not None
    assert outcome.state.failure.code is FailureCode.EVIDENCE_UNAVAILABLE
    assert outcome.state.status is RunStatus.BLOCKED
    assert outcome.state.counters.repair_rounds == 0


def test_repair_still_refuses_a_block_without_any_reason(tmp_root) -> None:
    """R1：说不出理由的 block 仍然是契约错误——失败关闭一个字都不放宽。"""

    state = _state_with(_summary())
    context = node_context(tmp_root, task=task_spec("task-1"))

    with pytest.raises(NodeContractError):
        repair(state, context)
