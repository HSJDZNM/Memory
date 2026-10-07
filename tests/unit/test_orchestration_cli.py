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


def test_json_flag_works_on_both_sides_of_the_subcommand(capsys) -> None:
    """`--json` 放在子命令**前面**也要生效。

    argparse 解析完子解析器后会把整个命名空间拷回父级——包括子解析器自己的默认值 False，
    于是父级设好的 True 被悄悄盖掉，用户拿到的是人读文本（而脚本按 JSON 解析会炸）。
    """

    assert main(["--json", "graph"]) == 0
    assert capsys.readouterr().out.lstrip().startswith("{")

    assert main(["graph", "--json"]) == 0
    assert capsys.readouterr().out.lstrip().startswith("{")

    # 反向：不给 --json 时仍然是人读文本（SUPPRESS 不能把默认值也吞掉）
    assert main(["graph"]) == 0
    assert not capsys.readouterr().out.lstrip().startswith("{")


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
