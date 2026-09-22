"""正例：用带名称的模块 logger 记录，日志里带得上模块归属（SEC-017）。"""

import logging

logger = logging.getLogger(__name__)


def record_login_failure(user_id):
    """记录一次登录失败。"""

    logger.warning("login failure for %s", user_id)
