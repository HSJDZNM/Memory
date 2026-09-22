"""正例：导入的 json 真的被用到了（STYLE-002 / Ruff F401）。"""

import json


def describe() -> str:
    """返回 json 序列化后的文本。"""

    return json.dumps({"ok": True})
