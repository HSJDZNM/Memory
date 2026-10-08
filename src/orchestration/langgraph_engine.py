"""LangGraph 引擎：**本包唯一**导入工作流框架的文件。

阶段计划与架构约定（`03-technology-and-layout.md` §禁止的依赖方向）都要求
"LangGraph 只能是 Policy Platform 的消费者"：因此

- 只有这个模块导入 `langgraph`，而且是**在构造引擎时**才导入（模块级零副作用）；
- 版本不认识就抛 `EngineUnavailableError`（失败关闭），不"尽力兼容"；
- 图结构不在这里定义：节点、静态边与条件分支都来自 `graph.DEFAULT_SPEC`，
  节点函数回调 `StepExecutor`，所以两个引擎的语义只有一份实现；
- **跨进程恢复用的是本包的 checkpoint 存储**，不是 LangGraph 的 checkpointer：
  阶段计划要求 checkpoint 里带"规则集 / 索引 / 工具 schema 的兼容性"，那是领域信息，
  通用 checkpointer 不提供。若部署方另外装配了 checkpointer，可以通过参数传入。

删掉这个文件（以及整个 `orchestration` 包）不影响 Policy Platform 独立运行：
核心层从不导入本包（`tests/contract/test_orchestration_engine.py` 会检查）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from importlib import import_module, metadata
from typing import Any, Callable, Mapping, Optional, TypedDict

from .engines import BaseEngine, StepExecutor
from .errors import EngineUnavailableError
from .models import FailureCode, FailureRef, GraphState, NodeId, RunStatus

__all__ = ["MIN_LANGGRAPH_VERSION", "LangGraphEngine", "langgraph_version"]

MIN_LANGGRAPH_VERSION = "1.0"
_SUPPORTED_MAJOR = 1

# 两个内部路由标签：终止 / 继续。它们只在 LangGraph 的 path_map 里出现，
# 不进入 `graph.GraphSpec`（spec 里的标签全部来自节点产出的结构化结论）。
_STOP = "__stop__"
_NEXT = "__next__"


class GraphChannels(TypedDict, total=False):
    """LangGraph 的通道：只承载"状态载荷 + 上一次的路由标签"。"""

    state: dict[str, Any]
    label: str


@dataclass(frozen=True)
class _LangGraph:
    StateGraph: Any
    START: Any
    END: Any
    GraphRecursionError: Any
    version: str


def langgraph_version() -> Optional[str]:
    """已安装的 langgraph 版本；没装返回 None（调用方决定怎么办）。"""

    try:
        return metadata.version("langgraph")
    except Exception:  # noqa: BLE001 - 包元数据缺失 = 不可用
        return None


def _version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in value.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _load() -> _LangGraph:
    version = langgraph_version()
    if version is None:
        raise EngineUnavailableError(
            "没有安装 langgraph：声明使用 LangGraph 引擎时失败关闭，不静默回落到别的实现"
        )
    if _version_tuple(version)[:1] != (_SUPPORTED_MAJOR,):
        raise EngineUnavailableError(
            f"langgraph 版本 {version} 不在支持范围（{MIN_LANGGRAPH_VERSION} <= v < 2.0）："
            "拒绝在未验证的 API 上跑治理工作流"
        )
    try:
        graph_module = import_module("langgraph.graph")
        errors_module = import_module("langgraph.errors")
        # **属性访问也在守卫内**：装了一半的 langgraph（StateGraph / START / END 缺失或改名）
        # 以前会把 AttributeError 抛到外面，而 select_engine("auto") 只接
        # EngineUnavailableError——"自动回落到参考引擎"于是变成一句空话（失败关闭失效）。
        state_graph = graph_module.StateGraph
        start = graph_module.START
        end = graph_module.END
        # GraphRecursionError 必须**真的有**：以前缺省回落到 RuntimeError，于是 _drive 里
        # `except lg.GraphRecursionError` 会把图运行期间**任何** RuntimeError（checkpoint 存储 I/O、
        # langgraph 内部错误、节点里冒出的 RuntimeError）都翻译成 LIMIT_NODE_RUNS / NEEDS_HUMAN，
        # 把真失败伪装成"撞了节点上限"。宁可判定这个 langgraph 不可用。
        recursion_error = errors_module.GraphRecursionError
    except Exception as error:  # noqa: BLE001 - 导入或 API 缺失即不可用
        raise EngineUnavailableError(
            f"langgraph 可导入但 API 不完整（{type(error).__name__}: {error}）"
        ) from error
    return _LangGraph(
        StateGraph=state_graph,
        START=start,
        END=end,
        GraphRecursionError=recursion_error,
        version=version,
    )


class LangGraphEngine(BaseEngine):
    """用 LangGraph 的 `StateGraph` 驱动同一份 `GraphSpec`。"""

    name = "langgraph"

    def __init__(
        self,
        *,
        executor: StepExecutor,
        clock: Callable[[], float] = time.monotonic,
        checkpointer: Any = None,
        recursion_slack: int = 8,
    ) -> None:
        super().__init__(executor=executor, clock=clock)
        self.checkpointer = checkpointer
        self.recursion_slack = recursion_slack
        # **构造即校验**：不这样做，`engine="auto"` 在框架缺席时会照样选中本引擎，
        # 直到第一次运行为止——"自动回落到参考引擎"就成了空话（独立验证探针 P6b 证伪的正是这条）。
        self.version = _load().version

    # ------------------------------------------------------------------ 组装
    def build(self):
        """把 spec 交给 LangGraph；返回编译后的图（测试与 CLI 都可以直接用）。"""

        lg = _load()
        spec = self.executor.spec
        builder = lg.StateGraph(GraphChannels)
        for node in NodeId:
            builder.add_node(node.value, self._node_function(node))
        # 入口是条件边：恢复时从 checkpoint 里的阶段继续，而不是永远从头跑。
        builder.add_conditional_edges(
            lg.START,
            self._entry,
            {node.value: node.value for node in NodeId},
        )
        # 静态边也要"失败即终止"：不然某个节点失败后图还会继续往下跑。
        for edge in spec.edges:
            target = lg.END if edge.target == "end" else edge.target
            builder.add_conditional_edges(
                edge.source,
                self._static_choice,
                {_STOP: lg.END, _NEXT: target},
            )
        for router in spec.routers:
            mapping = {
                label: (lg.END if target == "end" else target)
                for label, target in router.targets.items()
            }
            mapping[_STOP] = lg.END
            builder.add_conditional_edges(router.source, self._conditional(router.name), mapping)
        return builder.compile(checkpointer=self.checkpointer)

    def _node_function(self, node: NodeId) -> Callable[[GraphChannels], GraphChannels]:
        def run_node(channels: GraphChannels) -> GraphChannels:
            # 进入本节点时 `stage` 已经是本节点：`StepExecutor` 在**路由之后**才落盘，
            # 所以这里不需要（也不应该）改写 stage——改写会让两个引擎的 revision 不一致。
            state = GraphState.model_validate(channels["state"])
            result = self.executor.step(state)
            return {"state": result.state.payload(), "label": result.label}

        run_node.__name__ = f"node_{node.value}"
        return run_node

    @staticmethod
    def _static_choice(channels: GraphChannels) -> str:
        state = GraphState.model_validate(channels["state"])
        return _STOP if state.failure is not None else _NEXT

    def _entry(self, channels: GraphChannels) -> str:
        state = GraphState.model_validate(channels["state"])
        return state.stage.value

    def _conditional(self, router_name: str) -> Callable[[GraphChannels], str]:
        function = self.executor.router_fns[router_name]

        def choose(channels: GraphChannels) -> str:
            # LangGraph 的 `path_map` 已经负责"标签 → 节点"，这里只返回标签；
            # 但标签必须先在 spec 里登记过，否则同样是"猜下一步"，一律拒绝。
            state = GraphState.model_validate(channels["state"])
            if state.failure is not None:
                return _STOP
            label = function(state)
            known = next(
                (
                    router.targets
                    for router in self.executor.spec.routers
                    if router.name == router_name
                ),
                {},
            )
            if label not in known:
                from .errors import NodeContractError

                raise NodeContractError(
                    f"节点 {state.stage.value!r} 给出了未知路由标签 {label!r}：拒绝猜下一步"
                )
            return label

        choose.__name__ = f"route_{router_name}"
        return choose

    # ------------------------------------------------------------------ 驱动
    def _drive(self, state: GraphState) -> GraphState:
        lg = _load()
        graph = self.build()
        limit = min(state.limits.max_node_runs + self.recursion_slack, 200)
        try:
            channels = graph.invoke(
                {"state": state.payload(), "label": ""},
                config={"recursion_limit": limit},
            )
        except lg.GraphRecursionError:
            # 进度都在 LangGraph 的通道里，入口状态什么都没有：失败状态必须长在执行器最后保存的
            # 那份状态上，并落盘，否则恢复时看不见失败（会被读成 RUNNING 接着跑）。
            base = self.executor.latest_state(state)
            failure = FailureRef(
                code=FailureCode.LIMIT_NODE_RUNS,
                node=base.stage,
                detail="LangGraph 递归上限触发：停止自调用",
            )
            final = base.replace(status=RunStatus.NEEDS_HUMAN, failure=failure)
            self.executor.save(final)
            return final
        payload = channels["state"] if isinstance(channels, Mapping) else channels.state
        return GraphState.model_validate(dict(payload))
