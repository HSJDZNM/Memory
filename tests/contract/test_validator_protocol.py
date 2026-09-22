"""Phase 5 契约测试：证据协议、checker 对齐、核心层边界与可重放性。

契约的要点：证据协议的版本、数据与代码的对齐、以及"决策协议没有被 Phase 5 改动"。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from conftest import POLICIES_DIR, REPO_ROOT, VALIDATOR_PROJECT, make_context, validators_config
from policy.checkers import CONTEXT_CHECKERS, EVIDENCE_CHECKERS, SUPPORTED_CHECKERS
from policy.evidence import (
    EVIDENCE_SCHEMA_VERSION,
    FAIL_CLOSED_STATUSES,
    SUCCESS_STATUSES,
    EvidenceBundle,
    ValidatorStatus,
)
from policy.loader import load_rule_set
from policy.models import KNOWN_CHECKERS, SCHEMA_VERSION, ValidationResult
from validators.pipeline import KNOWN_VALIDATOR_IDS, PipelineRequest, run_pipeline
from validators.registry import load_config

pytestmark = pytest.mark.contract

CONFIG = validators_config()

# 核心层（端口与模型）不允许导入验证器实现：只有 CLI（policy.check）在应用层装配。
CORE_MODULES = ("models", "engine", "context", "scope", "loader", "evidence", "checkers")


def test_evidence_schema_version_is_pinned() -> None:
    assert EVIDENCE_SCHEMA_VERSION == "1.0"
    assert EvidenceBundle().schema_version == "1.0"

    with pytest.raises(Exception):
        EvidenceBundle(schema_version="2.0")


def test_checker_vocabulary_agrees_across_layers() -> None:
    mapping = CONFIG.registry.checkers_for_language("python")
    registry_checkers = set(mapping)

    assert all(owners for owners in mapping.values()), mapping
    assert set(KNOWN_CHECKERS) == set(SUPPORTED_CHECKERS)
    assert CONTEXT_CHECKERS | EVIDENCE_CHECKERS == SUPPORTED_CHECKERS
    assert registry_checkers <= SUPPORTED_CHECKERS
    # 注册表必须覆盖全部 checker，否则规则一旦用到就只能失败关闭
    assert registry_checkers == set(SUPPORTED_CHECKERS)


def test_registry_and_implementation_are_aligned() -> None:
    declared = {spec.id for spec in CONFIG.registry.validators}

    assert declared == set(KNOWN_VALIDATOR_IDS)


def test_every_shipped_rule_is_covered_by_a_validator() -> None:
    rules = load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT)
    checkers = CONFIG.registry.checkers_for_language("python")

    for rule in rules.rules:
        language = rule.scope.language
        assert language == "python", rule.canonical_id
        assert checkers.get(rule.enforcement.checker), (
            rule.canonical_id,
            rule.enforcement.checker,
        )


# Phase 5 就选了、但从来没有规则归属的 Ruff 码：它们只进 unmapped_findings 计数，不参与判定。
# 这里显式登记是"如实记账"，不是给新增留的口子——新增要选一个码，就必须同时有规则声明它。
LEGACY_UNOWNED_RUFF_CODES = frozenset({"F811", "F841"})


def ruff_select() -> frozenset[str]:
    """validation/ruff.toml 里真正 select 的 Ruff 码。"""

    document = tomllib.loads(
        (REPO_ROOT / "validation" / "ruff.toml").read_text(encoding="utf-8")
    )
    return frozenset(document["lint"]["select"])


def test_ruff_codes_are_declared_and_selected_in_both_directions() -> None:
    """Ruff 码的归属必须双向一致，否则规则会"静默失效"。

    两个方向都必须是空集：

    - **规则声明了、但没被 select 的码**：工具根本不会报这个码，那条规则永远拿不到证据，
      也永远不会出现在 violations 里——正是"看起来在管这件事、实际什么都没查"；
    - **select 了、但没有规则归属的码**：诊断只被计入 unmapped_findings，不参与判定，
      却在 `validation/ruff.toml` 里摆出"这是被治理的"的姿态。

    `validation/ruff.toml` 的注释表就是这条不变量的可读版本；本用例是它的机器版本。
    """

    selected = ruff_select()
    declared: dict[str, set[str]] = {}
    for rule in load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT).rules:
        body = getattr(rule.rule, "style_lint", None)
        if body is None:
            continue
        for code in body.codes:
            declared.setdefault(code, set()).add(rule.canonical_id)

    unselected = sorted(set(declared) - selected)
    assert unselected == [], (
        "规则声明了没有在 validation/ruff.toml 里 select 的 Ruff 码，那些规则永远不会命中："
        + repr([(code, sorted(declared[code])) for code in unselected])
    )

    unowned = sorted(selected - set(declared) - LEGACY_UNOWNED_RUFF_CODES)
    assert unowned == [], (
        "validation/ruff.toml select 了没有规则归属的 Ruff 码；要么写规则声明它，"
        "要么把它从 select 里去掉（否则它只是一条永远不计入判定的诊断）：" + repr(unowned)
    )


def test_rule_packs_only_reference_validators_of_their_language() -> None:
    for pack in CONFIG.registry.rule_packs:
        for name in pack.validators:
            spec = CONFIG.registry.spec(name)
            assert spec is not None
            assert name.startswith("py.") or name.startswith("tool.")


def test_statuses_partition_into_success_and_failure() -> None:
    assert SUCCESS_STATUSES & FAIL_CLOSED_STATUSES == frozenset()
    assert ValidatorStatus.OK in SUCCESS_STATUSES
    assert ValidatorStatus.FINDINGS in SUCCESS_STATUSES
    assert ValidatorStatus.TIMEOUT in FAIL_CLOSED_STATUSES
    assert ValidatorStatus.NOT_SELECTED not in SUCCESS_STATUSES | FAIL_CLOSED_STATUSES


def test_decision_protocol_is_untouched_by_phase_five() -> None:
    assert SCHEMA_VERSION == "1.0"
    assert "evidence" not in ValidationResult.model_fields
    payload = ValidationResult(decision="allow", request_id="req-1").to_decision_dict()

    assert set(payload) == {
        "schema_version",
        "decision",
        "request_id",
        "trace_id",
        "rule_set_hash",
        "matched_rules",
        "skipped_rules",
        "violations",
        "required_action",
        "policy_version",
    }


@pytest.mark.parametrize("module", CORE_MODULES)
def test_core_modules_do_not_import_the_validator_layer(module: str) -> None:
    source = (REPO_ROOT / "src" / "policy" / (module + ".py")).read_text(encoding="utf-8")
    imports = [
        line
        for line in source.splitlines()
        if re.match(r"^\s*(from|import)\s+", line) and "validators" in line
    ]

    assert imports == [], imports


def test_importing_the_engine_does_not_pull_in_the_validator_layer() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import policy.engine; "
            "print([name for name in sys.modules if name.startswith('validators')])",
        ],
        cwd=str(REPO_ROOT),
        env={"PYTHONPATH": str(REPO_ROOT / "src"), "SYSTEMROOT": str(Path("C:/Windows"))},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]"


def test_report_records_configuration_digests_and_environment() -> None:
    rules = load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT)
    context = make_context(file="src/shop/order_controller_bad.py", language="python")
    report = run_pipeline(
        PipelineRequest(
            target=context.file, workspace=VALIDATOR_PROJECT, context=context, rules=rules
        ),
        config=CONFIG,
    )

    assert report.configs["registry"].startswith("sha256:")
    assert report.configs["project"].startswith("sha256:")
    assert report.configs["test_layout"].startswith("sha256:")
    assert report.environment["python_version"].count(".") >= 1
    assert report.bundle.schema_version == EVIDENCE_SCHEMA_VERSION


ABSOLUTE_PATH_RE = re.compile(r"(^|[^A-Za-z0-9_])[A-Za-z]:[\\/]|(^|\s)/(home|root|etc|usr|var|opt|tmp|Users)/")


def test_evidence_payload_has_no_absolute_paths_or_durations() -> None:
    rules = load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT)
    context = make_context(file="src/shop/order_controller_bad.py", language="python")
    report = run_pipeline(
        PipelineRequest(
            target=context.file, workspace=VALIDATOR_PROJECT, context=context, rules=rules
        ),
        config=CONFIG,
    )

    payload = json.dumps(report.to_payload(), ensure_ascii=False)

    assert "duration_ms" not in payload
    assert ABSOLUTE_PATH_RE.search(payload) is None, payload[:400]


def test_two_runs_produce_identical_payloads() -> None:
    rules = load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT)
    context = make_context(file="src/shop/style_offences.py", language="python")
    request = PipelineRequest(
        target=context.file, workspace=VALIDATOR_PROJECT, context=context, rules=rules
    )

    first = run_pipeline(request, config=CONFIG).to_payload()
    second = run_pipeline(request, config=CONFIG).to_payload()

    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second, ensure_ascii=False, sort_keys=True
    )


def test_reports_only_use_declared_validator_ids() -> None:
    rules = load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT)
    context = make_context(file="src/shop/order_controller_bad.py", language="python")
    report = run_pipeline(
        PipelineRequest(
            target=context.file, workspace=VALIDATOR_PROJECT, context=context, rules=rules
        ),
        config=CONFIG,
    )

    for record in report.validators:
        assert record.validator_id in KNOWN_VALIDATOR_IDS or record.validator_id == "cli.explicit"


def test_config_load_is_atomic(tmp_root: Path) -> None:
    """任何一份数据文件坏掉都不能返回半个配置。"""

    from conftest import write_validation_config

    write_validation_config(tmp_root)
    (tmp_root / "validation" / "project.yaml").write_text("version: [1," + chr(10), encoding="utf-8")

    with pytest.raises(Exception):
        load_config(root=tmp_root, registry=REPO_ROOT / "validation" / "validators.yaml")
