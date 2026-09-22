"""STYLE-009 反例：用 type() 相等比较判断类型。"""

# 反例：PEP 8「Programming Recommendations」——"Object type comparisons should always use
# isinstance() instead of comparing types directly:"。


def same_kind(left, right):
    """Return whether left and right share a type."""
    if type(left) == type(right):
        return True
    return False
