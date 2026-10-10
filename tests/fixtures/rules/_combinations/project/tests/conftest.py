"""夹具项目的测试支撑文件：把 src 加入导入路径。

它**不是**测试文件（不匹配 validation/test-layout.yaml 的 test_patterns），也不是生产文件
（不匹配 production_patterns）——这正是组合语料第一条要压的形状（5.66）。
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
