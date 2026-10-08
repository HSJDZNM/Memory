"""tools/check_notebook.py：读/解析/编译三类失败都要变成这一条的读数，不许中断整轮。

为什么需要：`UnicodeDecodeError` 是 ValueError 子类（不在 `(OSError, json.JSONDecodeError)` 里）、
`OSError` 被盖成"不是合法 JSON"，而 `compile()` 对含 NUL 字节的正文抛 ValueError——三处都会让
整轮检查（含 build_notebooks.py --check）以栈回溯收场，而不是给出一条问题。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS = REPO_ROOT / "tools"


def _load():
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location(
        "check_notebook_under_test", TOOLS / "check_notebook.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _notebook(cells: list) -> str:
    return json.dumps({
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": cells,
    })


def _code_cell(source: list) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "source": source,
        "outputs": [],
        "execution_count": 1,
    }


def test_non_utf8_notebook_is_reported_not_raised(tmp_root: Path) -> None:
    """非 UTF-8 的 .ipynb：报一条问题，不许抛 UnicodeDecodeError。"""

    module = _load()
    path = tmp_root / "bad.ipynb"
    path.write_bytes(b'{"cells": [], "note": "\xff\xfe"}')

    problems = module.check(path)

    assert len(problems) == 1
    assert "不是 UTF-8" in problems[0]


def test_unreadable_path_is_not_called_invalid_json(tmp_root: Path) -> None:
    """路径是个目录 / 文件不存在：报"读不出来"，不许说成"不是合法 JSON"。"""

    module = _load()
    directory = tmp_root / "adir"
    directory.mkdir()

    problems = module.check(directory)

    assert len(problems) == 1
    assert "读不出来" in problems[0]
    assert "不是合法 JSON" not in problems[0]


def test_valid_notebook_passes(tmp_root: Path) -> None:
    """阳性对照：一份形状正确的 notebook 没有问题。"""

    module = _load()
    path = tmp_root / "ok.ipynb"
    path.write_text(_notebook([_code_cell(["value = 1"])]), encoding="utf-8", newline="")

    assert module.check(path) == []


def test_syntax_error_is_reported(tmp_root: Path) -> None:
    """阳性对照：真正的语法错误照旧报出来。"""

    module = _load()
    path = tmp_root / "syntax.ipynb"
    path.write_text(_notebook([_code_cell(["def broken(:" + chr(10)])]), encoding="utf-8", newline="")

    problems = module.check(path)

    assert any("语法错误" in item for item in problems), problems

def test_nul_byte_source_is_reported_without_a_fake_line_number(tmp_root: Path) -> None:
    """正文含 NUL 字节（JSON 里合法写作 \u0000）：记这一条，且不许写"第 None 行"。

    实测（Python 3.13）：compile 对 NUL 抛的是 SyntaxError（msg=source code string cannot
    contain null bytes，lineno=None）而不是 ValueError，所以旧处理器并没有漏掉它——漏掉的是
    行号：读数里出现了一个不存在的行号。
    """

    module = _load()
    path = tmp_root / "nul.ipynb"
    path.write_text(_notebook([_code_cell(["value = 1" + chr(0)])]), encoding="utf-8", newline="")

    problems = module.check(path)

    assert len(problems) == 1, problems
    assert "null bytes" in problems[0]
    assert "None 行" not in problems[0]


def test_syntax_error_keeps_its_line_number(tmp_root: Path) -> None:
    """阳性对照：真语法错误照旧带行号。"""

    module = _load()
    path = tmp_root / "syntax2.ipynb"
    path.write_text(_notebook([_code_cell(["def broken(:"])]), encoding="utf-8", newline="")

    problems = module.check(path)

    assert any("第 1 行" in item for item in problems), problems

def test_cell_level_messages_carry_the_file_path(tmp_root: Path) -> None:
    """单元级消息必须自带文件位置：main() 汇总多份 notebook 的问题，只写"单元 N"没法归属。"""

    module = _load()
    path = tmp_root / "loc.ipynb"
    path.write_text(_notebook([_code_cell(["def broken(:"])]), encoding="utf-8", newline="")

    problems = module.check(path)

    assert problems, "这份 notebook 应当报出问题"
    assert all(str(path) in item for item in problems), problems
    assert not any(item.startswith("单元 ") for item in problems), problems
