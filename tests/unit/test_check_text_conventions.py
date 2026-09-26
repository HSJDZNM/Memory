"""`tools/check_text_conventions.py` 对「读不到 / 不在工作树 / git 清单拿不到」的语义回归测试。

三类「看起来没问题、其实是没查」的形态都有实测事故：

- 未跟踪文件被别的进程握着 → 裸 `read_bytes()` 抛 `PermissionError`，脚本以未捕获异常崩成
  exit 1：门禁红在一个与仓库内容无关的文件上，而且给的是 traceback 而不是问题清单；
- 被跟踪文件从工作树删掉（提交还在）→ 旧实现走 `if not path.is_file(): continue`，打印
  检查 0 个文本文件、问题 0 处 并 exit 0，pre-push 钩子于是放行了一个带行尾空白的提交；
- `GIT_INDEX_FILE` 指向不存在的索引时 `git ls-files --cached` 空手而归 → 被跟踪文件被误判成
  未跟踪，「读不到」就被记成跳过、门禁放行。

约定：被跟踪 / 显式指定的路径一旦读不到或不在工作树，一律失败关闭；git 清单拿不到、
或清单为空，同样失败关闭；只有「未跟踪且只是读不到」这一类记一条显式跳过。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "text_conventions_under_test",
        REPO_ROOT / "tools" / "check_text_conventions.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lock(monkeypatch, locked: Path) -> None:
    """让 `locked` 读起来像被别的进程独占（OSError），其余文件照常读。"""

    real_read_bytes = Path.read_bytes

    def fake_read_bytes(self: Path) -> bytes:
        if self.name == locked.name:
            raise PermissionError(13, "被另一个进程独占")
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", fake_read_bytes)


def test_unreadable_untracked_file_is_an_explicit_skip(monkeypatch, capsys, tmp_root):
    """未跟踪且读不到 → 写明跳过了谁、为什么，退出码 0；不许崩 traceback。"""

    module = _load()
    locked = tmp_root / "tmpch8bfmsm"
    locked.write_bytes(b"")
    _lock(monkeypatch, locked)
    # 只替换清单，comitted_paths 用真实的：这个文件在 .tmp 下、确实未被跟踪
    monkeypatch.setattr(module, "tracked_files", lambda: {locked.as_posix()})

    assert module.main(["check_text_conventions.py"]) == 0
    out = capsys.readouterr().out
    assert "跳过（未跟踪且读取失败）" in out
    assert str(locked) in out
    assert "PermissionError" in out


def test_unreadable_tracked_file_fails_closed(monkeypatch, capsys, tmp_root):
    """被跟踪的仓库文件读不到 → 记问题、退出 1：不能把「没查」当「查过了」。"""

    module = _load()
    locked = tmp_root / "locked.md"
    locked.write_text("ok" + chr(10), encoding="utf-8")
    _lock(monkeypatch, locked)
    monkeypatch.setattr(module, "tracked_files", lambda: {locked.as_posix()})
    monkeypatch.setattr(module, "committed_paths", lambda: {locked.as_posix()})

    assert module.main(["check_text_conventions.py"]) == 1
    out = capsys.readouterr().out
    assert "读取失败（PermissionError）" in out


def test_missing_tracked_file_fails_closed(monkeypatch, capsys, tmp_root):
    """被跟踪但工作树里不存在（提交后 rm 掉）→ 失败关闭，不许记成「检查 0 个文件」。"""

    module = _load()
    gone = tmp_root / "gone.md"
    monkeypatch.setattr(module, "tracked_files", lambda: {gone.as_posix()})
    monkeypatch.setattr(module, "committed_paths", lambda: {gone.as_posix()})

    assert module.main(["check_text_conventions.py"]) == 1
    assert "工作树里不存在" in capsys.readouterr().out


def test_git_listing_failure_fails_closed(monkeypatch, capsys):
    """git 清单拿不到（例如 GIT_INDEX_FILE 指向不存在的索引）→ 失败关闭，不当作没有文件。"""

    module = _load()
    monkeypatch.setattr(module, "committed_paths", lambda: None)

    assert module.main(["check_text_conventions.py"]) == 1
    assert "按失败关闭处理" in capsys.readouterr().out


def test_empty_file_list_is_not_a_pass(monkeypatch, capsys):
    """清单为空也失败关闭：不把「没东西可查」当成「查过了」。"""

    module = _load()
    monkeypatch.setattr(module, "committed_paths", lambda: set())
    monkeypatch.setattr(module, "tracked_files", lambda: set())

    assert module.main(["check_text_conventions.py"]) == 1
    assert "没东西可查" in capsys.readouterr().out


def test_real_problems_are_still_reported(monkeypatch, capsys, tmp_root):
    """没被握住的文件照常检查：行尾空白仍然让门禁红（修复不得削弱检查本身）。"""

    module = _load()
    bad = tmp_root / "bad.md"
    bad.write_text("行尾有空格 " + chr(10), encoding="utf-8")
    monkeypatch.setattr(module, "tracked_files", lambda: {bad.as_posix()})

    assert module.main(["check_text_conventions.py"]) == 1
    assert "行尾有空白" in capsys.readouterr().out
