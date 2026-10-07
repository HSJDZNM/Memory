"""编排 CLI 的退出码契约：任务文件里的坏值是**用法错误**（2），不是编排损坏（1）。

`main()` 只把 `OrchestrationError` 与 `(OSError, ValueError, KeyError)` 译成退出码，所以数据解析
必须抛这三类之一：`int({...})` 的 TypeError 会**穿透**，用户看到的是一段栈回溯 + 退出码 1——
既不知道坏在哪个字段，也分不清"我写错了"与"平台坏了"（两者在退出码上同码）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from orchestration.cli import EXIT_ERROR, main, task_from_document


def _document(**patch: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "task_id": "cli-task",
        "target": "src/order/controller.py",
        "changes": [{"path": "src/order/controller.py", "content": "x\n"}],
    }
    base.update(patch)
    return base


@pytest.mark.parametrize(
    ("patch", "field"),
    [
        ({"changes": [{"path": "a.py", "content": "x", "tokens": {"a": 1}}]}, "tokens"),
        ({"changes": [{"path": "a.py", "content": "x", "cost_units": [1]}]}, "cost_units"),
        ({"acceptance": 5}, "acceptance"),
        ({"principal": ["subject"]}, "principal"),
    ],
)
def test_malformed_task_values_are_usage_errors(patch: Mapping[str, Any], field: str) -> None:
    """形状不对要说得出**是哪个字段**坏了（ValueError，而不是 TypeError）。"""

    with pytest.raises(ValueError) as error:
        task_from_document(_document(**patch))

    assert field in str(error.value)


def test_cli_exits_two_and_names_the_broken_field(tmp_root, capsys) -> None:
    """端到端：坏任务文件 → 退出码 2 + 一行理由（不是栈回溯，也不是 1）。"""

    path = Path(tmp_root) / "task.json"
    path.write_text(
        json.dumps(
            _document(changes=[{"path": "a.py", "content": "x", "tokens": {"a": 1}}])
        ),
        encoding="utf-8",
        newline="\n",
    )

    assert main(["run", "--task", str(path)]) == EXIT_ERROR

    captured = capsys.readouterr()
    assert "用法错误" in captured.err
    assert "tokens" in captured.err
