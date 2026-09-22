"""规则语料一致性（集成层）：每条规则的正反例都必须「判得出来」。

规则数据在 `policies/<domain>/<ID>.yaml`，语料夹具在 `tests/fixtures/rules/<RULE-ID>/`：

- `bad.py`：必须触发本条规则（出现在 `violations` 里，且不是被失败关闭顶掉）；
- `good.py`：必须不触发本条规则（不出现在 `violations`，也不进入 `skipped_rules`）。

判定走**真实验证器流水线**（`validators.pipeline.run_pipeline`，真的调用 Ruff，不 mock、
不伪造证据），证据包交给唯一判定入口 `policy.engine.evaluate`。上下文按夹具契约固定为
`layer="fixture"` / `language="python"`、`operation` 不声明；工作区 = 仓库根，
目标 = 夹具的仓库相对路径（正斜杠）。

覆盖面门禁：`source.kind == "standard"`（由镜像文档提炼）的规则必须正反例齐全，缺失即 FAIL
并列出要补的文件——新规则进来自动被覆盖，不需要改这个文件。`kind == "project-policy"` 的
项目自订规则不强制有夹具，但一旦有就会被同样判定。

规则集整体加载失败（YAML / 字段非法）会让本模块在收集阶段就报错——这是刻意的：规则没写全
允许夹具缺失（覆盖率门禁会 FAIL 并指名道姓），但不允许规则本身读不出来。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import POLICIES_DIR, REPO_ROOT, validators_config

from policy.engine import evaluate
from policy.loader import load_rule_set
from policy.models import (
    BLOCKING_SEVERITIES,
    Decision,
    PolicyContext,
    Rule,
    Severity,
    ValidationResult,
)
from validators.adapters.base import Probe, probe_tool
from validators.pipeline import PipelineReport, PipelineRequest, run_pipeline

pytestmark = pytest.mark.integration

# 夹具契约（见 tests/fixtures/rules/README.md）：目录名 = 规则 id，正反例各一个文件。
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures" / "rules"
FEEDS: tuple[str, ...] = ("good", "bad")
FIXTURE_LAYER = "fixture"
FIXTURE_LANGUAGE = "python"

# 失败关闭的两种措辞（policy.checkers）：出现它们说明「证据链不可用」，不是「命中了规则」。
FAIL_CLOSED_MARKERS = ("关键验证器不可用", "没有验证器")

CONFIG = validators_config()
RULES = load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT)
RULES_BY_ID = {rule.id: rule for rule in RULES.rules}


def fixture_path(rule_id: str, feed: str) -> Path:
    """某个夹具文件的绝对路径；feed 取 good / bad。"""

    return FIXTURES_ROOT / rule_id / (feed + ".py")


def repo_relative(path: Path) -> str:
    """夹具的仓库相对路径（正斜杠），与上下文里的 file 口径一致。"""

    return path.relative_to(REPO_ROOT).as_posix()


def standard_rules() -> tuple[Rule, ...]:
    """由镜像文档提炼的规则（source.kind == "standard"）：必须有正反例。"""

    return tuple(rule for rule in RULES.rules if rule.source.kind == "standard")


def fixture_cases(feed: str) -> tuple[str, ...]:
    """当前真的存在该文件、且能归属到某条规则的规则 id（按规则加载顺序，稳定）。"""

    return tuple(rule.id for rule in RULES.rules if fixture_path(rule.id, feed).is_file())


BAD_CASES = fixture_cases("bad")
GOOD_CASES = fixture_cases("good")

_RUNS: dict[tuple[str, str], tuple[PipelineReport, ValidationResult]] = {}
_PROBES: dict[str, Probe] = {}


def ruff_probe() -> Probe:
    """探测真实的 Ruff（整个模块只探一次）。"""

    if "ruff" not in _PROBES:
        spec = CONFIG.registry.spec("tool.ruff")
        _PROBES["ruff"] = probe_tool(
            spec.tool,
            timeout_ms=5000,
            max_output_bytes=65536,
            workspace=REPO_ROOT,
            tmp_dir=REPO_ROOT / ".tmp",
        )
    return _PROBES["ruff"]


def require_ruff() -> None:
    """本机没有 Ruff 就显式 skip：夹具判定依赖真实工具证据，绝不伪装成通过。"""

    probe = ruff_probe()
    if not probe.ok:
        pytest.skip(
            "本机没有可用的 Ruff（"
            + probe.reason
            + "）；规则语料判定依赖真实 Ruff 证据，CI 会装一份再跑"
        )


def run_fixture(rule_id: str, feed: str) -> tuple[PipelineReport, ValidationResult]:
    """对一个夹具文件跑真实流水线 + 引擎判定；同一 (规则, 文件) 只跑一次。"""

    key = (rule_id, feed)
    cached = _RUNS.get(key)
    if cached is not None:
        return cached

    target = repo_relative(fixture_path(rule_id, feed))
    context = PolicyContext(
        request_id="rule-corpus-" + rule_id + "-" + feed,
        file=target,
        language=FIXTURE_LANGUAGE,
        layer=FIXTURE_LAYER,
    )
    report = run_pipeline(
        PipelineRequest(target=target, workspace=REPO_ROOT, context=context, rules=RULES),
        config=CONFIG,
    )
    result = evaluate(RULES, context, evidence=report.bundle)
    _RUNS[key] = (report, result)
    return report, result


def skipped_ids(result: ValidationResult) -> set[str]:
    """skipped_rules 里的审计身份（形如 ARCH-001@1）。"""

    return {item.rule_id for item in result.skipped_rules}


def fail_closed_violations(rule_id: str, result: ValidationResult) -> tuple:
    """该规则被判成「关键验证器不可用 / 没有验证器」的违规。

    这类 critical 违规说明证据链本身不成立，不能当成「反例命中」；也是正例不该出现的阻断。
    """

    return tuple(
        item
        for item in result.violations
        if item.rule_id == rule_id
        and item.severity is Severity.CRITICAL
        and any(marker in item.message for marker in FAIL_CLOSED_MARKERS)
    )


def _violation_line(violation) -> str:
    evidence = violation.evidence
    where = evidence.subject if evidence.file is None else evidence.file
    if evidence.line is not None:
        where += ":" + str(evidence.line)
    detail = "" if evidence.detail is None else " — " + evidence.detail
    return (
        "  - " + violation.rule_id + "@" + str(violation.rule_version)
        + " [" + violation.severity.value + "] " + where + " " + violation.message + detail
    )


def describe(rule: Rule, report: PipelineReport, result: ValidationResult) -> str:
    """失败信息：一次把「哪条规则、哪个夹具、判成了什么」讲清楚。"""

    target = "<unknown>" if report.target is None else report.target.file
    blockers = "; ".join(
        item.validator + " " + item.status.value + "（" + item.reason + "）"
        for item in report.blockers
    )
    matched = "是" if rule.canonical_id in result.matched_rules else "否"
    skipped = "是" if rule.canonical_id in skipped_ids(result) else "否"
    lines = [
        "规则：" + rule.canonical_id
        + "（severity=" + rule.severity.value
        + "，checker=" + str(rule.enforcement.checker)
        + "，source.kind=" + rule.source.kind
        + "，scope=" + repr(rule.scope.declared_dimensions) + "）",
        "夹具：" + target,
        "决策：" + result.decision.value,
        "该规则在 matched_rules 里：" + matched + "；在 skipped_rules 里：" + skipped,
        "served_checkers：" + (", ".join(report.served_checkers) or "<none>"),
        "blockers：" + (blockers or "<none>"),
        "violations（全部）：",
    ]
    lines.extend(_violation_line(item) for item in result.violations)
    if not result.violations:
        lines.append("  <none>")
    if result.skipped_rules:
        lines.append("skipped_rules：")
        lines.extend(
            "  - " + item.rule_id + "：" + "; ".join(item.reasons)
            for item in result.skipped_rules
        )
    return "\n".join(lines)


# ---------------------------------------------------------------- 自发现与覆盖面门禁


def test_rule_discovery_is_not_empty() -> None:
    """规则集为空会让后面所有门禁变成空转，必须先拦住。"""

    assert RULES.rules, "policies/ 下没有加载到任何规则：覆盖面门禁会空转"


def test_every_standard_rule_has_both_fixtures() -> None:
    """由镜像文档提炼的规则（source.kind=standard）必须正反例齐全。"""

    missing: list[str] = []
    for rule in standard_rules():
        for feed in FEEDS:
            path = fixture_path(rule.id, feed)
            if not path.is_file():
                missing.append(repo_relative(path))
    if not missing:
        return

    lines = ["由镜像文档提炼（source.kind=standard）的规则缺少正反例夹具："]
    lines.extend("  - " + item for item in missing)
    lines.append(
        "补齐方式：bad.py 必须能触发该规则，good.py 必须不触发；两个文件都要能被 Python 解析"
        "（语法错误会让 py.ast 失败关闭，docstring 类规则会被 critical 顶掉）。"
    )
    lines.append("契约与本地复跑方式见 tests/fixtures/rules/README.md。")
    pytest.fail("\n".join(lines))


def test_fixture_directories_are_named_after_rules() -> None:
    """目录名必须等于规则 id：夹具与规则对不上时，判定会挂到别的规则上。"""

    if not FIXTURES_ROOT.is_dir():
        return

    known = {rule.id for rule in RULES.rules}
    orphans: list[Path] = []
    stale: list[Path] = []
    for child in sorted(FIXTURES_ROOT.iterdir()):
        if not child.is_dir() or child.name.startswith(".") or child.name == "__pycache__":
            continue
        # 一个"既没有 bad.py 也没有 good.py"的目录同样是孤儿：旧写法在这里 continue，
        # 于是放了几百 KB 笔记、或者改名改了一半的空目录会被静默跳过——
        # 孤儿目录的判定不该依赖"它恰好放了半个夹具"。
        if not any((child / (feed + ".py")).is_file() for feed in FEEDS):
            stale.append(child)
            continue
        if child.name not in known:
            orphans.append(child)
    if not orphans and not stale:
        return
    if stale:
        print(
            "tests/fixtures/rules/ 下有既没有 bad.py 也没有 good.py 的目录（夹具残缺或已废弃）："
            + ", ".join(child.name for child in stale)
        )
    if not orphans:
        pytest.fail(
            "夹具目录残缺：这些目录必须补齐 good.py 与 bad.py，或整个删掉——"
            + ", ".join(child.name for child in stale)
        )

    lowered = {name.lower(): name for name in known}
    lines = ["tests/fixtures/rules/ 下的目录名不是当前规则集里的规则 id："]
    for child in orphans:
        hint = lowered.get(child.name.lower())
        if hint is None:
            lines.append(
                "  - " + child.name + "（没有对应的 policies/ 规则：补上规则文件，或删除这个目录）"
            )
        else:
            lines.append(
                "  - " + child.name + "（存在同名规则 " + hint + "：目录名大小写必须一致）"
            )
    pytest.fail("\n".join(lines))


# ---------------------------------------------------------------- 反例必须命中


@pytest.mark.parametrize("rule_id", BAD_CASES)
def test_counterexample_hits_its_rule(rule_id: str) -> None:
    """bad.py 必须命中它自己那条规则，且不是被「验证器不可用」顶掉的。"""

    require_ruff()
    rule = RULES_BY_ID[rule_id]
    report, result = run_fixture(rule_id, "bad")
    context = describe(rule, report, result)

    blocked = fail_closed_violations(rule.id, result)
    assert not blocked, (
        rule.id + " 的反例被判成失败关闭（证据链不可用），而不是命中规则：\n" + context
    )

    assert rule.canonical_id not in skipped_ids(result), (
        rule.id + " 的 scope 没有命中夹具上下文（layer=" + FIXTURE_LAYER
        + "、operation 未声明）：\n" + context
    )

    own = tuple(item for item in result.violations if item.rule_id == rule.id)
    assert own, "bad.py 没有命中 " + rule.id + "（没有属于它的 violation）：\n" + context

    severities = sorted({item.severity.value for item in own})
    assert severities == [rule.severity.value], (
        rule.id + " 的 violation severity 与规则声明不一致：实际 " + repr(severities)
        + "，声明 " + rule.severity.value + "：\n" + context
    )

    if rule.severity in BLOCKING_SEVERITIES:
        assert result.decision is Decision.BLOCK, (
            rule.id + " 的 severity=" + rule.severity.value + " 必须阻断，实际决策是 "
            + result.decision.value + "：\n" + context
        )
        return

    assert result.decision is not Decision.ALLOW, (
        rule.id + " 的 severity=" + rule.severity.value + " 时决策不应是 allow：\n" + context
    )
    # 同一个文件里别的规则也可能阻断（夹具只约束它自己那一条）；
    # 只有文件里没有其他阻断项时，才能要求决策恰好等于 allow_with_warnings。
    foreign_blocking = [
        item
        for item in result.violations
        if item.rule_id != rule.id and item.severity in BLOCKING_SEVERITIES
    ]
    if not foreign_blocking:
        assert result.decision is Decision.ALLOW_WITH_WARNINGS, (
            rule.id + " 的 severity=" + rule.severity.value
            + "、且文件里没有其他阻断项，决策应当恰好是 allow_with_warnings：\n" + context
        )


# ---------------------------------------------------------------- 正例必须通过


@pytest.mark.parametrize("rule_id", GOOD_CASES)
def test_positive_example_passes_its_rule(rule_id: str) -> None:
    """good.py 不得触发它自己那条规则，也不得让该规则被跳过。"""

    require_ruff()
    rule = RULES_BY_ID[rule_id]
    report, result = run_fixture(rule_id, "good")
    context = describe(rule, report, result)

    blocked = fail_closed_violations(rule.id, result)
    assert not blocked, (
        rule.id + " 的正例被判成失败关闭（证据链不可用，不是正例的问题）：\n" + context
    )

    assert rule.canonical_id not in skipped_ids(result), (
        rule.id + " 的 scope 没有命中夹具上下文（layer=" + FIXTURE_LAYER
        + "、operation 未声明）：\n" + context
    )

    own = tuple(item for item in result.violations if item.rule_id == rule.id)
    assert not own, rule.id + " 的正例被判成违规（good.py 不得触发本规则）：\n" + context
