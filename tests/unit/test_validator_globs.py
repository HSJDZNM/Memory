"""validators.globs 的匹配语义：整串锚定、"**/" 的零层语义与缓存。"""

from __future__ import annotations

from validators.globs import glob_match, glob_to_regex


def test_glob_match_anchors_the_whole_path() -> None:
    """$ 会匹配"结尾换行之前"的位置：必须用 \\Z（复核发现）。"""

    assert glob_match("*.md", "README.md")
    assert not glob_match("*.md", "README.md" + chr(10))
    assert not glob_match("**/*.py", "src/a.py" + chr(10))
    assert not glob_match("**", "a/b/c.py" + chr(10))


def test_glob_semantics_are_stable() -> None:
    """**/ 覆盖零层与多层；* 不跨目录；编译结果按 pattern 缓存。"""

    assert glob_match("**/*.md", "README.md")
    assert glob_match("**/*.md", "docs/notes.md")
    assert glob_match("src/**/*.py", "src/a.py")
    assert glob_match("src/**/*.py", "src/pkg/a.py")
    assert not glob_match("src/*.py", "src/pkg/a.py")
    assert glob_to_regex("**/*.md") is glob_to_regex("**/*.md")
