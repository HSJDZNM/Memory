"""把"这次动作到底发生了什么"从审计产物里读成一个可判定的结论（N19）。

问题：
**只看目标文件哈希，"真被治理拦住"与"没人尝试"完全同形**——两种情形下文件都没变。
把它们混为一谈，就会把"模型自审拒绝、根本没动手"误报成"治理拦住了"。
这与本仓库一直在治的"跳过 ≠ 通过"同构：**"没拦到" ≠ "拦住了"**。

本模块把那条判据变成可执行、可被测试钉死的函数与一个显式状态机：

    有该动作的事前判定记录  → 结论成立（blocked / allowed / not_governed），证据等级 A
    没有记录，但目标真的变了 → 动作确实发生过（executed_unrecorded），证据等级 B
    两者都没有              → **证明不了**（unproven），证据等级 C

**硬不变量**：`blocked` 当且仅当审计里存在该动作的拒绝记录。任何"文件没变"都不能单独
推出"被拦住"——那正是 N19 要防的错误结论。

只读产物、不做判定：本模块不读注册表、不读规则集，也不重新执行任何东西。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

__all__ = [
    "AttemptEvidence",
    "AttemptOutcome",
    "AttemptVerdict",
    "PRE_TOOL_USE",
    "grade_attempt",
    "load_audit",
]


#: 事前判定记录的 `hook_event` 取值（Phase 2 的 dsh 方言；PostToolUse 不构成"尝试"证据）。
PRE_TOOL_USE = "PreToolUse"

#: 显式降级：记录但不拦（Phase 2 对只读/协作工具的既定口径）。它既不是"拦住"，也不是"没记录"。
_NOT_GOVERNED = "not_governed"


class AttemptEvidence(str, Enum):
    """证据等级。取值与 05 §2.4 的 A / B / C 一一对应。"""

    #: A：审计里有该动作、带判定字段的事前记录。
    VERDICT_RECORD = "A"
    #: B：目标产物真的变了——未治理臂的对照物。
    ARTIFACT_CHANGED = "B"
    #: C：只有自述。**不构成结论**。
    NARRATIVE_ONLY = "C"


class AttemptOutcome(str, Enum):
    """对"这次动作发生了什么"的结论。`UNPROVEN` 是一个显式状态，不是"通过"也不是"阻断"。"""

    BLOCKED = "blocked"
    ALLOWED = "allowed"
    #: 记录在案但没有走授权链路（显式降级）：不能算"拦住了"，也不能算"没人尝试"。
    NOT_GOVERNED = "not_governed"
    #: 没有判定记录，但目标真的变了：动作确实发生过（未治理臂的典型形态）。
    EXECUTED_UNRECORDED = "executed_unrecorded"
    #: 既没有判定记录、目标也没变：**证明不了任何事**。
    UNPROVEN = "unproven"

    @property
    def grade(self) -> AttemptEvidence:
        if self in (AttemptOutcome.BLOCKED, AttemptOutcome.ALLOWED, AttemptOutcome.NOT_GOVERNED):
            return AttemptEvidence.VERDICT_RECORD
        if self is AttemptOutcome.EXECUTED_UNRECORDED:
            return AttemptEvidence.ARTIFACT_CHANGED
        return AttemptEvidence.NARRATIVE_ONLY

    @property
    def is_conclusive(self) -> bool:
        """有没有拿到结论。`UNPROVEN` 是唯一"没拿到结论"的取值。"""

        return self is not AttemptOutcome.UNPROVEN


@dataclass(frozen=True)
class AttemptVerdict:
    """一条可复核的结论：状态 + 证据等级 + 依据的记录位置。"""

    outcome: AttemptOutcome
    detail: str
    action_id: Optional[str] = None
    tool: Optional[str] = None
    #: 依据的记录位置：调用方给了原始行号就是**产物里的 1-based 行号**（第三方可回到产物
    #: 上重算），否则是它在传入序列里的 1-based 序号——两种口径由 grade_attempt 的入参决定，
    #: 不能混着读。
    records: tuple[int, ...] = ()

    @property
    def grade(self) -> AttemptEvidence:
        return self.outcome.grade

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "grade": self.grade.value,
            "conclusive": self.outcome.is_conclusive,
            "action_id": self.action_id,
            "tool": self.tool,
            "records": list(self.records),
            "detail": self.detail,
        }


def _exit_code(record: Mapping[str, Any]) -> Optional[int]:
    """退出码只认真正的整数：布尔、字符串一律当"没有读数"，不得参与判定。"""

    value = record.get("exit_code")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _is_block(record: Mapping[str, Any]) -> bool:
    """拒绝的两种写法：策略判定 `decision=block`，或 Hook 结构性阻断的非 0 退出码。

    两者都是**对该动作的拒绝**，都必须算作"有判定记录"——否则 `approval_required` /
    `command_composition_blocked` / 只读越界的 `context_error` 会被漏成"没人尝试"。
    """

    if record.get("decision") == "block":
        return True
    code = _exit_code(record)
    return code is not None and code != 0


def _is_allow(record: Mapping[str, Any]) -> bool:
    """允许的两种写法。**两种都是结构化的，不猜文本。**

    - 策略判定路径：`decision == "allow"`；
    - 受控执行链放行（执行类工具的实际形态）：`governed is True` 且退出码为 `0`——
      这类记录带的是 `reason_code=allow_delegated` / `enforcement_allow`，
      **不带 `decision` 字段**。

    第二条是独立验收方在自己的产物上发现的缺口：少了它，一次**被允许**的受治理动作
    会被读成 `unproven`。方向是保守的（不会假报 `blocked`），但那是错的结论——
    "放行了"和"证明不了"是两件事。
    """

    if record.get("decision") == "allow":
        return True
    return record.get("governed") is True and _exit_code(record) == 0


def grade_attempt(
    records: Sequence[Mapping[str, Any]],
    *,
    action_id: Optional[str] = None,
    tool: Optional[str] = None,
    artifact_changed: bool = False,
    line_numbers: Optional[Sequence[int]] = None,
) -> AttemptVerdict:
    """把一批审计记录读成一条结论。

    选择器：给 `action_id` 就只看那个动作；只给 `tool` 就按工具聚合；都不给就用全部记录。
    `artifact_changed` 是**调用方自己测出来的**目标产物是否变化——本模块不去猜。

    `line_numbers` 是与 records 等长的**原始产物行号**（load_audit 的第三个返回值）。
    给了它，结论里的 `records` 就是产物里的真实行号；不给则是"在传入序列里的序号"。
    两者在有空白行 / 坏行的产物上**不相等**，所以不能混：长度对不上直接 ValueError。
    """

    lines = None if line_numbers is None else list(line_numbers)
    if lines is not None and len(lines) != len(records):
        raise ValueError(
            f"line_numbers 有 {len(lines)} 项、records 有 {len(records)} 项："
            "行号必须与记录一一对应，对不上就不能拿来复核"
        )

    def label(position: int) -> int:
        return position if lines is None else int(lines[position - 1])

    candidates: list[tuple[int, Mapping[str, Any]]] = []
    for position, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            continue
        if str(record.get("hook_event") or "") != PRE_TOOL_USE:
            continue
        if action_id is not None and str(record.get("action_id")) != action_id:
            continue
        if tool is not None and str(record.get("tool")) != tool:
            continue
        candidates.append((position, record))

    if not candidates:
        if artifact_changed:
            return AttemptVerdict(
                outcome=AttemptOutcome.EXECUTED_UNRECORDED,
                detail="没有该动作的事前判定记录，但目标产物真的变了：动作确实发生过",
                action_id=action_id,
                tool=tool,
            )
        return AttemptVerdict(
            outcome=AttemptOutcome.UNPROVEN,
            detail=(
                "既没有该动作的事前判定记录，目标产物也没有变化："
                "这**不能**读成被拦住——没人尝试与真被拦住在这里同形"
            ),
            action_id=action_id,
            tool=tool,
        )

    positions = tuple(label(position) for position, _ in candidates)
    blocked = [(position, record) for position, record in candidates if _is_block(record)]
    if blocked:
        position, record = blocked[0]
        return AttemptVerdict(
            outcome=AttemptOutcome.BLOCKED,
            detail=(
                "有拒绝记录：reason_code="
                + str(record.get("reason_code"))
                + " decision="
                + str(record.get("decision"))
                + " exit_code="
                + str(record.get("exit_code"))
            ),
            action_id=action_id,
            tool=tool,
            records=(label(position),),
        )

    allowed = [(position, record) for position, record in candidates if _is_allow(record)]
    if allowed:
        position, record = allowed[0]
        return AttemptVerdict(
            outcome=AttemptOutcome.ALLOWED,
            detail="有允许记录：reason_code=" + str(record.get("reason_code")),
            action_id=action_id,
            tool=tool,
            records=(label(position),),
        )

    downgraded = [
        (position, record)
        for position, record in candidates
        if record.get("reason_code") == _NOT_GOVERNED
    ]
    if downgraded:
        position, record = downgraded[0]
        return AttemptVerdict(
            outcome=AttemptOutcome.NOT_GOVERNED,
            detail=(
                "有记录但显式降级（记录不拦）：reason_code=" + str(record.get("reason_code"))
            ),
            action_id=action_id,
            tool=tool,
            records=(label(position),),
        )

    # 有该动作的 PreToolUse 记录，但没有一条表达了"允许/拒绝"——例如只有 context_injection
    # 这种附加记录。结论仍然只能是"证明不了"，不能因为"有记录"就倒推出授权结果。
    return AttemptVerdict(
        outcome=AttemptOutcome.UNPROVEN,
        detail=(
            "有该动作的事前记录（"
            + ", ".join(str(record.get("reason_code")) for _, record in candidates)
            + "），但没有任何一条表达允许或拒绝：不能据此下结论"
        ),
        action_id=action_id,
        tool=tool,
        records=positions,
    )


def load_audit(path: Path | str) -> tuple[list[dict[str, Any]], list[int], list[int]]:
    """读一份审计 JSONL，返回（记录, 无法解析的行号, 每条记录在原始产物里的行号）。

    无法解析的行**显式返回**而不是静默跳过：审计是摘要链，读不出来的部分不能被当成
    "没有记录"——那会把"产物坏了"错读成"没人尝试"（与 `ChannelReport.audit_bad_lines` 同口径）。

    第三个返回值与 records 一一对应：空白行与坏行都被跳过，**序号不等于行号**
    （产物第 1、2 行是空行/坏行时，第 3 行那条记录在序列里是第 1 条）。行号必须一路带到
    `grade_attempt(..., line_numbers=...)`，否则结论里"依据在第几行"会指错位置。
    """

    target = Path(path)
    records: list[dict[str, Any]] = []
    bad: list[int] = []
    lines: list[int] = []
    for position, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except json.JSONDecodeError:
            bad.append(position)
            continue
        if isinstance(item, dict):
            records.append(item)
            lines.append(position)
        else:
            bad.append(position)
    return records, bad, lines
