"""check_arch_style.py 的空输入守卫：没有文档时必须报问题，不能报"平衡"。

对应审查结论 tools/check_arch_style.py:81：docs/project/architecture 被改名 / 移动 /
路径写错时 glob 返回空、problems 为空，main() 打印"概括性与精确性平衡"并退出 0。
"""

from __future__ import annotations

from pathlib import Path

import check_arch_style as module  # type: ignore[import-not-found]

BT3 = chr(96) * 3


def test_empty_architecture_directory_is_a_problem(monkeypatch, tmp_root, capsys):
    empty = tmp_root / "architecture"
    empty.mkdir()
    monkeypatch.setattr(module, "ARCH", empty)

    problems = module.check_docs()

    assert problems and "未找到任何架构文档" in problems[0]
    assert "architecture" in problems[0]

    assert module.main() == 1
    assert "平衡" not in capsys.readouterr().out


def test_real_architecture_docs_are_still_checked(monkeypatch, capsys):
    """反真空：仓库真实目录在场时走原路径，且真的读了文档。"""

    seen: list[Path] = []
    original = module.check_docs

    def spy() -> list:
        seen.extend(sorted(module.ARCH.glob("*.md")))
        return original()

    monkeypatch.setattr(module, "check_docs", spy)
    module.main()

    assert seen, "真实架构目录里应当有 *.md"
    assert "未找到任何架构文档" not in capsys.readouterr().out

def test_cjk_slash_prose_is_not_an_anchor():
    r"""`并且/或者`、`对/错` 这类散文不再是"精确锚点"（旧正则里 \w 含 CJK）。"""

    for prose in ("这里要说清并且/或者的关系", "对/错要分开讲"):
        assert module.ANCHOR.search(prose) is None, prose


def test_real_anchors_are_still_recognised():
    """阳性对照：文件:行、路径、枚举照旧算锚点。"""

    for anchor in (
        "见 tools/check_arch_style.py:28",
        "见 docs/project/architecture/术语与口径.md",
        "决策可能是 allow_with_warnings",
        "`some_identifier` 在这里",
    ):
        assert module.ANCHOR.search(anchor) is not None, anchor

def test_tilde_fence_hides_a_backtick_fence_inside_it():
    """`~~~` 块里的 ``` 不许翻转围栏状态（旧实现会把它当成关闭，块内代码变正文/反之）。"""

    text = chr(10).join([
        "散文一",
        "~~~",
        BT3,
        "code_inside",
        BT3,
        "~~~",
        "散文二",
    ])

    lines = [line for _number, line in module.prose_lines(text)]

    assert lines == ["散文一", "散文二"]


def test_longer_closing_fence_closes_and_shorter_does_not():
    """关闭标记必须不短于开启标记：块内的短围栏不算关闭。"""

    text = chr(10).join([
        "散文一",
        BT3 * 4,
        BT3,
        "code_inside",
        BT3 * 4,
        "散文二",
    ])

    lines = [line for _number, line in module.prose_lines(text)]

    assert lines == ["散文一", "散文二"]


def test_plain_backtick_fence_still_works():
    """阳性对照：普通 ``` 块照旧被跳过。"""

    text = chr(10).join(["散文一", BT3, "code_inside", BT3, "散文二"])

    assert [line for _number, line in module.prose_lines(text)] == ["散文一", "散文二"]
