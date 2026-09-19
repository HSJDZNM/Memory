"""受治理的工具执行端口：节点自己**不做**授权判断。

阶段计划 §工作流边界：`任何节点要调用工具，仍必须走 Policy Platform。Graph Edge 不能替代授权检查。`

因此编排层的节点只负责"提出一次动作"，真正能不能动手由平台回答：

- `PlatformToolRunner`（默认）：把动作交给 Phase 4 的受控执行链
  （注册表 → action_hash → pre-check → 短时效授权 → 执行一次 → 事后验证 → 审计链）。
  它不复制任何判定逻辑，只把结果翻译成编排层的结构化结论；
- `RecordingToolRunner`：测试用的内存实现，只记录、不落盘，用来验证"节点在被拒绝时
  真的没有动手"。

失败关闭：注册表不可用、工具未登记、审计/台账不可写、执行前决策 block——四种情况都不会
让节点"自己决定继续"。需要审批的动作返回 `needs_approval`，由引擎转到人工门禁。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, Sequence, Tuple, runtime_checkable

from enforcement.action import build_action_request
from enforcement.audit import FileAuditSink
from enforcement.executor import ControlledExecutor
from enforcement.ledger import EnforcementLedger
from enforcement.models import (
    CheckStatus,
    Decision,
    ReasonCode,
    ToolSpec,
    digest_of,
)
from enforcement.precheck import pre_execute
from enforcement.registry import load_registry

from .errors import PlatformUnavailableError
from .models import ArtifactKind, ArtifactRef, FailureCode

__all__ = [
    "AGENT_ID",
    "ApprovalBinding",
    "PlatformToolRunner",
    "RecordingToolRunner",
    "ToolOutcome",
    "ToolRequest",
    "ToolRunner",
]

# 编排层在平台里是一个**显式声明的 Agent**：工具表按 agent 分段，主体不靠载荷自称。
AGENT_ID = "orchestrator"


@dataclass(frozen=True)
class ToolRequest:
    """一次受治理的动作请求。`params` 只能包含注册表声明过的参数。"""

    tool_id: str
    action_id: str
    request_id: str
    params: Mapping[str, Any]
    subject: str
    roles: Tuple[str, ...] = ()
    trace_id: Optional[str] = None
    policy: Optional[Any] = None
    approval_path: Optional[Path] = None
    workspace: Optional[Path] = None

    def digest(self) -> str:
        return digest_of(
            {
                "tool_id": self.tool_id,
                "action_id": self.action_id,
                "request_id": self.request_id,
                "params": {key: self.params[key] for key in sorted(self.params)},
                "subject": self.subject,
            }
        )


@dataclass(frozen=True)
class ApprovalBinding:
    """平台口径的绑定：人工审批必须绑**它**，而不是编排层自己的幂等键。

    Phase 4 的 `action_hash` 覆盖工具 schema 哈希、规范化参数、主体、权限与上下文摘要；
    编排层的 `action_id` 只是"这次动作叫什么名字"。把两者混为一谈的后果很具体：
    审批能通过编排层的检查，却在平台的 pre-check 上被判"参数或主体已经变化"。
    """

    action_hash: str
    action_id: str
    tool_id: str
    subject: str


@dataclass(frozen=True)
class ToolOutcome:
    """执行结论。`status` 只有三种，没有"疑似成功"。"""

    status: str
    tool_id: str
    action_id: str
    action_hash: str = ""
    reason_code: str = ""
    final_outcome: Optional[str] = None
    detail: str = ""
    needs_approval: bool = False
    changed: Tuple[ArtifactRef, ...] = ()

    @property
    def executed(self) -> bool:
        return self.status == "executed" and self.final_outcome == "delivered"


@runtime_checkable
class ToolRunner(Protocol):
    def binding(self, request: ToolRequest) -> ApprovalBinding:
        """算出这次动作在**平台口径**下的绑定（人工审批要绑它）。"""
        ...

    def run(self, request: ToolRequest) -> ToolOutcome: ...


class PlatformToolRunner:
    """把动作接到 Phase 4 的受控执行链上（注册表是数据，判定在平台里）。"""

    def __init__(
        self,
        *,
        registry_path: Path | str,
        approved_path: Optional[Path | str],
        audit_path: Path | str,
        ledger_path: Path | str,
        workspace: Path | str,
        agent_version: str = "0.1.0",
        clock=None,
    ) -> None:
        self.workspace = Path(workspace)
        self.audit_path = Path(audit_path)
        self.ledger_path = Path(ledger_path)
        self.agent_version = agent_version
        self._clock = clock
        try:
            loaded = load_registry(registry_path, approved_path=approved_path)
        except Exception as error:  # noqa: BLE001 - 注册表不可用等于没有治理
            raise PlatformUnavailableError(
                f"工具注册表不可用（{type(error).__name__}）：受控工具无法授权",
                code=FailureCode.TOOL_UNAVAILABLE,
            ) from error
        self.registry = loaded.registry
        self.sink = FileAuditSink(self.audit_path, workspace=self.workspace)
        self.ledger = EnforcementLedger(self.ledger_path)

    # ------------------------------------------------------------------ 辅助
    def spec_for(self, tool_id: str) -> ToolSpec:
        spec = self.registry.tool(tool_id)
        if spec is None:
            raise PlatformUnavailableError(
                f"工具 {tool_id!r} 未在注册表中登记：白名单外的一律不可执行",
                code=FailureCode.TOOL_UNAVAILABLE,
            )
        return spec

    def _approval(self, path: Optional[Path]):
        if path is None or not Path(path).is_file():
            return None
        from enforcement.approvals import load_approval

        try:
            return load_approval(path)
        except Exception:  # noqa: BLE001 - 读不出来等于没有审批
            return None

    def _changed(self, spec: ToolSpec, request: ToolRequest) -> Tuple[ArtifactRef, ...]:
        """执行后按目标文件计算 artifact 引用（只留路径与哈希，不留正文）。"""

        raw = request.params.get("file_path")
        if not isinstance(raw, str) or not raw:
            return ()
        candidate = (self.workspace / raw).resolve()
        try:
            candidate.relative_to(self.workspace.resolve())
        except ValueError:
            return ()
        if not candidate.is_file():
            return ()
        payload = candidate.read_bytes()
        return (
            ArtifactRef(
                artifact_id=f"{spec.tool_name}:{raw}",
                kind=ArtifactKind.CHANGE,
                path=raw,
                digest="sha256:" + hashlib.sha256(payload).hexdigest(),
                bytes=len(payload),
            ),
        )

    # ------------------------------------------------------------------ 绑定
    def _action(self, request: ToolRequest, spec: ToolSpec):
        workspace = Path(request.workspace) if request.workspace else self.workspace
        return build_action_request(
            spec,
            dict(request.params),
            action_id=request.action_id,
            request_id=request.request_id,
            agent=AGENT_ID,
            agent_version=self.agent_version,
            trace_id=request.trace_id,
            subject=request.subject,
            roles=request.roles,
            permissions=self.registry.permissions_for(request.roles),
            workspace=workspace,
            ttl_seconds=self.registry.grant_ttl_seconds,
        )

    def binding(self, request: ToolRequest) -> ApprovalBinding:
        """平台口径的 action_hash：人工审批凭它签发，Phase 4 凭它校验。"""

        spec = self.spec_for(request.tool_id)
        try:
            action = self._action(request, spec)
        except Exception as error:  # noqa: BLE001 - 参数不合法就是不可执行
            raise PlatformUnavailableError(
                f"动作请求不合法（{type(error).__name__}）：无法给出可审批的绑定",
                code=FailureCode.TOOL_UNAVAILABLE,
            ) from error
        return ApprovalBinding(
            action_hash=action.action_hash,
            action_id=action.action_id,
            tool_id=action.tool_id,
            subject=str(action.subject or request.subject),
        )

    # ------------------------------------------------------------------ 执行
    def run(self, request: ToolRequest) -> ToolOutcome:
        spec = self.spec_for(request.tool_id)
        workspace = Path(request.workspace) if request.workspace else self.workspace
        try:
            action = self._action(request, spec)
        except Exception as error:  # noqa: BLE001 - 参数不合法就是不合法
            return ToolOutcome(
                status="denied",
                tool_id=request.tool_id,
                action_id=request.action_id,
                reason_code="param_invalid",
                detail=f"动作请求不合法（{type(error).__name__}）",
            )

        # 没有平台决策就不执行：宁可停下，也不"先做了再补票"。
        if request.policy is None:
            return ToolOutcome(
                status="denied",
                tool_id=request.tool_id,
                action_id=request.action_id,
                action_hash=action.action_hash,
                reason_code=ReasonCode.POLICY_BLOCK.value,
                detail="没有平台判定的动作一律不执行",
            )

        try:
            pre = pre_execute(
                action,
                registry=self.registry,
                ledger=self.ledger,
                sink=self.sink,
                approval=self._approval(request.approval_path),
                policy_decision=request.policy,
                now=None if self._clock is None else self._clock(),
                workspace=workspace,
            )
        except Exception as error:  # noqa: BLE001 - 台账/审计不可写即失败关闭
            raise PlatformUnavailableError(
                f"受控执行前置检查不可用（{type(error).__name__}）",
                code=FailureCode.TOOL_UNAVAILABLE,
            ) from error

        decision = pre.decision
        if decision.decision is Decision.BLOCK:
            return ToolOutcome(
                status="denied",
                tool_id=request.tool_id,
                action_id=request.action_id,
                action_hash=action.action_hash,
                reason_code=decision.reason_code.value,
                detail=_first_detail(decision),
                needs_approval=decision.reason_code is ReasonCode.APPROVAL_REQUIRED,
            )

        executor = ControlledExecutor(
            ledger=self.ledger,
            drivers=_drivers(spec),
            sink=self.sink,
            max_grant_ttl_seconds=self.registry.max_grant_ttl_seconds,
        )
        outcome = executor.execute(
            action,
            spec=spec,
            pre=decision,
            workspace=workspace,
            now=None if self._clock is None else self._clock(),
        )
        return ToolOutcome(
            status="executed",
            tool_id=request.tool_id,
            action_id=request.action_id,
            action_hash=action.action_hash,
            reason_code=outcome.record.reason_code.value,
            final_outcome=outcome.final.outcome.value,
            detail="；".join(outcome.notes)[:400],
            changed=self._changed(spec, request),
        )


def _drivers(spec: ToolSpec) -> Mapping[str, Any]:
    """只装配这一个工具需要的驱动：驱动不可用就是不可执行。"""

    from enforcement.drivers import drivers_for

    drivers = drivers_for([spec])
    if spec.id not in drivers:
        raise PlatformUnavailableError(
            f"工具 {spec.id!r} 声明的驱动不可用：拒绝在没有驱动的情况下执行",
            code=FailureCode.TOOL_UNAVAILABLE,
        )
    return drivers


def _first_detail(decision) -> str:
    for check in decision.checks:
        if check.status is CheckStatus.FAILED:
            return f"{check.check}: {check.detail}"[:400]
    return decision.reason_code.value


@dataclass
class RecordingToolRunner:
    """只记录、不落盘：验证"被拒绝时节点没有动手"，以及重试不重复副作用。"""

    outcomes: Sequence[ToolOutcome] = ()
    calls: list[ToolRequest] = field(default_factory=list)
    bindings: list[ToolRequest] = field(default_factory=list)

    def binding(self, request: ToolRequest) -> ApprovalBinding:
        """确定性假绑定：摘要覆盖工具与参数，因此"换参数 → 旧审批作废"照样可测。"""

        self.bindings.append(request)
        return ApprovalBinding(
            action_hash=digest_of(
                {
                    "tool": request.tool_id,
                    "params": dict(request.params),
                    "subject": request.subject,
                }
            ),
            action_id=request.action_id,
            tool_id=request.tool_id,
            subject=request.subject,
        )

    def run(self, request: ToolRequest) -> ToolOutcome:
        self.calls.append(request)
        taken = len(self.calls) - 1
        if taken < len(self.outcomes):
            return self.outcomes[taken]
        return ToolOutcome(
            status="denied",
            tool_id=request.tool_id,
            action_id=request.action_id,
            reason_code="unavailable",
            detail="脚本已用尽：失败关闭，不做隐式执行",
        )


def tool_params(action: Mapping[str, Any]) -> str:
    """把参数渲染成**摘要**文本：需要展示时用它，永远不打印原文。"""

    return json.dumps({key: "<value>" for key in sorted(action)}, ensure_ascii=False)
