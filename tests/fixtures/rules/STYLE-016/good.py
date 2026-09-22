"""STYLE-016 正例：参数名小写、必要时用下划线分词。"""

# 正例：PEP 8「Function and Variable Names」+「Function and Method Arguments」（首参 self / cls，
# 与保留字冲突时加单个尾下划线，如 class_）。


def scale(scale_factor, value):
    """Return value scaled by scale_factor."""
    return value * scale_factor


print(scale(2, 3))
