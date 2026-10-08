"""安装 / 卸载本仓库的 pre-push 钩子。

Git 钩子不能随仓库提交（.git/hooks 是本地目录），所以用一个安装脚本把它们写进去。
钩子调用 tools/ci_local.py --hook：按改动范围跑 CI 的对应步骤，红了就拦住推送。

用法：
    python tools/install_hooks.py            # 安装（已存在则覆盖，并备份原文件）
    python tools/install_hooks.py --uninstall # 卸载（有备份就还原）
    python tools/install_hooks.py --show      # 只看当前钩子内容

跳过单次检查：git push --no-verify
解释器覆盖：设置环境变量 CI_LOCAL_PYTHON（钩子与 ci_local.py 都认它）
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
# 受限环境里 .venv 可能缺依赖、也装不进去：把 CI_LOCAL_PYTHON 指向已验证的解释器即可。
# 钩子与 tools/ci_local.py --python 走的是同一条逃生通道。
#
# 仓库根**在运行时**解析，不写死安装时的绝对路径：git 跑钩子时把 cwd 设成当前工作树根，
# 所以 git rev-parse --show-toplevel 拿到的是"你正在推的那棵树"。写死路径会让 worktree
# 里的推送去跑另一棵树的 ci_local（门禁测的不是你要推的东西），换目录 / 换机器后也会失效。
# .git/hooks 是所有工作树共用的，因此这条对 worktree 尤其要紧。
ROOT=$(git rev-parse --show-toplevel) || exit 2
PY="$ROOT/.venv/Scripts/python.exe"
[ -x "$PY" ] || PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="{fallback_python}"
if [ -n "$CI_LOCAL_PYTHON" ]; then PY="$CI_LOCAL_PYTHON"; fi
exec "$PY" "$ROOT/tools/ci_local.py" --hook
"""


def _venv_python() -> str:
    """装钩子时的解释器：只在"当前树没有 .venv"时兜底（见 SCRIPT 里的三段回退）。"""

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
        SCRIPT.format(fallback_python=_venv_python()),
        encoding="utf-8", newline="\n",
    )
    # git 只执行带可执行位的钩子（find_hook 会做 access(X_OK)）：write_text 默认 0644，
    # 在 POSIX 上新建的 pre-push 会被**静默忽略**，推送一个检查都不跑，而脚本还打印"已安装"。
    # Windows 没有可执行位，chmod 在这里是 no-op（只影响只读标志）。
    HOOK.chmod(0o755)
    print("已安装 pre-push -> " + HOOK.as_posix())
    print("跳过单次：git push --no-verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
