"""SEC-011 正例：安全用途改用 CSPRNG。"""
# 原文表格里 Python 对应的 Cryptographically Secure Functions 是 secrets()。
import secrets


def new_session_id():
    """用 CSPRNG 生成会话 ID。"""
    return "sid-" + secrets.token_hex(16)
