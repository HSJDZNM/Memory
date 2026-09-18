"""动态 import：目标不是常量字符串，依赖集无法静态确定（必须失败关闭）。"""

import importlib


def load(name: str) -> object:
    """按名字加载模块（测试用：这个名字来自入参）。"""

    return importlib.import_module(name)
