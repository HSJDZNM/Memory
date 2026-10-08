"""check_notebook.py 的结构校验：畸形 notebook 要报问题，不能抛异常。

对应审查结论 tools/check_notebook.py:25：json.loads 的返回值形状从未校验，
[] / "x" / 42 / null / cells=null / [null] 都会让 check() 抛
TypeError / AttributeError —— 于是 main() 对后面所有目标的检查一起中断。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import REPO_ROOT

from check_notebook import check  # type: ignore[import-not-found]

TOOL = REPO_ROOT / "tools" / "check_notebook.py"

GOOD = {
    "cells": [
        {
            "cell_type": "code",
            "metadata": {},
            "source": ["x = 1"],
            "outputs": [],
            "execution_count": None,
        }
    ],
    "metadata": {},
    "nbformat": 4,
    "nbformat_minor": 5,
}


def write(tmp_root: Path, name: str, payload: object) -> Path:
    path = tmp_root / name
    path.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
    return path


@pytest.mark.parametrize(
    ("payload", "needle"),
    [
        ([], "顶层必须是 JSON 对象"),
        ("x", "顶层必须是 JSON 对象"),
        (42, "顶层必须是 JSON 对象"),
        (None, "顶层必须是 JSON 对象"),
        ({**GOOD, "cells": None}, "cells 必须是数组"),
        ({**GOOD, "cells": "x"}, "cells 必须是数组"),
        ({**GOOD, "cells": [None]}, "单元必须是 JSON 对象"),
        ({**GOOD, "cells": ["x"]}, "单元必须是 JSON 对象"),
    ],
)
def test_malformed_shapes_are_reported_not_raised(tmp_root, payload, needle):
    path = write(tmp_root, "bad.ipynb", payload)

    problems = check(path)

    assert problems and needle in problems[0], problems


def test_a_wellformed_notebook_still_passes(tmp_root):
    """反真空：形状正确时不能报问题。"""

    assert check(write(tmp_root, "good.ipynb", GOOD)) == []


def test_the_cli_reports_the_shape_problem_instead_of_crashing(tmp_root):
    """真实命令验证：畸形 notebook 走 CLI 要 exit 1 + 说明，而不是 traceback。"""

    bad = write(tmp_root, "not-a-notebook.ipynb", [])
    completed = subprocess.run(
        [sys.executable, str(TOOL), str(bad)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
        check=False,
    )

    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert "顶层必须是 JSON 对象" in completed.stdout
    assert "Traceback" not in completed.stderr, completed.stderr
