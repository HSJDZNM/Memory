"""扫描仓库自有文本文件里的真实凭据（阶段验收矩阵里的发布级门禁之一）。

与 enforcement/audit.py 的分工：那边的脱敏是运行期兜底，这里是提交前的门禁。两者的关系是
**超集**——本门禁用的是那份运行期定义（`SECRET_VALUE_PATTERNS`）**加上**本文件自己的
`EXTRA_PATTERNS`（AWS 的 AKIA/ASIA、JWT）。所以"门禁拦下的东西"不保证运行期脱敏也认得：
一个 `AKIA…` 或 JWT 会在这里被挡住，而 audit 那边的脱敏不认它。
要让两边完全一致，得把 `EXTRA_PATTERNS` 挪进 `enforcement.audit`（那是运行期改动，不在这里顺手做）；
在那之前，"门禁 ⊇ 运行期"这条关系由 tests/unit/test_secret_scan.py 的用例钉着。

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
    "docs/mirrors/dora-capabilities/",
    "docs/mirrors/dotnet-design-guidelines/",
    "docs/mirrors/gitlab-code-review/",
    "docs/mirrors/google-eng-practices/",
    "docs/mirrors/owasp-cheatsheets/",
    "docs/mirrors/python-pep-code-style/",
    "tools/owasp_cheatsheets/",
)

# 本文件自己写着模式定义，跳过以免自我命中。
SELF = "tools/secret_scan.py"

ALLOW_MARKER = "secret-scan: allow"


class ScanEnvironmentError(RuntimeError):
    """扫描环境错误：有文件读不出来 ⇒ 这次门禁证明不了任何事（退出码 2）。

    不能当作"干净"：`git ls-files` 保证路径存在，所以 OSError 通常意味着扫描器真的没能检查它，
    而 UnicodeDecodeError 意味着一个后缀不在 BINARY_SUFFIXES 里的非 UTF-8 / 二进制文件从未被扫过。
    两种情况都可能把凭据放行出发布门禁。
    """

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
    """扫一个文件。

    读不出来就抛 ScanEnvironmentError（不当作干净）：静默 return [] 会让一个从未被检查过的
    文件以"没有发现疑似凭据"收场，而那正是发布门禁最不能接受的一种通过。
    """

    target = ROOT / path
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ScanEnvironmentError(
            "%s 读不出来（%s: %s）：它没有被检查过，不能当作干净"
            % (path, type(error).__name__, error)
        ) from error
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
    unreadable: list[str] = []
    try:
        files = tracked_files(include_mirrors=include_mirrors)
    except (OSError, subprocess.SubprocessError, ImportError) as error:
        # git 缺失 / 不在仓库里 / enforcement.audit 导不进来：都是**环境错误**（退出码 2）。
        # 让解释器用退出码 1 收场就与"发现凭据"同码，CI 分不清两者。
        print("secret scan: 扫描环境不可用（%s: %s）" % (type(error).__name__, error), file=sys.stderr)
        return 2
    for name in files:
        try:
            findings.extend(scan(name, patterns))
        except ScanEnvironmentError as error:
            unreadable.append(str(error))

    print("secret scan: 已扫描 %d 个文件（镜像 %s）"
          % (len(files), "包含" if include_mirrors else "跳过"))
    if unreadable:
        for item in unreadable:
            print("  ! " + item, file=sys.stderr)
        print(
            "有 %d 个文件读不出来：这次扫描不完整，按环境错误退出（2）——"
            "它们没有被检查过，不等于干净" % len(unreadable),
            file=sys.stderr,
        )
        return 2
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
