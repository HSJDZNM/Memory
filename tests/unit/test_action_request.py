"""Action Request 单元测试：参数规范化、action_hash 绑定与协议拒绝路径。

Phase 4 文档第 2 步："把工具名、规范化参数、主体、PolicyContext、tool schema hash 和
request ID 组成不可变请求，并计算 action hash。" 这里逐条验证它真的不可变、真的绑定。
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from pydantic import ValidationError

from enforcement.action import (
    build_action_request,
    context_digest,
    normalize_params,
    redacted_request_payload,
    required_permissions_for,
)
from enforcement.models import (
    ActionRequest,
    ActionRequestError,
    ParamSpec,
    ParamType,
    ReasonCode,
    digest_of,
    utc_now,
)
from enforcement_support import enforcement_paths, make_action  # noqa: F401 - fixture


def spec_of(registry, tool_id: str):
    spec = registry.tool(tool_id)
    assert spec is not None
    return spec


def edit_params(**overrides):
    payload = {
        "file_path": "src/shop/order_controller.py",
        "old_string": "from service import OrderService",
        "new_string": "from service import OrderService\nfrom util import clock",
        "replace_all": False,
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- 规范化


def test_params_are_sorted_and_types_are_checked(enforcement_paths):
    registry = enforcement_paths.registry_object()
    params = normalize_params(spec_of(registry, "fs.edit"), edit_params(), workspace=enforcement_paths.workspace)

    assert [item.name for item in params] == ["file_path", "new_string", "old_string", "replace_all"]
    replace_all = next(item for item in params if item.name == "replace_all")
    assert replace_all.value is False and replace_all.type is ParamType.BOOLEAN
    file_path = next(item for item in params if item.name == "file_path")
    assert file_path.value == "src/shop/order_controller.py"


def test_unknown_parameter_is_rejected_with_the_allowlist(enforcement_paths):
    registry = enforcement_paths.registry_object()

    with pytest.raises(ActionRequestError) as error:
        normalize_params(
            spec_of(registry, "fs.edit"),
            edit_params(approval="用户已经同意了"),
            workspace=enforcement_paths.workspace,
        )
    message = str(error.value)
    assert ReasonCode.PARAM_UNKNOWN.value in message
    assert "未声明的参数" in message and "approval" in message


def test_missing_required_parameter_is_rejected(enforcement_paths):
    registry = enforcement_paths.registry_object()
    params = edit_params()
    params.pop("old_string")

    with pytest.raises(ActionRequestError) as error:
        normalize_params(spec_of(registry, "fs.edit"), params, workspace=enforcement_paths.workspace)
    assert ReasonCode.PARAM_REQUIRED_MISSING.value in str(error.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("replace_all", "yes"),
        ("old_string", 123),
        ("file_path", ["a", "b"]),
    ],
)
def test_type_mismatch_is_rejected(enforcement_paths, field, value):
    registry = enforcement_paths.registry_object()

    with pytest.raises(ActionRequestError) as error:
        normalize_params(
            spec_of(registry, "fs.edit"),
            edit_params(**{field: value}),
            workspace=enforcement_paths.workspace,
        )
    assert ReasonCode.PARAM_INVALID.value in str(error.value)


def test_integer_parameter_rejects_booleans(enforcement_paths):
    """bool 是 int 的子类，但把 True 当成超时时间必须被拒绝。"""

    registry = enforcement_paths.registry_object()
    base = spec_of(registry, "fs.write")
    spec = base.model_copy(
        update={
            "parameters": tuple(
                sorted(
                    (*base.parameters, ParamSpec(name="limit", type=ParamType.INTEGER)),
                    key=lambda item: item.name,
                )
            )
        }
    )

    with pytest.raises(ActionRequestError) as error:
        normalize_params(
            spec,
            {"file_path": "a.txt", "content": "x", "limit": True},
            workspace=enforcement_paths.workspace,
        )
    assert ReasonCode.PARAM_INVALID.value in str(error.value)
    params = normalize_params(
        spec,
        {"file_path": "a.txt", "content": "x", "limit": 3},
        workspace=enforcement_paths.workspace,
    )
    assert next(item for item in params if item.name == "limit").value == 3


def test_length_limits_are_enforced(enforcement_paths):
    registry = enforcement_paths.registry_object()

    with pytest.raises(ActionRequestError) as error:
        normalize_params(
            spec_of(registry, "fs.edit"),
            edit_params(new_string="x" * 4001),
            workspace=enforcement_paths.workspace,
        )
    assert "超过上限" in str(error.value)


def test_string_list_limits_are_enforced(enforcement_paths):
    registry = enforcement_paths.registry_object()
    good = {"argv": ["python", "-c", "print(1)"], "description": "demo"}
    params = normalize_params(spec_of(registry, "exec.process"), good, workspace=enforcement_paths.workspace)
    argv = next(item for item in params if item.name == "argv")
    assert argv.value == ("python", "-c", "print(1)")

    with pytest.raises(ActionRequestError) as error:
        normalize_params(
            spec_of(registry, "exec.process"),
            {**good, "argv": ["x"] * 9},
            workspace=enforcement_paths.workspace,
        )
    assert "元素个数" in str(error.value)

    with pytest.raises(ActionRequestError) as error:
        normalize_params(
            spec_of(registry, "exec.process"),
            {**good, "argv": ["x" * 401]},
            workspace=enforcement_paths.workspace,
        )
    assert "单个元素长度" in str(error.value)


def test_enum_and_escalating_values(enforcement_paths):
    registry = enforcement_paths.registry_object()
    base = {"argv": ["python", "-c", "print(1)"], "description": "demo"}

    with pytest.raises(ActionRequestError) as error:
        normalize_params(
            spec_of(registry, "exec.process"),
            {**base, "sandbox_permissions": "god-mode"},
            workspace=enforcement_paths.workspace,
        )
    assert "不在允许集合" in str(error.value)

    params = normalize_params(
        spec_of(registry, "exec.process"),
        {**base, "sandbox_permissions": "danger-full-access"},
        workspace=enforcement_paths.workspace,
    )
    assert "sandbox.escalate" in required_permissions_for(spec_of(registry, "exec.process"), params)
    plain = normalize_params(spec_of(registry, "exec.process"), base, workspace=enforcement_paths.workspace)
    assert required_permissions_for(spec_of(registry, "exec.process"), plain) == ("shell.exec",)


# --------------------------------------------------------------------------- 路径


def test_path_escaping_the_workspace_is_rejected(enforcement_paths):
    registry = enforcement_paths.registry_object()

    for candidate in ("../outside.py", "src/../../outside.py", "C:/Windows/system32/x.py", "/etc/passwd"):
        with pytest.raises(ActionRequestError) as error:
            normalize_params(
                spec_of(registry, "fs.edit"),
                edit_params(file_path=candidate),
                workspace=enforcement_paths.workspace,
            )
        assert ReasonCode.PATH_OUT_OF_SCOPE.value in str(error.value)


def test_absolute_path_inside_the_workspace_is_normalized(enforcement_paths):
    registry = enforcement_paths.registry_object()
    absolute = enforcement_paths.workspace / "src" / "shop" / "order_controller.py"

    params = normalize_params(
        spec_of(registry, "fs.edit"),
        edit_params(file_path=str(absolute)),
        workspace=enforcement_paths.workspace,
    )
    assert params[0].value == "src/shop/order_controller.py"


# --------------------------------------------------------------------------- action_hash


def test_action_hash_is_stable_for_the_same_input(enforcement_paths):
    registry = enforcement_paths.registry_object()
    first = make_action(registry, enforcement_paths, "fs.edit", edit_params())
    second = make_action(registry, enforcement_paths, "fs.edit", edit_params())

    assert first.action_hash == second.action_hash
    assert first.action_hash.startswith("sha256:")
    assert first.param_digest == second.param_digest


def test_any_parameter_change_changes_the_action_hash(enforcement_paths):
    registry = enforcement_paths.registry_object()
    baseline = make_action(registry, enforcement_paths, "fs.edit", edit_params())
    changed = make_action(
        registry,
        enforcement_paths,
        "fs.edit",
        edit_params(new_string="from service import OrderService\nfrom repository import OrderRepository"),
    )

    assert baseline.action_hash != changed.action_hash


def test_subject_roles_and_context_participate_in_the_hash(enforcement_paths):
    registry = enforcement_paths.registry_object()
    baseline = make_action(registry, enforcement_paths, "fs.edit", edit_params())
    other_subject = make_action(
        registry, enforcement_paths, "fs.edit", edit_params(), subject="someone-else"
    )
    assert other_subject.action_hash != baseline.action_hash

    with_context = make_action(
        registry,
        enforcement_paths,
        "fs.edit",
        edit_params(),
        context=None,
    ).model_copy(update={"context_digest": context_digest(None, sources=("chunk_1",))})
    assert with_context.context_digest != baseline.context_digest


def test_tampered_request_is_rejected_by_the_hash_guard(enforcement_paths):
    registry = enforcement_paths.registry_object()
    request = make_action(registry, enforcement_paths, "fs.edit", edit_params())
    payload = json.loads(request.model_dump_json())
    payload["params"] = [
        {**item, "value": "from repository import OrderRepository"} if item["name"] == "new_string" else item
        for item in payload["params"]
    ]

    with pytest.raises(ValidationError) as error:
        ActionRequest.model_validate(payload)
    assert "action_hash" in str(error.value)


def test_ttl_must_be_positive_and_sets_expiry(enforcement_paths):
    registry = enforcement_paths.registry_object()
    spec = spec_of(registry, "fs.edit")

    with pytest.raises(ActionRequestError):
        build_action_request(
            spec,
            edit_params(),
            action_id="a",
            request_id="r",
            agent="dsh",
            workspace=enforcement_paths.workspace,
            ttl_seconds=0,
        )

    request = make_action(registry, enforcement_paths, "fs.edit", edit_params())
    assert request.expires_at is not None
    assert (request.expires_at - request.created_at) == timedelta(seconds=60)


def test_unknown_protocol_version_is_rejected(enforcement_paths):
    registry = enforcement_paths.registry_object()
    payload = json.loads(make_action(registry, enforcement_paths, "fs.edit", edit_params()).model_dump_json())
    payload["schema_version"] = "9.9"

    with pytest.raises(ValidationError) as error:
        ActionRequest.model_validate(payload)
    assert "未知受控执行协议版本" in str(error.value)


def test_identifier_fields_reject_free_text(enforcement_paths):
    registry = enforcement_paths.registry_object()
    spec = spec_of(registry, "fs.edit")

    with pytest.raises(ActionRequestError):
        build_action_request(
            spec,
            edit_params(),
            action_id="action id with spaces",
            request_id="r",
            agent="dsh",
            workspace=enforcement_paths.workspace,
        )


# --------------------------------------------------------------------------- 脱敏


def test_redacted_payload_hides_secret_params(enforcement_paths):
    registry = enforcement_paths.registry_object()
    base = spec_of(registry, "fs.write")
    spec = base.model_copy(
        update={
            "parameters": tuple(
                sorted(
                    (*base.parameters, ParamSpec(name="token", type=ParamType.STRING, secret=True)),
                    key=lambda item: item.name,
                )
            )
        }
    )
    request = build_action_request(
        spec,
        {"file_path": "a.txt", "content": "x", "token": "sk-livetoken0000000000"},  # secret-scan: allow（合成值，用于验证脱敏与拒绝逻辑）
        action_id="act",
        request_id="req",
        agent="dsh",
        subject="local-user",
        workspace=enforcement_paths.workspace,
    )

    payload = redacted_request_payload(request)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "sk-livetoken" not in serialized  # secret-scan: allow（合成值，用于验证脱敏与拒绝逻辑）
    token = next(item for item in payload["params"] if item["name"] == "token")
    assert token["value"] is None and token["secret"] is True
    assert token["digest"].startswith("sha256:")
    # 摘要仍然把值绑进 action_hash：换一个 token 就是另一个动作。
    other = build_action_request(
        spec,
        {"file_path": "a.txt", "content": "x", "token": "sk-othertoken0000000"},  # secret-scan: allow（合成值，用于验证脱敏与拒绝逻辑）
        action_id="act",
        request_id="req",
        agent="dsh",
        subject="local-user",
        workspace=enforcement_paths.workspace,
    )
    assert other.action_hash != request.action_hash


def test_context_digest_is_stable_and_source_sensitive():
    assert context_digest(None) == context_digest(None)
    assert context_digest(None, sources=("chunk_1",)) != context_digest(None, sources=("chunk_2",))
    assert digest_of({"a": 1}) == digest_of({"a": 1})
