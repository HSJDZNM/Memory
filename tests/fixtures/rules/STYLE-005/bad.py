"""STYLE-005 反例：通配符导入。"""

# 反例：PEP 8「Imports」——"Wildcard imports (`from <module> import *`) should be avoided, as
# they make it unclear which names are present in the namespace, confusing both readers and
# many automated tools."
from os import *

# F405：getcwd 可能来自通配符导入，也可能是未定义——这正是原文说的"命名空间里有什么说不清"。
print(getcwd())
