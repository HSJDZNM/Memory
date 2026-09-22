"""DOC-002 反例：摘要行与正文之间没有空行。"""

# 反例：PEP 257「Multi-line Docstrings」——"Multi-line docstrings consist of a summary line just
# like a one-line docstring, followed by a blank line, followed by a more elaborate
# description."，"it is important that it ... is separated from the rest of the docstring by a
# blank line."。


def summary_line():
    """Return the summary line.
    The rest of the docstring starts here without a blank line."""
    return "summary"
