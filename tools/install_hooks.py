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
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK_NAME = "pre-push"
BACKUP_NAME = "pre-push.install-hooks.bak"  # 本脚本专用名：不再与用户/别的工具的 pre-push.bak 撞名

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


def _git_output(*args: str) -> str | None:
    """跑一条 git 命令并返回 stdout；git 不在 / 命令失败一律 None（调用方据此降级）。"""

    try:
        completed = subprocess.run(
            ["git", "-C", str(ROOT), *args], capture_output=True, text=True, encoding="utf-8"
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def hooks_dir() -> Path | None:
    """钩子目录由 **git 自己**回答（`rev-parse --git-path hooks`），不写死 `.git/hooks`。

    旧写法（`(ROOT / ".git").is_dir()` + 硬编码 `.git/hooks`）漏三种形态：
    1. 链接工作树 / 子模块里 `.git` 是**文件**（gitdir 指针）→ 被误报"这里不是 git 仓库"，
       而 git 其实完全正常；
    2. 配了 `core.hooksPath` 时 git **根本不读** `.git/hooks` → 脚本报"已安装"，钩子毫无作用；
    3. 裸仓库（没有工作树）→ 现在由 `--is-inside-work-tree` 如实回答，而不是靠目录名猜。
    """

    if _git_output("rev-parse", "--is-inside-work-tree") != "true":
        return None
    raw = _git_output("rev-parse", "--git-path", "hooks")
    if not raw:
        return None
    directory = Path(raw)
    return directory if directory.is_absolute() else (ROOT / directory)


MARKER = "# 由 tools/install_hooks.py 生成；不要手改，改 tools/ci_local.py。"


def is_ours(path: Path) -> bool:
    """这个钩子是不是**本脚本装的**：只认生成标记，不看文件名、也不看备份在不在。

    旧写法没有任何归属校验：只要存在任意一个 `pre-push.bak` 就跳过备份（于是用户的或别的工具
    留下的备份会把"当前这个 pre-push 没有被备份"这件事掩盖掉，覆盖后无从还原），卸载时还会把
    那个不相干的 .bak 搬回来盖住当前钩子、或删掉一个不是本脚本装的钩子。
    """

    try:
        return MARKER in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def _sh_double_quoted(value: str) -> str:
    """把要放进 sh 双引号里的字面量转义（路径可能含 $、反引号、" 与反斜杠）。

    双引号里 `$` 与反引号照样会被展开、`"` 会提前闭合、反斜杠要成对写：把路径原样拼进
    `PY="{fallback_python}"` 的话，含 `$` 的路径会**静默换成另一个解释器**，含 `"` /
    反引号的路径会让整份钩子变成语法错误（每次 push 都失败）。这两类路径在真实文件系统里
    都合法（Windows 上 `$` 与反引号合法，POSIX 上三者都合法）。
    """

    escaped = value.replace("\\", "\\\\")
    for character in ('"', "$", "`"):
        escaped = escaped.replace(character, "\\" + character)
    return escaped


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

    directory = hooks_dir()
    if directory is None:
        print("这里不是 git 工作树（或 git 不可用）：装不了钩子", file=sys.stderr)
        return 2
    hook = directory / HOOK_NAME
    backup = directory / BACKUP_NAME

    if args.show:
        print(hook.read_text(encoding="utf-8") if hook.is_file() else "（没有安装钩子）")
        if directory != ROOT / ".git" / "hooks":
            print("# 钩子目录由 git 回答：" + directory.as_posix())
        return 0

    if args.uninstall:
        if hook.is_file() and not is_ours(hook):
            print(
                "当前 " + hook.name + " 不是本脚本装的：不动它（要删请自行处理）", file=sys.stderr
            )
            return 2
        if backup.is_file():
            shutil.move(str(backup), str(hook))
            print("已卸载，并还原了原来的 pre-push")
        elif hook.is_file():
            hook.unlink()
            print("已卸载")
        else:
            print("没有安装钩子")
        return 0

    if hook.is_file() and not is_ours(hook):
        if backup.is_file():
            # 我们只保存**第一次**看到的那份外来钩子（它就是用户的原始文件）。再遇到一份不同的
            # 外来钩子时不能默默覆盖：那会让备份描述的东西与"被替换掉的东西"对不上。
            print(
                "当前 " + hook.name + " 不是本脚本装的，而备份已存在（" + backup.name + "）："
                "继续安装会覆盖它，先自行处理后重试",
                file=sys.stderr,
            )
            return 2
        shutil.copy2(str(hook), str(backup))
        print("已备份原来的 pre-push -> " + backup.name)
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        SCRIPT.format(fallback_python=_sh_double_quoted(_venv_python())),
        encoding="utf-8", newline="\n",
    )
    # git 只执行带可执行位的钩子（find_hook 会做 access(X_OK)）：write_text 默认 0644，
    # 在 POSIX 上新建的 pre-push 会被**静默忽略**，推送一个检查都不跑，而脚本还打印"已安装"。
    # Windows 没有可执行位，chmod 在这里是 no-op（只影响只读标志）。
    hook.chmod(0o755)
    print("已安装 pre-push -> " + hook.as_posix())
    print("跳过单次：git push --no-verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
