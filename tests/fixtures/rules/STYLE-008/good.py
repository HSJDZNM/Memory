"""STYLE-008 正例：写成 not in / is not。"""

# 正例：PEP 8「Programming Recommendations」——同节 # Correct 例子即 "if foo is not None:"。


def first_match(item, items, sentinel):
    """Return the first usable value."""
    if item not in items:
        return None
    if sentinel is not None:
        return sentinel
    return item
