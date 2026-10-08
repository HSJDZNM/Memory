"""retrieval.cli 的路径锚点：相对 --corpus/--db 按 --root 解析，不跟随进程 CWD。

对应 L4 结论 src/retrieval/cli.py:321：--root 的帮助文本承诺它是「相对路径的锚点」，
而旧实现用 Path(requested_corpus) 直接按 CWD 解析——从别的目录调用会悄悄换一份清单/库。
"""

from __future__ import annotations

from pathlib import Path

from conftest import write_fixture_corpus

from retrieval.cli import _anchored, run


def test_anchored_keeps_absolute_paths(tmp_root) -> None:
    """绝对路径原样保留（join 只对相对路径生效）。"""

    anchor = tmp_root / "repo"
    absolute = tmp_root / "elsewhere" / "corpus.yaml"
    assert _anchored(anchor, str(absolute)) == absolute
    assert _anchored(anchor, "knowledge/corpus.yaml") == anchor / "knowledge" / "corpus.yaml"


def test_relative_corpus_resolves_against_root_not_cwd(tmp_root, monkeypatch, capsys) -> None:
    """从别的目录调用，--corpus=knowledge/corpus.yaml 仍指向 --root 下的那份清单。"""

    write_fixture_corpus(tmp_root)
    elsewhere = tmp_root / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)  # CWD 里没有 knowledge/corpus.yaml

    code = run(["index", "--check", "--root", str(tmp_root), "--corpus", "knowledge/corpus.yaml"])
    captured = capsys.readouterr()

    assert code == 0, captured.err
    assert "config error" not in captured.err


def test_a_missing_relative_corpus_still_errors(tmp_root, monkeypatch, capsys) -> None:
    """反真空：相对路径真的不存在时仍按配置错误退出 2（不是静默回落）。"""

    write_fixture_corpus(tmp_root)
    elsewhere = tmp_root / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    code = run(["index", "--check", "--root", str(tmp_root), "--corpus", "knowledge/nope.yaml"])
    captured = capsys.readouterr()

    assert code == 2
    assert "摄取清单不存在" in captured.err
