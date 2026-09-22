"""SEC-006 反例：用 yaml.load 解析不可信 YAML。"""
# 违反了 Django REST Framework Cheat Sheet "#### RCE" 的
#   "use the `Loader=yaml.SafeLoader` for YAML files. DO NOT load user-controlled YAML
#    files using the method `load()`."
# 以及 Deserialization Cheat Sheet "### Python -> #### Clear-box Review" 第 2 条
#   "Uses of `PyYAML` with `load`"（示例载荷是
#    "!!python/object/apply:os.system ['ipconfig']"）。
# 本规则必须命中的码：S506。
import yaml

untrusted = "a: 1"

print(yaml.load(untrusted))
