"""ab_measure 的 oracle：argv 形态与 cwd 基准必须由声明决定，不能靠猜。

为什么需要：
1. 冻结契约里 `test_command.argv` 是**解释器之后**的参数（解释器在 `python` 字段），
   而 ab_arm 的 measurement_input.json 写的是完整命令行；旧实现只认后者，
   于是按契约产出的 ["-m","pytest",…] 被直接交给 subprocess → FileNotFoundError →
   oracle 恒 unavailable（U1 读数永远是"起不来"）；
2. `cwd = tree / spec["cwd"]` 把两个生产方给的路径都解析错：ab_tasks 给的是绝对/进程 CWD
   相对的任务树路径，ab_arm 给的是**仓库根相对**的臂树路径——相对形态下 tree/<那段> 不存在
   → 直接 unavailable；绝对形态下 pathlib 丢掉左边的 tree，反事实路径会去跑**原始基线树**。

用例只驱动真实路径：真的起子进程跑 pytest，断言逐用例结果。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import ab_measure

pytestmark = pytest.mark.integration


def _tree(tmp_root: Path, *, name: str = "tree") -> Path:
    """最小被测树：自带空 pytest.ini（否则 pytest 会向上读到仓库自己的配置）。"""

    tree = tmp_root / name
    (tree / "tests").mkdir(parents=True, exist_ok=True)
    (tree / "pytest.ini").write_text("[pytest]" + chr(10), encoding="utf-8", newline=chr(10))
    (tree / "tests" / "test_demo.py").write_text(
        "def test_one():" + chr(10) + "    assert True" + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )
    return tree


def test_interpreter_relative_argv_gets_the_interpreter(tmp_root: Path) -> None:
    """契约形态：argv 是解释器之后的参数 → 前置 python。"""

    argv = ab_measure._oracle_argv({"argv": ["-m", "pytest", "-q"]}, "/py/python", tmp_root)

    assert argv == ["/py/python", "-m", "pytest", "-q"]


def test_full_command_argv_is_used_as_is(tmp_root: Path) -> None:
    """ab_arm 形态：argv 已经是完整命令行 → 原样使用，不再前置解释器。"""

    argv = ab_measure._oracle_argv(
        {"argv": [sys.executable, "-m", "pytest", "-q"]}, "/py/python", tmp_root
    )

    assert argv == [sys.executable, "-m", "pytest", "-q"]


def test_empty_argv_falls_back_to_the_default_target(tmp_root: Path) -> None:
    """没有 argv 时的回退不变：解释器 + 默认目标（树里有 tests/ 就只跑它）。"""

    tree = _tree(tmp_root)

    assert ab_measure._oracle_argv({}, "/py/python", tree) == [
        "/py/python", "-m", "pytest", "-q", "--tb=no", "tests",
    ]
    assert ab_measure._oracle_argv({}, "/py/python", tmp_root / "empty") == [
        "/py/python", "-m", "pytest", "-q", "--tb=no", ".",
    ]


def test_interpreter_relative_oracle_actually_runs(tmp_root: Path) -> None:
    """按冻结契约产出的 oracle 必须真的跑起来：旧实现这里恒 unavailable。"""

    tree = _tree(tmp_root)
    oracle = {
        "python": sys.executable,
        "test_command": {"argv": ["-m", "pytest", "-q"], "cwd": str(tree)},
        "fail_to_pass": [],
        "pass_to_pass": [],
    }

    trial = ab_measure.run_pytest_oracle(
        tree=tree, oracle=oracle, workdir=tmp_root / "work", timeout_s=120.0
    )

    assert trial["status"] == "available", trial.get("reason")
    assert trial["pytest_status"] == "ok", trial.get("reason")
    assert trial["counts"]["total"] == 1
    assert trial["cwd"] == "."