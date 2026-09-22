"""STYLE-005 正例：显式导入需要的名字。"""

# 正例：PEP 8「Imports」要求显式导入，读者与自动化工具都能看清命名空间里有什么。
import os

print(os.getcwd())
