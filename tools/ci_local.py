"""在本机按 CI 的顺序跑同一批检查。

为什么需要它：CI 有二十多步，手工挑着跑一定会漏。本仓库就发生过一次——改了 pre-check 的
检查链却漏跑"手册同步"，PR 因此变红。这个脚本把 workflow 当作唯一真相读出来，在本地按
同样顺序执行，并按"这次改了什么"决定跑多少；红了就退出 1，pre-push 钩子据此拦住推送。

用法：

    python tools/ci_local.py              # 按改动范围自动选择（默认）
    python tools/ci_local.py --full       # 跑全部能在本机跑的步骤
    python tools/ci_local.py --list       # 只列出会跑哪些步骤，不执行
    python tools/ci_local.py --hook       # pre-push 钩子用：更简短、失败即退出码 1

只用标准库 + PyYAML（已在锁定依赖里）。bash-only 的步骤（heredoc、set +e、grep -q、
cat > /tmp）在 Windows 上无法直接执行，脚本会**显式跳过并打印原因**，不假装跑过。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"

# 本地解释器：优先用仓库自己的 .venv，其次退回当前解释器。
_VENV = ROOT / ".venv" / "Scripts" / "python.exe"
if not _VENV.is_file():
    _VENV = ROOT / ".venv" / "bin" / "python"
PYTHON = str(_VENV) if _VENV.is_file() else sys.executable

# 这些标记说明该步骤是 bash-only（heredoc、set +e、grep -q、/tmp 路径），本机不执行。
BASH_ONLY_MARKERS = ("<<'PY'", "<<'JSON'", "set +e", "set -e", "grep -q", "cat >", "/tmp/")

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
    "Tool registry must match",
    "Enforcement self-check",
    "Controlled execution closed loop",
    "Audit chain verification",
    "Performance baseline",
)
HANDBOOK_STEPS = (
    "Learning notebooks are in sync",
    "Learning notebook structure",
)
RETRIEVAL_STEPS = (
    "Retrieval corpus integrity",
    "Retrieval evaluation baseline",
    "Tool registry must match",
    "Phase 5 acceptance evidence",
)

# 改了这些前缀，就要跑对应的那一组。
CODE_PREFIXES = ("src/", "tests/", "tools/", "examples/", "policies/", "registry/", ".github/")
RETRIEVAL_PREFIXES = ("knowledge/", "src/retrieval/", "docs/", "tools/retrieval_eval.py")
HANDBOOK_PREFIXES = ("src/", "tools/build_learning_notebook.py", "docs/learning/")


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
    return wanted


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="在本机按 CI 的顺序跑同一批检查")
    parser.add_argument("--full", action="store_true", help="跑全部能在本机跑的步骤")
    parser.add_argument("--list", action="store_true", help="只列出会跑哪些步骤")
    parser.add_argument("--hook", action="store_true", help="pre-push 钩子模式：更简短")
    args = parser.parse_args(argv)

    wanted = _selected_names(args.full)
    changed = _changed_paths()
    plan: list[tuple[str, list[str]]] = []
    skipped: list[tuple[str, str]] = []
    for name, run in _steps():
        if wanted and not any(name.startswith(prefix) for prefix in wanted):
            continue
        if name.startswith(("Install ", "Install pinned")):
            continue
        lines = _local_lines(run)
        if not lines:
            continue
        if _looks_unsafe(lines):
            skipped.append((name, "bash-only（heredoc / set +e / grep / /tmp），CI 上执行"))
            continue
        plan.append((name, lines))

    if args.list:
        print("改动文件 %d 个；本次会跑：" % len(changed))
        for name, _ in plan:
            print("  - " + name)
        if skipped:
            print("本机跳过（CI 上仍然执行）：")
            for name, why in skipped:
                print("  - %s：%s" % (name, why))
        return 0

    if not args.hook:
        print("改动文件 %d 个；执行 %d 步（本机跳过 %d 步）" % (len(changed), len(plan), len(skipped)))

    failures: list[str] = []
    for name, lines in plan:
        for line in lines:
            if not args.hook:
                print("\n=== %s ===\n$ %s" % (name, line), flush=True)
            completed = subprocess.run(line, cwd=str(ROOT), shell=True)
            if completed.returncode != 0:
                failures.append("%s -> 退出码 %s" % (name, completed.returncode))
                if args.hook:
                    print("ci_local: 阻断推送 —— %s" % failures[-1], file=sys.stderr)
                    print("ci_local: 修好再推；确需跳过用 git push --no-verify", file=sys.stderr)
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


if __name__ == "__main__":
    raise SystemExit(main())
