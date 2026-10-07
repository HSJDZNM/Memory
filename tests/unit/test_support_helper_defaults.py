"""测试支持模块的「显式给值不许被默认值顶掉」契约。

来源：同一处缺陷在多个 support helper 里重复出现——用 `x or DEFAULT` 表达"省略时回落到默认值"，
于是**显式给的空值**与"根本没给"被并成同一个分支，调用方拿到一份它从没要过的数据：

- `registry_document(tools=())`：要空工具表，拿到默认的六件套（`write_registry` 继承同一陷阱）；
- `write_change(content="")`：要一个空文件正文，拿到整段罐头正文；
- `tool_request(params={})`：要一个"缺参数"的请求，拿到一个合法的 `orc.fs.write` 请求；
- 请求没有主体时 `approval_for` 伪造 `local-user`：这条审批永远匹配不上
  （`verify_approval` 直接拒绝 `subject=None` 的请求），失败被推迟到更晚、且报的是
  "主体不一致"而不是"请求根本没有主体"。

这一组用例钉的是"分支按 `is None` 判"本身，而不是某一次调用的偶然行为：每个用例都先给
反向对照（默认调用确实有默认值），再断言显式空值原样存活。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from enforcement_support import (
    EnforcementPaths,
    approval_for,
    make_action,
    registry_document,
    write_registry,
)
from orchestration_support import tool_request, write_change


def test_registry_document_keeps_an_explicitly_empty_tool_list() -> None:
    """`tools=()` 是"显式空表"，不是"没给"。"""

    assert registry_document()["tools"], "默认文档必须带默认工具表，否则下面这条对照不成立"
    assert registry_document(tools=())["tools"] == []


def test_write_registry_keeps_an_explicitly_empty_tool_list(tmp_root: Path) -> None:
    """落盘路径同样要保留显式空表：`write_registry` 不能把默认表又塞回来。"""

    path, _ = write_registry(tmp_root, tools=(), approve=False)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["tools"] == []


def test_write_change_keeps_an_explicitly_empty_body() -> None:
    """`content=""` 是"写一个空文件"，不是"用默认正文"。"""

    assert write_change().content, "默认必须是可用的正文，否则这条对照不成立"
    assert write_change(content="").content == ""


def test_tool_request_keeps_explicitly_empty_params() -> None:
    """`params={}` 是"这次什么参数都没给"，不能被补成一份合法写请求。"""

    assert tool_request().params, "默认必须带参数，否则这条对照不成立"
    assert tool_request(params={}).params == {}


def test_approval_for_refuses_to_invent_a_subject_for_a_null_subject_request(
    tmp_root: Path,
) -> None:
    """请求没有主体时当场拒绝，而不是伪造一个永远匹配不上的审批主体。"""

    paths = EnforcementPaths(tmp_root)
    request = make_action(
        paths.registry_object(),
        paths,
        "fs.edit",
        {"file_path": "a.py", "old_string": "a", "new_string": "b"},
        subject=None,
    )
    assert request.subject is None

    with pytest.raises(ValueError) as error:
        approval_for(request)
    assert "主体" in str(error.value)
