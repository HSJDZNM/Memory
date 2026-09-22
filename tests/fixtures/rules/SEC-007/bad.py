"""SEC-007 反例：shell=True / os.system / 通配符命令。"""
# 违反了 OS Command Injection Defense Cheat Sheet
# "## Primary Defenses -> ### Defense Option 1: Avoid calling OS commands directly" 的
#   "The primary defense is to avoid calling OS commands directly."
# 以及 "## Code examples -> ### Java -> _Incorrect usage:_" 的
#   "the command together with the arguments are passed as a one string, making it easy to
#    manipulate that expression and inject malicious strings."
# 同文档 "### PHP" 结尾还写着 "**Hardcode the command** : never allow the user to choose
# which executable to run."
# 本规则必须命中的码：S602（shell=True）、S605（os.system）、S607（只写命令名）、
# S609（命令里带通配符 —— 通配符注入）。
import os
import subprocess

subprocess.Popen("rm -rf /tmp/owasp-injection-demo", shell=True)
subprocess.run(["chmod", "777", "*.py"], shell=True, check=False)
os.system("ls -l")
