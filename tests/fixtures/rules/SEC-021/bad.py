"""反例：用明文协议 telnet / ftp 通信。

违反 SEC-021（OWASP Secure Product Design Cheat Sheet：Always use Secure Communications
— Use secure protocols for communication, such as HTTPS, to protect against eavesdropping
and tampering）——telnet 与 ftp 把凭据和内容明文放在线路上。
"""

import ftplib
import telnetlib


def fetch_report(host):
    """从 FTP 服务器取报表（明文传输）。"""

    client = ftplib.FTP(host)
    client.login()
    return client


def open_admin_console(host, port):
    """连接管理口（telnet，明文传输）。"""

    return telnetlib.Telnet(host, port)
