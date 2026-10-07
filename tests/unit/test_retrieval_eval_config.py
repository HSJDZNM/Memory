"""retrieval_eval 的配置错误必须是退出码 2，且要在建索引之前就收场。

为什么需要：旧实现用 `raise SystemExit("<message>")` 报评测集不合法——那是退出码 1，
与"有门槛未满足"同码，CI 分不清"评测没通过"与"这次根本没配好"；基线的 JSON 读坏时更是
直接一段 traceback（也是 1）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import retrieval_eval


def test_broken_eval_set_raises_a_config_error_not_system_exit(tmp_root: Path) -> None:
    """评测集不合法 → EvalConfigError（由 main 映射成 2），不是 SystemExit(1)。"""

    target = tmp_root / "queries.yaml"
    target.write_text("version: 1" + chr(10) + "queries: 不是列表" + chr(10), encoding="utf-8", newline=chr(10))

    with pytest.raises(retrieval_eval.EvalConfigError) as error:
        retrieval_eval.load_eval_set(target)

    assert "评测集" in str(error.value)


def test_missing_eval_set_is_a_config_error(tmp_root: Path) -> None:
    with pytest.raises(retrieval_eval.EvalConfigError):
        retrieval_eval.load_eval_set(tmp_root / "not-there.yaml")


def test_load_baseline_rejects_broken_shapes(tmp_root: Path) -> None:
    """读不出来 / 不是 JSON / 不是对象 / methods 不是列表：一律 EvalConfigError。"""

    broken = tmp_root / "broken.json"
    broken.write_text("{ 不是 JSON", encoding="utf-8", newline=chr(10))
    with pytest.raises(retrieval_eval.EvalConfigError):
        retrieval_eval.load_baseline(broken)

    with pytest.raises(retrieval_eval.EvalConfigError):
        retrieval_eval.load_baseline(tmp_root / "not-there.json")

    not_object = tmp_root / "list.json"
    not_object.write_text("[1, 2]", encoding="utf-8", newline=chr(10))
    with pytest.raises(retrieval_eval.EvalConfigError):
        retrieval_eval.load_baseline(not_object)

    no_methods = tmp_root / "no-methods.json"
    no_methods.write_text(json.dumps({"eval_set_version": 3}), encoding="utf-8", newline=chr(10))
    with pytest.raises(retrieval_eval.EvalConfigError):
        retrieval_eval.load_baseline(no_methods)


def test_main_maps_config_errors_to_exit_code_2(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """CLI 层：配置错误 → SystemExit(2)，而且**在建索引之前**就停（不留索引库）。"""

    def boom(path: object = None) -> object:
        raise retrieval_eval.EvalConfigError("评测集校验失败：夹具")

    monkeypatch.setattr(retrieval_eval, "load_eval_set", boom)
    db = tmp_root / "index.sqlite3"

    with pytest.raises(SystemExit) as exitinfo:
        retrieval_eval.main(
            ["--method", "fts5", "--gate", "fts5", "--db", str(db), "--out", str(tmp_root / "out.json")]
        )

    assert exitinfo.value.code == 2
    assert "评测集校验失败" in capsys.readouterr().err
    assert not db.exists(), "配置错误要在建库之前收场"