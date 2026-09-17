"""Controlled Executor：只有"允许 + 全部绑定一致"时才执行，且至多执行一次。

执行器的判断完全不依赖自然语言：

1. pre 决策必须是 allow / allow_with_warnings，且带 grant；
2. grant 必须与当前动作逐位一致（action_hash、tool_id、schema 哈希、主体），未过期、
   未超过有效期上限、未被消费过；
3. 台账里必须先成功认领 action_id（重复 action 不会产生第二次副作用）；
4. 只有注册表声明的驱动存在时才执行；平台跑不了的驱动显式拒绝，不假装执行过。

执行之后立刻收集证据并跑 post-check，把 pre → 执行 → post 合成一个 FinalDecision，
三段都写进审计链，形成一条可重放的 trace。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Mapping, Optional

from policy.models import Decision

from .audit import AuditSink
from .drivers import DriverError, DriverResult, FileSnapshot, ToolDriver
from .ledger import EnforcementLedger
from .models import (
    ActionRequest,
    AuditError,
    AuditStage,
    ExecutionRecord,
    ExecutionStatus,
    FinalDecision,
    FinalOutcome,
    GrantError,
    LedgerError,
    PostDecision,
    PostEvidence,
    PostStatus,
    PreDecision,
    ReasonCode,
    RollbackMode,
    RollbackOutcome,
    ToolSpec,
    digest_of,
    utc_now,
)
from .postcheck import baseline_files, collect_evidence, restore_snapshot, validate

__all__ = [
    "ControlledExecutor",
    "ExecutionOutcome",
]


def _known_decision(pre: PreDecision) -> Decision:
    """把决策值收敛到封闭枚举；不认识的值按阻断处理（绝不默认放行）。"""

    value = pre.decision
    if isinstance(value, Decision):
        return value
    try:
        return Decision(str(value))
    except ValueError:
        return Decision.BLOCK


@dataclass
class ExecutionOutcome:
    """一次受控执行的完整结果（可直接序列化进审计与测试断言）。"""

    final: FinalDecision
    record: ExecutionRecord
    pre: PreDecision
    evidence: Optional[PostEvidence] = None
    post: Optional[PostDecision] = None
    snapshot: Optional[FileSnapshot] = None
    driver_result: Optional[DriverResult] = None
    notes: list[str] = field(default_factory=list)


class ControlledExecutor:
    """受控执行器。构造一次，执行多次；每次执行都必须带 pre 决策与 grant。"""

    def __init__(
        self,
        *,
        ledger: EnforcementLedger,
        drivers: Mapping[str, ToolDriver],
        sink: Optional[AuditSink] = None,
        max_grant_ttl_seconds: int = 300,
    ) -> None:
        self.ledger = ledger
        self.drivers = drivers
        self.sink = sink
        self.max_grant_ttl_seconds = max_grant_ttl_seconds

    # ------------------------------------------------------------------ 审计
    def _audit(
        self, stage: AuditStage, request: ActionRequest, payload: Mapping[str, object]
    ) -> Optional[str]:
        """写一条审计记录；失败返回原因而不是抛异常。

        pre 阶段已经用"审计不可写 → block"守住了执行前的一致性；
        执行之后再写不进去无法逆转事实，因此这里把失败如实记进 notes，
        不让它变成"静默成功"。
        """

        if self.sink is None:
            return "审计端口未配置：该次执行没有留下链上记录"
        try:
            self.sink.append(
                stage,
                payload=payload,
                trace_id=request.trace_id,
                action_id=request.action_id,
                request_id=request.request_id,
                tool_id=request.tool_id,
            )
        except AuditError as error:
            return f"审计写入失败（{stage.value}）：{error}"
        return None

    # ------------------------------------------------------------------ 执行
    def execute(
        self,
        request: ActionRequest,
        *,
        spec: ToolSpec,
        pre: PreDecision,
        workspace: Optional[Path | str] = None,
        untrusted_result: Optional[str] = None,
        now: Optional[datetime] = None,
        collect_post: bool = True,
    ) -> ExecutionOutcome:
        moment = now or utc_now()
        pre = pre.model_copy(update={"decision": _known_decision(pre)})
        baselines = baseline_files(request, spec, workspace=workspace)
        notes: list[str] = []

        def note(message: Optional[str]) -> None:
            if message:
                notes.append(message)

        refusal = self._refusal_reason(request, spec, pre, moment=moment)
        if refusal is not None:
            record = self._record(
                request,
                spec,
                status=ExecutionStatus.REFUSED,
                reason_code=refusal,
                detail=f"拒绝执行：{refusal.value}",
                started=moment,
                finished=moment,
            )
            note(
                self._audit(
                    AuditStage.EXECUTION,
                    request,
                    {
                        "status": record.status.value,
                        "reason_code": record.reason_code.value,
                        "action_hash": request.action_hash,
                    },
                )
            )
            return ExecutionOutcome(
                final=self._final(request, spec, pre, record, None),
                record=record,
                pre=pre,
                notes=notes,
            )

        grant = pre.grant
        assert grant is not None
        try:
            self.ledger.consume_grant(grant, now=moment)
        except GrantError as error:
            record = self._record(
                request,
                spec,
                status=ExecutionStatus.REFUSED,
                reason_code=ReasonCode.GRANT_REUSED,
                detail=str(error),
                started=moment,
                finished=moment,
            )
            note(
                self._audit(
                    AuditStage.EXECUTION,
                    request,
                    {
                        "status": record.status.value,
                        "reason_code": record.reason_code.value,
                        "action_hash": request.action_hash,
                    },
                )
            )
            return ExecutionOutcome(
                final=self._final(request, spec, pre, record, None),
                record=record,
                pre=pre,
                notes=notes,
            )

        driver = self.drivers.get(spec.id) or self.drivers.get(spec.driver.value)
        if driver is None:
            record = self._record(
                request,
                spec,
                status=ExecutionStatus.REFUSED,
                reason_code=ReasonCode.DRIVER_UNAVAILABLE,
                detail=f"没有为 {spec.driver.value} 注册执行驱动：平台不假装执行过",
                started=moment,
                finished=moment,
            )
            note(
                self._audit(
                    AuditStage.EXECUTION,
                    request,
                    {
                        "status": record.status.value,
                        "reason_code": record.reason_code.value,
                        "action_hash": request.action_hash,
                    },
                )
            )
            return ExecutionOutcome(
                final=self._final(request, spec, pre, record, None),
                record=record,
                pre=pre,
                notes=notes,
            )

        started = moment
        result: Optional[DriverResult] = None
        try:
            result = driver.execute(
                request, spec, workspace=None if workspace is None else Path(workspace)
            )
        except DriverError as error:
            finished = utc_now()
            record = self._record(
                request,
                spec,
                status=ExecutionStatus.FAILED,
                reason_code=ReasonCode.PROCESS_ERROR,
                detail=str(error),
                grant_id=grant.grant_id,
                started=started,
                finished=finished,
            )
        except Exception as error:  # noqa: BLE001 - 驱动异常必须变成结构化结果
            finished = utc_now()
            record = self._record(
                request,
                spec,
                status=ExecutionStatus.FAILED,
                reason_code=ReasonCode.PROCESS_ERROR,
                detail=f"{type(error).__name__}: {error}",
                grant_id=grant.grant_id,
                started=started,
                finished=finished,
            )
        else:
            finished = utc_now()
            record = self._record(
                request,
                spec,
                status=result.status,
                reason_code=(
                    ReasonCode.ALLOW
                    if result.status in (ExecutionStatus.EXECUTED, ExecutionStatus.DELEGATED)
                    else (
                        ReasonCode.EXECUTION_TIMEOUT
                        if result.timed_out
                        else ReasonCode.EXECUTION_FAILED
                    )
                ),
                detail=result.detail,
                exit_code=result.exit_code,
                timed_out=result.timed_out,
                stdout=result.stdout,
                stderr=result.stderr,
                structured=result.structured,
                driver=spec.driver,
                grant_id=grant.grant_id,
                started=started,
                finished=finished,
            )

        note(
            self._audit(
                AuditStage.EXECUTION,
                request,
                {
                    "status": record.status.value,
                    "reason_code": record.reason_code.value,
                    "action_hash": request.action_hash,
                    "exit_code": record.exit_code,
                    "timed_out": record.timed_out,
                    "duration_ms": record.duration_ms,
                    "stdout_digest": record.stdout_digest,
                    "stderr_digest": record.stderr_digest,
                    "driver": record.driver.value,
                    "grant_id": record.grant_id,
                },
            )
        )

        snapshot = None if result is None else result.snapshot
        evidence = None
        post = None
        rollback = None
        if collect_post:
            evidence = collect_evidence(
                request,
                spec,
                record,
                workspace=workspace,
                baselines=baselines,
                untrusted_result=untrusted_result,
                snapshot=snapshot,
                now=finished,
            )
            post, evidence = validate(
                request, spec, record, evidence, workspace=workspace, now=finished
            )
            rollback = self._maybe_rollback(request, spec, post, snapshot, workspace=workspace)
            if rollback is not None:
                post = post.model_copy(update={"rollback": rollback})
                if rollback.status == "applied":
                    post = post.model_copy(update={"status": PostStatus.REPAIR_REQUIRED})
            note(
                self._audit(
                    AuditStage.POST_EVIDENCE,
                    request,
                    {
                    "status": post.status.value,
                    "reason_code": post.reason_code.value,
                    "action_hash": request.action_hash,
                    "validators": [item.model_dump(mode="json") for item in evidence.validators],
                    "files": [
                        {
                            "path": item.path,
                            "changed": item.changed,
                            "sha256_before": item.sha256_before,
                            "sha256_after": item.sha256_after,
                            "diff_digest": item.diff_digest,
                        }
                        for item in evidence.files
                    ],
                    "process": None
                    if evidence.process is None
                    else {
                        "exit_code": evidence.process.exit_code,
                        "timed_out": evidence.process.timed_out,
                    },
                        "rollback": None
                        if rollback is None
                        else rollback.model_dump(mode="json"),
                    },
                )
            )

        final = self._final(request, spec, pre, record, post)
        try:
            self.ledger.record_execution(
                action_id=request.action_id,
                tool_id=request.tool_id,
                subject=request.subject,
                action_hash=request.action_hash,
                status=record.status.value,
                ok=(
                    record.status in (ExecutionStatus.EXECUTED, ExecutionStatus.DELEGATED)
                    and (post is None or post.status is not PostStatus.REPAIR_REQUIRED)
                    and (post is None or post.status is not PostStatus.INCONSISTENT)
                ),
                risk=request.risk.value,
            )
        except LedgerError:
            pass

        note(
            self._audit(
                AuditStage.FINAL_DECISION,
                request,
                {
                    "outcome": final.outcome.value,
                    "reason_code": final.reason_code.value,
                    "action_hash": request.action_hash,
                    "pre_decision": final.pre_decision.value,
                    "execution_status": None
                    if final.execution_status is None
                    else final.execution_status.value,
                    "post_status": None if final.post_status is None else final.post_status.value,
                    "detail": final.detail,
                },
            )
        )

        return ExecutionOutcome(
            final=final,
            record=record,
            pre=pre,
            evidence=evidence,
            post=post,
            snapshot=snapshot,
            driver_result=result,
            notes=notes,
        )

    # ------------------------------------------------------------------ 内部
    def _refusal_reason(
        self,
        request: ActionRequest,
        spec: ToolSpec,
        pre: PreDecision,
        *,
        moment: datetime,
    ) -> Optional[ReasonCode]:
        if pre.decision is Decision.BLOCK:
            return (
                pre.reason_code
                if pre.reason_code is not ReasonCode.ALLOW
                else ReasonCode.POLICY_BLOCK
            )
        if pre.grant is None:
            return ReasonCode.GRANT_INVALID
        if request.tool_id != spec.id:
            return ReasonCode.GRANT_INVALID
        if request.tool_schema_hash != spec.schema_hash:
            return ReasonCode.SCHEMA_NOT_APPROVED
        if not self.ledger.grant_recorded(pre.grant.grant_id, pre.grant.action_hash):
            # 只认本平台签发（pre-check 时登记）的凭据：手工构造的 grant 即使字段齐全也不认。
            return ReasonCode.GRANT_INVALID
        try:
            pre.grant.verify(
                request,
                now=moment,
                used=self.ledger.grant_used(pre.grant.grant_id),
                max_ttl_seconds=self.max_grant_ttl_seconds,
            )
        except GrantError as error:
            text = str(error)
            if "过期" in text:
                return ReasonCode.GRANT_EXPIRED
            if "已被使用" in text:
                return ReasonCode.GRANT_REUSED
            return ReasonCode.GRANT_INVALID
        return None

    def _maybe_rollback(
        self,
        request: ActionRequest,
        spec: ToolSpec,
        post: PostDecision,
        snapshot: Optional[FileSnapshot],
        *,
        workspace: Optional[Path | str],
    ) -> Optional[RollbackOutcome]:
        if post.status not in (PostStatus.REPAIR_REQUIRED, PostStatus.INCONSISTENT):
            if spec.rollback is RollbackMode.FILE_SNAPSHOT:
                return RollbackOutcome(
                    mode=RollbackMode.FILE_SNAPSHOT, status="skipped", detail="验证通过，无需回滚"
                )
            return None
        if spec.rollback is not RollbackMode.FILE_SNAPSHOT:
            return RollbackOutcome(
                mode=spec.rollback,
                status="unsupported",
                detail="该工具没有声明可回滚能力：副作用无法撤销，需要人工修复",
            )
        if snapshot is None:
            return RollbackOutcome(
                mode=RollbackMode.FILE_SNAPSHOT,
                status="unsupported",
                detail="没有可用的执行前快照（例如由 Agent 运行时执行）：不能假装回滚成功",
            )
        return restore_snapshot(snapshot, workspace=workspace)

    def _record(
        self,
        request: ActionRequest,
        spec: ToolSpec,
        *,
        status: ExecutionStatus,
        reason_code: ReasonCode,
        detail: str,
        started: datetime,
        finished: datetime,
        exit_code: Optional[int] = None,
        timed_out: bool = False,
        stdout: str = "",
        stderr: str = "",
        structured: Optional[Mapping[str, object]] = None,
        driver=None,
        grant_id: Optional[str] = None,
    ) -> ExecutionRecord:
        excerpt = (stdout or stderr or "").strip()
        if len(excerpt) > 600:
            excerpt = excerpt[:586] + "...[truncated]"
        return ExecutionRecord(
            action_id=request.action_id,
            request_id=request.request_id,
            trace_id=request.trace_id,
            action_hash=request.action_hash,
            grant_id=grant_id,
            tool_id=request.tool_id,
            risk=request.risk,
            status=status,
            reason_code=reason_code,
            driver=spec.driver if driver is None else driver,
            exit_code=exit_code,
            timed_out=timed_out,
            duration_ms=max(0, int((finished - started).total_seconds() * 1000)),
            stdout_digest=None if not stdout else digest_of(stdout),
            stderr_digest=None if not stderr else digest_of(stderr),
            output_excerpt=excerpt,
            structured_digest=None if structured is None else digest_of(dict(structured)),
            detail=detail,
            started_at=started,
            finished_at=finished,
        )

    def _final(
        self,
        request: ActionRequest,
        spec: ToolSpec,
        pre: PreDecision,
        record: ExecutionRecord,
        post: Optional[PostDecision],
    ) -> FinalDecision:
        if pre.decision.value == "block":
            outcome = FinalOutcome.BLOCKED
            reason = pre.reason_code
            detail = "pre-check 阻断：动作没有执行"
        elif record.status is ExecutionStatus.REFUSED:
            outcome = FinalOutcome.BLOCKED
            reason = record.reason_code
            detail = record.detail
        elif record.status is ExecutionStatus.FAILED:
            outcome = FinalOutcome.REPAIR_REQUIRED
            reason = record.reason_code
            detail = record.detail
        elif post is not None and post.status is PostStatus.INCONSISTENT:
            outcome = FinalOutcome.INCONSISTENT
            reason = post.reason_code
            detail = post.detail
        elif post is not None and post.status is PostStatus.REPAIR_REQUIRED:
            rolled_back = post.rollback is not None and post.rollback.status == "applied"
            outcome = FinalOutcome.ROLLED_BACK if rolled_back else FinalOutcome.REPAIR_REQUIRED
            reason = post.reason_code
            detail = post.detail
        else:
            outcome = FinalOutcome.DELIVERED
            reason = pre.reason_code
            detail = "执行完成，事后验证通过"
        return FinalDecision(
            outcome=outcome,
            reason_code=reason,
            action_id=request.action_id,
            request_id=request.request_id,
            trace_id=request.trace_id,
            action_hash=request.action_hash,
            tool_id=request.tool_id,
            risk=request.risk,
            pre_decision=pre.decision,
            execution_status=record.status,
            post_status=None if post is None else post.status,
            detail=detail,
            decided_at=utc_now(),
        )


def summarise_chain(outcome: ExecutionOutcome) -> dict[str, object]:
    """把三段合成一份可读摘要（CLI 与审计共用，不含参数原文）。"""

    return {
        "action_id": outcome.final.action_id,
        "action_hash": outcome.final.action_hash,
        "tool_id": outcome.final.tool_id,
        "pre": {
            "decision": outcome.pre.decision.value,
            "reason_code": outcome.pre.reason_code.value,
            "grant_id": None if outcome.pre.grant is None else outcome.pre.grant.grant_id,
        },
        "execution": {
            "status": outcome.record.status.value,
            "reason_code": outcome.record.reason_code.value,
            "exit_code": outcome.record.exit_code,
            "timed_out": outcome.record.timed_out,
        },
        "post": None
        if outcome.post is None
        else {
            "status": outcome.post.status.value,
            "reason_code": outcome.post.reason_code.value,
        },
        "final": {
            "outcome": outcome.final.outcome.value,
            "reason_code": outcome.final.reason_code.value,
        },
    }
