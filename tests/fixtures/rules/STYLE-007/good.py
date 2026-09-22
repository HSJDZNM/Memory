"""STYLE-007 正例：直接判断布尔值本身。"""

# 正例：PEP 8「Programming Recommendations」——同节 # Correct 例子是 "if greeting:"。


def describe(flag):
    """Return a label for flag."""
    if flag:
        return "on"
    return "off"
