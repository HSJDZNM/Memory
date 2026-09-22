"""SEC-010 正例：请求由应用自己用固定字面量构造。"""
# 原文："**Match the host against an allowlist, and build the request yourself.**
#        ... together with a scheme, port and path the application fixes itself."
# S310 只在 urlopen 的参数不是字面量时命中，所以固定 URL 必须写成字面量。
import urllib.request


def fetch_status():
    """请求固定的状态端点。"""
    return urllib.request.urlopen("https://example.invalid/status")
