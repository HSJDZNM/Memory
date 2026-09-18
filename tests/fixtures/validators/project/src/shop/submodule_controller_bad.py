"""反例：from <pkg> import <submodule> 形态，ARCH-001 必须命中。

这是"Controller 直接依赖 Repository"的另一种常见写法：被导入的是子模块，
依赖边必须落在 src/shop/order_repository.py 上（组件 repository），
而不是停在包名 shop 上。
"""

from shop import order_repository


def build() -> object:
    """返回数据访问层实例（反例）。"""

    return order_repository.OrderRepository()
