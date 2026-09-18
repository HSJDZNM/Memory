"""测试选择：从变更集找到最小相关测试，并识别"改了生产代码却没有对应测试"。

选择顺序由 validation/test-layout.yaml 声明（related → package → suite）；
本模块只做选择，不运行进程——运行在 adapters/pytest_runner.py。
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


def _patterns_for(level: str, layout: TestLayout, *, stem: str, package: str) -> Tuple[str, ...]:
    for item in layout.escalation:
        if item.level == level:
            return tuple(
                pattern.replace("{stem}", stem).replace("{package}", package)
                for pattern in item.match
            )
    return ()


def _stem_of(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name[: -len(".py")] if name.endswith(".py") else name


def _package_of(path: str, layout: TestLayout) -> str:
    for pattern in layout.production_patterns:
        prefix = pattern.split("**")[0].rstrip("/")
        if prefix and path.startswith(prefix + "/"):
            remainder = path[len(prefix) + 1 :]
            parts = remainder.split("/")
            return parts[0] if len(parts) > 1 else ""
    parts = path.split("/")
    return parts[0] if len(parts) > 1 else ""


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
    production = sorted(
        {
            item
            for item in (*changed_files, target_path)
            if layout.is_production(item)
        }
    )
    if not production:
        return TestSelection(level="none", reason="变更集里没有生产文件，测试选择不适用")
    if not tests:
        # 工作区里一个测试文件都没有：生产变更全部算"缺少对应测试"，
        # 而不是"没找到相关测试所以跳过"。
        return TestSelection(
            level="none",
            missing=tuple(production),
            reason="工作区里没有任何匹配测试模式的文件",
        )

    selected: list[str] = []
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
            selected.extend(files)
            continue

        # 相关与同包都没有 → 这条生产变更缺少对应测试
        missing.append(path)
        # 相关性不足时仍然升级到整个套件去跑（升级只影响"跑什么"，不改"有没有测试"）
        suite_level, suite_files = _match_levels(
            tests, layout, ("suite",), stem=stem, package=package
        )
        if suite_level is not None:
            highest = _wider(highest, suite_level)
            selected.extend(suite_files)

    unique = sorted(set(selected))
    nodeids = tuple(unique[:max_nodeids])
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
    package: str,
) -> Tuple[Optional[str], Tuple[str, ...]]:
    """按给定层级顺序找测试文件；没有命中时层级返回 None（调用方据此区分"没找到"）。"""

    for level in levels:
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
