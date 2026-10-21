"""通知工作队列的冒烟脚本：提交 3 条（含 1 条重复 key），打印去重后的记录。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from shop.notify_model import Notification  # noqa: E402
from shop.notify_worker import NotificationWorker  # noqa: E402


async def _run() -> list[dict]:
    """启动 worker、提交 3 条（第 3 条与第 1 条同 key），停机后返回处理记录。"""
    worker = NotificationWorker()
    await worker.start()
    await worker.submit(Notification("smoke-1", 1, "email"))
    await worker.submit(Notification("smoke-2", 2, "sms"))
    await worker.submit(Notification("smoke-1", 3, "email"))
    await worker.stop()
    return worker.processed()


def main() -> list[dict]:
    """跑一次确定性队列，返回去重后的 2 条处理记录。"""
    return asyncio.run(_run())


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, sort_keys=True))
