"""Phase 6 契约：规范事件 schema、能力声明、支持矩阵与工具表一致性。

这些用例守的是"协议形状"，不是某一次判定的结果：
- 未知版本 / 未知字段 / 未知事件类型一律拒绝（不得静默忽略）；
- 能力声明必须自洽，能力不足必须显式降级，而不是假装能拦；
- manifest 的能力声明与代码里的工具表必须一致（改一处必须改另一处）；
- 一致性套件用的探针工作区与 fixture 必须真的存在（否则测的是空气）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from adapters.base import AdapterRegistry, ceiling_from_capabilities
from adapters.conformance import SCENARIOS, render_event
from adapters.loader import load_adapter_config, load_registry_from_repo
from adapters.models import (
    CANONICAL_EVENT_SCHEMA_VERSION,
    EVENT_TYPES,
    AdapterEventError,
    AdapterManifest,
    ApprovalCapability,
    BlockingCapability,
    EnforcementLevel,
    EventType,
    ManifestError,
    ParticipantCapability,
    ParticipantKind,
    ResponseKind,
    normalize_event_path,
    parse_canonical_event,
)

from conftest import REPO_ROOT

ADAPTERS_ROOT = REPO_ROOT / "adapters"
APPROVED_PATH = ADAPTERS_ROOT / "approved.json"


def _manifest_document(**overrides) -> dict:
    document = {
        "schema_version": "1.0",
        "agent_id": "demo-agent",
        "agent_version": "1.2.3",
        "display_name": "Demo Agent",
        "protocol": "hook-command",
        "protocol_version": "demo-hooks@1",
        "pre_hook": {"declared": True, "kind": "pre_hook", "response_kind": "exit_code"},
        "post_hook": {"declared": False, "kind": "request_gate", "response_kind": "exit_code"},
        "approval": "none",
        "blocking": "pre_execute",
        "response_kind": "exit_code",
        "event_types": ["tool.pre_execute"],
        "requested_enforcement": "full",
        "tools": [
            {
                "name": "edit",
                "aliases": ["edit"],
                "operation": "edit",
                "path_field": "path",
                "path_scope": "workspace",
            }
        ],
    }
    document.update(overrides)
    return document


# --------------------------------------------------------------------------- manifest


def test_manifest_rejects_unknown_field() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        AdapterManifest.model_validate(_manifest_document(unexpected="x"))


def test_manifest_rejects_unknown_event_type() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        AdapterManifest.model_validate(_manifest_document(event_types=["tool.teleport"]))


def test_manifest_rejects_unknown_manifest_version() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        AdapterManifest.model_validate(_manifest_document(schema_version="2.0"))


def test_manifest_refuses_full_enforcement_without_pre_hook() -> None:
    """能力不足必须显式失败：声明 full 却没有执行前钩子是配置错误。"""

    with pytest.raises((ManifestError, ValidationError)) as error:
        AdapterManifest.model_validate(
            _manifest_document(
                pre_hook={"declared": False, "kind": "request_gate", "response_kind": "exit_code"},
                post_hook={"declared": True, "kind": "post_hook", "response_kind": "exit_code"},
                blocking="post_only",
                event_types=["tool.post_execute"],
            )
        )
    assert "完整 enforcement" in str(error.value)


def test_manifest_rejects_blocking_without_any_tool_event() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        AdapterManifest.model_validate(
            _manifest_document(event_types=["agent.start"], tools=[])
        )


def test_declared_false_hook_must_not_be_post_hook() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        ParticipantCapability(declared=False, kind=ParticipantKind.POST_HOOK, response_kind=ResponseKind.EXIT_CODE)


def test_manifest_rejects_whitespace_or_underscore_wrapped_alias_conflict() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        AdapterManifest.model_validate(
            _manifest_document(
                tools=[
                    {
                        "name": "edit",
                        "aliases": ["Edit"],
                        "operation": "edit",
                        "path_field": "path",
                        "path_scope": "workspace",
                    },
                    {
                        "name": "write",
                        "aliases": ["Edit"],
                        "operation": "create",
                        "path_field": "path",
                        "path_scope": "workspace",
                    },
                ]
            )
        )


def test_manifest_rejects_non_workspace_path_scope() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        AdapterManifest.model_validate(
            _manifest_document(
                tools=[
                    {
                        "name": "edit",
                        "operation": "edit",
                        "path_field": "path",
                        "path_scope": "anywhere",
                    }
                ]
            )
        )


# --------------------------------------------------------------------------- 能力上限


def test_post_only_agent_is_read_only() -> None:
    """只有事后钩子的 Agent 不得被当成完整 enforcement（计划 §6）。"""

    manifest = AdapterManifest.model_validate(
        _manifest_document(
            pre_hook={"declared": False, "kind": "request_gate", "response_kind": "exit_code"},
            post_hook={"declared": True, "kind": "post_hook", "response_kind": "exit_code"},
            blocking="post_only",
            event_types=["tool.post_execute"],
            requested_enforcement=None,
        )
    )
    ceiling = ceiling_from_capabilities(manifest)
    assert ceiling.level is EnforcementLevel.READ_ONLY
    assert any("事后" in reason or "执行前" in reason for reason in ceiling.reasons)


def test_adapter_may_lower_its_own_ceiling() -> None:
    manifest = AdapterManifest.model_validate(
        _manifest_document(requested_enforcement="read_only")
    )
    ceiling = ceiling_from_capabilities(manifest)
    assert ceiling.level is EnforcementLevel.READ_ONLY
    assert ceiling.requested is EnforcementLevel.READ_ONLY


def test_unsupported_adapter_may_not_declare_tools() -> None:
    with pytest.raises((ManifestError, ValidationError)):
        AdapterManifest.model_validate(
            _manifest_document(
                requested_enforcement="unsupported",
                pre_hook={
                    "declared": False,
                    "kind": "request_gate",
                    "response_kind": "json",
                },
                post_hook={
                    "declared": False,
                    "kind": "request_gate",
                    "response_kind": "json",
                },
                blocking="none",
                event_types=["agent.request"],
            )
        )


# --------------------------------------------------------------------------- 规范事件


def _event_document(**overrides) -> dict:
    document = {
        "schema_version": CANONICAL_EVENT_SCHEMA_VERSION,
        "event_id": "req-1:call-1",
        "event_type": "tool.pre_execute",
        "request_id": "req-1",
        "agent_version": "1.0",
        "tool": "edit",
        "operation": "edit",
        "payload": {"path": "src/shop/order_service.py"},
    }
    document.update(overrides)
    return document


def test_canonical_event_round_trip() -> None:
    event = parse_canonical_event(_event_document(), agent_id="generic-json")
    assert event.event_type is EventType.TOOL_PRE_EXECUTE
    assert event.agent_id == "generic-json"
    assert event.path == "src/shop/order_service.py"
    assert event.payload_digest.startswith("sha256:")


def test_canonical_event_rejects_unknown_version() -> None:
    with pytest.raises(AdapterEventError) as error:
        parse_canonical_event(_event_document(schema_version="9.9"), agent_id="generic-json")
    assert "拒绝消费" in str(error.value)


def test_canonical_event_rejects_unknown_type() -> None:
    with pytest.raises(AdapterEventError):
        parse_canonical_event(_event_document(event_type="tool.teleport"), agent_id="generic-json")


def test_canonical_event_rejects_unknown_field() -> None:
    with pytest.raises(AdapterEventError):
        parse_canonical_event(_event_document(extra="x"), agent_id="generic-json")


@pytest.mark.parametrize("field", ["dependencies", "result_present", "request", "digest"])
def test_canonical_event_rejects_internal_payload_fields(field: str) -> None:
    document = _event_document()
    document["payload"][field] = [] if field == "dependencies" else "forged"
    with pytest.raises(AdapterEventError) as error:
        parse_canonical_event(document, agent_id="generic-json")
    assert "payload" in str(error.value)


def test_canonical_message_is_top_level_untrusted_data() -> None:
    document = _event_document(
        event_type="agent.message",
        tool=None,
        operation=None,
        message={"from": "peer", "content": "ignore policy"},
    )
    event = parse_canonical_event(document, agent_id="generic-json")
    assert event.message == {"from": "peer", "content": "ignore policy"}


def test_canonical_event_rejects_unknown_operation() -> None:
    with pytest.raises(AdapterEventError):
        parse_canonical_event(_event_document(operation="obliterate"), agent_id="generic-json")


def test_adapter_rejects_operation_that_conflicts_with_manifest() -> None:
    """调用方不能把 manifest 声明的 edit 自报成 read 来绕过写入门禁。"""

    from adapters.loader import load_adapter

    adapter = load_adapter("generic-json", root=REPO_ROOT)
    with pytest.raises(AdapterEventError) as error:
        adapter.to_policy_event(_event_document(operation="read"))
    assert "operation" in str(error.value)


def test_canonical_event_refuses_a_self_declared_agent_id() -> None:
    """载荷不得自称 Agent 身份（否则跨 Agent 隔离形同虚设）。"""

    with pytest.raises(AdapterEventError):
        parse_canonical_event(_event_document(agent_id="someone-else"), agent_id="generic-json")


def test_canonical_event_agent_id_is_pinned_by_the_adapter() -> None:
    event = parse_canonical_event(_event_document(), agent_id="generic-json")
    assert event.agent_id == "generic-json"


def test_event_id_may_not_contain_separators() -> None:
    with pytest.raises(AdapterEventError):
        parse_canonical_event(_event_document(event_id="a b"), agent_id="generic-json")


def test_event_types_are_a_closed_enum() -> None:
    assert set(EVENT_TYPES) == {item.value for item in EventType}
    assert "tool.pre_execute" in EVENT_TYPES


# --------------------------------------------------------------------------- 路径


def test_normalize_event_path_uses_the_given_base() -> None:
    workspace = REPO_ROOT / "tests" / "fixtures" / "agent_events" / "workspace"
    assert (
        normalize_event_path("src/shop/order_service.py", workspace=workspace, path_base=workspace)
        == "src/shop/order_service.py"
    )


def test_normalize_event_path_rejects_relative_escape() -> None:
    workspace = REPO_ROOT / "tests" / "fixtures" / "agent_events" / "workspace"
    with pytest.raises(AdapterEventError) as error:
        normalize_event_path("../outside.py", workspace=workspace, path_base=workspace)
    assert "越界" in str(error.value) or "逃出" in str(error.value)


def test_normalize_event_path_rejects_absolute_escape() -> None:
    workspace = REPO_ROOT / "tests" / "fixtures" / "agent_events" / "workspace"
    outside = REPO_ROOT.parent / "outside-workspace.py"
    with pytest.raises(AdapterEventError):
        normalize_event_path(str(outside), workspace=workspace)


def test_normalize_event_path_allows_the_workspace_root() -> None:
    workspace = REPO_ROOT / "tests" / "fixtures" / "agent_events" / "workspace"
    assert normalize_event_path(".", workspace=workspace) == "."
    assert normalize_event_path(str(workspace), workspace=workspace) == "."

@pytest.mark.parametrize("raw", ["..", "../..", "./..", chr(92).join(["..", ".."]), "./../"])
def test_escape_shaped_dot_paths_are_not_read_as_the_workspace_root(raw: str) -> None:
    """只有纯点斜线写法才是工作区根：`strip("./")` 会把 `..` 一起剥成空串。

    旧判据 `raw.strip("./") == ""` 对 ".."、"../.."、"./.." 全为真——它们被当成工作区根
    返回 "."，下面那条 `..` 拒绝根本走不到：一次逃逸被静默改写成「范围正好是项目根」，
    而这份归一化的结果要驱动 layer / language / 规则范围。
    """

    workspace = REPO_ROOT / "tests" / "fixtures" / "agent_events" / "workspace"
    with pytest.raises(AdapterEventError):
        normalize_event_path(raw, workspace=workspace)


def test_dot_slash_spellings_of_the_workspace_root_still_resolve_to_the_root() -> None:
    """根写法的等价形态一个都不收紧：".", "./", "././" 都是范围等于项目根。"""

    workspace = REPO_ROOT / "tests" / "fixtures" / "agent_events" / "workspace"
    for raw in (".", "./", "././", ".//"):
        assert normalize_event_path(raw, workspace=workspace) == ".", raw
    # "..." 既不是根写法也不是逃逸：它保持成自己的名字，不得被折叠成 "."
    assert normalize_event_path("...", workspace=workspace) == "..."

def test_path_containment_follows_the_path_flavour_case_semantics(tmp_root: Path) -> None:
    """包含性判定的大小写口径必须跟路径实现走，不能自己 lower()。

    WindowsPath 的比较不区分大小写（PROJ 与 proj 是同一个目录），PurePosixPath 区分。
    旧实现两边都 lower()：在**区分大小写**的文件系统上，只差大小写的兄弟目录会被判成
    「在工作区内」，一个范围外的绝对路径于是按范围内的文件被评估（并被报成 secret.py）。
    """

    from adapters.models import _within

    anchor = tmp_root / "proj"
    anchor.mkdir()
    sibling = tmp_root / "PROJ" / "secret.py"

    inside = anchor in sibling.parents  # 路径实现自己给出的答案
    assert _within(sibling, anchor) == inside

    if inside:
        # Windows：同一个目录，按工作区相对路径报出来
        assert normalize_event_path(str(sibling), workspace=anchor) == "secret.py"
    else:
        # POSIX：兄弟目录，越界一律拒绝
        with pytest.raises(AdapterEventError):
            normalize_event_path(str(sibling), workspace=anchor)


def test_phase_six_glob_double_star_slash_matches_zero_directories() -> None:
    """`**/` 匹配零个或多个目录：层与语言的映射不得漏掉根目录文件。

    旧实现把 `**` 一律翻成 `.*`，于是 `**/*_service.py` 匹配不到根目录的
    `order_service.py`：它掉到更宽的 `**/*.py`（module），或者干脆没有 layer
    映射被拒绝；language 掉到 default_language（text）→ 依赖维度静默为空。
    这就是 G8 的形态：配置看着覆盖了，实际漏掉一整个层级。
    """

    from adapters.loader import load_adapter

    adapter = load_adapter("dsh", root=REPO_ROOT)
    assert adapter.layer_for("order_controller.py") == "controller"
    assert adapter.layer_for("order_service.py") == "service"
    assert adapter.layer_for("order_repository.py") == "repository"
    assert adapter.layer_for("order.py") == "module"
    assert adapter.layer_for("README.md") == "docs"
    assert adapter.language_for("order.py") == "python"


def test_phase_six_glob_semantics_match_the_validator_matcher() -> None:
    """跨模块对照：Phase 6 的 `_compile_glob` 与验证器层的匹配器必须同一答案。

    `src/validators/globs.py` 的 docstring 把这条一致性写成「由测试钉住」；
    Phase 6 的这份实现此前漏了 `**/` 的零层语义，正是 G8 的另一半。
    """

    from adapters.base import _compile_glob
    from validators.globs import glob_match

    patterns = (
        "**/*_controller.py",
        "**/*_service.py",
        "**/*_repository.py",
        "**/*.py",
        "**/*.md",
        "src/**/*.py",
        "**/*",
        "**",
        "*.py",
        "?x.py",
    )
    paths = (
        "README.md",
        "order.py",
        "order_service.py",
        "docs/notes.md",
        "docs/a/b.md",
        "src/a.py",
        "src/pkg/a.py",
        "x/y/z.bin",
    )
    mismatches = [
        (pattern, path)
        for pattern in patterns
        for path in paths
        if bool(_compile_glob(pattern).match(path)) != glob_match(pattern, path)
    ]
    assert not mismatches, mismatches
    # 对照必须非空转：至少有一条「零层」命中，否则两边全 False 也会通过。
    assert glob_match("**/*.py", "order.py")


# --------------------------------------------------------------------------- 注册表


def test_repository_registry_loads_and_is_approved() -> None:
    registry = load_registry_from_repo(REPO_ROOT)
    listing = registry.as_list()
    assert set(listing.ids) == {"dsh", "generic-json", "legacy-post-only"}
    for item in listing.descriptors:
        assert item.approved, item.agent_id
        assert item.enforcement is not EnforcementLevel.UNSUPPORTED


def test_support_matrix_reports_current_full_and_read_only_states() -> None:
    """当前清单有 full/read_only；unsupported 是受控状态，但没有活动条目。"""

    listing = load_registry_from_repo(REPO_ROOT).as_list()
    levels = {item.agent_id: item.enforcement for item in listing.descriptors}
    assert levels["dsh"] is EnforcementLevel.FULL
    assert levels["legacy-post-only"] is EnforcementLevel.READ_ONLY
    assert listing.governed() and listing.read_only()
    assert not listing.unsupported()


def test_registry_detects_manifest_drift() -> None:
    """改了能力声明却忘记重新审核 → 整次加载失败（失败关闭）。"""

    registry = AdapterRegistry.load(ADAPTERS_ROOT, approved_path=APPROVED_PATH)
    approved = json.loads(APPROVED_PATH.read_text(encoding="utf-8"))
    tampered = json.loads(json.dumps(approved))
    tampered["adapters"]["dsh"]["manifest_digest"] = "sha256:" + "0" * 64
    drift = AdapterRegistry(
        [registry.manifest("dsh")],
        approved=tampered,
    )
    with pytest.raises(Exception):
        drift.check_approved()
    listing = drift.as_list()
    assert not listing.get("dsh").approved


def test_registry_requires_an_approval_record() -> None:
    with pytest.raises(Exception):
        AdapterRegistry.load(ADAPTERS_ROOT, approved_path=ADAPTERS_ROOT / "missing.json")


def test_approved_fixtures_exist() -> None:
    """能力声明里登记的兼容性 fixture 必须真的存在（否则升级检查是空的）。"""

    for descriptor in load_registry_from_repo(REPO_ROOT).as_list().descriptors:
        assert descriptor.fixtures, descriptor.agent_id
        for name in descriptor.fixtures:
            assert (REPO_ROOT / name).is_file(), f"{descriptor.agent_id}/{name}"


def test_declared_fixture_paths_resolve() -> None:
    """fixture 路径是仓库相对的：本目录下的样本与 Phase 2 的共享样本都要能找到。"""

    for manifest_path in sorted(ADAPTERS_ROOT.glob("*/manifest.yaml")):
        document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest = AdapterManifest.model_validate(document)
        assert manifest.fixtures, manifest.agent_id
        for name in manifest.fixtures:
            candidate = REPO_ROOT / name
            assert candidate.is_file(), f"{manifest.agent_id}: {name}"


# --------------------------------------------------------------------------- 工具表一致性


def test_dsh_manifest_matches_the_phase_2_tool_table() -> None:
    """Phase 2 的代码工具表与 Phase 6 的能力声明必须描述同一件事。

    两边不一致时最坏的结果是"声明了 pre-execute 阻断，实际工具表里没有它"——
    那样的 Agent 会在升级后静默失去治理。
    """

    from adapters.dsh.adapter import TOOL_TABLE

    manifest = load_registry_from_repo(REPO_ROOT).manifest("dsh")
    declared = {item.name for item in manifest.tools}
    assert declared == set(TOOL_TABLE), sorted(declared ^ set(TOOL_TABLE))

    for item in manifest.tools:
        spec = TOOL_TABLE[item.name]
        assert item.operation == spec.operation or (item.operation is None and spec.operation is None)
        assert item.path_field == spec.path_field
        assert set(item.proposed_fields) == set(spec.proposed_fields)


def test_dsh_conformance_adapter_matches_the_manifest() -> None:
    """Phase 6 的 dsh Adapter 与 manifest 必须给出同一张工具表。"""

    from adapters.loader import load_adapter

    adapter = load_adapter("dsh", root=REPO_ROOT)
    manifest = adapter.manifest
    assert set(adapter.tool_names()) == {item.name for item in manifest.tools}
    # 别名表覆盖 Agent 侧的真实工具名。
    assert adapter.canonical_tool_name("edit") == "edit"
    assert adapter.canonical_tool_name("str_replace_editor") == "str_replace_editor"


def test_adapter_configs_load() -> None:
    for path in sorted(ADAPTERS_ROOT.glob("*/adapter.yaml")):
        config = load_adapter_config(path)
        assert config.rules
        assert config.project_root


# --------------------------------------------------------------------------- 场景渲染


def test_every_scenario_renders_for_every_adapter() -> None:
    """场景渲染器必须能为每个 Adapter 产出事件（否则套件静默少测）。"""

    from adapters.loader import load_adapters

    workspace = REPO_ROOT / "tests" / "fixtures" / "agent_events" / "workspace"
    adapters = load_adapters(
        ["dsh", "generic-json", "legacy-post-only"], root=REPO_ROOT
    )
    for adapter in adapters.values():
        for scenario in SCENARIOS:
            try:
                raw = render_event(
                    adapter,
                    scenario,
                    index=0,
                    workspace=workspace,
                    outside=str(REPO_ROOT.parent / "outside.py"),
                )
            except AdapterEventError as error:
                # 只读上限的 Adapter 声明的就是"没有执行前事件"：这里的失败是
                # **能力事实**，不是渲染缺陷——但它必须说出来，不能静默跳过。
                assert "不支持事件" in str(error), error
                continue
            assert isinstance(raw, dict)
            assert raw


# --------------------------------------------------------------------------- 决策翻译


def _decision_result(**overrides):
    """一份最小但完整的决策载荷（含协议 1.1 的三个新通道键）。"""

    from policy.models import ValidationResult

    document = {
        "request_id": "req-1",
        "trace_id": "trace-1",
        "decision": "allow",
        "rule_set_hash": "sha256:" + "a" * 64,
        "matched_rules": ["ARCH-001@1"],
        "skipped_rules": [{"rule_id": "STYLE-001@1", "reasons": ["language 不匹配"]}],
        "required_action": None,
    }
    document.update(overrides)
    return ValidationResult.model_validate(document)


def test_generic_json_response_translates_the_full_decision_payload() -> None:
    """ValidationResult 与协议载荷 dict 是文档写明的两条主路径，必须都能用。

    字段白名单漏掉 rule_set_hash / skipped_rules / pending_findings 时，
    两条路径都以「未知字段」抛错——通用 JSON 响应实际上无路可走。
    """

    from adapters.json_adapter import agent_response_from_decision

    result = _decision_result()
    from_result = agent_response_from_decision(result)
    from_payload = agent_response_from_decision(result.to_decision_dict())
    assert from_result == from_payload
    assert from_result["decision"] == "allow"
    assert from_result["executable"] is True


def test_generic_json_response_accepts_the_pending_findings_channel() -> None:
    """pending_findings 是独立通道（不是违规）：它同样不得被当成未知字段拒绝。"""

    from adapters.json_adapter import agent_response_from_decision

    finding = {
        "rule_id": "TEST-001@1",
        "rule_version": 1,
        "severity": "warning",
        "message": "选中的测试因项目内实现还不存在而未能收集",
        "evidence": {"kind": "pytest", "subject": "tests/test_x.py", "value": "pending"},
    }
    result = _decision_result(decision="allow_with_warnings", pending_findings=[finding])
    response = agent_response_from_decision(result)
    assert response["executable"] is True


def test_generic_json_response_still_rejects_unknown_decision_field() -> None:
    """补全白名单不等于放宽：协议之外的字段仍然拒绝，不得静默丢弃。"""

    from adapters.json_adapter import agent_response_from_decision

    payload = _decision_result().to_decision_dict()
    payload["severity_counts"] = {"warning": 1}
    with pytest.raises(AdapterEventError) as error:
        agent_response_from_decision(payload)
    assert "未知字段" in str(error.value)
