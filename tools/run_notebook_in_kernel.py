"""在真实 Jupyter 内核里执行 notebook，逐单元报告耗时与错误（不需要 nbformat）。

用法：python tools/run_notebook_in_kernel.py docs/project/learning/phase-0/walkthrough.ipynb [超时秒数]

用途：flat 执行（生成器里的逐单元 exec）发现不了内核特有的问题，例如单元依赖执行顺序、
内核消息协议、magic 命令。这个脚本用真实内核跑一遍，并把每个单元的输出与耗时打印出来。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from jupyter_client.manager import start_new_kernel

REPO_ROOT = Path(__file__).resolve().parents[1]


def execute(client, code: str, timeout: float) -> tuple[str, list[str], bool]:
    """执行一个代码单元，返回 (状态, 输出行, 是否有错误)。"""

    message_id = client.execute(code)
    lines: list[str] = []
    failed = False
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            message = client.get_iopub_msg(timeout=1)
        except Exception:
            continue
        if message.get("parent_header", {}).get("msg_id") != message_id:
            continue
        kind = message["msg_type"]
        content = message["content"]
        if kind == "stream":
            lines.extend(content["text"].rstrip().splitlines())
        elif kind == "error":
            failed = True
            lines.append("!! " + content["ename"] + ": " + (content["evalue"] or ""))
        elif kind == "status" and content["execution_state"] == "idle":
            return "ok", lines, failed
    return "timeout", lines, True


def main(argv: list[str]) -> int:
    notebook_path = Path(argv[1] if len(argv) > 1 else "docs/project/learning/phase-0/walkthrough.ipynb")
    timeout = float(argv[2]) if len(argv) > 2 else 30.0
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))

    manager, client = start_new_kernel(kernel_name="python3")
    problems: list[str] = []
    try:
        for index, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] != "code":
                continue
            code = "".join(cell["source"])
            start = time.time()
            status, lines, failed = execute(client, code, timeout)
            elapsed = time.time() - start
            first = code.strip().splitlines()[0][:56]
            print(f"单元 {index:>2} [{status}] {elapsed:5.2f}s  {first}")
            if failed or status != "ok":
                problems.append(f"单元 {index} 失败（{status}）")
                for line in lines[-6:]:
                    print("      ", line)
    finally:
        manager.shutdown_kernel(now=True)

    print("内核执行:", "全部通过" if not problems else f"{len(problems)} 个失败")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
