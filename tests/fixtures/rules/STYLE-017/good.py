"""STYLE-017 正例：变量名小写、必要时用下划线分词。"""

# 正例：PEP 8「Function and Variable Names」——变量沿用函数命名约定（lowercase + underscores）。

mixed_case = 2


class Counter:
    """A counter."""

    max_count = 1


def add():
    """Return the accumulated total."""
    total_count = mixed_case + Counter.max_count
    return total_count


print(add())
