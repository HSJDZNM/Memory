"""正例：用加密协议通信，不使用 telnet / ftp（SEC-021）。"""

import requests

REPORT_API = "https://reports.example.com/api/v1/reports/"
TIMEOUT_SECONDS = 5


def fetch_report(name, token):
    """通过 HTTPS 取报表。"""

    return requests.get(
        REPORT_API + name,
        headers={"Authorization": "Bearer " + token},
        timeout=TIMEOUT_SECONDS,
    )
