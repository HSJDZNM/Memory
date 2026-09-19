"""Phase 8 编排层的测试构造夹具：脚本化客户端、受控工作区、装配与运行。

为什么需要它（而不是在每个用例里手写 YAML / 路径）：

- 编排层的每个端口都是**显式注入**的（PolicyClient / ToolRunner / ChangeAuthor / ApprovalGate）：
  测试必须能"只换一个端口"，否则"编排缺陷"与"平台缺陷"分不开（阶段计划 §2 的两步走）；
- 编排层会写 checkpoint、审计链、台账与受控工作区：所有路径都必须落在 tmp_root 下，
  一旦指向仓库真实文件，测试就变成了"会改坏仓库的测试"；
- 客户端脚本、任务、候选改动、审批记录都是**数据**：把它们集中成构造器，
  用例里剩下的就只有"这次要断言什么"。

对外入口（只构造、不断言、不隐藏被测行为）：

- 平台回答：`readiness(...)` / `allow_outcome(...)` / `validate_allow(...)` /
  `validate_block(...)` / `retrieval_ok(...)` / `scripted_client(...)`，
  以及 HTTP 形状的 `FakeOpener`（走完 ApiPolicyClient 的真实传输代码，但绝不出网）；
- 任务与改动：`task_spec(...)` / `write_change(...)` / `edit_change(...)` /
  `action_key(...)`；
- 文件系统与装配：`workspace_factory(...)` / `graph_config(...)` /
  `run_graph(...)` / `platform_runner(...)` / `checkpoint_file(...)`；
- 审批：`approval_file(...)` 写的是 Phase 4 的 `ApprovalRecord`（不另起一套审批语义）。
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple

from conftest import REPO_ROOT

from enforcement.approvals import ApprovalRecord
from enforcement.models import digest_of, utc_now
from policy.models import Decision, ValidationResult

from orchestration.approvals import ApprovalGate
from orchestration.checkpoint import JsonCheckpointStore
from orchestration.client import (
    EVALUATE_PATH,
    READINESS_PATH,
    RETRIEVE_PATH,
    VALIDATE_PATH,
    DecisionOutcome,
    PlatformReadiness,
    RetrievalOutcome,
    ScriptedPolicyClient,
    ValidationOutcome,
)
from orchestration.engines import RunReport, StepExecutor
from orchestration.models import (
    ContextRef,
    GraphState,
    RunLimits,
    ViolationRef,
    empty_state,
)
from orchestration.nodes import Change, NodeContext, ScriptedAuthor, TaskSpec
from orchestration.runtime import Assembly, OrchestrationConfig, build_assembly
from orchestration.tools import (
    ApprovalBinding,
    PlatformToolRunner,
    ToolOutcome,
    ToolRequest,
)

__all__ = [
    "APPROVED_PATH",
    "CHANGED_INDEX_VERSION",
    "CHANGED_RULE_SET_HASH",
    "INDEX_VERSION",
    "PROJECT_SOURCES",
    "REGISTRY_PATH",
    "ROUTE_PATHS",
    "RULE_SET_HASH",
    "TARGET_PATH",
    "ExecutingToolRunner",
    "FakeOpener",
    "FakeResponse",
    "GraphRun",
    "action_key",
    "allow_outcome",
    "allow_policy",
    "approval_file",
    "checkpoint_file",
    "echo_decision_response",
    "echo_retrieval_response",
    "echo_validate_response",
    "edit_change",
    "executed_outcome",
    "graph_config",
    "node_context",
    "platform_runner",
    "readiness",
    "readiness_response",
    "retrieval_empty",
    "retrieval_ok",
    "retrieval_unavailable",
    "run_graph",
    "scripted_client",
    "step_executor",
    "task_spec",
    "tool_request",
    "validate_allow",
    "validate_block",
    "workspace_factory",
    "write_change",
]

# --------------------------------------------------------------------------- 常量

# 规则集 / 索引 / 工具 schema 的版本凭据：恢复兼容性只比这几个值，
# 因此它们必须是**显式常量**，测试才能构造"变了"与"没变"两种情形。
RULE_SET_HASH = "sha256:" + "a" * 64
CHANGED_RULE_SET_HASH = "sha256:" + "b" * 64
INDEX_VERSION = "idx-phase8-1"
CHANGED_INDEX_VERSION = "idx-phase8-2"

TARGET_PATH = "src/shop/order_controller.py"
REGISTRY_PATH = REPO_ROOT / "registry" / "tool-registry.yaml"
APPROVED_PATH = REPO_ROOT / "registry" / "tool-registry.approved.json"

# 受控小项目：真实 PlatformToolRunner 的 post-check 要求目标存在、内容匹配、语法合法，
# 所以这里写的是**能通过 file_syntax 的真实 Python 源码**，不是随便一段文本。
PROJECT_SOURCES: Mapping[str, str] = {
    "README.md": "# 受控小项目\n\n这不是真实仓库：它只活在测试的 tmp 目录里。\n",
    "src/shop/__init__.py": '"""受控小项目的 shop 包。"""\n',
    "src/shop/order_service.py": '''"""业务用例层。"""


class OrderService:
    """订单用例。"""

    def create(self, payload: dict) -> dict:
        """创建订单。"""

        return dict(payload)
''',
    TARGET_PATH: '''"""接口层：Controller 只依赖 Service。"""

from shop.order_service import OrderService


class OrderController:
    """把请求转成服务调用。"""

    def __init__(self, service: OrderService) -> None:
        """注入业务用例层。"""

        self._service = service

    def create(self, payload: dict) -> dict:
        """处理创建请求。"""

        return self._service.create(payload)
''',
}


def workspace_factory(root: Path | str, *, name: str = "workspace") -> Path:
    """在 tmp 下造一个受控小项目，返回项目根。

    目录结构与 `tests/fixtures/validators/project` 同形（`src/shop/`），
    但内容更小：受控写入用例只关心"文件名对不对、语法过不过"。
    """

    target = Path(root) / name
    for relative, text in PROJECT_SOURCES.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return target


# --------------------------------------------------------------------------- 平台回答


def readiness(
    *,
    rule_set_hash: Optional[str] = RULE_SET_HASH,
    index_version: Optional[str] = INDEX_VERSION,
    state: str = "ready",
    ready: bool = True,
) -> PlatformReadiness:
    """平台版本凭据：恢复时与 checkpoint 里的快照比对。"""

    return PlatformReadiness(
        state=state, ready=ready, rule_set_hash=rule_set_hash, index_version=index_version
    )


def allow_outcome(
    *,
    rule_set_hash: str = RULE_SET_HASH,
    required_action: Optional[str] = None,
    validation: Optional[ValidationResult] = None,
    request_id: str = "<auto>",
) -> DecisionOutcome:
    """evaluate 的 allow 回答。

    `required_action="approval"` 是编排层审批门禁的触发条件（节点先问平台、再要人工授权）；
    Phase 1 协议自己把审批表达成 `block + required_action=approval`（见 policy.models），
    这里保留 allow + approval 的形状，是为了把"门禁本身"单独测出来。
    """

    return DecisionOutcome(
        decision=Decision.ALLOW,
        request_id=request_id,
        rule_set_hash=rule_set_hash,
        required_action=required_action,
        validation=validation,
    )


def validate_allow(
    *,
    rule_set_hash: str = RULE_SET_HASH,
    evidence_digest: Optional[str] = None,
    validators: Tuple[str, ...] = ("python.ast@1.0",),
    request_id: str = "<auto>",
) -> ValidationOutcome:
    """validate 的 allow 回答（验证节点与测试节点都用它）。"""

    return ValidationOutcome(
        decision=Decision.ALLOW,
        request_id=request_id,
        rule_set_hash=rule_set_hash,
        evidence_digest=evidence_digest,
        validators=validators,
    )


def validate_block(
    *,
    rule_id: str = "ARCH-001",
    file: str = TARGET_PATH,
    line: int = 8,
    message: str = "Controller 不得直接访问 Repository。",
    rule_set_hash: str = RULE_SET_HASH,
    request_id: str = "<auto>",
) -> ValidationOutcome:
    """validate 的 block 回答：带上一条**结构化 violation**，修复节点只认它。"""

    return ValidationOutcome(
        decision=Decision.BLOCK,
        request_id=request_id,
        rule_set_hash=rule_set_hash,
        violations=(
            ViolationRef(
                rule_id=rule_id,
                rule_version=1,
                severity="error",
                file=file,
                line=line,
                message=message,
            ),
        ),
    )


def retrieval_ok(
    *,
    index_version: Optional[str] = INDEX_VERSION,
    chunk_id: str = "chunk-1",
    source_path: str = "policies/architecture/ARCH-001.yaml",
    request_id: str = "<auto>",
) -> RetrievalOutcome:
    """检索命中：只带回**引用**（路径 + 哈希 + 许可），不带正文。"""

    return RetrievalOutcome(
        status="ok",
        request_id=request_id,
        index_version=index_version,
        contexts=(
            ContextRef(
                chunk_id=chunk_id,
                source_path=source_path,
                digest="sha256:" + "c" * 64,
                license="project-policy",
                tier="rule",
            ),
        ),
    )


def retrieval_empty(*, request_id: str = "<auto>") -> RetrievalOutcome:
    """检索无结果：这是显式状态，不是"没有规范"。"""

    return RetrievalOutcome(status="empty", request_id=request_id, detail="没有命中")


def retrieval_unavailable(*, request_id: str = "<auto>") -> RetrievalOutcome:
    """检索不可用：编排层必须停下，不许凭记忆继续规范相关步骤。"""

    return RetrievalOutcome(status="unavailable", request_id=request_id, detail="索引不可读")


def scripted_client(
    *,
    evaluate: Sequence[Any] = (),
    retrieve: Sequence[Any] = (),
    validate: Sequence[Any] = (),
    readiness_value: Optional[PlatformReadiness] = None,
) -> ScriptedPolicyClient:
    """按脚本回答的假平台客户端；脚本用完即失败关闭（没有隐式 allow）。"""

    return ScriptedPolicyClient(
        evaluate_script=tuple(evaluate),
        retrieve_script=tuple(retrieve),
        validate_script=tuple(validate),
        readiness_value=readiness_value or readiness(),
    )


# --------------------------------------------------------------------------- 任务与改动


def task_spec(task_id: str, **overrides: Any) -> TaskSpec:
    """任务级显式输入：目标文件、需求正文（只进内存）、主体与角色。"""

    payload: dict[str, Any] = {
        "task_id": task_id,
        "target": TARGET_PATH,
        "requirement": "按仓库规则集实现订单控制器",
        "layer": "controller",
        "principal": {"subject": "local-user", "roles": ["developer"]},
        "trace_id": "trace-phase8",
    }
    payload.update(overrides)
    return TaskSpec(**payload)


def write_change(
    *,
    path: str = TARGET_PATH,
    summary: str = "整文件写入控制器",
    content: Optional[str] = None,
) -> Change:
    """整文件写入的候选改动（走注册表里的 orc.fs.write）。"""

    return Change(
        path=path,
        summary=summary,
        content=content
        or '''"""接口层：Controller 只依赖 Service。"""

from shop.order_service import OrderService


class OrderController:
    """把请求转成服务调用。"""

    def __init__(self, service: OrderService) -> None:
        """注入业务用例层。"""

        self._service = service

    def create(self, payload: dict) -> dict:
        """处理创建请求（编排层改写过的版本）。"""

        return self._service.create(payload)
''',
    )


def edit_change(
    *,
    path: str = TARGET_PATH,
    summary: str = "字面量替换控制器内容",
    old: str = 'def create(self, payload: dict) -> dict:\n        """处理创建请求。"""',
    replacement: str = (
        'def create(self, payload: dict) -> dict:\n'
        '        """处理创建请求（受治理的修复）。"""'
    ),
) -> Change:
    """字面量替换的候选改动（走注册表里的 orc.fs.edit）。"""

    return Change(path=path, summary=summary, old=old, replacement=replacement)


def action_key(task_id: str, change: Change, *, repair_rounds: int = 0) -> str:
    """节点给一次改动算出的幂等键（action_id 与 action_hash 同源）。

    与 `orchestration.nodes._action_id` 是同一条公式：审批记录必须绑到这个值上，
    因此它是**契约的一部分**，测试必须自己能算出来（而不是从节点里读回来）。
    """

    digest = change.digest().split(":", 1)[-1][:16]
    return f"{task_id}:{repair_rounds}:{digest}"


def executed_outcome(
    *, tool_id: str = "orc.fs.write", action_id: str = "action-1", detail: str = ""
) -> ToolOutcome:
    """已执行且已交付的工具结论：只有它才算副作用真的发生了。"""

    return ToolOutcome(
        status="executed",
        tool_id=tool_id,
        action_id=action_id,
        final_outcome="delivered",
        reason_code="allow",
        detail=detail,
    )


@dataclass
class ExecutingToolRunner:
    """内存 Tool Runner：记录每次调用，按脚本回答，脚本用完默认"已执行且已交付"。

    与 @@BT@@orchestration.tools.RecordingToolRunner@@BT@@ 的差别只有**用完之后的默认值**：
    录制版用完即失败关闭（denied），本实现用完按"执行成功"回答。
    状态机与契约用例只关心"节点有没有动手、动了几次"；真正的副作用与审计链由
    @@BT@@PlatformToolRunner@@BT@@ 在集成 / 安全用例里跑一遍。
    """

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
        return executed_outcome(tool_id=request.tool_id, action_id=request.action_id)


# --------------------------------------------------------------------------- 装配与运行


def graph_config(
    root: Path | str,
    *,
    name: str = "run",
    workspace: Optional[Path | str] = None,
    engine: str = "reference",
    limits: Optional[RunLimits] = None,
    registry_path: Path | str = REGISTRY_PATH,
    approved_path: Optional[Path | str] = APPROVED_PATH,
    approvals_dir: Optional[Path | str] = None,
    **overrides: Any,
) -> OrchestrationConfig:
    """一次运行的显式配置：工作区、checkpoint、注册表、审计、台账、审批**全在 tmp 下**。

    `approvals_dir` 会被 `build_assembly` 原样交给 `ApprovalGate`；
    门禁既接受**单个审批文件**，也接受**审批收件箱目录**（目录里按 action_id 挑第一条匹配记录）。
    默认给一个空目录，等价于"没有审批"，也就是失败关闭。
    """

    base = Path(root) / name
    workspace_path = (
        Path(workspace) if workspace is not None else workspace_factory(base, name="workspace")
    )
    approvals = Path(approvals_dir) if approvals_dir is not None else base / "approvals"
    if approvals.suffix != ".json":
        approvals.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "workspace": workspace_path,
        "checkpoint_dir": base / "checkpoints",
        "registry_path": Path(registry_path),
        "approved_path": None if approved_path is None else Path(approved_path),
        "audit_path": base / "audit.jsonl",
        "ledger_path": base / "ledger.jsonl",
        "approvals_dir": approvals,
        "engine": engine,
        "limits": limits or RunLimits(max_repair_rounds=2, max_tool_calls=8, max_node_runs=24),
    }
    payload.update(overrides)
    return OrchestrationConfig(**payload)


@dataclass(frozen=True)
class GraphRun:
    """一次图运行的全部产物：报告、装配、配置、checkpoint 存储与任务。"""

    report: RunReport
    assembly: Assembly
    config: OrchestrationConfig
    store: JsonCheckpointStore
    task: TaskSpec

    @property
    def checkpoint_text(self) -> str:
        """checkpoint **原文**：断言"没存正文 / 密钥"时必须看字节，而不是看解析结果。"""

        return checkpoint_file(self.config.checkpoint_dir, self.task.task_id)


def run_graph(
    root: Path | str,
    *,
    client: Any,
    author: Any,
    runner: Any,
    task: Optional[TaskSpec] = None,
    engine: str = "reference",
    limits: Optional[RunLimits] = None,
    name: str = "run",
    config: Optional[OrchestrationConfig] = None,
    state: Optional[GraphState] = None,
    **overrides: Any,
) -> GraphRun:
    """按生产装配路径建 Assembly 并跑一次引擎，返回报告与全部上下文。

    传入 `config=`（上一次运行返回的那份）就是**恢复**：checkpoint 目录不变，
    于是 `StepExecutor.prepare` 会走 `plan_resume`，
    报告里的 `resume_mode` 说明这次走的是 fresh / resume / revalidate / reapprove。
    """

    config = (
        config
        if config is not None
        else graph_config(root, name=name, engine=engine, limits=limits, **overrides)
    )
    task = task or task_spec(name if name != "run" else "phase8-task")
    assembly = build_assembly(config, task=task, author=author, client=client, tool_runner=runner)
    fresh = (
        state
        if state is not None
        else empty_state(task.task_id, limits=config.limits, trace_id=task.trace_id)
    )
    report = assembly.engine.run(task_id=task.task_id, state=fresh)
    return GraphRun(
        report=report,
        assembly=assembly,
        config=config,
        store=JsonCheckpointStore(config.checkpoint_dir),
        task=task,
    )


def node_context(
    root: Path | str,
    *,
    task: Optional[TaskSpec] = None,
    client: Any = None,
    runner: Any = None,
    author: Any = None,
    approvals: Optional[ApprovalGate] = None,
    workspace: Optional[Path | str] = None,
    name: str = "context",
) -> NodeContext:
    """节点运行时依赖：测试里全部显式给，节点自己不构造客户端、不读环境变量。"""

    base = Path(root) / name
    return NodeContext(
        task=task or task_spec(name),
        client=client if client is not None else scripted_client(),
        runner=runner if runner is not None else _null_runner(),
        author=author if author is not None else ScriptedAuthor([]),
        approvals=approvals if approvals is not None else ApprovalGate(None),
        workspace=Path(workspace) if workspace is not None else workspace_factory(base),
    )


def step_executor(
    root: Path | str,
    *,
    context: Optional[NodeContext] = None,
    store: Any = None,
    spec: Any = None,
    nodes: Optional[Mapping[Any, Any]] = None,
    router_fns: Optional[Mapping[str, Any]] = None,
    name: str = "executor",
) -> StepExecutor:
    """直接用 `StepExecutor` 组装：契约与对抗用例要能替换节点表与分支函数。"""

    from orchestration.graph import DEFAULT_SPEC, ROUTERS
    from orchestration.nodes import NODES

    return StepExecutor(
        node_context=context if context is not None else node_context(root, name=name),
        store=store,
        spec=DEFAULT_SPEC if spec is None else spec,
        nodes=NODES if nodes is None else nodes,
        router_fns=ROUTERS if router_fns is None else router_fns,
        engine_name=name,
    )


def _null_runner() -> Any:
    from orchestration.tools import RecordingToolRunner

    return RecordingToolRunner(outcomes=())


def platform_runner(
    root: Path | str,
    *,
    workspace: Path | str,
    name: str = "platform",
    registry_path: Path | str = REGISTRY_PATH,
    approved_path: Optional[Path | str] = APPROVED_PATH,
    agent_version: str = "0.1.0",
) -> PlatformToolRunner:
    """真实 Phase 4 受控执行链：注册表是仓库真实数据，审计 / 台账写在 tmp 下。"""

    base = Path(root) / name
    return PlatformToolRunner(
        registry_path=Path(registry_path),
        approved_path=None if approved_path is None else Path(approved_path),
        audit_path=base / "audit.jsonl",
        ledger_path=base / "ledger.jsonl",
        workspace=Path(workspace),
        agent_version=agent_version,
    )


def tool_request(
    *,
    tool_id: str = "orc.fs.write",
    action_id: str = "action-1",
    request_id: str = "request-1",
    params: Optional[Mapping[str, Any]] = None,
    subject: str = "local-user",
    roles: Tuple[str, ...] = ("developer",),
    policy: Optional[ValidationResult] = None,
    approval_path: Optional[Path | str] = None,
    workspace: Optional[Path | str] = None,
    trace_id: Optional[str] = "trace-phase8",
) -> ToolRequest:
    """受治理的动作请求（直接调 Tool Runner 的用例用它）。"""

    return ToolRequest(
        tool_id=tool_id,
        action_id=action_id,
        request_id=request_id,
        params=dict(params or {"file_path": TARGET_PATH, "content": "# 写入\n"}),
        subject=subject,
        roles=roles,
        trace_id=trace_id,
        policy=policy,
        approval_path=None if approval_path is None else Path(approval_path),
        workspace=None if workspace is None else Path(workspace),
    )


def allow_policy(
    *, request_id: str = "request-1", rule_set_hash: str = RULE_SET_HASH
) -> ValidationResult:
    """一份**真实的 Phase 1 决策对象**：受控执行链要求动作带平台判定，缺了它一律不执行。"""

    return ValidationResult(
        decision=Decision.ALLOW, request_id=request_id, rule_set_hash=rule_set_hash
    )


def checkpoint_file(root: Path | str, task_id: str) -> str:
    """读 checkpoint 原文（UTF-8）。"""

    store = JsonCheckpointStore(root)
    return store.path_for(task_id).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- 审批


def approval_file(
    path: Path | str,
    *,
    action_hash: str,
    action_id: str,
    tool_id: str = "orc.fs.write",
    subject: str = "local-user",
    roles: Sequence[str] = ("reviewer",),
    ttl_seconds: int = 300,
    granted_offset_seconds: int = -1,
    granted_by: str = "alice",
    approval_id: str = "approval-phase8",
) -> Path:
    """写一份 Phase 4 的人工审批 JSON（与注册表的审批角色口径一致）。

    `ttl_seconds` 为负、`granted_offset_seconds` 更负就是"已过期"；
    角色与门禁的 `approval_roles` 无交集就是"审批人没有审批权"。
    """

    now = utc_now()
    record = ApprovalRecord(
        approval_id=approval_id,
        action_hash=action_hash,
        action_id=action_id,
        tool_id=tool_id,
        subject=subject,
        granted_by=granted_by,
        granted_by_roles=tuple(roles),
        granted_at=now + timedelta(seconds=granted_offset_seconds),
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    return target


# --------------------------------------------------------------------------- HTTP 形状的假平台


class FakeResponse:
    """`urllib` 响应的最小替身：ApiPolicyClient 只用 status / read() 与上下文管理。"""

    def __init__(self, status: int, payload: Mapping[str, Any]) -> None:
        self.status = status
        self._body = json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


class FakeOpener:
    """按路径回答的假 opener：**绝不出网**，但走完 ApiPolicyClient 的真实传输代码。

    键是 Phase 7 的公开路由；值是 `(status, payload)` 或
    `request -> (status, payload)`——后者用于"回声 request_id / trace_id"
    这类必须与请求逐字段一致的回答。
    """

    def __init__(self, responses: Mapping[str, Any]) -> None:
        self.responses = dict(responses)
        self.calls: list[Tuple[str, str]] = []

    def __call__(self, request: Any, timeout: Optional[float] = None) -> FakeResponse:
        path = urllib.parse.urlsplit(request.full_url).path
        self.calls.append((request.get_method(), path))
        if path not in self.responses:
            raise AssertionError(f"假 opener 没有登记 {path!r}：拒绝发出未声明的请求")
        entry = self.responses[path]
        status, payload = entry(request) if callable(entry) else entry
        return FakeResponse(status, payload)

    def paths(self) -> Tuple[str, ...]:
        return tuple(path for _, path in self.calls)


def echo_decision_response(
    *,
    decision: Decision = Decision.ALLOW,
    required_action: Optional[str] = None,
    violations: Tuple[ViolationRef, ...] = (),
    rule_set_hash: str = RULE_SET_HASH,
    drop_trace: bool = False,
) -> Callable[[Any], Tuple[int, Mapping[str, Any]]]:
    """构造一个"回声请求 request_id / trace_id"的决策回答。

    `drop_trace=True` 用来演"平台没有把 trace 还回来"：调用方必须失败关闭（TraceError）。
    """

    def build(request: Any) -> Tuple[int, Mapping[str, Any]]:
        body = json.loads((request.data or b"{}").decode("utf-8"))
        result = ValidationResult(
            decision=decision,
            request_id=str(body.get("request_id", "")),
            trace_id=None if drop_trace else body.get("trace_id"),
            rule_set_hash=rule_set_hash,
            required_action=required_action,
            violations=tuple(violations),
        )
        return 200, {"decision": result.to_decision_dict()}

    return build


def echo_retrieval_response(
    *,
    index_version: str = INDEX_VERSION,
    source_path: str = "policies/architecture/ARCH-001.yaml",
) -> Callable[[Any], Tuple[int, Mapping[str, Any]]]:
    """检索命中回答（带回 trace 回声，否则 trace 纪律会先失败）。"""

    def build(request: Any) -> Tuple[int, Mapping[str, Any]]:
        body = json.loads((request.data or b"{}").decode("utf-8"))
        return 200, {
            "status": "ok",
            "context": {
                "snippets": [
                    {
                        "chunk_id": "chunk-http",
                        "source_path": source_path,
                        "text_hash": "sha256:" + "c" * 64,
                        "license": "project-policy",
                        "tier": "rule",
                    }
                ],
                "trace_id": body.get("trace_id"),
            },
            "index": {"index_version": index_version},
        }

    return build


def echo_validate_response(
    *,
    decision: Decision = Decision.ALLOW,
    violations: Tuple[ViolationRef, ...] = (),
    rule_set_hash: str = RULE_SET_HASH,
    drop_decision: bool = False,
) -> Callable[[Any], Tuple[int, Mapping[str, Any]]]:
    """validate 的回答：报告 + 决策载荷（两样都要有，缺决策即"验证器不可用"）。"""

    def build(request: Any) -> Tuple[int, Mapping[str, Any]]:
        body = json.loads((request.data or b"{}").decode("utf-8"))
        report: dict[str, Any] = {
            "validators": [{"validator": "python.ast@1.0", "status": "ok"}],
            "evidence": [{"rule_id": "ARCH-001", "kind": "dependency"}],
        }
        if drop_decision:
            return 200, {"report": report}
        result = ValidationResult(
            decision=decision,
            request_id=str(body.get("request_id", "")),
            trace_id=body.get("trace_id"),
            rule_set_hash=rule_set_hash,
            violations=tuple(violations),
        )
        return 200, {"report": report, "decision": result.to_decision_dict()}

    return build


def readiness_response(
    *, rule_set_hash: str = RULE_SET_HASH, index_version: str = INDEX_VERSION
) -> Tuple[int, Mapping[str, Any]]:
    """`/v1/health/ready` 的回答：恢复兼容性需要的两个凭据就在这里。"""

    return 200, {
        "state": "ready",
        "ready": True,
        "tenants": [
            {
                "tenant": "alpha",
                "checks": [
                    {"check": "rule_set", "rule_set_hash": rule_set_hash},
                    {"check": "index", "index_version": index_version},
                ],
            }
        ],
    }


#: 供测试直接引用的路由常量（避免在各用例里重复 import）。
ROUTE_PATHS: Mapping[str, str] = {
    "evaluate": EVALUATE_PATH,
    "retrieve": RETRIEVE_PATH,
    "validate": VALIDATE_PATH,
    "readiness": READINESS_PATH,
}
