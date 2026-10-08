"""相对导入的点数就是层级：from .. import x 登记成 "..x"，不是 "...x"。"""

from __future__ import annotations

from adapters.textfacts import _from_targets


def test_relative_import_targets_keep_exactly_the_declared_level():
    """每多一层就多一个点——旧实现在 module 全是点时又补了一个点，于是整体多报一层。"""

    assert _from_targets(".", "repository") == (".repository",)
    assert _from_targets("..", "repository") == ("..repository",)
    assert _from_targets("...", "repository") == ("...repository",)
    # 反真空：非相对模块仍然是 "模块名" + "模块名.子模块" 两个候选。
    assert _from_targets("shop", "order_repository") == ("shop", "shop.order_repository")
