"""SEC-004 正例：凭据只从环境变量读取，源码里不留明文。"""
# 原文 Cryptographic Storage Cheat Sheet "## Key Storage":
#   "Do not hard-code keys into the application source code."
# 凭据来自环境变量 / secrets manager，口令参数也不设默认值。
import os

import requests

DB_PASSWORD = os.environ["DB_PASSWORD"]
URL = "https://example.invalid/login"


def login(password):
    """用调用方传入的口令登录。"""
    return requests.post(URL, data={"user": password}, timeout=5)


login(DB_PASSWORD)
