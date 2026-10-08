"""仓库配置约定：.editorconfig / .gitignore 这两处"配置本身"也要能被检查。

它们没有执行体——一个由编辑器读、一个由 git 读——所以缺陷只在"编辑器 / git 真的那样做"
时才暴露，没人会在读配置时发现。用例因此用各自的**真实读者**来判定：.gitignore 用
git check-ignore（不自己实现一套匹配），.editorconfig 按节解析后查覆盖面与取值（纯数据）。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _editorconfig_sections() -> dict[str, dict[str, str]]:
    """按节解析 .editorconfig：{节名: {键: 值}}（只为读取，不重实现匹配引擎）。"""

    sections: dict[str, dict[str, str]] = {}
    current: str | None = None
    for line in (REPO_ROOT / ".editorconfig").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1]
            sections[current] = {}
            continue
        if current is None or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        sections[current][key.strip()] = value.strip()
    return sections


def _is_ignored(relative: str) -> bool:
    """交给 git 自己判定：exit 0 = 命中忽略规则，1 = 不忽略；--no-index 允许问不存在的路径。"""

    completed = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", relative],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode in (0, 1), completed.stderr
    return completed.returncode == 0


def test_editorconfig_covers_every_makefile_name_gnu_make_reads() -> None:
    """GNU make 认三个默认文件名，还有被 include 的 *.mk：一节的 glob 必须全罩住。

    为什么必须这样：只写 [Makefile] 时，GNUmakefile / makefile / *.mk 会落回 [*] 的
    indent_style = space——编辑器一保存就把配方行的 TAB 换成空格，make 直接报
    missing separator，而"保存时自动缩进"这件事没有人会怀疑到 .editorconfig 头上。
    """

    sections = _editorconfig_sections()
    header = next((name for name in sections if "Makefile" in name), None)
    assert header is not None, "没有任何一节覆盖 make 的配方文件"

    # 节名可能是 {a,b,c} 花括号组：去掉花括号后逐个比对
    patterns = {item.strip() for item in header.strip("{}").split(",")}
    assert {"Makefile", "GNUmakefile", "makefile", "*.mk"} <= patterns, patterns
    assert sections[header]["indent_style"] == "tab"
    assert int(sections[header].get("tab_width", "0")) > 2, (
        "tab_width 不设就继承 [*] 的 indent_size，TAB 只有两列宽"
    )


def test_gitignore_covers_sqlite_sidecar_files() -> None:
    """WAL / journal 模式下的 SQLite 会留下与主库同名的兄弟文件，只忽略主库等于没忽略。

    为什么必须这样：`foo.sqlite-wal` / `foo.sqlite-shm` / `foo.sqlite3-journal` 不匹配
    `*.sqlite` 这类后缀模式，可以被直接提交——而它们含有还没 checkpoint 的表内容。
    反向对照：显式后缀不是通配，`probe.db-archive.tar` 仍应可提交。
    """

    for base in ("probe.sqlite", "probe.sqlite3", "probe.db"):
        assert _is_ignored(base), base
        for suffix in ("-wal", "-shm", "-journal"):
            assert _is_ignored(base + suffix), base + suffix
    assert not _is_ignored("probe.db-archive.tar"), "只想盖住兄弟文件，不想吞掉同前缀的其它产物"
