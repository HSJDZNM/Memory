"""STYLE-012 正例：用有含义的变量名代替 l / I / O。"""

# 正例：PEP 8「Names to Avoid」要求不要用 l / I / O 作单字符变量名。

OFFSET = 3


def total(items):
    """Return the total length plus the offset."""
    length = len(items)
    return length + OFFSET
