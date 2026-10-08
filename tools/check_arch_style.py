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
    # 路径形态只认 ASCII 路径字符：`\w` 含 CJK，旧写法 `[\w-]+/[\w./-]+` 让"并且/或者"
    # "对/错"这类普通散文也算"精确锚点"，于是这条判据几乎永不触发（信号价值为零）。
    + r"|[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+"
    + r"|allow_with_warnings|needs_human|uncovered_checker|action_hash)"
)
FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,})")
SENTENCE = re.compile(r"[^。；！？\n]+[。；！？]?")

def prose_lines(text: str):
    """返回 (行号, 内容) 的散文行：跳过围栏代码与表格行。

    围栏状态按**开启时的标记**跟踪：只有同字符、且不短于开启标记的围栏才算关闭。
    旧实现"任何围栏行都翻转"——`~~~` 块里出现一个 ``` 就把块内正文当成代码、把块外代码当成
    正文继续算，既可能假红也可能**假绿**（门禁最怕后者）。
    """

    inside = None  # 开启中的围栏标记（字符 + 重复长度）
    for index, line in enumerate(text.splitlines(), 1):
        match = FENCE_OPEN.match(line)
        if match:
            marker = match.group(1)
            if inside is None:
                inside = marker
            elif marker[0] == inside[0] and len(marker) >= len(inside):
                inside = None
            continue
        if inside is not None:
            continue
        stripped = line.strip()
        if stripped.startswith("|") or stripped.startswith("<"):
            continue
        yield index, line


def prose_paragraphs(text: str):
    """只产出**段落散文**行：在 prose_lines 之上再排除标题、引用、列表行。

    为什么要再排除这三类：它们通常不以句末标点结尾，拼进长句统计会与下一行合成"人造长句"，
    把 >90 字比例推过阈值——那是版式，不是散文质量（实测：三个长标题 + 三句短句能凑出 100%）。
    """

    for _number, line in prose_lines(text):
        if line.strip().startswith(("#", ">", "-", "*", "|", "<")):
            continue
        yield line


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
    """每个 H2 小节的第一段散文（跳过表格、围栏、标题、引用块与列表行）。

    **段落开始之后**再遇到列表/引用行就是分界：旧实现照样 `continue`，于是把分界线两侧的行
    用空格接成一句（概括句长度因此虚高），而 `- **术语**：…` 这种列表开头还会让紧随其后的
    正文被当成"本节第一段"。
    """

    collected, started = [], False
    for line in body:
        stripped = line.strip()
        if not stripped:
            if started:
                break
            continue
        if stripped.startswith(("#", "---")):
            continue
        if stripped.startswith((">", "-", "*")):
            if started:
                break
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
            # 段落首字符本身是句末标点（`。；！？`）时 `SENTENCE.match()` 返回 None：
            # 旧写法直接 `.group(0)`，畸形一行就能让整轮检查以 AttributeError 收场。
            # 拿不到"第一句"就退回整段原文——宁可量得保守，也不能让检查崩掉。
            matched = SENTENCE.match(paragraph)
            first = (matched.group(0) if matched else paragraph).strip()
            if len(first) > 45:
                problems.append(path.name + " §" + title[:18] + " 概括句过长（" + str(len(first)) + " 字）：" + first[:34] + "…")
            if not ANCHOR.search(" ".join(body)):
                problems.append(path.name + " §" + title[:18] + " 没有精确锚点（文件:行 / 标识符 / 路径 / 枚举）")
        prose = " ".join(prose_paragraphs(text))
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
