"""STYLE-011 正例：用 def 语句定义函数。"""

# 正例：PEP 8「Programming Recommendations」——def 让函数名进入 traceback，而不是 <lambda>。


def double(x):
    """Return twice x."""
    return 2 * x


print(double(2))
