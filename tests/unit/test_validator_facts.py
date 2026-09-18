"""Phase 5 事实层测试：源码身份、AST 事实与依赖图。

这一层是 ARCH-001 的证据来源，所以"解析失败"必须与"没有依赖"严格区分：
无法解析的内部依赖、动态 import、语法错误都要留下可判定的痕迹。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import VALIDATOR_PROJECT, validators_config
from validators.depgraph import build_dependencies, build_module_index, package_of
from validators.python_ast import imported_names, parse_module
from validators.source import SourceError, read_source, resolve_target

CONFIG = validators_config()


def read(relative: str, *, workspace: Path = VALIDATOR_PROJECT) -> object:
    return read_source(relative, workspace=workspace, language="python", max_bytes=1_000_000)


def dependencies_for(source: str, target: str = "src/shop/order_controller_bad.py") -> object:
    facts = parse_module(source)
    index = build_module_index(VALIDATOR_PROJECT, CONFIG.project)
    return build_dependencies(
        facts,
        target_path=target,
        profile=CONFIG.project,
        index=index,
        validator="py.depgraph@1.0",
    )


# ------------------------------------------------------------------ 源码身份


def test_read_source_records_hash_language_and_size() -> None:
    source = read("src/shop/order_service.py")

    assert source.path == "src/shop/order_service.py"
    assert source.digest.language == "python"
    assert source.digest.sha256.startswith("sha256:")
    assert source.digest.bytes == len(source.text.encode("utf-8"))
    assert source.digest.lines > 5


def test_read_source_rejects_missing_file_and_directory() -> None:
    with pytest.raises(SourceError) as missing:
        read("src/shop/absent.py")
    assert "不存在" in str(missing.value)

    with pytest.raises(SourceError) as directory:
        read("src/shop")
    assert "不是文件" in str(directory.value)


def test_read_source_rejects_oversized_and_non_utf8(tmp_root: Path) -> None:
    workspace = tmp_root / "workspace"
    workspace.mkdir()
    big = workspace / "big.py"
    big.write_text("x = 1" + chr(10) * 100, encoding="utf-8", newline="")
    with pytest.raises(SourceError) as oversized:
        read_source("big.py", workspace=workspace, language="python", max_bytes=16)
    assert "超过上限" in str(oversized.value)

    binary = workspace / "binary.py"
    binary.write_bytes(b"\xff\xfe\x00binary")
    with pytest.raises(SourceError) as undecodable:
        read_source("binary.py", workspace=workspace, language="python", max_bytes=1024)
    assert "NUL" in str(undecodable.value) or "UTF-8" in str(undecodable.value)


def test_read_source_rejects_paths_outside_the_workspace(tmp_root: Path) -> None:
    workspace = tmp_root / "workspace"
    workspace.mkdir()
    outside = tmp_root / "outside.py"
    outside.write_text("x = 1" + chr(10), encoding="utf-8", newline="")

    for candidate in ("../outside.py", str(outside)):
        with pytest.raises(SourceError) as error:
            read_source(candidate, workspace=workspace, language="python", max_bytes=1024)
        assert "工作区" in str(error.value) or "逃出" in str(error.value)


def test_resolve_target_rejects_control_characters(tmp_root: Path) -> None:
    workspace = tmp_root / "workspace"
    workspace.mkdir()
    (workspace / "a.py").write_text("x = 1" + chr(10), encoding="utf-8", newline="")

    with pytest.raises(SourceError):
        resolve_target("a.py" + chr(10) + "b.py", workspace=workspace)
    with pytest.raises(SourceError):
        resolve_target("", workspace=workspace)


def test_symlink_escaping_the_workspace_is_rejected(tmp_root: Path) -> None:
    workspace = tmp_root / "workspace"
    workspace.mkdir()
    outside = tmp_root / "outside.py"
    outside.write_text("x = 1" + chr(10), encoding="utf-8", newline="")
    link = workspace / "link.py"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("本机不允许创建符号链接（Windows 需要开发者模式）")

    with pytest.raises(SourceError):
        read_source("link.py", workspace=workspace, language="python", max_bytes=1024)


# ------------------------------------------------------------------ AST 事实


def test_ast_collects_imports_aliases_and_relative_imports() -> None:
    facts = parse_module(
        "import os, json.decoder" + chr(10)
        + "import shop.order_repository as repo" + chr(10)
        + "from shop.order_service import OrderService as Service" + chr(10)
        + "from . import order_service" + chr(10)
    )

    modules = [(item.kind, item.module, item.level, item.alias) for item in facts.imports]
    assert ("import", "os", 0, None) in modules
    assert ("import", "json.decoder", 0, None) in modules
    assert ("import", "shop.order_repository", 0, "repo") in modules
    assert ("from_import", "shop.order_service", 0, None) in modules
    assert ("from_import", "", 1, None) in modules
    assert "repo" in imported_names(facts)


def test_ast_marks_dynamic_imports_by_constantness() -> None:
    constant = parse_module("import importlib" + chr(10) + "m = importlib.import_module('os.path')")
    variable = parse_module("import importlib" + chr(10) + "m = importlib.import_module(name)")

    assert [(item.module, item.constant) for item in constant.imports if item.dynamic] == [
        ("os.path", True)
    ]
    assert [(item.module, item.constant) for item in variable.imports if item.dynamic] == [
        ("", False)
    ]
    assert variable.dynamic_unresolved[0].expression == "importlib.import_module(name)"


def test_ast_records_definitions_with_docstrings_and_visibility() -> None:
    facts = parse_module(
        '"""模块。"""' + chr(10)
        + "def public() -> None:" + chr(10)
        + '    """有 docstring。"""' + chr(10)
        + "def _private() -> None:" + chr(10)
        + "    pass" + chr(10)
        + "class Holder:" + chr(10)
        + '    """类。"""' + chr(10)
        + "    def method(self) -> None:" + chr(10)
        + "        pass" + chr(10)
    )

    assert facts.module_docstring is True
    kinds = {(item.kind, item.qualified): (item.docstring, item.private) for item in facts.definitions}
    assert kinds[("function", "public")] == (True, False)
    assert kinds[("function", "_private")] == (False, True)
    assert kinds[("class", "Holder")] == (True, False)
    assert kinds[("method", "Holder.method")] == (False, False)


def test_ast_reports_syntax_errors_with_position() -> None:
    facts = parse_module("def broken(:" + chr(10))

    assert facts.ok is False
    assert facts.syntax_error is not None
    assert facts.syntax_error.line == 1
    assert facts.syntax_error.column is not None


def test_ast_of_a_module_without_docstring() -> None:
    facts = parse_module("import os" + chr(10))

    assert facts.module_docstring is False
    assert facts.ok is True


def test_ast_is_deterministic() -> None:
    source = (VALIDATOR_PROJECT / "src/shop/order_service.py").read_text(encoding="utf-8")

    assert parse_module(source) == parse_module(source)


# ------------------------------------------------------------------ 依赖图


def test_module_index_maps_packages_and_modules() -> None:
    index = build_module_index(VALIDATOR_PROJECT, CONFIG.project)

    assert index.modules["shop.order_service"] == "src/shop/order_service.py"
    assert index.modules["shop"] == "src/shop/__init__.py"
    assert "shop" in index.top_levels
    assert index.truncated is False


def test_package_of_prefers_the_most_specific_python_root() -> None:
    # src 布局：src/shop/a.py 的包是 shop（不是 src.shop），相对导入才按项目自己的路径展开
    assert package_of("src/shop/order_service.py", CONFIG.project) == ("shop",)
    assert package_of("src/shop/__init__.py", CONFIG.project) == ()
    assert package_of("examples/good_service.py", CONFIG.project) == ("examples",)
    assert package_of("docs/readme.txt", CONFIG.project) is None


def test_internal_dependency_is_named_after_its_component() -> None:
    result = dependencies_for("from shop.order_repository import OrderRepository" + chr(10))

    fact = result.dependencies[0]
    assert (fact.name, fact.module, fact.resolution.value) == (
        "repository",
        "shop.order_repository",
        "internal",
    )
    assert fact.line == 1
    assert fact.validator == "py.depgraph@1.0"
    assert "src/shop/order_repository.py" in result.nodes


def test_service_dependency_is_not_the_forbidden_one() -> None:
    result = dependencies_for("from shop.order_service import OrderService" + chr(10))

    assert [fact.name for fact in result.dependencies] == ["service"]
    assert result.unresolved == ()


def test_standard_library_and_external_packages_are_distinguished() -> None:
    result = dependencies_for("import os" + chr(10) + "import requests" + chr(10))

    pairs = {(fact.name, fact.resolution.value) for fact in result.dependencies}
    assert ("os", "stdlib") in pairs
    assert ("requests", "external") in pairs
    assert result.unresolved == ()


def test_missing_project_module_is_unresolved_not_absent() -> None:
    result = dependencies_for("from shop.missing_repository import Missing" + chr(10))

    assert [item.module for item in result.unresolved] == ["shop.missing_repository"]
    assert "项目内模块" in result.unresolved[0].reason
    assert result.dependencies[0].resolution.value == "unresolved"


def test_dynamic_import_without_a_constant_is_unresolved() -> None:
    result = dependencies_for(
        "import importlib" + chr(10) + "m = importlib.import_module(name)" + chr(10)
    )

    assert [item.kind for item in result.unresolved] == ["dynamic"]
    assert "常量" in result.unresolved[0].reason


def test_relative_imports_resolve_inside_the_package() -> None:
    result = dependencies_for(
        "from . import order_service" + chr(10) + "from .order_service import OrderService" + chr(10)
    )

    assert {fact.module for fact in result.dependencies} == {"shop.order_service"}
    assert {fact.name for fact in result.dependencies} == {"service"}
    assert result.unresolved == ()


def test_relative_import_beyond_the_top_level_package_is_unresolved() -> None:
    result = dependencies_for("from .... import something" + chr(10))

    assert [item.kind for item in result.unresolved] == ["from_import"]
    assert "顶层包" in result.unresolved[0].reason


def test_relative_import_of_a_missing_sibling_is_unresolved(tmp_root: Path) -> None:
    workspace = tmp_root / "workspace"
    (workspace / "loose").mkdir(parents=True)
    (workspace / "loose" / "module.py").write_text(
        "from . import absent" + chr(10), encoding="utf-8", newline=""
    )

    facts = parse_module("from . import absent" + chr(10))
    index = build_module_index(workspace, CONFIG.project)
    result = build_dependencies(
        facts,
        target_path="loose/module.py",
        profile=CONFIG.project,
        index=index,
        validator="py.depgraph@1.0",
    )

    # 同包内不存在这个模块 → 内部模块解析失败，属于失败关闭而不是"没有依赖"
    assert [item.module for item in result.unresolved] == ["loose.absent"]
    assert result.dependencies[0].resolution.value == "unresolved"


def test_dependency_facts_are_deduplicated_but_keep_lines() -> None:
    result = dependencies_for(
        "from shop.order_repository import OrderRepository" + chr(10)
        + "class C:" + chr(10)
        + "    def m(self) -> None:" + chr(10)
        + "        from shop.order_repository import OrderRepository" + chr(10)
    )

    lines = sorted(fact.line for fact in result.dependencies)
    assert lines == [1, 4]


def test_graph_edges_cover_calls_bound_to_imports() -> None:
    result = dependencies_for(
        "import shop.order_service as service" + chr(10) + "service.create({})" + chr(10)
    )

    kinds = {edge.kind for edge in result.edges}
    assert "import" in kinds
    assert "call" in kinds
    assert any(edge.target == "call:service.create" for edge in result.edges)


def test_module_index_skips_ignored_directories(tmp_root: Path) -> None:
    workspace = tmp_root / "workspace"
    (workspace / "pkg").mkdir(parents=True)
    (workspace / "pkg" / "__init__.py").write_text("" + chr(10), encoding="utf-8", newline="")
    (workspace / "pkg" / "module.py").write_text("x = 1" + chr(10), encoding="utf-8", newline="")
    for ignored in (".venv", "node_modules", "__pycache__", ".git"):
        target = workspace / ignored
        target.mkdir()
        (target / "hidden.py").write_text("x = 1" + chr(10), encoding="utf-8", newline="")

    index = build_module_index(workspace, CONFIG.project)

    assert index.modules == {"pkg": "pkg/__init__.py", "pkg.module": "pkg/module.py"}


def test_module_index_reports_truncation(tmp_root: Path) -> None:
    workspace = tmp_root / "workspace"
    workspace.mkdir()
    for number in range(5):
        (workspace / ("m" + str(number) + ".py")).write_text("x = 1" + chr(10), encoding="utf-8", newline="")

    index = build_module_index(workspace, CONFIG.project, max_files=2)

    assert index.truncated is True
    assert index.scanned == 3
