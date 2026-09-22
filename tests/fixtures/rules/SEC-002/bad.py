"""SEC-002 反例：用语言原生的反序列化还原不可信字节流。"""
# 违反了 Deserialization Cheat Sheet "### Python -> #### Clear-box Review" 的
#   "The uses of `pickle/c_pickle/_pickle` with `load/loads`"
# 以及 Django REST Framework Cheat Sheet "#### RCE" 的
#   "DO NOT load user-controlled pickle files"
# 数据流因此可以决定要构造什么对象。
# 本规则必须命中的码：S301（pickle）、S302（marshal）。
import marshal
import pickle

untrusted = b""

pickle.loads(untrusted)
marshal.loads(untrusted)
