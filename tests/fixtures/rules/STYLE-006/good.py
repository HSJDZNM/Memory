"""STYLE-006 正例：与 None 用 is / is not 比较。"""

# 正例：PEP 8「Programming Recommendations」要求与 None 的比较 "done with `is` or `is not`"。


def is_missing(value):
    """Return whether value is missing."""
    if value is None:
        return True
    return False


def is_present(value):
    """Return whether value is present."""
    if value is not None:
        return True
    return False
