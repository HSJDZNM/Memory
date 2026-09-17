"""安装 / 卸载本仓库的 pre-push 钩子。

Git 钩子不能随仓库提交（.git/hooks 是本地目录），所以用一个安装脚本把它们写进去。
钩子调用 tools/ci_local.py --hook：按改动范围跑 CI 的对应步骤，红了就拦住推送。

用法：
    python tools/install_hooks.py            # 安装（已存在则覆盖，并备份原文件）
    python tools/install_hooks.py --uninstall # 卸载（有备份就还原）
    python tools/install_hooks.py --show      # 只看当前钩子内容

跳过单次检查：git push --no-verify
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".git" / "hooks" / "pre-push"
BACKUP = ROOT / ".git" / "hooks" / "pre-push.bak"

SCRIPT = """#!/bin/sh
# 由 tools/install_hooks.py 生成；不要手改，改 tools/ci_local.py。
# 按改动范围跑 CI 的对应步骤，失败即阻断推送（跳过用 git push --no-verify）。
exec "{python}" "{script}" --hook
"""


def _venv_python() -> str:
    for candidate in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if candidate.is_file():
            return candidate.as_posix()
    return sys.executable.replace("\\", "/")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="安装 / 卸载 pre-push 钩子")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args(argv)

    if not (ROOT / ".git").is_dir():
        print("这里不是 git 仓库：找不到 .git 目录", file=sys.stderr)
        return 2

    if args.show:
        print(HOOK.read_text(encoding="utf-8") if HOOK.is_file() else "（没有安装钩子）")
        return 0

    if args.uninstall:
        if BACKUP.is_file():
            shutil.move(str(BACKUP), str(HOOK))
            print("已卸载，并还原了原来的 pre-push")
        elif HOOK.is_file():
            HOOK.unlink()
            print("已卸载")
        else:
            print("没有安装钩子")
        return 0

    if HOOK.is_file() and not BACKUP.is_file():
        shutil.copy2(str(HOOK), str(BACKUP))
        print("已备份原来的 pre-push -> " + BACKUP.name)
    HOOK.parent.mkdir(parents=True, exist_ok=True)
    HOOK.write_text(
        SCRIPT.format(python=_venv_python(), script=(ROOT / "tools" / "ci_local.py").as_posix()),
        encoding="utf-8", newline="\n",
    )
    print("已安装 pre-push -> " + HOOK.as_posix())
    print("跳过单次：git push --no-verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
