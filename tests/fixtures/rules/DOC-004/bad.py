"""DOC-004 反例：摘要用描述语气而不是祈使语气。"""

# 反例：PEP 257「One-line Docstrings」——"It prescribes the function or method's effect as a
# command ("Do this", "Return that"), not as a description; e.g. don't write
# "Returns the pathname ..."."。
# 模块 docstring 以中文开头，D401 的英文动词形态判断不适用于它。


def kos_root():
    """Returns the pathname of the KOS root directory."""
    return "/"
