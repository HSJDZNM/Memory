"""SEC-003 正例：安全用途使用 SHA-256 及以上强度的哈希。"""
# 同一条原文要求的正是 "should use SHA-256 ... rather than the older MD5 and SHA-1"。
import hashlib

from Crypto.Hash import SHA256


def digest(payload):
    """计算 SHA-256 摘要。"""
    return hashlib.sha256(payload).hexdigest()


print(digest(b"payload"), SHA256.new(b"payload").hexdigest())
