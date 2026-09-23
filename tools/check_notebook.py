"""轻量校验 .ipynb 结构（不依赖 nbformat，便于在最小环境里跑 CI）。

用法：python tools/check_notebook.py docs/project/learning/phase-0/walkthrough.ipynb

检查项：nbformat 版本、单元必需键、source 必须是字符串行数组、代码单元必须有 outputs，
以及每个代码单元的源码能被 compile() 解析。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_TOP = ("cells", "metadata", "nbformat", "nbformat_minor")
REQUIRED_CELL = ("cell_type", "metadata", "source")


def check(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{path}: 不是合法 JSON（{error}）"]

    for key in REQUIRED_TOP:
        if key not in notebook:
            problems.append(f"{path}: 缺少顶层键 {key}")
    if notebook.get("nbformat") != 4:
        problems.append(f"{path}: 只支持 nbformat 4，得到 {notebook.get('nbformat')!r}")

    for index, cell in enumerate(notebook.get("cells", [])):
        location = f"单元 {index}"
        for key in REQUIRED_CELL:
            if key not in cell:
                problems.append(f"{location}: 缺少键 {key}")
        if cell.get("cell_type") not in {"code", "markdown", "raw"}:
            problems.append(f"{location}: 未知 cell_type {cell.get('cell_type')!r}")
            continue
        source = cell.get("source")
        if not isinstance(source, list) or not all(isinstance(line, str) for line in source):
            problems.append(f"{location}: source 必须是字符串数组")
            continue
        if any(not line.endswith(chr(10)) for line in source[:-1]):
            problems.append(f"{location}: source 除最后一行外都必须以换行结尾")
        if source and source[-1].endswith(chr(10)):
            problems.append(f"{location}: source 最后一行不应以换行结尾")
        if cell.get("cell_type") != "code":
            continue
        if "outputs" not in cell or "execution_count" not in cell:
            problems.append(f"{location}: 代码单元必须含 execution_count 与 outputs")
        body = "".join(source)
        try:
            compile(body, f"<cell {index}>", "exec")
        except SyntaxError as error:
            problems.append(f"{location}: 语法错误 {error.msg}（第 {error.lineno} 行）")
    return problems


def main(argv: list[str]) -> int:
    targets = [Path(item) for item in argv[1:]]
    if not targets:
        print(__doc__)
        return 2

    problems: list[str] = []
    for target in targets:
        found = check(target)
        problems.extend(found)
        print(f"{target}: {'OK' if not found else str(len(found)) + ' 个问题'}")
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
