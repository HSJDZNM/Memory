"""SEC-001 反例：把不可信输入当成代码执行。"""
# 违反了 Django REST Framework Cheat Sheet
# "### API8:2019 Injection -> #### RCE" 的
#   "DO NOT add user input to dangerous methods (`eval()`, `exec()` and `execfile()`)"
# 本规则必须命中的码：S307（eval）、S102（exec）。
untrusted = "1 + 1"

eval(untrusted)
exec(untrusted)
