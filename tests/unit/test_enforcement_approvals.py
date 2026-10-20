"""B1 审批「参数域」（协议 1.3）与命令族（注册表 1.1）的单元/契约用例。

三条不许被这次放宽动摇的性质，各有专门用例钉住：

1. **请求里出现未声明且无默认值的参数仍然拒**（1.1 起就有的两向严格）；
2. **run_in_background=true 仍然拒**（审批层按默认值 false 拒；显式放行时由驱动层拒）；
3. **1.1 / 1.2 的记录行为与修前逐字相同**（不许因为注册表恰好有默认值就悄悄变宽）。

放宽只发生在**一处**：记录自述 1.3 且调用方拿到注册表默认值时，可选参数可以省略，
缺席按默认值补齐后参与匹配。其余组合（旧版本记录、拿不到默认值）一律保持旧口径。
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from enforcement_support import registry_document, write_registry

from enforcement.action import build_action_request
from enforcement.approvals import (
    APPROVAL_PARAM_DOMAIN_VERSION,
    APPROVAL_SCHEMA_VERSION,
    APPROVAL_SET_SCHEMA_VERSIONS,
    SUPPORTED_APPROVAL_SCHEMA_VERSIONS,
    ApprovalError,
    ApprovalRecord,
    approval_param_domain,
    select_approval,
    union_pattern,
    verify_approval,
)
from enforcement.audit import FileAuditSink
from enforcement.ledger import EnforcementLedger
from enforcement.models import (
    REGISTRY_SCHEMA_VERSION,
    SUPPORTED_REGISTRY_SCHEMA_VERSIONS,
    Decision,
    ReasonCode,
    ToolSpec,
    utc_now,
)
from enforcement.precheck import pre_execute
from enforcement.registry import (
    load_registry,
    load_registry_document,
    registry_document_from_mapping,
)

pytestmark = pytest.mark.contract

DEFAULTS = {"timeoutMs": 60000, "workdir": ".", "run_in_background": False}


# --------------------------------------------------------------------------- 构造辅助


def record(
    *,
    version: str,
    patterns: dict[str, str],
    tool_id: str = "exec.shell",
    approval_id: str = "approval-pattern-1",
    subject: str = "local-user",
    max_uses: int = 5,
) -> ApprovalRecord:
    now = utc_now()
    return ApprovalRecord(
        schema_version=version,
        approval_id=approval_id,
        binding="pattern",
        tool_id=tool_id,
        subject=subject,
        granted_by="dshznm",
        granted_by_roles=("reviewer",),
        granted_at=now - timedelta(seconds=2),
        expires_at=now + timedelta(seconds=3600),
        max_uses=max_uses,
        param_patterns=patterns,
    )


def verify(record_: ApprovalRecord, params: dict, *, defaults=DEFAULTS, uses: int = 0) -> None:
    verify_approval(
        record_,
        action_hash="sha256:h",
        action_id="act-1",
        tool_id=record_.tool_id,
        subject="local-user",
        approval_roles=("reviewer", "owner"),
        used=False,
        params=params,
        uses=uses,
        param_defaults=defaults,
    )


def shell_spec(**overrides) -> ToolSpec:
    """一个最小命令工具：2 个必填参数 + 3 个带默认值的可选参数 + 两个命令族。"""

    payload = {
        "id": "exec.shell",
        "title": "test shell",
        "agent": "dsh",
        "tool_name": "pwsh",
        "schema_version": "1.0",
        "risk": "privileged_execution",
        "effect": "process",
        "driver": "shell_command",
        "shell": ["pwsh", "-Command"],
        "command_param": "command",
        "required_permissions": ["shell.exec"],
        "approval": "required",
        "post_checks": ["exit_code_zero"],
        "timeout_ms": 60000,
        "allowed_commands": ["^print[(]'ok'[)]$", "^echo( .*)?$"],
        "forbidden_command_fragments": ["../"],
        "parameters": [
            {"name": "command", "type": "string", "required": True, "max_chars": 400},
            {"name": "description", "type": "string", "required": True, "max_chars": 200},
            {"name": "timeoutMs", "type": "integer", "default": 60000},
            {
                "name": "workdir",
                "type": "path",
                "path_scope": "workspace",
                "path_kind": "directory",
                "default": ".",
            },
            {"name": "run_in_background", "type": "boolean", "default": False},
        ],
        "command_families": [
            {"id": "tests", "patterns": ["^print[(]'ok'[)]$"]},
            {"id": "other", "patterns": ["^echo( .*)?$"]},
        ],
    }
    payload.update(overrides)
    return ToolSpec.model_validate(payload)


def build_paths(tmp_root, *, tools=None):
    """写一份测试注册表 + 已审核清单，返回（注册表对象, 注册表路径, 审批清单路径）。"""

    if tools is None:
        tools = (json.loads(shell_spec().model_dump_json()),)
    document = registry_document(tools=tools)
    registry_path, approved_path = write_registry(tmp_root, document=document)
    loaded = load_registry(registry_path, approved_path=approved_path)
    return loaded.registry, registry_path, approved_path


def run_pre(tmp_root, registry, *, params, approval, workspace):
    spec = registry.tool("exec.shell")
    request = build_action_request(
        spec,
        params,
        action_id="act-" + str(abs(hash(json.dumps(params, sort_keys=True))) % 10**8),
        request_id="req-b1",
        agent="dsh",
        agent_version="0.1.5-rc.1",
        trace_id="trace-b1",
        subject="local-user",
        roles=("owner",),
        permissions=registry.permissions_for(("owner",)),
        context=None,
        workspace=workspace,
        ttl_seconds=registry.grant_ttl_seconds,
    )
    outcome = pre_execute(
        request,
        registry=registry,
        ledger=EnforcementLedger(tmp_root / "ledger.jsonl"),
        sink=FileAuditSink(tmp_root / "audit.jsonl", workspace=workspace),
        approval=approval,
        dry_run=True,
    )
    return outcome, request


# --------------------------------------------------------------------------- 协议版本


def test_the_protocol_axis_moved_to_1_3_and_old_versions_stay_supported():
    assert APPROVAL_SCHEMA_VERSION == "1.3"
    assert APPROVAL_PARAM_DOMAIN_VERSION == "1.3"
    assert SUPPORTED_APPROVAL_SCHEMA_VERSIONS == {"1.1", "1.2", "1.3"}
    # 记录集从 1.2 起才有：1.1 不认识 records，1.2 / 1.3 都认识。
    assert APPROVAL_SET_SCHEMA_VERSIONS == {"1.2", "1.3"}


@pytest.mark.parametrize("version", ["1.1", "1.2"])
def test_old_records_still_load_with_the_same_meaning(tmp_root, version):
    from enforcement.approvals import load_approval

    original = record(version=version, patterns={"command": ".*"})
    path = tmp_root / f"legacy-{version}.json"
    path.write_text(original.model_dump_json(), encoding="utf-8", newline="")

    assert load_approval(path).model_dump_json() == original.model_dump_json()


# --------------------------------------------------------------------------- 参数域核心


def test_1_3_record_may_omit_a_defaulted_parameter_and_the_omission_means_the_default():
    ticket = record(version="1.3", patterns={"command": ".*", "description": ".*"})

    # 缺席与显式默认值在「参数域」里是同一件事（驱动层本来也这么读）
    verify(ticket, {"command": "x", "description": "d"})
    verify(ticket, {"command": "x", "description": "d", "timeoutMs": 60000})
    verify(ticket, {"command": "x", "description": "d", "timeoutMs": 60000, "workdir": "."})
    verify(
        ticket,
        {
            "command": "x",
            "description": "d",
            "timeoutMs": 60000,
            "workdir": ".",
            "run_in_background": False,
        },
    )


@pytest.mark.parametrize(
    "params, needle",
    [
        ({"command": "x", "description": "d", "timeoutMs": 30000}, "默认值 60000"),
        ({"command": "x", "description": "d", "workdir": "src"}, "默认值 '.'"),
        ({"command": "x", "description": "d", "run_in_background": True}, "默认值 False"),
    ],
)
def test_1_3_omission_is_not_a_wildcard(params, needle):
    """省略 = 只接受默认值；非默认值仍然拒，而且理由要说清"这条模式不是你写的"。"""

    ticket = record(version="1.3", patterns={"command": ".*", "description": ".*"})
    with pytest.raises(ApprovalError) as error:
        verify(ticket, params)
    message = str(error.value)
    assert needle in message
    assert "参数域" in message and "--param-pattern" in message


def test_1_3_declared_parameter_absent_from_the_request_is_filled_with_the_default():
    """记录显式声明了可选参数的**模式**时，请求侧缺席也按默认值补齐后再比对。"""

    matching = record(
        version="1.3", patterns={"command": ".*", "description": ".*", "timeoutMs": "^60000$"}
    )
    verify(matching, {"command": "x", "description": "d"})

    not_matching = record(
        version="1.3", patterns={"command": ".*", "description": ".*", "timeoutMs": "^30000$"}
    )
    with pytest.raises(ApprovalError):
        verify(not_matching, {"command": "x", "description": "d"})


@pytest.mark.parametrize("version", ["1.1", "1.2"])
def test_old_records_do_not_get_the_parameter_domain(version):
    """同样的省略在 1.1 / 1.2 的记录上**逐字不变**：请求多一格就拒，少了声明的就拒。"""

    ticket = record(version=version, patterns={"command": ".*", "description": ".*"})
    verify(ticket, {"command": "x", "description": "d"})  # 两向都严格对得上 → 放行
    with pytest.raises(ApprovalError) as extra:
        verify(ticket, {"command": "x", "description": "d", "timeoutMs": 60000})
    assert "没有在审批模式里声明" in str(extra.value)

    declared = record(
        version=version, patterns={"command": ".*", "description": ".*", "timeoutMs": "^60000$"}
    )
    with pytest.raises(ApprovalError) as missing:
        verify(declared, {"command": "x", "description": "d"})
    assert "不在本次请求里" in str(missing.value)


def test_1_3_without_registry_defaults_falls_back_to_the_old_reading():
    """拿不到注册表默认值就不补（失败关闭）：放宽必须是显式的，不能靠数据恰好在场。"""

    ticket = record(version="1.3", patterns={"command": ".*", "description": ".*"})
    with pytest.raises(ApprovalError) as error:
        verify(ticket, {"command": "x", "description": "d", "timeoutMs": 60000}, defaults=None)
    assert "没有在审批模式里声明" in str(error.value)


def test_undeclared_parameters_without_a_default_are_still_refused():
    """负例①：请求里出现未声明且无默认值的参数 → 拒（两个版本的记录都一样）。"""

    for version in ("1.2", "1.3"):
        ticket = record(version=version, patterns={"command": ".*", "description": ".*"})
        with pytest.raises(ApprovalError) as error:
            verify(ticket, {"command": "x", "description": "d", "sandbox_permissions": "x"})
        assert "没有在审批模式里声明" in str(error.value)
        assert "sandbox_permissions" in str(error.value)


def test_param_domain_only_touches_records_that_can_be_completed():
    """1.2 记录的生效域原样；1.3 记录才出现 implicit 模式（读出来的东西必须是可解释的）。"""

    old = record(version="1.2", patterns={"command": ".*"})
    domain = approval_param_domain(old, params={"command": "x"}, param_defaults=DEFAULTS)
    assert domain.patterns == {"command": ".*"} and not domain.implicit

    new = record(version="1.3", patterns={"command": ".*"})
    domain = approval_param_domain(new, params={"command": "x"}, param_defaults=DEFAULTS)
    assert domain.implicit == frozenset(DEFAULTS)
    assert set(domain.patterns) == {"command", *DEFAULTS}
    assert re.fullmatch(domain.patterns["workdir"], ".") is not None
    assert re.fullmatch(domain.patterns["workdir"], "src") is None


# --------------------------------------------------------------------------- 选择 ≠ 授权


def test_selection_prefers_the_ticket_whose_domain_covers_the_defaulted_shape():
    now = utc_now()

    def ticket(approval_id: str, patterns: dict[str, str]) -> ApprovalRecord:
        return ApprovalRecord(
            schema_version="1.3",
            approval_id=approval_id,
            binding="pattern",
            tool_id="exec.pwsh",
            subject="local-user",
            granted_by="dshznm",
            granted_by_roles=("reviewer",),
            granted_at=now - timedelta(seconds=2),
            expires_at=now + timedelta(seconds=3600),
            max_uses=3,
            param_patterns=patterns,
        )

    omits = ticket("approval-a-omits", {"command": "^git diff$", "description": ".*"})
    declares = ticket(
        "approval-b-declares",
        {"command": "^git diff$", "description": ".*", "timeoutMs": "^30000$"},
    )
    picked = select_approval(
        [declares, omits],
        tool_id="exec.pwsh",
        subject="local-user",
        params={"command": "git diff", "description": "d", "timeoutMs": 60000},
        param_defaults=DEFAULTS,
    )
    assert picked is not None and picked.approval_id == "approval-a-omits"

    # 选中 ≠ 授权：换成非默认超时后它照样被 verify 拒
    with pytest.raises(ApprovalError):
        verify(
            picked,
            {"command": "git diff", "description": "d", "timeoutMs": 30000},
            defaults=DEFAULTS,
        )


def test_selection_does_not_change_when_defaults_are_unavailable():
    """不给默认值（旧调用方）时排序与修前一致：1.3 的"部分对得上"这一档不生效。"""

    now = utc_now()

    def ticket(approval_id: str, version: str) -> ApprovalRecord:
        return ApprovalRecord(
            schema_version=version,
            approval_id=approval_id,
            binding="pattern",
            tool_id="exec.pwsh",
            subject="local-user",
            granted_by="dshznm",
            granted_by_roles=("reviewer",),
            granted_at=now - timedelta(seconds=2),
            expires_at=now + timedelta(seconds=3600),
            max_uses=3,
            param_patterns={"command": "^git diff$", "description": ".*"},
        )

    params = {"command": "git diff", "description": "d", "timeoutMs": 60000}
    # 1.2 记录没有参数域：形状对不上 → 按 approval_id 定序，不因"声明的那几格对得上"抢先
    assert (
        select_approval(
            [ticket("approval-b", "1.2"), ticket("approval-a", "1.2")],
            tool_id="exec.pwsh",
            subject="local-user",
            params=params,
        ).approval_id
        == "approval-a"
    )
    # 1.3 记录在**没给默认值**时同样没有这一档
    assert (
        select_approval(
            [ticket("approval-b", "1.3"), ticket("approval-a", "1.3")],
            tool_id="exec.pwsh",
            subject="local-user",
            params=params,
        ).approval_id
        == "approval-a"
    )


# --------------------------------------------------------------------------- 命令族


def test_union_pattern_is_an_exact_alternation():
    single = "^print[(]'ok'[)]$"
    assert union_pattern([single]) == single, "单条模式必须原样返回（保持可读/可审计）"

    union = union_pattern(["^print[(]'ok'[)]$", "^echo( .*)?$"])
    assert re.fullmatch(union, "print('ok')") is not None
    assert re.fullmatch(union, "echo hi") is not None
    assert re.fullmatch(union, "rm -rf src") is None
    with pytest.raises(ApprovalError):
        union_pattern([])


def test_families_are_audited_data_and_partition_the_allowlist(tmp_root):
    registry = load_registry().registry
    for tool_id in ("exec.pwsh", "exec.bash"):
        spec = registry.tool(tool_id)
        patterns = [pattern for family in spec.command_families for pattern in family.patterns]
        assert sorted(patterns) == sorted(spec.allowed_commands), tool_id
        assert spec.param_defaults() == DEFAULTS, tool_id
        # 默认值与驱动层的真实缺省一致（数据说的与代码做的是同一句话）
        assert spec.param_defaults()["timeoutMs"] == spec.timeout_ms
        # 提权参数**故意没有默认值**：平台从不把"缺席"当作 workspace-write
        assert "sandbox_permissions" not in spec.param_defaults()
        assert "justification" not in spec.param_defaults()


def test_family_data_enters_the_reviewed_schema_hash():
    base = shell_spec()
    changed = shell_spec(command_families=[{"id": "tests", "patterns": ["^print[(]'ok'[)]$"]}])
    assert changed.schema_hash != base.schema_hash
    assert base.command_family("tests").patterns == ("^print[(]'ok'[)]$",)
    assert base.command_family("nope") is None


def test_registry_schema_version_moved_to_1_4_and_old_documents_still_load(tmp_root):
    """注册表轴：1.1（B1 的族与默认值）→ 1.2（B3 的 read_guard）→ 1.3（C3 的 .policy 前缀）
    → 1.4（C3 前置阻断补齐：.git 与 .github/workflows 执行面），四份旧文档照常加载。"""

    assert REGISTRY_SCHEMA_VERSION == "1.4"
    assert SUPPORTED_REGISTRY_SCHEMA_VERSIONS == {"1.0", "1.1", "1.2", "1.3", "1.4"}

    import yaml as yaml_module

    for version in ("1.0", "1.1", "1.2", "1.3"):
        old = registry_document()
        old["registry_schema_version"] = version
        path = tmp_root / f"old-registry-{version}.yaml"
        path.write_text(
            yaml_module.safe_dump(old, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        assert load_registry_document(path)["registry_schema_version"] == version
        assert registry_document_from_mapping(
            {**old, "registry_schema_version": version}
        ).version == 1


@pytest.mark.parametrize(
    "overrides, needle",
    [
        ({"parameters": [{"name": "x", "type": "string", "required": True, "default": "a"}]}, "required"),
        ({"parameters": [{"name": "x", "type": "integer", "default": "60"}]}, "整数"),
        ({"parameters": [{"name": "x", "type": "integer", "default": True}]}, "整数"),
        ({"parameters": [{"name": "x", "type": "boolean", "default": 1}]}, "布尔"),
        ({"parameters": [{"name": "x", "type": "path", "default": "C:/x"}]}, "相对路径"),
        ({"parameters": [{"name": "x", "type": "path", "default": "../x"}]}, ".."),
        ({"parameters": [{"name": "x", "type": "string", "default": "ab", "max_chars": 1}]}, "max_chars"),
        ({"parameters": [{"name": "x", "type": "string", "default": "b", "pattern": "^a$"}]}, "pattern"),
        ({"parameters": [{"name": "x", "type": "string", "default": "b", "enum": ["a"]}]}, "enum"),
        (
            {"parameters": [{"name": "x", "type": "string_list", "max_items": 2, "default": ["a"]}]},
            "string_list",
        ),
        ({"command_families": [{"id": "a", "patterns": []}]}, "at least"),
        ({"command_families": [{"id": "a", "patterns": ["("]}]}, "正则"),
        (
            {"command_families": [{"id": "a", "patterns": ["^print[(]'ok'[)]$"]}] * 2},
            "重复",
        ),
        ({"command_families": [{"id": "a", "patterns": ["^print[(]'ok'[)]$"], "x": 1}]}, "Extra"),
        ({"command_families": [{"id": "a", "patterns": ["^print[(]'ok'[)]$"]}], "driver": "file_edit"}, "shell_command"),
    ],
)
def test_bad_defaults_and_families_are_refused_at_load_time(overrides, needle):
    with pytest.raises(Exception) as error:
        shell_spec(**overrides)
    assert needle in str(error.value)


# --------------------------------------------------------------------------- precheck 集成


def test_precheck_lets_a_1_3_ticket_cover_the_defaulted_shapes(tmp_root):
    """3 格 / 4 格 / 带 background=false 的调用：1.2 条子全拒，1.3 条子全放行。"""

    registry, _, _ = build_paths(tmp_root)
    workspace = tmp_root / "workspace"
    workspace.mkdir()

    patterns = {"command": "^print[(]'ok'[)]$", "description": ".*"}
    shapes = [
        {"command": "print('ok')", "description": "d"},
        {"command": "print('ok')", "description": "d", "timeoutMs": 60000},
        {"command": "print('ok')", "description": "d", "timeoutMs": 60000, "workdir": "."},
        {
            "command": "print('ok')",
            "description": "d",
            "timeoutMs": 60000,
            "workdir": ".",
            "run_in_background": False,
        },
    ]

    old = record(version="1.2", patterns=patterns)
    new = record(version="1.3", patterns=patterns)
    for index, params in enumerate(shapes):
        # 每次跑在独立目录里（台账/审计互不干扰）
        old_dir = tmp_root / f"old-{index}"
        old_dir.mkdir(exist_ok=True)
        old_outcome, _ = run_pre(
            old_dir, registry, params=params, approval=old, workspace=workspace
        )
        if index == 0:
            # 两向都严格对得上：1.2 记录照旧放行（修前修后逐字相同）
            assert old_outcome.decision.decision is not Decision.BLOCK, params
            assert "param_domain" not in old_outcome.decision.check("approval").detail
        else:
            assert old_outcome.decision.decision is Decision.BLOCK, params
            assert old_outcome.decision.reason_code is ReasonCode.APPROVAL_INVALID, params

        new_dir = tmp_root / f"new-{index}"
        new_dir.mkdir(exist_ok=True)
        new_outcome, _ = run_pre(
            new_dir, registry, params=params, approval=new, workspace=workspace
        )
        assert new_outcome.decision.decision is not Decision.BLOCK, new_outcome.decision.check(
            "approval"
        ).detail
        # 1.3 的判定详情必须说得出"这次补了哪些默认值格"（AGENTS 第 50 条）
        assert "param_domain=defaults:" in new_outcome.decision.check("approval").detail


def test_precheck_still_refuses_background_true_and_non_default_values(tmp_root):
    registry, _, _ = build_paths(tmp_root)
    workspace = tmp_root / "workspace"
    workspace.mkdir()
    ticket = record(version="1.3", patterns={"command": "^print[(]'ok'[)]$", "description": ".*"})

    for index, params in enumerate(
        (
            {"command": "print('ok')", "description": "d", "run_in_background": True},
            {"command": "print('ok')", "description": "d", "timeoutMs": 30000},
            {"command": "print('ok')", "description": "d", "workdir": "src"},
        )
    ):
        (tmp_root / f"neg-{index}").mkdir(exist_ok=True)
        outcome, _ = run_pre(
            tmp_root / f"neg-{index}", registry, params=params, approval=ticket, workspace=workspace
        )
        assert outcome.decision.decision is Decision.BLOCK, params
        assert outcome.decision.reason_code is ReasonCode.APPROVAL_INVALID, params
        assert outcome.decision.check("approval").detail


def test_precheck_refuses_unknown_and_non_allowlisted_commands(tmp_root):
    """负例：未知参数在构造期拒；白名单外命令在命令检查拒（与审批版本无关）。"""

    registry, _, _ = build_paths(tmp_root)
    workspace = tmp_root / "workspace"
    workspace.mkdir()

    with pytest.raises(Exception) as error:
        build_action_request(
            registry.tool("exec.shell"),
            {"command": "print('ok')", "description": "d", "sandbox_permission": "x"},
            action_id="act-unknown",
            request_id="req-unknown",
            agent="dsh",
            agent_version="0.1.5-rc.1",
            trace_id="trace-b1",
            subject="local-user",
            roles=("owner",),
            permissions=registry.permissions_for(("owner",)),
            context=None,
            workspace=workspace,
            ttl_seconds=registry.grant_ttl_seconds,
        )
    assert "sandbox_permission" in str(error.value)

    wildcard = record(version="1.3", patterns={"command": ".*", "description": ".*"})
    (tmp_root / "allowlist").mkdir(exist_ok=True)
    outcome, _ = run_pre(
        tmp_root / "allowlist",
        registry,
        params={"command": "rm -rf src", "description": "d"},
        approval=wildcard,
        workspace=workspace,
    )
    assert outcome.decision.decision is Decision.BLOCK
    assert outcome.decision.reason_code is ReasonCode.COMMAND_NOT_ALLOWLISTED


# --------------------------------------------------------------------------- CLI approve --family


def request_document(workspace, **overrides):
    document = {
        "action_id": "family-act-1",
        "request_id": "family-act-1",
        "trace_id": "family-trace-1",
        "agent": "dsh",
        "agent_version": "0.1.5-rc.1",
        "tool_id": "exec.shell",
        "subject": "local-user",
        "roles": ["owner"],
        "params": {"command": "print('ok')", "description": "demo"},
        "workspace": str(workspace),
    }
    document.update(overrides)
    return document


def test_approve_family_signs_one_exact_union_ticket(tmp_root, capsys):
    registry, registry_path, approved_path = build_paths(tmp_root)
    workspace = tmp_root / "workspace"
    workspace.mkdir()
    request = tmp_root / "request.json"
    request.write_text(json.dumps(request_document(workspace)), encoding="utf-8")
    out = tmp_root / "approval.json"

    from enforcement.cli import main

    code = main(
        [
            "approve",
            "--request", str(request),
            "--out", str(out),
            "--granted-by", "dshznm",
            "--roles", "reviewer",
            "--binding", "pattern",
            "--max-uses", "3",
            "--family", "exec.shell:tests",
            "--param-pattern", "description=.*",
            "--registry", str(registry_path),
            "--approved", str(approved_path),
            "--audit", str(tmp_root / "audit.jsonl"),
            "--ledger", str(tmp_root / "ledger.jsonl"),
        ]
    )
    assert code == 0, capsys.readouterr().err
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == APPROVAL_SCHEMA_VERSION
    assert payload["approval_id"] == "approval-exec.shell-tests"
    assert payload["param_patterns"]["command"] == "^print[(]'ok'[)]$"
    assert "命令族 exec.shell:tests" in payload["note"]
    assert set(payload["param_patterns"]) == {"command", "description"}

    from enforcement.approvals import load_approval

    ticket = load_approval(out)
    verify(ticket, {"command": "print('ok')", "description": "demo"}, defaults=registry.tool("exec.shell").param_defaults())


def test_approve_family_refuses_a_sample_request_it_does_not_cover(tmp_root, capsys):
    _registry, registry_path, approved_path = build_paths(tmp_root)
    workspace = tmp_root / "workspace"
    workspace.mkdir()
    request = tmp_root / "request.json"
    request.write_text(
        json.dumps(
            request_document(
                workspace,
                params={"command": "print('ok')", "description": "demo", "timeoutMs": 30000},
            )
        ),
        encoding="utf-8",
    )
    out = tmp_root / "approval.json"

    from enforcement.cli import main

    code = main(
        [
            "approve",
            "--request", str(request),
            "--out", str(out),
            "--granted-by", "dshznm",
            "--roles", "reviewer",
            "--binding", "pattern",
            "--max-uses", "3",
            "--family", "exec.shell:tests",
            "--param-pattern", "description=.*",
            "--registry", str(registry_path),
            "--approved", str(approved_path),
            "--audit", str(tmp_root / "audit2.jsonl"),
            "--ledger", str(tmp_root / "ledger2.jsonl"),
        ]
    )
    assert code == 2
    assert "对不上它自己的样例请求" in capsys.readouterr().err
    assert not out.exists(), "自检失败时绝不许把条子写出去"


@pytest.mark.parametrize(
    "family, needle",
    [
        ("exec.other:tests", "不是本次请求的工具"),
        ("exec.shell:nope", "没有声明命令族"),
        ("exec.shell", "TOOL:FAMILY"),
        (":tests", "TOOL:FAMILY"),
    ],
)
def test_resolve_family_refuses_anything_it_cannot_prove(family, needle):
    from enforcement.cli import CliError, resolve_family

    with pytest.raises(CliError) as error:
        resolve_family(shell_spec(), family)
    assert needle in str(error.value)


def test_resolve_family_refuses_patterns_outside_the_allowlist():
    from enforcement.cli import CliError, resolve_family

    spec = shell_spec(
        command_families=[{"id": "wide", "patterns": ["^rm -rf( .*)?$"]}]
    )
    with pytest.raises(CliError) as error:
        resolve_family(spec, "exec.shell:wide")
    assert "不在注册表白名单里" in str(error.value)
