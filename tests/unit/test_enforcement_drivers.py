"""文件类驱动的必需参数闸门：缺参数不得变成"用空值执行"。

对应 AGENTS.md 的失败关闭口径：工具表声明了必需参数，驱动是副作用之前的最后一道闸——
拿不到证明就拒绝，绝不把缺省值（None / 缺失键）当成空内容去写盘。
"""

from __future__ import annotations

import json

import pytest
from enforcement_support import enforcement_paths, make_action  # noqa: F401 - fixture 再导出

from enforcement.drivers import DriverError, FileDriver
from enforcement.models import ActionRequest, DriverKind, ExecutionStatus

__all__ = ["enforcement_paths"]


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
