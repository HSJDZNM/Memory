"""dsh × Phase 4 受控执行的桥接层。

职责：把 dsh 的 Hook 载荷翻译成 Phase 4 的 Action Request，并负责：

    PreToolUse  → build request → pre_execute → 允许/阻断（并记录执行前基线）
    PostToolUse → 取回基线 → 收集执行后证据 → validate → 写终态

它不导入 dsh 的类型，也不做任何策略判断：判断全部在 enforcement 包里。关键约束：

- 工具必须在 Tool Registry 里登记且描述与已审核哈希一致，否则阻断；
- 参数只取注册表声明过的那些，未声明的参数由 enforcement 的 allowlist 直接拒绝；
- 审批文件可以放**多条记录**（1.2 的审批集），按当前工具选择：run_code 与 exec.pwsh
  各持一份放行、互不挤占。选择不是判定——选中的记录仍由 pre_execute 完整校验；
  只有需要审批的动作才会去读这个文件（坏文件不冻结会话）；
- 执行前基线只写摘要（路径 + 哈希 + 字节数），不把文件内容写进台账；
- 台账里带 secret 参数的请求不参与事后重建（宁可判"证据不足"，也不把密钥落盘）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from enforcement.action import build_action_request, redacted_request_payload
from enforcement.approvals import (
    ApprovalRecord,
    load_approvals,
    select_approval,
)
from enforcement.audit import FileAuditSink
from enforcement.ledger import EnforcementLedger
from enforcement.models import (
    ActionRequest,
    ApprovalMode,
    AuditStage,
    ExecutionRecord,
    ExecutionStatus,
    FileBaseline,
    PostDecision,
    ReasonCode,
    ToolSpec,
    digest_of,
    utc_now,
)
from enforcement.postcheck import baseline_files, collect_evidence, validate
from enforcement.precheck import PrecheckOutcome, pre_execute
from enforcement.registry import ToolRegistry
from policy.models import Decision, ValidationResult

from .adapter import DSH_AGENT_ID, AdapterConfig, DshEventError

__all__ = [
    "EnforcementBridge",
    "EnforcementUnavailable",
    "PostEvent",
    "bridge_from_config",
    "post_event_fields",
]


class EnforcementUnavailable(DshEventError):
    """接线缺失（注册表读不到、台账不可写）：按失败关闭处理。"""


@dataclass(frozen=True)
class PostEvent:
    """PostToolUse 的关键字段：工具、不可信答复的摘要、调用标识与执行事实。

    退出事实（exit_code / timed_out / aborted / signal / result_kind）来自 dsh 规范化
    工具结果的 value（N16）。字段默认 None = "载荷里没有这条事实"，与修前完全一致，
    事后核对因此按失败关闭处理；只有真的拿到退出码，exit_code_zero 才可能判真。
    """

    event_id: str
    tool: str
    response_digest: str
    response_excerpt: str
    session_id: str
    exit_code: Optional[int] = None
    timed_out: Optional[bool] = None
    aborted: Optional[bool] = None
    signal: Optional[str] = None
    result_kind: Optional[str] = None


def _exit_code_fact(raw: Mapping[str, Any], key: str) -> Optional[int]:
    """解析退出码；null 表示"这次执行没有退出码"，其余不合法形状一律拒绝。

    bool 是 int 的子类（True == 1）、负数与小数都不是 dsh 契约里的退出码：把它们当成
    "没有退出码"会让账本上多一条看起来合规、实际什么都没证明的记录，因此显式拒绝。
    """

    if key not in raw or raw[key] is None:
        return None
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DshEventError(
            f"PostToolUse 载荷的 {key} 必须是 >= 0 的整数或 null（dsh 的退出码契约），"
            f"得到 {value!r}：形状不认的退出事实不得被忽略，它决定 exit_code_zero 的结论"
        )
    return value


def _boolean_fact(raw: Mapping[str, Any], key: str) -> Optional[bool]:
    """解析布尔执行事实；null 表示"没有这条事实"，其余形状一律拒绝。"""

    if key not in raw or raw[key] is None:
        return None
    value = raw[key]
    if not isinstance(value, bool):
        raise DshEventError(f"PostToolUse 载荷的 {key} 必须是布尔值或 null，得到 {value!r}")
    return value


def _text_fact(raw: Mapping[str, Any], key: str) -> Optional[str]:
    """解析文本执行事实（信号名 / 结果种类）；空串与 null 都表示"没有这条事实"。"""

    if key not in raw or raw[key] is None:
        return None
    value = raw[key]
    if not isinstance(value, str) or not value.strip():
        raise DshEventError(f"PostToolUse 载荷的 {key} 必须是非空字符串或 null，得到 {value!r}")
    return value.strip()


def post_event_fields(raw: Mapping[str, Any]) -> PostEvent:
    """从 PostToolUse 载荷里取出事后验证需要的字段；其余内容一律丢弃。

    字段口径（只增不改）：

    | 键 | 取值 | 含义 |
    | --- | --- | --- |
    | tool_exit_code | >= 0 的整数 / null | dsh 规范化工具结果里的退出码 |
    | tool_timed_out | bool / null | 命令是否因超时被终止 |
    | tool_aborted | bool / null | 命令是否被取消 |
    | tool_signal | 非空字符串 / null | 终止信号名 |
    | tool_result_kind | 非空字符串 / null | 结果种类（foreground / background） |

    未知键继续显式丢弃：dsh 的载荷本来就有 transcript_path / cwd / hook_event_name /
    tool_input 等本层不用的字段，逐个报错等于把适配器绑死在 dsh 的载荷形状上。
    但**认得出来的键一旦出现就必须是合法取值**——退出码是安全关键字段，
    "形状不认识就当成没有"会让 exit_code_zero 的结论建立在被误解的载荷上。
    """

    session_id = str(raw.get("session_id", "")).strip()
    tool_use_id = str(raw.get("tool_use_id", "")).strip()
    tool = str(raw.get("tool_name", "")).strip()
    if not session_id or not tool_use_id or not tool:
        raise DshEventError("PostToolUse 载荷缺少 session_id / tool_use_id / tool_name")

    response = raw.get("tool_response")
    if isinstance(response, Mapping):
        text = digest_of({str(key): response[key] for key in sorted(response, key=str)})
        excerpt = "structured tool_response"
    elif isinstance(response, str):
        text = digest_of(response)
        excerpt = response[:400]
    elif response is None:
        text = digest_of(None)
        excerpt = ""
    else:
        text = digest_of(str(response))
        excerpt = str(response)[:400]

    return PostEvent(
        event_id=f"{session_id}:{tool_use_id}",
        tool=tool,
        response_digest=text,
        response_excerpt=excerpt,
        session_id=session_id,
        exit_code=_exit_code_fact(raw, "tool_exit_code"),
        timed_out=_boolean_fact(raw, "tool_timed_out"),
        aborted=_boolean_fact(raw, "tool_aborted"),
        signal=_text_fact(raw, "tool_signal"),
        result_kind=_text_fact(raw, "tool_result_kind"),
    )


class EnforcementBridge:
    """把 dsh 事件接到 Phase 4 的 pre / post 链路上。"""

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        sink: FileAuditSink,
        ledger: EnforcementLedger,
        workspace: Path,
        agent_version: str = "unknown",
        approval_file: Optional[Path] = None,
    ) -> None:
        self.registry = registry
        self.sink = sink
        self.ledger = ledger
        self.workspace = Path(workspace)
        self.agent_version = agent_version
        # 人工门禁：审批必须与具体 action_hash 绑定，因此这里只加载、不"申请"。
        # 文件里可以放多条记录（1.2 的审批集），按工具选择——见 approval_for。
        self.approval_file = None if approval_file is None else Path(approval_file)

    def approval_for(self, request: ActionRequest) -> Optional[ApprovalRecord]:
        """选出当前动作该出示的那一张审批条子；这个工具没有条子就返回 None。

        修前这里是"一个审批文件 = 一条记录"，于是名额只能给一个工具：给了 run_code
        （PTC 传输），exec.pwsh 一律 approval_invalid；给了 pwsh，run_code 被拦、
        整个会话冻结。现在按 tool_id 选择，每个工具各持一份放行、互不挤占。

        **这不是判定**：选中的记录随后仍由 pre_execute → verify_approval 完整校验
        （工具 / 主体 / 时效 / 角色 / 参数模式 / 次数），选择不改变任何 allow / block。
        没有本工具的记录时返回 None（调用方据此得到 approval_required：这个工具没有条子），
        绝不用别的工具的记录顶替。

        **读不出来就报错，不吞**：修前 `except ApprovalError: return None` 把
        "审批文件坏了"静默降级成"没有审批"——两者的修复动作完全不同（前者改文件，
        后者签条子）。这个函数只在**该工具需要审批**时才被调用（见 pre），
        因此一个坏文件不会冻结整个会话：不需要审批的动作照常判定。
        """

        if self.approval_file is None or not self.approval_file.is_file():
            return None
        records = load_approvals(self.approval_file)
        return select_approval(
            records,
            tool_id=request.tool_id,
            action_id=request.action_id,
            subject=request.subject,
        )

    # ------------------------------------------------------------------ 解析
    def spec_for(self, tool_name: str) -> Optional[ToolSpec]:
        return self.registry.tool_by_name(DSH_AGENT_ID, tool_name)

    def build_request(
        self,
        *,
        spec: ToolSpec,
        action_id: str,
        request_id: str,
        trace_id: Optional[str],
        subject: Optional[str],
        roles: Sequence[str],
        params: Mapping[str, Any],
    ) -> ActionRequest:
        return build_action_request(
            spec,
            params,
            action_id=action_id,
            request_id=request_id,
            agent=DSH_AGENT_ID,
            agent_version=self.agent_version,
            trace_id=trace_id,
            subject=subject,
            roles=roles,
            permissions=self.registry.permissions_for(roles),
            workspace=self.workspace,
            ttl_seconds=self.registry.grant_ttl_seconds,
        )

    # ------------------------------------------------------------------ 执行前
    def pre(
        self,
        request: ActionRequest,
        *,
        policy_decision: Optional[ValidationResult] = None,
        policy_error: Optional[ReasonCode] = None,
        policy_detail: str = "",
        policy_skipped_reason: str = "",
        dry_run: bool = False,
    ) -> PrecheckOutcome:
        spec = self.registry.tool(request.tool_id)
        # 只在**该工具需要审批**时才碰审批文件：一个坏掉的审批文件必须只拦住需要审批的
        # 动作，而不是把整个会话（连读一个文件）都冻住——那正是本次要修掉的那个失败模式。
        approval = (
            self.approval_for(request)
            if spec is not None and spec.approval is ApprovalMode.REQUIRED
            else None
        )
        outcome = pre_execute(
            request,
            registry=self.registry,
            ledger=self.ledger,
            sink=self.sink,
            approval=approval,
            policy_decision=policy_decision,
            policy_error=policy_error,
            policy_detail=policy_detail,
            policy_skipped_reason=policy_skipped_reason,
            dry_run=dry_run,
        )
        if (
            not dry_run
            and outcome.decision.decision is not Decision.BLOCK
            and spec is not None
        ):
            self._record_state(request, spec)
        return outcome

    def _record_state(self, request: ActionRequest, spec: ToolSpec) -> None:
        """把执行前基线与请求视图写进台账，供 PostToolUse 事后比对。

        请求视图里的 secret 参数只留摘要，因此带 secret 的动作在事后无法重建请求，
        此时 post 阶段会显式判"证据不足"而不是编造结论。
        """

        payload = redacted_request_payload(request)
        # values_withheld 是这一层的元信息，不属于 ActionRequest 的字段：留在 payload 里会让
        # PostToolUse 的重建因为"未知字段"而失败。取出来单独记。
        values_withheld = bool(payload.pop("values_withheld", False))
        # "能不能重建这次请求"由两件事决定：注册表把参数标成 secret，或者取值里出现确定形态的
        # 凭据（后者会被 redacted_request_payload 扣掉取值）。两种情况下都不落盘原文，
        # PostToolUse 阶段因此只能判"证据不足"，而不是拿一份把密钥写进去的副本换结论。
        has_secret = values_withheld or any(item.secret for item in request.params)
        baselines = baseline_files(request, spec, workspace=self.workspace)
        self.ledger.append(
            {
                "kind": "pre_state",
                "action_id": request.action_id,
                "tool_id": request.tool_id,
                "action_hash": request.action_hash,
                "has_secret_params": has_secret,
                "values_withheld": values_withheld,
                "request": payload,
                "baselines": [
                    {
                        "path": item.path,
                        "existed": item.existed,
                        "sha256": item.sha256,
                        "bytes": item.bytes,
                    }
                    for item in baselines
                ],
            }
        )

    def state_for(self, action_id: str) -> Optional[Mapping[str, Any]]:
        records = [
            item for item in self.ledger.of_kind("pre_state") if item.get("action_id") == action_id
        ]
        return None if not records else records[-1]

    def baselines_for(self, action_id: str) -> tuple[FileBaseline, ...]:
        record = self.state_for(action_id)
        if record is None:
            return ()
        captured = utc_now()
        result: list[FileBaseline] = []
        for item in record.get("baselines", []) or []:
            if not isinstance(item, Mapping):
                continue
            result.append(
                FileBaseline(
                    path=str(item.get("path", "")),
                    existed=bool(item.get("existed")),
                    sha256=None if item.get("sha256") is None else str(item["sha256"]),
                    bytes=int(item.get("bytes", 0) or 0),
                    captured_at=captured,
                )
            )
        return tuple(result)

    def _restore_request(self, record: Mapping[str, Any]) -> Optional[ActionRequest]:
        """按台账里的请求视图重建请求；哈希校验由模型完成，重建失败就返回 None。"""

        if record.get("has_secret_params"):
            return None
        payload = record.get("request")
        if not isinstance(payload, Mapping):
            return None
        try:
            return ActionRequest.model_validate(dict(payload))
        except Exception:  # noqa: BLE001 - 重建不出来就别猜
            return None

    # ------------------------------------------------------------------ 执行后
    def post(self, raw: Mapping[str, Any]) -> Optional[PostDecision]:
        """处理 PostToolUse：取回基线 → 收集证据 → 验证 → 写终态。"""

        event = post_event_fields(raw)
        spec = self.spec_for(event.tool)
        if spec is None or not spec.post_checks:
            return None

        state = self.state_for(event.event_id)
        if state is None:
            # 这次调用没有经过 pre-check：它可能是被 pre 拒绝过（dsh 仍会送来 PostToolUse），
            # 也可能是根本没有 pre 阶段（接线缺失 / 旁路）而工具真的执行了。事后既没有授权、
            # 也没有基线，属于**证据不足**：按 AGENTS 第 15 条必须按 repair_required /
            # inconsistent 处理，绝不能返回 None —— hooks 把 None 读成 post_not_required
            # 并放行，一次未经授权、无法核对的执行就会伪装成「不需要事后核对」。
            # 占位记录照写：审计仍能区分「跑过 post 但没有基线」与「事后核对完成」。
            self.sink.append(
                AuditStage.POST_EVIDENCE,
                payload={
                    "stage_note": "post_without_pre",
                    "tool": event.tool,
                    "untrusted_result_digest": event.response_digest,
                    "detail": "找不到对应的 pre-check 记录：无法把这次执行绑定到某个动作",
                },
                action_id=event.event_id,
                tool_id=spec.id,
            )
            raise DshEventError(
                "PostToolUse 找不到对应的 pre-check 记录：既证明不了这次执行被授权过，"
                "也证明不了它被拒绝过——证据不足，不得按放行处理"
            )

        request = self._restore_request(state)
        if request is None:
            self.sink.append(
                AuditStage.POST_EVIDENCE,
                payload={
                    "stage_note": "post_without_request",
                    "tool": event.tool,
                    "detail": "台账里的请求视图不可重建（可能含 secret 参数）：证据不足，按需修复处理",
                },
                action_id=event.event_id,
                tool_id=spec.id,
            )
            # 台账里有一条 pre_state（动作被授权过），但请求视图重建不出来：
            # 拿不到 action_hash 就核对不了这次执行到底做了什么。原文里已经写着
            # 「证据不足，按需修复处理」，那就必须真的按需修复处理，不能返回 None 放行。
            raise DshEventError(
                "台账里的请求视图不可重建（可能含 secret 参数）：证据不足，"
                "按需修复处理，不得按放行处理"
            )

        # N16：执行是**委派**给 Agent 运行时的，退出码只能来自 PostToolUse 载荷里插件转发
        # 的退出事实。修前这里不传 exit_code，而字段默认 None 不会报错——于是注册表声明了
        # post_checks=[exit_code_zero] 的工具在这条路径上永远到不了 validated，命令输出被
        # 策略错误替换。拿不到（None）时的结论与修前一致：事后核对判"没有退出码"→ 需修复。
        record = ExecutionRecord(
            action_id=request.action_id,
            request_id=request.request_id,
            trace_id=request.trace_id,
            action_hash=request.action_hash,
            grant_id=None,
            tool_id=request.tool_id,
            risk=request.risk,
            status=ExecutionStatus.DELEGATED,
            reason_code=ReasonCode.ALLOW,
            driver=spec.driver,
            exit_code=event.exit_code,
            timed_out=bool(event.timed_out),
            duration_ms=0,
            structured_digest=event.response_digest,
            detail="由 Agent 运行时执行（dsh）；证据来自 PostToolUse 与执行前基线",
            started_at=utc_now(),
            finished_at=utc_now(),
        )
        evidence = collect_evidence(
            request,
            spec,
            record,
            workspace=self.workspace,
            baselines=self.baselines_for(event.event_id),
            untrusted_result=event.response_excerpt,
            now=utc_now(),
        )
        decision, evidence = validate(
            request, spec, record, evidence, workspace=self.workspace, now=utc_now()
        )
        self.sink.append(
            AuditStage.POST_EVIDENCE,
            payload={
                "status": decision.status.value,
                "reason_code": decision.reason_code.value,
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
                # 与 post_without_pre 那条记录**同一口径**：这个键回答的是"这次判定面对的是哪一份
                # 不可信答复"，因此写**完整转发答复**的摘要（record.structured_digest，与台账里
                # ExecutionRecord.structured_digest 同值）。此前这里写的是 evidence 里那个
                # **400 字符截断**后的摘要，于是同一份审计里出现两种口径、两条记录对不上，
                # 而且前缀相同的两份长输出会得到同一个摘要。
                "untrusted_result_digest": record.structured_digest,
                # 进程证据与文件证据一样要落盘：exit_code_zero 的结论完全建立在这上面，
                # 只在内存里的退出码等于没有证据（N16 的复现就是靠"审计里看不到退出码"）。
                "process": (
                    None if evidence.process is None else evidence.process.model_dump(mode="json")
                ),
            },
            trace_id=request.trace_id,
            action_id=request.action_id,
            request_id=request.request_id,
            tool_id=request.tool_id,
        )
        self.sink.append(
            AuditStage.FINAL_DECISION,
            payload={
                "outcome": (
                    "delivered" if decision.status.value == "validated" else "repair_required"
                ),
                "reason_code": decision.reason_code.value,
                "action_hash": request.action_hash,
                "pre_decision": "allow",
                "execution_status": record.status.value,
                "post_status": decision.status.value,
                "detail": decision.detail,
            },
            trace_id=request.trace_id,
            action_id=request.action_id,
            request_id=request.request_id,
            tool_id=request.tool_id,
        )
        self.ledger.record_execution(
            action_id=request.action_id,
            tool_id=request.tool_id,
            subject=request.subject,
            action_hash=request.action_hash,
            status=record.status.value,
            ok=decision.status.value == "validated",
            risk=request.risk.value,
        )
        return decision


def bridge_from_config(config: AdapterConfig) -> EnforcementBridge:
    """按 adapter 配置装配桥接层；缺注册表或注册表不可用时抛 EnforcementUnavailable。"""

    if config.registry_path is None:
        raise EnforcementUnavailable(
            "adapter 配置没有声明 registry：Phase 4 的受控工具必须由工具注册表描述，"
            "否则无法判断风险级别、权限与事后验证方式"
        )
    from enforcement.registry import load_registry

    try:
        loaded = load_registry(
            config.registry_path, approved_path=config.registry_approved_path
        )
    except Exception as error:  # noqa: BLE001 - 注册表不可用等于没有治理
        raise EnforcementUnavailable(f"工具注册表不可用：{error}") from error

    ledger_path = (
        config.enforcement_ledger
        if config.enforcement_ledger is not None
        else (config.project_root / ".policy" / "enforcement-ledger.jsonl")
    )
    audit_path = config.audit_log or (config.project_root / ".policy" / "audit.jsonl")
    return EnforcementBridge(
        registry=loaded.registry,
        sink=FileAuditSink(audit_path, workspace=config.project_root),
        ledger=EnforcementLedger(ledger_path),
        workspace=config.project_root,
        agent_version=config.agent_version,
        approval_file=config.approval_file,
    )
