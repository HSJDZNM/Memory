"""规则组合语料门禁（集成层）：多条规则叠加在**同一次变更**上时，结论是什么？

tests/fixtures/rules/<RULE-ID>/ 那道语料门禁只回答「**单条**规则判不判得出来」：它的上下文
固定为 layer="fixture"、**不声明 operation**。带 operation 维度的规则
（TESTING-001@1 / TESTING-002@1）于是在那道门禁里恒进 skipped_rules——它从没执行过
这两条规则，「谁来验组合」因此没有答案（04-open-work 5.68 记的防线失效处）。

本模块补的就是这一格。tests/fixtures/rules/_combinations/cases/*.yaml 的每个条目声明
**一次变更的形状**与**期望的结论**，用例走与 CLI / Hook 完全相同的链路：

    validators.pipeline.run_pipeline（真实验证器：真调 Ruff、真跑 pytest）
        → policy.engine.evaluate（唯一判定入口）

条目是**棘轮**：它把当前结论钉住，改结论必须显式改夹具。第一批里 conftest-alone 记录的是
**已知的死锁**（改测试支撑文件被拦死，5.66），不是「期望的行为」——条目文件的注释写着为什么、
什么时候该翻面。

**仍不覆盖什么**（照实写，别读成「组合全查过了」）：

- 只跑验证器路径：没有 Hook、没有 Phase 4 受控执行、没有审批；
- changed[] 是条目**声明**的变更集，不是 Hook「每次只报一个文件」那种形状
  （批次 / 意图粒度仍未被实现，见 5.68 的第 ⑤ 步）；
- 只钉两件事：决策，以及 served_checkers（本次真的产出了哪些证据）。「哪一条规则报了违规」
  由失败信息里的 violations（全部）给出，不参与断言。
"""

from __future__ import annotations

import ast
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import pytest
import yaml
from conftest import POLICIES_DIR, REPO_ROOT, validators_config

from policy.engine import evaluate
from policy.loader import load_rule_set
from policy.models import Decision, Operation, PolicyContext, Rule, ValidationResult
from validators.adapters.base import Probe, probe_tool
from validators.pipeline import PipelineReport, PipelineRequest, run_pipeline

pytestmark = pytest.mark.integration

COMBINATIONS_ROOT = REPO_ROOT / "tests" / "fixtures" / "rules" / "_combinations"
CASES_DIR = COMBINATIONS_ROOT / "cases"

# 条目文件的键集合是**闭集**：多一个键就等于「写了一条没人读的声明」（AGENTS 第 3 条：
# 未知字段不得静默忽略）。note 只给人看，不参与断言。
REQUIRED_KEYS: tuple[str, ...] = (
    "project",
    "target",
    "operation",
    "changed",
    "layer",
    "language",
    "expected_decision",
    "expected_served_checkers",
)
OPTIONAL_KEYS: tuple[str, ...] = ("note",)
KNOWN_KEYS = frozenset(REQUIRED_KEYS + OPTIONAL_KEYS)

CONFIG = validators_config()
RULES = load_rule_set([POLICIES_DIR], repo_root=REPO_ROOT)

_RUNS: dict[str, tuple[PipelineReport, ValidationResult]] = {}
_PROBES: dict[str, Probe] = {}


@dataclass(frozen=True)
class CombinationCase:
    """一个组合条目的全部可判定事实（形状 + 期望结论）。"""

    case_id: str
    path: Path
    project: str
    target: str
    operation: str
    changed: tuple[str, ...]
    layer: str
    language: str
    expected_decision: Decision
    expected_served_checkers: tuple[str, ...]
    note: str = ""

    def shape(self) -> str:
        """这次变更的形状，一行读完（失败信息的第一行）。"""

        return (
            "target=" + self.target
            + " operation=" + self.operation
            + " layer=" + self.layer
            + " language=" + self.language
            + " changed=" + repr(list(self.changed))
        )

    def where(self) -> str:
        return self.path.relative_to(REPO_ROOT).as_posix()


def _text(document: dict[str, Any], key: str, where: str, problems: list[str]) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        problems.append(where + "：键 " + key + " 必须是非空字符串，实际 " + repr(value))
        return ""
    return value.strip()


def _relative_path(value: Any, key: str, where: str, problems: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        problems.append(where + "：" + key + " 必须是非空的仓库相对路径，实际 " + repr(value))
        return ""
    candidate = value.strip()
    if candidate.startswith("/") or "\\" in candidate or ":" in candidate:
        problems.append(
            where + "：" + key + " 必须是仓库相对路径（正斜杠、无盘符、无反斜杠），实际 "
            + repr(value)
        )
        return ""
    if any(part in ("", ".", "..") for part in candidate.split("/")):
        problems.append(
            where + "：" + key + " 含空段 / . / ..，不是规范化的相对路径：" + repr(value)
        )
        return ""
    return candidate


def parse_case(path: Path) -> tuple[Optional[CombinationCase], tuple[str, ...]]:
    """读一个条目文件；返回（条目，问题清单）。问题非空时条目为 None。"""

    where = path.relative_to(REPO_ROOT).as_posix()
    problems: list[str] = []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        return None, (where + "：读不出来（" + type(error).__name__ + "：" + str(error) + "）",)
    if not isinstance(raw, dict):
        return None, (where + "：顶层必须是映射（键 = " + ", ".join(REQUIRED_KEYS) + "）",)

    unknown = sorted(set(raw) - KNOWN_KEYS)
    if unknown:
        problems.append(
            where + "：未知键 " + repr(unknown) + "（允许的键：" + ", ".join(sorted(KNOWN_KEYS))
            + "）——未知字段不得静默忽略"
        )

    project = _relative_path(raw.get("project"), "project", where, problems)
    target = _relative_path(raw.get("target"), "target", where, problems)
    layer = _text(raw, "layer", where, problems)
    language = _text(raw, "language", where, problems)

    if project and target:
        tree = REPO_ROOT / project
        if not tree.is_dir():
            problems.append(where + "：project 指向的目录不存在：" + project)
        elif not (tree / target).is_file():
            problems.append(
                where + "：target 在声明的项目树里不存在——组合条目必须是「真的在那棵树里」的文件："
                + target
            )

    operation = _text(raw, "operation", where, problems)
    if operation and operation not in {item.value for item in Operation}:
        problems.append(
            where + "：operation 取值 " + repr(operation) + " 不在 "
            + repr(sorted(item.value for item in Operation)) + " 里"
        )

    changed_raw = raw.get("changed")
    changed: list[str] = []
    if not isinstance(changed_raw, list) or not changed_raw:
        problems.append(where + "：changed 必须是非空列表（变更集），实际 " + repr(changed_raw))
    else:
        for index, item in enumerate(changed_raw):
            path_text = _relative_path(item, "changed[" + str(index) + "]", where, problems)
            if path_text:
                changed.append(path_text)
        if len(set(changed)) != len(changed):
            problems.append(where + "：changed 里有重复路径：" + repr(changed))

    decision_text = _text(raw, "expected_decision", where, problems)
    decision: Optional[Decision] = None
    if decision_text:
        try:
            decision = Decision(decision_text)
        except ValueError:
            problems.append(
                where + "：expected_decision 取值 " + repr(decision_text) + " 不是决策枚举（允许："
                + ", ".join(item.value for item in Decision) + "）"
            )

    served_raw = raw.get("expected_served_checkers")
    served: list[str] = []
    if not isinstance(served_raw, list):
        problems.append(
            where + "：expected_served_checkers 必须是列表（没有证据就写 []），实际 "
            + repr(served_raw)
        )
    else:
        for index, item in enumerate(served_raw):
            if not isinstance(item, str) or not item.strip():
                problems.append(
                    where + "：expected_served_checkers[" + str(index)
                    + "] 必须是非空字符串，实际 " + repr(item)
                )
                continue
            served.append(item.strip())
        if len(set(served)) != len(served):
            problems.append(where + "：expected_served_checkers 里有重复项：" + repr(served))

    note = raw.get("note", "")
    if note is not None and not isinstance(note, str):
        problems.append(where + "：note 必须是字符串，实际 " + repr(note))
        note = ""

    if problems:
        return None, tuple(problems)

    assert decision is not None  # problems 为空保证了它已被解析出来
    return (
        CombinationCase(
            case_id=path.stem,
            path=path,
            project=project,
            target=target,
            operation=operation,
            changed=tuple(changed),
            layer=layer,
            language=language,
            expected_decision=decision,
            expected_served_checkers=tuple(sorted(served)),
            note=note or "",
        ),
        (),
    )


def load_cases() -> tuple[tuple[CombinationCase, ...], tuple[str, ...]]:
    """读 cases/ 下的全部条目（按文件名排序，参数化 id 因此稳定）。"""

    if not CASES_DIR.is_dir():
        return (), ("条目目录不存在：" + CASES_DIR.relative_to(REPO_ROOT).as_posix(),)

    cases: list[CombinationCase] = []
    problems: list[str] = []
    seen: dict[str, str] = {}
    for path in sorted(CASES_DIR.glob("*.yaml")):
        case, case_problems = parse_case(path)
        problems.extend(case_problems)
        if case is None:
            continue
        if case.case_id in seen:
            problems.append(
                "条目 id 重复：" + case.case_id + "（" + seen[case.case_id] + " 与 "
                + case.where() + "）"
            )
            continue
        seen[case.case_id] = case.where()
        cases.append(case)
    if not cases and not problems:
        problems.append("cases/ 下一个条目都没有：" + CASES_DIR.relative_to(REPO_ROOT).as_posix())
    return tuple(cases), tuple(problems)


CASES, CASE_PROBLEMS = load_cases()
CASE_IDS = tuple(case.case_id for case in CASES)


def ruff_probe() -> Probe:
    """探测真实的 Ruff（整个模块只探一次）。"""

    if "ruff" not in _PROBES:
        _PROBES["ruff"] = probe_tool(
            CONFIG.registry.spec("tool.ruff").tool,
            timeout_ms=5000,
            max_output_bytes=65536,
            workspace=REPO_ROOT,
            tmp_dir=REPO_ROOT / ".tmp",
        )
    return _PROBES["ruff"]


def require_ruff() -> None:
    """本机没有 Ruff 就显式 skip：组合条目依赖真实证据，绝不伪装成通过。"""

    probe = ruff_probe()
    if not probe.ok:
        pytest.skip(
            "本机没有可用的 Ruff（" + probe.reason
            + "）；组合语料依赖真实 Ruff 证据，CI 会装一份再跑"
        )


def build_workspace(directory: Path, case: CombinationCase) -> Path:
    """把条目声明的项目树复制到临时目录——判定读的就是「这次那棵树」。

    复制而不是就地跑：受治工作区在真实链路里也是影子副本（pre_evidence），
    而且就地跑会往被跟踪夹具里写 __pycache__。
    """

    workspace = directory / "project"
    shutil.copytree(REPO_ROOT / case.project, workspace)
    return workspace


def run_case(
    case: CombinationCase, make_directory: Callable[[], Path]
) -> tuple[PipelineReport, ValidationResult]:
    """跑一次条目（同一模块内同一 id 只跑一次，结果缓存复用）。"""

    cached = _RUNS.get(case.case_id)
    if cached is not None:
        return cached

    workspace = build_workspace(make_directory(), case)
    context = PolicyContext(
        request_id="rule-combination-" + case.case_id,
        file=case.target,
        language=case.language,
        layer=case.layer,
        operation=case.operation,
    )
    report = run_pipeline(
        PipelineRequest(
            target=case.target,
            workspace=workspace,
            context=context,
            rules=RULES,
            changed_files=case.changed,
        ),
        config=CONFIG,
    )
    result = evaluate(RULES, context, evidence=report.bundle)
    _RUNS[case.case_id] = (report, result)
    return report, result


def _violation_line(violation: Any) -> str:
    evidence = violation.evidence
    where = evidence.subject if evidence.file is None else evidence.file
    if evidence.line is not None:
        where += ":" + str(evidence.line)
    detail = "" if evidence.detail is None else " — " + evidence.detail
    return (
        "  - " + violation.rule_id + "@" + str(violation.rule_version)
        + " [" + violation.severity.value + "] " + where + " " + violation.message + detail
    )


def describe(case: CombinationCase, report: PipelineReport, result: ValidationResult) -> str:
    """失败信息：一次把「哪条组合、什么形状、判成了什么」讲清楚。"""

    blockers = "; ".join(
        item.validator + " " + item.status.value + "（" + item.reason + "）"
        for item in report.blockers
    )
    lines = [
        "条目：" + case.case_id + "（" + case.where() + "）",
        "形状：" + case.shape(),
        "项目树：" + case.project,
        "决策：" + result.decision.value,
        "served_checkers：" + (", ".join(report.served_checkers) or "<none>"),
        "selection：" + json.dumps(dict(report.selection), ensure_ascii=False, sort_keys=True),
        "参与判定的规则：" + str(len(result.matched_rules)) + " 条",
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


# ---------------------------------------------------------------- 条目形状（先于判定）


def test_combination_cases_are_well_formed() -> None:
    """条目文件的形状是门禁的前提：读不出来就说明条目写错了，不是「判定失败」。"""

    if CASE_PROBLEMS:
        lines = ["组合条目有问题（条目文件在 tests/fixtures/rules/_combinations/cases/）："]
        lines.extend("  - " + item for item in CASE_PROBLEMS)
        lines.append("契约见 tests/fixtures/rules/_combinations/README.md。")
        pytest.fail("\n".join(lines))

    assert CASES, "一个条目都没有：这道门禁会空转"


def _module_string_list(source: str, name: str) -> tuple:
    """读出模块级 name = ["...", ...] 的字面量（AST 读，不做字符串匹配）。"""

    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        if not isinstance(node.value, ast.List):
            continue
        return tuple(
            item.value
            for item in node.value.elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        )
    return ()


def test_combination_fixture_project_is_ignored_at_the_directory_level() -> None:
    """夹具项目必须被仓库自己的收集**整目录**排除。

    为什么必须是目录级、而不是它下面的 tests/*：pytest 只对「要收集的那个路径」找**最近的**
    conftest（_pytest/main.py 的 pytest_ignore_collect 按 collection_path.parent 取
    collect_ignore_glob），而夹具项目自己的 tests/conftest.py 就是那个「最近的 conftest」——
    它没有声明这一项，忽略因此整体失效，而且它还会以模块名 conftest 抢先注册、把仓库自己的
    tests/conftest.py 顶掉（实测全量收集报 59 个 ImportError）。忽略项目**目录本身**，
    pytest 就不会下降进去，那个 conftest 也永远不会被 import。
    """

    declared = _module_string_list(
        (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"), "collect_ignore_glob"
    )
    assert "fixtures/rules/_combinations/project" in declared, (
        "tests/conftest.py 的 collect_ignore_glob 必须整目录排除 "
        "fixtures/rules/_combinations/project（写成它下面的 tests/* 会在夹具项目自带"
        " conftest.py 时整体失效）；实际声明：" + repr(declared)
    )
    assert not (COMBINATIONS_ROOT / "project" / "conftest.py").is_file(), (
        "夹具项目的**目录本身**不能有 conftest.py：pytest 找的是「最近的 conftest」，"
        "项目根一旦有它，上一条目录级忽略就又会失效"
    )


# ---------------------------------------------------------------- 组合必须真的被执行


def operation_scoped_rules() -> tuple[Rule, ...]:
    """带 operation 维度的规则——单条语料门禁**永远碰不到**它们（那道门禁不声明 operation）。"""

    return tuple(rule for rule in RULES.rules if "operation" in rule.scope.declared_dimensions)


def test_combination_corpus_exercises_every_operation_scoped_rule(
    tmp_root_factory: Callable[[], Path],
) -> None:
    """每条「带 operation 维度」的规则都必须至少参与过一次判定。

    没有这一条，这道门禁可以整体空转：条目全绿，而那些规则仍然恒在 skipped_rules 里——
    正是 tests/fixtures/rules/<ID>/ 那道门禁的失效方式（5.68）。
    """

    require_ruff()
    scoped = operation_scoped_rules()
    assert scoped, (
        "没有任何规则声明 operation 维度：这道门禁的存在前提不成立，需要重新评审它要不要留"
    )

    matched: set[str] = set()
    for case in CASES:
        _report, result = run_case(case, tmp_root_factory)
        matched.update(result.matched_rules)

    never = [rule.canonical_id for rule in scoped if rule.canonical_id not in matched]
    assert not never, (
        "这些规则声明了 operation 维度，却在全部组合条目里一次都没参与判定（恒在 skipped_rules）："
        + ", ".join(never)
        + "\n处置：在 tests/fixtures/rules/_combinations/cases/ 加一条声明了 operation 的条目，"
        "让变更的形状命中它——不要把它从这条检查里删掉。"
    )


# ---------------------------------------------------------------- 判定与证据必须与条目一致


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_combination_matches_its_declared_reading(case: CombinationCase, tmp_root: Path) -> None:
    """决策与 served_checkers 都必须逐字等于条目声明的读数。"""

    require_ruff()
    report, result = run_case(case, lambda: tmp_root)
    context = describe(case, report, result)

    assert result.decision is case.expected_decision, (
        case.case_id + " 的决策与条目声明不一致：实际 " + result.decision.value
        + "，声明 " + case.expected_decision.value + "\n" + context
    )

    served = tuple(report.served_checkers)
    assert served == case.expected_served_checkers, (
        case.case_id + " 的证据集合与条目声明不一致：\n  实际：" + repr(served)
        + "\n  声明：" + repr(case.expected_served_checkers)
        + "\n（照实重采并把新读数写进条目；不要为了让门禁变绿而放宽断言）\n" + context
    )
