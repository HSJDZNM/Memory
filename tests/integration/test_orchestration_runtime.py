"""Phase 8 集成：真实 checkpoint、真实受控执行链、中断与恢复、平台故障。

单元与契约测试证明了状态机本身；这里证明它**接上真实东西之后还成立**：

- checkpoint 是真实文件（`JsonCheckpointStore` 落在 tmp 下）：每个节点后中断都能恢复，
  恢复后的决策路径与不中断执行**逐字段一致**；
- 副作用只发生一次：工具调用中途中断会留下"未结算的意图"，下一次运行停下交给人
  （`side_effect_unknown`），而不是重放；节点重试命中幂等键时也不会再动手；
- 规则集变了就重新评估：旧 trace 在**新判定发生之前**就被清掉（用 checkpoint 探针证明）；
- 平台故障一律停下：策略服务 / 检索 / 验证器不可用分别得到各自的失败码，
  熔断打开后连平台都不再调用；
- 最后用**仓库真实注册表**跑一次受控写入：工具真的执行、审计与台账真的落盘、
  同一个 action_id 第二次一定被拒。
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass, field
from typing import Any, Tuple

import pytest

from orchestration.checkpoint import JsonCheckpointStore, build_record
from orchestration.client import (
    ApiPolicyClient,
    EvaluateCall,
    ResilientPolicyClient,
)
from orchestration.errors import CircuitOpenError, PlatformUnavailableError
from orchestration.models import (
    Decision,
    FailureCode,
    GraphState,
    NodeId,
    RunLimits,
    RunStatus,
    StageStatus,
)
from orchestration.nodes import ScriptedAuthor

from orchestration_support import (
    CHANGED_RULE_SET_HASH,
    ExecutingToolRunner,
    FakeOpener,
    ROUTE_PATHS,
    RULE_SET_HASH,
    TARGET_PATH,
    allow_outcome,
    allow_policy,
    echo_decision_response,
    echo_retrieval_response,
    echo_validate_response,
    graph_config,
    platform_runner,
    readiness,
    readiness_response,
    retrieval_ok,
    retrieval_unavailable,
    run_graph,
    scripted_client,
    task_spec,
    tool_request,
    validate_allow,
    validate_block,
    workspace_factory,
    write_change,
)

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------- 测试替身


@dataclass
class InterruptingClient:
    """在指定路由上抛 `KeyboardInterrupt`：模拟"进程在节点之间被杀掉"。"""

    inner: Any
    route: str = "evaluate"

    def readiness(self):
        return self.inner.readiness()

    def retrieve(self, call):
        return self._run("retrieve", call)

    def validate(self, call):
        return self._run("validate", call)

    def evaluate(self, call):
        return self._run("evaluate", call)

    def _run(self, route: str, call):
        if route == self.route:
            raise KeyboardInterrupt("进程被中断（测试模拟）")
        return getattr(self.inner, route)(call)


@dataclass
class InterruptingRunner:
    """工具执行到一半被杀掉：调用被记录下来，副作用状态**未知**。"""

    calls: list = field(default_factory=list)

    def run(self, request):
        self.calls.append(request)
        raise KeyboardInterrupt("工具执行期间中断（测试模拟）")


@dataclass
class CheckpointProbe:
    """转发平台调用，并在调用发生的那一刻读 checkpoint。

    用它证明"旧 trace 是在**新判定之前**清掉的"，而不是"跑完之后反正会被覆盖"。
    """

    inner: Any
    store: JsonCheckpointStore
    task_id: str
    seen: list = field(default_factory=list)

    def readiness(self):
        return self.inner.readiness()

    def retrieve(self, call):
        return self._record("retrieve", call)

    def validate(self, call):
        return self._record("validate", call)

    def evaluate(self, call):
        return self._record("evaluate", call)

    def _record(self, route: str, call):
        record = self.store.load(self.task_id)
        self.seen.append((route, tuple(item["request_id"] for item in record.state["traces"])))
        return getattr(self.inner, route)(call)


def _happy_client(rule_set_hash: str = RULE_SET_HASH):
    """allow 三连的客户端；readiness 也带上同一个规则集哈希（恢复要比这一项）。"""

    return scripted_client(
        evaluate=(allow_outcome(rule_set_hash=rule_set_hash),),
        retrieve=(retrieval_ok(),),
        validate=(
            validate_allow(rule_set_hash=rule_set_hash),
            validate_allow(rule_set_hash=rule_set_hash),
        ),
        readiness_value=readiness(rule_set_hash=rule_set_hash),
    )


def _traces(report) -> Tuple[Tuple[str, str, str, Any, Any], ...]:
    return tuple(
        (item.node.value, item.request_id, item.decision.value, item.trace_id, item.rule_set_hash)
        for item in report.state.traces
    )


# --------------------------------------------------------------------------- 恢复


def test_resume_between_nodes_matches_the_uninterrupted_run(tmp_root_factory) -> None:
    """节点之间中断 → 恢复：resume_mode 是 resume，决策路径与不中断执行逐字段一致。"""

    root = tmp_root_factory()
    task = task_spec("resume-task")
    config = graph_config(root, name="resume")

    def author():
        """每次装配都要一个新的作者：同一个对象被两次运行共用会掩盖端口语义。"""

        return ScriptedAuthor([write_change()])

    with pytest.raises(KeyboardInterrupt):
        run_graph(
            root,
            name="resume",
            task=task,
            config=config,
            client=InterruptingClient(_happy_client()),
            author=author(),
            runner=ExecutingToolRunner(),
        )

    resumed = run_graph(
        root,
        name="resume",
        task=task,
        config=config,
        client=_happy_client(),
        author=author(),
        runner=ExecutingToolRunner(),
    )
    assert resumed.report.resume_mode == "resume"
    assert resumed.report.status is RunStatus.COMPLETED
    assert resumed.report.failure is None

    baseline = run_graph(
        tmp_root_factory(),
        name="resume",
        task=task,
        client=_happy_client(),
        author=author(),
        runner=ExecutingToolRunner(),
    )
    assert _traces(resumed.report)
    assert _traces(resumed.report) == _traces(baseline.report)
    # 节点执行记录也一致：恢复重跑的是"还没结算的那一轮"，不是重新数一遍。
    assert resumed.report.state.runs == baseline.report.state.runs


def test_resume_continues_past_the_previous_failure(tmp_root_factory) -> None:
    """上一轮的失败码不是工作流的进度：恢复后从失败的那个节点接着跑，而不是立刻又停下。"""

    root = tmp_root_factory()
    task = task_spec("continue-task")
    config = graph_config(root, name="continue")

    stalled = run_graph(
        root,
        name="continue",
        task=task,
        config=config,
        # 没有 evaluate 脚本：实施节点会以"平台不可用"停下，checkpoint 里留下失败码。
        client=scripted_client(retrieve=(retrieval_ok(),)),
        author=ScriptedAuthor([write_change()]),
        runner=ExecutingToolRunner(),
    )
    assert stalled.report.status is RunStatus.BLOCKED
    assert stalled.report.failure is not None
    assert stalled.report.failure.code is FailureCode.POLICY_UNAVAILABLE
    stalled_record = stalled.store.load(task.task_id)
    assert stalled_record.state["failure"]["code"] == FailureCode.POLICY_UNAVAILABLE.value
    assert stalled_record.state["status"] == RunStatus.BLOCKED.value

    resumed = run_graph(
        root,
        name="continue",
        task=task,
        config=config,
        client=_happy_client(),
        author=ScriptedAuthor([write_change()]),
        runner=ExecutingToolRunner(),
    )
    assert resumed.report.resume_mode == "resume"
    assert resumed.report.status is RunStatus.COMPLETED
    assert resumed.report.failure is None
    assert {step.node for step in resumed.report.steps} >= {
        "implementation",
        "validation",
        "testing",
        "review",
    }


def test_interruption_inside_a_tool_call_leaves_an_unknown_side_effect(
    tmp_root_factory,
) -> None:
    """工具执行中中断 → 未结算的意图落盘；下一次运行停下交给人，绝不重放。"""

    root = tmp_root_factory()
    task = task_spec("interrupt-task")
    config = graph_config(root, name="interrupt")
    first_runner = InterruptingRunner()

    with pytest.raises(KeyboardInterrupt):
        run_graph(
            root,
            name="interrupt",
            task=task,
            config=config,
            client=_happy_client(),
            author=ScriptedAuthor([write_change()]),
            runner=first_runner,
        )
    assert len(first_runner.calls) == 1

    record = JsonCheckpointStore(config.checkpoint_dir).load(task.task_id)
    assert record.stage == NodeId.IMPLEMENTATION.value
    assert record.state["runs"][-1]["status"] == StageStatus.PENDING.value
    assert record.state["runs"][-1]["label"] == "intent"

    second_runner = ExecutingToolRunner()
    resumed = run_graph(
        root,
        name="interrupt",
        task=task,
        config=config,
        # 脚本刻意留空：只要节点还敢问平台，这次运行就会以"脚本用尽"失败，
        # 而正确行为是根本不问——因为副作用状态未知时不许继续。
        client=scripted_client(),
        author=ScriptedAuthor([write_change()]),
        runner=second_runner,
    )
    assert resumed.report.resume_mode == "resume"
    assert resumed.report.status is RunStatus.NEEDS_HUMAN
    assert resumed.report.failure is not None
    assert resumed.report.failure.code is FailureCode.SIDE_EFFECT_UNKNOWN
    assert second_runner.calls == []
    assert any("未结算" in note for note in resumed.report.state.notes)


def test_retry_of_a_completed_node_does_not_repeat_the_side_effect(tmp_root_factory) -> None:
    """把阶段拨回已经完成过的节点：命中幂等键 → 跳过，副作用只有一次。"""

    root = tmp_root_factory()
    task = task_spec("rewind-task")
    config = graph_config(root, name="rewind")
    runner = ExecutingToolRunner()

    first = run_graph(
        root,
        name="rewind",
        task=task,
        config=config,
        client=_happy_client(),
        author=ScriptedAuthor([write_change()]),
        runner=runner,
    )
    assert first.report.status is RunStatus.COMPLETED
    assert len(runner.calls) == 1

    record = first.store.load(task.task_id)
    rewound = GraphState.model_validate(dict(record.state)).replace(
        stage=NodeId.IMPLEMENTATION, status=RunStatus.RUNNING
    )
    first.store.save(
        build_record(
            rewound,
            engine="reference",
            sequence=record.sequence + 1,
            compatibility=record.compatibility,
        )
    )

    second = run_graph(
        root,
        name="rewind",
        task=task,
        config=config,
        # 不提供 evaluate 脚本：真去问平台就会失败，而正确行为是根本不问。
        client=scripted_client(validate=(validate_allow(), validate_allow())),
        author=ScriptedAuthor([write_change()]),
        runner=runner,
    )
    assert second.report.resume_mode == "resume"
    assert second.report.status is RunStatus.COMPLETED
    assert len(runner.calls) == 1
    assert any("幂等" in note for note in second.report.state.notes)


def test_rule_set_change_between_runs_revalidates(tmp_root_factory) -> None:
    """规则集变了 → resume_mode 是 revalidate，旧 trace 在新判定之前就没了。"""

    root = tmp_root_factory()
    task = task_spec("revalidate-task")
    config = graph_config(root, name="revalidate")
    runner = ExecutingToolRunner()

    first = run_graph(
        root,
        name="revalidate",
        task=task,
        config=config,
        client=_happy_client(RULE_SET_HASH),
        author=ScriptedAuthor([write_change()]),
        runner=runner,
    )
    assert first.report.status is RunStatus.COMPLETED
    assert {item.rule_set_hash for item in first.report.state.traces} == {RULE_SET_HASH}

    probe = CheckpointProbe(
        inner=_happy_client(CHANGED_RULE_SET_HASH),
        store=JsonCheckpointStore(config.checkpoint_dir),
        task_id=task.task_id,
    )
    second = run_graph(
        root,
        name="revalidate",
        task=task,
        config=config,
        client=probe,
        author=ScriptedAuthor([write_change()]),
        runner=runner,
    )
    assert second.report.resume_mode == "revalidate"
    assert second.report.status is RunStatus.COMPLETED
    # 第一次平台调用（检索）发生时，checkpoint 里的 trace 已经是空的。
    assert probe.seen[0] == ("retrieve", ())
    assert {item.rule_set_hash for item in second.report.state.traces} == {CHANGED_RULE_SET_HASH}
    assert RULE_SET_HASH not in json.dumps(second.report.to_payload(), ensure_ascii=False)
    # 计数器与已完成的节点记录接着数/留着：恢复不是"重新开始"。
    assert second.report.state.counters.node_runs > first.report.state.counters.node_runs
    assert len(runner.calls) == 1


def test_repair_limit_ends_in_needs_human_and_is_persisted(tmp_root_factory) -> None:
    """repair 次数用尽 → needs_human + limit_repair_rounds，而且这个终态已经落盘。"""

    root = tmp_root_factory()
    task = task_spec("limit-task")
    client = scripted_client(
        evaluate=(allow_outcome(), allow_outcome()),
        retrieve=(retrieval_ok(),),
        validate=(validate_block(), validate_block()),
    )
    run = run_graph(
        root,
        name="limit",
        task=task,
        client=client,
        author=ScriptedAuthor([write_change(), write_change(summary="第二次写入")]),
        runner=ExecutingToolRunner(),
        limits=RunLimits(max_repair_rounds=1, max_tool_calls=8, max_node_runs=24),
    )
    assert run.report.status is RunStatus.NEEDS_HUMAN
    assert run.report.failure is not None
    assert run.report.failure.code is FailureCode.LIMIT_REPAIR_ROUNDS
    assert run.report.state.counters.repair_rounds == 1
    assert run.report.state.counters.tool_calls == 2

    record = run.store.load(task.task_id)
    assert record.state["status"] == RunStatus.NEEDS_HUMAN.value
    assert record.state["failure"]["code"] == FailureCode.LIMIT_REPAIR_ROUNDS.value


# --------------------------------------------------------------------------- 平台故障


def _failing_client(kind: str):
    if kind == "policy-api-down":
        return scripted_client(
            evaluate=(
                PlatformUnavailableError("Policy API 不可达", code=FailureCode.POLICY_UNAVAILABLE),
            ),
            retrieve=(retrieval_ok(),),
        )
    if kind == "retrieval-down":
        return scripted_client(evaluate=(allow_outcome(),), retrieve=(retrieval_unavailable(),))
    if kind == "validator-down":
        return scripted_client(
            evaluate=(allow_outcome(),),
            retrieve=(retrieval_ok(),),
            validate=(
                PlatformUnavailableError("验证器不可用", code=FailureCode.VALIDATOR_UNAVAILABLE),
            ),
        )
    raise AssertionError(f"未知的故障类型：{kind}")


@pytest.mark.parametrize(
    ("kind", "expected_code", "expected_tool_calls"),
    [
        ("policy-api-down", FailureCode.POLICY_UNAVAILABLE, 0),
        ("retrieval-down", FailureCode.KNOWLEDGE_UNAVAILABLE, 0),
        ("validator-down", FailureCode.VALIDATOR_UNAVAILABLE, 1),
    ],
)
def test_platform_failures_stop_the_run(
    tmp_root_factory, kind: str, expected_code: FailureCode, expected_tool_calls: int
) -> None:
    """平台不可用一律 blocked，而且失败码能区分"谁不可用"——绝不悄悄继续。"""

    root = tmp_root_factory()
    runner = ExecutingToolRunner()
    run = run_graph(
        root,
        name=kind,
        task=task_spec(f"{kind}-task"),
        client=_failing_client(kind),
        author=ScriptedAuthor([write_change()]),
        runner=runner,
    )
    assert run.report.status is RunStatus.BLOCKED
    assert run.report.failure is not None
    assert run.report.failure.code is expected_code
    assert len(runner.calls) == expected_tool_calls


def test_validate_without_a_decision_blocks_the_run_over_the_real_client(tmp_root) -> None:
    """HTTP 形状的"没有决策"：传输层成功、协议层缺决策，必须 blocked 而不是 PASS。"""

    opener = FakeOpener(
        {
            ROUTE_PATHS["readiness"]: readiness_response(),
            ROUTE_PATHS["evaluate"]: echo_decision_response(),
            ROUTE_PATHS["retrieve"]: echo_retrieval_response(),
            ROUTE_PATHS["validate"]: echo_validate_response(drop_decision=True),
        }
    )
    client = ApiPolicyClient(
        "http://127.0.0.1:9", token="test-token", opener=opener, timeout=2.0
    )
    run = run_graph(
        tmp_root,
        name="http-validate",
        task=task_spec("http-validate-task", trace_id="trace-http"),
        client=client,
        author=ScriptedAuthor([write_change()]),
        runner=ExecutingToolRunner(),
    )
    assert run.report.status is RunStatus.BLOCKED
    assert run.report.failure is not None
    assert run.report.failure.code is FailureCode.VALIDATOR_UNAVAILABLE
    assert opener.paths() == (
        ROUTE_PATHS["readiness"],
        ROUTE_PATHS["retrieve"],
        ROUTE_PATHS["evaluate"],
        ROUTE_PATHS["validate"],
    )


def test_api_client_against_an_unused_port_fails_closed() -> None:
    """真实 socket、端口上没有服务：显式不可用 + 版本凭据"不知道"，绝不返回 allow。"""

    client = ApiPolicyClient(f"http://127.0.0.1:{_closed_port()}", token="test-token", timeout=2.0)
    with pytest.raises(PlatformUnavailableError) as excinfo:
        client.evaluate(
            EvaluateCall(request_id="req-1", context={"file": TARGET_PATH}, principal={})
        )
    assert excinfo.value.code is FailureCode.POLICY_UNAVAILABLE
    readiness_value = client.readiness()
    assert readiness_value.ready is False
    assert readiness_value.state == "unknown"
    assert readiness_value.rule_set_hash is None
    assert readiness_value.index_version is None


def _closed_port() -> int:
    """拿一个刚被释放的本地端口：连上去必然失败，而且不会碰到任何真实服务。"""

    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", 0))
        except OSError:  # 受限环境不允许 bind：退回 discard 端口，仍然是"没有服务"
            return 9
        return int(probe.getsockname()[1])


def test_resilient_client_opens_the_breaker_and_stops_calling_the_platform() -> None:
    """连续失败到阈值 → 熔断打开；打开期间**不调用平台**，直接失败关闭。"""

    inner = scripted_client(
        evaluate=(
            PlatformUnavailableError("平台不可达"),
            PlatformUnavailableError("平台不可达"),
            allow_outcome(),
        )
    )
    client = ResilientPolicyClient(inner, failure_threshold=2)
    call = EvaluateCall(request_id="req-1", context={"file": TARGET_PATH}, principal={})

    for _ in range(2):
        with pytest.raises(PlatformUnavailableError):
            client.evaluate(call)
    assert client.breaker.opened is True
    assert len(inner.calls) == 2

    with pytest.raises(CircuitOpenError) as excinfo:
        client.evaluate(call)
    assert excinfo.value.code is FailureCode.CIRCUIT_OPEN
    assert len(inner.calls) == 2, "熔断打开后不允许再调用平台"

    with pytest.raises(CircuitOpenError):
        client.breaker.reset()
    client.breaker.reset(authorised=True)
    assert client.evaluate(call).decision is Decision.ALLOW
    assert len(inner.calls) == 3


# --------------------------------------------------------------------------- 真实受控执行链


def test_end_to_end_write_through_the_real_tool_registry(tmp_root) -> None:
    """真实注册表 + 真实审计/台账：工具真的执行，重复的 action_id 一定被拒。"""

    workspace = workspace_factory(tmp_root, name="workspace")
    runner = platform_runner(tmp_root, workspace=workspace, name="platform")
    run = run_graph(
        tmp_root,
        name="e2e",
        task=task_spec("e2e-task"),
        client=scripted_client(
            evaluate=(allow_outcome(validation=allow_policy()),),
            retrieve=(retrieval_ok(),),
            validate=(validate_allow(), validate_allow()),
        ),
        author=ScriptedAuthor([write_change()]),
        runner=runner,
        workspace=workspace,
    )
    assert run.report.status is RunStatus.COMPLETED, run.report.failure
    written = workspace / TARGET_PATH
    assert "编排层改写过的版本" in written.read_text(encoding="utf-8")

    audit = tmp_root / "platform" / "audit.jsonl"
    ledger = tmp_root / "platform" / "ledger.jsonl"
    assert audit.is_file() and audit.read_text(encoding="utf-8").strip()
    assert ledger.is_file() and ledger.read_text(encoding="utf-8").strip()
    assert TARGET_PATH in audit.read_text(encoding="utf-8")

    # 同一个 action_id 第二次：平台侧（台账 + 审计链）拦住，返回"未执行"的结论。
    request = tool_request(
        action_id="duplicate-action-1",
        request_id="duplicate-request-1",
        params={"file_path": TARGET_PATH, "content": '"""第二次写入：必须被拒。"""\n'},
        policy=allow_policy(request_id="duplicate-request-1"),
        workspace=workspace,
    )
    first = runner.run(request)
    before = written.read_text(encoding="utf-8")
    second = runner.run(request)
    assert first.status == "executed"
    assert first.executed is True
    assert second.executed is False
    assert second.status == "denied"
    assert second.reason_code == "action_replay"
    assert written.read_text(encoding="utf-8") == before
