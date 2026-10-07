"""build_notebooks.py 的结构守卫：章节目录 / 单元形状出错时必须显式失败。

这些守卫守的是"产物是生成的"这条前提：生成器静默覆盖或静默跳过，等于让某一章永远不被
检查（它的产物与内容源可以随便漂移，而 --check 一直是绿的）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from conftest import REPO_ROOT

TOOL = REPO_ROOT / "docs" / "project" / "architecture" / "tech-detail" / "build_notebooks.py"


def load_tool() -> Any:
    """按路径加载生成器（它不是包里的模块，也不是被测应用的一部分）。"""

    spec = importlib.util.spec_from_file_location("build_notebooks_under_test", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_duplicate_chapter_number_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """两个目录共用一个编号：必须报错退出，不能"字母序靠后的赢"。

    历史缺陷（medium 台账 MA0，build_notebooks.py:109）：`found[path.name[:2]] = path` 让后来的
    目录静默覆盖前面的——被覆盖的那一章永远生成不出来，也永远进不了 --check。
    """

    module = load_tool()
    for name in ("03-旧章", "03-新章"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "cells.py").write_text("", encoding="utf-8", newline="")
    monkeypatch.setattr(module, "HERE", tmp_path)

    with pytest.raises(SystemExit) as info:
        module.chapter_dirs()
    assert info.value.code == 2


def test_unique_chapter_numbers_still_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """对照组：编号唯一时照常返回（不是"永远报错"）。"""

    module = load_tool()
    for name in ("00-甲", "01-乙"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "cells.py").write_text("", encoding="utf-8", newline="")
    monkeypatch.setattr(module, "HERE", tmp_path)

    assert sorted(module.chapter_dirs()) == ["00", "01"]
