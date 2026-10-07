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
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from policy.models import Decision, RequiredAction, ValidationResult

from .action import blocked_path_prefix, required_permissions_for
from .approvals import ApprovalBinding, ApprovalError, ApprovalRecord, verify_approval
from .audit import AuditSink
from .codecheck import check_code
from .ledger import ApprovalUseClaim, EnforcementLedger
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
    EnforcementError,
    LedgerError,
    PolicySummary,
    PreDecision,
    ReasonCode,
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


# 理由里的"可用替代"是给模型读的：只列已声明数据的有限前缀。上限存在的理由不是保密，
# 而是理由必须还能一次读完——讲清楚不能变成新的噪音。
_MAX_LISTED_PATTERNS = 8


def _listed(values: Sequence[str], *, max_items: int = _MAX_LISTED_PATTERNS) -> str:
    """把已声明的模式列成可读文本；超出上限时如实写明还有多少条没列出来。"""

    items = list(values)
    if not items:
        return "<无声明>"
    shown = [repr(item) for item in items[:max_items]]
    if len(items) > max_items:
        shown.append(f"另有 {len(items) - max_items} 条未列出")
    return ", ".join(shown)


def _declared_alternatives(
    spec: ToolSpec,
    approval: Optional[ApprovalRecord],
    *,
    include_whitelist: bool = True,
) -> str:
    """把"改成什么形态就能过"写进拒绝理由（M4 的可用性修复）。

    只引用两处**已声明**的数据：注册表的 allowed_commands（命令形态），
    以及随请求交来的、绑定同一工具的已签发审批的 param_patterns（审批覆盖的形态）。
    这里不猜参数、不拼路径、不带凭据，也**不放宽**任何判定：被拒的还是被拒，
    差别只是模型不必再靠试错去找"本会话到底能跑什么"。
    返回空串表示没有已声明的替代可说——此时宁可不写，也不许编一个出来。
    """

    clauses: list[str] = []
    if include_whitelist and spec.allowed_commands:
        clauses.append(
            "注册表白名单允许的命令形态（整串匹配）：" + _listed(list(spec.allowed_commands))
        )
    bound = approval if approval is not None and approval.tool_id == spec.id else None
    if bound is not None and bound.binding is ApprovalBinding.PATTERN:
        clauses.append(
            f"已签发审批 {bound.approval_id}（binding=pattern）覆盖的形态："
            + _listed(
                [f"{name}={pattern}" for name, pattern in sorted(bound.param_patterns.items())]
            )
        )
    elif bound is not None:
        clauses.append(
            f"已签发审批 {bound.approval_id} 是 binding=action 的单次绑定："
            "只对它签发时的那一次 action_hash 有效（参数、schema、主体任一变化即作废）"
        )
    if bound is None and spec.approval is ApprovalMode.REQUIRED:
        clauses.append(
            "本工具在注册表里声明 approval=required，而本次请求没有随附覆盖它的审批："
            "命令形态改对之后仍需人工签发（binding=action 只绑一次调用，"
            "binding=pattern 用 param_patterns 覆盖一类调用）"
        )
    if not clauses:
        return ""
    return "；可用替代：" + "；".join(clauses)


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
    checks.append(
        _check("registry", CheckStatus.PASSED, ReasonCode.ALLOW, f"{spec.id} 已注册且已审核")
    )

    # 本函数只读台账：一次快照供下面所有检查共用。旧实现每问一个问题就重读并重解析
    # 整份台账（追加写、只会变长的文件），单次 pre-check 要读七八遍；
    # 权威的一致性点在 pre_execute 的 claim（那里追加后必须重新读）。
    ledger_records = ledger.records()

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
            _check(
                "permissions",
                CheckStatus.PASSED,
                ReasonCode.ALLOW,
                f"required={list(required)}",
            )
        )

    # 4a) 受保护路径：普通写工具不能触达注册表声明的信任根。
    blocked_path = blocked_path_prefix(spec, request.params)
    if blocked_path is not None:
        parameter, path, prefix = blocked_path
        checks.append(
            _check(
                "path_prefixes",
                CheckStatus.FAILED,
                ReasonCode.PATH_OUT_OF_SCOPE,
                f"参数 {parameter} 的路径 {path!r} 命中受保护前缀 {prefix!r}；"
                "必须改用该信任根的专用受控工具；"
                "本会话可用的读取范围形态是受控项目内的仓库相对路径"
                "（范围等于项目根时记为 .），受保护前缀不在其中",
            )
        )
    elif any(item.blocked_prefixes for item in spec.parameters):
        checks.append(
            _check("path_prefixes", CheckStatus.PASSED, ReasonCode.ALLOW, "未命中受保护路径前缀")
        )
    else:
        checks.append(
            _check(
                "path_prefixes",
                CheckStatus.SKIPPED,
                ReasonCode.ALLOW,
                "该工具未声明禁止路径前缀",
            )
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
                    f"允许的模式为 {list(spec.allowed_commands)}"
                    + _declared_alternatives(spec, approval, include_whitelist=False),
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
                    "本阶段只允许单条语句，组合命令必须先扩白名单并复核（默认阻断）"
                    + _declared_alternatives(spec, approval),
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

    # 4d) 被禁片段：白名单正则描述的是"命令长什么样"，描述不了"这个选项会干什么"。
    #     git diff --output=<任意路径> 完整匹配通过却会写文件，就是这条检查存在的理由；
    #     片段清单是注册表里的数据（forbidden_command_fragments），不是代码里的常数。
    if spec.command_param is not None:
        raw = request.value_of(spec.command_param)
        command = raw if isinstance(raw, str) else ""
        blocked = sorted(
            {fragment for fragment in spec.forbidden_command_fragments if fragment in command}
        )
        if blocked:
            checks.append(
                _check(
                    "command_fragments",
                    CheckStatus.FAILED,
                    ReasonCode.COMMAND_FRAGMENT_BLOCKED,
                    f"命令包含被禁片段 {blocked}（路径穿越 / 会写文件的选项 / 外部 diff）："
                    "白名单只看命令长什么样，这些片段决定它会做什么，一律阻断"
                    + _declared_alternatives(spec, approval),
                )
            )
        else:
            checks.append(
                _check("command_fragments", CheckStatus.PASSED, ReasonCode.ALLOW, "无被禁片段")
            )
    else:
        checks.append(
            _check("command_fragments", CheckStatus.SKIPPED, ReasonCode.ALLOW, "该工具不是命令类")
        )

    # 4e) 委派类进程工具的第二道闸（G9）：结构化代码检查，或显式的"不可治理"声明。
    #     这里刻意不产生"第三种状态"：要么检查跑出结论（通过 / 命中 / 解析失败），
    #     要么把"没有覆盖面"写成显式状态并让它进审计与警告——不允许静默通过。
    if spec.code_check is not None:
        carrier = request.value_of(spec.code_check.param)
        result = check_code(carrier if isinstance(carrier, str) else None, spec.code_check)
        if result.passed:
            checks.append(
                _check("code_check", CheckStatus.PASSED, ReasonCode.ALLOW, result.detail)
            )
            if spec.code_check.known_gaps:
                # 结构性检查不是沙箱：把这条事实带进审计警告，别让"查过了"被读成"隔离了"
                warnings.append("code_check_structural_only")
        else:
            checks.append(
                _check("code_check", CheckStatus.FAILED, result.reason_code, result.detail)
            )
    elif spec.ungoverned is not None:
        checks.append(
            _check(
                "governance_coverage",
                CheckStatus.SKIPPED,
                ReasonCode.UNGOVERNED_DECLARED,
                f"{spec.id} 由 {spec.ungoverned.declared_by} 显式声明为不可治理："
                f"{spec.ungoverned.reason}；该声明写入审计，决策至少是 allow_with_warnings，"
                "不是静默通过",
            )
        )
        warnings.append(f"ungoverned_declared:{spec.id}")

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
                used=False
                if approval is None
                else ledger.approval_used(approval.approval_id, records=ledger_records),
                params=(
                    None
                    if approval is None
                    else {item.name: item.value for item in request.params}
                ),
                uses=0
                if approval is None
                else ledger.approval_use_count(approval.approval_id, records=ledger_records),
                now=moment,
            )
        except ApprovalError as error:
            code = (
                ReasonCode.APPROVAL_REQUIRED
                if approval is None
                else ReasonCode.APPROVAL_INVALID
            )
            checks.append(
                _check(
                    "approval",
                    CheckStatus.FAILED,
                    code,
                    str(error) + _declared_alternatives(spec, approval),
                )
            )
        else:
            detail = (
                f"approval_id={approval.approval_id} granted_by={approval.granted_by} "
                f"binding={approval.binding.value}"
            )
            if approval.binding is ApprovalBinding.PATTERN:
                detail += (
                    f" max_uses={approval.max_uses}"
                    f" used={ledger.approval_use_count(approval.approval_id, records=ledger_records)}"
                    f" patterns={sorted(approval.param_patterns)}"
                )
            checks.append(_check("approval", CheckStatus.PASSED, ReasonCode.ALLOW, detail))
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
            records=ledger_records,
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
                records=ledger_records,
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
        checks.append(
            _check("circuit_breaker", CheckStatus.SKIPPED, ReasonCode.ALLOW, "未配置熔断")
        )

    # 8) 重放 / 复用：台账 + 审计链两处都要看。
    #    只看台账的话，删掉台账文件就能让同一个 action 再执行一次；审计链是追加写的独立证据，
    #    因此两份记录里任何一份说"这个 action 已经发生过"，都必须阻断。
    claims = list(
        ledger.active_claims(
            action_id=request.action_id, tool_id=request.tool_id, records=ledger_records
        )
    )
    prior_hashes: list[object] = [item.get("action_hash") for item in claims]
    chain_error = ""
    if sink is None:
        chain_error = "没有配置审计端口"
    else:
        try:
            chain = list(sink.chain_records())
        except AuditError as error:
            chain_error = str(error)
        except AttributeError as error:
            # 端口没有实现声明里的 chain_records（第三方端口 / 旧实现）：同样按证据缺失处理。
            chain_error = f"审计端口没有实现 chain_records（{error}）"
        else:
            _collect_chain_occupants(
                chain, request=request, prior_hashes=prior_hashes
            )
    if chain_error:
        checks.append(
            _check(
                "audit_replay",
                CheckStatus.SKIPPED,
                ReasonCode.ALLOW,
                f"审计链记录不可读（{chain_error}）：重放判据退化为**只看台账**这一份证据——"
                "这是证据缺失，不是'没有重放'，本条结论只能按单一来源解读",
            )
        )
        warnings.append("replay_evidence_degraded")
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



def _is_corrected_pre_decision(payload: Mapping[str, Any]) -> bool:
    """这条 block 记录是不是"平台撤回了同一次尝试的 allow"的纠正记录。

    只认本模块写下的显式标记（checks 里 pre_decision_correction=passed）。普通的重放
    拦截**不**撤回先前的 allow——否则"先撞一次重放"就能把 action_id 洗白，
    而删台账文件正是审计链要防的那一步。
    """

    checks = payload.get("checks")
    if not isinstance(checks, (list, tuple)):
        return False
    return any(
        isinstance(item, Mapping)
        and item.get("check") == "pre_decision_correction"
        and item.get("status") == CheckStatus.PASSED.value
        for item in checks
    )

def _limit_key_of(
    spec: Optional[ToolSpec], request: ActionRequest, *, dry_run: bool
) -> Optional[str]:
    """本次判定要不要按限流键串行化；不需要就返回 None（不取锁）。

    计数在第 7 项检查里读，而 +1 的那条 pre_decision 直到 pre_execute 末尾才落盘，中间还
    夹着认领、审批占用、授权签发与审计写入：N 个并发请求会同时看到 calls < max_calls，
    然后**全部**放行——注册表里配置的窗口上限形同虚设（熔断计数同源，同样失效）。

    台账自己的原子性原语是"先追加再复核"，但它只覆盖单条记录；这里是"读一个数 + 写一条
    记录"两步，所以用同一个限流键上的跨进程互斥把两步圈在一起。粒度按 (subject|tool)：
    不同键不互相阻塞。不需要限流的工具与 dry-run（不写计数行）都不取锁。
    """

    if spec is None or spec.rate_limit is None or request.subject is None or dry_run:
        return None
    return f"{request.subject}|{request.tool_id}"


def _unavailable_outcome(
    request: ActionRequest,
    *,
    spec: Optional[ToolSpec],
    error: str,
    moment: datetime,
    sink: Optional[AuditSink],
) -> PrecheckOutcome:
    """限流临界区不可用：按失败关闭拒绝，并写清理由。

    **不退化成"读旧计数照样判"**：读不到一致的窗口计数，就证明不了这次调用在预算之内。
    """

    checks = [
        _check(
            "rate_limit_lock",
            CheckStatus.FAILED,
            ReasonCode.LEDGER_UNAVAILABLE,
            f"限流临界区不可用：{error}；"
            "证明不了本次调用在窗口预算内，按失败关闭拒绝（不是放行）",
        )
    ]
    try:
        if sink is not None:
            sink.append(
                AuditStage.PRE_DECISION,
                payload={
                    "decision": Decision.BLOCK.value,
                    "reason_code": ReasonCode.LEDGER_UNAVAILABLE.value,
                    "action_hash": request.action_hash,
                    "risk": request.risk.value,
                    "subject": request.subject,
                    "checks": [item.model_dump(mode="json") for item in checks],
                    "dry_run": False,
                },
                trace_id=request.trace_id,
                action_id=request.action_id,
                request_id=request.request_id,
                tool_id=request.tool_id,
                now=moment,
            )
    except AuditError:
        # 审计写不进去不改变结论：这是一次拒绝，不是放行。
        pass
    return PrecheckOutcome(
        decision=PreDecision(
            decision=Decision.BLOCK,
            reason_code=ReasonCode.LEDGER_UNAVAILABLE,
            action_id=request.action_id,
            request_id=request.request_id,
            trace_id=request.trace_id,
            action_hash=request.action_hash,
            tool_id=request.tool_id,
            tool_name=request.tool_name,
            risk=request.risk,
            checks=tuple(checks),
            grant=None,
            evaluated_at=moment,
        ),
        checks=list(checks),
        spec=spec,
        claim_id=None,
    )


def _collect_chain_occupants(
    chain: Sequence[Mapping[str, Any]],
    *,
    request: ActionRequest,
    prior_hashes: list[object],
) -> None:
    """把审计链里"真的允许过 / 真的跑过"的记录并进重放判据的占用集。

    只有产生过副作用的记录才占用 action_id：被阻断的尝试没有副作用，修好参数或补齐审批
    之后必须能重试，否则失败关闭会变成无法恢复的死锁。唯一的例外是"纠正记录"：它明确撤回
    **同一次尝试**的 allow（台账登记失败时决策从 allow 翻成 block）。
    """

    occupants: list[object] = []
    executed: set[object] = set()
    corrected: set[object] = set()
    for item in chain:
        if item.get("action_id") != request.action_id:
            continue
        if item.get("stage") not in ("pre_decision", "final_decision", "execution"):
            continue
        payload = item.get("payload") or {}
        if not isinstance(payload, Mapping):
            continue
        blocked = (
            payload.get("decision") == "block"
            or payload.get("outcome") == "blocked"
            or payload.get("status") == "refused"
        )
        if blocked or payload.get("dry_run"):
            # dry-run 的 allow 不是授权，也不占用 action_id：它不能挡住真正的执行。
            if blocked and _is_corrected_pre_decision(payload):
                corrected.add(
                    payload.get("action_hash") or f"<unknown:{item.get('digest')}>"
                )
            continue
        # 记录里没有 action_hash 时不能拿"当前请求的哈希"顶替：那会把
        # "这个 action_id 发生过"误判成"就是这次这个动作"。
        marker = payload.get("action_hash") or f"<unknown:{item.get('digest')}>"
        occupants.append(marker)
        if item.get("stage") in ("execution", "final_decision"):
            executed.add(marker)
    # 纠正只对"没有执行痕迹"的尝试生效：一旦有执行 / 终态记录，那条 allow 永远占用。
    prior_hashes.extend(
        marker for marker in occupants if marker not in corrected or marker in executed
    )


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

    spec = registry.tool(request.tool_id)
    moment = now or utc_now()
    limit_key = _limit_key_of(spec, request, dry_run=dry_run)
    # **锁序固定为 rate-lock → audit-lock**（判定里唯一另一把锁是审计追加用的；
    # 台账文件本身不加锁）。任何新增取锁点都必须沿用这条顺序，反向顺序就是死锁配方。
    with ExitStack() as stack:
        if limit_key is not None:
            try:
                stack.enter_context(ledger.limit_lock(limit_key))
            except LedgerError as error:
                return _unavailable_outcome(
                    request, spec=spec, error=str(error), moment=moment, sink=sink
                )
        return _pre_execute_locked(
            request,
            registry=registry,
            ledger=ledger,
            sink=sink,
            approval=approval,
            policy_decision=policy_decision,
            policy_error=policy_error,
            policy_detail=policy_detail,
            policy_skipped_reason=policy_skipped_reason,
            now=moment,
            workspace=workspace,
            grant_ttl_seconds=grant_ttl_seconds,
            dry_run=dry_run,
        )


def _pre_execute_locked(
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
    """执行前决策的实现：调用方 pre_execute 已按限流键把这一段串行化。"""

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
                _check(
                    "ledger_claim",
                    CheckStatus.FAILED,
                    ReasonCode.LEDGER_UNAVAILABLE,
                    str(error),
                )
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

    def release_after_block(label: str, reason: str) -> None:
        """阻断但还没执行：把认领（与已占用的审批额度）还回去。

        失败关闭不能变成死锁：本次动作一个字都没执行，占着 action_id 或额度会让
        修好原因之后的重试被误判成 ACTION_REPLAY / approval_quota_exhausted。
        归还本身失败时如实记一条 FAILED 检查项（不吞掉）：那条路径上只能换一个新的
        action_id，这件事本身就是读得出来的结论。
        """

        nonlocal claim_id, approval_claim
        if claim_id is not None:
            try:
                ledger.release_claim(
                    action_id=request.action_id,
                    tool_id=request.tool_id,
                    claim_id=claim_id,
                    reason=reason,
                )
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
                        "ledger_release",
                        CheckStatus.PASSED,
                        ReasonCode.ALLOW,
                        f"{label}：已释放本次认领，重试不会被当成重放",
                    )
                )
                claim_id = None
        if approval_claim is not None:
            assert approval is not None
            try:
                ledger.release_approval_use(
                    approval_id=approval.approval_id,
                    use_id=approval_claim.use_id,
                    reason=reason,
                )
            except LedgerError as release_error:
                checks.append(
                    _check(
                        "approval_release",
                        CheckStatus.FAILED,
                        ReasonCode.LEDGER_UNAVAILABLE,
                        f"归还审批额度失败：{release_error}",
                    )
                )
            else:
                checks.append(
                    _check(
                        "approval_release",
                        CheckStatus.PASSED,
                        ReasonCode.ALLOW,
                        f"{label}：已归还本次审批额度，重试不会被当成已用尽",
                    )
                )
                approval_claim = None

    # 审批额度：**先原子占用，再执行**。位置在认领之后、签发授权之前——
    # 认领失败的动作不消耗额度；额度用尽的动作也拿不到授权。
    # 每一次占用都进审计（approval_use 检查项 + payload 里的 approval_use）。
    approval_claim: Optional[ApprovalUseClaim] = None
    if (
        spec is not None
        and decision is not Decision.BLOCK
        and not dry_run
        and approval is not None
        and spec.approval is ApprovalMode.REQUIRED
    ):
        try:
            use_claim = ledger.claim_approval_use(
                approval_id=approval.approval_id,
                action_id=request.action_id,
                tool_id=request.tool_id,
                action_hash=request.action_hash,
                max_uses=approval.max_uses,
            )
        except LedgerError as error:
            checks.append(
                _check(
                    "approval_use",
                    CheckStatus.FAILED,
                    ReasonCode.LEDGER_UNAVAILABLE,
                    str(error),
                )
            )
            decision = Decision.BLOCK
            reason_code = ReasonCode.LEDGER_UNAVAILABLE
            # 额度占不上但认领已经拿到：动作不会执行，认领必须还回去。
            release_after_block("台账不可用", ReasonCode.LEDGER_UNAVAILABLE.value)
        else:
            if not use_claim.claimed:
                checks.append(
                    _check(
                        "approval_use",
                        CheckStatus.FAILED,
                        ReasonCode.APPROVAL_INVALID,
                        f"审批次数上限已用尽（{use_claim.uses}/{approval.max_uses}，"
                        f"reason={use_claim.reason}）：必须重新签发审批"
                        if use_claim.reason == "approval_quota_exhausted"
                        else f"审批额度无法占用（reason={use_claim.reason}）：拒绝执行",
                    )
                )
                decision = Decision.BLOCK
                reason_code = ReasonCode.APPROVAL_INVALID
                # 额度用尽同样是"没执行"：认领还回去，重新签发审批后同一个 action_id 可重试。
                # （抢输的那一方自己那一行由 ledger.claim_approval_use 归还，不在这里重复归还。）
                release_after_block("审批额度无法占用", ReasonCode.APPROVAL_INVALID.value)
            else:
                approval_claim = use_claim
                checks.append(
                    _check(
                        "approval_use",
                        CheckStatus.PASSED,
                        ReasonCode.ALLOW,
                        f"第 {use_claim.uses}/{approval.max_uses} 次"
                        f"（binding={approval.binding.value}）：先占用后执行",
                    )
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

    def pre_decision_payload() -> dict[str, Any]:
        """本次判定的审计载荷：decision / reason_code / checks / grant 都取**调用时**的值。

        同一个函数因此能写两种记录：第一次判定，以及台账失败之后对同一次尝试的**纠正
        记录**（决策已被翻成 block，链上不能只留一条 allow）。
        """

        return {
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
            "approval_binding": None if approval is None else approval.binding.value,
            "approval_max_uses": None if approval is None else approval.max_uses,
            "approval_use": None if approval_claim is None else approval_claim.uses,
            "grant_id": None if grant is None else grant.grant_id,
            "dry_run": dry_run,
            "checks": [item.model_dump(mode="json") for item in checks],
            "matched_rules": ()
            if policy_decision is None
            else list(policy_decision.matched_rules),
            "violations": ()
            if policy_decision is None
            else [item.canonical_id for item in policy_decision.violations],
        }

    # 审计：允许之前必须能留下证据。写不进去就按注册表声明的策略处置。
    audit_record = None
    if spec is not None:
        try:
            if sink is None:
                raise AuditError("没有配置审计端口（AuditSink）：不允许在无证据的情况下执行")
            audit_record = sink.append(
                AuditStage.PRE_DECISION,
                payload=pre_decision_payload(),
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
                # 失败关闭但不能留下死锁：这次动作还没执行，认领与额度都还回去，
                # 审计修好之后同一个 action_id 仍然可以重试。
                release_after_block("审计不可写", ReasonCode.AUDIT_UNAVAILABLE.value)
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
            # 授权登记失败 → 阻断，但动作还没执行：认领与已占用的额度一并还回去。
            release_after_block("台账不可写", ReasonCode.LEDGER_UNAVAILABLE.value)
            # 上面那条审计已经落盘为 allow + grant_id：必须补一条**纠正记录**，
            # 否则链上对这次动作的最后一句话与返回的 block 相反，读链的人会以为
            # 它被允许并签发过授权（本模块 1 号性质与 679-681 行注释明令禁止）。
            if audit_record is not None and sink is not None:
                checks.append(
                    _check(
                        "pre_decision_correction",
                        CheckStatus.PASSED,
                        ReasonCode.ALLOW,
                        f"台账不可写：追加纠正记录以撤回 #{audit_record.sequence} 那条 allow，"
                        "使链上的结论与本次返回的 block 一致",
                    )
                )
                try:
                    sink.append(
                        AuditStage.PRE_DECISION,
                        payload=pre_decision_payload(),
                        trace_id=request.trace_id,
                        action_id=request.action_id,
                        request_id=request.request_id,
                        tool_id=request.tool_id,
                        now=moment,
                    )
                except AuditError as correction_error:
                    checks[-1] = _check(
                        "pre_decision_correction",
                        CheckStatus.FAILED,
                        ReasonCode.AUDIT_UNAVAILABLE,
                        f"纠正记录写不进去：{correction_error}；"
                        "链上仍留有一条 allow 记录，读链时必须按本条失败解读",
                    )

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
