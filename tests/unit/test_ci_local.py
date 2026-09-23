"""本机 CI 编排器的解释器与模块搜索路径回归测试。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_ci_local():
    spec = importlib.util.spec_from_file_location(
        "ci_local_under_test",
        REPO_ROOT / "tools" / "ci_local.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_python_override_runs_modules_from_repo_src_and_preserves_environment(
    monkeypatch,
    tmp_root,
):
    ci_local = _load_ci_local()
    source_dir = tmp_root / "src"
    source_dir.mkdir()
    (source_dir / "ci_local_probe.py").write_text(
        "import os\n"
        "if os.environ.get('CI_LOCAL_SENTINEL') != 'kept':\n"
        "    raise RuntimeError('parent environment was not preserved')\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(ci_local, "ROOT", tmp_root)
    monkeypatch.setattr(
        ci_local,
        "_steps",
        lambda: [("Module import probe", '.venv/bin/python -c "import ci_local_probe"')],
    )
    monkeypatch.setattr(ci_local, "_selected_names", lambda full: [])
    monkeypatch.setattr(ci_local, "_changed_paths", lambda: [])
    # 这条用例验的是解释器覆盖，用的是合成的步骤名；登记门禁另有专门用例，这里显式让开。
    monkeypatch.setattr(ci_local, "unregistered_steps", lambda: [])
    monkeypatch.setenv("CI_LOCAL_SENTINEL", "kept")
    monkeypatch.setenv("PYTHONPATH", str(tmp_root / "wrong-source"))

    assert ci_local.main(["--full", "--python", sys.executable]) == 0


def test_every_runnable_workflow_step_is_registered_or_exempt():
    """workflow 里每个有 run 块的步骤都必须有归属。

    没登记进分组、也不在 NOT_RUN_ON_HOST 里的步骤，在按改动范围选择时
    **既不执行、也不报告跳过**——本仓库正是这样漏跑过真实检查。
    """

    ci_local = _load_ci_local()
    assert ci_local.unregistered_steps() == []


def test_previously_missing_steps_now_have_a_group():
    """曾经无人认领的 4 个真实步骤必须能匹配到某个已登记分组。"""

    ci_local = _load_ci_local()
    prefixes = ci_local.registered_prefixes()
    for name in (
        "Real dsh sandbox loop (skipped without dsh)",
        "Retrieval index is idempotent",
        "Retrieval refuses to answer without sources",
        "Enforcement refuses unknown parameters",
    ):
        assert any(name.startswith(prefix) for prefix in prefixes), name


def test_unregistered_step_fails_closed(monkeypatch, capsys):
    """认不出来的步骤名必须让门禁变红，而不是被静默丢掉。"""

    ci_local = _load_ci_local()
    monkeypatch.setattr(
        ci_local,
        "_steps",
        lambda: [("Some brand new CI step", '.venv/bin/python -c "pass"')],
    )
    monkeypatch.setattr(ci_local, "_selected_names", lambda full: [])
    monkeypatch.setattr(ci_local, "_changed_paths", lambda: [])

    assert ci_local.main(["--list"]) == 1
    assert "Some brand new CI step" in capsys.readouterr().err


def test_exempt_steps_are_reported_instead_of_dropped(monkeypatch, capsys):
    """登记豁免的步骤要出现在清单里（带原因），不能凭空消失。"""

    ci_local = _load_ci_local()
    monkeypatch.setattr(
        ci_local,
        "_steps",
        lambda: [("Install pinned dependencies", "uv venv")],
    )
    monkeypatch.setattr(ci_local, "_selected_names", lambda full: [])
    monkeypatch.setattr(ci_local, "_changed_paths", lambda: [])

    assert ci_local.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "已登记豁免" in out
    assert "Install pinned dependencies" in out
