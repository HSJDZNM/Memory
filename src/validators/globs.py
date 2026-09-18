"""仓库相对路径的 glob 匹配（验证器层）。

语义：

- "**/" 匹配零个或多个目录（"src/**/*.py" 同时覆盖 src/a.py 与 src/pkg/a.py）；
- 结尾的 "**" 匹配任意剩余路径；
- "*" 不跨目录，"? " 匹配单个字符。

与 adapters/dsh/adapter.py 里的匹配器**刻意不同**：那边把 "**/" 实现成"至少一层目录"，
因为它只服务 Phase 2 已有的 layer/language 映射表。两者都各自有契约测试钉住行为；
把语义改成一致会让 dsh 的既有映射表悄悄放大匹配范围（属于 Phase 2 的语义变更），
所以这里的差异是写下来的，不是疏忽。
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
