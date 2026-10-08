"""install_hooks.py：新装的钩子必须真的能被 git 执行（可执行位）。

对应审查结论 tools/install_hooks.py:72：write_text 默认 0644，POSIX 上 git 的
find_hook() 要求 access(X_OK)，新装的 pre-push 于是被静默忽略——推送不跑任何检查，
而脚本仍然打印“已安装”。
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "install_hooks_under_test", REPO_ROOT / "tools" / "install_hooks.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_repo(tmp_root: Path) -> Path:
    repo = tmp_root / "repo"
    (repo / ".git" / "hooks").mkdir(parents=True)
    (repo / "tools").mkdir()
    (repo / "tools" / "ci_local.py").write_text("# probe", encoding="utf-8")
    (repo / ".venv" / "Scripts").mkdir(parents=True)
    (repo / ".venv" / "Scripts" / "python.exe").write_text("", encoding="utf-8")
    return repo


def _install(module, monkeypatch, repo: Path):
    hooks = repo / ".git" / "hooks"
    monkeypatch.setattr(module, "ROOT", repo)
    # 钩子目录现在**问 git**（`rev-parse --git-path hooks`）：假仓库里没有 git，直接给答案。
    monkeypatch.setattr(module, "hooks_dir", lambda: hooks)
    assert module.main([]) == 0
    return hooks / "pre-push"


def test_install_writes_an_executable_hook(tmp_root, monkeypatch):
    """POSIX：新装的钩子必须带可执行位（git 的 find_hook 只认 X_OK 的钩子）。"""

    if os.name == "nt":
        pytest.skip("Windows 没有可执行位：X_OK 恒为真，这条断言在 Windows 上无法证伪")

    module = _load()
    hook = _install(module, monkeypatch, _fake_repo(tmp_root))

    assert hook.is_file()
    assert hook.read_text(encoding="utf-8").startswith("#!/bin/sh")
    assert os.access(hook, os.X_OK), "钩子没有可执行位：git 会静默忽略它"


def test_install_writes_a_hook_that_resolves_the_tree_at_runtime(tmp_root, monkeypatch):
    """钩子在运行时解析仓库根：同一个钩子文件（所有工作树共用）必须跟着 cwd 走。

    写死安装时的绝对路径会让 worktree 里的推送去跑另一棵树的 ci_local —— 门禁测的不是
    你要推的那棵树（实测：只能靠 git push --no-verify 绕过）。
    """

    module = _load()
    repo = _fake_repo(tmp_root)
    hook = _install(module, monkeypatch, repo)

    text = hook.read_text(encoding="utf-8")
    assert "ROOT=$(git rev-parse --show-toplevel)" in text
    assert '"$ROOT/tools/ci_local.py"' in text
    assert '"$ROOT/.venv/Scripts/python.exe"' in text
    assert "CI_LOCAL_PYTHON" in text
    assert (repo / "tools" / "ci_local.py").as_posix() not in text, "不许再写死安装时的路径"


def test_fallback_python_is_escaped_before_it_lands_in_the_hook(tmp_root, monkeypatch):
    """兜底解释器路径里的 $、反引号与 " 必须原样进钩子。

    钩子里那一行是双引号字符串：$ 与反引号照样会被展开、" 会提前闭合。实测（Git for
    Windows 的 bash）：含 $ 的路径被静默换成另一个解释器（PY=/opt/we/python3），
    含 " 或反引号的路径直接变成语法错误（bash -n 退出码 2，unexpected EOF）——
    也就是说钩子装得上、却每次 push 都失败。
    """

    module = _load()
    weird = '/opt/we"ird/$HOME/py`whoami`'
    monkeypatch.setattr(module, "_venv_python", lambda: weird)
    hook = _install(module, monkeypatch, _fake_repo(tmp_root))
    text = hook.read_text(encoding="utf-8")

    assert weird not in text, "路径原样拼进了双引号：$ 与反引号会被 sh 展开"
    # 兜底那一条是模板里最后一条 PY=：前两条回退用的是运行时解析的 $ROOT，不带注入面。
    line = [row for row in text.splitlines() if row.startswith('[ -x "$PY" ] || PY=')][-1]
    assert '\\$HOME' in line and "\\`whoami\\`" in line and '\\"ird' in line
    if os.name == "nt" or shutil.which("sh") is None:
        # Windows 的 system32\bash.exe 是 WSL，不能当成 POSIX sh 用：转义形态已断言，
        # 真实展开行为交给 POSIX（CI）上的后半段守着。
        pytest.skip("本机没有可信的 POSIX sh：只验证了转义形态")
    result = subprocess.run(
        [shutil.which("sh"), "-c", line + '; printf %s "$PY"'],
        capture_output=True, text=True, check=True,
    )
    assert result.stdout == weird, "展开后不再是同一个路径"


def test_hooks_dir_comes_from_git_not_from_a_hardcoded_dot_git(tmp_root, monkeypatch):
    """钩子目录由 git 回答——三种形态旧写法都会判错。

    旧检查是 `(ROOT / ".git").is_dir()`，于是：链接工作树 / 子模块里 `.git` 是文件 → 被误报
    "这里不是 git 仓库"；配了 `core.hooksPath` 时 git 根本不读 `.git/hooks` → 报"已安装"而钩子
    毫无作用；裸仓库 → 靠目录名猜。改成问 git 之后，这三种都由 git 的答案决定。
    """

    module = _load()
    monkeypatch.setattr(module, "ROOT", tmp_root)

    def fake_git(*args):
        if args == ("rev-parse", "--is-inside-work-tree"):
            return "true"
        if args == ("rev-parse", "--git-path", "hooks"):
            return "custom/hooks"
        return None

    monkeypatch.setattr(module, "_git_output", fake_git)
    assert module.hooks_dir() == tmp_root / "custom/hooks", "相对路径要锚回 ROOT"

    monkeypatch.setattr(module, "_git_output", lambda *args: "false")
    assert module.hooks_dir() is None, "不在工作树里要如实回答，而不是猜 .git 目录在不在"

    monkeypatch.setattr(module, "_git_output", lambda *args: None)
    assert module.hooks_dir() is None, "git 不可用同样是 None（不是「这里不是 git 仓库」）"


def test_install_reports_when_there_is_no_work_tree(tmp_root, monkeypatch, capsys):
    module = _load()
    monkeypatch.setattr(module, "ROOT", tmp_root)
    monkeypatch.setattr(module, "hooks_dir", lambda: None)

    assert module.main([]) == 2
    assert "不是 git 工作树" in capsys.readouterr().err


def _prepare(module, monkeypatch, repo: Path):
    hooks = repo / ".git" / "hooks"
    monkeypatch.setattr(module, "ROOT", repo)
    monkeypatch.setattr(module, "hooks_dir", lambda: hooks)
    return hooks / "pre-push", hooks / "pre-push.install-hooks.bak"


def test_a_foreign_hook_is_backed_up_under_our_own_name(tmp_root, monkeypatch):
    """备份用**本脚本专用**的名字，且真的存下那份外来钩子（旧写法只认 `pre-push.bak`）。"""

    module = _load()
    hook, backup = _prepare(module, monkeypatch, _fake_repo(tmp_root))
    hook.write_text("#!/bin/sh\necho 用户的钩子\n", encoding="utf-8")

    assert module.main([]) == 0

    assert backup.is_file()
    assert "用户的钩子" in backup.read_text(encoding="utf-8")
    assert module.MARKER in hook.read_text(encoding="utf-8"), "装上的必须是本脚本生成的钩子"


def test_a_second_foreign_hook_is_not_overwritten_when_a_backup_exists(
    tmp_root, monkeypatch, capsys
):
    """备份已存在时**拒绝**覆盖另一份外来钩子：否则备份与"被替换掉的东西"对不上。"""

    module = _load()
    hook, backup = _prepare(module, monkeypatch, _fake_repo(tmp_root))
    backup.write_text("#!/bin/sh\necho 更早的一份\n", encoding="utf-8")
    hook.write_text("#!/bin/sh\necho 另一份外来钩子\n", encoding="utf-8")

    assert module.main([]) == 2
    assert "备份已存在" in capsys.readouterr().err
    assert "另一份外来钩子" in hook.read_text(encoding="utf-8"), "不许静默覆盖"


def test_uninstall_refuses_to_touch_a_hook_it_did_not_install(tmp_root, monkeypatch, capsys):
    """卸载只动**自己装的**钩子：旧写法会把不相干的 .bak 搬回来盖住别人的钩子、或直接删掉它。"""

    module = _load()
    hook, _backup = _prepare(module, monkeypatch, _fake_repo(tmp_root))
    hook.write_text("#!/bin/sh\necho 别人的钩子\n", encoding="utf-8")

    assert module.main(["--uninstall"]) == 2
    assert hook.is_file(), "不是本脚本装的钩子不许删"
    assert "不是本脚本装的" in capsys.readouterr().err
