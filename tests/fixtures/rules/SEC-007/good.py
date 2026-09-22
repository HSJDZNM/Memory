"""SEC-007 正例：用内建库函数代替 OS 命令。"""
# 原文 "### Defense Option 1: Avoid calling OS commands directly" 的首选做法：
#   "Built-in library functions are a very good alternative to OS Commands, as they cannot
#    be manipulated to perform tasks other than those it is intended to do."
# 没有 shell、没有通配符、没有"用户可选的可执行文件"。
import pathlib


def prepare(workdir):
    """创建输出目录，不使用 rm/mkdir 之类的 OS 命令。"""
    workdir.mkdir(exist_ok=True, parents=True)
    return workdir


prepare(pathlib.Path("out"))
