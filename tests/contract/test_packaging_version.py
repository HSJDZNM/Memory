"""打包版本的**唯一来源**是模块字面量：`pyproject.toml` 只声明 `dynamic`，不再写死一个数。

历史：`pyproject.toml` 写 `version = "0.0.0"`，而 `policy_api.__version__` 是 `"0.1.0"`——装出来的
发行版元数据与 `policy_api.contract` 自报的服务版本各说各话。改成 `dynamic = ["version"]` +
`[tool.setuptools.dynamic] version = {attr = "policy_api.__version__"}` 之后，构建期从模块取值
（setuptools 静态读字面量，不需要导入包）。

实构建证据（本机 `uv build`）：`engineering_policy_platform-0.1.0-py3-none-any.whl` 的 METADATA 是
`Name: engineering-policy-platform` / `Version: 0.1.0`（改前是 `0.0.0`）。
"""

from __future__ import annotations

import tomllib

import pytest
from conftest import REPO_ROOT

import policy_api

pytestmark = pytest.mark.contract


def test_the_distribution_version_comes_from_the_module() -> None:
    """`pyproject.toml` 不写死版本：打包期从 `policy_api.__version__` 取，模块字面量是唯一来源。"""

    document = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = document["project"]

    assert "version" not in project, "静态 version 会让打包元数据与模块字面量各说各话"
    assert "version" in project.get("dynamic", ()), '必须声明 dynamic = ["version"]'
    attr = document["tool"]["setuptools"]["dynamic"]["version"]["attr"]
    assert attr == "policy_api.__version__", attr
    assert policy_api.__version__ and policy_api.__version__ != "0.0.0"
