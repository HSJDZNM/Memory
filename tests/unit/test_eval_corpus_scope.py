"""eval_corpus._drop_reason：语料范围判定必须是真包含，不是字符串前缀。

为什么需要：`str(target).startswith(str(base_resolved))` 会把兄弟目录 `<root>/<id>@<rev>-backup/x.py`
当成语料内容——它的字符串确实以语料根的字符串开头，而那份文件不在锁里、也不在这次语料里。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS = REPO_ROOT / "tools"


_MODULE = None


def _load_eval_corpus():
    """按**规范名** eval_corpus 加载并复用：同一个进程里多个用例文件必须共用一份实例。

    私有名各加载一份时，第二份的 `_load_extra()` 会拿到第一份的 SourceSpec 去建扩展源
    （tools/eval_corpus_extra.py 里是 `from eval_corpus import ...`），随后被自己的
    isinstance 检查拒掉——两个文件一起跑会整片红。
    """

    global _MODULE
    if _MODULE is not None:
        return _MODULE
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    existing = sys.modules.get("eval_corpus")
    if existing is not None and hasattr(existing, "_drop_reason"):
        _MODULE = existing
        return _MODULE
    spec = importlib.util.spec_from_file_location("eval_corpus", TOOLS / "eval_corpus.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["eval_corpus"] = module
    spec.loader.exec_module(module)
    _MODULE = module
    return module


def _scope(module, *, file: str, line: int = 1):
    annotation = module.Annotation(
        dataset="fixture", revision="0" * 40, file=file, line=line,
        code="S101", kind="line", source="fixture",
    )
    return module.AnnotationScope(annotation, line, line, (line,))


def test_sibling_directory_with_the_same_prefix_is_outside(tmp_root: Path) -> None:
    """`<corpus>-backup/x.py` 不是语料内容：字符串前缀测试会放它进来。"""

    module = _load_eval_corpus()
    base = tmp_root / "corpus"
    backup = tmp_root / "corpus-backup"
    backup.mkdir(parents=True, exist_ok=True)
    (backup / "x.py").write_text("value = 1" + chr(10), encoding="utf-8", newline=chr(10))

    skip = module._drop_reason(base, _scope(module, file="../corpus-backup/x.py"), {})

    assert skip is not None and skip.reason == module.SKIP_TARGET_OUTSIDE_CORPUS


def test_file_inside_the_corpus_is_not_skipped(tmp_root: Path) -> None:
    """语料内的文件照旧不丢（这次收紧不许误伤正常路径）。"""

    module = _load_eval_corpus()
    base = tmp_root / "corpus"
    base.mkdir(parents=True, exist_ok=True)
    (base / "x.py").write_text("value = 1" + chr(10), encoding="utf-8", newline=chr(10))

    assert module._drop_reason(base, _scope(module, file="x.py"), {}) is None

def test_unreadable_target_is_a_skip_not_a_crash(tmp_root: Path) -> None:
    """目标在那儿但读不出来（这里是目录）：记 target_unreadable，不抛 OSError。"""

    module = _load_eval_corpus()
    base = tmp_root / "corpus"
    (base / "adir").mkdir(parents=True, exist_ok=True)

    skip = module._drop_reason(base, _scope(module, file="adir"), {})

    assert skip is not None and skip.reason == module.SKIP_TARGET_UNREADABLE
    assert "读不出来" in skip.detail


def test_read_failure_is_a_skip_not_a_crash(
    tmp_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """读权限错误：记 target_unreadable，OSError 不许逃出 _drop_reason。"""

    module = _load_eval_corpus()
    base = tmp_root / "corpus"
    base.mkdir(parents=True, exist_ok=True)
    (base / "x.py").write_text("value = 1" + chr(10), encoding="utf-8", newline=chr(10))
    real_read_bytes = Path.read_bytes

    def boom(self: Path) -> bytes:
        if self.name == "x.py":
            raise PermissionError("denied by test")
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", boom)

    skip = module._drop_reason(base, _scope(module, file="x.py"), {})

    assert skip is not None and skip.reason == module.SKIP_TARGET_UNREADABLE
    assert "PermissionError" in skip.detail


def test_missing_target_still_uses_the_missing_reason(tmp_root: Path) -> None:
    """真·不存在仍然是 target_missing（理由不许被这次收口改错）。"""

    module = _load_eval_corpus()
    base = tmp_root / "corpus"
    base.mkdir(parents=True, exist_ok=True)

    skip = module._drop_reason(base, _scope(module, file="nope.py"), {})

    assert skip is not None and skip.reason == module.SKIP_TARGET_MISSING

def test_lock_files_shape_is_validated_not_dereferenced(tmp_root: Path) -> None:
    """lock 的 files 段形状不对：逐条记问题，不抛 KeyError/TypeError。"""

    module = _load_eval_corpus()
    problems: list = []

    locked = module._locked_files(
        "fixture",
        {"files": ["not-a-dict", {"path": "a.py"}, {"sha256": "x"}, {"path": "b.py", "sha256": "abc"}]},
        problems,
    )

    assert locked == {"b.py": "abc"}
    assert len(problems) == 3, problems
    assert any("缺 path" in item for item in problems)
    assert any("缺 sha256" in item for item in problems)


def test_lock_files_not_a_list_is_reported(tmp_root: Path) -> None:
    """files 不是数组（或缺失）同样只记问题。"""

    module = _load_eval_corpus()
    problems: list = []

    assert module._locked_files("fixture", {"files": {"a.py": {}}}, problems) == {}
    assert module._locked_files("fixture", {}, problems) == {}
    assert len(problems) == 2, problems


def test_verify_with_non_dict_lock_returns_a_problem(tmp_root: Path) -> None:
    """lock 顶层不是 JSON 对象：verify 返回 (False, 问题)，不是 AttributeError。"""

    module = _load_eval_corpus()
    dataset_id = next(iter(module.SOURCES))
    lock_dir = tmp_root / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    module.lock_path(dataset_id, lock_dir).write_text("[1, 2, 3]" + chr(10), encoding="utf-8", newline=chr(10))

    ok, problems = module.verify(dataset_id, root=tmp_root / "corpora", lock_dir=lock_dir)

    assert ok is False
    assert any("顶层必须是 JSON 对象" in item for item in problems), problems
