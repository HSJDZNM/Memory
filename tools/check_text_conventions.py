"""检查仓库文本文件是否符合 .editorconfig/.gitattributes 约定。

用法：

    python tools/check_text_conventions.py            # 检查本项目自己维护的文本文件
    python tools/check_text_conventions.py --all      # 连第三方镜像一起检查
    python tools/check_text_conventions.py 路径...    # 只检查指定文件

默认检查所有会被提交的文本文件（git ls-files --cached --others --exclude-standard），
跳过二进制、.gitignore 命中的生成物，以及**逐字复制**的第三方文档镜像
（镜像里的行尾空白来自上游原文，改动它们会在下次镜像同步时被覆盖）。

「没查」与「查过了」必须分得开，所以下面三种情况都失败关闭，绝不静默：

- 被跟踪或显式指定的文件读不到、或工作树里根本不存在（内容可能仍在索引与即将推送的
  提交里）→ 记问题，退出 1；
- 两个 git 清单（`git ls-files`）执行失败 → 直接失败关闭，**不**退化成「没有文件可查」；
- 清单为空 → 同样失败关闭，不把「没东西可查」当成「查过了」。

只有「未跟踪、且只是读不到」这一类记一条显式跳过（「跳过（未跟踪且读取失败）」），
连同原因打进报告。
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
    "docs/mirrors/dora-capabilities/",
    "docs/mirrors/dotnet-design-guidelines/",
    "docs/mirrors/gitlab-code-review/",
    "docs/mirrors/google-eng-practices/",
    "docs/mirrors/owasp-cheatsheets/",
    "docs/mirrors/python-pep-code-style/",
    "tools/owasp_cheatsheets/",
)


def is_mirrored(path: Path) -> bool:
    """判断路径是否属于第三方文档镜像（按 "/" 分隔的仓库相对路径比较）。"""

    normalized = path.as_posix()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return any(normalized.startswith(prefix) for prefix in MIRRORED_PREFIXES)


def _git_listed(args: list[str]) -> set[str] | None:
    """跑一次 `git ls-files` 并返回路径集合；**git 失败返回 None**（调用方必须失败关闭）。

    失败不能退化成空集合：那正好是绕过门禁的形状——`GIT_INDEX_FILE=<不存在的索引>` 会让
    `git ls-files --cached` 空手而归，被跟踪的文件于是被误判成未跟踪，「读不到」被记成跳过、
    门禁放行（pre-push 钩子继承调用方环境）。
    """

    completed = subprocess.run(
        ["git", "ls-files", "-z", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode != 0:
        return None
    return {item for item in completed.stdout.split(chr(0)) if item.strip()}


def tracked_files() -> set[str] | None:
    """列出会被提交的文件。

    必须用 `-z`（NUL 分隔）而不是按行切分：`core.quotepath` 默认开启，git 会把非 ASCII
    路径转义成八进制并加引号（`"docs/.../\344\275\277\347\224\250.md"`）。那种字符串
    `Path.is_file()` 为假，于是这些文件在下面的循环里被**静默跳过**——门禁少查了几个文件
    却不报任何错。改成中文文件名时就是靠"检查数从 343 掉到 338"才发现的。
    """

    return _git_listed(["--cached", "--others", "--exclude-standard"])


def committed_paths() -> set[str] | None:
    """`git ls-files --cached` 的路径集合：用来区分「仓库内容」与「路过工作树的临时文件」。

    只有未跟踪文件需要这个区分：被跟踪文件是门禁的责任对象，读不到就必须失败关闭；
    未跟踪文件不是仓库内容，本脚本对它没有可执行的结论。
    """

    return _git_listed(["--cached"])


def main(argv: list[str]) -> int:
    include_mirrors = "--all" in argv[1:]
    explicit = [item for item in argv[1:] if item != "--all"]
    # 两个 git 清单都必须成功：失败时不能退化成「没有文件可查」，也不能把被跟踪的文件当成
    # 未跟踪（见 _git_listed 的说明）。
    known = committed_paths()
    if known is None:
        print("git ls-files --cached 执行失败：无法区分仓库内容与临时文件，按失败关闭处理")
        return 1
    if explicit:
        targets = [Path(item) for item in explicit]
    else:
        listed = tracked_files()
        if listed is None:
            print("git ls-files 执行失败：无法确定要检查哪些文件，按失败关闭处理")
            return 1
        if not listed:
            print("git 没有列出任何文件：不把「没东西可查」当成「查过了」")
            return 1
        targets = [Path(item) for item in sorted(listed)]
    problems: list[str] = []
    unreadable: list[str] = []
    checked = 0
    skipped = 0

    for path in targets:
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        if not explicit and not include_mirrors and is_mirrored(path):
            skipped += 1
            continue
        if not path.is_file():
            # 工作树里没有这个文件。被跟踪 / 显式指定的路径**不是「没有违规」，而是「无法证明」**：
            # 内容可能仍在索引与即将推送的提交里（实测：提交一个带行尾空白的文件、再从工作树
            # rm 掉，旧实现会打印「检查 0 个文本文件、问题 0 处」并放行推送）。
            if explicit or path.as_posix() in known:
                problems.append(f"{path}: 工作树里不存在，无法检查文本约定")
            continue
        # 只检查文本文件：含 NUL 视为二进制
        try:
            data = path.read_bytes()
        except OSError as error:
            # 读不到的文件既不能算通过、也不能算违规，但不许静默：
            #   - 被跟踪文件 / 显式指定的路径是门禁的责任对象 → 记问题，失败关闭；
            #   - 未跟踪文件（常是别的进程握着的临时文件，本仓库也要求它不该落在工作树里）
            #     不是仓库内容 → 单独记一条跳过，连同原因打进报告。
            if explicit or path.as_posix() in known:
                problems.append(f"{path}: 读取失败（{type(error).__name__}）")
            else:
                unreadable.append(f"{path}: {type(error).__name__}")
            continue
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
    for item in unreadable:
        print(f"跳过（未跟踪且读取失败）: {item}")
    suffix = f"，跳过第三方镜像 {skipped} 个" if skipped else ""
    if unreadable:
        suffix += f"，跳过未跟踪且读取失败 {len(unreadable)} 个"
    print(f"检查 {checked} 个文本文件，问题 {len(problems)} 处{suffix}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
