"""STYLE-018 反例：import 未按分组排序。"""

# 反例：PEP 8「Imports」——"Imports should be grouped in the following order: 1. Standard
# library imports. 2. Related third party imports. 3. Local application/library specific
# imports."，且 "You should put a blank line between each group of imports."

import sys
import os

print(sys.version, os.sep)
