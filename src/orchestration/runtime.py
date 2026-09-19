"""装配层：把"引擎 + 客户端 + 工具端口 + checkpoint"接成一个可运行的工作流。

显式装配，默认安全：

- `engine="auto"`：装了受支持的 LangGraph 就用它，否则用参考引擎——**报告里会如实写明**
  用的是哪一个（`RunReport.engine`），不假装跑的是 LangGraph；
- `engine="langgraph"`：不可用即 `EngineUnavailableError`，不静默回落；
- 平台客户端默认是 HTTP（Phase 7 的公开路由）；测试与闭环可以换成脚本化实现；
- 工具端口默认是 Phase 4 受控执行链的桥接；测试可以换成只记录的实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from .approvals import ApprovalGate
from .checkpoint import CheckpointStore, JsonCheckpointStore
from .client import ApiPolicyClient, PolicyClient, ResilientPolicyClient
from .engines import GraphEngine, ReferenceEngine, StepExecutor
from .errors import EngineUnavailableError
from .models import PlatformSnapshot, RunLimits
from .nodes import ChangeAuthor, NodeContext, TaskSpec
from .tools import PlatformToolRunner, ToolRunner

__all__ = [
    "Assembly",
    "OrchestrationConfig",
    "build_assembly",
    "registry_identity",
    "select_engine",
]


@dataclass(frozen=True)
class OrchestrationConfig:
    """一次部署的显式配置。路径都是显式的：不从环境变量或"当前目录"推断。"""

    workspace: Path
    checkpoint_dir: Path
    registry_path: Path
    audit_path: Path
    ledger_path: Path
    approvals_dir: Path
    approved_path: Optional[Path] = None
    api_base_url: Optional[str] = None
    api_token: Optional[str] = None
    tenant: Optional[str] = None
    engine: str = "auto"
    agent_version: str = "0.1.0"
    limits: RunLimits = field(default_factory=RunLimits)
    circuit_failure_threshold: int = 3

    def __post_init__(self) -> None:
        if self.engine not in ("auto", "reference", "langgraph"):
            raise EngineUnavailableError(f"未知的引擎选择 {self.engine!r}")


def registry_identity(
    registry_path: Path | str, approved_path: Optional[Path | str] = None
) -> Optional[str]:
    """工具 schema 的兼容性凭据：就是注册表的身份哈希（审核口径一致）。"""

    try:
        from enforcement.registry import load_registry

        loaded = load_registry(registry_path, approved_path=approved_path)
    except Exception:  # noqa: BLE001 - 读不出来就没有凭据（恢复时按"变了"处理更安全）
        return None
    return loaded.registry.identity


@dataclass
class Assembly:
    """装配结果：一次运行的引擎、执行器、节点上下文与兼容性凭据。"""

    engine: GraphEngine
    executor: StepExecutor
    node_context: NodeContext
    client: PolicyClient
    tool_runner: ToolRunner
    snapshot: PlatformSnapshot
    checkpoint_store: Optional[CheckpointStore]
    engine_name: str


def select_engine(name: str, *, executor: StepExecutor, clock=None) -> Tuple[GraphEngine, str]:
    """`auto` 优先 LangGraph；不可用就回落参考引擎，并把选择如实返回。"""

    kwargs: dict[str, Any] = {"executor": executor}
    if clock is not None:
        kwargs["clock"] = clock
    if name == "reference":
        return ReferenceEngine(**kwargs), "reference"
    from .langgraph_engine import LangGraphEngine

    if name == "langgraph":
        return LangGraphEngine(**kwargs), "langgraph"
    try:
        return LangGraphEngine(**kwargs), "langgraph"
    except EngineUnavailableError:
        return ReferenceEngine(**kwargs), "reference"


def build_assembly(
    config: OrchestrationConfig,
    *,
    task: TaskSpec,
    author: ChangeAuthor,
    client: Optional[PolicyClient] = None,
    tool_runner: Optional[ToolRunner] = None,
    checkpoint_store: Optional[CheckpointStore] = None,
    clock=None,
    router_fns: Optional[Mapping[str, Any]] = None,
) -> Assembly:
    """按配置装配。所有端口都可以注入（测试、闭环与真实部署共用同一条装配路径）。"""


    if client is None:
        if config.api_base_url is None or config.api_token is None:
            raise EngineUnavailableError(
                "没有可用的平台客户端：既没有注入 client，也没有声明 api_base_url / token"
            )
        client = ResilientPolicyClient(
            ApiPolicyClient(config.api_base_url, token=config.api_token),
            failure_threshold=config.circuit_failure_threshold,
        )
    if tool_runner is None:
        tool_runner = PlatformToolRunner(
            registry_path=config.registry_path,
            approved_path=config.approved_path,
            audit_path=config.audit_path,
            ledger_path=config.ledger_path,
            workspace=config.workspace,
            agent_version=config.agent_version,
            clock=clock,
        )
    store = checkpoint_store
    if store is None:
        store = JsonCheckpointStore(config.checkpoint_dir)

    # 当前平台的版本凭据：工具 schema 来自注册表身份，规则集/索引来自 readiness。
    # 拿不到就是 None —— 恢复时会按"变了"处理（重新评估），绝不沿用旧 allow。
    readiness = client.readiness()
    snapshot = PlatformSnapshot(
        tool_schema_hash=registry_identity(config.registry_path, config.approved_path),
        rule_set_hash=readiness.rule_set_hash,
        index_version=readiness.index_version,
    )
    node_context = NodeContext(
        task=task,
        client=client,
        runner=tool_runner,
        author=author,
        approvals=ApprovalGate(config.approvals_dir, clock=clock),
        workspace=config.workspace,
        clock=clock or node_context_default_clock(),
    )
    executor_kwargs: dict[str, Any] = {
        "node_context": node_context,
        "store": store,
        "compatibility": snapshot,
    }
    if clock is not None:
        executor_kwargs["clock"] = clock
    if router_fns is not None:
        executor_kwargs["router_fns"] = router_fns
    executor = StepExecutor(**executor_kwargs)
    engine, engine_name = select_engine(config.engine, executor=executor, clock=clock)
    executor.engine_name = engine_name
    return Assembly(
        engine=engine,
        executor=executor,
        node_context=node_context,
        client=client,
        tool_runner=tool_runner,
        snapshot=snapshot,
        checkpoint_store=store,
        engine_name=engine_name,
    )


def node_context_default_clock():
    import time

    return time.monotonic
