"""STYLE-011 反例：把 lambda 赋值给变量。"""

# 反例：PEP 8「Programming Recommendations」——"Always use a def statement instead of an
# assignment statement that binds a lambda expression directly to an identifier:"。

double = lambda x: 2 * x

print(double(2))
