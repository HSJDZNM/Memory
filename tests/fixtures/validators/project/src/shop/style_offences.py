"""风格反例：超长行（E501）与未使用导入（F401），由 Ruff 检出。"""

import json
from shop.order_repository import OrderRepository


def describe() -> str:
    """返回一段刻意超过 100 列的描述，用来触发 Ruff 的 E501 诊断（行长上限在 validation/ruff.toml 里）。"""

    return "this line is intentionally long so that the configured line-length limit is exceeded by ruff"
