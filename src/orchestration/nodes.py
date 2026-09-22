"""节点：每个节点单一职责，输入输出有 schema。

阶段计划 §3：`每个节点单一职责，输入输出有 schema。Policy Retrieval 只取得上下文；
Validation 只提交证据；Repair 只基于结构化 violation 规划修复。`

因此：

- `policy_retrieval` **只**取上下文（不判定、不改文件）；
- `validation` **只**提交证据并读回结构化 Decision（不解释自然语言、不猜结论）；
- `implementation` / `repair` 只提出一次**受治理的**改动：先问平台（evaluate），
  再交给 Tool Runner（Phase 4 受控执行链）。没有平台判定就不动手；
- `repair` 的输入只有 `ValidationSummary.violations`——正文、日志与工具返回值都不参与规划；
- 节点返回**新状态**：正文（需求全文、文件内容）不进状态，只留摘要与引用；
- 节点不自己决定"下一步去哪"：它只给一个路由标签，分支由 `routers` 决定。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol, Tuple, runtime_checkable

from .approvals import ApprovalGate
from .client import (
    DecisionOutcome,
    EvaluateCall,
    PolicyClient,
    RetrieveCall,
    ValidateCall,
)
from .errors import (
    ApprovalError,
    NodeContractError,
    PlatformUnavailableError,
)
from .limits import LimitKind, charge
from .models import (
    ArtifactKind,
    ArtifactRef,
    FailureCode,
    GraphState,
    NodeId,
    NodeRun,
    PlanStep,
    PolicyTraceRef,
    RunStatus,
    StageStatus,
    ValidationSummary,
    canonical_digest,
)
from .tools import ToolOutcome, ToolRequest, ToolRunner

__all__ = [
    "Change",
    "ChangeAuthor",
    "NODES",
    "NodeContext",
    "NodeOutcome",
    "NodeFn",
    "ScriptedAuthor",
    "TaskSpec",
]

# 大纲与流程目标：受治理的写入工具（Phase 4 注册表里的 id）与动作之间的关系。
EDIT_TOOL = "orc.fs.edit"
WRITE_TOOL = "orc.fs.write"
PROTECTED_EDIT_TOOL = "orc.policy.edit"
PROTECTED_WRITE_TOOL = "orc.policy.write"


@dataclass(frozen=True)
class Change:
    """一次候选改动。`content` 与 `replacement` 二选一（写整文件 / 替换片段）。"""

    path: str
    summary: str = ""
    replacement: Optional[str] = None
    old: Optional[str] = None
    content: Optional[str] = None
    tokens: int = 0
    cost_units: int = 0

    def digest(self) -> str:
        material = {
            "path": self.path,
            "summary": self.summary,
            "old": self.old,
            "replacement": self.replacement,
            "content": self.content,
        }
        return canonical_digest(material)

    @property
    def tool_id(self) -> str:
        if self.old is not None:
            return PROTECTED_EDIT_TOOL if self.path.startswith("policies/") else EDIT_TOOL
        return PROTECTED_WRITE_TOOL if self.path.startswith("policies/") else WRITE_TOOL

    def params(self) -> dict[str, Any]:
        if self.old is not None:
            return {
                "file_path": self.path,
                "old_string": self.old,
                "new_string": self.replacement or "",
            }
        return {"file_path": self.path, "content": self.content or ""}


@runtime_checkable
class ChangeAuthor(Protocol):
    """候选改动的来源（真实系统里是模型；这里是可替换的端口）。"""

    def propose(self, *, task: "TaskSpec", state: GraphState, round_index: int) -> Change: ...


class ScriptedAuthor:
    """按轮次回答的确定性作者：第 0 轮给"会失败"的改动，第 1 轮给修好的改动。

    它是**测试与闭环**用的实现：真实作者（模型）不在本阶段内，替换它不影响任何节点契约。
    """

    def __init__(self, changes: Any) -> None:
        if isinstance(changes, Mapping):
            self._by_round: Mapping[int, Change] = dict(changes)
            self._sequence: Tuple[Change, ...] = ()
        else:
            self._by_round = {}
            self._sequence = tuple(changes)

    def propose(self, *, task: "TaskSpec", state: GraphState, round_index: int) -> Change:
        if self._by_round:
            change = self._by_round.get(round_index)
        else:
            change = self._sequence[round_index] if round_index < len(self._sequence) else None
        if change is None:
            raise NodeContractError(
                f"没有第 {round_index} 轮的候选改动：拒绝编造一次修改", node=state.stage
            )
        return change


@dataclass(frozen=True)
class TaskSpec:
    """任务级的显式输入。**正文只在内存里**：状态里只放摘要与验收条目。"""

    task_id: str
    target: str
    requirement: str
    layer: str
    language: str = "python"
    module: Optional[str] = None
    query: str = ""
    principal: Mapping[str, Any] = field(default_factory=dict)
    acceptance: Tuple[str, ...] = ()
    trace_id: Optional[str] = None

    def requirement_digest(self) -> str:
        return canonical_digest({"target": self.target, "requirement": self.requirement})


@dataclass
class NodeContext:
    """节点运行时依赖：全部显式注入，节点自己不构造客户端、不读环境变量。"""

    task: TaskSpec
    client: PolicyClient
    runner: ToolRunner
    author: ChangeAuthor
    approvals: ApprovalGate
    workspace: Path
    clock: Callable[[], float] = time.monotonic
    # 写前日志：副作用之前把"意图"刷进 checkpoint，崩溃后才有可能被发现（由引擎注入）。
    commit: Optional[Callable[[GraphState], None]] = None

    def context_payload(self, *, operation: str = "edit") -> dict[str, Any]:
        payload: dict[str, Any] = {
            "file": self.task.target,
            "layer": self.task.layer,
            "language": self.task.language,
            "operation": operation,
        }
        if self.task.module:
            payload["module"] = self.task.module
        return payload


@dataclass(frozen=True)
class NodeOutcome:
    state: GraphState
    label: str
    detail: str = ""


NodeFn = Callable[[GraphState, NodeContext], NodeOutcome]


# --------------------------------------------------------------------- 工具函数


def _request_id(state: GraphState, node: NodeId) -> str:
    """确定性的 request_id：同一任务、同一节点、同一轮次 → 同一个 ID（幂等可重放）。"""

    return f"{state.task_id}:{node.value}:{state.counters.repair_rounds}"


def _action_id(state: GraphState, change: Change) -> str:
    digest = change.digest().split(":", 1)[-1][:16]
    return f"{state.task_id}:{state.counters.repair_rounds}:{digest}"


def _record_run(
    state: GraphState,
    node: NodeId,
    *,
    label: str,
    status: StageStatus,
    key: str,
    outcome: Any,
    detail: str = "",
    failure: Optional[FailureCode] = None,
) -> GraphState:
    run = NodeRun(
        node=node,
        attempt=1,
        status=status,
        idempotency_key=key,
        outcome_digest=canonical_digest(outcome),
        label=label,
        failure_code=failure,
        detail=detail[:400],
    )
    return state.replace(runs=state.runs + (run,))


def _pending_run(state: GraphState, node: NodeId) -> Optional[NodeRun]:
    """该节点是否有一笔"已经开工但没结算"的副作用记录。

    **按节点而不是按幂等键判断**：副作用开始后崩溃，恢复时计数器可能已经前进，
    这一轮的候选改动未必与上一轮同名；"这个节点开过工却没结算"是比键更可靠的事实。
    """

    for run in reversed(state.runs):
        if run.node is node and run.status is StageStatus.PENDING:
            return run
    return None


def _intent(state: GraphState, node: NodeId, key: str, *, bound: Any) -> GraphState:
    """**先记账再动手**：副作用之前写下意图，崩溃后才有可能被如实发现。"""

    run = NodeRun(
        node=node,
        attempt=1,
        status=StageStatus.PENDING,
        idempotency_key=key,
        outcome_digest=canonical_digest({"intent": bound}),
        label="intent",
        detail="副作用意图（尚未结算）",
    )
    return state.replace(runs=state.runs + (run,))


def _settle(state: GraphState, node: NodeId, key: str) -> GraphState:
    """结算：抹掉同键的意图记录，后续由 `_record_run` 写最终结果。"""

    kept = tuple(
        run
        for run in state.runs
        if not (
            run.node is node
            and run.idempotency_key == key
            and run.status is StageStatus.PENDING
        )
    )
    return state.replace(runs=kept)


def _latest_failure(state: GraphState) -> Optional[ValidationSummary]:
    """最近一次验证/测试的摘要：按节点执行顺序取最新，而不是按字段优先级猜。"""

    for run in reversed(state.runs):
        if run.node is NodeId.TESTING and state.test_validation is not None:
            return state.test_validation
        if run.node is NodeId.VALIDATION and state.validation is not None:
            return state.validation
    return state.test_validation or state.validation


def _unsettled(state: GraphState, node: NodeId, *, key: str = "") -> NodeOutcome:
    """副作用状态未知：停止，交给人；不重放、也不假装成功。"""

    unknown = state.replace(
        **_failure_updates(
            FailureCode.SIDE_EFFECT_UNKNOWN, node, "上一次尝试的副作用状态未知：需要人工核对"
        ),
        notes=state.notes + (f"{node.value} 有未结算的副作用记录：停止并交给人",),
    )
    unknown = _record_run(
        unknown,
        node,
        label="needs_human",
        status=StageStatus.NEEDS_HUMAN,
        key=key or f"{state.task_id}:{node.value}:unsettled",
        outcome={"side_effect": "unknown"},
        detail="副作用状态未知",
        failure=FailureCode.SIDE_EFFECT_UNKNOWN,
    )
    return NodeOutcome(state=unknown, label="needs_human", detail="副作用状态未知")


def _trace(
    state: GraphState, node: NodeId, outcome: DecisionOutcome, *, status: StageStatus
) -> GraphState:
    ref = PolicyTraceRef(
        node=node,
        request_id=outcome.request_id,
        decision=outcome.decision,
        trace_id=outcome.trace_id,
        rule_set_hash=outcome.rule_set_hash,
        reason=f"matched={len(outcome.matched_rules)} skipped={len(outcome.skipped_rules)}",
    )
    summary = outcome.summary(status=status)
    updates: dict[str, Any] = {"traces": state.traces + (ref,)}
    if node is NodeId.VALIDATION:
        updates["validation"] = summary
    if node is NodeId.TESTING:
        updates["test_validation"] = summary
    return state.replace(**updates)


# --------------------------------------------------------------------- 节点实现


def requirement_analysis(state: GraphState, context: NodeContext) -> NodeOutcome:
    """把需求变成**结构化验收条目**；正文只留摘要。"""

    task = context.task
    criteria = task.acceptance or (
        f"{task.target} 满足仓库规则集",
        f"{task.target} 通过确定性验证器（AST / Lint / 测试）",
    )
    artifact = ArtifactRef(
        artifact_id=f"req:{task.task_id}",
        kind=ArtifactKind.REQUIREMENT,
        path=None,
        digest=task.requirement_digest(),
        note="需求正文不入状态，只留摘要",
    )
    updated = state.replace(
        requirements=tuple(criteria),
        artifacts=state.artifacts + (artifact,),
        notes=state.notes + (f"需求摘要 {task.requirement_digest()[:19]}…",),
    )
    key = f"{state.task_id}:requirement_analysis"
    updated = _record_run(
        updated,
        NodeId.REQUIREMENT_ANALYSIS,
        label="ok",
        status=StageStatus.OK,
        key=key,
        outcome={"requirements": list(criteria)},
    )
    return NodeOutcome(state=updated, label="ok")


def policy_retrieval(state: GraphState, context: NodeContext) -> NodeOutcome:
    """**只**取上下文：不判定、不改文件；三态（ok / empty / unavailable）分开处理。"""

    call = RetrieveCall(
        request_id=_request_id(state, NodeId.POLICY_RETRIEVAL),
        context=context.context_payload(operation="read"),
        principal=dict(context.task.principal),
        trace_id=state.trace_id,
        query=context.task.query or context.task.requirement[:120],
        limit=5,
    )
    outcome = context.client.retrieve(call)
    if outcome.status == "unavailable":
        raise PlatformUnavailableError(
            "检索不可用：不允许凭记忆继续规范相关步骤",
            code=FailureCode.KNOWLEDGE_UNAVAILABLE,
            node=NodeId.POLICY_RETRIEVAL,
        )
    snapshot = state.snapshot or _empty_snapshot()
    snapshot = snapshot.model_copy(update={"index_version": outcome.index_version})
    notes = state.notes
    if outcome.status == "empty":
        notes = notes + ("检索无结果（不是'没有规范'）：后续判定仍由验证器给出证据",)
    updated = state.replace(
        contexts=outcome.contexts,
        snapshot=snapshot,
        notes=notes,
        request_id=call.request_id,
    )
    key = f"{state.task_id}:policy_retrieval:{outcome.status}"
    updated = _record_run(
        updated,
        NodeId.POLICY_RETRIEVAL,
        label=outcome.status,
        status=StageStatus.OK,
        key=key,
        outcome={"status": outcome.status, "chunks": [item.chunk_id for item in outcome.contexts]},
    )
    return NodeOutcome(state=updated, label="ok", detail=f"检索状态 {outcome.status}")


def architecture_planning(state: GraphState, context: NodeContext) -> NodeOutcome:
    """纯规划：把验收条目映射成有顺序的步骤（不调用平台、不改文件）。"""

    steps: list[PlanStep] = [
        PlanStep(
            step_id="plan-implement",
            node=NodeId.IMPLEMENTATION,
            target=context.task.target,
            summary="按验收条目实施受治理的改动",
        ),
        PlanStep(
            step_id="plan-validate",
            node=NodeId.VALIDATION,
            target=context.task.target,
            summary="提交证据并读回结构化 Decision（失败则修复后重验）",
        ),
        PlanStep(
            step_id="plan-test",
            node=NodeId.TESTING,
            target=context.task.target,
            summary="运行测试类验证器",
        ),
    ]
    artifact = ArtifactRef(
        artifact_id=f"plan:{context.task.task_id}",
        kind=ArtifactKind.PLAN,
        path=None,
        digest=canonical_digest([step.model_dump(mode="json") for step in steps]),
        note="计划是数据：步骤与目标都在这里",
    )
    updated = state.replace(plan=tuple(steps), artifacts=state.artifacts + (artifact,))
    key = f"{state.task_id}:architecture_planning"
    updated = _record_run(
        updated,
        NodeId.ARCHITECTURE_PLANNING,
        label="ok",
        status=StageStatus.OK,
        key=key,
        outcome={"steps": [step.step_id for step in steps]},
    )
    return NodeOutcome(state=updated, label="ok")


def implementation(state: GraphState, context: NodeContext) -> NodeOutcome:
    change = context.author.propose(task=context.task, state=state, round_index=0)
    return _apply_change(state, context, change, node=NodeId.IMPLEMENTATION)


def repair(state: GraphState, context: NodeContext) -> NodeOutcome:
    """只基于结构化 violation 规划修复：没有 violation 就拒绝"凭感觉修"。"""

    # 取**最近一次**失败：验证失败时读验证结果，测试失败时读测试结果。
    # 早先的写法是 `state.validation or state.test_validation`，而测试只在验证通过后才跑，
    # 于是"测试失败 → 修复"这条边永远拿到一份空的 violations，必然抛契约错误——
    # 一条写在图里的分支成了死代码。
    summary = _latest_failure(state)
    if summary is None or not summary.violations:
        raise NodeContractError(
            "修复节点没有结构化 violation 可用：拒绝在没有依据的情况下修改文件",
            node=NodeId.REPAIR,
        )
    # 顺序很重要：先认"开工未结算"，再计轮次、再要候选改动。
    # 否则崩溃恢复后会用下一轮的候选去覆盖上一轮未结算的动作（键变了，保护就失效了）。
    if _pending_run(state, NodeId.REPAIR) is not None:
        return _unsettled(state, NodeId.REPAIR)
    state = charge(state, LimitKind.REPAIR_ROUNDS, 1)  # 超限 → LimitExceeded → needs_human
    round_index = state.counters.repair_rounds
    change = context.author.propose(task=context.task, state=state, round_index=round_index)
    return _apply_change(state, context, change, node=NodeId.REPAIR, round_index=round_index)


def _apply_change(
    state: GraphState,
    context: NodeContext,
    change: Change,
    *,
    node: NodeId,
    round_index: int = 0,
) -> NodeOutcome:
    """受治理的写入：先问平台（evaluate），再交给受控执行链。"""

    if change.path != context.task.target and not change.path.startswith("policies/"):
        raise NodeContractError(
            f"改动目标 {change.path!r} 超出任务声明的工作目标：拒绝越界修改", node=node
        )
    action_id = _action_id(state, change)
    key = action_id

    # 已经用同一个幂等键成功执行过：重试不再产生第二次副作用（Phase 4 的台账是最后一道闸）。
    if state.completed(node, key):
        skipped = state.replace(notes=state.notes + (f"{node.value} 命中幂等键：跳过重复执行",))
        skipped = _record_run(
            skipped,
            node,
            label="ok",
            status=StageStatus.OK,
            key=key,
            outcome={"idempotent": True},
            detail="已执行过同一动作：不再执行第二次",
        )
        return NodeOutcome(state=skipped, label="ok", detail="幂等跳过")

    # 有一笔"开工未结算"的副作用：状态未知，交给人，绝不重放也绝不假装成功。
    if _pending_run(state, node) is not None:
        return _unsettled(state, node, key=key)

    # 判定要针对**真正要改的那个文件**（change.path），不是任务模板里的目标文件：
    # 独立验证探针发现，改规则文件的动作曾经拿着"控制器文件"的上下文去问平台，
    # 于是"平台允许"与"你写了什么"是两件事。注册表的 path_scope 兜住了越界，
    # 但判定口径必须是真实的。
    call = EvaluateCall(
        request_id=_request_id(state, node),
        context={
            **context.context_payload(operation="edit"),
            "file": change.path,
            "task": context.task.requirement[:400],
        },
        principal=dict(context.task.principal),
        trace_id=state.trace_id,
    )
    # 幂等键必须覆盖"这次到底发了什么"：平台按（键 + 请求摘要）记账，
    # 同一个键配上不同的请求体会得到 409（真实 API 是文件台账，跨进程仍然记得）。
    # 键随请求走，同一个请求重放才真的幂等；请求变了，键就该变。
    call = replace(call, idempotency_key=f"{key}:{canonical_digest(call.envelope())}")
    decision = context.client.evaluate(call)
    state = _trace(state, node, decision, status=StageStatus.OK)
    # 平台的"需要人工审批"是 block + required_action=approval：它不是"策略拒绝"，
    # 而是"等人批准"，因此必须先经过审批门禁，再让 Phase 4 做最终判定。
    needs_approval = decision.required_action == "approval"
    if not decision.allowed and not needs_approval:
        updated = state.replace(
            **_failure_updates(FailureCode.POLICY_BLOCKED, node, "平台未允许该动作：不写入"),
            notes=state.notes + (f"{node.value} 被平台拒绝：不动手",),
        )
        updated = _record_run(
            updated,
            node,
            label="blocked",
            status=StageStatus.BLOCKED,
            key=call.request_id,
            outcome={"decision": decision.decision.value},
            detail="policy block",
            failure=FailureCode.POLICY_BLOCKED,
        )
        return NodeOutcome(state=updated, label="blocked", detail="policy block")

    request = ToolRequest(
        tool_id=change.tool_id,
        action_id=action_id,
        request_id=call.request_id,
        params=change.params(),
        subject=str(context.task.principal.get("subject", "")),
        roles=tuple(context.task.principal.get("roles", ())),
        trace_id=state.trace_id,
        policy=decision.validation,
        workspace=context.workspace,
    )

    approval_path: Optional[Path] = None
    if needs_approval:
        # 审批绑的是**平台口径的 action_hash**（覆盖参数、主体、工具 schema 与上下文摘要），
        # 不是编排层自己的幂等键——否则编排层放行、平台的 pre-check 照样会拒绝。
        binding = context.runner.binding(request)
        try:
            use = context.approvals.use(
                state,
                node=node,
                action_hash=binding.action_hash,
                action_id=binding.action_id,
                tool_id=binding.tool_id,
                subject=binding.subject,
            )
        except ApprovalError as error:
            updated = state.replace(
                **_failure_updates(error.code, node, error.detail),
                notes=state.notes + (f"{node.value} 需要人工审批：{error.code.value}",),
            )
            updated = _record_run(
                updated,
                node,
                label="needs_human",
                status=StageStatus.NEEDS_HUMAN,
                key=call.request_id,
                outcome={"decision": decision.decision.value},
                detail=error.detail,
                failure=error.code,
            )
            return NodeOutcome(state=updated, label="needs_human", detail=error.detail)
        state = context.approvals.consume(state, use)
        # 交给 Phase 4 的是**审批文件本身**：编排层只负责找到它，
        # 真正的校验（action_hash / 主体 / 有效期 / 单次使用）仍然由平台做。
        approval_path = context.approvals.resolve(action_id)

    # 记一次工具调用（上限在 limits 里；超限抛 LimitExceeded → needs_human）。
    state = charge(state, LimitKind.TOOL_CALLS, 1)
    state = charge(state, LimitKind.TOKENS, change.tokens)
    state = charge(state, LimitKind.COST_UNITS, change.cost_units)

    # 写前记账：副作用之前先落一笔意图并**立刻刷盘**，崩溃后才能在恢复时发现"开工未结算"。
    state = _intent(
        state, node, key, bound={"tool_id": change.tool_id, "request_id": call.request_id}
    )
    if context.commit is not None:
        context.commit(state)

    outcome: ToolOutcome = context.runner.run(
        replace(request, approval_path=approval_path) if approval_path else request
    )
    state = _settle(state, node, key)
    if not outcome.executed:
        code = (
            FailureCode.APPROVAL_MISSING
            if outcome.needs_approval
            else FailureCode.TOOL_DENIED
        )
        status = StageStatus.NEEDS_HUMAN if outcome.needs_approval else StageStatus.BLOCKED
        updated = state.replace(
            **_failure_updates(code, node, outcome.detail or outcome.reason_code),
            notes=state.notes + (f"{node.value} 未执行（{outcome.reason_code}）",),
        )
        updated = _record_run(
            updated,
            node,
            label="needs_human" if outcome.needs_approval else "blocked",
            status=status,
            key=request.action_id,
            outcome={"reason_code": outcome.reason_code},
            detail=outcome.detail,
            failure=code,
        )
        label = "needs_human" if outcome.needs_approval else "blocked"
        return NodeOutcome(state=updated, label=label)

    artifact = ArtifactRef(
        artifact_id=f"change:{request.action_id}",
        kind=ArtifactKind.CHANGE,
        path=change.path,
        digest=(outcome.changed[0].digest if outcome.changed else change.digest()),
        bytes=(outcome.changed[0].bytes if outcome.changed else 0),
        note=change.summary[:200] or "受治理的写入（内容不入状态）",
    )
    updated = state.replace(
        artifacts=state.artifacts + (artifact,),
        notes=state.notes + (f"{node.value} 写入 {change.path}（{request.action_id[:24]}…）",),
    )
    updated = _record_run(
        updated,
        node,
        label="ok",
        status=StageStatus.OK,
        key=request.action_id,
        outcome={"action_id": request.action_id, "artifact": artifact.artifact_id},
    )
    return NodeOutcome(state=updated, label="ok", detail=f"写入 {change.path}")


def validation(state: GraphState, context: NodeContext) -> NodeOutcome:
    """**只**提交证据：证据由服务端验证器流水线产出，客户端不能自带。"""

    call = ValidateCall(
        request_id=_request_id(state, NodeId.VALIDATION),
        context=context.context_payload(operation="edit"),
        principal=dict(context.task.principal),
        trace_id=state.trace_id,
        target=context.task.target,
        changed=(context.task.target,),
    )
    outcome = context.client.validate(call)
    state = _trace(state, NodeId.VALIDATION, _as_decision(outcome), status=StageStatus.OK)
    summary = outcome.summary()
    label = "fail" if summary.failing else "pass"
    updated = state.replace(
        validation=summary,
        snapshot=_with_rule_set(state, outcome.rule_set_hash),
        notes=state.notes
        + (
            f"验证 {label}（{outcome.decision.value}，violations={len(summary.violations)}）",
        ),
    )
    updated = _record_run(
        updated,
        NodeId.VALIDATION,
        label=label,
        status=StageStatus.OK if not summary.failing else StageStatus.FAILED,
        key=call.request_id,
        outcome={
            "decision": outcome.decision.value,
            "violations": [item.rule_id for item in summary.violations],
            "evidence": outcome.evidence_digest,
        },
    )
    return NodeOutcome(state=updated, label=label, detail=f"{len(summary.violations)} 条 violation")


def testing(state: GraphState, context: NodeContext) -> NodeOutcome:
    """测试类验证器：同样只提交证据 + 读回 Decision。"""

    call = ValidateCall(
        request_id=_request_id(state, NodeId.TESTING),
        context=context.context_payload(operation="edit"),
        principal=dict(context.task.principal),
        trace_id=state.trace_id,
        target=context.task.target,
        changed=(context.task.target,),
        only=("failing_tests",),
    )
    outcome = context.client.validate(call)
    state = _trace(state, NodeId.TESTING, _as_decision(outcome), status=StageStatus.OK)
    summary = outcome.summary()
    label = "fail" if summary.failing else "pass"
    updated = state.replace(
        test_validation=summary,
        notes=state.notes + (f"测试 {label}（{outcome.decision.value}）",),
    )
    updated = _record_run(
        updated,
        NodeId.TESTING,
        label=label,
        status=StageStatus.OK if not summary.failing else StageStatus.FAILED,
        key=call.request_id,
        outcome={"decision": outcome.decision.value},
    )
    return NodeOutcome(state=updated, label=label)


def review(state: GraphState, context: NodeContext) -> NodeOutcome:
    """收尾：只在**证据齐备**时进入 completed；否则如实写失败状态。"""

    validation_summary = state.validation
    if validation_summary is None or validation_summary.failing:
        raise NodeContractError(
            "没有一次通过的验证就走到收尾：拒绝把'图跑完了'当成通过", node=NodeId.REVIEW
        )
    report = ArtifactRef(
        artifact_id=f"report:{state.task_id}",
        kind=ArtifactKind.REPORT,
        path=None,
        digest=canonical_digest(
            {
                "traces": [item.request_id for item in state.traces],
                "validation": validation_summary.decision.value,
                "test": (
                    None if state.test_validation is None else state.test_validation.decision.value
                ),
                "artifacts": [item.artifact_id for item in state.artifacts],
            }
        ),
        note=f"共 {len(state.traces)} 次平台判定、{len(state.artifacts)} 个 artifact 引用",
    )
    updated = state.replace(
        status=RunStatus.COMPLETED,
        artifacts=state.artifacts + (report,),
        notes=state.notes + ("工作流完成：每个节点都能追溯到平台判定",),
    )
    updated = _record_run(
        updated,
        NodeId.REVIEW,
        label="ok",
        status=StageStatus.OK,
        key=f"{state.task_id}:review",
        outcome={"report": report.digest},
    )
    return NodeOutcome(state=updated, label="ok")


# --------------------------------------------------------------------- 装配


def _empty_snapshot():
    from .models import PlatformSnapshot

    return PlatformSnapshot()


def _with_rule_set(state: GraphState, rule_set_hash: Optional[str]):
    snapshot = state.snapshot or _empty_snapshot()
    if rule_set_hash is None:
        return snapshot
    return snapshot.model_copy(update={"rule_set_hash": rule_set_hash})


def _failure(code: FailureCode, node: NodeId, detail: str):
    from .models import FailureRef

    return FailureRef(code=code, node=node, detail=detail[:400])


def _failure_updates(code: FailureCode, node: NodeId, detail: str) -> dict[str, Any]:
    """失败码同时决定**终态**：状态与失败码永远一致，不靠调用方兜底。"""

    from .errors import STATUS_BY_CODE

    return {
        "status": STATUS_BY_CODE.get(code, RunStatus.FAILED),
        "failure": _failure(code, node, detail),
    }


def _as_decision(outcome: Any) -> DecisionOutcome:
    """把 validate 的结果统一成 `DecisionOutcome`，让 trace 只有一种形状。"""

    return DecisionOutcome(
        decision=outcome.decision,
        request_id=outcome.request_id,
        trace_id=outcome.trace_id,
        rule_set_hash=outcome.rule_set_hash,
        required_action=outcome.required_action,
        violations=outcome.violations,
        validation=outcome.validation,
    )


NODES: Mapping[NodeId, NodeFn] = {
    NodeId.REQUIREMENT_ANALYSIS: requirement_analysis,
    NodeId.POLICY_RETRIEVAL: policy_retrieval,
    NodeId.ARCHITECTURE_PLANNING: architecture_planning,
    NodeId.IMPLEMENTATION: implementation,
    NodeId.VALIDATION: validation,
    NodeId.REPAIR: repair,
    NodeId.TESTING: testing,
    NodeId.REVIEW: review,
}
