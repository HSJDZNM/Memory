"""轻量校验 .ipynb 结构（不依赖 nbformat，便于在最小环境里跑 CI）。

用法：python tools/check_notebook.py docs/project/architecture/tech-detail/00-技术总览/00-技术总览.ipynb

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
    # 读与解析分开报：UnicodeDecodeError 是 ValueError 的子类（不是 OSError/JSONDecodeError），
    # 而"文件不存在/是个目录"这类 OSError 也不是"不是合法 JSON"——旧写法把两者都盖成一句话，
    # 一半是崩溃（非 UTF-8 直接逃出去），一半是把真实原因说错。
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        return [f"{path}: 读不出来（{type(error).__name__}: {error}）"]
    except UnicodeDecodeError as error:
        return [f"{path}: 不是 UTF-8 文本（{error}）"]
    try:
        notebook = json.loads(text)
    except json.JSONDecodeError as error:
        return [f"{path}: 不是合法 JSON（{error}）"]

    # JSON 合法不等于形状正确：json.loads 可以返回 [] / "x" / 42 / null，
    # 直接对它们做成员测试或 .get() 会抛 TypeError / AttributeError —— 那是把
    # "这份 notebook 畸形"变成一次 traceback，还会中断后面所有目标的检查。
    if not isinstance(notebook, dict):
        return [f"{path}: 顶层必须是 JSON 对象，得到 {type(notebook).__name__}"]

    for key in REQUIRED_TOP:
        if key not in notebook:
            problems.append(f"{path}: 缺少顶层键 {key}")
    if notebook.get("nbformat") != 4:
        problems.append(f"{path}: 只支持 nbformat 4，得到 {notebook.get('nbformat')!r}")

    cells = notebook.get("cells")
    if not isinstance(cells, list):
        # 缺键已经在上面报过；这里只报"形状不对"，没有可迭代的单元就不再往下走。
        if "cells" in notebook:
            problems.append(f"{path}: cells 必须是数组，得到 {type(cells).__name__}")
        return problems

    for index, cell in enumerate(cells):
        location = f"单元 {index}"
        if not isinstance(cell, dict):
            problems.append(f"{location}: 单元必须是 JSON 对象，得到 {type(cell).__name__}")
            continue
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
            # 行号可能缺（NUL 字节这类源码级错误的 lineno 是 None）：旧写法会打印
            # "（第 None 行）"——读数里写一个假行号比不写更糟。
            where = f"（第 {error.lineno} 行）" if error.lineno else ""
            problems.append(f"{location}: 语法错误 {error.msg}{where}")
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
