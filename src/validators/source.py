"""目标文件的读取与身份计算（验证流水线的第一道门）。

约定：

- 目标路径必须是工作区内的仓库相对路径；绝对路径会被归一化，逃出工作区一律拒绝；
- 符号链接要按真实路径判定，指向工作区外的链接等同越界（不是"读一下看看"）；
- 读不到、超大、非 UTF-8、含 NUL 全部是失败关闭，而不是"跳过这个文件"。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from policy.evidence import SourceDigest
from policy.models import PolicyContextError, normalize_repo_path

from .registry import RegistryError

__all__ = ["SourceError", "SourceFile", "read_source", "resolve_target"]

_BAD_PATH_TOKENS = ("\x00", "\n", "\r")


class SourceError(RegistryError):
    """目标文件不可用（失败策略：失败关闭，不能当作"没有发现问题"）。"""


@dataclass(frozen=True)
class SourceFile:
    """一份被验证的源码：仓库相对路径 + 绝对路径 + 语言 + 文本 + 内容身份。"""

    path: str
    absolute: Path
    language: str
    text: str
    digest: SourceDigest


def resolve_target(path: str, *, workspace: Path | str) -> tuple[str, Path]:
    """把目标路径规范化成 (仓库相对路径, 绝对路径)，并保证它落在工作区之内。"""

    if not isinstance(path, str) or not path.strip():
        raise SourceError("目标路径不能为空")
    for token in _BAD_PATH_TOKENS:
        if token in path:
            raise SourceError(f"目标路径里出现不允许的字符 {token!r}")

    anchor = Path(workspace).resolve()
    raw = Path(path.strip())
    candidate = raw if raw.is_absolute() else anchor / raw
    try:
        resolved = candidate.resolve()
    except OSError as error:
        raise SourceError(f"目标路径无法解析：{path!r}（{error}）") from error

    if not resolved.is_relative_to(anchor):
        raise SourceError(f"目标路径逃出工作区 {anchor}，拒绝处理：{path!r}")
    if not resolved.exists():
        raise SourceError(f"目标文件不存在：{path!r}")
    if not resolved.is_file():
        raise SourceError(f"目标路径不是文件：{path!r}")

    relative = resolved.relative_to(anchor).as_posix()
    try:
        normalized = normalize_repo_path(relative)
    except PolicyContextError as error:
        raise SourceError(f"目标路径不合法：{error}") from error
    return normalized, resolved


def read_source(
    path: str,
    *,
    workspace: Path | str,
    language: str,
    max_bytes: int,
) -> SourceFile:
    """读取目标并计算内容哈希；任何读取问题都抛 SourceError。"""

    normalized, absolute = resolve_target(path, workspace=workspace)
    try:
        size = absolute.stat().st_size
    except OSError as error:
        raise SourceError(f"{normalized}: 无法读取文件属性（{error}）") from error
    if size > max_bytes:
        raise SourceError(
            f"{normalized}: 文件 {size} 字节超过上限 {max_bytes} 字节；"
            "超限属于失败关闭，不按空文件处理"
        )
    try:
        data = absolute.read_bytes()
    except OSError as error:
        raise SourceError(f"{normalized}: 无法读取文件（{error}）") from error
    if b"\x00" in data:
        raise SourceError(f"{normalized}: 含 NUL 字节，不是可分析的文本源码")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceError(f"{normalized}: 不是合法 UTF-8（{error}）") from error

    digest = SourceDigest(
        file=normalized,
        language=language,
        sha256="sha256:" + hashlib.sha256(data).hexdigest(),
        bytes=len(data),
        lines=text.count(chr(10)) + (0 if text.endswith(chr(10)) or not text else 1),
    )
    return SourceFile(
        path=normalized, absolute=absolute, language=language, text=text, digest=digest
    )
