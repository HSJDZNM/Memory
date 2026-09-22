"""SEC-005 反例：主动关闭 TLS 证书校验。"""
# 违反了 Mobile Application Security Cheat Sheet
# "## Network Communication -> ### 2. Use Secure Protocols" 的
#   "Do not override SSL certificate validation to allow self-signed or invalid
#    certificates."
# verify=False 与 _create_unverified_context() 就是"覆盖掉证书校验"本身。
# 本规则必须命中的码：S501（requests 关校验）、S323（未校验的 SSL 上下文）。
import ssl

import requests

requests.get("https://example.invalid/report", verify=False, timeout=5)
print(ssl._create_unverified_context())
