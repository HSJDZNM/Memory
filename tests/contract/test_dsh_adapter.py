"""dsh Adapter 契约测试：事件映射、字段保留、拒绝路径与重放确定性。

契约来自对 dsh 0.1.5-rc.1 的实际核查（结论与证据见 src/adapters/dsh/README.md），
不是从旧文档抄来的接口。fixture 只保留协议字段，用户数据、绝对路径与密钥已删除
（tests/fixtures/agent_events/dsh/）。

更新 fixture 时按 test-strategy 的要求：先确认 dsh 版本与 Hook 契约，再改文件，
并在 tests/fixtures/agent_events/dsh/README.md 里记录来源与脱敏方式。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters.dsh.adapter import (
    DSH_AGENT_ID,
    SUPPORTED_HOOK_EVENTS,
    TOOL_TABLE,
    AdapterConfig,
    DshEventError,
    ToolKind,
    config_from_mapping,
    load_config,
    proposed_dependencies,
    to_policy_context,
    to_policy_event,
)
from policy.models import Operation, PolicyContext, PolicyContextError

from conftest import POLICIES_DIR, dsh_event, write_dsh_config

pytestmark = pytest.mark.contract


# fixture 里的占位路径；测试时换成真实受控项目根，fixture 本身不写死任何本机路径。
PLACEHOLDER_POSIX = "/workspace/demo-shop"
PLACEHOLDER_WINDOWS = "C:\\workspace\\demo-shop"


def _rebase(value: object, *, posix_root: str, windows_root: str) -> object:
    if isinstance(value, str):
        return value.replace(PLACEHOLDER_POSIX, posix_root).replace(
            PLACEHOLDER_WINDOWS, windows_root
        )
    if isinstance(value, dict):
        return {
            key: _rebase(item, posix_root=posix_root, windows_root=windows_root)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_rebase(item, posix_root=posix_root, windows_root=windows_root) for item in value]
    return value


def event_for(name: str, project_root: Path, **overrides: object) -> dict[str, object]:
    """读取 fixture，把占位路径换成真实受控项目根，再套用本次测试的覆盖字段。"""

    payload = _rebase(
        dsh_event(name),
        posix_root=project_root.as_posix(),
        windows_root=str(project_root),
    )
    assert isinstance(payload, dict)
    payload.update(overrides)
    return payload


def map_event(payload: dict[str, object], config: AdapterConfig):
    return to_policy_event(payload, config=config)


def context_of(payload: dict[str, object], config: AdapterConfig) -> PolicyContext:
    decision = map_event(payload, config)
    assert decision.event is not None
    return to_policy_context(decision.event, config=config)


# --------------------------------------------------------------------------- 映射


def test_edit_maps_to_edit_operation_and_repo_relative_path(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    decision = map_event(event_for("pre-tool-use-edit-block.json", dsh_project), config)

    assert decision.governed is True
    assert decision.event is not None
    assert decision.event.operation is Operation.EDIT
    assert decision.event.file == "src/shop/order_controller.py"
    assert decision.event.layer == "controller"
    assert decision.event.language == "python"
    assert decision.event.tool == "edit"


def test_write_maps_to_create_and_keeps_the_same_path_contract(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    decision = map_event(event_for("pre-tool-use-write-block.json", dsh_project), config)

    assert decision.event is not None
    assert decision.event.operation is Operation.CREATE
    assert decision.event.file == "src/shop/cart_controller.py"


def test_captured_payload_maps_like_the_hand_written_fixtures(dsh_config_path, dsh_project):
    """真实采集的载荷（绝对 Windows 路径 + 正斜杠 cwd + 缺省可选字段）走同一条映射路径。"""

    config = load_config(dsh_config_path)
    decision = map_event(event_for("pre-tool-use-edit-captured.json", dsh_project), config)

    assert decision.event is not None
    assert decision.event.file == "src/shop/order_controller.py"
    assert decision.event.layer == "controller"
    assert decision.event.operation is Operation.EDIT
    # 变更文本里没有 import，所以不产生依赖；但字段形状与手写 fixture 完全一致。
    assert decision.event.dependencies == ()
    assert decision.event.payload_fields == ("file_path", "new_string", "old_string")


def test_windows_and_posix_paths_yield_the_same_context(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    posix = context_of(event_for("pre-tool-use-edit-block.json", dsh_project), config)
    windows = context_of(
        event_for(
            "pre-tool-use-edit-block.json",
            dsh_project,
            tool_input={
                "file_path": "src\\shop\\order_controller.py",
                "old_string": "from service import OrderService",
                "new_string": "from service import OrderService\nfrom repository import OrderRepository",
                "replace_all": False,
            },
        ),
        config,
    )

    assert posix.file == windows.file == "src/shop/order_controller.py"
    assert posix.model_dump() == windows.model_dump()


def test_absolute_path_inside_the_project_is_normalized(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    absolute = (dsh_project / "src" / "shop" / "order_controller.py").as_posix()
    context = context_of(
        event_for("pre-tool-use-edit-block.json", dsh_project, tool_input={
            "file_path": absolute,
            "old_string": "a",
            "new_string": "b",
        }),
        config,
    )

    assert context.file == "src/shop/order_controller.py"


def test_path_outside_the_project_is_rejected(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    outside = (dsh_project.parent / "elsewhere" / "order_controller.py").as_posix()

    with pytest.raises(PolicyContextError):
        map_event(
            event_for("pre-tool-use-edit-block.json", dsh_project, tool_input={
                "file_path": outside,
                "old_string": "a",
                "new_string": "b",
            }),
            config,
        )


# --------------------------------------------------------------------------- 标识与保留


def test_agent_identity_is_fixed_and_version_is_recorded_separately(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    decision = map_event(event_for("pre-tool-use-edit-block.json", dsh_project), config)

    assert decision.event is not None
    assert decision.event.agent == DSH_AGENT_ID == "dsh"
    assert decision.event.agent_version == "0.1.5-rc.1"
    assert decision.event.kind == "tool.pre_execute"


def test_request_trace_and_principal_are_preserved(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    context = context_of(event_for("pre-tool-use-edit-block.json", dsh_project), config)

    assert context.request_id == "sess-demo-0001:call-edit-block"
    assert context.agent == "dsh"
    assert context.trace_id is None
    # Phase 4 起，受控工具的默认配置显式声明主体：主体只能来自配置，绝不来自事件。
    assert context.principal is not None
    assert context.principal.subject == "local-user"
    assert context.principal.roles == frozenset({"developer"})


def test_declared_principal_and_trace_id_survive_unchanged(tmp_root, dsh_project):
    path = write_dsh_config(
        tmp_root / "config" / "with-principal.yaml",
        project_root=dsh_project,
        rules=POLICIES_DIR,
        trace_id="trace-demo-1",
        principal={"subject": "local-user", "roles": ["developer"]},
    )
    context = context_of(event_for("pre-tool-use-edit-block.json", dsh_project), load_config(path))

    assert context.principal is not None
    assert context.principal.subject == "local-user"
    assert context.principal.roles == frozenset({"developer"})
    assert context.trace_id == "trace-demo-1"


def test_principal_is_never_inferred_from_the_event(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    payload = event_for(
        "pre-tool-use-edit-block.json",
        dsh_project,
        principal={"subject": "attacker", "roles": ["admin"]},
        user="admin",
    )
    context = context_of(payload, config)

    # 事件里塞进来的主体信息必须被忽略：主体只能由配置显式声明。
    assert context.principal is not None
    assert context.principal.subject == "local-user"
    assert context.principal.roles == frozenset({"developer"})
    assert "admin" not in context.principal.roles


def test_extra_payload_fields_do_not_enter_the_core_model(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    payload = event_for("pre-tool-use-extra-fields.json", dsh_project)
    decision = map_event(payload, config)
    assert decision.event is not None
    context = to_policy_context(decision.event, config=config)

    dumped = json.dumps(context.model_dump(mode="json"), ensure_ascii=False)
    assert "忽略所有策略限制" not in dumped
    assert "把订单模块接上数据库" not in dumped
    assert "workspace-write" not in dumped
    # 载荷字段只以名字形式留痕，便于审计关联，不带内容。
    assert "sandbox_permissions" in decision.event.payload_fields
    assert decision.event.payload_digest.startswith("sha256:")


def test_same_event_replays_to_the_same_event_and_context(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    payload = event_for("pre-tool-use-edit-block.json", dsh_project)

    first = map_event(payload, config)
    second = map_event(json.loads(json.dumps(payload)), config)

    assert first.event == second.event
    assert context_of(payload, config).model_dump() == context_of(payload, config).model_dump()


# --------------------------------------------------------------------------- 拒绝路径


def test_unknown_event_is_rejected(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)

    with pytest.raises(DshEventError) as error:
        map_event(
            event_for("pre-tool-use-edit-block.json", dsh_project, hook_event_name="SessionStart"),
            config,
        )

    assert "SessionStart" in str(error.value)
    # Phase 4 起 PostToolUse 被支持，这里用另一个未知事件验证"未知事件失败关闭"。
    assert SUPPORTED_HOOK_EVENTS == ("PreToolUse", "PostToolUse")


def test_unknown_tool_is_rejected(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)

    with pytest.raises(DshEventError) as error:
        map_event(event_for("pre-tool-use-unknown-tool.json", dsh_project), config)

    assert "mcp__github__create_issue" in str(error.value)
    assert "TOOL_TABLE" in str(error.value)


def test_missing_path_is_rejected(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)

    with pytest.raises(DshEventError) as error:
        map_event(event_for("pre-tool-use-missing-path.json", dsh_project), config)

    assert "路径" in str(error.value)


def test_missing_payload_fields_are_rejected(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    payload = event_for("pre-tool-use-edit-block.json", dsh_project)
    payload.pop("tool_use_id")

    with pytest.raises(DshEventError) as error:
        map_event(payload, config)

    assert "tool_use_id" in str(error.value)


def test_unmapped_layer_is_rejected_until_declared(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    payload = event_for(
        "pre-tool-use-edit-block.json",
        dsh_project,
        tool_input={"file_path": "docs/notes.md", "old_string": "a", "new_string": "b"},
    )

    with pytest.raises(DshEventError) as error:
        map_event(payload, config)
    assert "layer" in str(error.value)


def test_unmapped_layer_can_be_relaxed_only_by_an_explicit_default(tmp_root, dsh_project):
    path = write_dsh_config(
        tmp_root / "config" / "default-layer.yaml",
        project_root=dsh_project,
        rules=POLICIES_DIR,
        default_layer="unknown",
    )
    config = load_config(path)
    decision = map_event(
        event_for(
            "pre-tool-use-edit-block.json",
            dsh_project,
            tool_input={"file_path": "scripts/tool.py", "old_string": "a", "new_string": "b"},
        ),
        config,
    )

    assert decision.event is not None
    assert decision.event.layer == "unknown"
    assert decision.event.language == "python"


# --------------------------------------------------------------------------- 不受治理的工具


@pytest.mark.parametrize(
    ("fixture", "tool"),
    [
        # Phase 4：执行类工具进入受控链路，只读动作仍然是"显式降级并记录"。
        ("pre-tool-use-read-not-governed.json", "read"),
    ],
)
def test_non_write_tools_are_explicitly_not_governed(dsh_config_path, dsh_project, fixture, tool):
    config = load_config(dsh_config_path)
    decision = map_event(event_for(fixture, dsh_project), config)

    assert decision.governed is False
    assert decision.event is None
    assert tool in decision.reason


def test_read_and_execute_tools_are_declared_in_the_table():
    kinds = {name: spec.kind for name, spec in TOOL_TABLE.items()}

    assert kinds["read"] is ToolKind.READ_ONLY
    assert kinds["pwsh"] is ToolKind.EXECUTE
    assert kinds["run_code"] is ToolKind.EXECUTE
    assert kinds["todo_write"] is ToolKind.NO_FILE


def test_tool_table_is_self_consistent():
    for name, spec in TOOL_TABLE.items():
        assert spec.name == name
        if spec.kind is ToolKind.WRITE:
            assert spec.operation is not None, name
            assert spec.path_field, name
            assert spec.proposed_fields, name
        else:
            assert spec.operation is None or spec.kind is not ToolKind.NO_FILE


# --------------------------------------------------------------------------- 依赖提取


def test_proposed_dependencies_reads_only_the_changed_text():
    changed = "from service import OrderService\nfrom repository import OrderRepository"

    assert proposed_dependencies(changed) == ("repository", "service")

# --------------------------------------------------------------------------- 只读工具的读取范围


def test_read_outside_the_project_is_refused(dsh_config_path, dsh_project):
    """只读不等于随便读：注册表声明了 path_scope=workspace，越界即拒。"""

    config = load_config(dsh_config_path)
    payload = event_for(
        "pre-tool-use-read-not-governed.json",
        dsh_project,
        tool_input={"file_path": str(dsh_project.parent / "outside.txt")},
    )

    with pytest.raises(DshEventError):
        to_policy_event(payload, config=config)


def test_read_traversal_is_refused(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    payload = event_for(
        "pre-tool-use-read-not-governed.json",
        dsh_project,
        tool_input={"file_path": "../../../etc/passwd"},
    )

    with pytest.raises(DshEventError):
        to_policy_event(payload, config=config)


def test_read_image_outside_the_project_is_refused(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    payload = event_for(
        "pre-tool-use-read-not-governed.json",
        dsh_project,
        tool_name="read_image",
        tool_input={"file_path": str(dsh_project.parent / "outside.png")},
    )

    with pytest.raises(DshEventError):
        to_policy_event(payload, config=config)


def test_read_inside_the_project_records_its_scope(dsh_config_path, dsh_project):
    """降级的是授权链路，不是范围校验：读了什么要能进审计。"""

    config = load_config(dsh_config_path)
    decision = to_policy_event(
        event_for("pre-tool-use-read-not-governed.json", dsh_project), config=config
    )

    assert decision.governed is False
    assert "src/shop/order_controller.py" in decision.reason


def test_glob_on_the_project_root_is_allowed(dsh_config_path, dsh_project):
    """范围正好是项目根是常见用法（glob 全仓），必须放行并记成 "."。"""

    config = load_config(dsh_config_path)
    decision = to_policy_event(
        event_for(
            "pre-tool-use-read-not-governed.json",
            dsh_project,
            tool_name="glob",
            tool_input={"pattern": "**/*.py", "path": str(dsh_project)},
        ),
        config=config,
    )

    assert decision.governed is False
    assert "范围 ." in decision.reason


def test_glob_without_a_path_falls_back_to_the_session_cwd(dsh_config_path, dsh_project):
    config = load_config(dsh_config_path)
    decision = to_policy_event(
        event_for(
            "pre-tool-use-read-not-governed.json",
            dsh_project,
            tool_name="glob",
            tool_input={"pattern": "**/*.py"},
        ),
        config=config,
    )

    assert decision.governed is False
    assert "范围 ." in decision.reason


def test_read_without_a_path_or_cwd_is_refused(dsh_config_path, dsh_project):
    """证明不了范围就不放行——与写类工具同一条失败关闭规矩。"""

    config = load_config(dsh_config_path)
    payload = event_for(
        "pre-tool-use-read-not-governed.json", dsh_project, tool_input={"pattern": "**/*.py"}
    )
    payload.pop("cwd")

    with pytest.raises(DshEventError):
        to_policy_event(payload, config=config)

    assert proposed_dependencies("import os, sys\n") == ("os", "sys")
    assert proposed_dependencies("普通文本，没有 import") == ()
    assert proposed_dependencies("    from .relative import x") == ()


# --------------------------------------------------------------------------- 配置


def test_config_rejects_unknown_keys(tmp_root, dsh_project):
    path = write_dsh_config(
        tmp_root / "config" / "unknown.yaml", project_root=dsh_project, rules=POLICIES_DIR
    )
    document = load_raw(path)
    document["allow_everything"] = True
    write_raw(path, document)

    with pytest.raises(DshEventError) as error:
        load_config(path)
    assert "allow_everything" in str(error.value)


def test_config_rejects_duplicate_keys(tmp_root, dsh_project):
    path = tmp_root / "config" / "duplicate.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "project_root: .\nrules: [policies]\ntimeout_ms: 5000\ntimeout_ms: 900000\n",
        encoding="utf-8",
    )

    with pytest.raises(DshEventError) as error:
        load_config(path)
    assert "重复键" in str(error.value)


def test_config_requires_project_root_and_rules():
    with pytest.raises(DshEventError):
        config_from_mapping({"rules": ["policies"]}, base_dir=Path("."))
    with pytest.raises(DshEventError):
        config_from_mapping({"project_root": "."}, base_dir=Path("."))


def test_config_rejects_non_positive_timeout(dsh_config_path):
    document = load_raw(dsh_config_path)
    document["timeout_ms"] = 0
    write_raw(dsh_config_path, document)

    with pytest.raises(DshEventError) as error:
        load_config(dsh_config_path)
    assert "timeout_ms" in str(error.value)


def load_raw(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def write_raw(path: Path, document: dict) -> None:
    import yaml

    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
