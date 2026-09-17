"""enforcement CLI 集成测试：真实子进程、真实文件、真实退出码。

Phase 4 的退出码约定与其它阶段一致：
    0 = 允许 / 验证通过；1 = 阻断 / 需要修复；2 = 配置或执行错误。
这里验证"命令真的按这条约定退出"，并顺带证明一条 trace 可以被重放出来。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from enforcement_support import (
    ENFORCEMENT_APPROVED,
    ENFORCEMENT_REGISTRY,
    EnforcementPaths,
    enforcement_paths,
    write_registry,
)

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]


def cli_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_cli(*arguments: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "enforcement.cli", *arguments],
        cwd=REPO_ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=cli_env(),
        check=False,
    )


def paths_args(paths: EnforcementPaths) -> list[str]:
    return [
        "--registry",
        str(paths.registry),
        "--approved",
        str(paths.approved),
        "--audit",
        str(paths.audit),
        "--ledger",
        str(paths.ledger),
    ]


def write_request(paths: EnforcementPaths, name: str, **overrides) -> Path:
    document = {
        "action_id": "cli-act-1",
        "request_id": "cli-act-1",
        "trace_id": "cli-trace-1",
        "agent": "dsh",
        "agent_version": "0.1.5-rc.1",
        "tool_id": "fs.edit",
        "subject": "local-user",
        "roles": ["developer"],
        "params": {
            "file_path": "src/shop/order_controller.py",
            "old_string": "from service import OrderService",
            "new_string": "from service import OrderService\nfrom util import clock",
            "replace_all": False,
        },
        "workspace": str(paths.workspace),
    }
    document.update(overrides)
    target = paths.root / name
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def seed(paths: EnforcementPaths) -> None:
    paths.file(
        "src/shop/order_controller.py",
        "from service import OrderService\n\n\ndef create_order(payload):\n    return OrderService().create(payload)\n",
    )


# --------------------------------------------------------------------------- registry


def test_registry_verify_passes_for_the_repository_asset():
    completed = run_cli("registry", "--verify")

    assert completed.returncode == 0, completed.stderr
    assert "exec.pwsh" in completed.stdout


def test_tampered_registry_is_reported(tmp_root):
    paths = EnforcementPaths(tmp_root)
    document = json.loads(
        subprocess.run(
            [sys.executable, "-c", "import sys,yaml,json;print(json.dumps(yaml.safe_load(open(sys.argv[1],encoding='utf-8'))))", str(paths.registry)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout
    )
    document["tools"][0]["parameters"][1]["max_chars"] = 1
    paths.registry.write_text(
        json.dumps(document), encoding="utf-8"
    )

    completed = run_cli("registry", "--verify", *paths_args(paths))
    assert completed.returncode == 2
    assert "已审核值不一致" in completed.stdout

    self_check = run_cli("self-check", *paths_args(paths))
    assert self_check.returncode == 2
    assert "problem:" in self_check.stdout

    # verify 默认只校验审计链；显式加 --check-registry 才会把注册表审核状态纳入门禁
    audit_only = run_cli("verify", "--audit", str(paths.audit))
    assert audit_only.returncode == 0
    with_registry = run_cli("verify", "--check-registry", *paths_args(paths))
    assert with_registry.returncode == 2
    assert "未审核的工具" in with_registry.stdout


# --------------------------------------------------------------------------- precheck


def test_precheck_allows_and_blocks_with_the_documented_exit_codes(enforcement_paths):
    seed(enforcement_paths)
    allowed = write_request(enforcement_paths, "allow.json")

    completed = run_cli("precheck", "--request", str(allowed), "--workspace", str(enforcement_paths.workspace), *paths_args(enforcement_paths))
    assert completed.returncode == 0, completed.stderr
    assert "pre-decision: allow" in completed.stdout
    # 只做决策，不执行：文件必须没变
    assert "from util import clock" not in enforcement_paths.read("src/shop/order_controller.py")

    blocked = write_request(
        enforcement_paths,
        "block.json",
        action_id="cli-act-2",
        tool_id="exec.process",
        roles=["developer"],
        params={"argv": ["python", "-c", "print(1)"], "description": "demo"},
    )
    completed = run_cli(
        "precheck", "--request", str(blocked), "--workspace", str(enforcement_paths.workspace), *paths_args(enforcement_paths)
    )
    assert completed.returncode == 1
    assert "permission_denied" in completed.stdout


def test_precheck_is_a_dry_run_and_does_not_block_the_real_execution(enforcement_paths):
    """按直觉操作：先 precheck 看结论，再 execute 执行——两条命令必须都能跑通。"""

    seed(enforcement_paths)
    request = write_request(enforcement_paths, "dry-run.json")
    arguments = [
        "--request",
        str(request),
        "--workspace",
        str(enforcement_paths.workspace),
        *paths_args(enforcement_paths),
    ]

    checked = run_cli("precheck", *arguments)
    assert checked.returncode == 0, checked.stderr
    payload = json.loads(run_cli("precheck", "--json", *arguments).stdout)
    assert payload["pre"]["dry_run"] is True
    assert payload["grant"] is None
    assert not enforcement_paths.ledger.exists() or "claim" not in enforcement_paths.ledger.read_text(encoding="utf-8")

    executed = run_cli("execute", *arguments)
    assert executed.returncode == 0, executed.stderr + executed.stdout
    assert "from util import clock" in enforcement_paths.read("src/shop/order_controller.py")


def test_unknown_request_fields_and_tools_are_config_errors(enforcement_paths):
    seed(enforcement_paths)
    unknown_field = write_request(enforcement_paths, "unknown-field.json", approved=True)
    completed = run_cli("precheck", "--request", str(unknown_field), *paths_args(enforcement_paths))
    assert completed.returncode == 2
    assert "未知字段" in completed.stderr

    unknown_tool = write_request(enforcement_paths, "unknown-tool.json", tool_id="fs.nope")
    completed = run_cli("precheck", "--request", str(unknown_tool), *paths_args(enforcement_paths))
    assert completed.returncode == 2
    assert "不在注册表里" in completed.stderr


# --------------------------------------------------------------------------- execute + trace


def test_execute_changes_the_file_and_leaves_a_replayable_trace(enforcement_paths):
    seed(enforcement_paths)
    request = write_request(enforcement_paths, "execute.json")

    completed = run_cli(
        "execute", "--request", str(request), "--workspace", str(enforcement_paths.workspace), *paths_args(enforcement_paths)
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert "final: delivered" in completed.stdout
    assert "from util import clock" in enforcement_paths.read("src/shop/order_controller.py")

    trace = run_cli("trace", "--action-id", "cli-act-1", "--audit", str(enforcement_paths.audit))
    assert trace.returncode == 0, trace.stderr
    for stage in ("pre_decision", "execution", "post_evidence", "final_decision"):
        assert stage in trace.stdout

    verify = run_cli("verify", "--audit", str(enforcement_paths.audit))
    assert verify.returncode == 0, verify.stderr
    assert "审计链校验通过" in verify.stdout


def test_replaying_an_executed_action_exits_1_and_never_touches_the_file(enforcement_paths):
    seed(enforcement_paths)
    request = write_request(enforcement_paths, "replay.json")

    first = run_cli(
        "execute", "--request", str(request), "--workspace", str(enforcement_paths.workspace), *paths_args(enforcement_paths)
    )
    assert first.returncode == 0
    content = enforcement_paths.read("src/shop/order_controller.py")

    second = run_cli(
        "execute", "--request", str(request), "--workspace", str(enforcement_paths.workspace), *paths_args(enforcement_paths)
    )
    assert second.returncode == 1
    assert "action_replay" in second.stdout
    assert enforcement_paths.read("src/shop/order_controller.py") == content


def test_missing_trace_reports_an_error(enforcement_paths):
    seed(enforcement_paths)
    completed = run_cli("trace", "--action-id", "never-happened", "--audit", str(enforcement_paths.audit))
    assert completed.returncode == 2
    assert "没有本层的链式记录" in completed.stdout or "没有匹配" in completed.stdout


def test_high_risk_tool_needs_an_approval_file_and_then_executes(enforcement_paths):
    request = write_request(
        enforcement_paths,
        "process.json",
        action_id="cli-act-proc",
        tool_id="exec.process",
        roles=["owner"],
        params={"argv": ["python", "-c", "print('cli-ok')"], "description": "demo"},
    )
    without = run_cli(
        "execute", "--request", str(request), "--workspace", str(enforcement_paths.workspace), *paths_args(enforcement_paths)
    )
    assert without.returncode == 1
    assert "approval_required" in without.stdout

    approval = enforcement_paths.root / "approval.json"
    approve = run_cli(
        "approve",
        "--request",
        str(request),
        "--out",
        str(approval),
        "--granted-by",
        "alice",
        "--roles",
        "reviewer",
        *paths_args(enforcement_paths),
    )
    assert approve.returncode == 0, approve.stderr
    payload = json.loads(approval.read_text(encoding="utf-8"))
    assert payload["subject"] == "local-user"

    executed = run_cli(
        "execute",
        "--request",
        str(request),
        "--approval",
        str(approval),
        "--workspace",
        str(enforcement_paths.workspace),
        *paths_args(enforcement_paths),
    )
    assert executed.returncode == 0, executed.stderr + executed.stdout
    assert "final: delivered" in executed.stdout

    replay = run_cli(
        "execute",
        "--request",
        str(request),
        "--approval",
        str(approval),
        "--workspace",
        str(enforcement_paths.workspace),
        *paths_args(enforcement_paths),
    )
    assert replay.returncode == 1


def test_documented_example_requests_are_runnable(enforcement_paths):
    """README 里写的命令必须真的能跑：先用闭环脚本准备演示工作区，再执行示例请求（复核 D6）。"""

    loop = subprocess.run(
        [sys.executable, "tools/enforcement_loop.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=cli_env(),
        check=False,
    )
    assert loop.returncode == 0, loop.stdout + loop.stderr

    example = REPO_ROOT / "examples" / "enforcement" / "edit-allow-request.json"
    document = json.loads(example.read_text(encoding="utf-8"))
    # 示例用的是仓库默认台账（.tmp/artifacts/enforcement-ledger.jsonl），因此 action_id 必须每次唯一，
    # 否则第二次运行会正确地判成重放。示例表达的是同一条请求形状。
    unique = "example:call-edit-" + uuid.uuid4().hex[:8]
    document["action_id"] = unique
    document["request_id"] = unique
    temporary = enforcement_paths.root / "example.json"
    temporary.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    completed = run_cli("execute", "--request", str(temporary), "--json")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["chain"]["final"]["outcome"] == "delivered"
    assert payload["execution"]["status"] == "executed"


def test_approve_and_execute_agree_when_the_request_has_a_policy_context(enforcement_paths):
    """带 policy_context 的请求：审批与执行必须绑定同一个 action_hash（复核 D7）。"""

    seed(enforcement_paths)
    request = write_request(
        enforcement_paths,
        "with-context.json",
        action_id="ctx-1",
        request_id="ctx-1",
        policy_context={
            "request_id": "ctx-1",
            "file": "src/shop/order_controller.py",
            "layer": "controller",
            "language": "python",
            "operation": "edit",
            "dependencies": ["repository"],
        },
    )
    arguments = [
        "--request",
        str(request),
        "--workspace",
        str(enforcement_paths.workspace),
        *paths_args(enforcement_paths),
    ]

    approval = enforcement_paths.root / "approval-ctx.json"
    approved = run_cli(
        "approve",
        "--out",
        str(approval),
        "--granted-by",
        "alice",
        "--roles",
        "reviewer",
        *arguments,
    )
    assert approved.returncode == 0, approved.stderr

    # 规则引擎会因 ARCH-001 命中而阻断（依赖里带 repository），这正好证明规则真的跑了
    executed = run_cli("execute", *arguments, "--approval", str(approval))
    assert executed.returncode == 1
    assert "policy_block" in executed.stdout
    assert "ARCH-001@1" in executed.stdout


def test_self_check_passes_for_the_repository_assets():
    completed = run_cli("self-check")

    assert completed.returncode == 0, completed.stderr
    assert "self-check ok" in completed.stdout


def test_json_output_is_machine_readable(enforcement_paths):
    seed(enforcement_paths)
    request = write_request(enforcement_paths, "json.json")

    completed = run_cli(
        "execute", "--json", "--request", str(request), "--workspace", str(enforcement_paths.workspace), *paths_args(enforcement_paths)
    )
    payload = json.loads(completed.stdout)

    assert payload["chain"]["final"]["outcome"] == "delivered"
    assert payload["pre"]["grant"]["action_hash"] == payload["action"]["action_hash"]
    assert payload["execution"]["status"] == "executed"
    assert payload["evidence"]["files"][0]["changed"] is True
    # --json 面向运维：保留非敏感参数原文（secret 参数除外），方便人工复核这次动作。
    new_string = next(item for item in payload["action"]["params"] if item["name"] == "new_string")
    assert new_string["value"] == "from service import OrderService\nfrom util import clock"
    # 审计链只存摘要：运维视图与审计证据的可见性口径不同，这一点必须成立。
    audit_text = enforcement_paths.audit.read_text(encoding="utf-8")
    assert "from util import clock" not in audit_text
    assert "from service import OrderService" not in audit_text
