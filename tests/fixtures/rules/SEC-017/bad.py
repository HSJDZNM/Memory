"""反例：直接调用根 logger。

违反 SEC-017（OWASP Logging Cheat Sheet：日志必须记录 when/where/who/what，其中 where
包含 Code location e.g. script name, module name）——根 logger 的记录里没有模块归属。
"""

import logging


def record_login_failure(user_id):
    """记录一次登录失败（走的是根 logger）。"""

    logging.warning("login failure for %s", user_id)
