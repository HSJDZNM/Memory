"""ab_tasks 的三个守卫：完整 stdout、逐节点实测结果、基线树的阳性标记。

为什么需要：这三个洞都是"仪器自己不会失败"——套件输出超过 4000 字符时 node id 与
PASSED/FAILED 摘要在截断里静默消失；既非红也非绿的节点不触发任何拒收；非空的 baseline/
目录被当成"已解压"，来源记录缺失时 verify_oracle 直接 KeyError/FileNotFoundError。

用例用**合成任务**驱动真路径（真的起子进程跑 pytest），任务树自带一份空 pytest.ini：
否则 pytest 会向上找到本仓库的 pytest.ini（rootdir=仓库、-p no:cacheprovider 与它的
cache_dir + --strict-config 冲突，实测退出码 4），那是宿主配置泄漏，不是被测行为。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

import ab_tasks

pytestmark = pytest.mark.integration

INSTANCE = "demo__demo-1"
REVISION = ab_tasks.SOURCES["swe-bench-verified"].revision


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _task_root(tmp_root: Path, *, tests: int = 200) -> tuple[Path, Path]:
    """合成一个任务：rows.jsonl + baseline 树（自带空 pytest.ini），返回 (root, baseline)。"""

    root = tmp_root / "ab-tasks"
    dataset = root / ("swe-bench-verified@" + REVISION)
    dataset.mkdir(parents=True, exist_ok=True)
    row = {
        "instance_id": INSTANCE,
        "repo": "demo/demo",
        "base_commit": "0" * 40,
        "environment_setup_commit": "0" * 40,
        "version": "1.0",
        "difficulty": "easy",
        "FAIL_TO_PASS": json.dumps(["tests/test_demo.py::test_000"]),
        "PASS_TO_PASS": json.dumps(["tests/test_demo.py::test_001"]),
        "test_patch": "--- a/tests/test_demo.py\n+++ b/tests/test_demo.py\n",
        "patch": "",
        "problem_statement": "演示任务",
    }
    _write(dataset / "rows.jsonl", json.dumps(row, ensure_ascii=False) + "\n")
    baseline = root / INSTANCE / "baseline"
    _write(baseline / "pytest.ini", "[pytest]\n")
    test_source = "\n".join(
        "def test_%03d():\n    assert True" % index for index in range(tests)
    ) + "\n"
    _write(baseline / "tests" / "test_demo.py", test_source)
    return root, baseline


def _tail_node_ids(stdout_tail: str) -> list[str]:
    return [
        line.strip()
        for line in stdout_tail.splitlines()
        if "::" in line and not line.startswith(" ")
    ]


def test_collect_sees_every_node_id_when_stdout_exceeds_the_tail(tmp_root: Path) -> None:
    """200 条用例的收集输出超过 4000 字符时，node id 一条都不许丢。"""

    root, baseline = _task_root(tmp_root, tests=200)
    probe = ab_tasks._run(
        [sys.executable, "-m", "pytest", "--no-header", "-rA", "-p", "no:cacheprovider",
         "--collect-only", "-q", "tests/test_demo.py"],
        cwd=baseline,
        # 显式 basetemp：嵌套 pytest 若共用本会话的 temp 根，会按自己的保留策略清理
        # pytest-of-*/pytest-* 目录，把外层运行正在用的捕获文件一起端掉（实测外层会话崩在
        # sessionfinish：ValueError: I/O operation on closed file）。
        env={"PYTEST_ADDOPTS": "--basetemp=" + str(tmp_root / "probe-tmp")},
    )
    assert probe["exit_code"] == 0, probe["stderr_tail"]
    assert len(probe["stdout"]) > 4000, "这条用例的前提就是输出超过截断长度"
    # 4000 字符的尾巴只装得下一部分 node id：旧实现解析它，于是 collected 远小于 200
    tail_ids = _tail_node_ids(probe["stdout_tail"])
    assert 0 < len(tail_ids) < 200

    collected = ab_tasks._collect(INSTANCE, root=root, python=sys.executable)

    assert collected["exit_code"] == 0, collected["stderr_tail"]
    assert collected["collected"] == 200
    assert len(collected["node_ids"]) == 200
    # 读数里仍然只带截断尾：完整串只用在解析上，不让载荷跟着膨胀
    assert len(collected["stdout_tail"]) <= 2500
