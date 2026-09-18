"""墙钟预算：**执行**不是"等"。

Phase 2 的 Hook 用的是"内部预算小于 Agent 侧超时"，这里把它搬到服务端，并明确一件事：

- 预算到点后要么拿到结论，要么拿到 `*_timeout`（HTTP 504 / 503），**没有第三种结果**。
  没有"降级成 allow"的分支——失败关闭在服务端和在 Hook 里是同一条纪律；
- 线程仍会把工作跑完（Python 没有可移植的线程取消），因此"超时"语义是
  **调用方不再等待** + 结果被丢弃 + 观测里记 `outcome=timeout`。这一点写在这里，
  是因为把"超时"说成"已经停止工作"是不诚实的；
- 计时用 `time.monotonic`（受时钟回拨影响的是 datetime，不是 monotonic）。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Generic, Optional, TypeVar

__all__ = ["Budget", "BudgetExceeded", "Elapsed", "run_with_budget"]

T = TypeVar("T")


class BudgetExceeded(Exception):
    """预算耗尽：调用方必须把它翻译成显式错误，不允许回退成默认结论。"""


@dataclass(frozen=True)
class Budget:
    """毫秒预算。`total_ms` 是本次请求的上限，`used_ms` 是已经花掉的部分。"""

    total_ms: int
    used_ms: int = 0

    def __post_init__(self) -> None:
        if self.total_ms <= 0:
            raise ValueError("预算必须是正数毫秒")

    @property
    def remaining_ms(self) -> int:
        return max(0, self.total_ms - self.used_ms)

    def spend(self, elapsed_ms: int) -> "Budget":
        return Budget(total_ms=self.total_ms, used_ms=self.used_ms + max(0, elapsed_ms))

    def require(self, *, stage: str) -> None:
        if self.remaining_ms <= 0:
            raise BudgetExceeded(f"请求预算已耗尽（{stage}）")


@dataclass(frozen=True)
class Elapsed:
    milliseconds: float
    timed_out: bool


def run_with_budget(
    operation: Callable[[], T],
    *,
    budget_ms: int,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[Optional[T], Elapsed]:
    """在预算内运行 operation。

    返回 `(结果, 计时)`；超时时结果为 None 且 `timed_out=True`。
    抛出的异常由调用方处理（本函数只负责预算，不做任何结论）。
    """

    if budget_ms <= 0:
        raise ValueError("budget_ms 必须是正数")
    started = clock()
    box: dict[str, object] = {}

    def target() -> None:
        try:
            box["value"] = operation()
        except BaseException as error:  # noqa: BLE001 - 异常原样交给调用方
            box["error"] = error

    worker = threading.Thread(target=target, name="policy-api-budget", daemon=True)
    worker.start()
    worker.join(budget_ms / 1000.0)
    elapsed = Elapsed(milliseconds=(clock() - started) * 1000.0, timed_out=worker.is_alive())
    if elapsed.timed_out:
        return None, elapsed
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box.get("value"), elapsed  # type: ignore[return-value]
