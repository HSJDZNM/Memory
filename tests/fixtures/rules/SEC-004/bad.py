"""SEC-004 反例：把口令硬编码进源码，并给口令参数设默认值。"""
# 违反了 Cryptographic Storage Cheat Sheet "## Key Storage" 的
#   "Do not hard-code keys into the application source code.
#    Do not check keys into version control systems."
# 以及 Django REST Framework Cheat Sheet "### API7:2019 Security Misconfiguration" 的
#   "DO NOT use default passwords. ... NEVER hardcode secrets."
# 下面的值全是明显的合成占位值，不是任何真实凭据。
# 本规则必须命中的码：S105（硬编码口令字符串）、S106（口令作为函数实参）、
# S107（口令作为默认参数）。
import requests

DB_PASSWORD = "hunter2-placeholder"
URL = "https://example.invalid/login"


def login(password="hunter2-placeholder"):
    """用硬编码的默认口令登录。"""
    return requests.post(URL, data={"user": password}, timeout=5)


requests.post(URL, data={"user": "nobody"}, password="hunter2-placeholder", timeout=5)
