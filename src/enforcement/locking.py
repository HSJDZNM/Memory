"""跨进程互斥：把"读-判-写"圈成一次原子操作。

Windows 用 msvcrt 的字节锁，POSIX 用 flock(LOCK_NB) + 自己的截止时间。**锁的是独立的
`.lock` 文件，不是数据文件本身**：Windows 上给数据文件加字节锁会让同一进程里的
`read_text()` 直接吃 PermissionError（Phase 6 台账与 Phase 7 幂等台账都踩过，
见 `adapters.runtime._process_file_lock` 与 `policy_api.idempotency._file_lock`）。

本模块是 enforcement 内部**唯一一份**实现：审计追加与限流判定各要一把锁，再复制第三份
只会让"对没拿到的区间解锁"这类坑多出两个复现点。抢不到锁一律抛 LockError，
由调用方翻译成自己模块的错误类型——失败关闭，绝不在没锁的情况下继续写。
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "LockError",
    "file_lock",
]

#: 抢不到锁时的等待上限；超时即失败关闭（不写、不判定）。
DEFAULT_LOCK_TIMEOUT_SECONDS = 5.0


class LockError(RuntimeError):
    """锁文件不可用或抢不到锁。调用方必须把它翻译成自己模块的错误（失败关闭）。"""


@contextmanager
def file_lock(
    lock_path: Path, *, timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS
) -> Iterator[None]:
    """在 `lock_path` 上取跨进程互斥；拿不到就抛 LockError。"""

    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+b")
        if handle.seek(0, 2) == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
    except OSError as error:
        raise LockError(f"锁文件不可用: {lock_path.name}（{error}）") from error

    held = False
    try:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    # 非阻塞抢锁 + 自己的截止时间：POSIX 的 LOCK_EX 会一直等下去，
                    # 那会把"别人卡住"变成这里卡住（失败关闭要先能失败）。
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if time.monotonic() >= deadline:
                    raise LockError(
                        f"取锁超时: {lock_path.name}（有另一个写入方持锁）"
                    ) from error
                time.sleep(0.01)
        held = True
        yield
    finally:
        try:
            if held:
                # 只解自己真的拿到的锁：对未持有的区间解锁会从 finally 抛 PermissionError，
                # 把在途的"取锁超时"这个真正的原因替换掉。
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
