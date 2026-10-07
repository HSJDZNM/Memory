"""install_hooks.py：新装的钩子必须真的能被 git 执行（可执行位）。

对应审查结论 tools/install_hooks.py:72：write_text 默认 0644，POSIX 上 git 的
find_hook() 要求 access(X_OK)，新装的 pre-push 于是被静默忽略——推送不跑任何检查，
而脚本仍然打印“已安装”。
"""

from __future__ import annotations

import importlib.util
import os
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