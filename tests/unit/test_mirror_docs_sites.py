"""mirror_docs.SITES：站点声明里不许有重复键（Python 只保留最后一个，前一个是死代码）。

为什么需要：python-pep-code-style 的 spec 里 "outbound_why" 出现过两次——读第一份的人会以为
镜像范围是"本站分区"，真正生效的却是后面那一句；这类重复不会报错，只会让声明与事实分叉。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "tools" / "mirror_docs.py"


def _sites_literal() -> ast.Dict:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "SITES" for target in node.targets
        ):
            assert isinstance(node.value, ast.Dict), "SITES 不是字面量字典"
            return node.value
    raise AssertionError("找不到 SITES 赋值")


def test_no_duplicate_keys_in_site_declarations() -> None:
    """SITES 里每个字典（含嵌套）都不许有重复键。"""

    duplicates: list[str] = []

    def walk(node: ast.AST) -> None:
        if isinstance(node, ast.Dict):
            seen: list[str] = []
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    if key.value in seen:
                        duplicates.append(key.value)
                    seen.append(key.value)
        for child in ast.iter_child_nodes(node):
            walk(child)

    walk(_sites_literal())

    assert duplicates == [], "站点声明里有重复键（前一份是死代码）：" + ", ".join(sorted(set(duplicates)))
