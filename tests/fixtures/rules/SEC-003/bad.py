"""SEC-003 反例：把有密码学弱点的哈希用在安全用途上。"""
# 违反了 Transport Layer Security Cheat Sheet
# "## Certificates -> ### Use Strong Cryptographic Hashing Algorithms" 的
#   "Certificates should use SHA-256 for the hashing algorithm, rather than the older MD5
#    and SHA-1 algorithms. These have a number of cryptographic weaknesses, and are not
#    trusted by modern browsers."
# 本规则必须命中的码：S324（hashlib 弱哈希）、S303（Crypto.Hash 弱哈希）。
import hashlib

from Crypto.Hash import MD5, SHA1

hashlib.md5(b"payload")
hashlib.sha1(b"payload")
MD5.new(b"payload")
SHA1.new(b"payload")
