"""build_notebooks.py 的结构守卫：章节目录 / 单元形状出错时必须显式失败。

这些守卫守的是"产物是生成的"这条前提：生成器静默覆盖或静默跳过，等于让某一章永远不被
检查（它的产物与内容源可以随便漂移，而 --check 一直是绿的）。
"""

from __future__ import annotations

import importlib.util
import subprocess
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


def test_markdown_only_chapter_does_not_crash_the_table_helper_injection() -> None:
    """没有代码单元、而说明里恰好出现 `pad(` 时不许抛 StopIteration。

    历史缺陷（medium 台账 MA0，build_notebooks.py:157）：`next(...)` 没有默认值——注入表格
    工具的判据是"**任何**单元里出现 `pad(`"，而取值却要求存在代码单元。两者不一致时，
    生成器以一个未捕获的 StopIteration 收场，"结构结论"（没有代码单元）没人报出来。
    """

    from types import SimpleNamespace

    module = load_tool()
    cells = (("markdown", "说明里提到 pad( 这个词"),)
    spec = SimpleNamespace(cells=cells)

    assert module.notebook_cells(spec) == [("markdown", "说明里提到 pad( 这个词")]


def test_optimized_mode_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`-O` 会把 assert 全部剥离：讲解的检查退化成"打印 + 退出码 0"，必须显式拒绝。

    历史缺陷（medium 台账 MA0，00-技术总览.py:178）：十个章节的正面检查全是 assert，而 assert
    在 `python -O` / `PYTHONOPTIMIZE=1` 下会被**整个删掉**——脚本照样打印全部表格、退出码照样 0。
    这些脚本存在的意义就是"结论被钉住"，被剥离之后它们正好变成要防的那种假绿。
    """

    from types import SimpleNamespace

    module = load_tool()
    monkeypatch.setattr(module.sys, "flags", SimpleNamespace(optimize=1))

    with pytest.raises(SystemExit) as info:
        module.run_cells(SimpleNamespace(stem="00-假章", cells=()), tmp_path)
    assert info.value.code == 2


def test_generated_script_carries_the_optimize_guard() -> None:
    """产物本身也要拒绝 `-O`：它同样会被人工直接运行。"""

    from types import SimpleNamespace

    module = load_tool()
    spec = SimpleNamespace(stem="00-假章", title="假章")

    script = module.extract_script(spec, (("code", "assert True"),))

    assert "_sys.flags.optimize" in script
    assert "assert 已被剥离" in script


def test_worktree_guard_only_allows_this_runs_two_artifacts() -> None:
    """工作区守卫按**精确路径**放行，不按后缀。

    历史缺陷（medium 台账 MA0，build_notebooks.py:384）：过滤器只排除不以 .py / .ipynb 结尾的
    行，于是任何 .py / .ipynb 改动都被当成"本次生成的产物"——单元把 src/policy/models.py 改坏、
    新建 src/evil.py、删掉 src/x.py 都不会让生成失败，而注释承诺的正是"只允许两份产物"。
    """

    module = load_tool()
    allowed = {
        "docs/project/architecture/tech-detail/00-技术总览/00-技术总览.ipynb",
        "docs/project/architecture/tech-detail/00-技术总览/00-技术总览.py",
    }
    before = {" M src/policy/models.py"}
    after = before | {
        "?? docs/project/architecture/tech-detail/00-技术总览/00-技术总览.ipynb",
        "?? docs/project/architecture/tech-detail/00-技术总览/00-技术总览.py",
        "?? src/evil.py",
        "?? tools/evil.ipynb",
        " D src/policy/loader.py",
    }

    unexpected = module.unexpected_worktree_changes(before, after, allowed=allowed)

    assert unexpected == {
        "?? src/evil.py",
        "?? tools/evil.ipynb",
        " D src/policy/loader.py",
    }


def test_git_status_failure_does_not_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """`git status` 失败时必须显式失败：拿不到基线就证明不了"没动仓库"。

    历史缺陷（medium 台账 MA0，build_notebooks.py:334）：`check=False` 之后从不看 returncode，
    git 失败时 stdout 为空、`after - before` 恒为空——"单元执行期间动了仓库"这条守卫永远绿。
    """

    from types import SimpleNamespace

    module = load_tool()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=128, stdout="", stderr="fatal: not a git repository"
        ),
    )

    with pytest.raises(SystemExit) as info:
        module.git_untracked_snapshot()
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

def _run_builder(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_check_summary_does_not_claim_execution() -> None:
    """`--check` 不执行单元：收尾读数不许出现"代码单元执行"这种暗示执行过的措辞。

    2026-10-08 裁定：「把自己的局限说成查过了」是同一族缺陷——`--check`（不执行）与
    `--no-exec`（不执行）都曾打印「代码单元执行: 全部通过」。这一条把措辞钉住，改回去就红。
    """

    completed = _run_builder("--check", "--only", "00")
    assert completed.returncode == 0, completed.stdout + completed.stderr

    assert "未执行单元" in completed.stdout, completed.stdout
    assert "代码单元执行" not in completed.stdout, "`--check` 不许声称执行过单元：" + completed.stdout


def test_no_exec_summary_does_not_claim_execution() -> None:
    """`--no-exec` 同样不执行单元：读数里也要写明（它写的是"已写入"）。"""

    completed = _run_builder("--no-exec", "--only", "00")
    assert completed.returncode == 0, completed.stdout + completed.stderr

    assert "未执行单元" in completed.stdout, completed.stdout
    assert "代码单元执行" not in completed.stdout, "`--no-exec` 不许声称执行过单元：" + completed.stdout


def test_executing_mode_still_reports_the_execution_result() -> None:
    """阳性对照：真执行的那一档照旧报"代码单元执行"——收口不是把这句话删掉了事。"""

    completed = _run_builder("--only", "00")
    assert completed.returncode == 0, completed.stdout + completed.stderr

    assert "代码单元执行: 全部通过" in completed.stdout, completed.stdout
