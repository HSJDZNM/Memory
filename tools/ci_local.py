"""在本机按 CI 的顺序跑同一批检查。

为什么需要它：CI 有二十多步，手工挑着跑一定会漏。本仓库就发生过一次——改了 pre-check 的
检查链却漏跑"手册同步"，PR 因此变红。这个脚本把 workflow 当作唯一真相读出来，在本地按
同样顺序执行，并按"这次改了什么"决定跑多少；红了就退出 1，pre-push 钩子据此拦住推送。

用法：

    python tools/ci_local.py              # 按改动范围自动选择（默认）
    python tools/ci_local.py --full       # 跑全部能在本机跑的步骤
    python tools/ci_local.py --list       # 只列出会跑哪些步骤，不执行
    python tools/ci_local.py --hook       # pre-push 钩子用：更简短、失败即退出码 1
    python tools/ci_local.py --full --python C:\\path\\to\\python.exe

    # 同一个覆盖，但 pre-push 钩子也用得上（钩子不接受参数）：
    $env:CI_LOCAL_PYTHON = "C:\\path\\to\\python.exe"; git push

并发语义：同一工作树**同时只允许一个实例**真正执行步骤。脚本用一把排他锁
（`<仓库根>/.tmp/ci-local.lock`，操作系统咨询锁、非阻塞）把"同时跑"从静默出错变成显式
拒绝：第二个实例**一步都不执行**，打印持锁者 pid 与起始时间后退出 1（`--hook` 模式下写明
阻断推送）。进程无论怎么死，锁都由操作系统释放，所以不会留下陈旧锁；要恢复只需等它跑完。
理由：ci_local 与它调起的 tools/orchestration_loop.py 共用固定路径的状态
（.tmp/phase-8-orchestration/、.tmp/artifacts/、.tmp/retrieval/），并行会互相拆台——
实测出现过"编排闭环 5/8 场景 FAIL"的假红，而单独跑一律通过。

只用标准库 + PyYAML（已在锁定依赖里）。bash-only 的步骤（heredoc、set +e、grep -q、
cat > /tmp）在 Windows 上无法直接执行，脚本会**显式跳过并打印原因**，不假装跑过。
workflow 里新增了步骤却没有登记进分组时，脚本**失败关闭**（退出码 1）而不是悄悄少跑——
"这个名字我认不出来"必须是一个结论，不能是一段沉默。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import IO, Any, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"

# 本地解释器：优先用仓库自己的 .venv，其次退回当前解释器。
# `CI_LOCAL_PYTHON` 与 `--python` 是同一条逃生通道，区别只在于**钩子也能用**：
# pre-push 钩子不接受参数（git 会把它自己的参数传进来），而受限环境里
# `.venv` 可能缺依赖、也装不进去，此时用环境变量指向一个已验证的解释器。
_VENV = ROOT / ".venv" / "Scripts" / "python.exe"
if not _VENV.is_file():
    _VENV = ROOT / ".venv" / "bin" / "python"
_OVERRIDE = os.environ.get("CI_LOCAL_PYTHON", "").strip()
PYTHON = _OVERRIDE or (str(_VENV) if _VENV.is_file() else sys.executable)

# 这些标记说明该步骤是 bash-only（heredoc、set +e、grep -q、/tmp 路径），本机不执行。
BASH_ONLY_MARKERS = ("<<'PY'", "<<'JSON'", "set +e", "set -e", "grep -q", "cat >", "/tmp/")

# 本机不执行的步骤（登记豁免，每条都要写明原因）：它们都是"装环境"类，本机用已有的 .venv。
# 没登记进分组、也不在本表里的步骤会被 unregistered_steps() 抓出来，main() 直接失败关闭。
NOT_RUN_ON_HOST = {
    "Install uv": "装 uv：本机用已有 .venv，不重复装环境",
    "Install pinned dependencies": "装依赖：本机用已有 .venv，不重复装环境",
    "Install external linter (ruff)": "装 ruff：本机用 validation/ruff.toml 指定的已有工具",
}

# 按改动范围分组的步骤名（前缀匹配）。名字取自 workflow 里的 name:，改 workflow 时要同步。
ALWAYS_STEPS = (
    "Repository consistency gate",
    "Secret scan gate",
    "Text conventions",
)
CODE_STEPS = (
    "Unit, contract",
    "Rule set self-check",
    "AST evidence replay",
    "Example replay",
    "Scope skip reason",
    "Validator registry is loadable",
    "Validator registry declares what is implemented",
    "External tool probe",
    "Validators fail closed",
    "Syntax errors fail closed",
    "Validator closed loop",
    "dsh adapter contract",
    "dsh hook wiring",
    "Real dsh sandbox loop",
    "Tool registry must match",
    "Enforcement self-check",
    "Enforcement refuses unknown parameters",
    "Controlled execution closed loop",
    "Audit chain verification",
    "Multi-agent conformance suite",
    "Adapter support matrix is approved",
    "Adapter event fixtures exist",
    "Agent channel wiring inventory",
    "Multi-agent closed loop",
    "Policy API self-check",
    "Policy API contract snapshot",
    "Policy API ASGI contract",
    "Policy API closed loop",
    "Performance baseline",
)
HANDBOOK_STEPS = (
    "Learning notebooks are in sync",
    "Learning notebook structure",
    "Tech-detail notebooks are in sync",
)
RETRIEVAL_STEPS = (
    "Retrieval corpus integrity",
    "Retrieval index is idempotent",
    "Retrieval refuses to answer without sources",
    "Retrieval evaluation baseline",
    "Tool registry must match",
    "Phase 8 acceptance evidence",
)
ORCHESTRATION_STEPS = (
    "Orchestration self-check",
    "Orchestration closed loop",
)

# 改了这些前缀，就要跑对应的那一组。
CODE_PREFIXES = (
    "src/",
    "tests/",
    "tools/",
    "examples/",
    "policies/",
    "registry/",
    "adapters/",
    ".github/",
)
RETRIEVAL_PREFIXES = ("knowledge/", "src/retrieval/", "docs/", "tools/retrieval_eval.py")
HANDBOOK_PREFIXES = (
    "src/",
    "tools/build_learning_notebook.py",
    "docs/project/learning/",
    "docs/project/architecture/tech-detail/",
)
ORCHESTRATION_PREFIXES = (
    "src/orchestration/",
    "tools/orchestration_loop.py",
    "tests/orchestration_support.py",
)


def _workflow_path() -> Path:
    files = sorted(WORKFLOW_DIR.glob("*.y*ml"))
    if not files:
        raise SystemExit("没有找到 .github/workflows/*.yml：无法知道 CI 跑什么")
    return files[0]


def _steps() -> list[tuple[str, str]]:
    """从 workflow 读 (步骤名, run 文本)；没有 run 的步骤（uses:）跳过。"""

    document = yaml.safe_load(_workflow_path().read_text(encoding="utf-8"))
    jobs = document.get("jobs") or {}
    collected: list[tuple[str, str]] = []
    for job in jobs.values():
        for step in job.get("steps") or []:
            run = step.get("run")
            if isinstance(run, str) and run.strip():
                collected.append((str(step.get("name", "")), run))
    return collected


def _changed_paths() -> list[str]:
    """相对 origin/main（取不到就相对 HEAD~1）的改动文件。"""

    for base in ("origin/main...HEAD", "HEAD~1"):
        completed = subprocess.run(
            ["git", "diff", "--name-only", base],
            cwd=str(ROOT), capture_output=True, text=True,
        )
        if completed.returncode == 0:
            tracked = [line for line in completed.stdout.splitlines() if line.strip()]
            break
    else:
        tracked = []
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(ROOT), capture_output=True, text=True,
    )
    dirty = [line[3:].strip() for line in status.stdout.splitlines() if len(line) > 3]
    return sorted(set(tracked) | set(dirty))


def _touched(changed: list[str], prefixes: tuple[str, ...]) -> bool:
    return any(item.startswith(prefixes) for item in changed)


def _selected_names(full: bool) -> list[str]:
    if full:
        return []  # 空 = 全选
    changed = _changed_paths()
    wanted = list(ALWAYS_STEPS)
    if _touched(changed, CODE_PREFIXES):
        wanted += list(CODE_STEPS)
    if _touched(changed, RETRIEVAL_PREFIXES):
        wanted += list(RETRIEVAL_STEPS)
    if _touched(changed, HANDBOOK_PREFIXES):
        wanted += list(HANDBOOK_STEPS)
    if _touched(changed, ORCHESTRATION_PREFIXES):
        wanted += list(ORCHESTRATION_STEPS)
    return wanted


def registered_prefixes() -> tuple[str, ...]:
    """所有已登记分组的步骤名前缀。"""

    return tuple(ALWAYS_STEPS + CODE_STEPS + HANDBOOK_STEPS + RETRIEVAL_STEPS + ORCHESTRATION_STEPS)


def unregistered_steps() -> list[str]:
    """workflow 里有 run 块、却既没登记进分组、也没写进 NOT_RUN_ON_HOST 的步骤名。

    这类步骤在按改动范围选择时**两个桶都不会进**：既不执行，也不会被打印成"跳过"。
    本仓库正是这样漏跑过真实检查（步骤名没同步进分组，本地永远看不见），
    所以调用方必须失败关闭，而不是把它们当空气。
    """

    prefixes = registered_prefixes()
    missing: list[str] = []
    for name, _run in _steps():
        if not name:
            missing.append("<未命名步骤>")
            continue
        if name in NOT_RUN_ON_HOST:
            continue
        if any(name.startswith(prefix) for prefix in prefixes):
            continue
        missing.append(name)
    return sorted(set(missing))


def _local_lines(run: str) -> list[str]:
    """把 CI 的 run 块翻译成本机可执行的行；顺带做"动作词白名单"。"""

    # 反斜杠续行的多行命令先接成一行，否则续行会被误判成"不是本项目的 python 调用"。
    joined = run.replace("\\" + chr(10), " ")

    lines: list[str] = []
    for raw in joined.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # 只允许"调本项目脚本或模块"的动作，避免把任意 shell 塞进钩子
        if line.startswith(".venv/bin/python "):
            line = PYTHON + " " + line[len(".venv/bin/python ") :]
        lines.append(line)
    return lines


def _looks_unsafe(lines: list[str]) -> bool:
    joined = "\n".join(lines)
    if any(marker in joined for marker in BASH_ONLY_MARKERS):
        return True
    return any(not line.startswith(PYTHON) for line in lines)


def _step_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    return environment


PlanGroups = tuple[list[tuple[str, list[str]]], list[tuple[str, str]], list[tuple[str, str]]]


def _plan_steps(full: bool) -> PlanGroups:
    """把 workflow 的步骤筛成三份：本机要执行的、本机跳过的、登记豁免的。

    规划只读 workflow，不写 `.tmp`，所以 `--list` 与取锁之前都可以调用它。
    """

    wanted = _selected_names(full)
    plan: list[tuple[str, list[str]]] = []
    skipped: list[tuple[str, str]] = []
    not_run: list[tuple[str, str]] = []
    for name, run in _steps():
        if name in NOT_RUN_ON_HOST:
            not_run.append((name, NOT_RUN_ON_HOST[name]))
            continue
        if wanted and not any(name.startswith(prefix) for prefix in wanted):
            continue
        lines = _local_lines(run)
        if not lines:
            not_run.append((name, "run 块里没有本机可执行的命令"))
            continue
        if _looks_unsafe(lines):
            skipped.append((name, "bash-only（heredoc / set +e / grep / /tmp），CI 上执行"))
            continue
        plan.append((name, lines))
    return plan, skipped, not_run


# --------------------------------------------------------------------------- 排他锁
#
# ci_local.py 与它调起的工具（tools/orchestration_loop.py、检索索引、阶段证据）都用**固定路径**
# 的共享状态（.tmp/phase-8-orchestration/、.tmp/artifacts/、.tmp/retrieval/）。两个实例同时跑会
# 互相拆台：实测出现过"编排闭环 5/8 场景 FAIL、二审 exit 1"，而单独跑一律通过——并发会跑出假红。
# 所以同一工作树同时只允许一个实例真正执行步骤，第二个**显式失败退出**（退出码 1，与"红了就退出 1
# / pre-push 钩子据此阻断"一致）：把"同时跑"从静默出错变成显式拒绝。
#
# 刻意**不加 --no-lock、不认环境变量**绕过：并发就是不允许。本仓库的立场是失败关闭，不做
# "看起来有保护"的中间态（同 AGENTS.md 里"GitHub 侧不启用分支保护"的取舍）。
#
# 机制是操作系统咨询锁，且**非阻塞**（绝不挂起等待）：Windows 用 msvcrt.locking(LK_NBLCK)，
# POSIX 用 fcntl.flock(LOCK_EX | LOCK_NB)。锁在进程结束时由 OS 释放，所以不可能留下陈旧锁——
# 不采用"文件存在即上锁"那种写法。
LOCK_OFFSET = 1_048_576  # 1 MiB：锁字节放这里，与文件开头的元数据隔开（Windows 的坑见下）
LOCK_METADATA_BYTES = 4096  # 读元数据只读文件开头这一段，绝不碰 LOCK_OFFSET 附近


def lock_path() -> Path:
    """锁文件路径：`ROOT / ".tmp" / "ci-local.lock"`。

    ROOT 取**调用时刻**的模块属性，不在导入时固化——单测会把它 monkeypatch 到临时目录。
    """

    return Path(ROOT) / ".tmp" / "ci-local.lock"


def lock_metadata(argv: Sequence[str] | None = None) -> dict[str, Any]:
    """本次实例的元数据：pid / 启动时间 / argv 摘要。持锁者把它写进锁文件开头。"""

    effective = list(sys.argv[1:] if argv is None else argv)
    return {
        "pid": os.getpid(),
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "argv": " ".join(effective)[:400],
    }


def read_lock_metadata(path: Path | None = None) -> dict[str, Any] | None:
    """读锁文件开头的元数据（第二个实例靠它报出持锁者 pid）；读不到就返回 None。

    ⚠️ Windows 陷阱：msvcrt.locking 走的是 LockFile 语义，是**强制锁**——被锁的字节区间别的
    进程**读不到**（POSIX 的 flock 是咨询锁，没有这个问题）。所以锁字节写在 LOCK_OFFSET、
    元数据写在文件开头：第二个实例才读得到持锁者 pid，而不是"信息不可读"。
    """

    target = lock_path() if path is None else Path(path)
    try:
        descriptor = os.open(target, os.O_RDONLY)
    except OSError:
        return None
    try:
        raw = os.read(descriptor, LOCK_METADATA_BYTES)
    except OSError:
        return None
    finally:
        os.close(descriptor)
    text = raw.decode("utf-8", "replace").strip()
    if not text:
        return None
    try:
        document = json.loads(text.splitlines()[0])
    except ValueError:
        return None
    return document if isinstance(document, dict) else None


class LockHandle:
    """一把已经持有的排他锁；`release()` 之后失效（重复调用是安全的空操作）。"""

    def __init__(self, path: Path, stream: IO[bytes]) -> None:
        self.path = path
        self._stream: IO[bytes] | None = stream

    def release(self) -> None:
        """清掉元数据、解锁、关掉文件描述符；重复调用什么都不做。"""

        stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            # 顺序很重要：**先清元数据、再解锁**。反过来的话，另一个实例可能已经拿到锁并写好
            # 它自己的 pid，而本进程随后的截断会把那个 pid 抹掉，它就只能报"信息不可读"。
            stream.seek(0)
            stream.truncate(0)
            stream.flush()
            _unlock_stream(stream)
        finally:
            stream.close()

    def __enter__(self) -> "LockHandle":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def _lock_stream(stream: IO[bytes]) -> None:
    """在 LOCK_OFFSET 处非阻塞加 1 字节排他锁；已被别人占着就抛 OSError（绝不等待）。"""

    descriptor = stream.fileno()
    stream.flush()
    if os.name == "nt":
        import msvcrt

        # msvcrt.locking 锁的是**当前文件位置**起的 1 字节，所以先把它挪到 LOCK_OFFSET。
        # LockFile 允许锁超出文件末尾的区间，因此不必把锁文件撑到 1 MiB。
        os.lseek(descriptor, LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_stream(stream: IO[bytes]) -> None:
    """释放 `_lock_stream` 加在 LOCK_OFFSET 处的那 1 字节锁。"""

    descriptor = stream.fileno()
    if os.name == "nt":
        import msvcrt

        os.lseek(descriptor, LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)


def try_acquire_lock(metadata: dict[str, Any] | None = None) -> LockHandle | None:
    """非阻塞取锁：拿到返回句柄，被别的实例占着返回 None（绝不等待，调用方据此退出 1）。

    拿到锁之后**先把元数据写进文件开头再返回**：任何能看到这把锁被占着的人都能读到"是谁在占、
    什么时候开始的"。跨进程可读的只有文件内容，所以这一步是契约的一部分。
    """

    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # 只 O_CREAT、**不加** O_TRUNC：截断会把持锁者写在开头的 pid 抹掉（Windows 的强制锁也挡不住
    # 别的进程截断同一个文件），第二个实例就只能报"信息不可读"。
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    stream = os.fdopen(descriptor, "r+b")
    try:
        _lock_stream(stream)
    except OSError:
        stream.close()
        return None
    payload = metadata if metadata is not None else lock_metadata()
    stream.seek(0)
    stream.truncate(0)
    stream.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
    stream.flush()
    return LockHandle(path, stream)


def _describe_lock_holder(holder: dict[str, Any] | None) -> str:
    """把锁文件里的元数据压成一行给人看的描述。"""

    if not holder:
        return "持锁者：锁文件里没有可读的元数据"
    parts = ["持锁者 pid=%s" % holder.get("pid", "<未记录>")]
    if holder.get("started_at"):
        parts.append("起始时间 %s" % holder["started_at"])
    if holder.get("argv"):
        parts.append("argv: %s" % holder["argv"])
    return "，".join(parts)


def _report_lock_conflict(holder: dict[str, Any] | None, *, hook: bool) -> None:
    """拿不到锁时把"谁在占、怎么办"写到 stderr：锁路径、持锁者 pid、起始时间、处置建议。"""

    print("ci_local: 已经有一个实例在执行本机门禁，拒绝并发。", file=sys.stderr)
    print("ci_local: 锁文件 %s" % lock_path(), file=sys.stderr)
    print("ci_local: %s" % _describe_lock_holder(holder), file=sys.stderr)
    print(
        "ci_local: 等它跑完再跑，不要并发——两个实例共用 .tmp/ 下的固定路径状态"
        "（phase-8-orchestration / artifacts / retrieval），同时跑会互相拆台、跑出假红。",
        file=sys.stderr,
    )
    print(
        "ci_local: 锁由操作系统持有，持锁进程一死就自动释放（不会留陈旧锁）；"
        "确认没有实例在跑就直接重试。",
        file=sys.stderr,
    )
    if hook:
        print("ci_local: 阻断推送 —— 有实例在跑时不重复执行 CI 步骤。", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    global PYTHON

    parser = argparse.ArgumentParser(description="在本机按 CI 的顺序跑同一批检查")
    parser.add_argument("--full", action="store_true", help="跑全部能在本机跑的步骤")
    parser.add_argument("--list", action="store_true", help="只列出会跑哪些步骤")
    parser.add_argument("--hook", action="store_true", help="pre-push 钩子模式：更简短")
    parser.add_argument(
        "--python",
        dest="python_executable",
        help="覆盖步骤使用的 Python：.venv 存在但不可加载时用（也可设 CI_LOCAL_PYTHON）",
    )
    args = parser.parse_args(argv)

    if args.python_executable:
        candidate = Path(args.python_executable).resolve()
        if not candidate.is_file():
            parser.error(f"--python 指向的文件不存在: {candidate}")
        PYTHON = str(candidate)

    missing = unregistered_steps()
    if missing:
        print(
            "ci_local: workflow 里有 %d 个步骤没有登记进任何分组：" % len(missing),
            file=sys.stderr,
        )
        for name in missing:
            print("  - " + name, file=sys.stderr)
        print(
            "ci_local: 按改动范围选择时它们既不执行、也不报告跳过。把它们登记进 "
            "ALWAYS/CODE/HANDBOOK/RETRIEVAL/ORCHESTRATION_STEPS 之一，"
            "或写进 NOT_RUN_ON_HOST 并写明原因。",
            file=sys.stderr,
        )
        return 1

    # `--list` 不取锁：它不写 `.tmp`，而且别的实例正在跑时也可能有人只想看看清单。
    # 规划本身也是只读的，所以它同样留在锁外面。
    if args.list:
        plan, skipped, not_run = _plan_steps(args.full)
        print("改动文件 %d 个；本次会跑：" % len(_changed_paths()))
        for name, _ in plan:
            print("  - " + name)
        if skipped:
            print("本机跳过（CI 上仍然执行）：")
            for name, why in skipped:
                print("  - %s：%s" % (name, why))
        if not_run:
            print("本机不执行（已登记豁免）：")
            for name, why in not_run:
                print("  - %s：%s" % (name, why))
        return 0

    # 从这里往后才真正执行步骤：先拿排他锁，拿不到就**一步都不跑**。
    # 位置有讲究：必须在 unregistered_steps() 的失败关闭检查与 `--list` 之后（两者都不写
    # `.tmp`，也不该被别的实例的运行挡住），又必须在任何步骤执行之前。
    # 先读一次元数据：拿不到锁时，它属于"此刻正占着锁"的那个人。放在尝试之前读，
    # 是为了避免"对方刚好在失败之后释放、元数据被清空"这个窗口——那样就报不出持锁者 pid 了。
    holder = read_lock_metadata()
    try:
        lock = try_acquire_lock(lock_metadata(argv))
    except OSError as error:
        print("ci_local: 建立排他锁失败（%s）：%s" % (lock_path(), error), file=sys.stderr)
        print(
            "ci_local: 拿不到这把锁就没有排他保证，本机门禁失败关闭，一步都不执行。",
            file=sys.stderr,
        )
        return 1
    if lock is None:
        # 前一次读不到（文件刚建好或被清空）就再读一次：此刻持锁者仍然在。
        _report_lock_conflict(holder or read_lock_metadata(), hook=args.hook)
        return 1

    try:
        changed = _changed_paths()
        plan, skipped, not_run = _plan_steps(args.full)
        if not args.hook:
            print(
                "改动文件 %d 个；执行 %d 步（本机跳过 %d 步，登记豁免 %d 步）"
                % (len(changed), len(plan), len(skipped), len(not_run))
            )

        failures: list[str] = []
        step_environment = _step_environment()
        for name, lines in plan:
            for line in lines:
                if not args.hook:
                    print("\n=== %s ===\n$ %s" % (name, line), flush=True)
                completed = subprocess.run(
                    line,
                    cwd=str(ROOT),
                    env=step_environment,
                    shell=True,
                )
                if completed.returncode != 0:
                    failures.append("%s -> 退出码 %s" % (name, completed.returncode))
                    if args.hook:
                        print("ci_local: 阻断推送 —— %s" % failures[-1], file=sys.stderr)
                        print(
                            "ci_local: 修好再推；确需跳过用 git push --no-verify",
                            file=sys.stderr,
                        )
                        return 1
                    break

        if failures:
            print("\n失败 %d 处：" % len(failures), file=sys.stderr)
            for item in failures:
                print("  - " + item, file=sys.stderr)
            return 1
        if not args.hook:
            print("\n本机检查全部通过（%d 步）" % len(plan))
        return 0
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
