# 反例：单行超过 100 列（违反 STYLE-001 / Ruff E501，行长上限在 validation/ruff.toml 里）。
"""风格反例：这一行本身是合规的模块 docstring。"""


def describe() -> str:
    """返回一段刻意超过 100 列的描述，用来触发 E501。"""

    return "this single line is intentionally long so that the configured line-length limit is exceeded by ruff"
