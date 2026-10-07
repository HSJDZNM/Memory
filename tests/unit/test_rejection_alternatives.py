"""M4/M5 拒绝理由要能“一次改对”，且安全语义一个字不放宽。

以下两件事缺一不可，每组用例都同时断言：

1. **可改对**：命令类阻断（组合 / 被禁片段 / 白名单不匹配）与审批类阻断
   （approval_required / approval_invalid）的理由里必须给出**可用的替代形态**——注册表里
   声明的 allowed_commands 与已签发审批里声明的 param_patterns（M4）；
   越界拒绝还要写清“本会话可用的读取范围形态”（M5）；
2. **不放宽**：同一组用例的另一半断言“该拦的还是拦”（原因码不变），
   且理由里**只出现已声明的数据**：不出现绝对路径、工作区路径或凭据；
   没有声明白名单的工具，理由也不得凭空编一个出来。

这些理由会进审计链、进代理的面向模型输出，因此它们不只是提示语，而是受测的契约。
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from enforcement.approvals import ApprovalBinding, ApprovalRecord
from enforcement.audit import FileAuditSink
from enforcement.ledger import EnforcementLedger
from enforcement.models import CheckStatus, Decision, ReasonCode, utc_now
from enforcement.precheck import pre_execute

from enforcement_support import EnforcementPaths, make_action, write_registry

pytestmark = pytest.mark.contract

# 只读工具 + 受保护前缀：越界拒绝（path_out_of_scope）的最小形态。
GUARDED_READ = {
    "id": "probe.read",
    "title": "probe read",
    "agent": "dsh",
    "tool_name": "read",
    "schema_version": "1.0",
    "risk": "read_only",
    "effect": "none",
    "driver": "none",
    "required_permissions": ["repo.read"],
    "audit_failure": "degrade",
    "parameters": [
        {
            "name": "file_path",
            "type": "path",
            "required": True,
            "path_scope": "workspace",
            "blocked_prefixes": ["policies"],
        }
    ],
}


def shell_spec(paths: EnforcementPaths):
    return paths.registry_object().tool("exec.shell")


def run(
    paths: EnforcementPaths,
    tool_id: str,
    params: dict,
    *,
    approval: ApprovalRecord | None = None,
    roles: tuple[str, ...] = ("owner",),
    action_id: str = "alt-1",
):
    registry = paths.registry_object()
    request = make_action(registry, paths, tool_id, params, roles=roles, action_id=action_id)
    return pre_execute(
        request,
        registry=registry,
        ledger=EnforcementLedger(paths.ledger),
        sink=FileAuditSink(paths.audit, workspace=paths.workspace),
        approval=approval,
    )


def pattern_approval(spec, *, patterns: dict, approval_id: str = "approval-alt-1") -> ApprovalRecord:
    """模式化审批：只声明 param_patterns（审批文件里的已声明数据）。"""

    now = utc_now()
    return ApprovalRecord(
        approval_id=approval_id,
        binding=ApprovalBinding.PATTERN,
        tool_id=spec.id,
        subject="local-user",
        granted_by="alice",
        granted_by_roles=("reviewer",),
        granted_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(seconds=300),
        max_uses=3,
        param_patterns=patterns,
    )


def assert_no_local_layout(detail: str, paths: EnforcementPaths) -> None:
    """理由不得靠泄露本机布局来“讲清楚”（与 N22 同一条要求）。"""

    assert paths.workspace.as_posix() not in detail
    assert str(paths.root) not in detail


# --------------------------------------------------------------------------- 命令类：组合 / 白名单 / 被禁片段


def test_composition_block_lists_the_forms_that_would_be_accepted(tmp_root):
    """组合命令被拦时，理由里要有“单条语句的可用形态”。"""

    paths = EnforcementPaths(tmp_root / "alt-composition")
    spec = shell_spec(paths)

    outcome = run(paths, "exec.shell", {"command": "echo hi ; print('ok')", "description": "复合"})

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.COMMAND_COMPOSITION_BLOCKED
    detail = outcome.decision.check("command_composition").detail
    # 为什么被拦：这句一个字都不能少
    assert "命令包含组合/替换/重定向片段" in detail
    assert "';'" in detail
    # 可用的替代：注册表里声明的形态原样出现
    assert "可用替代" in detail
    assert "注册表白名单允许的命令形态" in detail
    for item in spec.allowed_commands:
        assert repr(item) in detail, item
    assert_no_local_layout(detail, paths)


def test_whitelist_mismatch_keeps_the_declared_forms_and_names_the_missing_approval(tmp_root):
    """不在白名单里：原因码不变，但理由要说清“还差审批”。"""

    paths = EnforcementPaths(tmp_root / "alt-whitelist")
    spec = shell_spec(paths)

    outcome = run(
        paths,
        "exec.shell",
        {"command": "Get-ChildItem .", "description": "不在白名单内"},
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.COMMAND_NOT_ALLOWLISTED
    detail = outcome.decision.check("command_allowlist").detail
    assert "命令不在白名单内（完整匹配）" in detail
    for item in spec.allowed_commands:
        assert repr(item) in detail, item
    assert "可用替代" in detail
    assert "approval=required" in detail
    assert_no_local_layout(detail, paths)


def test_fragment_block_keeps_the_reason_and_the_forms(tmp_root):
    """被禁片段：白名单完整匹配也照拦，但要把可用形态一并给出。"""

    paths = EnforcementPaths(tmp_root / "alt-fragment")

    outcome = run(
        paths,
        "exec.shell",
        {"command": "echo hi --output=/tmp/leak.txt", "description": "写文件选项"},
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.COMMAND_FRAGMENT_BLOCKED
    detail = outcome.decision.check("command_fragments").detail
    assert "命令包含被禁片段" in detail
    assert "'--output'" in detail
    assert "可用替代" in detail
    assert "注册表白名单允许的命令形态" in detail
    assert_no_local_layout(detail, paths)


def test_first_failure_order_is_unchanged_for_a_command_that_fails_twice(tmp_root):
    """判定顺序不变：既不在白名单、又含分号时，仍然先报白名单。"""

    paths = EnforcementPaths(tmp_root / "alt-order")

    outcome = run(
        paths,
        "exec.shell",
        {"command": "xprint('ok'); print('bad')", "description": "两处都不合格"},
    )

    assert outcome.decision.reason_code is ReasonCode.COMMAND_NOT_ALLOWLISTED
    assert outcome.decision.check("command_composition").status is CheckStatus.FAILED


# --------------------------------------------------------------------------- 审批类


def test_missing_approval_reason_names_the_declared_modes(tmp_root):
    """缺审批：接下来要去哪里补什么，要写在理由里。"""

    paths = EnforcementPaths(tmp_root / "alt-approval-missing")

    outcome = run(paths, "exec.shell", {"command": "print('ok')", "description": "白名单内"})

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.APPROVAL_REQUIRED
    detail = outcome.decision.check("approval").detail
    assert "没有提供与当前 action_hash 绑定的审批记录" in detail
    assert "可用替代" in detail
    assert "注册表白名单允许的命令形态" in detail
    assert "binding=action" in detail and "binding=pattern" in detail
    assert_no_local_layout(detail, paths)


def test_pattern_approval_mismatch_shows_the_covered_form_and_still_allows_a_match(tmp_root):
    """审批模式不匹配：理由里有“条子到底覆盖什么”，而形态真对上时照常放行。"""

    paths = EnforcementPaths(tmp_root / "alt-approval-pattern")
    spec = shell_spec(paths)
    approval = pattern_approval(
        spec, patterns={"command": "^print[(]'ok'[)]$", "description": ".*"}
    )

    blocked = run(
        paths,
        "exec.shell",
        {"command": "echo hi", "description": "白名单内但审批没覆盖"},
        approval=approval,
        action_id="alt-pattern-blocked",
    )

    assert blocked.decision.decision is Decision.BLOCK
    assert blocked.decision.reason_code is ReasonCode.APPROVAL_INVALID
    detail = blocked.decision.check("approval").detail
    assert "参数 'command' 的取值不匹配审批模式" in detail
    assert "可用替代" in detail
    assert "binding=pattern" in detail
    assert "^print[(]'ok'[)]$" in detail
    for item in spec.allowed_commands:
        assert repr(item) in detail, item
    assert_no_local_layout(detail, paths)

    # 对照：同一条审批、形态对上就走通——理由变好用不等于判定变松
    allowed = run(
        paths,
        "exec.shell",
        {"command": "print('ok')", "description": "对上审批形态"},
        approval=approval,
        action_id="alt-pattern-allowed",
    )
    assert allowed.decision.decision is not Decision.BLOCK
    assert allowed.decision.check("approval").status is CheckStatus.PASSED


def test_alternatives_never_invent_a_whitelist_that_was_not_declared(tmp_root):
    """argv 类工具没有 allowed_commands：理由不得凭空编一个出来。"""

    paths = EnforcementPaths(tmp_root / "alt-no-whitelist")
    spec = paths.registry_object().tool("exec.process")
    assert not spec.allowed_commands

    outcome = run(
        paths,
        "exec.process",
        {"argv": ["python", "-c", "print(1)"], "description": "demo"},
    )

    assert outcome.decision.reason_code is ReasonCode.APPROVAL_REQUIRED
    detail = outcome.decision.check("approval").detail
    assert "可用替代" in detail
    assert "注册表白名单允许的命令形态" not in detail


# --------------------------------------------------------------------------- 只读越界（M5）


def test_read_scope_reason_names_the_usable_path_form(tmp_root):
    """越界拒绝要写清“本会话可用的读取范围形态”，且仍然是拒绝。"""

    paths = EnforcementPaths(tmp_root / "alt-scope")
    write_registry(paths.root, tools=(GUARDED_READ,))

    outcome = run(paths, "probe.read", {"file_path": "policies/ARCH-001.yaml"})

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.PATH_OUT_OF_SCOPE
    detail = outcome.decision.check("path_prefixes").detail
    assert "命中受保护前缀" in detail
    assert "本会话可用的读取范围形态" in detail
    assert "受控项目内的仓库相对路径" in detail
    assert "范围等于项目根时记为 ." in detail
    assert_no_local_layout(detail, paths)
