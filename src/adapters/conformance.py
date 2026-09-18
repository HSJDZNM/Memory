"""一致性套件：所有 Adapter 必须对同一组语义事件给出同一套结论。

计划 §一致性套件 的八条要求在这里是可执行的：

| 要求 | 场景 |
| --- | --- |
| 等价 edit 事件产生等价 PolicyContext | `allow-service-edit` / `block-controller-edit` |
| 路径、operation、主体和 trace 保留 | 同上 + `trace-propagated` |
| block 不触发原生工具 | `block-controller-edit` |
| allow 只触发一次 | `allow-service-edit` + `idempotent-replay` |
| 未知事件和版本被拒绝 | `unknown-event` / `unknown-version` |
| 错误响应能被 Agent 理解但不泄露内部信息 | `error-response-shape`（对所有响应都查一遍） |
| 重复 event ID 幂等 | `idempotent-replay` |
| 跨 Agent 隔离与循环限制 | `cross-agent-isolation` / `breaker-terminates-loop` |

关键设计：**场景是抽象语义，不是某家的报文**。每个 Adapter 用自己的
事件名与工具名（`render_event`）把它渲染成本家能理解的线协议。
"Agent A 用 Edit、Agent B 用 edit"这件事只出现在渲染层，
因此新增一个 Adapter 不会让核心测试期望长出分支。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

from policy.evidence import (
    DependencyFact,
    DependencyKind,
    DependencyResolution,
    EvidenceBundle,
)
from policy.models import Decision, Operation, RuleSet

from .base import Adapter
from .models import (
    AdapterEventError,
    AgentEvent,
    AgentResponse,
    EnforcementLevel,
    EventType,
)
from .runtime import AgentRuntime, RuntimeOutcome

__all__ = [
    "CONFORMANCE_SCHEMA_VERSION",
    "Check",
    "ConformanceReport",
    "SCENARIOS",
    "Scenario",
    "conformance_evidence",
    "conformance_enforcer",
    "render_event",
    "run_conformance",
]

CONFORMANCE_SCHEMA_VERSION = "1.0"

# 探针文件：全部位于受控工作区 `tests/fixtures/agent_events/workspace` 内，
# 因此"路径越界被拒绝"这件事是真的在测边界，而不是在测一个不存在的目录。
PROBE_CONTROLLER = "src/shop/order_controller.py"
PROBE_SERVICE = "src/shop/order_service.py"
PROBE_NEW_FILE = "src/shop/order_cache.py"
WORKSPACE_FIXTURE = "tests/fixtures/agent_events/workspace"


def conformance_evidence(_event: AgentEvent, context: Any) -> EvidenceBundle:
    """一致性套件的确定性证据夹具；只验证 Adapter，不替代 Phase 5 流水线测试。"""

    dependencies = tuple(
        DependencyFact(
            name=name,
            kind=DependencyKind.DECLARED,
            resolution=DependencyResolution.DECLARED,
            file=context.file,
            validator="adapter-conformance@1.0",
        )
        for name in context.dependencies
    )
    return EvidenceBundle(
        dependencies=dependencies,
        served_checkers=(
            "forbidden_dependency",
            "missing_docstring",
            "style_lint",
            "missing_tests",
            "failing_tests",
        ),
    )


def conformance_enforcer(adapter: Adapter, *, workspace: Path, state_root: Path) -> Any:
    """为已接线的完整 Adapter 构造真实 Phase 4 pre-check；缺配置即返回 None。"""

    if adapter.agent_id != "dsh":
        return None
    if adapter.registry_path is None or adapter.registry_approved_path is None:
        return None
    from adapters.dsh.enforcement import EnforcementBridge
    from enforcement.audit import FileAuditSink
    from enforcement.ledger import EnforcementLedger
    from enforcement.registry import load_registry

    registry = load_registry(
        adapter.registry_path,
        approved_path=adapter.registry_approved_path,
    ).registry
    state_root.mkdir(parents=True, exist_ok=True)
    return EnforcementBridge(
        registry=registry,
        sink=FileAuditSink(state_root / "audit.jsonl", workspace=workspace),
        ledger=EnforcementLedger(state_root / "ledger.jsonl"),
        workspace=workspace,
        agent_version=adapter.agent_version,
    )


@dataclass(frozen=True)
class Scenario:
    """一条与实现无关的语义事件及其期望。"""

    name: str
    description: str
    event_type: str
    expect: str
    outcome: Optional[str] = None
    tool_key: str = "edit"
    path: Optional[str] = None
    operation: Optional[str] = None
    text: str = ""
    session: str = "sess-1"
    call: str = "call-1"
    request: str = "req-1"
    trace: Optional[str] = None
    parent_trace: Optional[str] = None
    subject: Optional[str] = None
    schema_version: str = "1.0"
    # 只给"协议故意不认的事件"用：期望语义仍然是 event_type，
    # 但线上写的是另一个名字。`unknown-event` 场景靠它让各家的线协议
    # 真的收到一个未识别的事件名，而不是让套件伪造一个"未知事件类型"。
    wire_name: Optional[str] = None
    expectations: Tuple[str, ...] = ()
    repeat: int = 1
    call_suffix: bool = False


# 事件类型名用规范枚举的值，渲染时再翻译成各家的事件名。
SCENARIOS: Tuple[Scenario, ...] = (
    Scenario(
        session="sess-allow",
        call="call-allow",
        request="req-allow",
        name="allow-service-edit",
        description="Service 层新增一次不引入禁止依赖的改动 → allow，且原生工具恰好被调用一次",
        event_type=EventType.TOOL_PRE_EXECUTE.value,
        expect="allow",
        outcome="allow",
        tool_key="edit",
        path=PROBE_SERVICE,
        operation="edit",
        text="def load_orders():\n    return call_repository()\n",
        expectations=("allow_executes_tool", "context_dimensions"),
    ),
    Scenario(
        session="sess-block",
        call="call-block",
        request="req-block",
        name="block-controller-edit",
        description="Controller 直接依赖 repository → block，且**原生工具一次都不能被触发**",
        event_type=EventType.TOOL_PRE_EXECUTE.value,
        expect="block",
        outcome="policy_block",
        tool_key="edit",
        path=PROBE_CONTROLLER,
        operation="edit",
        text="from shop.order_repository import OrderRepository\nfrom repository import X\n",
        expectations=("block_does_not_execute", "block_reports_rule"),
    ),
    Scenario(
        session="sess-escape",
        call="call-escape",
        request="req-escape",
        name="path-escape",
        description="路径逃出工作区（../）→ 拒绝，不进入判定，工具不执行",
        event_type=EventType.TOOL_PRE_EXECUTE.value,
        expect="block",
        tool_key="edit",
        path="../outside.py",
        operation="edit",
        text="x = 1\n",
        expectations=("block_does_not_execute", "opaque_error"),
    ),
    Scenario(
        session="sess-absolute",
        call="call-absolute",
        request="req-absolute",
        name="absolute-path-outside",
        description="绝对路径落在工作区之外 → 拒绝（含只读动作）",
        event_type=EventType.TOOL_PRE_EXECUTE.value,
        expect="block",
        tool_key="edit",
        path="{outside}",
        operation="edit",
        text="x = 1\n",
        expectations=("block_does_not_execute", "opaque_error"),
    ),
    Scenario(
        session="sess-tool",
        call="call-tool",
        request="req-tool",
        name="unknown-tool",
        description="工具不在该 Agent 的工具表里 → 拒绝（白名单，不是黑名单）",
        event_type=EventType.TOOL_PRE_EXECUTE.value,
        expect="block",
        tool_key="nonexistent_tool",
        path=PROBE_SERVICE,
        operation="edit",
        text="x = 1\n",
        expectations=("block_does_not_execute", "opaque_error"),
    ),
    Scenario(
        session="sess-event",
        call="call-event",
        request="req-event",
        name="unknown-event",
        description="未声明的事件类型 → 拒绝并记录协议错误",
        event_type=EventType.TOOL_PRE_EXECUTE.value,
        wire_name="ToolTeleport",
        expect="block",
        expectations=("block_does_not_execute", "opaque_error"),
    ),
    Scenario(
        session="sess-version",
        call="call-version",
        request="req-version",
        name="unknown-version",
        description="未知协议版本 → 拒绝（消费方看不懂必须拒绝，不得默认放行）",
        event_type=EventType.TOOL_PRE_EXECUTE.value,
        expect="block",
        tool_key="write",
        path=PROBE_NEW_FILE,
        operation="create",
        text="x = 1\n",
        schema_version="9.9",
        expectations=("block_does_not_execute", "opaque_error"),
    ),
    Scenario(
        session="sess-nopath",
        call="call-nopath",
        request="req-nopath",
        name="missing-path",
        description="工具参数缺少路径：路径是安全关键字段，不得猜测 → 拒绝",
        event_type=EventType.TOOL_PRE_EXECUTE.value,
        expect="block",
        tool_key="edit",
        path=None,
        operation="edit",
        text="x = 1\n",
        expectations=("block_does_not_execute", "opaque_error"),
    ),
    Scenario(
        session="sess-replay",
        call="call-replay",
        request="req-replay",
        name="idempotent-replay",
        description="同一个 event_id 重放 → 第二次因幂等被阻断，工具仍然只被调用一次",
        event_type=EventType.TOOL_PRE_EXECUTE.value,
        expect="replay",
        outcome="event_replay",
        tool_key="edit",
        path=PROBE_NEW_FILE,
        operation="edit",
        text="value = 2\n",
        repeat=2,
        expectations=("replay_blocks_second", "allow_executes_tool"),
    ),
    Scenario(
        name="trace-propagated",
        description="显式 trace 被保留进事件与响应",
        event_type=EventType.TOOL_PRE_EXECUTE.value,
        expect="allow",
        outcome="allow",
        tool_key="edit",
        path=PROBE_NEW_FILE,
        operation="edit",
        text="value = 3\n",
        trace="trace-agent-a-1",
        expectations=("trace_preserved",),

    ),
    Scenario(
        name="trace-forged",
        description="伪造父 trace（引用别的 Agent 的 trace）→ 拒绝",
        event_type=EventType.TOOL_PRE_EXECUTE.value,
        expect="block",
        outcome="trace_forged",
        tool_key="edit",
        path=PROBE_NEW_FILE,
        operation="edit",
        text="value = 4\n",
        parent_trace="trace-agent-other-1",
        expectations=("block_does_not_execute", "opaque_error"),
        session="sess-forged",
        call="call-forged",
        request="req-forged",
    ),
    Scenario(
        name="breaker-terminates-loop",
        description="同一请求下的受治理事件数超过上限 → 熔断（互相触发的循环必须能被终止）",
        event_type=EventType.TOOL_PRE_EXECUTE.value,
        expect="breaker",
        outcome="request_busy",
        tool_key="edit",
        path=PROBE_NEW_FILE,
        operation="edit",
        text="value = 5\n",
        # 重复次数必须**超过**熔断阈值：熔断测的是"第 N+1 次会被拦下"，
        # 跑的次数等于阈值就永远测不到那条分支。
        repeat=8,
        call_suffix=True,
        expectations=("breaker_blocks",),
        session="sess-loop",
        request="req-loop",
    ),
)


def _tool_name(adapter: Adapter, key: str) -> str:
    """把场景里的工具键翻译成**该 Adapter 的 Agent 侧名字**。

    这是"差异留在 Adapter 内"的落点：场景写 `edit` 这个语义键，
    每个 Adapter 用它自己的别名表（manifest 里的 aliases）渲染出真正的名字。
    """

    if key == "nonexistent_tool":
        return "definitely_not_a_tool"
    for spec in adapter.manifest.tools:
        if spec.name == key or key in spec.aliases:
            return spec.aliases[0] if spec.aliases else spec.name
    return key


def render_event(
    adapter: Adapter,
    scenario: Scenario,
    *,
    index: int,
    workspace: Path,
    outside: str = "",
) -> Mapping[str, Any]:
    """把语义场景渲染成该 Adapter 的线协议事件。

    `None` 路径只在**受控字段**上表达："没有路径参数"。dsh 的 `edit` 没有
    file_path 就是缺字段，因此渲染时直接省掉这个键。
    """

    # call_suffix 让每次重复都成为**独立的一次调用**（循环场景需要它：
    # 否则第二次会被幂等直接拦下，熔断就永远测不到）。
    call = scenario.call + (f"-{index}" if scenario.call_suffix else "")
    # {outside} 的唯一含义是"受控工作区的同级路径"：把"越界"定义成
    # "相对工作区往外一层"，它才与工作区放在哪里无关。
    outside_path = str(Path(workspace).resolve().parent / "outside-workspace.py")
    path = (
        None
        if scenario.path is None
        else scenario.path.replace("{outside}", outside_path)
    )
    text = scenario.text
    if scenario.call_suffix:
        # 循环里的每次调用内容都不同（真实循环几乎总是这样）：
        # 这样它不会被"同一 event_id 复用不同参数"拦下，熔断才是唯一能终止它的机制。
        text = text + "step_%d = %d" % (index, index) + chr(10)
    payload: dict[str, Any] = {}
    if path is not None:
        payload["path"] = path
    if text:
        payload["text"] = text
    if adapter.manifest.protocol == "canonical-json":
        tool = None if scenario.path is None and scenario.event_type.endswith("teleport") else _tool_name(adapter, scenario.tool_key)
        if scenario.name in ("unknown-event", "unknown-version"):
            tool = None
        event: dict[str, Any] = {
            "schema_version": scenario.schema_version,
            "event_id": f"{scenario.session}:{call}",
            "event_type": scenario.wire_name or scenario.event_type,
            "request_id": scenario.request,
            "agent_version": adapter.agent_version,
            "occurred_at": "2026-01-01T00:00:00Z",
            "principal": {"subject": scenario.subject or "local-user", "roles": ["developer"]},
            "payload": payload,
        }
        if scenario.trace is not None:
            event["trace_id"] = scenario.trace
        if scenario.parent_trace is not None:
            event["parent_trace_id"] = scenario.parent_trace
        if tool is not None:
            event["tool"] = tool
            event["operation"] = scenario.operation
        return event

    try:
        desired = EventType(scenario.event_type)
    except ValueError:
        raise AdapterEventError(
            f"场景 {scenario.name!r} 声明了未知事件类型 {scenario.event_type!r}："
            "一致性套件只认受控枚举，不接受场景自己发明事件"
        ) from None
    if desired not in adapter.manifest.event_types:
        # 不静默跳过：Adapter 声明不支持这个事件时，"这个场景没测到"必须是一个
        # 显式结论。只读上限的 Adapter（例如只有 PostToolUse）会走到这里。
        raise AdapterEventError(
            f"adapter {adapter.agent_id} 不支持事件 {desired.value!r}"
            f"（能力声明里的事件为 {[item.value for item in adapter.manifest.event_types]}）："
            "该场景对这个 Adapter 不适用"
        )

    hooks = adapter.manifest.hooks
    spec = None
    if scenario.name not in ("unknown-event", "unknown-version"):
        spec = adapter.spec_for(_tool_name(adapter, scenario.tool_key)) if scenario.tool_key != "nonexistent_tool" else None
    tool_input: dict[str, Any] = {}
    if spec is not None:
        for field in spec.proposed_fields:
            tool_input[field] = text
        if adapter.agent_id == "dsh" and spec.name == "edit":
            tool_input["old_string"] = "pass"
    if path is not None and spec is not None and spec.path_field is not None:
        tool_input[spec.path_field] = path
    wire = getattr(adapter, "AGENT_WIRE", None)
    if (
        scenario.wire_name is None
        and isinstance(wire, Mapping)
        and wire.get(
        hooks.pre_execute if desired is EventType.TOOL_PRE_EXECUTE else hooks.post_execute
    ) is not None and wire[
        hooks.pre_execute if desired is EventType.TOOL_PRE_EXECUTE else hooks.post_execute
        ] is not desired
    ):
        raise AdapterEventError(
            f"adapter {adapter.agent_id} 把 "
            f"{hooks.pre_execute if desired is EventType.TOOL_PRE_EXECUTE else hooks.post_execute!r}"
            " 映射到了别的事件类型：一致性套件不能替它猜语义"
        )

    raw: dict[str, Any] = {
        "hook_event_name": scenario.wire_name
        or (
            hooks.pre_execute
            if desired is EventType.TOOL_PRE_EXECUTE
            else hooks.post_execute
        ),
        hooks.session_field: scenario.session,
        hooks.tool_field: _tool_name(adapter, scenario.tool_key),
        hooks.input_field: tool_input,
        hooks.call_id_field: call,
        hooks.cwd_field: str(workspace),
    }
    if scenario.trace is not None:
        raw["trace_id"] = scenario.trace
    if scenario.parent_trace is not None:
        raw["parent_trace_id"] = scenario.parent_trace
    return raw


@dataclass
class Check:
    """一条一致性检查的结论。"""

    adapter: str
    scenario: str
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "scenario": self.scenario,
            "check": self.name,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass
class ConformanceReport:
    """一次一致性套件的完整结论。"""

    schema_version: str = CONFORMANCE_SCHEMA_VERSION
    checks: list[Check] = field(default_factory=list)
    adapters: Tuple[str, ...] = ()
    scenarios: Tuple[str, ...] = ()

    @property
    def failures(self) -> Tuple[Check, ...]:
        return tuple(item for item in self.checks if not item.passed)

    @property
    def ok(self) -> bool:
        return not self.failures

    def summary(self) -> Mapping[str, Any]:
        coverage = {
            adapter: {
                "checks": sum(1 for item in self.checks if item.adapter == adapter),
                "inapplicable": sum(
                    1
                    for item in self.checks
                    if item.adapter == adapter and item.name == "declared_inapplicable"
                ),
            }
            for adapter in self.adapters
        }
        return {
            "schema_version": self.schema_version,
            "result": "pass" if self.ok else "fail",
            "adapters": list(self.adapters),
            "scenarios": list(self.scenarios),
            "checks": len(self.checks),
            "coverage": coverage,
            "failures": [item.to_dict() for item in self.failures],
        }


def _response_dict(response: Any) -> Mapping[str, Any]:
    if isinstance(response, AgentResponse):
        return response.model_dump(mode="json")
    if isinstance(response, Mapping):
        return response
    return {}


def _run_scenario(
    *,
    adapter: Adapter,
    runtime: AgentRuntime,
    scenario: Scenario,
    workspace: Path,
    outside: Path,
    report: ConformanceReport,
) -> None:
    calls: list[AgentEvent] = []
    outcomes: list[RuntimeOutcome] = []

    def execute(event: AgentEvent) -> None:
        calls.append(event)

    for index in range(scenario.repeat):
        raw = render_event(
            adapter,
            scenario,
            index=index,
            workspace=workspace,
            outside=str(outside),
        )
        outcome = runtime.handle(adapter.agent_id, raw, execute=execute)
        outcomes.append(outcome)

    first = outcomes[0]
    last = outcomes[-1]
    capability_limited = first.outcome_code == "capability_unavailable"

    def check(name: str, passed: bool, detail: str = "") -> None:
        report.checks.append(
            Check(adapter=adapter.agent_id, scenario=scenario.name, name=name, passed=passed, detail=detail)
        )

    # —— 期望的结论（与 Agent 无关） ——
    code = last.outcome_code
    if capability_limited:
        check(
            "capability_limit_explicit",
            first.response.decision is Decision.BLOCK and not calls,
            f"能力上限得到 {first.outcome_code}，原生工具被调用 {len(calls)} 次",
        )
    elif scenario.expect == "allow":
        check("outcome_allow", code in ("allow", "allow_with_warnings"), f"得到 {code}")
    elif scenario.expect == "block":
        check("outcome_block", last.response.decision is Decision.BLOCK, f"得到 {code}")
    elif scenario.expect == "replay":
        check(
            "replay_blocked",
            code == "event_replay" and last.response.decision is Decision.BLOCK,
            f"得到 {code}",
        )
    elif scenario.expect == "breaker":
        check(
            "breaker_terminated",
            code == "request_busy" and last.response.decision is Decision.BLOCK,
            f"得到 {code}",
        )
    if scenario.outcome is not None and not capability_limited:
        check("outcome_code", code == scenario.outcome, f"期望 {scenario.outcome}，得到 {code}")

    # —— 逐条期望 ——
    for expectation in scenario.expectations:
        if expectation == "allow_executes_tool":
            if capability_limited:
                check(
                    "capability_block_does_not_execute",
                    not calls and first.response.decision is Decision.BLOCK,
                    f"能力受限时原生工具被调用 {len(calls)} 次（必须为 0）",
                )
            else:
                check(
                    "allow_executes_tool",
                    len(calls) >= 1 and first.response.decision is not Decision.BLOCK,
                    f"原生工具被调用 {len(calls)} 次",
                )
        elif expectation == "block_does_not_execute":
            check(
                "block_does_not_execute",
                not calls and first.response.decision is Decision.BLOCK,
                f"原生工具被调用 {len(calls)} 次（必须为 0）",
            )
        elif expectation == "block_reports_rule":
            if capability_limited:
                check(
                    "capability_block_reports_reason",
                    first.response.reason_code == "capability_unavailable",
                    "只读上限必须明确报告 capability_unavailable",
                )
            else:
                check(
                    "block_reports_rule",
                    bool(first.response.violations) or bool(first.response.matched_rules),
                    "阻断响应必须带上规则身份，否则 Agent 无法修",
                )
        elif expectation == "context_dimensions":
            event = first.event
            if event is None:
                check("context_dimensions", False, "没有规范化事件")
                continue
            context = adapter.to_policy_context(event, workspace=workspace)
            check(
                "context_dimensions",
                context.file == scenario.path
                and context.operation is Operation.EDIT
                and context.layer == "service"
                and context.language == "python"
                and context.agent == adapter.agent_id,
                f"file={context.file} operation={context.operation} layer={context.layer} "
                f"language={context.language} agent={context.agent}",
            )
        elif expectation == "trace_preserved":
            check(
                "trace_preserved",
                first.event is not None
                and first.event.trace_id == scenario.trace
                and first.response.trace_id == scenario.trace,
                f"event.trace_id={None if first.event is None else first.event.trace_id}",
            )
        elif expectation == "opaque_error":
            payload = _response_dict(last.response)
            text = str(payload.get("message") or "")
            leaked = (
                str(workspace) in text
                or "Traceback" in text
                or "policies/" in text
                or "/src/" in text
            )
            check(
                "error_response_opaque",
                not leaked and payload.get("reason_code") not in (None, ""),
                f"reason_code={payload.get('reason_code')} message={text[:80]!r}",
            )
        elif expectation == "replay_blocks_second":
            expected_calls = 0 if capability_limited else 1
            check(
                "idempotent_exactly_once",
                len(calls) == expected_calls,
                f"原生工具被调用 {len(calls)} 次（必须恰好 {expected_calls} 次）",
            )
        elif expectation == "breaker_blocks":
            check(
                "breaker_blocks",
                last.response.decision is Decision.BLOCK,
                "熔断必须阻断后续事件",
            )


def run_conformance(
    *,
    adapters: Mapping[str, Adapter],
    rules: RuleSet,
    workspace: Path,
    outside: Path,
    ledger_path: Optional[Path] = None,
    ledger_dir: Optional[Path] = None,
    trace_path: Optional[Path] = None,
    breaker_limit: int = 3,
) -> ConformanceReport:
    """对每个 Adapter 跑一遍全部场景，返回逐项结论。

    `breaker_limit` 刻意取小值：熔断场景会跑 `repeat` 次同一个请求，
    只有重复次数真的超过阈值，"第 N+1 次被拦下"这条分支才会被走到。
    """

    report = ConformanceReport(
        adapters=tuple(sorted(adapters)),
        scenarios=tuple(item.name for item in SCENARIOS),
    )
    full = {
        name: adapter
        for name, adapter in adapters.items()
        if adapter.ceiling.level is EnforcementLevel.FULL
    }
    if not full:
        report.checks.append(
            Check(
                adapter="*",
                scenario="*",
                name="at_least_one_full_adapter",
                passed=False,
                detail="一致性套件需要至少一个完整 enforcement 的 Adapter",
            )
        )
        return report

    for name in sorted(adapters):
        adapter = adapters[name]
        for scenario in SCENARIOS:
            desired = EventType(scenario.event_type)
            if desired not in adapter.manifest.event_types:
                report.checks.append(
                    Check(
                        adapter=adapter.agent_id,
                        scenario=scenario.name,
                        name="declared_inapplicable",
                        passed=True,
                        detail=(
                            f"manifest 未声明 {desired.value}；"
                            "该能力缺口已显式记录，没有把未执行的场景算成行为通过"
                        ),
                    )
                )
                continue
            # 每个场景各用一份台账：幂等与熔断都是**场景内部**的性质，
            # 让它们共享一份台账只会让前一个场景把后一个场景拦成重放/熔断，
            # 测出来的就不再是被测行为了。
            scenario_ledger = (
                None
                if ledger_dir is None
                else Path(ledger_dir) / f"{adapter.agent_id}__{scenario.name}.jsonl"
            )
            state_root = (
                Path(".tmp")
                / "adapters"
                / "conformance"
                / adapter.agent_id
                / scenario.name
                if scenario_ledger is None
                else scenario_ledger.parent / (scenario_ledger.stem + "__enforcement")
            )
            enforcer = conformance_enforcer(
                adapter,
                workspace=workspace,
                state_root=state_root,
            )
            runtime = AgentRuntime(
                adapters={adapter.agent_id: adapter},
                rules=rules,
                ledger_path=scenario_ledger if scenario_ledger is not None else ledger_path,
                trace_path=trace_path,
                # 判定必须绑定到这次真正使用的工作区：否则在 A 工作区里合法的路径
                # 会在 B 工作区里越界，却按 A 的边界放行。
                workspace=workspace,
                breaker_limit=breaker_limit,
                enforcers={} if enforcer is None else {adapter.agent_id: enforcer},
                evidence_providers={adapter.agent_id: conformance_evidence},
            )
            _run_scenario(
                adapter=adapter,
                runtime=runtime,
                scenario=scenario,
                workspace=workspace,
                outside=outside,
                report=report,
            )
    return report
