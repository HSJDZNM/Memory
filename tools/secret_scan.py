"""扫描仓库自有文本文件里的真实凭据（阶段验收矩阵里的发布级门禁之一）。

与 enforcement/audit.py 的分工：那边的脱敏是运行期兜底，这里是提交前的门禁；两者共用
同一份"凭据长什么样"的定义（SECRET_VALUE_PATTERNS），避免口径漂移。

范围：会被提交的文本文件（git ls-files --cached --others --exclude-standard）。
第三方离线镜像逐字复制上游原文（通常自带示例密钥），默认跳过，--all 才一起扫。

误报处理：在命中行加注释标记 secret-scan: allow 即可显式豁免（必须写明理由），
不要靠改模式来放行。

用法：
    python tools/secret_scan.py          # 扫描仓库自有文件
    python tools/secret_scan.py --all    # 连离线镜像一起扫

退出码：0 干净；1 发现疑似凭据；2 用法或环境错误。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
    ".7z", ".rar", ".exe", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf",
    ".otf", ".mp3", ".mp4", ".mov", ".wav", ".onnx", ".pt", ".safetensors", ".parquet",
    ".sqlite", ".sqlite3", ".db",
}

# 逐字复制上游原文的目录：镜像正文里的"示例密钥"不是本仓库的凭据。
MIRRORED_PREFIXES = (
    "docs/dora-capabilities/",
    "docs/dotnet-design-guidelines/",
    "docs/gitlab-code-review/",
    "docs/google-eng-practices/",
    "docs/owasp-cheatsheets/",
    "docs/python-pep-code-style/",
    "tools/owasp_cheatsheets/",
)

# 本文件自己写着模式定义，跳过以免自我命中。
SELF = "tools/secret_scan.py"

ALLOW_MARKER = "secret-scan: allow"

# 扫描专用补充：形态确定、误报率低。
EXTRA_PATTERNS = (
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),          # AWS access key id
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\."),  # JWT
)


def secret_patterns() -> tuple[re.Pattern[str], ...]:
    from enforcement.audit import SECRET_VALUE_PATTERNS

    return tuple(SECRET_VALUE_PATTERNS) + EXTRA_PATTERNS


def tracked_files(*, include_mirrors: bool) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=str(ROOT), capture_output=True, check=True,
    )
    names = [item for item in out.stdout.decode("utf-8", "replace").split("\0") if item]
    result: list[str] = []
    for name in names:
        if name == SELF:
            continue
        if not include_mirrors and name.startswith(MIRRORED_PREFIXES):
            continue
        if Path(name).suffix.lower() in BINARY_SUFFIXES:
            continue
        result.append(name)
    return sorted(result)


def scan(path: str, patterns: tuple[re.Pattern[str], ...]) -> list[str]:
    target = ROOT / path
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    findings: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for pattern in patterns:
            match = pattern.search(line)
            if match is None:
                continue
            excerpt = match.group(0)
            if len(excerpt) > 12:
                excerpt = excerpt[:12] + "..."
            findings.append("%s:%d: %s（命中 %s）" % (path, number, excerpt, pattern.pattern[:40]))
            break
    return findings


def main(argv: list[str]) -> int:
    include_mirrors = "--all" in argv[1:]
    unknown = [item for item in argv[1:] if item != "--all"]
    if unknown:
        print(__doc__)
        return 2

    patterns = secret_patterns()
    findings: list[str] = []
    files = tracked_files(include_mirrors=include_mirrors)
    for name in files:
        findings.extend(scan(name, patterns))

    print("secret scan: 已扫描 %d 个文件（镜像 %s）"
          % (len(files), "包含" if include_mirrors else "跳过"))
    if not findings:
        print("没有发现疑似凭据")
        return 0
    for item in findings:
        print("  ! " + item, file=sys.stderr)
    print("发现 %d 处疑似凭据；确认是合成值请在行内加注释标记 %r 并写明理由" % (len(findings), ALLOW_MARKER),
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
