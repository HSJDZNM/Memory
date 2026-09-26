"""只有未归属码（F841）的样本：Ruff 能分析这个文件，但它的诊断不归任何项目规则。"""


def keeps_an_unused_local() -> int:
    """返回 2，同时留一个赋值后从未使用的局部变量（触发 F841）。"""

    unused = 1
    return 2
