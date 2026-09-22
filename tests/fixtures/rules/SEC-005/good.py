"""SEC-005 正例：保留证书校验。"""
# 原文 "Do not override SSL certificate validation"；这里既用默认校验，也显式建受校验的上下文。
import ssl

import requests


def fetch():
    """用默认（开启校验的）TLS 拉取报告。"""
    return requests.get("https://example.invalid/report", verify=True, timeout=5)


print(fetch(), ssl.create_default_context())
