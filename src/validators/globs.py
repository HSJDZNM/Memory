"""仓库相对路径的 glob 匹配（验证器层）。

语义：

- "**/" 匹配零个或多个目录（"src/**/*.py" 同时覆盖 src/a.py 与 src/pkg/a.py）；
- 结尾的 "**" 匹配任意剩余路径；
- "*" 不跨目录，"? " 匹配单个字符。

历史上 adapters/dsh/adapter.py 里的匹配器把 "**/" 实现成"至少一层目录"，与本模块不一致
——这正是治理覆盖缺口 G8：配置里写 "**/*.md" 看着覆盖所有 Markdown，实际漏掉根目录一整个层级。
该分歧已消除：两边语义一致（"**/" = 零个或多个目录），由 tests/contract 下的跨模块对照测试钉住；
dsh 侧 layer/language 映射表因匹配范围放大而产生的逐条影响，
记录在 docs/project/engineering-policy-platform/reviews/governance-remediation/03-rule-fidelity.md。
"""

from __future__ import annotations

import re

__all__ = ["glob_match", "glob_to_regex"]

_CACHE: dict[str, re.Pattern[str]] = {}


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """把 glob 编译成正则；"**/" 表示零个或多个目录。"""

    cached = _CACHE.get(pattern)
    if cached is not None:
        return cached

    parts: list[str] = []
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if pattern[index : index + 2] == "**":
                if pattern[index + 2 : index + 3] == "/":
                    parts.append("(?:.*/)?")
                    index += 3
                    continue
                parts.append(".*")
                index += 2
                continue
            parts.append("[^/]*")
        elif char == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(char))
        index += 1
    compiled = re.compile("^" + "".join(parts) + "$")
    _CACHE[pattern] = compiled
    return compiled


def glob_match(pattern: str, path: str) -> bool:
    """仓库相对路径匹配；pattern 与 path 都用 "/" 分隔。"""

    return bool(glob_to_regex(pattern).match(path))
