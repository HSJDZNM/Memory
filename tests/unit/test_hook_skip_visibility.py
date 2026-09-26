"""G3 跳过可见性 / G11 注入留痕：审计字段单元测试。

两条修复都落在**审计记录**上，所以这里既做确定性单测（直接调用可见性计算，不依赖工具注册表），
也用真实 Hook 调用写出真实审计再读回来断言：

- G3：effective_rule_count / skipped_rule_count / skipped_reason 必须能让读者区分
  "这条规则查了并通过"与"这条规则被跳过"；跳过绝不等于通过；
- G11：会进入 AI 上下文的项目约定文档（AGENTS.md / CLAUDE.md）的来源路径 + sha256
  在会话起点附近留痕一次，并如实标注这是近似而非真实注入时刻；
- 同时守住"只增不改"：改动前就有的审计字段一个都不能少、语义不能变。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from conftest import REPO_ROOT, dsh_event, make_checker_rule, write_dsh_config

from adapters.dsh.adapter import load_config
from adapters.dsh.hooks import (
    AUDIT_SCHEMA_VERSION,
    EXIT_ALLOW,
    EXIT_BLOCK,
    AuditLedger,
    DshPreExecuteHook,
    run_hook,
)
from policy.checkers import CONTEXT_CHECKERS
from policy.models import Decision, RuleSet, SkippedRule, ValidationResult

# 改动前就存在的审计字段（G3/G11 只能往里加，不能删或改语义）。
EXISTING_GOVERNED_FIELDS = frozenset(
    {
        "audit_schema_version",
        "timestamp",
        "agent",
        "agent_version",
        "reason_code",
        "exit_code",
        "executed",
        "elapsed_ms",
        "rule_set_hash",
        "session_id",
        "tool",
        "cwd_scope",
        "governed",
        "event_id",
        "request_id",
        "trace_id",
        "operation",
        "file",
        "layer",
        "language",
        "dependencies",
        "payload_digest",
        "payload_fields",
        "matched_rules",
        "skipped_rules",
        "decision",
        "required_action",
        "execution",
    }
)


def records(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def payload(name: str, project_root: Path, **overrides: object) -> dict[str, object]:
    return dsh_event(name, cwd=str(project_root), **overrides)


def last_decision(path: Path) -> dict:
    """最后一条**判定**记录。

    不能直接取最后一行：G11 的注入留痕按既有约定排在判定记录之后（首行仍是本次判定，
    留痕追加在尾部），所以取末行会取到留痕。
    """

    for record in reversed(records(path)):
        if "decision" in record:
            return record
    raise AssertionError(f"审计里没有判定记录：{path}")


def visibility_hook(dsh_config_path) -> DshPreExecuteHook:
    """只用来算可见性的 Hook：规则集是合成的，绝不依赖工具注册表是否可用。"""

    rules = RuleSet(
        rules=(
            make_checker_rule("ARCH-001", checker="forbidden_dependency"),
            make_checker_rule(
                "STYLE-001",
                checker="style_lint",
                body={"style_lint": {"tool": "ruff", "codes": ["E501"]}},
            ),
            make_checker_rule(
                "DOC-001",
                checker="missing_docstring",
                body={"missing_docstring": {"targets": ["module"]}},
            ),
        ),
        source_paths=(),
    )
    return DshPreExecuteHook(config=load_config(dsh_config_path), rules=rules)


# --------------------------------------------------------------------------- G3（确定性）


def test_skip_reason_groups_by_checker_and_never_counts_as_checked(dsh_config_path):
    hook = visibility_hook(dsh_config_path)
    decision = ValidationResult(
        decision=Decision.ALLOW,
        request_id="req-1",
        skipped_rules=(
            SkippedRule(rule_id="STYLE-001@1", reasons=("需要验证器证据",)),
            SkippedRule(rule_id="DOC-001@1", reasons=("需要验证器证据",)),
            # 规则集里没有的规则 ID 不能静默消失
            SkippedRule(rule_id="GONE-999@1", reasons=("未知",)),
        ),
    )

    visibility = hook.rule_visibility(decision)

    assert visibility["rule_count"] == 3
    assert visibility["effective_rule_count"] == 0
    assert visibility["skipped_rule_count"] == 3
    assert visibility["skipped_reason"] == {
        "missing_docstring": 1,
        "not_in_rule_set": 1,
        "style_lint": 1,
    }
    assert visibility["skipped_rule_ids_unknown"] == ["GONE-999@1"]
    # pre-execute 路径只做文本类 checker：能力边界与"这条规则为什么没查"都要写清楚
    assert visibility["checker_scope"] == sorted(CONTEXT_CHECKERS)
    assert "只做文本类 checker" in visibility["checker_scope_note"]
    assert "跳过不等于通过" in visibility["checker_scope_note"]


def test_a_rule_that_was_actually_checked_is_counted_as_effective(dsh_config_path):
    hook = visibility_hook(dsh_config_path)
    decision = ValidationResult(
        decision=Decision.ALLOW,
        request_id="req-1",
        matched_rules=(),
        skipped_rules=(SkippedRule(rule_id="STYLE-001@1"),),
    )

    visibility = hook.rule_visibility(decision)

    assert visibility["rule_count"] == 3
    assert visibility["effective_rule_count"] == 2
    assert visibility["skipped_rule_count"] == 1
    assert visibility["skipped_reason"] == {"style_lint": 1}


def test_actions_without_a_file_dimension_do_not_pretend_the_rules_ran(dsh_config_path):
    hook = visibility_hook(dsh_config_path)

    visibility = hook.rule_visibility_not_applicable()

    assert visibility["rule_count"] == 3
    assert visibility["effective_rule_count"] == 0
    assert visibility["skipped_rule_count"] == 3
    assert visibility["skipped_reason"] == {"phase1_not_applicable": 3}
    assert "Phase 1 规则引擎不适用" in visibility["checker_scope_note"]


# --------------------------------------------------------------------------- G3（真实产物）


def test_the_audit_of_an_allowed_edit_reports_the_split(dsh_config_path, dsh_project):
    audit = dsh_project.parent / "audit.jsonl"

    outcome = run_hook(
        payload("pre-tool-use-edit-allow.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=audit,
    )

    assert outcome.exit_code == EXIT_ALLOW, outcome.stderr
    record = last_decision(audit)
    assert record["decision"] == "allow"
    # 两个数必须相加等于总数：跳过的那部分再也不能藏在 allow 后面
    assert record["rule_count"] > record["effective_rule_count"] > 0
    assert record["effective_rule_count"] + record["skipped_rule_count"] == record["rule_count"]
    assert sum(record["skipped_reason"].values()) == record["skipped_rule_count"]
    # 证据类 checker 在这次判定里一条都没查（pre-execute 路径没有证据提供者）
    assert "style_lint" in record["skipped_reason"]
    assert record["checker_scope"] == sorted(CONTEXT_CHECKERS)
    assert record["skipped_rules"]  # 既有字段照旧


def test_the_audit_of_a_blocked_edit_reports_the_split(dsh_config_path, dsh_project):
    audit = dsh_project.parent / "audit.jsonl"

    outcome = run_hook(
        payload("pre-tool-use-edit-block.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=audit,
    )

    assert outcome.exit_code == EXIT_BLOCK
    record = last_decision(audit)
    assert record["decision"] == "block"
    assert record["effective_rule_count"] + record["skipped_rule_count"] == record["rule_count"]
    assert "ARCH-001@1" in record["matched_rules"]


class _Risk:
    value = "destructive_write"


class _FakeSpec:
    name = "pwsh"
    id = "exec.pwsh"
    risk = _Risk()
    driver = "none"
    post_checks: tuple = ()


class _FakeRequest:
    action_hash = "sha256:" + "0" * 64
    action_id = "sess-demo-0001:call-pwsh"
    tool_id = "exec.pwsh"
    risk = _Risk()


class _FakeDecision:
    decision = Decision.ALLOW
    grant = None
    checks: tuple = ()


class _FakeOutcome:
    decision = _FakeDecision()


class _AllowAllBridge:
    """最小假桥：驱动"没有文件维度的受控动作"这一段审计分支。

    为什么需要它：真实链路里让 pwsh 放行需要一份与 action_hash 绑定的人工审批文件
    （那是 Phase 4 集成测试的职责，且本文件不该依赖审批文件的时效与编号空间）。
    这里只替掉"授权链路"，判定、审计与可见性字段仍然是真实实现写出来的。
    """

    def spec_for(self, tool_name):
        return _FakeSpec()

    def build_request(self, **_kwargs):
        return _FakeRequest()

    def pre(self, _request, **_kwargs):
        return _FakeOutcome()


def test_the_audit_of_an_execute_action_says_the_rules_did_not_run(dsh_config_path, dsh_project):
    audit = dsh_project.parent / "audit.jsonl"
    hook = DshPreExecuteHook(
        config=load_config(dsh_config_path),
        rules=RuleSet(rules=(make_checker_rule("ARCH-001"),), source_paths=()),
        ledger=AuditLedger(audit),
        bridge=_AllowAllBridge(),
    )

    outcome = hook.handle(payload("pre-tool-use-pwsh-execute.json", dsh_project))

    assert outcome.exit_code == EXIT_ALLOW, outcome.stderr
    record = records(audit)[0]
    assert record["scope_note"].startswith("Phase 4 受控执行")
    assert record["effective_rule_count"] == 0
    assert record["skipped_rule_count"] == record["rule_count"] == 1
    assert record["skipped_reason"] == {"phase1_not_applicable": 1}
    assert "Phase 1 规则引擎不适用" in record["checker_scope_note"]


def test_existing_audit_fields_are_kept_unchanged(tmp_root, dsh_project):
    """只增不改：改动前就有的字段必须原样存在，schema 版本不动。"""

    config_path = write_dsh_config(
        tmp_root / "config" / "with-trace.yaml",
        project_root=dsh_project,
        rules=REPO_ROOT / "policies",
        trace_id="trace-demo-1",
    )
    audit = dsh_project.parent / "audit.jsonl"

    run_hook(
        payload("pre-tool-use-edit-allow.json", dsh_project),
        config_path=config_path,
        audit_path=audit,
    )

    record = last_decision(audit)
    missing = EXISTING_GOVERNED_FIELDS - set(record)
    # _audit 的既有行为是"取值为 None 就不写"（required_action 在 allow 时就是 None），
    # 这不是本次改动引入的，所以只允许这一个字段缺席。
    assert missing <= {"required_action"}, sorted(missing)
    assert record["trace_id"] == "trace-demo-1"
    assert "required_action" not in record
    assert record["audit_schema_version"] == AUDIT_SCHEMA_VERSION == "1.0"
    assert record["agent"] == "dsh"
    assert record["rule_set_hash"].startswith("sha256:")
    assert record["payload_digest"].startswith("sha256:")
    # 既有字段的取值口径不变：event_id 仍是 session:call，skipped_rules 仍是 rule_id 列表
    assert record["event_id"] == "sess-demo-0001:call-edit-allow"
    assert isinstance(record["skipped_rules"], list)
    assert all(isinstance(item, str) for item in record["skipped_rules"])
    # 新增的成对契约字段
    assert record["hook_event"] == "PreToolUse"
    assert record["action_id"] == "sess-demo-0001:call-edit-allow"
    assert record["tool_use_id"] == "call-edit-allow"


# --------------------------------------------------------------------------- G11


def test_the_session_records_which_context_documents_are_in_play(dsh_config_path, dsh_project):
    agents = dsh_project / "AGENTS.md"
    agents.write_text(
        "# 项目约定" + chr(10) + "- 分层：controller -> service -> repository" + chr(10),
        encoding="utf-8",
        newline="",
    )
    audit = dsh_project.parent / "audit.jsonl"

    # 只读工具：这条用例只关心留痕，不引入工具注册表这一层依赖
    outcome = run_hook(
        payload("pre-tool-use-read-not-governed.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=audit,
    )

    assert outcome.exit_code == EXIT_ALLOW, outcome.stderr
    entries = records(audit)
    injection = [item for item in entries if item.get("reason_code") == "context_injection"]
    assert len(injection) == 1, entries
    detail = injection[0]["context_injection"]
    # 如实标注这是近似：dsh 的 SessionStart 没有接到本 Hook
    assert detail["approximate"] is True
    documents = {item["path"]: item for item in detail["documents"]}
    assert set(documents) == {"AGENTS.md", "CLAUDE.md"}
    assert documents["AGENTS.md"]["present"] is True
    assert documents["AGENTS.md"]["sha256"] == (
        "sha256:" + hashlib.sha256(agents.read_bytes()).hexdigest()
    )
    assert documents["AGENTS.md"]["bytes"] == agents.stat().st_size
    # 不存在的约定文档也要显式写 present=False，而不是静默省略成"没有约定"
    assert documents["CLAUDE.md"] == {"path": "CLAUDE.md", "present": False}
    assert "近似" in detail["note"]
    # 既有约定：第一条记录是本次判定（既有消费方按首行读审计），留痕只能排在后面
    assert entries[0].get("reason_code") != "context_injection"


def test_the_injection_record_is_written_once_per_session(dsh_config_path, dsh_project):
    audit = dsh_project.parent / "audit.jsonl"

    first = run_hook(
        payload("pre-tool-use-read-not-governed.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=audit,
    )
    second = run_hook(
        payload("pre-tool-use-read-not-governed.json", dsh_project, tool_use_id="call-read-2"),
        config_path=dsh_config_path,
        audit_path=audit,
    )

    assert first.exit_code == EXIT_ALLOW, first.stderr
    assert second.exit_code == EXIT_ALLOW, second.stderr
    injection = [item for item in records(audit) if item.get("reason_code") == "context_injection"]
    assert len(injection) == 1, records(audit)


# --------------------------------------------------------------------------- 事后阶段记录


def test_post_stage_records_are_distinguishable_from_pre_records(dsh_config_path, dsh_project):
    """事后记录必须能被区分：带 hook_event=PostToolUse 与 action_id，且不冒充 governed。

    为什么"不冒充 governed"是契约：tools/dsh_sandbox_loop.py 用 last_governed() 取
    "最后一次受治理的 pre 记录"来判断放行/阻断；事后记录若带 governed=True，
    它会取到事后记录，既有闭环的断言就会被改变语义。
    """

    audit = dsh_project.parent / "audit.jsonl"

    outcome = run_hook(
        payload("post-tool-use-edit.json", dsh_project),
        config_path=dsh_config_path,
        audit_path=audit,
    )

    entry = records(audit)[-1]
    assert entry["hook_event"] == "PostToolUse"
    assert entry["action_id"] == "sess-demo-0001:call-post"
    assert entry["tool_use_id"] == "call-post"
    assert entry["reason_code"] == outcome.reason_code
    assert "governed" not in entry
    # 事后记录不能顶替 pre 记录的幂等键（否则重放会被判成"参数被改过"）
    assert "event_id" not in entry
