"""check_arch_style.py 的空输入守卫：没有文档时必须报问题，不能报"平衡"。

对应审查结论 tools/check_arch_style.py:81：docs/project/architecture 被改名 / 移动 /
路径写错时 glob 返回空、problems 为空，main() 打印"概括性与精确性平衡"并退出 0。
"""

from __future__ import annotations

from pathlib import Path

import check_arch_style as module  # type: ignore[import-not-found]


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
