"""文件类驱动的必需参数闸门：缺参数不得变成"用空值执行"。

对应 AGENTS.md 的失败关闭口径：工具表声明了必需参数，驱动是副作用之前的最后一道闸——
拿不到证明就拒绝，绝不把缺省值（None / 缺失键）当成空内容去写盘。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from enforcement_support import enforcement_paths, make_action  # noqa: F401 - fixture 再导出

from enforcement.drivers import DriverError, FileDriver
from enforcement.models import ActionRequest, DriverKind, ExecutionStatus

__all__ = ["enforcement_paths"]


# --------------------------------------------------------------------------- 进程类驱动
#
# 注册表声明了 workdir / timeoutMs / run_in_background，驱动就必须**消费**它们：
# 忽略一个已声明的参数等于执行一个和批准内容不同的动作（工具表是授权面）。

PROCESS_TOOL = {
    "id": "exec.probe",
    "title": "probe",
    "agent": "dsh",
    "tool_name": "probe",
    "schema_version": "1.0",
    "risk": "privileged_execution",
    "effect": "process",
    "driver": "process_argv",
    "required_permissions": ["shell.exec"],
    "approval": "required",
    "post_checks": ["exit_code_zero"],
    "timeout_ms": 20000,
    "parameters": [
        {"name": "argv", "type": "string_list", "required": True, "max_items": 8,
         "max_item_chars": 400},
        {"name": "description", "type": "string", "required": True, "max_chars": 200},
        {"name": "workdir", "type": "path", "path_scope": "workspace",
         "path_kind": "directory"},
        {"name": "timeoutMs", "type": "integer"},
        {"name": "run_in_background", "type": "boolean"},
    ],
}


def _probe_setup(tmp_root):
    from enforcement.action import build_action_request
    from enforcement.registry import load_registry
    from enforcement_support import write_registry

    registry_path, approved = write_registry(tmp_root, tools=(PROCESS_TOOL,))
    registry = load_registry(registry_path, approved_path=approved).registry
    workspace = tmp_root / "workspace"
    workspace.mkdir(exist_ok=True)
    spec = registry.tool("exec.probe")

    def build(params, *, action_id="probe-1"):
        return build_action_request(
            spec,
            params,
            action_id=action_id,
            request_id=action_id,
            agent="dsh",
            subject="local-user",
            roles=("developer",),
            permissions=registry.permissions_for(("developer",)),
            workspace=workspace,
            ttl_seconds=60,
        )

    return registry, spec, workspace, build


def _python(code: str) -> list:
    import sys

    return [sys.executable, "-c", code]


def test_workdir_becomes_the_process_cwd(tmp_root):
    """workdir 声明了就必须生效：进程的 cwd 是那个目录，而不是工作区根。"""

    from enforcement.drivers import ProcessDriver

    _, spec, workspace, build = _probe_setup(tmp_root)
    (workspace / "src").mkdir()
    request = build(
        {"argv": _python("import os; print(os.getcwd())"), "description": "probe",
         "workdir": "src"}
    )

    result = ProcessDriver().execute(request, spec, workspace=workspace)

    assert result.status is ExecutionStatus.EXECUTED
    assert Path(result.stdout.strip()) == (workspace / "src").resolve()


def test_a_missing_workdir_is_refused_not_ignored(tmp_root):
    """workdir 指向不存在的目录 → 拒绝，绝不"忽略它、在工作区根照跑"。"""

    from enforcement.drivers import ProcessDriver

    _, spec, workspace, build = _probe_setup(tmp_root)
    request = build({"argv": _python("print(1)"), "description": "probe", "workdir": "nope"})

    with pytest.raises(DriverError) as error:
        ProcessDriver().execute(request, spec, workspace=workspace)

    assert "不是已存在的目录" in str(error.value)


def test_a_tampered_workdir_outside_the_workspace_is_refused(tmp_root):
    """驱动是最后一道闸：就算请求被改成越界 workdir（绕过归一化），也必须拒绝。"""

    from enforcement.drivers import ProcessDriver

    _, spec, workspace, build = _probe_setup(tmp_root)
    request = build({"argv": _python("print(1)"), "description": "probe", "workdir": "src"})
    tampered = request.model_copy(
        update={
            "params": tuple(
                item.model_copy(update={"value": "../outside"})
                if item.name == "workdir"
                else item
                for item in request.params
            )
        }
    )

    with pytest.raises(DriverError) as error:
        ProcessDriver().execute(tampered, spec, workspace=workspace)

    assert "不在受控工作区内" in str(error.value)


def test_timeout_ms_shortens_the_budget(tmp_root):
    """timeoutMs 声明了就必须生效：本次调用的预算由它决定（并如实标记 timed_out）。"""

    from enforcement.drivers import ProcessDriver

    _, spec, workspace, build = _probe_setup(tmp_root)
    request = build(
        {"argv": _python("import time; time.sleep(5)"), "description": "probe",
         "timeoutMs": 80}
    )

    result = ProcessDriver().execute(request, spec, workspace=workspace)

    assert result.status is ExecutionStatus.FAILED
    assert result.timed_out is True, result.detail
    assert result.exit_code is None


def test_timeout_ms_above_the_registry_cap_is_refused(tmp_root):
    """超过注册表声明的预算一律拒绝：悄悄按上限跑等于执行了另一个动作。"""

    from enforcement.drivers import ProcessDriver

    _, spec, workspace, build = _probe_setup(tmp_root)
    request = build(
        {"argv": _python("print(1)"), "description": "probe", "timeoutMs": 999999}
    )

    with pytest.raises(DriverError) as error:
        ProcessDriver().execute(request, spec, workspace=workspace)

    assert "超过注册表声明" in str(error.value)


def test_background_requests_are_refused_explicitly(tmp_root):
    """run_in_background=true 显式拒绝（后台进程没有退出码，事后核对必然退化成修复）。"""

    from enforcement.drivers import ProcessDriver

    _, spec, workspace, build = _probe_setup(tmp_root)
    background = build(
        {"argv": _python("print(1)"), "description": "probe", "run_in_background": True},
        action_id="probe-bg",
    )

    with pytest.raises(DriverError) as error:
        ProcessDriver().execute(background, spec, workspace=workspace)

    assert "run_in_background=true" in str(error.value)
    assert "退出码" in str(error.value)

    foreground = build(
        {"argv": _python("print(1)"), "description": "probe", "run_in_background": False},
        action_id="probe-fg",
    )
    assert ProcessDriver().execute(
        foreground, spec, workspace=workspace
    ).status is ExecutionStatus.EXECUTED


def test_the_shell_driver_also_consumes_workdir(enforcement_paths):
    """shell 类工具同样消费 workdir：不存在的目录必须拒绝，而不是忽略它照跑。"""

    from enforcement.action import build_action_request
    from enforcement.drivers import ShellCommandDriver
    from enforcement.models import ParamType, ParamValue, digest_of

    registry = enforcement_paths.registry_object()
    spec = registry.tool("exec.shell")
    request = build_action_request(
        spec,
        {"command": "print('ok')", "description": "probe"},
        action_id="shell-wd",
        request_id="shell-wd",
        agent="dsh",
        subject="local-user",
        roles=("developer",),
        permissions=registry.permissions_for(("developer",)),
        workspace=enforcement_paths.workspace,
        ttl_seconds=60,
    )
    workdir = ParamValue(
        name="workdir", type=ParamType.PATH, value="nope", chars=4,
        digest=digest_of({"name": "workdir", "value": "nope"}),
    )
    tampered = request.model_copy(update={"params": (*request.params, workdir)})

    driver = ShellCommandDriver(shell=spec.shell)
    with pytest.raises(DriverError) as error:
        driver.execute(tampered, spec, workspace=enforcement_paths.workspace)

    assert "不是已存在的目录" in str(error.value)


def without_param(request: ActionRequest, name: str) -> ActionRequest:
    """把某个参数从请求里摘掉，等价于"这个请求根本没有带这个参数"。

    模型只校验"带了的参数"，注册表声明的 required 由 normalize_params 把关；
    经 model_validate 还原的请求（例如外部请求文档）可以缺参，驱动必须自己拒绝。
    摘要清空后由模型按当前内容重算，模拟一份自洽但缺参的请求文档。
    """

    payload = json.loads(request.model_dump_json())
    payload["params"] = [item for item in payload["params"] if item["name"] != name]
    payload["action_hash"] = ""
    return ActionRequest.model_validate(payload)


def test_file_write_without_content_refuses_instead_of_truncating(enforcement_paths):
    """缺 content 的写请求曾把已有文件截成 0 字节，而且仍然返回 executed。"""

    registry = enforcement_paths.registry_object()
    spec = registry.tool("fs.write")
    assert spec is not None
    target = enforcement_paths.file("src/shop/keep.py", "keep me\n")
    request = make_action(
        registry,
        enforcement_paths,
        "fs.write",
        {"file_path": "src/shop/keep.py", "content": "replaced\n"},
    )

    with pytest.raises(DriverError) as error:
        FileDriver(DriverKind.FILE_WRITE).execute(
            without_param(request, "content"), spec, workspace=enforcement_paths.workspace
        )
    assert "content" in str(error.value)
    assert target.read_text(encoding="utf-8") == "keep me\n"


def test_file_write_with_content_still_executes(enforcement_paths):
    """反真空：参数齐全时驱动照常执行，闸门没有把正常路径一起关掉。"""

    registry = enforcement_paths.registry_object()
    spec = registry.tool("fs.write")
    assert spec is not None
    target = enforcement_paths.file("src/shop/written.py", "old\n")
    request = make_action(
        registry,
        enforcement_paths,
        "fs.write",
        {"file_path": "src/shop/written.py", "content": "new\n"},
    )

    result = FileDriver(DriverKind.FILE_WRITE).execute(
        request, spec, workspace=enforcement_paths.workspace
    )

    assert result.status is ExecutionStatus.EXECUTED
    assert target.read_text(encoding="utf-8") == "new\n"


def test_file_edit_without_new_string_refuses_instead_of_deleting(enforcement_paths):
    """缺 new_string 的 edit 曾把匹配到的原文静默删掉，并返回 executed。"""

    registry = enforcement_paths.registry_object()
    spec = registry.tool("fs.edit")
    assert spec is not None
    target = enforcement_paths.file("src/shop/keep.py", "alpha\nbeta\n")
    request = make_action(
        registry,
        enforcement_paths,
        "fs.edit",
        {
            "file_path": "src/shop/keep.py",
            "old_string": "alpha",
            "new_string": "gamma",
            "replace_all": False,
        },
    )

    with pytest.raises(DriverError) as error:
        FileDriver(DriverKind.FILE_EDIT).execute(
            without_param(request, "new_string"), spec, workspace=enforcement_paths.workspace
        )
    assert "new_string" in str(error.value)
    assert target.read_text(encoding="utf-8") == "alpha\nbeta\n"


def test_file_edit_with_empty_old_string_does_not_blame_the_file(enforcement_paths):
    """空 old_string 是"参数没传"，不是"文件里没有要替换的原文"。"""

    registry = enforcement_paths.registry_object()
    spec = registry.tool("fs.edit")
    assert spec is not None
    enforcement_paths.file("src/shop/keep.py", "alpha\nbeta\n")
    request = make_action(
        registry,
        enforcement_paths,
        "fs.edit",
        {
            "file_path": "src/shop/keep.py",
            "old_string": "",
            "new_string": "gamma",
            "replace_all": False,
        },
    )

    with pytest.raises(DriverError) as error:
        FileDriver(DriverKind.FILE_EDIT).execute(
            request, spec, workspace=enforcement_paths.workspace
        )
    assert "old_string" in str(error.value)
