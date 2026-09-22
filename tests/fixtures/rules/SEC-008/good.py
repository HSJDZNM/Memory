"""SEC-008 正例：参数化查询。"""
# 原文 "## Primary Defenses -> ### Defense Option 1: Prepared Statements (with
# Parameterized Queries)"：
#   "Prepared statements ensure that an attacker is not able to change the intent of a
#    query, even if SQL commands are inserted by an attacker."
# SQL 只以字面量出现，用户数据走参数元组。
def find_user(cursor, name):
    """按用户名查库（参数化写法）。"""
    return cursor.execute("SELECT * FROM users WHERE name = %s", (name,))
