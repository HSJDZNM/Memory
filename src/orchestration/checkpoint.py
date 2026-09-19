"""Checkpoint：带版本、带幂等键、可恢复，而且**不存正文**。

阶段计划 §5 的两句话是这里的全部要求：

1. `Checkpoint 保存状态版本和已完成节点的幂等键。`
2. `恢复时先确认规则集、索引和工具 schema 版本是否仍兼容；不兼容时重新评估，不沿用旧 allow。`

实现选择（写在 Phase 8 实施记录里）：

- 存储是**单文件原子替换**：先写 `*.tmp` 再 `os.replace`，崩溃只会留下旧版本，不会留下半份；
- 记录里存 `GraphState` 的规范化 JSON 与它的 sha256，读回时逐字节校验；
- 版本、字段、摘要任何一项对不上都抛 `CheckpointError`（失败关闭）；
- 兼容性由 `PlatformSnapshot` 决定，结论是三种之一：`resume` / `revalidate` / `refuse`。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, Tuple, runtime_checkable

from pydantic import Field, field_validator

from .errors import CheckpointError, ResumeError
from .models import (
    SUPPORTED_STATE_SCHEMA_VERSIONS,
    GraphState,
    PlatformSnapshot,
    RunStatus,
    StrictModel,
    canonical_digest,
)

__all__ = [
    "CHECKPOINT_SCHEMA_VERSION",
    "SUPPORTED_CHECKPOINT_SCHEMA_VERSIONS",
    "CheckpointRecord",
    "CheckpointStore",
    "JsonCheckpointStore",
    "ResumeMode",
    "ResumePlan",
    "plan_resume",
]

CHECKPOINT_SCHEMA_VERSION = "1.0"
SUPPORTED_CHECKPOINT_SCHEMA_VERSIONS = frozenset({CHECKPOINT_SCHEMA_VERSION})

# 兼容性维度 → 恢复动作。规则集/索引变了要重新评估；工具 schema 变了要重新审批；
# 协议世代（决策载荷、状态形状）变了根本不能接着跑。
_REVALIDATE_DIMENSIONS = ("rule_set_hash", "index_version")
_REAPPROVE_DIMENSIONS = ("tool_schema_hash",)
_REFUSE_DIMENSIONS = ("policy_version", "decision_schema_version")


class CheckpointRecord(StrictModel):
    """一条 checkpoint：状态载荷 + 摘要 + 兼容性凭据 + 引擎标识。"""

    checkpoint_schema_version: str = CHECKPOINT_SCHEMA_VERSION
    task_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=0)
    sequence: int = Field(ge=1)
    engine: str = Field(min_length=1, max_length=40)
    stage: str = Field(min_length=1, max_length=64)
    state: Mapping[str, Any]
    state_digest: str = Field(min_length=1, max_length=80)
    compatibility: PlatformSnapshot
    # 覆盖**除本字段之外**的整条记录：只保护 state 的话，改掉 compatibility
    # （例如把 rule_set_hash 改成当前值）就能让恢复跳过重新评估。
    record_digest: str = ""

    def computed_digest(self) -> str:
        payload = json.loads(self.model_dump_json())
        payload.pop("record_digest", None)
        return canonical_digest(payload)

    @field_validator("checkpoint_schema_version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        if value not in SUPPORTED_CHECKPOINT_SCHEMA_VERSIONS:
            raise ValueError(f"未知的 checkpoint 版本：{value}")
        return value


@runtime_checkable
class CheckpointStore(Protocol):
    def save(self, record: CheckpointRecord) -> None: ...

    def load(self, task_id: str) -> CheckpointRecord: ...

    def exists(self, task_id: str) -> bool: ...


def build_record(
    state: GraphState,
    *,
    engine: str,
    sequence: int,
    compatibility: Optional[PlatformSnapshot] = None,
) -> CheckpointRecord:
    """从状态构造 checkpoint：摘要覆盖状态载荷，兼容性默认取状态里的快照。"""

    payload = state.payload()
    snapshot = compatibility or state.snapshot or PlatformSnapshot()
    record = CheckpointRecord(
        task_id=state.task_id,
        revision=state.revision,
        sequence=sequence,
        engine=engine,
        stage=state.stage.value,
        state=payload,
        state_digest=canonical_digest(payload),
        compatibility=snapshot,
    )
    return record.model_copy(update={"record_digest": record.computed_digest()})


class JsonCheckpointStore:
    """每任务一个 JSON 文件；写入是原子替换，读取逐字节校验。"""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, task_id: str) -> Path:
        safe = "".join(ch for ch in task_id if ch.isalnum() or ch in "-_.")
        if not safe:
            raise CheckpointError("task_id 里没有可用字符，拒绝构造 checkpoint 路径")
        return self.root / f"{safe}.checkpoint.json"

    def exists(self, task_id: str) -> bool:
        return self.path_for(task_id).is_file()

    def save(self, record: CheckpointRecord) -> None:
        # 摘要必须与载荷一致：不一致说明调用方在写一份自相矛盾的 checkpoint。
        expected = canonical_digest(dict(record.state))
        if expected != record.state_digest:
            raise CheckpointError("checkpoint 的 state_digest 与 state 不一致，拒绝写入")
        if record.record_digest != record.computed_digest():
            raise CheckpointError("checkpoint 的 record_digest 与记录不一致，拒绝写入")
        target = self.path_for(record.task_id)
        temporary = target.with_suffix(".tmp")
        text = json.dumps(
            json.loads(record.model_dump_json()), ensure_ascii=False, indent=2, sort_keys=True
        )
        temporary.write_text(text + chr(10), encoding="utf-8", newline=chr(10))
        # Windows 上"刚写完就替换"偶发 WinError 5（索引器/杀毒短暂持有句柄，实测约 0.5%）：
        # 这是环境噪声，不是编排语义，因此做**有界**重试（3 次，间隔很短）。
        # 重试失败仍然抛出：绝不"写不进去就当写成功"。
        last_error: Optional[OSError] = None
        for attempt in range(3):
            try:
                os.replace(temporary, target)
                return
            except PermissionError as error:  # pragma: no cover - 依赖宿主环境
                last_error = error
                time.sleep(0.05 * (attempt + 1))
        raise CheckpointError(f"checkpoint 写入失败（{type(last_error).__name__}）") from last_error

    def load(self, task_id: str) -> CheckpointRecord:
        path = self.path_for(task_id)
        if not path.is_file():
            raise CheckpointError(f"没有找到 {task_id} 的 checkpoint：不能凭空恢复")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CheckpointError(f"checkpoint 不可解析（{type(error).__name__}）") from error
        if not isinstance(document, Mapping):
            raise CheckpointError("checkpoint 顶层必须是 JSON 对象")
        try:
            record = CheckpointRecord.model_validate(dict(document))
        except Exception as error:  # noqa: BLE001 - 未知字段 / 未知版本一律拒绝
            raise CheckpointError(f"checkpoint 记录不合法：{error}") from error
        if canonical_digest(dict(record.state)) != record.state_digest:
            raise CheckpointError("checkpoint 的 state_digest 校验失败：内容被改过或写坏了")
        if record.record_digest != record.computed_digest():
            # 只校验 state 的话，改掉 compatibility（比如把规则集哈希改成当前值）
            # 就能让恢复跳过"重新评估"——那正是最需要保护的一块。
            raise CheckpointError("checkpoint 的 record_digest 校验失败：记录被改过或写坏了")
        version = record.state.get("state_schema_version")
        if version not in SUPPORTED_STATE_SCHEMA_VERSIONS:
            raise CheckpointError(f"checkpoint 里的状态版本不可读：{version!r}")
        return record


class ResumeMode(str, Enum):
    FRESH = "fresh"
    RESUME = "resume"
    REVALIDATE = "revalidate"
    REAPPROVE = "reapprove"
    REFUSE = "refuse"


@dataclass(frozen=True)
class ResumePlan:
    mode: ResumeMode
    state: Optional[GraphState]
    changed: Tuple[str, ...] = ()
    detail: str = ""


def plan_resume(
    record: Optional[CheckpointRecord],
    current: PlatformSnapshot,
    *,
    fresh_state: GraphState,
) -> ResumePlan:
    """决定"能不能接着跑"。

    - 没有 checkpoint → `FRESH`（从头开始）；
    - 协议世代变了（`policy_version` / 决策载荷 schema）→ `REFUSE`：不沿用任何旧决定；
    - 规则集或索引变了 → `REVALIDATE`：清掉旧 trace / 旧验证结果，回到检索节点重评；
    - 工具 schema 变了 → `REAPPROVE`：清掉审批引用（旧审批绑的是旧 schema 的哈希）；
    - 其余 → `RESUME`：接着上次的阶段继续。
    """

    if record is None:
        return ResumePlan(
            mode=ResumeMode.FRESH, state=fresh_state, detail="没有 checkpoint，从头开始"
        )
    changed = record.compatibility.incompatible_with(current)
    refused = tuple(name for name in changed if name in _REFUSE_DIMENSIONS)
    if refused:
        raise ResumeError(
            "checkpoint 与当前平台的协议世代不兼容（"
            + "、".join(refused)
            + "）：拒绝恢复，必须重新开始"
        )
    # 恢复 = "从这里再试一次"：上一轮的终止标记不能带进新一轮，
    # 否则引擎会在第一个节点之后立刻因为"还有 failure"而停下。
    state = _revivable(GraphState.model_validate(dict(record.state)))
    revalidate = tuple(name for name in changed if name in _REVALIDATE_DIMENSIONS)
    reapprove = tuple(name for name in changed if name in _REAPPROVE_DIMENSIONS)
    if revalidate:
        cleared = state.model_copy(
            update={
                "traces": (),
                "validation": None,
                "test_validation": None,
                "contexts": (),
                "stage": _rewind_stage(state.stage),
                "notes": state.notes
                + (f"规则集或索引变化（{', '.join(revalidate)}）：旧决定作废，重新评估",),
            }
        )
        return ResumePlan(
            mode=ResumeMode.REVALIDATE,
            state=cleared.replace(),
            changed=changed,
            detail="规则集或索引已变化：不沿用旧 allow",
        )
    if reapprove:
        cleared = state.model_copy(
            update={
                "approvals": (),
                "notes": state.notes + ("工具 schema 变化：旧审批作废，需要重新审批",),
            }
        )
        return ResumePlan(
            mode=ResumeMode.REAPPROVE,
            state=cleared.replace(),
            changed=changed,
            detail="工具 schema 已变化：审批需要重新签发",
        )
    return ResumePlan(
        mode=ResumeMode.RESUME, state=state, changed=changed, detail="与当前平台兼容，接着跑"
    )


def _revivable(state: GraphState) -> GraphState:
    """清掉"上一轮为什么停下"的痕迹：失败码与终态都不是工作流的进度。"""

    if state.failure is None and state.status is RunStatus.RUNNING:
        return state
    return state.replace(status=RunStatus.RUNNING, failure=None)


def _rewind_stage(stage):
    """规则集/索引变化后退回还需要平台判断的第一个节点。"""

    from .models import NodeId

    order = (
        NodeId.REQUIREMENT_ANALYSIS,
        NodeId.POLICY_RETRIEVAL,
        NodeId.ARCHITECTURE_PLANNING,
        NodeId.IMPLEMENTATION,
        NodeId.VALIDATION,
        NodeId.REPAIR,
        NodeId.TESTING,
        NodeId.REVIEW,
    )
    if stage in order and order.index(stage) < order.index(NodeId.POLICY_RETRIEVAL):
        return stage
    return NodeId.POLICY_RETRIEVAL
