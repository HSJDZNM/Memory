"""正例：日志配置来自应用内部的静态配置，不开放远程改写（SEC-022）。"""

import logging.config

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}


def configure_logging():
    """应用启动时按内部配置装配日志。"""

    logging.config.dictConfig(LOGGING_CONFIG)
