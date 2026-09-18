"""Phase 5 复核回归：独立复核发现的问题与它们的修复都钉在这里。

每条用例对应 docs/engineering-policy-platform/reviews/post-phase-5-review.md 里的一个编号。
共同点是：它们都是"看起来有保护、实际没有"或"依赖根本没被看见"的形态。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import (
    FAKE_TOOL,
    REPO_ROOT,
    VALIDATOR_PROJECT,
    fake_tool_spec,
    validators_config,
    write_validation_config,
)
from validators.adapters.base import tool_label
from validators.depgraph import build_dependencies, build_module_index
from validators.python_ast import dynamic_import_bindings, parse_module
from validators.registry import RegistryError, load_registry
from validators.selection import select_tests

CONFIG = validators_config()
INDEX = build_module_index(VALIDATOR_PROJECT, CONFIG.project)
TARGET = "src/shop/order_controller_bad.py"


def dependencies(source: str):
    facts = parse_module(source)
    return facts, build_dependencies(
        facts,
        target_path=TARGET,
        profile=CONFIG.project,
        index=INDEX,
        validator="py.depgraph@1.0",
    )


# ------------------------------------------------------------------ F2：from pkg import submodule


def test_from_import_of_a_submodule_is_a_dependency_edge() -> None:
    """`from shop import order_repository` 导入的是子模块，必须解析成组件 repository。"""

    _facts, result = dependencies("from shop import order_repository" + chr(10))

    facts = [(item.name, item.module, item.resolution.value) for item in result.dependencies]
    # 子模块边（repository）与包本身（shop）都在；关键是前者必须存在
    assert ("repository", "shop.order_repository", "internal") in facts
    assert result.unresolved == ()


def test_from_import_of_a_module_name_does_not_become_unresolved() -> None:
    """`from shop import order_service` 里的名字是模块，正常解析；不能留下"解析失败"。"""

    _facts, result = dependencies("from shop import order_service" + chr(10))

    names = {item.name for item in result.dependencies}
    assert "service" in names
    assert "repository" not in names
    assert result.unresolved == ()


def test_from_import_of_a_name_inside_a_module_keeps_the_module_edge() -> None:
    _facts, result = dependencies("from shop.order_repository import OrderRepository" + chr(10))

    assert {item.name for item in result.dependencies} == {"repository"}
    assert result.unresolved == ()


# ------------------------------------------------------------------ F3：动态 import 的别名形式


def test_aliased_dynamic_import_is_detected() -> None:
    source = "from importlib import import_module as im" + chr(10) + "im(name)" + chr(10)
    facts = parse_module(source)

    assert dynamic_import_bindings(facts.imports) == ("im",)
    assert [item.expression for item in facts.dynamic_unresolved] == ["im(name)"]

    _facts, result = dependencies(source)
    assert [item.kind for item in result.unresolved] == ["dynamic"]


def test_aliased_dynamic_import_with_a_constant_resolves_the_module() -> None:
    _facts, result = dependencies(
        "from importlib import import_module as im" + chr(10)
        + "im('shop.order_repository')" + chr(10)
    )

    resolved = [
        (item.name, item.resolution.value)
        for item in result.dependencies
        if item.name == "repository"
    ]
    assert resolved == [("repository", "internal")]
    assert result.unresolved == ()


def test_other_dynamic_import_spellings_are_covered() -> None:
    for source in (
        "from builtins import __import__ as load" + chr(10) + "load(name)" + chr(10),
        "import importlib as il" + chr(10) + "il.import_module(name)" + chr(10),
        "import importlib" + chr(10) + "importlib.import_module(name)" + chr(10),
    ):
        _facts, result = dependencies(source)
        assert [item.kind for item in result.unresolved] == ["dynamic"], source


# ------------------------------------------------------------------ F4：缺测试语义


def test_missing_tests_is_reported_even_when_the_workspace_has_tests() -> None:
    """工作区里有测试文件，但这条生产变更没有相关或同包测试 → 必须报缺测试。"""

    selection = select_tests(
        target_path="src/shop/order_repository.py",
        changed_files=("src/shop/order_repository.py",),
        layout=CONFIG.layout,
        workspace=VALIDATOR_PROJECT,
        max_nodeids=10,
    )

    assert selection.missing == ("src/shop/order_repository.py",)
    assert selection.level == "suite"  # 仍然跑套件：升级只影响"跑什么"
    assert selection.escalated is True
    assert selection.nodeids == ("tests/test_order_service.py",)


def test_related_test_means_no_missing_entry() -> None:
    selection = select_tests(
        target_path="src/shop/order_service.py",
        changed_files=("src/shop/order_service.py",),
        layout=CONFIG.layout,
        workspace=VALIDATOR_PROJECT,
        max_nodeids=10,
    )

    assert selection.missing == ()
    assert selection.escalated is False


def test_node_id_cap_marks_truncation(tmp_root: Path) -> None:
    workspace = tmp_root / "workspace"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "lonely.py").write_text("x = 1" + chr(10), encoding="utf-8", newline="")
    (workspace / "tests").mkdir()
    for number in range(3):
        (workspace / "tests" / ("test_case_" + str(number) + ".py")).write_text(
            "def test_ok() -> None:" + chr(10) + "    assert True" + chr(10),
            encoding="utf-8",
            newline="",
        )

    selection = select_tests(
        target_path="src/lonely.py",
        changed_files=("src/lonely.py",),
        layout=CONFIG.layout,
        workspace=workspace,
        max_nodeids=2,
    )

    assert len(selection.nodeids) == 2
    assert selection.truncated is True
    assert "截断" in selection.reason


# ------------------------------------------------------------------ F6/F9：注册表对齐与工具名


def test_unimplemented_validator_id_is_rejected_at_load(tmp_root: Path) -> None:
    document = yaml.safe_load(
        (REPO_ROOT / "validation" / "validators.yaml").read_text(encoding="utf-8")
    )
    document["validators"].append(
        {
            "id": "py.ghost",
            "version": "1.0",
            "kind": "builtin",
            "stage": "docstring",
            "checkers": ["missing_docstring"],
            "critical": True,
            "description": "注册表里有、实现里没有",
        }
    )
    for pack in document["rule_packs"]:
        if pack["id"] == "python-core":
            pack["validators"] = list(pack["validators"]) + ["py.ghost"]
    root = write_validation_config(tmp_root, registry=document)

    with pytest.raises(RegistryError) as error:
        load_registry(root / "validation" / "validators.yaml", root=REPO_ROOT)

    assert "py.ghost" in str(error.value)


def test_tool_label_replaces_the_python_placeholder() -> None:
    spec = fake_tool_spec("pytest", "ok", validator_id="tool.pytest")
    spec = spec.model_copy(
        update={"tool": spec.tool.model_copy(update={"command": ("{python}", "-m", "pytest")})}
    )

    assert tool_label(spec.tool) == "pytest"
    # 真实注册表里的 ruff / mypy 声明的是可执行文件名，原样使用
    assert tool_label(CONFIG.registry.spec("tool.ruff").tool) == "ruff"
    assert tool_label(CONFIG.registry.spec("tool.mypy").tool) == "mypy"


def test_tool_label_never_returns_a_path() -> None:
    """证据里的工具名只留名字：声明里写路径（假工具就是这种形态）也不能带进证据。

    CI-F1：这里曾把夹具工具的绝对路径原样写进载荷的 tool 字段。安全用例
    （test_decisions_do_not_leak_absolute_paths）在 Linux 上抓住了它，而 Windows
    上因为反斜杠 + JSON 转义两重差异一直是绿的——两处都已修。
    """

    spec = fake_tool_spec("ruff", "ok")
    spec = spec.model_copy(
        update={
            "tool": spec.tool.model_copy(
                update={"command": ("{python}", str(FAKE_TOOL), "ruff", "ok")}
            )
        }
    )

    label = tool_label(spec.tool)

    assert label == FAKE_TOOL.name
    assert "/" not in label and chr(92) not in label
    # 直接声明可执行文件路径（注册表允许这种写法）同样只留文件名
    assert tool_label(spec.tool.model_copy(update={"command": (str(FAKE_TOOL),)})) == FAKE_TOOL.name
