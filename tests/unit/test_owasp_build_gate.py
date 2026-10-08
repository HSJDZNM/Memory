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


def _index_slugs() -> list[str]:
    """脚本里 `INDEX_FILES` 声明的索引页 slug。

    夹具要按**真实产物形状**建树：`02_fetch.py` 的 `INDEXES` 会抓全部 6 个索引页（含 `Glossary`），
    发布镜像里就有 6 份索引（`docs/mirrors/owasp-cheatsheets/00_索引与标准/` 下 6 个文件）。
    夹具只造 sheet 的话，`03_build.py` 的"落位表 vs 产物"双向核对会**正确地**报
    `EXTRA=[...索引页]`——那是夹具不像真实产物，不是核对写错了。
    """

    for node in ast.walk(ast.parse(SCRIPT.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "INDEX_FILES" for target in node.targets
        ):
            keys = [key.value for key in node.value.keys if isinstance(key, ast.Constant)]
            assert keys, "INDEX_FILES 里没有解析到任何 slug"
            return keys
    raise AssertionError("没有从 03_build.py 里解析到 INDEX_FILES")


def _fixture(tmp_root: Path, slugs: list[str]) -> None:
    work = tmp_root / "_work" / "owasp-cheatsheets"
    work.mkdir(parents=True, exist_ok=True)

    def record(slug: str, kind: str) -> dict:
        return {
            "slug": slug,
            "saved": True,
            "kind": kind,
            "url": "https://cheatsheetseries.owasp.org/cheatsheets/" + slug + ".html",
            "title": slug.replace("_", " "),
        }

    entries = {slug: record(slug, "sheet") for slug in slugs}
    entries.update({slug: record(slug, "index") for slug in _index_slugs()})
    (work / "meta.json").write_text(
        json.dumps(entries),
        encoding="utf-8",
        newline="",
    )
    # 源文件也写齐：这样阳性对照能一路走到 `BUILD OK`（不留"夹具本来就没法跑完"的模糊地带）。
    content = work / "content"
    content.mkdir(parents=True, exist_ok=True)
    for slug in entries:
        (content / (slug + ".md")).write_text(
            "# " + slug + chr(10) + chr(10) + "正文。" + chr(10),
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

    assert completed.returncode == 0, output
    assert "placement mismatch" not in output, output


def test_index_table_drift_fails_even_under_optimize(tmp_root: Path) -> None:
    """索引页落位表同样双向核对：`meta.json` 里出现 `INDEX_FILES` 没有的索引页必须显式拒绝。

    旧实现只有 sheet 那一半核对，索引页漂移会一路走到 `dest_of()` 返回 `None`，
    再以 `TypeError: expected str, bytes or os.PathLike object, not NoneType` 炸出来。
    """

    _fixture(tmp_root, _placed_slugs())
    meta_path = tmp_root / "_work" / "owasp-cheatsheets" / "meta.json"
    entries = json.loads(meta_path.read_text(encoding="utf-8"))
    drifted = "Not_An_Index_File"
    entries[drifted] = {
        "slug": drifted,
        "saved": True,
        "kind": "index",
        "url": "https://cheatsheetseries.owasp.org/" + drifted + ".html",
        "title": drifted,
    }
    meta_path.write_text(json.dumps(entries), encoding="utf-8", newline="")

    completed = _run_optimized(tmp_root)
    output = completed.stdout + completed.stderr

    assert completed.returncode == 2, output
    assert "index placement mismatch" in output, output
    assert drifted in output, output
    assert "TypeError" not in output, output
