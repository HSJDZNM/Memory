"""Phase 4 × dsh 集成测试：受控执行链路与 PostToolUse 事后验证。

Phase 2 的 pre-execute Hook 只回答"规则允许吗"；Phase 4 追加两件事：

1. 受控工具（写类 + 高权限执行类）必须经过 Tool Registry 的授权链
   （主体 / 权限 / 参数白名单 / 命令白名单 / 审批 / 限流 / 审计），授权与具体动作绑定；
2. PostToolUse 补齐"执行后验证"：用执行前基线与运行时结果判断这次动作到底产生了什么效果。

没有注册表、没有主体、参数不在白名单里——一律阻断，而不是"规则没意见就放行"。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters.dsh.adapter import AdapterConfig, DshEventError, load_config
from adapters.dsh.enforcement import EnforcementBridge, bridge_from_config
from adapters.dsh.hooks import EXIT_ALLOW, EXIT_BLOCK, DshPreExecuteHook, run_hook
from policy.loader import load_rule_set
from policy.models import Decision

from conftest import REPO_ROOT, dsh_event, write_dsh_config

pytestmark = pytest.mark.integration


def payload(name: str, project_root: Path, **overrides: object) -> dict[str, object]:
    return dsh_event(name, cwd=str(project_root), **overrides)


def build_hook(config_path: Path, *, audit: Path | None = None) -> DshPreExecuteHook:
    config = load_config(config_path)
    rules = load_rule_set(config.rule_dirs, repo_root=config.rule_anchor)
    from adapters.dsh.hooks import AuditLedger

    return DshPreExecuteHook(
        config=config,
        rules=rules,
        ledger=None if audit is None else AuditLedger(audit),
    )


def records(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def enforcement_ledger_for(audit: Path) -> Path:
    return audit.with_name(f"{audit.stem}.enforcement-ledger{audit.suffix}")


def write_source(project_root: Path, relative: str, content: str) -> Path:
    target = project_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="")
    return target


# --------------------------------------------------------------------------- 写类工具


def test_governed_write_gets_a_bound_grant_and_runs_once(dsh_config_path, dsh_project):
    audit = dsh_project.parent / "audit.jsonl"
    outcome = run_hook(
        payload("pre-tool-use-edit-allow.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=audit,
    )

    assert outcome.exit_code == EXIT_ALLOW, outcome.stderr
    granted = [
        item
        for item in records(audit)
        if item.get("reason_code") == "enforcement_allow" and item.get("grant_id")
    ]
    assert granted, "允许的动作必须在审计里留下与动作绑定的授权凭据"
    assert granted[0]["action_hash"].startswith("sha256:")
    assert granted[0]["risk"] == "reversible_write"
    assert granted[0]["grant_expires_at"]


def test_policy_block_still_wins_and_never_reaches_the_executor(dsh_config_path, dsh_project):
    audit = dsh_project.parent / "audit.jsonl"
    outcome = run_hook(
        payload("pre-tool-use-edit-block.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=audit,
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "policy_block"
    assert "ARCH-001@1" in outcome.stderr
    # 规则阻断发生在 Phase 4 门禁之前：不会留下授权凭据
    assert not [item for item in records(audit) if item.get("grant_id")]


def test_missing_registry_blocks_governed_tools(tmp_root, dsh_project):
    config_path = write_dsh_config(
        tmp_root / "config" / "no-registry.yaml",
        project_root=dsh_project,
        rules=REPO_ROOT / "policies",
        registry=None,
        registry_approved=None,
    )
    outcome = run_hook(
        payload("pre-tool-use-edit-allow.json", dsh_project), config_path=config_path
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "enforcement_unavailable"


def test_missing_principal_blocks_governed_tools(tmp_root, dsh_project):
    config_path = write_dsh_config(
        tmp_root / "config" / "no-principal.yaml",
        project_root=dsh_project,
        rules=REPO_ROOT / "policies",
        principal=None,
    )
    outcome = run_hook(
        payload("pre-tool-use-edit-allow.json", dsh_project), config_path=config_path
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "principal_required"


# --------------------------------------------------------------------------- 高权限执行


def test_execute_tool_without_the_shell_permission_is_blocked(dsh_config_path, dsh_project):
    """pwsh 在 Phase 4 进入受控链路：默认角色没有 shell.exec，连参数白名单都到不了。"""

    outcome = run_hook(
        payload("pre-tool-use-pwsh-execute.json", dsh_project),
        config_path=dsh_config_path,
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "permission_denied"
    assert "shell.exec" in outcome.stderr


def test_unregistered_execute_tool_is_blocked_instead_of_degraded(dsh_config_path, dsh_project):
    """注册表里没有的执行类工具必须阻断，不能因为"不认识"就退化成放行。"""

    outcome = run_hook(
        payload(
            "pre-tool-use-pwsh-execute.json",
            dsh_project,
            tool_name="workflow",
            tool_input={"description": "跑一个子工作流"},
            tool_use_id="call-workflow",
        ),
        config_path=dsh_config_path,
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "tool_not_registered"


def test_execute_tool_with_permission_still_needs_an_approval(tmp_root, dsh_project):
    config_path = write_dsh_config(
        tmp_root / "config" / "owner.yaml",
        project_root=dsh_project,
        rules=REPO_ROOT / "policies",
        principal={"subject": "local-user", "roles": ["owner"]},
    )
    outcome = run_hook(
        payload("pre-tool-use-pwsh-execute.json", dsh_project), config_path=config_path
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "approval_required"
    assert "approval" in outcome.stderr


def test_execute_tool_with_a_command_outside_the_allowlist_is_blocked(tmp_root, dsh_project):
    config_path = write_dsh_config(
        tmp_root / "config" / "owner-2.yaml",
        project_root=dsh_project,
        rules=REPO_ROOT / "policies",
        principal={"subject": "local-user", "roles": ["owner"]},
    )
    outcome = run_hook(
        payload(
            "pre-tool-use-pwsh-execute.json",
            dsh_project,
            tool_input={"command": "Remove-Item -Recurse -Force .", "description": "cleanup"},
        ),
        config_path=config_path,
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "command_not_allowlisted"


# --------------------------------------------------------------------------- PostToolUse


def test_post_tool_use_validates_the_delegated_edit(dsh_config_path, dsh_project):
    audit = dsh_project.parent / "audit.jsonl"
    source = write_source(dsh_project, "src/shop/order_controller.py", "from service import OrderService\n")

    pre = run_hook(
        payload("pre-tool-use-edit-allow.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=audit,
    )
    assert pre.exit_code == EXIT_ALLOW

    # 模拟 Agent 运行时执行这次编辑（内容与请求参数一致）
    write_source(
        dsh_project,
        "src/shop/order_controller.py",
        "from service import OrderService\nfrom util import clock\n",
    )

    post = run_hook(
        payload("post-tool-use-edit.json", dsh_project, tool_use_id="call-edit-allow"),
        config_path=dsh_config_path,
        audit_path=audit,
    )
    assert post.exit_code == EXIT_ALLOW, post.stderr
    assert post.reason_code == "post_validated"

    stages = [item["stage"] for item in records(audit) if item.get("stage")]
    assert "pre_decision" in stages and "post_evidence" in stages and "final_decision" in stages
    final = [item for item in records(audit) if item.get("stage") == "final_decision"][-1]
    assert final["payload"]["outcome"] == "delivered"


def test_post_tool_use_flags_an_execution_that_changed_nothing(dsh_config_path, dsh_project):
    audit = dsh_project.parent / "audit.jsonl"
    write_source(dsh_project, "src/shop/order_controller.py", "from service import OrderService\n")

    pre = run_hook(
        payload("pre-tool-use-edit-allow.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=audit,
    )
    assert pre.exit_code == EXIT_ALLOW

    post = run_hook(
        payload("post-tool-use-edit.json", dsh_project, tool_use_id="call-edit-allow"),
        config_path=dsh_config_path,
        audit_path=audit,
    )

    assert post.exit_code == EXIT_BLOCK
    assert post.reason_code == "post_inconsistent"
    assert "没有任何变化" in post.stderr


def test_post_tool_use_requires_repair_when_the_result_does_not_parse(dsh_config_path, dsh_project):
    audit = dsh_project.parent / "audit.jsonl"
    write_source(dsh_project, "src/shop/order_controller.py", "from service import OrderService\n")

    run_hook(
        payload("pre-tool-use-edit-allow.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=audit,
    )
    write_source(dsh_project, "src/shop/order_controller.py", "from service import OrderService(\n")

    post = run_hook(
        payload("post-tool-use-edit.json", dsh_project, tool_use_id="call-edit-allow"),
        config_path=dsh_config_path,
        audit_path=audit,
    )

    assert post.exit_code == EXIT_BLOCK
    assert post.reason_code == "post_repair_required"
    assert "无法撤销" in post.stderr


def test_post_tool_use_without_a_pre_record_does_not_guess(dsh_config_path, dsh_project):
    """没有 pre-check 记录 = 证据不足：只记占位，然后**拒绝**（不得放行）。

    修前这条路径返回 None，hooks 把它读成 `post_not_required` 并放行——一次没有经过
    授权的执行（例如 pre 阶段根本没接线）于是伪装成「不需要事后核对」。占位记录照写：
    审计仍能区分「跑过 post 但没有基线」与「事后核对完成」。
    """

    audit = dsh_project.parent / "audit.jsonl"
    write_source(dsh_project, "src/shop/order_controller.py", "from service import OrderService\n")

    post = run_hook(
        payload("post-tool-use-edit.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=audit,
    )

    assert post.exit_code == EXIT_BLOCK
    assert post.reason_code == "post_error"
    assert "证据不足" in post.stderr
    notes = [item for item in records(audit) if item.get("payload", {}).get("stage_note")]
    assert notes and notes[0]["payload"]["stage_note"] == "post_without_pre"


def test_post_refuses_when_the_request_view_cannot_be_rebuilt(tmp_root: Path) -> None:
    """请求视图重建不出来（含 secret 参数）= 证据不足：拒绝，不得当放行。

    台账里的请求视图对 secret 参数只留摘要（AGENTS 第 16 条），事后因此重建不出
    ActionRequest、也算不出 action_hash。修前这条路径返回 None，hooks 把它读成
    post_not_required 并放行——而记录里写的却是「证据不足，按需修复处理」。
    """

    from adapters.dsh.enforcement import EnforcementBridge
    from enforcement.action import build_action_request
    from enforcement.audit import FileAuditSink
    from enforcement.ledger import EnforcementLedger
    from enforcement.registry import load_registry
    from enforcement_support import EnforcementPaths, write_registry

    secret_tool = {
        "id": "fs.write_secret",
        "title": "test write with a secret parameter",
        "agent": "dsh",
        "tool_name": "write",
        "schema_version": "1.0",
        "risk": "reversible_write",
        "effect": "file_write",
        "driver": "file_write",
        "required_permissions": ["repo.write"],
        "rollback": "file_snapshot",
        "post_checks": ["content_matches"],
        "parameters": [
            {"name": "file_path", "type": "path", "required": True, "path_scope": "workspace"},
            {"name": "content", "type": "string", "required": True, "secret": True},
        ],
    }
    paths = EnforcementPaths(tmp_root)
    write_registry(paths.root, tools=(secret_tool,))
    registry = load_registry(paths.registry, approved_path=paths.approved).registry
    bridge = EnforcementBridge(
        registry=registry,
        sink=FileAuditSink(paths.audit, workspace=paths.workspace),
        ledger=EnforcementLedger(paths.ledger),
        workspace=paths.workspace,
    )

    request = build_action_request(
        registry.tool("fs.write_secret"),
        {"file_path": "src/shop/x.py", "content": "VALUE = 1" + chr(10)},
        action_id="sess-secret:call-1",
        request_id="sess-secret",
        agent="dsh",
        agent_version="0.1.5-rc.1",
        trace_id=None,
        subject="local-user",
        roles=("developer",),
        permissions=registry.permissions_for(("developer",)),
        workspace=paths.workspace,
        ttl_seconds=registry.grant_ttl_seconds,
    )
    assert bridge.pre(request).decision.decision is not Decision.BLOCK

    with pytest.raises(DshEventError) as error:
        bridge.post(
            {
                "session_id": "sess-secret",
                "tool_use_id": "call-1",
                "tool_name": "write",
                "tool_response": "ok",
            }
        )
    assert "请求视图不可重建" in str(error.value)
    assert "证据不足" in str(error.value)


def test_bridge_state_records_do_not_store_file_content(dsh_config_path, dsh_project):
    audit = dsh_project.parent / "audit.jsonl"
    write_source(dsh_project, "src/shop/order_controller.py", "SECRET_MARKER = 1\nfrom service import OrderService\n")

    run_hook(
        payload("pre-tool-use-edit-allow.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=audit,
    )

    text = audit.read_text(encoding="utf-8")
    assert "SECRET_MARKER" not in text
    ledger = [
        item
        for item in records(enforcement_ledger_for(audit))
        if item.get("kind") == "pre_state"
    ]
    assert ledger, "执行前基线必须写进台账，否则事后无法比对"
    assert ledger[0]["baselines"][0]["sha256"].startswith("sha256:")


def test_bridge_can_be_built_directly_from_a_config(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    bridge = bridge_from_config(config)

    assert isinstance(bridge, EnforcementBridge)
    assert bridge.spec_for("edit").id == "fs.edit"
    assert bridge.spec_for("nope") is None
    assert bridge.sink.path != bridge.ledger.path


# --------------------------------------------------------------------------- N16：委派路径的退出码
#
# 修前的机制（05-emergent-issues.md §2.1）：注册表给 exec.pwsh / exec.bash 声明了
# post_checks=[exit_code_zero]，但"由 Agent 运行时执行"这条委派路径上，退出码从来没有进过
# ExecutionRecord —— 插件只转发 result.content 的文本，post_event_fields 只取四个字段，
# 于是 exit_code_zero 必然判 False（"命令没有退出码"）→ repair_required → dsh 用策略错误
# 替换掉工具输出。下面四条用例走的是**真实桥接**（插件的 PostToolUse 载荷形状 →
# DshPreExecuteHook.post_execute → 审计），而不是手工构造一个带退出码的 record。


def write_pattern_approval(
    path: Path,
    *,
    tool_id: str,
    subject: str,
    command_pattern: str,
    max_uses: int = 5,
) -> Path:
    """写一张模式化审批（binding=pattern）。

    会话里 action_id / tool_use_id 每次都现生成（N24），单次绑定必然失配，
    因此只有 pattern 档能让测试真的走到"放行 → 事后核对"这一段。
    """

    from datetime import timedelta

    from enforcement.approvals import ApprovalRecord
    from enforcement.models import utc_now

    now = utc_now()
    record = ApprovalRecord(
        approval_id="approval-n16-pwsh",
        binding="pattern",
        tool_id=tool_id,
        subject=subject,
        granted_by="alice",
        granted_by_roles=("reviewer",),
        granted_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(seconds=300),
        max_uses=max_uses,
        param_patterns={"command": command_pattern},
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json() + chr(10), encoding="utf-8", newline="")
    return path


def pwsh_config(tmp_root: Path, dsh_project: Path, *, name: str) -> Path:
    """owner 角色 + 模式化审批：让 pwsh 的 pre-check 真的放行一次。"""

    approval = write_pattern_approval(
        tmp_root / "config" / f"{name}-approval.json",
        tool_id="exec.pwsh",
        subject="local-user",
        command_pattern="^python -m pytest( .*)?$",
    )
    return write_dsh_config(
        tmp_root / "config" / f"{name}.yaml",
        project_root=dsh_project,
        rules=REPO_ROOT / "policies",
        principal={"subject": "local-user", "roles": ["owner"]},
        approval_file=str(approval),
    )


def pwsh_post(
    project_root: Path,
    *,
    exit_code: object = None,
    tool_use_id: str = "call-pwsh",
    **extra: object,
) -> dict[str, object]:
    """按插件的转发形状构造 PostToolUse 载荷。

    退出事实来自 dsh 规范化工具结果的 result.value
    （{kind, exitCode, signal, timedOut, aborted, timeoutMs, stdout, stderr}）。
    这里手工拼形状而不是加 fixture 文件：这些字段是插件转发的运行期事实，
    不是 dsh 原始载荷里的字段（原始载荷里没有它们）。
    """

    fields: dict[str, object] = {
        "hook_event_name": "PostToolUse",
        "tool_name": "pwsh",
        "tool_input": {"command": "python -m pytest tests/unit -q", "description": "run tests"},
        "tool_use_id": tool_use_id,
        "tool_response": "3 passed in 0.42s",
        "tool_result_kind": "foreground",
        "tool_timed_out": False,
        "tool_aborted": False,
    }
    if exit_code is not None:
        fields["tool_exit_code"] = exit_code
    fields.update(extra)
    return dsh_event("post-tool-use-edit.json", cwd=str(project_root), **fields)


def post_evidence_records(audit: Path) -> list[dict]:
    return [
        item
        for item in records(audit)
        if item.get("stage") == "post_evidence" and "payload" in item
    ]


def test_delegated_pwsh_with_exit_zero_is_validated_through_the_real_bridge(tmp_root, dsh_project):
    """N16 的核心判据：exit 0 → validated，且工具输出不被策略错误替换。

    "输出不被替换"在本层是机器可判的：Hook 退出码 0 且 stderr 为空，
    插件就会把 dsh 的原始结果原样交给模型（返回 next()）。
    """

    config_path = pwsh_config(tmp_root, dsh_project, name="pwsh-owner")
    audit = dsh_project.parent / "audit.jsonl"

    pre = run_hook(
        payload("pre-tool-use-pwsh-execute.json", dsh_project),
        config_path=config_path,
        audit_path=audit,
    )
    assert pre.exit_code == EXIT_ALLOW, pre.stderr

    post = run_hook(
        pwsh_post(dsh_project, exit_code=0),
        config_path=config_path,
        audit_path=audit,
    )

    assert post.exit_code == EXIT_ALLOW, post.stderr
    assert post.reason_code == "post_validated"
    assert post.stderr == ""

    evidence = post_evidence_records(audit)[-1]
    assert evidence["payload"]["process"]["exit_code"] == 0, evidence
    final = [item for item in records(audit) if item.get("stage") == "final_decision"][-1]
    assert final["payload"]["outcome"] == "delivered"


def test_delegated_pwsh_with_a_non_zero_exit_reports_the_real_code(tmp_root, dsh_project):
    """exit 非 0 → repair_required，且理由里带**真实退出码**（不是"不可判定"）。"""

    config_path = pwsh_config(tmp_root, dsh_project, name="pwsh-owner")
    audit = dsh_project.parent / "audit.jsonl"

    pre = run_hook(
        payload("pre-tool-use-pwsh-execute.json", dsh_project),
        config_path=config_path,
        audit_path=audit,
    )
    assert pre.exit_code == EXIT_ALLOW, pre.stderr

    post = run_hook(
        pwsh_post(dsh_project, exit_code=1),
        config_path=config_path,
        audit_path=audit,
    )

    assert post.exit_code == EXIT_BLOCK
    assert post.reason_code == "post_repair_required"
    assert "退出码 1" in post.stderr, post.stderr
    evidence = post_evidence_records(audit)[-1]
    assert evidence["payload"]["process"]["exit_code"] == 1, evidence


def test_delegated_pwsh_without_exit_facts_still_needs_repair(tmp_root, dsh_project):
    """失败关闭不得放松：拿不到退出码时的结论必须与修前一致（repair_required）。"""

    config_path = pwsh_config(tmp_root, dsh_project, name="pwsh-owner")
    audit = dsh_project.parent / "audit.jsonl"

    pre = run_hook(
        payload("pre-tool-use-pwsh-execute.json", dsh_project),
        config_path=config_path,
        audit_path=audit,
    )
    assert pre.exit_code == EXIT_ALLOW, pre.stderr

    post = run_hook(pwsh_post(dsh_project), config_path=config_path, audit_path=audit)

    assert post.exit_code == EXIT_BLOCK
    assert post.reason_code == "post_repair_required"
    assert "没有退出码" in post.stderr, post.stderr


def test_a_malformed_exit_fact_is_refused_instead_of_silently_dropped(tmp_root, dsh_project):
    """形状不认的退出事实不得被静默忽略：显式拒绝并写明是哪个字段。

    bool 是 int 的子类（True == 1），负数与小数也不是 dsh 契约里的退出码；
    把它们当成"没有退出码"会让账本上多一条看起来合规的记录。
    """

    config_path = pwsh_config(tmp_root, dsh_project, name="pwsh-owner")
    audit = dsh_project.parent / "audit.jsonl"

    pre = run_hook(
        payload("pre-tool-use-pwsh-execute.json", dsh_project),
        config_path=config_path,
        audit_path=audit,
    )
    assert pre.exit_code == EXIT_ALLOW, pre.stderr

    for bad in (True, "0", -1, 1.5):
        post = run_hook(
            pwsh_post(dsh_project, exit_code=bad),
            config_path=config_path,
            audit_path=audit,
        )
        assert post.exit_code == EXIT_BLOCK, bad
        assert post.reason_code == "post_error", (bad, post.reason_code)
        assert "tool_exit_code" in post.stderr, (bad, post.stderr)
