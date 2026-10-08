"""owasp/03_build.py：删旧产物之前必须先预检源文件（否则一次半截抓取会清空已发布的镜像）。

为什么需要：旧实现是"先 rmtree(OUT) 再逐篇读 SRC"。SRC 缺失 / 半截 / 某一篇读不出来时，
已发布的镜像被清空或在循环中途停成半份，而且没有回滚。
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "owasp_cheatsheets" / "03_build.py"
MIRROR = Path("docs") / "mirrors" / "owasp-cheatsheets"
INDEX_SLUG = "index"
SENTINEL = "上一轮已发布的文件"


def _placed_slugs() -> list[str]:
    slugs: list[str] = []
    for node in ast.walk(ast.parse(SCRIPT.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "put":
            for argument in node.args[2:]:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    slugs.append(argument.value)
    assert slugs, "没有从 03_build.py 里解析到任何 put(...) 字面量"
    return slugs


def _work(tmp_root: Path) -> Path:
    work = tmp_root / "_work" / "owasp-cheatsheets"
    work.mkdir(parents=True, exist_ok=True)
    return work


def _meta(entries: dict) -> str:
    return json.dumps(entries, ensure_ascii=False)


def _entry(slug: str, kind: str) -> dict:
    return {
        "slug": slug,
        "saved": True,
        "kind": kind,
        "url": "https://cheatsheetseries.owasp.org/cheatsheets/" + slug + ".html",
        "title": slug.replace("_", " "),
    }


def _index_slugs() -> list[str]:
    """脚本里 `INDEX_FILES` 声明的索引页 slug（夹具要按真实产物形状建全，理由见 gate 测试同名助手）。"""

    for node in ast.walk(ast.parse(SCRIPT.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "INDEX_FILES" for target in node.targets
        ):
            keys = [key.value for key in node.value.keys if isinstance(key, ast.Constant)]
            assert keys, "INDEX_FILES 里没有解析到任何 slug"
            return keys
    raise AssertionError("没有从 03_build.py 里解析到 INDEX_FILES")


def _prepare(tmp_root: Path, *, with_sources: bool) -> None:
    work = _work(tmp_root)
    slugs = _placed_slugs()
    entries = {slug: _entry(slug, "sheet") for slug in slugs}
    # 索引页按真实形状建全：`02_fetch.py` 的 `INDEXES` 抓 6 个（含 `Glossary`）。只造 `index`
    # 一个的话，双向核对会报 `EXTRA=[其余 5 个]`，构建在预检之前就以 exit 2 退出——
    # 那不是本用例要测的性质（"删旧产物之前先预检源文件"）。
    entries.update({slug: _entry(slug, "index") for slug in _index_slugs()})
    (work / "meta.json").write_text(_meta(entries), encoding="utf-8", newline="")
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
    mirror = tmp_root / MIRROR
    mirror.mkdir(parents=True, exist_ok=True)
    (mirror / "sentinel.md").write_text(SENTINEL + chr(10), encoding="utf-8", newline="")
    if with_sources:
        content_dir = work / "content"
        content_dir.mkdir(parents=True, exist_ok=True)
        for slug in list(entries):
            (content_dir / (slug + ".md")).write_text(
                "# " + slug + chr(10) + chr(10) + "正文。" + chr(10),
                encoding="utf-8",
                newline="",
            )


def _run(tmp_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_missing_sources_keep_the_published_mirror(tmp_root: Path) -> None:
    """源文件一份都没有：拒绝重建，且**不删**已发布的镜像。"""

    _prepare(tmp_root, with_sources=False)

    completed = _run(tmp_root)
    output = completed.stdout + completed.stderr

    assert completed.returncode == 2, output
    assert "预检失败" in output, output
    assert (tmp_root / MIRROR / "sentinel.md").is_file(), "旧镜像被删了：预检没有拦住这次重建"


def test_complete_sources_replace_the_mirror(tmp_root: Path) -> None:
    """阳性对照：源文件齐全时照旧重建（旧产物被替换，不再是"永远拒绝"）。"""

    _prepare(tmp_root, with_sources=True)

    completed = _run(tmp_root)
    output = completed.stdout + completed.stderr

    assert completed.returncode == 0, output
    assert "BUILD OK" in output, output
    assert not (tmp_root / MIRROR / "sentinel.md").exists(), "旧产物没有被替换"
