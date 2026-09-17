"""Phase 4 命令行入口：注册表审核、pre-check、受控执行、trace 重放与自检。

    python -m enforcement.cli registry --list
    python -m enforcement.cli registry --verify
    python -m enforcement.cli registry --approve --reviewer alice
    python -m enforcement.cli precheck --request examples/enforcement/edit-allow.json
    python -m enforcement.cli execute  --request examples/enforcement/edit-allow.json
    python -m enforcement.cli approve  --request <req.json> --out <approval.json> \
        --granted-by alice --roles reviewer --ttl 300
    python -m enforcement.cli trace    --audit .tmp/artifacts/enforcement-audit.jsonl \
        --action-id sess-1:call-1
    python -m enforcement.cli verify
    python -m enforcement.cli self-check

退出码：

    0 = 允许 / 验证通过（allow、allow_with_warnings、validated、delivered）
    1 = 阻断 / 需要修复（block、repair_required、inconsistent、rolled_back）
    2 = 配置或执行错误（注册表不合规、未审核、请求文件不合法、审计链损坏、CLI 用法错误）
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import threading
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from policy.check import repo_root
from policy.context import build_context
from policy.engine import EngineError, evaluate
from policy.loader import LoaderError, load_rule_set
from policy.models import Decision, PolicyContext, PolicyContextError, RuleSet, ValidationResult

from . import action as action_module
from .approvals import ApprovalRecord, approval_payload
from .audit import FileAuditSink
from .drivers import drivers_for
from .executor import ControlledExecutor, summarise_chain
from .ledger import EnforcementLedger
from .models import (
    ActionRequest,
    AuditStage,
    EnforcementError,
    FinalOutcome,
    ReasonCode,
    ToolSpec,
    utc_now,
)
from .precheck import pre_execute
from .registry import (
    DEFAULT_APPROVED_PATH,
    DEFAULT_REGISTRY_PATH,
    ToolRegistry,
    approve_registry,
    load_registry,
    write_approved,
)
from .trace import explain, load_trace

__all__ = [
    "EXIT_ALLOWED",
    "EXIT_BLOCKED",
    "EXIT_ERROR",
    "build_parser",
    "build_request_document",
    "main",
    "resolve_tool",
]

EXIT_ALLOWED = 0
EXIT_BLOCKED = 1
EXIT_ERROR = 2

DEFAULT_AUDIT = ".tmp/artifacts/enforcement-audit.jsonl"
DEFAULT_LEDGER = ".tmp/artifacts/enforcement-ledger.jsonl"

_REQUEST_FIELDS = (
    "action_id",
    "request_id",
    "trace_id",
    "agent",
    "agent_version",
    "tool_id",
    "tool_name",
    "subject",
    "roles",
    "params",
    "workspace",
    "policy_context",
    "sources",
)


class CliError(Exception):
    """CLI 层的用法或配置错误（退出码 2）。"""


# --------------------------------------------------------------------------- 请求文档


def _load_document(path: Path | str, *, what: str) -> Mapping[str, Any]:
    document_path = Path(path)
    if not document_path.is_file():
        raise CliError(f"{what}文件不存在: {document_path}")
    try:
        # utf-8-sig：Windows 编辑器常带 BOM；容忍它不会改变内容，也不会改变哈希口径。
        document = json.loads(document_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CliError(f"{what}文件不可解析: {document_path}（{error}）") from error
    if not isinstance(document, Mapping):
        raise CliError(f"{what}文件必须是 JSON 对象")
    return document


def resolve_tool(document: Mapping[str, Any], registry: ToolRegistry) -> ToolSpec:
    """解析请求里的工具：优先按稳定 ID，其次按（Agent, 工具名）。"""

    tool_id = document.get("tool_id")
    if isinstance(tool_id, str) and tool_id.strip():
        spec = registry.tool(tool_id.strip())
        if spec is None:
            raise CliError(f"工具 {tool_id!r} 不在注册表里：未注册的工具没有执行语义")
        return spec
    tool_name = document.get("tool_name")
    agent = str(document.get("agent", ""))
    if isinstance(tool_name, str) and tool_name.strip():
        spec = registry.tool_by_name(agent, tool_name.strip())
        if spec is None:
            raise CliError(f"{agent or '<unknown>'} 的工具 {tool_name!r} 不在注册表里")
        return spec
    raise CliError("请求必须声明 tool_id，或同时声明 agent 与 tool_name")


def build_request_document(
    document: Mapping[str, Any],
    *,
    registry: ToolRegistry,
    workspace: Optional[Path | str] = None,
    now: Optional[Any] = None,
    context: Optional[PolicyContext] = None,
) -> ActionRequest:
    """把请求文档变成不可变 Action Request；未声明字段一律报错。"""

    unknown = sorted(set(document) - set(_REQUEST_FIELDS))
    if unknown:
        raise CliError(f"请求出现未知字段 {unknown}；允许的字段为 {sorted(_REQUEST_FIELDS)}")

    spec = resolve_tool(document, registry)
    params = document.get("params", {})
    if not isinstance(params, Mapping):
        raise CliError("params 必须是对象")

    action_id = document.get("action_id")
    request_id = document.get("request_id") or action_id
    if not isinstance(action_id, str) or not action_id.strip():
        raise CliError("请求必须声明 action_id（幂等键）")
    if not isinstance(request_id, str) or not request_id.strip():
        raise CliError("请求必须声明 request_id")

    roles = document.get("roles", [])
    if isinstance(roles, str) or not isinstance(roles, (list, tuple)):
        raise CliError("roles 必须是字符串列表")
    permissions = registry.permissions_for([str(role) for role in roles])

    return action_module.build_action_request(
        spec,
        params,
        action_id=action_id,
        request_id=str(request_id),
        agent=str(document.get("agent", spec.agent)),
        agent_version=document.get("agent_version"),
        trace_id=document.get("trace_id"),
        subject=document.get("subject"),
        roles=[str(role) for role in roles],
        permissions=permissions,
        context=context,
        sources=[str(item) for item in document.get("sources", [])],
        workspace=workspace,
        ttl_seconds=registry.grant_ttl_seconds,
        now=now or utc_now(),
    )


# --------------------------------------------------------------------------- 策略判定


def evaluate_with_budget(
    rules: RuleSet, context: PolicyContext, budget_ms: int
) -> tuple[Optional[ValidationResult], Optional[ReasonCode], str]:
    """在预算内跑规则引擎；超时按失败关闭返回 policy_timeout。"""

    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["result"] = evaluate(rules, context)
        except BaseException as error:  # noqa: BLE001 - 任何异常都要变成结构化结论
            box["error"] = error

    worker = threading.Thread(target=run, name="enforcement-policy", daemon=True)
    worker.start()
    worker.join(budget_ms / 1000)
    if worker.is_alive():
        return None, ReasonCode.POLICY_TIMEOUT, f"策略判定超过内部预算 {budget_ms} ms"
    if "error" in box:
        raise box["error"]
    return box["result"], None, ""


def context_for_document(
    document: Mapping[str, Any], *, workspace: Path
) -> Optional[PolicyContext]:
    """从请求文档里构造显式上下文；没有声明就返回 None（不猜）。"""

    raw_context = document.get("policy_context")
    if raw_context is None:
        return None
    if not isinstance(raw_context, Mapping):
        raise CliError("policy_context 必须是对象")
    try:
        return build_context(dict(raw_context), repo_root=workspace)
    except PolicyContextError as error:
        raise CliError(f"policy_context 不合法：{error}") from error


def policy_decision_for(
    document: Mapping[str, Any],
    spec: ToolSpec,
    *,
    rules_dirs: Sequence[Path],
    workspace: Path,
    repo_root_anchor: Path,
    context: Optional[PolicyContext] = None,
) -> tuple[Optional[ValidationResult], Optional[ReasonCode], str, str]:
    """有 policy_context 就跑规则引擎，没有就显式跳过（绝不声称跑过）。

    两个锚点是分开的：上下文里的路径相对**受控工作区**归一，而规则目录属于**规则库所在的仓库**
    （受控项目常常在另一个目录里，规则库固定在仓库里）。
    """

    if context is None and document.get("policy_context") is None:
        return (
            None,
            None,
            "",
            "请求没有声明 policy_context：该动作没有文件维度，Phase 1 规则引擎不适用（显式跳过）",
        )
    if context is None:
        context = context_for_document(document, workspace=workspace)
    assert context is not None
    rules = load_rule_set(rules_dirs, repo_root=repo_root_anchor)
    decision, error, detail = evaluate_with_budget(rules, context, spec.timeout_ms)
    if error is not None:
        return None, error, detail, ""
    return decision, None, "", ""


# --------------------------------------------------------------------------- 渲染


def _render_decision(payload: Mapping[str, Any]) -> str:
    lines: list[str] = []
    pre = payload.get("pre") or {}
    lines.append(
        f"pre-decision: {pre.get('decision')} ({pre.get('reason_code')}) tool={payload.get('tool_id')}"
    )
    for check in payload.get("checks", []):
        lines.append(
            f"  [{check.get('status'):<7}] {check.get('check'):<18} "
            f"{check.get('reason_code')} {check.get('detail') or ''}".rstrip()
        )
    if payload.get("execution"):
        execution = payload["execution"]
        lines.append(
            f"execution: {execution.get('status')} ({execution.get('reason_code')}) "
            f"exit={execution.get('exit_code')} timed_out={execution.get('timed_out')}"
        )
    if payload.get("post"):
        post = payload["post"]
        lines.append(f"post-check: {post.get('status')} ({post.get('reason_code')})")
        for check in post.get("checks", []):
            lines.append(f"  [{check.get('status'):<7}] {check.get('check'):<18} {check.get('detail') or ''}".rstrip())
    if payload.get("final"):
        final = payload["final"]
        lines.append(f"final: {final.get('outcome')} ({final.get('reason_code')})")
    for note in payload.get("notes", []):
        lines.append(f"note: {note}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- 子命令


def _registry(args: argparse.Namespace) -> int:
    loaded = load_registry(args.registry, approved_path=args.approved)
    registry = loaded.registry

    if args.approve:
        if args.reviewer is None:
            raise CliError("--approve 必须同时给出 --reviewer：审核产物必须能追到人")
        document = approve_registry(registry, reviewer=args.reviewer)
        write_approved(document, args.approved)
        print(
            json.dumps(
                {
                    "approved": args.approved,
                    "registry_digest": document["registry_digest"],
                    "tools": len(document["tools"]),
                    "reviewed_by": document["reviewed_by"],
                    "approved_at": document["approved_at"],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return EXIT_ALLOWED

    if args.show:
        spec = registry.tool(args.show)
        if spec is None:
            raise CliError(f"注册表里没有工具 {args.show!r}")
        payload = {
            "tool": json.loads(spec.model_dump_json()),
            "schema_hash": spec.schema_hash,
            "approved": registry.is_approved(spec),
            "approval_reason": registry.approval_reason(spec),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return EXIT_ALLOWED if registry.is_approved(spec) else EXIT_ERROR

    unapproved = [
        {"tool_id": spec.id, "reason": registry.approval_reason(spec)}
        for spec in registry.tools
        if not registry.is_approved(spec)
    ]
    payload = {
        "registry": registry.path,
        "registry_schema_version": "1.0",
        "version": registry.version,
        "registry_digest": registry.identity,
        "approved_digest": registry.approved_metadata.get("registry_digest"),
        "reviewed_by": registry.approved_metadata.get("reviewed_by"),
        "tools": [
            {
                "id": spec.id,
                "agent": spec.agent,
                "tool_name": spec.tool_name,
                "risk": spec.risk.value,
                "driver": spec.driver.value,
                "approval": spec.approval.value,
                "permissions": list(spec.required_permissions),
                "post_checks": list(spec.post_checks),
                "params": [param.name for param in spec.parameters],
                "schema_hash": spec.schema_hash,
                "approved": registry.is_approved(spec),
            }
            for spec in registry.tools
        ],
        "roles": {role: list(perms) for role, perms in sorted(registry.roles.items())},
        "unapproved": unapproved,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"registry: {registry.path}（version={registry.version}，{len(registry.tools)} 个工具）")
        for item in payload["tools"]:
            mark = "ok " if item["approved"] else "!! "
            print(
                f"  {mark}{item['id']:<14} {item['risk']:<20} driver={item['driver']:<14} "
                f"approval={item['approval']:<9} perms={','.join(item['permissions']) or '-'}"
            )
        if unapproved:
            print("未审核的工具（pre-check 会阻断）：")
            for item in unapproved:
                print(f"  - {item['reason']}")
    return EXIT_ALLOWED if not unapproved else EXIT_ERROR


def resolve_workspace(
    args: argparse.Namespace, document: Mapping[str, Any], repo: Path
) -> Path:
    """受控工作区解析顺序：命令行 → 请求文档 → 仓库根。

    workspace 参与 action_hash，因此 approve 与 execute 必须解析出同一个值，
    否则审批会因为"绑定了另一个工作区"而失效（这是正确行为，但必须让它可预期）。
    """

    if args.workspace:
        return Path(args.workspace).resolve()
    declared = document.get("workspace")
    if isinstance(declared, str) and declared.strip():
        candidate = Path(declared.strip())
        return candidate.resolve() if candidate.is_absolute() else (repo / candidate).resolve()
    return repo


def _prepare(args: argparse.Namespace, repo: Path):
    loaded = load_registry(args.registry, approved_path=args.approved)
    document = _load_document(args.request, what="请求")
    workspace = resolve_workspace(args, document, repo)
    context = context_for_document(document, workspace=workspace)
    request = build_request_document(
        document, registry=loaded.registry, workspace=workspace, context=context
    )
    spec = loaded.registry.tool(request.tool_id)
    assert spec is not None
    if args.rules:
        rules_dirs = tuple(Path(item).resolve() for item in args.rules)
    else:
        rules_dirs = (repo / "policies",)
    decision, error, detail, skipped = policy_decision_for(
        document,
        spec,
        rules_dirs=rules_dirs,
        workspace=workspace,
        repo_root_anchor=repo,
        context=context,
    )
    audit = FileAuditSink(args.audit, workspace=workspace)
    ledger = EnforcementLedger(args.ledger)
    approval = None
    if args.approval:
        from .approvals import load_approval

        approval = load_approval(args.approval)
    return loaded.registry, request, spec, decision, error, detail, skipped, audit, ledger, approval, workspace


def _precheck(args: argparse.Namespace, repo: Path) -> int:
    (
        registry,
        request,
        spec,
        decision,
        error,
        detail,
        skipped,
        audit,
        ledger,
        approval,
        _workspace,
    ) = _prepare(args, repo)
    outcome = pre_execute(
        request,
        registry=registry,
        ledger=ledger,
        sink=audit,
        approval=approval,
        policy_decision=decision,
        policy_error=error,
        policy_detail=detail,
        policy_skipped_reason=skipped,
        dry_run=True,
    )
    pre = outcome.decision
    payload = {
        "action": action_module.redacted_request_payload(request),
        "pre": json.loads(pre.model_dump_json()),
        "checks": [item.model_dump(mode="json") for item in pre.checks],
        "tool_id": request.tool_id,
        "grant": None if pre.grant is None else json.loads(pre.grant.model_dump_json()),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_render_decision({"pre": payload["pre"], "checks": payload["checks"], "tool_id": request.tool_id}))
    return EXIT_ALLOWED if pre.decision is not Decision.BLOCK else EXIT_BLOCKED


def _execute(args: argparse.Namespace, repo: Path) -> int:
    (
        registry,
        request,
        spec,
        decision,
        error,
        detail,
        skipped,
        audit,
        ledger,
        approval,
        workspace,
    ) = _prepare(args, repo)
    pre_outcome = pre_execute(
        request,
        registry=registry,
        ledger=ledger,
        sink=audit,
        approval=approval,
        policy_decision=decision,
        policy_error=error,
        policy_detail=detail,
        policy_skipped_reason=skipped,
    )
    executor = ControlledExecutor(
        ledger=ledger,
        drivers=drivers_for(registry.tools),
        sink=audit,
        max_grant_ttl_seconds=registry.max_grant_ttl_seconds,
    )
    outcome = executor.execute(
        request,
        spec=spec,
        pre=pre_outcome.decision,
        workspace=workspace,
    )
    payload = {
        "action": action_module.redacted_request_payload(request),
        "chain": summarise_chain(outcome),
        "pre": json.loads(outcome.pre.model_dump_json()),
        "checks": [item.model_dump(mode="json") for item in outcome.pre.checks],
        "execution": json.loads(outcome.record.model_dump_json()),
        "evidence": None if outcome.evidence is None else json.loads(outcome.evidence.model_dump_json()),
        "post": None if outcome.post is None else json.loads(outcome.post.model_dump_json()),
        "final": json.loads(outcome.final.model_dump_json()),
        "notes": outcome.notes,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            _render_decision(
                {
                    "pre": payload["pre"],
                    "tool_id": request.tool_id,
                    "checks": payload["checks"],
                    "execution": payload["execution"],
                    "post": payload["post"],
                    "final": payload["final"],
                    "notes": payload["notes"],
                }
            )
        )
    return EXIT_ALLOWED if outcome.final.outcome in (FinalOutcome.DELIVERED,) else EXIT_BLOCKED


def _approve(args: argparse.Namespace, repo: Path) -> int:
    loaded = load_registry(args.registry, approved_path=args.approved)
    document = _load_document(args.request, what="请求")
    # 审批必须绑定与执行完全相同的请求：因此这里和 _prepare 走同一条构造路径
    # （工作区解析顺序、显式上下文、权限解析都不允许有第二套口径）。
    workspace = resolve_workspace(args, document, repo)
    context = context_for_document(document, workspace=workspace)
    request = build_request_document(
        document,
        registry=loaded.registry,
        workspace=workspace,
        context=context,
    )
    now = utc_now()
    record = ApprovalRecord(
        approval_id=args.approval_id or "approval-" + uuid.uuid4().hex[:12],
        action_hash=request.action_hash,
        action_id=request.action_id,
        tool_id=request.tool_id,
        subject=args.subject or request.subject or "",
        granted_by=args.granted_by,
        granted_by_roles=tuple(args.roles),
        granted_at=now,
        expires_at=now + timedelta(seconds=args.ttl),
        note=args.note or "",
    )
    payload = approval_payload(record)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"approval": str(target), **payload}, ensure_ascii=False, indent=2, sort_keys=True))
    return EXIT_ALLOWED


def _trace(args: argparse.Namespace, _repo: Path) -> int:
    report = load_trace(
        args.audit,
        trace_id=args.trace_id,
        action_id=args.action_id,
        request_id=args.request_id,
        require_final=not args.allow_incomplete,
    )
    if args.json:
        print(
            json.dumps(
                {
                    "entries": [
                        {
                            "sequence": entry.sequence,
                            "stage": entry.stage.value,
                            "summary": entry.summary(),
                            "digest": entry.digest,
                            "payload": dict(entry.payload),
                        }
                        for entry in report.entries
                    ],
                    "issues": list(report.issues),
                    "ok": report.ok,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(explain(report))
        for issue in report.issues:
            print(f"issue: {issue}")
    return EXIT_ALLOWED if report.ok else EXIT_ERROR


def _verify(args: argparse.Namespace, repo: Path) -> int:
    sink = FileAuditSink(args.audit, workspace=repo)
    issues = list(sink.verify())
    payload: dict[str, Any] = {
        "audit": str(args.audit),
        **sink.describe(),
        "ok": not issues,
    }
    if getattr(args, "verify_registry", False):
        loaded = load_registry(args.registry, approved_path=args.approved)
        unapproved = [
            spec.id for spec in loaded.registry.tools if not loaded.registry.is_approved(spec)
        ]
        payload["registry"] = loaded.registry.path
        payload["registry_digest"] = loaded.registry.identity
        payload["unapproved_tools"] = unapproved
        if unapproved:
            issues.append(f"未审核的工具：{unapproved}")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"audit: {payload['audit']} 链记录={payload['chained_records']} 外来行={payload['foreign_records']}")
        for issue in issues:
            print(f"issue: {issue}")
        if not issues:
            print("审计链校验通过")
    return EXIT_ALLOWED if not issues else EXIT_ERROR


def _self_check(args: argparse.Namespace, repo: Path) -> int:
    """上线自检：注册表可加载、每个工具都已审核、审计与台账可写、驱动齐备。"""

    problems: list[str] = []
    warnings: list[str] = []
    loaded = load_registry(args.registry, approved_path=args.approved)
    registry = loaded.registry
    for spec in registry.tools:
        reason = registry.approval_reason(spec)
        if reason:
            problems.append(reason)
    drivers = drivers_for(registry.tools)
    for spec in registry.tools:
        if spec.id not in drivers:
            problems.append(f"{spec.id}: 没有平台驱动（{spec.driver.value}）")
        if spec.shell and shutil.which(spec.shell[0]) is None:
            warnings.append(
                f"{spec.id}: 本机找不到 {spec.shell[0]!r}；该工具会被判 execution failed"
                "（process_error），不会静默通过"
            )
    try:
        sink = FileAuditSink(args.audit, workspace=repo)
        sink.append(AuditStage.REQUEST, payload={"self_check": True})
    except EnforcementError as error:
        problems.append(f"审计端口不可写：{error}")
    try:
        EnforcementLedger(args.ledger).append({"kind": "self_check"})
    except EnforcementError as error:
        problems.append(f"台账不可写：{error}")

    payload = {
        "registry": registry.path,
        "registry_digest": registry.identity,
        "tools": len(registry.tools),
        "approved": sum(1 for spec in registry.tools if registry.is_approved(spec)),
        "audit": str(args.audit),
        "ledger": str(args.ledger),
        "problems": problems,
        "warnings": warnings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            f"registry={registry.path} tools={payload['tools']} approved={payload['approved']}"
        )
        for warning in warnings:
            print(f"warning: {warning}")
        for problem in problems:
            print(f"problem: {problem}")
        if not problems:
            print("self-check ok")
    return EXIT_ALLOWED if not problems else EXIT_ERROR


# --------------------------------------------------------------------------- 入口


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m enforcement.cli",
        description="Phase 4 受控执行：Tool Registry、pre-check、受控执行与审计链。",
    )
    # 公共开关放在每个子命令上（子命令自己的默认值不会覆盖先写的全局值）。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH), help="Tool Registry 路径")
    common.add_argument(
        "--approved", default=str(DEFAULT_APPROVED_PATH), help="已审核哈希清单路径"
    )
    common.add_argument("--audit", default=DEFAULT_AUDIT, help="审计 JSONL 路径")
    common.add_argument("--ledger", default=DEFAULT_LEDGER, help="台账 JSONL 路径")
    common.add_argument("--json", action="store_true", help="输出机器可读结果")

    subparsers = parser.add_subparsers(dest="command", required=True)

    registry_parser = subparsers.add_parser(
        "registry", parents=[common], help="查看 / 审核 Tool Registry"
    )
    registry_parser.add_argument("--list", action="store_true", help="列出全部工具（默认行为）")
    registry_parser.add_argument("--show", default=None, help="查看单个工具的审核状态")
    registry_parser.add_argument("--verify", action="store_true", help="校验已审核哈希（默认行为）")
    registry_parser.add_argument("--approve", action="store_true", help="把当前描述登记为已审核")
    registry_parser.add_argument("--reviewer", default=None, help="审核人标识（--approve 必需）")

    for name, help_text in (
        ("precheck", "只做执行前决策，不执行"),
        ("execute", "执行前决策 + 受控执行 + 事后验证"),
    ):
        sub = subparsers.add_parser(name, parents=[common], help=help_text)
        sub.add_argument("--request", required=True, help="请求 JSON 路径")
        sub.add_argument("--approval", default=None, help="审批 JSON 路径（高风险动作必需）")
        sub.add_argument(
            "--rules", action="append", default=None, help="规则目录（可重复；默认 policies/）"
        )
        sub.add_argument("--workspace", default=None, help="受控工作区（默认仓库根目录）")

    approve_parser = subparsers.add_parser(
        "approve", parents=[common], help="为某个请求签发人工审批（人工门禁）"
    )
    approve_parser.add_argument("--request", required=True, help="请求 JSON 路径")
    approve_parser.add_argument("--out", required=True, help="审批 JSON 输出路径")
    approve_parser.add_argument("--granted-by", required=True, help="审批人标识")
    approve_parser.add_argument(
        "--roles", action="append", default=None, help="审批人角色（默认 reviewer）"
    )
    approve_parser.add_argument("--subject", default=None, help="被授权主体（默认请求里的主体）")
    approve_parser.add_argument("--ttl", type=int, default=300, help="审批有效期（秒）")
    approve_parser.add_argument("--approval-id", default=None, help="审批 ID（默认随机）")
    approve_parser.add_argument("--note", default=None, help="备注")
    approve_parser.add_argument("--workspace", default=None, help="受控工作区（默认仓库根目录）")

    trace_parser = subparsers.add_parser(
        "trace", parents=[common], help="按 trace / action / request 重放审计链"
    )
    trace_parser.add_argument("--trace-id", default=None)
    trace_parser.add_argument("--action-id", default=None)
    trace_parser.add_argument("--request-id", default=None)
    trace_parser.add_argument(
        "--allow-incomplete", action="store_true", help="允许没有终态记录的链"
    )

    verify_parser = subparsers.add_parser(
        "verify", parents=[common], help="校验审计链完整性与注册表审核状态"
    )
    verify_parser.add_argument(
        "--check-registry", dest="verify_registry", action="store_true", help="同时校验注册表审核状态"
    )

    subparsers.add_parser(
        "self-check", parents=[common], help="上线自检：注册表 / 审核 / 审计 / 台账 / 驱动"
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass

    args = build_parser().parse_args(argv)
    repo = repo_root()

    try:
        if args.command == "registry":
            return _registry(args)
        if args.command == "precheck":
            return _precheck(args, repo)
        if args.command == "execute":
            return _execute(args, repo)
        if args.command == "approve":
            if not args.roles:
                args.roles = ["reviewer"]
            return _approve(args, repo)
        if args.command == "trace":
            return _trace(args, repo)
        if args.command == "verify":
            return _verify(args, repo)
        if args.command == "self-check":
            return _self_check(args, repo)
    except CliError as error:
        print(f"config error: {error}", file=sys.stderr)
        return EXIT_ERROR
    except (EnforcementError, LoaderError, EngineError, OSError, ValueError) as error:
        print(f"config error: {type(error).__name__}: {error}", file=sys.stderr)
        return EXIT_ERROR

    print(f"config error: 未知子命令 {args.command!r}", file=sys.stderr)
    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
