"""引擎：参考实现与 LangGraph 实现消费同一份 `GraphSpec` 与同一批节点。

分工刻意画在"控制流"这一层：

- `StepExecutor` 负责**与编排框架无关**的一切：上限记账、节点调用、失败映射、
  checkpoint 落盘、恢复兼容性、幂等跳过。两个引擎都调用它，因此语义只有一份；
- `ReferenceEngine` 用一个 while 循环驱动 `StepExecutor`（没有第三方依赖）；
- `LangGraphEngine`（见 `langgraph_engine.py`）把同一份 spec 交给 LangGraph 的
  `StateGraph`，节点函数与条件边仍然回调 `StepExecutor`。

"换掉编排框架"因此不是口号：`tests/contract/test_orchestration_engines.py` 用同一组场景
跑两个引擎并要求 `RunReport` 逐字段一致（引擎名与耗时除外）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Protocol, Tuple

from pydantic import ValidationError

from .checkpoint import (
    CheckpointRecord,
    CheckpointStore,
    ResumeMode,
    build_record,
    plan_resume,
)
from .errors import (
    STATUS_BY_CODE,
    NodeContractError,
    OrchestrationError,
    status_for,
)
from .graph import DEFAULT_SPEC, END, ROUTERS, GraphSpec, RouterFn
from .limits import charge_node_run
from .models import (
    FailureCode,
    FailureRef,
    GraphState,
    NodeId,
    PlatformSnapshot,
    RunStatus,
)
from .nodes import NODES, NodeContext, NodeFn, NodeOutcome

__all__ = [
    "BaseEngine",
    "GraphEngine",
    "ReferenceEngine",
    "RunReport",
    "StepExecutor",
    "StepRecord",
    "StepResult",
]


@dataclass(frozen=True)
class StepRecord:
    """一个节点的一次执行（只留摘要：状态、标签、输出摘要与失败码）。"""

    node: str
    label: str
    status: str
    outcome_digest: str
    detail: str = ""
    failure: Optional[str] = None


@dataclass(frozen=True)
class StepResult:
    state: GraphState
    label: str
    terminal: bool = False


@dataclass(frozen=True)
class RunReport:
    task_id: str
    engine: str
    status: RunStatus
    state: GraphState
    steps: Tuple[StepRecord, ...]
    resumed: bool = False
    resume_mode: str = ResumeMode.FRESH.value
    failure: Optional[FailureRef] = None
    elapsed_ms: int = 0
    checkpoints: int = 0
    limit_reached: bool = False

    def to_payload(self) -> dict[str, Any]:
        """机器可读报告：**不含正文**，只有引用、决定与计数。"""

        return {
            "task_id": self.task_id,
            "engine": self.engine,
            "status": self.status.value,
            "resumed": self.resumed,
            "resume_mode": self.resume_mode,
            "failure": None if self.failure is None else self.failure.model_dump(mode="json"),
            "elapsed_ms": self.elapsed_ms,
            "checkpoints": self.checkpoints,
            "limit_reached": self.limit_reached,
            "steps": [
                {
                    "node": item.node,
                    "label": item.label,
                    "status": item.status,
                    "outcome_digest": item.outcome_digest,
                    "detail": item.detail,
                    "failure": item.failure,
                }
                for item in self.steps
            ],
            "counters": self.state.counters.model_dump(mode="json"),
            "limits": self.state.limits.model_dump(mode="json"),
            "traces": [
                {
                    "node": item.node.value,
                    "request_id": item.request_id,
                    "decision": item.decision.value,
                    "rule_set_hash": item.rule_set_hash,
                    "trace_id": item.trace_id,
                }
                for item in self.state.traces
            ],
            "artifacts": [
                {
                    "artifact_id": item.artifact_id,
                    "kind": item.kind.value,
                    "path": item.path,
                    "digest": item.digest,
                    "bytes": item.bytes,
                }
                for item in self.state.artifacts
            ],
            "validation": None
            if self.state.validation is None
            else self.state.validation.model_dump(mode="json"),
            "test_validation": None
            if self.state.test_validation is None
            else self.state.test_validation.model_dump(mode="json"),
            "contexts": [item.model_dump(mode="json") for item in self.state.contexts],
            "state_digest": self.state.digest(),
            "notes": list(self.state.notes),
        }


class StepExecutor:
    """单步执行器：两个引擎共用。它不决定"用哪个框架"，只决定"这一步怎么算完"。"""

    def __init__(
        self,
        *,
        node_context: NodeContext,
        store: Optional[CheckpointStore] = None,
        spec: GraphSpec = DEFAULT_SPEC,
        nodes: Mapping[NodeId, NodeFn] = NODES,
        router_fns: Mapping[str, RouterFn] = ROUTERS,
        engine_name: str = "reference",
        compatibility: Optional[PlatformSnapshot] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        problems = spec.problems()
        if problems:
            raise NodeContractError("图定义自检失败：" + "；".join(problems))
        self.context = node_context
        self.store = store
        self.spec = spec
        self.nodes = nodes
        self.router_fns = router_fns
        self.engine_name = engine_name
        self.compatibility = compatibility or PlatformSnapshot()
        self.clock = clock
        self.sequence = 0
        self.checkpoints = 0
        self._last_saved: Optional[GraphState] = None
        self.started_at = self.clock()
        # 节点可以直接把状态刷进 checkpoint（写前日志）：端口是显式注入的，不是全局单例。
        self.context.commit = self.save

    # ------------------------------------------------------------------ 恢复
    def prepare(self, *, task_id: str, fresh_state: GraphState) -> Tuple[GraphState, bool, str]:
        record: Optional[CheckpointRecord] = None
        if self.store is not None and self.store.exists(task_id):
            record = self.store.load(task_id)
        # 比对基准是"**当前**平台的版本凭据"（装配时从 readiness 取），不是新状态的空快照。
        plan = plan_resume(record, self.compatibility, fresh_state=fresh_state)
        assert plan.state is not None
        state = plan.state
        # 恢复的墙钟预算从**这次运行**开始算：上一轮花掉的时间不该记在这一轮头上。
        self.started_at = self.clock()
        if self.store is not None and plan.mode is not ResumeMode.FRESH:
            # 恢复本身就是一次状态变化：立刻落一份 checkpoint，避免"恢复了但没记录"。
            state = state.replace(notes=state.notes + (f"恢复：{plan.detail}",))
            self.save(state)
        return state, plan.mode is not ResumeMode.FRESH, plan.mode.value

    def snapshot(self, state: GraphState) -> PlatformSnapshot:
        """兼容性凭据 = 装配处声明的当前值（优先）+ 状态里累积到的值（补空缺）。"""

        base = state.snapshot or PlatformSnapshot()
        updates: dict[str, Any] = {}
        for name in ("rule_set_hash", "index_version", "tool_schema_hash"):
            value = getattr(self.compatibility, name)
            if value is not None:
                updates[name] = value
        return base.model_copy(update=updates) if updates else base

    # ------------------------------------------------------------------ 单步
    def step(self, state: GraphState) -> StepResult:
        """跑一个节点，然后**把"下一步"写进 checkpoint**。

        顺序刻意如此：先执行、再路由、再把"带着下一步的状态"落盘。这样
        "checkpoint 之后崩溃"永远不会让恢复重跑刚刚完成的那个节点——
        "恢复后不重复副作用"靠的就是这个顺序，而不是靠运气。
        """

        node = state.stage
        function = self.nodes.get(node)
        if function is None:
            return self._fail(state, FailureCode.NODE_UNKNOWN, f"未知节点 {node.value!r}")
        # 墙钟预算在**引擎**这一层检查（独立验证探针 P2 发现：声明了上限却从不检查）。
        # 它刻意不写回状态：状态里一旦有墙钟数字，"相同输入得到逐字节相同的状态"就不成立了。
        budget = state.limits.max_elapsed_ms
        if budget and int((self.clock() - self.started_at) * 1000) > budget:
            return self._fail(
                state,
                FailureCode.LIMIT_WALL_CLOCK,
                f"墙钟预算耗尽（>{budget}ms）：停止推进，交给人",
            )
        try:
            state = charge_node_run(state)
        except OrchestrationError as error:
            return self._fail(state, error.code, error.detail)
        try:
            outcome = function(state, self.context)
        except OrchestrationError as error:
            return self._fail(state, error.code, error.detail)
        except ValidationError as error:
            return self._fail(
                state,
                FailureCode.NODE_CONTRACT_INVALID,
                f"节点输出不合法（{type(error).__name__}）",
            )
        except Exception as error:  # noqa: BLE001 - 未知异常一律失败关闭
            # 诊断信息要留，但先脱敏再限量：异常文本里可能带绝对路径或凭据。
            from enforcement.audit import redact_text

            message = redact_text(str(error), limit=200)
            return self._fail(
                state,
                FailureCode.STATE_INVALID,
                f"节点抛出未分类异常（{type(error).__name__}: {message}）",
            )
        if not isinstance(outcome, NodeOutcome):
            return self._fail(state, FailureCode.NODE_CONTRACT_INVALID, "节点没有返回 NodeOutcome")
        state = outcome.state.replace(snapshot=self.snapshot(outcome.state))
        if state.failure is not None:
            self.save(state)
            return StepResult(state=state, label=outcome.label, terminal=True)
        # 节点自报的标签也必须被校验：分支节点的标签是契约的一部分
        # （"不存在"的标签说明节点与图定义已经漂移），不能只当注释留在报告里。
        router = self.spec.router_for(node.value)
        if router is not None and outcome.label not in router.targets:
            return self._fail(
                state,
                FailureCode.NODE_CONTRACT_INVALID,
                f"节点 {node.value!r} 给出了图定义里没有的标签 {outcome.label!r}",
            )
        try:
            target = self.route(state, outcome.label)
        except OrchestrationError as error:
            return self._fail(state, error.code, error.detail)
        if target == END:
            state = state.replace(status=_terminal_status(state))
            self.save(state)
            return StepResult(state=state, label=outcome.label, terminal=True)
        state = state.replace(stage=NodeId(target))
        self.save(state)
        return StepResult(state=state, label=outcome.label, terminal=False)

    def route(self, state: GraphState, label: str) -> str:
        """给出下一步。失败状态一律终止；不认识的标签是契约错误。"""

        if state.failure is not None:
            return END
        node = state.stage
        router = self.spec.router_for(node.value)
        if router is not None:
            function = self.router_fns.get(router.name)
            if function is None:
                raise NodeContractError(f"条件分支 {router.name!r} 没有实现")
            chosen = function(state)
            target = router.targets.get(chosen)
            if target is None:
                raise NodeContractError(
                    f"节点 {node.value!r} 给出了未知路由标签 {chosen!r}：拒绝猜下一步"
                )
            return target
        outgoing = self.spec.outgoing(node.value)
        if len(outgoing) != 1:
            raise NodeContractError(
                f"节点 {node.value!r} 有 {len(outgoing)} 条出边：静态分支必须唯一"
            )
        return outgoing[0]

    # ------------------------------------------------------------------ 收尾
    def save(self, state: GraphState) -> None:
        if self.store is None:
            return
        self.sequence += 1
        record = build_record(
            state,
            engine=self.engine_name,
            sequence=self.sequence,
            compatibility=self.snapshot(state),
        )
        self.store.save(record)
        self._last_saved = state
        self.checkpoints += 1

    def _fail(self, state: GraphState, code: FailureCode, detail: str) -> StepResult:
        # 节点可能已经刷过盘（写前记账的意图）。失败状态必须**长在最新那份状态上**，
        # 否则那笔 PENDING 意图会被抹掉：恢复时看不见"开工未结算"，副作用会被重放。
        base = state
        if self._last_saved is not None and len(self._last_saved.runs) > len(state.runs):
            base = self._last_saved
        failure = FailureRef(code=code, node=base.stage, detail=detail[:400])
        updated = base.replace(
            status=STATUS_BY_CODE.get(code, RunStatus.FAILED),
            failure=failure,
            notes=base.notes + (f"{base.stage.value} 失败：{code.value}",),
        )
        self.save(updated)
        return StepResult(state=updated, label="stop", terminal=True)


class BaseEngine:
    """引擎基类：负责计时、恢复与报告组装；控制流交给子类的 `_drive`。"""

    name = "base"

    def __init__(
        self,
        *,
        executor: StepExecutor,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.executor = executor
        self.clock = clock

    def _drive(self, state: GraphState) -> GraphState:
        raise NotImplementedError

    def run(self, *, task_id: str, state: GraphState) -> RunReport:
        started = self.clock()
        resumed_state, resumed, resume_mode = self.executor.prepare(
            task_id=task_id, fresh_state=state
        )
        steps: list[StepRecord] = []
        try:
            final = self._drive(resumed_state)
        except OrchestrationError as error:
            failure = FailureRef(
                code=error.code, node=resumed_state.stage, detail=error.detail[:400]
            )
            final = resumed_state.replace(status=status_for(error), failure=failure)
        steps = [
            StepRecord(
                node=item.node.value,
                label=item.label,
                status=item.status.value,
                outcome_digest=item.outcome_digest,
                detail=item.detail,
                failure=None if item.failure_code is None else item.failure_code.value,
            )
            for item in final.runs
        ]
        status = final.status
        if status is RunStatus.RUNNING and final.failure is not None:
            # 失败码决定终态（needs_human / blocked / failed），节点与引擎都不自己发明状态。
            status = STATUS_BY_CODE.get(final.failure.code, RunStatus.FAILED)
        elif status is RunStatus.RUNNING:
            status = RunStatus.COMPLETED if final.stage is NodeId.REVIEW else RunStatus.BLOCKED
        elapsed = int((self.clock() - started) * 1000)
        return RunReport(
            task_id=task_id,
            engine=self.name,
            status=status,
            state=final,
            steps=tuple(steps),
            resumed=resumed,
            resume_mode=resume_mode,
            failure=final.failure,
            elapsed_ms=elapsed,
            checkpoints=self.executor.checkpoints,
        )


class ReferenceEngine(BaseEngine):
    """最小参考引擎：一个循环 + 一份 spec，不依赖任何工作流框架。"""

    name = "reference"

    def _drive(self, state: GraphState) -> GraphState:
        # 入口就是当前阶段：新建时是 requirement_analysis，恢复时是 checkpoint 里的阶段
        # （可能已被"规则集变化"回退）。绝不无条件从头再跑。
        for _ in range(state.limits.max_node_runs + 1):
            result = self.executor.step(state)
            state = result.state
            if result.terminal:
                return state
        # 循环次数保护：上限没被 charge 到（例如节点自己提前 return）也必须停下。
        failure = FailureRef(
            code=FailureCode.LIMIT_NODE_RUNS, node=state.stage, detail="节点执行次数超过上限"
        )
        return state.replace(status=RunStatus.NEEDS_HUMAN, failure=failure)


def _terminal_status(state: GraphState) -> RunStatus:
    if state.failure is not None:
        return STATUS_BY_CODE.get(state.failure.code, RunStatus.FAILED)
    return RunStatus.COMPLETED if state.stage is NodeId.REVIEW else RunStatus.BLOCKED


class GraphEngine(Protocol):
    """引擎契约：两个实现（reference / langgraph）必须给出可比较的 `RunReport`。"""

    name: str

    def run(self, *, task_id: str, state: GraphState) -> RunReport: ...
