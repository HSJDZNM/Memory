"""正例：每个外部请求都显式设置了超时（SEC-014）。"""

import requests

PROFILE_API = "https://profiles.example.com/api/v1/users/"
TIMEOUT_SECONDS = (3, 5)


def fetch_profile(user_id):
    """按用户 ID 读取画像，并设置连接/读取超时。"""

    return requests.get(PROFILE_API + user_id, timeout=TIMEOUT_SECONDS)
