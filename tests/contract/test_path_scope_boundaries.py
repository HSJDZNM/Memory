"""G5 路径口径边界契约测试：六种情形各有断言，且区别来自**数据**而不是代码特判。

背景：曾经"工作目录 = 项目根"被判越界，而且报错说"参数错误"——同一个"在范围内"的语义
在四个地方各写了一遍，边界上四处不一致。这里把六种情形固定下来：

    | 情形 | 参数声明 | 期望 |
    | --- | --- | --- |
    | 绝对工作区根 | path_kind=directory | 归一化为 "." 并通过 |
    | "."          | path_kind=directory | 归一化为 "." 并通过 |
    | "./"         | path_kind=directory | 归一化为 "." 并通过 |
    | 子目录        | path_kind=directory | 原样通过 |
    | 越界路径      | 任意              | path_out_of_scope |
    | "." 传给文件参数 | path_kind=file（默认） | 拒绝，但如实报"它不是文件" |

"等于根算不算范围内"由 ParamSpec.path_kind 这份**数据**决定：目录参数接受根，
文件参数不接受。放宽文件参数会让"写文件"这个语义悄悄变宽，所以它必须继续被拒。
"""

from __future__ import annotations

import pytest
from enforcement_support import ENFORCEMENT_APPROVED, ENFORCEMENT_REGISTRY
from pydantic import ValidationError

from enforcement.action import ActionRequestError, build_action_request, normalize_params
from enforcement.models import ParamSpec, ParamType, PathKind, ReasonCode, ToolSpec
from enforcement.registry import load_registry

pytestmark = pytest.mark.contract


def registry():
    return load_registry(ENFORCEMENT_REGISTRY, approved_path=ENFORCEMENT_APPROVED).registry


def directory_params(workdir: str) -> dict[str, object]:
    return {"command": "python -m pytest tests -q", "description": "demo", "workdir": workdir}


def file_params(file_path: str) -> dict[str, object]:
    return {"file_path": file_path, "content": "x"}


def test_registry_declares_directory_and_file_path_kinds_as_data():
    """目录 / 文件的区别必须写在注册表里；代码里不许出现针对某个参数名的特判。"""

    loaded = registry()
    for tool_id in ("exec.pwsh", "exec.bash"):
        declaration = loaded.tool(tool_id).parameter("workdir")
        assert declaration is not None
        assert declaration.path_kind is PathKind.DIRECTORY, tool_id
    for tool_id, name in (
        ("fs.edit", "file_path"),
        ("fs.write", "file_path"),
        ("fs.read", "file_path"),
        ("orc.fs.write", "file_path"),
        ("orc.policy.edit", "file_path"),
    ):
        declaration = loaded.tool(tool_id).parameter(name)
        assert declaration is not None
        assert declaration.path_kind is PathKind.FILE, f"{tool_id}.{name}"


@pytest.mark.parametrize(("raw", "expected"), [(".", "."), ("./", "."), ("sub", "sub")])
def test_directory_parameter_accepts_relative_forms(tmp_root, raw, expected):
    spec = registry().tool("exec.pwsh")
    params = normalize_params(spec, directory_params(raw), workspace=tmp_root)
    workdir = next(item for item in params if item.name == "workdir")
    assert workdir.value == expected


def test_absolute_workspace_root_is_normalized_to_dot(tmp_root):
    spec = registry().tool("exec.pwsh")
    request = build_action_request(
        spec,
        directory_params(str(tmp_root)),
        action_id="path-absolute-root",
        request_id="path-absolute-root",
        agent="dsh",
        subject="local-user",
        permissions=("shell.exec",),
        workspace=tmp_root,
        ttl_seconds=60,
    )
    assert request.value_of("workdir") == "."


def test_path_outside_the_workspace_is_reported_as_out_of_scope(tmp_root):
    """越界就是越界：原因码必须是 path_out_of_scope，不能被包成笼统的参数错误。"""

    spec = registry().tool("exec.pwsh")
    for raw in (str(tmp_root.parent), "..", "../outside", str(tmp_root / ".." / "outside")):
        with pytest.raises(ActionRequestError) as error:
            normalize_params(spec, directory_params(raw), workspace=tmp_root)
        assert error.value.reason_code == ReasonCode.PATH_OUT_OF_SCOPE.value, raw
        assert "[path_out_of_scope]" in str(error.value), raw


def test_file_parameter_still_rejects_the_workspace_root(tmp_root):
    """放宽目录参数不等于放宽文件参数："." 不是文件，理由要如实写出来。"""

    write_spec = registry().tool("fs.write")
    edit_spec = registry().tool("fs.edit")
    for raw in (".", "./", str(tmp_root)):
        with pytest.raises(ActionRequestError) as error:
            normalize_params(write_spec, file_params(raw), workspace=tmp_root)
        assert error.value.reason_code == ReasonCode.PARAM_INVALID.value, raw
        assert "path_kind: file" in str(error.value), raw

        # 编辑目标同样是文件参数：V1 的修前探针报的是 context_error，修完必须仍然是拒绝
        with pytest.raises(ActionRequestError) as error:
            normalize_params(
                edit_spec,
                {"file_path": raw, "old_string": "a", "new_string": "b"},
                workspace=tmp_root,
            )
        assert error.value.reason_code == ReasonCode.PARAM_INVALID.value, raw


def test_policy_context_file_field_still_requires_a_file():
    """上下文里的 file 仍按"文件"解释：等于仓库根的路径不得被归一化成 "."。"""

    from policy.context import repo_relative_path
    from policy.models import PolicyContextError

    with pytest.raises(PolicyContextError):
        repo_relative_path(".", repo_root=".")
    with pytest.raises(PolicyContextError):
        repo_relative_path(".", allow_root=False)


def test_unknown_path_kind_and_misplaced_path_kind_are_rejected():
    with pytest.raises(ValidationError) as error:
        ParamSpec(name="workdir", type=ParamType.PATH, path_kind="folder")
    assert "path_kind" in str(error.value)

    with pytest.raises(ValidationError) as error:
        ParamSpec(name="content", type=ParamType.STRING, path_kind=PathKind.DIRECTORY)
    assert "path_kind" in str(error.value)


def test_path_kind_cannot_relax_blocked_prefixes_or_scope(tmp_root):
    """目录语义只影响"等于根"这一个边界：受保护前缀仍然照拦。"""

    from enforcement.action import blocked_path_prefix

    base = registry().tool("orc.fs.write")
    params = normalize_params(
        base,
        {"file_path": "registry/tool-registry.yaml", "content": "x"},
        workspace=tmp_root,
    )
    hit = blocked_path_prefix(base, params)
    assert hit is not None and hit[2] == "registry"

    directory = ToolSpec(
        id="probe.dir",
        title="probe",
        agent="dsh",
        tool_name="probe",
        schema_version="1.0",
        risk="read_only",
        effect="none",
        driver="none",
        parameters=(
            ParamSpec(
                name="target",
                type=ParamType.PATH,
                path_scope="workspace",
                path_kind=PathKind.DIRECTORY,
                blocked_prefixes=["registry"],
            ),
        ),
    )
    blocked = normalize_params(directory, {"target": "registry"}, workspace=tmp_root)
    assert blocked_path_prefix(directory, blocked) == ("target", "registry", "registry")
