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


def test_crlf_suffixes_only_exempt_the_line_ending_rule(monkeypatch, capsys, tmp_root):
    """.ps1/.bat/.cmd 只豁免行尾：BOM / 行尾空白照查（旧实现对它们跳过全部规则）。"""

    module = _load()
    ps1 = tmp_root / "script.ps1"
    ps1.write_bytes(b"\xef\xbb\xbfWrite-Host 'x' " + b"\r\n")
    monkeypatch.setattr(module, "tracked_files", lambda: {ps1.as_posix()})
    monkeypatch.setattr(module, "committed_paths", lambda: {ps1.as_posix()})

    assert module.main(["check_text_conventions.py"]) == 1
    out = capsys.readouterr().out
    assert "含 UTF-8 BOM" in out
    assert "行尾有空白" in out
    assert "含 CRLF" not in out, "行尾豁免本身不能被这条修复取消"


def test_crlf_suffix_still_needs_a_final_newline(monkeypatch, capsys, tmp_root):
    """豁免行尾 ≠ 豁免末尾换行：.bat 没有末尾换行同样要报。"""

    module = _load()
    bat = tmp_root / "run.bat"
    bat.write_bytes(b"echo hi")
    monkeypatch.setattr(module, "tracked_files", lambda: {bat.as_posix()})
    monkeypatch.setattr(module, "committed_paths", lambda: {bat.as_posix()})

    assert module.main(["check_text_conventions.py"]) == 1
    assert "未以单个换行符结尾" in capsys.readouterr().out


def test_real_problems_are_still_reported(monkeypatch, capsys, tmp_root):
    """没被握住的文件照常检查：行尾空白仍然让门禁红（修复不得削弱检查本身）。"""

    module = _load()
    bad = tmp_root / "bad.md"
    bad.write_text("行尾有空格 " + chr(10), encoding="utf-8")
    monkeypatch.setattr(module, "tracked_files", lambda: {bad.as_posix()})

    assert module.main(["check_text_conventions.py"]) == 1
    assert "行尾有空白" in capsys.readouterr().out

def test_binary_skips_are_counted_in_the_summary(monkeypatch, capsys, tmp_root):
    """条目 [18]：跳过的二进制要单独报数——旧实现既不算 checked 也不算 skipped，
    `… some/file.bin`（哪怕名字敲错）会打印"检查 0 个文本文件，问题 0 处"并退 0。"""

    module = _load()
    blob = tmp_root / "asset.png"
    blob.write_bytes(b"\x89PNG\r\n\x1a\n")

    assert module.main(["check_text_conventions.py", str(blob)]) == 0
    out = capsys.readouterr().out

    assert "检查 0 个文本文件，问题 0 处" in out
    assert "跳过二进制 1 个" in out, out


def test_nul_sniffed_binary_is_counted_too(monkeypatch, capsys, tmp_root):
    """按内容判出来的二进制（前缀含 NUL）同样记账。"""

    module = _load()
    blob = tmp_root / "sneaky.dat"
    blob.write_bytes(b"text\x00more")

    assert module.main(["check_text_conventions.py", str(blob)]) == 0
    out = capsys.readouterr().out

    assert "跳过二进制 1 个" in out, out

def test_vanished_untracked_target_is_an_explicit_skip(monkeypatch, capsys, tmp_root):
    """条目 [19]：未跟踪路径在工作树里消失（"先列出、后消失"的窗口 / 悬空链接）必须留痕。

    旧实现这条分支什么都不记——不报问题、不打印跳过、不计数，文件无痕消失，
    与模块 docstring 的"绝不静默"相反。
    """

    module = _load()
    ghost = tmp_root / "tmp-ghost-m9check"
    monkeypatch.setattr(module, "tracked_files", lambda: {ghost.as_posix()})

    assert module.main(["check_text_conventions.py"]) == 0
    out = capsys.readouterr().out

    assert "跳过（未跟踪且工作树里不存在）" in out, out
    assert "tmp-ghost-m9check" in out, out
    assert "跳过未跟踪且工作树里不存在 1 个" in out, out

def test_running_from_a_subdirectory_checks_the_same_set(monkeypatch, capsys):
    """条目 [17]：从子目录调用必须与从仓库根调用检查**同一批文件**。

    旧实现跑的是不带 `--full-name` 的 `git ls-files`（输出被限制在当前目录、路径也相对它）：
    从 `docs/` 跑一次只检查 363 个文件（全仓 619），`MIRRORED_PREFIXES` 是仓库相对的、全部匹配不上，
    上游镜像被当成本仓库文本报出 49 处假问题——而汇总照样打印成一次"全仓"结论。
    """

    module = _load()
    summaries: dict[str, str] = {}
    for label, cwd in (("root", REPO_ROOT), ("docs", REPO_ROOT / "docs")):
        monkeypatch.chdir(cwd)
        assert module.main(["check_text_conventions.py"]) == 0, label
        out = capsys.readouterr().out
        summaries[label] = [line for line in out.splitlines() if line.startswith("检查 ")][-1]

    assert summaries["root"] == summaries["docs"], summaries
    assert "mirrors" not in summaries["docs"], summaries["docs"]


def test_empty_committed_list_does_not_disable_fail_closed(monkeypatch, capsys):
    """`--cached` 清单为空（索引读不到）时，被跟踪文件不许被当成未跟踪。

    这是「清单为空」的**局部**形态：`tracked_files()` 仍然有内容（`--others` 照常列出未跟踪
    文件），所以只靠"文件清单为空"那道门拦不住——必须在 `committed_paths()` 这一层就失败关闭。
    """

    module = _load()
    monkeypatch.setattr(module, "committed_paths", lambda: set())
    monkeypatch.setattr(module, "tracked_files", lambda: {"README.md"})

    assert module.main(["check_text_conventions.py"]) == 1
    assert "按失败关闭处理" in capsys.readouterr().out
