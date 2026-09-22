"""STYLE-008 反例：not ... in / not ... is 写法。"""

# 反例：PEP 8「Programming Recommendations」——"Use `is not` operator rather than
# `not ... is`."，同节 # Wrong 例子即 "if not foo is None:"。


def first_match(item, items, sentinel):
    """Return the first usable value."""
    if not item in items:
        return None
    if not sentinel is None:
        return sentinel
    return item
