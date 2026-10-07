"""同一条受控判据的两份实现必须给出同一个结论（H1 / L15 的跨侧契约）。

`decision_reason` 在两侧各有一份：`adapters.dsh.hooks`（Hook 审计与账本按它归类）与
`orchestration.models`（消费方的修复节点按它分流，violation 经 `ViolationRef` 投影）。
两份实现曾经**都读错通道**：hooks 读 `evidence.detail`，而 blocker 的 detail 是自由文本
原因（永远比不中受控取值）；编排侧读 `evidence_value`，而平台从不把 "uncovered_checker" /
"blocker" 写进 value。真实载荷上，一次"平台没能查"于是被判成"规则报了违规"——修复节点
拿着一个平台根本没查的结论去改文件，这正是 H1 要防的事。

这条用例是修复的意义所在：载荷用 `policy.checkers` 的**真函数**产出、经
`ValidationResult.to_decision_dict()` 序列化（不手抄形状），两侧必须给出同一个 reason。
"""

from __future__ import annotations

import pytest

from policy.checkers import (
    UNPROVEN_CHANGED_TEXT,
    blocker_violation,
    uncovered_checker_violation,
    unproven_dependency_violation,
)
from policy.evidence import Blocker, ValidatorStatus
from policy.loader import load_rule_file
from policy.models import Decision as PolicyDecision
from policy.models import RequiredAction, ValidationResult

from conftest import ARCH_DIR, REPO_ROOT, make_context

pytestmark = pytest.mark.contract

BLOCKER_LABEL = "关键验证器不可用（blocker）"
UNCOVERED_LABEL = "没有验证器为 checker 产证据（uncovered_checker）"
DEPENDENCY_LABEL = "依赖无法证明（规则真的报了违规）"
APPROVAL_LABEL = "审批门禁（block + 空 violations）"
ALLOW_LABEL = "放行（不是 block）"


def _rule():
    return load_rule_file(
        ARCH_DIR / "ARCH-001.yaml",
        repo_path="policies/architecture/ARCH-001.yaml",
        repo_root=REPO_ROOT,
    ).rule


def _payload(*violations, required_action=None, decision=PolicyDecision.BLOCK):
    """判定侧产出 → 协议载荷：走真模型 + to_decision_dict，不手抄形状。"""

    result = ValidationResult(
        decision=decision,
        request_id="parity-1",
        required_action=required_action,
        violations=tuple(violations),
    )
    return result.to_decision_dict()


def _payloads() -> dict[str, tuple[dict, object]]:
    rule = _rule()
    return {
        BLOCKER_LABEL: (
            _payload(
                blocker_violation(
                    rule,
                    Blocker(
                        validator_id="pytest",
                        validator_version="1",
                        status=ValidatorStatus.FAILED,
                        reason="验证器没有跑成",
                        checkers=("missing_tests",),
                    ),
                )
            ),
            "evidence_unavailable",
        ),
        UNCOVERED_LABEL: (
            _payload(uncovered_checker_violation(rule, "missing_tests")),
            "evidence_unavailable",
        ),
        DEPENDENCY_LABEL: (
            _payload(
                unproven_dependency_violation(
                    rule,
                    make_context(file="src/order/controller.py", layer="controller"),
                    (UNPROVEN_CHANGED_TEXT,),
                )
            ),
            "policy_violation",
        ),
        APPROVAL_LABEL: (_payload(required_action=RequiredAction.APPROVAL), "approval_required"),
        ALLOW_LABEL: (_payload(decision=PolicyDecision.ALLOW), None),
    }


def _hook_reason(payload: dict) -> object:
    from adapters.dsh.hooks import decision_reason

    return decision_reason(ValidationResult.from_decision_dict(payload))


def _orchestration_reason(payload: dict) -> object:
    from orchestration.client import _violations_from
    from orchestration.models import Decision as OrchestrationDecision
    from orchestration.models import decision_reason

    return decision_reason(
        OrchestrationDecision.BLOCK
        if payload["decision"] == "block"
        else OrchestrationDecision.ALLOW,
        required_action=payload.get("required_action"),
        violations=_violations_from(payload),
    )


@pytest.mark.parametrize(
    "label",
    [BLOCKER_LABEL, UNCOVERED_LABEL, DEPENDENCY_LABEL, APPROVAL_LABEL, ALLOW_LABEL],
)
def test_both_sides_derive_the_same_reason(label: str) -> None:
    payload, expected = _payloads()[label]

    hook = _hook_reason(payload)
    orchestration = _orchestration_reason(payload)

    assert hook == expected, label + "：" + "hooks 得到 " + repr(hook)
    assert orchestration == expected, label + "：" + "编排侧得到 " + repr(orchestration)
    assert hook == orchestration


def test_the_old_detail_rule_could_not_match_the_blocker_shape() -> None:
    """把"旧判据为什么恒假"的形状钉下来：blocker 的 detail 是自由文本原因。

    旧 hooks 判据是 `kind == "validator" and detail in {"uncovered_checker", "blocker"}`：
    只有 uncovered_checker 那条能命中；旧编排判据读的是 value，而平台从不写那两个取值。
    """

    payload, _ = _payloads()[BLOCKER_LABEL]
    evidence = payload["violations"][0]["evidence"]
    assert evidence["kind"] == "validator"
    assert evidence["detail"] not in {"uncovered_checker", "blocker"}
    assert evidence["value"] != "blocker"

    uncovered, _ = _payloads()[UNCOVERED_LABEL]
    uncovered_evidence = uncovered["violations"][0]["evidence"]
    assert uncovered_evidence["kind"] == "validator"
    assert uncovered_evidence["detail"] == "uncovered_checker"
