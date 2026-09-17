"""Phase 4 测试支撑：测试注册表、受控路径、Action Request 与审批构造。

放在独立模块而不是 conftest.py：Phase 4 的测试文件显式 import 这里的 fixture，
共享同一份"按生产代码路径生成注册表 + 已审核清单"的实现。
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import pytest
import yaml

from conftest import REPO_ROOT

__all__ = [
    "ENFORCEMENT_APPROVED",
    "ENFORCEMENT_REGISTRY",
    "SHELL_COMMAND",
    "TEST_REGISTRY_TOOLS",
    "EnforcementPaths",
    "approval_for",
    "enforcement_paths",
    "make_action",
    "registry_document",
    "write_registry",
]

ENFORCEMENT_REGISTRY = REPO_ROOT / "registry" / "tool-registry.yaml"
ENFORCEMENT_APPROVED = REPO_ROOT / "registry" / "tool-registry.approved.json"

# 测试用注册表：结构与仓库真实注册表一致，但进程 / 命令工具用当前解释器，
# 因此在 Windows 与 Linux 上都能真的执行，而不是靠 skip 掩盖。
TEST_REGISTRY_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "id": "fs.edit",
        "title": "test edit",
        "agent": "dsh",
        "tool_name": "edit",
        "schema_version": "1.0",
        "risk": "reversible_write",
        "effect": "file_write",
        "driver": "file_edit",
        "required_permissions": ["repo.write"],
        "rollback": "file_snapshot",
        "post_checks": ["content_matches", "file_changed", "file_syntax", "diff_recorded"],
        "rate_limit": {
            "max_calls": 3,
            "window_seconds": 60,
            "max_failures": 2,
            "breaker_seconds": 60,
        },
        "parameters": [
            {"name": "file_path", "type": "path", "required": True, "path_scope": "workspace"},
            {"name": "old_string", "type": "string", "required": True, "max_chars": 4000},
            {"name": "new_string", "type": "string", "required": True, "max_chars": 4000},
            {"name": "replace_all", "type": "boolean"},
        ],
    },
    {
        "id": "fs.write",
        "title": "test write",
        "agent": "dsh",
        "tool_name": "write",
        "schema_version": "1.0",
        "risk": "reversible_write",
        "effect": "file_write",
        "driver": "file_write",
        "required_permissions": ["repo.write"],
        "rollback": "file_snapshot",
        "post_checks": ["content_matches", "target_exists", "file_syntax", "diff_recorded"],
        "parameters": [
            {"name": "file_path", "type": "path", "required": True, "path_scope": "workspace"},
            {"name": "content", "type": "string", "required": True, "max_chars": 20000},
        ],
    },
    {
        "id": "fs.read",
        "title": "test read",
        "agent": "dsh",
        "tool_name": "read",
        "schema_version": "1.0",
        "risk": "read_only",
        "effect": "none",
        "driver": "none",
        "required_permissions": ["repo.read"],
        "audit_failure": "degrade",
        "parameters": [
            {"name": "file_path", "type": "path", "required": True, "path_scope": "workspace"}
        ],
    },
    {
        "id": "exec.process",
        "title": "test argv process",
        "agent": "dsh",
        "tool_name": "run_code",
        "schema_version": "1.0",
        "risk": "privileged_execution",
        "effect": "process",
        "driver": "process_argv",
        "required_permissions": ["shell.exec"],
        "approval": "required",
        "post_checks": ["exit_code_zero"],
        "timeout_ms": 20000,
        "rate_limit": {
            "max_calls": 2,
            "window_seconds": 60,
            "max_failures": 2,
            "breaker_seconds": 60,
        },
        "parameters": [
            {
                "name": "argv",
                "type": "string_list",
                "required": True,
                "max_items": 8,
                "max_item_chars": 400,
            },
            {"name": "description", "type": "string", "required": True, "max_chars": 200},
            {
                "name": "sandbox_permissions",
                "type": "string",
                "enum": ["workspace-write", "danger-full-access"],
                "escalating_values": ["danger-full-access"],
                "requires_permission": "sandbox.escalate",
            },
        ],
    },
    {
        "id": "exec.shell",
        "title": "test shell command",
        "agent": "dsh",
        "tool_name": "pwsh",
        "schema_version": "1.0",
        "risk": "privileged_execution",
        "effect": "process",
        "driver": "shell_command",
        "shell": ["@PYTHON@", "-c"],
        "command_param": "command",
        "required_permissions": ["shell.exec"],
        "approval": "required",
        "post_checks": ["exit_code_zero"],
        "timeout_ms": 20000,
        # 故意带上 ( .*)? 尾巴：组合命令必须被结构性检查拦住，而不是靠正则的运气
        "allowed_commands": ["^print[(]'ok'[)]$", "^echo( .*)?$"],
        # 与生产注册表同形：白名单只看"命令长什么样"，被禁片段决定"它会做什么"
        "forbidden_command_fragments": ["../", "..\\", "--output"],
        "parameters": [
            {"name": "command", "type": "string", "required": True, "max_chars": 400},
            {"name": "description", "type": "string", "required": True, "max_chars": 200},
        ],
    },
    {
        "id": "exec.delegated",
        "title": "test delegated tool",
        "agent": "dsh",
        "tool_name": "bash",
        "schema_version": "1.0",
        "risk": "privileged_execution",
        "effect": "process",
        "driver": "none",
        "required_permissions": ["shell.exec"],
        "approval": "required",
        "post_checks": [],
        "parameters": [
            {"name": "code", "type": "string", "required": True, "max_chars": 2000},
            {"name": "description", "type": "string", "required": True, "max_chars": 200},
        ],
    },
)

# 命令白名单里允许的唯一命令（用字符类避免转义地狱）：print('ok')
SHELL_COMMAND = "print('ok')"


def _with_python(tool: dict[str, Any]) -> dict[str, Any]:
    """把 shell 前缀里的 @PYTHON@ 换成当前解释器（跨平台可执行）。"""

    payload = json.loads(json.dumps(tool))
    shell = payload.get("shell")
    if isinstance(shell, list):
        payload["shell"] = [
            sys.executable if item == "@PYTHON@" else item for item in shell
        ]
    return payload


def registry_document(
    tools: tuple[dict[str, Any], ...] | None = None, **overrides: Any
) -> dict[str, Any]:
    """构造一份测试注册表文档（结构与仓库真实注册表一致）。"""

    document: dict[str, Any] = {
        "registry_schema_version": "1.0",
        "version": 1,
        "defaults": {"timeout_ms": 5000, "grant_ttl_seconds": 60, "max_grant_ttl_seconds": 300},
        "permissions": {
            "repo.read": "读取",
            "repo.write": "写入",
            "repo.approve": "审批",
            "shell.exec": "执行",
            "sandbox.escalate": "提权",
        },
        "roles": {
            "developer": ["repo.read", "repo.write"],
            "reviewer": ["repo.read", "repo.write", "repo.approve"],
            "owner": ["repo.read", "repo.write", "repo.approve", "shell.exec", "sandbox.escalate"],
        },
        "approvals": {"require_role": "reviewer"},
        "tools": [_with_python(item) for item in (tools or TEST_REGISTRY_TOOLS)],
    }
    document.update(overrides)
    return document


def write_registry(
    root: Path,
    *,
    document: dict[str, Any] | None = None,
    tools: tuple[dict[str, Any], ...] | None = None,
    approve: bool = True,
    reviewer: str = "test-reviewer",
) -> tuple[Path, Path]:
    """写一份测试注册表 + 已审核清单，返回（注册表, 已审核清单）。

    已审核清单由 registry 模块自己生成，"审核"这件事在测试里走的也是生产代码路径。
    """

    from enforcement.registry import (
        approve_registry,
        registry_document_from_mapping,
        write_approved,
    )

    registry_path = root / "registry" / "tool-registry.yaml"
    approved_path = root / "registry" / "tool-registry.approved.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    payload = registry_document(tools=tools) if document is None else document
    registry_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8", newline=""
    )
    if approve:
        registry = registry_document_from_mapping(copy.deepcopy(payload))
        write_approved(approve_registry(registry, reviewer=reviewer), approved_path)
    return registry_path, approved_path


class EnforcementPaths:
    """一组受控路径：注册表、已审核清单、审计、台账、工作区。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.workspace = root / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.registry, self.approved = write_registry(root)
        self.audit = root / "audit.jsonl"
        self.ledger = root / "ledger.jsonl"
        self.repo_root = REPO_ROOT

    def load(self) -> Any:
        from enforcement.registry import load_registry

        return load_registry(self.registry, approved_path=self.approved)

    def registry_object(self) -> Any:
        return self.load().registry

    def file(self, relative: str, content: str) -> Path:
        target = self.workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="")
        return target

    def read(self, relative: str) -> str:
        return (self.workspace / relative).read_text(encoding="utf-8")

    def services(self) -> Any:
        """按生产代码路径装配（注册表 / 审计 / 台账 / 驱动 / 受控执行器）。"""

        from enforcement.audit import FileAuditSink
        from enforcement.drivers import drivers_for
        from enforcement.executor import ControlledExecutor
        from enforcement.ledger import EnforcementLedger

        registry = self.registry_object()
        sink = FileAuditSink(self.audit, workspace=self.workspace)
        ledger = EnforcementLedger(self.ledger)
        executor = ControlledExecutor(
            ledger=ledger,
            drivers=drivers_for(registry.tools),
            sink=sink,
            max_grant_ttl_seconds=registry.max_grant_ttl_seconds,
        )
        return registry, sink, ledger, executor


@pytest.fixture()
def enforcement_paths(tmp_root: Path) -> EnforcementPaths:
    return EnforcementPaths(tmp_root)


def make_action(
    registry: Any,
    paths: EnforcementPaths,
    tool_id: str,
    params: dict[str, Any],
    *,
    roles: Sequence[str] = ("developer",),
    subject: str | None = "local-user",
    action_id: str = "act-1",
    request_id: str = "req-1",
    trace_id: str = "trace-1",
    context: Any = None,
    workspace: Path | None = None,
) -> Any:
    """按生产代码路径构造 Action Request。"""

    from enforcement.action import build_action_request

    spec = registry.tool(tool_id)
    assert spec is not None
    return build_action_request(
        spec,
        params,
        action_id=action_id,
        request_id=request_id,
        agent="dsh",
        agent_version="0.1.5-rc.1",
        trace_id=trace_id,
        subject=subject,
        roles=roles,
        permissions=registry.permissions_for(roles),
        context=context,
        workspace=workspace or paths.workspace,
        ttl_seconds=registry.grant_ttl_seconds,
    )


def approval_for(
    request: Any,
    *,
    subject: str | None = None,
    roles: Sequence[str] = ("reviewer",),
    ttl: int = 300,
    granted_by: str = "alice",
    approval_id: str = "approval-test-1",
    action_hash: str | None = None,
) -> Any:
    """为某个 Action Request 生成人工审批（走生产侧模型校验）。"""

    from datetime import timedelta

    from enforcement.approvals import ApprovalRecord
    from enforcement.models import utc_now

    now = utc_now()
    return ApprovalRecord(
        approval_id=approval_id,
        action_hash=action_hash or request.action_hash,
        action_id=request.action_id,
        tool_id=request.tool_id,
        subject=subject or request.subject or "local-user",
        granted_by=granted_by,
        granted_by_roles=tuple(roles),
        granted_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(seconds=ttl),
    )
