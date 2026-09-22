"""反例：导入了 json 却从未使用（违反 STYLE-002 / Ruff F401）。

注意：这一行刻意不写 "noqa" 注释——写了就会把 F401 抑制掉，夹具会变成假绿。
"""

import json


def describe() -> str:
    """返回一段固定文本，不触碰 json。"""

    return "json is not used anywhere in this module"
