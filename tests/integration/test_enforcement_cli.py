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
from enforcement.approvals import APPROVAL_SCHEMA_VERSION
from enforcement_support import (
    EnforcementPaths,
    enforcement_paths,
)

# pytest 按测试模块命名空间里的**属性名**注册 fixture（没写 name= 时取的就是它），
# 所以这里必须用原名导入：它正是测试函数形参 `enforcement_paths` 要解析到的名字。
# `__all__` 声明这是一次刻意的再导出，不是未使用的导入（F401/F811 对它是误报）；
# 删掉这个导入 = 26 个用例在 setup 期报 `fixture 'enforcement_paths' not found`。
__all__ = ["enforcement_paths"]

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


def approval_records(path: Path) -> list[dict]:
    """读回 approve 写出的**审批文档**，返回其中的记录（两种形状都认）。

    审批协议 1.2 起一个文件可以放多条记录（`records`，按 `tool_id` 选择，每个工具各持
    一份放行）；只有一条时仍写成历史上的单记录文档——形状由 `records` 键唯一确定。
    这些用例断言的是"签出来的那条记录长什么样"，因此统一走这个读取口。
    """

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["schema_version"] == APPROVAL_SCHEMA_VERSION, document["schema_version"]
    return list(document["records"]) if "records" in document else [document]


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
        (
            "from service import OrderService\n"
            "\n"
            "\n"
            "def create_order(payload):\n"
            "    return OrderService().create(payload)\n"
        ),
    )


# --------------------------------------------------------------------------- registry


def test_registry_verify_passes_for_the_repository_asset():
    completed = run_cli("registry", "--verify")

    assert completed.returncode == 0, completed.stderr
    assert "exec.pwsh" in completed.stdout


def test_verify_refuses_a_missing_or_evidence_less_audit_artifact(tmp_root):
    """没有产物 ≠ 链完整：缺失的、或只有外来行的审计文件都不能读成"校验通过"。

    旧行为：文件不存在时 _scan() 返回空列表 → verify() 无 issue → exit 0 +
    "审计链校验通过"；只有 Phase 2 外来行时同样。而同一份文件上 verdict 子命令
    对"文件不存在"是直接报错的（cli.py:743），两条路径自相矛盾。
    """

    paths = EnforcementPaths(tmp_root)
    assert not paths.audit.exists()

    missing = run_cli("verify", "--audit", str(paths.audit))
    assert missing.returncode == 2
    assert "不存在" in missing.stdout

    paths.audit.write_text(
        json.dumps({"decision": "block", "file": "src/x.py"}) + "\n", encoding="utf-8"
    )
    foreign_only = run_cli("verify", "--audit", str(paths.audit))
    assert foreign_only.returncode == 2
    assert "没有本层" in foreign_only.stdout


def test_verify_json_ok_reflects_the_registry_check(tmp_root):
    """--check-registry --json 的 ok 必须把"未审核工具"算进去（同一份载荷不许自相矛盾）。"""

    paths = EnforcementPaths(tmp_root)
    document = json.loads(
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys,yaml,json;print(json.dumps(yaml.safe_load("
                "open(sys.argv[1],encoding='utf-8'))))",
                str(paths.registry),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout
    )
    document["tools"][0]["parameters"][1]["max_chars"] = 1  # 审核之后被改动
    paths.registry.write_text(json.dumps(document), encoding="utf-8")

    completed = run_cli("verify", "--json", "--check-registry", *paths_args(paths))

    assert completed.returncode == 2, completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["unapproved_tools"], payload
    assert payload["ok"] is False, "有未审核工具时 ok 不能是 true"
    assert any("未审核的工具" in issue for issue in payload["issues"])


def test_tampered_registry_is_reported(tmp_root):
    paths = EnforcementPaths(tmp_root)
    document = json.loads(
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys,yaml,json;print(json.dumps(yaml.safe_load("
                "open(sys.argv[1],encoding='utf-8'))))",
                str(paths.registry),
            ],
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
    # （self-check 已经往 --audit 指定的文件里写过本层记录，所以这里是"有证据"的 0）。
    audit_only = run_cli("verify", "--audit", str(paths.audit))
    assert audit_only.returncode == 0
    with_registry = run_cli("verify", "--check-registry", *paths_args(paths))
    assert with_registry.returncode == 2
    assert "未审核的工具" in with_registry.stdout


# --------------------------------------------------------------------------- precheck


def test_precheck_allows_and_blocks_with_the_documented_exit_codes(enforcement_paths):
    seed(enforcement_paths)
    allowed = write_request(enforcement_paths, "allow.json")

    completed = run_cli(
        "precheck",
        "--request", str(allowed),
        "--workspace", str(enforcement_paths.workspace),
        *paths_args(enforcement_paths),
    )
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
        "precheck",
        "--request", str(blocked),
        "--workspace", str(enforcement_paths.workspace),
        *paths_args(enforcement_paths),
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
    assert (
        not enforcement_paths.ledger.exists()
        or "claim" not in enforcement_paths.ledger.read_text(encoding="utf-8")
    )

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
        "execute",
        "--request", str(request),
        "--workspace", str(enforcement_paths.workspace),
        *paths_args(enforcement_paths),
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
        "execute",
        "--request", str(request),
        "--workspace", str(enforcement_paths.workspace),
        *paths_args(enforcement_paths),
    )
    assert first.returncode == 0
    content = enforcement_paths.read("src/shop/order_controller.py")

    second = run_cli(
        "execute",
        "--request", str(request),
        "--workspace", str(enforcement_paths.workspace),
        *paths_args(enforcement_paths),
    )
    assert second.returncode == 1
    assert "action_replay" in second.stdout
    assert enforcement_paths.read("src/shop/order_controller.py") == content


def test_missing_trace_reports_an_error(enforcement_paths):
    seed(enforcement_paths)
    completed = run_cli(
        "trace", "--action-id", "never-happened", "--audit", str(enforcement_paths.audit)
    )
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
        "execute",
        "--request", str(request),
        "--workspace", str(enforcement_paths.workspace),
        *paths_args(enforcement_paths),
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
    records = approval_records(approval)
    assert [item["subject"] for item in records] == ["local-user"]
    assert [item["tool_id"] for item in records] == ["exec.process"]

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
    # 示例用的是仓库默认台账（.tmp/artifacts/enforcement-ledger.jsonl），因此 action_id
    # 必须每次唯一，否则第二次运行会正确地判成重放。示例表达的是同一条请求形状。
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


def write_shell_request(
    paths: EnforcementPaths, name: str, *, action_id: str, command: str = "print('ok')"
) -> Path:
    """命令类工具的请求（测试注册表的 exec.shell 用当前解释器执行，跨平台可跑）。"""

    document = {
        "action_id": action_id,
        "request_id": action_id,
        "agent": "dsh",
        "tool_id": "exec.shell",
        "subject": "local-user",
        "roles": ["owner"],
        "params": {"command": command, "description": "demo"},
        "workspace": str(paths.workspace),
    }
    target = paths.root / name
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def test_pattern_approval_makes_a_governed_session_rerunnable(enforcement_paths):
    """G4 的真实场景：管理员签一张"允许跑这条命令"的条子，换调用编号仍然可用。

    条子绑的是"工具 + 参数模式 + 主体 + 窗口 + 次数上限"，不再绑运行期现生成的调用编号；
    但同一个 action_id 仍然绝不会执行第二次（下一次 execute 会判 action_replay）。
    """

    approval = enforcement_paths.root / "pattern-approval.json"
    first = write_shell_request(enforcement_paths, "shell-1.json", action_id="pat-call-1")
    approved = run_cli(
        "approve",
        "--request",
        str(first),
        "--out",
        str(approval),
        "--granted-by",
        "alice",
        "--roles",
        "reviewer",
        "--binding",
        "pattern",
        "--max-uses",
        "3",
        "--param-pattern",
        "command=^print[(]'ok'[)]$",
        "--param-pattern",
        "description=.*",
        *paths_args(enforcement_paths),
    )
    assert approved.returncode == 0, approved.stderr
    records = approval_records(approval)
    assert [item["tool_id"] for item in records] == ["exec.shell"]
    payload = records[0]
    assert payload["binding"] == "pattern"
    assert payload["max_uses"] == 3
    assert payload["action_hash"] is None, "模式化审批不得绑定运行期生成的调用编号"
    # 模式必须覆盖本次请求的全部参数：只绑 command 会漏掉 description 那一格。
    assert payload["param_patterns"] == {
        "command": "^print[(]'ok'[)]$",
        "description": ".*",
    }

    def execute(request_path: Path) -> subprocess.CompletedProcess[str]:
        return run_cli(
            "execute",
            "--request",
            str(request_path),
            "--approval",
            str(approval),
            "--workspace",
            str(enforcement_paths.workspace),
            *paths_args(enforcement_paths),
        )

    # 换调用编号、命令逐字一致：执行两次都应当 delivered
    for index in (1, 2):
        request = write_shell_request(
            enforcement_paths, f"shell-run-{index}.json", action_id=f"pat-call-{index}"
        )
        executed = execute(request)
        assert executed.returncode == 0, executed.stdout + executed.stderr
        assert "final: delivered" in executed.stdout

    # 第一个 action_id 再来一次：重放拦截与审批档位无关（额度还剩一次，仍然必须拒）
    replay = execute(first)
    assert replay.returncode == 1
    assert "final: blocked (action_replay)" in replay.stdout, replay.stdout

    # 第三次（新编号）用完额度
    third = write_shell_request(enforcement_paths, "shell-run-3.json", action_id="pat-call-3")
    assert execute(third).returncode == 0

    # 第四次：次数上限用尽
    fourth = write_shell_request(enforcement_paths, "shell-run-4.json", action_id="pat-call-4")
    exhausted = execute(fourth)
    assert exhausted.returncode == 1
    assert "approval_invalid" in exhausted.stdout
    assert "次数上限" in exhausted.stdout


def test_approve_merges_records_for_several_tools_into_one_store(enforcement_paths):
    """G4/5.21：一个审批文件可以放**多个工具**的放行；默认**并入**，不是覆盖。

    修前是"一个文件一条记录"，而桌面端 GUI 的每个动作都经过 run_code 传输工具——
    名额只能给一个工具，另一个永远拿不到审批（给了传输工具，跑命令的工具一律
    approval_invalid；反过来则整个会话冻结）。这里钉住两件事：

    1. 签第二个工具**不会抹掉**第一个（否则"名额只有一个"只是换了个形状）；
    2. **重签同一个工具**是取代，不会并排留下两张条子（一张更旧/更松的条子留在文件里，
       下一次加载就得靠选择规则去猜该用哪张）。
    """

    store = enforcement_paths.root / "store" / "approval.json"
    shell = write_shell_request(enforcement_paths, "merge-shell.json", action_id="merge-shell-1")
    delegated = write_request(
        enforcement_paths,
        "merge-delegated.json",
        action_id="merge-delegated-1",
        tool_id="exec.delegated",
        roles=["owner"],
        params={"code": "value = 1\n", "description": "demo"},
    )

    def approve(request: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return run_cli(
            "approve",
            "--request",
            str(request),
            "--out",
            str(store),
            "--granted-by",
            "alice",
            "--roles",
            "reviewer",
            "--binding",
            "pattern",
            "--max-uses",
            "3",
            *extra,
            *paths_args(enforcement_paths),
        )

    shell_patterns = (
        "--param-pattern", "command=^print[(]'ok'[)]$",
        "--param-pattern", "description=.*",
    )
    delegated_patterns = (
        "--param-pattern", "code=(?s).*",
        "--param-pattern", "description=.*",
    )

    first = approve(shell, *shell_patterns, "--approval-id", "approval-merge-shell")
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["tools"] == ["exec.shell"]

    second = approve(delegated, *delegated_patterns, "--approval-id", "approval-merge-delegated")
    assert second.returncode == 0, second.stderr
    assert json.loads(second.stdout)["tools"] == ["exec.delegated", "exec.shell"]
    assert [item["tool_id"] for item in approval_records(store)] == [
        "exec.shell",
        "exec.delegated",
    ]

    # 两个工具各自用自己的条子通过审批这一关（同一个文件、同一份注册表）
    for request in (shell, delegated):
        checked = run_cli(
            "precheck",
            "--request",
            str(request),
            "--approval",
            str(store),
            "--workspace",
            str(enforcement_paths.workspace),
            *paths_args(enforcement_paths),
        )
        assert "[passed ] approval" in checked.stdout, checked.stdout

    # 重签 exec.shell：取代旧的那条，另一个工具一个字不动
    again = approve(shell, *shell_patterns, "--approval-id", "approval-merge-shell-2")
    assert again.returncode == 0, again.stderr
    summary = json.loads(again.stdout)
    assert summary["superseded"] == ["approval-merge-shell"]
    assert summary["tools"] == ["exec.delegated", "exec.shell"]
    remaining = approval_records(store)
    assert [item["approval_id"] for item in remaining] == [
        "approval-merge-shell-2",
        "approval-merge-delegated",
    ]


def test_two_records_in_one_store_each_execute_under_their_own_approval(enforcement_paths):
    """①（执行侧）：两份记录并存时，两个工具**各自执行一次**，各用各的条子。

    与上面那条（只看审批这一关）不同，这里走完整的 execute：认领 action_id →
    占用审批额度 → 签发授权 → 执行 → 事后核对。判据是审计里两次 pre_decision 用的
    approval_id 不同——"各自持一份放行"在账本上必须看得见。
    """

    store = enforcement_paths.root / "store" / "approval.json"
    shell = write_shell_request(enforcement_paths, "store-shell.json", action_id="store-shell-1")
    process = write_request(
        enforcement_paths,
        "store-process.json",
        action_id="store-process-1",
        tool_id="exec.process",
        roles=["owner"],
        params={"argv": ["python", "-c", "print('cli-ok')"], "description": "demo"},
    )

    def approve(request: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return run_cli(
            "approve",
            "--request",
            str(request),
            "--out",
            str(store),
            "--granted-by",
            "alice",
            "--roles",
            "reviewer",
            *extra,
            *paths_args(enforcement_paths),
        )

    patterned = approve(
        shell,
        "--binding",
        "pattern",
        "--max-uses",
        "3",
        "--param-pattern",
        "command=^print[(]'ok'[)]$",
        "--param-pattern",
        "description=.*",
        "--approval-id",
        "approval-store-shell",
    )
    assert patterned.returncode == 0, patterned.stderr

    # exec.process 的参数 argv 是列表（模式匹配只支持字符串 / 整数 / 布尔），
    # 因此这一格只能走单次绑定——两种档位在同一个文件里并存，互不影响。
    bound = approve(process, "--approval-id", "approval-store-process")
    assert bound.returncode == 0, bound.stderr
    assert json.loads(bound.stdout)["tools"] == ["exec.process", "exec.shell"]

    for request in (shell, process):
        executed = run_cli(
            "execute",
            "--request",
            str(request),
            "--approval",
            str(store),
            "--workspace",
            str(enforcement_paths.workspace),
            *paths_args(enforcement_paths),
        )
        assert executed.returncode == 0, executed.stdout + executed.stderr
        assert "final: delivered" in executed.stdout

    pre = [
        item
        for item in (
            json.loads(line)
            for line in enforcement_paths.audit.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if item.get("stage") == "pre_decision"
    ]
    assert [item["payload"]["approval_id"] for item in pre] == [
        "approval-store-shell",
        "approval-store-process",
    ]




def test_approve_refuses_contradictory_or_unknown_binding_flags(enforcement_paths):
    request = write_shell_request(enforcement_paths, "shell-bad.json", action_id="bad-1")
    approval = enforcement_paths.root / "bad-approval.json"
    base = [
        "--request", str(request),
        "--out", str(approval),
        "--granted-by", "alice",
        "--roles", "reviewer",
    ]

    mixed = run_cli(
        "approve", *base, "--param-pattern", "command=.*", *paths_args(enforcement_paths)
    )
    assert mixed.returncode == 2
    assert "--binding pattern" in mixed.stderr

    no_pattern = run_cli("approve", *base, "--binding", "pattern", *paths_args(enforcement_paths))
    assert no_pattern.returncode == 2
    assert "param-pattern" in no_pattern.stderr

    misuse = run_cli("approve", *base, "--max-uses", "3", *paths_args(enforcement_paths))
    assert misuse.returncode == 2
    assert "max-uses" in misuse.stderr

    unknown_param = run_cli(
        "approve",
        *base,
        "--binding",
        "pattern",
        "--param-pattern",
        "payload=.*",
        *paths_args(enforcement_paths),
    )
    assert unknown_param.returncode == 2
    assert "不是工具" in unknown_param.stderr


def test_self_check_passes_for_the_repository_assets():
    completed = run_cli("self-check")

    assert completed.returncode == 0, completed.stderr
    assert "self-check ok" in completed.stdout


def test_json_output_is_machine_readable(enforcement_paths):
    seed(enforcement_paths)
    request = write_request(enforcement_paths, "json.json")

    completed = run_cli(
        "execute",
        "--json",
        "--request", str(request),
        "--workspace", str(enforcement_paths.workspace),
        *paths_args(enforcement_paths),
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
