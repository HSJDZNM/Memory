"""Phase 8 对抗：伪造审批、恢复绕过、未知分支、工具异常、trace 断裂与密钥不留痕。

这里问的都是同一个问题的不同形状：**出错时会不会悄悄放行？**

- 审批：只有与**平台口径 action_hash**（覆盖参数、主体、工具 schema、trace）绑定的
  有效记录才能解锁工具；伪造的哈希 / 主体 / 过期 / 无审批权 / 干脆没有文件一律拒绝，而且
  拒绝发生在调用工具**之前**；
- 恢复：`needs_human` 不是"通过"，恢复会重新走一遍门禁——补上合法审批才放行，
  没有就继续失败关闭；
- 分支：未知节点、未知路由标签、非 `NodeOutcome` 的返回值都是失败终态，绝不是 completed；
- 工具异常：runner 抛异常时终态是 failed 且带稳定失败码，绝不写一份"没有失败"的报告；
- trace：平台没有回声 trace 就是传播中断（`TraceError`），宁可停下；
- 密钥：需求正文、文件正文与凭据都不进 checkpoint，也不进报告载荷。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any

import pytest

from orchestration.client import ApiPolicyClient, EvaluateCall
from orchestration.engines import ReferenceEngine, StepExecutor
from orchestration.errors import TraceError
from orchestration.models import (
    FailureCode,
    NodeId,
    RunStatus,
    StageStatus,
    empty_state,
)
from orchestration.nodes import ScriptedAuthor

from orchestration_support import (
    ROUTE_PATHS,
    RULE_SET_HASH,
    ExecutingToolRunner,
    FakeOpener,
    action_key,
    allow_outcome,
    allow_policy,
    approval_file,
    echo_decision_response,
    echo_retrieval_response,
    echo_validate_response,
    graph_config,
    node_context,
    platform_runner,
    readiness,
    readiness_response,
    retrieval_ok,
    run_graph,
    scripted_client,
    step_executor,
    task_spec,
    validate_allow,
    workspace_factory,
    write_change,
)

pytestmark = pytest.mark.security


# --------------------------------------------------------------------------- 测试替身


@dataclass
class SpyToolRunner:
    """把 binding / run 转发给真实 PlatformToolRunner，同时留痕。

    两件事同时要：审批必须绑**平台口径**的 action_hash（所以 binding 不能造假），
    又要能断言"工具根本没被调用"（所以调用要被记录下来）。
    """

    inner: Any
    calls: list = field(default_factory=list)
    bindings: list = field(default_factory=list)

    def binding(self, request):
        self.bindings.append(request)
        return self.inner.binding(request)

    def run(self, request):
        self.calls.append(request)
        return self.inner.run(request)


@dataclass
class RaisingRunner:
    """run() 直接抛异常：模拟驱动崩溃、审计不可写这类"平台侧炸了"。"""

    calls: list = field(default_factory=list)

    def binding(self, request):
        return None

    def run(self, request):
        self.calls.append(request)
        raise RuntimeError("驱动崩溃（测试模拟）")


def _approval_client(*, rule_set_hash: str = RULE_SET_HASH):
    """平台回答 allow 但要求人工审批：节点必须去门禁要一份绑定当前动作的审批。"""

    return scripted_client(
        evaluate=(
            allow_outcome(
                required_action="approval",
                validation=allow_policy(),
                rule_set_hash=rule_set_hash,
            ),
        ),
        retrieve=(retrieval_ok(),),
        validate=(validate_allow(), validate_allow()),
        readiness_value=readiness(rule_set_hash=rule_set_hash),
    )


def _signature_for(kind: str, binding) -> Any:
    """按类型给出要写进收件箱的审批参数；None 表示"什么都不写"。"""

    base = {
        "action_hash": binding.action_hash,
        "action_id": binding.action_id,
        "tool_id": binding.tool_id,
        "subject": binding.subject,
    }
    if kind == "signed":
        return base
    if kind == "missing-file":
        return None
    if kind == "wrong-action-hash":
        return {**base, "action_hash": "sha256:" + "0" * 64}
    if kind == "wrong-subject":
        return {**base, "subject": "someone-else"}
    if kind == "wrong-action-id":
        return {**base, "action_id": f"{binding.action_id}-forged"}
    if kind == "expired":
        return {**base, "ttl_seconds": -10, "granted_offset_seconds": -100}
    if kind == "no-approval-role":
        return {**base, "roles": ("developer",)}
    raise AssertionError(f"未知的审批类型：{kind}")


# --------------------------------------------------------------------------- 审批


_APPROVAL_CASES = (
    pytest.param("signed", RunStatus.COMPLETED, None, id="valid-approval-unlocks"),
    pytest.param(
        "missing-file", RunStatus.NEEDS_HUMAN, FailureCode.APPROVAL_MISSING, id="no-approval-file"
    ),
    pytest.param(
        "wrong-action-hash",
        RunStatus.NEEDS_HUMAN,
        FailureCode.APPROVAL_PARAM_MISMATCH,
        id="forged-action-hash",
    ),
    pytest.param(
        "wrong-action-id",
        RunStatus.NEEDS_HUMAN,
        FailureCode.APPROVAL_PARAM_MISMATCH,
        id="forged-action-id",
    ),
    pytest.param(
        "wrong-subject",
        RunStatus.NEEDS_HUMAN,
        FailureCode.APPROVAL_SUBJECT_MISMATCH,
        id="forged-subject",
    ),
    pytest.param("expired", RunStatus.NEEDS_HUMAN, FailureCode.APPROVAL_EXPIRED, id="expired"),
    pytest.param(
        "no-approval-role",
        RunStatus.NEEDS_HUMAN,
        FailureCode.APPROVAL_MISSING,
        id="approver-without-authority",
    ),
)


@pytest.mark.parametrize(("kind", "expected_status", "expected_code"), _APPROVAL_CASES)
def test_forged_approval_never_unlocks_the_tool(
    tmp_root_factory, kind: str, expected_status: RunStatus, expected_code
) -> None:
    """审批必须绑平台口径的 action_hash：伪造 / 过期 / 越权 / 缺失一律在动手之前被拒。"""

    root = tmp_root_factory()
    workspace = workspace_factory(root, name="workspace")
    inbox = root / "inbox"
    runner = SpyToolRunner(platform_runner(root, workspace=workspace, name="platform"))
    config = graph_config(root, name="approval", workspace=workspace, approvals_dir=inbox)
    task = task_spec("approval-task")
    change = write_change()
    target = workspace / change.path
    before = target.read_text(encoding="utf-8")

    first = run_graph(
        root,
        name="approval",
        task=task,
        config=config,
        client=_approval_client(),
        author=ScriptedAuthor([change]),
        runner=runner,
    )
    assert first.report.status is RunStatus.NEEDS_HUMAN
    assert first.report.failure is not None
    assert first.report.failure.code is FailureCode.APPROVAL_MISSING
    assert runner.calls == [], "没有审批就不许调用工具"
    assert target.read_text(encoding="utf-8") == before

    # 节点在要审批之前算出的**平台口径绑定**：人类据此签发（或伪造）审批。
    assert len(runner.bindings) == 1
    binding = runner.inner.binding(runner.bindings[0])
    assert binding.action_id == action_key(task.task_id, change)
    assert binding.subject == "local-user"
    assert binding.action_hash and binding.action_hash != binding.action_id

    signature = _signature_for(kind, binding)
    if signature is not None:
        approval_file(inbox / "approval.json", **signature)

    second = run_graph(
        root,
        name="approval",
        task=task,
        config=config,
        client=_approval_client(),
        author=ScriptedAuthor([change]),
        runner=runner,
    )
    assert second.report.resume_mode == "resume"
    assert second.report.status is expected_status, second.report.failure

    if expected_status is RunStatus.COMPLETED:
        assert second.report.failure is None
        assert len(runner.calls) == 1, "合法审批必须真的解锁工具"
        assert "编排层改写过的版本" in target.read_text(encoding="utf-8")
        assert second.report.state.approvals, "审批使用必须记进状态"
    else:
        assert second.report.failure is not None
        assert second.report.failure.code is expected_code
        assert runner.calls == [], "伪造的审批绝不能让工具跑起来"
        assert target.read_text(encoding="utf-8") == before


def test_approval_inbox_picks_the_record_bound_to_this_action(tmp_root_factory) -> None:
    """收件箱里可以有多份审批：被挑中的必须是**当前 action_id** 的那一份。

    否则失败码会退化成笼统的"没有审批"（按哈希挑），或者错报成别人的参数漂移（按文件名挑），
    人也就无从知道该去修哪一份记录。
    """

    root = tmp_root_factory()
    workspace = workspace_factory(root, name="workspace")
    inbox = root / "inbox"
    runner = SpyToolRunner(platform_runner(root, workspace=workspace, name="platform"))
    config = graph_config(root, name="inbox", workspace=workspace, approvals_dir=inbox)
    task = task_spec("inbox-task")
    change = write_change()

    run_graph(
        root,
        name="inbox",
        task=task,
        config=config,
        client=_approval_client(),
        author=ScriptedAuthor([change]),
        runner=runner,
    )
    binding = runner.inner.binding(runner.bindings[0])

    # 文件名排序在前的那份属于**别的动作**；当前动作的那份主体不对。
    approval_file(
        inbox / "01-other-action.json",
        action_hash="sha256:" + "2" * 64,
        action_id="another-task:0:deadbeefdeadbeef",
        subject=binding.subject,
    )
    approval_file(
        inbox / "02-this-action.json",
        action_hash=binding.action_hash,
        action_id=binding.action_id,
        tool_id=binding.tool_id,
        subject="someone-else",
    )

    second = run_graph(
        root,
        name="inbox",
        task=task,
        config=config,
        client=_approval_client(),
        author=ScriptedAuthor([change]),
        runner=runner,
    )
    assert second.report.status is RunStatus.NEEDS_HUMAN
    assert second.report.failure is not None
    assert second.report.failure.code is FailureCode.APPROVAL_SUBJECT_MISMATCH
    assert runner.calls == []


def test_resume_does_not_bypass_the_approval_gate(tmp_root_factory) -> None:
    """恢复会重新走门禁：过期审批不能靠"再来一次"复活，补上合法审批才放行。"""

    root = tmp_root_factory()
    workspace = workspace_factory(root, name="workspace")
    inbox = root / "inbox"
    runner = SpyToolRunner(platform_runner(root, workspace=workspace, name="platform"))
    config = graph_config(root, name="resume-approval", workspace=workspace, approvals_dir=inbox)
    task = task_spec("resume-approval-task")
    change = write_change()
    target = workspace / change.path
    before = target.read_text(encoding="utf-8")

    first = run_graph(
        root,
        name="resume-approval",
        task=task,
        config=config,
        client=_approval_client(),
        author=ScriptedAuthor([change]),
        runner=runner,
    )
    binding = runner.inner.binding(runner.bindings[0])

    # 1) 过期审批：拒绝。
    approval_file(
        inbox / "approval.json",
        action_hash=binding.action_hash,
        action_id=binding.action_id,
        tool_id=binding.tool_id,
        subject=binding.subject,
        ttl_seconds=-10,
        granted_offset_seconds=-100,
    )
    expired = run_graph(
        root,
        name="resume-approval",
        task=task,
        config=config,
        client=_approval_client(),
        author=ScriptedAuthor([change]),
        runner=runner,
    )
    assert expired.report.resume_mode == "resume"
    assert expired.report.status is RunStatus.NEEDS_HUMAN
    assert expired.report.failure is not None
    assert expired.report.failure.code is FailureCode.APPROVAL_EXPIRED
    assert runner.calls == []
    assert target.read_text(encoding="utf-8") == before

    # 2) 参数漂移：换成别的动作的审批同样拒绝（批准的是"那一次动作"，不是"这个节点"）。
    approval_file(
        inbox / "approval.json",
        action_hash="sha256:" + "1" * 64,
        action_id=binding.action_id,
        tool_id=binding.tool_id,
        subject=binding.subject,
    )
    drifted = run_graph(
        root,
        name="resume-approval",
        task=task,
        config=config,
        client=_approval_client(),
        author=ScriptedAuthor([change]),
        runner=runner,
    )
    assert drifted.report.status is RunStatus.NEEDS_HUMAN
    assert drifted.report.failure is not None
    assert drifted.report.failure.code is FailureCode.APPROVAL_PARAM_MISMATCH
    assert runner.calls == []

    # 3) 补上绑定当前动作的审批：这一次才真的动手。
    approval_file(
        inbox / "approval.json",
        action_hash=binding.action_hash,
        action_id=binding.action_id,
        tool_id=binding.tool_id,
        subject=binding.subject,
    )
    granted = run_graph(
        root,
        name="resume-approval",
        task=task,
        config=config,
        client=_approval_client(),
        author=ScriptedAuthor([change]),
        runner=runner,
    )
    assert granted.report.status is RunStatus.COMPLETED, granted.report.failure
    assert len(runner.calls) == 1
    assert "编排层改写过的版本" in target.read_text(encoding="utf-8")

    # 4) 审批的账记得清清楚楚：记的是**平台口径的 action_hash**，而且单次额度已经用完。
    assert first.report.status is RunStatus.NEEDS_HUMAN
    assert first.report.failure is not None
    assert first.report.failure.code is FailureCode.APPROVAL_MISSING
    uses = granted.report.state.approvals
    assert [item.uses for item in uses] == [1]
    assert uses[0].action_hash == binding.action_hash


def test_approval_binding_includes_the_trace(tmp_root_factory) -> None:
    """trace 也是 action_hash 的一部分：换 trace 就是换了一次动作，旧审批不再有效。"""

    root = tmp_root_factory()
    workspace = workspace_factory(root, name="workspace")
    runner = SpyToolRunner(platform_runner(root, workspace=workspace, name="platform"))
    task = task_spec("trace-binding-task", trace_id="trace-one")
    change = write_change()
    config = graph_config(
        root, name="trace-binding", workspace=workspace, approvals_dir=root / "inbox"
    )
    first = run_graph(
        root,
        name="trace-binding",
        task=task,
        config=config,
        client=_approval_client(),
        author=ScriptedAuthor([change]),
        runner=runner,
    )
    assert first.report.status is RunStatus.NEEDS_HUMAN  # 还没有审批

    request = runner.bindings[0]
    binding = runner.inner.binding(request)
    assert binding.action_id == action_key(task.task_id, change)
    other = replace(request, trace_id="trace-two")
    assert runner.inner.binding(other).action_hash != binding.action_hash


# --------------------------------------------------------------------------- 分支与异常


def _bad_output(state, context):
    return {"not": "a NodeOutcome"}


_BRANCH_CASES = (
    pytest.param("unknown-node", {}, None, FailureCode.NODE_UNKNOWN, id="unknown-node"),
    pytest.param(
        "bad-node-output",
        {NodeId.REQUIREMENT_ANALYSIS: _bad_output},
        None,
        FailureCode.NODE_CONTRACT_INVALID,
        id="non-node-outcome",
    ),
    pytest.param(
        "unknown-route-label",
        None,
        {"validation_outcome": lambda state: "nonsense"},
        FailureCode.NODE_CONTRACT_INVALID,
        id="unknown-route-label",
    ),
)


@pytest.mark.parametrize(("kind", "nodes", "router_fns", "expected_code"), _BRANCH_CASES)
def test_unknown_nodes_labels_and_bad_output_never_complete(
    tmp_root_factory, kind: str, nodes, router_fns, expected_code
) -> None:
    """未知节点 / 非 NodeOutcome / 未知路由标签：终态一律是 failed，绝不是 completed。"""

    root = tmp_root_factory()
    if kind == "unknown-route-label":
        context = node_context(
            root,
            client=scripted_client(validate=(validate_allow(),)),
            name="branch-context",
        )
        state = empty_state("branch-task").replace(stage=NodeId.VALIDATION)
    else:
        context = node_context(root, name="branch-context")
        state = empty_state("branch-task")
    executor: StepExecutor = step_executor(
        root, context=context, nodes=nodes, router_fns=router_fns, name="branch"
    )
    report = ReferenceEngine(executor=executor).run(task_id="branch-task", state=state)
    assert report.status is RunStatus.FAILED
    assert report.status is not RunStatus.COMPLETED
    assert report.failure is not None
    assert report.failure.code is expected_code
    payload = report.to_payload()
    assert payload["status"] == "failed"
    assert payload["failure"] is not None


def test_a_raising_tool_runner_never_produces_a_failure_free_report(tmp_root_factory) -> None:
    """runner 抛异常：终态是 failed，报告带失败码，而且"开工未结算"的意图留在 checkpoint 里。"""

    root = tmp_root_factory()
    task = task_spec("raising-task")
    runner = RaisingRunner()
    run = run_graph(
        root,
        name="raising",
        task=task,
        client=scripted_client(
            evaluate=(allow_outcome(),), retrieve=(retrieval_ok(),)
        ),
        author=ScriptedAuthor([write_change()]),
        runner=runner,
    )
    assert len(runner.calls) == 1
    assert run.report.status is RunStatus.FAILED
    assert run.report.status is not RunStatus.COMPLETED
    assert run.report.failure is not None
    assert run.report.failure.code is FailureCode.STATE_INVALID
    payload = run.report.to_payload()
    assert payload["failure"] is not None
    assert payload["status"] != "completed"

    # 写前记账必须活下来：副作用之前刷盘的那笔"意图"不能被失败状态覆盖。
    record = run.store.load(task.task_id)
    assert record.state["failure"]["code"] == FailureCode.STATE_INVALID.value
    assert record.state["status"] == RunStatus.FAILED.value
    assert record.state["runs"][-1]["status"] == StageStatus.PENDING.value
    assert record.state["runs"][-1]["label"] == "intent"

    # 恢复必须认出"开工未结算"：交给人，而且绝不重放。
    again = run_graph(
        root,
        name="raising",
        task=task,
        config=run.config,
        client=scripted_client(
            evaluate=(allow_outcome(),), retrieve=(retrieval_ok(),)
        ),
        author=ScriptedAuthor([write_change()]),
        runner=runner,
    )
    assert again.report.status is RunStatus.NEEDS_HUMAN
    assert again.report.failure is not None
    assert again.report.failure.code is FailureCode.SIDE_EFFECT_UNKNOWN
    assert len(runner.calls) == 1, "副作用状态未知时不许重放"


# --------------------------------------------------------------------------- trace


def test_trace_break_stops_the_run(tmp_root_factory) -> None:
    """平台没有把 trace 还回来 = 传播中断：直接失败关闭，绝不"当作没有 trace"。"""

    opener = FakeOpener(
        {
            ROUTE_PATHS["readiness"]: readiness_response(),
            ROUTE_PATHS["evaluate"]: echo_decision_response(drop_trace=True),
            ROUTE_PATHS["retrieve"]: echo_retrieval_response(),
        }
    )
    client = ApiPolicyClient("http://127.0.0.1:9", token="test-token", opener=opener, timeout=2.0)
    with pytest.raises(TraceError) as excinfo:
        client.evaluate(
            EvaluateCall(
                request_id="req-trace",
                context={"file": "src/shop/order_controller.py"},
                principal={},
                trace_id="trace-must-come-back",
            )
        )
    assert excinfo.value.code is FailureCode.TRACE_MISSING

    run = run_graph(
        tmp_root_factory(),
        name="trace",
        task=task_spec("trace-task", trace_id="trace-must-come-back"),
        client=client,
        author=ScriptedAuthor([write_change()]),
        runner=ExecutingToolRunner(),
    )
    assert run.report.status is RunStatus.BLOCKED
    assert run.report.failure is not None
    assert run.report.failure.code is FailureCode.TRACE_MISSING


def test_echoed_trace_is_accepted(tmp_root_factory) -> None:
    """对照组：trace 原样回声时正常通过——上面的失败不是"所有调用都失败"。"""

    opener = FakeOpener(
        {
            ROUTE_PATHS["readiness"]: readiness_response(),
            ROUTE_PATHS["evaluate"]: echo_decision_response(),
            ROUTE_PATHS["retrieve"]: echo_retrieval_response(),
            ROUTE_PATHS["validate"]: echo_validate_response(),
        }
    )
    client = ApiPolicyClient("http://127.0.0.1:9", token="test-token", opener=opener, timeout=2.0)
    run = run_graph(
        tmp_root_factory(),
        name="trace-ok",
        task=task_spec("trace-ok-task", trace_id="trace-echo"),
        client=client,
        author=ScriptedAuthor([write_change()]),
        runner=ExecutingToolRunner(),
    )
    assert run.report.status is RunStatus.COMPLETED, run.report.failure
    assert {item.trace_id for item in run.report.state.traces} == {"trace-echo"}


# --------------------------------------------------------------------------- 密钥


def test_secrets_never_land_in_checkpoints_or_reports(tmp_root_factory) -> None:
    """需求正文、文件正文与凭据都不进 checkpoint，也不进报告载荷。"""

    secret = "sk-live-phase8-do-not-persist"  # secret-scan: allow（合成值，用于验证"凭据不进持久化状态"）
    requirement = f"实现订单控制器；上游给的凭据是 token={secret}，不得写进任何持久化状态"
    content = f'"""文件正文里也出现一次 {secret}：它同样不该进 checkpoint。"""\n'

    root = tmp_root_factory()
    task = task_spec("secret-task", requirement=requirement)
    change = write_change(summary="写入控制器（摘要里不放凭据）", content=content)
    run = run_graph(
        root,
        name="secret",
        task=task,
        client=scripted_client(
            evaluate=(allow_outcome(),), retrieve=(retrieval_ok(),),
            validate=(validate_allow(), validate_allow()),
        ),
        author=ScriptedAuthor([change]),
        runner=ExecutingToolRunner(),
    )
    assert run.report.status is RunStatus.COMPLETED, run.report.failure

    checkpoint_text = run.checkpoint_text
    payload_text = json.dumps(run.report.to_payload(), ensure_ascii=False)
    for blob, label in ((checkpoint_text, "checkpoint"), (payload_text, "报告")):
        assert secret not in blob, f"{label} 里出现了凭据"
        assert requirement not in blob, f"{label} 里出现了需求正文"
        assert "文件正文里也出现一次" not in blob, f"{label} 里出现了文件正文"
    # 引用与摘要照旧在：不是靠"什么都不存"通过断言。
    assert change.digest() in checkpoint_text
    assert task.requirement_digest() in checkpoint_text
