"""OWASP 05_verify CLI：非 UTF-8 的 Markdown 必须被**报出来**，而不是让校验崩在第 1 节。

为什么需要：第 1 节（链接完整性）用严格 UTF-8 读每个 .md，而"编码异常"是第 2 节才报的检查。
一份非 UTF-8 的正文会让整个脚本带 UnicodeDecodeError 中断：第 2 节永远跑不到，
输出的是一段栈回溯而不是诊断——校验器在它专门要检的输入上失明。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "owasp_cheatsheets" / "05_verify.py"
MIRROR = Path("docs") / "mirrors" / "owasp-cheatsheets"

pytestmark = pytest.mark.integration


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def _mirror(tmp_root: Path) -> Path:
    """最小镜像树：README / STRUCTURE / manifest / LICENSE 齐全，+ 一个坏编码的 .md。"""

    root = tmp_root / MIRROR
    _write(root / "README.md", "# 说明" + chr(10))
    _write(root / "STRUCTURE.md", "# 结构" + chr(10))
    _write(root / "LICENSE.txt", "CC BY-SA 4.0" + chr(10))
    _write(root / "good.md", "# 好文件" + chr(10) + chr(10) + "[断链](missing.md)" + chr(10))
    _write(root / "manifest.json", json.dumps({"pages": [], "pages_excluded": 0, "pages_candidate": 0}) + chr(10))
    # 非 UTF-8：0xff 不是合法 UTF-8 起始字节
    (root / "bad.md").write_bytes(b"# \xff\xfe\x80" + bytes([10]))
    return root


def _run(tmp_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_non_utf8_markdown_is_reported_not_crashed(tmp_root: Path) -> None:
    """坏编码的文件要被第 2 节报成「编码异常」，退出码 1，且不许出现栈回溯。"""

    _mirror(tmp_root)
    completed = _run(tmp_root)
    output = completed.stdout + completed.stderr

    assert "Traceback" not in output, output
    assert "UnicodeDecodeError" not in output, output
    assert "编码异常" in completed.stdout, output
    assert "断链 1 条" in completed.stdout, output
    assert completed.returncode == 1


def test_clean_mirror_still_passes(tmp_root: Path) -> None:
    """这一层守护不许把干净镜像判红：坏文件删掉后必须 PASS、退出码 0。"""

    root = _mirror(tmp_root)
    (root / "bad.md").unlink()
    (root / "missing.md").write_text("# 目标" + chr(10), encoding="utf-8", newline="")
    digest = hashlib.sha256((root / "good.md").read_bytes()).hexdigest()
    _write(
        root / "manifest.json",
        json.dumps(
            {
                "pages": [
                    {
                        "local_path": "good.md",
                        "bytes": (root / "good.md").stat().st_size,
                        "sha256": digest,
                    }
                ],
                "pages_excluded": 0,
                "pages_candidate": 1,
            }
        )
        + chr(10),
    )

    completed = _run(tmp_root)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "PASS" in completed.stdout

def test_root_relative_link_resolves_against_the_mirror_root(tmp_root: Path) -> None:
    """`[x](/target.md)` 指的是镜像根，不是文件系统根：不许被判成断链。"""

    root = _mirror(tmp_root)
    (root / "bad.md").unlink()
    _write(root / "target.md", "# 目标" + chr(10))
    (root / "good.md").write_text(
        "# 好文件" + chr(10) + chr(10) + "[根相对](/target.md)" + chr(10),
        encoding="utf-8",
        newline="",
    )

    completed = _run(tmp_root)

    assert "断链" not in completed.stdout, completed.stdout
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "PASS" in completed.stdout

def test_broken_manifest_json_is_a_diagnostic_not_a_traceback(tmp_root: Path) -> None:
    """manifest.json 不是合法 JSON：报问题、退出 1，不许栈回溯。"""

    root = _mirror(tmp_root)
    (root / "bad.md").unlink()
    (root / "missing.md").write_text("# 目标" + chr(10), encoding="utf-8", newline="")
    (root / "manifest.json").write_text("{ 不是 JSON", encoding="utf-8", newline="")

    completed = _run(tmp_root)

    output = completed.stdout + completed.stderr
    assert "Traceback" not in output, output
    assert "manifest.json 读不出来" in completed.stdout, output
    assert completed.returncode == 1


def test_manifest_entry_without_fields_is_reported(tmp_root: Path) -> None:
    """条目缺 local_path / bytes / sha256：报形状问题，不许 KeyError。"""

    root = _mirror(tmp_root)
    (root / "bad.md").unlink()
    (root / "missing.md").write_text("# 目标" + chr(10), encoding="utf-8", newline="")
    _write(
        root / "manifest.json",
        json.dumps({"pages": [{"local_path": "good.md"}], "pages_excluded": 0, "pages_candidate": 1})
        + chr(10),
    )

    completed = _run(tmp_root)

    output = completed.stdout + completed.stderr
    assert "Traceback" not in output, output
    assert "manifest 校验失败" in completed.stdout
    assert "字节数不符" in completed.stdout, output
    assert completed.returncode == 1

def test_indented_fence_hides_its_links(tmp_root: Path) -> None:
    """缩进 0–3 空格的围栏（列表里很常见）同样要剥掉：块内的断链不算断链。

    这里刻意用 `~~~`：缩进的反引号围栏会被行内代码规则（`` `[^`]*` ``）顺带吃掉，
    测不到"围栏没剥"这条路径；波浪号围栏没有这个副作用，能真正区分修前修后。
    """

    root = _mirror(tmp_root)
    (root / "bad.md").unlink()
    _write(root / "target.md", "# 目标" + chr(10))
    (root / "good.md").write_text(
        "# 好文件" + chr(10) + chr(10)
        + "   ~~~" + chr(10)
        + "   [示例](/definitely-missing.md)" + chr(10)
        + "   ~~~" + chr(10),
        encoding="utf-8",
        newline="",
    )

    completed = _run(tmp_root)

    assert "断链" not in completed.stdout, completed.stdout


def test_four_backtick_fence_containing_a_triple_backtick_line(tmp_root: Path) -> None:
    """四反引号围栏里的 ``` 行不算关闭：块内的断链不许被查出来。"""

    root = _mirror(tmp_root)
    (root / "bad.md").unlink()
    _write(root / "target.md", "# 目标" + chr(10))
    (root / "good.md").write_text(
        "# 好文件" + chr(10) + chr(10)
        + chr(96) * 4 + chr(10)
        + chr(96) * 3 + chr(10)
        + "[示例](/definitely-missing.md)" + chr(10)
        + chr(96) * 4 + chr(10),
        encoding="utf-8",
        newline="",
    )

    completed = _run(tmp_root)

    assert "断链" not in completed.stdout, completed.stdout


def test_a_real_broken_link_is_still_reported(tmp_root: Path) -> None:
    """阳性对照：正文里的断链照旧报出来（这次收口不许把真问题一起吃掉）。"""

    root = _mirror(tmp_root)
    (root / "bad.md").unlink()
    _write(root / "target.md", "# 目标" + chr(10))
    (root / "good.md").write_text(
        "# 好文件" + chr(10) + chr(10) + "[真断链](/nope.md)" + chr(10),
        encoding="utf-8",
        newline="",
    )

    completed = _run(tmp_root)

    assert "断链" in completed.stdout, completed.stdout
    assert "/nope.md" in completed.stdout
