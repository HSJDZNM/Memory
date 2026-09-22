"""正例：在 except 分支里用 logging.exception，记录里带上 stack trace（SEC-018）。"""

import logging

logger = logging.getLogger(__name__)


def parse_amount(raw):
    """把字符串金额解析成整数；解析失败时连同堆栈一起记录。"""

    try:
        return int(raw)
    except ValueError:
        logger.exception("amount is not a number")
        return 0
