"""SEC-011 反例：用非密码学随机数生成会话 ID。"""
# 违反了 Cryptographic Storage Cheat Sheet
# "## Algorithms -> ### Secure Random Number Generation" 的
#   "Random numbers (or strings) are needed for various security critical functionality,
#    such as generating encryption keys, IVs, session IDs, CSRF tokens or password reset
#    tokens."
#   "they **must not** be used for anything security critical, as it is often possible for
#    attackers to guess or predict the output."
# 同节表格点出 Python 的 Unsafe Functions 是 random()，安全函数是 secrets()。
# 本规则必须命中的码：S311。
import random


def new_session_id():
    """生成会话 ID（可预测，dangerous）。"""
    return "sid-%016x" % int(random.random() * (2**64))
