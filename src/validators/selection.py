"""测试选择：从变更集找到最小相关测试，并识别"改了生产代码却没有对应测试"。

选择顺序由 validation/test-layout.yaml 声明（related → package → suite）；
本模块只做选择，不运行进程——运行在 adapters/pytest_runner.py。

**变更集里本身就有测试文件时**（P4 / 5.58）：那些文件就是要跑的测试，直接选中它们
（`level="target"`）。少了这一支，只改测试文件的变更会得到 `level="none"`——pytest 根本
不被调起，`failing_tests` 拿不到证据，TESTING-002 于是以 critical 阻断（AGENTS 第 20 条），
受治工作区**写不了任何测试**；而 TESTING-001 又拦住"只改实现"，两条测试规则合起来是一条
死路，与第 51 条「先写测试不该被自己的平台拦死」正好相反。

"哪些路径算测试"只有一份声明（AGENTS 第 49 条）：这里只认 `validation/test-layout.yaml` 的
`test_patterns`——不按文件名猜、也不把"测试目录下的辅助文件"顺手算进来（那会是第二份声明）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple  # noqa: F401 - Optional 用于层级返回值

from .globs import glob_match
from .models import TestLayout
from .registry import RegistryError

__all__ = ["TestSelection", "select_tests"]

_SKIP_DIRS = frozenset(
    {"__pycache__", ".git", ".venv", "venv", ".tmp", ".mypy_cache", ".ruff_cache",
     ".pytest_cache", "node_modules", "build", "dist", ".tox"}
)


class SelectionError(RegistryError):
    """测试选择阶段的问题（配置、路径）。"""


@dataclass(frozen=True)
class TestSelection:
    """一次测试选择的结果。

    两个概念刻意分开：

    - **跑什么**：related → package 找不到时升级到 suite（相关性不足就多跑一点）；
    - **有没有对应测试**：只看 related / package。升级到 suite 不代表"这个变更带了测试"，
      否则只要工作区里存在任意一个测试文件，TESTING-001 就永远不会触发（等价死规则）。

    `level` 是受控取值（每一种都对应一个可读的"这次是怎么选的"）：

    | 取值 | 含义 |
    | --- | --- |
    | `target` | 本次变更（含目标本身）里就有声明为测试路径的文件：它们**就是**要跑的测试 |
    | `related` / `package` / `suite` | 由生产文件按 test-layout.yaml 的层级选出来的测试 |
    | `none` | 没有选中任何测试（`missing` 说明哪几条生产变更缺对应测试） |

    `target` 只描述"生产文件一个都没有、选中的全是变更里的测试文件"这一种形状；
    生产文件与测试文件同时在变更集里时仍然报 related / package / suite（那些测试文件
    会以最高相关性并入候选，见 `select_tests`）。
    """

    level: str
    nodeids: Tuple[str, ...] = ()
    missing: Tuple[str, ...] = ()
    related: Tuple[str, ...] = ()
    reason: str = ""
    escalated: bool = False
    truncated: bool = False

    def to_payload(self) -> dict:
        return {
            "level": self.level,
            "nodeids": list(self.nodeids),
            "missing": list(self.missing),
            "related": list(self.related),
            "reason": self.reason,
            "escalated": self.escalated,
            "truncated": self.truncated,
        }


def list_test_files(workspace: Path | str, layout: TestLayout) -> Tuple[str, ...]:
    """列出工作区里符合测试模式的文件（仓库相对路径，稳定排序）。"""

    anchor = Path(workspace).resolve()
    found: list[str] = []
    for directory, dirnames, filenames in os.walk(anchor):
        dirnames[:] = sorted(
            name for name in dirnames if name not in _SKIP_DIRS and not name.startswith(".")
        )
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            path = Path(directory) / filename
            try:
                relative = path.resolve().relative_to(anchor).as_posix()
            except ValueError:
                continue
            if layout.is_test(relative):
                found.append(relative)
    return tuple(sorted(found))


def _patterns_for(
    level: str, layout: TestLayout, *, stem: str, package: Optional[str]
) -> Tuple[str, ...]:
    for item in layout.escalation:
        if item.level != level:
            continue
        patterns: list[str] = []
        for pattern in item.match:
            if "{package}" in pattern and not package:
                # 推不出可信的包名：跳过这条模式，而不是拿空串去替换——那会生成
                # "tests/**//**/test_*.py" 这种永远匹配不到任何真实路径的 glob（复核发现）。
                continue
            patterns.append(pattern.replace("{stem}", stem).replace("{package}", package or ""))
        return tuple(patterns)
    return ()


def _stem_of(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name[: -len(".py")] if name.endswith(".py") else name


def _literal_prefix(pattern: str) -> str:
    """模式里第一个通配符之前的那段字面目录（没有字面目录时返回空串）。

    旧实现用 pattern.split("**")[0]，于是 "packages/*/src/**/*.py" 这种**根里带 glob** 的
    模式得到字面串 "packages/*/src"，永远不可能命中真实路径（复核发现）。
    """

    cut = len(pattern)
    for char in "*?[":
        index = pattern.find(char)
        if index != -1:
            cut = min(cut, index)
    return pattern[:cut].rstrip("/")


def _package_of(path: str, layout: TestLayout) -> Optional[str]:
    """生产文件在 python 根下的第一层目录名；推不出可信值时返回 None。

    None 的两种来源：文件直接躺在 python 根下（没有"包"这一层），或没有任何生产模式
    能同时提供字面前缀与整体匹配。调用方据此**跳过** package 级，而不是拿一个不可信的
    名字去替换 {package}（复核发现）。
    """

    from .globs import glob_match

    for pattern in layout.production_patterns:
        prefix = _literal_prefix(pattern)
        if not prefix or not path.startswith(prefix + "/"):
            continue
        if not glob_match(pattern, path):
            continue
        parts = path[len(prefix) + 1 :].split("/")
        return parts[0] if len(parts) > 1 else None
    return None


def select_tests(
    *,
    target_path: str,
    changed_files: Sequence[str],
    layout: TestLayout,
    workspace: Path | str,
    max_nodeids: int,
) -> TestSelection:
    """选出最小相关测试；找不到任何测试的生产变更记进 missing（由规则决定是否阻断）。"""

    tests = list_test_files(workspace, layout)
    changed = (*changed_files, target_path)
    production = sorted({item for item in changed if layout.is_production(item)})
    # P4 / 5.58：变更集（含目标本身）里**被声明为测试路径**、且真的在这棵树里的文件。
    # 它们本身就是"要跑的测试"——不需要（也不可能）再去找"与生产文件同名的测试"。
    # 两个条件都不能省：
    #   - layout.is_test 是唯一一份"哪些路径算测试"的声明（AGENTS 第 49 条），不按文件名猜；
    #   - item in on_disk 保证交出去的 node id 真的存在——不在树里的路径交给 pytest 只会
    #     变成一条读不懂的用法错误，而不是证据。
    on_disk = set(tests)
    changed_tests = tuple(
        sorted({item for item in changed if item in on_disk and layout.is_test(item)})
    )
    if not production:
        if changed_tests:
            nodeids = changed_tests[:max_nodeids]
            truncated = len(changed_tests) > len(nodeids)
            if not nodeids:
                # 上限为 0 的退化形状：仍然说得出"为什么一个都没选中"，而不是报一个空的 target。
                return TestSelection(
                    level="none",
                    related=changed_tests,
                    reason="目标在测试路径上，但候选上限为 0：一个测试都没选中",
                )
            reason = (
                "目标本身在测试路径上（validation/test-layout.yaml 的 test_patterns）："
                "本次变更中的 " + str(len(nodeids)) + " 个测试文件直接作为选中结果"
            )
            if truncated:
                reason += (
                    "（候选 " + str(len(changed_tests)) + " 个，超过上限 "
                    + str(max_nodeids) + "，已截断）"
                )
            return TestSelection(
                level="target",
                nodeids=nodeids,
                related=changed_tests,
                reason=reason,
                truncated=truncated,
            )
        return TestSelection(level="none", reason="变更集里没有生产文件，测试选择不适用")
    if not tests:
        # 工作区里一个测试文件都没有：生产变更全部算"缺少对应测试"，
        # 而不是"没找到相关测试所以跳过"。
        return TestSelection(
            level="none",
            missing=tuple(production),
            reason="工作区里没有任何匹配测试模式的文件",
        )

    # 每个候选记下**它是在哪一级被选中的**：截断必须保相关性高的（复核发现：旧实现按字母序
    # 截断，套件升级一旦把候选顶过上限，tests/aaa/... 会把真正相关的测试挤出名单）。
    # 变更集里的测试文件与"由生产文件选出来的测试"一起排序：它们本身就在这次变更里，
    # 相关性等同于 related 级（截断时不该被挤掉）。missing 仍然只看生产文件。
    ranked: dict[str, int] = {item: _ORDER["related"] for item in changed_tests}
    missing: list[str] = []
    highest = "related"
    for path in production:
        stem = _stem_of(path)
        package = _package_of(path, layout)
        level, files = _match_levels(
            tests, layout, ("related", "package"), stem=stem, package=package
        )
        if level is not None:
            highest = _wider(highest, level)
            for item in files:
                ranked.setdefault(item, _ORDER[level])
            continue

        # 相关与同包都没有 → 这条生产变更缺少对应测试
        missing.append(path)
        # 相关性不足时仍然升级到整个套件去跑（升级只影响"跑什么"，不改"有没有测试"）
        suite_level, suite_files = _match_levels(
            tests, layout, ("suite",), stem=stem, package=package
        )
        if suite_level is not None:
            highest = _wider(highest, suite_level)
            for item in suite_files:
                ranked.setdefault(item, _ORDER[suite_level])

    unique = tuple(sorted(ranked, key=lambda item: (ranked[item], item)))
    nodeids = unique[:max_nodeids]
    truncated = len(unique) > len(nodeids)
    escalated = highest == "suite" and bool(nodeids)
    if nodeids:
        reason = "按层级 " + highest + " 选中 " + str(len(nodeids)) + " 个测试文件"
        if truncated:
            reason += "（相关性候选 " + str(len(unique)) + " 个，超过上限 " + str(max_nodeids) + "，已截断）"
    elif missing:
        reason = "生产变更找不到相关或同包测试，且没有可运行的套件"
    else:
        reason = "没有选中任何测试文件"
    return TestSelection(
        level=highest if nodeids else "none",
        nodeids=nodeids,
        missing=tuple(sorted(set(missing))),
        related=tuple(unique),
        reason=reason,
        escalated=escalated,
        truncated=truncated,
    )


def _match_levels(
    tests: Tuple[str, ...],
    layout: TestLayout,
    levels: Tuple[str, ...],
    *,
    stem: str,
    package: Optional[str],
) -> Tuple[Optional[str], Tuple[str, ...]]:
    """按给定层级顺序找测试文件；没有命中时层级返回 None（调用方据此区分"没找到"）。"""

    for level in levels:
        if level == "package" and not package:
            # 没有可信的包名时 package 级不适用：跳过它（既不误报"没有同包测试"，
            # 也不拿空串拼出匹配不到东西的模式）——复核发现。
            continue
        patterns = _patterns_for(level, layout, stem=stem, package=package)
        matched = tuple(
            candidate
            for candidate in tests
            if any(glob_match(pattern, candidate) for pattern in patterns)
        )
        if matched:
            return level, matched
    return None, ()


_ORDER = {"related": 0, "package": 1, "suite": 2, "none": -1}


def _wider(current: str, candidate: str) -> str:
    return candidate if _ORDER.get(candidate, 0) > _ORDER.get(current, 0) else current
