"""SEC-008 反例：用字符串格式化把用户输入拼进 SQL。"""
# 违反了 SQL Injection Prevention Cheat Sheet "## What Is a SQL Injection Attack?" 的
#   "Attackers can use SQL injection on an application if it has dynamic database queries
#    that use string concatenation and user-supplied input. To avoid SQL injection flaws,
#    developers need to:
#      1. Stop writing dynamic queries with string concatenation."
# 本规则必须命中的码：S608。
def find_user(cursor, name):
    """按用户名查库（拼接写法）。"""
    return cursor.execute("SELECT * FROM users WHERE name = '%s'" % name)
