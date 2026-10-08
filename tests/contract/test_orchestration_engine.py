"""Phase 8 契约：两个引擎同语义、图定义自检、判定来源与依赖方向。

契约测试守的是**跨版本、跨实现**的承诺，所以这里的断言都很硬：

- `编排可替换` 不是口号：同一组场景分别跑参考引擎与 LangGraph 引擎，
  丢掉引擎名与耗时后报告必须**逐字节一致**——控制流只写了一份（StepExecutor），
  两个引擎只是驱动方式不同；
- 图定义是数据：`DEFAULT_SPEC.problems()` 必须为空，每个节点都要有出路，
  认不出来的路由标签是契约错误（失败关闭），PASS / FAIL 只由结构化 Decision 决定；
- 依赖方向必须可执行地断言：只有 `langgraph_engine` 能导入工作流框架，
  核心层从不导入 `orchestration`，编排层也不许碰策略内部实现；
- 编排协议版本是**自己的**，且绝不从阶段号推导；`policy_version` 与决策协议版本
  只能从 `policy.models` 取值（与 Phase 7 的 `API_SCHEMA_VERSION` 同一条纪律）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Tuple

import pytest
from pydantic import ValidationError

from conftest import REPO_ROOT

from policy import models as policy_models

from orchestration import models as orchestration_models
from orchestration.checkpoint import CHECKPOINT_SCHEMA_VERSION, JsonCheckpointStore
from orchestration.client import API_SCHEMA_VERSION, EvaluateCall, RetrieveCall, ValidateCall
from orchestration.engines import ReferenceEngine, StepExecutor
from orchestration.errors import CheckpointError, EngineUnavailableError, NodeContractError
from orchestration.langgraph_engine import LangGraphEngine, _load
from orchestration.graph import (
    DEFAULT_SPEC,
    END,
    ROUTERS,
    Edge,
    GraphSpec,
    Router,
    validation_outcome,
)
from orchestration.models import (
    STATE_SCHEMA_VERSION,
    SUPPORTED_STATE_SCHEMA_VERSIONS,
    Decision,
    FailureCode,
    GraphState,
    NodeId,
    PlatformSnapshot,
    RunLimits,
    RunStatus,
    StageStatus,
    ValidationSummary,
    empty_state,
)
from orchestration.nodes import NODES, Change

from orchestration_support import (
    ExecutingToolRunner,
    allow_outcome,
    build_assembly,
    graph_config,
    retrieval_ok,
    run_graph,
    scripted_client,
    step_executor,
    task_spec,
    validate_allow,
    validate_block,
    write_change,
)

pytestmark = pytest.mark.contract


# --------------------------------------------------------------------------- 引擎等价


@dataclass(frozen=True)
class Scenario:
    """一个状态机场景：平台脚本 + 候选改动 + 期望终态。两个引擎跑的是同一份。"""

    name: str
    status: RunStatus
    evaluate: Tuple[Any, ...]
    retrieve: Tuple[Any, ...]
    validate: Tuple[Any, ...]
    changes: Tuple[Change, ...]
    limits: RunLimits = field(
        default_factory=lambda: RunLimits(max_repair_rounds=2, max_tool_calls=8, max_node_runs=24)
    )

    def client(self):
        return scripted_client(
            evaluate=self.evaluate, retrieve=self.retrieve, validate=self.validate
        )

    def author(self):
        from orchestration.nodes import ScriptedAuthor

        return ScriptedAuthor(list(self.changes))

    def runner(self) -> ExecutingToolRunner:
        return ExecutingToolRunner()


SCENARIOS: Tuple[Scenario, ...] = (
    Scenario(
        name="happy-path",
        status=RunStatus.COMPLETED,
        evaluate=(allow_outcome(),),
        retrieve=(retrieval_ok(),),
        validate=(validate_allow(), validate_allow()),
        changes=(write_change(),),
    ),
    Scenario(
        name="validation-fail-repair-pass",
        status=RunStatus.COMPLETED,
        evaluate=(allow_outcome(), allow_outcome()),
        retrieve=(retrieval_ok(),),
        validate=(validate_block(), validate_allow(), validate_allow()),
        changes=(
            write_change(summary="第一次写入仍会失败"),
            write_change(summary="按 violation 修好的写入"),
        ),
    ),
    Scenario(
        name="repair-limit-reached",
        status=RunStatus.NEEDS_HUMAN,
        evaluate=(allow_outcome(), allow_outcome()),
        retrieve=(retrieval_ok(),),
        validate=(validate_block(), validate_block()),
        changes=(write_change(summary="第一次写入"), write_change(summary="第二次写入")),
        limits=RunLimits(max_repair_rounds=1, max_tool_calls=8, max_node_runs=24),
    ),
    Scenario(
        name="testing-failure-repair-pass",
        # 测试失败同样走 repair：repair 取的是**最近一次**失败（validation 通过之后就是
        # test_validation 的 violation），所以"测试失败 → 修复 → 重新验证与测试 → 收尾"
        # 能走完，而不是一条死分支。
        status=RunStatus.COMPLETED,
        evaluate=(allow_outcome(), allow_outcome()),
        retrieve=(retrieval_ok(),),
        validate=(validate_allow(), validate_block(), validate_allow(), validate_allow()),
        changes=(write_change(summary="第一次写入"), write_change(summary="修好的写入")),
    ),
)

_COMPARABLE_DROPPED = ("engine", "elapsed_ms", "checkpoints")


def _comparable(payload: dict) -> dict:
    """报告里只该有两处"随实现变化"的字段：引擎名、耗时与 checkpoint 计数。"""

    comparable = dict(payload)
    for key in _COMPARABLE_DROPPED:
        comparable.pop(key, None)
    return comparable


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.name)
def test_reference_and_langgraph_engines_agree(tmp_root_factory, scenario: Scenario) -> None:
    """同一场景跑两个引擎：报告（去掉引擎名 / 耗时 / checkpoint 计数）必须逐字节一致。"""

    payloads: dict[str, dict] = {}
    for engine in ("reference", "langgraph"):
        root = tmp_root_factory()
        run = run_graph(
            root,
            name=f"{scenario.name}-{engine}",
            task=task_spec("same-task"),
            engine=engine,
            client=scenario.client(),
            author=scenario.author(),
            runner=scenario.runner(),
            limits=scenario.limits,
        )
        assert run.report.engine == engine
        assert run.report.status is scenario.status, run.report.failure
        payloads[engine] = run.report.to_payload()

    reference = json.dumps(_comparable(payloads["reference"]), ensure_ascii=False, sort_keys=True)
    langgraph = json.dumps(_comparable(payloads["langgraph"]), ensure_ascii=False, sort_keys=True)
    assert reference == langgraph, "两个引擎的报告不一致：控制流语义被写成了两份"


def test_auto_engine_reports_the_engine_it_actually_used(tmp_root) -> None:
    """engine="auto" 必须如实写明用了哪个引擎：装了受支持的 LangGraph 就用它，报告不撒谎。"""

    from orchestration.langgraph_engine import langgraph_version
    from orchestration.runtime import select_engine

    executor = step_executor(tmp_root, name="auto")
    engine, name = select_engine("auto", executor=executor)
    assert name in ("langgraph", "reference")
    if langgraph_version() is not None:
        assert name == "langgraph"
    report = engine.run(task_id="auto-task", state=empty_state("auto-task"))
    assert report.engine == name


def test_limit_reached_is_derived_from_the_terminal_failure_code(tmp_root) -> None:
    """"因为撞上限而停下"是一类要能读出来的事实（这个字段此前永远是 False）。

    它只按终止失败码推导：节点与引擎都不必各自记得去置它，读报告的人也不必反推
    "needs_human 到底是预算不够还是审批缺失"。
    """

    limited = next(item for item in SCENARIOS if item.name == "repair-limit-reached")
    run = run_graph(
        tmp_root,
        name="limit-flag",
        task=task_spec("limit-flag-task"),
        client=limited.client(),
        author=limited.author(),
        runner=limited.runner(),
        limits=limited.limits,
    )
    assert run.report.failure is not None
    assert run.report.failure.code is FailureCode.LIMIT_REPAIR_ROUNDS
    assert run.report.limit_reached is True
    assert run.report.to_payload()["limit_reached"] is True

    # 反向：正常跑完的一轮不该被标成"撞了上限"
    happy = SCENARIOS[0]
    done = run_graph(
        tmp_root,
        name="limit-flag-ok",
        task=task_spec("limit-flag-ok-task"),
        client=happy.client(),
        author=happy.author(),
        runner=happy.runner(),
        limits=happy.limits,
    )
    assert done.report.status is RunStatus.COMPLETED
    assert done.report.limit_reached is False


def test_repair_limit_is_reported_with_its_failure_code(tmp_root) -> None:
    """上限击穿不是"静默停下"：报告里必须带失败码，状态是 needs_human。"""

    scenario = next(item for item in SCENARIOS if item.name == "repair-limit-reached")
    run = run_graph(
        tmp_root,
        name="repair-limit",
        task=task_spec("limit-task"),
        client=scenario.client(),
        author=scenario.author(),
        runner=scenario.runner(),
        limits=scenario.limits,
    )
    assert run.report.status is RunStatus.NEEDS_HUMAN
    assert run.report.failure is not None
    assert run.report.failure.code is FailureCode.LIMIT_REPAIR_ROUNDS
    assert run.report.state.counters.repair_rounds == 1


# --------------------------------------------------------------------------- 图定义


def test_graph_spec_self_check_and_every_node_has_a_way_out() -> None:
    """图定义自检为空，而且每个节点都必须有出路（静态边或条件分支），否则会走不下去。"""

    assert DEFAULT_SPEC.problems() == ()
    assert DEFAULT_SPEC.entry == NodeId.REQUIREMENT_ANALYSIS.value
    for node in NodeId:
        router = DEFAULT_SPEC.router_for(node.value)
        routed = () if router is None else tuple(router.targets.values())
        targets = DEFAULT_SPEC.outgoing(node.value) + routed
        assert targets, f"{node.value} 既没有静态边也没有条件分支"
        assert all(target in {item.value for item in NodeId} | {END} for target in targets)
    assert END in DEFAULT_SPEC.outgoing(NodeId.REVIEW.value)
    assert set(NODES) == set(NodeId)
    assert set(ROUTERS) == {router.name for router in DEFAULT_SPEC.routers}


def test_router_source_must_be_a_known_node() -> None:
    """Router.source 与 Edge.source 同一条口径：写错的源节点名（或 END）在构造期就拒绝。

    以前没有这条校验，于是一个拼错的源节点能构造出来、能通过 problems()，却永远命不中
    router_for——条件分支静默退化成静态路径（"验证失败 → 修复"那一支永远不触发）。
    """

    for bad in ("nonexistent_node", END):
        with pytest.raises(ValidationError):
            Router(name="validation_outcome", source=bad, targets={"pass": END})


def test_graph_problems_reject_contradictory_routers() -> None:
    """分支自相矛盾要报出来：同源两个分支、以及静态边与分支同挂一个节点。"""

    node = NodeId.VALIDATION.value
    duplicated = GraphSpec(
        entry=NodeId.REQUIREMENT_ANALYSIS.value,
        edges=(
            Edge(source=NodeId.REQUIREMENT_ANALYSIS.value, target=node),
            # 同一个节点上再挂一条静态边：route() 会优先走条件分支，这条边被静默忽略
            Edge(source=node, target=END),
        ),
        routers=(
            Router(name="validation_outcome", source=node, targets={"pass": END}),
            Router(name="validation_outcome", source=node, targets={"pass": END}),
        ),
    )
    issues = duplicated.problems()
    assert any("多个条件分支" in issue for issue in issues)
    # 静态边与分支同挂一个节点：route() 会走分支，静态边被静默忽略
    assert any("静态边会被忽略" in issue for issue in issues)

    # 正例一条都不误报：默认图定义没有任何矛盾
    assert DEFAULT_SPEC.problems() == ()


def test_graph_problems_reject_a_graph_that_cannot_finish() -> None:
    """自检要回答"这张图能不能跑完"：没有出口的环与孤立节点都必须报出来。

    只查"每个节点有没有出边"是不够的：`validation ⇄ repair` 满足它却永远不会结束
    （实测旧版本对这个环报出 6 条，全是别的节点没有出边，**没有一条**说它到不了终点），
    而这条自检在引擎构造期是契约错误（`BaseEngine.__init__`）——漏掉它等于让跑不完的图通过。
    """

    loop = GraphSpec(
        entry=NodeId.VALIDATION.value,
        edges=(
            Edge(source=NodeId.VALIDATION.value, target=NodeId.REPAIR.value),
            Edge(source=NodeId.REPAIR.value, target=NodeId.VALIDATION.value),
        ),
    )
    issues = loop.problems()
    assert any("到不了终点 end" in issue for issue in issues)
    assert any("从入口不可达" in issue and "requirement_analysis" in issue for issue in issues)

    # 反向不变量：真实的图定义一条都不误报（自检不能靠"多报"显得有用）
    assert DEFAULT_SPEC.problems() == ()


def test_an_incomplete_langgraph_is_unavailable_not_an_attribute_error(monkeypatch) -> None:
    """装了一半的 langgraph（StateGraph / GraphRecursionError 缺失）必须判"不可用"。

    旧实现把 `getattr` 放在守卫**外面**：AttributeError 会直接抛出去，而 select_engine("auto")
    只接 EngineUnavailableError——"自动回落到参考引擎"于是变成一句空话。
    GraphRecursionError 更关键：它以前缺省回落到 RuntimeError，于是图运行期间的**任何**
    RuntimeError 都会被 `except lg.GraphRecursionError` 翻译成 LIMIT_NODE_RUNS / NEEDS_HUMAN。
    """

    import sys
    import types

    graph_module = types.ModuleType("langgraph.graph")  # 没有 StateGraph
    errors_module = types.ModuleType("langgraph.errors")
    monkeypatch.setitem(sys.modules, "langgraph.graph", graph_module)
    monkeypatch.setitem(sys.modules, "langgraph.errors", errors_module)

    with pytest.raises(EngineUnavailableError):
        _load()

    # 补上 graph 侧的 API，但 errors 侧仍然没有 GraphRecursionError：同样判不可用
    graph_module.StateGraph = object
    graph_module.START = "__start__"
    graph_module.END = "__end__"

    with pytest.raises(EngineUnavailableError):
        _load()


def test_a_checkpointer_is_rejected_with_a_reason(tmp_root) -> None:
    """checkpointer 参数被**显式拒绝**，而不是"收下却跑不起来"。

    旧实现把它原样交给 compile，而 invoke 从不带 configurable.thread_id——第一次驱动就抛
    ValueError: Checkpointer requires ... thread_id…；就算补上 thread_id，它也会按自己的线程状态
    恢复，与本包"跨进程恢复只认自己的 checkpoint 存储"的策略分叉（两套状态源）。
    """

    executor = step_executor(tmp_root, name="checkpointer")

    with pytest.raises(NodeContractError) as error:
        LangGraphEngine(executor=executor, checkpointer=object())

    assert "checkpoint 存储" in str(error.value)
    assert "thread" in str(error.value)


def test_the_recursion_error_type_is_the_frameworks_own() -> None:
    """捕获的"递归上限"必须是框架自己的那个类，不能回落到 RuntimeError。

    回落成 RuntimeError 会让 _drive 里的 except 把图运行期间的**任何** RuntimeError
    （checkpoint 存储 I/O、langgraph 内部错误）都翻译成 LIMIT_NODE_RUNS / NEEDS_HUMAN——
    真失败被伪装成"预算不够"。
    """

    loaded = _load()

    assert loaded.GraphRecursionError is not RuntimeError
    assert issubclass(loaded.GraphRecursionError, Exception)


def test_a_node_runtime_error_is_an_invalid_state_not_a_budget_stop(tmp_root) -> None:
    """节点里冒出的 RuntimeError 由**执行器**翻译成 STATE_INVALID 的失败步。

    这条同时钉住两个边界：(1) 未分类异常不会逃出编排层（失败关闭，且状态里留下 type 与脱敏文本）；
    (2) 它不会被误报成 LIMIT_NODE_RUNS——后者只有"真的撞了节点上限"才配。
    """

    def exploding(state, context):  # noqa: ANN001, ANN202 - 只求抛出去
        raise RuntimeError("节点内部炸了（不是递归上限）")

    nodes = dict(NODES)
    nodes[NodeId.REQUIREMENT_ANALYSIS] = exploding
    executor = StepExecutor(
        node_context=step_executor(tmp_root, name="runtime-error").context,
        store=None,
        spec=DEFAULT_SPEC,
        nodes=nodes,
    )
    engine = LangGraphEngine(executor=executor)

    report = engine.run(task_id="runtime-error", state=empty_state("runtime-error"))

    assert report.failure is not None
    assert report.failure.code is FailureCode.STATE_INVALID
    assert report.status is RunStatus.FAILED
    assert "不是递归上限" in report.failure.detail


def test_engine_level_failure_keeps_progress_and_persists_it(tmp_root) -> None:
    """引擎级失败：失败状态长在"最后一步的状态"上，而且必须落盘。

    用入口状态收尾会同时丢掉两样东西：本轮的执行记录（steps 里看不到走过哪些节点、
    failure.node 指向入口阶段），以及 checkpoint 里的失败标记——下一次 prepare 会把
    那份状态读成 RUNNING 接着跑，已经产生副作用的节点会被重放。
    """

    scenario = SCENARIOS[0]
    task = task_spec("engine-failure")
    config = graph_config(tmp_root, name="engine-failure")
    assembly = build_assembly(
        config,
        task=task,
        author=scenario.author(),
        client=scenario.client(),
        tool_runner=scenario.runner(),
    )

    class ExplodingEngine(ReferenceEngine):
        """先真的走一步（执行器会把进度写进 checkpoint），再抛一个编排错误。"""

        def _drive(self, state: GraphState) -> GraphState:
            self.stepped = self.executor.step(state).state
            raise CheckpointError("注入的引擎级失败：用来验证收尾状态取自哪一份")

    engine = ExplodingEngine(executor=assembly.engine.executor)
    report = engine.run(
        task_id=task.task_id, state=empty_state(task.task_id, limits=config.limits)
    )

    # 1) 本轮的执行记录一条都不许丢
    assert engine.stepped.runs, "第一步应当已经写进 runs"
    assert report.steps, "引擎级失败也必须带上本轮走过的节点"
    # 2) failure.node 是"失败发生在哪个阶段"，不是入口阶段
    assert report.failure is not None
    assert report.failure.node == engine.stepped.stage
    assert report.failure.node != NodeId.REQUIREMENT_ANALYSIS
    # 3) 失败状态真的落盘：重新读 checkpoint 看得见失败
    record = JsonCheckpointStore(config.checkpoint_dir).load(task.task_id)
    persisted = GraphState.model_validate(dict(record.state))
    assert persisted.failure is not None
    assert persisted.failure.code is report.failure.code
    assert persisted.stage is report.failure.node


def test_unknown_router_label_is_a_contract_error(tmp_root) -> None:
    """认不出来的路由标签必须报错：绝不猜下一步。"""

    executor = step_executor(
        tmp_root,
        router_fns={"validation_outcome": lambda state: "nonsense"},
    )
    state = empty_state("task-1").replace(
        stage=NodeId.VALIDATION,
        validation=ValidationSummary(decision=Decision.ALLOW, request_id="task-1:validation:0"),
    )
    with pytest.raises(NodeContractError) as excinfo:
        executor.route(state, "nonsense")
    assert excinfo.value.code is FailureCode.NODE_CONTRACT_INVALID


def test_unknown_router_label_ends_the_step_in_failure(tmp_root, tmp_root_factory) -> None:
    """把同样的坏分支放进一次真实节点执行：终态是 FAILED，绝不是 completed。"""

    client = scripted_client(validate=(validate_allow(),))
    executor = step_executor(
        tmp_root,
        context=_context_with_client(tmp_root_factory(), client),
        router_fns={"validation_outcome": lambda state: "nonsense"},
    )
    state = empty_state("task-1").replace(stage=NodeId.VALIDATION)
    result = executor.step(state)
    assert result.terminal is True
    assert result.state.status is RunStatus.FAILED
    assert result.state.failure is not None
    assert result.state.failure.code is FailureCode.NODE_CONTRACT_INVALID


def _context_with_client(root: Path, client):
    from orchestration_support import node_context

    return node_context(root, client=client, name="contract-context")


@pytest.mark.parametrize(
    ("decision", "stage_status", "expected"),
    [
        (Decision.ALLOW, StageStatus.FAILED, NodeId.TESTING.value),
        (Decision.BLOCK, StageStatus.OK, NodeId.REPAIR.value),
    ],
)
def test_pass_fail_is_decided_only_by_the_structured_decision(
    tmp_root, decision: Decision, stage_status: StageStatus, expected: str
) -> None:
    """PASS / FAIL 只看结构化 Decision：节点自己写的 status、给的路由标签都不参与分支。"""

    executor = step_executor(tmp_root, router_fns=ROUTERS)
    summary = ValidationSummary(
        decision=decision, status=stage_status, request_id="task-1:validation:0"
    )
    state = empty_state("task-1").replace(stage=NodeId.VALIDATION, validation=summary)
    assert executor.route(state, "nonsense") == expected
    assert ROUTERS["validation_outcome"] is validation_outcome
    assert (summary.failing is True) == (decision is Decision.BLOCK)


def test_validation_router_without_a_decision_is_a_contract_error(tmp_root) -> None:
    """没有验证结果就求值分支 = 契约错误：不许把"没跑过"当成 PASS。"""

    executor = step_executor(tmp_root)
    state = empty_state("task-1").replace(stage=NodeId.VALIDATION)
    with pytest.raises(NodeContractError):
        executor.route(state, "pass")
    with pytest.raises(NodeContractError):
        executor.route(state, "fail")


def test_resume_path_refuses_the_arguments_it_used_to_ignore(tmp_root) -> None:
    """`config=` 是恢复路径：被静默丢掉的参数与默认 task id 都必须当场报错。

    为什么必须这样：旧实现把 `config` 之外的 `engine` / `limits` / `**overrides` 算出来后
    丢掉，调用方以为换了引擎或上限；更隐蔽的是 `task` 缺省——第一次运行用的是非默认 task id 时，
    这里会去查另一个 checkpoint，查不到就**静默**规划一次全新运行，调用方以为恢复成功。
    这一组用例只钉"拒绝"，不重复跑引擎：三种组合都在装配之前就失败。
    """

    config = graph_config(tmp_root, name="resume")

    with pytest.raises(ValueError, match="config="):
        run_graph(tmp_root, config=config, engine="langgraph", client=None, author=None, runner=None)
    with pytest.raises(ValueError, match="config="):
        run_graph(
            tmp_root,
            config=config,
            limits=RunLimits(max_repair_rounds=0),
            client=None,
            author=None,
            runner=None,
        )
    with pytest.raises(ValueError, match="task="):
        run_graph(tmp_root, config=config, client=None, author=None, runner=None)


# --------------------------------------------------------------------------- 依赖方向

CORE_LAYERS = ("policy", "retrieval", "validators", "enforcement", "policy_api", "adapters")
_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", re.MULTILINE)
# LangGraph 只能出现在 langgraph_engine.py 里：那里是**延迟导入**（模块级零副作用），
# 所以静态的 import 语句扫不到它——必须连 import_module("langgraph...") 这种动态写法一起扫。
_LANGGRAPH_RE = re.compile(
    r"(?:^\s*(?:from|import)\s+langgraph\b|import_module\(\s*[\"']langgraph)", re.MULTILINE
)


def _imports(path: Path) -> Tuple[str, ...]:
    return tuple(_IMPORT_RE.findall(path.read_text(encoding="utf-8")))


def _source_files(*directories: str) -> Tuple[Path, ...]:
    files: list[Path] = []
    for directory in directories:
        files.extend(sorted((REPO_ROOT / directory).rglob("*.py")))
    return tuple(files)


def _matches(module: str, needle: str) -> bool:
    return module == needle or module.startswith(needle + ".")


def test_only_the_langgraph_engine_imports_langgraph() -> None:
    """全仓库只有 src/orchestration/langgraph_engine.py 能导入工作流框架。"""

    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in _source_files("src")
        if _LANGGRAPH_RE.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == ["src/orchestration/langgraph_engine.py"]
    for path in _source_files(*[f"src/{layer}" for layer in CORE_LAYERS]):
        assert "langgraph" not in path.read_text(encoding="utf-8").lower(), path


def test_core_layers_never_import_the_orchestration_package() -> None:
    """核心层从不导入 orchestration：删掉整个编排包，平台必须照常独立运行。"""

    for layer in CORE_LAYERS:
        for path in _source_files(f"src/{layer}"):
            modules = _imports(path)
            assert not any(_matches(module, "orchestration") for module in modules), path


def test_orchestration_does_not_import_policy_internals() -> None:
    """编排层只消费公开协议：policy.models 可以，engine / loader / check 一律不许。"""

    forbidden = ("policy.engine", "policy.loader", "policy.check")
    files = _source_files("src/orchestration")
    assert files
    for path in files:
        modules = _imports(path)
        for module in modules:
            offenders = [needle for needle in forbidden if _matches(module, needle)]
            assert not offenders, f"{path.name} 导入了策略内部实现：{module}"
    # 边界不是"什么都不导入"：平台协议正是从核心取的。
    models_path = REPO_ROOT / "src" / "orchestration" / "models.py"
    assert any(_matches(module, "policy.models") for module in _imports(models_path))


def test_auto_falls_back_to_reference_and_never_mislabels_it(tmp_root, monkeypatch) -> None:
    """LangGraph 不可用时 `auto` 必须回落参考引擎，且报告里如实写 reference。

    AGENTS 第 35 条的落地：不可用即回落，但**不许把参考引擎报成 LangGraph**；
    显式 `engine="langgraph"` 相反——不可用就 EngineUnavailableError，不静默回落。
    受支持的环境里 `auto` 永远选 langgraph，所以这条回落分支只能靠注入不可用来覆盖：
    删掉 `select_engine` 里的 except，本用例必须变红。
    """

    from orchestration.engines import ReferenceEngine
    from orchestration.errors import EngineUnavailableError
    from orchestration.langgraph_engine import LangGraphEngine
    from orchestration.runtime import select_engine

    def unavailable(self, *args, **kwargs):
        raise EngineUnavailableError("langgraph 不可用（用例注入）")

    monkeypatch.setattr(LangGraphEngine, "__init__", unavailable)
    executor = step_executor(tmp_root, name="fallback")

    engine, name = select_engine("auto", executor=executor)
    assert name == "reference"
    assert isinstance(engine, ReferenceEngine)

    with pytest.raises(EngineUnavailableError):
        select_engine("langgraph", executor=executor)


def test_orchestration_protocol_versions_are_its_own() -> None:
    """编排状态协议 / 传输协议各有自己的版本，而且绝不从阶段号推导。"""

    # 台阶 3a（H1/H10）：状态载荷增了受控 reason 与证据通道 → 编排状态协议按自己的规则递增。
    assert STATE_SCHEMA_VERSION == "1.1"
    assert SUPPORTED_STATE_SCHEMA_VERSIONS == frozenset({STATE_SCHEMA_VERSION})
    assert CHECKPOINT_SCHEMA_VERSION == "1.0"
    assert API_SCHEMA_VERSION == "1.0"
    assert orchestration_models.STATE_SCHEMA_VERSION is STATE_SCHEMA_VERSION
    assert orchestration_models.empty_state.__module__ == "orchestration.models"

    source = (REPO_ROOT / "src" / "orchestration" / "models.py").read_text(encoding="utf-8")
    line = next(item for item in source.splitlines() if item.startswith("STATE_SCHEMA_VERSION"))
    assert '"1.1"' in line
    assert "phase" not in line.lower()
    assert "8" not in line.split("=", 1)[1]


def test_platform_snapshot_versions_come_from_the_core() -> None:
    """policy_version 与决策协议版本只能从 policy.models 取——本包不许自己算一个。"""

    snapshot = PlatformSnapshot()
    assert snapshot.policy_version == policy_models.POLICY_VERSION
    assert snapshot.decision_schema_version == policy_models.SCHEMA_VERSION
    assert snapshot.state_schema_version == orchestration_models.STATE_SCHEMA_VERSION
    fields = PlatformSnapshot.model_fields
    assert fields["policy_version"].default == policy_models.POLICY_VERSION
    assert fields["decision_schema_version"].default == policy_models.SCHEMA_VERSION


@pytest.mark.parametrize(
    "call",
    [
        EvaluateCall(
            request_id="evaluate-1",
            context={"file": "src/shop/order_controller.py"},
            principal={},
            idempotency_key="orchestration-action-1",
        ),
        RetrieveCall(
            request_id="retrieve-1",
            context={"file": "src/shop/order_controller.py"},
            principal={},
            idempotency_key="orchestration-action-1",
            query="policy",
        ),
        ValidateCall(
            request_id="validate-1",
            context={"file": "src/shop/order_controller.py"},
            principal={},
            idempotency_key="orchestration-action-1",
            target="src/shop/order_controller.py",
        ),
    ],
)
def test_policy_calls_never_send_orchestration_idempotency_key(call) -> None:
    """判定信封不复用编排动作键，避免大响应进入 API 幂等台账。"""

    assert "idempotency_key" not in call.envelope()
