"""Phase 5 契约测试：证据协议、checker 对齐、核心层边界与可重放性。

契约的要点：证据协议的版本、数据与代码的对齐、以及"决策协议没有被 Phase 5 改动"。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from dataclasses import fields as dataclass_fields
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
from validators.pipeline import (
    KNOWN_VALIDATOR_IDS,
    PIPELINE_SCHEMA_VERSION,
    PipelineReport,
    PipelineRequest,
    run_pipeline,
)
from validators.registry import load_config

pytestmark = pytest.mark.contract

CONFIG = validators_config()

# 核心层（端口与模型）不允许导入验证器实现：只有 CLI（policy.check）在应用层装配。
CORE_MODULES = ("models", "engine", "context", "scope", "loader", "evidence", "checkers")


def test_evidence_schema_version_is_pinned() -> None:
    # P7：validators[].served_checkers → declared_checkers 是载荷的**字段变化**，
    # 按 src/policy/evidence.py 自己的规则（"字段增删或语义变化都要显式改这里"）递增。
    # Q7（1.1 → 1.2）：新增 ValidatorStatus.PENDING_IMPLEMENTATION 与
    # EvidenceBundle.pending_implementation（「待实现」这一族字段）。
    assert EVIDENCE_SCHEMA_VERSION == "1.2"
    assert EvidenceBundle().schema_version == "1.2"

    with pytest.raises(Exception):
        EvidenceBundle(schema_version="2.0")

    # 旧载荷一律拒绝：1.0 的 validators[] 用的是另一个键名；1.1 没有「待实现」这一族字段，
    # 静默接受等于把"覆盖它的测试跑不了"读成"没有这条信息"。
    for old in ("1.0", "1.1"):
        with pytest.raises(Exception):
            EvidenceBundle(schema_version=old)


def test_pipeline_schema_version_is_pinned_and_single_sourced() -> None:
    """流水线载荷也变了（validators[] 的键 + language_coverage + pending_implementation），
    版本号同步且只有一份真值。"""

    import validators

    assert PIPELINE_SCHEMA_VERSION == "1.2"
    assert validators.PIPELINE_SCHEMA_VERSION == PIPELINE_SCHEMA_VERSION


def test_every_validator_status_is_classified() -> None:
    """新增一个 ValidatorStatus 必须落进三类之一，否则它会被当成"没问题"。

    "待实现"（Q7）刻意两边都不进：它不是"证据到手"（否则没查成的会被记成查过了），
    也不是"证据没拿到"（那不是失败关闭，是"这次的树还在构建中"）。它属于第三类：
    有可读状态、不产生 Blocker、判定侧产出 warning。
    """

    assert ValidatorStatus.PENDING_IMPLEMENTATION not in SUCCESS_STATUSES
    assert ValidatorStatus.PENDING_IMPLEMENTATION not in FAIL_CLOSED_STATUSES
    classified = (
        set(SUCCESS_STATUSES)
        | set(FAIL_CLOSED_STATUSES)
        | {ValidatorStatus.NOT_SELECTED, ValidatorStatus.PENDING_IMPLEMENTATION}
    )
    assert classified == set(ValidatorStatus)


def test_report_payload_carries_every_field() -> None:
    """载荷键与报告字段一一对应：新增字段忘了进载荷，账本里就永远读不到它。"""

    rules = load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT)
    context = make_context(file="src/shop/order_controller_bad.py", language="python")
    report = run_pipeline(
        PipelineRequest(
            target=context.file, workspace=VALIDATOR_PROJECT, context=context, rules=rules
        ),
        config=CONFIG,
    )

    assert "pending_implementation" in set(EvidenceBundle().to_payload())
    assert set(EvidenceBundle().to_payload()) == set(EvidenceBundle.model_fields) | {"schema"}
    assert set(report.to_payload()) == {item.name for item in dataclass_fields(PipelineReport)}
    assert report.to_payload()["pending_implementation"] == []


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


def analysis_failure_codes_by_validator() -> dict[str, tuple[str, ...]]:
    """注册表里声明的"本次分析不成立"码（按验证器分组）。"""

    return {
        spec.id: spec.tool.analysis_failure_codes
        for spec in CONFIG.registry.validators
        if spec.tool is not None and spec.tool.analysis_failure_codes
    }


def test_analysis_failure_codes_are_disjoint_from_governed_codes() -> None:
    """一个码不可能既"可判定的规则码"、又"本次分析不成立"。

    两个方向都必须是空集：与 `validation/ruff.toml` 的 `select` 交集（select 里的码是
    "工具会报、规则会判"的码），与规则声明的码交集（否则那条规则要么永远拿不到证据，
    要么在"分析不成立"时被当成命中）。这是数据自洽性检查：它保证 N17 的修复名单
    不会退化成另一张"没人读的码表"。
    """

    declared = analysis_failure_codes_by_validator()
    # 名单为空 = 修复被撤销（回到"没查成的被记成查过了"），所以这条断言本身就是门禁
    assert declared, "tool.ruff 必须声明「分析不成立」码（N17 的修复依赖它）"

    selected = {item.upper() for item in ruff_select()}
    owned: set[str] = set()
    for rule in load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT).rules:
        body = getattr(rule.rule, "style_lint", None)
        if body is not None:
            owned.update(code.upper() for code in body.codes)

    conflicts = [
        (validator_id, code)
        for validator_id, codes in declared.items()
        for code in codes
        if code.upper() in selected
    ]
    assert conflicts == [], "分析不成立码不能同时是 select 里的可判定码：" + repr(conflicts)

    collisions = [
        (validator_id, code)
        for validator_id, codes in declared.items()
        for code in codes
        if code.upper() in owned
    ]
    assert collisions == [], "分析不成立码不能同时有规则归属：" + repr(collisions)


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
