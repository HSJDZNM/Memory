"""STYLE-007 反例：把布尔值与 True / False 用 == 比较。"""

# 反例：PEP 8「Programming Recommendations」——"Don't compare boolean values to True or False
# using `==`:"，同节 # Wrong 例子即 "if greeting == True:"。


def describe(flag):
    """Return a label for flag."""
    if flag == True:
        return "on"
    if flag == False:
        return "off"
    return "unknown"
