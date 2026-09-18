"""dsh pre-execute Hook：策略判定、受控执行与审计。

数据流（Phase 2 文档第 4 步）：

    dsh tool request → Adapter → Policy Engine → allow: 执行一次
                                              → block: 结构化违规，不执行

dsh 侧的真实契约（0.1.5-rc.1，证据见 src/adapters/dsh/README.md）：

- Hook 是一个**外部命令**：dsh 把事件 JSON 写到它的 stdin，命令按 PowerShell 语法执行；
- **exit 2 表示阻断**，stderr 作为理由显示给模型；其他非 0 退出、启动失败、
  被超时杀掉，对 dsh 都只是"非阻断失败"——**工具照样执行**；
- 因此失败关闭不可能靠 dsh 给：必须由本模块自己保证。这里做三件事：
  1) 内部预算（timeout_ms）严格小于 hooks.json 里的 timeout，超预算自己判 block；
  2) 捕获所有异常并转成 exit 2，绝不让解释器以退出码 1 结束；
  3) hooks.json 读不到等于零 hook 注册，所以运行期用 --self-check 显式验证接线。

本模块不导入 dsh、不读源码文件、不调用 LLM：策略判定完全由核心 policy 包完成。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence

from enforcement.audit import FileAuditSink
from enforcement.ledger import EnforcementLedger
from policy.engine import EngineError, evaluate
from policy.loader import LoaderError, load_rule_set
from policy.models import (
    SCHEMA_VERSION,
    Decision,
    PolicyContextError,
    RuleSet,
    ValidationResult,
)

from .adapter import (
    HOOK_EVENT_POST_TOOL_USE,
    TOOL_TABLE,
    AdapterConfig,
    DshEventError,
    PolicyEvent,
    ToolKind,
    load_config,
    to_policy_context,
    to_policy_event,
)
from .enforcement import EnforcementBridge, EnforcementUnavailable, bridge_from_config

__all__ = [
    "EXIT_ALLOW",
    "EXIT_BLOCK",
    "AUDIT_SCHEMA_VERSION",
    "AuditLedger",
    "ControlledExecutor",
    "DshPreExecuteHook",
    "ExecutionOutcome",
    "HookOutcome",
    "NullExecutor",
    "PolicyTimeout",
    "build_parser",
    "enforcement_feedback",
    "feedback_text",
    "main",
    "run_hook",
    "sanitize",
]

# dsh 协议：0 = 放行；2 = 阻断（stderr 即阻断理由）。没有第三种"警告"出口。
EXIT_ALLOW = 0
EXIT_BLOCK = 2

AUDIT_SCHEMA_VERSION = "1.0"

# 反馈文本长度上限：阻断理由会进入模型上下文，必须足够短且不含敏感内容。
FEEDBACK_MAX_CHARS = 4000

_ABS_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\)[^\s'\"]+")
_SECRET_RE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_\-]{8,}|api[_-]?key\s*[=:]\s*\S+|authorization:\s*\S+|bearer\s+\S+)"
)


class PolicyTimeout(Exception):
    """策略判定超出内部预算：按失败策略阻断，不执行工具。"""


def sanitize(text: str, *, project_root: Optional[Path] = None, limit: int = FEEDBACK_MAX_CHARS) -> str:
    """脱敏：去掉绝对路径与密钥样式，截断到固定长度。

    返回给模型的内容绝不包含内部堆栈、绝对路径、完整规则库或敏感上下文。
    """

    if not isinstance(text, str):
        text = str(text)
    if project_root is not None:
        variants = {str(project_root), str(project_root).replace("\\", "/")}
        for variant in variants:
            if variant:
                text = text.replace(variant, "<repo>")
    text = _ABS_PATH_RE.sub("<abs>", text)
    text = _SECRET_RE.sub("<redacted>", text)
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text


@dataclass(frozen=True)
class ExecutionOutcome:
    """执行器的一次调用结果。

    status 只有三种，刻意保持封闭：executed（确实执行了一次）、
    delegated（本次判定的下游由 Agent 执行，Phase 2 的默认语义）、failed。
    """

    status: str
    detail: str = ""


class ControlledExecutor(Protocol):
    """受控执行器端口：只在 allow 之后被调用，且至多一次。"""

    def execute(self, event: PolicyEvent) -> ExecutionOutcome:
        ...


class NullExecutor:
    """生产环境的执行器：Phase 2 里工具由 dsh 自己在 pre-execute 之后调用。

    Hook 放行（exit 0）就是"允许 dsh 执行一次"；这个类只负责把这个事实记录清楚，
    测试则换成记录调用次数与参数的 fake。
    """

    def execute(self, event: PolicyEvent) -> ExecutionOutcome:
        return ExecutionOutcome(
            status="delegated", detail=f"交由 dsh 执行 {event.tool}（pre-execute 之后）"
        )


@dataclass(frozen=True)
class HookOutcome:
    """一次 Hook 处理的完整结果，可直接序列化进审计。"""

    exit_code: int
    reason_code: str
    stderr: str = ""
    stdout: str = ""
    decision: Optional[ValidationResult] = None
    event: Optional[PolicyEvent] = None
    executed: bool = False
    elapsed_ms: int = 0

    @property
    def blocked(self) -> bool:
        return self.exit_code == EXIT_BLOCK


class AuditLedger:
    """追加写的 JSONL 审计与幂等台账。

    每个 hook 调用都是一个新进程，因此"同一 event_id 不重复执行"必须落在文件上：
    审计记录同时充当幂等台账，键是 event_id，值是上一次判定的载荷摘要与结论。
    只写摘要与结论，不写工具参数原文、不写源码内容。
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _entries(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        entries: list[dict[str, Any]] = []
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # 只有最后一行可能因为进程被杀而截断；其余情况视为审计不可信。
                continue
            if isinstance(record, dict):
                entries.append(record)
        return entries

    def lookup(self, event_id: str) -> Optional[dict[str, Any]]:
        """返回该 event_id 上一次已完成的判定（最后一条），没有就返回 None。"""

        found: Optional[dict[str, Any]] = None
        for record in self._entries():
            if record.get("event_id") == event_id and "exit_code" in record:
                found = record
        return found

    def append(self, record: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(dict(record), ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")


def _evaluate_with_budget(
    evaluator: Callable[[RuleSet, Any], ValidationResult],
    rules: RuleSet,
    context: Any,
    budget_ms: int,
) -> ValidationResult:
    """在预算内完成策略判定。

    用 daemon 线程 + join(timeout) 实现：超时后线程不会阻止解释器退出，
    本函数抛出 PolicyTimeout，调用方按失败策略阻断（工具不执行）。
    预算必须严格小于 hooks.json 的 timeout，否则 dsh 会先杀进程，
    而"被杀死"在 dsh 协议里是放行语义。
    """

    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["result"] = evaluator(rules, context)
        except BaseException as error:  # noqa: BLE001 - 任何异常都必须回到调用方
            box["error"] = error

    worker = threading.Thread(target=run, name="policy-evaluate", daemon=True)
    worker.start()
    worker.join(budget_ms / 1000)
    if worker.is_alive():
        raise PolicyTimeout(f"策略判定超过内部预算 {budget_ms} ms")

    error = box.get("error")
    if error is not None:
        raise error
    return box["result"]


def feedback_text(
    *,
    reason_code: str,
    event: Optional[PolicyEvent],
    decision: Optional[ValidationResult],
    detail: str = "",
) -> str:
    """面向模型的阻断理由：规则 ID、严重级别、原因、证据与期望修复方向。"""

    lines: list[str] = []
    header = "[policy] BLOCKED" + (f" {event.tool}" if event else "")
    if event is not None:
        header += f" {event.file}"
    lines.append(f"{header} ({reason_code})")
    if detail:
        lines.append(f"detail: {detail}")
    if decision is not None:
        for violation in decision.violations:
            lines.append(
                f"rule {violation.canonical_id} severity={violation.severity.value}: "
                f"{violation.message}"
            )
            evidence = violation.evidence
            evidence_line = f"evidence: {evidence.kind}={evidence.value}"
            if evidence.detail:
                evidence_line += f" ({evidence.detail})"
            lines.append(evidence_line)
        if decision.required_action is not None:
            lines.append(f"required_action: {decision.required_action.value}")
        lines.append("expected: controller -> service -> repository（不要在该层直接依赖 repository）")
        if event is not None:
            lines.append(f"request: {event.request_id}")
    lines.append(f"schema: {SCHEMA_VERSION} agent: dsh")
    return "\n".join(lines)


def enforcement_feedback(
    *,
    tool: str,
    file: Optional[str],
    reason_code: str,
    checks: Sequence[Any] = (),
    detail: str = "",
) -> str:
    """把 Phase 4 的检查结论渲染成模型可读的阻断理由（只含结构化字段）。"""

    header = f"[policy] BLOCKED {tool}" + (f" {file}" if file else "")
    lines = [f"{header} ({reason_code})"]
    if detail:
        lines.append(f"detail: {detail}")
    for check in checks:
        if getattr(check, "status", None) is not None and check.status.value == "failed":
            lines.append(f"check {check.check}: {check.reason_code.value} {check.detail}")
    lines.append(f"schema: {SCHEMA_VERSION} agent: dsh enforcement: phase-4")
    return chr(10).join(lines)


@dataclass
class DshPreExecuteHook:
    """pre-execute Hook 的实现：Adapter → Engine → （Phase 4）受控执行门禁 → 执行或阻断。"""

    config: AdapterConfig
    rules: RuleSet
    executor: ControlledExecutor = field(default_factory=NullExecutor)
    evaluator: Callable[[RuleSet, Any], ValidationResult] = evaluate
    clock: Callable[[], float] = time.monotonic
    ledger: Optional[AuditLedger] = None
    capture_dir: Optional[Path] = None
    sequence: int = 0
    bridge: Optional[EnforcementBridge] = None

    def __post_init__(self) -> None:
        """没有显式注入桥接层时，按配置自己装配一次。

        这样"忘了接线"不会静默降级成"没有治理"：装配失败时 self.bridge 仍是 None，
        受控工具会在门禁处被阻断（enforcement_unavailable）。
        """

        if self.bridge is None:
            try:
                self.bridge = bridge_from_config(self.config)
            except EnforcementUnavailable:
                self.bridge = None

    def _audit(
        self,
        record: Mapping[str, Any],
        *,
        outcome: HookOutcome,
    ) -> None:
        if self.ledger is None:
            return
        payload: dict[str, Any] = {
            "audit_schema_version": AUDIT_SCHEMA_VERSION,
            "timestamp": _utc_now(),
            "agent": "dsh",
            "agent_version": self.config.agent_version,
            "reason_code": outcome.reason_code,
            "exit_code": outcome.exit_code,
            "executed": outcome.executed,
            "elapsed_ms": outcome.elapsed_ms,
            "rule_set_hash": self.rules.identity,
        }
        payload.update({key: value for key, value in record.items() if value is not None})
        self.ledger.append(payload)

    def _capture(self, raw_payload: Mapping[str, Any], tool_name: str) -> None:
        """把收到的原始事件原样落盘，用于采集脱敏 fixture。

        文件按工具名 + 调用标识命名：每次 Hook 都是新进程，序号会重复，
        用调用标识才能保证"一次调用一个文件"（采集失败会让 fixture 不可信）。
        """

        if self.capture_dir is None:
            return
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self.sequence += 1
        safe_tool = re.sub(r"[^A-Za-z0-9_.-]", "_", tool_name) or "unknown"
        call_id = str(raw_payload.get("tool_use_id") or f"{self.sequence:03d}")
        safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", call_id) or f"{self.sequence:03d}"
        target = self.capture_dir / f"{safe_tool}-{safe_id}.json"
        target.write_text(
            json.dumps(dict(raw_payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def handle(self, raw_payload: Any) -> HookOutcome:
        """处理一条事件：任何异常路径都返回阻断，绝不抛给解释器。"""

        started = self.clock()
        base_record: dict[str, Any] = {}
        if isinstance(raw_payload, Mapping):
            tool_name = str(raw_payload.get("tool_name", "unknown"))
            self._capture(raw_payload, tool_name)
            base_record = {
                "session_id": raw_payload.get("session_id"),
                "tool": tool_name,
                "cwd_scope": "<repo>" if raw_payload.get("cwd") else None,
            }

        try:
            return self._decide(raw_payload, started=started, base_record=base_record)
        except DshEventError as error:
            return self._fail(
                "context_error", sanitize(str(error), project_root=self.config.project_root),
                started=started, base_record=base_record,
            )
        except PolicyContextError as error:
            return self._fail(
                "context_error", sanitize(str(error), project_root=self.config.project_root),
                started=started, base_record=base_record,
            )
        except PolicyTimeout as error:
            return self._fail(
                "policy_timeout", str(error), started=started, base_record=base_record
            )
        except EngineError as error:
            return self._fail(
                "engine_error", sanitize(str(error), project_root=self.config.project_root),
                started=started, base_record=base_record,
            )
        except (LoaderError, OSError) as error:
            return self._fail(
                "config_error", sanitize(str(error), project_root=self.config.project_root),
                started=started, base_record=base_record,
            )
        except Exception as error:  # noqa: BLE001 - 未知异常也必须失败关闭
            return self._fail(
                "internal_error",
                f"{type(error).__name__}: "
                + sanitize(str(error), project_root=self.config.project_root),
                started=started,
                base_record=base_record,
            )

    def _decide(
        self, raw_payload: Any, *, started: float, base_record: dict[str, Any]
    ) -> HookOutcome:
        admission = to_policy_event(raw_payload, config=self.config)
        spec = None if self.bridge is None else self.bridge.spec_for(
            str(raw_payload.get("tool_name", "")) if isinstance(raw_payload, Mapping) else ""
        )

        if not admission.governed:
            tool_name = str(raw_payload.get("tool_name", "")) if isinstance(raw_payload, Mapping) else ""
            table_spec = TOOL_TABLE.get(tool_name)
            # Phase 4：执行类工具（以及注册表里声明的写类工具）一律走受控链路。
            # 注意"不在注册表里"也必须走这条路：交给门禁去拒绝（tool_not_registered），
            # 而不是因为"注册表不认识它"就退化成放行。
            if table_spec is not None and table_spec.kind is ToolKind.EXECUTE:
                return self._decide_via_enforcement(
                    raw_payload, spec=spec, started=started, base_record=base_record
                )
            if spec is not None and spec.risk.value in ("reversible_write", "destructive_write"):
                return self._decide_via_enforcement(
                    raw_payload, spec=spec, started=started, base_record=base_record
                )
            # 只读或不吃文件的工具：显式降级并记录，不假装检查过（Phase 4 的"允许显式降级"）。
            note = admission.reason
            outcome = HookOutcome(
                exit_code=EXIT_ALLOW,
                reason_code="not_governed",
                event=None,
                elapsed_ms=int((self.clock() - started) * 1000),
            )
            self._audit({**base_record, "governed": False, "scope_note": note}, outcome=outcome)
            return outcome

        event = admission.event
        assert event is not None
        record: dict[str, Any] = {
            **base_record,
            "governed": True,
            "event_id": event.event_id,
            "request_id": event.request_id,
            "trace_id": event.trace_id,
            "tool": event.tool,
            "operation": event.operation.value,
            "file": event.file,
            "layer": event.layer,
            "language": event.language,
            "dependencies": list(event.dependencies),
            "payload_digest": event.payload_digest,
            "payload_fields": list(event.payload_fields),
        }

        if self.ledger is not None:
            previous = self.ledger.lookup(event.event_id)
            if previous is not None:
                same_payload = previous.get("payload_digest") == event.payload_digest
                detail = (
                    "该 event_id 已经判定过：为避免重复执行工具，重放一律阻断"
                    if same_payload
                    else "该 event_id 被复用到了不同参数：事件标识不再可信，拒绝执行"
                )
                return self._fail(
                    "event_replay" if same_payload else "event_id_reuse",
                    detail,
                    started=started,
                    base_record=record,
                )

        context = to_policy_context(event, config=self.config)
        decision = _evaluate_with_budget(
            self.evaluator, self.rules, context, self.config.timeout_ms
        )

        if decision.decision not in (Decision.ALLOW, Decision.ALLOW_WITH_WARNINGS, Decision.BLOCK):
            return self._fail(
                "unknown_decision",
                f"Engine 返回未知 decision {decision.decision!r}；不认识的决策值不得放行",
                started=started,
                base_record=record,
            )

        record["matched_rules"] = list(decision.matched_rules)
        record["skipped_rules"] = [item.rule_id for item in decision.skipped_rules]
        record["decision"] = decision.decision.value
        record["required_action"] = (
            None if decision.required_action is None else decision.required_action.value
        )

        if decision.decision is Decision.BLOCK:
            outcome = HookOutcome(
                exit_code=EXIT_BLOCK,
                reason_code="policy_block",
                stderr=feedback_text(
                    reason_code="policy_block", event=event, decision=decision
                ),
                decision=decision,
                event=event,
                elapsed_ms=int((self.clock() - started) * 1000),
            )
            self._audit(record, outcome=outcome)
            return outcome

        # Phase 4：把"引擎允许"升级成"绑定到具体动作的授权"。
        gate = self._enforcement_gate(
            raw_payload,
            spec=self.bridge.spec_for(event.tool) if self.bridge is not None else None,
            tool=event.tool,
            file=event.file,
            started=started,
            base_record=record,
            policy_decision=decision,
        )
        if gate is not None:
            return gate

        # allow / allow_with_warnings：执行器恰好被调用一次，参数由 Adapter 提供、不再改写。
        execution = self.executor.execute(event)
        executed = execution.status in {"executed", "delegated"}
        warnings = [
            violation.canonical_id
            for violation in decision.violations
        ]
        stderr = ""
        if decision.decision is Decision.ALLOW_WITH_WARNINGS:
            stderr = (
                "[policy] ALLOWED WITH WARNINGS "
                + (f"{event.tool} {event.file}: " if event else "")
                + ", ".join(warnings)
            )
        outcome = HookOutcome(
            exit_code=EXIT_ALLOW,
            reason_code=(
                "allow_with_warnings"
                if decision.decision is Decision.ALLOW_WITH_WARNINGS
                else "allow"
            ),
            stderr=stderr,
            decision=decision,
            event=event,
            executed=executed,
            elapsed_ms=int((self.clock() - started) * 1000),
        )
        record["execution"] = execution.status
        self._audit(record, outcome=outcome)
        return outcome

    # ------------------------------------------------------------------ Phase 4 门禁
    def _enforcement_block(
        self,
        *,
        reason_code: str,
        checks: Sequence[Any],
        detail: str,
        started: float,
        base_record: Mapping[str, Any],
        tool: Optional[str] = None,
        file: Optional[str] = None,
    ) -> HookOutcome:
        """按 Phase 4 的检查结论阻断，并把失败项写进给模型的理由与审计记录。"""

        stderr = sanitize(
            enforcement_feedback(
                tool=tool or "<unknown>",
                file=file,
                reason_code=reason_code,
                checks=checks,
                detail=sanitize(detail, project_root=self.config.project_root),
            ),
            project_root=self.config.project_root,
        )
        outcome = HookOutcome(
            exit_code=EXIT_BLOCK,
            reason_code=reason_code,
            stderr=stderr,
            elapsed_ms=int((self.clock() - started) * 1000),
        )
        self._audit(
            {**base_record, "enforcement_reason": reason_code, "enforcement_detail": detail},
            outcome=outcome,
        )
        return outcome

    def _enforcement_gate(
        self,
        raw_payload: Any,
        *,
        spec: Optional[Any],
        tool: str,
        file: Optional[str],
        started: float,
        base_record: Mapping[str, Any],
        policy_decision: Optional[ValidationResult] = None,
        policy_skipped: str = "",
    ) -> Optional[HookOutcome]:
        """Phase 4 的执行前授权。返回 None 表示放行；返回 HookOutcome 表示已阻断。"""

        if self.bridge is None:
            return self._enforcement_block(
                reason_code="enforcement_unavailable",
                checks=(),
                detail=(
                    "adapter 配置没有接入 Phase 4 工具注册表（registry / registry_approved）："
                    "受控工具不得在无授权链路下执行"
                ),
                started=started,
                base_record=base_record,
                tool=tool,
                file=file,
            )
        if spec is None:
            return self._enforcement_block(
                reason_code="tool_not_registered",
                checks=(),
                detail=(
                    f"工具 {tool!r} 不在 Tool Registry 里：未登记的工具没有执行语义，默认阻断；"
                    "升级 Agent 后必须先登记工具并重新审核注册表"
                ),
                started=started,
                base_record=base_record,
                tool=tool,
                file=file,
            )

        tool_input = raw_payload.get("tool_input") if isinstance(raw_payload, Mapping) else {}
        if not isinstance(tool_input, Mapping):
            tool_input = {}
        session_id = str(raw_payload.get("session_id") or "")
        tool_use_id = str(raw_payload.get("tool_use_id") or "")
        # 与 Phase 2 的 event_id 同口径：PostToolUse 只能靠这个标识把事后证据接回同一个动作。
        action_id = (
            f"{session_id}:{tool_use_id}"
            if session_id and tool_use_id
            else (tool_use_id or session_id or "unknown")
        )
        try:
            request = self.bridge.build_request(
                spec=spec,
                action_id=action_id,
                request_id=action_id,
                trace_id=self.config.trace_id,
                subject=None if self.config.principal is None else self.config.principal.subject,
                roles=() if self.config.principal is None else tuple(self.config.principal.roles),
                params=dict(tool_input),
            )
        except Exception as error:  # noqa: BLE001 - 参数不合法一律阻断
            return self._enforcement_block(
                reason_code="enforcement_param_error",
                checks=(),
                detail=str(error),
                started=started,
                base_record=base_record,
                tool=tool,
                file=file,
            )

        try:
            outcome = self.bridge.pre(
                request,
                policy_decision=policy_decision,
                policy_skipped_reason=policy_skipped,
            )
        except Exception as error:  # noqa: BLE001 - 受控链路不可用一律阻断
            return self._enforcement_block(
                reason_code="enforcement_error",
                checks=(),
                detail=f"{type(error).__name__}: {error}",
                started=started,
                base_record=base_record,
                tool=tool,
                file=file,
            )

        if outcome.decision.decision is Decision.BLOCK:
            return self._enforcement_block(
                reason_code=outcome.decision.reason_code.value,
                checks=outcome.decision.checks,
                detail="Phase 4 pre-check 未通过：动作没有执行",
                started=started,
                base_record={
                    **base_record,
                    "action_hash": request.action_hash,
                    "action_id": request.action_id,
                    "tool_id": request.tool_id,
                    "risk": request.risk.value,
                },
                tool=tool,
                file=file,
            )
        # 允许：把授权凭据记进审计（工具本身由 dsh 在 pre-execute 之后执行）。
        if outcome.decision.grant is not None and self.ledger is not None:
            self._audit(
                {
                    **base_record,
                    "action_hash": request.action_hash,
                    "action_id": request.action_id,
                    "tool_id": request.tool_id,
                    "risk": request.risk.value,
                    "grant_id": outcome.decision.grant.grant_id,
                    "grant_expires_at": outcome.decision.grant.expires_at.isoformat(),
                },
                outcome=HookOutcome(
                    exit_code=EXIT_ALLOW,
                    reason_code="enforcement_allow",
                    elapsed_ms=int((self.clock() - started) * 1000),
                ),
            )
        return None

    def _decide_via_enforcement(
        self, raw_payload: Any, *, spec: Optional[Any], started: float, base_record: dict[str, Any]
    ) -> HookOutcome:
        """Phase 4 的高权限执行路径：授权通过后由 Agent 运行时执行。"""

        tool = str(raw_payload.get("tool_name", "unknown")) if isinstance(raw_payload, Mapping) else "unknown"
        gate = self._enforcement_gate(
            raw_payload,
            spec=spec,
            tool=tool,
            file=None,
            started=started,
            base_record=base_record,
            policy_skipped=(
                "该动作没有文件维度：Phase 1 规则引擎不适用；"
                "授权由 Tool Registry（权限 / 参数白名单 / 命令白名单 / 审批）决定"
            ),
        )
        if gate is not None:
            return gate

        outcome = HookOutcome(
            exit_code=EXIT_ALLOW,
            reason_code="allow_delegated",
            event=None,
            executed=False,
            elapsed_ms=int((self.clock() - started) * 1000),
        )
        self._audit(
            {
                **base_record,
                "governed": True,
                "scope_note": "Phase 4 受控执行：高权限动作放行，由 Agent 运行时执行",
            },
            outcome=outcome,
        )
        return outcome

    def _fail(
        self,
        reason_code: str,
        detail: str,
        *,
        started: float,
        base_record: Mapping[str, Any],
    ) -> HookOutcome:
        """失败关闭：任何无法安全判定的情况都阻断，并给出可诊断但不含敏感信息的原因。"""

        event = None
        outcome = HookOutcome(
            exit_code=EXIT_BLOCK,
            reason_code=reason_code,
            stderr=feedback_text(
                reason_code=reason_code, event=event, decision=None, detail=detail
            ),
            elapsed_ms=int((self.clock() - started) * 1000),
        )
        self._audit({**base_record, "detail": detail}, outcome=outcome)
        return outcome


def _utc_now() -> str:
    import datetime as clock

    return clock.datetime.now(clock.timezone.utc).isoformat().replace("+00:00", "Z")


def post_execute_outcome(
    raw_payload: Mapping[str, Any],
    *,
    bridge: Optional[EnforcementBridge],
    config: AdapterConfig,
    hook: "DshPreExecuteHook",
    started: float,
) -> HookOutcome:
    """PostToolUse：事后验证。失败时用 exit 2 表示"这次执行的结果不可信"。

    PostToolUse 阶段副作用已经发生，dsh 只能把工具结果标成错误——所以这里的语义是
    "结果需要修复"，绝不是"回滚成功"。
    """

    if bridge is None:
        return HookOutcome(
            exit_code=EXIT_ALLOW,
            reason_code="post_not_governed",
            elapsed_ms=int((hook.clock() - started) * 1000),
        )
    try:
        decision = bridge.post(raw_payload)
    except Exception as error:  # noqa: BLE001 - 事后验证失败不得谎报通过
        return HookOutcome(
            exit_code=EXIT_BLOCK,
            reason_code="post_error",
            stderr=sanitize(
                f"[policy] POST-CHECK FAILED detail: {type(error).__name__}: {error}",
                project_root=config.project_root,
            ),
            elapsed_ms=int((hook.clock() - started) * 1000),
        )

    if decision is None:
        return HookOutcome(
            exit_code=EXIT_ALLOW,
            reason_code="post_not_required",
            elapsed_ms=int((hook.clock() - started) * 1000),
        )
    if decision.status.value == "validated":
        return HookOutcome(
            exit_code=EXIT_ALLOW,
            reason_code="post_validated",
            elapsed_ms=int((hook.clock() - started) * 1000),
        )
    detail = "; ".join(
        f"{item.check}: {item.detail}" for item in decision.checks if item.status.value == "failed"
    )
    return HookOutcome(
        exit_code=EXIT_BLOCK,
        reason_code=f"post_{decision.status.value}",
        stderr=sanitize(
            chr(10).join(
                [
                    f"[policy] POST-CHECK {decision.status.value} ({decision.reason_code.value})",
                    *( [f"detail: {detail}"] if detail else [] ),
                    "该动作已经执行，副作用无法撤销：按 repair_required 处理，需要人工或后续修复流程介入",
                ]
            ),
            project_root=config.project_root,
        ),
        elapsed_ms=int((hook.clock() - started) * 1000),
    )


def run_hook(
    raw_payload: Any,
    *,
    config_path: Path | str,
    executor: Optional[ControlledExecutor] = None,
    evaluator: Optional[Callable[[RuleSet, Any], ValidationResult]] = None,
    audit_path: Optional[Path | str] = None,
    capture_dir: Optional[Path | str] = None,
    hooks_config_path: Optional[Path | str] = None,
    bridge: Optional[EnforcementBridge] = None,
) -> HookOutcome:
    """装配并执行一次 Hook 调用（测试与 CLI 共用的入口）。

    PreToolUse 走执行前授权；PostToolUse 走事后验证；两者共用同一份台账与审计链，
    因此一次工具调用在审计里是一条完整的 trace。
    """

    config = load_config(config_path)
    rules = load_rule_set(config.rule_dirs, repo_root=config.rule_anchor)

    ledger_path = audit_path if audit_path is not None else config.audit_log
    ledger = None if ledger_path is None else AuditLedger(ledger_path)

    if bridge is None:
        try:
            bridge = bridge_from_config(config)
        except EnforcementUnavailable:
            bridge = None

    if bridge is not None and audit_path is not None:
        # --audit 是"本次会话的审计文件"：Phase 2 的记录与 Phase 4 的链落在同一份证据里。
        # 幂等/授权状态使用独立台账；两种 JSONL 协议不能混写，否则严格读取无法区分
        # "合法的外来审计行"与"丢失 schema 的损坏台账行"。
        audit_file = Path(audit_path)
        state_file = audit_file.with_name(
            f"{audit_file.stem}.enforcement-ledger{audit_file.suffix}"
        )
        bridge.sink = FileAuditSink(audit_file, workspace=config.project_root)
        bridge.ledger = EnforcementLedger(state_file)

    kwargs: dict[str, Any] = {
        "config": config,
        "rules": rules,
        "ledger": ledger,
        "capture_dir": None if capture_dir is None else Path(capture_dir),
        "bridge": bridge,
    }
    if executor is not None:
        kwargs["executor"] = executor
    if evaluator is not None:
        kwargs["evaluator"] = evaluator

    hook = DshPreExecuteHook(**kwargs)
    report = check_wiring(config, hooks_config_path=hooks_config_path)
    if report:
        outcome = hook._fail(  # noqa: SLF001 - 接线错误必须走同一条失败关闭路径
            "wiring_error", report, started=hook.clock(), base_record={}
        )
        return outcome

    if isinstance(raw_payload, Mapping) and raw_payload.get("hook_event_name") == HOOK_EVENT_POST_TOOL_USE:
        return post_execute_outcome(
            raw_payload, bridge=bridge, config=config, hook=hook, started=hook.clock()
        )
    return hook.handle(raw_payload)


def check_wiring(
    config: AdapterConfig, *, hooks_config_path: Optional[Path | str] = None
) -> str:
    """接线自检：把"配置没接上 = 静默放行"这一类失效变成显式错误。

    dsh 在 hooks.json 读不到时不注册任何 hook，也不会报错；因此运行期必须自己确认
    hooks.json 存在、指向的 adapter 配置就是本次使用的那份，且内部预算小于 dsh 超时。
    """

    if hooks_config_path is None:
        return ""
    path = Path(hooks_config_path)
    if not path.is_file():
        return f"hooks.json 不存在：{path.name}；dsh 会因此不注册任何 hook（等于没有治理）"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return f"hooks.json 不可解析（{type(error).__name__}）；dsh 会因此不注册任何 hook"

    commands: list[str] = []
    hooks_section = document.get("hooks") if isinstance(document, Mapping) else None
    if isinstance(hooks_section, Mapping):
        for groups in hooks_section.values():
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, Mapping):
                    continue
                for entry in group.get("hooks", []):
                    if isinstance(entry, Mapping) and isinstance(entry.get("command"), str):
                        commands.append(entry["command"])
    if not any("adapters.dsh.hooks" in command for command in commands):
        return "hooks.json 里没有指向 adapters.dsh.hooks 的命令；当前组合没有接入策略 Hook"

    timeout_sec = None
    for groups in (hooks_section or {}).values() if isinstance(hooks_section, Mapping) else []:
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, Mapping):
                continue
            for entry in group.get("hooks", []):
                if isinstance(entry, Mapping) and isinstance(entry.get("command"), str):
                    if "adapters.dsh.hooks" in entry["command"] and isinstance(
                        entry.get("timeout"), (int, float)
                    ):
                        timeout_sec = float(entry["timeout"])
    if timeout_sec is not None and timeout_sec * 1000 <= config.timeout_ms:
        return (
            f"hooks.json 的 timeout={timeout_sec:g}s 不大于内部预算 {config.timeout_ms}ms："
            "dsh 会先杀掉 Hook，而被杀在 dsh 协议里等同于放行，必须让内部预算先触发"
        )
    return ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m adapters.dsh.hooks",
        description="dsh pre-execute Hook：读 stdin 的事件 JSON，放行（exit 0）或阻断（exit 2）。",
    )
    parser.add_argument("--config", required=True, help="adapter 配置（YAML）路径")
    parser.add_argument("--audit", default=None, help="审计 JSONL 路径（覆盖配置里的 audit_log）")
    parser.add_argument(
        "--hooks-config",
        default=None,
        help="hooks.json 路径：提供时做接线自检（存在性、命令、超时预算）",
    )
    parser.add_argument(
        "--capture",
        default=None,
        help="把收到的原始事件写到该目录（用于采集脱敏 fixture；不影响判定）",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="只做配置与接线自检，不读 stdin；成功退出码 0，失败 2",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Hook 的进程入口。

    契约：stdout 在放行时保持为空（dsh 只在 exit 0 且 stdout 以 { 开头时才解析 JSON，
    提前写入文本会被误当成结构化输出）；所有诊断写 stderr。
    """

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):  # 已经被重定向且不可重配置
                pass

    args = build_parser().parse_args(argv)

    try:
        if args.self_check:
            config = load_config(args.config)
            load_rule_set(config.rule_dirs, repo_root=config.rule_anchor)
            report = check_wiring(config, hooks_config_path=args.hooks_config)
            if report:
                print(f"[policy] wiring error: {report}", file=sys.stderr)
                return EXIT_BLOCK
            print("[policy] self-check ok", file=sys.stderr)
            return EXIT_ALLOW

        payload = json.loads(sys.stdin.read() or "null")
    except (DshEventError, LoaderError, OSError, ValueError) as error:
        print(f"[policy] BLOCKED (startup_error) detail: {error}", file=sys.stderr)
        return EXIT_BLOCK

    try:
        outcome = run_hook(
            payload,
            config_path=args.config,
            audit_path=args.audit,
            capture_dir=args.capture,
            hooks_config_path=args.hooks_config,
        )
    except Exception as error:  # noqa: BLE001 - 最后一道失败关闭：绝不能以退出码 1 结束
        print(
            f"[policy] BLOCKED (startup_error) detail: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return EXIT_BLOCK

    if outcome.stderr:
        print(outcome.stderr, file=sys.stderr)
    if outcome.exit_code == EXIT_ALLOW:
        return EXIT_ALLOW
    if not outcome.stderr:
        print(f"[policy] BLOCKED ({outcome.reason_code})", file=sys.stderr)
    return EXIT_BLOCK


if __name__ == "__main__":
    raise SystemExit(main())
