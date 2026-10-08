"""图定义：节点、边与分支都是**数据 + 纯函数**，两个引擎消费同一份。

阶段计划要求 `PASS/FAIL 分支只由结构化 Decision 决定`。因此：

- 静态边写在 `DEFAULT_SPEC` 里；
- 条件分支写成具名纯函数（`ROUTERS`），输入是 `GraphState`，输出是一个**路由标签**，
  由 `GraphSpec` 把标签映射到目标节点；标签认不出来就是契约错误（失败关闭）；
- 引擎不写死任何一条边：参考实现与 LangGraph 实现都读这份 spec，
  "换掉编排框架"因此是可测的（`tests/contract/test_orchestration_engines.py`）。
"""

from __future__ import annotations

from typing import Callable, Mapping, Tuple

from pydantic import Field, field_validator

from .errors import NodeContractError
from .models import GraphState, NodeId, StrictModel

__all__ = [
    "DEFAULT_SPEC",
    "END",
    "ROUTERS",
    "Edge",
    "GraphSpec",
    "Router",
    "RouterFn",
    "known_targets",
]

END = "end"


def known_targets() -> frozenset[str]:
    return frozenset(node.value for node in NodeId) | {END}


class Edge(StrictModel):
    """一条静态边。`END` 表示"工作流在这里结束"。"""

    source: str
    target: str

    @field_validator("source")
    @classmethod
    def _check_source(cls, value: str) -> str:
        if value not in known_targets() or value == END:
            raise ValueError(f"未知的源节点：{value!r}")
        return value

    @field_validator("target")
    @classmethod
    def _check_target(cls, value: str) -> str:
        if value not in known_targets():
            raise ValueError(f"未知的目标节点：{value!r}")
        return value


class Router(StrictModel):
    """一个条件分支：`label → target`，标签由具名纯函数产生。"""

    name: str = Field(min_length=1, max_length=64)
    source: str
    targets: Mapping[str, str]

    @field_validator("source")
    @classmethod
    def _check_source(cls, value: str) -> str:
        # 与 Edge 同一条口径。Router.source 以前没有校验：一个写错的节点名（或 END）能构造出来、
        # 也能通过 problems()，却永远命不中 router_for——条件分支静默退化成静态路径
        # （例如"验证失败 → 修复"那一支永远不触发），而失败关闭的图定义承诺不该有这种形态。
        if value not in known_targets() or value == END:
            raise ValueError(f"未知的源节点：{value!r}")
        return value

    @field_validator("targets")
    @classmethod
    def _check_targets(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        if not value:
            raise ValueError("条件分支至少要有一个目标")
        for label, target in value.items():
            if not label or len(label) > 64:
                raise ValueError("路由标签必须是 1..64 字符")
            if target not in known_targets():
                raise ValueError(f"未知的路由目标：{target!r}")
        return dict(value)


class GraphSpec(StrictModel):
    entry: str = "requirement_analysis"
    edges: Tuple[Edge, ...] = ()
    routers: Tuple[Router, ...] = ()

    def outgoing(self, node: str) -> Tuple[str, ...]:
        return tuple(edge.target for edge in self.edges if edge.source == node)

    def router_for(self, node: str) -> Router | None:
        for router in self.routers:
            if router.source == node:
                return router
        return None

    def problems(self) -> Tuple[str, ...]:
        """图定义自检：能走通、**能走到终点**、每个节点都到得了，且分支本身不能自相矛盾。

        为什么可达性也算：只查"每个节点有没有出边"是**不够**的——`validation ⇄ repair` 这种
        没有出口的环满足它，却永远不会结束（引擎会把这条自检当契约错误，见 BaseEngine.__init__，
        所以漏掉它等于让一张跑不完的图通过自检）；孤立节点同样满足它，却永远跑不到。
        自检要回答的是"这张图能不能跑完"，不是"每个节点有没有写下一步"。
        """

        issues: list[str] = []
        nodes = tuple(node.value for node in NodeId)
        if self.entry not in nodes:
            issues.append(f"入口 {self.entry!r} 不是已知节点")
        for node in nodes:
            router = self.router_for(node)
            targets = self.outgoing(node) + (
                () if router is None else tuple(router.targets.values())
            )
            if not targets:
                issues.append(f"节点 {node!r} 既没有静态边也没有条件分支：会走不下去")
        for edge in self.edges:
            if not any(edge.source == item.value for item in NodeId):
                issues.append(f"边 {edge.source!r} 不是已知节点")
        # 同一个节点挂两条静态边：走哪条**无法确定**。实测两个引擎给出不同结果——
        # 参考引擎按 spec 顺序取第一条（另一条静默丢掉），LangGraph 因为两条边共用同一个分支名
        # 直接编译失败（`ValueError: Branch with name _static_choice already exists for node ...`）。
        # 自检必须在这里拒绝，而不是让两个引擎各自决定。
        for node in nodes:
            outgoing = self.outgoing(node)
            if len(outgoing) > 1:
                issues.append(
                    f"节点 {node!r} 有 {len(outgoing)} 条静态边（{list(outgoing)}）："
                    "走哪条无法确定，两个引擎会给出不同结果"
                )
        seen_router_sources: set[str] = set()
        for router in self.routers:
            if router.name not in ROUTERS:
                issues.append(f"条件分支 {router.name!r} 没有对应的纯函数实现")
            # 同一个源节点挂两个分支：router_for 只返回第一个命中的，而 LangGraph 侧会把每个
            # router 都注册一遍——两个引擎会读出两种图，且是静默的。
            if router.source in seen_router_sources:
                issues.append(f"节点 {router.source!r} 上有多个条件分支：只会有一个生效")
            seen_router_sources.add(router.source)
            # 静态边与条件分支挂在同一个节点上：route() 优先走分支，静态边被静默忽略。
            if self.outgoing(router.source):
                issues.append(
                    f"节点 {router.source!r} 同时有静态边与条件分支：静态边会被忽略"
                )
        # 从入口出发做一次可达性遍历（静态边 + 条件分支的**全部**目标：分支走到哪条由判定决定，
        # 自检只看"有没有可能走到"）。
        reachable: set[str] = set()
        frontier = [item for item in (self.entry,) if item in nodes]
        while frontier:
            current = frontier.pop()
            if current in reachable:
                continue
            reachable.add(current)
            router = self.router_for(current)
            targets = list(self.outgoing(current))
            if router is not None:
                targets.extend(router.targets.values())
            frontier.extend(target for target in targets if target not in reachable)
        if self.entry in nodes and END not in reachable:
            issues.append(
                "从入口出发到不了终点 end：这张图永远不会结束（存在没有出口的环）"
            )
        for node in nodes:
            if node not in reachable:
                issues.append(f"节点 {node!r} 从入口不可达：写了但永远跑不到")
        return tuple(issues)


# --------------------------------------------------------------------- 分支函数


RouterFn = Callable[[GraphState], str]


def validation_outcome(state: GraphState) -> str:
    """PASS / FAIL 只看结构化 Decision：没有验证结果也算失败。"""

    summary = state.validation
    if summary is None:
        raise NodeContractError("验证分支在没有 ValidationSummary 的情况下被求值")
    return "fail" if summary.failing else "pass"


def testing_outcome(state: GraphState) -> str:
    summary = state.test_validation
    if summary is None:
        raise NodeContractError("测试分支在没有测试结果的情况下被求值")
    return "fail" if summary.failing else "pass"


ROUTERS: Mapping[str, RouterFn] = {
    "validation_outcome": validation_outcome,
    "testing_outcome": testing_outcome,
}


def default_spec() -> GraphSpec:
    """阶段计划里的工作流：需求 → 检索 → 规划 → 实施 → 验证 ⇄ 修复 → 测试 → 收尾。"""

    return GraphSpec(
        entry=NodeId.REQUIREMENT_ANALYSIS.value,
        edges=(
            Edge(source=NodeId.REQUIREMENT_ANALYSIS.value, target=NodeId.POLICY_RETRIEVAL.value),
            Edge(source=NodeId.POLICY_RETRIEVAL.value, target=NodeId.ARCHITECTURE_PLANNING.value),
            Edge(source=NodeId.ARCHITECTURE_PLANNING.value, target=NodeId.IMPLEMENTATION.value),
            Edge(source=NodeId.IMPLEMENTATION.value, target=NodeId.VALIDATION.value),
            Edge(source=NodeId.REPAIR.value, target=NodeId.VALIDATION.value),
            Edge(source=NodeId.REVIEW.value, target=END),
        ),
        routers=(
            Router(
                name="validation_outcome",
                source=NodeId.VALIDATION.value,
                targets={"pass": NodeId.TESTING.value, "fail": NodeId.REPAIR.value},
            ),
            Router(
                name="testing_outcome",
                source=NodeId.TESTING.value,
                targets={"pass": NodeId.REVIEW.value, "fail": NodeId.REPAIR.value},
            ),
        ),
    )


DEFAULT_SPEC = default_spec()
