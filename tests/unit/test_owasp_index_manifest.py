"""owasp/04_index.py 的产物必须是**语料状态的函数**，不是"生成时刻的函数"。

为什么需要：manifest.json 是 sha256 键控的产物（描述这批文档），而它唯一一处墙钟字段
`fetched_at` 让同一份语料重跑一次字节就变；正文/README/STRUCTURE 用的都是 build_state 的
抓取日期（TODAY），两者还会互相矛盾。脚本在 import 时就跑完整条流水线（读 _work/ 状态、写
docs/mirrors/），所以这里用 AST 检查语义：这个文件里**不许出现墙钟调用**。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "tools" / "owasp_cheatsheets" / "04_index.py"

#: 墙钟调用的方法名：它们在"产物必须可复现"的生成器里一律不许出现。
WALL_CLOCK_METHODS = ("now", "today", "utcnow", "time", "monotonic")


def _tree() -> ast.Module:
    return ast.parse(SOURCE.read_text(encoding="utf-8"))


def test_manifest_has_no_wall_clock_field() -> None:
    """生成器里不许有 datetime.now()/time.time() 之类的墙钟调用。"""

    offenders: list[str] = []
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in WALL_CLOCK_METHODS:
                offenders.append("第 " + str(node.lineno) + " 行：" + node.func.attr + "()")

    assert offenders == [], "manifest 生成器里出现了墙钟调用（产物将不可复现）：" + "；".join(offenders)


def test_manifest_fetched_at_comes_from_the_build_state() -> None:
    """fetched_at 取 build_state 的抓取日期（TODAY），与正文口径一致。"""

    manifest = None
    for node in _tree().body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "manifest" for target in node.targets
        ):
            manifest = node.value
    assert isinstance(manifest, ast.Dict), "找不到 manifest 字典字面量"

    values = {
        key.value: value
        for key, value in zip(manifest.keys, manifest.values)
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }
    fetched = values.get("fetched_at")
    assert isinstance(fetched, ast.Name) and fetched.id == "TODAY", (
        "fetched_at 必须是 build_state 的抓取日期（TODAY），实际是 " + ast.dump(fetched)
    )

def _extract_function(name: str):
    """把 04_index.py 里的某个函数单独 exec 出来（脚本在 import 时就跑整条流水线，不能 import）。"""

    for node in _tree().body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            module = ast.Module(body=[node], type_ignores=[])
            namespace: dict = {}
            exec(compile(module, str(SOURCE), "exec"), namespace)  # noqa: S102 - 只跑这一个纯函数
            return namespace[name]
    raise AssertionError("找不到函数 " + name)


def test_saved_counter_counts_cheat_sheets_only() -> None:
    """站点索引页不算进 pages_saved（否则 candidate / saved / excluded 三个数对不上）。"""

    saved_cheat_sheets = _extract_function("saved_cheat_sheets")
    pages = [
        {"role": "cheat-sheet"},
        {"role": "cheat-sheet"},
        {"role": "site-index"},
        {"role": "site-index"},
        {"role": "cheat-sheet"},
    ]

    assert saved_cheat_sheets(pages) == 3
    assert saved_cheat_sheets([]) == 0


def test_manifest_uses_the_split_counter() -> None:
    """manifest 里的 pages_saved 必须走这个口径，不许退回 len(pages)。"""

    manifest = None
    for node in _tree().body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "manifest" for target in node.targets
        ):
            manifest = node.value
    assert isinstance(manifest, ast.Dict)

    values = {
        key.value: value
        for key, value in zip(manifest.keys, manifest.values)
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }
    saved = values.get("pages_saved")
    assert isinstance(saved, ast.Call), "pages_saved 必须是计算出来的，不是字面量"
    assert isinstance(saved.func, ast.Name) and saved.func.id == "saved_cheat_sheets", ast.dump(saved)
