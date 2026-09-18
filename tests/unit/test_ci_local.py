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
    monkeypatch.setenv("CI_LOCAL_SENTINEL", "kept")
    monkeypatch.setenv("PYTHONPATH", str(tmp_root / "wrong-source"))

    assert ci_local.main(["--full", "--python", sys.executable]) == 0
