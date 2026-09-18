"""与协议无关的文本事实：从"本次改动引入的文本"里提取直接依赖。

预执行门禁要回答的问题是"**这次改动引入了什么**"，而不是"文件里原本有什么"
（后者属于 Phase 4 的 post-execute 与 Phase 5 的 Validator）。因此这里刻意只看
变更片段：edit 的 new_string 通常不是完整模块，用行级词法提取而不是 ast.parse。

放在公共层的理由：依赖是**核心上下文的维度**，不是某一家 Agent 的属性。
Phase 2 的 dsh Adapter 把它写在自己家里，Phase 6 的第二个 Adapter 就会再写一遍——
同一个语义出现两份实现，迟早会在其中一份上出现漏判。
"""

from __future__ import annotations

import re
from typing import Tuple

from policy.models import canonical_identifier

__all__ = ["IDENTIFIER_RE", "proposed_dependencies"]

# from 形态与 import 形态分开匹配：import a, b as c 里的每个名字都要算上，
# 否则"一次改动引入多个依赖"会被漏判（正是预执行门禁最不能漏的情况）。
FROM_IMPORT_RE = re.compile(r"^[ \t]*from[ \t]+([A-Za-z_][\w.]*)[ \t]+import\b", re.MULTILINE)
PLAIN_IMPORT_RE = re.compile(r"^[ \t]*import[ \t]+([^\n]+)$", re.MULTILINE)
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][\w.]*$")


def proposed_dependencies(text: str) -> Tuple[str, ...]:
    """从变更文本里提取顶层依赖标识（去重 + 稳定排序）。"""

    if not isinstance(text, str):
        raise TypeError(f"变更文本必须是字符串，得到 {type(text).__name__}")

    found: set[str] = set()

    def record(module: str) -> None:
        """登记一个模块标识：完整路径与末段都要算。

        规则写的是 `forbidden_dependency: [repository]`（末段），
        而改动里写的是 `from shop.order_repository import ...`（完整路径）。
        只取首段（`shop`）会让规则永远不命中——这正是"看起来在管、实际什么都没查"
        的典型形态；只取末段又会漏掉 `import a.b` 这种写法。
        两个都登记，规则作者写哪个都能命中。
        """

        canonical = canonical_identifier(module)
        if not canonical:
            return
        found.add(canonical)
        last = canonical.rsplit(".", 1)[-1]
        if last and last != canonical:
            found.add(last)

    for match in FROM_IMPORT_RE.finditer(text):
        record(match.group(1))

    for match in PLAIN_IMPORT_RE.finditer(text):
        for chunk in match.group(1).split("#")[0].split(","):
            token = chunk.strip()
            if not token:
                continue
            name = token.split()[0]  # 去掉 "as 别名"
            if not IDENTIFIER_RE.match(name):
                continue
            record(name)

    return tuple(sorted(found))
