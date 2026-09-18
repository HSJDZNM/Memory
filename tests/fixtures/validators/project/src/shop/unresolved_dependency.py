"""无法解析的项目内依赖：顶层包 shop 存在，但没有这个模块。"""

from shop.missing_repository import MissingRepository


def build() -> object:
    """返回一个不存在的依赖类型（测试用）。"""

    return MissingRepository
