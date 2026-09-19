"""受控执行协议契约测试：模型不变量、版本拒绝与 dsh 工具表一致性。

Phase 4 的协议必须和 Phase 1 的决策协议一样"看不懂就拒绝"：
未知 schema 版本、未知决策值、自相矛盾的证据都不得被消费。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from enforcement.models import (
    ActionRequest,
    ApprovalMode,
    AuditRecord,
    AuditStage,
    Decision,
    DriverKind,
    EnforcementError,
    ExecutionRecord,
    ExecutionStatus,
    FileEffect,
    FinalDecision,
    FinalOutcome,
    PreDecision,
    ReasonCode,
    RiskLevel,
    parse_pre_decision,
    utc_now,
)
from enforcement.registry import load_registry
from enforcement_support import (
    ENFORCEMENT_APPROVED,
    ENFORCEMENT_REGISTRY,
    enforcement_paths,
    make_action,
)

pytestmark = pytest.mark.contract


# --------------------------------------------------------------------------- 协议


def test_pre_decision_round_trips(enforcement_paths):
    registry = enforcement_paths.registry_object()
    request = make_action(registry, enforcement_paths, "fs.edit", {
        "file_path": "src/shop/order_controller.py",
        "old_string": "a",
        "new_string": "b",
    })

    from enforcement.audit import FileAuditSink
    from enforcement.ledger import EnforcementLedger
    from enforcement.precheck import pre_execute

    outcome = pre_execute(
        request,
        registry=registry,
        ledger=EnforcementLedger(enforcement_paths.ledger),
        sink=FileAuditSink(enforcement_paths.audit, workspace=enforcement_paths.workspace),
    )
    payload = outcome.decision.to_decision_dict()
    parsed = parse_pre_decision(payload)

    assert parsed.decision is outcome.decision.decision
    assert parsed.action_hash == request.action_hash
    assert parsed.grant is not None and parsed.grant.action_hash == request.action_hash
    assert parsed.checks == outcome.decision.checks


def test_unknown_protocol_version_is_refused(enforcement_paths):
    registry = enforcement_paths.registry_object()
    request = make_action(registry, enforcement_paths, "fs.edit", {"file_path": "a.py", "old_string": "a", "new_string": "b"})
    from enforcement.audit import FileAuditSink
    from enforcement.ledger import EnforcementLedger
    from enforcement.precheck import pre_execute

    payload = pre_execute(
        request,
        registry=registry,
        ledger=EnforcementLedger(enforcement_paths.ledger),
        sink=FileAuditSink(enforcement_paths.audit, workspace=enforcement_paths.workspace),
    ).decision.to_decision_dict()
    payload["schema_version"] = "2.0"

    with pytest.raises(EnforcementError) as error:
        parse_pre_decision(payload)
    assert "未知受控执行协议版本" in str(error.value)


def test_allow_without_a_grant_is_a_protocol_error(enforcement_paths):
    registry = enforcement_paths.registry_object()
    request = make_action(registry, enforcement_paths, "fs.edit", {"file_path": "a.py", "old_string": "a", "new_string": "b"})

    with pytest.raises(ValidationError) as error:
        PreDecision(
            decision=Decision.ALLOW,
            reason_code=ReasonCode.ALLOW,
            action_id=request.action_id,
            request_id=request.request_id,
            action_hash=request.action_hash,
            tool_id=request.tool_id,
            tool_name=request.tool_name,
            risk=request.risk,
            evaluated_at=utc_now(),
        )
    assert "必须携带" in str(error.value)


def test_block_with_a_grant_is_a_protocol_error(enforcement_paths):
    from enforcement.precheck import issue_grant

    registry = enforcement_paths.registry_object()
    request = make_action(registry, enforcement_paths, "fs.edit", {"file_path": "a.py", "old_string": "a", "new_string": "b"})
    grant = issue_grant(request, registry.tool("fs.edit"), ttl_seconds=10, now=utc_now())

    with pytest.raises(ValidationError):
        PreDecision(
            decision=Decision.BLOCK,
            reason_code=ReasonCode.POLICY_BLOCK,
            action_id=request.action_id,
            request_id=request.request_id,
            action_hash=request.action_hash,
            tool_id=request.tool_id,
            tool_name=request.tool_name,
            risk=request.risk,
            grant=grant,
            evaluated_at=utc_now(),
        )


def test_execution_record_rejects_contradictory_states(enforcement_paths):
    registry = enforcement_paths.registry_object()
    request = make_action(registry, enforcement_paths, "fs.edit", {"file_path": "a.py", "old_string": "a", "new_string": "b"})

    with pytest.raises(ValidationError):
        ExecutionRecord(
            action_id=request.action_id,
            request_id=request.request_id,
            action_hash=request.action_hash,
            tool_id=request.tool_id,
            risk=RiskLevel.REVERSIBLE_WRITE,
            status=ExecutionStatus.EXECUTED,
            reason_code=ReasonCode.POLICY_BLOCK,  # 执行了却记成被阻断
            duration_ms=1,
            started_at=utc_now(),
            finished_at=utc_now(),
        )
    with pytest.raises(ValidationError):
        ExecutionRecord(
            action_id=request.action_id,
            request_id=request.request_id,
            action_hash=request.action_hash,
            tool_id=request.tool_id,
            risk=RiskLevel.REVERSIBLE_WRITE,
            status=ExecutionStatus.REFUSED,
            reason_code=ReasonCode.ALLOW,
            exit_code=0,  # 没执行却有退出码
            duration_ms=1,
            started_at=utc_now(),
            finished_at=utc_now(),
        )


def test_file_effect_rejects_self_contradicting_evidence():
    with pytest.raises(ValidationError):
        FileEffect(
            path="a.py", existed_before=True, exists_after=True,
            sha256_before="sha256:a", sha256_after="sha256:b", changed=False,
        )
    with pytest.raises(ValidationError):
        FileEffect(
            path="a.py", existed_before=True, exists_after=True,
            sha256_before="sha256:a", sha256_after="sha256:a", changed=True,
        )


def test_final_decision_refuses_impossible_transitions(enforcement_paths):
    registry = enforcement_paths.registry_object()
    request = make_action(registry, enforcement_paths, "fs.edit", {"file_path": "a.py", "old_string": "a", "new_string": "b"})

    with pytest.raises(ValidationError):
        FinalDecision(
            outcome=FinalOutcome.DELIVERED,
            reason_code=ReasonCode.ALLOW,
            action_id=request.action_id,
            request_id=request.request_id,
            action_hash=request.action_hash,
            tool_id=request.tool_id,
            risk=request.risk,
            pre_decision=Decision.BLOCK,
            decided_at=utc_now(),
        )
    with pytest.raises(ValidationError):
        FinalDecision(
            outcome=FinalOutcome.BLOCKED,
            reason_code=ReasonCode.ALLOW,
            action_id=request.action_id,
            request_id=request.request_id,
            action_hash=request.action_hash,
            tool_id=request.tool_id,
            risk=request.risk,
            pre_decision=Decision.ALLOW,
            execution_status=ExecutionStatus.EXECUTED,
            decided_at=utc_now(),
        )


def test_audit_record_digest_is_checked():
    record = AuditRecord(sequence=1, stage=AuditStage.REQUEST, payload={"a": 1}, recorded_at=utc_now())
    payload = json.loads(record.model_dump_json())
    payload["payload"]["a"] = 2

    with pytest.raises(ValidationError):
        AuditRecord.model_validate(payload)


def test_action_hash_is_stable_across_processes(enforcement_paths, tmp_root):
    """哈希口径必须跨进程一致：否则"另一个进程发出的授权"永远对不上。"""

    registry = enforcement_paths.registry_object()
    request = make_action(registry, enforcement_paths, "fs.edit", {
        "file_path": "src/shop/order_controller.py",
        "old_string": "from service import OrderService",
        "new_string": "from service import OrderService\nfrom util import clock",
        "replace_all": False,
    })
    script = (
        "import json,sys;"
        "sys.path.insert(0, 'src');"
        "from enforcement.action import build_action_request;"
        "from enforcement.registry import load_registry;"
        f"loaded = load_registry(r'{enforcement_paths.registry}', approved_path=r'{enforcement_paths.approved}');"
        "spec = loaded.registry.tool('fs.edit');"
        "request = build_action_request(spec, json.loads(sys.argv[1]), action_id='act-1',"
        " request_id='req-1', agent='dsh', agent_version='0.1.5-rc.1', trace_id='trace-1',"
        " subject='local-user', roles=['developer'],"
        " permissions=loaded.registry.permissions_for(['developer']),"
        f" workspace=r'{enforcement_paths.workspace}', ttl_seconds=60);"
        "print(request.action_hash)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, json.dumps({
            "file_path": "src/shop/order_controller.py",
            "old_string": "from service import OrderService",
            "new_string": "from service import OrderService\nfrom util import clock",
            "replace_all": False,
        })],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == request.action_hash


# --------------------------------------------------------------------------- 与 dsh 工具表一致


def test_real_registry_declares_the_fragments_that_make_a_command_dangerous(enforcement_paths):
    """审计发现 M2：git diff --output=<任意路径> 能完整匹配命令白名单，却会把内容写到工作区外。

    白名单正则只能描述"命令长什么样"。这条用例把"白名单不是沙箱"钉成回归：
    命令类工具必须声明被禁片段，并且这些片段真的会让 pre-check 阻断。
    """

    from enforcement.action import build_action_request
    from enforcement.audit import FileAuditSink
    from enforcement.ledger import EnforcementLedger
    from enforcement.models import CheckStatus
    from enforcement.precheck import check_list

    registry = load_registry(ENFORCEMENT_REGISTRY, approved_path=ENFORCEMENT_APPROVED).registry
    spec = registry.tool("exec.pwsh")
    assert "../" in spec.forbidden_command_fragments
    assert "--output" in spec.forbidden_command_fragments

    request = build_action_request(
        spec,
        {"command": "git diff --output=C:/Windows/Temp/leak.txt", "description": "probe"},
        action_id="fragment-probe-1",
        request_id="fragment-probe-1",
        agent="dsh",
        subject="local-user",
        roles=("owner",),
        permissions=registry.permissions_for(("owner",)),
        workspace=enforcement_paths.workspace,
        ttl_seconds=60,
    )
    checks, _spec, _warnings = check_list(
        request,
        registry=registry,
        ledger=EnforcementLedger(enforcement_paths.ledger),
        sink=FileAuditSink(enforcement_paths.audit, workspace=enforcement_paths.workspace),
    )
    by_name = {item.check: item for item in checks}
    # 白名单确实放行了它——这正是问题所在
    assert by_name["command_allowlist"].status is CheckStatus.PASSED
    assert by_name["command_composition"].status is CheckStatus.PASSED
    # 片段检查才是拦住它的那一道
    assert by_name["command_fragments"].status is CheckStatus.FAILED


def test_registry_tools_exist_in_the_dsh_tool_table():
    """注册表与 Adapter 工具表不能漂移：两边都认识同一个工具才可能治理它。

    注册表从 Phase 8 起**按 Agent 分段**（编排层有自己的 `orchestrator` 工具），
    因此这条契约只比对 `agent == "dsh"` 的那一段；编排层那一段由
    `test_orchestrator_tools_match_the_orchestration_layer` 单独比对。
    """

    from adapters.dsh.adapter import TOOL_TABLE

    registry = load_registry(ENFORCEMENT_REGISTRY, approved_path=ENFORCEMENT_APPROVED).registry
    for spec in [item for item in registry.tools if item.agent == "dsh"]:
        table_entry = TOOL_TABLE.get(spec.tool_name)
        assert table_entry is not None, f"{spec.tool_name} 不在 dsh TOOL_TABLE 里"
        expected = {"reversible_write": "write", "read_only": "read_only", "privileged_execution": "execute"}
        if spec.risk.value in expected:
            assert table_entry.kind.value == expected[spec.risk.value], spec.id


def test_every_governed_dsh_tool_is_registered():
    """Adapter 里所有写类与执行类工具都必须出现在注册表里，否则默认阻断。"""

    from adapters.dsh.adapter import TOOL_TABLE, ToolKind

    registry = load_registry(ENFORCEMENT_REGISTRY, approved_path=ENFORCEMENT_APPROVED).registry
    registered = {spec.tool_name for spec in registry.tools if spec.agent == "dsh"}
    # Phase 4 明确记在案的未登记工具：线协议参数尚未核实，因此默认阻断（见实施记录）。
    documented_unregistered = {"str_replace_editor", "workflow"}

    for name, spec in TOOL_TABLE.items():
        if spec.kind in (ToolKind.WRITE, ToolKind.EXECUTE):
            assert name in registered or name in documented_unregistered, name


def test_orchestrator_tools_match_the_orchestration_layer():
    """Phase 8：编排层声明的受控工具必须与代码里的工具 ID 逐项一致，且都已审核。

    改注册表必须重新审核（`python -m enforcement.cli registry --approve`）；
    代码里写死的工具 ID 与注册表漂移时，受控执行链会以 `tool_not_registered` 阻断——
    这条测试让漂移在门禁里就暴露，而不是等到运行时。
    """

    from orchestration.nodes import EDIT_TOOL, PROTECTED_EDIT_TOOL, WRITE_TOOL

    registry = load_registry(ENFORCEMENT_REGISTRY, approved_path=ENFORCEMENT_APPROVED).registry
    owned = [spec for spec in registry.tools if spec.agent == "orchestrator"]
    assert {spec.id for spec in owned} == {EDIT_TOOL, WRITE_TOOL, PROTECTED_EDIT_TOOL}
    for spec in owned:
        assert registry.is_approved(spec), f"{spec.id} 未被审核：受控执行链会拒绝执行"
        # 写入类工具必须声明路径范围，否则无法判断目标是否逃出受控工作区。
        paths = [item for item in spec.parameters if item.type.value == "path"]
        assert paths and all(item.path_scope == "workspace" for item in paths), spec.id
    # 改"判定依据本身"的动作必须走人工审批，且驱动可用（平台侧真的能执行）。
    protected = registry.tool(PROTECTED_EDIT_TOOL)
    assert protected is not None and protected.approval is ApprovalMode.REQUIRED
    assert protected.driver is DriverKind.FILE_EDIT


def test_read_only_tools_are_explicitly_not_governed_in_phase_4():
    from adapters.dsh.adapter import TOOL_TABLE, ToolKind

    registry = load_registry(ENFORCEMENT_REGISTRY, approved_path=ENFORCEMENT_APPROVED).registry
    read_only = [
        spec
        for spec in registry.tools
        if spec.risk is RiskLevel.READ_ONLY and spec.agent == "dsh"
    ]
    assert read_only, "只读动作必须被显式登记（允许降级，但仍记录）"
    for spec in read_only:
        assert TOOL_TABLE[spec.tool_name].kind in (ToolKind.READ_ONLY, ToolKind.NO_FILE)
