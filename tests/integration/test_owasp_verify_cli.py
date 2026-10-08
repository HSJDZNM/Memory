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
