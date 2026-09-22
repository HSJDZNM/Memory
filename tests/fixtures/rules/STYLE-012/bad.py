"""STYLE-012 反例：l / I / O 这类单字符变量名。"""

# 反例：PEP 8「Names to Avoid」——"Never use the characters 'l' (lowercase letter el),
# 'O' (uppercase letter oh), or 'I' (uppercase letter eye) as single character variable names."
# 在多数等宽字体里它们与数字 1 / 0 难以区分。

I = 2
O = 3


def total(items):
    """Return the total length plus I and O."""
    l = len(items)
    return l + I + O
