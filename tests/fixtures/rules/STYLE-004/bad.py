"""STYLE-004 反例：模块级赋值之后才写 import。"""

# 反例：PEP 8「Imports」——"Imports are always put at the top of the file, just after any
# module comments and docstrings, and before module globals and constants."
VALUE = 1

import os

print(os.sep, VALUE)
