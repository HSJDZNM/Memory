"""审计链与台账单元测试：链完整性、脱敏、注入安全、限流窗口与授权单次使用。

对应 Phase 4 文档"日志失效与安全"一节：换行 / 控制字符 / 超长参数不得造成注入，
密钥与绝对路径必须被脱敏，日志不可写与链被改动的行为必须可判定。
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from enforcement.audit import (
    AuditChain,
    FileAuditSink,
    NullAuditSink,
    redact_text,
    sanitize_payload,
)
from enforcement.ledger import EnforcementLedger
from enforcement.models import (
    AuditError,
    AuditRecord,
    AuditStage,
    AuthorizationGrant,
    GrantError,
    LedgerError,
    RollbackMode,
    parse_audit_record,
    to_timestamp,
    utc_now,
)
from enforcement.trace import explain, load_trace, verify_chain


def sink_for(tmp_root, name="audit.jsonl") -> FileAuditSink:
    return FileAuditSink(tmp_root / name, workspace=tmp_root)


# --------------------------------------------------------------------------- 脱敏


def test_redaction_removes_secrets_and_absolute_paths(tmp_root):
    text = (
        "key=sk-live0123456789abcdef token: ghp_ABCDEFGHIJKLMNOP "  # secret-scan: allow（合成值，用于验证脱敏与拒绝逻辑）
        "path C:\\Users\\someone\\secret\\file.py and /home/user/x"
    )
    redacted = redact_text(text, workspace=tmp_root)

    assert "sk-live" not in redacted
    assert "ghp_" not in redacted
    assert "C:\\Users" not in redacted
    assert "<redacted-secret>" in redacted


def test_bearer_tokens_and_posix_paths_are_redacted(tmp_root):
    """复核 D4：Authorization: Bearer <token> 必须整体吃掉，POSIX 绝对路径也要脱敏。"""

    text = (
        'curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def" '  # secret-scan: allow（合成值，用于验证脱敏与拒绝逻辑）
        "http://example.invalid ; cat /home/alice/.ssh/id_rsa ; token=abc123 "
        "C:/Users/bob/secret.py"
    )
    redacted = redact_text(text, workspace=tmp_root)

    assert "eyJhbGciOiJIUzI1NiJ9" not in redacted
    assert "abc123" not in redacted
    assert "/home/alice" not in redacted
    assert "C:/Users/bob" not in redacted
    assert "<redacted-secret>" in redacted and "<abs>" in redacted


def test_control_characters_are_escaped_so_a_record_stays_one_line(tmp_root):
    sink = sink_for(tmp_root)
    payload = {"detail": "line1\nline2\r\nline3\x00\x1b[31mred"}
    sink.append(AuditStage.REQUEST, payload=payload)

    text = (tmp_root / "audit.jsonl").read_text(encoding="utf-8")
    assert text.count("\n") == 1  # 只有记录自身的换行
    record = json.loads(text.strip())
    assert "\\x00" in record["payload"]["detail"]
    assert "\\x0d" in record["payload"]["detail"]  # CR 也被转义：日志行数不因载荷而变


def test_long_payloads_are_truncated_instead_of_exploding(tmp_root):
    sink = sink_for(tmp_root)
    record = sink.append(AuditStage.REQUEST, payload={"blob": "x" * 5000})

    assert len(record.payload["blob"]) <= 2000
    assert record.payload["blob"].endswith("...[truncated]")


def test_payload_container_limits_are_applied(tmp_root):
    payload = {f"k{index}": index for index in range(100)}
    sanitized = sanitize_payload(payload, workspace=tmp_root)

    assert len(sanitized) <= 64
    nested = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": 1}}}}}}}}
    assert sanitize_payload(nested, workspace=tmp_root)


def test_oversized_record_fails_closed(tmp_root):
    sink = FileAuditSink(tmp_root / "audit.jsonl", max_record_bytes=200)

    with pytest.raises(AuditError) as error:
        sink.append(AuditStage.REQUEST, payload={"blob": "y" * 5000})
    assert "上限" in str(error.value)
    assert not (tmp_root / "audit.jsonl").exists()


def test_null_sink_refuses_to_pretend():
    with pytest.raises(AuditError):
        NullAuditSink().append(AuditStage.REQUEST, payload={})


# --------------------------------------------------------------------------- 链完整性


def test_chain_links_records_and_verifies(tmp_root):
    sink = sink_for(tmp_root)
    first = sink.append(AuditStage.REQUEST, payload={"a": 1})
    second = sink.append(AuditStage.PRE_DECISION, payload={"b": 2})

    assert first.sequence == 1 and first.prev_digest == ""
    assert second.sequence == 2 and second.prev_digest == first.digest
    assert sink.verify() == ()
    assert sink.final_digest() == second.digest


def test_tampering_with_a_record_is_detected(tmp_root):
    sink = sink_for(tmp_root)
    sink.append(AuditStage.REQUEST, payload={"a": 1})
    sink.append(AuditStage.FINAL_DECISION, payload={"outcome": "delivered"})

    path = tmp_root / "audit.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["payload"]["a"] = 2
    lines[0] = json.dumps(record, ensure_ascii=False, sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    issues = sink.verify()
    assert issues and "摘要与内容不一致" in issues[0]


def test_deleting_a_record_breaks_the_chain(tmp_root):
    sink = sink_for(tmp_root)
    sink.append(AuditStage.REQUEST, payload={"a": 1})
    sink.append(AuditStage.PRE_DECISION, payload={"b": 2})
    sink.append(AuditStage.FINAL_DECISION, payload={"c": 3})

    path = tmp_root / "audit.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")

    issues = sink.verify()
    assert any("序号" in issue for issue in issues)


def test_unknown_protocol_version_is_rejected():
    with pytest.raises(AuditError):
        parse_audit_record({"schema_version": "9.9", "sequence": 1, "stage": "request"})


def test_foreign_records_are_counted_not_silently_adopted(tmp_root):
    path = tmp_root / "audit.jsonl"
    path.write_text(
        json.dumps({"decision": "block", "file": "src/x.py"}) + "\n", encoding="utf-8"
    )
    sink = FileAuditSink(path, workspace=tmp_root)
    sink.append(AuditStage.REQUEST, payload={"a": 1})

    assert sink.foreign_records() == 1
    assert len(sink.chain_records()) == 1
    assert sink.verify() == ()


def test_trace_replay_orders_the_chain_and_requires_a_final_decision(tmp_root):
    sink = sink_for(tmp_root)
    for stage in (
        AuditStage.REQUEST,
        AuditStage.RETRIEVAL,
        AuditStage.PROPOSAL,
        AuditStage.ACTION_REQUEST,
        AuditStage.PRE_DECISION,
        AuditStage.EXECUTION,
        AuditStage.POST_EVIDENCE,
    ):
        sink.append(stage, payload={"stage": stage.value}, action_id="act-1", trace_id="trace-1")

    report = load_trace(tmp_root / "audit.jsonl", action_id="act-1")
    assert not report.ok
    assert any("终态" in issue for issue in report.issues)
    assert [entry.stage for entry in report.entries][:3] == [
        AuditStage.REQUEST,
        AuditStage.RETRIEVAL,
        AuditStage.PROPOSAL,
    ]

    sink.append(
        AuditStage.FINAL_DECISION,
        payload={"outcome": "delivered", "reason_code": "allow"},
        action_id="act-1",
        trace_id="trace-1",
    )
    report = load_trace(tmp_root / "audit.jsonl", action_id="act-1")
    assert report.ok
    assert report.has_final
    assert "final_decision" in explain(report)
    assert verify_chain(report.records) == ()


def test_execution_without_a_pre_decision_is_reported(tmp_root):
    sink = sink_for(tmp_root)
    sink.append(AuditStage.EXECUTION, payload={"status": "executed"}, action_id="act-9")

    issues = verify_chain(sink.chain_records())
    assert any("没有决策就不能有执行" in issue for issue in issues)


def test_refused_execution_without_a_decision_is_not_flagged(tmp_root):
    """refused 恰恰是"没有决策/决策属于别的动作"时的合法留痕，不能被当成链不完整。"""

    sink = sink_for(tmp_root)
    sink.append(
        AuditStage.EXECUTION,
        payload={"status": "refused", "reason_code": "grant_invalid"},
        action_id="act-10",
    )
    sink.append(
        AuditStage.FINAL_DECISION,
        payload={"outcome": "blocked", "reason_code": "grant_invalid"},
        action_id="act-10",
    )

    assert verify_chain(sink.chain_records()) == ()


def test_stage_order_regression_is_reported(tmp_root):
    sink = sink_for(tmp_root)
    sink.append(AuditStage.FINAL_DECISION, payload={"outcome": "delivered"}, action_id="act-1")
    sink.append(AuditStage.REQUEST, payload={}, action_id="act-1")

    issues = verify_chain(sink.chain_records())
    assert any("阶段顺序倒退" in issue for issue in issues)


# --------------------------------------------------------------------------- 台账


def test_claim_is_first_writer_wins(tmp_root):
    ledger = EnforcementLedger(tmp_root / "ledger.jsonl")
    first = ledger.claim(action_id="a-1", tool_id="fs.edit", action_hash="sha256:h", claim_id="c-1")
    second = ledger.claim(action_id="a-1", tool_id="fs.edit", action_hash="sha256:h", claim_id="c-2")

    assert first.claimed is True
    assert second.claimed is False
    assert second.reason == "action_replay"

    third = ledger.claim(action_id="a-1", tool_id="fs.edit", action_hash="sha256:other", claim_id="c-3")
    assert third.claimed is False and third.reason == "action_id_reuse"


def test_grant_is_single_use(tmp_root):
    ledger = EnforcementLedger(tmp_root / "ledger.jsonl")
    now = utc_now()
    grant = AuthorizationGrant(
        grant_id="grant-1",
        action_id="a-1",
        action_hash="sha256:h",
        tool_id="fs.edit",
        tool_schema_hash="sha256:s",
        subject="local-user",
        permissions=("repo.write",),
        risk="reversible_write",
        issued_at=now,
        expires_at=now + timedelta(seconds=60),
        nonce="n-1",
    )
    ledger.record_grant(grant)
    ledger.consume_grant(grant)

    assert ledger.grant_used("grant-1") is True
    with pytest.raises(GrantError):
        ledger.consume_grant(grant)


def test_rate_limit_windows_count_only_recent_records(tmp_root):
    ledger = EnforcementLedger(tmp_root / "ledger.jsonl")
    ledger.append({"kind": "pre_decision", "limit_key": "local-user|fs.edit"})
    ledger.append({"kind": "pre_decision", "limit_key": "local-user|fs.edit"})

    assert (
        ledger.count_since(
            kind="pre_decision", key_field="limit_key", key_value="local-user|fs.edit", window_seconds=60
        )
        == 2
    )
    assert (
        ledger.count_since(
            kind="pre_decision", key_field="limit_key", key_value="other|fs.edit", window_seconds=60
        )
        == 0
    )
    # 时间窗口之外的记录不计数
    assert (
        ledger.count_since(
            kind="pre_decision",
            key_field="limit_key",
            key_value="local-user|fs.edit",
            window_seconds=1,
            now=utc_now() + timedelta(seconds=120),
        )
        == 0
    )


def test_ledger_records_reject_malformed_or_foreign_lines(tmp_root):
    path = tmp_root / "ledger.jsonl"
    path.write_text("not json\n" + json.dumps({"kind": "other"}) + "\n", encoding="utf-8")
    ledger = EnforcementLedger(path)
    with pytest.raises(LedgerError):
        ledger.records()


def test_ledger_records_are_versioned(tmp_root):
    path = tmp_root / "ledger.jsonl"
    path.write_text(json.dumps({"kind": "other"}) + "\n", encoding="utf-8")
    with pytest.raises(LedgerError):
        EnforcementLedger(path).records()


def test_broken_ledger_path_fails_closed(tmp_root):
    directory = tmp_root / "as-directory"
    directory.mkdir()
    ledger = EnforcementLedger(directory)

    with pytest.raises(LedgerError):
        ledger.append({"kind": "x"})


def test_audit_chain_helper_builds_expected_sequences(tmp_root):
    record = AuditChain.next_record(
        [],
        stage=AuditStage.REQUEST,
        payload={"a": 1},
        workspace=tmp_root,
    )
    assert record.sequence == 1 and record.prev_digest == ""
    assert isinstance(record, AuditRecord)
    assert record.digest == record.compute_digest()
    assert to_timestamp(record.recorded_at).endswith("Z")
