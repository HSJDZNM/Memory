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

from adapters.dsh.adapter import AdapterConfig, load_config
from adapters.dsh.enforcement import EnforcementBridge, bridge_from_config
from adapters.dsh.hooks import EXIT_ALLOW, EXIT_BLOCK, DshPreExecuteHook, run_hook
from policy.loader import load_rule_set

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
    audit = dsh_project.parent / "audit.jsonl"
    write_source(dsh_project, "src/shop/order_controller.py", "from service import OrderService\n")

    post = run_hook(
        payload("post-tool-use-edit.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=audit,
    )

    assert post.exit_code == EXIT_ALLOW
    assert post.reason_code == "post_not_required"
    notes = [item for item in records(audit) if item.get("payload", {}).get("stage_note")]
    assert notes and notes[0]["payload"]["stage_note"] == "post_without_pre"


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
