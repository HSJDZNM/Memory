"""STYLE-010 正例：捕获具体异常类型。"""

# 正例：PEP 8「Programming Recommendations」——写明要捕获的异常，而不是 bare except。


def read_value(source):
    """Return the value produced by source."""
    try:
        return source()
    except OSError:
        return None
