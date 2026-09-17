"""Phase 1 决策协议契约测试：固定 JSON 快照 + 版本消费规则。

快照是"协议不许悄悄变"的守门人：改了字段名或语义，这里必须先失败，
然后由提交者显式更新快照并在文档里说明兼容性（见 tests/fixtures/README.md）。

更新快照（只在确实要改协议时执行）：

    $env:POLICY_UPDATE_SNAPSHOTS = "1"; python -m pytest tests/contract -q
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from policy.engine import evaluate
from policy.models import (
    SCHEMA_VERSION,
    Decision,
    Evidence,
    ProtocolError,
    RequiredAction,
    RuleSet,
    SkippedRule,
    ValidationResult,
    Violation,
    parse_decision,
)

from conftest import FIXTURES_DIR, make_context, make_rule

pytestmark = pytest.mark.contract

SNAPSHOT_DIR = FIXTURES_DIR / "decisions"
UPDATE = os.environ.get("POLICY_UPDATE_SNAPSHOTS") == "1"

# 快照用的规则集固定在测试里：哈希不随仓库 policies/ 变化而变化。
SNAPSHOT_RULES = RuleSet(
    rules=(
        make_rule("ARCH-001", scope={"language": "python", "layer": "controller"}),
        make_rule(
            "CODING-002",
            scope={"layer": ["controller", "service"]},
            severity="warning",
            forbidden=("logging",),
        ),
        make_rule(
            "SEC-003",
            scope={"operation": "execute"},
            severity="critical",
            forbidden=("subprocess",),
        ),
        make_rule(
            "ARCH-004",
            scope={"layer": "controller", "operation": "delete"},
            forbidden=("migrations",),
            requires_approval=True,
        ),
    )
)


def case_context(**overrides: object):
    payload: dict[str, object] = {
        "request_id": "req-snapshot",
        "file": "src/order/controller.py",
        "layer": "controller",
        "language": "python",
        "trace_id": "trace-snapshot",
    }
    payload.update(overrides)
    return make_context(**payload)


CASES = {
    "allow": lambda: evaluate(SNAPSHOT_RULES, case_context(dependencies=["service"])),
    "warning": lambda: evaluate(
        SNAPSHOT_RULES, case_context(dependencies=["service", "logging"])
    ),
    "block": lambda: evaluate(
        SNAPSHOT_RULES, case_context(dependencies=["repository", "subprocess"])
    ),
    "approval": lambda: evaluate(
        SNAPSHOT_RULES, case_context(operation="delete", dependencies=["service"])
    ),
}


def snapshot_path(name: str) -> Path:
    return SNAPSHOT_DIR / f"{name}.json"


def read_snapshot(name: str) -> dict:
    return json.loads(snapshot_path(name).read_text(encoding="utf-8"))


def write_snapshot(name: str, payload: dict) -> None:
    snapshot_path(name).parent.mkdir(parents=True, exist_ok=True)
    snapshot_path(name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )


@pytest.mark.parametrize("name", sorted(CASES))
def test_decision_snapshot_is_unchanged(name: str) -> None:
    payload = CASES[name]().to_decision_dict()

    if UPDATE:
        write_snapshot(name, payload)
        pytest.skip(f"已更新快照 {name}.json")

    assert read_snapshot(name) == payload


@pytest.mark.parametrize("name", sorted(CASES))
def test_snapshot_round_trips_through_protocol(name: str) -> None:
    parsed = parse_decision(read_snapshot(name))
    recomputed = CASES[name]()

    assert parsed.model_dump() == recomputed.model_dump()
    assert parsed.to_decision_dict() == read_snapshot(name)


def test_required_snapshots_exist() -> None:
    """测试策略要求 allow / warning / block 三个结果各有一份固定快照。"""

    for name in ("allow", "warning", "block", "approval"):
        assert snapshot_path(name).is_file(), f"缺少协议快照 {name}.json"


def test_snapshot_cases_cover_all_three_decisions() -> None:
    decisions = {name: CASES[name]().decision for name in CASES}

    assert decisions["allow"] is Decision.ALLOW
    assert decisions["warning"] is Decision.ALLOW_WITH_WARNINGS
    assert decisions["block"] is Decision.BLOCK
    assert decisions["approval"] is Decision.BLOCK


def test_snapshot_documents_skip_reasons_and_approval() -> None:
    allow = read_snapshot("allow")
    approval = read_snapshot("approval")

    assert allow["schema_version"] == SCHEMA_VERSION
    assert allow["required_action"] is None
    assert allow["violations"] == []
    assert allow["matched_rules"] == ["ARCH-001@1", "CODING-002@1"]
    assert allow["skipped_rules"] == [
        {"rule_id": "ARCH-004@1", "reasons": ["operation <missing> != delete"]},
        {"rule_id": "SEC-003@1", "reasons": ["operation <missing> != execute"]},
    ]
    assert approval["decision"] == "block"
    assert approval["required_action"] == "approval"
    assert approval["violations"] == []
    assert approval["matched_rules"] == [
        "ARCH-001@1",
        "ARCH-004@1",
        "CODING-002@1",
    ]


def test_unsupported_schema_version_is_refused() -> None:
    payload = read_snapshot("block")
    payload["schema_version"] = "2.0"

    with pytest.raises(ProtocolError) as error:
        parse_decision(payload)

    assert "2.0" in str(error.value)
    assert "拒绝消费" in str(error.value)


def test_missing_schema_version_is_refused() -> None:
    payload = read_snapshot("block")
    payload.pop("schema_version")

    with pytest.raises(ProtocolError):
        parse_decision(payload)


def test_unknown_decision_value_is_refused() -> None:
    payload = read_snapshot("block")
    payload["decision"] = "maybe"

    with pytest.raises(ProtocolError):
        parse_decision(payload)


def test_unknown_required_action_is_refused() -> None:
    payload = read_snapshot("approval")
    payload["required_action"] = "auto_merge"

    with pytest.raises(ProtocolError):
        parse_decision(payload)


def test_non_mapping_payload_is_refused() -> None:
    with pytest.raises(ProtocolError):
        parse_decision(["not", "a", "mapping"])  # type: ignore[arg-type]


def test_protocol_version_is_reported_in_the_payload() -> None:
    payload = read_snapshot("allow")

    assert payload["policy_version"] == "phase-1"
    assert payload["request_id"] == "req-snapshot"
    assert payload["trace_id"] == "trace-snapshot"
    assert payload["rule_set_hash"] == SNAPSHOT_RULES.identity


def test_evidence_payload_keeps_optional_fields_when_present() -> None:
    result = ValidationResult(
        decision=Decision.BLOCK,
        request_id="req-1",
        violations=(
            Violation(
                rule_id="ARCH-001",
                rule_version=1,
                severity="critical",
                message="测试违规",
                evidence=Evidence(
                    kind="dependency",
                    subject="src/order/controller.py",
                    value="repository",
                    file="src/order/controller.py",
                    line=12,
                    detail="layer=controller 直接依赖 repository",
                ),
            ),
        ),
        skipped_rules=(SkippedRule(rule_id="ARCH-002@1", reasons=("layer controller != service",)),),
    )

    payload = result.to_decision_dict()
    evidence = payload["violations"][0]["evidence"]

    assert evidence == {
        "kind": "dependency",
        "subject": "src/order/controller.py",
        "value": "repository",
        "file": "src/order/controller.py",
        "line": 12,
        "detail": "layer=controller 直接依赖 repository",
    }
    assert payload["skipped_rules"] == [
        {"rule_id": "ARCH-002@1", "reasons": ["layer controller != service"]}
    ]
    assert parse_decision(payload).model_dump() == result.model_dump()


def test_optional_evidence_fields_are_omitted_when_absent() -> None:
    result = ValidationResult(
        decision=Decision.BLOCK,
        request_id="req-1",
        violations=(
            Violation(
                rule_id="ARCH-001",
                rule_version=1,
                severity="error",
                message="测试违规",
                evidence=Evidence(kind="dependency", subject="a.py", value="repository"),
            ),
        ),
    )

    assert set(result.to_decision_dict()["violations"][0]["evidence"]) == {
        "kind",
        "subject",
        "value",
    }


@pytest.mark.parametrize("name", sorted(CASES))
def test_decision_dict_and_model_are_lossless(name: str) -> None:
    result = CASES[name]()

    assert parse_decision(result.to_decision_dict()).model_dump() == result.model_dump()


def test_required_action_enum_has_a_single_authorised_value() -> None:
    assert [item.value for item in RequiredAction] == ["approval"]
