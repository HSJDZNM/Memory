"""审计链的重放与解释：一条 trace 从请求到终态必须能被重新读出来。

这里的"重放"不是重新执行工具，而是重新**解释**已经发生的事：

    用户请求 → 检索来源 → 模型提议 → Action Request → Pre Decision
    → 执行结果 → Post Evidence → Final Decision

三件事必须成立：链的摘要连续（没人改过历史）、阶段顺序合法、每个动作都有终态。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .audit import AuditChain, FileAuditSink
from .models import AuditError, AuditStage, parse_audit_record

__all__ = [
    "STAGE_ORDER",
    "TraceEntry",
    "TraceReport",
    "explain",
    "load_trace",
    "verify_chain",
]

STAGE_ORDER: tuple[AuditStage, ...] = (
    AuditStage.REQUEST,
    AuditStage.RETRIEVAL,
    AuditStage.PROPOSAL,
    AuditStage.ACTION_REQUEST,
    AuditStage.PRE_DECISION,
    AuditStage.EXECUTION,
    AuditStage.POST_EVIDENCE,
    AuditStage.FINAL_DECISION,
)

_STAGE_INDEX = {stage: index for index, stage in enumerate(STAGE_ORDER)}


@dataclass(frozen=True)
class TraceEntry:
    """一条已解释的审计记录。"""

    sequence: int
    stage: AuditStage
    payload: Mapping[str, Any]
    digest: str
    recorded_at: str = ""

    def summary(self) -> str:
        payload = self.payload
        if self.stage is AuditStage.PRE_DECISION:
            return f"decision={payload.get('decision')} reason={payload.get('reason_code')}"
        if self.stage is AuditStage.EXECUTION:
            return (
                f"status={payload.get('status')} exit={payload.get('exit_code')} "
                f"driver={payload.get('driver')}"
            )
        if self.stage is AuditStage.POST_EVIDENCE:
            return f"post={payload.get('status')} reason={payload.get('reason_code')}"
        if self.stage is AuditStage.FINAL_DECISION:
            return f"outcome={payload.get('outcome')} reason={payload.get('reason_code')}"
        return ", ".join(f"{key}={value}" for key, value in sorted(payload.items())[:4])


@dataclass
class TraceReport:
    """一次 trace 的完整重放结果。"""

    records: list[Mapping[str, Any]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    entries: list[TraceEntry] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def has_final(self) -> bool:
        return any(entry.stage is AuditStage.FINAL_DECISION for entry in self.entries)

    def payload_of(self, stage: AuditStage) -> Optional[Mapping[str, Any]]:
        for entry in self.entries:
            if entry.stage is stage:
                return entry.payload
        return None


def verify_chain(records: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """校验摘要链、序号与阶段顺序，返回问题列表。

    阶段顺序是**按动作**判断的：同一份审计文件里会有多个动作各自的
    pre → execution → post → final 序列，全局单调反而是错的。
    """

    issues = list(AuditChain.verify(records))
    highest: dict[str, int] = {}
    decided: set[str] = set()
    for index, item in enumerate(records):
        try:
            record = parse_audit_record(item)
        except AuditError as error:
            issues.append(f"#{index}: {error}")
            continue
        position = _STAGE_INDEX.get(record.stage)
        if position is None:
            issues.append(f"#{index}: 未知阶段 {record.stage!r}")
            continue
        # 以 action_id 为单位分组；没有 action_id 的记录（如请求阶段）单独成组。
        group = str(record.action_id or record.trace_id or "<unanchored>")

        if record.stage is AuditStage.PRE_DECISION:
            # 重试会重新走一次 pre-check：允许它开启新一轮，但之后仍必须按顺序推进。
            highest[group] = position
            decided.add(group)
            continue

        # "没有决策就没有执行"只针对**真的产生了效果**的阶段：
        # refused 的执行记录恰恰是"没有决策/决策属于别的动作"时的合法留痕。
        produced_effect = record.stage is AuditStage.EXECUTION and (
            str((record.payload or {}).get("status", "")) in ("executed", "delegated", "failed")
        )
        if (produced_effect or record.stage is AuditStage.POST_EVIDENCE) and group not in decided:
            issues.append(
                f"#{index}: {group} 出现 {record.stage.value} 之前没有任何 pre_decision "
                "（没有决策就不能有执行/证据记录）"
            )
        previous_index = highest.get(group, -1)
        if position < previous_index:
            issues.append(
                f"#{index}: 阶段顺序倒退（{group} 的 {record.stage.value} 出现在更晚的阶段之后）"
            )
        highest[group] = max(previous_index, position)
    return tuple(issues)


def load_trace(
    path: Path | str,
    *,
    trace_id: Optional[str] = None,
    action_id: Optional[str] = None,
    request_id: Optional[str] = None,
    require_final: bool = True,
) -> TraceReport:
    """按 trace / action / request 过滤一条链并解释它。"""

    sink = FileAuditSink(path)
    records = list(sink.chain_records())
    if not records:
        return TraceReport(issues=["审计日志里没有本层的链式记录（enforcement schema）"])

    issues = list(verify_chain(records))
    selected = [
        item
        for item in records
        if (trace_id is None or item.get("trace_id") == trace_id)
        and (action_id is None or item.get("action_id") == action_id)
        and (request_id is None or item.get("request_id") == request_id)
    ]
    if not selected:
        issues.append("没有匹配该 trace / action / request 的记录")

    entries: list[TraceEntry] = []
    for item in selected:
        record = parse_audit_record(item)
        entries.append(
            TraceEntry(
                sequence=record.sequence,
                stage=record.stage,
                payload=dict(record.payload),
                digest=record.digest,
                recorded_at=str(item.get("recorded_at", "")),
            )
        )
    entries.sort(key=lambda entry: entry.sequence)

    if require_final and entries and not any(
        entry.stage is AuditStage.FINAL_DECISION for entry in entries
    ):
        issues.append("该 trace 没有终态记录（final_decision）：链路不完整，不能判定为完成")

    return TraceReport(records=selected, issues=issues, entries=entries)


def explain(report: TraceReport) -> str:
    """把一条 trace 渲染成人能读的链路说明。"""

    lines: list[str] = []
    for entry in report.entries:
        lines.append(f"[{entry.sequence:>3}] {entry.stage.value:<14} {entry.summary()}")
    if not lines:
        lines.append("（没有记录）")
    return "\n".join(lines)
