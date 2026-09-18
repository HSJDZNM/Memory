"""验证器流水线：按规则选验证器 → 分波执行 → 聚合证据 → 交给 Policy Engine。

形状（对应 Phase 5 计划书第 6 步）：

    Code → Source → AST → Dependency → Docstring → Lint → Type → Tests → Evidence → Policy

要点：

- **按规则选择**：只有 scope 命中的规则需要的 checker 才会去跑对应验证器，验证器再按
  requires 补齐前置事实（源码 / AST）；没跑的验证器在报告里记 not_selected 与原因；
- **失败关闭**：critical 验证器没跑成（缺失 / 版本不符 / 超时 / 崩溃 / 配置错误 / 输出非法）
  会让它服务的 checker（以及依赖它的验证器所服务的 checker）整体不可判定，由引擎按 critical 阻断；
- **证据与判定分离**：流水线只产出证据与阻断点，"allow / block" 由 Policy Engine 决定；
- **确定性**：波次内并行执行，但证据、依赖、记录、阻断点都按稳定键排序，与完成顺序无关。
"""

from __future__ import annotations

import platform
import shutil
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
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
    SourceDigest,
    ToolInvocation,
    ValidationEvidence,
    ValidatorKind,
    ValidatorRecord,
    ValidatorStatus,
)
from policy.models import PolicyContext, Rule, RuleSet

from .adapters.base import AdapterResult, Probe, probe_tool
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
    "KNOWN_VALIDATOR_IDS",
    "PIPELINE_SCHEMA_VERSION",
    "BuiltinError",
    "PipelineReport",
    "PipelineRequest",
    "render_report",
    "run_pipeline",
]

PIPELINE_SCHEMA_VERSION = "1.0"

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


@dataclass(frozen=True)
class PipelineReport:
    """一次流水线运行的完整报告。"""

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
    selection: Mapping[str, Any] = field(default_factory=dict)
    environment: Mapping[str, str] = field(default_factory=dict)
    configs: Mapping[str, Optional[str]] = field(default_factory=dict)

    @property
    def bundle(self) -> EvidenceBundle:
        return EvidenceBundle(
            target=self.target,
            dependencies=self.dependencies,
            evidence=self.evidence,
            validators=self.validators,
            blockers=self.blockers,
            served_checkers=self.served_checkers,
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
            "checks": list(self.checks),
            "validators": [item.to_payload() for item in self.validators],
            "blockers": [item.to_payload() for item in self.blockers],
            "dependencies": [item.to_payload() for item in self.dependencies],
            "evidence": [item.to_payload() for item in self.evidence],
            "served_checkers": list(self.served_checkers),
            "unmapped_findings": self.unmapped_findings,
            "selection": dict(self.selection),
            "environment": dict(self.environment),
            "configs": {key: value for key, value in self.configs.items()},
        }


def render_report(report: PipelineReport) -> str:
    """把一次运行的证据渲染成给人看的文本（判定部分由 policy.check 负责）。"""

    lines = [
        "target: " + (report.target.file if report.target else "<unknown>"),
        "language: " + (report.language or "<unknown>"),
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
    )

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
                for name, future in futures.items():
                    outputs[name] = future.result()
                    statuses[name] = outputs[name].status
    finally:
        if not keep_temp:
            shutil.rmtree(run_root, ignore_errors=True)

    records: list[ValidatorRecord] = []
    blocked: list[Blocker] = list(selection_blockers)
    dependency_facts: list[DependencyFact] = []
    evidence: list[ValidationEvidence] = []
    served: set[str] = set()
    unmapped = 0
    selection: Mapping[str, Any] = {}

    for spec in sorted(selected_specs, key=lambda item: item.id):
        output = outputs[spec.id]
        checkers = output.served or spec.checkers
        records.append(
            ValidatorRecord(
                validator_id=spec.id,
                validator_version=spec.version,
                kind=spec.kind,
                stage=spec.stage,
                status=output.status,
                critical=spec.critical,
                duration_ms=0 if output.tool is None else output.tool.duration_ms,
                reason=output.reason,
                tool=output.tool,
                evidence_count=len(output.evidence),
                served_checkers=tuple(sorted(checkers)),
            )
        )
        dependency_facts.extend(output.dependencies)
        evidence.extend(output.evidence)
        unmapped += output.unmapped
        if output.payload.get("selection"):
            selection = output.payload["selection"]
        if output.status in SUCCESS_STATUSES:
            served.update(checkers)
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
                served_checkers=("forbidden_dependency",),
            )
        )
        served.add("forbidden_dependency")
        blocked = [item for item in blocked if "forbidden_dependency" not in item.checkers]

    return PipelineReport(
        target=None if state.source is None else state.source.digest,
        language=language,
        checks=tuple(sorted(needed)),
        validators=tuple(sorted(records, key=lambda item: item.validator)),
        blockers=tuple(sorted(blocked, key=lambda item: (item.validator, item.reason))),
        dependencies=tuple(sorted(dependency_facts, key=lambda item: item.sort_key)),
        evidence=tuple(sorted(evidence, key=lambda item: item.sort_key)),
        served_checkers=tuple(sorted(served)),
        unmapped_findings=unmapped,
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


def _select_specs(
    registry: Any,
    *,
    language: Optional[str],
    needed: Sequence[str],
    only: Sequence[str],
    skip: FrozenSet[str] = frozenset(),
    target: str,
) -> Tuple[Tuple[ValidatorSpec, ...], list[Blocker]]:
    """按"命中的规则需要哪些 checker"挑选验证器，并补齐它们依赖的前置验证器。

    skip 里的 checker 由别处的证据负责（例如 CLI 显式声明的依赖），不再选验证器；
    没有任何验证器负责的 checker 会变成失败关闭的阻断点。
    """

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
    tmp_dir.mkdir(parents=True, exist_ok=True)
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
        if not request.changed_files:
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
        served=spec.checkers,
    )
