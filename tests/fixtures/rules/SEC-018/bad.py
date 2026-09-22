"""反例：在 except 分支里用 logging.error 记录异常，stack trace 丢失。

违反 SEC-018（OWASP Logging Cheat Sheet：Extended details e.g. stack trace, system error
messages, debug information）——logging.error 只写消息，事后无法还原出事点。
"""

import logging

logger = logging.getLogger(__name__)


def parse_amount(raw):
    """把字符串金额解析成整数；解析失败时记录异常。"""

    try:
        return int(raw)
    except ValueError:
        logger.error("amount is not a number")
        return 0
