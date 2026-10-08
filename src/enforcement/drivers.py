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
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, Sequence

from .action import blocked_path_prefix
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
#: 每条流**读进内存**的上限：先整份读进来再截断等于把命令的输出量变成进程的内存占用。
_MAX_OUTPUT_BYTES = 64 * 1024
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


def _read_bounded(stream: Any, limit: int = _MAX_OUTPUT_BYTES) -> bytes:
    """从管道读最多 limit 字节；超出部分照样读掉，只是不保留。

    **不能读到上限就不读了**：管道写满后子进程会阻塞在 write 上永远不退出，那会把一次
    "输出很多"变成一次假的"超时"。所以超限的部分继续读、直接丢掉——内存有界，语义不变。
    """

    kept = bytearray()
    while True:
        chunk = stream.read(8192)
        if not chunk:
            break
        if len(kept) < limit:
            kept.extend(chunk[: limit - len(kept)])
    return bytes(kept)


def _drain(stream: Any, sink: list[bytes]) -> None:  # pragma: no cover - 线程体
    try:
        sink.append(_read_bounded(stream))
    except Exception:  # noqa: BLE001 - 管道被强杀时的读取异常不影响判定
        sink.append(b"")


def _clean(text: str, limit: int = _MAX_OUTPUT_CHARS) -> str:
    """输出里可能带控制字符与超长内容：落盘前统一中和并截断。"""

    if not isinstance(text, str):
        text = str(text)
    text = _SAFE_TEXT_RE.sub(lambda match: "\\x%02x" % ord(match.group(0)), text)
    if len(text) > limit:
        text = text[: limit - 14] + "...[truncated]"
    return text


def _workspace_root(workspace: Optional[Path]) -> Path:
    if workspace is None:
        raise DriverError("执行文件类动作必须声明受控工作区（workspace）")
    return Path(workspace).resolve()


def _inside(root: Path, candidate: Path) -> bool:
    return root == candidate or root in candidate.parents


def _resolve(workspace: Optional[Path], relative: str) -> Path:
    root = _workspace_root(workspace)
    target = (root / relative).resolve()
    if not _inside(root, target):
        raise DriverError(f"目标路径 {relative!r} 逃出工作区，拒绝执行")
    return target


def _is_link_like(path: Path, info: os.stat_result) -> bool:
    """符号链接与目录联接（junction）都算"落点可被改写"。

    Windows 上 junction 不是 symlink（`os.path.islink` 为 False），但同样会把写入重定向到
    别处：3.12+ 用 `os.path.isjunction`，更早的版本看 `st_reparse_tag`。
    """

    if stat.S_ISLNK(info.st_mode):
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None:
        return bool(isjunction(path))
    return getattr(info, "st_reparse_tag", 0) == 0xA0000003  # IO_REPARSE_TAG_MOUNT_POINT


def _assert_no_link_components(root: Path, relative: str) -> None:
    """逐段 lstat：路径上任何**已存在**的组件是链接就拒绝。

    链接会让"resolved 之后在工作区内"这个结论在写到磁盘时失效——目标或它的父目录被换成
    指向工作区外的链接，mkdir/write_text 会照写（TOCTOU）。
    """

    current = root
    for part in Path(relative).parts:
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return
        except OSError as error:
            raise DriverError(
                f"无法确认目标 {relative!r} 的落点（{error}）：证明不了就不写"
            ) from error
        if _is_link_like(current, info):
            raise DriverError(
                f"目标 {relative!r} 的路径组件 {current.name!r} 是符号链接 / 目录联接："
                "链接会改写落点，证明不了写入还在工作区内，拒绝执行"
            )


def _write_confined(text: str, *, workspace: Optional[Path], relative: str) -> None:
    """写文件之前**再证明一次**落点，并用 O_NOFOLLOW 打开。

    `_resolve()` 与真正写盘之间隔着参数处理与内容计算，这期间并发方可以把目标或它的父目录
    换成链接，把写入重定向到工作区之外。所以这里：重新解析并复核范围 → 逐段拒绝链接组件 →
    用 `O_NOFOLLOW`（平台支持时）打开。证明不了就 DriverError，绝不写。
    """

    root = _workspace_root(workspace)
    fresh = (root / relative).resolve()
    if not _inside(root, fresh):
        raise DriverError(f"目标路径 {relative!r} 逃出工作区，拒绝执行")
    _assert_no_link_components(root, relative)
    try:
        fresh.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise DriverError(f"{relative} 的父目录创建失败：{error}") from error
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    handle: Optional[int] = None
    try:
        handle = os.open(str(fresh), flags, 0o644)
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            handle = None  # 交给 with 关
            stream.write(text)
    except OSError as error:
        raise DriverError(f"{relative} 写入失败：{error}") from error
    finally:
        if handle is not None:
            os.close(handle)


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
        # 驱动是副作用之前的最后一道闸：缺参数、参数类型不对一律拒绝，
        # 绝不把 None / 非字符串 str() 成 "" 或别的路径去执行。
        raw_path = request.value_of("file_path")
        if raw_path is None:
            raw_path = request.value_of("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise DriverError(
                "文件类动作缺少 file_path 参数（非空字符串）：目标证明不了就不执行"
            )
        relative = raw_path.strip()
        blocked_path = blocked_path_prefix(spec, request.params)
        if blocked_path is not None:
            parameter, path, prefix = blocked_path
            raise DriverError(
                f"参数 {parameter} 的路径 {path!r} 命中受保护前缀 {prefix!r}，拒绝执行"
            )
        target = _resolve(workspace, relative)
        snapshot = snapshot_of(target, relative=relative)

        if self.kind is DriverKind.FILE_EDIT:
            old_value = request.value_of("old_string")
            if not isinstance(old_value, str) or not old_value:
                raise DriverError(
                    "file_edit 动作缺少 old_string 参数（非空字符串）："
                    "缺省的空原文只会得到「没有找到要替换的原文」，"
                    "把「参数没传」说成「文件里没有」"
                )
            new_value = request.value_of("new_string")
            if not isinstance(new_value, str):
                raise DriverError(
                    "file_edit 动作缺少 new_string 参数（字符串）："
                    "缺省会被当成空串，把一次替换静默变成一次删除"
                )
            old, new = old_value, new_value
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
            _write_confined(updated, workspace=workspace, relative=relative)
            structured = {
                "path": relative,
                "occurrences": occurrences,
                "bytes_before": snapshot.size,
                "bytes_after": len(updated.encode("utf-8")),
            }
        else:
            content_value = request.value_of("content")
            if not isinstance(content_value, str):
                raise DriverError(
                    "file_write 动作缺少 content 参数（字符串）："
                    "把缺省当空内容会把已存在的文件截成 0 字节，而且仍然报 executed"
                )
            content = content_value
            _write_confined(content, workspace=workspace, relative=relative)
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
        _refuse_background(request)
        return _run_process(
            [str(item) for item in argv],
            timeout_ms=_requested_timeout_ms(request, spec) + self.timeout_grace_ms,
            workspace=workspace,
            cwd=_requested_workdir(request, workspace=workspace),
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
        # 不用 assert：`python -O` 会把断言整条剥掉，之后 request.value_of(None) 只报
        # 「缺少命令参数 None」——把"注册表没声明 command_param"这个配置错误说成参数缺失，
        # 读的人会去查请求而不是查注册表。
        if spec.command_param is None:
            raise DriverError(
                "shell_command 驱动要求注册表声明 command_param（命令文本所在参数）："
                "证明不了哪个参数是命令就不执行"
            )
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
        _refuse_background(request)
        return _run_process(
            [*self.shell, text],
            timeout_ms=_requested_timeout_ms(request, spec),
            workspace=workspace,
            cwd=_requested_workdir(request, workspace=workspace),
        )




def _requested_workdir(request: ActionRequest, *, workspace: Optional[Path]) -> Optional[Path]:
    """注册表声明的 workdir 参数 → 受控工作区里的绝对目录；没声明就不改 cwd。

    "参数在数据里声明了、驱动却不看"等于静默忽略：命令会在工作区根跑，而调用方
    （模型 / 用户）以为自己指定了目录。归一化与范围校验在 action.normalize_params /
    pre-check 已经做过一遍，这里是驱动层的第二道：证明不了就拒绝，绝不回落到默认 cwd。
    """

    raw = request.value_of("workdir")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise DriverError("workdir 必须是非空字符串（受控工作区相对路径）")
    if workspace is None:
        raise DriverError("请求声明了 workdir，却没有受控工作区锚点：拒绝执行")
    root = Path(workspace).resolve()
    target = (root / raw.strip()).resolve()
    if root != target and root not in target.parents:
        raise DriverError(f"workdir {raw!r} 不在受控工作区内：拒绝在证明不了的位置执行")
    if not target.is_dir():
        raise DriverError(f"workdir {raw!r} 不是已存在的目录：拒绝执行")
    return target


def _requested_timeout_ms(request: ActionRequest, spec: ToolSpec) -> int:
    """注册表声明的 timeoutMs 参数 → 本次调用的超时预算；缺省用注册表的 timeout_ms。

    预算是授权面的一部分：请求**超过**注册表声明的上限时拒绝，而不是悄悄按上限跑——
    "悄悄改小"与"悄悄改大"都是在执行一个和批准内容不同的动作。
    """

    raw = request.value_of("timeoutMs")
    if raw is None:
        return spec.timeout_ms
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise DriverError("timeoutMs 必须是正整数毫秒")
    if raw > spec.timeout_ms:
        raise DriverError(
            f"请求的超时 {raw}ms 超过注册表声明的 {spec.timeout_ms}ms："
            "要更长预算请改注册表并重新审核，驱动层不放宽"
        )
    return raw


def _refuse_background(request: ActionRequest) -> None:
    """run_in_background=true 显式拒绝（不是静默忽略）。

    平台拿不到后台进程的退出码：post_checks 里的 exit_code_zero 会必然退化成
    repair_required（§5.35），平台也没有进程树回收与回滚语义——声明不了就不假装支持。
    """

    value = request.value_of("run_in_background")
    if value not in (None, False):
        raise DriverError(
            "run_in_background=true 本平台显式拒绝：后台进程没有退出码，"
            "exit_code_zero 事后核对必然退化成 repair_required，也没有进程树回收与回滚语义。"
            "需要后台执行请另立工具，并在注册表里写清事后核对与回滚方式"
        )

def _run_process(
    argv: Sequence[str], *, timeout_ms: int, workspace: Optional[Path],
    cwd: Optional[Path] = None,
) -> DriverResult:
    started = time.monotonic()
    working_directory = cwd if cwd is not None else workspace
    popen_kwargs: dict[str, Any] = {
        "cwd": None if working_directory is None else str(working_directory),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "shell": False,
    }
    if os.name == "nt":
        # Windows：新进程组 + job object（见 _assign_windows_job）。TerminateJobObject
        # 带走整棵进程树——只 kill 直接子进程会留下它启动的命令继续跑。
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        # POSIX：独立会话 = 独立进程组，超时时 killpg(-pid) 一次带走整组。
        popen_kwargs["start_new_session"] = True
    if working_directory is not None and not Path(working_directory).is_dir():
        # 工作目录不存在时 Popen 在子进程里 chdir 失败、回报 ENOENT，旧实现把它说成
        # "命令不可执行"——归因错了地方（要启动什么与在哪个目录启动必须分开写）。
        # 自己先证明目录存在，其它启动失败（EACCES / NotADirectoryError …）也一律
        # 翻成 DriverError，不让裸 OSError 破坏本模块的错误契约。
        raise DriverError(
            f"工作目录不存在或不是目录：{working_directory}（拒绝在证明不了的位置执行）"
        )
    try:
        process = subprocess.Popen(list(argv), **popen_kwargs)
        _assign_windows_job(process)
    except FileNotFoundError as error:
        raise DriverError(f"命令不可执行：{error}") from error
    except OSError as error:
        raise DriverError(f"无法启动进程（{type(error).__name__}）：{error}") from error

    # 边跑边读、读到上限就只丢不存：communicate() 会先把整份输出缓冲进内存，
    # 一条 verbose（但仍在白名单里）的命令就能把执行进程的内存吃光——超时只限时间、不限产量。
    out_box: list[bytes] = []
    err_box: list[bytes] = []
    readers = [
        threading.Thread(target=_drain, args=(process.stdout, out_box), daemon=True),
        threading.Thread(target=_drain, args=(process.stderr, err_box), daemon=True),
    ]
    for reader in readers:
        reader.start()

    timed_out = False
    try:
        try:
            process.wait(timeout=timeout_ms / 1000)
        except subprocess.TimeoutExpired:
            timed_out = True
            # 终止**整棵进程树**：ShellCommandDriver 的直接子进程是声明的 shell，
            # 真正干活的往往是它再启动的命令（孙子进程）；旧实现用 subprocess.run，
            # 它只 kill 直接子进程，孙子进程会继续运行并继续写文件。
            _terminate_tree(process)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover - 已经终止过
                pass
    finally:
        _close_windows_job(process)
        for reader in readers:
            reader.join(5)

    stdout = _clean((out_box[0] if out_box else b"").decode("utf-8", errors="replace"))
    stderr = _clean((err_box[0] if err_box else b"").decode("utf-8", errors="replace"))
    if timed_out:
        return DriverResult(
            status=ExecutionStatus.FAILED,
            detail=(
                f"命令在 {timeout_ms}ms 内没有结束：已终止整棵进程树"
                "（部分输出不代表完整结果）"
            ),
            exit_code=None,
            timed_out=True,
            stdout=stdout,
            stderr=stderr,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    returncode = process.returncode
    status = ExecutionStatus.EXECUTED if returncode == 0 else ExecutionStatus.FAILED
    return DriverResult(
        status=status,
        detail=f"exit={returncode}",
        exit_code=returncode,
        stdout=stdout,
        stderr=stderr,
        structured={"exit_code": returncode},
        duration_ms=int((time.monotonic() - started) * 1000),
    )


def _terminate_tree(process: subprocess.Popen) -> None:
    """终止子进程及其后代。

    - POSIX：进程组（start_new_session 已把子进程放进自己的组，killpg 带走全组）；
    - Windows：优先 TerminateJobObject（见 _assign_windows_job），再退到 taskkill /T，
      最后 process.kill()。为什么不用 taskkill 当主路径：在受限环境（沙箱 / 受限令牌）里
      它可能直接 Access denied，而 job object 仍然有效。

    实现与 `validators.adapters.base._terminate_tree` 同型：那一份属于 Phase 5 的验证器层，
    enforcement 不反向导入它（分层方向相反），所以这里保留一份最小实现。
    """

    if process.poll() is not None:
        return
    try:
        job = getattr(process, "_enforcement_job_handle", None)
        if job:
            _terminate_windows_job(job)
        elif os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(os.getpgid(process.pid), 9)
    except Exception:  # pragma: no cover - 尽力而为，随后再 kill 一次
        pass
    finally:
        try:
            process.kill()
        except Exception:  # pragma: no cover
            pass


# Windows 的 job object：把子进程绑进一个 job，TerminateJobObject 会带走它的整棵进程树。
# 只用标准库 ctypes（不引入 pywin32），非 Windows 上是空操作。
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def _windows_job_api() -> Any:  # pragma: no cover - 平台分支
    if os.name != "nt":
        return None
    cached = getattr(_windows_job_api, "_cached", None)
    if cached is not None:
        return cached
    import ctypes
    from ctypes import wintypes

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_void_p),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimit),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    bundle = (kernel32, _ExtendedLimit)
    _windows_job_api._cached = bundle  # type: ignore[attr-defined]
    return bundle


def _assign_windows_job(process: subprocess.Popen) -> None:
    """把子进程绑进一个"关闭即杀"的 job object；失败就退回 taskkill 路径。"""

    api = _windows_job_api()
    if api is None:  # pragma: no cover - POSIX
        return
    kernel32, extended_limit = api
    try:
        import ctypes

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return
        info = extended_limit()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        kernel32.SetInformationJobObject(
            job,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not kernel32.AssignProcessToJobObject(job, ctypes.c_void_p(int(process._handle))):
            kernel32.CloseHandle(job)
            return
        process._enforcement_job_handle = job  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - 尽力而为
        return


def _terminate_windows_job(job: int) -> None:
    api = _windows_job_api()
    if api is None:  # pragma: no cover
        return
    kernel32, _ = api
    try:
        kernel32.TerminateJobObject(job, 1)
    except Exception:  # pragma: no cover
        pass


def _close_windows_job(process: subprocess.Popen) -> None:
    job = getattr(process, "_enforcement_job_handle", None)
    if not job:
        return
    api = _windows_job_api()
    if api is None:  # pragma: no cover
        return
    kernel32, _ = api
    try:
        kernel32.CloseHandle(job)
    except Exception:  # pragma: no cover
        pass
    process._enforcement_job_handle = None  # type: ignore[attr-defined]


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



