"""反例：开启 logging.config.listen，任何人都能在运行时改写日志配置。

违反 SEC-022（OWASP Logging Cheat Sheet：Alterations to the level/extent of logging must
be intrinsic to the application or follow change management processes）——监听 socket 既不
是应用内在的，也没有走变更管理，还能把合规日志整个关掉。
"""

import logging.config

CONFIG_PORT = 9999


def start_config_listener():
    """在端口上监听远程下发的日志配置。"""

    listener = logging.config.listen(CONFIG_PORT)
    listener.start()
    return listener
