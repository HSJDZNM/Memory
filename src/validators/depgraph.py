"""依赖图：文件 / 模块 / 组件为节点，import（以及可静态绑定的调用）为边。

解析结果必须区分三类，绝不把"解析失败"当作"没有依赖"：

- internal：解析到项目内的文件（按组件映射得到参与规则匹配的名字）；
- stdlib / external：标准库或第三方包；
- unresolved：动态 import 目标不是常量、或"看起来是项目内的模块却不存在"——
  这类事实由流水线转成失败关闭的阻断点。

调用链只在根名字能静态绑定到某条 import 时产生边；self._repository.save() 这类实例字段
需要类型推断（那是 tool.mypy 的活），本模块不猜。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import FrozenSet, Mapping, Optional, Sequence, Tuple

from policy.evidence import DependencyFact, DependencyKind, DependencyResolution

from .models import ProjectProfile
from .python_ast import ModuleFacts

__all__ = [
    "DependencyResult",
    "GraphEdge",
    "ModuleIndex",
    "UnresolvedDependency",
    "build_dependencies",
    "build_module_index",
    "package_of",
]

# 索引与解析时跳过的目录：既避免把虚拟环境当项目代码，也避免把构建产物算成依赖。
SKIP_DIRS: FrozenSet[str] = frozenset(
    {
        "__pycache__",
        "node_modules",
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        ".tmp",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "site-packages",
        "build",
        "dist",
    }
)


@dataclass(frozen=True)
class ModuleIndex:
    """项目内模块 → 仓库相对路径的索引（按声明的 python 根建立）。"""

    modules: Mapping[str, str]
    top_levels: FrozenSet[str]
    scanned: int
    truncated: bool


@dataclass(frozen=True)
class UnresolvedDependency:
    """无法静态解析的依赖：必须留痕，不能当作"没有依赖"。"""

    module: str
    kind: str
    line: Optional[int]
    column: Optional[int]
    reason: str

    @property
    def sort_key(self) -> Tuple[str, str, int, int]:
        return (self.module, self.kind, self.line or 0, self.column or 0)


@dataclass(frozen=True)
class GraphEdge:
    """依赖图的一条边（用于报告与测试；判定只依赖 DependencyFact）。"""

    source: str
    target: str
    kind: str


@dataclass(frozen=True)
class DependencyResult:
    """一次依赖解析的全部产物。"""

    dependencies: Tuple[DependencyFact, ...] = ()
    unresolved: Tuple[UnresolvedDependency, ...] = ()
    nodes: Tuple[str, ...] = ()
    edges: Tuple[GraphEdge, ...] = ()
    module: Optional[str] = None
    package: Tuple[str, ...] = field(default=())

    def to_payload(self) -> Mapping[str, object]:
        return {
            "module": self.module,
            "package": list(self.package),
            "nodes": list(self.nodes),
            "edges": [
                {"source": edge.source, "target": edge.target, "kind": edge.kind}
                for edge in self.edges
            ],
            "unresolved": [
                {
                    "module": item.module,
                    "kind": item.kind,
                    "line": item.line,
                    "column": item.column,
                    "reason": item.reason,
                }
                for item in self.unresolved
            ],
        }


def build_module_index(
    workspace: Path | str,
    profile: ProjectProfile,
    *,
    max_files: int = 20000,
) -> ModuleIndex:
    """按项目档案声明的 python 根建立"模块名 → 仓库相对路径"索引。"""

    anchor = Path(workspace).resolve()
    modules: dict[str, str] = {}
    scanned = 0
    truncated = False

    for root_name in profile.python_roots:
        root = (anchor / root_name).resolve()
        if not root.is_dir() or not root.is_relative_to(anchor):
            continue
        for directory, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(
                name for name in dirnames if name not in SKIP_DIRS and not name.startswith(".")
            )
            for filename in sorted(filenames):
                if not filename.endswith(".py"):
                    continue
                scanned += 1
                if scanned > max_files:
                    truncated = True
                    break
                path = Path(directory) / filename
                try:
                    relative = path.resolve().relative_to(anchor).as_posix()
                except ValueError:
                    continue
                try:
                    local = path.resolve().relative_to(root)
                except ValueError:
                    continue
                parts = list(local.parts)
                if parts[-1] == "__init__.py":
                    parts = parts[:-1]
                else:
                    parts[-1] = parts[-1][: -len(".py")]
                if not parts:
                    continue
                modules[".".join(parts)] = relative
            if truncated:
                break
        if truncated:
            break

    top_levels = frozenset(name.split(".")[0] for name in modules)
    return ModuleIndex(
        modules=modules, top_levels=top_levels, scanned=scanned, truncated=truncated
    )


def package_of(path: str, profile: ProjectProfile) -> Optional[Tuple[str, ...]]:
    """目标文件所属的包（模块名去掉最后一段）；不是 .py 时返回 None。

    多个 python 根同时匹配时取**最具体**的那个（src 布局下 src/shop/a.py 的包是 shop，
    而不是 src.shop）：相对导入必须按项目自己的导入路径展开。
    """

    best: Optional[Tuple[int, Tuple[str, ...]]] = None
    for root_name in profile.python_roots:
        prefix = "" if root_name in (".", "") else root_name.strip("/") + "/"
        if prefix and not path.startswith(prefix):
            continue
        remainder = path[len(prefix) :] if prefix else path
        if not remainder.endswith(".py"):
            continue
        parts = remainder[: -len(".py")].split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        candidate = tuple(parts[:-1]) if parts else ()
        if best is None or len(prefix) > best[0]:
            best = (len(prefix), candidate)
    return None if best is None else best[1]


def _resolve_module(
    module: str, *, index: ModuleIndex, stdlib: FrozenSet[str]
) -> Tuple[DependencyResolution, Optional[str], str]:
    """解析一个绝对模块名。返回 (解析结果, 项目内路径, 原因)。"""

    top = module.split(".")[0]
    if top == "__future__":
        return DependencyResolution.STDLIB, None, "标准库 __future__"
    if top in stdlib:
        return DependencyResolution.STDLIB, None, "标准库 " + top
    path = index.modules.get(module)
    if path is not None:
        return DependencyResolution.INTERNAL, path, "项目内模块 " + module + " 指向 " + path
    if top in index.top_levels:
        return (
            DependencyResolution.UNRESOLVED,
            None,
            "看起来是项目内模块（顶层包 " + top + " 存在），但索引里没有 " + module,
        )
    return DependencyResolution.EXTERNAL, None, "外部包 " + top


def _relative_modules(
    fact_module: str, level: int, names: Sequence[str], package: Sequence[str]
) -> Tuple[Tuple[str, ...], Optional[str]]:
    """把相对导入展开成绝对模块名；无法展开时返回原因。"""

    if level < 1:
        return (), "相对导入的 level 必须是正数"
    drop = level - 1
    if drop > len(package):
        return (
            (),
            "相对导入超出顶层包（level=" + str(level) + "，当前包深度 " + str(len(package)) + "）",
        )
    prefix = list(package[: len(package) - drop]) if drop else list(package)
    if fact_module:
        return (".".join([*prefix, fact_module]),), None
    if not names:
        return (), "相对导入没有指明模块名"
    return tuple(".".join([*prefix, name]) for name in names), None


def build_dependencies(
    facts: ModuleFacts,
    *,
    target_path: str,
    profile: ProjectProfile,
    index: ModuleIndex,
    validator: str,
    stdlib: Optional[FrozenSet[str]] = None,
) -> DependencyResult:
    """把模块事实解析成依赖事实、未解析项与依赖图。"""

    stdlib_names = frozenset(sys.stdlib_module_names) if stdlib is None else stdlib
    package = package_of(target_path, profile)
    absolute_package = package if package is not None else ()

    dependencies: list[DependencyFact] = []
    unresolved: list[UnresolvedDependency] = []
    edges: list[GraphEdge] = []
    nodes: set[str] = {target_path}
    seen: set[Tuple[str, str, Optional[int], str]] = set()

    def add(
        module: str,
        *,
        kind: DependencyKind,
        line: Optional[int],
        column: Optional[int],
    ) -> None:
        resolution, path, reason = _resolve_module(module, index=index, stdlib=stdlib_names)
        top = module.split(".")[0]
        if resolution is DependencyResolution.INTERNAL and path is not None:
            name = profile.component_for(path) or top
            nodes.add(path)
            edges.append(GraphEdge(source=target_path, target=path, kind=kind.value))
        elif resolution is DependencyResolution.UNRESOLVED:
            name = top
            unresolved.append(
                UnresolvedDependency(
                    module=module, kind=kind.value, line=line, column=column, reason=reason
                )
            )
            edges.append(
                GraphEdge(source=target_path, target="unresolved:" + module, kind=kind.value)
            )
        else:
            name = top
            nodes.add("external:" + top)
            edges.append(
                GraphEdge(source=target_path, target="external:" + top, kind=kind.value)
            )
        marker = (name, kind.value, line, resolution.value)
        if marker in seen:
            return
        seen.add(marker)
        dependencies.append(
            DependencyFact(
                name=name,
                module=module,
                kind=kind,
                resolution=resolution,
                file=target_path,
                line=line,
                column=column,
                validator=validator,
                detail=reason,
            )
        )

    for fact in facts.imports:
        if fact.dynamic and not fact.constant:
            unresolved.append(
                UnresolvedDependency(
                    module="",
                    kind="dynamic",
                    line=fact.line,
                    column=fact.column,
                    reason=(
                        "动态 import 的目标不是常量字符串（"
                        + (fact.expression or "?")
                        + "），依赖集无法静态确定"
                    ),
                )
            )
            edges.append(GraphEdge(source=target_path, target="unresolved:dynamic", kind="dynamic"))
            continue

        if fact.kind == "dynamic":
            add(fact.module, kind=DependencyKind.DYNAMIC, line=fact.line, column=fact.column)
            continue

        if fact.level > 0:
            modules, failure = _relative_modules(
                fact.module, fact.level, fact.names, absolute_package
            )
            if failure is not None or package is None:
                unresolved.append(
                    UnresolvedDependency(
                        module=fact.module,
                        kind="from_import",
                        line=fact.line,
                        column=fact.column,
                        reason=failure or "目标不在任何声明的 python 根下，相对导入无法解析",
                    )
                )
                continue
            for module in modules:
                add(module, kind=DependencyKind.FROM_IMPORT, line=fact.line, column=fact.column)
            continue

        kind = DependencyKind.IMPORT if fact.kind == "import" else DependencyKind.FROM_IMPORT
        add(fact.module, kind=kind, line=fact.line, column=fact.column)

    bound = {item.bound_name for item in facts.imports if item.bound_name}
    for call in facts.calls:
        if call.root in bound:
            edges.append(GraphEdge(source=target_path, target="call:" + call.dotted, kind="call"))
            nodes.add("call:" + call.dotted)

    return DependencyResult(
        dependencies=tuple(sorted(dependencies, key=lambda item: item.sort_key)),
        unresolved=tuple(sorted(unresolved, key=lambda item: item.sort_key)),
        nodes=tuple(sorted(nodes)),
        edges=tuple(sorted(edges, key=lambda item: (item.source, item.target, item.kind))),
        module=".".join([*absolute_package, Path(target_path).stem])
        if package is not None
        else None,
        package=absolute_package,
    )
