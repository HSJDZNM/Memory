"""Phase 8 编排闭环：把"编排层只是平台消费者"这件事证明出来。

    python tools/orchestration_loop.py          # 跑完整闭环，结论写到 .tmp/artifacts/
    python tools/orchestration_loop.py --json    # 只打印结论

它证明八件事（对应 Phase 8 的退出条件）：

1. **端到端受控场景**：需求 → 检索 → 规划 → 受治理写入（Phase 4 受控执行链）→
   验证 FAIL（ARCH-001）→ 修复 → 验证 PASS → 测试 → 收尾，每个节点都留下平台判定；
2. **编排可替换**：参考引擎与 LangGraph 引擎给出逐字节相同的 RunReport；
3. **循环有上限**：repair 轮次击穿即 needs_human，不会无限自调用；
4. **checkpoint 与恢复**：节点之间中断再恢复，决策路径与不中断一致，checkpoint 里没有正文；
5. **规则集变化不沿用旧 allow**：恢复时旧 trace 与旧验证结果作废，重新评估；
6. **人工审批**：没有审批的高风险动作不执行；签了真实审批之后只执行一次；
7. **平台故障失败关闭**：Policy API 不可达 → blocked 且零工具执行，连续失败会熔断；
8. **幂等**：同一个动作不会被执行第二次（幂等跳过 + Phase 4 台账两道闸）。

所有产物都在 `.tmp/phase-8-orchestration/` 下；HTTP 用的是**本机真实端口**（127.0.0.1），
不打外网、不改仓库真实文件。

两处**显式适配**：都不是"替平台判定"，都如实写进结论的 facts：

- `only` 字段：`nodes.testing` 传的是 checker 名（`failing_tests`），而
  `validators.pipeline` 的 `only` 收的是**验证器 id**（`tool.pytest`）。不处理的话真实 API
  会 500（`internal_error`）→ 编排层得到 `policy_unavailable` → 测试节点永远走不过去。
  闭环把该请求字段去掉：证据、验证器与判定仍然全部来自平台；
- 审批投递：注册表声明 `approval: required` 的工具，节点只在**平台决策**带
  `required_action=approval` 时才去审批门禁；而真实引擎把"需要审批"表达成
  `block + required_action=approval`，节点在 `decision.allowed` 那一步就返回
  `policy_blocked`。闭环因此在**可注入的工具端口**上按 `action_id` 把收件箱里的审批
  **文件**交给 Phase 4 的 pre-check（角色 / 哈希 / 主体 / 有效期 / 单次使用仍由平台判定）。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DEMO_ROOT = REPO_ROOT / ".tmp" / "phase-8-orchestration"
RESULT = REPO_ROOT / ".tmp" / "artifacts" / "phase-8-orchestration-result.json"
FIXTURE_PROJECT = REPO_ROOT / "tests" / "fixtures" / "validators" / "project"
REGISTRY = REPO_ROOT / "registry" / "tool-registry.yaml"
APPROVED = REPO_ROOT / "registry" / "tool-registry.approved.json"
CORPUS = REPO_ROOT / "knowledge" / "corpus.yaml"
INDEX = REPO_ROOT / ".tmp" / "retrieval" / "index.sqlite3"

HOST = "127.0.0.1"
TENANT = "alpha"
RULE_TENANT = "beta"
TOKEN = "phase8-loop-token"
RULE_TOKEN = "phase8-loop-rule-token"

WORKSPACE = DEMO_ROOT / "workspace"
CONTROLLER = "src/shop/order_controller.py"
CONTROLLER_BAD = "src/shop/order_controller_bad.py"
CONTROLLER_TEST = "tests/test_order_controller.py"
POLICY_FILE = "policies/architecture/ARCH-001.yaml"

# 受控工作区里补的**相关测试**：夹具项目没有 controller 的测试，而 TESTING-001
# （生产文件变更必须带测试）会让"验证 PASS"永远到不了——没有它，端到端场景无解。
CONTROLLER_TEST_LINES = (
    '"""OrderController 的边界测试（编排闭环的受控工作区）。"""',
    "",
    "from shop.order_controller import OrderController",
    "",
    "",
    "class StubService:",
    '    """最小 Service 替身：只记录调用。"""',
    "",
    "    def __init__(self) -> None:",
    '        """初始化调用记录。"""',
    "",
    "        self.calls: list[dict] = []",
    "",
    "    def create(self, payload: dict) -> dict:",
    '        """记录一次创建调用。"""',
    "",
    "        self.calls.append(payload)",
    '        return {"id": "order-1", **payload}',
    "",
    "",
    "def test_controller_delegates_to_service() -> None:",
    '    """Controller 只通过 Service 处理请求。"""',
    "",
    "    service = StubService()",
    '    result = OrderController(service).create({"id": "order-1"})',
    '    assert result["id"] == "order-1"',
    '    assert service.calls == [{"id": "order-1"}]',
)

# 只给"规则集变化"场景用：layer 对不上任何闭环上下文，因此它只改变规则集身份，
# 不改变任何一次判定（否则测的就不是"旧 allow 作废"，而是"新规则换了结论"）。
MARKER_RULE_LINES = (
    "# 编排闭环专用的规则集标记（只在 .tmp/ 的受控副本里）。",
    "id: ORCH-LOOP-001",
    "version: 1",
    "name: orchestration-loop-marker",
    "description: 只用来改变规则集身份，不参与任何闭环上下文的判定。",
    "scope:",
    "  language: python",
    "  layer: p8-loop-marker",
    "severity: warning",
    "enforcement:",
    "  type: deterministic",
    "  checker: missing_docstring",
    "rule:",
    "  missing_docstring:",
    "    targets: [module]",
    "message: 这条规则的 layer 永远不会命中闭环的上下文。",
    "source:",
    "  kind: project-policy",
    "  path: policies/ORCH-LOOP-001.yaml",
    "  note: 闭环用它证明规则集变化会让恢复重新评估。",
)

# 探针规则：真实引擎把"需要人工审批"表达成 block + required_action=approval。
# checker 必须是**上下文类**（forbidden_dependency），否则纯 evaluate 会把它记进
# skipped_rules，required_action 根本不会出现。
APPROVAL_RULE_LINES = (
    "# 闭环探针：改规则文件需要人工审批（真实平台口径）。",
    "id: ORCH-APPROVAL-PROBE-001",
    "version: 1",
    "name: policy-file-change-needs-approval",
    "description: 改规则文件属于高风险动作：平台以 block + required_action=approval 表达。",
    "scope:",
    "  language: python",
    "  operation: [edit]",
    "severity: error",
    "enforcement:",
    "  type: deterministic",
    "  checker: forbidden_dependency",
    "  requires_approval: true",
    "rule:",
    "  forbidden_dependency: [repository]",
    "message: 改规则文件必须有人工审批。",
    "source:",
    "  kind: project-policy",
    "  path: policies/ORCH-APPROVAL-PROBE-001.yaml",
)


@dataclass
class Scenario:
    name: str
    passed: bool
    detail: str = ""
    facts: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- 基础设施


def relative(path: Path) -> str:
    """结论里只写仓库相对路径：报告不该泄露绝对路径。"""

    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return int(probe.getsockname()[1])


def child_env() -> dict[str, str]:
    """子进程环境：让 `python -m retrieval.cli` / `python -m enforcement.cli` 能找到 src 布局。"""

    environment = dict(os.environ)
    existing = environment.get("PYTHONPATH", "")
    parts = [str(SRC_DIR), *([existing] if existing else [])]
    environment["PYTHONPATH"] = os.pathsep.join(parts)
    return environment


def ensure_index() -> tuple[bool, str]:
    """检索索引是构建产物：缺了就在这里按仓库的命令重建，失败要**响亮**地说出来。"""

    if INDEX.is_file():
        return True, "索引库已存在"
    completed = subprocess.run(
        [sys.executable, "-m", "retrieval.cli", "index"],
        cwd=str(REPO_ROOT),
        env=child_env(),
        capture_output=True,
        text=True,
        timeout=900,
    )
    if INDEX.is_file():
        return True, "索引库已重建"
    detail = (completed.stderr or completed.stdout or "").strip().splitlines()
    reason = detail[-1] if detail else f"退出码 {completed.returncode}"
    return False, f"检索索引不可用（python -m retrieval.cli index 失败：{reason[:200]}）"


def reset_workspace() -> Path:
    """受控工作区 = 夹具项目副本 + policies/ 副本 + controller 的相关测试。"""

    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE, ignore_errors=True)
    shutil.copytree(FIXTURE_PROJECT, WORKSPACE)
    copy_policies()
    test_path = WORKSPACE / CONTROLLER_TEST
    test_path.write_text("\n".join(CONTROLLER_TEST_LINES) + "\n", encoding="utf-8", newline="\n")
    return WORKSPACE


def copy_policies() -> None:
    """把仓库规则复制进受控工作区：审批场景要有可改的规则文件，规则集变化场景要有可改的副本。"""

    for source in sorted((REPO_ROOT / "policies").rglob("*.yaml")):
        target = WORKSPACE / "policies" / source.relative_to(REPO_ROOT / "policies")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    if not path.is_file():
        return ()
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            records.append(decoded)
    return tuple(records)


def execution_count(records: Sequence[dict[str, Any]], action_id: str) -> int:
    """台账里该 action 的**执行**条数（claim / grant 不算）。"""

    return sum(
        1
        for item in records
        if item.get("kind") == "execution" and item.get("action_id") == action_id
    )


def diff_keys(left: Any, right: Any) -> Optional[str]:
    """规范化 JSON 之后第一个不同的键名（没有不同就返回 None）。"""

    if json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True):
        return None
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                return key
            if json.dumps(left[key], sort_keys=True) != json.dumps(right[key], sort_keys=True):
                return key
        return ""
    return ""


def build_api_config(port: int) -> Path:
    """两个租户：alpha 用仓库规则；beta 用工作区规则副本（只给"规则集变化"用）。"""

    from policy_api.config import hash_token

    document = """
schema_version: "1.0"
service_name: phase8-orchestration-loop
deployment: loop
base_url: http://{host}:{port}
limits:
  max_request_bytes: 65536
  max_response_bytes: 262144
  max_context_bytes: 32768
  max_prompt_chars: 8000
  max_concurrency: 4
budgets:
  evaluate_ms: 5000
  retrieve_ms: 5000
  validate_ms: 60000
rate_limit:
  capacity: 1000
  refill_per_second: 1000.0
audit:
  enabled: true
  path: {audit}
tenants:
  - tenant_id: {tenant}
    display_name: 编排闭环（仓库规则集）
    project: alpha-project
    project_root: {workspace}
    rules_root: .
    rules: [policies]
    validation_root: .
    validators: validation/validators.yaml
    audit_log: {tenant_audit}
    retrieval:
      enabled: true
      corpus: knowledge/corpus.yaml
      database: .tmp/retrieval/index.sqlite3
  - tenant_id: {rule_tenant}
    display_name: 编排闭环（工作区规则副本）
    project: beta-project
    project_root: {workspace}
    rules_root: {workspace}
    rules: [policies]
    validation_root: .
    validators: validation/validators.yaml
    audit_log: {rule_audit}
    retrieval:
      enabled: true
      corpus: knowledge/corpus.yaml
      database: .tmp/retrieval/index.sqlite3
clients:
  - client_id: alpha-client
    token_sha256: {token}
    tenants: [{tenant}]
    projects: [alpha-project]
    roles: [developer]
  - client_id: beta-client
    token_sha256: {rule_token}
    tenants: [{rule_tenant}]
    projects: [beta-project]
    roles: [developer]
""".format(
        host=HOST,
        port=port,
        audit=relative(DEMO_ROOT / "audit.api.jsonl"),
        tenant=TENANT,
        rule_tenant=RULE_TENANT,
        workspace=relative(WORKSPACE),
        tenant_audit=relative(DEMO_ROOT / "audit.alpha.jsonl"),
        rule_audit=relative(DEMO_ROOT / "audit.beta.jsonl"),
        token=hash_token(TOKEN),
        rule_token=hash_token(RULE_TOKEN),
    )
    return write_text(DEMO_ROOT / "policy-api.yaml", document.lstrip())


def start_server(runtime: Any, port: int) -> Any:
    """在后台线程起一个真实的 uvicorn（真端口、真协议），返回 server 句柄。"""

    import uvicorn

    from policy_api.app import create_app

    server = uvicorn.Server(
        uvicorn.Config(create_app(runtime), host=HOST, port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, name="phase8-api", daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if getattr(server, "started", False):
            return server
        time.sleep(0.05)
    raise RuntimeError("uvicorn 未能在 20s 内启动")


# --------------------------------------------------------------------------- 显式适配


class ContractCompatClient:
    """真实 HTTP 客户端（`ApiPolicyClient`）+ 一处**请求字段**兼容。

    只做一件事：把编排层写错的 `only` 字段摘掉。它不读证据、不改决策、不缓存结论——
    每一次 allow / block 都来自真实 API。
    """

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.calls: list[dict[str, Any]] = []
        self.dropped_only = 0
        self.paths: list[str] = []

    def _record(self, route: str, call: Any, summary: dict[str, Any]) -> None:
        request_id = getattr(call, "request_id", "")
        self.calls.append({"route": route, "request_id": request_id, **summary})

    def evaluate(self, call: Any) -> Any:
        outcome = self.inner.evaluate(call)
        self._record(
            "evaluate",
            call,
            {
                "decision": outcome.decision.value,
                "required_action": outcome.required_action,
                "rule_ids": [item.rule_id for item in outcome.violations],
            },
        )
        return outcome

    def retrieve(self, call: Any) -> Any:
        outcome = self.inner.retrieve(call)
        self._record(
            "retrieve",
            call,
            {
                "status": outcome.status,
                "chunks": len(outcome.contexts),
                "index_version": outcome.index_version,
            },
        )
        return outcome

    def validate(self, call: Any) -> Any:
        if call.only:
            # checker 名 → 平台契约（验证器 id）不一致：这里只摘掉字段，
            # 让平台按自己的规则集跑完整流水线；证据与判定仍然由平台产出。
            self.dropped_only += 1
            call = replace(call, only=())
        outcome = self.inner.validate(call)
        self._record(
            "validate",
            call,
            {
                "decision": outcome.decision.value,
                "rule_ids": [item.rule_id for item in outcome.violations],
                "validators": list(outcome.validators),
                "blockers": list(outcome.blockers),
            },
        )
        return outcome

    def readiness(self) -> Any:
        self.paths.append("/v1/health/ready")
        return self.inner.readiness()

    def route_calls(self, route: str) -> list[dict[str, Any]]:
        return [item for item in self.calls if item["route"] == route]


class InterruptingClient:
    """在第 N 次某个路由的调用上抛 `KeyboardInterrupt`：模拟进程在节点之间被杀。"""

    def __init__(self, inner: Any, *, route: str, nth: int = 1) -> None:
        self.inner = inner
        self.route = route
        self.nth = nth
        self.seen = 0
        self.tripped = False

    def _maybe_trip(self, route: str) -> None:
        if route != self.route:
            return
        self.seen += 1
        if self.seen >= self.nth and not self.tripped:
            self.tripped = True
            raise KeyboardInterrupt(f"模拟进程在 {route} 调用处被杀")

    def evaluate(self, call: Any) -> Any:
        self._maybe_trip("evaluate")
        return self.inner.evaluate(call)

    def retrieve(self, call: Any) -> Any:
        self._maybe_trip("retrieve")
        return self.inner.retrieve(call)

    def validate(self, call: Any) -> Any:
        self._maybe_trip("validate")
        return self.inner.validate(call)

    def readiness(self) -> Any:
        return self.inner.readiness()


class ObservableToolRunner:
    """包一层真实 `PlatformToolRunner`：记录动作，并按收件箱补上审批**文件**。

    `relay=True` 时，如果节点没有把审批文件交给 Phase 4（见模块文档的审批投递适配），
    就按 `action_id` 从审批收件箱里找到那份文件附上。它自己**不判定**任何事：
    没有记录就不附（pre-check 照样 block），附错了也由平台判 `approval_*` 失败码。
    """

    def __init__(self, inner: Any, *, approval_inbox: Optional[Path] = None, relay: bool = False) -> None:
        self.inner = inner
        self.approval_inbox = approval_inbox
        self.relay = relay
        self.requests: list[Any] = []
        self.outcomes: list[Any] = []
        self.relayed: list[str] = []

    def binding(self, request: Any) -> Any:
        return self.inner.binding(request)

    def run(self, request: Any) -> Any:
        from orchestration.approvals import ApprovalGate

        if self.relay and request.approval_path is None and self.approval_inbox is not None:
            located = ApprovalGate(self.approval_inbox).resolve(request.action_id)
            if located is not None:
                request = replace(request, approval_path=located)
                self.relayed.append(request.action_id)
        self.requests.append(request)
        outcome = self.inner.run(request)
        self.outcomes.append(outcome)
        return outcome


# --------------------------------------------------------------------------- 一次运行


@dataclass
class Run:
    """一次编排运行的装配结果：所有路径都在 DEMO_ROOT 下，端口是本机真实端口。"""

    tag: str
    root: Path
    task: Any
    workspace: Path
    config: Any
    assembly: Any
    client: Any
    runner: ObservableToolRunner

    @property
    def ledger_path(self) -> Path:
        return Path(self.config.ledger_path)

    @property
    def audit_path(self) -> Path:
        return Path(self.config.audit_path)

    @property
    def approvals(self) -> Path:
        return Path(self.config.approvals_dir)

    def ledger(self) -> tuple[dict[str, Any], ...]:
        return read_jsonl(self.ledger_path)

    def start(self, *, task_id: Optional[str] = None) -> Any:
        from orchestration.models import empty_state

        identifier = task_id or self.task.task_id
        state = empty_state(
            identifier,
            limits=self.config.limits,
            trace_id=self.task.trace_id,
            request_id=f"{identifier}:request",
        )
        return self.assembly.engine.run(task_id=identifier, state=state)

    def checkpoint_text(self, task_id: Optional[str] = None) -> str:
        from orchestration.checkpoint import JsonCheckpointStore

        store = JsonCheckpointStore(self.config.checkpoint_dir)
        return store.path_for(task_id or self.task.task_id).read_text(encoding="utf-8")

    def checkpoint_state(self, task_id: Optional[str] = None) -> Any:
        from orchestration.checkpoint import JsonCheckpointStore
        from orchestration.models import GraphState

        store = JsonCheckpointStore(self.config.checkpoint_dir)
        record = store.load(task_id or self.task.task_id)
        return GraphState.model_validate(dict(record.state))

    def path_facts(self) -> dict[str, Any]:
        return {
            "checkpoints": relative(Path(self.config.checkpoint_dir)),
            "audit": relative(self.audit_path),
            "ledger": relative(self.ledger_path),
            "approvals": relative(self.approvals),
        }


def make_run(
    tag: str,
    *,
    task: Any,
    author: Any,
    base_url: str,
    engine: str = "reference",
    token: str = TOKEN,
    limits: Any = None,
    agent_version: str = "0.1.0",
    interrupt: Optional[tuple[str, int]] = None,
    relay: bool = False,
    reset: bool = True,
    checkpoint_dir: Optional[Path] = None,
    workspace: Optional[Path] = None,
) -> Run:
    """按显式配置装配一次运行：真 HTTP 客户端 + 真 Phase 4 受控执行链 + 真 checkpoint。"""

    from orchestration.client import ApiPolicyClient
    from orchestration.models import RunLimits
    from orchestration.runtime import OrchestrationConfig, build_assembly
    from orchestration.tools import PlatformToolRunner

    area = DEMO_ROOT / "runs" / tag
    if reset and checkpoint_dir is None:
        shutil.rmtree(area, ignore_errors=True)
    area.mkdir(parents=True, exist_ok=True)
    approvals = area / "approvals"
    approvals.mkdir(parents=True, exist_ok=True)
    workdir = workspace or WORKSPACE
    config = OrchestrationConfig(
        workspace=workdir,
        checkpoint_dir=checkpoint_dir or (area / "checkpoints"),
        registry_path=REGISTRY,
        approved_path=APPROVED,
        audit_path=area / "audit.jsonl",
        ledger_path=area / "ledger.jsonl",
        approvals_dir=approvals,
        api_base_url=base_url,
        api_token=token,
        tenant=TENANT if token == TOKEN else RULE_TENANT,
        engine=engine,
        agent_version=agent_version,
        limits=limits or RunLimits(),
    )
    client: Any = ContractCompatClient(ApiPolicyClient(base_url, token=token))
    if interrupt is not None:
        client = InterruptingClient(client, route=interrupt[0], nth=interrupt[1])
    runner = ObservableToolRunner(
        PlatformToolRunner(
            registry_path=config.registry_path,
            approved_path=config.approved_path,
            audit_path=config.audit_path,
            ledger_path=config.ledger_path,
            workspace=config.workspace,
            agent_version=config.agent_version,
        ),
        approval_inbox=approvals,
        relay=relay,
    )
    assembly = build_assembly(config, task=task, author=author, client=client, tool_runner=runner)
    return Run(
        tag=tag,
        root=area,
        task=task,
        workspace=workdir,
        config=config,
        assembly=assembly,
        client=client,
        runner=runner,
    )


def compat_of(run: Run) -> ContractCompatClient:
    """取到最里层那个真实客户端（可能被 InterruptingClient 包了一层）。"""

    client = run.client
    while not isinstance(client, ContractCompatClient):
        client = client.inner
    return client


# --------------------------------------------------------------------------- 任务与作者


def controller_task(task_id: str, *, requirement: str) -> Any:
    from orchestration.nodes import TaskSpec

    return TaskSpec(
        task_id=task_id,
        target=CONTROLLER,
        requirement=requirement,
        layer="controller",
        language="python",
        query="controller service repository 依赖边界",
        principal={"subject": "orchestrator", "roles": ["developer"]},
        acceptance=("ARCH-001 不再命中", "相关测试通过"),
        trace_id=f"trace-{task_id}",
    )


def bad_controller_text() -> str:
    """坏版本取自**夹具项目**，不是受控工作区。

    受控工作区会被实施节点改写：如果从工作区读"好版本"，中断之后重建作者就会把
    "当前（坏的）内容"当成"修好后的内容"，修复动作变成一次空编辑——
    闭环自己的产物依赖会污染它要证明的语义。
    """

    return read_text(FIXTURE_PROJECT / CONTROLLER_BAD)


def good_controller_text() -> str:
    return read_text(FIXTURE_PROJECT / CONTROLLER)


def controller_author() -> Any:
    """第一轮故意越层（ARCH-001 命中），第二轮按结构化 violation 修好。"""

    from orchestration.nodes import Change, ScriptedAuthor

    bad = bad_controller_text()
    good = good_controller_text()
    return ScriptedAuthor(
        [
            Change(path=CONTROLLER, summary="第一次实现（越层依赖）", content=bad),
            Change(path=CONTROLLER, summary="按 ARCH-001 修复依赖方向", old=bad, replacement=good),
        ]
    )


def steps_facts(report: Any) -> list[dict[str, Any]]:
    return [
        {"node": item.node, "label": item.label, "status": item.status} for item in report.steps
    ]


def traces_facts(state: Any) -> list[dict[str, Any]]:
    return [
        {"node": item.node.value, "request_id": item.request_id, "decision": item.decision.value}
        for item in state.traces
    ]


def require_index() -> Optional[Scenario]:
    """索引不可用就让需要检索的场景**明确失败**，而不是跳过。"""

    if INDEX.is_file():
        return None
    return Scenario("检索索引不可用", False, INDEX_REASON)


INDEX_REASON = "检索索引不存在且无法重建"


# --------------------------------------------------------------------------- 场景


def scenario_end_to_end(api: "Api") -> Scenario:
    """需求 → 检索 → 规划 → 受治理写入 → 验证 FAIL → 修复 → PASS → 测试 → 收尾。"""

    blocked = require_index()
    if blocked is not None:
        return Scenario("端到端受控场景", False, blocked.detail)

    reset_workspace()
    task = controller_task("p8-e2e", requirement="让 OrderController 只经 Service 访问 Repository")
    run = make_run("e2e", task=task, author=controller_author(), base_url=api.base_url)
    report = run.start()
    compat = compat_of(run)
    validations = compat.route_calls("validate")
    decisions = [item["decision"] for item in validations]
    failing_rules = validations[0]["rule_ids"] if validations else []
    executed = [item for item in run.runner.outcomes if item.executed]
    action_ids = [item.action_id for item in executed]
    ledger = run.ledger()
    contexts = report.state.contexts

    expected = [
        "requirement_analysis",
        "policy_retrieval",
        "architecture_planning",
        "implementation",
        "validation",
        "repair",
        "validation",
        "testing",
        "review",
    ]
    sequence = [item["node"] for item in steps_facts(report)]
    passed = (
        report.status.value == "completed"
        and sequence == expected
        and decisions[:1] == ["block"]
        and "ARCH-001" in failing_rules
        and decisions[-2:] == ["allow", "allow"]
        and len(executed) == 2
        and all(execution_count(ledger, item) == 1 for item in action_ids)
        and bool(contexts)
    )
    detail = (
        f"{len(report.steps)} 步，判定 {decisions}，violation {failing_rules}，"
        f"动作 {len(executed)} 次"
    )
    return Scenario(
        "端到端受控场景",
        passed,
        detail,
        {
            "engine": report.engine,
            "status": report.status.value,
            "steps": steps_facts(report),
            "traces": traces_facts(report.state),
            "validation_decisions": decisions,
            "failing_rule_ids": failing_rules,
            "action_ids": action_ids,
            "counters": report.state.counters.model_dump(),
            "retrieval": {
                "chunks": len(contexts),
                "index_version": report.state.snapshot.index_version
                if report.state.snapshot
                else None,
                "sources": [item.source_path for item in contexts][:3],
                "licenses": sorted({item.license for item in contexts}),
            },
            "compat": {"dropped_only": compat.dropped_only},
            **run.path_facts(),
        },
    )


def scenario_engine_is_swappable(api: "Api") -> Scenario:
    """同一场景两个引擎：RunReport 的载荷逐字节一致（引擎名 / 耗时 / checkpoint 数除外）。"""

    from orchestration.errors import EngineUnavailableError

    payloads: dict[str, Any] = {}
    try:
        for engine in ("reference", "langgraph"):
            reset_workspace()
            task = controller_task("p8-engine", requirement="两个引擎给出同一份报告")
            author = controller_author()
            run = make_run(f"engine-{engine}", task=task, author=author, base_url=api.base_url,
                           engine=engine)
            report = run.start()
            payload = report.to_payload()
            for key in ("engine", "elapsed_ms", "checkpoints"):
                payload.pop(key, None)
            payloads[engine] = {"report": payload, "status": report.status.value}
    except EngineUnavailableError as error:
        return Scenario("编排可替换", False, f"LangGraph 引擎不可用：{error.detail}", {})

    from orchestration.langgraph_engine import langgraph_version

    left = payloads["reference"]["report"]
    right = payloads["langgraph"]["report"]
    difference = diff_keys(left, right)
    identical = difference is None
    passed = (
        identical
        and payloads["reference"]["status"] == "completed"
        and payloads["langgraph"]["status"] == "completed"
    )
    return Scenario(
        "编排可替换",
        passed,
        "两个引擎的报告逐字节一致" if identical else f"报告在 {difference!r} 上不同",
        {
            "identical": identical,
            "first_difference": difference,
            "reference_status": payloads["reference"]["status"],
            "langgraph_status": payloads["langgraph"]["status"],
            "langgraph_version": langgraph_version(),
        },
    )


def scenario_repair_limit(api: "Api") -> Scenario:
    """repair 轮次上限击穿：needs_human + limit_repair_rounds，绝不无限自调用。"""

    from orchestration.models import RunLimits
    from orchestration.nodes import Change, ScriptedAuthor

    reset_workspace()
    bad = bad_controller_text()
    still_bad = bad.replace(
        "反例：Controller 直接依赖 Repository，ARCH-001 必须由 AST 证据命中。",
        "反例（第二轮）：Controller 仍然直接依赖 Repository。",
    )
    author = ScriptedAuthor(
        [
            Change(path=CONTROLLER, summary="第一次实现（越层依赖）", content=bad),
            Change(path=CONTROLLER, summary="第二次尝试（仍然越层）", content=still_bad),
        ]
    )
    limits = RunLimits(max_repair_rounds=1, max_tool_calls=6)
    task = controller_task("p8-limit", requirement="上限击穿时必须停下来交给人")
    run = make_run("limit", task=task, author=author, base_url=api.base_url, limits=limits)
    report = run.start()
    compat = compat_of(run)
    validations = compat.route_calls("validate")
    failure = report.failure.code.value if report.failure else None
    passed = (
        report.status.value == "needs_human"
        and failure == "limit_repair_rounds"
        and report.state.counters.repair_rounds == 1
        and len(validations) >= 2
    )
    return Scenario(
        "循环上限",
        passed,
        f"{report.status.value} / {failure}，repair 轮次 {report.state.counters.repair_rounds}",
        {
            "status": report.status.value,
            "failure": failure,
            "repair_rounds": report.state.counters.repair_rounds,
            "node_runs": report.state.counters.node_runs,
            "tool_calls": report.state.counters.tool_calls,
            "validation_decisions": [item["decision"] for item in validations],
            "nodes": [item["node"] for item in steps_facts(report)],
        },
    )


def scenario_checkpoint_resume(api: "Api") -> Scenario:
    """节点之间中断再恢复：决策路径与不中断一致，且 checkpoint 里没有正文。"""

    blocked = require_index()
    if blocked is not None:
        return Scenario("checkpoint 与恢复", False, blocked.detail)

    task_id = "p8-resume"
    reset_workspace()
    baseline_task = controller_task(task_id, requirement="中断之后恢复的决策路径必须一致")
    baseline = make_run("resume-baseline", task=baseline_task, author=controller_author(),
                        base_url=api.base_url)
    baseline_report = baseline.start()
    baseline_traces = [item.request_id for item in baseline_report.state.traces]

    reset_workspace()
    interrupted = False
    run = make_run(
        "resume",
        task=controller_task(task_id, requirement="中断之后恢复的决策路径必须一致"),
        author=controller_author(),
        base_url=api.base_url,
        interrupt=("validate", 1),
    )
    try:
        run.start()
    except KeyboardInterrupt:
        interrupted = True
    before_resume = run.checkpoint_state(task_id)

    resumed = make_run(
        "resume",
        task=controller_task(task_id, requirement="中断之后恢复的决策路径必须一致"),
        author=controller_author(),
        base_url=api.base_url,
        reset=False,
    )
    report = resumed.start()
    resumed_traces = [item.request_id for item in report.state.traces]
    checkpoint_text = resumed.checkpoint_text(task_id)
    # 敏感标记从**本次任务与本次改动**里取，而不是手写几行字面量：
    # 任务文件换了内容，这条断言要跟着换（手写字面量会悄悄失效）。
    author_changes = controller_author()
    sensitive = (
        baseline_task.requirement,
        *(item.content or item.replacement or "" for item in author_changes._sequence),
    )
    sensitive = tuple(item for item in sensitive if item)
    leaked = [item for item in sensitive if item in checkpoint_text]
    no_sensitive = not leaked
    traces_equal = resumed_traces == baseline_traces
    passed = (
        interrupted
        and report.resumed
        and report.resume_mode == "resume"
        and report.status.value == "completed"
        and traces_equal
        and no_sensitive
    )
    return Scenario(
        "checkpoint 与恢复",
        passed,
        f"resume_mode={report.resume_mode}，决策路径一致={traces_equal}，"
        f"checkpoint 无正文={no_sensitive}",
        {
            "interrupted": interrupted,
            "resume_mode": report.resume_mode,
            "resumed": report.resumed,
            "status": report.status.value,
            "failure": None if report.failure is None else report.failure.model_dump(mode="json"),
            "baseline_status": baseline_report.status.value,
            "baseline_failure": (
                None if baseline_report.failure is None else baseline_report.failure.model_dump(mode="json")
            ),
            "traces": resumed_traces,
            "traces_count": len(resumed_traces),
            "traces_equal": traces_equal,
            "no_sensitive_text": no_sensitive,
            "leaked_markers": leaked,
            "traces_before_interrupt": [
                item.request_id for item in before_resume.traces
            ],
            "checkpoint_bytes": len(checkpoint_text.encode("utf-8")),
        },
    )


def scenario_rule_set_change(api: "Api") -> Scenario:
    """规则集变了：恢复结论是 revalidate，旧 trace 作废，新决策从检索节点重来。"""

    blocked = require_index()
    if blocked is not None:
        return Scenario("规则集变化不沿用旧 allow", False, blocked.detail)

    task_id = "p8-revalidate"
    reset_workspace()
    run = make_run(
        "revalidate",
        task=controller_task(task_id, requirement="规则集变化之后旧 allow 必须作废"),
        author=controller_author(),
        base_url=api.base_url,
        token=RULE_TOKEN,
        interrupt=("validate", 1),
    )
    interrupted = False
    try:
        run.start()
    except KeyboardInterrupt:
        interrupted = True
    before = run.checkpoint_state(task_id)
    before_traces = [item.node.value for item in before.traces]
    rule_set_before = run.assembly.snapshot.rule_set_hash

    # 改规则集：往工作区的规则副本里加一条 layer 永远对不上的规则。
    write_text(WORKSPACE / "policies" / "ORCH-LOOP-001.yaml", "\n".join(MARKER_RULE_LINES) + "\n")

    resumed = make_run(
        "revalidate",
        task=controller_task(task_id, requirement="规则集变化之后旧 allow 必须作废"),
        author=controller_author(),
        base_url=api.base_url,
        token=RULE_TOKEN,
        reset=False,
    )
    rule_set_after = resumed.assembly.snapshot.rule_set_hash
    report = resumed.start()
    final_traces = [item.node.value for item in report.state.traces]
    decisions = compat_calls(resumed)
    revalidated_note = any("旧决定作废" in note for note in report.state.notes)
    cleared = "implementation" in before_traces and "implementation" not in final_traces
    passed = (
        interrupted
        and rule_set_before != rule_set_after
        and report.resume_mode == "revalidate"
        and revalidated_note
        and cleared
        and report.status.value == "completed"
        and "validation" in final_traces
    )
    return Scenario(
        "规则集变化不沿用旧 allow",
        passed,
        f"resume_mode={report.resume_mode}，旧 trace 清掉={cleared}，终态 {report.status.value}",
        {
            "resume_mode": report.resume_mode,
            "cleared": cleared,
            "status": report.status.value,
            "traces_before": before_traces,
            "traces_after": final_traces,
            "revalidate_note": revalidated_note,
            "rule_set_changed": rule_set_before != rule_set_after,
            "validation_decisions": decisions,
        },
    )


def compat_calls(run: Run) -> list[str]:
    return [item["decision"] for item in compat_of(run).route_calls("validate")]


def scenario_human_approval(api: "Api") -> Scenario:
    """改规则文件（orc.policy.edit）必须人工审批：没审批不执行，签了只执行一次。"""

    from orchestration.approvals import ApprovalGate
    from orchestration.models import empty_state
    from orchestration.nodes import Change, ScriptedAuthor, TaskSpec

    reset_workspace()
    rule_text = read_text(WORKSPACE / POLICY_FILE)
    old_line = "message: Controller 必须通过 Service 访问 Repository。"
    new_line = "message: Controller 必须通过 Service 访问 Repository（编排闭环修订）。"
    change = Change(
        path=POLICY_FILE,
        summary="修订 ARCH-001 的说明文本",
        old=old_line,
        replacement=new_line,
    )
    task = TaskSpec(
        task_id="p8-approval",
        target=CONTROLLER,
        requirement="修订 policies/ARCH-001.yaml 的说明文本（高风险动作，需要人工审批）",
        layer="controller",
        language="python",
        query="controller service repository 审批",
        principal={"subject": "orchestrator", "roles": ["developer"]},
        acceptance=("规则文件的可审批写入只执行一次",),
        trace_id="trace-p8-approval",
    )
    first = make_run("approval-1", task=task, author=ScriptedAuthor([change]), base_url=api.base_url)
    first_report = first.start()
    first_failure = first_report.failure.code.value if first_report.failure else None
    first_executed = any(item.executed for item in first.runner.outcomes)
    if not first.runner.requests:
        # 第一次运行必须走到"需要审批"那一步才可能拿到绑定；走不到就把判定原样报出来，
        # 不要用一个 IndexError 把真实原因盖掉。
        decisions = compat_of(first).route_calls("evaluate")
        return Scenario(
            "人工审批",
            False,
            f"第一次运行没有提出任何动作（{first_report.status.value}/"
            f"{first_failure}）：平台判定 {decisions[:1]}",
            {
                "first_status": first_report.status.value,
                "first_failure": first_failure,
                "first_failure_detail": (
                    None if first_report.failure is None else first_report.failure.detail
                ),
                "evaluate_calls": decisions[:2],
                "controller": CONTROLLER,
                "policy_file": POLICY_FILE,
            },
        )
    attempted = first.runner.requests[0]
    binding = first.runner.binding(attempted)

    # 用真实的 Phase 4 CLI 签发审批：它和受控执行走同一条 action 构造路径。
    document = {
        "action_id": attempted.action_id,
        "request_id": attempted.request_id,
        "agent": "orchestrator",
        "agent_version": first.config.agent_version,
        "tool_id": attempted.tool_id,
        "subject": attempted.subject,
        "roles": list(attempted.roles),
        "params": dict(attempted.params),
        "workspace": Path(attempted.workspace).as_posix(),
    }
    if attempted.trace_id is not None:
        document["trace_id"] = attempted.trace_id
    request_path = write_text(
        first.root / "approval-request.json",
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    approval_path = first.approvals / "approval.json"
    signed = subprocess.run(
        [
            sys.executable,
            "-m",
            "enforcement.cli",
            "approve",
            "--request",
            str(request_path),
            "--out",
            str(approval_path),
            "--granted-by",
            "p8-reviewer",
            "--roles",
            "reviewer",
            "--registry",
            str(REGISTRY),
            "--approved",
            str(APPROVED),
            "--workspace",
            str(first.workspace),
        ],
        cwd=str(REPO_ROOT),
        env=child_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if not approval_path.is_file():
        return Scenario(
            "人工审批",
            False,
            "Phase 4 CLI 未能签发审批：" + (signed.stderr or signed.stdout).strip()[:200],
            {},
        )
    record = json.loads(read_text(approval_path))
    approval_hash_matches = record["action_hash"] == binding.action_hash

    # 门禁本身接受这份审批（正向对照：审批确实绑在平台口径的动作上）。
    gate = ApprovalGate(first.approvals)
    probe_state = empty_state(task.task_id, limits=first.config.limits)
    gate_use = gate.use(
        probe_state,
        node=__import__("orchestration.models", fromlist=["NodeId"]).NodeId.IMPLEMENTATION,
        action_hash=binding.action_hash,
        action_id=binding.action_id,
        tool_id=binding.tool_id,
        subject=binding.subject,
    )

    # 第二次运行：把人工签发的审批放进**这次运行的收件箱**。
    # 审批门禁是节点自己的一道闸（"图到达了审批节点"不等于批准），因此审批必须真的在
    # 这次运行的收件箱里；工具端口只是把找到的那份文件交给 Phase 4 复验。
    reset_workspace()
    second = make_run(
        "approval-2",
        task=task,
        author=ScriptedAuthor([change]),
        base_url=api.base_url,
        relay=True,
    )
    shutil.copy2(approval_path, second.approvals / approval_path.name)
    second_report = second.start()
    second_ledger = second.ledger()
    executions = execution_count(second_ledger, attempted.action_id)
    changed_paths = [item.path for item in second_report.state.artifacts if item.path]
    rule_after = read_text(WORKSPACE / POLICY_FILE)
    write_happened = new_line in rule_after and old_line in rule_text

    # 缺陷探针：真实平台把"需要审批"表达成 block + required_action=approval，
    # 节点却在 decision.allowed 那一步就返回 policy_blocked，审批门禁根本到不了。
    probe_rule = WORKSPACE / "policies" / "ORCH-APPROVAL-PROBE-001.yaml"
    write_text(probe_rule, "\n".join(APPROVAL_RULE_LINES) + "\n")
    probe_run = make_run(
        "approval-probe",
        task=task,
        author=ScriptedAuthor([change]),
        base_url=api.base_url,
        token=RULE_TOKEN,
    )
    probe_report = probe_run.start()
    probe_rule.unlink(missing_ok=True)
    platform_decisions = compat_of(probe_run).route_calls("evaluate")
    platform_probe = {
        "status": probe_report.status.value,
        "failure": None if probe_report.failure is None else probe_report.failure.code.value,
        "platform_decision": platform_decisions[0]["decision"] if platform_decisions else None,
        "platform_required_action": platform_decisions[0]["required_action"]
        if platform_decisions
        else None,
        "executions": len([item for item in probe_run.runner.outcomes if item.executed]),
    }
    routed_to_gate = platform_probe["failure"] in ("approval_missing", "approval_param_mismatch")

    passed = (
        first_report.status.value == "needs_human"
        and first_failure == "approval_missing"
        and not first_executed
        and approval_hash_matches
        and gate_use.action_hash == binding.action_hash
        and second_report.status.value == "completed"
        and executions == 1
        and write_happened
        # "需要审批"的判定必须真的走到门禁上，而不是被当成普通阻断——
        # 只写进 facts 不算断言（独立验证指出了这一点）。
        and routed_to_gate
    )
    detail = (
        f"第一次 {first_report.status.value}/{first_failure}（未执行={not first_executed}），"
        f"审批哈希匹配={approval_hash_matches}，第二次 {second_report.status.value}，"
        f"执行 {executions} 次"
    )
    return Scenario(
        "人工审批",
        passed,
        detail,
        {
            "first_status": first_report.status.value,
            "first_failure": first_failure,
            "first_executed": first_executed,
            "action_id": attempted.action_id,
            "approval_action_hash_matches": approval_hash_matches,
            "approval_granted_by_roles": list(record["granted_by_roles"]),
            "gate_accepts_platform_binding": gate_use.action_hash == binding.action_hash,
            "second_status": second_report.status.value,
            "second_failure": (
                None if second_report.failure is None else second_report.failure.model_dump(mode="json")
            ),
            "second_steps": steps_facts(second_report),
            "approvals_seen_by_second": relative(second.approvals),
            "second_changed_paths": sorted(set(changed_paths)),
            "second_executions": executions,
            "write_happened": write_happened,
            "approval_delivered_by": "runner_inbox_relay" if second.runner.relayed else "node",
            "platform_approval_decision": platform_probe,
            "platform_decision_routed_to_gate": routed_to_gate,
            **first.path_facts(),
        },
    )


def scenario_platform_outage(api: "Api") -> Scenario:
    """Policy API 不可达：blocked + policy_unavailable + 零工具执行；连续失败熔断。"""

    from orchestration.client import ApiPolicyClient, EvaluateCall, ResilientPolicyClient
    from orchestration.errors import CircuitOpenError, PlatformUnavailableError

    dead = free_port()
    dead_url = f"http://{HOST}:{dead}"
    reset_workspace()
    task = controller_task("p8-outage", requirement="平台不可用时高风险路径必须停下")
    run = make_run("outage", task=task, author=controller_author(), base_url=dead_url)
    report = run.start()
    failure = report.failure.code.value if report.failure else None
    tool_calls = len(run.runner.requests)
    executions = [item for item in run.ledger() if item.get("kind") == "execution"]

    resilient = ResilientPolicyClient(
        ApiPolicyClient(dead_url, token=TOKEN, timeout=1.0), failure_threshold=3
    )
    failures = 0
    for index in range(3):
        call = EvaluateCall(
            request_id=f"p8-outage:{index}",
            context={"file": CONTROLLER, "layer": "controller", "language": "python"},
            principal={"subject": "orchestrator", "roles": ["developer"]},
        )
        try:
            resilient.evaluate(call)
        except PlatformUnavailableError:
            failures += 1
    opened = resilient.breaker.opened
    circuit_code = None
    try:
        resilient.evaluate(
            EvaluateCall(
                request_id="p8-outage:after",
                context={"file": CONTROLLER, "layer": "controller", "language": "python"},
                principal={"subject": "orchestrator", "roles": ["developer"]},
            )
        )
    except CircuitOpenError as error:
        circuit_code = error.code.value

    passed = (
        report.status.value == "blocked"
        and failure == "policy_unavailable"
        and tool_calls == 0
        and not executions
        and opened
        and circuit_code == "circuit_open"
    )
    return Scenario(
        "平台故障失败关闭",
        passed,
        f"{report.status.value}/{failure}，工具调用 {tool_calls} 次，熔断={opened}",
        {
            "status": report.status.value,
            "failure": failure,
            "tool_calls": tool_calls,
            "tool_executions": len(executions),
            "breaker": {
                "opened": opened,
                "consecutive_failures": resilient.breaker.consecutive_failures,
                "calls": resilient.breaker.calls,
            },
            "platform_failures": failures,
            "circuit_error": circuit_code,
        },
    )


def scenario_idempotent_action(api: "Api") -> Scenario:
    """同一个任务重跑：同一个动作不会被执行第二次（幂等跳过 + 台账唯一执行）。"""

    from orchestration.models import NodeId
    from orchestration.nodes import NODES, Change, ScriptedAuthor

    blocked = require_index()
    if blocked is not None:
        return Scenario("幂等：同一次动作不执行第二次", False, blocked.detail)

    reset_workspace()
    good_line = '"""正例：Controller 只依赖 Service，ARCH-001 不应命中。"""'
    marked_line = '"""正例：Controller 只依赖 Service，ARCH-001 不应命中（幂等场景）。"""'
    change = Change(path=CONTROLLER, summary="更新 controller 的模块说明", old=good_line,
                    replacement=marked_line)
    task = controller_task("p8-idempotent", requirement="同一个动作不执行第二次")
    run = make_run("idempotent", task=task, author=ScriptedAuthor([change]), base_url=api.base_url)
    first = run.start()
    action_id = run.runner.requests[0].action_id
    second = run.start()

    # 节点级重试：把状态指回 implementation，同一个幂等键必须直接跳过。
    retry_state = second.state.replace(stage=NodeId.IMPLEMENTATION)
    calls_before = len(run.runner.requests)
    retry = NODES[NodeId.IMPLEMENTATION](retry_state, run.assembly.node_context)
    retried_tool_calls = len(run.runner.requests) - calls_before
    executions = execution_count(run.ledger(), action_id)
    skipped = "幂等" in retry.detail or any("命中幂等键" in note for note in retry.state.notes)

    passed = (
        first.status.value == "completed"
        and second.status.value == "completed"
        and executions == 1
        and retried_tool_calls == 0
        and skipped
    )
    return Scenario(
        "幂等：同一次动作不执行第二次",
        passed,
        f"台账执行 {executions} 次，第二次 {second.status.value}，节点重试工具调用 "
        f"{retried_tool_calls} 次",
        {
            "action_id": action_id,
            "executions": executions,
            "first_status": first.status.value,
            "second_status": second.status.value,
            "second_resume_mode": second.resume_mode,
            "node_retry_tool_calls": retried_tool_calls,
            "node_retry_skipped": skipped,
            "tool_calls": len(run.runner.requests),
        },
    )


SCENARIOS: tuple[Callable[["Api"], Scenario], ...] = (
    scenario_end_to_end,
    scenario_engine_is_swappable,
    scenario_repair_limit,
    scenario_checkpoint_resume,
    scenario_rule_set_change,
    scenario_human_approval,
    scenario_platform_outage,
    scenario_idempotent_action,
)


# --------------------------------------------------------------------------- 入口


@dataclass
class Api:
    """在跑的场景共用的真实 Policy API：真端口、真租户、真规则集。"""

    base_url: str
    port: int
    runtime: Any
    server: Any
    index_reason: str = ""


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 8 编排闭环")
    parser.add_argument("--json", action="store_true", help="只打印结论 JSON")
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="NAME",
        help="只跑名字里包含该片段的场景（调试用，可重复）",
    )
    args = parser.parse_args(argv)
    selected = [
        item for item in SCENARIOS if not args.only or any(key in item.__name__ for key in args.only)
    ]

    started = time.monotonic()
    global INDEX_REASON
    index_ok, index_reason = ensure_index()
    INDEX_REASON = index_reason
    reset_workspace()
    port = free_port()
    config_path = build_api_config(port)

    from policy_api.testing import build_runtime

    # readiness 必须反映**当前**的规则集与索引：恢复时的兼容性判定读的就是它，
    # 默认 1s 的缓存会让"刚改完规则就恢复"看到旧哈希（也就看不到"规则集变了"）。
    runtime = build_runtime(config_path, root=REPO_ROOT, readiness_ttl_seconds=0.0)
    readiness = runtime.readiness(force=True)
    server = start_server(runtime, port)
    api = Api(base_url=f"http://{HOST}:{port}", port=port, runtime=runtime, server=server,
              index_reason=index_reason)

    scenarios: list[Scenario] = []
    try:
        for scenario in selected:
            if not index_ok:
                scenarios.append(
                    Scenario(
                        scenario.__name__,
                        False,
                        f"检索索引不可用：{index_reason}",
                        {"index": relative(INDEX)},
                    )
                )
                continue
            try:
                scenarios.append(scenario(api))
            except Exception as error:  # noqa: BLE001 - 场景自身崩了也算失败，并写出原因
                import traceback

                scenarios.append(
                    Scenario(
                        scenario.__name__,
                        False,
                        type(error).__name__ + ": " + str(error)[:200],
                        {"traceback": traceback.format_exc(limit=4)},
                    )
                )
    finally:
        server.should_exit = True
        time.sleep(0.2)

    elapsed = round(time.monotonic() - started, 1)
    payload = {
        "phase": 8,
        "workspace": relative(DEMO_ROOT),
        "result": "pass" if all(item.passed for item in scenarios) else "fail",
        "scenarios": [
            {"name": item.name, "passed": item.passed, "detail": item.detail, "facts": item.facts}
            for item in scenarios
        ],
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        for item in scenarios:
            mark = "PASS" if item.passed else "FAIL"
            print("[" + mark + "] " + item.name + ": " + item.detail)
        print(
            "result: "
            + payload["result"]
            + "  用时 "
            + str(elapsed)
            + "s  (证据: "
            + relative(RESULT)
            + ")"
        )
        if payload["result"] != "pass":
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
