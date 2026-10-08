"""validator_loop 的"工具事实可追溯"场景：跳过路径必须窄（条目 [65]）。

为什么需要：这一格原来把 `record is None`（验证器根本没被选中/记录）与任何非 OK 探针状态
（crashed / config_error / timeout / output_invalid）都当成"本机没有可用的 Ruff"的**良性跳过**；
而 `main()` 只汇总 `passed`（`verified` 只是信息位），于是"Ruff 从没跑过"也能整体 pass + 退出 0。
现在只有 `unavailable` / `version_mismatch`（= 这台机器给不出 Ruff）才跳过，其余按失败处理。
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "tools" / "validator_loop.py"


def _load():
    if str(REPO_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "src"))
    spec = importlib.util.spec_from_file_location("validator_loop_under_test", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _record(*, status: str, tool: object = None) -> object:
    return types.SimpleNamespace(status=types.SimpleNamespace(value=status), tool=tool)


def _run(monkeypatch, record: object | None):
    module = _load()
    monkeypatch.setattr(module, "prepare", lambda name: REPO_ROOT)
    report = types.SimpleNamespace(record=lambda validator_id: record)
    monkeypatch.setattr(module, "decide", lambda workspace, target: (report, object()))
    return module.scenario_tool_facts_are_traceable()


def test_no_record_at_all_is_a_failure(monkeypatch) -> None:
    """验证器根本没被记录：不是"本机没装"，按失败处理（旧实现算良性跳过）。"""

    scenario = _run(monkeypatch, None)

    assert scenario.passed is False, scenario
    assert "没有跑" in scenario.detail, scenario.detail


def test_version_mismatch_is_the_benign_skip(monkeypatch) -> None:
    """阳性对照：`unavailable` / `version_mismatch` 才是"这台机器给不出 Ruff"的良性跳过。"""

    for status in ("unavailable", "version_mismatch"):
        scenario = _run(monkeypatch, _record(status=status))
        assert scenario.passed is True and scenario.verified is False, (status, scenario)
        assert "没有可用的 Ruff" in scenario.detail, scenario.detail


def test_probe_failures_are_not_skips(monkeypatch) -> None:
    """crashed / config_error / timeout / output_invalid：都不是"没装"，按失败处理。"""

    for status in ("crashed", "config_error", "timeout", "output_invalid"):
        scenario = _run(monkeypatch, _record(status=status))
        assert scenario.passed is False, (status, scenario)
        assert status in scenario.detail, scenario.detail
