# 反例：模块、类与顶层函数都没有 docstring —— 违反 PEP 257 / DOC-001。


class OrderCalculator:
    def total(self, amounts):
        return sum(amounts)


def describe(amounts):
    return "共 " + str(len(amounts)) + " 笔"
