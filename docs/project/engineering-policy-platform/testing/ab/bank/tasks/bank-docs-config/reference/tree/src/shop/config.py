"""应用配置（v2）的严格加载器。

v2 的形状见 docs/config.md：顶层 app_name / retry_policy / feature_flags；
retry_policy 内 max_attempts / backoff_ms / jitter。任何不合约的输入都失败关闭
（ValueError），错误消息只用文件名，不出现绝对路径。
"""

from pathlib import Path

import yaml

TOP_LEVEL_KEYS = ("app_name", "retry_policy", "feature_flags")
RETRY_POLICY_KEYS = ("max_attempts", "backoff_ms", "jitter")
V1_RETRY_HINT = "v1 的 retry 已改名：v2 用 retry_policy（见 docs/config-migration.md）"


def load_config(path: Path) -> dict:
    """读取并校验一个 v2 配置，返回规范化的新 dict；任何不合约都抛 ValueError。"""
    data = _parse_yaml(_read_text(path), path)
    return _validate_top_level(data, path)


def _read_text(path: Path) -> str:
    """按 UTF-8 读配置文本；读不到（不存在 / 是目录 / 权限）时转成 ValueError。"""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError("无法读取配置文件 " + path.name) from exc


def _parse_yaml(text: str, path: Path) -> object:
    """用 yaml.safe_load 解析（不构造任意对象）；语法错误转成 ValueError。"""
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError("配置文件 " + path.name + " 不是合法 YAML") from exc


def _validate_top_level(data: object, path: Path) -> dict:
    """校验顶层是映射、键集合恰为 v2 的三个键，返回新 dict。"""
    if not isinstance(data, dict):
        raise ValueError("配置文件 " + path.name + " 的顶层必须是映射")
    if "retry" in data:
        raise ValueError("配置文件 " + path.name + " 用了 v1 的 retry 键；" + V1_RETRY_HINT)
    unknown = sorted(set(data) - set(TOP_LEVEL_KEYS))
    if unknown:
        raise ValueError("配置文件 " + path.name + " 含未知顶层键：" + ", ".join(unknown))
    missing = [key for key in TOP_LEVEL_KEYS if key not in data]
    if missing:
        raise ValueError("配置文件 " + path.name + " 缺顶层键：" + ", ".join(missing))
    return {
        "app_name": _validate_app_name(data["app_name"], path),
        "retry_policy": _validate_retry_policy(data["retry_policy"], path),
        "feature_flags": _validate_feature_flags(data["feature_flags"], path),
    }


def _validate_app_name(value: object, path: Path) -> str:
    """校验 app_name：非空字符串。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("配置文件 " + path.name + " 的 app_name 必须是非空字符串")
    return value


def _validate_retry_policy(value: object, path: Path) -> dict:
    """校验 retry_policy：映射且子键集合恰为 v2 的三个子键，返回新 dict。"""
    if not isinstance(value, dict):
        raise ValueError("配置文件 " + path.name + " 的 retry_policy 必须是映射")
    unknown = sorted(set(value) - set(RETRY_POLICY_KEYS))
    if unknown:
        raise ValueError(
            "配置文件 " + path.name + " 的 retry_policy 含未知键：" + ", ".join(unknown)
        )
    missing = [key for key in RETRY_POLICY_KEYS if key not in value]
    if missing:
        raise ValueError(
            "配置文件 " + path.name + " 的 retry_policy 缺键：" + ", ".join(missing)
        )
    return {
        "max_attempts": _validate_integer(value["max_attempts"], path, "max_attempts", 1),
        "backoff_ms": _validate_integer(value["backoff_ms"], path, "backoff_ms", 0),
        "jitter": _validate_boolean(value["jitter"], path),
    }


def _validate_integer(value: object, path: Path, name: str, minimum: int) -> int:
    """校验整数字段：bool 不算 int（isinstance(True, int) 为真），且不得小于 minimum。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("配置文件 " + path.name + " 的 " + name + " 必须是整数")
    if value < minimum:
        raise ValueError("配置文件 " + path.name + " 的 " + name + " 必须 >= " + str(minimum))
    return value


def _validate_boolean(value: object, path: Path) -> bool:
    """校验布尔字段：整数 1 / 0 不算 bool。"""
    if not isinstance(value, bool):
        raise ValueError("配置文件 " + path.name + " 的 jitter 必须是布尔值")
    return value


def _validate_feature_flags(value: object, path: Path) -> list:
    """校验 feature_flags：列表且元素都是非空字符串；返回新列表。"""
    if not isinstance(value, list):
        raise ValueError("配置文件 " + path.name + " 的 feature_flags 必须是列表")
    flags = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                "配置文件 " + path.name + " 的 feature_flags 元素必须是非空字符串"
            )
        flags.append(item)
    return flags
