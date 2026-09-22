"""STYLE-006 反例：与 None 用 == / != 比较。"""

# 反例：PEP 8「Programming Recommendations」——"Comparisons to singletons like None should
# always be done with `is` or `is not`, never the equality operators."


def is_missing(value):
    """Return whether value is missing."""
    if value == None:
        return True
    return False


def is_present(value):
    """Return whether value is present."""
    if value != None:
        return True
    return False
