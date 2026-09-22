"""STYLE-016 反例：参数名含大写字母。"""

# 反例：PEP 8「Function and Variable Names」——"Variable names follow the same convention as
# function names."，参数属于变量，因此同样是小写 + 下划线。


def scale(ScaleFactor, value):
    """Return value scaled by ScaleFactor."""
    return value * ScaleFactor


print(scale(2, 3))
