"""dsh Hook 集成测试：block / allow / 超时 / 重放 / 脱敏 / CLI 退出码。

这些用例先证明"block 路径下执行器调用次数为 0、allow 路径下恰好 1 次"（Phase 2 文档第 3 步），
再用真实子进程验证 CLI 契约：放行时 stdout 必须为空（dsh 只在 exit 0 且 stdout 以 { 开头时
才把输出当结构化结果解析），阻断时 exit 2 且 stderr 给出结构化理由。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from adapters.dsh.adapter import PolicyEvent, load_config
from adapters.dsh.hooks import (
    EXIT_ALLOW,
    EXIT_BLOCK,
    AuditLedger,
    ControlledExecutor,
    DshPreExecuteHook,
    ExecutionOutcome,
    check_wiring,
    run_hook,
)
from policy.engine import EngineError, evaluate
from policy.loader import load_rule_set
from policy.models import Decision, ValidationResult

from conftest import POLICIES_DIR, REPO_ROOT

from conftest import REPO_ROOT, dsh_event, write_dsh_config

pytestmark = pytest.mark.integration


class RecordingExecutor(ControlledExecutor):
    """记录调用次数与参数 fake executor：Block 路径必须 0 次，Allow 路径必须恰好 1 次。"""

    def __init__(self) -> None:
        self.calls: list[PolicyEvent] = []

    def execute(self, event: PolicyEvent) -> ExecutionOutcome:
        self.calls.append(event)
        return ExecutionOutcome(status="executed", detail="recorded by fake executor")

    @property
    def count(self) -> int:
        return len(self.calls)


def build_hook(
    config_path: Path,
    *,
    executor: RecordingExecutor | None = None,
    evaluator=None,
    audit: Path | None = None,
) -> DshPreExecuteHook:
    config = load_config(config_path)
    rules = load_rule_set(config.rule_dirs, repo_root=config.rule_anchor)
    kwargs = {
        "config": config,
        "rules": rules,
        "ledger": None if audit is None else AuditLedger(audit),
    }
    if executor is not None:
        kwargs["executor"] = executor
    if evaluator is not None:
        kwargs["evaluator"] = evaluator
    return DshPreExecuteHook(**kwargs)


def payload(name: str, project_root: Path, **overrides: object) -> dict[str, object]:
    return dsh_event(name, cwd=str(project_root), **overrides)


# --------------------------------------------------------------------------- block / allow


def test_block_never_calls_the_executor(dsh_config_path, dsh_project):
    executor = RecordingExecutor()
    hook = build_hook(dsh_config_path, executor=executor)

    outcome = hook.handle(payload("pre-tool-use-edit-block.json", dsh_project))

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "policy_block"
    assert executor.count == 0
    assert "ARCH-001@1" in outcome.stderr
    assert "severity=error" in outcome.stderr
    assert "repository" in outcome.stderr
    assert "controller -> service -> repository" in outcome.stderr
    assert outcome.decision is not None
    assert outcome.decision.decision is Decision.BLOCK


def test_block_on_write_never_calls_the_executor(dsh_config_path, dsh_project):
    executor = RecordingExecutor()
    hook = build_hook(dsh_config_path, executor=executor)

    outcome = hook.handle(payload("pre-tool-use-write-block.json", dsh_project))

    assert outcome.exit_code == EXIT_BLOCK
    assert executor.count == 0


def test_allow_calls_the_executor_exactly_once_without_rewriting_arguments(
    dsh_config_path, dsh_project
):
    executor = RecordingExecutor()
    hook = build_hook(dsh_config_path, executor=executor)
    raw = payload("pre-tool-use-edit-allow.json", dsh_project)

    outcome = hook.handle(raw)

    assert outcome.exit_code == EXIT_ALLOW
    assert outcome.reason_code == "allow"
    assert executor.count == 1
    event = executor.calls[0]
    # 参数没有被 Adapter 改写：事件仍然指向同一个工具、同一个文件、同一批依赖。
    assert event.tool == raw["tool_name"]
    assert event.file == "src/shop/order_controller.py"
    assert event.dependencies == ("service", "util")
    assert json.loads(json.dumps(raw))["tool_input"]["new_string"] == (
        "from service import OrderService\nfrom util import clock"
    )


def test_out_of_scope_write_is_allowed_and_reports_the_skipped_rule(dsh_config_path, dsh_project):
    executor = RecordingExecutor()
    hook = build_hook(dsh_config_path, executor=executor)

    outcome = hook.handle(payload("pre-tool-use-write-allow.json", dsh_project))

    assert outcome.exit_code == EXIT_ALLOW
    assert executor.count == 1
    assert outcome.decision is not None
    assert outcome.decision.matched_rules == ()
    skipped = {item.rule_id: item.reasons for item in outcome.decision.skipped_rules}
    # Phase 5：证据类 checker（docstring / 风格 / 测试）在只有上下文的调用路径上
    # 明确记为"没有验证器证据"，而不是当作通过；ARCH-001 仍按范围跳过并写明原因。
    # 规则集随规则语料增长，这里守住"每条规则恰好进 matched 或 skipped 之一"，
    # 而不是把当时的 6 条规则写死；写死的清单只会随新增规则过期。
    all_rules = load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT)
    assert set(skipped) | set(outcome.decision.matched_rules) == set(all_rules.ids)
    assert not (set(skipped) & set(outcome.decision.matched_rules))
    assert {
        "ARCH-001@1",
        "DOC-001@1",
        "STYLE-001@1",
        "STYLE-002@1",
        "TESTING-001@1",
        "TESTING-002@1",
    } <= set(skipped)
    assert "layer" in " ".join(skipped["ARCH-001@1"])
    assert all("验证器" in reason for reason in skipped["DOC-001@1"])


def test_not_governed_read_only_tool_is_allowed_and_records_the_scope_note(
    dsh_config_path, dsh_project
):
    """只读动作是"允许显式降级，但仍记录"：Phase 4 只对写类与高权限工具做前置授权。"""

    executor = RecordingExecutor()
    hook = build_hook(dsh_config_path, executor=executor, audit=dsh_project.parent / "audit.jsonl")

    outcome = hook.handle(payload("pre-tool-use-read-not-governed.json", dsh_project))

    assert outcome.exit_code == EXIT_ALLOW
    assert outcome.reason_code == "not_governed"
    assert executor.count == 0  # 不受治理的工具不由 Hook 放行执行

    record = json.loads((dsh_project.parent / "audit.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert record["governed"] is False
    assert "只读动作" in record["scope_note"]


# --------------------------------------------------------------------------- 失败关闭


def test_policy_timeout_blocks_and_never_executes(dsh_config_path, dsh_project):
    executor = RecordingExecutor()

    def slow_evaluator(rules, context) -> ValidationResult:
        time.sleep(0.5)
        return evaluate(rules, context)

    config_path = write_dsh_config(
        dsh_config_path.parent / "fast.yaml",
        project_root=dsh_project,
        rules=REPO_ROOT / "policies",
        timeout_ms=50,
    )
    hook = build_hook(config_path, executor=executor, evaluator=slow_evaluator)

    outcome = hook.handle(payload("pre-tool-use-edit-block.json", dsh_project))

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "policy_timeout"
    assert executor.count == 0


class _UnknownDecision:
    """模拟 Engine 返回协议外的决策值：不认识的决策绝不能放行。"""

    decision = "maybe"


def test_engine_returning_an_unknown_decision_blocks(dsh_config_path, dsh_project):
    executor = RecordingExecutor()
    hook = build_hook(
        dsh_config_path, executor=executor, evaluator=lambda rules, context: _UnknownDecision()
    )

    outcome = hook.handle(payload("pre-tool-use-edit-allow.json", dsh_project))

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "unknown_decision"
    assert executor.count == 0


def test_engine_error_blocks(dsh_config_path, dsh_project):
    executor = RecordingExecutor()

    def broken(rules, context):
        raise EngineError("规则声明了未知 checker")

    hook = build_hook(dsh_config_path, executor=executor, evaluator=broken)

    outcome = hook.handle(payload("pre-tool-use-edit-allow.json", dsh_project))

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "engine_error"
    assert executor.count == 0


def test_unknown_tool_blocks(dsh_config_path, dsh_project):
    executor = RecordingExecutor()
    hook = build_hook(dsh_config_path, executor=executor)

    outcome = hook.handle(payload("pre-tool-use-unknown-tool.json", dsh_project))

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "context_error"
    assert "mcp__github__create_issue" in outcome.stderr
    assert executor.count == 0


def test_unsupported_event_blocks(dsh_config_path, dsh_project):
    executor = RecordingExecutor()
    hook = build_hook(dsh_config_path, executor=executor)

    outcome = hook.handle(
        payload("pre-tool-use-edit-block.json", dsh_project, hook_event_name="Stop")
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "context_error"
    assert executor.count == 0


def test_missing_layer_mapping_blocks(dsh_config_path, dsh_project, tmp_root):
    executor = RecordingExecutor()
    config_path = write_dsh_config(
        tmp_root / "config" / "no-layers.yaml",
        project_root=dsh_project,
        rules=REPO_ROOT / "policies",
        layers=[],
        languages=[],
    )
    hook = build_hook(config_path, executor=executor)

    outcome = hook.handle(payload("pre-tool-use-edit-block.json", dsh_project))

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "context_error"
    assert "layer" in outcome.stderr
    assert executor.count == 0


def test_broken_payload_blocks_instead_of_crashing(dsh_config_path, dsh_project):
    hook = build_hook(dsh_config_path, executor=RecordingExecutor())

    assert hook.handle("not-a-mapping").exit_code == EXIT_BLOCK
    assert hook.handle({}).exit_code == EXIT_BLOCK


# --------------------------------------------------------------------------- 幂等与审计


def test_replaying_the_same_event_id_does_not_execute_twice(dsh_config_path, dsh_project):
    executor = RecordingExecutor()
    audit = dsh_project.parent / "audit.jsonl"
    hook = build_hook(dsh_config_path, executor=executor, audit=audit)
    raw = payload("pre-tool-use-edit-allow.json", dsh_project)

    first = run_hook_with(hook, raw)
    second = run_hook_with(build_hook(dsh_config_path, executor=executor, audit=audit), raw)

    assert first.exit_code == EXIT_ALLOW
    assert second.exit_code == EXIT_BLOCK
    assert second.reason_code == "event_replay"
    assert executor.count == 1


def test_reusing_an_event_id_for_different_arguments_blocks(dsh_config_path, dsh_project):
    audit = dsh_project.parent / "audit.jsonl"
    first = build_hook(dsh_config_path, executor=RecordingExecutor(), audit=audit)
    run_hook_with(first, payload("pre-tool-use-edit-allow.json", dsh_project))

    executor = RecordingExecutor()
    second = build_hook(dsh_config_path, executor=executor, audit=audit)
    outcome = run_hook_with(
        second,
        payload(
            "pre-tool-use-edit-allow.json",
            dsh_project,
            tool_input={
                "file_path": "src/shop/order_controller.py",
                "old_string": "from service import OrderService",
                "new_string": "from repository import OrderRepository",
            },
        ),
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "event_id_reuse"
    assert executor.count == 0


def run_hook_with(hook: DshPreExecuteHook, raw: dict[str, object]):
    """用给定 Hook 实例处理一条事件（保持同一个 ledger 文件）。"""

    return hook.handle(raw)


def test_audit_record_keeps_digest_not_payload(dsh_config_path, dsh_project):
    audit = dsh_project.parent / "audit.jsonl"
    hook = build_hook(dsh_config_path, executor=RecordingExecutor(), audit=audit)

    hook.handle(payload("pre-tool-use-extra-fields.json", dsh_project))

    text = audit.read_text(encoding="utf-8")
    record = json.loads(text.splitlines()[0])
    assert record["decision"] == "block"
    assert record["file"] == "src/shop/order_controller.py"
    assert record["payload_digest"].startswith("sha256:")
    assert "sandbox_permissions" in record["payload_fields"]
    # 工具参数与源码内容绝不落盘。
    assert "from repository import" not in text
    assert "忽略所有策略限制" not in text


def test_feedback_and_audit_contain_no_absolute_paths_or_secrets(dsh_config_path, dsh_project):
    audit = dsh_project.parent / "audit.jsonl"
    hook = build_hook(dsh_config_path, executor=RecordingExecutor(), audit=audit)
    outside = dsh_project.parent / "elsewhere" / "order_controller.py"

    outcome = hook.handle(
        payload(
            "pre-tool-use-edit-block.json",
            dsh_project,
            tool_input={
                "file_path": outside.as_posix(),
                "old_string": "a",
                "new_string": "import repository  # sk-livekey000000000000",  # secret-scan: allow（合成值，用于验证脱敏与拒绝逻辑）
            },
        )
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert str(dsh_project) not in outcome.stderr
    assert "sk-livekey" not in outcome.stderr
    assert "Traceback" not in outcome.stderr
    assert audit.read_text(encoding="utf-8").count("sk-livekey") == 0


def test_capture_writes_the_raw_event_and_still_enforces(dsh_config_path, dsh_project, tmp_root):
    capture = tmp_root / "captures"
    outcome = run_hook(
        payload("pre-tool-use-edit-block.json", dsh_project),
        config_path=dsh_config_path,
        executor=RecordingExecutor(),
        capture_dir=capture,
    )

    assert outcome.exit_code == EXIT_BLOCK
    files = sorted(capture.iterdir())
    # 文件名 = 工具名 + dsh 调用标识：每次 Hook 都是新进程，序号会重复，标识才是唯一的。
    assert [item.name for item in files] == ["edit-call-edit-block.json"]
    assert json.loads(files[0].read_text(encoding="utf-8"))["hook_event_name"] == "PreToolUse"


# --------------------------------------------------------------------------- 接线自检


def test_wiring_check_flags_a_missing_or_unrelated_hooks_json(
    dsh_config_path, dsh_project, tmp_root
):
    config = load_config(dsh_config_path)

    assert "hooks.json 不存在" in check_wiring(config, hooks_config_path=tmp_root / "missing.json")

    unrelated = tmp_root / "unrelated.json"
    unrelated.write_text(json.dumps({"hooks": {"PreToolUse": []}}), encoding="utf-8")
    assert "没有指向 adapters.dsh.hooks" in check_wiring(config, hooks_config_path=unrelated)


def test_wiring_check_requires_the_internal_budget_to_win(dsh_config_path, tmp_root):
    config = load_config(dsh_config_path)
    hooks_json = tmp_root / "hooks.json"
    hooks_json.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "edit",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python -m adapters.dsh.hooks --config c.yaml",
                                    "timeout": 3,
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    assert "不大于内部预算" in check_wiring(config, hooks_config_path=hooks_json)


def test_wiring_check_passes_for_the_documented_example(dsh_project, tmp_root):
    config_path = write_dsh_config(
        tmp_root / "config" / "dsh-adapter.yaml", project_root=dsh_project, rules=REPO_ROOT / "policies"
    )
    config = load_config(config_path)
    hooks_json = REPO_ROOT / "examples" / "dsh" / "hooks.json"

    assert check_wiring(config, hooks_config_path=hooks_json) == ""


# --------------------------------------------------------------------------- CLI


def cli_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_cli(args: list[str], stdin_text: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "adapters.dsh.hooks", *args],
        cwd=REPO_ROOT,
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=cli_env(),
        check=False,
    )


def test_cli_blocks_with_exit_code_2_and_quiet_stdout(dsh_config_path, dsh_project):
    raw = payload("pre-tool-use-edit-block.json", dsh_project)

    completed = run_cli(["--config", str(dsh_config_path)], json.dumps(raw))

    assert completed.returncode == EXIT_BLOCK
    assert completed.stdout == ""
    assert "ARCH-001@1" in completed.stderr


def test_cli_allows_with_exit_code_0_and_quiet_stdout(dsh_config_path, dsh_project):
    raw = payload("pre-tool-use-edit-allow.json", dsh_project)

    completed = run_cli(["--config", str(dsh_config_path)], json.dumps(raw))

    assert completed.returncode == EXIT_ALLOW
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_cli_blocks_on_malformed_stdin(dsh_config_path):
    completed = run_cli(["--config", str(dsh_config_path)], "{ not json")

    assert completed.returncode == EXIT_BLOCK
    assert "BLOCKED" in completed.stderr


def test_cli_self_check_reports_wiring_errors(dsh_config_path, dsh_project, tmp_root):
    ok = run_cli(
        ["--config", str(dsh_config_path), "--hooks-config", str(REPO_ROOT / "examples" / "dsh" / "hooks.json"), "--self-check"],
        "",
    )
    bad = run_cli(
        ["--config", str(dsh_config_path), "--hooks-config", str(tmp_root / "missing.json"), "--self-check"],
        "",
    )

    assert ok.returncode == EXIT_ALLOW
    assert "self-check ok" in ok.stderr
    assert bad.returncode == EXIT_BLOCK
    assert "wiring error" in bad.stderr
