"""验证器流水线：按规则选验证器 → 分波执行 → 聚合证据 → 交给 Policy Engine。

形状（对应 Phase 5 计划书第 6 步）：

    Code → Source → AST → Dependency → Docstring → Lint → Type → Tests → Evidence → Policy

要点：

- **按规则选择**：只有 scope 命中的规则需要的 checker 才会去跑对应验证器，验证器再按
  requires 补齐前置事实（源码 / AST）；没跑的验证器在报告里记 not_selected 与原因；
- **失败关闭**：critical 验证器没跑成（缺失 / 版本不符 / 超时 / 崩溃 / 配置错误 / 输出非法）
  会让它服务的 checker（以及依赖它的验证器所服务的 checker）整体不可判定，由引擎按 critical 阻断；
- **第三种状态（Q7）**：工具跑成了、但选中的测试因**项目内**某模块/名字在本次树里还不存在而
  收集失败时，记 pending_implementation——不进 served_checkers（没查成的不能记成查过了），
  也不产生 Blocker（那不是"证据没拿到"，而是"先写测试、再写实现"这条正确顺序）；
  判定侧据此产出 warning（decision=allow_with_warnings），理由与缺失目标都进报告与账本；
- **证据与判定分离**：流水线只产出证据与阻断点，"allow / block" 由 Policy Engine 决定；
- **确定性**：波次内并行执行，但证据、依赖、记录、阻断点都按稳定键排序，与完成顺序无关。
"""

from __future__ import annotations

import platform
import shutil
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, FrozenSet, Mapping, Optional, Sequence, Tuple

from policy import engine as engine_module
from policy.evidence import (
    FAIL_CLOSED_STATUSES,
    SUCCESS_STATUSES,
    Blocker,
    DependencyFact,
    DependencyKind,
    DependencyResolution,
    EvidenceBundle,
    PendingImplementation,
    SourceDigest,
    ToolInvocation,
    ValidationEvidence,
    ValidatorKind,
    ValidatorRecord,
    ValidatorStatus,
)
from policy.models import PolicyContext, Rule, RuleSet, canonical_identifier

from .adapters.base import AdapterResult, probe_tool
from .adapters.mypy import run_mypy
from .adapters.pytest_runner import run_pytest
from .adapters.ruff import run_ruff
from .depgraph import DependencyResult, build_dependencies, build_module_index
from .docstrings import missing_docstring_evidence
from .models import ValidatorSpec
from .python_ast import ModuleFacts, parse_module
from .registry import ValidationConfig, RegistryError, config_digest
from .source import SourceError, SourceFile, read_source

__all__ = [
    "JUDGEMENT_EMPTY",
    "JUDGEMENT_OUTCOMES",
    "JUDGEMENT_UNANALYZED",
    "KNOWN_VALIDATOR_IDS",
    "LANGUAGE_COVERAGE_COVERED",
    "LANGUAGE_COVERAGE_DECLARED_IN",
    "LANGUAGE_COVERAGE_NOT_COVERED",
    "LANGUAGE_COVERAGE_STATUSES",
    "LANGUAGE_COVERAGE_UNKNOWN",
    "PIPELINE_SCHEMA_VERSION",
    "BuiltinError",
    "CheckerJudgement",
    "PipelineReport",
    "PipelineRequest",
    "language_coverage",
    "render_report",
    "run_pipeline",
]

# 1.1：validators[] 的 served_checkers → declared_checkers（P7："声明负责"≠"真的服务过"），
#      并新增 PipelineReport.language_coverage（P2：哪些语言按设计不取证写成数据）。
# 1.2：新增 ValidatorStatus.PENDING_IMPLEMENTATION 与 PipelineReport.pending_implementation
#      （Q7：「测试已落地、目标模块还不存在」是「待实现」，不是 validator crashed）。
#      1.1 的载荷里没有这一族字段：读到一条待实现记录的人只会看到"某个 checker 不在
#      served_checkers 里"，因此不能静默接受。
PIPELINE_SCHEMA_VERSION = "1.2"

# checker 的"非判定"口径（PipelineReport.judgements 的 outcome）：
#   empty      —— 验证器跑成了，但本次一条诊断都没归到任何规则（只计数、不判定）；
#   unanalyzed —— 验证器没能分析本次目标（命中注册表声明的"分析不成立"码，失败关闭）。
# "判定过、未发现"**不在这里**：它是 served_checkers 的成员，不需要再写一遍。
JUDGEMENT_EMPTY = "empty"
JUDGEMENT_UNANALYZED = "unanalyzed"
JUDGEMENT_OUTCOMES: Tuple[str, ...] = (JUDGEMENT_EMPTY, JUDGEMENT_UNANALYZED)

# 语言覆盖口径（PipelineReport.language_coverage）：
#   covered_by_rule_pack   —— 这门语言有 rule pack，验证器选择走原有路径；
#   not_covered_by_design  —— 这门语言在 validation/validators.yaml 的 uncovered_languages 里
#                             被显式声明为"按设计不取证"：这是**判定**，不是错误、也不是静默放行；
#   language_unknown       —— 上下文没有声明语言，无法选择验证器（仍然是失败关闭）。
# 为什么要有这条记录（07 号报告 P2）：只有 python 有 rule pack 时，非 python 目标在取证路径上
# 只能失败关闭——连"本次没有任何规则需要验证器证据"的文档写入也被一并拦下。缺的不是失败关闭，
# 而是"哪些语言按设计不取证"的表达；把它写成一条显式判定，账本才读得出"为什么这次没查"。
LANGUAGE_COVERAGE_DECLARED_IN = "validation/validators.yaml"
LANGUAGE_COVERAGE_COVERED = "covered_by_rule_pack"
LANGUAGE_COVERAGE_NOT_COVERED = "not_covered_by_design"
LANGUAGE_COVERAGE_UNKNOWN = "language_unknown"
# 受控集合：未知取值一律报错（PipelineReport 会校验），避免"新的覆盖口径"悄悄出现却没人读得懂。
LANGUAGE_COVERAGE_STATUSES: Tuple[str, ...] = (
    LANGUAGE_COVERAGE_COVERED,
    LANGUAGE_COVERAGE_NOT_COVERED,
    LANGUAGE_COVERAGE_UNKNOWN,
)

# 显式依赖（CLI --dependencies）在证据里的验证器身份：它也是一种证据来源，不是"没有证据"。
EXPLICIT_VALIDATOR_ID = "cli.explicit"
EXPLICIT_VALIDATOR_VERSION = "1.0"

# 本模块实现了哪些验证器。注册表里出现的 id 必须都在这里，否则拒绝运行——
# 这是"数据声明的能力"与"代码真的实现了"之间的对齐检查（tests/contract 钉住两者相等）。
KNOWN_VALIDATOR_IDS: FrozenSet[str] = frozenset(
    {
        "py.source",
        "py.ast",
        "py.depgraph",
        "py.docstring",
        "tool.ruff",
        "tool.mypy",
        "tool.pytest",
    }
)


class BuiltinError(RegistryError):
    """内置验证器执行失败（读不到、解析不了、索引不了）。"""


@dataclass(frozen=True)
class PipelineRequest:
    """一次验证请求的显式输入。"""

    target: str
    workspace: Path
    context: PolicyContext
    rules: RuleSet
    changed_files: Tuple[str, ...] = ()
    explicit_dependencies: Optional[Tuple[str, ...]] = None
    only: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidatorOutput:
    """单个验证器的执行结果（流水线内部结构）。"""

    status: ValidatorStatus
    evidence: Tuple[ValidationEvidence, ...] = ()
    dependencies: Tuple[DependencyFact, ...] = ()
    reason: Optional[str] = None
    tool: Optional[ToolInvocation] = None
    unmapped: int = 0
    payload: Mapping[str, Any] = field(default_factory=dict)
    served: Tuple[str, ...] = ()
    analysis_failure: Tuple[str, ...] = ()
    # Q7：status 为 pending_implementation 时，这里说得出"哪个测试模块因为哪个项目内
    # 缺失的目标而收集失败"。空清单 + 待实现状态 = 无理由的放行，流水线会失败关闭。
    pending: Tuple[PendingImplementation, ...] = ()


@dataclass(frozen=True)
class CheckerJudgement:
    """一个 checker 的"非判定"口径：为什么它没被判定，或为什么它只是跑过。

    存在这条记录的理由是 N17：修复前，ruff 在语法错误的文件上"没能分析"却记为 ok，
    39 条 style_lint 于是被记成"已判定 / 未发现"——账本要靠**缺席**才能表达"没查成"，
    而缺席与"判定过、未发现"长得一样。把两种非判定情形写成显式状态后，两者可区分。

    它**不是**判定结果，也不改变判定：allow / block 仍只由 Policy Engine 决定。
    """

    checker: str
    outcome: str
    validators: Tuple[str, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        if self.outcome not in JUDGEMENT_OUTCOMES:
            raise ValueError(
                "未知的判定口径 " + repr(self.outcome)
                + "；允许的取值只有 " + repr(list(JUDGEMENT_OUTCOMES))
            )

    def to_payload(self) -> Mapping[str, Any]:
        return {
            "checker": self.checker,
            "outcome": self.outcome,
            "validators": list(self.validators),
            "detail": self.detail,
        }


def language_coverage(registry: Any, language: Optional[str]) -> Mapping[str, Any]:
    """语言维度的显式判定：有 rule pack / 按声明不取证 / 语言未知。

    字段形状是接口（审计摘要的 passthrough 直接取它），因此键固定为
    `language` / `status` / `reason` / `declared_in`，status 取值落在
    LANGUAGE_COVERAGE_STATUSES 里。

    **失败关闭没有被放宽**：既没有 rule pack、也没被声明为"按设计不取证"的语言仍然
    抛 RegistryError（退出码 2）。"我们没声明过它"与"我们声明了不验证它"是两件事，
    前者不该被后者顺带放行（AGENTS 第 3/20/42 条）。
    """

    if language is None:
        return {
            "language": None,
            "status": LANGUAGE_COVERAGE_UNKNOWN,
            "reason": (
                "上下文没有声明语言：无法选择验证器（拒绝靠扩展名猜语言，"
                "见 AGENTS 核心约束 6），需要证据的规则按失败关闭处理"
            ),
            "declared_in": LANGUAGE_COVERAGE_DECLARED_IN,
        }

    token = canonical_identifier(language) or language
    if registry.packs_for(token):
        return {
            "language": token,
            "status": LANGUAGE_COVERAGE_COVERED,
            "reason": "",
            "declared_in": LANGUAGE_COVERAGE_DECLARED_IN,
        }

    declared = registry.uncovered(token)
    if declared is not None:
        return {
            "language": declared.language,
            "status": LANGUAGE_COVERAGE_NOT_COVERED,
            "reason": declared.reason,
            "declared_in": LANGUAGE_COVERAGE_DECLARED_IN,
        }

    raise RegistryError(
        "上下文声明的语言 " + token + " 没有任何 rule pack（已声明的语言："
        + ", ".join(sorted({pack.language for pack in registry.rule_packs}))
        + "），也没有在 " + LANGUAGE_COVERAGE_DECLARED_IN + " 的 uncovered_languages 里"
        "被声明为「按设计不取证」；拒绝在不了解该语言规则的情况下给出结论"
    )


@dataclass(frozen=True)
class PipelineReport:
    """一次流水线运行的完整报告。

    `language_coverage` 没有默认值：一份说不出"这次的语言是怎么被覆盖的"的报告，
    与"这次没查"长得一模一样（07 号报告 P2）。
    """

    language_coverage: Mapping[str, Any]
    schema_version: str = PIPELINE_SCHEMA_VERSION
    target: Optional[SourceDigest] = None
    language: Optional[str] = None
    checks: Tuple[str, ...] = ()
    validators: Tuple[ValidatorRecord, ...] = ()
    blockers: Tuple[Blocker, ...] = ()
    dependencies: Tuple[DependencyFact, ...] = ()
    evidence: Tuple[ValidationEvidence, ...] = ()
    served_checkers: Tuple[str, ...] = ()
    unmapped_findings: int = 0
    judgements: Tuple[CheckerJudgement, ...] = ()
    # Q7：「待实现」——工具跑成了、但这次的树还在构建中。它不是 served（没查成），
    # 也不是 blocker（不阻断），而是第三种可读状态：见 policy.evidence.PendingImplementation。
    pending_implementation: Tuple[PendingImplementation, ...] = ()
    truncated_evidence: int = 0
    selection: Mapping[str, Any] = field(default_factory=dict)
    environment: Mapping[str, str] = field(default_factory=dict)
    configs: Mapping[str, Optional[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # status 是受控集合：未知取值一律报错，不留"没人读得懂的新口径"
        status = self.language_coverage.get("status")
        if status not in LANGUAGE_COVERAGE_STATUSES:
            raise ValueError(
                "未知的语言覆盖状态 " + repr(status)
                + "；允许的取值只有 " + repr(list(LANGUAGE_COVERAGE_STATUSES))
            )

    @property
    def bundle(self) -> EvidenceBundle:
        return EvidenceBundle(
            target=self.target,
            dependencies=self.dependencies,
            evidence=self.evidence,
            validators=self.validators,
            blockers=self.blockers,
            served_checkers=self.served_checkers,
            pending_implementation=self.pending_implementation,
            unmapped_findings=self.unmapped_findings,
        ).normalize()

    def record(self, validator_id: str) -> Optional[ValidatorRecord]:
        for item in self.validators:
            if item.validator_id == validator_id:
                return item
        return None

    def to_payload(self) -> Mapping[str, Any]:
        return {
            "schema_version": self.schema_version,
            "target": None
            if self.target is None
            else {
                "file": self.target.file,
                "language": self.target.language,
                "sha256": self.target.sha256,
                "bytes": self.target.bytes,
                "lines": self.target.lines,
            },
            "language": self.language,
            "language_coverage": dict(self.language_coverage),
            "checks": list(self.checks),
            "validators": [item.to_payload() for item in self.validators],
            "blockers": [item.to_payload() for item in self.blockers],
            "dependencies": [item.to_payload() for item in self.dependencies],
            "evidence": [item.to_payload() for item in self.evidence],
            "served_checkers": list(self.served_checkers),
            "unmapped_findings": self.unmapped_findings,
            "judgements": [item.to_payload() for item in self.judgements],
            "pending_implementation": [
                item.to_payload() for item in self.pending_implementation
            ],
            "truncated_evidence": self.truncated_evidence,
            "selection": dict(self.selection),
            "environment": dict(self.environment),
            "configs": {key: value for key, value in self.configs.items()},
        }


def render_report(report: PipelineReport) -> str:
    """把一次运行的证据渲染成给人看的文本（判定部分由 policy.check 负责）。"""

    coverage = report.language_coverage
    lines = [
        "target: " + (report.target.file if report.target else "<unknown>"),
        "language: " + (report.language or "<unknown>"),
        "language_coverage: " + str(coverage.get("status")) + (
            "（" + str(coverage.get("reason")) + "）"
            if coverage.get("reason")
            else ""
        ),
        "checks: " + (", ".join(report.checks) or "<none>"),
        "validators:",
    ]
    for record in report.validators:
        detail = "" if record.reason is None else " (" + record.reason + ")"
        lines.append("  - " + record.validator + " " + record.status.value + detail)
    if report.blockers:
        lines.append("blockers (失败关闭):")
        for blocker in report.blockers:
            lines.append(
                "  - " + blocker.validator + " " + blocker.status.value + "：" + blocker.reason
            )
    if report.pending_implementation:
        lines.append("pending_implementation (待实现：覆盖它的测试这次跑不了):")
        for item in report.pending_implementation:
            lines.append(
                "  - " + item.validator + " " + ", ".join(item.checkers)
                + "：" + ", ".join(item.test_modules)
                + " 因项目内还不存在的 " + ", ".join(item.missing_targets) + " 无法收集"
            )
    if report.judgements:
        lines.append("judgements (非判定口径，不是\"判定过、未发现\"):")
        for note in report.judgements:
            lines.append(
                "  - " + note.checker + " " + note.outcome
                + "（" + ", ".join(note.validators) + "）：" + note.detail
            )
    if report.dependencies:
        lines.append("dependencies:")
        for fact in report.dependencies:
            lines.append(
                "  - " + fact.name + " <- " + (fact.module or "<declared>")
                + " (" + fact.kind.value + ", " + fact.resolution.value
                + (", line " + str(fact.line) if fact.line else "") + ")"
            )
    if report.evidence:
        lines.append("evidence:")
        for item in report.evidence:
            location = item.location
            where = "" if location is None else location.file + (
                ":" + str(location.line) if location.line else ""
            )
            lines.append(
                "  - [" + item.severity.value + "] " + (item.rule_id or "<unmapped>")
                + " " + where + " " + item.message
            )
    if report.unmapped_findings:
        lines.append(
            "unmapped: " + str(report.unmapped_findings) + " 条诊断没有对应的规则（不参与判定）"
        )
    return chr(10).join(lines)


class _RunState:
    """一次运行中的共享事实（波次之间传递），以及每条事实的来源验证器。"""

    def __init__(self) -> None:
        self.source: Optional[SourceFile] = None
        self.facts: Optional[ModuleFacts] = None
        self.dependencies: Optional[DependencyResult] = None


def run_pipeline(
    request: PipelineRequest,
    *,
    config: ValidationConfig,
    python: str = sys.executable,
    keep_temp: bool = False,
) -> PipelineReport:
    """执行一次完整流水线，返回报告（判定由调用方用 report.bundle 交给引擎）。"""

    context = request.context
    matched, _skipped = engine_module.matching_rules(request.rules, context)
    language = context.language

    needed: set[str] = set()
    for rule in matched:
        checker = rule.enforcement.checker
        if checker:
            needed.add(checker)

    registry = config.registry
    # 语言覆盖口径先算出来并进报告：它是"这次为什么查了 / 为什么没查"的一部分，
    # 不能只靠验证器记录里的**缺席**来表达（缺席与"判定过、未发现"长得一样）。
    coverage = language_coverage(registry, language)
    # 显式声明依赖时，依赖类验证器不再参与：证据来源是调用方的声明（记录在 cli.explicit）。
    skip = (
        frozenset({"forbidden_dependency"})
        if request.explicit_dependencies is not None
        else frozenset()
    )
    selected_specs, selection_blockers = _select_specs(
        registry,
        language=language,
        needed=needed,
        only=request.only,
        skip=skip,
        target=request.target,
        coverage=coverage,
    )

    changed_files = _validated_changed(request.changed_files)
    if changed_files != tuple(request.changed_files):
        request = replace(request, changed_files=changed_files)  # type: ignore[arg-type]

    run_id = uuid.uuid4().hex[:12]
    run_root = config.root / ".tmp" / "validators" / run_id
    state = _RunState()
    outputs: dict[str, ValidatorOutput] = {}
    statuses: dict[str, ValidatorStatus] = {}

    try:
        for wave in _waves(selected_specs, registry):
            runnable: list[ValidatorSpec] = []
            for spec in wave:
                blocked_by = [
                    name
                    for name in spec.requires
                    if statuses.get(name) in FAIL_CLOSED_STATUSES
                ]
                if blocked_by:
                    # 前置验证器没有跑成：本验证器不再执行，避免同一个根因产出多条阻断点
                    outputs[spec.id] = ValidatorOutput(
                        status=ValidatorStatus.NOT_SELECTED,
                        reason="前置验证器未成功：" + ", ".join(blocked_by),
                        served=spec.checkers,
                    )
                    statuses[spec.id] = ValidatorStatus.NOT_SELECTED
                    continue
                runnable.append(spec)

            if len(runnable) == 1:
                spec = runnable[0]
                outputs[spec.id] = _execute(
                    spec,
                    request=request,
                    config=config,
                    matched=matched,
                    state=state,
                    python=python,
                    run_root=run_root,
                )
                statuses[spec.id] = outputs[spec.id].status
                continue
            if not runnable:
                continue
            with ThreadPoolExecutor(max_workers=registry.defaults.max_parallel) as pool:
                futures = {
                    spec.id: pool.submit(
                        _execute,
                        spec,
                        request=request,
                        config=config,
                        matched=matched,
                        state=state,
                        python=python,
                        run_root=run_root,
                    )
                    for spec in runnable
                }
                for spec in runnable:
                    future = futures[spec.id]
                    try:
                        outputs[spec.id] = future.result()
                    except Exception as error:  # noqa: BLE001 - 线程里逃出来的异常也必须失败关闭
                        # _execute 自己已经兜底了；这里再兜一层是因为"兜底之外"的异常
                        # （目录准备、未来的新代码路径）会让整趟 run_pipeline 抛出去，
                        # 其余 future 的异常在 shutdown 时被丢掉——报告直接消失（复核发现）。
                        outputs[spec.id] = ValidatorOutput(
                            status=ValidatorStatus.CRASHED,
                            reason="验证器线程异常：" + type(error).__name__ + ": " + str(error),
                            served=spec.checkers,
                        )
                    statuses[spec.id] = outputs[spec.id].status
    finally:
        if not keep_temp:
            shutil.rmtree(run_root, ignore_errors=True)

    records: list[ValidatorRecord] = []
    blocked: list[Blocker] = list(selection_blockers)
    dependency_facts: list[DependencyFact] = []
    evidence: list[ValidationEvidence] = []
    served: set[str] = set()
    judgements: list[CheckerJudgement] = []
    pending_records: list[PendingImplementation] = []
    unmapped = 0
    selection: Mapping[str, Any] = {}

    evidence_limit = registry.defaults.max_evidence
    truncated_evidence = 0
    for spec in sorted(selected_specs, key=lambda item: item.id):
        output = outputs[spec.id]
        # P7 的两个口径必须分开读：declared = 注册表声明负责的（spec.checkers）；
        # served = 本次真的服务过的（适配器可以收窄，例如 pytest 退出码 5 时只服务
        # missing_tests：它的证据来自选择阶段，与"有没有用例被执行"无关）。
        checkers = output.served or spec.checkers
        # 判定口径只记"需要判定的 checker"（report.checks），避免把没规则用到的 checker
        # 也写成一条噪音记录。
        judged = tuple(sorted(checker for checker in checkers if checker in needed))
        validator = spec.id + "@" + spec.version
        if output.analysis_failure:
            # 工具说"这个文件我分析不了"：没有可判定的结果，必须显式写下来，
            # 不能靠"它不在 served_checkers 里"来表达（那与"判定过、未发现"长得一样）
            judgements.extend(
                CheckerJudgement(
                    checker=checker,
                    outcome=JUDGEMENT_UNANALYZED,
                    validators=(validator,),
                    detail=output.reason or "验证器未能分析本次目标",
                )
                for checker in judged
            )
        kept = output.evidence[:evidence_limit]
        dropped = len(output.evidence) - len(kept)
        truncated_evidence += dropped
        reason = output.reason
        if dropped:
            # 上限是资源保护，但"截断了多少条"必须写进记录，不能静默丢证据
            note = "证据超过上限 " + str(evidence_limit) + "，已截断 " + str(dropped) + " 条"
            reason = note if not reason else reason + "；" + note
        records.append(
            ValidatorRecord(
                validator_id=spec.id,
                validator_version=spec.version,
                kind=spec.kind,
                stage=spec.stage,
                status=output.status,
                critical=spec.critical,
                duration_ms=0 if output.tool is None else output.tool.duration_ms,
                reason=reason,
                tool=output.tool,
                evidence_count=len(kept),
                declared_checkers=tuple(sorted(spec.checkers)),
            )
        )
        dependency_facts.extend(output.dependencies)
        evidence.extend(kept)
        unmapped += output.unmapped
        if output.payload.get("selection"):
            selection = output.payload["selection"]
        if output.status in SUCCESS_STATUSES:
            served.update(checkers)
            if not kept and output.unmapped and judged:
                # 跑过、但一条诊断都没归到规则：诊断只计数、不判定（AGENTS 第 22 条），
                # 所以这一条必须显式写下来，否则它看起来就和"判定过、未发现"一样。
                judgements.extend(
                    CheckerJudgement(
                        checker=checker,
                        outcome=JUDGEMENT_EMPTY,
                        validators=(validator,),
                        detail="本次 " + str(output.unmapped)
                        + " 条诊断都没有规则归属（只计数、不判定）",
                    )
                    for checker in judged
                )
            continue
        if output.status is ValidatorStatus.PENDING_IMPLEMENTATION:
            # Q7：第三种状态。**不进 served_checkers**（没查成的不能记成查过了，AGENTS 50 / N17），
            # **也不产生 Blocker**（那不是"证据没拿到"，而是"这次的树还在构建中"）。
            # 同一验证器负责的其它 checker 照常记账：missing_tests 的证据来自选择阶段，
            # 与 pytest 能不能收集无关。
            if not output.pending:
                # 说不出"哪个测试模块因为什么查不了"的待实现 = 无理由的放行：失败关闭。
                blocked.append(
                    Blocker(
                        validator_id=spec.id,
                        validator_version=spec.version,
                        status=ValidatorStatus.CONFIG_ERROR,
                        reason=(
                            "验证器自报状态 pending_implementation，却没有给出待实现清单"
                            "（哪个测试模块、因哪个项目内缺失的目标）：拒绝把说不清理由的"
                            "状态当成通过"
                        ),
                        checkers=tuple(sorted(_blocked_checkers(spec, selected_specs, registry))),
                    )
                )
                continue
            pending_checkers = {
                checker for item in output.pending for checker in item.checkers
            }
            served.update(checker for checker in checkers if checker not in pending_checkers)
            pending_records.extend(output.pending)
            continue
        if spec.critical and output.status in FAIL_CLOSED_STATUSES:
            blocked.append(
                Blocker(
                    validator_id=spec.id,
                    validator_version=spec.version,
                    status=output.status,
                    reason=output.reason or "验证器没有跑成",
                    checkers=tuple(sorted(_blocked_checkers(spec, selected_specs, registry))),
                )
            )

    served.difference_update(
        {checker for blocker in blocked for checker in blocker.checkers}
    )

    if request.explicit_dependencies is not None:
        dependency_facts = [
            DependencyFact(
                name=name,
                module=None,
                kind=DependencyKind.DECLARED,
                resolution=DependencyResolution.DECLARED,
                file=request.target,
                validator=EXPLICIT_VALIDATOR_ID + "@" + EXPLICIT_VALIDATOR_VERSION,
                detail="由调用方显式声明（CLI --dependencies）",
            )
            for name in sorted(set(request.explicit_dependencies))
        ]
        records.append(
            ValidatorRecord(
                validator_id=EXPLICIT_VALIDATOR_ID,
                validator_version=EXPLICIT_VALIDATOR_VERSION,
                kind=ValidatorKind.BUILTIN,
                stage="dependency",
                status=ValidatorStatus.OK,
                critical=True,
                reason="依赖由调用方显式声明，未使用 AST / 依赖图证据",
                evidence_count=0,
                declared_checkers=("forbidden_dependency",),
            )
        )
        served.add("forbidden_dependency")
        # 只把 forbidden_dependency 从每条 blocker 的 checker 集合里摘掉，**不整条丢弃**：
        # 同一个 blocker 里可能还列着别的 checker（语言缺失的 CONFIG_ERROR 用的就是
        # checkers=tuple(sorted(needed))，某验证器服务多个 checker 时 _blocked_checkers 同理），
        # 而上面的 difference_update 已经把这些 checker 从 served 里删掉了——整条丢掉会让它们
        # 既不服务也不阻断，正是"没查和查了没问题看起来一样"的那类歧义（复核发现）。
        # 摘空了的 blocker 才丢弃（Blocker.checkers 有 min_length=1，空集合不可表示）。
        trimmed = [
            item.model_copy(
                update={
                    "checkers": tuple(
                        checker for checker in item.checkers if checker != "forbidden_dependency"
                    )
                }
            )
            for item in blocked
        ]
        blocked = [item for item in trimmed if item.checkers]

    return PipelineReport(
        language_coverage=coverage,
        target=None if state.source is None else state.source.digest,
        language=language,
        checks=tuple(sorted(needed)),
        validators=tuple(sorted(records, key=lambda item: item.validator)),
        blockers=tuple(sorted(blocked, key=lambda item: (item.validator, item.reason))),
        dependencies=tuple(sorted(dependency_facts, key=lambda item: item.sort_key)),
        evidence=tuple(sorted(evidence, key=lambda item: item.sort_key)),
        served_checkers=tuple(sorted(served)),
        unmapped_findings=unmapped,
        judgements=tuple(
            sorted(judgements, key=lambda item: (item.checker, item.outcome, item.validators))
        ),
        pending_implementation=tuple(sorted(pending_records, key=lambda item: item.sort_key)),
        truncated_evidence=truncated_evidence,
        selection=selection,
        environment={
            "python_version": platform.python_version(),
            "platform": platform.system().lower(),
            "implementation": platform.python_implementation().lower(),
        },
        configs={
            "registry": config_digest(config.registry_path),
            "project": config_digest(config.project_path),
            "test_layout": config_digest(config.layout_path),
        },
    )


def _validated_changed(files: Sequence[str]) -> Tuple[str, ...]:
    """校验变更集里的路径：越界或非法一律配置错误，绝不让它悄悄流进测试选择。"""

    from policy.models import PolicyContextError, normalize_repo_path

    cleaned: list[str] = []
    for item in files:
        try:
            cleaned.append(normalize_repo_path(str(item).replace("\\", "/")))
        except PolicyContextError as error:
            raise RegistryError("变更集里的路径不合法：" + str(error)) from error
    return tuple(sorted(set(cleaned)))


def _select_specs(
    registry: Any,
    *,
    language: Optional[str],
    needed: Sequence[str],
    only: Sequence[str],
    skip: FrozenSet[str] = frozenset(),
    target: str,
    coverage: Mapping[str, Any],
) -> Tuple[Tuple[ValidatorSpec, ...], list[Blocker]]:
    """按"命中的规则需要哪些 checker"挑选验证器，并补齐它们依赖的前置验证器。

    skip 里的 checker 由别处的证据负责（例如 CLI 显式声明的依赖），不再选验证器；
    没有任何验证器负责的 checker 会变成失败关闭的阻断点。
    """

    # 没有 rule pack 的语言在 language_coverage() 里已经分过流：声明过"按设计不取证"的
    # 落到这里按下面的规则处理；没声明过的在那里直接 RegistryError（失败关闭不放宽）。
    if coverage["status"] == LANGUAGE_COVERAGE_NOT_COVERED:
        # 按声明不取证 ≠ 放行：**没有任何规则需要验证器证据**时它是一条显式判定
        # （07 号报告 P2 的现场：所有规则都是 python 作用域，.md 目标一条都用不上）；
        # 一旦有规则需要某个 checker 的证据，就与"没有验证器为它提供证据"同样失败关闭。
        pending = sorted(set(needed) - set(skip))
        if not pending:
            return (), []
        return (), [
            Blocker(
                validator_id="pipeline",
                validator_version=PIPELINE_SCHEMA_VERSION,
                status=ValidatorStatus.NOT_SELECTED,
                reason=(
                    "语言 " + str(coverage["language"]) + " 按声明不取证（"
                    + LANGUAGE_COVERAGE_DECLARED_IN + " 的 uncovered_languages："
                    + str(coverage["reason"]) + "），但本次有规则需要 checker "
                    + checker + " 的证据；拒绝在证明不了的情况下放行"
                ),
                checkers=(checker,),
            )
            for checker in pending
        ]

    if not needed:
        return (), []

    if language is None:
        blocker = Blocker(
            validator_id="pipeline",
            validator_version=PIPELINE_SCHEMA_VERSION,
            status=ValidatorStatus.CONFIG_ERROR,
            reason=(
                "上下文没有声明语言，无法选择验证器（拒绝靠扩展名猜语言，见 AGENTS 核心约束 6）"
            ),
            checkers=tuple(sorted(needed)),
        )
        return (), [blocker]

    available = {spec.id: spec for spec in registry.validators_for_language(language)}
    if only:
        unknown = sorted(set(only) - set(available))
        if unknown:
            raise RegistryError(
                "请求的验证器不在该语言的 rule pack 里：" + ", ".join(unknown)
            )
        available = {name: available[name] for name in only}

    by_checker = registry.checkers_for_language(language)
    chosen: dict[str, ValidatorSpec] = {}
    blockers: list[Blocker] = []
    for checker in sorted(set(needed)):
        if checker in skip:
            continue
        owners = [name for name in by_checker.get(checker, ()) if name in available]
        if not owners:
            blockers.append(
                Blocker(
                    validator_id="pipeline",
                    validator_version=PIPELINE_SCHEMA_VERSION,
                    status=ValidatorStatus.NOT_SELECTED,
                    reason="没有验证器为 checker " + checker + " 提供证据（rule pack 未覆盖）",
                    checkers=(checker,),
                )
            )
            continue
        for name in owners:
            _add_with_requirements(available, name, chosen)
    return tuple(sorted(chosen.values(), key=lambda item: (registry.stage_index()[item.stage], item.id))), blockers


def _add_with_requirements(
    available: Mapping[str, ValidatorSpec], name: str, chosen: dict[str, ValidatorSpec]
) -> None:
    if name in chosen:
        return
    spec = available.get(name)
    if spec is None:
        return
    chosen[name] = spec
    for required in spec.requires:
        _add_with_requirements(available, required, chosen)


def _waves(specs: Sequence[ValidatorSpec], registry: Any) -> Tuple[Tuple[ValidatorSpec, ...], ...]:
    """按依赖深度分波：同一波内的验证器互不依赖，可以并行。"""

    by_id = {spec.id: spec for spec in specs}
    depth: dict[str, int] = {}

    def compute(spec: ValidatorSpec, seen: frozenset[str] = frozenset()) -> int:
        if spec.id in depth:
            return depth[spec.id]
        if spec.id in seen:
            raise RegistryError("验证器 requires 出现环：" + spec.id)
        value = 0
        for required in spec.requires:
            target = by_id.get(required)
            if target is None:
                continue
            value = max(value, compute(target, seen | {spec.id}) + 1)
        depth[spec.id] = value
        return value

    for spec in specs:
        compute(spec)
    buckets: dict[int, list[ValidatorSpec]] = {}
    for spec in specs:
        buckets.setdefault(depth[spec.id], []).append(spec)
    index = registry.stage_index()
    return tuple(
        tuple(sorted(buckets[level], key=lambda item: (index[item.stage], item.id)))
        for level in sorted(buckets)
    )


def _blocked_checkers(
    spec: ValidatorSpec, specs: Sequence[ValidatorSpec], registry: Any
) -> set[str]:
    """失败的验证器会让哪些 checker 不可判定：它自己的 + 依赖它的验证器所服务的。"""

    by_id = {item.id: item for item in specs}
    checkers = set(spec.checkers)
    for other in specs:
        if _depends_on(other, spec.id, by_id, seen=frozenset()):
            checkers |= set(other.checkers)
    return checkers


def _depends_on(
    spec: ValidatorSpec, target: str, by_id: Mapping[str, ValidatorSpec], *, seen: frozenset[str]
) -> bool:
    if spec.id in seen:
        return False
    if target in spec.requires:
        return True
    for required in spec.requires:
        parent = by_id.get(required)
        if parent is not None and _depends_on(parent, target, by_id, seen=seen | {spec.id}):
            return True
    return False


def _execute(
    spec: ValidatorSpec,
    *,
    request: PipelineRequest,
    config: ValidationConfig,
    matched: Sequence[Rule],
    state: _RunState,
    python: str,
    run_root: Path,
) -> ValidatorOutput:
    """执行一个验证器。内置的走本模块的实现，外部的走 adapters/。"""

    if spec.id not in KNOWN_VALIDATOR_IDS:
        return ValidatorOutput(
            status=ValidatorStatus.CONFIG_ERROR,
            reason="注册表声明了本实现没有的验证器 " + spec.id,
            served=spec.checkers,
        )

    tmp_dir = run_root / spec.id
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        # 临时目录建不出来（只读根 / ENOSPC / 路径过长）是失败关闭点：旧实现在 try 之外建目录，
        # 异常直接穿出 _execute（复核发现）。
        return ValidatorOutput(
            status=ValidatorStatus.CRASHED,
            reason="无法创建验证器临时目录：" + type(error).__name__ + ": " + str(error),
            served=spec.checkers,
        )
    served_rules = [rule for rule in matched if rule.enforcement.checker in spec.checkers]

    try:
        if spec.id == "py.source":
            return _run_source(spec, request=request, config=config, state=state)
        if spec.id == "py.ast":
            return _run_ast(spec, state=state)
        if spec.id == "py.depgraph":
            return _run_depgraph(spec, request=request, config=config, state=state)
        if spec.id == "py.docstring":
            return _run_docstring(spec, request=request, state=state, rules=served_rules)
        return _run_external(
            spec,
            request=request,
            config=config,
            rules=served_rules,
            python=python,
            tmp_dir=tmp_dir,
        )
    except RegistryError as error:
        return ValidatorOutput(
            status=ValidatorStatus.CONFIG_ERROR, reason=str(error), served=spec.checkers
        )
    except Exception as error:  # 内置验证器崩溃也要失败关闭，而不是让整条流水线抛出去
        return ValidatorOutput(
            status=ValidatorStatus.CRASHED,
            reason="验证器异常：" + type(error).__name__ + ": " + str(error),
            served=spec.checkers,
        )


def _run_source(
    spec: ValidatorSpec, *, request: PipelineRequest, config: ValidationConfig, state: _RunState
) -> ValidatorOutput:
    language = request.context.language
    if language is None:
        return ValidatorOutput(
            status=ValidatorStatus.CONFIG_ERROR, reason="上下文没有声明语言", served=spec.checkers
        )
    try:
        source = read_source(
            request.target,
            workspace=request.workspace,
            language=language,
            max_bytes=config.registry.defaults.max_source_bytes,
        )
    except SourceError as error:
        return ValidatorOutput(
            status=ValidatorStatus.FAILED, reason=str(error), served=spec.checkers
        )
    state.source = source
    return ValidatorOutput(
        status=ValidatorStatus.OK,
        reason="源码哈希 " + source.digest.sha256[:19],
        payload={"source": source.digest},
        served=spec.checkers,
    )


def _run_ast(spec: ValidatorSpec, *, state: _RunState) -> ValidatorOutput:
    if state.source is None:
        return ValidatorOutput(
            status=ValidatorStatus.FAILED, reason="没有源码事实（py.source 未成功）", served=spec.checkers
        )
    facts = parse_module(state.source.text)
    state.facts = facts
    if facts.syntax_error is not None:
        issue = facts.syntax_error
        location = ""
        if issue.line is not None:
            location = ":" + str(issue.line) + ("" if issue.column is None else ":" + str(issue.column))
        return ValidatorOutput(
            status=ValidatorStatus.FAILED,
            reason=(
                "语法错误 " + state.source.path + location + "：" + issue.message
                + "（解析不了的文件不能被判定为没有依赖问题）"
            ),
            served=spec.checkers,
        )
    return ValidatorOutput(
        status=ValidatorStatus.OK,
        reason=(
            "import " + str(len(facts.imports)) + " 条 / 调用 " + str(len(facts.calls))
            + " 条 / 定义 " + str(len(facts.definitions)) + " 个"
        ),
        served=spec.checkers,
    )


def _run_depgraph(
    spec: ValidatorSpec, *, request: PipelineRequest, config: ValidationConfig, state: _RunState
) -> ValidatorOutput:
    if state.facts is None or state.source is None:
        return ValidatorOutput(
            status=ValidatorStatus.FAILED, reason="没有模块事实（py.ast 未成功）", served=spec.checkers
        )
    index = build_module_index(request.workspace, config.project)
    result = build_dependencies(
        state.facts,
        target_path=state.source.path,
        profile=config.project,
        index=index,
        validator=spec.id + "@" + spec.version,
    )
    state.dependencies = result
    payload = {"dependency_graph": result.to_payload(), "indexed_modules": len(index.modules)}
    if result.unresolved:
        reasons = "；".join(
            (item.module or "<dynamic>") + "（" + item.reason + "）" for item in result.unresolved
        )
        return ValidatorOutput(
            status=ValidatorStatus.FAILED,
            dependencies=result.dependencies,
            reason="依赖无法静态解析，拒绝判定为没有依赖：" + reasons,
            payload=payload,
            served=spec.checkers,
        )
    return ValidatorOutput(
        status=ValidatorStatus.OK,
        dependencies=result.dependencies,
        reason="依赖 " + str(len(result.dependencies)) + " 条",
        payload=payload,
        served=spec.checkers,
    )


def _run_docstring(
    spec: ValidatorSpec,
    *,
    request: PipelineRequest,
    state: _RunState,
    rules: Sequence[Rule],
) -> ValidatorOutput:
    if state.facts is None:
        return ValidatorOutput(
            status=ValidatorStatus.FAILED, reason="没有模块事实（py.ast 未成功）", served=spec.checkers
        )
    owners = [rule for rule in rules if getattr(rule.rule, "missing_docstring", None) is not None]
    if not owners:
        return ValidatorOutput(status=ValidatorStatus.OK, reason="没有需要检查 docstring 的规则", served=spec.checkers)
    evidence = missing_docstring_evidence(
        state.facts,
        target_path=request.target,
        rules=owners,
        validator=spec.id + "@" + spec.version,
    )
    return ValidatorOutput(
        status=ValidatorStatus.FINDINGS if evidence else ValidatorStatus.OK,
        evidence=evidence,
        reason=None if evidence else "声明过的对象都有 docstring",
        served=spec.checkers,
    )


def _run_external(
    spec: ValidatorSpec,
    *,
    request: PipelineRequest,
    config: ValidationConfig,
    rules: Sequence[Rule],
    python: str,
    tmp_dir: Path,
) -> ValidatorOutput:
    if spec.tool is None:
        return ValidatorOutput(
            status=ValidatorStatus.CONFIG_ERROR, reason="external 验证器缺少 tool 声明", served=spec.checkers
        )
    probe = probe_tool(
        spec.tool,
        python=python,
        timeout_ms=config.registry.defaults.probe_timeout_ms,
        max_output_bytes=config.registry.defaults.max_output_bytes,
        workspace=request.workspace,
        tmp_dir=tmp_dir,
    )
    if not probe.ok:
        return ValidatorOutput(
            status=probe.status, reason=probe.reason, served=spec.checkers
        )

    if not rules:
        return ValidatorOutput(
            status=ValidatorStatus.OK,
            reason="没有需要该 checker 的规则",
            served=spec.checkers,
        )

    python_paths = tuple(request.workspace / root for root in config.project.python_roots)
    if spec.id == "tool.ruff":
        result = run_ruff(
            spec=spec,
            config=config,
            probe=probe,
            target_path=request.target,
            workspace=request.workspace,
            rules=rules,
            python=python,
            tmp_dir=tmp_dir,
            python_paths=python_paths,
        )
    elif spec.id == "tool.mypy":
        result = run_mypy(
            spec=spec,
            config=config,
            probe=probe,
            target_path=request.target,
            workspace=request.workspace,
            rules=rules,
            python=python,
            tmp_dir=tmp_dir,
            python_paths=python_paths,
        )
    elif spec.id == "tool.pytest":
        requires_changes = any(
            getattr(rule.rule, "missing_tests", None) is not None
            and rule.rule.missing_tests.changed_only
            for rule in rules
        ) or not any(getattr(rule.rule, "missing_tests", None) is not None for rule in rules)
        if not request.changed_files and requires_changes:
            return ValidatorOutput(
                status=ValidatorStatus.UNAVAILABLE,
                reason=(
                    "缺少变更集（--changed / git diff）：测试验证器需要知道这次改了什么，"
                    "没有变更集属于证据不足"
                ),
                served=spec.checkers,
            )
        result = run_pytest(
            spec=spec,
            config=config,
            probe=probe,
            target_path=request.target,
            workspace=request.workspace,
            rules=rules,
            python=python,
            tmp_dir=tmp_dir,
            changed_files=request.changed_files,
            python_paths=python_paths,
        )
    else:
        return ValidatorOutput(
            status=ValidatorStatus.CONFIG_ERROR,
            reason="没有为 " + spec.id + " 实现适配器",
            served=spec.checkers,
        )

    return _from_adapter(result, spec=spec)


def _from_adapter(result: AdapterResult, *, spec: ValidatorSpec) -> ValidatorOutput:
    return ValidatorOutput(
        status=result.status,
        evidence=result.evidence,
        reason=result.reason,
        tool=result.tool,
        unmapped=result.unmapped,
        payload=result.payload,
        served=result.served or spec.checkers,
        analysis_failure=result.analysis_failure,
        pending=result.pending,
    )
