"""目标文件的读取与身份计算（验证流水线的第一道门）。

约定：

- 目标路径必须是工作区内的仓库相对路径；绝对路径会被归一化，逃出工作区一律拒绝；
- 符号链接要按真实路径判定，指向工作区外的链接等同越界（不是"读一下看看"）；
- 读不到、超大、非 UTF-8、含 NUL 全部是失败关闭，而不是"跳过这个文件"。
"""

from __future__ import annotations

import hashlib
import os
import stat
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


def _open_source(absolute: Path, *, normalized: str) -> int:
    """打开目标文件：POSIX 带 O_NOFOLLOW，其它平台用 getattr 兜底取 0。

    兜底是"这个平台没有该标志"，不是"跳过校验"：拿不到 O_NOFOLLOW 时由
    `_assert_descriptor_inside` 接过"仍在工作区内"这条不变量（见那里的说明）。
    """

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(absolute, flags)
    except OSError as error:
        raise SourceError(f"{normalized}: 无法读取文件（{error}）") from error


def _assert_descriptor_inside(fd: int, *, absolute: Path, anchor: Path, normalized: str) -> None:
    """复核"打开的这个对象仍在工作区内"。

    优先读**描述符自身**的真实路径（Linux 的 /proc/self/fd，读数不带竞态）；拿不到时
    退回 `realpath` 重新解析。`O_NOFOLLOW` 只覆盖最后一级组件，父目录被换成指向
    工作区外的链接要靠这一步。

    残余窗口如实写在这里：`realpath` 与 `open` 之间仍有理论上的竞态（Windows 没有
    O_NOFOLLOW，也没有 /proc 读数）。但内容始终来自同一个已打开的 fd——不存在
    "读到半个文件"或"读的过程中又被换掉"，被换链时读到的也只会是拒读。
    """

    try:
        descriptor = Path(os.readlink(f"/proc/self/fd/{fd}"))
    except OSError:
        try:
            descriptor = Path(os.path.realpath(absolute))
        except OSError as error:
            raise SourceError(f"{normalized}: 无法确认目标仍在工作区内（{error}）") from error
    if not descriptor.is_relative_to(anchor):
        raise SourceError(
            f"{normalized}: 打开后目标指向工作区外的 {descriptor}；拒绝读取（换链/竞态）"
        )


def _read_bounded(fd: int, *, max_bytes: int) -> bytes:
    """从描述符读，最多 max_bytes + 1 字节：多读的那一个字节就是"超限"的证据。"""

    buffer = bytearray()
    while len(buffer) <= max_bytes:
        chunk = os.read(fd, max_bytes + 1 - len(buffer))
        if not chunk:
            break
        buffer.extend(chunk)
    return bytes(buffer)


def read_source(
    path: str,
    *,
    workspace: Path | str,
    language: str,
    max_bytes: int,
) -> SourceFile:
    """读取目标并计算内容哈希；任何读取问题都抛 SourceError。

    **打开一次、只从描述符读**：`resolve_target` 证明的是"解析那一刻"的包含关系，
    之后再用路径重新 `stat` / `read_bytes` 就给了换链一个窗口——把目标（或它的父目录）
    换成指向工作区外的链接，读到的会是工作区外的内容，而摘要仍然把它绑在工作区内的
    相对路径上（证据被污染）。大小上限同理：`stat` 与 `read` 是两次独立的路径解析，
    "stat 说 16 字节、read 读回 16MB"可以同时成立，读取本身必须有界。
    """

    anchor = Path(workspace).resolve()
    normalized, absolute = resolve_target(path, workspace=workspace)
    fd = _open_source(absolute, normalized=normalized)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise SourceError(f"{normalized}: 目标不是普通文件，拒绝按源码读取")
        _assert_descriptor_inside(fd, absolute=absolute, anchor=anchor, normalized=normalized)
        if info.st_size > max_bytes:
            raise SourceError(
                f"{normalized}: 文件 {info.st_size} 字节超过上限 {max_bytes} 字节；"
                "超限属于失败关闭，不按空文件处理"
            )
        data = _read_bounded(fd, max_bytes=max_bytes)
    except OSError as error:
        raise SourceError(f"{normalized}: 无法读取文件（{error}）") from error
    finally:
        os.close(fd)
    if len(data) > max_bytes:
        raise SourceError(
            f"{normalized}: 文件在读取过程中增长到超过上限 {max_bytes} 字节；"
            "超限属于失败关闭，不按空文件处理"
        )
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
