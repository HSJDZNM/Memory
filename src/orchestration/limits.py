"""硬上限：repair 次数、工具调用、节点执行、token、时间与费用。

阶段计划 §4：`为 repair 次数、tool chain 深度、token、时间和费用设置硬上限。
超过上限进入 needs_human 或失败状态，不能无限自调用。`

纪律：

- 上限是**数据**（`RunLimits`），不是代码里的常数：不同的任务可以给不同的预算；
- 击穿上限抛 `LimitExceeded`，其失败码决定终态（`needs_human`），而不是静默截断；
- 计数只增不减：恢复（resume）时计数从 checkpoint 里读回来，不能"重新开始数"。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Tuple, Final

from .errors import LimitExceeded
from .models import FailureCode, GraphState

__all__ = ["LIMIT_RULES", "LimitKind", "charge", "charge_node_run", "describe_budget"]


class LimitKind(str, Enum):
    REPAIR_ROUNDS = "repair_rounds"
    TOOL_CALLS = "tool_calls"
    NODE_RUNS = "node_runs"
    TOKENS = "tokens"
    COST_UNITS = "cost_units"
    ELAPSED_MS = "elapsed_ms"


@dataclass(frozen=True)
class LimitRule:
    counter: str
    limit: str
    code: FailureCode
    description: str


# 每一种计数对应一个上限字段与一个失败码；`token` 与费用是按量计的，其余按次计。
LIMIT_RULES: Final[Mapping[LimitKind, LimitRule]] = {
    LimitKind.REPAIR_ROUNDS: LimitRule(
        "repair_rounds", "max_repair_rounds", FailureCode.LIMIT_REPAIR_ROUNDS, "repair 轮次"
    ),
    LimitKind.TOOL_CALLS: LimitRule(
        "tool_calls", "max_tool_calls", FailureCode.LIMIT_TOOL_CALLS, "工具调用次数"
    ),
    LimitKind.NODE_RUNS: LimitRule(
        "node_runs", "max_node_runs", FailureCode.LIMIT_NODE_RUNS, "节点执行次数"
    ),
    LimitKind.TOKENS: LimitRule("tokens", "max_tokens", FailureCode.LIMIT_TOKENS, "token 预算"),
    LimitKind.COST_UNITS: LimitRule(
        "cost_units", "max_cost_units", FailureCode.LIMIT_COST, "费用单位"
    ),
    LimitKind.ELAPSED_MS: LimitRule(
        "elapsed_ms", "max_elapsed_ms", FailureCode.LIMIT_WALL_CLOCK, "墙钟预算"
    ),
}


def charge(state: GraphState, kind: LimitKind, amount: int = 1) -> GraphState:
    """记一次用量并检查上限；超限抛 `LimitExceeded`（终态 needs_human）。

    返回**新状态**：计数器只增不减，恢复时从 checkpoint 继续数。
    """

    if not isinstance(kind, LimitKind):
        raise LimitExceeded(f"未知的上限类别：{kind!r}", node=state.stage)
    if amount < 0:
        raise LimitExceeded("用量不能为负", node=state.stage)
    rule = LIMIT_RULES[kind]
    current = int(getattr(state.counters, rule.counter))
    limit = int(getattr(state.limits, rule.limit))
    updated = current + amount
    if updated > limit:
        # 失败码决定终态（needs_human）；这里不做任何"截断后继续"。
        error = LimitExceeded(
            f"{rule.description}超过上限：{updated} > {limit}",
            node=state.stage,
        )
        error.code = rule.code
        raise error
    counters = state.counters.model_copy(update={rule.counter: updated})
    return state.replace(counters=counters)


def charge_node_run(state: GraphState) -> GraphState:
    """节点执行前调用一次：先记账再执行，恢复时不会把同一轮重数一遍。"""

    return charge(state, LimitKind.NODE_RUNS, 1)


def describe_budget(state: GraphState) -> Tuple[Tuple[str, int, int], ...]:
    """(名称, 已用, 上限) 的有序摘要，供报告与 CLI 展示。"""

    items: list[Tuple[str, int, int]] = []
    for kind in LimitKind:
        rule = LIMIT_RULES[kind]
        items.append(
            (
                rule.counter,
                int(getattr(state.counters, rule.counter)),
                int(getattr(state.limits, rule.limit)),
            )
        )
    return tuple(items)
