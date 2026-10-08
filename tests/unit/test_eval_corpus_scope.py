"""eval_corpus._drop_reason：语料范围判定必须是真包含，不是字符串前缀。

为什么需要：`str(target).startswith(str(base_resolved))` 会把兄弟目录 `<root>/<id>@<rev>-backup/x.py`
当成语料内容——它的字符串确实以语料根的字符串开头，而那份文件不在锁里、也不在这次语料里。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS = REPO_ROOT / "tools"


_MODULE = None


def _load_eval_corpus():
    """按路径加载一次并缓存：这个模块在被 import 时会跑 _load_extra()，重复执行会污染 SOURCES。"""

    global _MODULE
    if _MODULE is not None:
        return _MODULE
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location(
        "eval_corpus_scope_under_test", TOOLS / "eval_corpus.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
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
