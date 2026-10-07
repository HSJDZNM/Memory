"""Phase 8 单元：状态 / 上限 / checkpoint / 恢复 / 审批的语义。

这一层是**框架中立**的：它不关心跑的是参考引擎还是 LangGraph，只关心
"状态里能放什么、计数器怎么长、checkpoint 读回来还是不是同一份、恢复能不能沿用旧 allow"。

四条纪律在这里被写成断言（阶段计划 §1 / §4 / §5 / §6）：

- 状态是**严格模型**：未知字段、绝对路径、`..` 路径、未知状态版本一律拒绝；
- 上限击穿抛 `LimitExceeded`，失败码决定终态（needs_human），绝不静默截断；
- checkpoint 只存**引用**：正文、密钥、文件内容都不进盘，读回来逐字节校验摘要；
- 恢复先比协议世代与版本凭据：规则集 / 索引变了重新评估，工具 schema 变了重新审批，
  世代变了直接拒绝——不兼容时沿用旧 allow 就是绕过治理。

标记用 `pytest.mark.contract`：pytest.ini 与 pyproject.toml 只登记了
contract / integration / security 三个标记（`--strict-markers` 下用未登记的 `unit` 会直接报错），
`tests/unit/test_precheck.py` 也是同样的选择。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from enforcement.approvals import ApprovalBinding, ApprovalRecord

from orchestration.approvals import ApprovalGate
from orchestration.checkpoint import (
    JsonCheckpointStore,
    ResumeError,
    ResumeMode,
    build_record,
    plan_resume,
)
from orchestration.errors import (
    STATUS_BY_CODE,
    ApprovalError,
    CheckpointError,
    LimitExceeded,
    NodeContractError,
    OrchestrationError,
    status_for,
)
from orchestration.limits import LIMIT_RULES, LimitKind, charge, charge_node_run, describe_budget
from orchestration.models import (
    STATE_SCHEMA_VERSION,
    SUPPORTED_STATE_SCHEMA_VERSIONS,
    ApprovalUse,
    ArtifactKind,
    ArtifactRef,
    ContextRef,
    Counters,
    Decision,
    FailureCode,
    FailureRef,
    GraphState,
    NodeId,
    NodeRun,
    PlatformSnapshot,
    PolicyTraceRef,
    RunLimits,
    RunStatus,
    StageStatus,
    ValidationSummary,
    ViolationRef,
    canonical_digest,
    empty_state,
)
from orchestration.client import _is_relative
from orchestration.nodes import Change, _changed_paths

from orchestration_support import (
    INDEX_VERSION,
    RULE_SET_HASH,
    TARGET_PATH,
    action_key,
    approval_file,
    task_spec,
    write_change,
)

pytestmark = pytest.mark.contract

TOOL_SCHEMA_HASH = "sha256:" + "d" * 64
ACTION_HASH = "task-1:0:0123456789abcdef"


# --------------------------------------------------------------------------- 状态


def test_graph_state_rejects_unknown_fields() -> None:
    """未知字段一律拒绝：编排状态与平台载荷之间不许有"悄悄多出来"的字段。"""

    with pytest.raises(ValidationError):
        GraphState(task_id="task-1", unexpected="x")
    with pytest.raises(ValidationError):
        GraphState(task_id="task-1", counters={"repair_rounds": 0, "unexpected": 1})
    with pytest.raises(ValidationError):
        RunLimits(unexpected=1)


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "~/secrets/token.txt",
        "C:/repo/src/shop/order_controller.py",
        "src\\shop\\order_controller.py",
        "../outside.py",
        "src/../outside.py",
        "src//order_controller.py",
    ],
)
def test_graph_state_rejects_non_relative_paths(path: str) -> None:
    """状态里的路径只能是仓库相对路径：绝对路径、反斜杠、`..` 与空段都拒绝。"""

    with pytest.raises(ValidationError):
        ArtifactRef(
            artifact_id="change-1",
            kind=ArtifactKind.CHANGE,
            path=path,
            digest="sha256:" + "0" * 64,
        )
    with pytest.raises(ValidationError):
        ContextRef(chunk_id="chunk-1", source_path=path, digest="sha256:" + "0" * 64)
    with pytest.raises(ValidationError):
        ViolationRef(rule_id="ARCH-001", rule_version=1, severity="error", file=path)


def test_empty_paths_are_only_allowed_where_they_mean_no_file() -> None:
    """空路径只在"这条 violation 没有文件维度"时有意义；引用类字段必须非空。"""

    with pytest.raises(ValidationError):
        ArtifactRef(
            artifact_id="change-1",
            kind=ArtifactKind.CHANGE,
            path="",
            digest="sha256:" + "0" * 64,
        )
    with pytest.raises(ValidationError):
        ContextRef(chunk_id="chunk-1", source_path="", digest="sha256:" + "0" * 64)
    assert ViolationRef(rule_id="ARCH-001", rule_version=1, severity="error", file="").file == ""


def test_graph_state_rejects_unknown_state_version() -> None:
    """读不懂的状态版本必须拒绝：不许按"看起来差不多"继续跑。"""

    with pytest.raises(ValidationError):
        GraphState(task_id="task-1", state_schema_version="9.9")
    assert SUPPORTED_STATE_SCHEMA_VERSIONS == frozenset({STATE_SCHEMA_VERSION})


def test_replace_returns_a_new_revision_and_never_mutates() -> None:
    """replace() 产出新实例并递增 revision：checkpoint 里每一版都是完整快照。"""

    state = empty_state("task-1")
    updated = state.replace(notes=("需求摘要已记录",))
    assert updated.revision == state.revision + 1
    assert state.notes == ()
    assert updated.notes == ("需求摘要已记录",)
    assert state is not updated
    assert updated.replace(notes=updated.notes).revision == updated.revision + 1


def test_digest_is_stable_for_the_same_input() -> None:
    """相同输入必须得到逐字节相同的摘要（没有墙钟时间，只有自增序号）。"""

    first = empty_state("task-1", limits=RunLimits(max_tool_calls=3))
    second = empty_state("task-1", limits=RunLimits(max_tool_calls=3))
    assert first.digest() == second.digest()
    assert first.digest().startswith("sha256:")
    assert first.digest() != first.replace(notes=("变了",)).digest()
    # 规范化 JSON 与键序无关：摘要只取决于内容
    assert canonical_digest({"b": 1, "a": [1, 2]}) == canonical_digest({"a": [1, 2], "b": 1})


# --------------------------------------------------------------------------- 上限


def test_counters_only_grow_and_reject_negative_values() -> None:
    """计数器只增不减：恢复时从 checkpoint 继续数，不"重新开始数"。"""

    state = empty_state("task-1", limits=RunLimits(max_tool_calls=2))
    charged = charge(state, LimitKind.TOOL_CALLS, 2)
    assert charged.counters.tool_calls == 2
    assert state.counters.tool_calls == 0
    assert charge(state, LimitKind.TOOL_CALLS, 0).counters.tool_calls == 0
    assert charge_node_run(state).counters.node_runs == 1
    assert ("tool_calls", 2, 2) in describe_budget(charged)
    with pytest.raises(ValidationError):
        Counters(tool_calls=-1)
    with pytest.raises(ValidationError):
        RunLimits(max_repair_rounds=-1)


@pytest.mark.parametrize("kind", list(LimitKind))
def test_charge_raises_limit_exceeded_with_the_matching_failure_code(kind: LimitKind) -> None:
    """每一种上限击穿都必须带自己的失败码——失败码决定终态，节点不许自己发明状态。"""

    rule = LIMIT_RULES[kind]
    # max_node_runs 的下界是 1（"至少要能跑一个节点"），其余计数可以从 0 起算。
    limit_value = 1 if rule.limit == "max_node_runs" else 0
    limits = RunLimits(**{rule.limit: limit_value})
    state = empty_state("task-1", limits=limits).replace(
        counters=Counters(**{rule.counter: limit_value})
    )
    with pytest.raises(LimitExceeded) as excinfo:
        charge(state, kind, 1)
    assert excinfo.value.code is rule.code
    # 六种上限全部都是"交给人"：上限击穿不该被报成"编排自己坏了"。
    assert status_for(excinfo.value) is RunStatus.NEEDS_HUMAN
    assert describe_budget(state)  # 预算摘要永远可读，不需要异常来兜底


def test_limit_rules_cover_every_limit_kind() -> None:
    """新增一种计数必须同时给出上限字段与失败码（否则上限会变成"没人管的常量"）。"""

    assert set(LIMIT_RULES) == set(LimitKind)
    for rule in LIMIT_RULES.values():
        assert hasattr(RunLimits(), rule.limit)
        assert hasattr(Counters(), rule.counter)
        assert isinstance(rule.code, FailureCode)


def test_charge_rejects_unknown_kind_and_negative_amount() -> None:
    """未知上限类别与负用量都是失败关闭，不是"跳过这一次记账"。"""

    state = empty_state("task-1")
    with pytest.raises(LimitExceeded) as unknown:
        charge(state, "not-a-limit-kind")  # type: ignore[arg-type]
    assert isinstance(unknown.value.code, FailureCode)
    with pytest.raises(LimitExceeded):
        charge(state, LimitKind.TOKENS, -1)
    assert state.counters.tokens == 0


# --------------------------------------------------------------------------- 失败码


def test_status_by_code_covers_every_failure_code() -> None:
    """每个失败码都必须登记终态；未登记的码会掉进 FAILED（"编排自己坏了"）。

    映射必须是**全函数**：新增一个 FailureCode 而忘记登记 STATUS_BY_CODE 时这条会失败。
    （LIMIT_NODE_RUNS 曾经漏登记，于是"节点执行次数超限"被报成 FAILED——已修。）
    """

    missing = set(FailureCode) - set(STATUS_BY_CODE)
    assert missing == set(), (
        "新增失败码必须同时登记 errors.STATUS_BY_CODE，"
        f"当前未登记：{sorted(code.value for code in missing)}"
    )
    assert STATUS_BY_CODE[FailureCode.STATE_INVALID] is RunStatus.FAILED
    assert STATUS_BY_CODE[FailureCode.POLICY_UNAVAILABLE] is RunStatus.BLOCKED
    assert STATUS_BY_CODE[FailureCode.TOOL_DENIED] is RunStatus.BLOCKED
    assert STATUS_BY_CODE[FailureCode.APPROVAL_MISSING] is RunStatus.NEEDS_HUMAN
    assert STATUS_BY_CODE[FailureCode.SIDE_EFFECT_UNKNOWN] is RunStatus.NEEDS_HUMAN
    assert STATUS_BY_CODE[FailureCode.LIMIT_REPAIR_ROUNDS] is RunStatus.NEEDS_HUMAN
    for status in STATUS_BY_CODE.values():
        assert isinstance(status, RunStatus)


def test_status_for_unregistered_code_falls_back_to_failed() -> None:
    """未登记的失败码按 FAILED 处理：不猜、不放行。

    当前所有失败码都已登记，于是用一个"假码"来证明兜底路径仍然存在——
    兜底不是"默认允许"，而是"编排自己坏了"。
    """

    error = LimitExceeded("未登记的失败码")
    error.code = "not-a-registered-code"  # type: ignore[assignment]
    assert isinstance(error, OrchestrationError)
    assert status_for(error) is RunStatus.FAILED


# --------------------------------------------------------------------------- checkpoint


def test_json_checkpoint_store_round_trip(tmp_root) -> None:
    """写入 / 读回必须逐字段一致，而且只落在 tmp 目录下。"""

    store = JsonCheckpointStore(tmp_root / "checkpoints")
    state = empty_state("task-1", limits=RunLimits(max_tool_calls=3))
    record = build_record(state, engine="reference", sequence=1)
    assert not store.exists("task-1")
    store.save(record)
    assert store.exists("task-1")
    loaded = store.load("task-1")
    assert loaded.state_digest == record.state_digest
    assert dict(loaded.state) == dict(record.state)
    assert loaded.engine == "reference"
    assert loaded.sequence == 1
    assert loaded.stage == NodeId.REQUIREMENT_ANALYSIS.value
    assert GraphState.model_validate(dict(loaded.state)).digest() == state.digest()
    path = store.path_for("task-1")
    assert path.parent == store.root
    assert tmp_root in path.parents


def test_checkpoint_path_stays_inside_the_store(tmp_root) -> None:
    """task_id 不能变成路径逃逸：分隔符被剥掉，空名字直接失败关闭。"""

    store = JsonCheckpointStore(tmp_root / "checkpoints")
    assert store.path_for("../../etc/passwd").parent == store.root
    with pytest.raises(CheckpointError):
        store.path_for("///")


def test_checkpoint_store_rejects_a_tampered_digest(tmp_root) -> None:
    """摘要与载荷不一致：写入就拒（不写自相矛盾的 checkpoint），读回也拒（内容被改过）。"""

    store = JsonCheckpointStore(tmp_root / "checkpoints")
    record = build_record(empty_state("task-1"), engine="reference", sequence=1)
    tampered = record.model_copy(update={"state": {**dict(record.state), "task_id": "other"}})
    with pytest.raises(CheckpointError):
        store.save(tampered)

    store.save(record)
    path = store.path_for("task-1")
    document = json.loads(path.read_text(encoding="utf-8"))
    document["state"]["notes"] = ["被改过"]
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(CheckpointError):
        store.load("task-1")


def test_checkpoint_store_rejects_unknown_version_missing_and_corrupt(tmp_root) -> None:
    """未知版本 / 记录缺失 / JSON 损坏 / 未知状态版本：四种都安全失败。

    绝不把"读不出来"当成"没有 checkpoint"：后者会从头跑，前者必须停下。
    """

    store = JsonCheckpointStore(tmp_root / "checkpoints")
    with pytest.raises(CheckpointError):
        store.load("missing-task")

    store.save(build_record(empty_state("task-2"), engine="reference", sequence=1))
    path = store.path_for("task-2")
    original = path.read_text(encoding="utf-8")

    document = json.loads(original)
    document["checkpoint_schema_version"] = "9.9"
    _write(path, document)
    with pytest.raises(CheckpointError):
        store.load("task-2")

    # 未知状态版本：摘要**重新算过**，让版本成为唯一的坏点。
    document = json.loads(original)
    document["state"]["state_schema_version"] = "9.9"
    document["state_digest"] = canonical_digest(document["state"])
    _write(path, document)
    with pytest.raises(CheckpointError):
        store.load("task-2")

    path.write_text("{ 这不是 JSON\n", encoding="utf-8", newline="\n")
    with pytest.raises(CheckpointError):
        store.load("task-2")


def _write(path, document) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def test_checkpoint_stores_references_not_bodies(tmp_root) -> None:
    """checkpoint 里只有引用：需求正文与文件正文都不进盘，只留路径与哈希。"""

    requirement = "REQUIREMENT-BODY：把订单控制器改成只依赖 Service。"
    content = "FILE-BODY：def create(...) -> ... 这是要写进文件的正文。"
    task = task_spec("task-1", requirement=requirement)
    change = write_change(content=content)
    artifact = ArtifactRef(
        artifact_id=f"change:{action_key(task.task_id, change)}",
        kind=ArtifactKind.CHANGE,
        path=change.path,
        digest=change.digest(),
        bytes=len(content.encode("utf-8")),
        note="只留摘要",
    )
    state = empty_state(task.task_id, requirements=(task.target,)).replace(artifacts=(artifact,))

    store = JsonCheckpointStore(tmp_root / "checkpoints")
    store.save(build_record(state, engine="reference", sequence=1))
    raw = store.path_for(task.task_id).read_text(encoding="utf-8")
    assert requirement not in raw
    assert content not in raw
    assert change.path in raw
    assert artifact.digest in raw
    assert "只留摘要" in raw


# --------------------------------------------------------------------------- 恢复


def _history_state() -> GraphState:
    """一份"跑过一段"的状态：有 trace、验证结果、审批引用与已完成的节点记录。"""

    summary = ValidationSummary(
        decision=Decision.ALLOW,
        request_id="task-1:validation:0",
        trace_id="trace-1",
        rule_set_hash=RULE_SET_HASH,
    )
    trace = PolicyTraceRef(
        node=NodeId.VALIDATION,
        request_id="task-1:validation:0",
        decision=Decision.ALLOW,
        trace_id="trace-1",
        rule_set_hash=RULE_SET_HASH,
    )
    use = ApprovalUse(
        node=NodeId.IMPLEMENTATION,
        approval_id="approval-phase8",
        action_hash=ACTION_HASH,
        subject="local-user",
        issued_at="2026-09-19T00:00:00+00:00",
        expires_at="2026-09-19T01:00:00+00:00",
    )
    run = NodeRun(
        node=NodeId.IMPLEMENTATION,
        attempt=1,
        status=StageStatus.OK,
        idempotency_key=ACTION_HASH,
        outcome_digest="sha256:" + "e" * 64,
        label="ok",
    )
    return empty_state("task-1", limits=RunLimits(), trace_id="trace-1").replace(
        stage=NodeId.VALIDATION,
        contexts=(
            ContextRef(
                chunk_id="chunk-1",
                source_path="policies/architecture/ARCH-001.yaml",
                digest="sha256:" + "c" * 64,
            ),
        ),
        traces=(trace,),
        validation=summary,
        test_validation=summary,
        approvals=(use,),
        runs=(run,),
        snapshot=_snapshot(),
    )


def _snapshot(**overrides) -> PlatformSnapshot:
    payload = {
        "rule_set_hash": RULE_SET_HASH,
        "index_version": INDEX_VERSION,
        "tool_schema_hash": TOOL_SCHEMA_HASH,
    }
    payload.update(overrides)
    return PlatformSnapshot(**payload)


def test_plan_resume_without_record_starts_fresh() -> None:
    """没有 checkpoint 就是从头开始——不是"用空状态假装恢复"。"""

    fresh = empty_state("task-1")
    plan = plan_resume(None, _snapshot(), fresh_state=fresh)
    assert plan.mode is ResumeMode.FRESH
    assert plan.state is fresh


def test_plan_resume_with_equal_snapshot_resumes() -> None:
    """版本凭据完全一致才叫"接着跑"：报告里 resume_mode 必须如实说 resume。"""

    record = build_record(_history_state(), engine="reference", sequence=3)
    plan = plan_resume(record, _snapshot(), fresh_state=empty_state("task-1"))
    assert plan.mode is ResumeMode.RESUME
    assert plan.changed == ()
    assert plan.state is not None
    assert plan.state.stage is NodeId.VALIDATION
    assert len(plan.state.traces) == 1


@pytest.mark.parametrize(
    "changed_dimension",
    ["rule_set_hash", "index_version"],
)
def test_plan_resume_rule_or_index_change_revalidates(changed_dimension: str) -> None:
    """规则集 / 索引变了 → 重新评估：旧 trace 与旧验证结果作废，阶段退回检索节点。

    已经记录过的节点执行记录（幂等键）必须保留：重跑不等于"重新开始"，
    更不等于再执行一次副作用。
    """

    recorded = _history_state()
    record = build_record(recorded, engine="reference", sequence=3)
    current = _snapshot(**{changed_dimension: "sha256:" + "f" * 64})
    plan = plan_resume(record, current, fresh_state=empty_state("task-1"))
    assert plan.mode is ResumeMode.REVALIDATE
    assert plan.changed == (changed_dimension,)
    state = plan.state
    assert state is not None
    assert state.traces == ()
    assert state.validation is None
    assert state.test_validation is None
    assert state.contexts == ()
    assert state.stage is NodeId.POLICY_RETRIEVAL
    assert state.runs == recorded.runs
    assert state.approvals == recorded.approvals
    assert any("重新评估" in note for note in state.notes)


def test_plan_resume_tool_schema_change_reapproves() -> None:
    """工具 schema 变了 → 旧审批作废（它绑的是旧 schema 的哈希），其余历史保留。"""

    recorded = _history_state()
    record = build_record(recorded, engine="reference", sequence=3)
    plan = plan_resume(
        record, _snapshot(tool_schema_hash="sha256:" + "f" * 64), fresh_state=empty_state("task-1")
    )
    assert plan.mode is ResumeMode.REAPPROVE
    assert plan.changed == ("tool_schema_hash",)
    state = plan.state
    assert state is not None
    assert state.approvals == ()
    assert state.traces == recorded.traces
    assert state.stage is NodeId.VALIDATION
    assert any("重新审批" in note for note in state.notes)


def test_plan_resume_rule_change_and_tool_schema_change_both_invalidate() -> None:
    """规则集与工具 schema **一起**变：两边的失效都要做，不能只做前一件。

    老实现里 revalidate 分支先 return，reapprove 的清空被整段丢掉——审批绑的是旧工具 schema
    算出来的 action_hash，却跟着恢复进新一轮，等于让一张过期条子继续生效。
    """

    recorded = _history_state()
    record = build_record(recorded, engine="reference", sequence=3)
    current = _snapshot(
        rule_set_hash="sha256:" + "f" * 64, tool_schema_hash="sha256:" + "e" * 64
    )
    plan = plan_resume(record, current, fresh_state=empty_state("task-1"))

    # 退得更远的那一个决定 mode：重评会把阶段退回检索节点。
    assert plan.mode is ResumeMode.REVALIDATE
    assert set(plan.changed) == {"rule_set_hash", "tool_schema_hash"}
    state = plan.state
    assert state is not None
    # 决定失效
    assert state.traces == ()
    assert state.validation is None
    assert state.test_validation is None
    assert state.contexts == ()
    assert state.stage is NodeId.POLICY_RETRIEVAL
    # 审批**同样**失效（这一条就是老实现丢掉的那一半）
    assert recorded.approvals != ()
    assert state.approvals == ()
    assert any("重新评估" in note for note in state.notes)
    assert any("重新审批" in note for note in state.notes)


@pytest.mark.parametrize("changed_dimension", ["policy_version", "decision_schema_version"])
def test_plan_resume_generation_change_refuses(changed_dimension: str) -> None:
    """协议世代变了就直接拒绝恢复：不沿用任何旧决定（ResumeError → checkpoint_incompatible）。"""

    record = build_record(_history_state(), engine="reference", sequence=3)
    current = _snapshot(**{changed_dimension: "9.9"})
    with pytest.raises(ResumeError) as excinfo:
        plan_resume(record, current, fresh_state=empty_state("task-1"))
    assert excinfo.value.code is FailureCode.CHECKPOINT_INCOMPATIBLE
    assert isinstance(excinfo.value, CheckpointError)


# --------------------------------------------------------------------------- 状态里不放正文


def test_state_text_rejects_bodies_and_credentials() -> None:
    """"状态里不放正文"是**拒绝**，不是约定。

    `requirements` / `notes` 走 `_safe_text`（src/orchestration/models.py:102）：超过
    `_MAX_NOTE`(200) 字符、或含确定形态的凭据，一律 ValidationError——既不落盘，也不
    "先收下再说"。独立验证探针当年正是靠"把需求原文塞进验收条目"证伪了这条纪律，
    所以它必须有回归：把 `_safe_text` 换成 `_short_text` 之外的放行实现，这里必须变红。
    """

    # 先钉住"合法短结论能过"：否则下面几条可能因为"什么都拒绝"而恒真。
    accepted = empty_state("task-1", requirements=("Controller 不得直连 Repository",))
    assert accepted.requirements == ("Controller 不得直连 Repository",)

    # 两条拒绝理由不同，分别钉住：超长走 _short_text，凭据形态走 contains_secret_value。
    # 只断言"抛了 ValidationError"是不够的——别的字段约束也会抛 ValidationError。
    with pytest.raises(ValidationError) as too_long_error:
        empty_state("task-1", requirements=("正文" * 101,))  # 202 字符 > _MAX_NOTE(200)
    assert "文本超过" in str(too_long_error.value)

    credentials = (
        # 合成值：只用于验证"凭据形态必须被拒绝"，不是真实密钥。
        "key = sk-live-0123456789abcdef",  # secret-scan: allow（合成值，用于验证凭据形态被拒绝）
        "-----BEGIN RSA PRIVATE KEY-----",  # secret-scan: allow（合成私钥块，用于验证私钥块被拒绝）
    )
    for credential in credentials:
        with pytest.raises(ValidationError) as credential_error:
            empty_state("task-1", requirements=(credential,))
        assert "凭据" in str(credential_error.value)


# --------------------------------------------------------------------------- 审批


def _gate_state(**limits) -> GraphState:
    return empty_state("task-1", limits=RunLimits(**limits))


def _use(gate: ApprovalGate, state: GraphState, **overrides):
    payload = {
        "node": NodeId.IMPLEMENTATION,
        "action_hash": ACTION_HASH,
        "action_id": ACTION_HASH,
        "tool_id": "orc.fs.write",
        "subject": "local-user",
    }
    payload.update(overrides)
    return gate.use(state, **payload)


def test_approval_gate_accepts_a_valid_record_and_records_the_use(tmp_root) -> None:
    """有效审批 → ApprovalUse；消费一次后单次审批就用完了（恢复不会让它重新生效）。"""

    path = approval_file(
        tmp_root / "approvals" / "approval.json", action_hash=ACTION_HASH, action_id=ACTION_HASH
    )
    gate = ApprovalGate(path, approval_roles=("reviewer",))
    state = _gate_state()
    use = _use(gate, state)
    assert isinstance(use, ApprovalUse)
    assert use.approval_id == "approval-phase8"
    assert use.action_hash == ACTION_HASH
    assert use.subject == "local-user"
    assert use.uses == 1

    consumed = ApprovalGate.consume(state, use)
    assert consumed.approvals[0].approval_id == "approval-phase8"
    with pytest.raises(ApprovalError) as excinfo:
        _use(gate, consumed)
    assert excinfo.value.code is FailureCode.APPROVAL_CONSUMED


# 合成值：它们只用来验证"凭据形态的文本不许进状态"这条拒绝路径，不是任何真实凭据。
# secret_scan 门禁按形态匹配，所以逐行显式声明放行并写明理由（门禁的提示语要求这样做）。
SECRET_LIKE = (
    "Bearer abcdefgh12345678",  # secret-scan: allow —— 合成形态，用于断言拒绝写入状态
    "sk-abcdefgh12345678",  # secret-scan: allow —— 合成形态，用于断言拒绝写入状态
    "glpat-abcdefgh12345678",  # secret-scan: allow —— 合成形态，用于断言拒绝写入状态
    "-----BEGIN RSA PRIVATE KEY-----",  # secret-scan: allow —— 合成标题行，用于断言拒绝写入状态
)


@pytest.mark.parametrize("secret", SECRET_LIKE)
def test_free_text_in_long_term_state_cannot_carry_credentials(secret: str) -> None:
    """状态是长期的：凭据形态的自由文本一律拒绝写入（与 requirements / notes 同一条口径）。

    这几处（ArtifactRef.note / PolicyTraceRef.reason / ViolationRef.message /
    NodeRun.detail / FailureRef.detail）装的是上游或外部文本——凭据一旦落盘就没有回收路径，
    所以判据钉在构造期，不靠调用方自觉。
    """

    with pytest.raises(ValidationError):
        FailureRef(code=FailureCode.LIMIT_NODE_RUNS, detail=secret)
    with pytest.raises(ValidationError):
        NodeRun(
            node=NodeId.REPAIR,
            status=StageStatus.OK,
            idempotency_key="task-1:repair:0",
            outcome_digest="sha256:" + "0" * 64,
            detail=secret,
        )
    with pytest.raises(ValidationError):
        ViolationRef(rule_id="ARCH-001", rule_version=1, severity="error", message=secret)
    with pytest.raises(ValidationError):
        PolicyTraceRef(
            node=NodeId.VALIDATION, request_id="req-1", decision=Decision.BLOCK, reason=secret
        )
    with pytest.raises(ValidationError):
        ArtifactRef(
            artifact_id="change-1",
            kind=ArtifactKind.CHANGE,
            digest="sha256:" + "0" * 64,
            note=secret,
        )


def test_ordinary_free_text_still_enters_the_state() -> None:
    """反向不变量：正常结论照常进状态——探针只认**确定形态**的凭据，不做宽口径猜测。"""

    detail = "节点超出预算：拒绝继续（limit_node_runs）"
    assert FailureRef(code=FailureCode.LIMIT_NODE_RUNS, detail=detail).detail == detail
    assert ViolationRef(
        rule_id="ARCH-001", rule_version=1, severity="error", message="Controller 不得直接访问 Repository。"
    ).message.startswith("Controller")


@pytest.mark.parametrize(
    "value",
    [
        "",
        "/abs/x.py",
        "~/x.py",
        "..\\x.py",
        "C:\\x.py",
        "\\\\server\\share\\x.py",
        "src/%2e%2e/secret.py",
        "src//x.py",
        "../x.py",
        "src/../../x.py",
    ],
)
def test_client_rejects_anything_that_is_not_a_state_relative_path(value: str) -> None:
    """进状态的外部路径只收"状态模型也认"的仓库相对路径（两套口径必然漂移）。

    旧判据只看前导 / 与 ~、再按 / 切一层 ..：Windows 形态（反斜杠、盘符、UNC）与百分号编码的
    穿越都能进状态，而同一个值交给状态模型就会被拒——客户端的"挑得进来"与模型的"收得下来"
    是两条规则，于是坏值在中间那一段里活着。
    """

    assert _is_relative(value) is False


@pytest.mark.parametrize("value", ["src/order/controller.py", "docs/x.md", "src/a%20b.py", "a.b"])
def test_client_accepts_plain_relative_paths(value: str) -> None:
    """反向不变量：普通相对路径照旧收（带一个百分号编码的空格不该被误伤）。"""

    assert _is_relative(value) is True


def _change_artifact(index: int, path: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=f"change:{index}",
        kind=ArtifactKind.CHANGE,
        path=path,
        digest="sha256:" + "0" * 64,
    )


def test_the_change_set_for_evidence_comes_from_executed_changes() -> None:
    """要验证的是**这次真的改了**的文件集合，不是写死的任务目标。

    `_apply_change` 允许改 `policies/…`：写死任务目标会让平台去验证一棵没被改的树
    （验证器选择与 pytest 的 changed_only 都读这个集合），真正改过的文件反而没声明。
    """

    target = "src/order/controller.py"
    fresh = empty_state("task-1")
    # 还没改过任何文件：退回任务目标（新任务第一次验证）
    assert _changed_paths(fresh, target) == (target,)

    repaired = fresh.replace(artifacts=(_change_artifact(0, "policies/coding/ARCH-001.yaml"),))
    assert _changed_paths(repaired, target) == ("policies/coding/ARCH-001.yaml",)

    # 多轮修复：按发生顺序去重；非 CHANGE 的 artifact（需求 / 计划 / 报告）不参与
    accumulated = fresh.replace(
        artifacts=(
            ArtifactRef(
                artifact_id="plan:0", kind=ArtifactKind.PLAN, path="docs/plan.md",
                digest="sha256:" + "0" * 64,
            ),
            _change_artifact(0, "policies/coding/ARCH-001.yaml"),
            _change_artifact(1, "policies/coding/ARCH-001.yaml"),
            _change_artifact(2, "src/other.py"),
        )
    )
    assert _changed_paths(accumulated, target) == (
        "policies/coding/ARCH-001.yaml",
        "src/other.py",
    )


def test_distinct_task_ids_never_share_a_checkpoint_file(tmp_root) -> None:
    """task_id 的清洗是有损的：'a:b' 与 'ab' 曾经落到同一个文件（互相覆盖、互相读回来）。

    现在只在"删字符真的改变了 id"时追加 id 摘要；安全字符组成的 id 文件名保持不变，
    既有 checkpoint 照常读得到。
    """

    store = JsonCheckpointStore(tmp_root / "checkpoints")

    assert store.path_for("a:b") != store.path_for("ab")
    assert store.path_for("ab").name == "ab.checkpoint.json"

    store.save(build_record(empty_state("a:b"), engine="reference", sequence=1))
    store.save(build_record(empty_state("ab"), engine="reference", sequence=1))

    assert store.load("a:b").task_id == "a:b"
    assert store.load("ab").task_id == "ab"


def test_load_refuses_a_checkpoint_belonging_to_another_task(tmp_root) -> None:
    """文件名只是索引：记录里的 task_id 与请求不一致，就是读到了别的任务的状态，必须拒绝。"""

    store = JsonCheckpointStore(tmp_root / "checkpoints")
    record = build_record(empty_state("task-1"), engine="reference", sequence=1)
    swapped = record.model_copy(update={"task_id": "task-2"})
    swapped = swapped.model_copy(update={"record_digest": swapped.computed_digest()})
    store.path_for("task-1").write_text(
        swapped.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    with pytest.raises(CheckpointError) as error:
        store.load("task-1")

    assert "task_id" in str(error.value)


def _pattern_approval(path: Path, *, approval_id: str = "approval-pattern") -> Path:
    """一份 binding=pattern 的审批：按契约**没有** action_id，是为"将来的某次调用"签的。"""

    now = datetime.now(timezone.utc).replace(microsecond=0)
    record = ApprovalRecord(
        approval_id=approval_id,
        binding=ApprovalBinding.PATTERN,
        tool_id="orc.fs.write",
        subject="local-user",
        granted_by="alice",
        granted_by_roles=("reviewer",),
        granted_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(seconds=300),
        max_uses=3,
        param_patterns={"file_path": ".*", "content": ".*"},
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    return Path(path)


def test_directory_inbox_picks_the_record_whose_action_id_matches(tmp_root) -> None:
    """收件箱里有无关条目时，仍然按 action_id 挑中**这一次**的那一份。"""

    inbox = tmp_root / "inbox"
    # 文件名排序把无关的那份排在前面：挑选必须靠 action_id，不靠顺序
    approval_file(
        inbox / "a-unrelated.json", action_hash="sha256:" + "a" * 64, action_id="other:0:xyz"
    )
    approval_file(inbox / "b-requested.json", action_hash=ACTION_HASH, action_id=ACTION_HASH)

    gate = ApprovalGate(inbox, approval_roles=("reviewer",))

    assert gate.resolve(ACTION_HASH).name == "b-requested.json"


def test_directory_inbox_prefers_a_pattern_approval_over_an_unrelated_record(tmp_root) -> None:
    """没有 action_id 匹配时的兜底顺序：pattern 档优先，其次是无关的 action 档。

    两档都不改变安全性（都不可能通过 verify：action_id / action_hash 必须逐位一致），
    它们回答的是"该去修哪一份记录"：
      - pattern 档是唯一**合法地**适用于"未匹配调用"的绑定（它按契约没有 action_id）；
      - 无关的 action 档照样返回，是为了让拒绝理由说得出"你签的是另一个动作"，
        而不是退化成笼统的"没有审批"——tests/security 的 forged-action-id 钉住这一点。
    """

    with_pattern = tmp_root / "with-pattern"
    approval_file(
        with_pattern / "a-unrelated.json", action_hash="sha256:" + "a" * 64, action_id="other:0:xyz"
    )
    pattern = _pattern_approval(with_pattern / "b-pattern.json")

    assert ApprovalGate(with_pattern, approval_roles=("reviewer",)).resolve(ACTION_HASH) == pattern

    only_action = tmp_root / "only-action"
    unrelated = approval_file(
        only_action / "a-unrelated.json", action_hash="sha256:" + "a" * 64, action_id="other:0:xyz"
    )

    # 返回它**不等于**授权：verify 会按 action_id / action_hash 逐位比对后拒绝（见 security 套件）。
    assert ApprovalGate(only_action, approval_roles=("reviewer",)).resolve(ACTION_HASH) == unrelated


def test_a_single_use_approval_stays_single_use_even_when_the_budget_allows_more(tmp_root) -> None:
    """条子自己的 max_uses 与编排层的预算数**不是一回事**：单次条子只能用一次。

    旧实现只按 RunLimits.max_approval_uses 算额度，并把 `used >= max_approval_uses` 传给 Phase 4：
    预算配成 2 时，一张单次条子可以用两次，而且平台那次"这张条子是否已消费"的复核永远收到 False——
    "单次使用"于是只剩编排层这一层保证，而它当时算错了。
    """

    path = approval_file(
        tmp_root / "approvals" / "approval.json", action_hash=ACTION_HASH, action_id=ACTION_HASH
    )
    gate = ApprovalGate(path, approval_roles=("reviewer",))
    state = _gate_state(max_approval_uses=2)

    first = _use(gate, state)
    state = ApprovalGate.consume(state, first)
    assert state.approvals[0].uses == 1

    with pytest.raises(ApprovalError) as excinfo:
        _use(gate, state)
    assert excinfo.value.code is FailureCode.APPROVAL_CONSUMED


def test_a_platform_side_rejection_keeps_its_reason_in_the_detail(tmp_root) -> None:
    """平台拒绝时的理由必须带上它自己那一句——只留异常类名等于把原因丢了。

    失败码这一侧保持类默认值（APPROVAL_MISSING）：Phase 4 的拒绝意味着"这份条子在这件事上
    不可用"，与"没有可用审批"同级，tests/security 的 approver-without-authority 钉的就是它。
    """

    path = approval_file(
        tmp_root / "approvals" / "approval.json",
        action_hash=ACTION_HASH,
        action_id=ACTION_HASH,
        roles=("developer",),
    )
    gate = ApprovalGate(path, approval_roles=("reviewer",))

    with pytest.raises(ApprovalError) as error:
        _use(gate, _gate_state())

    assert "审批人没有审批权" in str(error.value)
    assert error.value.code is FailureCode.APPROVAL_MISSING


def test_the_platform_side_recheck_sees_a_consumed_record(tmp_root) -> None:
    """平台那次复核必须收得到"这张条子已经消费过"这件事实（used 的口径是 >= 1，不是预算数）。

    这条钉的是**参数口径**：编排层的计数被绕过时，最后一层保证在 Phase 4 侧——
    而它只有在拿到真实事实时才拦得住。
    """

    from enforcement.approvals import load_approval, verify_approval

    path = approval_file(
        tmp_root / "approvals" / "approval.json", action_hash=ACTION_HASH, action_id=ACTION_HASH
    )
    record = load_approval(path)

    with pytest.raises(Exception) as error:
        verify_approval(
            record,
            action_hash=ACTION_HASH,
            action_id=ACTION_HASH,
            tool_id="orc.fs.write",
            subject="local-user",
            approval_roles=("reviewer",),
            used=True,
        )
    assert "已被使用" in str(error.value)

    # 反向：没消费过时必须放行（复核不是"一律拒绝"）
    verify_approval(
        record,
        action_hash=ACTION_HASH,
        action_id=ACTION_HASH,
        tool_id="orc.fs.write",
        subject="local-user",
        approval_roles=("reviewer",),
        used=False,
    )


@pytest.mark.parametrize(
    ("record_kwargs", "use_kwargs", "expected"),
    [
        pytest.param(None, {}, FailureCode.APPROVAL_MISSING, id="no-approval-file"),
        pytest.param(
            {"action_hash": "sha256:forged"}, {}, FailureCode.APPROVAL_PARAM_MISMATCH,
            id="other-action-hash",
        ),
        pytest.param(
            {"action_id": "task-1:0:ffffffffffffffff"}, {}, FailureCode.APPROVAL_PARAM_MISMATCH,
            id="other-action-id",
        ),
        pytest.param(
            {"tool_id": "orc.fs.edit"}, {}, FailureCode.APPROVAL_PARAM_MISMATCH,
            id="other-tool",
        ),
        pytest.param(
            {"subject": "someone-else"}, {}, FailureCode.APPROVAL_SUBJECT_MISMATCH,
            id="other-subject",
        ),
        pytest.param(
            {"ttl_seconds": -10, "granted_offset_seconds": -100}, {},
            FailureCode.APPROVAL_EXPIRED, id="expired",
        ),
        pytest.param(
            {"granted_offset_seconds": 600, "ttl_seconds": 1200}, {},
            FailureCode.APPROVAL_MISSING, id="granted-in-the-future",
        ),
        pytest.param(
            {"roles": ("developer",)}, {}, FailureCode.APPROVAL_MISSING, id="no-approval-role",
        ),
        pytest.param(
            {"subject": "someone-else"}, {"subject": None},
            FailureCode.APPROVAL_SUBJECT_MISMATCH, id="missing-request-subject",
        ),
    ],
)
def test_approval_gate_rejects_unusable_records(
    tmp_root, record_kwargs, use_kwargs, expected: FailureCode
) -> None:
    """缺失 / 参数漂移 / 跨主体 / 过期 / 无审批权 / 主体缺失：全部拒绝，且失败码稳定。"""

    path = None
    if record_kwargs is not None:
        path = approval_file(
            tmp_root / "approvals" / "approval.json",
            **{"action_hash": ACTION_HASH, "action_id": ACTION_HASH, **record_kwargs},
        )
    gate = ApprovalGate(path, approval_roles=("reviewer",))
    with pytest.raises(ApprovalError) as excinfo:
        _use(gate, _gate_state(), **use_kwargs)
    assert excinfo.value.code is expected
    assert status_for(excinfo.value) is RunStatus.NEEDS_HUMAN


# 这条用例的审批记录日期是**写死**的（granted 2020-01-01 / expires 2099-01-01），而门禁默认
# 读真实墙钟（src/orchestration/approvals.py 的 _now）——不钉死的话它的"爆炸日"就是
# 2099-01-01（或本机时钟早于 2020-01-01）。2026-10-03 稳定性清点：显式注入一个落在两者
# 之间的 now，结论只由载荷决定，不由跑测试那天决定。
_PINNED_APPROVAL_NOW = datetime(2026, 10, 3, tzinfo=timezone.utc)


def test_approval_record_from_phase4_is_the_only_accepted_shape(tmp_root) -> None:
    """审批语义来自 Phase 4：门禁读的就是 ApprovalRecord 的 JSON，本包不发明第二种格式。"""

    payload = {
        "schema_version": "1.1",
        "approval_id": "approval-9",
        "action_hash": ACTION_HASH,
        "action_id": ACTION_HASH,
        "tool_id": "orc.fs.write",
        "subject": "local-user",
        "granted_by": "alice",
        "granted_by_roles": ["reviewer"],
        "granted_at": "2020-01-01T00:00:00+00:00",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "note": "只允许这一次受治理的写入",
    }
    path = tmp_root / "approvals" / "approval.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert ApprovalRecord.model_validate(payload).approval_id == "approval-9"
    use = _use(
        ApprovalGate(path, approval_roles=("reviewer",), clock=lambda: _PINNED_APPROVAL_NOW),
        _gate_state(),
    )
    assert use.approval_id == "approval-9"

    payload["unexpected"] = "x"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ApprovalError) as excinfo:
        _use(
            ApprovalGate(path, approval_roles=("reviewer",), clock=lambda: _PINNED_APPROVAL_NOW),
            _gate_state(),
        )
    assert excinfo.value.code is FailureCode.APPROVAL_MISSING


def test_change_digest_binds_parameters() -> None:
    """参数变一个字符，激活键就变：旧审批自动作废（审批绑定的就是这个值）。"""

    base = Change(path=TARGET_PATH, summary="写入", content="a\n")
    changed = Change(path=TARGET_PATH, summary="写入", content="b\n")
    assert action_key("task-1", base) != action_key("task-1", changed)
    assert action_key("task-1", base, repair_rounds=1) != action_key("task-1", base)


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({}, id="neither-old-nor-content"),
        pytest.param({"old": "a", "content": "b"}, id="both-old-and-content"),
        pytest.param({"old": "a"}, id="old-without-replacement"),
    ],
)
def test_change_contract_is_enforced_at_construction(kwargs: dict) -> None:
    """三种畸形改动都必须在构造期被拒：它们以前都是**静默**的数据损失。

    实测（修复前 params() 的读数）：都没有 → content: ''（整文件截断）；
    有 old 没有 replacement → new_string: ''（把匹配到的文本删掉）；两个都有 → content 被丢掉。
    候选改动是受治理写入的参数，错一个字段就是一次不可逆写入。
    """

    with pytest.raises(NodeContractError):
        Change(path=TARGET_PATH, **kwargs)


def test_change_params_never_coerce_missing_values_to_empty() -> None:
    """params() 不再用 `or ""` 兜底：缺失的值不可能被抹成一次空写入。"""

    writing = Change(path=TARGET_PATH, content="a\n")
    assert writing.params() == {"file_path": TARGET_PATH, "content": "a\n"}

    editing = Change(path=TARGET_PATH, old="a", replacement="b")
    assert editing.params() == {
        "file_path": TARGET_PATH,
        "old_string": "a",
        "new_string": "b",
    }


def test_change_path_must_be_canonical() -> None:
    """路径判据不许是词法的：policies/../src/other.py 以 policies/ 开头，写的却是别的文件。

    词法前缀让"这一改动要不要走受治理的规则工具"由**一个别的文件**的名字决定；
    构造期用平台自己的规范化器归一，拿不到规范形态就拒绝。
    """

    for raw in ("policies/../src/other.py", "/etc/passwd", "../outside.py"):
        with pytest.raises(NodeContractError):
            Change(path=raw, content="x\n")

    # 等价写法归一：digest、params 与 tool_id 都对着同一个路径算
    assert Change(path="./policies/ARCH-001.yaml", content="x\n").path == "policies/ARCH-001.yaml"


def test_policy_tool_selection_follows_the_canonical_path() -> None:
    """规则目录**之内**才走受治理的规则工具；判据是路径段，不是裸前缀。"""

    assert Change(path="policies/coding/NEW-001.yaml", content="x\n").tool_id == "orc.policy.write"
    assert Change(path="src/order/controller.py", content="x\n").tool_id == "orc.fs.write"
    # 路径恰好是 policies 本身（目录）同样算规则目录之内
    assert Change(path="policies", content="x\n").tool_id == "orc.policy.write"


def test_policy_changes_use_approval_gated_tools_for_create_and_edit() -> None:
    """新建与编辑规则都会改变判定依据，不能落到普通文件工具。"""

    created = Change(path="policies/coding/NEW-001.yaml", summary="新建规则", content="id: NEW-001\n")
    edited = Change(
        path="policies/coding/OLD-001.yaml",
        summary="修改规则",
        old="severity: warning",
        replacement="severity: error",
    )
    assert created.tool_id == "orc.policy.write"
    assert edited.tool_id == "orc.policy.edit"
