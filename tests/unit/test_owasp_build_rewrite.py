"""owasp/03_build.py 的 rewrite：只改正文，不碰围栏与行内代码。

为什么需要：旧实现在整篇 Markdown 上跑 LINKRE.sub，于是代码样例里指向 cheatsheetseries.owasp.org
的 markdown 链接被改成相对路径——发布出去的示例代码与上游原文不一致。
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "tools" / "owasp_cheatsheets" / "03_build.py"
BT = chr(96)
FENCE = BT * 3
TARGET_URL = "https://cheatsheetseries.owasp.org/cheatsheets/Target_Cheat_Sheet.html"
TARGET_LOCAL = "/mirror/01_x/target.md"
SRC_PATH = "/mirror/01_x/page.md"


def _load_rewrite(source_text: str):
    """把 rewrite 与它依赖的 LINKRE 从源码里取出来单独跑（脚本 import 时会读 _work/ 写 docs/）。"""

    tree = ast.parse(source_text)
    namespace: dict = {"os": os, "re": re, "BT": BT, "FENCE": FENCE,
                       "url2path": {TARGET_URL: TARGET_LOCAL}}
    found_rewrite = False
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "LINKRE" for target in node.targets
        ):
            namespace["LINKRE"] = eval(
                compile(ast.Expression(node.value), str(SOURCE), "eval"), {"re": re}
            )
        if isinstance(node, ast.FunctionDef) and node.name == "rewrite":
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), namespace)
            found_rewrite = True
    assert found_rewrite, "没有在源码里找到 rewrite"
    assert "LINKRE" in namespace, "没有在源码里找到 LINKRE"
    return namespace["rewrite"]


def _rel() -> str:
    return os.path.relpath(TARGET_LOCAL, os.path.dirname(SRC_PATH)).replace("\\", "/")


def test_prose_links_are_rewritten() -> None:
    """阳性对照：正文里的站内链接照旧改成本地相对路径。"""

    rewrite = _load_rewrite(SOURCE.read_text(encoding="utf-8"))
    md = "见 [目标](" + TARGET_URL + ")。" + chr(10)

    assert rewrite(md, SRC_PATH) == "见 [目标](" + _rel() + ")。" + chr(10)


def test_fenced_code_is_left_alone() -> None:
    """围栏里的链接是示例代码：一个字都不许改。"""

    rewrite = _load_rewrite(SOURCE.read_text(encoding="utf-8"))
    md = chr(10).join([
        "正文 [目标](" + TARGET_URL + ")",
        FENCE + "markdown",
        "[示例](" + TARGET_URL + ")",
        FENCE,
    ])

    result = rewrite(md, SRC_PATH)

    assert "[示例](" + TARGET_URL + ")" in result
    assert "正文 [目标](" + _rel() + ")" in result


def test_inline_code_is_left_alone() -> None:
    """行内代码里的链接同样是示例。"""

    rewrite = _load_rewrite(SOURCE.read_text(encoding="utf-8"))
    md = "写法是 " + BT + "[x](" + TARGET_URL + ")" + BT + "，正文 [目标](" + TARGET_URL + ")" + chr(10)

    result = rewrite(md, SRC_PATH)

    assert BT + "[x](" + TARGET_URL + ")" + BT in result
    assert "正文 [目标](" + _rel() + ")" in result


def test_mutation_without_the_code_guard_is_caught() -> None:
    """变异证明：把围栏/行内代码的保护去掉（回到"整篇 sub"），本文件的用例会红。

    做法是在保护逻辑之前插一条 `return LINKRE.sub(repl, md)`（等价于旧实现的行为），
    再断言"代码样例确实被改写了"——即证明上面两条用例对这段保护是敏感的，不是摆设。
    """

    source = SOURCE.read_text(encoding="utf-8")
    anchor = "    out, in_fence = [], False"
    assert anchor in source, "变异锚点不见了：rewrite 的保护逻辑被改写过，请更新这条用例"
    mutated = source.replace(anchor, "    return LINKRE.sub(repl, md)\n" + anchor, 1)

    rewrite = _load_rewrite(mutated)
    md = chr(10).join([FENCE, "[示例](" + TARGET_URL + ")", FENCE])

    assert "[示例](" + _rel() + ")" in rewrite(md, SRC_PATH), (
        "去掉保护之后围栏内的链接应当被改写（否则本文件的用例测不到这段保护）"
    )
