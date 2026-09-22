"""正例：只绑定回环接口，服务不暴露在全部网卡上（SEC-019）。"""

import socket

LISTEN_PORT = 8080
BIND_ADDRESS = "127.0.0.1"


def serve():
    """启动一个只监听回环地址的 TCP 服务。"""

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((BIND_ADDRESS, LISTEN_PORT))
    server.listen(5)
    return server
