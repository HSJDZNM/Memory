"""owasp pipeline.py：只给开关时必须失败关闭，不许静默跑完整条流水线。

为什么需要：旧实现先 `[a for a in sys.argv[1:] if not a.startswith("-")]` 丢掉所有开关，
于是 `pipeline.py --help` / 误敲 `--dry-run` 都得到空 args → 走"没给参数"分支 → **跑完整条流水线**
（含真实网络抓取）。开关不是注释，收到不认识的开关要拒绝。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "owasp_cheatsheets" / "pipeline.py"


def _load():
    spec = importlib.util.spec_from_file_location("owasp_pipeline_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_flags_only_refuses_instead_of_running_everything(monkeypatch) -> None:
    """只给 --help 之类的开关：退出码 2、一个阶段都不跑。"""

    module = _load()
    calls: list = []
    monkeypatch.setattr(module.subprocess, "call", lambda *a, **k: calls.append(a) or 0)

    for flag in ("--help", "--dry-run"):
        monkeypatch.setattr(sys, "argv", ["pipeline.py", flag])
        assert module.main() == 2, flag

    assert calls == [], "只给开关时不许启动任何阶段"


def test_no_argument_still_runs_all_stages(monkeypatch) -> None:
    """阳性对照：完全不给参数仍然按文档跑全部阶段。"""

    module = _load()
    calls: list = []
    monkeypatch.setattr(module.subprocess, "call", lambda *a, **k: calls.append(a) or 0)
    monkeypatch.setattr(sys, "argv", ["pipeline.py"])

    assert module.main() == 0
    assert len(calls) == len(module.STAGES)

def test_only_a_single_stage_selector_is_accepted(monkeypatch) -> None:
    """`0` / 空串这类前缀一次匹配多个阶段：拒绝，不许静默跑整条流水线。"""

    module = _load()
    calls: list = []
    monkeypatch.setattr(module.subprocess, "call", lambda *a, **k: calls.append(a) or 0)

    for selector in ("0", "", "zz"):
        monkeypatch.setattr(sys, "argv", ["pipeline.py", selector])
        assert module.main() == 2, repr(selector)

    assert calls == []


def test_exact_stage_selector_runs_only_that_stage(monkeypatch) -> None:
    """阳性对照：`03` 只跑 03_build.py。"""

    module = _load()
    calls: list = []
    monkeypatch.setattr(module.subprocess, "call", lambda *a, **k: calls.append(a) or 0)
    monkeypatch.setattr(sys, "argv", ["pipeline.py", "03"])

    assert module.main() == 0
    assert len(calls) == 1
    assert calls[0][0][-1].endswith("03_build.py")
