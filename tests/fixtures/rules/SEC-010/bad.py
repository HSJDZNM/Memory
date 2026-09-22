"""SEC-010 反例：把用户给的整串 URL 直接交给 urlopen。"""
# 违反了 Server-Side Request Forgery Prevention Cheat Sheet
# "##### Application layer -> ###### URL"（Case 1）的
#   "Do not accept complete URLs from the user because URL are difficult to validate and
#    the parser can be abused depending on the technology used"
#   "**Match the host against an allowlist, and build the request yourself.**"
# 没有 allowlist，也没有重新拼装请求。
# 本规则必须命中的码：S310。
import urllib.request


def fetch(user_supplied_url):
    """按用户给的 URL 发起请求（dangerous）。"""
    return urllib.request.urlopen(user_supplied_url)
