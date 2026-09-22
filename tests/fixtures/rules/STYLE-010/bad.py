"""STYLE-010 反例：裸 except。"""

# 反例：PEP 8「Programming Recommendations」——"When catching exceptions, mention specific
# exceptions whenever possible instead of using a bare `except:` clause:"。
# 裸 except 连 SystemExit 与 KeyboardInterrupt 一起吞，程序变得难以中断。


def read_value(source):
    """Return the value produced by source."""
    try:
        return source()
    except:
        return None
