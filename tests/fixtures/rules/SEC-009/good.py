"""SEC-009 正例：改用 defusedxml。"""
# 原文 "## Python"：
#   "To protect your application from the applicable attacks, the defusedxml package
#    exists to help you sanitize your input and protect your application against DDoS and
#    remote attacks."
from defusedxml.ElementTree import parse


def load(path):
    """用安全的解析器读取 XML。"""
    return parse(path)


load("trusted.xml")
