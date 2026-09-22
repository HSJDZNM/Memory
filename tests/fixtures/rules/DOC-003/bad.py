"""DOC-003 反例：单行 docstring 的闭合三引号被折到下一行。"""

# 反例：PEP 257「One-line Docstrings」——"They should really fit on one line."，
# "The closing quotes are on the same line as the opening quotes. This looks better for
# one-liners."。


def summary_line():
    """Return the summary line.
    """
    return "summary"
