"""SEC-009 反例：使用被原文标为 Vulnerable 的标准库 XML 解析器。"""
# 违反了 XML External Entity Prevention Cheat Sheet "## Python" 的
#   "The table below shows you which various XML parsing modules in Python 3 are
#    vulnerable to certain XXE attacks."
# 该表把 sax / etree / minidom / pulldom 在 "Billion Laughs" 与 "Quadratic Blowup"
# 两行全部标成 "Vulnerable"。
# 本规则必须命中的码：S313（cElementTree）、S314（ElementTree）、S315（expatreader）、
# S316（expatbuilder）、S317（sax）、S318（minidom）。
from xml.dom.expatbuilder import parseString
from xml.dom.minidom import parse
from xml.etree.cElementTree import parse as cet_parse
from xml.etree.ElementTree import parse as et_parse
from xml.sax import parse as sax_parse
from xml.sax.expatreader import create_parser

UNTRUSTED = "untrusted.xml"

cet_parse(UNTRUSTED)
et_parse(UNTRUSTED)
sax_parse(UNTRUSTED)
create_parser()
parseString("<a/>")
parse(UNTRUSTED)
