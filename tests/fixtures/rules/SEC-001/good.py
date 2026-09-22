"""SEC-001 正例：只解析数据，不做动态代码执行。"""
# 原文 Injection Prevention Cheat Sheet "## Injection Prevention Rules":
#   "### Rule #2 (Use a safe API)"
#   "The preferred option is to use a safe API which avoids the use of the interpreter
#    entirely or provides a parameterized interface."
# ast.literal_eval 只接受字面量，不会执行代码。
import ast


def parse_payload(text):
    """解析配置文本，不执行其中的代码。"""
    return ast.literal_eval(text)


print(parse_payload("{'answer': 2}"))
