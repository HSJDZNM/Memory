"""retrieval/__init__.py 的模块地图必须与 CLI 实际注册的子命令一致。

对应 L4 结论 src/retrieval/__init__.py:13：清单落后于 build_parser（少了 quarantine / vector），
而这份 docstring 正是调用方了解「这个包提供什么、怎么用」的入口。
"""

from __future__ import annotations

import argparse

import retrieval
from retrieval.cli import build_parser


def _subcommands() -> set[str]:
    parser = build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def test_module_map_lists_every_subcommand() -> None:
    names = _subcommands()
    assert names, "build_parser 没有注册任何子命令：这条断言本身失效了"
    text = retrieval.__doc__ or ""
    missing = sorted(name for name in names if name not in text)
    assert missing == [], f"模块地图没列出这些子命令：{missing}"
