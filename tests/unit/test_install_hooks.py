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
    monkeypatch.setattr(module, "ROOT", repo)
    monkeypatch.setattr(module, "HOOK", repo / ".git" / "hooks" / "pre-push")
    monkeypatch.setattr(module, "BACKUP", repo / ".git" / "hooks" / "pre-push.bak")
    assert module.main([]) == 0
    return repo / ".git" / "hooks" / "pre-push"


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
