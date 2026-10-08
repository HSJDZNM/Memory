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
from pydantic import ValidationError

from policy.checkers import (
    UNPROVEN_CHANGED_TEXT,
    blocker_violation,
    uncovered_checker_violation,
    unproven_dependency_violation,
)
from policy.evidence import Blocker, ValidatorStatus
from policy.loader import load_rule_file
from policy.models import Decision as PolicyDecision
from policy.models import Evidence, Severity, ValidationResult, Violation

from conftest import ARCH_DIR, REPO_ROOT, make_context
from orchestration.client import (
    REASON_EVIDENCE_UNAVAILABLE,
    REASON_POLICY_VIOLATION,
    _violations_from,
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


def _rule():
    """一条真规则：下面两种"平台没能查"的 violation 都从规则出发，用判定侧的真函数产出。"""

    return load_rule_file(
        ARCH_DIR / "ARCH-001.yaml",
        repo_path="policies/architecture/ARCH-001.yaml",
        repo_root=REPO_ROOT,
    ).rule


def _platform_refs(*violations: Violation) -> tuple[ViolationRef, ...]:
    """判定侧产出 → 平台序列化 → 消费方投影。**不手抄形状**。

    手抄正是这条缺陷藏了这么久的原因：用例里把 `uncovered_checker` / `blocker` 写进
    `evidence_value`，而平台从来不那样写（它把 checker 名写进 value，`uncovered_checker` 写进
    detail，blocker 的 detail 是自由文本原因）。走真函数 + 真投影，形状漂移会当场把用例打红。
    `_violations_from` 就是 `ApiPolicyClient.evaluate/validate` 用的那一个投影。
    """

    result = ValidationResult(
        decision=PolicyDecision.BLOCK,
        request_id="task-1:validation:0",
        rule_set_hash=RULE_SET_HASH,
        violations=tuple(violations),
    )
    return _violations_from(result.to_decision_dict())


def _blocker_refs() -> tuple[ViolationRef, ...]:
    """关键验证器不可用：判定侧的真实产出（blocker_violation）。"""

    return _platform_refs(
        blocker_violation(
            _rule(),
            Blocker(
                validator_id="pytest",
                validator_version="1",
                status=ValidatorStatus.FAILED,
                reason="验证器没有跑成",
                checkers=("missing_tests",),
            ),
        )
    )


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
    """H10：证据通道（kind）决定归类，**不解析中文 message**；三种 violation 都是真产出。

    两条"平台没能查"（关键验证器不可用 / 没有验证器为 checker 产证据）都必须归到
    evidence_unavailable——它们改文件改不掉，修复节点据此停止而不是去改代码；
    一条"规则报了违规"（依赖无法证明）归 policy_violation。
    """

    rule = _rule()

    # 1) 关键验证器不可用（blocker_violation）：value 是验证器状态、detail 是自由文本原因
    blocker_refs = _blocker_refs()
    assert blocker_refs[0].evidence_kind == "validator"
    assert blocker_refs[0].evidence_value == ValidatorStatus.FAILED.value
    assert _summary(violations=blocker_refs).reason_code == REASON_EVIDENCE_UNAVAILABLE

    # 2) 没有验证器为 checker 产证据（uncovered_checker_violation）：value 是 checker 名
    uncovered_refs = _platform_refs(uncovered_checker_violation(rule, "missing_tests"))
    assert uncovered_refs[0].evidence_kind == "validator"
    assert uncovered_refs[0].evidence_value == "missing_tests"
    assert _summary(violations=uncovered_refs).reason_code == REASON_EVIDENCE_UNAVAILABLE

    # 3) 规则真的报了违规（依赖无法证明）：kind 是 "dependency"，可修
    dependency_refs = _platform_refs(
        unproven_dependency_violation(
            rule,
            make_context(file="src/order/controller.py", layer="controller"),
            (UNPROVEN_CHANGED_TEXT,),
        )
    )
    assert dependency_refs[0].evidence_kind == "dependency"
    assert _summary(violations=dependency_refs).reason_code == REASON_POLICY_VIOLATION


def test_a_summary_cannot_carry_a_reason_the_findings_do_not_support() -> None:
    """给了 reason_code 就必须等于派生值；派生不出来时只能是 None。

    旧实现只在"派生出东西"时才比，于是 allow（或 block + 空 violations + 无审批要求）的摘要
    可以带任意受控 reason——这个字段成了**第二个判定通道**，消费方按一个发现并不支持的理由分流。
    """

    with pytest.raises(ValidationError):
        ValidationSummary(
            decision=Decision.ALLOW,
            request_id="task-1:validation:0",
            reason_code=REASON_POLICY_VIOLATION,
        )

    with pytest.raises(ValidationError):
        ValidationSummary(
            decision=Decision.BLOCK,
            request_id="task-1:validation:0",
            reason_code=REASON_EVIDENCE_UNAVAILABLE,
        )

    # 正例：说得出理由时仍按同一套规则派生
    assert _summary(required_action="approval").reason_code == "approval_required"


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


def test_an_approval_gate_with_violations_still_stops_instead_of_writing(tmp_root) -> None:
    """审批门禁**带 violation** 时同样不许动手：`decision_reason` 第 1 条优先于 violations。

    所以「block + required_action=approval + 有 violation」是一个**能构造出来**的形态，
    而旧代码把审批只放在「空 violations」分支里判——这种形态会滑到下面，
    去规划一次正需要人来批准的写入（AGENTS 第 38 条）。
    """

    violation = Violation(
        rule_id="ARCH-001",
        rule_version=1,
        severity=Severity.ERROR,
        message="测试违规",
        evidence=Evidence(
            kind="dependency", subject="src/order/controller.py", value="repository"
        ),
    )
    refs = _platform_refs(violation)
    assert refs, "前提：这条 violation 真的会被投影出来"
    assert decision_reason(
        Decision.BLOCK, required_action="approval", violations=refs
    ) == "approval_required", "前提：审批优先于 violations（派生规则第 1 条）"

    state = _state_with(_summary(required_action="approval", violations=refs))
    context = node_context(tmp_root, task=task_spec("task-1"))

    outcome = repair(state, context)

    assert outcome.label == "needs_human"
    assert outcome.state.failure is not None
    assert outcome.state.failure.code is FailureCode.APPROVAL_MISSING
    assert outcome.state.status is RunStatus.NEEDS_HUMAN
    assert outcome.state.counters.repair_rounds == 0
    assert not outcome.state.artifacts, "审批门禁不许产生任何改动 artifact"


def test_repair_stops_when_the_platform_could_not_check(tmp_root) -> None:
    """R3：平台没能查 → BLOCKED，不规划改动。"""

    state = _state_with(_summary(violations=_blocker_refs()))
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
