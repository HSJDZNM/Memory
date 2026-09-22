"""SEC-006 正例：用 yaml.safe_load 解析不可信 YAML。"""
# safe_load 等价于 Loader=yaml.SafeLoader，只构造基本类型，不构造任意 Python 对象。
import yaml


def parse(document):
    """把 YAML 文本解析成基本类型。"""
    return yaml.safe_load(document)


print(parse("a: 1"))
