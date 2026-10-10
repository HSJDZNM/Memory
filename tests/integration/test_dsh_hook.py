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
from conftest import POLICIES_DIR, REPO_ROOT, dsh_event, write_dsh_config

from adapters.dsh.adapter import PolicyEvent, load_config
from adapters.dsh import hooks as hooks_module
from adapters.dsh.hooks import (
    EXIT_ALLOW,
    EXIT_BLOCK,
    SCOPE_FALLBACK_LINE_PREFIX,
    SCOPE_FALLBACK_SCHEMA_VERSION,
    SCOPE_OUTSIDE_POST_REASON,
    SCOPE_OUTSIDE_REASON,
    AuditLedger,
    ControlledExecutor,
    DshPreExecuteHook,
    ExecutionOutcome,
    check_wiring,
    run_hook,
)
from enforcement.models import ActionRequestError
from policy.engine import EngineError, evaluate
from policy.loader import load_rule_set
from policy.models import Decision, ValidationResult

pytestmark = pytest.mark.integration

# 直接调 CLI 的用例必须像真实接线一样把 hooks.json 指出来：G12 之后"接线自检缺席"
# 是失败关闭（退出码 2），不再默认放行。这里复用仓库文档里那份接线示例，
# 于是这些用例同时也在守着"示例接线真的能过自检"（timeout=30s > 内部预算 5000ms）。
HOOKS_CONFIG = REPO_ROOT / "examples" / "dsh" / "hooks.json"


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


def test_parameter_error_keeps_the_structured_reason_code(
    dsh_config_path, dsh_project, monkeypatch
):
    """G5 的后半段：范围问题不能被包成笼统的"参数错误"。

    实测过的误导：workdir 等于工作区根被判越界时，反馈里写的是 enforcement_param_error，
    人和模型都会以为参数写错了，而真实原因是范围（path_out_of_scope）。
    Phase 4 的 ActionRequestError 带**结构化** reason_code，Hook 必须透传它；
    只有拿不到结构化原因时才可以退回笼统值。
    """

    audit = dsh_config_path.parent / "audit.jsonl"
    hook = build_hook(dsh_config_path, audit=audit)

    def refuse(**_: object) -> None:
        raise ActionRequestError(
            "参数 workdir 不在受控工作区内：路径不在仓库之内", reason_code="path_out_of_scope"
        )

    monkeypatch.setattr(hook.bridge, "build_request", refuse)

    outcome = hook.handle(payload("pre-tool-use-edit-allow.json", dsh_project))

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "path_out_of_scope"
    # 审计里也必须如实：既要有结构化码，也不能同时留下被包过的笼统码。
    # （注意审计里还有别的 reason_code，例如 G11 的 context_injection 留痕记录，
    # 所以这里按"存在/不存在"断言，而不是取最后一条。）
    codes = [
        json.loads(line)["reason_code"]
        for line in audit.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert "path_out_of_scope" in codes
    assert "enforcement_param_error" not in codes


def test_parameter_error_falls_back_when_no_structured_code(
    dsh_config_path, dsh_project, monkeypatch
):
    """反向：拿不到结构化 reason_code 时退回笼统值，而不是编一个具体的码出来。"""

    audit = dsh_config_path.parent / "audit.jsonl"
    hook = build_hook(dsh_config_path, audit=audit)

    def refuse(**_: object) -> None:
        raise ActionRequestError("参数不合法")

    monkeypatch.setattr(hook.bridge, "build_request", refuse)

    outcome = hook.handle(payload("pre-tool-use-edit-allow.json", dsh_project))

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "enforcement_param_error"


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
    #
    # 依赖名集合是 G6 语义变更后的**正确值**，不是为了让测试变绿而改的数字。
    # 变更文本见下面第 128 行的断言：from service import OrderService / from util import clock。
    # - from 的模块本身是依赖（service / util），完整点分路径必须保留
    #   （旧实现只留顶层名字，等于把 shop.order_repository 这类写法放行）；
    # - 被导入的名字还**可能是子模块**： from X import Y 里的 Y 可能是子模块
    #   （"from shop import order_repository" 正是必须命中的写法之一，AST 路径会把边
    #   落在子模块文件上）。预执行路径没有模块索引，无法区分"Y 是子模块"还是
    #   "Y 是类/函数"，因此把候选一起登记。
    #   漏登记 = 结构性放行；多登记只可能让依赖规则更早阻断 —— 方向是失败关闭。
    assert event.dependencies == ("service", "service.orderservice", "util", "util.clock")
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

    audit_lines = (dsh_project.parent / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(audit_lines[0])
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


def test_an_out_of_scope_read_blocks_with_an_actionable_reason(dsh_config_path, dsh_project):
    """N22：面向模型的理由里要有可用替代；只读越界仍然一律阻断。"""

    executor = RecordingExecutor()
    hook = build_hook(dsh_config_path, executor=executor)

    outcome = hook.handle(
        payload(
            "pre-tool-use-read-not-governed.json",
            dsh_project,
            tool_name="glob",
            tool_input={"pattern": "**/*.py", "path": str(dsh_project.parent)},
        )
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "context_error"
    assert "仓库相对路径" in outcome.stderr
    assert "path_scope=workspace" in outcome.stderr
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
                # 合成值：这里验证的是"凭据被脱敏"与"越界被拒绝"，不是真凭据
                "new_string": "import repository  # sk-livekey000000000000",  # secret-scan: allow（合成值：验证凭据脱敏与越界拒绝，不是真凭据）
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
        tmp_root / "config" / "dsh-adapter.yaml",
        project_root=dsh_project,
        rules=REPO_ROOT / "policies",
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

    completed = run_cli(
        ["--config", str(dsh_config_path), "--hooks-config", str(HOOKS_CONFIG)],
        json.dumps(raw),
    )

    assert completed.returncode == EXIT_BLOCK
    assert completed.stdout == ""
    assert "ARCH-001@1" in completed.stderr


def test_cli_allows_with_exit_code_0_and_quiet_stdout(dsh_config_path, dsh_project):
    raw = payload("pre-tool-use-edit-allow.json", dsh_project)

    completed = run_cli(
        ["--config", str(dsh_config_path), "--hooks-config", str(HOOKS_CONFIG)],
        json.dumps(raw),
    )

    assert completed.returncode == EXIT_ALLOW
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_cli_blocks_on_malformed_stdin(dsh_config_path):
    completed = run_cli(["--config", str(dsh_config_path)], "{ not json")

    assert completed.returncode == EXIT_BLOCK
    assert "BLOCKED" in completed.stderr


def test_cli_self_check_reports_wiring_errors(dsh_config_path, dsh_project, tmp_root):
    ok = run_cli(
        [
            "--config", str(dsh_config_path),
            "--hooks-config", str(REPO_ROOT / "examples" / "dsh" / "hooks.json"),
            "--self-check",
        ],
        "",
    )
    bad = run_cli(
        [
            "--config", str(dsh_config_path),
            "--hooks-config", str(tmp_root / "missing.json"),
            "--self-check",
        ],
        "",
    )

    assert ok.returncode == EXIT_ALLOW
    assert "self-check ok" in ok.stderr
    assert bad.returncode == EXIT_BLOCK
    assert "wiring error" in bad.stderr

# --------------------------------------------------------------------------- 台账路径（N21）


def audit_records(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_the_derived_ledger_path_is_a_first_class_fact(tmp_root, dsh_project):
    """N21：带 --audit 时台账路径被派生改写，这个事实必须读得到、有显式警告。

    修前：配置里声明了 enforcement_ledger，带 --audit 跑时它被静默覆盖，
    按配置名去数台账得到 0 条 —— 会被读成"事后核对从来没跑过"。
    派生本身保留（两份 JSONL 协议不能混写），改的是"这件事没人读得到"。
    """

    from adapters.dsh.hooks import EFFECTIVE_PATHS_PREFIX

    declared = tmp_root / "config" / "declared-ledger.jsonl"
    config_path = write_dsh_config(
        tmp_root / "config" / "override.yaml",
        project_root=dsh_project,
        rules=POLICIES_DIR,
        enforcement_ledger=str(declared),
    )
    state = dsh_project.parent / "state"
    audit = state / "audit.jsonl"

    # 1) 自检把"真正生效的路径"写成一行一等输出，并显式指出配置声明被覆盖
    checked = run_cli(
        [
            "--config", str(config_path),
            "--audit", str(audit),
            "--hooks-config", str(HOOKS_CONFIG),
            "--self-check",
        ],
        "",
    )
    assert checked.returncode == EXIT_ALLOW, checked.stderr
    prefix = EFFECTIVE_PATHS_PREFIX
    lines = [item for item in checked.stderr.splitlines() if item.startswith(prefix)]
    assert len(lines) == 1, checked.stderr
    report = json.loads(lines[0][len(prefix):])
    assert report["ledger_source"] == "derived_from_audit"
    assert report["ledger_overridden"] is True
    assert report["ledger"].endswith("audit.enforcement-ledger.jsonl")
    assert report["ledger_declared"].endswith("declared-ledger.jsonl")
    assert "派生" in report["ledger_override_note"]

    # 2) 台账真的写在派生路径上；配置声明的那份根本没有被创建
    pre = run_hook(
        payload("pre-tool-use-edit-allow.json", dsh_project),
        config_path=config_path,
        audit_path=audit,
    )
    assert pre.exit_code == EXIT_ALLOW, pre.stderr
    derived = state / "audit.enforcement-ledger.jsonl"
    assert derived.is_file(), "台账必须落在派生路径上"
    assert not declared.exists(), "配置声明的那份不该被写"

    # 3) 审计里有一条写明两个路径的警告记录（元信息：不带 hook_event / action_id）
    overrides = [
        item for item in audit_records(audit) if item.get("reason_code") == "ledger_path_overridden"
    ]
    assert len(overrides) == 1, overrides
    warning = overrides[0]["ledger_path"]
    assert warning["effective"].endswith("audit.enforcement-ledger.jsonl")
    assert warning["declared"].endswith("declared-ledger.jsonl")
    assert warning["source"] == "derived_from_audit"
    assert "hook_event" not in overrides[0]
    assert "action_id" not in overrides[0]

    # 4) 每会话只记一次：同一次运行里的第二次判定不再重复写
    again = run_hook(
        payload("pre-tool-use-edit-allow.json", dsh_project, tool_use_id="call-edit-allow-2"),
        config_path=config_path,
        audit_path=audit,
    )
    assert again.exit_code == EXIT_ALLOW, again.stderr
    overrides = [
        item for item in audit_records(audit) if item.get("reason_code") == "ledger_path_overridden"
    ]
    assert len(overrides) == 1


def test_without_the_audit_override_the_declared_ledger_path_is_the_effective_one(
    tmp_root, dsh_project
):
    """反向对照：不带 --audit 时没有"被改写"这回事，也就不该有警告。"""

    from adapters.dsh.hooks import EFFECTIVE_PATHS_PREFIX

    declared = tmp_root / "config" / "declared-ledger.jsonl"
    config_path = write_dsh_config(
        tmp_root / "config" / "declared.yaml",
        project_root=dsh_project,
        rules=POLICIES_DIR,
        enforcement_ledger=str(declared),
    )

    checked = run_cli(
        ["--config", str(config_path), "--hooks-config", str(HOOKS_CONFIG), "--self-check"],
        "",
    )

    assert checked.returncode == EXIT_ALLOW, checked.stderr
    prefix = EFFECTIVE_PATHS_PREFIX
    lines = [item for item in checked.stderr.splitlines() if item.startswith(prefix)]
    report = json.loads(lines[0][len(prefix):])
    assert report["ledger_source"] == "configured"
    assert report["ledger_overridden"] is False
    assert report["ledger_override_note"] is None
    assert report["ledger"] == report["ledger_declared"]

# --------------------------------------------------------------------------- Phase 4 阻断明细的脱敏


def test_the_phase_four_block_detail_is_redacted_in_the_audit(
    dsh_config_path, dsh_project, tmp_root
):
    """AGENTS 第 16 条：进审计的明细与给模型的 stderr 是**两份产物**，两份都要脱敏。

    实测（08 轮复核，独立探针 probe_p4_detail_redaction.py）：_enforcement_block 给模型的
    stderr 走了 sanitize，而写进审计的 enforcement_detail 是原文——一条 workdir 越界的 pwsh
    载荷会让本机绝对路径落进审计 JSONL（07 轮的 30 条矩阵里没有这个形状，所以一直没被触发）。

    修复用 enforcement.audit.redact_text（工作区→<workspace>、绝对路径→<abs>），
    而不是给模型看的 sanitize：后者带 FEEDBACK_MAX_CHARS=4000 的**面向模型**截断，
    拿它洗审计明细会把明细截成另一种失真。
    """

    audit = dsh_project.parent / "audit.jsonl"
    hook = build_hook(dsh_config_path, audit=audit)
    outside = tmp_root / "outside-workdir"
    outside.mkdir(parents=True, exist_ok=True)

    outcome = hook.handle(
        payload(
            "pre-tool-use-pwsh-execute.json",
            dsh_project,
            tool_input={
                "command": "python -m pytest -q",
                "description": "跑一次测试",
                "timeoutMs": 60000,
                "workdir": str(outside),
            },
        )
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "path_out_of_scope"
    # 对照：给模型的那一份早就是脱敏的（既有行为）
    assert str(outside) not in outcome.stderr

    gated = [
        item
        for item in (
            json.loads(line)
            for line in audit.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if item.get("reason_code") == "path_out_of_scope"
    ]
    assert gated
    detail = gated[-1]["enforcement_detail"]
    assert str(outside) not in detail
    assert str(outside).replace("\\", "/") not in detail
    assert str(dsh_project) not in detail
    assert str(dsh_project).replace("\\", "/") not in detail
    # 脱敏是换成可读记号，不是删掉信息：读者仍看得出这里出现过一个绝对路径
    assert "<abs>" in detail or "<workspace>" in detail

# --------------------------------------------------------------------------- 作用域感知（task-2）
#
# 背景：桥一定声明 projectDir，而 projectDir 兼任「Hook 在哪个目录启动」与「载荷里 cwd 的取值」。
# 于是判定用来归一化工具目标的 cwd 被覆盖成 projectDir——会话开在别的目录时，绝对路径被拒、
# 相对路径被拿去相对 projectDir 解析（判定关于**另一个文件**，而结论照样进账本，比拦住更坏）。
#
# 第 2 代载荷（hook_payload_version: "1.0"）多带一个**会话自己的** cwd，Hook 于是能先判范围：
#   会话 cwd 在 project_root 内 → 与今天逐字节相同；
#   在外                      → 放行，但写一条**显式**的 session_out_of_scope
#                              （专属码；与只读降级的 not_governed 不是同一件事，见本文件末尾那条对照）；
#   声明第 2 代却给不出可解析的绝对会话 cwd → 失败关闭（「证明不了」不是「允许」）；
#   没有版本键（第 1 代 / 外部方言桥）→ 范围问题不适用，走今天的路径。


def _audit_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_out_of_scope_session_is_allowed_with_an_explicit_record(dsh_config_path, dsh_project):
    """范围外的会话：放行，但账本上必须能读出「这次没管」+ 两个事实。"""

    audit = dsh_config_path.parent / "scope-outside.jsonl"
    hook = build_hook(dsh_config_path, audit=audit)
    outside = dsh_project.parent / "elsewhere"

    outcome = hook.handle(
        payload(
            "pre-tool-use-edit-block.json",
            dsh_project,
            hook_payload_version="1.0",
            session_cwd=str(outside),
        )
    )

    # 关键：这条结论**不是** allow，而是一个显式的「没治理」——两者的区别就是本次修复的目的。
    assert outcome.exit_code == EXIT_ALLOW
    assert outcome.reason_code == SCOPE_OUTSIDE_REASON

    record = _audit_rows(audit)[0]
    assert record["hook_event"] == "PreToolUse"
    assert record["reason_code"] == SCOPE_OUTSIDE_REASON
    assert record["governed"] is False
    assert record["session_scope"] == "outside_project"
    # 两个事实分开写：会话 cwd 折叠成 <outside-workspace>、项目根渲染成 "."。
    # （审计里不放绝对路径是既有脱敏纪律；要原始路径看 --capture 的载荷。）
    assert record["session_cwd"] == "<outside-workspace>"
    assert record["project_root"] == "."
    assert record["scope_note"]
    # 范围外**没有做判定**：没有 event_id，也没有 violations 一类的判定产物。
    assert "event_id" not in record
    assert "violations" not in record


def test_out_of_scope_post_execute_records_the_scope_reason(dsh_config_path, dsh_project):
    """成对契约：事前判「没管」，事后就不能反过来宣称「验证过」。"""

    audit = dsh_config_path.parent / "scope-outside-post.jsonl"
    hook = build_hook(dsh_config_path, audit=audit)
    outside = dsh_project.parent / "elsewhere"

    # PostToolUse 由 run_hook 分派到事后路径（handle() 是 pre 专用入口）——这里走真分派。
    outcome = run_hook(
        payload(
            "post-tool-use-edit.json",
            dsh_project,
            hook_payload_version="1.0",
            session_cwd=str(outside),
        ),
        config_path=dsh_config_path,
        audit_path=audit,
    )

    assert outcome.exit_code == EXIT_ALLOW
    assert outcome.reason_code == SCOPE_OUTSIDE_POST_REASON
    record = _audit_rows(audit)[0]
    assert record["hook_event"] == "PostToolUse"
    assert record["governed"] is False
    assert record["session_scope"] == "outside_project"
    assert record["session_cwd"] == "<outside-workspace>"
    assert record["project_root"] == "."


def test_scope_outside_and_read_only_degradation_are_different_reason_codes(
    dsh_config_path, dsh_project
):
    """AGENTS 第 50 条：一个 reason_code 只许有一个含义。

    `not_governed` / `post_not_governed` 的原本含义是「只读工具的授权链路显式降级」；
    「会话在受治范围外」是另一件事（这次根本没管），所以它有自己的码。两者一旦共用一个名字，
    按 reason_code 聚合读账本的人就会把「没管」与「管了但降级」读成同一件事——
    这正是本次返工要钉开的东西：**两条记录都必须还在，只是不再同名**。
    """

    outside = dsh_project.parent / "elsewhere"

    scope_pre_audit = dsh_config_path.parent / "codes-scope-pre.jsonl"
    scope_pre = build_hook(dsh_config_path, audit=scope_pre_audit).handle(
        payload(
            "pre-tool-use-edit-block.json",
            dsh_project,
            hook_payload_version="1.0",
            session_cwd=str(outside),
        )
    )

    readonly_audit = dsh_config_path.parent / "codes-readonly.jsonl"
    readonly = build_hook(dsh_config_path, audit=readonly_audit).handle(
        payload("pre-tool-use-read-not-governed.json", dsh_project)
    )

    scope_post_audit = dsh_config_path.parent / "codes-scope-post.jsonl"
    scope_post = run_hook(
        payload(
            "post-tool-use-edit.json",
            dsh_project,
            hook_payload_version="1.0",
            session_cwd=str(outside),
        ),
        config_path=dsh_config_path,
        audit_path=scope_post_audit,
    )

    # 事前：范围外 vs 只读降级——两个含义、两个码。
    assert scope_pre.reason_code == SCOPE_OUTSIDE_REASON
    assert readonly.reason_code == "not_governed"
    assert scope_pre.reason_code != readonly.reason_code
    # 事后：范围外用作用域族自己的事后码，不是只读降级那条。
    assert scope_post.reason_code == SCOPE_OUTSIDE_POST_REASON
    assert scope_post.reason_code != "post_not_governed"

    # 记录也必须是两件事：范围外带作用域事实，只读降级带的是「为什么没进授权链路」。
    assert _audit_rows(scope_pre_audit)[0]["session_scope"] == "outside_project"
    assert "session_scope" not in _audit_rows(readonly_audit)[0]
    assert _audit_rows(readonly_audit)[0]["scope_note"]


def test_in_scope_session_keeps_the_normal_decision(dsh_config_path, dsh_project):
    """同一个会话 cwd = 项目根：结论与第 1 代逐字相同，且**不**多出作用域键。"""

    audit = dsh_config_path.parent / "scope-inside.jsonl"
    hook = build_hook(dsh_config_path, audit=audit)

    outcome = hook.handle(
        payload(
            "pre-tool-use-edit-block.json",
            dsh_project,
            hook_payload_version="1.0",
            session_cwd=str(dsh_project),
        )
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "policy_block"
    record = _audit_rows(audit)[0]
    assert record["governed"] is True
    assert "session_scope" not in record
    assert "session_cwd" not in record


def test_legacy_payload_still_takes_todays_path(dsh_config_path, dsh_project):
    """第 1 代（没有版本键）走今天的路径——这条是「范围内行为不变」的锚点。"""

    audit = dsh_config_path.parent / "scope-legacy.jsonl"
    hook = build_hook(dsh_config_path, audit=audit)

    outcome = hook.handle(payload("pre-tool-use-edit-block.json", dsh_project))

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "policy_block"
    record = _audit_rows(audit)[0]
    assert record["governed"] is True
    assert "session_scope" not in record


def test_second_generation_without_a_session_cwd_fails_closed(dsh_config_path, dsh_project):
    """声明了第 2 代却不给会话 cwd：证明不了范围 → 失败关闭，绝不默认放行。"""

    audit = dsh_config_path.parent / "scope-unprovable.jsonl"
    hook = build_hook(dsh_config_path, audit=audit)

    outcome = hook.handle(
        payload("pre-tool-use-edit-block.json", dsh_project, hook_payload_version="1.0")
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "payload_scope_unprovable"


def test_unknown_payload_version_fails_closed(dsh_config_path, dsh_project):
    """未知协议版本一律拒收（核心层约束 3），不静默降级到第 1 代。"""

    audit = dsh_config_path.parent / "scope-version.jsonl"
    hook = build_hook(dsh_config_path, audit=audit)

    outcome = hook.handle(
        payload(
            "pre-tool-use-edit-block.json",
            dsh_project,
            hook_payload_version="9.9",
            session_cwd=str(dsh_project),
        )
    )

    assert outcome.exit_code == EXIT_BLOCK
    assert outcome.reason_code == "payload_version_unsupported"


# --------------------------------------------------------------------------- 范围外 + 账写不进去
#
# 2026-10-10 真机故障：桥挂在 desktop profile 上之后**每个** GUI 会话都跑 Hook，而 Hook 要往
# **受治项目**的 .policy/audit.jsonl 记账。别的会话（工作区不是受治文件夹）没有那个路径的写权限
# → PermissionError → 失败关闭 → 那个会话整个干不了活（用户要做的对比测试里，第二个工作区
# 不是「不受管」而是「干不了活」）。
#
# 修的是**范围外**这一侧：账写不进去不许拦人，但「这次没管」与「为什么没记上账」都要留下来。
# 范围内一个字不变：账写不进去仍然不许执行。
#
# 「不可写」用**真被 OS 拒**的落点制造——把审计目标做成一个**目录**（append 打不开目录：
# Windows 是 PermissionError、POSIX 是 IsADirectoryError，两个都是 OSError）。这不是打桩：
# 拒绝来自文件系统本身，而且与"目标在沙箱外"是同一类失败。


def _unwritable_ledger(tmp_root: Path) -> Path:
    """一个**真的打不开**的审计目标：目录。"""

    target = tmp_root / "audit-as-directory"
    target.mkdir(exist_ok=True)
    return target


@pytest.fixture()
def fallback_ledger(tmp_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把降级落点指到本次用例自己的目录（落点不是被测行为；写进去仍然是一次真写）。"""

    path = tmp_root / "scope-fallback" / "out-of-scope.jsonl"
    monkeypatch.setattr(hooks_module, "scope_fallback_path", lambda: path)
    return path


def test_out_of_scope_session_survives_an_unwritable_governed_ledger(
    dsh_config_path, dsh_project, tmp_root, fallback_ledger, capsys
):
    """范围外：受治账写不进去**不拦人**，但回退记录与 stderr 机读行都要在。"""

    outside = dsh_project.parent / "elsewhere"
    hook = build_hook(dsh_config_path, audit=_unwritable_ledger(tmp_root))

    outcome = hook.handle(
        payload(
            "pre-tool-use-edit-block.json",
            dsh_project,
            hook_payload_version="1.0",
            session_cwd=str(outside),
        )
    )

    assert outcome.exit_code == EXIT_ALLOW
    assert outcome.reason_code == SCOPE_OUTSIDE_REASON

    line = capsys.readouterr().err.split(SCOPE_FALLBACK_LINE_PREFIX, 1)[1].splitlines()[0]
    parsed = json.loads(line)
    assert parsed["schema_version"] == SCOPE_FALLBACK_SCHEMA_VERSION
    assert parsed["session_scope"] == "outside_project"
    assert parsed["audit_fallback"]

    rows = _audit_rows(fallback_ledger)
    assert rows, "范围外不能静默跳过：受治账写不进去时必须留下回退记录"
    assert rows[-1]["reason_code"] == SCOPE_OUTSIDE_REASON
    assert rows[-1]["governed"] is False
    # 「记不到账」这件事本身必须可读：回退记录带原因与它本来该去哪儿。
    assert rows[-1]["audit_fallback"] is True
    assert rows[-1]["audit_fallback_reason"]
    assert rows[-1]["audit_fallback_target"] is not None


def test_run_hook_out_of_scope_survives_the_ledger_derivation_write(
    dsh_config_path, dsh_project, tmp_root, fallback_ledger
):
    """真分派路径：N21 那条「台账派生」元信息写不进去时，范围外**仍然放行**。

    这条正是本次故障的翻车点：元信息写在判定**之后**，它一抛就把一次本该放行的调用翻成了
    startup_error——于是整段会话连一次工具调用都做不成。事后事务不许反过来改写判定。
    """

    outside = dsh_project.parent / "elsewhere"
    outcome = run_hook(
        payload(
            "pre-tool-use-edit-block.json",
            dsh_project,
            hook_payload_version="1.0",
            session_cwd=str(outside),
        ),
        config_path=dsh_config_path,
        audit_path=_unwritable_ledger(tmp_root),
        hooks_config_path=HOOKS_CONFIG,
    )

    assert outcome.exit_code == EXIT_ALLOW
    assert outcome.reason_code == SCOPE_OUTSIDE_REASON
    assert _audit_rows(fallback_ledger), "元信息写不进去也不能静默：痕迹要落到回退账"


def test_scope_is_decided_before_the_ledger_never_the_other_way_round(
    dsh_config_path, dsh_project, tmp_root
):
    """④ 同一条「账写不进去」的事实，在两个范围上得到**相反**的后果。

    先判范围、再动账。反过来说：若让"账写不进去"本身成为放行判据，范围内的会话只要把账弄坏
    就能逃逸——那是把失败关闭反过来用。
    """

    outside = dsh_project.parent / "elsewhere"

    out_side = build_hook(dsh_config_path, audit=_unwritable_ledger(tmp_root)).handle(
        payload(
            "pre-tool-use-edit-block.json",
            dsh_project,
            hook_payload_version="1.0",
            session_cwd=str(outside),
        )
    )
    assert out_side.exit_code == EXIT_ALLOW

    # 范围内：连一条**本来会放行**的改动也不许执行（账写不进去 = 失败关闭）。
    in_side = build_hook(dsh_config_path, audit=_unwritable_ledger(tmp_root)).handle(
        payload(
            "pre-tool-use-edit-allow.json",
            dsh_project,
            hook_payload_version="1.0",
            session_cwd=str(dsh_project),
        )
    )
    assert in_side.exit_code == EXIT_BLOCK
    assert in_side.reason_code == "config_error"
