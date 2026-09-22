"""正例：模块 / 类 / 顶层函数都有 docstring（PEP 257，DOC-001）。"""


class OrderCalculator:
    """订单金额计算器。"""

    def total(self, amounts: "list[int]") -> int:
        """返回金额合计。"""

        return sum(amounts)


def describe(amounts: "list[int]") -> str:
    """返回一段人类可读的描述。"""

    return "共 " + str(len(amounts)) + " 笔"
