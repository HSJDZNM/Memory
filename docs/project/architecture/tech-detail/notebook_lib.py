
# -*- coding: utf-8 -*-
"""tech-detail 讲解 notebook 的内容源公共词汇。

每章的 `cells.py`（一章一个目录）定义一份 `SPEC`：一份 notebook 的单元序列与生成期断言。
改内容改 `cells.py`；产物（同目录的 `<NN>-<名称>.ipynb` 与同名 `.py`）由
`build_notebooks.py` 重新生成：**规格是唯一真相源，产物不手改**。
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Tuple

# 一个单元：(cell_type, 文本)。cell_type 取 "markdown" 或 "code"。
Cell = Tuple[str, str]


def _dedent(text: str) -> str:
    """去掉三引号带来的整体缩进与首行空行。

    notebook 里的顶层语句一旦被缩进就是语法错误；markdown 的标题被缩进则不会渲染成标题。
    因此两种单元都要做「去掉首行空行 + 按公共缩进裁剪」，内部真实的分层缩进仍然保留。

    **边界（台账 notebook_lib.py:26，判定：潜在项、不修语义）**：textwrap.dedent 只裁
    **公共**前缀——「首行顶格、其余行缩进」时公共前缀是 0，于是**什么都不裁**
    （最小构造：第一行 x = 1 顶格、第二行缩进 4 格的 y = 2 → 原样返回；两行都缩进 4 格时才
    会裁掉那 4 格）。不在这里加「按首行缩进裁」之类的聪明规则：那种形态与**合法的嵌套缩进**
    （if True: 后面跟 4 格）在文本上不可区分，改了会把本来正确的单元裁坏。
    本仓库现状（实测）：10 章 141 个单元**全部**顶格写（公共缩进 0），这个函数对它们是恒等变换；
    真出现「整块缩进但首行浅」的单元时，代码单元会在生成期**真执行**时以 IndentationError 响，
    markdown 单元则会把那些行渲染成代码块——两种都不是静默的。
    """

    return textwrap.dedent(text.lstrip("\n"))


def markdown(text: str) -> Cell:
    """说明单元。"""

    return ("markdown", _dedent(text))


def code(text: str) -> Cell:
    """代码单元：生成期会真的执行它，任何异常都会让生成失败。"""

    return ("code", _dedent(text))


@dataclass(frozen=True)
class NotebookSpec:
    """一份讲解 notebook 的规格。"""

    #: 产物文件名（不带扩展名），与章节目录名逐字相同
    stem: str
    #: notebook 一级标题
    title: str
    #: 一句话说明（索引表用）
    summary: str
    #: 本 notebook 独占的临时目录（相对仓库根），必须落在 .tmp/tech-detail/ 下
    temp_dir: str
    #: 全部单元，顺序即 notebook 顺序（代码单元会被真的执行）
    cells: Tuple[Cell, ...]
    #: 生成期结构核对：拿到全部代码单元执行完的命名空间，返回问题列表
    structure: Optional[Callable[[dict], Sequence[str]]] = None
