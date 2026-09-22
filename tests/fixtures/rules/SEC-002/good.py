"""SEC-002 正例：只接受纯数据格式。"""
# 原文 Deserialization Cheat Sheet "## Language-Agnostic Methods for Deserializing Safely"
# -> "### Using Alternative Data Formats":
#   "A great reduction of risk is achieved by avoiding native (de)serialization formats.
#    By switching to a pure data format like JSON or XML, you lessen the chance of custom
#    deserialization logic being repurposed towards malicious ends."
import json


def parse(text):
    """把 JSON 文本还原成基本类型。"""
    return json.loads(text)


print(parse('{"answer": 2}'))
