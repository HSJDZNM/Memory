"""STYLE-017 反例：变量名大小写混排（mixedCase）。"""

# 反例：PEP 8「Function and Variable Names」——"Variable names follow the same convention as
# function names."，且 "mixedCase is allowed only in contexts where that's already the
# prevailing style (e.g. threading.py), to retain backwards compatibility."（新建代码不属于例外）
# 三个作用域各命中一次：N816 全局、N815 类作用域、N806 函数作用域。

mixedCase = 2


class Counter:
    """A counter."""

    maxCount = 1


def add():
    """Return the accumulated total."""
    totalCount = mixedCase + Counter.maxCount
    return totalCount


print(add())
