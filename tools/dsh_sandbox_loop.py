"""重放 Phase 2 的真实 dsh 沙箱闭环。

它在一个受控临时项目里跑两遍真实 dsh（headless profile + 进程内策略 Hook 插件）：

    1) bad 编辑：controller 直接依赖 repository → 必须被 ARCH-001 阻断，文件哈希不变；
    2) good 编辑：新增一个方法 → 必须放行，且只发生一次预期变更。

断言失败即退出码 1；dsh 不可用、**Hook 进程根本起不来**（CI 的 ubuntu runner、
或沙箱禁止管道 stdio）、或 **dsh 自身被环境挡住**（$DSH_HOME 写不进去 / 系统 temp
不可写）时按**环境跳过**处理并退出码 0，因为这条闭环验证的是"本机真实 Agent Runtime
的行为"，不是可移植的单元测试。

但"跳过"必须**可判定**、不能被读成"已验证"，也不能把不同的失败原因糊成一个：**每条**
跳过路径都在产物里写 `environment_skipped: true`（正常路径写 `false`）与各自的 reason。
"dsh 自身起不来"按**被拒路径**分成 `profile_write_denied`（落在 $DSH_HOME 下）与
`other_path_denied`（落在 temp / spill 等 dsh 自己的启动临时区），两者都在
`dsh_startup_denied_kind` 与 `dsh_startup_denied_path` 里写明是哪条路径被拒；
归不了因的权限错误**不产生跳过**（宁可红着，也不把它洗成环境限制）。
`--require-dsh` 让**任何**环境跳过都失败，跳过也绝不写成 pass。

用法：

    python tools/dsh_sandbox_loop.py                 # 构建并跑完整闭环
    python tools/dsh_sandbox_loop.py --require-dsh   # 任何环境跳过都视为失败
    python tools/dsh_sandbox_loop.py --keep          # 保留上一轮的审计与采集，不重建项目

产物写在 .tmp/ 下（可随时删除并由本脚本重建）：

    .tmp/phase-2-sandbox/demo-shop/           受控项目（含 .policy/ 配置与审计）
    .tmp/phase-2-sandbox/logs/                dsh 的原始输出
    .tmp/artifacts/phase-2-sandbox-result.json 结构化结论（供阶段证据引用）
"""

from __future__ import annotations

import argparse
import datetime as clock
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SANDBOX = REPO_ROOT / ".tmp" / "phase-2-sandbox"
PROJECT = SANDBOX / "demo-shop"
LOGS = SANDBOX / "logs"
ARTIFACT = REPO_ROOT / ".tmp" / "artifacts" / "phase-2-sandbox-result.json"

AGENT_VERSION = "0.1.5-rc.1"
RULE_ID = "ARCH-001@1"

CONTROLLER_START = '''"""订单 HTTP 入口。"""

from service import OrderService


class OrderController:
    def __init__(self) -> None:
        self.service = OrderService()

    def create(self, payload: dict) -> dict:
        return self.service.create(payload)
'''

SERVICE = '''"""订单业务逻辑。"""

from repository import OrderRepository


class OrderService:
    def __init__(self) -> None:
        self.repository = OrderRepository()

    def create(self, payload: dict) -> dict:
        return self.repository.insert(payload)
'''

ADAPTER_CONFIG = '''# 受控沙箱项目的 dsh Adapter 配置（由 tools/dsh_sandbox_loop.py 生成）。
agent_version: "{agent_version}"
project: demo-shop
project_root: ..
rules:
  - {repo}/policies
rules_root: {repo}
timeout_ms: 5000
layers:
  - pattern: "**/*_controller.py"
    layer: controller
  - pattern: "**/*_service.py"
    layer: service
  - pattern: "**/*_repository.py"
    layer: repository
languages:
  - pattern: "**/*.py"
    language: python
default_language: text
audit_log: .policy/audit.jsonl
# Phase 4：受控执行需要的授权链路。缺少任何一项，受控工具都会被 Hook 阻断。
principal:
  subject: local-user
  roles:
    - developer
registry: {repo}/registry/tool-registry.yaml
registry_approved: {repo}/registry/tool-registry.approved.json
enforcement_ledger: .policy/enforcement-ledger.jsonl
'''

HOOK_COMMAND = (
    "python -m adapters.dsh.hooks --config .policy/dsh-adapter.yaml "
    "--hooks-config .policy/hooks.json --audit .policy/audit.jsonl "
    "--capture .policy/captures"
)

HOOKS_JSON = {
    "hooks": {
        "PreToolUse": [
            {
                "hooks": [
                    {"type": "command", "command": HOOK_COMMAND, "timeout": 30}
                ]
            }
        ]
    }
}

PATCH_TEMPLATE = """# 由 tools/dsh_sandbox_loop.py 生成：把进程内策略 Hook 插件挂到 profile 上。
- insert:
    - id: policy-hook
      name: '{repo}/src/adapters/dsh/policy-hook.plugin.mjs'
      config:
        command: '{command}'
        timeoutMs: 30000
        projectDir: '{project}'
"""

BLOCK_PROMPT = (
    "用 edit 工具在 src/shop/order_controller.py 的 import 区加一行 "
    "'from repository import OrderRepository'，然后一句话报告结果。"
)
ALLOW_PROMPT = (
    "用 edit 工具在 src/shop/order_controller.py 的 create 方法后面加一个方法 "
    "def ping(self) -> str: 内部返回 'pong'，然后一句话报告结果。"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def build_project(*, keep: bool) -> None:
    """重建受控项目；--keep 时只重置被治理的源文件，保留审计与采集。"""

    (PROJECT / "src" / "shop").mkdir(parents=True, exist_ok=True)
    (PROJECT / ".policy").mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

    write(PROJECT / "AGENTS.md", (
        "# demo-shop（受控沙箱）\n\n"
        "这是用于验证工程策略门禁的最小项目，不是真实业务代码。\n\n"
        "- 分层约定：controller → service → repository；\n"
        "- 规则库在别处，本目录只放沙箱代码。\n"
    ))
    write(PROJECT / "src" / "shop" / "order_controller.py", CONTROLLER_START)
    write(PROJECT / "src" / "shop" / "order_service.py", SERVICE)

    write(
        PROJECT / ".policy" / "dsh-adapter.yaml",
        ADAPTER_CONFIG.format(agent_version=AGENT_VERSION, repo=REPO_ROOT.as_posix()),
    )
    write(
        PROJECT / ".policy" / "hooks.json",
        json.dumps(HOOKS_JSON, ensure_ascii=False, indent=2) + "\n",
    )
    write(
        PROJECT / ".policy" / "patch.yml",
        PATCH_TEMPLATE.format(
            repo=REPO_ROOT.as_posix(),
            command=HOOK_COMMAND,
            project=PROJECT.as_posix(),
        ),
    )

    if not keep:
        for stale in (".policy/audit.jsonl", ".policy/captures"):
            target = PROJECT / stale
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists():
                target.unlink()


def dsh_argv() -> list[str] | None:
    """解析 dsh 可执行文件。

    Windows 上 npm 装出来的是 .CMD 垫片：shutil.which 能找到它，但 CreateProcess
    不接受裸名（不会自动补 PATHEXT），必须用解析后的绝对路径。
    """

    for name in ("dsh", "dsh.cmd", "dsh.exe", "dsh.bat"):
        found = shutil.which(name)
        if found:
            return [found]
    return None


# 进程内 Hook 插件在 spawn 被拒时的原文（见 src/adapters/dsh/policy-hook.plugin.mjs 的
# catch 分支）。它出现的唯一含义是"Hook 进程起不来"，与策略判定无关。
SPAWN_DENIED_MARKERS = ("spawn EPERM", "Hook 无法执行")

# 权限被拒的原文标记：出现在日志里只说明"某个路径被拒"，**不说明是哪一层失败**。
# 旧判据就是在这里走偏的：它把这类标记与"文本里出现 profiles/.dsh/cordis/dsh-home"一与，
# 而 dsh 的崩溃堆栈里天然带着 <dsh-home>/profiles/<name>/#spill-local 这些帧——
# 于是任何一种启动失败都被说成"写 $DSH_HOME 下的 profile 被拒"。
PERMISSION_DENIED_MARKERS = (
    "EPERM",
    "EACCES",
    "WinError 5",
    "Permission denied",
    "Access is denied",
)

# dsh 启动阶段崩溃的原文（"连插件树/配置都没装起来"）。**只有**它出现，
# 日志里的权限错误才可能与 dsh 启动有关；没有它一律按"与启动无关"处理：
# 宁可让真失败保持红，也不要把无关的 EPERM 洗成环境跳过。
DSH_BOOT_FAILURE_MARKERS = (
    "plugin tree failed to load",
    "failed to apply loader entry",
    "dsh-app-boot",
    "runProfile",
)

# dsh 自己的启动临时区：spill-local 插件在启动时 mkdtemp 的目录名前缀。
DSH_SCRATCH_PREFIX = "dsh-"
DEFAULT_DSH_HOME_DIRNAME = ".dsh"

# 两种"dsh 自身起不来"的**独立状态**，区别只在被拒路径落在哪里：
#   profile_write_denied —— 落在 $DSH_HOME（或其 profiles 子目录）下，沿用原状态与措辞；
#   other_path_denied    —— 落在 $DSH_HOME 之外的 dsh 启动临时区（系统 temp / dsh- scratch）。
PROFILE_WRITE_DENIED = "profile_write_denied"
OTHER_PATH_DENIED = "other_path_denied"

# 被拒路径的三种原文形态（都要求路径带引号，避免把 syscall/errno 当成路径）：
#   Node   EPERM: operation not permitted, mkdtemp 'C:\...\Temp\dsh-spill-XXXXXX'
#   Node   EACCES: permission denied, open '/home/x/.dsh/profiles/headless/cordis.yml'
#   Python PermissionError: [Errno 13] Permission denied: '<path>'
#   .NET   [WinError 5] Access is denied: '<path>'
_NODE_DENIAL = re.compile(
    r"(?:EPERM|EACCES)\s*:\s*[^'\n]*?,\s*(?P<syscall>[A-Za-z_][A-Za-z0-9_]*)\s+'(?P<path>[^'\n]+)'"
)
_STRUCTURED_DENIAL = re.compile(
    r"code:\s*'(?:EPERM|EACCES)'[\s\S]{0,240}?path:\s*'(?P<path>[^'\n]+)'"
)
_QUOTED_DENIAL = re.compile(
    r"(?:\[Errno\s+13\]\s*Permission denied|\[WinError\s+5\][^'\n]*?"
    r"|Permission denied|Access is denied)\s*:?\s*'(?P<path>[^'\n]+)'"
)
_QUOTED_TOKEN = re.compile(r"'([^'\n]+)'|\"([^\"\n]+)\"")
# 日志里出现的 <root>/profiles/<name>：说明 dsh 正在把 root 当 profile 根用。
_DSH_HOME_WINDOWS = re.compile(r"((?:[A-Za-z]:[\\/])[^\s'\"()]*?)[\\/]profiles[\\/]")
_DSH_HOME_POSIX = re.compile(r"(/[^\s'\"():]*?)[\\/]profiles[\\/]")


@dataclass(frozen=True)
class DeniedPath:
    """日志里一条"某个路径被环境拒绝"的原文记录（不预设它与 dsh 启动的关系）。"""

    path: str
    syscall: str | None = None
    evidence: str = ""


@dataclass(frozen=True)
class StartupDenial:
    """一次**可归因**的"dsh 自身起不来"：路径、系统调用与全部被拒路径都留证据。"""

    kind: str
    denial: DeniedPath
    paths: tuple[str, ...]
    home_roots: tuple[str, ...]

    @property
    def path(self) -> str:
        return self.denial.path

    @property
    def syscall(self) -> str | None:
        return self.denial.syscall


def _norm_path(value: str) -> str:
    """路径归一化：统一分隔符、折叠重复分隔符、Windows 上大小写不敏感。"""

    text = value.strip().strip("'\"").replace("\\", "/")
    text = re.sub(r"/{2,}", "/", text).rstrip("/")
    return (text or "/").lower() if os.name == "nt" else (text or "/")


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = _norm_path(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return tuple(result)


def _looks_like_path(value: str) -> bool:
    text = value.strip()
    if text.startswith(("/", "\\", "./", "../", ".\\", "..\\")):
        return True
    return len(text) >= 3 and text[1] == ":" and text[0].isalpha()



def denied_paths(text: str) -> tuple[DeniedPath, ...]:
    """按原文形态解析出日志里**每个**被拒路径；解析不出路径就返回空（不猜）。"""

    found: list[DeniedPath] = []
    seen: set[str] = set()

    def remember(path: str, syscall: str | None, evidence: str) -> None:
        key = _norm_path(path)
        if not key or key in seen:
            return
        seen.add(key)
        detail = evidence.strip()[:200]
        found.append(DeniedPath(path=path.strip(), syscall=syscall, evidence=detail))

    for match in _NODE_DENIAL.finditer(text):
        remember(match.group("path"), match.group("syscall"), match.group(0))
    for match in _STRUCTURED_DENIAL.finditer(text):
        remember(match.group("path"), None, match.group(0).replace(chr(10), " "))
    for match in _QUOTED_DENIAL.finditer(text):
        remember(match.group("path"), None, match.group(0))
    for line in text.splitlines():
        if not any(marker in line for marker in PERMISSION_DENIED_MARKERS):
            continue
        for match in _QUOTED_TOKEN.finditer(line):
            candidate = match.group(1) or match.group(2) or ""
            if _looks_like_path(candidate):
                remember(candidate, None, line)
    return tuple(found)



def dsh_home_roots(text: str = "") -> tuple[str, ...]:
    """$DSH_HOME 的候选根：环境变量、默认 ~/.dsh、以及日志自己暴露出来的 profile 根。

    第三条是**从证据出发**的推断（日志里真的出现 <root>/profiles/<name>），
    不是旧判据那种"文本里出现了 profiles 这个词就算"。
    """

    candidates: list[str] = []
    env_home = os.environ.get("DSH_HOME")
    if env_home:
        candidates.append(env_home)
    candidates.append(str(Path.home() / DEFAULT_DSH_HOME_DIRNAME))
    for pattern in (_DSH_HOME_WINDOWS, _DSH_HOME_POSIX):
        for match in pattern.finditer(text):
            candidate = match.group(1)
            if _norm_path(candidate).count("/") >= 2:
                candidates.append(candidate)
    return _unique(candidates)


def temp_roots() -> tuple[str, ...]:
    """本机临时根的候选集合：显式环境变量与平台默认值都算（少一个就会漏判）。"""

    candidates = [
        tempfile.gettempdir(),
        os.environ.get("TEMP"),
        os.environ.get("TMP"),
        os.environ.get("TMPDIR"),
    ]
    if os.name == "nt":
        candidates.append(os.path.expandvars(r"%LOCALAPPDATA%\Temp"))
        candidates.append(os.path.expandvars(r"%SystemRoot%\Temp"))
    else:
        candidates.append("/tmp")
    return _unique([item for item in candidates if item])


def is_under(path: str, roots: Iterable[str]) -> bool:
    """path 是否落在某个根之下（按归一化后的前缀判定，不是子串包含）。"""

    target = _norm_path(path)
    return any(
        target == _norm_path(root) or target.startswith(_norm_path(root) + "/") for root in roots
    )


def is_dsh_startup_scratch(path: str, temps: Iterable[str] | None = None) -> bool:
    """是不是 dsh 自己的启动临时区：系统 temp 之下，或目录名以 dsh- 开头。"""

    if Path(_norm_path(path)).name.startswith(DSH_SCRATCH_PREFIX):
        return True
    return is_under(path, temp_roots() if temps is None else temps)


def has_dsh_boot_failure(text: str) -> bool:
    return any(marker in text for marker in DSH_BOOT_FAILURE_MARKERS)


def classify_startup_denial(
    text: str,
    *,
    homes: Sequence[str] | None = None,
    temps: Sequence[str] | None = None,
) -> StartupDenial | None:
    """按**被拒路径**判断"dsh 自身起不来、是哪一类"。

    判定顺序（每一步都只承认能归因的证据，归不了因就不产生环境跳过）：
      1. 解析出的被拒路径落在 $DSH_HOME（或其 profiles 子目录）下 → profile_write_denied；
      2. 否则必须有 dsh 启动崩溃的原文，且被拒路径落在 dsh 自己的启动临时区 → other_path_denied；
      3. 其余一律返回 None：让这条闭环按失败收场，而不是被洗成 skipped。

    homes/temps 可注入，供检查用例在不碰真实环境变量的前提下驱动判定。
    """

    denials = denied_paths(text)
    if not denials:
        return None
    home_roots = tuple(homes) if homes is not None else dsh_home_roots(text)
    temp_root_list = tuple(temps) if temps is not None else temp_roots()
    inside_home = [item for item in denials if is_under(item.path, home_roots)]
    if inside_home:
        return StartupDenial(
            kind=PROFILE_WRITE_DENIED,
            denial=inside_home[0],
            paths=tuple(item.path for item in denials),
            home_roots=home_roots,
        )
    if not has_dsh_boot_failure(text):
        return None
    scratch = [item for item in denials if is_dsh_startup_scratch(item.path, temp_root_list)]
    if not scratch:
        return None
    return StartupDenial(
        kind=OTHER_PATH_DENIED,
        denial=scratch[0],
        paths=tuple(item.path for item in denials),
        home_roots=home_roots,
    )


def startup_denied_reason(denial: StartupDenial) -> str:
    """把判定写成 reason：两种状态都必须写出**是哪条路径被拒**，且不许写成规则判定。"""

    syscall = f"；拒绝系统调用：{denial.syscall}" if denial.syscall else ""
    if denial.kind == PROFILE_WRITE_DENIED:
        return (
            "dsh 自身起不来（写 profile 被环境拒绝）：受限沙箱不允许写 $DSH_HOME 下的 "
            "profiles/*.yml，dsh 在注册任何 Hook 之前就退出了。这是环境限制，"
            "不是策略判定，也不是本仓库的缺陷——但它与「Hook 起不来」是两层不同的失败，"
            f"所以单独一个状态与理由。被拒路径：{denial.path}{syscall}"
        )
    return (
        "dsh 自身起不来（$DSH_HOME 之外的路径被环境拒绝）：dsh 在注册任何 Hook 之前就退出了，"
        f"但被拒路径不在 $DSH_HOME 下，而在 dsh 自己的启动临时区——被拒路径：{denial.path}{syscall}"
        "（dsh 的 spill-local 插件启动时要 mkdtemp，系统 temp 不可写就会走到这里）。"
        "这不是「写 profile 被拒」，也不是策略判定，更不是本仓库的缺陷；"
        "不要把这条跳过读成任何一条规则判定。"
    )


def run_dsh(prompt: str, log_name: str) -> int:
    argv = dsh_argv()
    assert argv is not None
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [*argv, "--profile", "headless", "--patch", str(PROJECT / ".policy" / "patch.yml"), prompt],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    write(LOGS / log_name, completed.stdout + chr(10) + completed.stderr)
    return completed.returncode


def hook_could_not_spawn() -> bool:
    """判断"审计为空"是不是因为 Hook 进程根本起不来（而不是策略判定或别的失败）。

    本机实测的机制：Hook 走 `ctx.shell`（dsh 的 shell 服务），它用**管道 stdio** 捕获
    Hook 的输出；而受限沙箱禁止打开命名管道，于是 spawn 直接 EPERM。进程内插件把这个
    异常翻译成 deny（失败关闭），模型看到的是"拒绝调用"，审计里则什么都没有——
    与"被 ARCH-001 阻断"是两件完全不同的事，必须区分开，否则会把它当成策略结论。

    复现（仓库外的普通 shell 里）：
        .tmp/phase-2-sandbox/demo-shop> dsh --profile headless \
            --patch .policy/patch.yml \
            "用 edit 工具在 src/shop/order_controller.py 的 import 区加一行"
    """

    for log in sorted(LOGS.glob("*.txt")):
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(marker in text for marker in SPAWN_DENIED_MARKERS):
            return True
    return False


def dsh_startup_denial() -> StartupDenial | None:
    """扫 dsh 的原始日志，返回第一条**可归因**的"dsh 自身起不来"（归不了因就返回 None）。

    归因按被拒路径分类，见 classify_startup_denial：落在 $DSH_HOME 下是写 profile 被拒，
    落在 dsh 自己的启动临时区（系统 temp / dsh- scratch）是另一类失败。
    两者都必须写明是哪条路径被拒；归不了因的权限错误**不产生环境跳过**。
    """

    for log in sorted(LOGS.glob("*.txt")):
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        denial = classify_startup_denial(text)
        if denial is not None:
            return denial
    return None


def dsh_could_not_start() -> bool:
    """兼容包装：是否确认"dsh 自身起不来"（具体是哪一类看 dsh_startup_denial()）。"""

    return dsh_startup_denial() is not None


def audit_records() -> list[dict]:
    path = PROJECT / ".policy" / "audit.jsonl"
    if not path.is_file():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def last_governed(records: list[dict], tool: str) -> dict | None:
    found = None
    for record in records:
        if record.get("tool") == tool and record.get("governed") is True:
            found = record
    return found


def describe(record: dict | None) -> dict:
    if record is None:
        return {}
    return {
        "event_id": record.get("event_id"),
        "request_id": record.get("request_id"),
        "tool": record.get("tool"),
        "operation": record.get("operation"),
        "file": record.get("file"),
        "layer": record.get("layer"),
        "dependencies": record.get("dependencies"),
        "decision": record.get("decision"),
        "reason_code": record.get("reason_code"),
        "exit_code": record.get("exit_code"),
        "executed": record.get("executed"),
        "matched_rules": record.get("matched_rules"),
        "payload_digest": record.get("payload_digest"),
        "rule_set_hash": record.get("rule_set_hash"),
        "timestamp": record.get("timestamp"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="重放 Phase 2 的真实 dsh 沙箱闭环")
    parser.add_argument(
        "--require-dsh",
        action="store_true",
        help="任何环境跳过（dsh 不可用 / Hook 进程起不来 / dsh 自身被环境挡住）都视为失败",
    )
    parser.add_argument("--keep", action="store_true", help="保留上一轮审计与采集")
    args = parser.parse_args(argv)

    if dsh_argv() is None:
        message = "未找到 dsh 可执行文件：跳过真实沙箱闭环（本机验证项，不适合无 dsh 的环境）"
        print(message, file=sys.stderr)
        if args.require_dsh:
            return 1
        write(ARTIFACT, json.dumps(
            {
                "phase": 2,
                "result": "skipped",
                "environment_skipped": True,
                "reason": message,
            },
            ensure_ascii=False,
            indent=2,
        ) + chr(10))
        return 0

    build_project(keep=args.keep)
    controller = PROJECT / "src" / "shop" / "order_controller.py"

    # ---- 场景 1：bad 编辑必须被阻断，文件哈希不变 -------------------------------
    block_before = sha256(controller)
    block_exit = run_dsh(BLOCK_PROMPT, "block-run.txt")
    block_after = sha256(controller)
    records = audit_records()
    block_record = last_governed(records, "edit")

    block_ok = (
        block_before == block_after
        and block_record is not None
        and block_record.get("decision") == "block"
        and block_record.get("exit_code") == 2
        and RULE_ID in (block_record.get("matched_rules") or [])
        and block_record.get("executed") is False
    )

    # ---- 场景 2：good 编辑必须放行，且只发生一次预期变更 -------------------------
    allow_before = sha256(controller)
    allow_exit = run_dsh(ALLOW_PROMPT, "allow-run.txt")
    allow_after = sha256(controller)
    records = audit_records()
    allow_record = last_governed(records, "edit")

    allow_ok = (
        allow_before != allow_after
        and "def ping" in controller.read_text(encoding="utf-8")
        and allow_record is not None
        and allow_record.get("decision") == "allow"
        and allow_record.get("exit_code") == 0
        and allow_record.get("executed") is True
        and RULE_ID in (allow_record.get("matched_rules") or [])
    )

    payload = {
        "phase": 2,
        "agent": "dsh",
        "agent_version": AGENT_VERSION,
        "result": "pass" if (block_ok and allow_ok) else "fail",
        # 环境跳过 ≠ 通过：这个字段是消费者区分"已验证 / 没跑过"的唯一依据
        # （result 的取值集合保持不变，免得动到已验证过的退出码契约）。
        "environment_skipped": False,
        "block_scenario": {
            "passed": block_ok,
            "dsh_exit_code": block_exit,
            "file_sha256_before": block_before,
            "file_sha256_after": block_after,
            "audit": describe(block_record),
        },
        "allow_scenario": {
            "passed": allow_ok,
            "dsh_exit_code": allow_exit,
            "file_sha256_before": allow_before,
            "file_sha256_after": allow_after,
            "audit": describe(allow_record),
        },
        "captured_payloads": sorted(
            item.name for item in (PROJECT / ".policy" / "captures").glob("*.json")
        )
        if (PROJECT / ".policy" / "captures").is_dir()
        else [],
        "logs": sorted(item.name for item in LOGS.glob("*.txt")),
        "timestamp": clock.datetime.now(clock.timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    # 审计里一条记录都没有 = Hook 根本没被执行。这不是策略判定结果，必须与"被规则阻断"
    # 区分开。若确认是"spawn 被沙箱拒绝"，本机就没有能力跑这条闭环：按**环境跳过**处理
    # （退出码 0 + 写明原因），因为把它报成失败会让门禁长期红着、最终被当成噪声；
    # 而伪造一个 pass 更糟——所以既不改判定，也不悄悄放过。
    if not records:
        payload["diagnosis"] = (
            "Hook 从未被调用（审计文件为空）：检查外层环境是否允许嵌套进程启动"
            "（沙箱禁止管道 stdio 时 dsh 的 ctx.shell 会 EPERM）、"
            "以及 dsh 侧是否启用了 patch.yml 的进程内转发插件"
        )
        if hook_could_not_spawn():
            payload["result"] = "skipped"
            payload["environment_skipped"] = True
            payload["reason"] = (
                "Hook 进程起不来（spawn EPERM）：受限沙箱禁止管道 stdio，而 dsh 的 ctx.shell "
                "正是用管道捕获 Hook 输出。命令桥（dsh-hooks-claude-code）走同一个 ctx.shell，"
                "因此换接线方式也绕不过去——这是环境限制，不是策略判定，也不是本仓库的缺陷。"
            )
            payload["sandbox_blocked_spawn"] = True
            payload["reproduce"] = (
                "在不受限的 shell 里执行：cd .tmp/phase-2-sandbox/demo-shop && "
                "dsh --profile headless --patch .policy/patch.yml "
                "\"用 edit 工具在 src/shop/order_controller.py 的 import 区加一行 "
                "'from repository import OrderRepository'，然后一句话报告结果。\""
            )
        elif (denial := dsh_startup_denial()) is not None:
            payload["result"] = "skipped"
            payload["environment_skipped"] = True
            # 兼容字段 + 新字段：消费者既能沿用 dsh_startup_denied，也能直接读出
            # "是哪一类、哪条路径被拒"，不必从 reason 文本里猜。
            payload["dsh_startup_denied"] = True
            payload["dsh_startup_denied_kind"] = denial.kind
            payload["dsh_startup_denied_path"] = denial.path
            payload["dsh_startup_denied_paths"] = list(denial.paths)
            payload["dsh_startup_denied_syscall"] = denial.syscall
            payload["dsh_startup_denied_home_roots"] = list(denial.home_roots)
            payload["reason"] = startup_denied_reason(denial)
            if denial.kind == PROFILE_WRITE_DENIED:
                payload["reproduce"] = (
                    "在不受限的 shell 里（或先把 DSH_HOME 指到可写目录）执行："
                    "python tools/dsh_sandbox_loop.py --require-dsh"
                )
            else:
                payload["reproduce"] = (
                    "在不受限的 shell 里（或先把 TEMP/TMP 指到可写目录——dsh 的 spill-local "
                    "插件在启动时要 mkdtemp）执行：python tools/dsh_sandbox_loop.py --require-dsh"
                )
    write(ARTIFACT, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + chr(10))
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if payload["result"] == "pass":
        return 0
    # 环境跳过默认不红（否则门禁在没 dsh / 沙箱禁止管道 stdio 的机器上长期红着，
    # 最终被当成噪声——这个教训已经记过一次）；但 --require-dsh 必须能把它判成失败：
    # 这个开关问的是"这条闭环真的在本机跑过吗"，**每一条**跳过路径都得被它覆盖。
    if payload.get("environment_skipped") is True:
        return 1 if args.require_dsh else 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
