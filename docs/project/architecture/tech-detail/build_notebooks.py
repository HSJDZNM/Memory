
# -*- coding: utf-8 -*-
"""生成 docs/project/architecture/tech-detail/ 下的 10 份讲解 notebook（00–09）。

**一章一个目录**（`00-技术总览/` … `09-能不能成为规则/`）：每一章的内容源（`cells.py`）与两份产物
（同名的 `.ipynb` 与 `.py`）都在同一个目录里。
一章一份可执行讲解：**讲解把这套流程跑给人看**，每一步都留下能核对的输出。
内容源在章节目录的 `cells.py`（一个编号一个文件），产物是同名的 `.ipynb` 与 `.py`。

为什么由脚本生成而不是手写 .ipynb：手工编辑的 notebook 在 git 里是一大坨 JSON diff，
而且"文档里写的"与"代码实际跑的"会分叉。生成时顺带做四件事：

1. 把全部代码单元导出成同名的纯 Python 文件（便于阅读与 diff，也方便直接运行）；
2. 从**仓库根**与**本目录**各执行一遍全部代码单元——Jupyter 从哪启动都要得到同样结论；
3. 检查每个 notebook 只用自己独占的 `.tmp/tech-detail/<编号>/`，不碰 `ci_local.py` 与其他
   闭环共用的固定 `.tmp/` 路径（AGENTS.md 写过：并发写这些路径会互相拆台、跑出假红）；
4. 默认断言"只写 .tmp/"：跑完一圈后 git 工作区不应多出未被忽略的文件
   （这条守卫靠 git 快照前后比对，**分不清**"单元写的"与"别的进程同时改的"——
   所以生成需要独占工作区，并发改动会误报，重跑即可）。

用法：

    python docs/project/architecture/tech-detail/build_notebooks.py              # 生成全部并逐单元执行
    python docs/project/architecture/tech-detail/build_notebooks.py --only 03    # 只处理一份（可重复）
    python docs/project/architecture/tech-detail/build_notebooks.py --list       # 只列清单
    python docs/project/architecture/tech-detail/build_notebooks.py --check      # 只比对产物与规格
    python docs/project/architecture/tech-detail/build_notebooks.py --no-exec    # 只写产物、不执行单元

退出码：0 全部通过；1 有失败；2 用法或环境错误。
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import io
import json
import os
import subprocess
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path
from typing import Iterable, Sequence

HERE = Path(__file__).resolve().parent


def find_repo_root(start: Path) -> Path:
    """往上找仓库根：同时有 pyproject.toml 与 src/policy/ 的那一层。"""

    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "policy").is_dir():
            return candidate
    raise SystemExit("没有找到仓库根目录（需要 pyproject.toml 与 src/policy/）")


REPO_ROOT = find_repo_root(HERE)
SRC_DIR = REPO_ROOT / "src"
TOOLS_DIR = REPO_ROOT / "tools"
CELLS_NAME = "cells.py"

KERNELSPEC = {"display_name": "Python 3", "language": "python", "name": "python3"}
LANGUAGE_INFO = {"name": "python", "file_extension": ".py", "mimetype": "text/x-python"}

# ci_local.py 与各阶段闭环共用的固定 .tmp 路径：讲解 notebook 一律不碰。
SHARED_TEMP_PATHS = (
    ".tmp/phase-2-sandbox",
    ".tmp/phase-4-demo",
    ".tmp/phase-5-demo",
    ".tmp/phase-8-orchestration",
    ".tmp/retrieval",
    ".tmp/artifacts",
    "ci-local.lock",
)

TABLE_HELPER = '''

# 表格对齐用的小工具：中文（全角）字符在等宽字体里占 2 列，而 f"{文本:<10}"
# 数的是"字符个数"——中英混排时列会被挤歪。按显示宽度补空格才是对的。
import unicodedata


def display_width(text):
    """文本在等宽字体里占多少列：全角/宽字符算 2 列，其余算 1 列。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in str(text))


def pad(text, width, align="left"):
    """按显示宽度把文本补齐到 width 列，让每一列都从同一个位置开始。"""
    text = str(text)
    blanks = " " * max(0, width - display_width(text))
    if align == "right":
        return blanks + text
    if align == "center":
        left = len(blanks) // 2
        return blanks[:left] + text + blanks[left:]
    return text + blanks
'''


def chapter_dirs() -> dict[str, Path]:
    """磁盘上真实存在的章节目录：名字形如 `00-技术总览`，且里面有 `cells.py`。

    一章一个目录：讲解的内容源（`cells.py`）与两份产物都在同一章里，
    看一章只要打开一个目录。目录名与产物名必须逐字相同（load_spec 会核）。
    """

    found: dict[str, Path] = {}
    collisions: dict[str, list[str]] = {}
    for path in sorted(HERE.glob("[0-9][0-9]-*")):
        if not (path.is_dir() and (path / CELLS_NAME).is_file()):
            continue
        number = path.name[:2]
        if number in found:
            collisions.setdefault(number, [found[number].name]).append(path.name)
            continue
        found[number] = path
    if collisions:
        # 编号是这一章的**唯一键**（`--only 03`、产物名、清单都按它找）。两个目录共用一个编号时
        # "字母序靠后的赢"是静默覆盖：被覆盖的那一章永远生成不出来，也永远进不了 `--check`
        # ——它的产物与内容源可以随便漂移而没有任何读数会红。这是仓库结构错误，直接拒绝
        # （与"没有找到仓库根"同一条出口：退出码 2）。
        for number, names in sorted(collisions.items()):
            print(f"章节目录编号重复：{number} → {', '.join(names)}", file=sys.stderr)
        raise SystemExit(2)
    return found


def available_numbers() -> list[str]:
    """磁盘上真实存在的编号，按名字排序。"""

    return sorted(chapter_dirs())


def load_spec(number: str):
    """按编号加载这一章的内容源模块。只加载被选中的那一个，改一半的邻居不会拖累本次生成。"""

    directory = chapter_dirs().get(number)
    if directory is None:
        raise SystemExit(f"没有编号 {number} 的章节目录（需要 {number}-*/cells.py）")
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    module_name = f"tech_detail_cells_{number}"
    file_spec = importlib.util.spec_from_file_location(module_name, directory / CELLS_NAME)
    module = importlib.util.module_from_spec(file_spec)
    sys.modules[module_name] = module
    file_spec.loader.exec_module(module)
    spec = getattr(module, "SPEC", None)
    if spec is None:
        raise SystemExit(f"{directory.name}/cells.py 没有定义 SPEC")
    if spec.stem != directory.name:
        raise SystemExit(
            f"[{number}] 章节目录与产物名必须逐字相同：目录 {directory.name!r}，SPEC.stem {spec.stem!r}"
            "：一章一个目录，产物就写在它自己那一章里"
        )
    if spec.temp_dir != f".tmp/tech-detail/{number}":
        raise SystemExit(
            f"[{number}] temp_dir 必须是 .tmp/tech-detail/{number}，得到 {spec.temp_dir!r}"
            "：每个 notebook 只用自己独占的临时目录，才不会被并发的其他闭环干扰"
        )
    return spec


def notebook_cells(spec) -> list[tuple[str, str]]:
    """单元序列，并给第一个代码单元附上表格对齐工具（只在真的用到 pad 时才注入）。"""

    cells = list(spec.cells)
    if not any("pad(" in text for _, text in cells):
        return cells
    first_code = next(
        (index for index, (kind, _) in enumerate(cells) if kind == "code"), None
    )
    if first_code is None:
        # 没有代码单元（只有说明，且说明里恰好提到 `pad(`）：这里不注入表格工具。
        # 生成器不该用一个未捕获的 StopIteration 抢在 guard_spec 前面把结论变成 traceback
        # ——"没有任何代码单元"是一条**结构结论**，由守卫按它的口径报出来。
        return cells
    kind, text = cells[first_code]
    cells[first_code] = (kind, text.rstrip() + TABLE_HELPER)
    return cells


def code_string_literals(text: str) -> list[str]:
    """代码单元里的字符串字面量（不含 docstring）。

    为什么不做"全文子串匹配"：讲解里**提到**共用临时路径是正当的（"为什么不碰它"就属于该讲的内容），
    只有把它写成字面量才意味着真会去读它、写它。解析不了（语法错误）时退回全文——宁可多报，不放过。
    """

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [text]

    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            head = body[0] if body else None
            if isinstance(head, ast.Expr) and isinstance(head.value, ast.Constant):
                docstrings.add(id(head.value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


def guard_spec(spec) -> list[str]:
    """静态守卫：共用临时路径不许**写成字符串字面量**。

    这些路径与 `ci_local.py`、各阶段闭环共用，并发写会互相拆台、跑出假红（AGENTS.md 记过）。
    注释或 docstring 里提到它们不算违规——那是讲解内容，不是会执行的路径。
    """

    problems: list[str] = []
    for index, (kind, text) in enumerate(spec.cells):
        if kind != "code":
            continue
        for literal in code_string_literals(text):
            for shared in SHARED_TEMP_PATHS:
                if shared in literal:
                    problems.append(
                        f"[{spec.stem}] 单元 {index} 把共用临时路径 {shared!r} 写成了字符串字面量："
                        f"讲解 notebook 只用 {spec.temp_dir}（并发写共用路径会跑出假红）；"
                        "只是说明的话请写进注释或 docstring"
                    )
    if not spec.cells:
        problems.append(f"[{spec.stem}] 没有任何单元")
    if not any(kind == "code" for kind, _ in spec.cells):
        problems.append(f"[{spec.stem}] 没有任何代码单元：那就不是「可执行讲解」了")
    if not any(kind == "markdown" for kind, _ in spec.cells):
        problems.append(f"[{spec.stem}] 没有任何说明单元：只有代码不算讲解")
    return problems


def cell_source(text: str) -> list[str]:
    """把源码拆成 notebook 需要的行数组（每行带换行，末行不带）。"""

    lines = text.splitlines()
    return [line + "\n" for line in lines[:-1]] + ([lines[-1]] if lines else [])


def build_notebook(cells: Sequence[tuple[str, str]]) -> dict:
    built = []
    for index, (kind, text) in enumerate(cells):
        source = cell_source(text)
        if source:
            source[-1] = source[-1].rstrip("\n")
        cell = {"cell_type": kind, "id": f"{kind}-{index:02d}", "metadata": {}, "source": source}
        if kind == "code":
            # 生成器只写代码与说明，不写运行痕迹：execution_count 与 outputs 永远为空。
            cell["execution_count"] = None
            cell["outputs"] = []
        built.append(cell)
    return {
        "cells": built,
        "metadata": {"kernelspec": KERNELSPEC, "language_info": LANGUAGE_INFO},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def dump_notebook(notebook: dict) -> str:
    return json.dumps(notebook, ensure_ascii=False, indent=1) + "\n"


def extract_script(spec, cells: Sequence[tuple[str, str]]) -> str:
    """把全部单元导出成纯 Python，便于阅读与 git diff。"""

    banner = "# " + "-" * 76
    relative = (HERE / spec.stem / f"{spec.stem}.py").relative_to(REPO_ROOT).as_posix()
    generator = (HERE / "build_notebooks.py").relative_to(REPO_ROOT).as_posix()
    parts = [
        f'"""{spec.title}：tech-detail 讲解 notebook 的纯 Python 版本。',
        "",
        f"由 {generator} 生成，内容与同名的",
        ".ipynb 逐字相同（那份里每段代码也是一个单元）。直接运行本文件即可复现全部输出：",
        "",
        f"    python {relative}",
        "",
        "内容改动请修改同目录的 cells.py 后重新生成，不要直接编辑本文件。",
        '"""',
        "",
        "# **`assert` 就是这些讲解的检查手段**：`-O` / `PYTHONOPTIMIZE` 会把它们**全部剥离**——",
        "# 每张表照样打印、退出码照样 0，而结论一条都没校验：这正是这些脚本要防的假绿。",
        "# 所以在开头就拒绝运行，而不是跑完看起来都对。",
        "import sys as _sys",
        "",
        "if _sys.flags.optimize:",
        "    raise SystemExit(",
        '        "请勿用 -O / PYTHONOPTIMIZE 运行本讲解：assert 已被剥离，结论无法校验"',
        "    )",
    ]
    for kind, text in cells:
        parts.append("")
        if kind == "markdown":
            parts.append(banner)
            parts.extend(("# " + line).rstrip() for line in text.splitlines())
            parts.append(banner)
        else:
            parts.extend(text.splitlines())
    return "\n".join(parts).rstrip() + "\n"


def structural_problems(path: Path) -> list[str]:
    """复用 tools/check_notebook.py 的结构校验，避免这里长出一份平行实现。"""

    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    from check_notebook import check as check_notebook_file

    return [f"[{path.name}] {item}" for item in check_notebook_file(path)]


def run_cells(spec, workdir: Path, *, verbose: bool = True) -> list[str]:
    """在指定工作目录下按顺序执行全部代码单元；返回失败原因列表。"""

    if sys.flags.optimize:
        # 与产物开头那段同一个理由：assert 被剥离时，单元会"全部通过"而结论一条都没校验。
        # 这里必须显式拒绝——生成/门禁路径上绝不允许出现这种假绿。
        print(
            "请勿用 -O / PYTHONOPTIMIZE 运行：assert 会被剥离，讲解单元会全部\"通过\"而结论无从校验",
            file=sys.stderr,
        )
        raise SystemExit(2)
    failures: list[str] = []
    namespace: dict = {"__name__": "__notebook__"}
    for directory in (SRC_DIR, TOOLS_DIR):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))

    previous = Path.cwd()
    os.chdir(workdir)
    try:
        for index, (kind, text) in enumerate(notebook_cells(spec)):
            if kind != "code":
                continue
            buffer = io.StringIO()
            try:
                with redirect_stdout(buffer):
                    exec(compile(text, f"<{spec.stem} cell {index}>", "exec"), namespace)
            except Exception:  # noqa: BLE001 - 生成期要看到全部失败
                failures.append(
                    f"[{spec.stem}] 工作目录 {workdir.name or workdir} 下单元 {index} 执行失败:"
                    + "\n"
                    + traceback.format_exc()
                )
                if verbose:
                    print(f"  [{spec.stem}] 单元 {index:>2} [失败]")
                continue
            if verbose:
                lines = buffer.getvalue().strip().splitlines()
                head = lines[0][:64] if lines else "(无输出)"
                print(f"  [{spec.stem}] 单元 {index:>2} [ok] {head}")
        if spec.structure is not None:
            failures.extend(f"[{spec.stem}] {item}" for item in spec.structure(namespace))
    finally:
        os.chdir(previous)
    return failures


def git_untracked_snapshot() -> set[str]:
    # core.quotePath=false：否则中文文件名会被转义成 "\346\212\200..."，路径后缀判断会失效。
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", "status", "--porcelain"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        # **拿不到基线就不许报"干净"**：git 失败（tarball 检出里没有 .git、索引坏了、
        # dubious ownership）时 stdout 是空的，`after - before` 于是恒为空——
        # "单元动了仓库"这条守卫会永远绿。它是守卫，不是尽力而为的读数。
        detail = (result.stderr or "").strip().splitlines()
        print(
            "git status 失败（退出码 " + str(result.returncode) + "）：工作区守卫拿不到基线，"
            "拒绝按“没有改动”继续" + (f"：{detail[0][:200]}" if detail else ""),
            file=sys.stderr,
        )
        raise SystemExit(2)
    return {line for line in result.stdout.splitlines() if line.strip()}


def unexpected_worktree_changes(
    before: set[str], after: set[str], *, allowed: set[str]
) -> set[str]:
    """本次运行**不该**出现的改动：除 `allowed`（本次生成的两份产物）之外的任何新行。

    为什么不能按后缀放行：`git status --porcelain` 里任何以 `.py` / `.ipynb` 结尾的行都会被
    当成"本次生成的产物"，于是某个单元把仓库里任意 `.py` 改坏（` M src/policy/models.py`）、
    新建 `?? src/evil.py`、删掉 ` D src/x.py` 都不会让生成失败——而这条守卫的注释说的是
    "只允许本目录刚生成的两份产物"。精确比对路径才是那句话的字面意思。
    """

    unexpected: set[str] = set()
    for line in after - before:
        # porcelain v1 的形状：XY<空格>PATH（未跟踪是 `?? PATH`）。
        path = line[3:].strip().strip('"')
        if path not in allowed:
            unexpected.add(line)
    return unexpected


def build_one(spec, *, check_only: bool, execute: bool) -> list[str]:
    failures: list[str] = []
    cells = notebook_cells(spec)
    code_cells = sum(1 for kind, _ in cells if kind == "code")
    markdown_cells = len(cells) - code_cells
    directory = HERE / spec.stem
    assert directory.is_dir(), f"{spec.stem}：章节目录不存在"
    notebook_path = directory / f"{spec.stem}.ipynb"
    script_path = directory / f"{spec.stem}.py"
    text = dump_notebook(build_notebook(cells))
    script = extract_script(spec, cells)
    print(f"[{spec.stem}] {spec.title}：单元 {len(cells)}（代码 {code_cells} / 说明 {markdown_cells}）")

    failures.extend(guard_spec(spec))

    if check_only:
        for path, expected in ((notebook_path, text), (script_path, script)):
            if not path.is_file():
                failures.append(f"{path.name} 不存在：请重新运行本脚本")
            elif path.read_text(encoding="utf-8") != expected:
                failures.append(f"{path.name} 与内容源不一致：请重新运行本脚本")
        # 顺带做结构校验：复用 tools/check_notebook.py（nbformat 版本、单元必需键、
        # source 行数组形态、代码单元能否 compile）。这样 CI 侧一条命令就够，
        # 不用在 workflow 里手写 10 个文件路径——那种清单迟早会漏掉新增的一份。
        if notebook_path.is_file():
            failures.extend(structural_problems(notebook_path))
        if not failures:
            print(f"[{spec.stem}] 产物与内容源一致，结构校验通过")
        return failures

    before = git_untracked_snapshot()
    notebook_path.write_text(text, encoding="utf-8", newline="\n")
    script_path.write_text(script, encoding="utf-8", newline="\n")
    print("  已写入:", notebook_path.relative_to(REPO_ROOT).as_posix())
    print("  已写入:", script_path.relative_to(REPO_ROOT).as_posix())

    if execute:
        for workdir in (REPO_ROOT, HERE):
            label = workdir.relative_to(REPO_ROOT).as_posix() or "."
            found = run_cells(spec, workdir)
            print(f"  工作目录 {label}: " + ("全部通过" if not found else f"{len(found)} 个失败"))
            failures.extend(found)
        after = git_untracked_snapshot()
        # 新出现的未被忽略的文件只允许是本目录刚生成的两份产物（.ipynb / .py）；
        # 其余一律算"单元执行动了仓库"，必须报错而不是放过。
        unexpected = unexpected_worktree_changes(
            before,
            after,
            allowed={
                notebook_path.relative_to(REPO_ROOT).as_posix(),
                script_path.relative_to(REPO_ROOT).as_posix(),
            },
        )
        if unexpected:
            failures.append(
                f"[{spec.stem}] 单元执行期间工作区出现了未被忽略的改动（只允许写 .tmp/ 与本次生成的产物）："
                + "; ".join(sorted(unexpected))
                + "。这条守卫分不清「单元写的」与「别的进程同时改的」——生成需要独占工作区；"
                "先看改动是不是本次 notebook 造成的，不是就等无人并发改动时重跑（实测过一次误报："
                "另一个进程在单元执行期间改了 tech-detail 的 cells.py）。"
            )
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    numbers = available_numbers()
    parser = argparse.ArgumentParser(description="生成 tech-detail 讲解 notebook")
    parser.add_argument("--only", action="append", default=None, help="只处理指定编号（可重复），如 --only 03")
    parser.add_argument("--list", action="store_true", help="只列出清单")
    parser.add_argument("--check", action="store_true", help="只比对产物与内容源，不写入也不执行")
    parser.add_argument("--no-exec", action="store_true", help="写产物但不执行代码单元")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.list:
        for number in numbers:
            spec = load_spec(number)
            print(f"{number}  {spec.stem}  {spec.title}  (临时目录 {spec.temp_dir})")
        return 0

    selected = args.only or numbers
    unknown = [item for item in selected if item not in numbers]
    if unknown:
        print(f"未知编号 {unknown}；可选：{numbers}", file=sys.stderr)
        return 2

    failures: list[str] = []
    for number in selected:
        failures.extend(build_one(load_spec(number), check_only=args.check, execute=not args.no_exec))

    for failure in failures:
        print(failure, file=sys.stderr)
    # 收尾读数必须说清"这一档到底做没做那件事"：`--check` / `--no-exec` 都**不执行单元**，
    # 却一度统一打印「代码单元执行: 全部通过」——把自己的局限说成了"查过了"（2026-10-08 裁定）。
    # 真执行的那一档照旧报执行结果；另外两档报同步/写入结果，并显式写明未执行单元。
    if args.check:
        print(
            "产物与内容源: "
            + ("一致" if not failures else f"{len(failures)} 处不一致")
            + "（未执行单元；执行由 Tech-detail notebooks execute 步骤负责）"
        )
    elif args.no_exec:
        print(
            "产物与内容源: "
            + ("已写入" if not failures else f"写入时 {len(failures)} 处不一致")
            + "（未执行单元：--no-exec）"
        )
    else:
        print("代码单元执行:", "全部通过" if not failures else f"{len(failures)} 个失败")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
