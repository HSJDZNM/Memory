"""临时文件卫生：临时根必须落在仓库内 .tmp/，不能回退到仓库根。

实测的缺陷：TMPDIR/TEMP/TMP 都不可写时（受限沙箱里 %TEMP% 的写入被拒），Python 的 tempfile
会回退到 os.getcwd()（_candidate_tempdir_list 的最后一站就是 cwd）；pytest 的全局捕获用
TemporaryFile 承接 stdout/stderr，于是在会话一开始就把两个 0 字节的 tmpXXXXXXXX 建在仓库根。
它们被活进程独占、直到会话结束才消失：期间 git status 变脏，tools/check_text_conventions.py
还会在「先列出来、后读不到」的窗口里报错。
"""
from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path

from conftest import REPO_ROOT

TEMP_VARIABLES = ("TMPDIR", "TEMP", "TMP")
# tempfile 的默认命名是前缀 "tmp" + 8 位随机字符：只匹配这个形状，避免把别的 tmp* 误算进来。
TMP_FILE_GLOB = "tmp????????"


def _repo_root_tmp_names() -> set[str]:
    """仓库根（非递归）里形如 tempfile 产物的文件名。"""

    return {path.name for path in REPO_ROOT.glob(TMP_FILE_GLOB)}


def _load_ci_local():
    """按路径加载 tools/ci_local.py（与 tests/unit/test_ci_local.py 同一手法）。"""

    spec = importlib.util.spec_from_file_location(
        "ci_local_temp_hygiene", REPO_ROOT / "tools" / "ci_local.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_session_temp_root_is_inside_repo_tmp_and_writable() -> None:
    """会话注入的三个临时变量指向仓库内 .tmp/ 下的同一个可写目录，tempfile 也认它。"""

    resolved: set[str] = set()
    for name in TEMP_VARIABLES:
        value = os.environ.get(name)
        assert value, f"{name} 必须由会话显式设置，否则受限环境里会回退到 cwd"
        directory = Path(value)
        assert directory.is_dir(), f"{name} 指向的目录必须存在：{directory}"
        assert directory.resolve().is_relative_to((REPO_ROOT / ".tmp").resolve())
        resolved.add(str(directory.resolve()))
    # 三个变量必须一致：tempfile 依次看 TMPDIR / TEMP / TMP，不一致就等于行为随机器而变。
    assert len(resolved) == 1
    effective = Path(tempfile.gettempdir()).resolve()
    assert effective.is_relative_to((REPO_ROOT / ".tmp").resolve())
    assert effective != REPO_ROOT.resolve()


def test_gate_step_environment_injects_temp_root_for_subprocesses(monkeypatch, tmp_root) -> None:
    """门禁给每个子步骤注入的临时根同样落在 .tmp/ 下，并且真的能写。"""

    ci_local = _load_ci_local()
    monkeypatch.setattr(ci_local, "ROOT", tmp_root)

    environment = ci_local._step_environment()
    roots = {str(Path(environment[name]).resolve()) for name in TEMP_VARIABLES}
    assert len(roots) == 1
    root = Path(roots.pop())
    assert root.is_dir()
    assert root.is_relative_to((tmp_root / ".tmp").resolve())
    probe = root / "write_probe.txt"  # 落在临时目录里，不碰真仓库根
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()


def test_tempfile_creation_stays_out_of_the_repo_root(monkeypatch, tmp_root) -> None:
    """临时根指向夹具目录时，mkstemp 的文件落进夹具，仓库根一个 tmp* 都不多。"""

    before = _repo_root_tmp_names()
    sandbox = tmp_root / "temp-root"
    sandbox.mkdir()
    for name in TEMP_VARIABLES:
        monkeypatch.setenv(name, str(sandbox))
    # 丢掉缓存：否则 gettempdir() 仍然返回会话开始时算出来的那个值，这项断言就测了个空气。
    monkeypatch.setattr(tempfile, "tempdir", None)

    descriptor, name = tempfile.mkstemp()
    os.close(descriptor)
    created = Path(name)
    try:
        assert created.parent.resolve() == sandbox.resolve()
        assert created.name.startswith("tmp")
    finally:
        created.unlink()
    assert _repo_root_tmp_names() == before
