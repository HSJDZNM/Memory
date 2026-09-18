"""标准库 ast 的模块事实：import、调用链、定义与语法错误。

为什么先用标准库 ast：单语言原型阶段引入 tree-sitter 只是多一个依赖；等出现标准库
无法覆盖的需求（多语言、需要语法错误恢复）时再按 Phase 5 文档加 Adapter。

本模块只解析、不执行：不 import 目标模块、不解析注解、不运行任何代码。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

__all__ = [
    "CallFact",
    "DefinitionFact",
    "ImportFact",
    "ModuleFacts",
    "SyntaxIssue",
    "dynamic_import_bindings",
    "parse_module",
]

# 会被当作动态 import 的调用名。仅靠"调用名长什么样"不够：
#   from importlib import import_module as im; im(name)   ← 别名形式，名字上看不出来
# 因此还要从 import 绑定里收集"本地动态 import 入口"，见 _dynamic_import_bindings。
_DYNAMIC_IMPORT_NAMES = frozenset({"__import__", "importlib.import_module", "import_module"})

# 这些模块里导出的动态 import 入口，一旦被 from-import 绑定（含别名）就要盯住。
_DYNAMIC_IMPORT_SOURCES = {
    "importlib": frozenset({"import_module"}),
    "builtins": frozenset({"__import__"}),
}


@dataclass(frozen=True)
class SyntaxIssue:
    """语法错误：位置与消毒后的消息（消息来自解释器，可能包含源码片段）。"""

    message: str
    line: Optional[int]
    column: Optional[int]


@dataclass(frozen=True)
class ImportFact:
    """一条 import 事实。

    module 为空 + dynamic=True 表示"动态 import，但目标不是常量字符串"——
    这类依赖无法静态解析，必须留痕（不能当作"没有依赖"）。
    """

    module: str
    level: int
    alias: Optional[str]
    line: int
    column: int
    kind: str
    dynamic: bool = False
    constant: bool = True
    expression: Optional[str] = None
    names: Tuple[str, ...] = ()
    # 这次 import 在模块里实际绑定的名字（from-import 的每个名字都展开，含 "as" 别名）。
    # 动态 import 的别名形式（from importlib import import_module as im）靠它才看得出来。
    bindings: Tuple[str, ...] = ()

    @property
    def bound_name(self) -> Optional[str]:
        """这次 import 在模块里绑定的名字（用于把调用链绑定回 import）。"""

        if self.alias:
            return self.alias
        if not self.module:
            return None
        return self.module.split(".")[0] if self.kind == "import" else self.module.split(".")[-1]


@dataclass(frozen=True)
class CallFact:
    """一条调用事实：点分调用名与它的根名字。"""

    dotted: str
    root: str
    attribute: Optional[str]
    line: int
    column: int


@dataclass(frozen=True)
class DefinitionFact:
    """一个定义（模块/类/函数/方法）及其是否有 docstring。"""

    kind: str
    name: str
    qualified: str
    line: int
    column: int
    docstring: bool
    private: bool


@dataclass(frozen=True)
class ModuleFacts:
    """一个模块的全部静态事实。"""

    module_docstring: bool
    imports: Tuple[ImportFact, ...] = ()
    calls: Tuple[CallFact, ...] = ()
    definitions: Tuple[DefinitionFact, ...] = ()
    syntax_error: Optional[SyntaxIssue] = None

    @property
    def ok(self) -> bool:
        return self.syntax_error is None

    @property
    def dynamic_unresolved(self) -> Tuple[ImportFact, ...]:
        return tuple(item for item in self.imports if item.dynamic and not item.constant)


def dotted_name(node: ast.AST) -> Optional[str]:
    """把 Name / Attribute 链拼成点分名；不是名字链时返回 None。"""

    parts: list[str] = []
    current: Optional[ast.AST] = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def _location(node: ast.AST) -> Tuple[int, int]:
    return int(getattr(node, "lineno", 1)), int(getattr(node, "col_offset", 0))


def _is_private(name: str) -> bool:
    return name.startswith("_")


def _has_docstring(node: ast.AST) -> bool:
    body = getattr(node, "body", None)
    if not isinstance(body, list) or not body:
        return False
    first = body[0]
    return (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
        and bool(first.value.value.strip())
    )


def _docstring_of(node: ast.AST) -> Optional[str]:
    """取出定义的第一段字符串字面量（供 docstring 质量检查使用）。"""

    body = getattr(node, "body", None)
    if not isinstance(body, list) or not body:
        return None
    first = body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return first.value.value
    return None


def parse_module(text: str) -> ModuleFacts:
    """解析 Python 源码为模块事实。语法错误不抛异常，而是作为事实返回（失败关闭由调用方决定）。"""

    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        line = None if error.lineno is None else int(error.lineno)
        column = None if error.offset is None else max(0, int(error.offset) - 1)
        message = str(error.msg)
        return ModuleFacts(
            module_docstring=False,
            syntax_error=SyntaxIssue(message=message, line=line, column=column),
        )
    except (ValueError, RecursionError, MemoryError) as error:
        return ModuleFacts(
            module_docstring=False,
            syntax_error=SyntaxIssue(
                message=f"解析失败（{type(error).__name__}）", line=None, column=None
            ),
        )

    imports: list[ImportFact] = []
    calls: list[CallFact] = []
    definitions: list[DefinitionFact] = []
    call_nodes: list[ast.Call] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            line, column = _location(node)
            for alias in node.names:
                imports.append(
                    ImportFact(
                        module=alias.name,
                        level=0,
                        alias=alias.asname,
                        line=line,
                        column=column,
                        kind="import",
                        bindings=(alias.asname or alias.name.split(".")[0],),
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            line, column = _location(node)
            imports.append(
                ImportFact(
                    module=node.module or "",
                    level=int(node.level),
                    alias=None,
                    line=line,
                    column=column,
                    kind="from_import",
                    names=tuple(alias.name for alias in node.names),
                    bindings=tuple(alias.asname or alias.name for alias in node.names),
                )
            )
        elif isinstance(node, ast.Call):
            name = dotted_name(node.func)
            if name is None:
                continue
            line, column = _location(node)
            parts = name.split(".")
            calls.append(
                CallFact(
                    dotted=name,
                    root=parts[0],
                    attribute=parts[-1] if len(parts) > 1 else None,
                    line=line,
                    column=column,
                )
            )
            call_nodes.append(node)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definitions.append(_definition(node, parent=None))
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    definitions.append(_definition(child, parent=node.name))

    # 动态 import 的识别放在最后：先把 import 绑定收齐，别名形式才看得见
    # （from importlib import import_module as im; im(name) 曾经整个漏判）。
    bindings = set(dynamic_import_bindings(imports))
    for node in call_nodes:
        name = dotted_name(node.func)
        if name is None:
            continue
        tail = name.rpartition(".")[2]
        if name in _DYNAMIC_IMPORT_NAMES or tail == "import_module" or name in bindings:
            line, column = _location(node)
            imports.append(_dynamic_import(node, name, line, column))

    return ModuleFacts(
        module_docstring=_docstring_of(tree) is not None,
        imports=tuple(sorted(imports, key=lambda item: (item.line, item.column, item.module))),
        calls=tuple(sorted(calls, key=lambda item: (item.line, item.column, item.dotted))),
        definitions=tuple(
            sorted(definitions, key=lambda item: (item.line, item.column, item.qualified))
        ),
    )


def _dynamic_import(node: ast.Call, name: str, line: int, column: int) -> ImportFact:
    """动态 import：常量参数解析成模块名，非常量参数留成"无法解析"。"""

    target = node.args[0] if node.args else None
    if isinstance(target, ast.Constant) and isinstance(target.value, str):
        return ImportFact(
            module=target.value,
            level=0,
            alias=None,
            line=line,
            column=column,
            kind="dynamic",
            dynamic=True,
            constant=True,
            expression=name,
        )
    return ImportFact(
        module="",
        level=0,
        alias=None,
        line=line,
        column=column,
        kind="dynamic",
        dynamic=True,
        constant=False,
        expression=name + "(" + _describe_argument(target) + ")",
    )


def _describe_argument(target: Optional[ast.AST]) -> str:
    """描述无法静态解析的参数（只保留形状，不保留源码原文）。"""

    if target is None:
        return "<缺少参数>"
    name = dotted_name(target)
    if name is not None:
        return name
    return type(target).__name__


def _definition(
    node: ast.AST, *, parent: Optional[str]
) -> DefinitionFact:
    name = str(getattr(node, "name", "<anonymous>"))
    line, column = _location(node)
    kind = "class" if isinstance(node, ast.ClassDef) else ("method" if parent else "function")
    qualified = f"{parent}.{name}" if parent else name
    return DefinitionFact(
        kind=kind,
        name=name,
        qualified=qualified,
        line=line,
        column=column,
        docstring=_has_docstring(node),
        private=_is_private(name),
    )


def dynamic_import_bindings(imports: Sequence[ImportFact]) -> Tuple[str, ...]:
    """这批 import 里绑定到动态 import 入口的本地名字（含别名）。

    from importlib import import_module as im  →  "im"
    from builtins import __import__           →  "__import__"（名字本身已在白名单里，仍然列出）
    import importlib as il                    →  不在这里：点分调用 il.import_module 由后缀判断覆盖。
    """

    bound: list[str] = []
    for fact in imports:
        if fact.level != 0 or fact.kind != "from_import":
            continue
        exported = _DYNAMIC_IMPORT_SOURCES.get(fact.module)
        if not exported:
            continue
        pairs = tuple(zip(fact.names, fact.bindings)) if fact.bindings else tuple(
            (name, name) for name in fact.names
        )
        for name, binding in pairs:
            if name in exported:
                bound.append(binding)
    return tuple(sorted(set(bound)))


def imported_names(facts: ModuleFacts) -> Tuple[str, ...]:
    """模块里被 import 绑定过的名字（供调用链绑定使用）。"""

    return tuple(
        sorted({item.bound_name for item in facts.imports if item.bound_name})
    )
