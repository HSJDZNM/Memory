"""owasp/03_build.py 的放置门禁：显式失败，且必须在 `python -O` 下照样生效。

为什么需要：`assert not missing and not extra` 在 PYTHONOPTIMIZE 下被整条删掉——表格漂移
（人工 placement 表 vs meta.json 实际保存的清单）于是变成"什么也没发生"，脚本继续用一份
对不上的映射重建镜像。这里用真脚本 + `-O` 各跑一次来钉住这个性质。
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "owasp_cheatsheets" / "03_build.py"
UNPLACED = "Not_Placed_In_The_Literal_Table_Cheat_Sheet"


def _placed_slugs() -> list[str]:
    """脚本里 `put(...)` 字面量声明的全部 slug（阳性对照要造一份与它完全一致的 meta）。"""

    slugs: list[str] = []
    for node in ast.walk(ast.parse(SCRIPT.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "put":
            for argument in node.args[2:]:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    slugs.append(argument.value)
    assert slugs, "没有从 03_build.py 里解析到任何 put(...) 字面量"
    return slugs


def _fixture(tmp_root: Path, slugs: list[str]) -> None:
    work = tmp_root / "_work" / "owasp-cheatsheets"
    work.mkdir(parents=True, exist_ok=True)
    (work / "meta.json").write_text(
        json.dumps({
            slug: {
                "slug": slug,
                "saved": True,
                "kind": "sheet",
                "url": "https://cheatsheetseries.owasp.org/cheatsheets/" + slug + ".html",
                "title": slug.replace("_", " "),
            }
            for slug in slugs
        }),
        encoding="utf-8",
        newline="",
    )
    (work / "taxonomy.json").write_text(
        json.dumps({
            "indexes": {
                "IndexASVS.html": [],
                "IndexProactiveControls.html": [],
                "IndexTopTen.html": [],
                "IndexMASVS.html": [],
            }
        }),
        encoding="utf-8",
        newline="",
    )


def _run_optimized(tmp_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-O", str(SCRIPT)],
        cwd=tmp_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_no_assert_is_used_as_a_gate() -> None:
    """这个脚本里不许出现 assert：它在 -O 下会被删掉。"""

    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    offenders = [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Assert)]

    assert offenders == [], "这些行用 assert 当门禁（-O 下会消失）：" + repr(offenders)


def test_placement_mismatch_fails_even_under_optimize(tmp_root: Path) -> None:
    """表里有未归类的保存页：`python -O` 下也必须非零退出并写明原因。"""

    _fixture(tmp_root, [UNPLACED])

    completed = _run_optimized(tmp_root)
    output = completed.stdout + completed.stderr

    assert completed.returncode != 0, output
    assert "placement mismatch" in output, output
    assert UNPLACED in output


def test_matching_table_does_not_trip_the_gate(tmp_root: Path) -> None:
    """阳性对照：保存的页都在表格里时，这条门禁不报（别把它写成"永远红"）。"""

    _fixture(tmp_root, _placed_slugs())

    completed = _run_optimized(tmp_root)
    output = completed.stdout + completed.stderr

    assert "placement mismatch" not in output, output
