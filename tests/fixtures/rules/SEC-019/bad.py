"""反例：把服务绑定到 0.0.0.0（全部网卡）。

违反 SEC-019（OWASP NoSQL Security Cheat Sheet：Bind services to internal interfaces,
not 0.0.0.0）——绑全部网卡会把内部管理面暴露到所有可达网络。
"""

import socket

LISTEN_PORT = 8080


def serve():
    """启动一个监听全部网卡的 TCP 服务。"""

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", LISTEN_PORT))
    server.listen(5)
    return server
