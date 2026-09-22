"""STYLE-009 正例：类型判断用 isinstance()。"""

# 正例：PEP 8「Programming Recommendations」——同节 # Correct 例子即 "if isinstance(obj, int):"。


def is_integer(value):
    """Return whether value is an integer."""
    if isinstance(value, int):
        return True
    return False
