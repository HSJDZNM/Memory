"""bank/harness 三个脚本的公共基础（只用标准库）。

为什么单独一份：冻结清单、臂清单、run 载荷三条轴共用同一套「确定性排序 / 仓库相对路径 /
组合摘要 / 脱敏」口径。抄三遍就一定会漂，而载荷一旦漂了，逐字节相同的用例就守不住。

口径（与 dgate2 的 `run_manifest.py`、`a3-task-v3/reset-arm.py` 同一条）

- JSON 键排序、UTF-8、LF、单尾换行；同一输入两次渲染逐字节相同；
- 载荷里只有**仓库相对 POSIX 路径**，仓库外一律写 `<outside-workspace>`；
- 组合摘要 = `sha256("\n".join(lines) + "\n")`，其中 `lines` 是
  `"<sha256>  <仓库相对路径>"` 按**路径**升序排好的文本——这与
  `a3-task-v3/reset-arm.py` 的 `_manifest_sha256` 是同一个算法，两边的基线摘要因此可直接互比；
- 没有时戳、没有 run id、没有绝对路径。

退出码的划分（三个脚本一致，README 里也写一遍）

- `0` = 成立（写盘成功 / 校验通过 / 会话跑完且干净）；
- `1` = **事实不成立**：读不到、少文件、哈希漂移、载荷不合规、期望的状态没出现；
- `2` = **声明不成立**：参数组合错、清单里的字段/路径形状不合法、前置条件（凭据/dsh/沙箱）缺失。

这条划分不是美化：`1` 与 `2` 的区别是「世界跟清单说的不一样」与「你给的清单本身不对」，
处置方式不同（前者去查冻结件，后者去改调用）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2

#: 仓库外路径在载荷里的写法（与 dgate2 run_manifest.py 同一个 token）。
OUTSIDE_WORKSPACE = "<outside-workspace>"
#: 仓库根在人类可读消息里的写法（载荷不走这里，载荷用仓库相对路径）。
REPO_TOKEN = "<repo>"
#: 凭据值在日志里的写法（绝不落明文）。
REDACTED = "<redacted>"

HEX64 = re.compile(r"^[0-9a-f]{64}$")
WINDOWS_ABS = re.compile(r"^[A-Za-z]:[\\/]")
_ABS_IN_TEXT = re.compile(r"(?<![\w])[A-Za-z]:[\\/][^\s，；）】)\]]*")
_UNC_IN_TEXT = re.compile(r"(?<![\w])\\\\[^\s，；）】)\]]*")
_POSIX_IN_TEXT = re.compile(r"(?<![\w])/(?:[^\s，；）】)\]]+)")


class HarnessInputError(Exception):
    """读不到声明 / 用法错误：携带退出码（默认 2，事实类问题用 1）。"""

    def __init__(self, message: str, exit_code: int = EXIT_USAGE) -> None:
        super().__init__(message)
        self.exit_code = exit_code


# --------------------------------------------------------------------------- 路径


def find_repo_root(start: Path, explicit: Optional[Path] = None) -> Path:
    """仓库根：`--repo-root` > 从 `start` 向上找 `.git` > 从 cwd 向上找。

    找不到是用法错误，**不猜一个路径**：猜错会让载荷里的「仓库相对路径」全部错位，
    而错位的载荷仍然能通过自己的校验——那是最坏的一种绿。
    """

    if explicit is not None:
        resolved = explicit.resolve()
        if not (resolved / ".git").exists():
            raise HarnessInputError("--repo-root 下没有 .git：%s" % resolved)
        return resolved
    for candidate in [start.resolve(), *start.resolve().parents]:
        if (candidate / ".git").exists():
            return candidate
    for candidate in [Path.cwd().resolve(), *Path.cwd().resolve().parents]:
        if (candidate / ".git").exists():
            return candidate
    raise HarnessInputError("找不到仓库根（--repo-root / 脚本位置 / cwd 向上都没有 .git）")


def display_path(path: Path, repo_root: Path) -> str:
    """仓库内写仓库相对 POSIX 路径；仓库外写 `<outside-workspace>`。"""

    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except (ValueError, OSError):
        return OUTSIDE_WORKSPACE


def is_safe_relative(path: str) -> bool:
    """仓库相对 POSIX 路径的形状检查：不绝对、不带 `..`、不用反斜杠、没有空段。"""

    if not path or path.startswith(("/", "\\")) or WINDOWS_ABS.match(path):
        return False
    if "\\" in path:
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


def assert_relative(raw: Any, label: str) -> str:
    """把清单里的路径字段钉成仓库相对 POSIX 形状；绝对路径是声明错误（退出 2）。"""

    if not isinstance(raw, str) or not raw.strip():
        raise HarnessInputError("%s 必须是非空字符串路径" % label)
    value = raw.strip()
    if not is_safe_relative(value):
        raise HarnessInputError(
            "%s 必须是**仓库相对** POSIX 路径（不绝对 / 不带 .. / 不用反斜杠）：%r" % (label, value)
        )
    return value


def is_under(path: Path, root: Path) -> bool:
    """`path` 是否落在 `root` 之内（含相等）。两边先 resolve，避免 `..` 绕过。"""

    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


# --------------------------------------------------------------------------- 摘要与 JSON


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path, label: str) -> str:
    """文件字节 sha256；读不到就失败关闭（`label` 是仓库相对说明，不是绝对路径）。"""

    hasher = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
    except OSError as error:
        raise HarnessInputError(
            "%s 读不到（%s）" % (label, error.strerror or type(error).__name__),
            exit_code=EXIT_INVALID,
        ) from error
    return hasher.hexdigest()


def read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise HarnessInputError(
            "%s 读不到（%s）" % (label, error.strerror or type(error).__name__),
            exit_code=EXIT_INVALID,
        ) from error
    except UnicodeDecodeError as error:
        raise HarnessInputError(
            "%s 不是 UTF-8 文本（%s）" % (label, error), exit_code=EXIT_INVALID
        ) from error


def _reject_constant(value: str) -> Any:
    raise ValueError("非标准 JSON 常量 %s" % value)


def load_json(path: Path, label: str, exit_code: int = EXIT_INVALID) -> Any:
    """读 JSON；`NaN` / `Infinity` 这类非标准常量一律拒绝（它们会让摘要不稳定）。

    读不到、不是 UTF-8、不是合法 JSON **一律按 `exit_code` 退出**：调用方据此把
    「声明不成立」（2，例如 `--set`）与「事实不成立」（1，例如冻结记录本身）分开。
    """

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise HarnessInputError(
            "%s 读不到（%s）" % (label, error.strerror or type(error).__name__),
            exit_code=exit_code,
        ) from error
    except UnicodeDecodeError as error:
        raise HarnessInputError(
            "%s 不是 UTF-8 文本（%s）" % (label, error), exit_code=exit_code
        ) from error
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except ValueError as error:
        raise HarnessInputError(
            "%s 不是合法 JSON（%s）" % (label, error), exit_code=exit_code
        ) from error


def render_json(payload: Any) -> str:
    """确定性载荷：键排序 + 固定缩进 + 单尾换行（写盘用 UTF-8 字节，不受平台换行影响）。"""

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_text_lf(path: Path, text: str) -> None:
    """UTF-8 + LF + 单尾换行；目录不存在就建。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------- 清单文本与组合摘要


def manifest_lines(entries: Iterable[Tuple[str, str]]) -> List[str]:
    """`(路径, 摘要)` → 按**路径**升序的 `"<sha256>  <路径>"` 行。

    排序键必须是路径而不是整行：整行以摘要开头，按行排序就变成按哈希排序，
    两个内容相同、排序不同的清单会得到不同的组合摘要——那正好是「同输入不同结论」。
    """

    return ["%s  %s" % (digest, path) for path, digest in sorted(entries)]


def combined_digest(lines: Sequence[str]) -> str:
    """组合摘要：`sha256:` + sha256(`"\n".join(lines) + "\n"`)，与 reset-arm.py 同算法。"""

    text = "\n".join(lines) + "\n"
    return "sha256:" + sha256_bytes(text.encode("utf-8"))


def parse_manifest_lines(lines: Sequence[str]) -> Tuple[Dict[str, str], List[str]]:
    """解析 `"<sha256>  <路径>"` 行（容忍单个空格分隔）；返回（路径→摘要, 问题）。"""

    entries: Dict[str, str] = {}
    problems: List[str] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        digest, separator, path = line.partition("  ")
        if not separator:
            digest, separator, path = line.partition(" ")
        if not separator or not HEX64.match(digest) or not path.strip():
            problems.append("第 %d 行不是「<sha256>  <路径>」" % number)
            continue
        key = path.strip()
        if key in entries:
            problems.append("第 %d 行的路径重复：%s" % (number, key))
            continue
        entries[key] = digest
    return entries, problems


# --------------------------------------------------------------------------- 通配符


def _segments(value: str) -> List[str]:
    return [part for part in value.split("/") if part not in ("", ".")]


def glob_match(pattern: str, path: str) -> bool:
    """段级通配：`**` 匹配零个或多个段，其余段用 :func:`fnmatch.fnmatchcase`。

    :mod:`fnmatch` 与 :meth:`pathlib.PurePath.match` 都不把 `**` 当递归：前者把 `*`
    吃掉分隔符，后者在 3.13 之前对 `**` 同样按单段处理。忽略规则写错了是**静默**的
    （要么忽略太多，要么什么都没忽略），所以这里自己实现，并有专门用例钉住。
    """

    return _match_segments(_segments(pattern), 0, _segments(path), 0)


def _match_segments(pattern: List[str], i: int, parts: List[str], j: int) -> bool:
    if i == len(pattern):
        return j == len(parts)
    if pattern[i] == "**":
        if _match_segments(pattern, i + 1, parts, j):
            return True
        for k in range(j, len(parts)):
            if _match_segments(pattern, i + 1, parts, k + 1):
                return True
        return False
    if j == len(parts):
        return False
    if not fnmatchcase(parts[j], pattern[i]):
        return False
    return _match_segments(pattern, i + 1, parts, j + 1)


def matches_any(patterns: Sequence[str], path: str) -> bool:
    return any(glob_match(pattern, path) for pattern in patterns)


def prunas_dir(patterns: Sequence[str], relative_dir: str) -> bool:
    """目录能否整棵剪掉：只有以 `/**` 结尾的模式才能证明「里面的文件都会被忽略」。"""

    for pattern in patterns:
        if pattern.endswith("/**") and glob_match(pattern[:-3], relative_dir):
            return True
    return False


# --------------------------------------------------------------------------- 遍历


def walk_files(
    root: Path,
    ignore: Sequence[str],
    label: str,
) -> Tuple[List[str], List[str], List[str]]:
    """按 `root` 遍历文件；返回（根内相对路径, 不可枚举目录, 被忽略的路径）。

    - 路径一律是**相对 `root`** 的 POSIX 串（载荷再由调用方拼成仓库相对路径）；
    - 不可枚举的目录**如实记录**，不当作「没有文件」（AGENTS 第 53 条：宁可让读数保持红）；
    - 被忽略的路径单独返回，让调用方能把「忽略了多少」写进载荷——默认忽略与显式忽略要分得开。
    """

    if not root.is_dir():
        raise HarnessInputError("%s 不是目录：%s" % (label, root), exit_code=EXIT_INVALID)

    files: List[str] = []
    unreadable: List[str] = []
    ignored: List[str] = []

    def onerror(error: OSError) -> None:
        value = getattr(error, "filename", None)
        unreadable.append(str(value) if value else str(error))

    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror):
        here = Path(dirpath)
        relative_dir = "" if here == root else here.relative_to(root).as_posix()
        kept: List[str] = []
        for name in sorted(dirnames):
            child = "%s/%s" % (relative_dir, name) if relative_dir else name
            if prunas_dir(ignore, child):
                ignored.append(child + "/")
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            child = "%s/%s" % (relative_dir, name) if relative_dir else name
            if matches_any(ignore, child):
                ignored.append(child)
                continue
            files.append(child)
    return sorted(files), sorted(unreadable), sorted(ignored)


# --------------------------------------------------------------------------- 脱敏


def redact_secret(text: str, secret: Optional[str]) -> str:
    """把凭据值从文本里抹掉（值本身绝不写盘；这里只保证它不会**经由**日志落盘）。"""

    if not secret:
        return text
    return text.replace(secret, REDACTED)


def sanitize_text(text: str, repo_root: Optional[Path] = None) -> str:
    """人类可读输出 / 日志的脱敏：仓库根 → `<repo>`，绝对路径 → `<outside-workspace>`。"""

    cleaned = text
    if repo_root is not None:
        root = str(repo_root)
        for needle in {root, root.replace("\\", "/"), root.replace("/", "\\")}:
            if needle:
                cleaned = cleaned.replace(needle, REPO_TOKEN)
    cleaned = _ABS_IN_TEXT.sub(OUTSIDE_WORKSPACE, cleaned)
    cleaned = _UNC_IN_TEXT.sub(OUTSIDE_WORKSPACE, cleaned)
    cleaned = _POSIX_IN_TEXT.sub(OUTSIDE_WORKSPACE, cleaned)
    return cleaned


def first_line(text: str, limit: int = 160) -> str:
    """取首行并截断：宿主版本号这类自由文本只留一行，免得把整份 stdout 抄进载荷。"""

    for line in (text or "").splitlines():
        candidate = line.strip()
        if candidate:
            return candidate[:limit]
    return ""


def check_no_absolute_paths(value: Any, where: str = "payload") -> List[str]:
    """递归找载荷里的绝对路径（盘符 / UNC / 以斜杠开头），返回命中的位置。

    载荷里出现绝对路径 = 换一台机器就不可比 + 可能泄露用户名，所以写成可断言的自检，
    而不是「我们小心一点」。
    """

    hits: List[str] = []

    def visit(item: Any, trail: str) -> None:
        if isinstance(item, str):
            if item.startswith("/") or WINDOWS_ABS.match(item) or item[:2] == "\\\\":
                hits.append("%s:%s" % (where, trail))
            return
        if isinstance(item, dict):
            for key, child in item.items():
                if isinstance(key, str) and (
                    key.startswith("/") or WINDOWS_ABS.match(key) or key[:2] == "\\\\"
                ):
                    hits.append("%s:%s<key>" % (where, trail))
                visit(child, "%s.%s" % (trail, key))
            return
        if isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, "%s[%d]" % (trail, index))

    visit(value, "$")
    return hits


__all__ = [
    "EXIT_INVALID",
    "EXIT_OK",
    "EXIT_USAGE",
    "HEX64",
    "HarnessInputError",
    "OUTSIDE_WORKSPACE",
    "REDACTED",
    "REPO_TOKEN",
    "assert_relative",
    "check_no_absolute_paths",
    "combined_digest",
    "display_path",
    "find_repo_root",
    "first_line",
    "glob_match",
    "is_safe_relative",
    "is_under",
    "load_json",
    "manifest_lines",
    "matches_any",
    "parse_manifest_lines",
    "prunas_dir",
    "read_text",
    "redact_secret",
    "render_json",
    "sanitize_text",
    "sha256_bytes",
    "sha256_file",
    "walk_files",
    "write_text_lf",
]
