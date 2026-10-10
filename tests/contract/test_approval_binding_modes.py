"""G4 审批绑定档位测试：模式化审批可用，但防重放性质一条都不能少。

背景（实测）：审批只绑 action_hash，而 action_hash 覆盖运行时生成的 action_id /
tool_use_id，于是"同一条命令、只换调用编号"条子立刻作废——受治理的会话连 pytest 都跑不了。
这里验证补上的**模式化审批**（binding=pattern）确实解决了可用性缺口，同时逐条固定住
不可让步的性质：

1. 同一 action_id 绝不执行第二次（台账 + 审计链两处把关，与审批无关）；
2. 参数一变、模式匹配不上即拒绝；
3. 次数上限先原子占用后执行，用尽即拒绝，且写进台账 / 审计；
4. 过期、跨主体盗用、角色不足一律拒绝；
5. 自相矛盾或未知的审批字段一律拒绝（单次绑定仍是默认档）。
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from enforcement_support import (
    EnforcementPaths,
    approval_for,
    enforcement_paths,
    make_action,
)

# pytest 按测试模块命名空间里的**属性名**注册 fixture（没写 name= 时取的就是它），
# 所以这里必须用原名导入：它正是测试函数形参 `enforcement_paths` 要解析到的名字。
# `__all__` 声明这是一次刻意的再导出，不是未使用的导入（F401/F811 对它是误报）；
# 删掉这个导入 = 26 个用例在 setup 期报 `fixture 'enforcement_paths' not found`。
__all__ = ["enforcement_paths"]

from enforcement.approvals import (
    APPROVAL_SCHEMA_VERSION,
    APPROVAL_SET_SCHEMA_VERSIONS,
    ApprovalError,
    ApprovalRecord,
    approval_payload,
    approval_store_payload,
    load_approval,
    load_approvals,
    select_approval,
)
from enforcement.audit import FileAuditSink, NullAuditSink
from enforcement.ledger import EnforcementLedger
from enforcement.models import Decision, ReasonCode, utc_now
from enforcement.precheck import pre_execute

pytestmark = pytest.mark.contract

COMMAND_PATTERN = "^print[(]'ok'[)]$"


def shell_params(command: str = "print('ok')") -> dict[str, object]:
    return {"command": command, "description": "demo"}


def pattern_approval(
    request,
    *,
    patterns: dict[str, str],
    max_uses: int = 3,
    ttl: int = 300,
    expired: bool = False,
    subject: str | None = None,
    roles: tuple[str, ...] = ("reviewer",),
    approval_id: str = "approval-pattern-1",
) -> ApprovalRecord:
    now = utc_now()
    if expired:
        granted_at, expires_at = now - timedelta(hours=2), now - timedelta(hours=1)
    else:
        granted_at, expires_at = now - timedelta(seconds=1), now + timedelta(seconds=ttl)
    return ApprovalRecord(
        approval_id=approval_id,
        binding="pattern",
        tool_id=request.tool_id,
        subject=subject or request.subject or "local-user",
        granted_by="alice",
        granted_by_roles=roles,
        granted_at=granted_at,
        expires_at=expires_at,
        max_uses=max_uses,
        param_patterns=patterns,
    )


def run_pre(
    paths: EnforcementPaths,
    tool_id: str,
    params: dict[str, object],
    *,
    approval=None,
    action_id: str = "act-1",
    subject: str = "local-user",
    roles: tuple[str, ...] = ("owner",),
    sink=None,
    request=None,
):
    registry = paths.registry_object()
    request = request or make_action(
        registry, paths, tool_id, params, roles=roles, subject=subject, action_id=action_id
    )
    ledger = EnforcementLedger(paths.ledger)
    audit = sink if sink is not None else FileAuditSink(paths.audit, workspace=paths.workspace)
    outcome = pre_execute(
        request, registry=registry, ledger=ledger, sink=audit, approval=approval
    )
    return outcome, request


# --------------------------------------------------------------------------- 基线四例


def test_without_any_approval_the_governed_action_is_refused(enforcement_paths):
    outcome, _ = run_pre(enforcement_paths, "exec.shell", shell_params())

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.APPROVAL_REQUIRED


def test_single_binding_stays_the_default_and_binds_the_exact_call(enforcement_paths):
    paths = EnforcementPaths(enforcement_paths.root / "single")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = approval_for(first)
    assert approval.binding.value == "action", "单次绑定必须仍是默认档"

    exact, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, request=first)
    assert exact.decision.decision is not Decision.BLOCK, exact.decision.check("approval").detail

    # 只换调用编号：单次绑定按定义应当失效（更严格档），这是它的语义而不是缺陷
    renamed, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-2")
    assert renamed.decision.decision is Decision.BLOCK
    assert renamed.decision.reason_code is ReasonCode.APPROVAL_INVALID
    assert "action_hash" in renamed.decision.check("approval").detail


def test_used_single_binding_approval_is_refused(enforcement_paths):
    paths = EnforcementPaths(enforcement_paths.root / "used")
    registry = paths.registry_object()
    request = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = approval_for(request)
    EnforcementLedger(paths.ledger).record_approval_use(
        approval.approval_id, action_hash=request.action_hash
    )

    outcome, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, request=request)

    assert outcome.decision.decision is Decision.BLOCK
    assert "已被使用" in outcome.decision.check("approval").detail


def test_approver_must_hold_the_approval_role(enforcement_paths):
    paths = EnforcementPaths(enforcement_paths.root / "role")
    registry = paths.registry_object()
    request = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(
        request, patterns={"command": COMMAND_PATTERN, "description": ".*"}, roles=("developer",)
    )

    outcome, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-1")

    assert outcome.decision.decision is Decision.BLOCK
    assert "审批权" in outcome.decision.check("approval").detail


# --------------------------------------------------------------------------- 模式化审批


def test_pattern_approval_lets_the_same_command_run_under_a_new_call_id(enforcement_paths):
    """G4 的可用性缺口：同一条命令、同一个申请人，只换调用编号必须仍然放行。"""

    paths = EnforcementPaths(enforcement_paths.root / "pattern")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(first, patterns={"command": COMMAND_PATTERN, "description": ".*"}, max_uses=3)

    one, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-1")
    two, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-2")

    assert one.decision.decision is not Decision.BLOCK, one.decision.check("approval").detail
    assert two.decision.decision is not Decision.BLOCK, two.decision.check("approval").detail
    assert "binding=pattern" in two.decision.check("approval").detail
    assert two.decision.check("approval_use").detail.startswith("第 2/3 次")


def test_pattern_approval_rejects_a_command_that_does_not_match_the_pattern(enforcement_paths):
    paths = EnforcementPaths(enforcement_paths.root / "mismatch")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(first, patterns={"command": COMMAND_PATTERN, "description": ".*"}, max_uses=3)

    # echo hi 本身在白名单内（^echo( .*)?$），但它不匹配审批模式
    outcome, _ = run_pre(
        paths, "exec.shell", shell_params("echo hi"), approval=approval, action_id="call-other"
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.APPROVAL_INVALID
    assert "不匹配审批模式" in outcome.decision.check("approval").detail


def test_pattern_approval_stops_at_the_declared_use_limit(enforcement_paths):
    paths = EnforcementPaths(enforcement_paths.root / "quota")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(first, patterns={"command": COMMAND_PATTERN, "description": ".*"}, max_uses=2)

    for index in (1, 2):
        allowed, _ = run_pre(
            paths, "exec.shell", shell_params(), approval=approval, action_id=f"call-{index}"
        )
        assert allowed.decision.decision is not Decision.BLOCK, (
            allowed.decision.check("approval").detail
        )

    exhausted, _ = run_pre(
        paths, "exec.shell", shell_params(), approval=approval, action_id="call-3"
    )

    assert exhausted.decision.decision is Decision.BLOCK
    assert exhausted.decision.reason_code is ReasonCode.APPROVAL_INVALID
    assert "次数上限" in exhausted.decision.check("approval").detail
    # 额度占用必须真的写进台账：2 次成功 = 2 条 approval_used
    assert len(EnforcementLedger(paths.ledger).approval_uses(approval.approval_id)) == 2


def test_pattern_approval_must_cover_every_request_parameter(enforcement_paths):
    """只声明一部分参数的"一类调用"条子必须被拒，且理由要说清怎么改。

    真实注册表的 exec.pwsh 除了 command 还有 workdir / timeoutMs / run_in_background /
    sandbox_permissions 等参数；binding=pattern 不校验 action_hash，因此"只校验声明过的
    那几个"等于给未声明的参数留一张跟着条子放行的后门（改 workdir 就是改这次调用干什么）。
    """

    paths = EnforcementPaths(enforcement_paths.root / "coverage")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    partial = pattern_approval(first, patterns={"command": COMMAND_PATTERN}, max_uses=3)

    outcome, _ = run_pre(
        paths, "exec.shell", shell_params(), approval=partial, action_id="call-1"
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.APPROVAL_INVALID
    detail = outcome.decision.check("approval").detail
    assert "description" in detail
    assert "必须覆盖全部参数" in detail
    # 拒绝理由必须给出"改成什么形态就能过"（AGENTS 第 50 条）
    assert "--param-pattern description=.*" in detail
    assert "binding=action" in detail


def test_pattern_approval_never_crosses_subjects(enforcement_paths):
    paths = EnforcementPaths(enforcement_paths.root / "subject")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(
        first, patterns={"command": COMMAND_PATTERN, "description": ".*"}, subject="someone-else"
    )

    outcome, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-1")

    assert outcome.decision.decision is Decision.BLOCK
    assert "主体" in outcome.decision.check("approval").detail


def test_expired_pattern_approval_is_refused(enforcement_paths):
    paths = EnforcementPaths(enforcement_paths.root / "expired")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(first, patterns={"command": COMMAND_PATTERN, "description": ".*"}, expired=True)

    outcome, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-1")

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.APPROVAL_INVALID
    assert "过期" in outcome.decision.check("approval").detail


def test_the_same_action_id_can_never_run_twice_even_with_pattern_approval(enforcement_paths):
    """放宽"人工签条"这一环，绝不能放宽按 action_id 的重放拦截。"""

    paths = EnforcementPaths(enforcement_paths.root / "replay")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(first, patterns={"command": COMMAND_PATTERN, "description": ".*"}, max_uses=5)

    one, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-1")
    assert one.decision.decision is not Decision.BLOCK

    replay, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval, action_id="call-1")

    assert replay.decision.decision is Decision.BLOCK
    assert replay.decision.reason_code is ReasonCode.ACTION_REPLAY


def test_approval_quota_is_returned_when_the_audit_is_unwritable(enforcement_paths):
    """失败关闭不能变成死锁：动作没执行，额度必须还回去。"""

    paths = EnforcementPaths(enforcement_paths.root / "release")
    registry = paths.registry_object()
    first = make_action(registry, paths, "exec.shell", shell_params(), roles=("owner",))
    approval = pattern_approval(first, patterns={"command": COMMAND_PATTERN, "description": ".*"}, max_uses=1)

    blocked, _ = run_pre(
        paths, "exec.shell", shell_params(), approval=approval, sink=NullAuditSink()
    )
    assert blocked.decision.decision is Decision.BLOCK
    assert blocked.decision.reason_code is ReasonCode.AUDIT_UNAVAILABLE
    ledger = EnforcementLedger(paths.ledger)
    assert ledger.of_kind("approval_use_released"), "审计不可写时必须归还审批额度"

    retried, _ = run_pre(paths, "exec.shell", shell_params(), approval=approval)
    assert retried.decision.decision is not Decision.BLOCK, (
        retried.decision.check("approval_use").detail
    )
    assert retried.decision.check("approval_use").detail.startswith("第 1/1 次")


def test_pattern_matching_refuses_unsupported_param_shapes(enforcement_paths):
    """列表类参数不支持模式匹配：宁可在审批阶段拒绝，也不做宽松转换。"""

    paths = EnforcementPaths(enforcement_paths.root / "shape")
    registry = paths.registry_object()
    request = make_action(
        registry,
        paths,
        "exec.process",
        {"argv": ["python", "-c", "print(1)"], "description": "demo"},
        roles=("owner",),
    )
    approval = pattern_approval(request, patterns={"argv": ".*"}, max_uses=2)

    outcome, _ = run_pre(
        paths,
        "exec.process",
        {"argv": ["python", "-c", "print(1)"], "description": "demo"},
        approval=approval,
        action_id="call-1",
    )

    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.APPROVAL_INVALID
    assert "不支持模式匹配" in outcome.decision.check("approval").detail


# --------------------------------------------------------------------------- 声明校验


def test_contradictory_or_unknown_approval_fields_are_refused(tmp_root):
    now = utc_now()
    common = {
        "approval_id": "a-1",
        "tool_id": "exec.shell",
        "subject": "local-user",
        "granted_by": "alice",
        "granted_by_roles": ("reviewer",),
        "granted_at": now,
        "expires_at": now + timedelta(seconds=300),
    }

    # 单次绑定不得声明多次使用，也不得声明参数模式
    with pytest.raises(ApprovalError):
        ApprovalRecord(**common, binding="action", action_hash="h", action_id="i", max_uses=2)
    with pytest.raises(ApprovalError):
        ApprovalRecord(
            **common,
            binding="action",
            action_hash="h",
            action_id="i",
            param_patterns={"command": COMMAND_PATTERN, "description": ".*"},
        )
    # 单次绑定必须声明 action_hash / action_id
    with pytest.raises(ApprovalError):
        ApprovalRecord(**common, binding="action")
    # 模式化审批不得声明 action_hash / action_id，且必须有参数模式
    with pytest.raises(ApprovalError):
        ApprovalRecord(
            **common, binding="pattern", action_hash="h", param_patterns={"command": ".*"}
        )
    with pytest.raises(ApprovalError):
        ApprovalRecord(**common, binding="pattern")
    # 未知 binding 与非法正则
    with pytest.raises(Exception):
        ApprovalRecord(**common, binding="wildcard", action_hash="h", action_id="i")
    with pytest.raises(ApprovalError):
        ApprovalRecord(**common, binding="pattern", param_patterns={"command": "("})
    # 两个只在首尾空白上不同的参数名 strip 之后是同一个：不许静默 last-wins，
    # 否则一条更严格的模式会被悄悄丢掉。
    with pytest.raises(ApprovalError):
        ApprovalRecord(
            **common,
            binding="pattern",
            param_patterns={"command": COMMAND_PATTERN, " command ": ".*"},
        )

    # 未知字段：审批 JSON 里多写一个字段就必须被拒绝（不是静默忽略）
    document = {
        **common,
        "binding": "action",
        "action_hash": "h",
        "action_id": "i",
        "granted_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=300)).isoformat(),
        "unexpected": True,
    }
    path = tmp_root / "approval-unknown.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ApprovalError) as error:
        load_approval(path)
    assert "unexpected" in str(error.value) or "不合法" in str(error.value)


# --------------------------------------------------------------------------- 审批集（协议 1.2）
#
# 一个审批文件可以放**多条记录**，加载期按 tool_id 选择（open-work 5.21 / 5.59）：
# 桌面端 GUI 的每个动作都包在 run_code（PTC 传输）里，子工具调用逐个判定；"一个文件
# 一条记录"意味着名额只能给一个工具——给了传输工具，跑命令的工具一律 approval_invalid；
# 反过来则整个会话冻结。


def record_for(
    tool_id: str,
    *,
    approval_id: str,
    patterns: dict[str, str] | None = None,
    binding: str = "pattern",
    action_id: str | None = None,
    action_hash: str | None = None,
    subject: str = "local-user",
    expires_in: int = 300,
    max_uses: int = 3,
) -> ApprovalRecord:
    """造一条记录（不落盘）：协议层用例不依赖注册表，直接用任意 tool_id。"""

    now = utc_now()
    # 负的 expires_in = "已经过期，但有效期本身是正的"：直接把过期时间放到过去会撞上
    # "有效期必须为正"的构造期校验（那条校验是对的），因此签发时间要一起往前挪。
    granted_at = now + timedelta(seconds=expires_in - 1)
    expires_at = now + timedelta(seconds=expires_in)
    if binding == "action":
        return ApprovalRecord(
            approval_id=approval_id,
            binding="action",
            action_hash=action_hash or "sha256:h",
            action_id=action_id or "act-1",
            tool_id=tool_id,
            subject=subject,
            granted_by="alice",
            granted_by_roles=("reviewer",),
            granted_at=granted_at,
            expires_at=expires_at,
        )
    return ApprovalRecord(
        approval_id=approval_id,
        binding="pattern",
        tool_id=tool_id,
        subject=subject,
        granted_by="alice",
        granted_by_roles=("reviewer",),
        granted_at=granted_at,
        expires_at=expires_at,
        max_uses=max_uses,
        param_patterns=patterns or {"command": ".*"},
    )


def write_store(path, *records: ApprovalRecord):
    path.write_text(
        json.dumps(approval_store_payload(records), ensure_ascii=False),
        encoding="utf-8",
        newline="",
    )
    return path


def test_a_record_set_loads_every_record_and_selects_by_tool(tmp_root):
    """① 两份记录并存：每个工具各持一份放行，选出来的就是它自己那张。"""

    run_code = record_for(
        "exec.run_code",
        approval_id="app-run-code",
        patterns={"code": "(?s).*", "description": ".*"},
    )
    pwsh = record_for(
        "exec.pwsh",
        approval_id="app-pwsh",
        patterns={"command": "^python -m pytest( .*)?$", "description": ".*"},
    )
    path = write_store(tmp_root / "store.json", run_code, pwsh)

    records = load_approvals(path)
    assert [item.approval_id for item in records] == ["app-run-code", "app-pwsh"]
    assert select_approval(records, tool_id="exec.run_code").approval_id == "app-run-code"
    assert select_approval(records, tool_id="exec.pwsh").approval_id == "app-pwsh"


def test_selection_never_borrows_another_tools_record(tmp_root):
    """③ 不串味：别的工具的条子既不选中、也不作为"可用替代"的来源。"""

    pwsh = record_for("exec.pwsh", approval_id="app-pwsh")
    path = write_store(tmp_root / "store.json", pwsh)
    records = load_approvals(path)

    assert select_approval(records, tool_id="exec.run_code") is None
    # 反过来也一样：没有记录的工具有没有条子，答案只有一个是/否，与文件里放了什么无关。
    assert select_approval(records, tool_id="exec.pwsh").approval_id == "app-pwsh"


def test_selection_is_deterministic_and_prefers_the_usable_ticket(tmp_root):
    """选择规则是确定的，而且**只影响出示哪张条子**，不影响判定。

    1. 过期的条子排在后面（它必然被拒，但理由是"过期"比"参数不匹配"更接近真相）；
    2. 本次 action_id 的单次绑定 > 模式化 > 其它单次绑定；
    3. 同档按 approval_id 升序。
    """

    dead = record_for("exec.pwsh", approval_id="app-dead", expires_in=-60)
    stale_action = record_for("exec.pwsh", approval_id="app-stale", binding="action", action_id="other")
    pattern = record_for("exec.pwsh", approval_id="app-pattern")
    exact = record_for("exec.pwsh", approval_id="app-exact", binding="action", action_id="act-7")

    def picked(records, **kwargs) -> str | None:
        # 比 approval_id 而不是比对象：granted_by_roles 是 Sequence[str]，
        # 直接构造得到 tuple、从 JSON 读回得到 list——载荷逐字节相同，容器类型不是契约。
        selected = select_approval(records, **kwargs)
        return None if selected is None else selected.approval_id

    assert picked([dead, pattern], tool_id="exec.pwsh") == "app-pattern"
    assert (
        picked([stale_action, pattern, exact], tool_id="exec.pwsh", action_id="act-7")
        == "app-exact"
    )
    assert picked([stale_action, pattern], tool_id="exec.pwsh") == "app-pattern"
    # 同档：按 approval_id 升序（同样的输入必须选出同一张条子）
    first = record_for("exec.pwsh", approval_id="app-a")
    second = record_for("exec.pwsh", approval_id="app-b")
    assert picked([second, first], tool_id="exec.pwsh") == "app-a"

    # 主体不相符的条子排在后面：不是"它被跳过了"，而是"该出示的那张是主体相符的这张"
    mine = record_for("exec.pwsh", approval_id="app-mine", subject="local-user")
    theirs = record_for("exec.pwsh", approval_id="app-theirs", subject="someone-else")
    assert picked([theirs, mine], tool_id="exec.pwsh", subject="local-user") == "app-mine"


def test_selection_does_not_make_an_unusable_record_usable(tmp_root):
    """选中 ≠ 授权：挑出来的那张条子照样要过 verify_approval 的每一关。"""

    from enforcement.approvals import verify_approval

    record = record_for(
        "exec.pwsh", approval_id="app-wrong-subject", subject="someone-else"
    )
    path = write_store(tmp_root / "store.json", record)
    selected = select_approval(load_approvals(path), tool_id="exec.pwsh", subject="local-user")

    assert selected is not None and selected.approval_id == "app-wrong-subject", (
        "用例前提：它确实被选中了（出示的是这一张）"
    )
    with pytest.raises(ApprovalError):
        verify_approval(
            selected,
            action_hash="sha256:h",
            action_id="act-1",
            tool_id="exec.pwsh",
            subject="local-user",
            approval_roles=("reviewer",),
            used=False,
            params={"command": "anything"},
            uses=0,
        )


def test_a_legacy_single_record_document_is_still_read_with_the_same_meaning(tmp_root):
    """④ 旧形状（单记录）**继续被接受**：键集合与字段语义一字未变，没有歧义可制造误读。

    与 1.0→1.1 那次刻意不同：那次"pattern 到底覆盖了什么"本身就是歧义的，只能拒收重签。
    这一次旧文档的读法**逐字相同**，所以没有理由强迫所有人重签；它只是不会因为
    "文件里只有一条"就顺手授权别的工具。
    """

    legacy = record_for("exec.run_code", approval_id="app-legacy").model_copy(
        update={"schema_version": "1.1"}
    )
    path = tmp_root / "legacy.json"
    path.write_text(legacy.model_dump_json(), encoding="utf-8", newline="")

    assert load_approval(path).model_dump_json() == legacy.model_dump_json()
    assert [item.approval_id for item in load_approvals(path)] == ["app-legacy"]
    assert select_approval(load_approvals(path), tool_id="exec.pwsh") is None

    # 1.2 的单记录文档同样读得回来（记录自己的版本与"文档形状"是两件事）
    current = record_for("exec.run_code", approval_id="app-current")
    current_path = tmp_root / "current.json"
    current_path.write_text(current.model_dump_json(), encoding="utf-8", newline="")
    assert current.schema_version == APPROVAL_SCHEMA_VERSION
    assert load_approvals(current_path)[0].model_dump_json() == current.model_dump_json()


@pytest.mark.parametrize(
    "document, needle",
    [
        pytest.param(
            {"schema_version": "1.1", "records": []},
            "不认识",
            id="1.1-does-not-know-records",
        ),
        pytest.param(
            {"records": []},
            "schema_version",
            id="set-without-a-version",
        ),
        pytest.param(
            {"schema_version": "1.2", "records": []},
            "records",
            id="empty-set",
        ),
        pytest.param(
            "duplicate-approval-id",
            "同名两义",
            id="duplicate-approval-id",
        ),
        pytest.param(
            {"schema_version": "9.9", "records": []},
            "未知审批协议版本",
            id="unknown-version",
        ),
        pytest.param(
            {"schema_version": "1.2", "records": [{"approval_id": "x"}], "extra": 1},
            "records",
            id="unknown-field",
        ),
    ],
)
def test_contradictory_or_unknown_set_documents_are_refused_at_load_time(
    tmp_root, document, needle
):
    """自相矛盾 / 未知的文档一律在加载期拒绝——绝不静默按新语义读旧文件。"""

    if document == "duplicate-approval-id":
        # 同一个 approval_id 落到两条**合法**记录上：台账按 id 记"用了几次"，
        # 那就是同名两义。两条记录本身都必须是合法的，否则报的是别的错。
        shared = approval_payload(record_for("exec.pwsh", approval_id="dup"))
        other = approval_payload(record_for("exec.run_code", approval_id="dup"))
        document = {"schema_version": "1.2", "records": [shared, other]}

    path = tmp_root / "bad-store.json"
    path.write_text(json.dumps(document), encoding="utf-8", newline="")
    with pytest.raises(ApprovalError) as error:
        load_approvals(path)
    assert needle in str(error.value), str(error.value)


def test_load_approval_refuses_to_guess_when_the_store_has_several_records(tmp_root):
    """窄口子（load_approval）在记录集上不猜：猜一条等于把"该出示哪张条子"变成暗决定。"""

    path = write_store(
        tmp_root / "store.json",
        record_for("exec.run_code", approval_id="app-run-code"),
        record_for("exec.pwsh", approval_id="app-pwsh"),
    )
    with pytest.raises(ApprovalError) as error:
        load_approval(path)
    assert "2 条记录" in str(error.value) and "select_approval" in str(error.value)

    # 只有一条记录的记录集仍然可以走窄口子（编排层的收件箱就是一个文件一条记录）
    single = write_store(tmp_root / "single.json", record_for("exec.pwsh", approval_id="app-only"))
    assert load_approval(single).approval_id == "app-only"


def test_the_store_round_trips_through_the_written_document(tmp_root):
    """写出去的文档能被原样读回来，且版本号只有一个来源。

    **形状随条数**，这是刻意的兼容性选择：只有一条记录时写成历史上的单记录文档——
    仓库内外都有一批消费者按 `record["action_hash"]` 读"只有一条记录的文件"
    （`tools/orchestration_loop.py` 就是其中之一），而"文件里只有一条记录"没有歧义；
    两条起才写成记录集（那才是新形状，老消费方读不懂会失败关闭）。
    """

    single = (record_for("exec.run_code", approval_id="app-run-code"),)
    payload = approval_store_payload(single)
    assert payload["schema_version"] == APPROVAL_SCHEMA_VERSION
    assert "records" not in payload, "一条记录必须写成单记录文档（老消费者照常能读）"
    assert payload["action_hash"] is None and payload["approval_id"] == "app-run-code"

    pair = single + (
        record_for("exec.pwsh", approval_id="app-pwsh", binding="action", action_id="act-9"),
    )
    payload = approval_store_payload(pair)
    assert payload["schema_version"] in APPROVAL_SET_SCHEMA_VERSIONS
    assert [item["approval_id"] for item in payload["records"]] == ["app-run-code", "app-pwsh"]

    # 空集：不是"没有限制"，是一个读不出意图的文件
    with pytest.raises(ApprovalError):
        approval_store_payload(())

    path = tmp_root / "store.json"
    path.write_text(json.dumps(payload), encoding="utf-8", newline="")
    # 契约是**载荷**逐字节相同（granted_by_roles 的容器类型 tuple/list 不是契约）
    assert [approval_payload(item) for item in load_approvals(path)] == [
        approval_payload(item) for item in pair
    ]
