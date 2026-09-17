"""Pre-execute Policy：把一次规范化动作判成 allow / allow_with_warnings / block。

检查顺序固定，每一项都留下结构化结论（checks），因此"为什么被拦"永远可解释：

    registry → action_window → principal → permissions → approval
    → policy（规则引擎，可显式跳过）→ rate_limit → circuit_breaker
    → ledger（重放 / 复用）→ audit（允许之后才写）

三条不可让步的性质：

1. **失败关闭**：任何一项 FAILED 都得到 block；审计不可写、台账不可用、
   规则引擎超时这类"关键组件失效"同样 block（除非注册表把低风险工具显式声明成 degrade）。
2. **授权与参数绑定**：允许时签发的 grant 含 action_hash，有效期短（由注册表数据决定），
   执行器只认它与当前动作逐位一致的情况——"换参数继续用旧决定"在数学上不可能。
3. **重放不可执行**：同一 action_id 的第二次请求在台账上已经被认领，
   直接 block（或由执行器返回既有结果），绝不会再执行一次。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Mapping, Optional, Sequence

from policy.models import Decision, RequiredAction, ValidationResult

from .action import required_permissions_for
from .approvals import ApprovalError, ApprovalRecord, verify_approval
from .audit import AuditSink
from .ledger import EnforcementLedger
from .models import (
    FORBIDDEN_COMMAND_FRAGMENTS,
    ActionRequest,
    ApprovalMode,
    AuditError,
    AuditFailurePolicy,
    AuditStage,
    AuthorizationGrant,
    CheckResult,
    CheckStatus,
    LedgerError,
    PolicySummary,
    PreDecision,
    ReasonCode,
    EnforcementError,
    ToolSpec,
    utc_now,
)
from .registry import ToolRegistry

__all__ = [
    "PrecheckOutcome",
    "check_list",
    "issue_grant",
    "pre_execute",
]


@dataclass
class PrecheckOutcome:
    """pre_execute 的返回值：决策 + 生效的检查项（供审计与测试直接断言）。"""

    decision: PreDecision
    checks: list[CheckResult] = field(default_factory=list)
    spec: Optional[ToolSpec] = None
    claim_id: Optional[str] = None

    @property
    def allowed(self) -> bool:
        return self.decision.decision is not Decision.BLOCK


def _check(
    name: str, status: CheckStatus, reason: ReasonCode, detail: str = ""
) -> CheckResult:
    return CheckResult(check=name, status=status, reason_code=reason, detail=detail)


def _first_failure(checks: Sequence[CheckResult]) -> Optional[CheckResult]:
    for item in checks:
        if item.status is CheckStatus.FAILED:
            return item
    return None


def issue_grant(
    request: ActionRequest,
    spec: ToolSpec,
    *,
    ttl_seconds: int,
    now: datetime,
    max_ttl_seconds: Optional[int] = None,
) -> AuthorizationGrant:
    """签发短时效、单次使用、与 action_hash 绑定的授权。"""

    if request.subject is None:
        raise EnforcementError("没有主体就不能签发授权：授权必须能追到人")
    ttl = ttl_seconds
    if request.expires_at is not None:
        remaining = int((request.expires_at - now).total_seconds())
        ttl = max(1, min(ttl, remaining))
    if max_ttl_seconds is not None and ttl > max_ttl_seconds:
        ttl = max_ttl_seconds
    return AuthorizationGrant(
        grant_id="grant-" + uuid.uuid4().hex[:16],
        action_id=request.action_id,
        action_hash=request.action_hash,
        tool_id=request.tool_id,
        tool_schema_hash=request.tool_schema_hash,
        subject=request.subject,
        permissions=request.permissions,
        risk=request.risk,
        issued_at=now,
        expires_at=now + timedelta(seconds=ttl),
        single_use=True,
        nonce=uuid.uuid4().hex,
    )


def check_list(
    request: ActionRequest,
    *,
    registry: ToolRegistry,
    ledger: EnforcementLedger,
    approval: Optional[ApprovalRecord] = None,
    policy_decision: Optional[ValidationResult] = None,
    policy_error: Optional[ReasonCode] = None,
    policy_detail: str = "",
    policy_skipped_reason: str = "",
    now: Optional[datetime] = None,
    sink: Optional[AuditSink] = None,
) -> tuple[list[CheckResult], Optional[ToolSpec], tuple[str, ...]]:
    """跑完全部"执行前"检查（不含审计写入与认领），返回（检查项, 工具, 警告）。"""

    moment = now or utc_now()
    checks: list[CheckResult] = []
    warnings: list[str] = []

    # 1) 工具是否注册、描述是否与已审核哈希一致。
    spec = registry.tool(request.tool_id)
    if spec is None:
        checks.append(
            _check(
                "registry",
                CheckStatus.FAILED,
                ReasonCode.TOOL_NOT_REGISTERED,
                f"工具 {request.tool_id!r} 不在 Tool Registry 里：未注册的工具没有执行语义，"
                "默认阻断；升级 Agent 后必须先登记工具并补契约测试",
            )
        )
        return checks, None, ()
    approval_reason = registry.approval_reason(spec)
    if approval_reason:
        checks.append(
            _check("registry", CheckStatus.FAILED, ReasonCode.SCHEMA_NOT_APPROVED, approval_reason)
        )
        return checks, spec, ()
    checks.append(_check("registry", CheckStatus.PASSED, ReasonCode.ALLOW, f"{spec.id} 已注册且已审核"))

    # 2) 动作自身的时效：过期请求不得执行。
    if request.expires_at is not None and moment >= request.expires_at:
        checks.append(
            _check(
                "action_window",
                CheckStatus.FAILED,
                ReasonCode.ACTION_EXPIRED,
                "动作请求已过期：必须重新构造请求并重走 pre-check",
            )
        )
    else:
        checks.append(_check("action_window", CheckStatus.PASSED, ReasonCode.ALLOW))

    # 3) 主体：受治理动作必须能追到人。
    if request.subject is None:
        checks.append(
            _check(
                "principal",
                CheckStatus.FAILED,
                ReasonCode.PRINCIPAL_REQUIRED,
                "缺少主体（principal）：受治理动作必须显式声明主体，"
                "Adapter 不得从文件名、目录或用户消息推断",
            )
        )
    else:
        unknown_roles = registry.unknown_roles(request.roles)
        detail = f"subject={request.subject} roles={list(request.roles)}"
        if unknown_roles:
            detail += f"；未登记角色的权限视为空：{list(unknown_roles)}"
            warnings.append(f"unknown_roles={list(unknown_roles)}")
        checks.append(_check("principal", CheckStatus.PASSED, ReasonCode.ALLOW, detail))

    # 4) 权限：工具声明的权限 + 参数取值触发的额外权限。
    required = required_permissions_for(spec, request.params)
    granted = set(request.permissions)
    missing = sorted(set(required) - granted)
    if missing:
        checks.append(
            _check(
                "permissions",
                CheckStatus.FAILED,
                ReasonCode.PERMISSION_DENIED,
                f"缺少权限 {missing}（需要 {list(required)}，具备 {sorted(granted)}）",
            )
        )
    else:
        checks.append(
            _check("permissions", CheckStatus.PASSED, ReasonCode.ALLOW, f"required={list(required)}")
        )

    # 4b) 命令白名单：完整匹配，不允许前缀绕过。
    if spec.command_param is not None:
        raw = request.value_of(spec.command_param)
        text = raw.strip() if isinstance(raw, str) else ""
        if not text:
            checks.append(
                _check(
                    "command_allowlist",
                    CheckStatus.FAILED,
                    ReasonCode.PARAM_REQUIRED_MISSING,
                    f"缺少命令参数 {spec.command_param}",
                )
            )
        elif not any(re.fullmatch(pattern, text) is not None for pattern in spec.allowed_commands):
            checks.append(
                _check(
                    "command_allowlist",
                    CheckStatus.FAILED,
                    ReasonCode.COMMAND_NOT_ALLOWLISTED,
                    f"命令不在白名单内（完整匹配）：{text[:200]!r}；"
                    f"允许的模式为 {list(spec.allowed_commands)}",
                )
            )
        else:
            checks.append(
                _check(
                    "command_allowlist",
                    CheckStatus.PASSED,
                    ReasonCode.ALLOW,
                    f"{len(spec.allowed_commands)} 条白名单模式，完整匹配通过",
                )
            )
    else:
        checks.append(
            _check("command_allowlist", CheckStatus.SKIPPED, ReasonCode.ALLOW, "该工具不是命令类")
        )

    # 4c) 组合命令：一条语句之外的东西（分隔 / 管道 / 替换 / 重定向 / 换行）一律结构性阻断。
    #     只靠 allowlist 正则不够：一个 ( .*)? 的尾巴就能吞掉 " ; 任意命令"。
    if spec.command_param is not None:
        raw = request.value_of(spec.command_param)
        command = raw if isinstance(raw, str) else ""
        hits = sorted({fragment for fragment in FORBIDDEN_COMMAND_FRAGMENTS if fragment in command})
        if hits:
            checks.append(
                _check(
                    "command_composition",
                    CheckStatus.FAILED,
                    ReasonCode.COMMAND_COMPOSITION_BLOCKED,
                    f"命令包含组合/替换/重定向片段 {[item for item in hits]}："
                    "本阶段只允许单条语句，组合命令必须先扩白名单并复核（默认阻断）",
                )
            )
        else:
            checks.append(
                _check(
                    "command_composition",
                    CheckStatus.PASSED,
                    ReasonCode.ALLOW,
                    "单条语句，无组合片段",
                )
            )
    else:
        checks.append(
            _check("command_composition", CheckStatus.SKIPPED, ReasonCode.ALLOW, "该工具不是命令类")
        )

    # 5) 审批：高风险动作的人工门禁。
    if spec.approval is ApprovalMode.REQUIRED:
        try:
            verify_approval(
                approval,
                action_hash=request.action_hash,
                action_id=request.action_id,
                tool_id=request.tool_id,
                subject=request.subject,
                approval_roles=registry.approval_role_members(),
                used=False if approval is None else ledger.approval_used(approval.approval_id),
                now=moment,
            )
        except ApprovalError as error:
            code = (
                ReasonCode.APPROVAL_REQUIRED
                if approval is None
                else ReasonCode.APPROVAL_INVALID
            )
            checks.append(_check("approval", CheckStatus.FAILED, code, str(error)))
        else:
            checks.append(
                _check(
                    "approval",
                    CheckStatus.PASSED,
                    ReasonCode.ALLOW,
                    f"approval_id={approval.approval_id} granted_by={approval.granted_by}",
                )
            )
    else:
        checks.append(
            _check("approval", CheckStatus.SKIPPED, ReasonCode.ALLOW, "该工具不需要人工审批")
        )

    # 6) 规则引擎：有文件维度的动作跑规则；没有就显式写成跳过，绝不声称跑过。
    if policy_error is not None:
        checks.append(
            _check(
                "policy",
                CheckStatus.FAILED,
                policy_error,
                policy_detail or "策略判定不可用：高风险动作不执行",
            )
        )
    elif policy_decision is None:
        checks.append(
            _check(
                "policy",
                CheckStatus.SKIPPED,
                ReasonCode.ALLOW,
                policy_skipped_reason or "该动作没有文件维度：Phase 1 规则引擎不适用（显式跳过）",
            )
        )
    elif policy_decision.decision is Decision.BLOCK:
        detail = "; ".join(
            f"{item.canonical_id}: {item.message}" for item in policy_decision.violations
        ) or ("需要人工审批" if policy_decision.requires_approval else "规则判定阻断")
        checks.append(_check("policy", CheckStatus.FAILED, ReasonCode.POLICY_BLOCK, detail))
    else:
        detail = "matched=" + (", ".join(policy_decision.matched_rules) or "<none>")
        if policy_decision.decision is Decision.ALLOW_WITH_WARNINGS:
            warnings.append("policy_allow_with_warnings")
        checks.append(_check("policy", CheckStatus.PASSED, ReasonCode.ALLOW, detail))

    # 7) 限流与熔断：窗口与阈值来自注册表数据。
    limit_key = f"{request.subject}|{request.tool_id}"
    if spec.rate_limit is not None:
        calls = ledger.count_since(
            kind="pre_decision",
            key_field="limit_key",
            key_value=limit_key,
            window_seconds=spec.rate_limit.window_seconds,
            now=moment,
        )
        if calls >= spec.rate_limit.max_calls:
            checks.append(
                _check(
                    "rate_limit",
                    CheckStatus.FAILED,
                    ReasonCode.RATE_LIMITED,
                    f"{spec.rate_limit.window_seconds}s 窗口内已允许 {calls} 次，"
                    f"上限 {spec.rate_limit.max_calls}",
                )
            )
        else:
            checks.append(
                _check(
                    "rate_limit",
                    CheckStatus.PASSED,
                    ReasonCode.ALLOW,
                    f"{calls}/{spec.rate_limit.max_calls} in {spec.rate_limit.window_seconds}s",
                )
            )
        if spec.rate_limit.max_failures:
            failures = ledger.failures_since(
                key_field="limit_key",
                key_value=limit_key,
                window_seconds=spec.rate_limit.breaker_seconds or spec.rate_limit.window_seconds,
                now=moment,
            )
            if failures >= spec.rate_limit.max_failures:
                checks.append(
                    _check(
                        "circuit_breaker",
                        CheckStatus.FAILED,
                        ReasonCode.CIRCUIT_OPEN,
                        f"窗口内失败 {failures} 次，达到熔断阈值 "
                        f"{spec.rate_limit.max_failures}",
                    )
                )
            else:
                checks.append(
                    _check(
                        "circuit_breaker",
                        CheckStatus.PASSED,
                        ReasonCode.ALLOW,
                        f"{failures}/{spec.rate_limit.max_failures}",
                    )
                )
        else:
            checks.append(
                _check("circuit_breaker", CheckStatus.SKIPPED, ReasonCode.ALLOW, "未配置熔断")
            )
    else:
        checks.append(_check("rate_limit", CheckStatus.SKIPPED, ReasonCode.ALLOW, "未配置限流"))
        checks.append(_check("circuit_breaker", CheckStatus.SKIPPED, ReasonCode.ALLOW, "未配置熔断"))

    # 8) 重放 / 复用：台账 + 审计链两处都要看。
    #    只看台账的话，删掉台账文件就能让同一个 action 再执行一次；审计链是追加写的独立证据，
    #    因此两份记录里任何一份说"这个 action 已经发生过"，都必须阻断。
    claims = list(ledger.active_claims(action_id=request.action_id, tool_id=request.tool_id))
    prior_hashes: list[object] = [item.get("action_hash") for item in claims]
    if sink is not None and hasattr(sink, "chain_records"):
        for item in sink.chain_records():  # type: ignore[attr-defined]
            if item.get("action_id") != request.action_id:
                continue
            if item.get("stage") not in ("pre_decision", "final_decision", "execution"):
                continue
            payload = item.get("payload") or {}
            if not isinstance(payload, Mapping):
                continue
            # 只有"真的允许过 / 真的跑过"才占用 action_id：被阻断的尝试没有产生副作用，
            # 修好参数或补齐审批之后必须能重试，否则失败关闭会变成无法恢复的死锁。
            blocked = (
                payload.get("decision") == "block"
                or payload.get("outcome") == "blocked"
                or payload.get("status") == "refused"
            )
            if blocked or payload.get("dry_run"):
                # dry-run 的 allow 不是授权，也不占用 action_id：它不能挡住真正的执行。
                continue
            # 记录里没有 action_hash 时不能拿"当前请求的哈希"顶替：那会把
            # "这个 action_id 发生过"误判成"就是这次这个动作"。
            prior_hashes.append(payload.get("action_hash") or f"<unknown:{item.get('digest')}>")
    prior = [item for item in prior_hashes if item is not None]
    if prior:
        same = any(item == request.action_hash for item in prior)
        checks.append(
            _check(
                "ledger",
                CheckStatus.FAILED,
                ReasonCode.ACTION_REPLAY if same else ReasonCode.ACTION_ID_REUSE,
                "该 action_id 已经判定/执行过（台账或审计链有记录）：重复请求不执行第二次"
                if same
                else "该 action_id 被复用到了不同参数：动作标识不再可信，拒绝执行",
            )
        )
    else:
        checks.append(_check("ledger", CheckStatus.PASSED, ReasonCode.ALLOW, "首次认领"))

    return checks, spec, tuple(warnings)


def pre_execute(
    request: ActionRequest,
    *,
    registry: ToolRegistry,
    ledger: EnforcementLedger,
    sink: Optional[AuditSink] = None,
    approval: Optional[ApprovalRecord] = None,
    policy_decision: Optional[ValidationResult] = None,
    policy_error: Optional[ReasonCode] = None,
    policy_detail: str = "",
    policy_skipped_reason: str = "",
    now: Optional[datetime] = None,
    workspace: Optional[Path | str] = None,
    grant_ttl_seconds: Optional[int] = None,
    dry_run: bool = False,
) -> PrecheckOutcome:
    """完整执行前决策：检查 → 认领 → 授权 → 审计。

    dry_run=True 时只回答"现在执行会被允许吗"：不认领 action_id、不签发可用授权、
    不写限流台账，审计记录上标注 dry_run。CLI 的 precheck 子命令用的就是这个语义——
    否则"先 precheck 再 execute"会因为 action_id 被占用而变成重放。
    """

    moment = now or utc_now()
    checks, spec, warnings = check_list(
        request,
        registry=registry,
        ledger=ledger,
        approval=approval,
        policy_decision=policy_decision,
        policy_error=policy_error,
        policy_detail=policy_detail,
        policy_skipped_reason=policy_skipped_reason,
        now=moment,
        sink=sink,
    )

    failure = _first_failure(checks)
    decision = Decision.BLOCK if failure is not None else (
        Decision.ALLOW_WITH_WARNINGS if warnings else Decision.ALLOW
    )
    reason_code = failure.reason_code if failure is not None else ReasonCode.ALLOW
    if failure is None and decision is Decision.ALLOW_WITH_WARNINGS:
        reason_code = ReasonCode.ALLOW_WITH_WARNINGS

    policy_summary = (
        None if policy_decision is None else PolicySummary.from_validation_result(policy_decision)
    )

    # 台账认领：先占用 action_id，再决定要不要签发授权。
    # 顺序很重要：审计记录里写下的决策必须与最终返回的决策一致，
    # 否则 trace 上会出现"pre 说 allow、实际却阻断"的自相矛盾。
    claim_id: Optional[str] = None
    if spec is not None and decision is not Decision.BLOCK and not dry_run:
        try:
            claim = ledger.claim(
                action_id=request.action_id,
                tool_id=request.tool_id,
                action_hash=request.action_hash,
                claim_id="claim-" + uuid.uuid4().hex[:16],
            )
        except LedgerError as error:
            checks.append(
                _check("ledger_claim", CheckStatus.FAILED, ReasonCode.LEDGER_UNAVAILABLE, str(error))
            )
            decision = Decision.BLOCK
            reason_code = ReasonCode.LEDGER_UNAVAILABLE
        else:
            if not claim.claimed:
                same = claim.reason == "action_replay"
                checks.append(
                    _check(
                        "ledger_claim",
                        CheckStatus.FAILED,
                        ReasonCode.ACTION_REPLAY if same else ReasonCode.ACTION_ID_REUSE,
                        "另一个进程已认领该 action：拒绝并发重复执行"
                        if same
                        else "该 action_id 已被用于不同参数",
                    )
                )
                decision = Decision.BLOCK
                reason_code = ReasonCode.ACTION_REPLAY if same else ReasonCode.ACTION_ID_REUSE
            else:
                claim_id = claim.claim_id
                checks.append(
                    _check("ledger_claim", CheckStatus.PASSED, ReasonCode.ALLOW, claim.claim_id)
                )

    grant: Optional[AuthorizationGrant] = None
    if (
        spec is not None
        and decision is not Decision.BLOCK
        and request.subject is not None
        and not dry_run
    ):
        grant = issue_grant(
            request,
            spec,
            ttl_seconds=grant_ttl_seconds or registry.grant_ttl_seconds,
            now=moment,
            max_ttl_seconds=registry.max_grant_ttl_seconds,
        )

    # 审计：允许之前必须能留下证据。写不进去就按注册表声明的策略处置。
    audit_record = None
    if spec is not None:
        try:
            if sink is None:
                raise AuditError("没有配置审计端口（AuditSink）：不允许在无证据的情况下执行")
            audit_record = sink.append(
                AuditStage.PRE_DECISION,
                payload={
                    "decision": decision.value,
                    "reason_code": reason_code.value,
                    "action_hash": request.action_hash,
                    "params": [
                        {
                            "name": item.name,
                            "type": item.type.value,
                            "chars": item.chars,
                            "digest": item.digest,
                            "secret": item.secret,
                        }
                        for item in request.params
                    ],
                    "param_digest": request.param_digest,
                    "context_digest": request.context_digest,
                    "risk": request.risk.value,
                    "subject": request.subject,
                    "roles": list(request.roles),
                    "permissions": list(request.permissions),
                    "approval_id": None if approval is None else approval.approval_id,
                    "grant_id": None if grant is None else grant.grant_id,
                    "dry_run": dry_run,
                    "checks": [item.model_dump(mode="json") for item in checks],
                    "matched_rules": ()
                    if policy_decision is None
                    else list(policy_decision.matched_rules),
                    "violations": ()
                    if policy_decision is None
                    else [item.canonical_id for item in policy_decision.violations],
                },
                trace_id=request.trace_id,
                action_id=request.action_id,
                request_id=request.request_id,
                tool_id=request.tool_id,
                now=moment,
            )
        except AuditError as error:
            if spec.audit_failure is AuditFailurePolicy.BLOCK:
                checks.append(
                    _check("audit", CheckStatus.FAILED, ReasonCode.AUDIT_UNAVAILABLE, str(error))
                )
                decision = Decision.BLOCK
                reason_code = ReasonCode.AUDIT_UNAVAILABLE
                grant = None
                # 失败关闭但不能留下死锁：这次动作还没执行，把认领释放掉，
                # 审计修好之后同一个 action_id 仍然可以重试。
                if claim_id is not None:
                    try:
                        ledger.release_claim(
                            action_id=request.action_id,
                            tool_id=request.tool_id,
                            claim_id=claim_id,
                            reason=ReasonCode.AUDIT_UNAVAILABLE.value,
                        )
                        checks.append(
                            _check(
                                "ledger_release",
                                CheckStatus.PASSED,
                                ReasonCode.ALLOW,
                                "审计不可写：已释放本次认领，重试不会被当成重放",
                            )
                        )
                        claim_id = None
                    except LedgerError as release_error:
                        checks.append(
                            _check(
                                "ledger_release",
                                CheckStatus.FAILED,
                                ReasonCode.LEDGER_UNAVAILABLE,
                                f"释放认领失败：{release_error}（该 action_id 需要换一个新的）",
                            )
                        )
            else:
                checks.append(
                    _check(
                        "audit",
                        CheckStatus.SKIPPED,
                        ReasonCode.AUDIT_UNAVAILABLE,
                        f"审计不可用，按注册表声明的 degrade 继续：{error}",
                    )
                )
                warnings = (*warnings, "audit_degraded")
                if decision is Decision.ALLOW:
                    decision = Decision.ALLOW_WITH_WARNINGS
                    reason_code = ReasonCode.ALLOW_WITH_WARNINGS
        else:
            checks.append(
                _check(
                    "audit",
                    CheckStatus.PASSED,
                    ReasonCode.ALLOW,
                    f"sequence={audit_record.sequence}",
                )
            )
    else:
        # 未注册工具的阻断也必须留痕：否则 CLI 侧会出现"被拦了但什么都没有"的空档。
        try:
            if sink is not None:
                sink.append(
                    AuditStage.PRE_DECISION,
                    payload={
                        "decision": decision.value,
                        "reason_code": reason_code.value,
                        "action_hash": request.action_hash,
                        "risk": request.risk.value,
                        "subject": request.subject,
                        "checks": [item.model_dump(mode="json") for item in checks],
                        "dry_run": dry_run,
                    },
                    trace_id=request.trace_id,
                    action_id=request.action_id,
                    request_id=request.request_id,
                    tool_id=request.tool_id,
                    now=moment,
                )
        except AuditError:
            # 未注册工具不会被任何执行器接受，这里写不进去不改变结论。
            pass
        checks.append(
            _check(
                "audit",
                CheckStatus.SKIPPED,
                ReasonCode.ALLOW,
                "工具未注册：无执行可能，审计写入为尽力而为",
            )
        )

    if decision is not Decision.BLOCK and grant is not None and not dry_run:
        try:
            ledger.record_grant(grant)
            ledger.append(
                {
                    "kind": "pre_decision",
                    "action_id": request.action_id,
                    "tool_id": request.tool_id,
                    "action_hash": request.action_hash,
                    "decision": decision.value,
                    "risk": request.risk.value,
                    "subject": request.subject,
                    "limit_key": f"{request.subject}|{request.tool_id}",
                    "reason_code": reason_code.value,
                }
            )
        except LedgerError as error:
            checks.append(
                _check("ledger", CheckStatus.FAILED, ReasonCode.LEDGER_UNAVAILABLE, str(error))
            )
            decision = Decision.BLOCK
            reason_code = ReasonCode.LEDGER_UNAVAILABLE
            grant = None

    return PrecheckOutcome(
        decision=PreDecision(
            decision=decision,
            reason_code=reason_code,
            action_id=request.action_id,
            request_id=request.request_id,
            trace_id=request.trace_id,
            action_hash=request.action_hash,
            tool_id=request.tool_id,
            tool_name=request.tool_name,
            risk=request.risk,
            checks=tuple(checks),
            grant=grant,
            required_action=(
                RequiredAction.APPROVAL
                if reason_code in (ReasonCode.APPROVAL_REQUIRED, ReasonCode.APPROVAL_INVALID)
                else None
            ),
            policy=policy_summary,
            evaluated_at=moment,
            expires_at=None if grant is None else grant.expires_at,
            dry_run=dry_run,
        ),
        checks=list(checks),
        spec=spec,
        claim_id=claim_id,
    )
