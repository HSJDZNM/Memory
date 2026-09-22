"""反例：调用外部服务时没有设置超时。

违反 SEC-014（OWASP DoS Cheat Sheet：Define an absolute connection timeout）——缺超时的请求
会一直占住连接与工作线程，一个慢响应就能把服务拖住。
"""

import requests

PROFILE_API = "https://profiles.example.com/api/v1/users/"


def fetch_profile(user_id):
    """按用户 ID 读取画像（这里刻意不传 timeout）。"""

    return requests.get(PROFILE_API + user_id)


def push_event(payload):
    """上报一条事件（这里刻意不传 timeout）。"""

    return requests.post(PROFILE_API + "events", json=payload)
