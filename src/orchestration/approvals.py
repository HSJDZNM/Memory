"""人工审批门禁：参数绑定、限期、单次使用，**语义来自 Phase 4，不另起一套**。

阶段计划 §6：`高影响动作使用参数绑定、有效期有限的审批引用。恢复或参数改变后重新审批，
不能把"图已到达该节点"视为用户批准。`

因此这里：

- 审批记录就是 Phase 4 的 `ApprovalRecord`（同一个文件格式、同一套校验函数
  `enforcement.approvals.verify_approval`）——本包不发明第二种审批语义；
- 判定仍然由 Phase 4 的函数做；本包只把"为什么拒绝"翻译成编排层的**失败码**
  （失败码是编排层的契约，调用方按码分支），翻译依据是**结构化字段**，不是错误文本；
- 单次使用记在状态里（`ApprovalUse.uses`），并同时受 `RunLimits.max_approval_uses` 约束；
- 恢复时审批必须重新校验：参数一变 action_hash 就变，旧审批自动作废。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence, Tuple

from enforcement.approvals import ApprovalRecord, load_approval, verify_approval

from .errors import ApprovalError
from .models import ApprovalUse, FailureCode, GraphState, NodeId

__all__ = ["ApprovalDecision", "ApprovalGate", "approval_binding_digest"]


def approval_binding_digest(action_hash: str, action_id: str) -> str:
    """审批绑定的就是这三件事：action_hash（含参数与 schema）、动作、工具。"""

    return f"{action_hash}|{action_id}"


@dataclass(frozen=True)
class ApprovalDecision:
    granted: bool
    approval_id: Optional[str] = None
    detail: str = ""
    code: Optional[FailureCode] = None


class ApprovalGate:
    """按文件路径加载审批记录，并按 `verify_approval` 的结论放行或拒绝。"""

    def __init__(
        self,
        path: Optional[Path | str],
        *,
        approval_roles: Sequence[str] = ("reviewer",),
        clock=None,
    ) -> None:
        self.path = None if path is None else Path(path)
        self.approval_roles = tuple(approval_roles)
        # 时钟可注入：测试里"过期"必须是确定性的，不能靠 sleep。
        self._clock = clock

    def _now(self) -> datetime:
        if self._clock is not None:
            return self._clock()
        from enforcement.models import utc_now

        return utc_now()

    def locate(self, action_id: Optional[str] = None) -> Optional[Tuple[Path, ApprovalRecord]]:
        """读审批记录，并返回它来自哪个文件。

        路径既可以是**一个文件**（Phase 4 CLI 的 `--approval` 语义），也可以是
        **一个目录**（"审批收件箱"）：目录里按文件名排序逐个尝试，取第一条
        `action_id` 匹配的记录。按 action_id 而不是 action_hash 挑选，是为了让
        "主体不符 / 参数漂移 / 已过期"能给出**具体**的失败码，而不是笼统的"没有审批"。

        返回文件路径是必要的：这份审批随后要**原样**交给 Phase 4 的 pre-check
        （判定权在平台，编排层只负责找到它）。
        """

        if self.path is None:
            return None
        if self.path.is_file():
            try:
                return self.path, load_approval(self.path)
            except Exception:  # noqa: BLE001 - 读不出来等于没有审批
                return None
        if not self.path.is_dir():
            return None
        fallback: Optional[Tuple[Path, ApprovalRecord]] = None
        for candidate in sorted(self.path.glob("*.json")):
            try:
                record = load_approval(candidate)
            except Exception:  # noqa: BLE001 - 坏文件跳过，不让它挡住其它审批
                continue
            if action_id is not None and record.action_id == action_id:
                return candidate, record
            if fallback is None:
                fallback = (candidate, record)
        return fallback

    def _record(self, action_id: Optional[str] = None) -> Optional[ApprovalRecord]:
        located = self.locate(action_id)
        return None if located is None else located[1]

    def resolve(self, action_id: str) -> Optional[Path]:
        """找到这份审批所在的**文件**：交给 Phase 4 的 pre-check 用。"""

        located = self.locate(action_id)
        return None if located is None else located[0]

    # ------------------------------------------------------------------ 判定
    def _classify(
        self,
        record: Optional[ApprovalRecord],
        *,
        action_hash,
        action_id,
        tool_id,
        subject,
        uses_left: int,
    ) -> Optional[FailureCode]:
        """把不符合项翻译成失败码（依据结构化字段，不解析错误文本）。"""

        if record is None:
            return FailureCode.APPROVAL_MISSING
        if (
            record.action_hash != action_hash
            or record.action_id != action_id
            or record.tool_id != tool_id
        ):
            return FailureCode.APPROVAL_PARAM_MISMATCH
        if subject is None or record.subject != subject:
            return FailureCode.APPROVAL_SUBJECT_MISMATCH
        if self._now() >= record.expires_at:
            return FailureCode.APPROVAL_EXPIRED
        if uses_left <= 0:
            return FailureCode.APPROVAL_CONSUMED
        return None

    def use(
        self,
        state: GraphState,
        *,
        node: NodeId,
        action_hash: str,
        action_id: str,
        tool_id: str,
        subject: Optional[str],
    ) -> ApprovalUse:
        """校验并消费一次审批；任何不符都抛 `ApprovalError`（带失败码）。"""

        record = self._record(action_id)
        used = sum(
            item.uses
            for item in state.approvals
            if item.approval_id == (record.approval_id if record else "")
            and item.action_hash == action_hash
        )
        uses_left = min(
            state.limits.max_approval_uses - used,
            state.limits.max_approval_uses,
        )
        code = self._classify(
            record,
            action_hash=action_hash,
            action_id=action_id,
            tool_id=tool_id,
            subject=subject,
            uses_left=uses_left,
        )
        if code is not None:
            error = ApprovalError(
                _message_for(code, node=node, action_hash=action_hash, action_id=action_id),
                node=node,
            )
            error.code = code
            raise error
        assert record is not None  # _classify 已经排除了 None
        try:
            # 判定权仍然在 Phase 4：角色、签发时间与单次使用都由它复核。
            verify_approval(
                record,
                action_hash=action_hash,
                action_id=action_id,
                tool_id=tool_id,
                subject=subject,
                approval_roles=self.approval_roles,
                used=used >= state.limits.max_approval_uses,
                now=self._now(),
            )
        except Exception as error:  # noqa: BLE001 - Phase 4 拒绝即拒绝，只翻译分类
            raise ApprovalError(
                f"审批被平台拒绝：{type(error).__name__}", node=node
            ) from error
        return ApprovalUse(
            node=node,
            approval_id=record.approval_id,
            action_hash=action_hash,
            subject=record.subject,
            issued_at=record.granted_at.isoformat(),
            expires_at=record.expires_at.isoformat(),
            uses=1,
        )

    @staticmethod
    def consume(state: GraphState, use: ApprovalUse) -> GraphState:
        """把一次审批使用记进状态：同名同哈希的引用累加使用次数。"""

        items = list(state.approvals)
        for index, item in enumerate(items):
            if item.approval_id == use.approval_id and item.action_hash == use.action_hash:
                items[index] = item.model_copy(update={"uses": item.uses + use.uses})
                return state.replace(approvals=tuple(items))
        items.append(use)
        return state.replace(approvals=tuple(items))


def _message_for(
    code: FailureCode, *, node: NodeId, action_hash: str, action_id: str = ""
) -> str:
    messages = {
        FailureCode.APPROVAL_MISSING: "该动作需要审批，但缺少与当前 action_hash 绑定的审批记录",
        FailureCode.APPROVAL_PARAM_MISMATCH: "审批绑定的动作、工具或参数与当前请求不一致",
        FailureCode.APPROVAL_SUBJECT_MISMATCH: "审批主体与当前请求主体不一致：审批不得跨主体复用",
        FailureCode.APPROVAL_EXPIRED: "审批已过期：必须重新审批",
        FailureCode.APPROVAL_CONSUMED: "审批已被用完：恢复不会让它重新生效",
    }
    return (
        f"[{node.value}] {messages.get(code, '审批不可用')}"
        f"（action_id={action_id}，action_hash={action_hash[:16]}…）"
    )
