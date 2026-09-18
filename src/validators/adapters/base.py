"""外部工具适配器的公共机制：探针、版本、参数 allowlist、超时、输出上限与错误分类。

失败分类（每一种都对应一个显式的 ValidatorStatus，绝不混成"没有发现问题"）：

| 情况 | 状态 |
| --- | --- |
| 可执行文件找不到 | unavailable |
| 版本低于/高于声明区间，或版本读不出来 | version_mismatch |
| 超过超时（含子进程树被终止） | timeout |
| 被信号杀死 / 解释器内部错误 | crashed |
| 工具自己报配置错误、用法错误 | config_error |
| 退出码正常但输出为空、乱码、超长、JSON 非法 | output_invalid |

安全约定：

- 进程只接收白名单环境变量（不把宿主的 HOME / 凭据类变量交给被测项目）；
- 参数只能是声明模板加受校验的替换值（路径必须是工作区内的仓库相对路径，且不能以 "-" 开头）；
- 超时用进程组 / job object 终止整棵进程树，不留孤儿进程；
- 工具输出先脱敏（密钥、绝对路径、控制字符、换行）再进证据，且单条有长度上限。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

from policy.evidence import ToolInvocation, ValidationEvidence, ValidatorStatus
from validators.models import ToolSpec
from validators.registry import RegistryError, config_digest

__all__ = [
    "AdapterResult",
    "Probe",
    "ToolError",
    "ToolRun",
    "build_argv",
    "config_facts",
    "parse_json_output",
    "probe_tool",
    "resolve_executable",
    "run_tool",
    "sanitize_text",
    "tool_environment",
    "tool_label",
]

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_VERSION_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)")

# 允许传给子进程的环境变量：够工具跑起来，但不包含宿主的凭据与个人配置。
ENV_ALLOWLIST: Tuple[str, ...] = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
)


class ToolError(RegistryError):
    """外部工具调用层面的错误（配置、参数、环境）。"""


@dataclass(frozen=True)
class Probe:
    """一次工具探测的结果。"""

    status: ValidatorStatus
    executable: Optional[str] = None
    version: Optional[str] = None
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.status is ValidatorStatus.OK


@dataclass(frozen=True)
class ToolRun:
    """一次工具执行的结果（输出已脱敏、已限量）。"""

    status: ValidatorStatus
    exit_code: Optional[int]
    stdout: str
    stderr: str
    output_bytes: int
    truncated: bool
    duration_ms: int
    timed_out: bool = False
    reason: str = ""

    def payload(
        self,
        *,
        tool: str,
        version: Optional[str],
        config: Optional[str] = None,
        config_sha256: Optional[str] = None,
    ) -> ToolInvocation:
        return ToolInvocation(
            tool=tool,
            version=version,
            config=config,
            config_sha256=config_sha256,
            exit_code=self.exit_code,
            duration_ms=self.duration_ms,
            output_bytes=self.output_bytes,
            truncated=self.truncated,
            status=self.status,
        )


@dataclass(frozen=True)
class AdapterResult:
    """适配器的统一返回值：状态 + 证据 + 工具事实 + 未映射诊断数。"""

    status: ValidatorStatus
    evidence: Tuple[ValidationEvidence, ...] = ()
    tool: Optional[ToolInvocation] = None
    reason: Optional[str] = None
    unmapped: int = 0
    findings: int = 0
    payload: Mapping[str, Any] = field(default_factory=dict)


def sanitize_text(text: str, *, workspace: Optional[Path | str] = None, limit: int = 2000) -> str:
    """脱敏 + 中和：密钥、绝对路径、控制字符、ANSI 转义与换行都不进证据。"""

    if not isinstance(text, str):
        text = str(text)
    text = _ANSI_RE.sub("", text)
    # 换行/回车要转义：证据会被写进 JSONL 与日志，多行载荷会让"一条记录一行"失效。
    text = text.replace(chr(13) + chr(10), " ")
    text = text.replace(chr(10), chr(92) + "n").replace(chr(13), chr(92) + "r")
    try:
        from enforcement.audit import redact_text
    except ImportError:  # pragma: no cover - 同仓库内不应发生
        redact_text = None
    if redact_text is not None:
        text = redact_text(text, workspace=workspace, limit=limit)
    else:  # pragma: no cover
        text = _CONTROL_RE.sub(lambda match: "\\x%02x" % ord(match.group(0)), text)
        if len(text) > limit:
            text = text[: limit - 14] + "...[truncated]"
    return text


def tool_environment(*, tmp_dir: Path, python_paths: Sequence[Path] = ()) -> Mapping[str, str]:
    """构造子进程环境：只保留白名单变量，临时目录指向本次运行专属目录。

    PYTHONPATH 只包含项目档案声明的 python 根（src 布局下 src/ 就是导入根），
    这样测试与被测代码用的是项目自己的导入路径，而不是宿主环境的偶然结果。
    """

    env: dict[str, str] = {}
    for name in ENV_ALLOWLIST:
        value = os.environ.get(name)
        if value:
            env[name] = value
    env["TEMP"] = str(tmp_dir)
    env["TMP"] = str(tmp_dir)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONHASHSEED"] = "0"
    if python_paths:
        env["PYTHONPATH"] = os.pathsep.join(str(path) for path in python_paths)
    return env


def resolve_executable(name: str, *, python: str = sys.executable) -> Optional[str]:
    """解析可执行文件：PATH 到当前解释器同目录（venv 里装的工具就在这里）。"""

    if name == "{python}":
        return python
    found = shutil.which(name)
    if found:
        return found
    candidates = [Path(python).parent / name]
    if os.name == "nt":
        candidates.extend(
            Path(python).parent / (name + suffix) for suffix in (".exe", ".cmd", ".bat")
        )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _version_ok(version: str, requirement: str) -> bool:
    """按简单区间判断版本是否满足声明（>= / < / , 组合，与仓库一致性检查同口径）。"""

    requirement = requirement.strip()
    if not requirement:
        return True
    matched = _VERSION_RE.match(version)
    current = tuple(int(part) for part in matched.group(1).split(".")) if matched else ()
    if not current:
        return False
    for item in requirement.split(","):
        token = item.strip()
        if not token:
            continue
        match = re.match(r"^(>=|<=|==|!=|>|<)\s*(\d+(?:\.\d+)*)$", token)
        if match is None:
            raise ToolError("无法理解的版本区间片段: " + token)
        operator, bound_text = match.group(1), match.group(2)
        bound = tuple(int(part) for part in bound_text.split("."))
        width = max(len(current), len(bound))
        left = current + (0,) * (width - len(current))
        right = bound + (0,) * (width - len(bound))
        if operator == ">=" and not left >= right:
            return False
        if operator == "<=" and not left <= right:
            return False
        if operator == ">" and not left > right:
            return False
        if operator == "<" and not left < right:
            return False
        if operator == "==" and not left == right:
            return False
        if operator == "!=" and not left != right:
            return False
    return True


def probe_tool(
    spec: ToolSpec,
    *,
    python: str = sys.executable,
    timeout_ms: int,
    max_output_bytes: int,
    workspace: Path | str,
    tmp_dir: Path,
) -> Probe:
    """探测外部工具：能不能找到、版本是多少、是否落在声明区间内。"""

    executable = resolve_executable(spec.command[0], python=python)
    if executable is None:
        return Probe(
            status=ValidatorStatus.UNAVAILABLE,
            reason="找不到可执行文件 " + spec.command[0] + "（PATH 与解释器同目录都没有）",
        )
    argv = [executable, *spec.command[1:], *spec.version_args]
    completed = _run_process(
        argv,
        cwd=Path(workspace),
        env=tool_environment(tmp_dir=tmp_dir),
        timeout_ms=timeout_ms,
        max_output_bytes=max_output_bytes,
    )
    if completed.status is not ValidatorStatus.OK:
        return Probe(status=completed.status, executable=executable, reason=completed.reason)
    text = (completed.stdout + chr(10) + completed.stderr).strip()
    match = re.search(spec.version_pattern, text)
    if match is None:
        return Probe(
            status=ValidatorStatus.VERSION_MISMATCH,
            executable=executable,
            reason="无法从版本输出解析出版本：" + sanitize_text(text, limit=200),
        )
    version = match.group(1)
    try:
        ok = _version_ok(version, spec.version_requirement)
    except ToolError as error:
        return Probe(
            status=ValidatorStatus.CONFIG_ERROR, executable=executable, reason=str(error)
        )
    if not ok:
        return Probe(
            status=ValidatorStatus.VERSION_MISMATCH,
            executable=executable,
            version=version,
            reason="工具版本 " + version + " 不满足声明区间 " + spec.version_requirement,
        )
    return Probe(status=ValidatorStatus.OK, executable=executable, version=version)


def build_argv(
    spec: ToolSpec,
    probe: Probe,
    *,
    python: str,
    workspace: Path,
    config: Optional[Path],
    paths: Sequence[str] = (),
    nodeids: Sequence[str] = (),
    target: Optional[Path] = None,
    tmp_dir: Optional[Path] = None,
) -> Tuple[str, ...]:
    """按声明模板拼参数；替换值一律先校验，越界就抛 ToolError（失败关闭）。"""

    if probe.executable is None:
        raise ToolError("工具没有解析到可执行文件，不能构造参数")
    values: dict[str, Any] = {
        "{python}": python,
        "{workspace}": str(workspace),
        "{config}": str(config) if config is not None else "",
        "{tmp}": str(tmp_dir) if tmp_dir is not None else "",
        "{target}": str(target) if target is not None else "",
        "{paths}": tuple(_check_repo_relative(item) for item in paths),
        "{nodeids}": tuple(_check_nodeid(item) for item in nodeids),
    }
    if values["{config}"] == "" and any(item == "{config}" for item in spec.argv):
        raise ToolError("工具 argv 需要 {config}，但注册表没有声明 tool.config")

    argv: list[str] = [probe.executable, *spec.command[1:]]
    for item in spec.argv:
        if item in values:
            value = values[item]
            if isinstance(value, str):
                if value == "" and item != "{python}":
                    raise ToolError("占位符 " + item + " 没有取值，拒绝构造不完整的命令行")
                argv.append(value)
            else:
                argv.extend(value)
            continue
        argv.append(item)
    return tuple(argv)


def _check_repo_relative(value: str) -> str:
    """路径替换值必须是工作区内的相对路径（拒绝绝对路径、上跳、选项注入）。"""

    if not value or value.startswith("-"):
        raise ToolError("拒绝把可疑路径交给外部工具: " + repr(value))
    for token in ("\x00", chr(10), chr(13)):
        if token in value:
            raise ToolError("路径里出现不允许的字符")
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise ToolError("拒绝把绝对路径交给外部工具: " + value)
    if ".." in value.split("/"):
        raise ToolError("拒绝把上跳路径交给外部工具: " + value)
    return value


def _check_nodeid(value: str) -> str:
    """pytest node id 只允许路径形态加 ::用例名，且不能以 "-" 开头。"""

    if not value or value.startswith("-"):
        raise ToolError("拒绝把可疑 node id 交给 pytest: " + repr(value))
    if any(token in value for token in ("\x00", chr(10), chr(13), " ")):
        raise ToolError("node id 里出现空白或控制字符: " + repr(value))
    return value


def run_tool(
    spec: ToolSpec,
    probe: Probe,
    argv: Sequence[str],
    *,
    workspace: Path,
    tmp_dir: Path,
    timeout_ms: int,
    max_output_bytes: int,
    findings_exit_codes: Sequence[int] = (0,),
    config: Optional[Path] = None,
    python_paths: Sequence[Path] = (),
) -> ToolRun:
    """执行外部工具并把结果归一成 ToolRun。"""

    completed = _run_process(
        list(argv),
        cwd=workspace,
        env=tool_environment(tmp_dir=tmp_dir, python_paths=python_paths),
        timeout_ms=timeout_ms,
        max_output_bytes=max_output_bytes,
    )
    if completed.status is not ValidatorStatus.OK:
        return completed
    if completed.exit_code in tuple(findings_exit_codes) or completed.exit_code == 0:
        status = ValidatorStatus.OK
    else:
        status = _classify_failure(completed)
    reason = completed.reason
    if status is not ValidatorStatus.OK and not reason:
        # 失败分类必须能追溯到"工具自己说了什么"，否则证据只剩一个状态码
        excerpt = sanitize_text((completed.stderr or completed.stdout).strip(), limit=300)
        reason = "退出码 " + str(completed.exit_code) + ("：" + excerpt if excerpt else "")
    return ToolRun(
        status=status,
        exit_code=completed.exit_code,
        stdout=completed.stdout,
        stderr=completed.stderr,
        output_bytes=completed.output_bytes,
        truncated=completed.truncated,
        duration_ms=completed.duration_ms,
        timed_out=completed.timed_out,
        reason=reason,
    )


def tool_label(spec: ToolSpec, *, python: str = sys.executable) -> str:
    """证据里显示的工具名。

    注册表可以用 ["{python}", "-m", "pytest"] 声明工具，此时字面量 "{python}"
    不该直接进证据（读者会以为这工具叫这个名字）；用紧随其后的模块名兜底。
    """

    parts = list(spec.command)
    if parts and parts[0] == "{python}":
        module = next((item for item in parts[1:] if not item.startswith("-")), None)
        return module or Path(python).name
    return parts[0] if parts else "<tool>"


def _classify_failure(completed: ToolRun) -> ValidatorStatus:
    """非零退出码的分类：工具自己说用法/配置错了就是 config_error，其余按 crashed。"""

    text = (completed.stdout + " " + completed.stderr).lower()
    markers = (
        "usage:",
        "unrecognized arguments",
        "error: unrecognized",
        "config error",
        "invalid config",
        "no such option",
        "can't open file",
    )
    if any(marker in text for marker in markers):
        return ValidatorStatus.CONFIG_ERROR
    return ValidatorStatus.CRASHED


def _run_process(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_ms: int,
    max_output_bytes: int,
) -> ToolRun:
    """执行子进程：限时、限量、超时终止整棵进程树、输出必须是 UTF-8。"""

    if not cwd.is_dir():
        return ToolRun(
            status=ValidatorStatus.CONFIG_ERROR,
            exit_code=None,
            stdout="",
            stderr="",
            output_bytes=0,
            truncated=False,
            duration_ms=0,
            reason="工作目录不存在: " + str(cwd),
        )

    popen_kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "env": dict(env),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    started = time.monotonic()
    try:
        process = subprocess.Popen(list(argv), **popen_kwargs)
        _assign_windows_job(process)
    except FileNotFoundError as error:
        return ToolRun(
            status=ValidatorStatus.UNAVAILABLE,
            exit_code=None,
            stdout="",
            stderr="",
            output_bytes=0,
            truncated=False,
            duration_ms=0,
            reason="可执行文件不存在: " + str(error),
        )
    except OSError as error:
        return ToolRun(
            status=ValidatorStatus.CRASHED,
            exit_code=None,
            stdout="",
            stderr="",
            output_bytes=0,
            truncated=False,
            duration_ms=0,
            reason="无法启动进程: " + str(error),
        )

    timed_out = False
    out = b""
    err = b""
    try:
        out, err = process.communicate(timeout=max(0.001, timeout_ms / 1000.0))
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_tree(process)
        try:
            out, err = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - 已经 kill 过
            out, err = b"", b""
    finally:
        # 进程已结束（或已被终止）：关掉 job handle 顺手带走可能残留的后代进程。
        _close_windows_job(process)
    duration_ms = int((time.monotonic() - started) * 1000)

    raw = out + err
    output_bytes = len(raw)
    truncated = output_bytes > max_output_bytes
    if truncated:
        out = out[:max_output_bytes]
        err = err[:max_output_bytes]
    try:
        stdout = out.decode("utf-8")
        stderr = err.decode("utf-8")
    except UnicodeDecodeError as error:
        return ToolRun(
            status=ValidatorStatus.OUTPUT_INVALID,
            exit_code=process.returncode,
            stdout="",
            stderr="",
            output_bytes=output_bytes,
            truncated=truncated,
            duration_ms=duration_ms,
            reason="工具输出不是合法 UTF-8（" + str(error) + "）",
        )

    if timed_out:
        return ToolRun(
            status=ValidatorStatus.TIMEOUT,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            output_bytes=output_bytes,
            truncated=truncated,
            duration_ms=duration_ms,
            timed_out=True,
            reason="超过超时 " + str(timeout_ms) + "ms，已终止进程树",
        )
    if process.returncode is not None and process.returncode < 0:
        return ToolRun(
            status=ValidatorStatus.CRASHED,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            output_bytes=output_bytes,
            truncated=truncated,
            duration_ms=duration_ms,
            reason="进程被信号终止（returncode=" + str(process.returncode) + "）",
        )
    return ToolRun(
        status=ValidatorStatus.OK,
        exit_code=process.returncode,
        stdout=stdout,
        stderr=stderr,
        output_bytes=output_bytes,
        truncated=truncated,
        duration_ms=duration_ms,
    )


def _terminate_tree(process: subprocess.Popen) -> None:
    """终止子进程及其后代。

    - POSIX：进程组（start_new_session 加 killpg）；
    - Windows：优先 TerminateJobObject（见 _assign_windows_job），再退到 taskkill /T，
      最后 process.kill()。为什么不用 taskkill 当主路径：在受限环境（沙箱 / 受限令牌）里
      它可能直接 Access denied（本机实测如此），而 job object 仍然有效。
    """

    if process.poll() is not None:
        return
    try:
        job = getattr(process, "_validator_job_handle", None)
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


def _windows_api() -> Any:  # pragma: no cover - 平台分支
    if os.name != "nt":
        return None
    cached = getattr(_windows_api, "_cached", None)
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
    _windows_api._cached = bundle  # type: ignore[attr-defined]
    return bundle


def _assign_windows_job(process: subprocess.Popen) -> None:
    """把子进程绑进一个"关闭即杀"的 job object；失败就退回 taskkill 路径。"""

    api = _windows_api()
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
        process._validator_job_handle = job  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - 尽力而为
        return


def _terminate_windows_job(job: int) -> None:
    api = _windows_api()
    if api is None:  # pragma: no cover
        return
    kernel32, _ = api
    try:
        kernel32.TerminateJobObject(job, 1)
    except Exception:  # pragma: no cover
        pass


def _close_windows_job(process: subprocess.Popen) -> None:
    job = getattr(process, "_validator_job_handle", None)
    if not job:
        return
    api = _windows_api()
    if api is None:  # pragma: no cover
        return
    kernel32, _ = api
    try:
        kernel32.CloseHandle(job)
    except Exception:  # pragma: no cover
        pass
    process._validator_job_handle = None  # type: ignore[attr-defined]


def parse_json_output(text: str) -> Any:
    """解析工具的 JSON 输出；空输出或非法 JSON 抛 ToolError（上层记 output_invalid）。"""

    stripped = text.strip()
    if not stripped:
        raise ToolError("工具输出为空，无法按 JSON 解析")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as error:
        raise ToolError("工具输出不是合法 JSON: " + str(error)) from error


def config_facts(
    config: Optional[Path], *, root: Optional[Path | str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """配置文件的可追溯事实：(仓库相对路径, sha256)。

    只写仓库相对路径：证据会进日志与报告，绝对路径属于要脱敏的信息。
    """

    if config is None:
        return None, None
    display = config
    if root is not None:
        try:
            display = config.resolve().relative_to(Path(root).resolve())
        except ValueError:
            display = Path(config.name)
    return display.as_posix(), config_digest(config)
