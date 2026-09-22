"""STYLE-003 反例：一行导入多个模块。

本行还会触发 I001（isort 要求拆成两行），那条诊断归属 STYLE-018，不在本规则口径内。
"""

# 反例：PEP 8「Imports」的 # Wrong 例子——"import sys, os"。
import os, sys

print(os.sep, sys.version)
