"""执行驱动：真正去改变文件系统或启动进程的那一层。

驱动只做一件事：执行一个已经通过 pre-check 的 Action Request，并如实报告结果。
它不做策略判断、不读规则、不写审计。任何能力缺失（没有对应驱动、平台跑不了这个工具）
都必须抛 DriverError —— "假装执行过"是本阶段最不能出现的失败模式。

三种驱动：

- FileDriver：在受控工作区内做字面量替换（edit）或整文件写入（create/write），
  执行前保存快照，供事后验证失败时回滚；
- ProcessDriver：argv 列表直接执行（shell=False），超时即杀掉并如实标记；
- ShellCommandDriver：把命令文本交给声明的 shell 前缀执行，命令必须先通过注册表里的
  allowed_commands 完整匹配（pre-check 已经查过一遍，这里是第二道）；
- DelegatingDriver：平台不执行，交由 Agent 运行时执行（pre-execute Hook 的语义）。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Protocol, Sequence

from .models import (
    FORBIDDEN_COMMAND_FRAGMENTS,
    ActionRequest,
    DriverError,
    DriverKind,
    ExecutionStatus,
    ToolSpec,
)

__all__ = [
    "DelegatingDriver",
    "DriverResult",
    "FileDriver",
    "FileSnapshot",
    "ProcessDriver",
    "ShellCommandDriver",
    "default_drivers",
    "drivers_for",
    "snapshot_of",
]

_MAX_OUTPUT_CHARS = 8000
_SAFE_TEXT_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class FileSnapshot:
    """执行前的文件快照（回滚的唯一依据）。"""

    path: str
    existed: bool
    content: bytes = b""
    mode: Optional[int] = None

    @property
    def size(self) -> int:
        return len(self.content)


@dataclass
class DriverResult:
    """驱动的一次执行结果。status 只有 executed / delegated / failed 三种。"""

    status: ExecutionStatus
    detail: str = ""
    exit_code: Optional[int] = None
    timed_out: bool = False
    stdout: str = ""
    stderr: str = ""
    structured: Optional[Mapping[str, object]] = None
    snapshot: Optional[FileSnapshot] = None
    duration_ms: int = 0
    fields: dict[str, object] = field(default_factory=dict)


class ToolDriver(Protocol):
    """执行驱动端口。"""

    kind: DriverKind

    def execute(
        self, request: ActionRequest, spec: ToolSpec, *, workspace: Optional[Path] = None
    ) -> DriverResult:
        ...


def _clean(text: str, limit: int = _MAX_OUTPUT_CHARS) -> str:
    """输出里可能带控制字符与超长内容：落盘前统一中和并截断。"""

    if not isinstance(text, str):
        text = str(text)
    text = _SAFE_TEXT_RE.sub(lambda match: "\\x%02x" % ord(match.group(0)), text)
    if len(text) > limit:
        text = text[: limit - 14] + "...[truncated]"
    return text


def _resolve(workspace: Optional[Path], relative: str) -> Path:
    if workspace is None:
        raise DriverError("执行文件类动作必须声明受控工作区（workspace）")
    root = Path(workspace).resolve()
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise DriverError(f"目标路径 {relative!r} 逃出工作区，拒绝执行")
    return target


def snapshot_of(path: Path, *, relative: str) -> FileSnapshot:
    if not path.exists():
        return FileSnapshot(path=relative, existed=False)
    if path.is_dir():
        raise DriverError(f"{relative!r} 是目录：文件类驱动只处理文件")
    return FileSnapshot(
        path=relative,
        existed=True,
        content=path.read_bytes(),
        mode=path.stat().st_mode,
    )


class FileDriver:
    """文件类驱动：edit（字面量替换）与 write（整文件写入）。"""

    def __init__(self, kind: DriverKind) -> None:
        if kind not in (DriverKind.FILE_EDIT, DriverKind.FILE_WRITE):
            raise DriverError(f"FileDriver 不支持驱动类型 {kind!r}")
        self.kind = kind

    def execute(
        self, request: ActionRequest, spec: ToolSpec, *, workspace: Optional[Path] = None
    ) -> DriverResult:
        started = time.monotonic()
        relative = str(request.value_of("file_path") or request.value_of("path") or "")
        if not relative:
            raise DriverError("文件类动作缺少 file_path 参数")
        target = _resolve(workspace, relative)
        snapshot = snapshot_of(target, relative=relative)

        if self.kind is DriverKind.FILE_EDIT:
            old = str(request.value_of("old_string", ""))
            new = str(request.value_of("new_string", ""))
            replace_all = bool(request.value_of("replace_all", False))
            if not snapshot.existed:
                raise DriverError(f"{relative} 不存在：edit 只能在已存在的文件上做替换")
            try:
                text = snapshot.content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise DriverError(f"{relative} 不是 UTF-8 文本，拒绝替换（{error}）") from error
            occurrences = text.count(old) if old else 0
            if occurrences == 0:
                raise DriverError(f"{relative} 里没有找到要替换的原文：工具没有产生任何效果")
            if occurrences > 1 and not replace_all:
                raise DriverError(
                    f"{relative} 里匹配到 {occurrences} 处原文，replace_all=false 时替换有歧义"
                )
            updated = text.replace(old, new) if replace_all else text.replace(old, new, 1)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(updated, encoding="utf-8", newline="")
            structured = {
                "path": relative,
                "occurrences": occurrences,
                "bytes_before": snapshot.size,
                "bytes_after": len(updated.encode("utf-8")),
            }
        else:
            content = str(request.value_of("content", ""))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="")
            structured = {
                "path": relative,
                "bytes_before": snapshot.size,
                "bytes_after": len(content.encode("utf-8")),
            }

        return DriverResult(
            status=ExecutionStatus.EXECUTED,
            detail=f"{self.kind.value} {relative}",
            structured=structured,
            snapshot=snapshot,
            duration_ms=int((time.monotonic() - started) * 1000),
        )


class ProcessDriver:
    """argv 列表驱动：shell=False，超时即杀，输出只在内存里短暂存在。"""

    kind = DriverKind.PROCESS_ARGV

    def __init__(self, *, timeout_grace_ms: int = 250) -> None:
        self.timeout_grace_ms = timeout_grace_ms

    def execute(
        self, request: ActionRequest, spec: ToolSpec, *, workspace: Optional[Path] = None
    ) -> DriverResult:
        argv = request.value_of("argv")
        if argv is None:
            single = request.value_of("command")
            if isinstance(single, str) and single.strip():
                argv = [single]
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
            raise DriverError("process 驱动需要非空的 argv 字符串列表")
        return _run_process(
            [str(item) for item in argv],
            timeout_ms=spec.timeout_ms + self.timeout_grace_ms,
            workspace=workspace,
        )


class ShellCommandDriver:
    """命令文本驱动：先做白名单完整匹配，再交给声明的 shell 前缀执行。"""

    kind = DriverKind.SHELL_COMMAND

    def __init__(self, *, shell: Sequence[str]) -> None:
        if not shell:
            raise DriverError("ShellCommandDriver 必须声明 shell 前缀")
        self.shell = tuple(str(item) for item in shell)

    def execute(
        self, request: ActionRequest, spec: ToolSpec, *, workspace: Optional[Path] = None
    ) -> DriverResult:
        assert spec.command_param is not None
        command = request.value_of(spec.command_param)
        if not isinstance(command, str) or not command.strip():
            raise DriverError(f"缺少命令参数 {spec.command_param}")
        text = command.strip()
        if not any(re.fullmatch(pattern, text) is not None for pattern in spec.allowed_commands):
            raise DriverError(
                "命令不在白名单内（完整匹配）："
                f"{text[:200]!r}；允许的模式为 {list(spec.allowed_commands)}"
            )
        hits = sorted(
            {fragment for fragment in FORBIDDEN_COMMAND_FRAGMENTS if fragment in text}
        )
        if hits:
            raise DriverError(
                f"命令包含组合/替换/重定向片段 {hits}：只允许单条语句（驱动层的第二道防线）"
            )
        blocked = sorted(
            {fragment for fragment in spec.forbidden_command_fragments if fragment in text}
        )
        if blocked:
            raise DriverError(
                f"命令包含被禁片段 {blocked}（路径穿越 / 会写文件的选项 / 外部 diff）："
                "驱动层的第二道防线，拒绝执行"
            )
        return _run_process(
            [*self.shell, text],
            timeout_ms=spec.timeout_ms,
            workspace=workspace,
        )


def _run_process(
    argv: Sequence[str], *, timeout_ms: int, workspace: Optional[Path]
) -> DriverResult:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(argv),
            cwd=None if workspace is None else str(workspace),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_ms / 1000,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout if isinstance(error.stdout, str) else ""
        stderr = error.stderr if isinstance(error.stderr, str) else ""
        return DriverResult(
            status=ExecutionStatus.FAILED,
            detail=f"命令在 {timeout_ms}ms 内没有结束：已终止（部分输出不代表完整结果）",
            exit_code=None,
            timed_out=True,
            stdout=_clean(stdout),
            stderr=_clean(stderr),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except FileNotFoundError as error:
        raise DriverError(f"命令不可执行：{error}") from error

    status = (
        ExecutionStatus.EXECUTED
        if completed.returncode == 0
        else ExecutionStatus.FAILED
    )
    return DriverResult(
        status=status,
        detail=f"exit={completed.returncode}",
        exit_code=completed.returncode,
        stdout=_clean(completed.stdout or ""),
        stderr=_clean(completed.stderr or ""),
        structured={"exit_code": completed.returncode},
        duration_ms=int((time.monotonic() - started) * 1000),
    )


class DelegatingDriver:
    """平台不执行：pre-execute 放行后由 Agent 运行时执行，事后由 PostToolUse 补证据。"""

    kind = DriverKind.NONE

    def execute(
        self, request: ActionRequest, spec: ToolSpec, *, workspace: Optional[Path] = None
    ) -> DriverResult:
        return DriverResult(
            status=ExecutionStatus.DELEGATED,
            detail=f"交由 Agent 运行时执行 {spec.tool_name}（pre-execute 之后，post-check 由 PostToolUse 完成）",
            structured={"delegated": True},
        )


def drivers_for(specs: Sequence[ToolSpec]) -> dict[str, ToolDriver]:
    """按注册表的工具声明构建平台驱动表（键是工具 ID）。

    shell 前缀是每个工具自己的数据，因此同一个平台可以同时支持 pwsh 与 bash，
    而不需要在代码里判断"当前这台机器是什么系统"。
    """

    drivers: dict[str, ToolDriver] = {}
    for spec in specs:
        if spec.driver is DriverKind.FILE_EDIT:
            drivers[spec.id] = FileDriver(DriverKind.FILE_EDIT)
        elif spec.driver is DriverKind.FILE_WRITE:
            drivers[spec.id] = FileDriver(DriverKind.FILE_WRITE)
        elif spec.driver is DriverKind.PROCESS_ARGV:
            drivers[spec.id] = ProcessDriver()
        elif spec.driver is DriverKind.SHELL_COMMAND:
            drivers[spec.id] = ShellCommandDriver(shell=spec.shell)
        elif spec.driver is DriverKind.NONE:
            drivers[spec.id] = DelegatingDriver()
    return drivers


def default_drivers(*, shell: Sequence[str] | None = None) -> Mapping[DriverKind, ToolDriver]:
    """按驱动类型索引的兼容视图（测试与简单场景用）。"""

    drivers: dict[DriverKind, ToolDriver] = {
        DriverKind.FILE_EDIT: FileDriver(DriverKind.FILE_EDIT),
        DriverKind.FILE_WRITE: FileDriver(DriverKind.FILE_WRITE),
        DriverKind.PROCESS_ARGV: ProcessDriver(),
        DriverKind.NONE: DelegatingDriver(),
    }
    if shell:
        drivers[DriverKind.SHELL_COMMAND] = ShellCommandDriver(shell=shell)
    return drivers


def python_executable() -> str:
    """当前解释器路径：测试与示例用它构造确定性的 argv，而不是猜系统里有什么。"""

    return sys.executable or "python"


def environment_with(extra: Mapping[str, str]) -> dict[str, str]:
    env = dict(os.environ)
    env.update(extra)
    return env
