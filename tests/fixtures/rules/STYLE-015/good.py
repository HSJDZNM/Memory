"""STYLE-015 正例：函数名小写、必要时用下划线分词。"""

# 正例：PEP 8「Function and Variable Names」——lowercase, with words separated by underscores。


def calculate_total(items):
    """Return the total of items."""
    return sum(items)


print(calculate_total([1, 2]))
