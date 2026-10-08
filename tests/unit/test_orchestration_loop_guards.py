"""编排闭环的两个场景守卫：没有提出任何请求时**以 FAIL 收场**，不抛 IndexError（第 0.5 条 b）。

为什么需要：`tools/orchestration_loop.py` 的 `main()` 会把场景抛出的异常兜底成 FAIL，
但理由只剩 `IndexError: list index out of range`——真实原因（前置运行没走到"提出动作"那一步）
被盖掉了，而那是一条**指错对象**的理由（AGENTS 第 52 条的同一条纪律）。

两条用例分别钉住：

1. 幂等场景（`scenario_idempotent_action`）**新增**的守卫；
2. 人工审批场景（`scenario_human_approval`）**既有**的守卫——它此前没有被任何用例覆盖。

用例不跑任何真实运行：`require_index` / `reset_workspace` / `read_text` / `make_run` 都被替身接管，
被断言的是"守卫怎么把空 `requests` 翻译成读数"。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# 一次"什么都没提出来"的运行：status=blocked + 平台不可用，且 runner.requests 为空。
BLOCKED_REPORT = SimpleNamespace(
    status=SimpleNamespace(value="blocked"),
    failure=SimpleNamespace(
        code=SimpleNamespace(value="policy_unavailable"),
        detail="Policy API 不可达（URLError）",
    ),
)


def _load_loop() -> Any:
    spec = importlib.util.spec_from_file_location(
        "orchestration_loop_under_test", REPO_ROOT / "tools" / "orchestration_loop.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Runner:
    """`ObservableToolRunner` 的最小替身：两条守卫只读 `requests` 与 `outcomes`。"""

    def __init__(self) -> None:
        self.requests: list[Any] = []
        self.outcomes: list[Any] = []


class _Run:
    """`Run` 的最小替身：`client` 必须是 `compat_of` 认得的那个包装（否则读数取不出来）。"""

    def __init__(self, module: Any) -> None:
        self.runner = _Runner()
        self.client = module.ContractCompatClient(object())

    def start(self) -> Any:
        return BLOCKED_REPORT


def _prepare(monkeypatch: Any, module: Any) -> _Run:
    run = _Run(module)
    monkeypatch.setattr(module, "require_index", lambda: None)
    monkeypatch.setattr(module, "reset_workspace", lambda: None)
    monkeypatch.setattr(module, "read_text", lambda path: "message: 旧说明\n")
    monkeypatch.setattr(module, "make_run", lambda *args, **kwargs: run)
    return run


def test_idempotent_scenario_reports_fail_instead_of_index_error(monkeypatch) -> None:
    module = _load_loop()
    run = _prepare(monkeypatch, module)
    assert run.runner.requests == []

    scenario = module.scenario_idempotent_action(SimpleNamespace(base_url="http://127.0.0.1:9"))

    assert scenario.passed is False
    assert scenario.name == "幂等：同一次动作不执行第二次"
    assert "前置场景失败" in scenario.detail
    assert "没有可复用的请求" in scenario.detail
    assert "IndexError" not in scenario.detail
    assert scenario.facts["first_status"] == "blocked"
    assert scenario.facts["first_failure"] == "policy_unavailable"
    assert scenario.facts["first_failure_detail"] == "Policy API 不可达（URLError）"
    assert scenario.facts["evaluate_calls"] == []
    assert scenario.facts["tool_calls"] == 0


def test_human_approval_scenario_reports_fail_instead_of_index_error(monkeypatch) -> None:
    module = _load_loop()
    _prepare(monkeypatch, module)

    scenario = module.scenario_human_approval(SimpleNamespace(base_url="http://127.0.0.1:9"))

    assert scenario.passed is False
    assert scenario.name == "人工审批"
    assert "没有提出任何动作" in scenario.detail
    assert "IndexError" not in scenario.detail
    assert scenario.facts["first_status"] == "blocked"
    assert scenario.facts["first_failure"] == "policy_unavailable"


def test_a_malformed_ledger_line_is_not_silently_dropped(tmp_path: Path) -> None:
    """坏行是"证据缺失"，不是"没有这条"：必须报出行号与原因。

    `read_jsonl` 是 `execution_count(...)` / "零执行" 与台账事实的证据源：静默跳过一条被截断的
    记录（本 harness 会中途 Ctrl-C，append-only 文件因此可能留尾巴）会让结论**少算一次执行**，
    而报告照样打印。
    """

    module = _load_loop()
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text('{"a": 1}\nnot json\n{"a": 2}\n', encoding="utf-8")

    with pytest.raises(RuntimeError) as error:
        module.read_jsonl(ledger)

    assert "第 2 行" in str(error.value)
    assert "不是合法 JSON" in str(error.value)


def test_a_jsonl_line_that_is_not_an_object_is_reported(tmp_path: Path) -> None:
    """合法 JSON 但不是对象（数组 / 数字）同样是"这条记录读不出来"。"""

    module = _load_loop()
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text('{"a": 1}\n[1, 2]\n', encoding="utf-8")

    with pytest.raises(RuntimeError) as error:
        module.read_jsonl(ledger)

    assert "不是对象" in str(error.value)
