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
    if not todo:
        print("未知阶段: " + args[0])
        print("可用: all, " + ", ".join(s[:2] for s in STAGES))
        return 2
    for s in todo:
        print("")
        print("=" * 64)
        print(">>> " + s)
        print("=" * 64)
        rc = subprocess.call([sys.executable, os.path.join(HERE, s)])
        if rc != 0:
            print("")
            print("!! " + s + " 失败，退出码 " + str(rc))
            return rc
    print("")
    print("流水线完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
