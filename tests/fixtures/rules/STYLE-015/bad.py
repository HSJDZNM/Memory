"""STYLE-015 反例：函数名含大写字母。"""

# 反例：PEP 8「Function and Variable Names」——"Function names should be lowercase, with words
# separated by underscores as necessary to improve readability."。


def CalculateTotal(items):
    """Return the total of items."""
    return sum(items)


print(CalculateTotal([1, 2]))
