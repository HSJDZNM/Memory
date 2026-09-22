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

from conftest import REPO_ROOT

from policy import models as policy_models

from orchestration import models as orchestration_models
from orchestration.checkpoint import CHECKPOINT_SCHEMA_VERSION
from orchestration.client import API_SCHEMA_VERSION, EvaluateCall, RetrieveCall, ValidateCall
from orchestration.errors import NodeContractError
from orchestration.graph import DEFAULT_SPEC, END, ROUTERS, validation_outcome
from orchestration.models import (
    STATE_SCHEMA_VERSION,
    SUPPORTED_STATE_SCHEMA_VERSIONS,
    Decision,
    FailureCode,
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

    assert STATE_SCHEMA_VERSION == "1.0"
    assert SUPPORTED_STATE_SCHEMA_VERSIONS == frozenset({STATE_SCHEMA_VERSION})
    assert CHECKPOINT_SCHEMA_VERSION == "1.0"
    assert API_SCHEMA_VERSION == "1.0"
    assert orchestration_models.STATE_SCHEMA_VERSION is STATE_SCHEMA_VERSION
    assert orchestration_models.empty_state.__module__ == "orchestration.models"

    source = (REPO_ROOT / "src" / "orchestration" / "models.py").read_text(encoding="utf-8")
    line = next(item for item in source.splitlines() if item.startswith("STATE_SCHEMA_VERSION"))
    assert '"1.0"' in line
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
