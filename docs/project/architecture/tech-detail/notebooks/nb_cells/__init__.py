
# -*- coding: utf-8 -*-
"""tech-detail 讲解 notebook 的内容源包。

每个 `nb<NN>.py` 定义一份 `SPEC`：一份 notebook 的单元序列与生成期断言。
改内容改这里；产物（`<NN>-<名称>.ipynb` 与同名 `.py`）由 `build_notebooks.py` 重新生成——
和同目录 `build.py` 生成的图一样：**规格是唯一真相源，产物不手改**。
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
    因此两种单元都要做"去掉首行空行 + 按公共缩进裁剪"，内部真实的分层缩进仍然保留。
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

    stem: str
    #: 产物文件名（不带扩展名），与同名 .drawio 完全一致
    title: str
    #: notebook 一级标题
    summary: str
    #: 一句话说明（索引表用）
    temp_dir: str
    #: 本 notebook 独占的临时目录（相对仓库根），必须落在 .tmp/tech-detail/ 下
    cells: Tuple[Cell, ...]
    #: 生成期结构核对：拿到全部代码单元执行完的命名空间，返回问题列表
    structure: Optional[Callable[[dict], Sequence[str]]] = None
