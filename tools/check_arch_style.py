# -*- coding: utf-8 -*-
"""检查 docs/project/architecture 的文风：概括性语言与精确描述性语言是否失衡。

用法：

    python tools/check_arch_style.py

退出码：0 = 平衡；1 = 有失衡项（概括句过长 / 长句比例过高 / 术语墙 / 连续无标点）。

与 docs/project/architecture/术语与口径.md §7 一致，但**只检查散文**：
- 表格行与代码围栏不参与句子/长句/术语墙判定（它们本来就该密）；
- 概括句取每个 H2 小节的第一段散文（跳过表格、围栏、标题、引用块）。
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARCH = ROOT / "docs/project/architecture"
BT = chr(96)
TOKEN = BT + "[^" + BT + "\n]+" + BT
# 「精确锚点」判据：每个 H2 小节至少要有文件:行 / 标识符 / 路径 / 枚举中一种，
# 否则概括句没有人能顺着查下去（口径表 §7）。与图无关——它读的是散文。
ANCHOR = re.compile(
    "(" + TOKEN
    + r"|\b[\w./-]+\.(py|md|yaml|json):\d+"
    + r"|[\w-]+/[\w./-]+"
    + r"|allow_with_warnings|needs_human|uncovered_checker|action_hash)"
)
FENCE_OPEN = "^\\s*(" + BT * 3 + "|~~~)"
SENTENCE = re.compile(r"[^。；！？\n]+[。；！？]?")
FENCE = re.compile(FENCE_OPEN)


def prose_lines(text: str):
    """返回 (行号, 内容) 的散文行：跳过围栏代码与表格行。"""
    inside = False
    for index, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            inside = not inside
            continue
        if inside:
            continue
        stripped = line.strip()
        if stripped.startswith("|") or stripped.startswith("<"):
            continue
        yield index, line


def sections(text: str):
    title, body = None, []
    for index, line in prose_lines(text):
        if line.startswith("## "):
            if title:
                yield title, body
            title, body = line[3:].strip(), []
        elif title:
            body.append(line)
    if title:
        yield title, body


def first_paragraph(body) -> str:
    collected, started = [], False
    for line in body:
        stripped = line.strip()
        if not stripped:
            if started:
                break
            continue
        if stripped.startswith((">", "-", "*", "#", "---")):
            continue
        started = True
        collected.append(stripped)
    return " ".join(collected)


def check_docs() -> list:
    problems = []
    paths = sorted(ARCH.glob("*.md"))
    if not paths:
        # 空输入集不是"通过"：目录被改名 / 移动 / 路径写错时 glob 返回空，旧实现会打印
        # "平衡"并退出 0 —— 一次什么都没检查的绿。缺输入本身就是一条问题。
        try:  # 守卫自己不能崩：目录不在仓库内（测试夹具）时如实显示原路径
            shown = ARCH.relative_to(ROOT).as_posix()
        except ValueError:
            shown = ARCH.as_posix()
        problems.append("未找到任何架构文档：" + shown + "（目录被改名 / 移动，或路径写错？）")
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for title, body in sections(text):
            paragraph = first_paragraph(body)
            if not paragraph:
                continue
            first = SENTENCE.match(paragraph).group(0).strip()
            if len(first) > 45:
                problems.append(path.name + " §" + title[:18] + " 概括句过长（" + str(len(first)) + " 字）：" + first[:34] + "…")
            if not ANCHOR.search(" ".join(body)):
                problems.append(path.name + " §" + title[:18] + " 没有精确锚点（文件:行 / 标识符 / 路径 / 枚举）")
        prose = " ".join(line for _n, line in prose_lines(text))
        sentences = [s.strip() for s in SENTENCE.findall(prose) if len(s.strip()) > 3]
        ratio = len([s for s in sentences if len(s) > 90]) / max(1, len(sentences))
        if ratio > 1 / 3:
            problems.append(path.name + " 长句（>90 字）比例过高：" + str(int(100 * ratio)) + "%（散文句 " + str(len(sentences)) + " 句）")
        for index, line in prose_lines(text):
            if len(re.findall(TOKEN, line)) >= 8:
                problems.append(path.name + ":" + str(index) + " 术语墙（单行 >=8 个标识符）")
            if "http" in line:
                continue
            run = max((len(part) for part in re.split(r"[，。；：、（）\s]", line.strip())), default=0)
            if run > 60:
                problems.append(path.name + ":" + str(index) + " 连续无标点 " + str(run) + " 字")
    return problems


def main() -> int:
    problems = check_docs()
    print("=" * 18, "文风自检（只看散文）")
    if not problems:
        print("  概括性与精确性平衡，未发现失衡项")
        return 0
    for item in problems[:40]:
        print("  x " + item)
    print("共 " + str(len(problems)) + " 处")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
