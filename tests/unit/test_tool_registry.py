"""Tool Registry 单元测试：数据化注册表的加载、审核哈希与不变量。

覆盖 Phase 4 文档第 1 步："每个工具记录稳定 ID、schema 版本、风险级别、允许参数、
所需权限、是否需要 post-check 和超时；运行时工具描述与已审核哈希不一致时拒绝使用。"
"""

from __future__ import annotations

import copy
import json

import pytest
import yaml

from enforcement.models import (
    ApprovalMode,
    DriverKind,
    EffectKind,
    RegistryError,
    RiskLevel,
    RollbackMode,
)
from enforcement.registry import (
    APPROVED_SCHEMA_VERSION,
    approve_registry,
    load_registry,
    registry_document_from_mapping,
    write_approved,
)
from enforcement_support import (
    ENFORCEMENT_APPROVED,
    ENFORCEMENT_REGISTRY,
    TEST_REGISTRY_TOOLS,
    registry_document,
    write_registry,
)

# --------------------------------------------------------------------------- 真实注册表


def test_repository_registry_loads_and_every_tool_is_approved():
    loaded = load_registry(ENFORCEMENT_REGISTRY, approved_path=ENFORCEMENT_APPROVED)
    registry = loaded.registry

    assert registry.tools, "注册表不能为空"
    for spec in registry.tools:
        assert registry.is_approved(spec), registry.approval_reason(spec)
    assert loaded.approved_document["registry_digest"] == registry.identity
    assert loaded.approved_document["approved_schema_version"] == APPROVED_SCHEMA_VERSION


def test_repository_registry_classifies_risk_the_way_the_phase_document_requires():
    registry = load_registry(ENFORCEMENT_REGISTRY, approved_path=ENFORCEMENT_APPROVED).registry

    assert registry.tool("fs.edit").risk is RiskLevel.REVERSIBLE_WRITE
    assert registry.tool("fs.write").risk is RiskLevel.REVERSIBLE_WRITE
    assert registry.tool("fs.read").risk is RiskLevel.READ_ONLY
    for tool_id in ("exec.pwsh", "exec.bash", "exec.run_code"):
        spec = registry.tool(tool_id)
        assert spec.risk is RiskLevel.PRIVILEGED_EXECUTION
        assert spec.approval is ApprovalMode.REQUIRED, tool_id
        assert "shell.exec" in spec.required_permissions
    assert registry.tool("exec.pwsh").driver is DriverKind.SHELL_COMMAND


def test_registry_identity_is_order_independent():
    document = registry_document()
    first = registry_document_from_mapping(copy.deepcopy(document))
    shuffled = copy.deepcopy(document)
    shuffled["tools"] = list(reversed(shuffled["tools"]))
    second = registry_document_from_mapping(shuffled)

    assert first.identity == second.identity
    assert [spec.id for spec in first.tools] == [spec.id for spec in second.tools]


# --------------------------------------------------------------------------- 结构校验


def test_every_exported_name_exists():
    """__all__ 里的名字必须真的存在：导出清单是契约，不是愿望清单。"""

    import enforcement.registry as registry_module

    missing = [name for name in registry_module.__all__ if not hasattr(registry_module, name)]

    assert missing == [], missing


def test_registry_rejects_duplicate_yaml_keys(tmp_root):
    path = tmp_root / "dup.yaml"
    path.write_text(
        "registry_schema_version: '1.0'\nversion: 1\nversion: 2\ntools: []\n", encoding="utf-8"
    )

    with pytest.raises(RegistryError) as error:
        load_registry(path, approved_path=None)
    assert "重复键" in str(error.value)


@pytest.mark.parametrize(
    ("mutation", "needle"),
    [
        (lambda doc: doc.update({"allow_everything": True}), "未知字段"),
        (lambda doc: doc["defaults"].update({"shell": "pwsh"}), "defaults"),
        (lambda doc: doc.update({"registry_schema_version": "9.9"}), "未知注册表协议版本"),
        (lambda doc: doc.update({"version": 0}), "version"),
        (lambda doc: doc.update({"tools": []}), "tools"),
        (lambda doc: doc["tools"][0].update({"risk": "whatever"}), "不合法"),
        (lambda doc: doc["tools"][1].update({"id": "fs.edit"}), "重复"),
        (
            lambda doc: doc["roles"].update({"developer": ["repo.write", "repo.delete"]}),
            "未声明的权限",
        ),
        (
            lambda doc: doc["tools"][3]["parameters"][2].update(
                {"requires_permission": "sandbox.nonexistent"}
            ),
            "未声明",
        ),
    ],
)
def test_registry_rejects_structural_problems(tmp_root, mutation, needle):
    document = registry_document()
    mutation(document)
    path = tmp_root / "registry.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")

    with pytest.raises(RegistryError) as error:
        load_registry(path, approved_path=None)
    if needle is not None:
        assert needle in str(error.value)


def test_registry_rejects_duplicate_tool_ids_and_names(tmp_root):
    duplicated_id = copy.deepcopy(list(TEST_REGISTRY_TOOLS))
    duplicated_id[1]["id"] = duplicated_id[0]["id"]
    _, approved = write_registry(tmp_root, tools=tuple(duplicated_id), approve=False)
    assert not approved.exists()
    with pytest.raises(RegistryError) as error:
        load_registry(tmp_root / "registry" / "tool-registry.yaml", approved_path=None)
    assert "重复" in str(error.value)

    duplicated_name = copy.deepcopy(list(TEST_REGISTRY_TOOLS))
    duplicated_name[1]["tool_name"] = duplicated_name[0]["tool_name"]
    write_registry(tmp_root, tools=tuple(duplicated_name), approve=False)
    with pytest.raises(RegistryError) as error:
        load_registry(tmp_root / "registry" / "tool-registry.yaml", approved_path=None)
    assert "已被占用" in str(error.value)


@pytest.mark.parametrize(
    ("index", "mutation", "needle"),
    [
        (3, lambda tool: tool.pop("approval"), "必须 approval=required"),
        (3, lambda tool: tool.update({"approval": "none"}), "必须 approval=required"),
        (3, lambda tool: tool.update({"post_checks": ["looks_fine"]}), "未知 post_check"),
        (
            3,
            lambda tool: tool.update({"rollback": "file_snapshot", "effect": "process"}),
            "file_snapshot",
        ),
        (
            3,
            lambda tool: tool["parameters"].append(
                {"name": "extra_list", "type": "string_list", "required": True}
            ),
            "max_items",
        ),
        (
            3,
            lambda tool: tool["parameters"].append(
                {"name": "note", "type": "string", "escalating_values": ["x"]}
            ),
            "requires_permission",
        ),
        (4, lambda tool: tool.pop("allowed_commands"), "allowed_commands"),
        (4, lambda tool: tool.pop("shell"), "shell 前缀"),
        (4, lambda tool: tool.pop("command_param"), "command_param"),
        (
            4,
            lambda tool: tool.update({"allowed_commands": ["("]}),
            "正则不合法",
        ),
    ],
)
def test_tool_declaration_invariants_are_enforced(tmp_root, index, mutation, needle):
    tools = copy.deepcopy(list(TEST_REGISTRY_TOOLS))
    mutation(tools[index])
    write_registry(tmp_root, tools=tuple(tools), approve=False)

    with pytest.raises(RegistryError) as error:
        load_registry(tmp_root / "registry" / "tool-registry.yaml", approved_path=None)
    assert needle in str(error.value), error.value


def test_only_read_only_tools_may_degrade_the_audit(tmp_root):
    """审计不可写时的降级只能给只读工具：任何有副作用的动作都必须失败关闭（复核 D5）。"""

    tools = copy.deepcopy(list(TEST_REGISTRY_TOOLS))
    tools[0].update({"audit_failure": "degrade"})  # fs.edit 是 reversible_write
    write_registry(tmp_root, tools=tuple(tools), approve=False)

    with pytest.raises(RegistryError) as error:
        load_registry(tmp_root / "registry" / "tool-registry.yaml", approved_path=None)
    assert "degrade" in str(error.value) and "只读" in str(error.value)

    # 只读工具声明 degrade 是允许的（注册表里的 fs.read 就是如此）
    registry = registry_document_from_mapping(registry_document())
    assert registry.tool("fs.read").audit_failure.value == "degrade"
    assert registry.tool("fs.edit").audit_failure.value == "block"


def test_read_only_tool_cannot_declare_a_write_effect(tmp_root):
    tools = copy.deepcopy(list(TEST_REGISTRY_TOOLS))
    tools[2].update({"effect": "file_write", "driver": "file_write"})
    write_registry(tmp_root, tools=tuple(tools), approve=False)

    with pytest.raises(RegistryError) as error:
        load_registry(tmp_root / "registry" / "tool-registry.yaml", approved_path=None)
    assert "read_only" in str(error.value)


def test_approval_role_must_be_declared(tmp_root):
    document = registry_document()
    document["approvals"] = {"require_role": "ghost"}
    write_registry(tmp_root, document=document, approve=False)

    with pytest.raises(RegistryError) as error:
        load_registry(tmp_root / "registry" / "tool-registry.yaml", approved_path=None)
    assert "require_role" in str(error.value)


# --------------------------------------------------------------------------- 已审核哈希


def test_schema_hash_changes_when_any_reviewed_field_changes():
    base = registry_document_from_mapping(registry_document())
    baseline = {spec.id: spec.schema_hash for spec in base.tools}

    mutators = {
        "参数上限": lambda tool: tool["parameters"][1].update({"max_chars": 1}),
        "风险级别": lambda tool: tool.update(
            {"risk": "destructive_write", "approval": "required"}
        ),
        "权限": lambda tool: tool.update({"required_permissions": []}),
        "审批": lambda tool: tool.update({"approval": "required"}),
        "post_check": lambda tool: tool.update({"post_checks": ["file_changed"]}),
        "超时": lambda tool: tool.update({"timeout_ms": 9999}),
        "驱动": lambda tool: tool.update({"driver": "file_write"}),
    }
    for label, mutate in mutators.items():
        tools = copy.deepcopy(list(TEST_REGISTRY_TOOLS))
        mutate(tools[0])
        changed = registry_document_from_mapping(registry_document(tools=tuple(tools)))
        assert changed.tool("fs.edit").schema_hash != baseline["fs.edit"], label
        # 其它工具不受影响：哈希是按工具计算的。
        assert changed.tool("fs.write").schema_hash == baseline["fs.write"], label


def test_schema_hash_is_stable_across_reloads(tmp_root):
    path, approved = write_registry(tmp_root)
    first = load_registry(path, approved_path=approved).registry.identity
    second = load_registry(path, approved_path=approved).registry.identity
    assert first == second


def test_unapproved_tool_is_unusable_and_reason_is_specific(tmp_root):
    path, approved = write_registry(tmp_root)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["tools"][0]["parameters"][1]["max_chars"] = 1  # 审核之后被改动
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")

    loaded = load_registry(path, approved_path=approved)
    spec = loaded.registry.tool("fs.edit")

    assert not loaded.registry.is_approved(spec)
    reason = loaded.registry.approval_reason(spec)
    assert "已审核值不一致" in reason
    assert loaded.registry.is_approved(loaded.registry.tool("fs.write"))


def test_governance_table_edit_unapproves_every_tool_until_reapproved(tmp_root):
    """只改 roles 里一条授权（工具描述一个字没变）也必须重新审核。

    registry.identity 覆盖 tools + roles + permissions + defaults + approvals，
    而逐工具 schema_hash 只看工具自己那一段：不比对治理表摘要的话，一次
    "给 developer 加 shell.exec" 的手改会让 10 个工具全都继续显示"已审核"。
    """

    path, approved = write_registry(tmp_root)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["roles"]["developer"] = ["repo.read", "repo.write", "shell.exec"]
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")

    loaded = load_registry(path, approved_path=approved)
    reasons = {spec.id: loaded.registry.approval_reason(spec) for spec in loaded.registry.tools}
    assert all(not loaded.registry.is_approved(spec) for spec in loaded.registry.tools), reasons
    assert all("角色 / 权限 / 默认值 / 审批角色表" in reason for reason in reasons.values())

    # 恢复路径必须仍然可达：重新审核之后全部工具可用（--approve 不读旧产物，不会被旧版本挡住）
    reloaded = registry_document_from_mapping(yaml.safe_load(path.read_text(encoding="utf-8")))
    write_approved(approve_registry(reloaded, reviewer="alice"), approved)
    recovered = load_registry(path, approved_path=approved)
    assert all(recovered.registry.is_approved(spec) for spec in recovered.registry.tools)


def test_registry_identity_digest_is_checked_not_only_recorded(tmp_root):
    """registry_digest 不能"记了不查"：治理表与全部工具哈希都对得上时，身份仍必须相等。

    覆盖关系是"治理表摘要 + 逐工具 schema_hash = registry_payload 的全部字段"，
    所以正常情况下 identity 必然等于已审核值；不等就说明有字段没被这两道检查看住。
    """

    path, approved = write_registry(tmp_root)
    document = json.loads(approved.read_text(encoding="utf-8"))
    document["registry_digest"] = "sha256:" + "0" * 64
    approved.write_text(json.dumps(document), encoding="utf-8")

    loaded = load_registry(path, approved_path=approved)
    reasons = [loaded.registry.approval_reason(spec) for spec in loaded.registry.tools]

    assert all(not loaded.registry.is_approved(spec) for spec in loaded.registry.tools)
    assert all("身份与已审核摘要不一致" in reason for reason in reasons), reasons


def test_pre_1_1_approved_artifact_is_rejected(tmp_root):
    """1.0 的清单没有治理表摘要：它证明不了治理表被审核过，必须重签（拒收未知版本）。"""

    path, approved = write_registry(tmp_root)
    document = json.loads(approved.read_text(encoding="utf-8"))
    document["approved_schema_version"] = "1.0"
    document.pop("governance_digest", None)
    approved.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(RegistryError) as error:
        load_registry(path, approved_path=approved)
    assert "未知已审核清单版本" in str(error.value)


def test_missing_approved_file_blocks_every_tool(tmp_root):
    path, _ = write_registry(tmp_root, approve=False)
    loaded = load_registry(path, approved_path=tmp_root / "registry" / "missing.json")

    for spec in loaded.registry.tools:
        assert not loaded.registry.is_approved(spec)
    assert "已审核清单里没有这条工具" in loaded.registry.approval_reason(loaded.registry.tools[0])


def test_approved_file_with_unknown_version_is_rejected(tmp_root):
    path, approved = write_registry(tmp_root)
    document = json.loads(approved.read_text(encoding="utf-8"))
    document["approved_schema_version"] = "2.0"
    approved.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(RegistryError) as error:
        load_registry(path, approved_path=approved)
    assert "未知已审核清单版本" in str(error.value)


def test_approve_records_reviewer_and_digest():
    registry = registry_document_from_mapping(registry_document())
    document = approve_registry(registry, reviewer="alice")

    assert document["reviewed_by"] == "alice"
    assert document["registry_digest"] == registry.identity
    assert document["governance_digest"] == registry.governance_digest
    assert set(document["tools"]) == {spec.id for spec in registry.tools}
    with pytest.raises(RegistryError):
        approve_registry(registry, reviewer="   ")


# --------------------------------------------------------------------------- 权限解析


def test_permissions_are_resolved_from_roles():
    registry = registry_document_from_mapping(registry_document())

    assert registry.permissions_for(["developer"]) == ("repo.read", "repo.write")
    assert registry.permissions_for(["owner"]) == (
        "repo.approve",
        "repo.read",
        "repo.write",
        "sandbox.escalate",
        "shell.exec",
    )
    # 未知角色不授予任何权限：失败关闭，且能被调用方解释。
    assert registry.permissions_for(["ghost"]) == ()
    assert registry.unknown_roles(["ghost", "developer"]) == ("ghost",)
    assert registry.approval_role_members() == ("reviewer", "owner") or set(
        registry.approval_role_members()
    ) == {"reviewer", "owner"}


def test_tool_lookup_by_id_and_by_name():
    registry = registry_document_from_mapping(registry_document())

    assert registry.tool("fs.edit").tool_name == "edit"
    assert registry.tool("nope") is None
    assert registry.tool_by_name("dsh", "edit").id == "fs.edit"
    assert registry.tool_by_name("DSH", "edit").id == "fs.edit"
    assert registry.tool_by_name("dsh", "nope") is None


def test_declared_effects_and_rollback_are_data():
    registry = registry_document_from_mapping(registry_document())

    assert registry.tool("fs.edit").effect is EffectKind.FILE_WRITE
    assert registry.tool("fs.edit").rollback is RollbackMode.FILE_SNAPSHOT
    assert registry.tool("fs.read").effect is EffectKind.NONE
    assert registry.tool("exec.process").driver is DriverKind.PROCESS_ARGV
    assert registry.tool("exec.shell").allowed_commands == (
        "^print[(]'ok'[)]$",
        "^echo( .*)?$",
    )
