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

import shutil
import sys
from pathlib import Path

import pytest

import ab_measure

REPO_ROOT = Path(__file__).resolve().parents[2]

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

def _failing_test(path: Path) -> None:
    path.write_text(
        "def test_extra():" + chr(10) + "    assert False" + chr(10),
        encoding="utf-8",
        newline=chr(10),
    )


def test_cwd_from_the_declared_tree_is_rebased_into_the_measured_tree(tmp_root: Path) -> None:
    """ab_arm 形态（arm_tree.path + 仓库根相对的 cwd）：cwd 必须映射进**被测的那棵树**。

    副本里多一条会红的用例：如果实现跑去跑原始臂树，读数会是 ok——本条用例就是靠这个分辨的。
    """

    arm = _tree(tmp_root, name="arm")
    copy = tmp_root / "cf"
    shutil.copytree(arm, copy)
    _failing_test(copy / "tests" / "test_extra.py")
    relative = arm.relative_to(REPO_ROOT).as_posix()
    oracle = {
        "python": sys.executable,
        "arm_tree": {"path": relative},
        "test_command": {"argv": [sys.executable, "-m", "pytest", "-q"], "cwd": relative},
    }

    trial = ab_measure.run_pytest_oracle(
        tree=copy, oracle=oracle, workdir=tmp_root / "work", timeout_s=120.0
    )

    assert trial["status"] == "available", trial.get("reason")
    assert trial["pytest_status"] == "red", trial.get("reason")
    assert trial["cwd"] == "."


def test_repo_relative_cwd_pointing_at_the_measured_tree_is_accepted(tmp_root: Path) -> None:
    """cwd 正好是声明树本身（两个生产方的常态）：映射结果就是被测树。"""

    tree = _tree(tmp_root, name="rel-tree")
    relative = tree.relative_to(REPO_ROOT).as_posix()
    oracle = {
        "python": sys.executable,
        "arm_tree": {"path": relative},
        "test_command": {"argv": [sys.executable, "-m", "pytest", "-q"], "cwd": relative},
    }

    trial = ab_measure.run_pytest_oracle(
        tree=tree, oracle=oracle, workdir=tmp_root / "work", timeout_s=120.0
    )

    assert trial["status"] == "available", trial.get("reason")
    assert trial["pytest_status"] == "ok"
    assert trial["cwd"] == "."


def test_cwd_outside_every_candidate_tree_is_unavailable(tmp_root: Path) -> None:
    """cwd 指向别处的一棵真树：不许跑去那里跑，写 unavailable + 理由。"""

    tree = _tree(tmp_root, name="measured")
    elsewhere = _tree(tmp_root, name="elsewhere")
    oracle = {
        "python": sys.executable,
        "test_command": {"argv": [sys.executable, "-m", "pytest", "-q"], "cwd": str(elsewhere)},
    }

    trial = ab_measure.run_pytest_oracle(
        tree=tree, oracle=oracle, workdir=tmp_root / "work", timeout_s=120.0
    )

    assert trial["status"] == "unavailable"
    assert "解析不到" in trial["reason"]


def test_hand_written_tree_relative_cwd_still_runs(tmp_root: Path) -> None:
    """没有声明树的裸 oracle（cwd 相对被测树）保持老读法，不被这次收紧误伤。"""

    tree = _tree(tmp_root, name="manual")
    oracle = {
        "python": sys.executable,
        "test_command": {"argv": [sys.executable, "-m", "pytest", "-q"], "cwd": "tests"},
    }

    trial = ab_measure.run_pytest_oracle(
        tree=tree, oracle=oracle, workdir=tmp_root / "work", timeout_s=120.0
    )

    assert trial["status"] == "available", trial.get("reason")
    assert trial["pytest_status"] == "ok"
    assert trial["cwd"] == "tests"
