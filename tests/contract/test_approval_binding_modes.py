"""G4 审批绑定档位测试：模式化审批可用，但防重放性质一条都不能少。

背景（实测）：审批只绑 action_hash，而 action_hash 覆盖运行时生成的 action_id /
tool_use_id，于是"同一条命令、只换调用编号"条子立刻作废——受治理的会话连 pytest 都跑不了。
这里验证补上的**模式化审批**（binding=pattern）确实解决了可用性缺口，同时逐条固定住
不可让步的性质：

1. 同一 action_id 绝不执行第二次（台账 + 审计链两处把关，与审批无关）；
2. 参数一变、模式匹配不上即拒绝；
3. 次数上限先原子占用后执行，用尽即拒绝，且写进台账 / 审计；
4. 过期、跨主体盗用、角色不足一律拒绝；
5. 自相矛盾或未知的审批字段一律拒绝（单次绑定仍是默认档）。
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from enforcement.approvals import ApprovalError, ApprovalRecord, load_approval
from enforcement.audit import FileAuditSink, NullAuditSink
from enforcement.ledger import EnforcementLedger
from enforcement.models import Decision, ReasonCode, utc_now
from enforcement.precheck import pre_execute
from enforcement_support import (
    EnforcementPaths,
    approval_for,
    enforcement_paths,
    make_action,
)

pytestmark = pytest.mark.contract

COMMAND_PATTERN = "^print[(]'ok'[)]$"


def shell_params(command: str = "print('ok')") -> dict[str, object]:
    return {"command": command, "description": "demo"}


def pattern_approval(
    request,
    *,
    patterns: dict[str, str],
    max_uses: int = 3,
    ttl: int = 300,
    expired: bool = False,
    subject: str | None = None,
    roles: tuple[str, ...] = ("reviewer",),
    approval_id: str = "approval-pattern-1",
) -> ApprovalRecord:
    now = utc_now()
    if expired:
        granted_at, expires_at = now - timedelta(hours=2), now - timedelta(hours=1)
    else:
        granted_at, expires_at = now - timedelta(seconds=1), now + timedelta(seconds=ttl)
    return ApprovalRecord(
        approval_id=approval_id,
        binding="pattern",
        tool_id=request.tool_id,
        subject=subject or request.subject or "local-user",
        granted_by="alice",
        granted_by_roles=roles,
        granted_at=granted_at,
        expires_at=expires_at,
        max_uses=max_uses,
        param_patterns=patterns,
    )


def run_pre(
    paths: EnforcementPaths,
    tool_id: str,
    params: dict[str, object],
    *,
    approval=None,
    action_id: str = "act-1",
    subject: str = "local-user",
    roles: tuple[str, ...] = ("owner",),
    sink=None,
    request=None,
):
    registry = paths.registry_object()
    request = request or make_action(
        registry, paths, tool_id, params, roles=roles, subject=subject, action_id=action_id
    )
    ledger = EnforcementLedger(paths.ledger)
    audit = sink if sink is not None else FileAuditSink(paths.audit, workspace=paths.workspace)
    outcome = pre_execute(
        request, registry=registry, ledger=ledger, sink=audit, approval=approval
    )
    return outcome, request


# --------------------------------------------------------------------------- 基线四例


def test_without_any_approval_the_governed_action_is_refused(enforcement_paths):
    outcome, _ = run_pre(enforcement_paths, "exec.shell", shell_params())

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.APPROVAL_REQUIRED


def test_single_binding_stays_the_default_and_binds_the_exact_call(enforcement_paths):
    paths = EnforcementPaths(enforcement_paths.root / "single")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = approval_for(first)
    assert approval.binding.value == "action", "单次绑定必须仍是默认档"

    exact, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, request=first)
    assert exact.decision.decision is not Decision.BLOCK, exact.decision.check("approval").detail

    # 只换调用编号：单次绑定按定义应当失效（更严格档），这是它的语义而不是缺陷
    renamed, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-2")
    assert renamed.decision.decision is Decision.BLOCK
    assert renamed.decision.reason_code is ReasonCode.APPROVAL_INVALID
    assert "action_hash" in renamed.decision.check("approval").detail


def test_used_single_binding_approval_is_refused(enforcement_paths):
    paths = EnforcementPaths(enforcement_paths.root / "used")
    registry = paths.registry_object()
    request = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = approval_for(request)
    EnforcementLedger(paths.ledger).record_approval_use(
        approval.approval_id, action_hash=request.action_hash
    )

    outcome, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, request=request)

    assert outcome.decision.decision is Decision.BLOCK
    assert "已被使用" in outcome.decision.check("approval").detail


def test_approver_must_hold_the_approval_role(enforcement_paths):
    paths = EnforcementPaths(enforcement_paths.root / "role")
    registry = paths.registry_object()
    request = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(
        request, patterns={"command": COMMAND_PATTERN}, roles=("developer",)
    )

    outcome, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-1")

    assert outcome.decision.decision is Decision.BLOCK
    assert "审批权" in outcome.decision.check("approval").detail


# --------------------------------------------------------------------------- 模式化审批


def test_pattern_approval_lets_the_same_command_run_under_a_new_call_id(enforcement_paths):
    """G4 的可用性缺口：同一条命令、同一个申请人，只换调用编号必须仍然放行。"""

    paths = EnforcementPaths(enforcement_paths.root / "pattern")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(first, patterns={"command": COMMAND_PATTERN}, max_uses=3)

    one, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-1")
    two, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-2")

    assert one.decision.decision is not Decision.BLOCK, one.decision.check("approval").detail
    assert two.decision.decision is not Decision.BLOCK, two.decision.check("approval").detail
    assert "binding=pattern" in two.decision.check("approval").detail
    assert two.decision.check("approval_use").detail.startswith("第 2/3 次")


def test_pattern_approval_rejects_a_command_that_does_not_match_the_pattern(enforcement_paths):
    paths = EnforcementPaths(enforcement_paths.root / "mismatch")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(first, patterns={"command": COMMAND_PATTERN}, max_uses=3)

    # echo hi 本身在白名单内（^echo( .*)?$），但它不匹配审批模式
    outcome, _ = run_pre(
        paths, "exec.shell", shell_params("echo hi"), approval=approval, action_id="call-other"
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.APPROVAL_INVALID
    assert "不匹配审批模式" in outcome.decision.check("approval").detail


def test_pattern_approval_stops_at_the_declared_use_limit(enforcement_paths):
    paths = EnforcementPaths(enforcement_paths.root / "quota")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(first, patterns={"command": COMMAND_PATTERN}, max_uses=2)

    for index in (1, 2):
        allowed, _ = run_pre(
            paths, "exec.shell", shell_params(), approval=approval, action_id=f"call-{index}"
        )
        assert allowed.decision.decision is not Decision.BLOCK, allowed.decision.check("approval").detail

    exhausted, _ = run_pre(
        paths, "exec.shell", shell_params(), approval=approval, action_id="call-3"
    )

    assert exhausted.decision.decision is Decision.BLOCK
    assert exhausted.decision.reason_code is ReasonCode.APPROVAL_INVALID
    assert "次数上限" in exhausted.decision.check("approval").detail
    # 额度占用必须真的写进台账：2 次成功 = 2 条 approval_used
    assert len(EnforcementLedger(paths.ledger).approval_uses(approval.approval_id)) == 2


def test_pattern_approval_never_crosses_subjects(enforcement_paths):
    paths = EnforcementPaths(enforcement_paths.root / "subject")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(
        first, patterns={"command": COMMAND_PATTERN}, subject="someone-else"
    )

    outcome, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-1")

    assert outcome.decision.decision is Decision.BLOCK
    assert "主体" in outcome.decision.check("approval").detail


def test_expired_pattern_approval_is_refused(enforcement_paths):
    paths = EnforcementPaths(enforcement_paths.root / "expired")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(first, patterns={"command": COMMAND_PATTERN}, expired=True)

    outcome, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-1")

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.APPROVAL_INVALID
    assert "过期" in outcome.decision.check("approval").detail


def test_the_same_action_id_can_never_run_twice_even_with_pattern_approval(enforcement_paths):
    """放宽"人工签条"这一环，绝不能放宽按 action_id 的重放拦截。"""

    paths = EnforcementPaths(enforcement_paths.root / "replay")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(first, patterns={"command": COMMAND_PATTERN}, max_uses=5)

    one, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-1")
    assert one.decision.decision is not Decision.BLOCK

    replay, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-1")

    assert replay.decision.decision is Decision.BLOCK
    assert replay.decision.reason_code is ReasonCode.ACTION_REPLAY


def test_approval_quota_is_returned_when_the_audit_is_unwritable(enforcement_paths):
    """失败关闭不能变成死锁：动作没执行，额度必须还回去。"""

    paths = EnforcementPaths(enforcement_paths.root / "release")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(first, patterns={"command": COMMAND_PATTERN}, max_uses=1)

    blocked, _ = run_pre(
        paths, "exec.shell", shell_params(), approval=approval, sink=NullAuditSink()
    )
    assert blocked.decision.decision is Decision.BLOCK
    assert blocked.decision.reason_code is ReasonCode.AUDIT_UNAVAILABLE
    ledger = EnforcementLedger(paths.ledger)
    assert ledger.of_kind("approval_use_released"), "审计不可写时必须归还审批额度"

    retried, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval)
    assert retried.decision.decision is not Decision.BLOCK, retried.decision.check("approval_use").detail
    assert retried.decision.check("approval_use").detail.startswith("第 1/1 次")


def test_pattern_matching_refuses_unsupported_param_shapes(enforcement_paths):
    """列表类参数不支持模式匹配：宁可在审批阶段拒绝，也不做宽松转换。"""

    paths = EnforcementPaths(enforcement_paths.root / "shape")
    registry = paths.registry_object()
    request = make_action(
        registry,
        paths,
        "exec.process",
        {"argv": ["python", "-c", "print(1)"], "description": "demo"},
        roles=("owner",),
    )
    approval = pattern_approval(request, patterns={"argv": ".*"}, max_uses=2)

    outcome, _ = run_pre(
        paths,
        "exec.process",
        {"argv": ["python", "-c", "print(1)"], "description": "demo"},
        approval=approval,
        action_id="call-1",
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.APPROVAL_INVALID
    assert "不支持模式匹配" in outcome.decision.check("approval").detail


# --------------------------------------------------------------------------- 声明校验


def test_contradictory_or_unknown_approval_fields_are_refused(tmp_root):
    now = utc_now()
    common = {
        "approval_id": "a-1",
        "tool_id": "exec.shell",
        "subject": "local-user",
        "granted_by": "alice",
        "granted_by_roles": ("reviewer",),
        "granted_at": now,
        "expires_at": now + timedelta(seconds=300),
    }

    # 单次绑定不得声明多次使用，也不得声明参数模式
    with pytest.raises(ApprovalError):
        ApprovalRecord(**common, binding="action", action_hash="h", action_id="i", max_uses=2)
    with pytest.raises(ApprovalError):
        ApprovalRecord(
            **common,
            binding="action",
            action_hash="h",
            action_id="i",
            param_patterns={"command": COMMAND_PATTERN},
        )
    # 单次绑定必须声明 action_hash / action_id
    with pytest.raises(ApprovalError):
        ApprovalRecord(**common, binding="action")
    # 模式化审批不得声明 action_hash / action_id，且必须有参数模式
    with pytest.raises(ApprovalError):
        ApprovalRecord(**common, binding="pattern", action_hash="h", param_patterns={"command": ".*"})
    with pytest.raises(ApprovalError):
        ApprovalRecord(**common, binding="pattern")
    # 未知 binding 与非法正则
    with pytest.raises(Exception):
        ApprovalRecord(**common, binding="wildcard", action_hash="h", action_id="i")
    with pytest.raises(ApprovalError):
        ApprovalRecord(**common, binding="pattern", param_patterns={"command": "("})

    # 未知字段：审批 JSON 里多写一个字段就必须被拒绝（不是静默忽略）
    document = {
        **common,
        "binding": "action",
        "action_hash": "h",
        "action_id": "i",
        "granted_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=300)).isoformat(),
        "unexpected": True,
    }
    path = tmp_root / "approval-unknown.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ApprovalError) as error:
        load_approval(path)
    assert "unexpected" in str(error.value) or "不合法" in str(error.value)
