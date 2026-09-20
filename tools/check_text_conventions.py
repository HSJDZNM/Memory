"""检查仓库文本文件是否符合 .editorconfig/.gitattributes 约定。

用法：

    python tools/check_text_conventions.py            # 检查本项目自己维护的文本文件
    python tools/check_text_conventions.py --all      # 连第三方镜像一起检查
    python tools/check_text_conventions.py 路径...    # 只检查指定文件

默认检查所有会被提交的文本文件（git ls-files --cached --others --exclude-standard），
跳过二进制、.gitignore 命中的生成物，以及**逐字复制**的第三方文档镜像
（镜像里的行尾空白来自上游原文，改动它们会在下次镜像同步时被覆盖）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".7z", ".rar", ".exe", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf",
    ".otf", ".mp3", ".mp4", ".mov", ".wav", ".onnx", ".pt", ".safetensors", ".parquet",
}
CRLF_SUFFIXES = {".bat", ".cmd", ".ps1"}

# 逐字复制上游原文的目录/文件：这些内容不按本仓库的排版约定改写。
MIRRORED_PREFIXES = (
    "docs/dora-capabilities/",
    "docs/dotnet-design-guidelines/",
    "docs/gitlab-code-review/",
    "docs/google-eng-practices/",
    "docs/owasp-cheatsheets/",
    "docs/python-pep-code-style/",
    "tools/owasp_cheatsheets/",
)


def is_mirrored(path: Path) -> bool:
    """判断路径是否属于第三方文档镜像（按 "/" 分隔的仓库相对路径比较）。"""

    normalized = path.as_posix()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return any(normalized.startswith(prefix) for prefix in MIRRORED_PREFIXES)


def tracked_files() -> list[Path]:
    """列出会被提交的文件。

    必须用 `-z`（NUL 分隔）而不是按行切分：`core.quotepath` 默认开启，git 会把非 ASCII
    路径转义成八进制并加引号（`"docs/.../\344\275\277\347\224\250.md"`）。那种字符串
    `Path.is_file()` 为假，于是这些文件在下面的循环里被**静默跳过**——门禁少查了几个文件
    却不报任何错。改成中文文件名时就是靠"检查数从 343 掉到 338"才发现的。
    """

    completed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return [Path(item) for item in completed.stdout.split(chr(0)) if item.strip()]


def main(argv: list[str]) -> int:
    include_mirrors = "--all" in argv[1:]
    explicit = [item for item in argv[1:] if item != "--all"]
    targets = [Path(item) for item in explicit] or tracked_files()
    problems: list[str] = []
    checked = 0
    skipped = 0

    for path in targets:
        if not path.is_file() or path.suffix.lower() in BINARY_SUFFIXES:
            continue
        if not explicit and not include_mirrors and is_mirrored(path):
            skipped += 1
            continue
        # 只检查文本文件：含 NUL 视为二进制
        data = path.read_bytes()
        if b"\x00" in data[:4096]:
            continue
        checked += 1
        if path.suffix.lower() in CRLF_SUFFIXES:
            continue
        if b"\r\n" in data:
            problems.append(f"{path}: 含 CRLF，仓库约定为 LF")
        if data.startswith(b"\xef\xbb\xbf"):
            problems.append(f"{path}: 含 UTF-8 BOM")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            problems.append(f"{path}: 不是合法 UTF-8（{error}）")
            continue
        if text and not text.endswith(chr(10)):
            problems.append(f"{path}: 文件未以单个换行符结尾")
        if text.endswith(chr(10) + chr(10)):
            problems.append(f"{path}: 文件以多个空行结尾")
        for number, line in enumerate(text.splitlines(), start=1):
            if line != line.rstrip():
                problems.append(f"{path}:{number}: 行尾有空白")

    for problem in problems:
        print(problem)
    suffix = f"，跳过第三方镜像 {skipped} 个" if skipped else ""
    print(f"检查 {checked} 个文本文件，问题 {len(problems)} 处{suffix}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
