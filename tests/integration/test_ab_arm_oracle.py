"""ab_arm 的 junit → 声明 node id 对齐：精确匹配，不许把别的用例的结论记到这条上。

为什么需要：旧实现用「文件主干是不是 name 的子串 + 末段后缀相等」两跳近似，两个方向都会读错——
a) `tests/test_a.py::test_foo` 会吃到 `tests/test_ab.py::test_foo` 的 passed；
b) 类作用域的 `tests/test_x.py::TestFoo::test_bar` 永远匹配不上 junit 键（那个键是
   `tests/test_x/TestFoo.py::test_bar`），真跑过的用例被记成 missing。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import ab_arm

pytestmark = pytest.mark.integration

FIXTURE_TREE_SOURCE = "def test_one():" + chr(10) + "    assert True" + chr(10)


def test_a_same_named_test_in_another_module_is_not_attributed() -> None:
    """只有 test_ab.py 的结果时，声明的 test_a.py::test_foo 必须是 missing。"""

    outcomes = {"tests/test_ab.py::test_foo": "passed"}

    declared = ab_arm.declared_outcomes(["tests/test_a.py::test_foo"], outcomes)

    assert declared == {"tests/test_a.py::test_foo": "missing"}


def test_class_scoped_node_id_matches_its_junit_key() -> None:
    """类作用域的 node id 必须能对上 junit 键（旧实现恒 missing）。"""

    outcomes = {"tests/test_x/TestFoo.py::test_bar": "passed"}

    declared = ab_arm.declared_outcomes(["tests/test_x.py::TestFoo::test_bar"], outcomes)

    assert declared == {"tests/test_x.py::TestFoo::test_bar": "passed"}


def test_exact_match_and_missing_are_distinguished() -> None:
    """同名不同模块都在时各归各的；真没跑到的仍是 missing。"""

    outcomes = {
        "tests/test_a.py::test_foo": "passed",
        "tests/test_ab.py::test_foo": "failed",
    }

    declared = ab_arm.declared_outcomes(
        ["tests/test_a.py::test_foo", "tests/test_ab.py::test_foo", "tests/test_c.py::test_foo"],
        outcomes,
    )

    assert declared["tests/test_a.py::test_foo"] == "passed"
    assert declared["tests/test_ab.py::test_foo"] == "failed"
    assert declared["tests/test_c.py::test_foo"] == "missing"


def test_run_oracle_reads_a_real_junit_report(tmp_root: Path) -> None:
    """真跑一次：声明的 node id 在真 junit 上判 passed。"""

    tree = tmp_root / "tree"
    (tree / "tests").mkdir(parents=True)
    (tree / "tests" / "test_demo.py").write_text(
        FIXTURE_TREE_SOURCE, encoding="utf-8", newline=chr(10)
    )
    arm_dir = tmp_root / "arm"
    arm_dir.mkdir(parents=True, exist_ok=True)

    reading = ab_arm.run_oracle(
        tree=tree,
        arm_dir=arm_dir,
        python=sys.executable,
        node_ids=["tests/test_demo.py::test_one"],
        timeout_s=120,
    )

    assert reading["status"] == "ran", reading.get("reason")
    assert reading["collected"] == 1
    assert reading["outcomes"] == {"tests/test_demo.py::test_one": "passed"}
