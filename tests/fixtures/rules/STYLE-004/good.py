"""STYLE-004 正例：import 位于模块注释与 docstring 之后、模块级常量之前。"""

# 正例：PEP 8「Imports」——import 永远放在文件顶部，先于模块级赋值。
import os

VALUE = 1

print(os.sep, VALUE)
