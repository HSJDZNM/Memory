# -*- coding: utf-8 -*-
"""OWASP 代码安全指南库流水线入口。

用法:
    python tools/owasp_cheatsheets/pipeline.py all      # 依次运行全部阶段
    python tools/owasp_cheatsheets/pipeline.py 03       # 只运行 03_build.py
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STAGES = ["01_analyze.py", "02_fetch.py", "03_build.py", "04_index.py", "05_verify.py"]

#: 单个阶段的墙钟上限（秒）：某个阶段挂起（例如 02_fetch 在网络上等、或交互式提示等输入）
#: 时不许把整条流水线永远钉死。可用 OWASP_PIPELINE_STAGE_TIMEOUT_S 显式覆盖。
STAGE_TIMEOUT_S = float(os.environ.get("OWASP_PIPELINE_STAGE_TIMEOUT_S", "1800"))


def main():
    argv = sys.argv[1:]
    flags = [item for item in argv if item.startswith("-")]
    args = [item for item in argv if not item.startswith("-")]
    if not args and flags:
        # 只给了开关就不再当成"没给参数"：`pipeline.py --help` 或者手滑敲成 `--dry-run`，
        # 旧行为是把开关一丢、直接跑完整条流水线（包含真实网络抓取）——那是静默的。
        print("本工具没有开关（收到：" + " ".join(flags) + "）")
        print("用法: python pipeline.py [all|01|02|03|04|05]")
        return 2
    if not args or args[0] == "all":
        todo = STAGES
    else:
        todo = [s for s in STAGES if s.startswith(args[0])]
        # **唯一匹配**才算指定了一个阶段：`0`（或空串）会一次匹配全部五个，
        # 手滑成 `0` 就静默跑完整条流水线；将来多一个同前缀阶段也会被悄悄带上。
        if len(todo) != 1:
            print("未知或有歧义的阶段: " + repr(args[0]) + "（匹配到 " + str(len(todo)) + " 个阶段）")
            print("可用: all, " + ", ".join(s[:2] for s in STAGES))
            return 2
    for s in todo:
        print("")
        print("=" * 64)
        print(">>> " + s)
        print("=" * 64)
        try:
            rc = subprocess.call(
                [sys.executable, os.path.join(HERE, s)], timeout=STAGE_TIMEOUT_S
            )
        except subprocess.TimeoutExpired:
            print("")
            print("!! " + s + " 超过 " + str(int(STAGE_TIMEOUT_S)) + " 秒仍未结束：流水线停在这里，不继续跑后面的阶段")
            return 2
        except OSError as error:
            # sys.executable 缺失（嵌入/冻结解释器）也会走到这里：要一条可读的失败，不是栈回溯。
            print("")
            print("!! " + s + " 起不来：" + type(error).__name__ + ": " + str(error))
            return 2
        if rc != 0:
            print("")
            if rc < 0:
                # POSIX 下子进程被信号杀死时 subprocess.call 返回负值（SIGKILL → -9）。
                # 直接把它当退出码返回，sys.exit(-9) 会被操作系统折成 247（256-9），
                # 调用方读到的状态就是错的。按惯例记 128+signal。
                print("!! " + s + " 被信号终止（signal " + str(-rc) + "）：记 128+signal = "
                      + str(128 - rc))
                return 128 - rc
            print("!! " + s + " 失败，退出码 " + str(rc))
            return rc
    print("")
    print("流水线完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
